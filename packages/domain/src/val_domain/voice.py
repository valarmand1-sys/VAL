"""Val's provider-neutral live-voice input boundary.

Owner execution order, Voice mode work package 1. Spoken conversation is
ordinary conversation that arrived by a different door, and this module exists
to keep that true:

    **Canonical conversation history is TEXT.** The recognizer's final
    transcription becomes the canonical user turn; raw microphone audio is never
    history and never a database field.

So nothing here carries audio. A `VoiceUtterance` is words and the facts about
how they were heard. Audio exists only in the volatile places that must touch
it — the capture path and the recognizer — and is named nowhere in the record.

**Provisional and final are different kinds of thing, not two values of one.**
Provisional text is a rolling guess over speech still in progress: it may
revise, it is never a message, it never reaches cognition, and it never enters
recall. Final text is the settled transcription of a completed utterance, and
only it becomes a turn. They are separate types rather than one type with a
flag, so handing the wrong one onward is a type error rather than a silent
promotion.

Like `val_domain.provider`, `val_domain.perception` and `val_domain.speech`,
nothing here imports a provider package.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID


class VoiceUnavailableError(Exception):
    """Live voice could not start, or could not continue.

    Raised rather than returned. A session that meets this stops listening and
    says so: there is no cloud speech service to fall back to, none is wired,
    and none may be.
    """


class VoiceSessionState(StrEnum):
    """What a voice session is doing, in words the interface can show.

    Owner-facing states, not implementation telemetry: each is a thing a person
    can act on — whether Val is waiting for them, hearing them, or working.
    """

    LISTENING = "listening"
    HEARING = "hearing"
    THINKING = "thinking"
    CLOSED = "closed"
    ERROR = "error"


@dataclass(frozen=True)
class RecognizerIdentity:
    """Which recognizer heard this, exactly.

    Carried onto every voice-origin message, because *you typed* and *the
    recognizer heard* are not the same claim, and Val should be able to tell
    them apart months later without guessing.
    """

    name: str
    version: str
    commit: str
    model_identifier: str
    model_sha256: str
    vad_model_identifier: str
    vad_model_sha256: str

    def as_record(self) -> dict[str, str]:
        return {
            "recognizer": self.name,
            "recognizer_version": self.version,
            "recognizer_commit": self.commit,
            "asr_model": self.model_identifier,
            "asr_model_sha256": self.model_sha256,
            "vad_model": self.vad_model_identifier,
            "vad_model_sha256": self.vad_model_sha256,
        }


@dataclass(frozen=True)
class EndpointConfiguration:
    """When the recognizer decides an utterance has ended.

    Stated explicitly and recorded on the session, so the figures that produced
    a transcript are readable from the record rather than from this file. These
    are the conversational starting values the order names; there is no tuning
    campaign behind them.
    """

    threshold: float = 0.5
    min_speech_ms: int = 220
    min_silence_ms: int = 650
    speech_pad_ms: int = 80
    #: A single utterance longer than this is endpointed anyway, so a stuck VAD
    #: cannot hold a turn open forever.
    max_utterance_s: float = 30.0

    def as_record(self) -> dict[str, float | int]:
        return {
            "threshold": self.threshold,
            "min_speech_ms": self.min_speech_ms,
            "min_silence_ms": self.min_silence_ms,
            "speech_pad_ms": self.speech_pad_ms,
            "max_utterance_s": self.max_utterance_s,
        }


@dataclass(frozen=True)
class ProvisionalText:
    """A rolling guess over speech still in progress. **Never a message.**

    It exists to be shown to the owner as they speak, and to be superseded. It
    is not persisted as conversation, not sent to cognition, not indexed, and
    not reachable from recall.
    """

    session_id: UUID
    utterance: int
    text: str
    at: float


@dataclass(frozen=True)
class VoiceUtterance:
    """One settled utterance: the words, and how they came to be words."""

    session_id: UUID
    utterance: int
    text: str
    #: Why endpointing fired — `silence`, `maximum_length`, `flush`. Recorded
    #: because a turn ended by a length cap is a different event from one ended
    #: by the owner finishing a sentence.
    reason: str
    #: Monotonic instants, kept so a later package can decompose latency without
    #: re-deriving them from logs.
    speech_start_at: float = 0.0
    endpoint_at: float = 0.0
    final_at: float = 0.0
    #: The utterance numbers this one absorbed when the owner resumed before Val
    #: answered. Empty on an ordinary turn.
    merged_from: tuple[int, ...] = ()

    @property
    def endpoint_to_final_ms(self) -> float:
        return max(0.0, (self.final_at - self.endpoint_at) * 1000)

    def merged_with(self, later: VoiceUtterance) -> VoiceUtterance:
        """One human utterance, spoken in two breaths, as one turn.

        The words are joined with a single space and nothing else is rewritten:
        the owner said both halves and the canonical turn is both halves.
        """
        return VoiceUtterance(
            session_id=self.session_id,
            utterance=later.utterance,
            text=f"{self.text.rstrip()} {later.text.lstrip()}".strip(),
            reason=later.reason,
            speech_start_at=self.speech_start_at or later.speech_start_at,
            endpoint_at=later.endpoint_at,
            final_at=later.final_at,
            merged_from=(*self.merged_from, self.utterance),
        )


@dataclass(frozen=True)
class RecognizerEvent:
    """One thing the recognizer observed, in the five kinds it may report."""

    kind: str  # speech_start | provisional | speech_end | final | error
    session: int = 0
    text: str = ""
    reason: str = ""
    at: float = 0.0
    endpoint_at: float = 0.0
    detail: str = ""
    #: Owner acceptance, 25 September 2026 (WP3 Step B §10). The endpoint evidence,
    #: as durations and never as audio: how much silence ended this utterance, how
    #: long the gap before it was, how much of it the VAD actually called speech, and
    #: how long it ran. The repair pass added these to the helper and **stopped one
    #: boundary short** — this type dropped them, so the run they were built for
    #: could not record them. They are carried now.
    silence_seconds: float = 0.0
    gap_before_seconds: float | None = None
    voiced_seconds: float = 0.0
    seconds: float = 0.0
    #: Owner diagnostic, 25 September 2026. Which stretch of the helper's input
    #: stream an utterance was, in samples since it began listening — its first
    #: sample, its length, the first window the VAD was confident of, and how much
    #: of the stream had arrived. Counts for continuity, never audio.
    first_sample: int = 0
    samples: int = 0
    run_start_sample: int = 0
    received_samples: int = 0
    #: When **this process** read the event off the helper's stdout, on its own
    #: monotonic clock. Not from the payload: the helper's clock is its own, and on
    #: this machine two processes' monotonic clocks do not share an origin, so the
    #: helper's `at` and `endpoint_at` are comparable with each other and with
    #: nothing here. Zero when the event did not come through an adapter that notes it.
    received_at: float = 0.0

    @classmethod
    def of(cls, payload: dict[str, object]) -> RecognizerEvent:
        """Read one event the recognizer reported.

        Every field is coerced rather than trusted: the payload crosses a process
        boundary, and a field of the wrong shape should give a dull default here
        instead of an exception somewhere less obvious.
        """
        return cls(
            kind=_word(payload.get("event")),
            session=_count(payload.get("session")),
            text=_word(payload.get("text")),
            reason=_word(payload.get("reason")),
            at=_instant(payload.get("at")),
            endpoint_at=_instant(payload.get("endpoint_at")),
            detail=_word(payload.get("detail")),
            silence_seconds=_instant(payload.get("silence_seconds")),
            gap_before_seconds=(
                None
                if payload.get("gap_before_seconds") is None
                else _instant(payload.get("gap_before_seconds"))
            ),
            voiced_seconds=_instant(payload.get("voiced_seconds")),
            seconds=_instant(payload.get("seconds")),
            first_sample=_count(payload.get("first_sample")),
            samples=_count(payload.get("samples")),
            run_start_sample=_count(payload.get("run_start_sample")),
            received_samples=_count(payload.get("received_samples")),
        )


def _word(value: object) -> str:
    return value if isinstance(value, str) else ""


def _count(value: object) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def _instant(value: object) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


@runtime_checkable
class LiveRecognizer(Protocol):
    """What a live recognizer must do, and the little it is allowed to be.

    **It owns no microphone.** Audio is handed to it. It owns no conversation,
    no identity and no policy; it reports speech boundaries and text, and
    nothing it returns is a message until Core makes one.
    """

    @property
    def identity(self) -> RecognizerIdentity:
        """Exactly what heard this — read-only, because it is a fact about the
        recognizer and not a label a caller may set on one."""
        ...

    @property
    def endpoint(self) -> EndpointConfiguration:
        """The endpointing figures this recognizer is actually running with.

        Read from the recognizer rather than assumed, so what a session records
        is what actually decided its utterance boundaries.
        """
        ...

    def start(self) -> None:
        """Bring the recognizer up, or raise `VoiceUnavailableError`."""
        ...

    def feed(self, pcm: bytes) -> None:
        """One block of 16 kHz mono little-endian int16 PCM."""
        ...

    def drain(self) -> Iterator[RecognizerEvent]:
        """Every event observed since the last drain, in order."""
        ...

    def flush(self) -> None:
        """End the utterance in progress, if any, and finalize it."""
        ...

    def stop(self) -> None:
        """Release the recognizer and everything it holds."""
        ...


#: The one canonical service-side audio contract for voice input (§5). Stated
#: once so the capture path, the recognizer and the tests cannot disagree.
SAMPLE_RATE = 16_000
SAMPLE_WIDTH_BYTES = 2
CHANNELS = 1


def pcm_is_valid(pcm: bytes) -> str | None:
    """Why this block may not be fed to the recognizer, or `None`.

    Validation only: the block is never stored, never written to a file, and
    never copied anywhere but the recognizer's own volatile buffer.
    """
    if not pcm:
        return "an empty block carries no audio"
    if len(pcm) % (SAMPLE_WIDTH_BYTES * CHANNELS):
        return (
            f"{len(pcm)} bytes is not a whole number of "
            f"{CHANNELS}-channel {SAMPLE_WIDTH_BYTES * 8}-bit frames"
        )
    return None
