"""The speech-length bound, reached — remaining latency work, 27 September 2026, §6.

The ordinary runs never reached the bound, so its failure behaviour is forced here: the
wrapper (`infrastructure/speech/qwen_tts_speak_bounded.py`) against a model that never
ends its speech, and the delivery given a segment that ends that way part-way through.
Reaching the bound stops generation at the bound, ends the segment as a named failure
rather than a completion, and the delivery records only what was fully spoken — the
segment is not counted as delivered and the rest of the answer is left unspoken, not
discarded.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

import importlib.util
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import Engine
from test_deliberation_machinery import clean_personas, store
from test_speech_delivery import ANSWER, a_delivery, deliver
from test_speech_streaming import StreamingVoice, a_piece

from val_domain.speech import (
    DeliveryState,
    SpeechRequest,
    SpeechResult,
    SpeechUnavailableError,
)
from val_gateway.playback import DesktopSink

WRAPPER = Path(__file__).resolve().parents[3] / "infrastructure/speech/qwen_tts_speak_bounded.py"


def the_wrapper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bounded_runner", WRAPPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass
class Samples:
    size: int


@dataclass
class Piece:
    audio: Samples
    sample_rate: int = 24000


class TalkativeModel:
    """The library's contract: one piece per second of codec tokens, ending either at
    its own end of speech (`natural_seconds`) or at `max_tokens` — whichever is first."""

    def __init__(self, natural_seconds: float | None) -> None:
        self.natural_seconds = natural_seconds
        self.pieces_made = 0

    def generate(self, text: str, max_tokens: int = 4096, **_: object) -> Iterator[Piece]:
        tokens = 0
        while True:
            if self.natural_seconds is not None and tokens / 12.5 >= self.natural_seconds:
                return
            if tokens >= max_tokens:
                return
            step = min(12.5, max_tokens - tokens)
            tokens += step
            self.pieces_made += 1
            yield Piece(Samples(round(step / 12.5 * 24000)))


def test_a_runaway_segment_stops_at_its_bound_and_ends_as_a_failure() -> None:
    wrapper = the_wrapper()
    model = wrapper._bounded(TalkativeModel(natural_seconds=None))
    text = "A caesura is a pause within a line of verse."
    bound_seconds = wrapper.max_speech_tokens(text) / wrapper.CODEC_TOKENS_PER_SECOND
    heard = 0.0
    with pytest.raises(wrapper.SpeechLengthBoundReached) as reached:
        for piece in model.generate(text=text, stream=True):
            heard += piece.audio.size / piece.sample_rate
    assert abs(heard - bound_seconds) < 1.0, "generation ran to the bound and no further"
    assert "not counted as spoken" in str(reached.value)
    # The library's loop ended at the bound: nothing was made after it.
    assert model.pieces_made == pytest.approx(bound_seconds, abs=1)


def test_ordinary_speech_is_unchanged_by_the_bound() -> None:
    wrapper = the_wrapper()
    text = "A caesura is a pause within a line of verse, marked by sense or punctuation."
    ordinary = len(text) / 14.0  # her pace, measured at ~13-16 characters per second
    model = wrapper._bounded(TalkativeModel(natural_seconds=ordinary))
    heard = sum(p.audio.size / p.sample_rate for p in model.generate(text=text, stream=True))
    assert heard == pytest.approx(ordinary, abs=1.0)


def test_the_forced_bound_is_only_what_the_test_sets(monkeypatch: pytest.MonkeyPatch) -> None:
    wrapper = the_wrapper()
    monkeypatch.delenv("VAL_TTS_BOUND_FORCE_SECONDS", raising=False)
    natural = wrapper.max_speech_tokens("Good evening, my lord.")
    monkeypatch.setenv("VAL_TTS_BOUND_FORCE_SECONDS", "1.5")
    assert wrapper.max_speech_tokens("Good evening, my lord.") == 19
    assert natural > 19


class BoundReachedVoice(StreamingVoice):
    """Voices the first segment normally; the second runs to its bound part-way."""

    def synthesize_stream(
        self, request: SpeechRequest, on_chunk: Callable[[bytes, float], None]
    ) -> SpeechResult | None:
        if self.spoken:
            on_chunk(a_piece(24000), 1.0)  # some of it went out before the bound
            raise SpeechUnavailableError(
                "speech length bound reached: a segment of 60 characters ran to its bound "
                "(250 codec tokens, 20.0 s of audio) without ending its speech; it is not "
                "counted as spoken"
            )
        return super().synthesize_stream(request, on_chunk)


def test_a_segment_that_reaches_its_bound_is_not_recorded_as_spoken(store: Engine) -> None:
    voice = BoundReachedVoice(pieces=2)
    sink = DesktopSink()
    delivery = a_delivery(store, voice, sink=sink)
    deliver(delivery, ANSWER)
    assert delivery.state is DeliveryState.FAILED
    reason = delivery.reason or ""
    assert "speech length bound reached" in reason
    assert "segment 2 began and did not complete" in reason, "begun, and not complete"
    # Completed: the first segment only. The second's first sound reached him, so under
    # the delivered-boundary rule its text is not relabelled unheard — but it is not
    # recorded as completed, and nothing after it is claimed.
    assert [segment.index for segment in delivery.spoken] == [1]
    assert delivery.sink.segments_played == 2
    assert delivery.delivered_prefix.startswith(delivery.spoken[0].text)
    assert len(delivery.delivered_prefix) < len(ANSWER), "the rest was never claimed"
    assert delivery.sink.stopped_because is not None, "what was playing is told to stop"
