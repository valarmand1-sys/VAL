"""His words are shown while she is still thinking — owner diagnostic, 25 September 2026.

He said "Good evening, Val." and saw nothing of it until her answer appeared,
twice now. The previous repair taught the desktop to re-read the conversation "as
soon as a canonical owner turn exists" — but it keyed on the session's `turns`,
and the session appended a turn only when `submit` returned, which is after her
answer was written and her voice had synthesised it. The trigger could not fire
early, and the test for it asserted a callback over a script, not what the service
returned. The service log of his run shows it: one conversation read in the whole
session, returned after she had begun to speak.

These tests hold the service to the boundary that failed, against the real
application and real PostgreSQL, **with cognition deliberately held**:

- the session poll names his committed message while the provider has not
  returned, and
- a conversation read issued then **returns** — with his message and without an
  answer — before cognition completes; it is not merely issued.

A second failure mode is held too, because the owner's order named it as a
candidate: a read that is issued on time and cannot return. The audio route did
its recognizer work synchronously on the event loop, so a slow block of audio
held every other request — conversation reads included — until it finished.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from test_service import ScriptedAdapter, ok
from test_voice_service import PCM, ScriptedRecognizer, final, started, voice_client


@dataclass
class HeldAdapter(ScriptedAdapter):
    """Answers from its script — but only once the test lets it."""

    entered: threading.Event = field(default_factory=threading.Event)
    release: threading.Event = field(default_factory=threading.Event)

    def complete(self, *args: object, **kwargs: object) -> object:
        self.entered.set()
        assert self.release.wait(30), "the test never released cognition"
        return super().complete(*args, **kwargs)  # type: ignore[arg-type]


def poll_until(
    service: TestClient, key: str, ready: Callable[[dict], bool], timeout: float = 10.0
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        view = service.get(f"/voice/sessions/{key}").json()
        if ready(view):
            return view
        time.sleep(0.02)
    raise AssertionError(f"the session never reached the expected state: {view}")


def speak(service: TestClient, key: str) -> None:
    response = service.post(
        f"/voice/sessions/{key}/audio",
        content=PCM,
        headers={"content-type": "application/octet-stream"},
    )
    assert response.status_code == 200


def test_his_message_is_returned_to_the_desktop_while_cognition_is_unfinished(
    store: Engine,
) -> None:
    adapter = HeldAdapter([ok("Good evening, my lord.")])
    recognizer = ScriptedRecognizer(batches=[[started(), final("Good evening, Val.")]])
    with voice_client(store, adapter, recognizer) as service:
        # A brand-new chat, exactly as in his diagnostic: no conversation exists
        # until his words create one.
        key = service.post("/voice/sessions", json={"no_project": True}).json()["session"]
        speak(service, key)

        view = poll_until(service, key, lambda v: v["committed"] is not None)
        assert adapter.entered.wait(10), "cognition never began"
        # Cognition is running and has not returned.
        assert not adapter.release.is_set()
        assert view["turns"] == [], "no answered exchange exists yet"
        committed = view["committed"]
        assert view["conversation_id"] == committed["conversation_id"]

        # The read the desktop issues now RETURNS, with his words and no answer.
        read = service.get(f"/conversations/{committed['conversation_id']}")
        assert read.status_code == 200
        messages = read.json()["messages"]
        assert [(m["role"], m["content"]) for m in messages] == [("user", "Good evening, Val.")]
        assert messages[0]["id"] == committed["message_id"]
        assert not adapter.release.is_set(), "all of that happened while she was thinking"

        adapter.release.set()
        answered = poll_until(service, key, lambda v: len(v["turns"]) == 1)
        # The same message, not a second copy of it; the answer once.
        assert answered["committed"] == committed
        after = service.get(f"/conversations/{committed['conversation_id']}").json()["messages"]
        assert [(m["role"], m["content"]) for m in after] == [
            ("user", "Good evening, Val."),
            ("val", "Good evening, my lord."),
        ]
        assert len({m["id"] for m in after}) == 2
        service.post(f"/voice/sessions/{key}/close")


@dataclass
class SlowRecognizer(ScriptedRecognizer):
    """A recognizer whose next hand-over blocks, as a full pipe to a busy helper does."""

    hold: threading.Event = field(default_factory=threading.Event)
    holding: threading.Event = field(default_factory=threading.Event)
    block_next: bool = False

    def feed(self, pcm: bytes) -> None:
        if self.block_next:
            self.block_next = False
            self.holding.set()
            assert self.hold.wait(30), "the test never released the recognizer"
        super().feed(pcm)


def test_a_slow_block_of_audio_does_not_hold_a_conversation_read(store: Engine) -> None:
    adapter = ScriptedAdapter([ok("Good evening, my lord."), ok("Indeed.")])
    recognizer = SlowRecognizer(
        batches=[[started(), final("Good evening, Val.")], [], [], []],
    )
    with voice_client(store, adapter, recognizer) as service:
        key = service.post("/voice/sessions", json={"no_project": True}).json()["session"]
        speak(service, key)
        view = poll_until(service, key, lambda v: len(v["turns"]) == 1)
        conversation = view["conversation_id"]

        recognizer.block_next = True
        feeding = threading.Thread(target=speak, args=(service, key), daemon=True)
        feeding.start()
        assert recognizer.holding.wait(10), "the audio route never reached the recognizer"

        returned: list[int] = []
        reader = threading.Thread(
            target=lambda: returned.append(
                service.get(f"/conversations/{conversation}").status_code
            ),
            daemon=True,
        )
        reader.start()
        reader.join(timeout=5)
        try:
            assert returned == [200], (
                "a conversation read did not return while one audio block was being "
                "handed to the recognizer: the audio route is holding the event loop"
            )
        finally:
            recognizer.hold.set()
            feeding.join(timeout=10)
            reader.join(timeout=10)
        service.post(f"/voice/sessions/{key}/close")


# --- owner Step B retest, 25 September 2026: the owner-facing intervals ---------------


def test_the_session_says_how_long_ago_his_speech_ended(store: Engine) -> None:
    from val_domain.voice import RecognizerEvent

    ended = RecognizerEvent(
        kind="final",
        session=1,
        text="Good evening, Val.",
        reason="silence",
        at=11.6,
        endpoint_at=11.2,
        silence_seconds=0.672,
        received_at=time.monotonic(),
    )
    adapter = ScriptedAdapter([ok("Good evening, my lord.")])
    recognizer = ScriptedRecognizer(batches=[[started(), ended]])
    with voice_client(store, adapter, recognizer) as service:
        key = service.post("/voice/sessions", json={"no_project": True}).json()["session"]
        speak(service, key)
        view = poll_until(service, key, lambda v: v["speech_end"] is not None)
        # The endpoint was 0.4 s before receipt and the silence confirming it 0.672 s:
        # speech ended at least 1.072 s before this response. An estimate, labelled so.
        assert view["speech_end"]["utterance"] == 1
        assert view["speech_end"]["ms_ago"] >= 1072
        poll_until(service, key, lambda v: len(v["turns"]) == 1)
        service.post(f"/voice/sessions/{key}/close")


def test_the_desktop_s_intervals_are_logged_as_numbers_and_nothing_else(
    store: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    recognizer = ScriptedRecognizer(batches=[])
    with voice_client(store, ScriptedAdapter([]), recognizer) as service:
        key = service.post("/voice/sessions", json={"no_project": True}).json()["session"]
        report = {
            "utterance": 1,
            "speech_end_to_owner_message_dom_ms": 2150,
            "owner_message_dom_to_playback_start_ms": 14250,
            "speech_end_to_playback_start_ms": 16400,
            "committed_seen_to_owner_message_dom_ms": 30,
        }
        with caplog.at_level(logging.INFO, logger="val.api"):
            assert service.post(f"/voice/sessions/{key}/timings", json=report).status_code == 204
        logged = [
            r.getMessage() for r in caplog.records if "voice desktop timing" in r.getMessage()
        ]
        assert len(logged) == 1 and "16400" in logged[0]
        refused = service.post(
            f"/voice/sessions/{key}/timings", json={**report, "text": "Good evening, Val."}
        )
        assert refused.status_code == 422, "nothing but the numbers is accepted"
        unknown = service.post(f"/voice/sessions/{uuid4()}/timings", json=report)
        assert unknown.status_code == 404
        service.post(f"/voice/sessions/{key}/close")
