"""Val listens: one live voice session, and the canonical turn it produces.

Owner execution order, Voice mode work package 1. Everything here exists to make
one sentence true:

    **A spoken turn is an ordinary turn.**

So there is no voice cognition route, no voice-specific classification, no voice
exemption from consequence handling, and nothing here reaches a provider. When an
utterance settles, its text goes through the ordinary Core path — the same door a
typed turn uses — and therefore through project resolution, classification, the
strip and blind machinery, memory, recall, the record-state envelope, the persona,
routing, budget and persistence, unchanged.

Three distinctions this module refuses to blur:

**Provisional is not final.** A rolling guess is mutable working state. It is not
a message, not history, not recall evidence, not Partner context and not indexed.
It lives in this object and in a text-only recovery journal, and there is no query
from either into conversation history: recall reads `messages_current`, and
nothing here is part of it.

**Recovered is not canonical.** A guess that survived a crash comes back labelled
`interrupted`. Nothing promotes it to something the owner said.

**Consequential acts run on settled text only.** The classifier sees the final
transcript and never a guess, because a guess never reaches `send` at all.

And the merge rule the order calls resume-before-delivery: when the owner pauses,
the utterance endpoints, and he carries straight on before Val has said anything
aloud, that is **one** thing he meant to say. Two visible owner messages for one
human utterance is the failure to avoid. Before submission the two halves are
simply joined, which costs nothing and cancels nothing. After submission the
canonical wording is corrected through the existing append-only revision
machinery — never by UPDATE, never by deleting the first turn, and never at all
when the message anchors a recorded decision, where faking continuity would
falsify evidence that was valid when it was produced.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import Engine, text

from val_domain import timings
from val_domain.provider import DeltaSink
from val_domain.speech import DeliveryState
from val_domain.timings import mark
from val_domain.voice import (
    LiveRecognizer,
    ProvisionalText,
    RecognizerEvent,
    VoiceSessionState,
    VoiceUnavailableError,
    VoiceUtterance,
)
from val_gateway.deliberate import DeliberatedOutcome
from val_gateway.exchange import ClarificationNeeded
from val_gateway.loop import TruncatedTurn, Turn, UnansweredTurn
from val_gateway.revisions import RevisionRefusedError, retract
from val_policy.egress import LiveVoiceConversations

_LOGGER = logging.getLogger("val.voice")

#: How long after an utterance settles the house waits before submitting it, in
#: case the owner was only drawing breath. Long enough to catch a resumed
#: sentence, short enough that an ordinary turn does not feel held back.
RESUME_GRACE_SECONDS = 1.1

#: How often the recovery journal may record the guess in progress. The journal
#: exists to survive a crash mid-utterance, not to keep every guess: a row per
#: provisional would be a transcript of the recognizer's uncertainty, which is
#: nobody's business and no help in recovery.
JOURNAL_EVERY_SECONDS = 1.0

#: Guesses shorter than this are not journalled at all. A crash that loses two
#: words costs nothing to recover from, and the row would outlive its purpose.
JOURNAL_MIN_CHARACTERS = 8

#: A placeholder for "no durable session row yet". Never written to the store —
#: the session's id is a database value — and only ever appears in a view.
NO_SESSION = UUID(int=0)


class Submit(Protocol):
    """How a settled utterance becomes a turn.

    Injected rather than called directly so this module states exactly what it
    needs from Core — text in, outcome out — and so a test can hold the boundary
    without a provider. The *implementation* passed in is always the ordinary
    deliberated send; there is no voice-specific route to pass instead.

    `on_delta` is Core's visible output as it is produced (Val Core Phase 1), which
    is what lets Val begin speaking before she has finished writing. Optional, and
    ignored by a route that cannot stream: progressive speech is an improvement on
    the same turn, never a different turn.

    `merged` says this text is two halves of one sentence joined before submission
    — the resume-before-delivery case. It changes nothing about the turn; it names
    which route to canonical the live-voice seal is being applied by (owner ruling,
    24 September 2026, §2.1), so the seal row records how the text got there rather
    than assuming the ordinary case.
    """

    def __call__(
        self,
        content: str,
        conversation_id: UUID | None,
        *,
        on_delta: DeltaSink | None = None,
        merged: bool = False,
    ) -> DeliberatedOutcome: ...


class Delivery(Protocol):
    """Speech delivery for one answer, as the session needs to see it.

    A protocol rather than the class, so the session depends on *what delivery
    must be able to do* — take visible text, say whether he has begun hearing
    her, and stop — and not on how it speaks.
    """

    @property
    def audible(self) -> bool:
        """Has any audio reached the ear? **The delivered boundary.**"""
        ...

    @property
    def active(self) -> bool:
        """Is delivery live, so that owner speech now is barge-in?"""
        ...

    @property
    def state(self) -> DeliveryState:
        """How far delivery got: not_started, started, completed, interrupted, failed."""
        ...

    @property
    def delivered_prefix(self) -> str:
        """Exactly the words that reached the ear, in order."""
        ...

    @property
    def segments_delivered(self) -> int:
        """How many speech-safe pieces were handed over."""
        ...

    @property
    def cancellation_ms(self) -> float | None:
        """Service-side: signal to sink stopped. `None` if never interrupted."""
        ...

    def feed(self, delta: str) -> None: ...

    def finish(self, settled_text: str | None = None) -> None: ...

    def interrupt(self, reason: str = ...) -> float: ...

    def bind(self, message_id: UUID) -> None: ...

    def record_segments(self) -> int: ...

    @property
    def message_id(self) -> UUID | None:
        """Val's answer this delivery is about, once it is bound. Work package 3
        §11 needs it: a segment handed to the desktop must name which answer it
        belongs to, or the physical record cannot be joined to the conversation."""
        ...


#: How the session obtains delivery for one answer. `None` — the default — is a
#: session that hears and does not speak, which is exactly work package 1.
DeliveryFactory = Callable[[], Delivery]


@dataclass(frozen=True)
class VoiceTurn:
    """One canonical owner turn that arrived by voice."""

    utterance: VoiceUtterance
    outcome: DeliberatedOutcome
    conversation_id: UUID
    #: **The owner's** message — the canonical turn this utterance became.
    message_id: UUID
    #: **Val's** answer, when she gave one. Delivery is about her words, not his,
    #: so anything asking what was spoken keys on this and never on `message_id`.
    answer_message_id: UUID | None = None
    provisional_events: int = 0
    #: Set when the owner resumed after submission and the canonical wording was
    #: corrected through the revision machinery rather than by a second turn.
    #: **Superseded by `superseded_by` since the WP3 repair pass** — kept because
    #: historical turns carry it and it still describes what happened to them.
    revised_to: str | None = None
    #: Owner acceptance repair, 25 September 2026 (WP3 §1.1). The owner resumed
    #: before delivery, so this exchange was **withdrawn** — his fragment and the
    #: answer to it, both preserved in the record with their evidence and cost — and
    #: the joined wording was submitted as a new turn. This holds that joined
    #: wording. The obsolete answer never became Val's authoritative answer to it.
    superseded_by: str | None = None
    #: Why a post-submission merge was refused, when one was. Kept because a
    #: refusal is a fact about the record, not an error to swallow.
    merge_refused: str | None = None
    #: True once the caller has delivered this answer to the owner. Until then a
    #: resumed utterance may still be merged into it.
    delivered: bool = False
    #: The session clock when this turn was submitted. The fallback bound on how long
    #: a turn may remain mergeable when the recognizer reported no marks of its own
    #: (owner acceptance, 25 September 2026).
    submitted_at: float = 0.0


@dataclass(frozen=True)
class VoiceSessionView:
    """What a session looks like from outside, for the desktop to poll.

    The guess and the settled facts are separate fields, deliberately: a caller
    that renders `provisional` as a message has to have chosen to.
    """

    session_id: UUID
    conversation_id: UUID | None
    state: VoiceSessionState
    utterance: int
    provisional: str
    hearing: bool
    #: A settled utterance waiting out the resume window, or in flight. Not a turn.
    pending: str
    turns: tuple[VoiceTurn, ...]
    error: str | None
    recognizer: dict[str, str]
    endpoint: dict[str, float | int]


@dataclass
class _Utterance:
    """Bookkeeping for the breath currently being heard."""

    index: int
    provisional: str = ""
    provisional_events: int = 0
    speech_start_at: float = 0.0
    journalled_at: float = 0.0
    journal_entry: int = 0
    journalled_text: str = ""


@dataclass
class _Pending:
    """A settled utterance inside the resume window, not yet submitted."""

    utterance: VoiceUtterance
    provisional_events: int
    settled_at: float


# --- the durable record ----------------------------------------------------------------

_OPEN_SESSION = text(
    "insert into voice_sessions "
    "  (conversation_id, started_at, state, recognizer, recognizer_version, "
    "   recognizer_commit, asr_model, asr_model_sha256, vad_model, vad_model_sha256, "
    "   endpoint_configuration) "
    "values (:conversation_id, :started_at, :state, :recognizer, :recognizer_version, "
    "        :recognizer_commit, :asr_model, :asr_model_sha256, :vad_model, "
    "        :vad_model_sha256, cast(:endpoint_configuration as jsonb)) "
    "returning id"
)

_CLOSE_SESSION = text(
    "update voice_sessions set state = :state, closed_at = now(), closed_reason = :reason "
    " where id = :id and closed_at is null"
)

_PROVENANCE = text(
    "insert into voice_message_provenance "
    "  (message_id, voice_session_id, input_mode, transcription_status, finalized_at, "
    "   utterance, endpoint_reason, provisional_events, merged_from) "
    "values (:message_id, :voice_session_id, 'voice', 'final', :finalized_at, "
    "        :utterance, :endpoint_reason, :provisional_events, :merged_from)"
)

_JOURNAL = text(
    "insert into voice_recovery_journal "
    "  (voice_session_id, conversation_id, utterance, entry, provisional_text, state, "
    "   superseded_by_message_id) "
    "values (:voice_session_id, :conversation_id, :utterance, :entry, :provisional_text, "
    "        :state, :superseded_by_message_id)"
)

_LAST_ENTRY = text(
    "select entry, provisional_text from voice_recovery_journal "
    " where voice_session_id = :session and utterance = :utterance "
    " order by entry desc limit 1"
)

#: The open guesses a restart should be told about: the highest-numbered entry
#: for each utterance, where that entry still says `provisional`.
_OPEN_GUESSES = text(
    "select j.voice_session_id, j.conversation_id, j.utterance, j.entry, j.provisional_text "
    "  from voice_recovery_journal j "
    " where j.state = 'provisional' "
    "   and not exists ( "
    "         select 1 from voice_recovery_journal later "
    "          where later.voice_session_id = j.voice_session_id "
    "            and later.utterance = j.utterance "
    "            and later.entry > j.entry) "
    " order by j.recorded_at"
)


@dataclass(frozen=True)
class InterruptedUtterance:
    """A guess a crash left open. **Provisional, and labelled so.**

    Offered back to the owner as the words the recognizer had reached, never as
    something he said. Nothing acts on it and nothing submits it.
    """

    voice_session_id: UUID
    conversation_id: UUID
    utterance: int
    provisional_text: str
    state: str = "interrupted"


def interrupted(engine: Engine) -> tuple[InterruptedUtterance, ...]:
    """Guesses left open by an interrupted session, marked as interrupted.

    Called at startup. Each open entry gains one further append-only entry saying
    `interrupted`, so a second restart does not report the same guess as still
    live — and no row is ever updated in order to say it.
    """
    with engine.begin() as connection:
        rows = connection.execute(_OPEN_GUESSES).mappings().all()
        found = tuple(
            InterruptedUtterance(
                voice_session_id=row["voice_session_id"],
                conversation_id=row["conversation_id"],
                utterance=row["utterance"],
                provisional_text=row["provisional_text"],
            )
            for row in rows
        )
        for row in rows:
            connection.execute(
                _JOURNAL,
                {
                    "voice_session_id": row["voice_session_id"],
                    "conversation_id": row["conversation_id"],
                    "utterance": row["utterance"],
                    "entry": row["entry"] + 1,
                    "provisional_text": row["provisional_text"],
                    "state": "interrupted",
                    "superseded_by_message_id": None,
                },
            )
    return found


class VoiceSession:
    """One live listening session attached to one conversation.

    Owns a recognizer, the guess in progress, the resume window and the journal.
    Owns no microphone: audio is handed to `feed`. Owns no authority: a settled
    utterance is submitted through the ordinary Core path and governed there.
    """

    def __init__(
        self,
        engine: Engine,
        recognizer: LiveRecognizer,
        *,
        submit: Submit,
        conversation_id: UUID | None = None,
        resume_grace_seconds: float = RESUME_GRACE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        speech: DeliveryFactory | None = None,
        warm: Callable[[], object] | None = None,
    ) -> None:
        self._engine = engine
        self._recognizer = recognizer
        self._submit = submit
        self._grace = resume_grace_seconds
        self._now = clock
        #: Guards the session's own state. Never held across database work.
        self._lock = threading.RLock()
        #: Guards writing the session row, so two threads cannot open two.
        self._opening = threading.Lock()

        self.conversation_id = conversation_id
        self.started_at = datetime.now(UTC)
        self.endpoint = recognizer.endpoint
        self.state = VoiceSessionState.LISTENING
        self.error: str | None = None
        self._session_id: UUID | None = None
        self._utterances = 0
        self._current: _Utterance | None = None
        self._pending: _Pending | None = None
        self._inflight: _Pending | None = None
        self._turns: list[VoiceTurn] = []
        self._worker: threading.Thread | None = None
        #: How this session speaks, if it speaks at all. `None` is work package 1's
        #: session exactly: it hears, and says nothing aloud.
        self._speech = speech
        #: Delivery of the answer to the turn now in flight, while it lasts.
        self._delivery: Delivery | None = None
        #: The delivery that has just finished, kept until the next turn replaces it.
        #: Owner execution order, 24 September 2026 (§11): the desktop collects
        #: synthesised audio a poll at a time, and a segment produced in the last
        #: instant of a turn would otherwise be discarded with the delivery before
        #: the desktop had a chance to ask for it — losing the end of her sentence.
        #: Held, not accumulated: exactly one, replaced when the next turn begins.
        self._recent: Delivery | None = None
        #: Every barge-in this session performed, in milliseconds from the
        #: recognizer's event reaching delivery control to the sink stopping.
        self.cancellations: list[float] = []
        #: How the cognition runtime is brought up early. A local model carries an
        #: idle TTL, so the first turn after an idle hour otherwise pays its load
        #: while the owner waits — measured 9.143 s (latency pass §12).
        self._warm = warm
        #: What warming found and did, for the record. `None` until it has run.
        self.warmed: object | None = None

    # --- identity -------------------------------------------------------------------

    @property
    def session_id(self) -> UUID:
        """The durable session's id, written on first need.

        Written lazily rather than at open because a voice session belongs to a
        conversation, and a conversation cannot exist without a message: for a
        brand-new chat the conversation is created by the first spoken turn
        itself. The consequence is stated rather than hidden — until a
        conversation exists there is nothing to journal a guess against, so the
        very first utterance of a brand-new chat has no crash recovery. Every
        later one does, and a session opened on an existing conversation has it
        throughout.
        """
        return self._ensure_session()

    def _ensure_session(self) -> UUID:
        with self._opening:
            if self._session_id is not None:
                return self._session_id
            conversation_id = self.conversation_id
            if conversation_id is None:
                raise VoiceUnavailableError(
                    "this voice session is not attached to a conversation yet: a voice "
                    "session is an input modality on a conversation, and a conversation "
                    "exists once it has a message."
                )
            record = self._recognizer.identity.as_record()
            with self._engine.begin() as connection:
                self._session_id = connection.execute(
                    _OPEN_SESSION,
                    {
                        "conversation_id": conversation_id,
                        "started_at": self.started_at,
                        "state": VoiceSessionState.LISTENING.value,
                        "recognizer": record["recognizer"],
                        "recognizer_version": record["recognizer_version"],
                        "recognizer_commit": record["recognizer_commit"],
                        "asr_model": record["asr_model"],
                        "asr_model_sha256": record["asr_model_sha256"],
                        "vad_model": record["vad_model"],
                        "vad_model_sha256": record["vad_model_sha256"],
                        "endpoint_configuration": json.dumps(
                            self.endpoint.as_record(), sort_keys=True
                        ),
                    },
                ).scalar_one()
            return self._session_id

    # --- lifecycle ------------------------------------------------------------------

    def start(self) -> None:
        """Bring the recognizer up. Nothing is heard until this succeeds."""
        try:
            self._recognizer.start()
        except VoiceUnavailableError as failure:
            self._fail(str(failure))
            raise
        with self._lock:
            self.state = VoiceSessionState.LISTENING
        # The cognition runtime is brought up **now**, on its own thread, while he
        # is still drawing breath — not when he stops talking. It is the same
        # readiness call the turn makes, and the turn still makes it: this only
        # moves the waiting off the moment he is waiting.
        if self._warm is not None:
            threading.Thread(target=self._warm_runtime, daemon=True).start()

    def _warm_runtime(self) -> None:
        """Bring up what the first turn would otherwise wait for.

        Two things now: the cognition runtime (latency pass §12) and the voice model
        (owner acceptance, 25 September 2026 — 6.708 s against 2.727 s for the same
        phrase, the difference being the weights coming off disk). Neither is a gate:
        both are reported and swallowed, and the turn asks for itself regardless.
        """
        if self._warm is None:
            return
        try:
            self.warmed = self._warm()
        except Exception as failure:  # reported, never fatal: warming is not a gate
            self.warmed = {"warmed": False, "reason": f"{type(failure).__name__}: {failure}"}

    def close(self, reason: str = "closed by the caller") -> None:
        """Stop listening, settle the record, and release everything held."""
        with self._lock:
            current, self._current = self._current, None
            pending, self._pending = self._pending, None
        try:
            self._recognizer.stop()
        except VoiceUnavailableError:
            pass
        # A guess that never became a turn is abandoned, said plainly. The words
        # are kept as the guess they were; nothing promotes them.
        if current is not None and current.journal_entry:
            self._journal(current, "abandoned", words=current.journalled_text)
        if pending is not None:
            self._abandon(pending.utterance)
        with self._lock:
            state = VoiceSessionState.ERROR if self.error else VoiceSessionState.CLOSED
            self.state = state
            session_id = self._session_id
            detail = self.error or reason
        if session_id is not None:
            with self._engine.begin() as connection:
                connection.execute(
                    _CLOSE_SESSION, {"id": session_id, "state": state.value, "reason": detail}
                )
        with self._lock:
            # Voice off releases the hand-off as well as the recognizer: audio the
            # desktop never collected is discarded rather than left waiting for a
            # session that has ended (§5, §11).
            recent, self._recent = self._recent, None
        if recent is not None:
            sink = getattr(recent, "sink", None)
            stop = getattr(sink, "stop", None)
            if callable(stop):
                stop("the voice session ended")

    def _fail(self, detail: str) -> None:
        with self._lock:
            self.error = detail
            self.state = VoiceSessionState.ERROR

    # --- audio in -------------------------------------------------------------------

    def feed(self, pcm: bytes) -> None:
        """One block of the canonical PCM, handed straight to the recognizer.

        Not stored, not accumulated here, not written anywhere. The block's only
        onward path is the recognizer's own volatile buffer.
        """
        self._recognizer.feed(pcm)
        self.advance()

    def finalize(self) -> None:
        """End the utterance in progress now, rather than waiting for silence."""
        self._recognizer.flush()
        self.advance()

    @property
    def speech_handover(self) -> Delivery | None:
        """The delivery whose audio the desktop may still collect.

        The one in flight, or the one that has just finished. Owner execution order,
        24 September 2026 (§11): audio is collected a poll at a time, so the end of
        an answer must remain collectable for a moment after the turn is over —
        otherwise her last few words are synthesised and silently dropped.
        """
        with self._lock:
            return self._delivery if self._delivery is not None else self._recent

    @property
    def delivery(self) -> Delivery | None:
        """Speech delivery for the answer being spoken now, if one is."""
        with self._lock:
            return self._delivery

    def interrupt_delivery(self, reason: str = "the caller signalled barge-in") -> float | None:
        """Stop Val speaking now, from outside the recognizer's own observation.

        The same act `_began` performs when the recognizer hears him: the capture
        layer that will hear him first (work package 3) reaches it through here.
        Returns the service-side cancellation interval in milliseconds, or `None`
        when nothing was being spoken.
        """
        with self._lock:
            delivering = self._delivery
        if delivering is None or not delivering.active:
            return None
        elapsed = delivering.interrupt(reason)
        self.cancellations.append(elapsed)
        return elapsed

    def deliver(self, message_id: UUID) -> None:
        """The caller has delivered this turn's answer to the owner.

        After this, resumed speech is a new turn rather than a continuation: the
        owner has heard Val, so what he says next is a reply and not the rest of a
        sentence. In this package nothing speaks aloud, so nothing calls this
        automatically — the delivering layer does, in work package 2.
        """
        with self._lock:
            self._turns = [
                replace(turn, delivered=True) if turn.message_id == message_id else turn
                for turn in self._turns
            ]

    # --- the state machine ----------------------------------------------------------

    def advance(self) -> None:
        """Take in everything the recognizer has observed, and act on it.

        Called on every feed and every poll. Never blocks on cognition: a settled
        utterance is submitted on a worker, so audio keeps arriving while Val
        thinks.
        """
        for event in self._recognizer.drain():
            self._observe(event)
        self._submit_if_due()

    def _observe(self, event: RecognizerEvent) -> None:
        if event.kind == "speech_start":
            self._began(event)
        elif event.kind == "provisional":
            self._guessed(event)
        elif event.kind == "speech_end":
            with self._lock:
                self.state = VoiceSessionState.THINKING
        elif event.kind == "final":
            self._settled(event)
        elif event.kind == "error":
            self._fail(event.detail or "the recognizer reported a failure")

    def _began(self, event: RecognizerEvent) -> None:
        with self._lock:
            self._utterances = max(self._utterances + 1, event.session)
            self._current = _Utterance(index=self._utterances, speech_start_at=event.at)
            self.state = VoiceSessionState.HEARING
            delivering = self._delivery
        # **Barge-in.** He is speaking while Val is delivering, so she stops. The
        # sink is stopped first and the record follows: what matters is that she
        # is not talking over him. Nothing already executed is undone — speech
        # stopping is not a time machine — and the exact prefix he heard goes on
        # the record rather than being reconstructed later.
        if delivering is not None and delivering.active:
            self.cancellations.append(delivering.interrupt("the owner began speaking"))

    def _guessed(self, event: RecognizerEvent) -> None:
        """A revised guess: held in memory, and journalled on a throttle."""
        with self._lock:
            if self._current is None:
                # A guess with no start. Take the recognizer's own numbering
                # rather than inventing one.
                self._utterances = max(self._utterances, event.session)
                self._current = _Utterance(index=self._utterances)
            current = self._current
            current.provisional = event.text
            current.provisional_events += 1
            self.state = VoiceSessionState.HEARING
            due = self._now() - current.journalled_at >= JOURNAL_EVERY_SECONDS
            worth_keeping = len(event.text.strip()) >= JOURNAL_MIN_CHARACTERS
            record = due and worth_keeping
            if record:
                current.journalled_at = self._now()
        if record:
            self._journal(current, "provisional")

    def _settled(self, event: RecognizerEvent) -> None:
        """A final transcription: a new pending turn, or a resumed one."""
        # Owner acceptance, 25 September 2026 (WP3 Step B §10). **The endpoint evidence,
        # written where it survives the run.** The repair pass taught the helper to
        # report the silence that ended each utterance and the gap before it began, and
        # stopped one boundary short: the event type dropped the fields, so his Step B
        # run — the run they were added for — could not be measured. They reach here
        # now, and they are logged, because nothing else records them and an unrecorded
        # measurement is not evidence. Durations only: no audio, no content.
        _LOGGER.info(
            "voice endpoint: utterance=%s reason=%s voiced=%.3fs silence=%.3fs "
            "gap_before=%s length=%.3fs",
            event.session,
            event.reason or "silence",
            event.voiced_seconds,
            event.silence_seconds,
            "unknown" if event.gap_before_seconds is None else f"{event.gap_before_seconds:.3f}s",
            event.seconds,
        )
        merge_into_submitted = False
        with self._lock:
            current, self._current = self._current, None
            index = current.index if current is not None else max(self._utterances, event.session)
            events = current.provisional_events if current is not None else 0
            words = event.text.strip()
            if not words:
                # Silence, or speech that carried no words. **No user turn.**
                self.state = VoiceSessionState.LISTENING
                abandon = current if current is not None and current.journal_entry else None
            else:
                abandon = None
        if not words:
            if abandon is not None:
                self._journal(abandon, "abandoned", words=abandon.journalled_text)
            return
        with self._lock:
            mark("transcript_final")
            settled = VoiceUtterance(
                session_id=self._session_id or NO_SESSION,
                utterance=index,
                text=words,
                reason=event.reason or "silence",
                speech_start_at=current.speech_start_at if current is not None else 0.0,
                endpoint_at=event.endpoint_at,
                final_at=event.at,
            )
            waiting = self._pending
            if waiting is not None:
                # Still inside the resume window: he was drawing breath, not
                # finishing. Nothing has been submitted, so nothing needs
                # cancelling — the two halves are simply one utterance.
                self._pending = _Pending(
                    utterance=waiting.utterance.merged_with(settled),
                    provisional_events=waiting.provisional_events + events,
                    settled_at=self._now(),
                )
                self.state = VoiceSessionState.THINKING
                return
            # Nothing waiting. If a turn has been submitted and Val has not yet
            # delivered it, this is the same intended utterance arriving late.
            merge_into_submitted = self._mergeable(settled) is not None
            if not merge_into_submitted:
                self._pending = _Pending(
                    utterance=settled, provisional_events=events, settled_at=self._now()
                )
                self.state = VoiceSessionState.THINKING
                return
        self._merge_after_submission(settled, events)
        with self._lock:
            self.state = VoiceSessionState.LISTENING

    def _mergeable(self, resumed: VoiceUtterance | None = None) -> VoiceTurn | None:
        """The turn a resumed utterance may still be joining, or None.

        Two conditions, and the second was missing until owner acceptance found it.

        **He must not have begun to hear her.** Once the first audio has reached the
        ear, what he says next is a reply rather than the rest of his own sentence
        (§12).

        **And the pause must be short enough to be a pause.** Owner acceptance,
        24 September 2026: a fragment whose answer was interrupted before any audio
        stayed `delivered = False` for ever, so it remained mergeable indefinitely —
        and **thirty-five seconds later** a fresh, deliberate attempt was appended to
        it, producing his own words in the wrong order with the stale fragment first.
        The resume mechanism exists to bridge an endpoint that fired inside one
        sentence, so the bridge is bounded by **the configured resume window**: if he
        began speaking again more than that long after the previous utterance ended,
        it is a new turn, whatever state its answer is in.

        `resumed` is the utterance asking to merge. It is optional only because the
        two callers ask at different moments; without it the time bound cannot be
        applied, so the caller that omits it gets the delivery check alone and must
        not use the result to merge.
        """
        if self._delivery is not None and self._delivery.audible:
            return None
        candidate = next(
            (
                turn
                for turn in reversed(self._turns)
                if not turn.delivered
                and turn.revised_to is None
                and turn.superseded_by is None
                and turn.merge_refused is None
            ),
            None,
        )
        if candidate is None or resumed is None:
            return candidate
        # The pause between his two stretches of speech: from the previous utterance's
        # endpoint to this one's first voiced frame, both the recognizer's own
        # monotonic marks.
        pause = resumed.speech_start_at - candidate.utterance.endpoint_at
        if resumed.speech_start_at and candidate.utterance.endpoint_at:
            return None if pause > self._grace else candidate
        # **A recognizer that reported no marks does not thereby unlock an unbounded
        # merge.** Falling back to the session's own clock: how long this turn has been
        # waiting for an answer he has not heard. It is a looser measure than the pause
        # — it includes cognition — so it is given the grace twice over, and it still
        # bounds what was previously unbounded.
        waited = self._now() - candidate.submitted_at
        return None if waited > self._grace * 2 else candidate

    def _merge_after_submission(self, settled: VoiceUtterance, events: int) -> None:
        """Supersede an already-submitted turn Val has not yet delivered.

        **Owner acceptance repair, 25 September 2026 (WP3 §1.1).** This used to
        *revise* the owner's message and leave Val's answer in place, marked as
        having answered the earlier wording. That is the right doctrine for a
        correction Lord Armand chose to make; it is the wrong one here, because he
        chose nothing — the house split one sentence in two, answered the first
        half, and then relabelled his words underneath an answer to something else.
        In his acceptance every one of five spoken turns ended that way.

        So the exchange is **superseded** instead:

        1. the obsolete answer's speech is stopped before a word of it can be
           spoken — available because `_mergeable` only returns a turn whose
           delivery has not become audible;
        2. the exchange is **withdrawn** through the existing retraction machinery
           — his fragment and the answer to it both stay in the record, marked,
           with every classification, cost and measurement attached to them
           untouched, exactly as Remove does;
        3. the joined wording is submitted as a **new** turn, which gets its own
           answer and its own delivery.

        The consequence is the invariant §1.1 asks for, in its strongest form: a
        voice answer is never bound to wording that changed afterwards, because a
        voice turn's message is never revised after the fact at all. An obsolete
        call that really ran stays on `model_calls` as the historical fact it is,
        and no longer masquerades as the answer to what he actually said.
        """
        with self._lock:
            recent = self._mergeable(settled)
            delivery = self._delivery if self._delivery is not None else self._recent
        if recent is None:
            return
        combined = f"{recent.utterance.text.rstrip()} {settled.text.lstrip()}".strip()

        # 1. Nothing of the obsolete answer is spoken. Checked against the message it
        #    belongs to, so a later turn's delivery is never stopped by mistake.
        if delivery is not None and delivery.message_id == recent.answer_message_id:
            delivery.interrupt("the owner was still speaking; this answer is superseded")

        # 2. Withdraw the exchange. A retraction deletes no evidence and invalidates
        #    none; it takes the pair out of the working conversation and out of both
        #    recall paths, which is what stops the obsolete answer being treated as
        #    current by anything downstream.
        try:
            retract(
                self._engine,
                recent.message_id,
                note=(
                    "superseded: the owner resumed before delivery, so this half-heard "
                    "utterance and the answer to it are withdrawn in favour of the "
                    "complete wording"
                ),
            )
        except RevisionRefusedError as refused:
            # Already withdrawn, or refused for a recorded reason. Nothing is faked:
            # the resumed speech becomes its own turn and the refusal is on record.
            note = f"{refused.reason}: {refused}"
            with self._lock:
                self._turns = [
                    replace(turn, merge_refused=note)
                    if turn.message_id == recent.message_id
                    else turn
                    for turn in self._turns
                ]
                self._pending = _Pending(
                    utterance=settled, provisional_events=events, settled_at=self._now()
                )
            return

        # 3. The complete wording becomes a new turn, through the ordinary door.
        with self._lock:
            self._turns = [
                replace(turn, superseded_by=combined)
                if turn.message_id == recent.message_id
                else turn
                for turn in self._turns
            ]
            self._pending = _Pending(
                utterance=replace(
                    settled,
                    text=combined,
                    merged_from=(*recent.utterance.merged_from, recent.utterance.utterance),
                ),
                provisional_events=recent.provisional_events + events,
                settled_at=self._now(),
            )
            self.state = VoiceSessionState.THINKING

    def _submit_if_due(self) -> None:
        """Submit a pending utterance once the resume window has passed."""
        with self._lock:
            pending = self._pending
            if pending is None or self._inflight is not None:
                return
            if self._now() - pending.settled_at < self._grace:
                return
            self._pending = None
            self._inflight = pending
            # A plain thread starts with an empty context, so a diagnostic recorder
            # installed by the caller would be invisible inside the turn. Carried
            # explicitly rather than lost (latency pass §8); `None` in production,
            # where nothing is recording.
            worker = threading.Thread(
                target=self._run, args=(pending, timings.current()), daemon=True
            )
            self._worker = worker
        mark("owner_turn_submitted")
        worker.start()

    def await_turn(self, timeout: float = 180.0) -> None:
        """Block until nothing is pending or in flight.

        For a caller that wants the answer rather than a poll — the acceptance
        path, and the tests. The live desktop polls instead.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.advance()
            with self._lock:
                busy = self._pending is not None or self._inflight is not None
                worker = self._worker
            if not busy:
                return
            if worker is not None and worker.is_alive():
                worker.join(timeout=min(0.5, max(0.0, deadline - time.monotonic())))
            else:
                time.sleep(0.02)
        raise VoiceUnavailableError(f"the spoken turn did not settle within {timeout:.0f}s")

    def _run(self, pending: _Pending, recorder: timings.TurnTimings | None = None) -> None:
        """One settled utterance, through the ordinary Core path — and spoken."""
        with timings.recording(recorder) if recorder is not None else nullcontext():
            self._run_turn(pending)

    def _run_turn(self, pending: _Pending) -> None:
        utterance = pending.utterance
        # Delivery is created before the turn is submitted, so Val can begin
        # speaking the first sentence while she is still writing the second. It
        # receives only Core's visible output, through Core's own delta sink.
        delivery = None if self._speech is None else self._speech()
        with self._lock:
            self._delivery = delivery
            # The previous turn's hand-off ends when this one begins: one delivery
            # is collectable at a time, and an older one is released here.
            self._recent = None
        try:
            outcome = self._submit(
                utterance.text,
                self.conversation_id,
                on_delta=None if delivery is None else delivery.feed,
                # Which route to canonical the seal is applied by: an ordinary
                # settled utterance, or two halves joined inside the resume window.
                merged=bool(utterance.merged_from),
            )
        except Exception as failure:
            if delivery is not None:
                delivery.interrupt("the turn failed before it could be spoken")
            self._fail(f"the spoken turn could not be submitted: {failure}")
            with self._lock:
                self._inflight = None
                self._delivery = None
            return
        try:
            self._record(pending, outcome, delivery)
        except Exception as failure:
            # The turn itself succeeded and is in the conversation; its
            # provenance did not get written. That is a state the owner must be
            # able to see, and this runs on a worker thread whose exception
            # nobody would otherwise observe — so it is reported rather than left
            # to die quietly with the thread.
            self._fail(
                f"the spoken turn was answered and its voice provenance could not be "
                f"recorded: {failure}"
            )
        finally:
            with self._lock:
                self._inflight = None
                # The delivery leaves `_delivery` and stays collectable through
                # `_recent`, so the last synthesised segment of an answer is not
                # thrown away between the turn ending and the desktop's next poll.
                if self._delivery is not None:
                    self._recent = self._delivery
                self._delivery = None
                if self.state is VoiceSessionState.THINKING:
                    self.state = VoiceSessionState.LISTENING

    def _record(
        self, pending: _Pending, outcome: DeliberatedOutcome, delivery: Delivery | None = None
    ) -> None:
        """The provenance sidecar, the journal's supersession, and what was heard."""
        conversation_id, message_id = _identify(outcome)
        if conversation_id is None or message_id is None:
            # A clarification, or a refusal before anything was written: no
            # canonical turn exists, so there is no provenance to record — and no
            # message for a delivery to be about.
            if delivery is not None:
                delivery.interrupt("the turn produced no message to speak")
            return
        with self._lock:
            self.conversation_id = conversation_id
        session_id = self._ensure_session()
        utterance = pending.utterance
        with self._engine.begin() as connection:
            connection.execute(
                _PROVENANCE,
                {
                    "message_id": message_id,
                    "voice_session_id": session_id,
                    "finalized_at": datetime.now(UTC),
                    "utterance": utterance.utterance,
                    "endpoint_reason": utterance.reason,
                    "provisional_events": pending.provisional_events,
                    "merged_from": list(utterance.merged_from),
                },
            )
        self._supersede(utterance, message_id)

        # Speech, settled. `bind` names the persisted message so the delivery
        # record can exist at all; `finish` flushes the exact remaining suffix and
        # waits for the voice; `record_segments` writes the ephemeral rows. An
        # interrupted delivery has already closed itself, and `finish` on it does
        # nothing — which is why a barge-in's record is not overwritten here.
        heard = False
        answer_message_id: UUID | None = None
        answered = _answered(outcome)
        if answered is not None:
            answer_message_id = answered[0]
        if delivery is not None:
            answer = answered
            if answer is None:
                # No persisted answer of Val's: a truncated fragment is not
                # something she said, and an unanswered turn has nothing to say.
                # Delivery ends with the reason and leaves no record, because
                # there is no assistant message for a record to be about.
                delivery.interrupt("the turn produced no answer of Val's to speak")
            else:
                val_message_id, val_text = answer
                delivery.bind(val_message_id)
                delivery.finish(val_text)
                delivery.record_segments()
                heard = delivery.audible
        with self._lock:
            # The turn is finished and its delivery is no longer the one in flight —
            # but its audio may not have been collected yet. Owner execution order,
            # 24 September 2026 (§11): it stays collectable through `_recent` until
            # the next turn begins, so the last segment of an answer is not dropped
            # between `record_segments` and the desktop's next poll.
            self._recent = self._delivery
            self._delivery = None
            self._turns.append(
                VoiceTurn(
                    utterance=replace(utterance, session_id=session_id),
                    outcome=outcome,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    answer_message_id=answer_message_id,
                    provisional_events=pending.provisional_events,
                    # **The delivered boundary is the first audio**, and it has
                    # already been crossed by the time this row is written.
                    delivered=heard,
                    # When it was submitted, on the session's own clock: the fallback
                    # bound on how long it may remain mergeable.
                    submitted_at=pending.settled_at,
                )
            )

    # --- the journal ----------------------------------------------------------------

    def _journal(self, current: _Utterance, state: str, *, words: str | None = None) -> None:
        """One append-only recovery entry. **Text only, and never `final`.**"""
        session_id, conversation_id = self._session_id, self.conversation_id
        if session_id is None or conversation_id is None:
            # Nothing to attach a guess to yet; stated in `session_id`.
            return
        provisional = current.provisional if words is None else words
        if not provisional.strip():
            return
        with self._lock:
            current.journal_entry += 1
            entry = current.journal_entry
            current.journalled_text = provisional
            utterance = current.index
        with self._engine.begin() as connection:
            connection.execute(
                _JOURNAL,
                {
                    "voice_session_id": session_id,
                    "conversation_id": conversation_id,
                    "utterance": utterance,
                    "entry": entry,
                    "provisional_text": provisional,
                    "state": state,
                    "superseded_by_message_id": None,
                },
            )

    def _supersede(self, utterance: VoiceUtterance, message_id: UUID) -> None:
        """Close each guess append-only, naming the turn that replaced it.

        A new entry, never an update: the guess and its supersession are both on
        the record, so the order of events stays readable. Every utterance the
        turn absorbed is closed, not only the last one.
        """
        self._close_guesses(utterance, "superseded", message_id)

    def _abandon(self, utterance: VoiceUtterance) -> None:
        """A settled utterance the session closed without submitting."""
        self._close_guesses(utterance, "abandoned", None)

    def _close_guesses(
        self, utterance: VoiceUtterance, state: str, message_id: UUID | None
    ) -> None:
        session_id, conversation_id = self._session_id, self.conversation_id
        if session_id is None or conversation_id is None:
            return
        with self._engine.begin() as connection:
            for number in (*utterance.merged_from, utterance.utterance):
                last = connection.execute(
                    _LAST_ENTRY, {"session": session_id, "utterance": number}
                ).one_or_none()
                connection.execute(
                    _JOURNAL,
                    {
                        "voice_session_id": session_id,
                        "conversation_id": conversation_id,
                        "utterance": number,
                        "entry": (last.entry if last is not None else 0) + 1,
                        # The words as last journalled when there is such a row,
                        # and otherwise the settled text — which is what a reader
                        # recovering this utterance would need either way.
                        "provisional_text": (
                            last.provisional_text if last is not None else utterance.text
                        ),
                        "state": state,
                        "superseded_by_message_id": message_id,
                    },
                )

    # --- what the outside sees ------------------------------------------------------

    def provisional(self) -> ProvisionalText | None:
        """The guess in progress, as the thing it is. Never a message."""
        with self._lock:
            current = self._current
            if current is None or not current.provisional:
                return None
            return ProvisionalText(
                session_id=self._session_id or NO_SESSION,
                utterance=current.index,
                text=current.provisional,
                at=self._now(),
            )

    def snapshot(self) -> VoiceSessionView:
        """Everything a polling caller needs, in one consistent read."""
        self.advance()
        with self._lock:
            current = self._current
            waiting = self._pending or self._inflight
            return VoiceSessionView(
                session_id=self._session_id or NO_SESSION,
                conversation_id=self.conversation_id,
                state=self.state,
                utterance=current.index if current is not None else self._utterances,
                provisional=current.provisional if current is not None else "",
                hearing=current is not None,
                pending="" if waiting is None else waiting.utterance.text,
                turns=tuple(self._turns),
                error=self.error,
                recognizer=self._recognizer.identity.as_record(),
                endpoint=self.endpoint.as_record(),
            )

    def __enter__(self) -> VoiceSession:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _answered(outcome: DeliberatedOutcome) -> tuple[UUID, str] | None:
    """Val's persisted answer for this turn — its id and its exact words.

    `None` when there is none to speak: a clarification, an unanswered turn, or a
    truncated fragment, which Core deliberately does not persist as her reply. A
    fragment she did not finish saying is not something to say aloud.
    """
    if isinstance(outcome, ClarificationNeeded | UnansweredTurn):
        return None
    settled = outcome.turn
    if isinstance(settled, TruncatedTurn):
        return None
    return settled.val_message.id, settled.val_message.content


