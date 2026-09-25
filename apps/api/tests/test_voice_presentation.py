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

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

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
