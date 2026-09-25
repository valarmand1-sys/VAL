"""Val speaks: progressive delivery of the answer she is still writing.

Owner execution order, Voice mode work package 2, sections 6 to 13. The path is:

    Core's visible response stream → the exact speech segmenter
        → the established local voice → progressive ephemeral audio
        → delivery-state truth → interruption

**Speech is delivery, not authorship.** Only Core's visible governed response text
enters speech. Never hidden reasoning, never a provider reasoning delta, never a
raw provider field, never a control or verdict marker Core withheld, never
internal exception text, never unfinished provider state, and never text Core did
not deliver. The segmenter refuses a forbidden marker rather than filtering it,
because its arrival would mean a boundary upstream had failed.

**Live speech is ephemeral.** Audio is generated, handed to the sink, and
released. No waveform for an ordinary spoken answer is written to disk, and the
durable record holds text, ordering, digests and timings — never bytes and never
a path to bytes that do not exist.

**Delivery is not generation.** Core can finish writing text the owner never
hears. `speech_deliveries` is the append-only record of what delivery actually
did, each row carrying the exact prefix delivered at that moment, so nothing
later behaves as though the unheard suffix was heard. The assistant message is
never rewritten to tidy that up.

**The delivered boundary is the first audio**, not the last. From the moment the
first piece reaches the sink, new owner speech is a fresh turn rather than a
continuation of the one Val is answering — because he has begun to hear her.

**Barge-in stops her.** When the recognizer reports the owner speaking while
delivery is live, the sink is stopped, the queue is discarded, nothing further is
synthesised, and the exact delivered prefix goes on the record. Consequential
effects already executed are not rolled back: speech stopping is not a time
machine.
"""

from __future__ import annotations

import hashlib
import queue
import threading
import time
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Engine, text

from val_domain import timings
from val_domain.gateway import ModelConfig
from val_domain.speech import (
    DeliveryState,
    SpeechRequest,
    SpokenSegment,
    VoiceConditioning,
)
from val_domain.timings import mark
from val_domain.voice import VoiceUnavailableError
from val_policy.speech_segments import Segment, SpeechSegmenter, SpeechTextRefusedError

#: How long one segment's synthesis may take before delivery is called failed.
SEGMENT_TIMEOUT_SECONDS = 120.0

#: How long `finish` waits for the synthesis queue to drain.
DRAIN_TIMEOUT_SECONDS = 300.0

#: The service-side target the order names: from the recognizer's speech_start
#: reaching delivery control to the sink being stopped. **Not** a claim about when
#: a physical speaker falls silent, which needs the speakers (work package 3).
CANCELLATION_TARGET_MS = 300.0


class EphemeralSink:
    """The production sink for this package: in memory, and then gone.

    Holds the piece currently being delivered and nothing else. **There is no file
    write anywhere in this class** — that is what makes live speech ephemeral
    rather than merely uncollected.

    It is also the reason the loopback proof in §14 is available: what this sink
    holds is audio *leaving* the house's own process, and there is no path from
    here back into the recognizer's PCM input. A test asserts that by construction
    rather than by acoustics, and the physical room is work package 3's.
    """

    def __init__(self) -> None:
        self.began: bool = False
        self.finished: bool = False
        self.stopped_because: str | None = None
        #: Only the piece in hand. Replaced, not accumulated.
        self._current: bytes = b""
        self.segments_played = 0
        self.bytes_played = 0
        self.seconds_played = 0.0
        self.texts: list[str] = []
        self.first_audio_at: float | None = None
        self._lock = threading.Lock()

    def begin(self) -> None:
        with self._lock:
            self.began = True

    def play(self, segment: SpokenSegment) -> None:
        with self._lock:
            if self.stopped_because is not None:
                return
            # The previous piece is released here, by being replaced. Nothing
            # accumulates and nothing is kept once delivery moves on.
            self._current = segment.audio
            self.segments_played += 1
            self.bytes_played += segment.audio_bytes
            self.seconds_played += segment.duration_seconds
            self.texts.append(segment.text)
            if self.first_audio_at is None:
                self.first_audio_at = time.monotonic()

    def finish(self) -> None:
        with self._lock:
            self.finished = True
            self._current = b""

    def stop(self, reason: str) -> None:
        with self._lock:
            self.stopped_because = reason
            self._current = b""

    @property
    def holding_bytes(self) -> int:
        """How much audio the sink is holding. Zero once delivery has ended."""
        with self._lock:
            return len(self._current)


