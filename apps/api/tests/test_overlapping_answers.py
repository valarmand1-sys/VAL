"""Interruption across overlapping answers — owner order of 1 October 2026.

The physical check of 30 September: a 25-second answer was playing, a newer answer was
being prepared for words he had spoken before it began, and three interjections did not
stop her — each was recorded and answered after the long answer had played through. The
session held one answer "in flight" and could no longer reach the one that was sounding.

These drive the real application the way the desktop does — audio in, the session poll,
the speech poll, the playback reports — with the release's three switches on: owner
precedence, the adaptive endpoint and combined continuations.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

import time

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from test_service import OpenLedger, ScriptedAdapter, ok
from test_voice_service import (
    PCM,
    ScriptedRecognizer,
    ScriptedVoiceProvider,
    a_governed_voice,
    final,
    started,
)

from val_api.app import create_app
from val_gateway.gateway import Gateway
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader
from val_gateway.provenance import verifier
from val_gateway.speech import register_voice

BARN = (
    "The barn stands at the east end of the lower field, my lord, where the lane turns. "
    "It was built for hay and has held everything since, from a threshing floor to a dance. "
    "The roof was renewed two summers ago and the doors hang true again. "
    "It will seat a hundred and twenty at long tables with room left for the band."
)
ORCHARD = "The orchard is in its second leaf, my lord, and the pears are ahead of the apples."


def _client(store: Engine, adapter: ScriptedAdapter, recognizer: ScriptedRecognizer) -> TestClient:
    voice = a_governed_voice()
    register_voice(
        store,
        voice,
        described={
            "reference_sample_rate": 24000,
            "reference_duration_seconds": 18.756,
            "designed_by_quantization": "8-bit MLX",
            "designed_by_runtime": "mlx-audio 0.5.5",
            "designed_generation": {},
            "origin": "owner-authorised established reference",
            "identity_claim": "not model-verified",
        },
    )
    gateway = Gateway(
        adapters={"anthropic": adapter, "openai": adapter, "lmstudio": adapter},
        recorder=lambda record: record_call(store, record),
        ledger=OpenLedger(),
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(store),
        verify_provenance=verifier(store),
        speech=ScriptedVoiceProvider(),  # type: ignore[arg-type]
        voice=voice,
    )
    return TestClient(
        create_app(
            store,
            gateway,
            warnings=[],
            recognizers=lambda: recognizer,
            owner_precedence=True,
            adaptive_endpoint=True,
            combine_continuations=True,
        )
    )


def _hear(reachable: TestClient, session: str) -> None:
    """One audio frame: the recognizer releases its next scripted batch."""
    reachable.post(
        f"/voice/sessions/{session}/audio",
        content=PCM,
        headers={"content-type": "application/octet-stream"},
    )


def _view(reachable: TestClient, session: str) -> dict:
    return reachable.get(f"/voice/sessions/{session}").json()


def _turns(reachable: TestClient, session: str, count: int, seconds: float = 12.0) -> dict:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        view = _view(reachable, session)
        assert not view["error"], view["error"]
        if len(view["turns"]) >= count:
            return view
        time.sleep(0.05)
    raise AssertionError(f"{count} turn(s) never settled: {len(_view(reachable, session)['turns'])}")


def _offer(reachable: TestClient, session: str) -> dict:
    return reachable.get(f"/voice/sessions/{session}/speech/next").json()


def _collect(reachable: TestClient, session: str, seconds: float = 4.0) -> list[dict]:
    """Poll the way the desktop does for a while; every offer that carried something."""
    seen: list[dict] = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        offer = _offer(reachable, session)
        if offer["stop"] or offer["segment"] is not None:
            seen.append(offer)
        if offer.get("all_offered"):
            break
        time.sleep(0.02)
    return seen


def _report(reachable: TestClient, session: str, message: str, index: int, state: str) -> int:
    body = {"message_id": message, "segment_index": index, "state": state}
    if state == "playback_interrupted":
        body["reason"] = "the owner began speaking"
    return reachable.post(f"/voice/sessions/{session}/speech/played", json=body).status_code


def _answer_id(view: dict, turn: int) -> str:
    return view["turns"][turn]["answer"]["val_message"]["id"]


def _segments_of(offers: list[dict], message: str) -> list[int]:
    return sorted(
        {
            o["segment"]["segment_index"]
            for o in offers
            if o["segment"] is not None and o["segment"]["message_id"] == message
        }
    )


def _deliveries(store: Engine, message: str) -> list[tuple[str, int, int | None, str | None]]:
    with store.connect() as connection:
        return [
            (row.state, row.segments_delivered, row.segments_total, row.reason)
            for row in connection.execute(
                text(
                    "select state, segments_delivered, segments_total, reason "
                    "  from speech_deliveries where message_id = :id order by event"
                ),
                {"id": message},
            )
        ]


def _val_messages(store: Engine) -> int:
    with store.connect() as connection:
        return connection.execute(
            text("select count(*) from messages where role = 'val'")
        ).scalar_one()


def test_his_voice_stops_the_answer_that_is_playing_while_a_newer_one_waits(
    store: Engine,
) -> None:
    """The 30 September sequence, and the stop that should have ended it."""
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1), final("Tell me about the barn.", 1)],
            [started(2), final("What about the orchard?", 2)],  # before any of A is heard
            [started(3)],  # his voice, while A is playing
            [final("Stop.", 3)],
            [started(4), final("Stop.", 4)],  # and again
        ]
    )
    adapter = ScriptedAdapter([ok(BARN), ok(ORCHARD)])
    with _client(store, adapter, recognizer) as reachable:
        session = reachable.post("/voice/sessions", json={"project": "Project Alpha"}).json()[
            "session"
        ]
        _hear(reachable, session)
        barn = _answer_id(_turns(reachable, session, 1), 0)
        # He speaks again before any of her answer has been handed over.
        _hear(reachable, session)
        orchard = _answer_id(_turns(reachable, session, 2), 1)

        # The older answer is the one handed over; the newer waits behind it, whole.
        offers = _collect(reachable, session)
        assert _segments_of(offers, barn), "the barn answer is being handed over"
        assert _segments_of(offers, orchard) == [], "nothing of the newer answer yet"
        first = _segments_of(offers, barn)[0]
        assert _report(reachable, session, barn, first, "playback_started") == 200
        barn_total = len(_segments_of(offers, barn))
        assert barn_total >= 2, "a long answer, in several segments"
        waiting = [_offer(reachable, session) for _ in range(5)]
        assert all(o["segment"] is None and not o["stop"] for o in waiting)

        # His voice, while the barn answer plays and the orchard answer exists.
        _hear(reachable, session)
        stop = _offer(reachable, session)
        assert stop["stop"] is True, "the answer that is sounding is stopped"
        assert stop["message_id"] == barn, "and it is the one that was playing"
        assert _report(reachable, session, barn, first, "playback_interrupted") == 200
        again = [_offer(reachable, session) for _ in range(5)]
        assert not any(o["stop"] for o in again), "told once"
        assert all(o["segment"] is None for o in again), "the newer answer is held while he speaks"

        # "Stop." — the queued answer is set aside and nothing new is said.
        _hear(reachable, session)
        _turns(reachable, session, 3)
        after = _collect(reachable, session, seconds=1.0)
        assert _segments_of(after, orchard) == [], "the stopped answer never plays later"
        assert not any(o["stop"] for o in after)

        # A second "Stop." is the same stop: recorded, not answered.
        _hear(reachable, session)
        view = _turns(reachable, session, 4)
        assert _collect(reachable, session, seconds=1.0) == []

        barn_delivery = reachable.get(f"/messages/{barn}/delivery").json()
        orchard_delivery = reachable.get(f"/messages/{orchard}/delivery").json()

    assert adapter.calls == 2, "two answers were asked for; neither stop was answered"
    assert _val_messages(store) == 2
    heard = [turn["text"] for turn in view["turns"]]
    assert heard == ["Tell me about the barn.", "What about the orchard?", "Stop.", "Stop."], (
        "every utterance kept, in order"
    )
    assert view["turns"][2]["answer"].get("val_message") is None
    assert view["turns"][3]["answer"].get("val_message") is None

    # The record says what the player says.
    assert barn_delivery["state"] == "interrupted"
    assert barn_delivery["segments_delivered"] == 1
    assert barn_delivery["completed_as_heard"] is False
    assert f"segment {first} was cut off while playing" in barn_delivery["reason"]
    assert "never played" in barn_delivery["reason"]
    assert orchard_delivery["state"] == "interrupted"
    assert orchard_delivery["segments_delivered"] == 0, "none of it is recorded as heard"
    assert orchard_delivery["completed_as_heard"] is False


def test_speech_at_the_playback_start_boundary_stops_her_and_late_reports_restart_nothing(
    store: Engine,
) -> None:
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1), final("Tell me about the barn.", 1)],
            [started(2)],  # the instant her first piece has been handed over
            [final("Actually, never mind. Tell me about the orchard instead.", 2)],
        ]
    )
    adapter = ScriptedAdapter([ok(BARN), ok(ORCHARD)])
    with _client(store, adapter, recognizer) as reachable:
        session = reachable.post("/voice/sessions", json={"project": "Project Alpha"}).json()[
            "session"
        ]
        _hear(reachable, session)
        barn = _answer_id(_turns(reachable, session, 1), 0)
        first = None
        deadline = time.monotonic() + 5
        while first is None and time.monotonic() < deadline:
            offer = _offer(reachable, session)
            first = offer["segment"]
            time.sleep(0.02)
        assert first is not None and first["message_id"] == barn
        # No playback report has arrived yet: the piece left for the desktop this instant.
        _hear(reachable, session)
        stop = _offer(reachable, session)
        assert stop["stop"] is True and stop["message_id"] == barn

        # Late events from the stopped answer.
        assert _report(reachable, session, barn, first["segment_index"], "playback_started") == 200
        assert (
            _report(reachable, session, barn, first["segment_index"], "playback_interrupted")
            == 200
        )
        late = [_offer(reachable, session) for _ in range(5)]
        assert not any(o["stop"] for o in late), "a late report does not stop her again"
        assert all(o["segment"] is None for o in late), "and nothing of the stopped answer returns"

        # The replacement is answered, and its answer plays.
        _hear(reachable, session)
        view = _turns(reachable, session, 2)
        orchard = _answer_id(view, 1)
        offers = _collect(reachable, session)
        assert _segments_of(offers, orchard), "the replacement's answer is handed over"
        assert _segments_of(offers, barn) == [], "the stopped answer is not"
        assert not any(o["stop"] for o in offers)
        barn_delivery = reachable.get(f"/messages/{barn}/delivery").json()

    assert barn_delivery["state"] == "interrupted"
    assert barn_delivery["segments_delivered"] == 1


def test_a_replacement_sets_aside_a_finished_answer_he_has_not_heard(store: Engine) -> None:
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1), final("Tell me about the barn.", 1)],
            [started(2), final("No, tell me about the orchard.", 2)],
        ]
    )
    adapter = ScriptedAdapter([ok(BARN), ok(ORCHARD)])
    with _client(store, adapter, recognizer) as reachable:
        session = reachable.post("/voice/sessions", json={"project": "Project Alpha"}).json()[
            "session"
        ]
        _hear(reachable, session)
        barn = _answer_id(_turns(reachable, session, 1), 0)
        _hear(reachable, session)
        orchard = _answer_id(_turns(reachable, session, 2), 1)
        offers = _collect(reachable, session)
        barn_delivery = reachable.get(f"/messages/{barn}/delivery").json()

    assert _segments_of(offers, barn) == [], "the replaced answer is never spoken"
    assert _segments_of(offers, orchard), "the replacement's answer is"
    assert not any(o["stop"] for o in offers), "nothing was at the desktop to stop"
    assert barn_delivery["state"] == "interrupted"
    assert barn_delivery["segments_delivered"] == 0
    assert "before any of it was heard" in barn_delivery["reason"]


def test_a_continuation_keeps_the_unheard_answer_and_a_held_poll_closes_nothing(
    store: Engine,
) -> None:
    """Her earlier answer plays whole, then the answer to what he added. And the defect
    behind the record that read `completed 6/6`: a poll held for his words carried no
    segment while the delivery read `completed`, and the desktop took that for the end."""
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1), final("Tell me about the barn.", 1)],
            [started(2)],
            [final("And also the orchard.", 2)],
        ]
    )
    adapter = ScriptedAdapter([ok(BARN), ok(ORCHARD)])
    with _client(store, adapter, recognizer) as reachable:
        session = reachable.post("/voice/sessions", json={"project": "Project Alpha"}).json()[
            "session"
        ]
        _hear(reachable, session)
        barn = _answer_id(_turns(reachable, session, 1), 0)
        _hear(reachable, session)  # he begins to speak before any of it is handed over
        held = [_offer(reachable, session) for _ in range(5)]
        assert all(o["segment"] is None and not o["stop"] for o in held)
        assert all(o["delivery_state"] == "held" for o in held), held
        assert not any(o.get("all_offered") for o in held), "a held answer is not an ended one"
        _hear(reachable, session)
        orchard = _answer_id(_turns(reachable, session, 2), 1)

        offers = _collect(reachable, session, seconds=6.0)
        barn_segments = _segments_of(offers, barn)
        for index in barn_segments:
            assert _report(reachable, session, barn, index, "playback_started") == 200
            assert _report(reachable, session, barn, index, "playback_completed") == 200
        rest = _collect(reachable, session, seconds=6.0)
        barn_delivery = reachable.get(f"/messages/{barn}/delivery").json()

    assert barn_delivery["segments_total"] == len(barn_segments), "every segment was handed over"
    assert barn_delivery["state"] == "completed"
    assert barn_delivery["player"] == "confirmed"
    assert barn_delivery["completed_as_heard"] is True
    assert _segments_of(offers, orchard) == [], "the newer answer waits for the older to finish"
    assert _segments_of(rest, orchard), "and then it is spoken"
