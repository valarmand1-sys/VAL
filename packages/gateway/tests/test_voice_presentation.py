"""The session says his words are canonical while she is still thinking.

Owner diagnostic, 25 September 2026. The session learned that a spoken turn existed
only when `submit` returned — after her answer was written and her voice had
synthesised it — and exposed nothing before then; for a brand-new chat it did not
even know which conversation to name. These tests hold the session's own view to
the commit, with cognition deliberately held, and hold the per-turn timeline line
that his run lacked.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy import Engine
from test_deliberation_machinery import (  # noqa: F401 - pytest fixtures by injection
    ScriptedAdapter,
    clean_personas,
    ok,
    store,
)
from test_voice_input import (
    MARKER,
    ScriptedRecognizer,
    a_session,
    final,
    messages_of,
    settle,
    started,
)

from val_gateway.voice import VoiceSessionState


@dataclass
class HeldAdapter(ScriptedAdapter):
    """Answers from its script, once the test lets it."""

    entered: threading.Event = field(default_factory=threading.Event)
    release: threading.Event = field(default_factory=threading.Event)

    def complete(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        self.entered.set()
        assert self.release.wait(30), "the test never released cognition"
        return super().complete(*args, **kwargs)


def test_the_commit_is_visible_in_the_session_before_cognition_returns(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    adapter = HeldAdapter([ok("Good evening, my lord.")])
    recognizer = ScriptedRecognizer(
        batches=[[started(1, at=10.0), final(1, "Good evening, Val.", at=11.6, endpoint_at=11.2)]]
    )
    session, _, clock = a_session(store, recognizer, adapter=adapter)
    session.feed(MARKER)
    clock.tick(5.0)
    session.advance()  # the resume window has passed: the turn is submitted

    assert adapter.entered.wait(10), "cognition began"
    deadline = time.monotonic() + 10
    view = session.snapshot()
    while view.committed is None and time.monotonic() < deadline:
        time.sleep(0.01)
        view = session.snapshot()

    # Cognition has not returned, and the session already names his message.
    assert not adapter.release.is_set()
    assert view.committed is not None
    assert view.turns == ()
    assert view.state is VoiceSessionState.THINKING
    assert view.conversation_id == view.committed.conversation_id
    assert messages_of(store, view.committed.conversation_id) == ["Good evening, Val."]

    adapter.release.set()
    settle(session, clock)
    answered = session.snapshot()
    assert answered.committed == view.committed, "the same message, not a second one"
    assert [turn.message_id for turn in answered.turns] == [view.committed.message_id]
    session.close()


def test_every_spoken_turn_writes_one_timeline_line(
    store: Engine,  # noqa: F811 - pytest fixture injection
    caplog: pytest.LogCaptureFixture,
) -> None:
    recognizer = ScriptedRecognizer(batches=[[started(1), final(1, "Good evening, Val.")]])
    session, _, clock = a_session(
        store, recognizer, adapter=ScriptedAdapter([ok("Good evening, my lord.")])
    )
    with caplog.at_level(logging.INFO, logger="val.voice"):
        session.feed(MARKER)
        settle(session, clock)
    lines = [r.getMessage() for r in caplog.records if "voice turn timeline" in r.getMessage()]
    assert len(lines) == 1
    record = json.loads(lines[0].split("voice turn timeline: ", 1)[1])
    marks = record["marks"]
    # The boundaries his run could not supply, each with a time.
    for name in ("owner_message_committed", "message_persisted", "turn_start"):
        assert name in marks, name
    assert marks["owner_message_committed"]["count"] == 1
    assert record["message_id"] is not None
    assert record["anchor_wall"].endswith("+00:00")
    # Nothing he said is in it.
    assert "Good evening" not in lines[0]
    session.close()


class HeldVoice:
    """A delivery whose voice has not finished: `finish` waits until the test says so."""

    def __init__(self) -> None:
        self.finishing = threading.Event()
        self.release = threading.Event()
        self.audible = True
        self.bound: object = None

    def feed(self, text: str) -> None:
        pass

    def bind(self, message_id: object) -> None:
        self.bound = message_id

    def finish(self, text: str) -> None:
        self.finishing.set()
        assert self.release.wait(30), "the test never let her voice finish"

    def record_segments(self) -> None:
        pass

    def interrupt(self, reason: str) -> None:
        pass


def test_her_answer_is_announced_before_her_voice_has_finished(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    """Voice-mode repair §4, 25 September 2026.

    The desktop read her answer only when `turns` learned of it — after every segment
    had been synthesised — so her text arrived mid-way through a two-segment answer.
    The session now names her answer the moment Core has written it.
    """
    recognizer = ScriptedRecognizer(batches=[[started(1), final(1, "Good evening, Val.")]])
    session, _, clock = a_session(
        store, recognizer, adapter=ScriptedAdapter([ok("Good evening, my lord.")])
    )
    voice = HeldVoice()
    session._speech = lambda: voice  # type: ignore[assignment,return-value]
    session.feed(MARKER)
    clock.tick(5.0)
    session.advance()
    assert voice.finishing.wait(10), "her voice began"

    view = session.snapshot()
    assert view.turns == (), "the turn is not over: her voice is still being made"
    assert view.answered is not None
    assert view.answered.message_id == voice.bound, "the answer her voice speaks"
    assert view.committed is not None
    assert view.answered.utterance == view.committed.utterance
    assert messages_of(store, view.answered.conversation_id) == [
        "Good evening, Val.",
        "Good evening, my lord.",
    ]

    voice.release.set()
    settle(session, clock)
    assert [turn.answer_message_id for turn in session.snapshot().turns] == [voice.bound]
    session.close()
