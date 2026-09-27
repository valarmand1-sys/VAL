"""Maintenance waits for the speakers, not only for synthesis (release-gaps order, 26 Sept 2026).

The Milestone A collision runs showed every refresh dispatched one second after the
turn's completion and 2.7 to 19.6 s before his next words — words that began 0.3 s after
the *player* fell silent. The idle clock started when synthesis ended, while the desktop
was still speaking the tail of her answer. Audio handed to the desktop is now counted
as heard for its own duration, serially; a barge-in or a reported stop ends it.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

import time
from collections.abc import Callable

from sqlalchemy import Engine
from test_deliberation_machinery import ScriptedAdapter, clean_personas, ok, store
from test_voice_input import MARKER, ScriptedRecognizer, a_conversation, final, started
from test_voice_priming import a_session, settle, wait_for

import val_gateway.voice as voice_module
from val_gateway.voice import VoiceSession


def test_handed_over_audio_counts_as_owner_work(store: Engine) -> None:
    session = VoiceSession(
        store,
        ScriptedRecognizer(batches=[]),
        submit=lambda *a, **k: None,  # type: ignore[arg-type]
        conversation_id=a_conversation(store),
    )
    assert not session._owner_waiting(including_speech=True)
    session.speech_handed_over(2.0)
    session.speech_handed_over(1.0)  # serial: the second piece plays after the first
    assert session._owner_waiting(including_speech=True)
    assert session._heard_until - time.monotonic() > 2.5
    session.playback_reported("playback_completed")  # completion changes nothing
    assert session._owner_waiting(including_speech=True)
    session.playback_reported("playback_interrupted")  # a stop ends what is heard
    assert not session._owner_waiting(including_speech=True)
    session.close()


def test_the_refresh_is_dispatched_only_after_the_audio_has_been_heard(store: Engine) -> None:
    recognizer = ScriptedRecognizer(batches=[[started(1), final(1, "Good evening, Val.")]])
    session, _, clock = a_session(
        store, recognizer, adapter=ScriptedAdapter([ok("Good evening, my lord.")])
    )
    called_at: list[float] = []

    def primer(still_wanted: Callable[[], bool], routes: object = None) -> object:
        called_at.append(time.monotonic())
        return {"primed": True, "outcome": "established", "wanted": still_wanted()}

    voice_module.REFRESH_IDLE_SECONDS = 0.2
    try:
        session._prime = primer
        session._initial_prime_started = True
        # As if the desktop had just collected 1.5 s of her previous answer: the turn
        # below completes well inside that, so synthesis-end idleness would dispatch
        # the refresh at ~0.2 s; the heard boundary must hold it past 1.5 s.
        session.speech_handed_over(1.5)
        heard_until = session._heard_until
        session.feed(MARKER)
        settle(session, clock)
        wait_for(lambda: len(session.primes) == 1, timeout=10.0)
        assert session.primes[0]["kind"] == "refresh"  # type: ignore[index]
        assert called_at[0] >= heard_until + 0.15, called_at[0] - heard_until
    finally:
        voice_module.REFRESH_IDLE_SECONDS = 1.0
    session.close()
