"""Readiness said component by component, primes at Voice On, refreshes only when idle —
owner order of 26 September 2026, Milestone A §2 and §3.

"Ready" used to mean the session existed and the microphone was live. Now the session
reports what is actually warm: the cognition runtime, the voice worker, the Partner
prefix, the light prefix. The first prime runs at Voice On unless he is already
speaking; a refresh after a turn waits for the session to fall idle, is coalesced, and
re-primes only the effort the turn did not use.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

import threading
import time
from uuid import UUID

import pytest
from sqlalchemy import Engine
from test_deliberation_machinery import clean_personas, store
from test_voice_input import MARKER, ScriptedRecognizer, a_conversation, final, started

import val_gateway.voice as voice_module
from val_gateway.voice import VoiceReadiness, VoiceSession

ESTABLISHED = {"primed": True, "outcome": "established", "slug": "partner"}
LIGHT_ESTABLISHED = {"primed": True, "outcome": "established", "slug": "low"}


def wait_for(predicate, timeout: float = 5.0) -> bool:  # noqa: ANN001
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def test_readiness_is_warming_until_the_warm_up_and_both_primes_report(store: Engine) -> None:
    primes: list[tuple[str, ...] | None] = []
    warmed = threading.Event()

    def warm() -> object:
        warmed.wait(2)
        return {"cognition": {"warmed": True}, "voice": {"warmed": True}}

    def prime(still_wanted, routes=("partner", "light")) -> object:  # noqa: ANN001
        primes.append(tuple(routes))
        return {**ESTABLISHED, "light": LIGHT_ESTABLISHED}

    session = VoiceSession(
        store,
        ScriptedRecognizer(batches=[]),
        submit=lambda *a, **k: None,  # type: ignore[arg-type]
        conversation_id=a_conversation(store),
        warm=warm,
        prime=prime,
        speech=object(),  # type: ignore[arg-type]
    )
    session.start()
    assert session.snapshot().readiness.ready is False
    assert session.snapshot().readiness.cognition == "warming"
    warmed.set()
    assert wait_for(lambda: session.snapshot().readiness.ready), session.snapshot().readiness
    record = session.snapshot().readiness.as_record()
    assert record == {
        "ready": True,
        "cognition": "ready",
        "voice": "ready",
        "prefix_partner": "primed",
        "prefix_light": "primed",
        "detail": None,
    }
    assert primes == [("partner", "light")], "one initial prime of both entries at Voice On"
    session.close()


def test_a_failed_component_is_shown_as_failed_not_ready(store: Engine) -> None:
    session = VoiceSession(
        store,
        ScriptedRecognizer(batches=[]),
        submit=lambda *a, **k: None,  # type: ignore[arg-type]
        conversation_id=a_conversation(store),
        warm=lambda: {
            "cognition": {"warmed": True},
            "voice": {"warmed": False, "reason": "the voice worker did not start"},
        },
        prime=lambda still_wanted, routes=("partner", "light"): ESTABLISHED,
        speech=object(),  # type: ignore[arg-type]
    )
    session.start()
    assert wait_for(lambda: session.snapshot().readiness.prefix_partner == "primed")
    readiness = session.snapshot().readiness
    assert readiness.voice == "failed"
    assert readiness.ready is False and readiness.detail == "the voice worker did not start"
    assert readiness.prefix_light == "not_applicable"
    session.close()


def test_the_initial_prime_stands_aside_while_he_is_speaking(store: Engine) -> None:
    primes: list[float] = []
    recognizer = ScriptedRecognizer(batches=[[started(1)]])
    spoken = threading.Event()

    def warm() -> object:
        spoken.wait(2)  # warming finishes after he has begun to speak
        return {"cognition": {"warmed": True}}

    session = VoiceSession(
        store,
        recognizer,
        submit=lambda *a, **k: None,  # type: ignore[arg-type]
        conversation_id=a_conversation(store),
        warm=warm,
        prime=lambda still_wanted, routes=("partner", "light"): (
            primes.append(time.monotonic()) or ESTABLISHED
        ),
    )
    session.start()
    session.feed(MARKER)  # he is speaking: the recognizer has an utterance open
    spoken.set()
    assert wait_for(lambda: session.snapshot().readiness.cognition == "ready")
    time.sleep(0.3)
    assert primes == [], "no prime while he is speaking"
    assert session.snapshot().readiness.prefix_partner == "skipped"
    session.close()


def test_a_refresh_waits_for_idleness_coalesces_and_primes_both_entries(
    store: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice_module, "REFRESH_IDLE_SECONDS", 0.2)
    primes: list[tuple[str, ...]] = []

    def prime(still_wanted, routes=("partner", "light")) -> object:  # noqa: ANN001
        primes.append(tuple(routes))
        return {**ESTABLISHED, "light": LIGHT_ESTABLISHED}

    session = VoiceSession(
        store,
        ScriptedRecognizer(batches=[]),
        submit=lambda *a, **k: None,  # type: ignore[arg-type]
        conversation_id=a_conversation(store),
        prime=prime,
    )
    session.start()
    assert wait_for(lambda: len(primes) == 1)  # the initial prime
    # Two turns finishing close together owe one refresh; the last used the light route.
    session._last_turn_task = "light_conversation"
    session._schedule_refresh()
    session._schedule_refresh()
    assert wait_for(lambda: len(primes) == 2, timeout=3.0), primes
    time.sleep(0.5)
    assert primes == [("partner", "light"), ("light", "partner")], (
        "one coalesced refresh of both entries, light first, Partner last"
    )
    session.close()


def test_a_refresh_is_held_while_he_is_speaking(
    store: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice_module, "REFRESH_IDLE_SECONDS", 0.2)
    primes: list[tuple[str, ...]] = []
    recognizer = ScriptedRecognizer(batches=[[started(1)]])
    session = VoiceSession(
        store,
        recognizer,
        submit=lambda *a, **k: None,  # type: ignore[arg-type]
        conversation_id=a_conversation(store),
        prime=lambda still_wanted, routes=("partner", "light"): (
            primes.append(tuple(routes)) or ESTABLISHED
        ),
    )
    session.start()
    assert wait_for(lambda: len(primes) == 1)
    session.feed(MARKER)  # speaking
    session._last_turn_task = "conversation"
    session._schedule_refresh()
    time.sleep(0.8)
    assert len(primes) == 1, "no refresh while his words are being heard"
    session.close()


def test_a_turn_in_cognition_before_readiness_is_shown_as_warming(store: Engine) -> None:
    hold = threading.Event()

    def submit(content: str, existing: UUID | None, **kwargs: object) -> object:
        hold.wait(5)
        raise RuntimeError("stop here")

    recognizer = ScriptedRecognizer(batches=[[started(1), final(1, "Good evening, Val.")]])
    clock = {"now": 1000.0}
    session = VoiceSession(
        store,
        recognizer,
        submit=submit,  # type: ignore[arg-type]
        conversation_id=a_conversation(store),
        clock=lambda: clock["now"],
        warm=lambda: {"cognition": {"warmed": True}},
        prime=lambda still_wanted, routes=("partner", "light"): {
            "primed": False,
            "outcome": "skipped",
            "reason": "an owner request is waiting",
        },
    )
    session.start()
    session.feed(MARKER)
    clock["now"] += 5.0
    session.advance()
    assert wait_for(lambda: session.snapshot().progress is not None)
    assert session.snapshot().progress == "warming", session.snapshot().readiness
    hold.set()
    session.await_turn(timeout=10)
    session.close()


def test_readiness_record_shape() -> None:
    assert VoiceReadiness().ready is False
    assert VoiceReadiness(cognition="ready", voice="not_applicable", prefix_partner="primed").ready
