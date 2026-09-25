"""When a voice session primes, and when it must not — owner order, 25 September 2026.

Priming-cache pass §13, §14, §17. The prime is optional maintenance. It starts at
Voice On so it can overlap his speaking, is refreshed after each answer's cognition
while her voice is still being synthesised, and **never starts while a request of
his is waiting** — neither a settled utterance in its resume window nor a turn whose
cognition is under way. One run at a time.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

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
    a_conversation,
    a_session,
    final,
    settle,
    started,
)

from val_gateway.voice import VoiceSession


class Primer:
    """Records each maintenance run and what it was told about his waiting."""

    def __init__(self, hold: threading.Event | None = None) -> None:
        self.runs: list[bool] = []
        self.entered = threading.Event()
        self.hold = hold

    def __call__(self, still_wanted: Callable[[], bool]) -> object:
        self.runs.append(still_wanted())
        self.entered.set()
        if self.hold is not None:
            assert self.hold.wait(10)
        return {"primed": True, "outcome": "established"}


def wait_for(condition: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("never happened")


def test_voice_on_alone_does_not_prime(store: Engine) -> None:  # noqa: F811
    """Priming at Voice On overlapped his speaking and slowed the recognizer."""
    primer = Primer()
    session = VoiceSession(
        store,
        ScriptedRecognizer(batches=[]),
        submit=lambda *a, **k: pytest.fail("nothing was said"),  # type: ignore[arg-type,misc]
        conversation_id=a_conversation(store),
        prime=primer,
    )
    session.start()
    time.sleep(0.2)
    assert primer.runs == []
    session.close()


def test_his_first_settled_utterance_starts_the_first_prime_once(store: Engine) -> None:  # noqa: F811
    recognizer = ScriptedRecognizer(
        batches=[[started(1), final(1, "Good evening, Val.")], [started(2), final(2, "Also this.")]]
    )
    session, _, _clock = a_session(store, recognizer)
    primer = Primer()
    session._prime = primer
    session.feed(MARKER)  # settled: the recognizer's work is done, the window is open
    assert primer.entered.wait(5), "the first prime began in the resume window"
    wait_for(lambda: len(session.primes) == 1)
    assert primer.runs == [True], "his request was not yet submitted"
    assert session.primes[0]["kind"] == "initial"  # type: ignore[index]
    session.feed(MARKER)  # a second settle in the same session starts nothing new
    time.sleep(0.2)
    assert len(primer.runs) == 1
    session.close()


def test_no_maintenance_starts_while_his_utterance_waits(store: Engine) -> None:  # noqa: F811
    recognizer = ScriptedRecognizer(batches=[[started(1), final(1, "Good evening, Val.")]])
    session, _, _clock = a_session(store, recognizer)
    primer = Primer()
    session._prime = primer
    session._initial_prime_started = True  # this test is about the refresh rule alone
    session.feed(MARKER)  # settled, inside the resume window: his request is waiting
    assert session.snapshot().pending == "Good evening, Val."
    session._maintain("refresh")
    time.sleep(0.1)
    assert primer.runs == [], "not started at all"
    session.close()


def test_the_prime_is_refreshed_once_the_turn_is_over_and_not_during_it(
    store: Engine,  # noqa: F811
) -> None:
    recognizer = ScriptedRecognizer(batches=[[started(1), final(1, "Good evening, Val.")]])
    session, _, clock = a_session(
        store, recognizer, adapter=ScriptedAdapter([ok("Good evening, my lord.")])
    )
    busy_when_called: list[bool] = []

    def primer(still_wanted: Callable[[], bool]) -> object:
        # Neither her cognition nor her voice may still be running for his turn.
        busy_when_called.append(session._cognition_busy or session._inflight is not None)
        return {"primed": True, "outcome": "established", "wanted": still_wanted()}

    session._prime = primer
    session._initial_prime_started = True  # this test is about the refresh alone
    session.feed(MARKER)
    settle(session, clock)
    wait_for(lambda: len(session.primes) == 1)
    assert busy_when_called == [False], "after the whole turn, never during any part of it"
    assert session.primes[0]["kind"] == "refresh"  # type: ignore[index]
    session.close()


def test_one_maintenance_run_at_a_time(store: Engine) -> None:  # noqa: F811
    hold = threading.Event()
    primer = Primer(hold=hold)
    session = VoiceSession(
        store,
        ScriptedRecognizer(batches=[]),
        submit=lambda *a, **k: pytest.fail("nothing was said"),  # type: ignore[arg-type,misc]
        conversation_id=a_conversation(store),
        prime=primer,
    )
    session.start()
    session._maintain("refresh")
    assert primer.entered.wait(5)
    session._maintain("refresh")  # while the first is still running
    time.sleep(0.1)
    hold.set()
    wait_for(lambda: len(session.primes) == 1)
    time.sleep(0.1)
    assert len(primer.runs) == 1
    session.close()


def test_a_waiting_request_is_reported_to_a_run_already_under_way(
    store: Engine,  # noqa: F811
) -> None:
    """The gateway asks just before sending; by then he may be waiting."""
    recognizer = ScriptedRecognizer(batches=[[started(1), final(1, "Hello, Val.")]])
    session, _, _clock = a_session(store, recognizer)
    answers: list[bool] = []

    def primer(still_wanted: Callable[[], bool]) -> object:
        session.feed(MARKER)  # he finishes speaking while the prime prepares
        answers.append(still_wanted())
        return {"primed": False, "outcome": "skipped"}

    session._prime = primer
    session._maintain("refresh")
    wait_for(lambda: len(session.primes) == 1)
    assert answers == [False], "the send is not made once his request is waiting"
    session.close()
