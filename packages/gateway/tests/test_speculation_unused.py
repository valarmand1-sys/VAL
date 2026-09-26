"""A preparation that lands too late is recorded as unused, never lost — 26 September 2026.

The pilot of that date found the session giving up on an in-flight preparation and
then answering afresh, with the preparation's later result vanishing from the record.
The wait is now long enough that an in-flight preparation is waited for rather than
duplicated; when the bound is passed anyway, the turn proceeds and whatever the
preparation produces is recorded `discarded_unused`.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from test_deliberation_machinery import clean_personas, store
from test_voice_input import MARKER, ScriptedRecognizer, a_conversation, final, started

import val_gateway.voice as voice_module
from val_gateway.voice import VoiceSession


@dataclass(frozen=True)
class _Late:
    """The shape `_discard_speculation` reads from a prepared answer."""

    conversation_id: UUID | None
    utterance_sha256: str
    tier: int
    prepared_ms: int
    response: object | None = None


def test_a_preparation_past_the_bound_is_recorded_unused(
    store: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice_module, "SPECULATION_WAIT_SECONDS", 0.05)
    recognizer = ScriptedRecognizer(batches=[[started(1), final(1, "Good evening, Val.")]])
    conversation = a_conversation(store)
    received: list[object] = []
    release = threading.Event()

    def submit(content: str, existing: UUID | None, **kwargs: object) -> object:
        received.append(kwargs.get("prepared"))
        raise RuntimeError("stop here: the submission itself is not under test")

    def prepare_(content: str, conversation_id: UUID | None) -> object:
        release.wait(5)  # still running when the turn is due
        return _Late(conversation_id, "a" * 64, 1, 1234)

    clock = {"now": 1000.0}
    session = VoiceSession(
        store,
        recognizer,
        submit=submit,  # type: ignore[arg-type]
        conversation_id=conversation,
        clock=lambda: clock["now"],
        prepare=prepare_,
    )
    session.start()
    session.feed(MARKER)
    time.sleep(0.2)  # the preparation thread is under way
    clock["now"] += 5.0
    session.advance()
    session.await_turn(timeout=10)
    assert received == [None], "the turn went on without the preparation"
    release.set()
    deadline = time.monotonic() + 5
    rows: list[tuple[str, int | None]] = []
    while time.monotonic() < deadline and not rows:
        with store.connect() as connection:
            rows = [
                (row[0], row[1])
                for row in connection.execute(
                    text("select outcome, prepared_ms from speculative_preparations")
                ).all()
            ]
        time.sleep(0.05)
    assert rows == [("discarded_unused", 1234)]
    session.close()
