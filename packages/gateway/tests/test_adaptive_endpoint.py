"""The adaptive endpoint through the session — owner order of 27 September 2026, §3.

Plainly finished words are submitted after a short window; ambiguous words wait as long
as the fixed path does; and speech that resumes inside the fixed path's silence bound
after an early submission cancels the early turn and joins the two halves into one turn —
never a half-question answered, never a duplicate, never an abandoned request.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

import time
from uuid import UUID

from sqlalchemy import Engine, text
from test_deliberation_machinery import ScriptedAdapter, build_gateway, clean_personas, ok, store
from test_owner_precedence import SlowStreamingAdapter, UnheardDelivery
from test_voice_input import MARKER, ScriptedRecognizer, a_conversation, final, started
from test_voice_presentation import HeldVoice

from val_gateway.deliberate import send
from val_gateway.projects import load_catalogue
from val_gateway.seal import SealRoute
from val_gateway.voice import VoiceSession
from val_policy.turn_completion import COMPLETE_GRACE_S, UNCERTAIN_GRACE_S


def rows(store: Engine, query: str) -> list[tuple]:
    with store.connect() as connection:
        return [tuple(r) for r in connection.execute(text(query)).all()]


def _session(store: Engine, adapter: ScriptedAdapter, batches: list) -> VoiceSession:
    gateway = build_gateway(store, adapter)
    catalogue = load_catalogue(store)

    def submit(content: str, existing: UUID | None, **kwargs: object) -> object:
        return send(
            store,
            gateway,
            content,
            catalogue=catalogue,
            conversation_id=existing,
            spoken=True,
            seal_route=SealRoute.UTTERANCE_FINALIZED,
            on_delta=kwargs.get("on_delta"),  # type: ignore[arg-type]
            cancelled=kwargs.get("cancelled"),  # type: ignore[arg-type]
        )

    def unheard() -> HeldVoice:
        held = UnheardDelivery()
        held.audible = False
        return held

    clock = {"now": 1000.0}
    session = VoiceSession(
        store,
        ScriptedRecognizer(batches=batches),
        submit=submit,  # type: ignore[arg-type]
        conversation_id=a_conversation(store),
        clock=lambda: clock["now"],
        speech=unheard,  # type: ignore[arg-type]
        adaptive_endpoint=True,
    )
    session._clock_box = clock  # type: ignore[attr-defined]
    return session


def test_finished_words_go_after_the_short_window(store: Engine) -> None:
    adapter = ScriptedAdapter([ok("Good evening, my lord.")])
    session = _session(store, adapter, [[started(1), final(1, "Good evening, Val.")]])
    clock = session._clock_box  # type: ignore[attr-defined]
    session.start()
    session.feed(MARKER)
    clock["now"] += COMPLETE_GRACE_S + 0.01
    session.advance()
    assert session._inflight is not None or rows(store, "select count(*) from messages")[0][0]
    session.await_turn(timeout=10)
    assert [r[0] for r in rows(store, "select role::text from messages order by sequence")] == [
        "user",
        "val",
    ]
    session.close()


def test_ambiguous_words_wait_as_long_as_today(store: Engine) -> None:
    adapter = ScriptedAdapter([ok("My lord?")])
    session = _session(store, adapter, [[started(1), final(1, "The venue.")]])
    clock = session._clock_box  # type: ignore[attr-defined]
    session.start()
    session.feed(MARKER)
    clock["now"] += COMPLETE_GRACE_S + 0.01
    session.advance()
    assert session._inflight is None and session._pending is not None, "not yet"
    clock["now"] += UNCERTAIN_GRACE_S
    session.advance()
    session.await_turn(timeout=10)
    assert rows(store, "select count(*) from messages where role = 'val'")[0][0] == 1
    session.close()


def test_a_resumption_after_an_early_submission_joins_the_halves(store: Engine) -> None:
    adapter = SlowStreamingAdapter(
        [
            ok(" ".join(["invitation"] * 60)),
            ok("The invitation and the venue, my lord: both are in hand."),
        ],
        delay=0.05,
    )
    session = _session(
        store,
        adapter,
        [
            [
                started(1, at=10.0),
                final(1, "Tell me about the invitation.", at=11.6, endpoint_at=11.5),
            ],
            [started(2, at=12.2)],
            [final(2, "And the venue as well.", at=13.4, endpoint_at=13.3)],
        ],
    )
    clock = session._clock_box  # type: ignore[attr-defined]
    session.start()
    session.feed(MARKER)
    clock["now"] += COMPLETE_GRACE_S + 0.01
    session.advance()  # submitted early: plainly finished words
    time.sleep(0.3)
    session.feed(MARKER)  # he resumes 0.7 s after the endpoint: inside the bound
    assert session.speech_hold, "nothing of the early answer is handed over while he speaks"
    session.feed(MARKER)  # the rest settles
    for _ in range(80):
        session.advance()
        clock["now"] += 0.5
        if rows(store, "select count(*) from messages where role = 'val'")[0][0] >= 1:
            break
        time.sleep(0.05)
    session.await_turn(timeout=15)
    got = rows(
        store,
        "select m.role::text, mc.content, m.id in (select message_id from message_revisions "
        "where kind::text = 'retraction') from messages m join messages_current mc on mc.id = m.id "
        "order by m.sequence",
    )
    assert [(r[0], r[2]) for r in got] == [("user", True), ("user", False), ("val", False)], got
    assert got[1][1] == "Tell me about the invitation. And the venue as well."
    assert got[2][1].startswith("The invitation and the venue")
    assert adapter.released == [True], "the early call was cancelled, once"
    session.close()


def test_speech_resuming_after_the_bound_is_its_own_turn(store: Engine) -> None:
    adapter = SlowStreamingAdapter(
        [ok(" ".join(["invitation"] * 20)), ok("The venue, my lord.")], delay=0.02
    )
    session = _session(
        store,
        adapter,
        [
            [
                started(1, at=10.0),
                final(1, "Tell me about the invitation.", at=11.6, endpoint_at=11.5),
            ],
            [started(2, at=14.0)],
            [final(2, "What about the venue?", at=15.2, endpoint_at=15.1)],
        ],
    )
    clock = session._clock_box  # type: ignore[attr-defined]
    session.start()
    session.feed(MARKER)
    clock["now"] += COMPLETE_GRACE_S + 0.01
    session.advance()
    time.sleep(0.1)
    session.feed(MARKER)
    session.feed(MARKER)
    for _ in range(120):
        session.advance()
        clock["now"] += 0.5
        if rows(store, "select count(*) from messages where role = 'val'")[0][0] >= 2:
            break
        time.sleep(0.05)
    session.await_turn(timeout=15)
    got = rows(store, "select role::text from messages order by sequence")
    assert [r[0] for r in got] == ["user", "val", "user", "val"], got
    assert adapter.released == []
    session.close()