def _identify(outcome: DeliberatedOutcome) -> tuple[UUID | None, UUID | None]:
    """The conversation and the owner's message, whatever shape the outcome took.

    A clarification produced no turn and no message: there is nothing to attach
    provenance to, and saying so is the honest answer rather than inventing an id.
    """
    if isinstance(outcome, ClarificationNeeded):
        return None, None
    if isinstance(outcome, UnansweredTurn):
        # The message was said and persisted; Val did not answer. It is a
        # voice-origin owner turn either way, and its provenance belongs on record.
        return outcome.conversation.id, outcome.user_message.id
    settled: Turn | TruncatedTurn = outcome.turn
    return settled.conversation.id, settled.user_message.id


class VoiceSessions:
    """The sessions this process is listening with.

    Somewhere for a session to live between one HTTP call and the next.
    Deliberately a plain in-process map: a live voice session *is* process state —
    it holds a subprocess and volatile audio buffers — and could not be resumed
    from a store if it tried. What survives a restart is the text in the recovery
    journal, labelled as the guess it was.
    """

    def __init__(self) -> None:
        self._sessions: dict[UUID, VoiceSession] = {}
        self._lock = threading.Lock()

    def add(self, key: UUID, session: VoiceSession) -> None:
        with self._lock:
            self._sessions[key] = session

    def get(self, key: UUID) -> VoiceSession | None:
        with self._lock:
            return self._sessions.get(key)

    def remove(self, key: UUID) -> VoiceSession | None:
        with self._lock:
            return self._sessions.pop(key, None)

    def live_conversations(self) -> LiveVoiceConversations:
        """Which conversations have Voice on right now — the seal's transient layer.

        Owner ruling, 24 September 2026 (§2.1). A conversation with an open,
        owner-started session is local-only for every request it makes while the
        session lasts, typed or spoken, and whether or not anything has been said.
        Read from live state rather than from a table on purpose: a durable row
        saying "Voice is on" that outlived a crash would be exactly the stored
        preference §4.2 forbids, and it could not be true anyway — a session dies
        with the process that held its microphone.

        A session that has not yet been attached to a conversation contributes
        nothing here, because there is no conversation yet to seal; its first
        spoken turn asserts the seal directly when it creates one.
        """
        with self._lock:
            return LiveVoiceConversations(
                session.conversation_id
                for session in self._sessions.values()
                if session.conversation_id is not None
                and session.state is not VoiceSessionState.CLOSED
            )

    def keys(self) -> tuple[UUID, ...]:
        with self._lock:
            return tuple(self._sessions)

    def close_all(self, reason: str = "the service is shutting down") -> None:
        with self._lock:
            live = list(self._sessions.values())
            self._sessions.clear()
        for session in live:
            session.close(reason)