@dataclass
class _Pending:
    """One segment waiting to be spoken."""

    segment: Segment
    queued_at: float


#: One append-only delivery event.
_DELIVERY_EVENT = text(
    "insert into speech_deliveries "
    "  (message_id, voice_session_id, event, state, delivered_prefix, "
    "   delivered_characters, segments_delivered, segments_total, reason, "
    "   first_audio_ms, elapsed_ms) "
    "values (:message_id, :voice_session_id, :event, :state, :delivered_prefix, "
    "        :delivered_characters, :segments_delivered, :segments_total, :reason, "
    "        :first_audio_ms, :elapsed_ms)"
)

#: One ephemeral spoken segment: text, ordering, digests, timings — no path.
_GENERATION = text(
    "insert into speech_generations "
    "  (voice_id, message_id, model_config_id, final_text, final_text_sha256, provider, "
    "   model_identifier, model_revision, quantization, runtime, runtime_version, "
    "   generation, clone_prompt_sha256, audio_sha256, audio_path, audio_retained, "
    "   audio_bytes, sample_rate, duration_seconds, local, cost_usd, elapsed_ms, "
    "   segment_index, segment_reason) "
    "values (:voice_id, :message_id, :model_config_id, :final_text, :final_text_sha256, "
    "        :provider, :model_identifier, :model_revision, :quantization, :runtime, "
    "        :runtime_version, cast(:generation as jsonb), :clone_prompt_sha256, "
    "        :audio_sha256, NULL, false, :audio_bytes, :sample_rate, :duration_seconds, "
    "        true, 0, :elapsed_ms, :segment_index, :segment_reason)"
)

_VOICE_ID = text("select id from speech_voices where reference_sha256 = :digest")


