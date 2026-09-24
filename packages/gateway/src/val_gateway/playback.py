"""From the sink to the speakers — owner execution order, 24 September 2026.

Voice work package 3 §11 and §11.1. Work package 2 proved delivery as far as an
in-process sink. This is the loopback hand-off from that sink to the desktop that
owns the Mac's speakers, and the record of what the speakers then did.

Two facts are kept apart here, because collapsing them is the specific lie this
module exists to prevent:

**Available to the desktop** — synthesis finished, the bytes are queued, and the
desktop may collect them. Nothing has been heard.

**Playback started** — the desktop has actually scheduled the audio on an output
device, and reported so. Only this is sound in the room.

The queue is bounded and the bytes are handed out **once**: a collected segment is
released the moment it leaves, so the house holds live speech no longer than it
takes to pass it along. There is no file write anywhere in this module, and a
segment that is never collected is discarded rather than accumulated.

No listener, no port, no URL: the desktop collects over the existing loopback
service. This module opens nothing.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Engine, text

from val_domain.speech import SpokenSegment
from val_gateway.delivery import EphemeralSink

__all__ = [
    "DesktopSink",
    "OfferedSegment",
    "PlaybackEvent",
    "PlaybackState",
    "record_playback",
]

#: How many synthesised segments may wait for the desktop to collect them. Small
#: on purpose: this is a hand-off, not a buffer, and a desktop that has stopped
#: collecting is one whose playback has ended — in which case the audio is stale
#: and discarding it is correct.
QUEUE_DEPTH = 8


class PlaybackState(StrEnum):
    """What the speakers did, in the vocabulary migration 0030 enforces."""

    AVAILABLE_TO_DESKTOP = "available_to_desktop"
    PLAYBACK_STARTED = "playback_started"
    PLAYBACK_COMPLETED = "playback_completed"
    PLAYBACK_INTERRUPTED = "playback_interrupted"
    PLAYBACK_FAILED = "playback_failed"


@dataclass(frozen=True)
class OfferedSegment:
    """One segment on its way to the speakers."""

    segment_index: int
    text: str
    audio: bytes
    #: WAV, because that is what the local voice produces and nothing here
    #: transcodes it. Stated rather than assumed, so the desktop decodes what it
    #: was actually given.
    audio_format: str
    sample_rate: int
    duration_seconds: float


class DesktopSink(EphemeralSink):
    """The production sink when a desktop is listening: hand over, then let go.

    Subclasses the ephemeral sink rather than replacing it, so everything work
    package 2 proved about delivery truth — the delivered boundary, the exact
    prefix, the interrupt semantics — keeps holding unchanged, and this adds only
    the hand-off. `play` still records the segment as delivered; it now also makes
    it collectable.

    `stop` discards what has not been collected. That is the barge-in rule in its
    plainest form: a segment the owner interrupted before it was collected must not
    be played a moment later because it happened to be in a queue.
    """

    def __init__(self, depth: int = QUEUE_DEPTH) -> None:
        super().__init__()
        self._waiting: queue.Queue[OfferedSegment] = queue.Queue(maxsize=depth)
        self._offered = 0
        self._collected = 0
        self._dropped = 0
        self._segments = 0
        self._handover = threading.Lock()

    # --- the sink side --------------------------------------------------------------

    def play(self, segment: SpokenSegment) -> None:
        super().play(segment)
        with self._handover:
            if self.stopped_because is not None:
                return
            self._segments += 1
            offer = OfferedSegment(
                # The segmenter's own index, not a count kept here: the desktop and
                # the record must agree on which piece this is, and two counters
                # are one more than that requires.
                segment_index=segment.index,
                text=segment.text,
                audio=segment.audio,
                audio_format="wav",
                sample_rate=segment.sample_rate,
                duration_seconds=segment.duration_seconds,
            )
        try:
            self._waiting.put_nowait(offer)
        except queue.Full:
            # A desktop that has stopped collecting is one whose playback has
            # ended. The oldest waiting segment is stale; dropping it is honest,
            # and it is counted so the record can say it happened.
            self._dropped += 1
            return
        with self._handover:
            self._offered += 1

    def stop(self, reason: str) -> None:
        super().stop(reason)
        self._discard()

    def finish(self) -> None:
        super().finish()

    # --- the desktop side -----------------------------------------------------------

    def collect(self) -> OfferedSegment | None:
        """Hand the next segment to the desktop, or None when none is waiting.

        The bytes leave this process here and are not retained: the queue entry is
        consumed, and this sink keeps only counts afterwards.
        """
        try:
            offer = self._waiting.get_nowait()
        except queue.Empty:
            return None
        with self._handover:
            self._collected += 1
        return offer

    def _discard(self) -> None:
        dropped = 0
        while True:
            try:
                self._waiting.get_nowait()
            except queue.Empty:
                break
            dropped += 1
        with self._handover:
            self._dropped += dropped

    @property
    def waiting(self) -> int:
        return self._waiting.qsize()

    @property
    def collected(self) -> int:
        with self._handover:
            return self._collected

    @property
    def dropped(self) -> int:
        with self._handover:
            return self._dropped


#: Append-only, like every other record of what actually happened.
_APPEND = text(
    "insert into speech_playbacks "
    "  (message_id, voice_session_id, segment_index, event, state, text, elapsed_ms, reason) "
    "select :message_id, :voice_session_id, :segment_index, "
    "       coalesce(max(event), 0) + 1, :state, :text, :elapsed_ms, :reason "
    "  from speech_playbacks where message_id = :message_id and segment_index = :segment_index "
    "returning id, event"
)


def record_playback(
    engine: Engine,
    *,
    message_id: UUID,
    segment_index: int,
    state: PlaybackState,
    spoken_text: str,
    voice_session_id: UUID | None = None,
    elapsed_ms: int | None = None,
    reason: str | None = None,
) -> int:
    """Append one physical-playback transition and return its event number.

    The event number is computed inside the insert from the rows that exist, so two
    reports arriving together cannot claim the same number — the unique constraint
    refuses the loser rather than letting one overwrite the other.
    """
    with engine.begin() as connection:
        row = connection.execute(
            _APPEND,
            {
                "message_id": message_id,
                "voice_session_id": voice_session_id,
                "segment_index": segment_index,
                "state": state.value,
                "text": spoken_text,
                "elapsed_ms": elapsed_ms,
                "reason": reason,
            },
        ).one()
    return int(row.event)


@dataclass(frozen=True)
class PlaybackEvent:
    """One physical-playback transition, as the record holds it."""

    segment_index: int
    event: int
    state: PlaybackState
    text: str
    elapsed_ms: int | None
    reason: str | None
    recorded_at: datetime


def playback_of(engine: Engine, message_id: UUID) -> tuple[PlaybackEvent, ...]:
    """Every physical-playback transition for one answer, oldest first."""
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "select segment_index, event, state, text, elapsed_ms, reason, recorded_at "
                "  from speech_playbacks where message_id = :id "
                " order by segment_index, event"
            ),
            {"id": message_id},
        ).all()
    return tuple(
        PlaybackEvent(
            segment_index=row.segment_index,
            event=row.event,
            state=PlaybackState(row.state),
            text=row.text,
            elapsed_ms=row.elapsed_ms,
            reason=row.reason,
            recorded_at=row.recorded_at,
        )
        for row in rows
    )


def now_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