class SpeechDelivery:
    """One assistant turn's speech, from the first delta to the last piece of audio.

    Created before the turn is submitted, fed Core's visible deltas as they
    arrive, and bound to the persisted message once it exists. Audio reaches the
    ear immediately; only the *record* waits for the message id, because a message
    that does not exist yet cannot be referenced — and a turn that never settles
    leaves no delivery rows, which is the honest outcome.
    """

    def __init__(
        self,
        engine: Engine,
        *,
        speech: object,
        voice: VoiceConditioning,
        configuration: ModelConfig,
        sink: EphemeralSink | None = None,
        voice_session_id: UUID | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._engine = engine
        self._speech = speech
        self._voice = voice
        self._configuration = configuration
        self.sink = sink if sink is not None else EphemeralSink()
        self._voice_session_id = voice_session_id
        self._now = clock

        self.segmenter = SpeechSegmenter()
        self.state = DeliveryState.NOT_STARTED
        self.reason: str | None = None
        self.spoken: list[SpokenSegment] = []
        self.message_id: UUID | None = None
        self.started_at = self._now()
        #: When Core's first visible text reached speech, and when the first audio
        #: left for the ear — both from the moment delivery was created, which is
        #: just before the turn is submitted. §16's two reportable intervals are
        #: differences of these.
        self.first_delta_ms: int | None = None
        self.first_audio_ms: int | None = None
        self.elapsed_ms: int | None = None
        #: Owner acceptance, 25 September 2026 (WP3 Step B §9.1, §27). **When the first
        #: segment's synthesis began, and whether cognition had finished by then.**
        #: His report was that Val read out already-complete text, and the question
        #: "does segment 1 start before the answer is finished?" needs an answer from
        #: the record rather than from an argument about the code. Measured from the
        #: same origin as the two figures above.
        self.first_tts_start_ms: int | None = None
        self.cognition_complete_ms: int | None = None
        #: Recorded for the §13.1 measurement: the interval from the barge-in
        #: signal arriving here to the sink being stopped.
        self.cancellation_ms: float | None = None
        self.failure: str | None = None

        self._queue: queue.Queue[_Pending | None] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._lock = threading.RLock()
        self._closed: bool = False
        self._events: list[dict[str, object]] = []

    # --- what the outside asks ------------------------------------------------------

    def _is_closed(self) -> bool:
        """Read the flag under the lock. A method rather than a bare attribute
        read, because it is changed by the synthesis worker and by `interrupt`
        between two checks in the same method."""
        with self._lock:
            return self._closed

    @property
    def audible(self) -> bool:
        """Has any audio reached the sink? **The delivered boundary.**

        True from the first piece, not the last: once he has begun to hear her,
        what he says next is a reply rather than the rest of his own sentence.
        """
        return self.sink.first_audio_at is not None

    @property
    def active(self) -> bool:
        """Is delivery live — so that owner speech now is barge-in?"""
        with self._lock:
            return not self._closed and self.state in (
                DeliveryState.NOT_STARTED,
                DeliveryState.STARTED,
            )

    @property
    def first_core_visible_to_first_audio_ms(self) -> int | None:
        """§16: Core's first visible text to the first audio at the delivery boundary.

        `None` until both have happened. This is a service-side figure and is not a
        claim about a physical speaker, which needs the speakers (work package 3).
        """
        if self.first_delta_ms is None or self.first_audio_ms is None:
            return None
        return self.first_audio_ms - self.first_delta_ms

    @property
    def segments_delivered(self) -> int:
        """How many speech-safe pieces actually reached the ear."""
        return self.sink.segments_played

    @property
    def delivered_prefix(self) -> str:
        """Exactly the words the owner heard, in order, as one string.

        The concatenation of the segments that actually reached the sink — never
        the whole answer, and never a guess at where he stopped listening.
        """
        return " ".join(self.sink.texts)

    # --- the stream ------------------------------------------------------------------

    def feed(self, delta: str) -> None:
        """One piece of Core's visible text. Segments it and queues any speech.

        This is the `DeltaSink` Core hands its visible output to. It returns
        promptly: synthesis happens on a worker, so Val keeps writing while the
        first sentence is being spoken.
        """
        if self._is_closed():
            return
        with self._lock:
            if self.first_delta_ms is None and delta:
                self.first_delta_ms = int((self._now() - self.started_at) * 1000)
                mark("speech_first_visible_text")
        try:
            ready = self.segmenter.feed(delta)
        except SpeechTextRefusedError as refused:
            self._fail(str(refused))
            return
        for segment in ready:
            self._queue_segment(segment)

    def finish(self, settled_text: str | None = None) -> None:
        """Val has stopped writing: flush the exact suffix and wait for the voice.

        The moment cognition completed is recorded here, because this is where Core
        says so — and §9.1's invariant is a comparison between that moment and the
        first segment's synthesis start.

        `settled_text` is her persisted answer, and it is authoritative. Two cases
        it settles, both of which a stream alone cannot:

          * **A route that could not stream.** No delta arrived, so nothing has
            been spoken. The settled answer is spoken now — not progressively,
            which is a latency loss and not a silence. Progressive speech is an
            improvement on a route that streams, never a requirement for speech to
            happen at all.
          * **A stream that does not match the record.** Val Core settles a turn
            from the completed response and never from the sum of the deltas, so
            the two *could* disagree. If they disagree in anything but boundary
            whitespace, delivery **fails with that named reason** rather than
            speaking words the record does not hold.
        """
        if self.cognition_complete_ms is None:
            # Core has stopped writing. Recorded before anything else here, so the
            # comparison in §9.1 is against the moment itself rather than the moment
            # plus whatever this method then does.
            self.cognition_complete_ms = round((self._now() - self.started_at) * 1000)
        if self._is_closed():
            return
        if settled_text is not None:
            streamed = self.segmenter.source
            if not streamed.strip():
                self.feed(settled_text)
                if self._is_closed():
                    return
            elif "".join(streamed.split()) != "".join(settled_text.split()):
                self._fail(
                    "the text streamed to speech is not the answer that was persisted, so "
                    "speaking it would be speaking something the record does not hold; "
                    f"{len(streamed)} characters were streamed and "
                    f"{len(settled_text)} persisted."
                )
                return
        try:
            for segment in self.segmenter.flush():
                self._queue_segment(segment)
        except SpeechTextRefusedError as refused:
            self._fail(str(refused))
            return
        self._drain()
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self.elapsed_ms = int((self._now() - self.started_at) * 1000)
            if self.failure is not None:
                self.state, self.reason = DeliveryState.FAILED, self.failure
            elif self.audible:
                self.state, self.reason = DeliveryState.COMPLETED, None
            else:
                # Nothing was spoken and nothing failed: there was nothing to say.
                self.state, self.reason = DeliveryState.NOT_STARTED, None
        self.sink.finish()
        self._record_event()

    def interrupt(self, reason: str = "the owner spoke") -> float:
        """Stop delivery now. Returns the service-side cancellation interval, in ms.

        The sink is stopped first and the bookkeeping follows, because the thing
        that matters is that Val stops talking over him — not that the record is
        tidy a millisecond sooner. Queued segments are discarded and no further
        synthesis is started.
        """
        signalled = self._now()
        self.sink.stop(reason)
        elapsed = (self._now() - signalled) * 1000
        with self._lock:
            if self._closed:
                return elapsed
            self._closed = True
            self.cancellation_ms = elapsed
            self.elapsed_ms = int((self._now() - self.started_at) * 1000)
            self.state, self.reason = DeliveryState.INTERRUPTED, reason
        # Wake the worker so it leaves rather than finishing a segment nobody
        # will hear.
        self._queue.put(None)
        self._record_event()
        return elapsed

    # --- synthesis, on a worker ------------------------------------------------------

    def _queue_segment(self, segment: Segment) -> None:
        with self._lock:
            if self._closed:
                return
            mark("speech_segment_queued")
            self._queue.put(_Pending(segment=segment, queued_at=self._now()))
            if self._worker is None or not self._worker.is_alive():
                # The recorder is carried across the thread boundary explicitly: a
                # plain thread starts with an empty context, so a diagnostic
                # installed by the caller would otherwise be invisible inside the
                # voice worker. `None` in production, where nothing is recording.
                self._worker = threading.Thread(
                    target=self._speak, args=(timings.current(),), daemon=True
                )
                self._worker.start()

    def _speak(self, recorder: timings.TurnTimings | None = None) -> None:
        """Take segments off the queue, give them to the local voice, deliver them."""
        with timings.recording(recorder) if recorder is not None else nullcontext():
            self._speak_queue()

    @property
    def first_segment_began_before_the_answer_was_finished(self) -> bool | None:
        """Whether synthesis of segment 1 started before cognition completed.

        `None` while either boundary is unknown — an interval with one end is not an
        interval, and a `False` that merely meant "not measured yet" would be the kind
        of small untruth this record exists to prevent.
        """
        if self.first_tts_start_ms is None or self.cognition_complete_ms is None:
            return None
        return self.first_tts_start_ms < self.cognition_complete_ms

    def _speak_queue(self) -> None:
        while True:
            try:
                # A short poll, not a semantic interval: it is how long `finish`
                # waits after the last segment before the worker notices there is
                # nothing more coming. A second here was a second added to the end
                # of every spoken answer.
                pending = self._queue.get(timeout=0.1)
            except queue.Empty:
                if self._is_closed() or self._queue.empty():
                    return
                continue
            if pending is None:
                return
            if self._is_closed():
                return
            started = self._now()
            if self.first_tts_start_ms is None:
                # The first segment's synthesis. Recorded against the same origin as
                # the other two figures, so §9.1's question — did this begin before
                # the answer was finished? — is answered by the record.
                self.first_tts_start_ms = round((started - self.started_at) * 1000)
            mark("tts_synthesize_start")
            try:
                result = self._speech.synthesize(  # type: ignore[attr-defined]
                    SpeechRequest(text=pending.segment.text, voice=self._voice)
                )
                mark("tts_synthesize_return")
            except Exception as failure:
                self._fail(f"the local voice could not speak this segment: {failure}")
                return
            if self._is_closed():
                # Interrupted while this piece was being made. It is not
                # delivered, and it is not recorded as delivered.
                return
            spoken = SpokenSegment(
                index=pending.segment.index,
                text=pending.segment.text,
                reason=pending.segment.reason,
                audio=result.audio,
                audio_sha256=hashlib.sha256(result.audio).hexdigest(),
                sample_rate=result.sample_rate,
                duration_seconds=result.duration_seconds,
                generated_ms=int((self._now() - started) * 1000),
                clone_prompt_sha256=result.clone_prompt_sha256,
            )
            first = not self.audible
            self.sink.play(spoken)
            mark("audio_at_sink")
            with self._lock:
                self.spoken.append(spoken)
                if first and self.sink.first_audio_at is not None:
                    # **The delivered boundary.**
                    self.first_audio_ms = int((self.sink.first_audio_at - self.started_at) * 1000)
                    self.state = DeliveryState.STARTED
            if first:
                self._record_event()

    def _drain(self) -> None:
        """Wait for the voice to finish what is queued — or stop waiting.

        A closed delivery is not drained: when a segment fails or the owner cuts
        in, the worker leaves with segments still queued, and nothing is ever
        going to take them. Waiting out the full timeout for a queue nobody is
        reading was a five-minute pause after every voice failure, which is how
        this line came to exist.
        """
        deadline = time.monotonic() + DRAIN_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self._is_closed():
                return
            with self._lock:
                worker = self._worker
                if self._queue.empty() and (worker is None or not worker.is_alive()):
                    return
            if worker is not None:
                worker.join(timeout=0.2)
            else:
                time.sleep(0.02)

    def _fail(self, detail: str) -> None:
        with self._lock:
            self.failure = detail
            if self._closed:
                return
            self._closed = True
            self.state, self.reason = DeliveryState.FAILED, detail
            self.elapsed_ms = int((self._now() - self.started_at) * 1000)
        self.sink.stop(detail)
        self._record_event()

    # --- the record ------------------------------------------------------------------

    def bind(self, message_id: UUID) -> None:
        """Name the persisted assistant message, and write what delivery did.

        Called once the turn has settled. Every event held back until now is
        written in order, so the append-only record reads as it happened rather
        than as it was discovered.
        """
        with self._lock:
            self.message_id = message_id
            held, self._events = list(self._events), []
        if not held:
            self._append({"state": self.state.value, "reason": self.reason})
            return
        for event in held:
            self._write(event)

    def _record_event(self) -> None:
        """Note the current state, to be written now or when the message exists."""
        snapshot: dict[str, object] = {
            "state": self.state.value,
            "reason": self.reason,
        }
        with self._lock:
            if self.message_id is None:
                self._events.append(snapshot)
                return
        self._write(snapshot)

    def _append(self, snapshot: dict[str, object]) -> None:
        self._write(snapshot)

    def _write(self, snapshot: dict[str, object]) -> None:
        message_id = self.message_id
        if message_id is None:
            return
        prefix = self.delivered_prefix
        state = str(snapshot["state"])
        # A `not_started` row must carry nothing delivered; the store's own check
        # says so, and the prefix is only non-empty once something was spoken.
        if state == DeliveryState.NOT_STARTED.value:
            prefix = ""
        with self._engine.begin() as connection:
            event = (
                connection.execute(
                    text(
                        "select coalesce(max(event), 0) + 1 from speech_deliveries "
                        " where message_id = :id"
                    ),
                    {"id": message_id},
                ).scalar_one()
                or 1
            )
            connection.execute(
                _DELIVERY_EVENT,
                {
                    "message_id": message_id,
                    "voice_session_id": self._voice_session_id,
                    "event": event,
                    "state": state,
                    "delivered_prefix": prefix,
                    "delivered_characters": len(prefix),
                    "segments_delivered": self.sink.segments_played,
                    "segments_total": (
                        len(self.segmenter.segments) if self.segmenter._closed else None
                    ),
                    "reason": snapshot.get("reason"),
                    "first_audio_ms": self.first_audio_ms,
                    "elapsed_ms": self.elapsed_ms,
                },
            )

    def record_segments(self) -> int:
        """Write one ephemeral `speech_generations` row per segment actually spoken.

        Text, ordering, digests, timings and the clone prompt — **no path and no
        bytes**, and `audio_retained` false, because the waveform was delivered
        and released. Returns how many rows were written.
        """
        message_id = self.message_id
        if message_id is None or not self.spoken:
            return 0
        with self._engine.begin() as connection:
            voice_id = connection.execute(
                _VOICE_ID, {"digest": self._voice.reference_sha256}
            ).scalar_one_or_none()
            if voice_id is None:
                raise VoiceUnavailableError(
                    "the governed voice has no `speech_voices` row, so a spoken segment "
                    "cannot be attributed to it; nothing was recorded."
                )
            for spoken in self.spoken:
                connection.execute(
                    _GENERATION,
                    {
                        "voice_id": voice_id,
                        "message_id": message_id,
                        "model_config_id": self._configuration.id,
                        "final_text": spoken.text,
                        "final_text_sha256": hashlib.sha256(spoken.text.encode()).hexdigest(),
                        "provider": self._configuration.provider,
                        "model_identifier": self._configuration.model_identifier,
                        "model_revision": getattr(self._speech, "model_revision", "") or "",
                        "quantization": getattr(self._speech, "quantization", "") or "",
                        "runtime": "mlx-audio",
                        "runtime_version": "",
                        "generation": "{}",
                        "clone_prompt_sha256": spoken.clone_prompt_sha256,
                        "audio_sha256": spoken.audio_sha256,
                        "audio_bytes": spoken.audio_bytes,
                        "sample_rate": spoken.sample_rate,
                        "duration_seconds": round(spoken.duration_seconds, 3),
                        "elapsed_ms": spoken.generated_ms,
                        "segment_index": spoken.index,
                        "segment_reason": spoken.reason,
                    },
                )
        return len(self.spoken)


@dataclass(frozen=True)
class DeliveryRecord:
    """A delivery as the store holds it: the newest event, and its prefix."""

    message_id: UUID
    state: DeliveryState
    delivered_prefix: str
    delivered_characters: int
    segments_delivered: int
    segments_total: int | None
    reason: str | None
    events: int


_NEWEST = text(
    "select message_id, state, delivered_prefix, delivered_characters, segments_delivered, "
    "       segments_total, reason, event "
    "  from speech_deliveries where message_id = :id order by event desc limit 1"
)

_COUNT = text("select count(*) from speech_deliveries where message_id = :id")


def delivery_for(engine: Engine, message_id: UUID) -> DeliveryRecord | None:
    """What delivery actually did for this message, from the record.

    The newest event is the state. There is no UPDATE anywhere, so an
    `interrupted` delivery stays interrupted unless a later event says otherwise
    and says when.
    """
    with engine.connect() as connection:
        row = connection.execute(_NEWEST, {"id": message_id}).one_or_none()
        if row is None:
            return None
        events = connection.execute(_COUNT, {"id": message_id}).scalar_one()
    return DeliveryRecord(
        message_id=row.message_id,
        state=DeliveryState(row.state),
        delivered_prefix=row.delivered_prefix,
        delivered_characters=row.delivered_characters,
        segments_delivered=row.segments_delivered,
        segments_total=row.segments_total,
        reason=row.reason,
        events=events,
    )


#: The Val messages in this conversation whose speech ended short, newest first.
#: Read when the next turn is assembled, so later context can reflect what the
#: owner actually heard rather than what Core generated.
_SHORT_DELIVERIES = text(
    "select d.message_id, d.state, d.delivered_prefix, d.delivered_characters, "
    "       d.segments_delivered, d.segments_total, d.reason, m.content "
    "  from speech_deliveries d "
    "  join messages m on m.id = d.message_id "
    " where m.conversation_id = :conversation "
    "   and d.event = (select max(x.event) from speech_deliveries x "
    "                   where x.message_id = d.message_id) "
    "   and d.state in ('interrupted', 'failed', 'not_started') "
    " order by m.sequence desc"
)


@dataclass(frozen=True)
class ShortDelivery:
    """A Val answer the owner did not hear the whole of."""

    message_id: UUID
    state: DeliveryState
    delivered_characters: int
    total_characters: int
    reason: str | None

    @property
    def heard_nothing(self) -> bool:
        return self.delivered_characters == 0


def short_deliveries(engine: Engine, conversation_id: UUID) -> tuple[ShortDelivery, ...]:
    """Answers in this conversation whose speech ended short, newest first."""
    with engine.connect() as connection:
        rows = connection.execute(_SHORT_DELIVERIES, {"conversation": conversation_id}).all()
    return tuple(
        ShortDelivery(
            message_id=row.message_id,
            state=DeliveryState(row.state),
            delivered_characters=row.delivered_characters,
            total_characters=len(row.content or ""),
            reason=row.reason,
        )
        for row in rows
    )
