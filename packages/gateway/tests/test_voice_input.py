# ruff: noqa: F811, F401 - fixtures and harness imported by name
"""Live voice input through Val Core — Voice mode work package 1, 23 Sept 2026.

Real PostgreSQL, the real deliberated Core path, a scripted provider standing in
for the model and a scripted recognizer standing in for whisper.cpp. What is
under test is **Val's** behaviour, not whisper's accuracy: the recognizer was
settled by its own proof, and the things that have to hold here are the ones the
order names.

The hard invariants, in the order the acceptance list gives them:

- a guess is not a message, cannot enter history, cannot enter recall, and cannot
  enter the cognition context;
- silence produces no user turn at all;
- one settled utterance produces exactly one canonical user message, through the
  ordinary door, with its provenance recoverable;
- the recovery journal is text and is superseded append-only;
- a guess an interrupted session left open comes back labelled `interrupted` and
  is never promoted into something the owner said;
- an owner who resumes before Val has delivered gets one turn, not two;
- consequential classification sees settled text and never a guess;
- no raw audio is persisted anywhere, in any column, ever.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from test_deliberation_machinery import (
    ScriptedAdapter,
    blind_says,
    build_gateway,
    classifier_says,
    clean_personas,
    full_script,
    ok,
    reconciled,
    store,
    strip_says,
)

from val_domain.voice import (
    EndpointConfiguration,
    LiveRecognizer,
    RecognizerEvent,
    RecognizerIdentity,
    VoiceSessionState,
    VoiceUtterance,
    pcm_is_valid,
)
from val_gateway import conversations as conv
from val_gateway.deliberate import DeliberatedOutcome
from val_gateway.deliberate import send as deliberated_send
from val_gateway.loop import Turn
from val_gateway.projects import load_catalogue
from val_gateway.seal import SealRoute
from val_gateway.voice import (
    RESUME_GRACE_SECONDS,
    VoiceSession,
    interrupted,
)
from val_policy.project_resolution import ProjectSignals

# =============================================================================
# The scripted recognizer
# =============================================================================

IDENTITY = RecognizerIdentity(
    name="whisper.cpp",
    version="v1.9.4",
    commit="927cfce34f31707e17f2bff35c349632fb9e2c3a",
    model_identifier="ggml-small.en",
    model_sha256="c" * 64,
    vad_model_identifier="silero-vad-v6.2.0",
    vad_model_sha256="d" * 64,
)


@dataclass
class ScriptedRecognizer:
    """A recognizer that reports from a script, one batch per handover.

    Each `feed` or `flush` releases the next batch, so a test drives the machine
    a step at a time instead of racing a real one. It satisfies
    `val_domain.voice.LiveRecognizer` structurally, which is the point: the
    session holds the boundary, not an implementation.
    """

    batches: list[list[RecognizerEvent]] = field(default_factory=list)
    #: **The fake keeps the last block so a test can prove it arrived.** Val's own
    #: code keeps none, which is what `test_v_...` checks.
    observed_block: bytes = b""
    fed_blocks: int = 0
    started: bool = False
    stopped: bool = False
    flushed: int = 0
    _queue: list[RecognizerEvent] = field(default_factory=list)

    @property
    def identity(self) -> RecognizerIdentity:
        return IDENTITY

    @property
    def endpoint(self) -> EndpointConfiguration:
        return EndpointConfiguration()

    def start(self) -> None:
        self.started = True

    def feed(self, pcm: bytes) -> None:
        assert pcm_is_valid(pcm) is None, "the session fed something that is not the contract"
        self.observed_block = pcm
        self.fed_blocks += 1
        self._release()

    def flush(self) -> None:
        self.flushed += 1
        self._release()

    def drain(self) -> Iterator[RecognizerEvent]:
        while self._queue:
            yield self._queue.pop(0)

    def stop(self) -> None:
        self.stopped = True

    def _release(self) -> None:
        if self.batches:
            self._queue.extend(self.batches.pop(0))


class Clock:
    """A clock a test moves by hand, so the resume window is exact."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def tick(self, seconds: float) -> None:
        self.now += seconds


def started(index: int, at: float = 0.0) -> RecognizerEvent:
    """`at` is the recognizer's own monotonic mark. Supplied where a test cares about
    the pause between two stretches of speech, which is what bounds a resume merge."""
    return RecognizerEvent(kind="speech_start", session=index, at=at)


def guess(index: int, words: str) -> RecognizerEvent:
    return RecognizerEvent(kind="provisional", session=index, text=words)


def ended(index: int) -> RecognizerEvent:
    return RecognizerEvent(kind="speech_end", session=index, reason="silence")


def final(
    index: int, words: str, reason: str = "silence", at: float = 0.0, endpoint_at: float = 0.0
) -> RecognizerEvent:
    return RecognizerEvent(
        kind="final", session=index, text=words, reason=reason, at=at, endpoint_at=endpoint_at
    )


#: A block of the canonical PCM with a distinctive byte pattern, so the
#: persistence proof can look for it by name.
MARKER = b"\x11\x22" * 160
SILENCE = b"\x00\x00" * 160


# =============================================================================
# Wiring
# =============================================================================


def a_conversation(engine: Engine) -> UUID:
    catalogue = load_catalogue(engine)
    (alpha,) = catalogue.matching("project-alpha")
    from val_domain.project import ResolutionSource, ResolvedProject

    scope = ResolvedProject(project=alpha, via=ResolutionSource.EXPLICIT_SELECTION)
    return conv.create(engine, scope=scope, title="Spoken").id


def a_session(
    engine: Engine,
    recognizer: ScriptedRecognizer,
    *,
    adapter: ScriptedAdapter | None = None,
    conversation_id: UUID | None = None,
    clock: Clock | None = None,
) -> tuple[VoiceSession, ScriptedAdapter, Clock]:
    """A voice session whose submission is the **ordinary deliberated send**.

    Deliberately not a stand-in: requirement I is that a spoken turn goes through
    normal Val Core, and the only way to hold that is to put normal Val Core here.
    """
    provider = adapter or ScriptedAdapter([ok("Quite so.")])
    hands = clock or Clock()

    def submit(
        content: str,
        existing: UUID | None,
        *,
        on_delta: Callable[[str], None] | None = None,
        merged: bool = False,
        on_persisted: Callable[[UUID, UUID], None] | None = None,
    ) -> DeliberatedOutcome:
        # Mirrors the service's own voice door exactly (owner ruling, 24 September
        # 2026, Voice work package 3 §1.5): a spoken turn is submitted `spoken`,
        # which seals its conversation in the same transaction as the message and
        # takes the classifier and strip calls off the path. A double that omitted
        # it would be testing a voice turn the application no longer performs.
        return deliberated_send(
            engine,
            build_gateway(engine, provider),
            content,
            catalogue=load_catalogue(engine),
            # Exactly as the service does it: the signals are offered only when
            # there is no conversation yet. Restating a project on a resumed
            # conversation is a scope switch, which starts a new one.
            signals=None
            if existing is not None
            else ProjectSignals(explicit_selection="Project Alpha"),
            conversation_id=existing,
            # Work package 2: Core's visible output as it is produced, so a
            # session that speaks can begin before she has finished writing. WP1's
            # sessions pass nothing and behave exactly as they did.
            on_delta=on_delta,
            on_persisted=on_persisted,
            spoken=True,
            seal_route=SealRoute.RESUME_MERGE if merged else SealRoute.UTTERANCE_FINALIZED,
        )

    session = VoiceSession(
        engine,
        recognizer,
        submit=submit,
        conversation_id=conversation_id if conversation_id is not None else a_conversation(engine),
        clock=hands,
    )
    session.start()
    return session, provider, hands


def attach(session: VoiceSession) -> UUID:
    """Write the durable session row now.

    What opening a session on an existing conversation does. A test that journals
    a guess before any turn exists has to do it explicitly, because a session with
    no conversation has nothing to attach a guess to.
    """
    return session.session_id


def settle(session: VoiceSession, clock: Clock) -> None:
    """Let the resume window pass, and wait for the turn to land."""
    clock.tick(RESUME_GRACE_SECONDS + 0.1)
    session.await_turn(timeout=30.0)


def revisions_of(engine: Engine, message_id: UUID) -> list[str | None]:
    """The corrected wordings recorded against one message, in order."""
    with engine.connect() as connection:
        return [
            row.content
            for row in connection.execute(
                text(
                    "select content from message_revisions where message_id = :id "
                    " order by revision_number"
                ),
                {"id": message_id},
            )
        ]


def messages_of(engine: Engine, conversation_id: UUID) -> list[str]:
    with engine.connect() as connection:
        return [
            row.content
            for row in connection.execute(
                text("select content from messages where conversation_id = :id order by sequence"),
                {"id": conversation_id},
            )
        ]


def said_by_the_owner(engine: Engine, conversation_id: UUID) -> list[str]:
    """Only his messages — Val's answers are hers, and can echo his words."""
    with engine.connect() as connection:
        return [
            row.content
            for row in connection.execute(
                text(
                    "select content from messages where conversation_id = :id "
                    "   and role = 'user' order by sequence"
                ),
                {"id": conversation_id},
            )
        ]


# =============================================================================
# A-G. The recognizer's events, as the session sees them
# =============================================================================


def test_a_pcm_enters_the_recognizer_in_memory_and_the_session_keeps_none(
    store: Engine,
) -> None:
    """A. The block reaches the recognizer, and Val's own state holds no audio."""
    recognizer = ScriptedRecognizer(batches=[[started(1)]])
    session, _, _ = a_session(store, recognizer)

    session.feed(MARKER)

    assert recognizer.observed_block == MARKER, "the exact bytes, unmodified, in memory"
    assert recognizer.fed_blocks == 1
    held = [value for value in vars(session).values() if isinstance(value, bytes | bytearray)]
    assert held == [], "the session keeps no audio of any kind"


def test_b_silence_creates_no_user_message(store: Engine) -> None:
    """B. Speech that carried no words is not a turn. It is silence."""
    recognizer = ScriptedRecognizer(batches=[[started(1), final(1, "   ")]])
    conversation = a_conversation(store)
    session, adapter, clock = a_session(store, recognizer, conversation_id=conversation)

    session.feed(SILENCE)
    settle(session, clock)

    assert messages_of(store, conversation) == [], "no message was created"
    assert adapter.sent == [], "no provider was called at all"
    assert session.snapshot().state is VoiceSessionState.LISTENING


def test_c_to_g_the_five_event_concepts_are_distinct(store: Engine) -> None:
    """C-G. speech_start, provisional, revision, speech_end, final — each observed."""
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1)],
            [guess(1, "And so my")],
            [guess(1, "And so, my fellow Americans,")],
            [ended(1), final(1, "And so, my fellow Americans,")],
        ]
    )
    conversation = a_conversation(store)
    session, _, _ = a_session(store, recognizer, conversation_id=conversation)

    session.feed(MARKER)
    assert session.snapshot().hearing is True, "C. speech_start moved the session to hearing"

    session.feed(MARKER)
    first = session.snapshot().provisional
    assert first == "And so my", "D. a provisional transcript is exposed"

    session.feed(MARKER)
    revised = session.snapshot().provisional
    assert revised == "And so, my fellow Americans,", "E. and it revises"
    assert revised != first

    session.feed(MARKER)
    view = session.snapshot()
    assert view.hearing is False, "F. speech_end ended the utterance"
    assert view.pending == "And so, my fellow Americans,", "G. the final transcription settled"
    assert view.provisional == "", "the guess is gone once the words are settled"


# =============================================================================
# H-J. One utterance, one canonical turn, through the ordinary door
# =============================================================================


def test_h_one_finalized_utterance_creates_exactly_one_canonical_message(
    store: Engine,
) -> None:
    """H. One breath, one owner message. Not two, and not none."""
    recognizer = ScriptedRecognizer(
        batches=[[started(1), guess(1, "the light"), final(1, "Fix the light, please.")]]
    )
    conversation = a_conversation(store)
    session, _, clock = a_session(store, recognizer, conversation_id=conversation)

    session.feed(MARKER)
    settle(session, clock)

    said = messages_of(store, conversation)
    assert said[0] == "Fix the light, please."
    assert sum(1 for line in said if line == "Fix the light, please.") == 1
    assert len(session.snapshot().turns) == 1


def test_i_the_spoken_turn_goes_through_normal_val_core(store: Engine) -> None:
    """I. Persona, routing, persistence — the ordinary path, and one exception to it.

    A voice-specific route would show up here as a missing classification row:
    every deliberated turn has one, and a turn that skipped Core would not.

    **Amended 24 September 2026 (Voice work package 3 §1.5, §2.3).** The row is
    still here, and it now says the classification did **not run**. The owner ruled
    that a live microphone transcript never leaves this machine; the consequentiality
    classifier is a cloud structured route; so a spoken turn no longer makes that
    call, and the turn makes exactly one call — the local response. The assertion
    that a classifier reply was consumed has become the assertion that none was,
    which is the stronger of the two: it fails both if Core is bypassed and if the
    transcript reaches the classifier.
    """
    recognizer = ScriptedRecognizer(batches=[[started(1), final(1, "What time is dinner?")]])
    conversation = a_conversation(store)
    adapter = ScriptedAdapter([ok("Eight, my lord.")])
    session, _, clock = a_session(store, recognizer, adapter=adapter, conversation_id=conversation)

    session.feed(MARKER)
    settle(session, clock)

    (turn,) = session.snapshot().turns
    with store.connect() as connection:
        classifications = connection.execute(
            text("select count(*) from classifications where message_id = :id"),
            {"id": turn.message_id},
        ).scalar_one()
        tasks = {
            row.task_type
            for row in connection.execute(
                text("select task_type from model_calls where conversation_id = :id"),
                {"id": conversation},
            )
        }
        recorded = connection.execute(
            text(
                "select established, verdict, attempts, not_run_reason "
                "  from classifications where message_id = :id"
            ),
            {"id": turn.message_id},
        ).one()
    assert classifications == 1, "the turn's classification is on record either way"
    assert recorded.not_run_reason is not None, "and it says the classification did not run"
    assert "local-only" in recorded.not_run_reason
    assert (recorded.established, recorded.verdict, recorded.attempts) == (False, None, 0), (
        "a classification that did not run claims no verdict and no attempt"
    )
    assert "conversation" in tasks, "the response call is on record as an ordinary conversation"
    assert "classification" not in tasks, "and no classification call was made at all"
    assert messages_of(store, conversation)[-1] == "Eight, my lord."
    assert len(adapter.sent) == 1, "the response alone: a sealed turn makes one call"


def test_j_provenance_records_input_mode_voice_and_the_exact_recognizer(
    store: Engine,
) -> None:
    """J. `input_mode = voice`, and precisely which ears heard it."""
    recognizer = ScriptedRecognizer(
        batches=[[started(1), guess(1, "Ask the cook"), final(1, "Ask the cook about dinner.")]]
    )
    conversation = a_conversation(store)
    session, _, clock = a_session(store, recognizer, conversation_id=conversation)

    session.feed(MARKER)
    settle(session, clock)
    (turn,) = session.snapshot().turns

    with store.connect() as connection:
        row = (
            connection.execute(
                text(
                    "select p.*, s.recognizer, s.recognizer_version, s.recognizer_commit, "
                    "       s.asr_model, s.asr_model_sha256, s.vad_model, s.vad_model_sha256, "
                    "       s.endpoint_configuration "
                    "  from voice_message_provenance p "
                    "  join voice_sessions s on s.id = p.voice_session_id "
                    " where p.message_id = :id"
                ),
                {"id": turn.message_id},
            )
            .mappings()
            .one()
        )

    assert row["input_mode"] == "voice"
    assert row["transcription_status"] == "final"
    assert row["finalized_at"] is not None
    assert row["utterance"] == 1
    assert row["endpoint_reason"] == "silence"
    assert row["provisional_events"] == 1
    assert row["recognizer"] == "whisper.cpp"
    assert row["recognizer_version"] == "v1.9.4"
    assert row["recognizer_commit"] == "927cfce34f31707e17f2bff35c349632fb9e2c3a"
    assert row["asr_model"] == "ggml-small.en"
    assert row["asr_model_sha256"] == "c" * 64
    assert row["vad_model"] == "silero-vad-v6.2.0"
    assert row["vad_model_sha256"] == "d" * 64
    assert row["endpoint_configuration"]["min_silence_ms"] == 650


def test_j_the_visible_message_text_carries_none_of_that(store: Engine) -> None:
    """J, second half: provenance is a sidecar, not a decoration on the words."""
    recognizer = ScriptedRecognizer(batches=[[started(1), final(1, "Good evening.")]])
    conversation = a_conversation(store)
    session, _, clock = a_session(store, recognizer, conversation_id=conversation)

    session.feed(MARKER)
    settle(session, clock)

    assert messages_of(store, conversation)[0] == "Good evening."


# =============================================================================
# K-M. A guess is not a message, and cannot become one sideways
# =============================================================================


def test_k_the_provisional_transcript_is_absent_from_message_history(
    store: Engine,
) -> None:
    """K. The guess never appears in the conversation, before or after settling."""
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1), guess(1, "Cancel the ord")],
            [final(1, "Cancel the order of chairs.")],
        ]
    )
    conversation = a_conversation(store)
    session, _, clock = a_session(store, recognizer, conversation_id=conversation)

    session.feed(MARKER)
    assert messages_of(store, conversation) == [], "a guess is not history while it is a guess"

    session.feed(MARKER)
    settle(session, clock)

    said = messages_of(store, conversation)
    assert "Cancel the ord" not in said
    assert said[0] == "Cancel the order of chairs."


def test_l_no_recall_query_can_reach_a_guess(store: Engine) -> None:
    """L. Structural, not behavioural: recall reads `messages_current` and nothing else.

    The guess lives in the recovery journal, which no recall query names. That is
    a stronger guarantee than a flag, because there is no query to forget to add
    a condition to.
    """
    import inspect

    from val_gateway import memory

    source = inspect.getsource(memory)
    assert "voice_recovery_journal" not in source
    assert "voice_message_provenance" not in source
    assert "messages_current" in source, "recall reads the view a guess is not part of"


def test_m_a_guess_never_reaches_the_cognition_context(store: Engine) -> None:
    """M. Nothing the provider was sent contains the words the recognizer guessed."""
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1), guess(1, "Sell the horse"), guess(1, "Sell the house")],
            [final(1, "Sell the house in Kent.")],
        ]
    )
    conversation = a_conversation(store)
    adapter = ScriptedAdapter([ok("As you wish.")])
    session, _, clock = a_session(store, recognizer, adapter=adapter, conversation_id=conversation)

    session.feed(MARKER)
    session.feed(MARKER)
    settle(session, clock)

    transmitted = "\n".join(
        (call.system or "") + "\n".join(message.content for message in call.messages)
        for call in adapter.sent
    )
    assert "Sell the horse" not in transmitted, "a discarded guess never left the house"
    assert "Sell the house in Kent." in transmitted, "the settled words did"


# =============================================================================
# N-Q. The recovery journal
# =============================================================================


def test_n_the_recovery_journal_holds_text_and_nothing_else(store: Engine) -> None:
    """N. Not a promise: the column types say so."""
    with store.connect() as connection:
        columns = connection.execute(
            text(
                "select column_name, data_type from information_schema.columns "
                " where table_name in "
                "   ('voice_recovery_journal', 'voice_sessions', 'voice_message_provenance')"
            )
        ).all()
    assert columns, "the voice tables exist"
    types = {row.data_type for row in columns}
    assert "bytea" not in types, "no voice table has a binary column"
    assert not any("audio" in row.column_name for row in columns)
    assert not any("pcm" in row.column_name for row in columns)
    assert not any("waveform" in row.column_name for row in columns)


def test_n_a_guess_is_journalled_as_text_while_it_is_being_spoken(store: Engine) -> None:
    recognizer = ScriptedRecognizer(
        batches=[[started(1), guess(1, "Tell the gardener about the roses")]]
    )
    conversation = a_conversation(store)
    session, _, _ = a_session(store, recognizer, conversation_id=conversation)
    attach(session)

    session.feed(MARKER)

    with store.connect() as connection:
        rows = connection.execute(
            text(
                "select entry, provisional_text, state, superseded_by_message_id "
                "  from voice_recovery_journal order by entry"
            )
        ).all()
    assert [(row.entry, row.state) for row in rows] == [(1, "provisional")]
    assert rows[0].provisional_text == "Tell the gardener about the roses"
    assert rows[0].superseded_by_message_id is None


def test_o_the_journal_is_not_reachable_from_conversation_history(store: Engine) -> None:
    """O. `messages_current` — the view every read goes through — excludes it."""
    recognizer = ScriptedRecognizer(batches=[[started(1), guess(1, "Something half said here")]])
    conversation = a_conversation(store)
    session, _, _ = a_session(store, recognizer, conversation_id=conversation)
    attach(session)
    session.feed(MARKER)

    with store.connect() as connection:
        from_view = connection.execute(
            text("select count(*) from messages_current where content like '%half said%'")
        ).scalar_one()
        in_journal = connection.execute(
            text(
                "select count(*) from voice_recovery_journal "
                " where provisional_text like '%half said%'"
            )
        ).scalar_one()
    assert in_journal == 1, "the guess is in the journal"
    assert from_view == 0, "and in no conversation read"
    assert conv.history(store, conversation) == (), "and in no conversation history"


def test_p_successful_finalization_supersedes_the_guess_append_only(
    store: Engine,
) -> None:
    """P. A new entry names the turn; the original guess stays exactly as written."""
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1), guess(1, "Tell the gardener")],
            [final(1, "Tell the gardener about the roses.")],
        ]
    )
    conversation = a_conversation(store)
    session, _, clock = a_session(store, recognizer, conversation_id=conversation)
    attach(session)

    session.feed(MARKER)
    session.feed(MARKER)
    settle(session, clock)
    (turn,) = session.snapshot().turns

    with store.connect() as connection:
        rows = connection.execute(
            text(
                "select entry, provisional_text, state, superseded_by_message_id "
                "  from voice_recovery_journal order by entry"
            )
        ).all()
    assert [(row.entry, row.state) for row in rows] == [(1, "provisional"), (2, "superseded")]
    assert rows[0].provisional_text == "Tell the gardener", "the original entry is untouched"
    assert rows[1].superseded_by_message_id == turn.message_id


def test_p_the_journal_refuses_to_be_rewritten(store: Engine) -> None:
    """P, the structural half: append-only is enforced by the store, not by habit."""
    recognizer = ScriptedRecognizer(batches=[[started(1), guess(1, "A half-said thing")]])
    conversation = a_conversation(store)
    session, _, _ = a_session(store, recognizer, conversation_id=conversation)
    attach(session)
    session.feed(MARKER)

    with pytest.raises(Exception, match=r"evidence|UPDATE"):
        with store.begin() as connection:
            connection.execute(text("update voice_recovery_journal set state = 'superseded'"))
    with pytest.raises(Exception, match=r"delete|DELETE|hard"):
        with store.begin() as connection:
            connection.execute(text("delete from voice_recovery_journal"))


def test_q_an_interrupted_guess_comes_back_labelled_and_never_canonical(
    store: Engine,
) -> None:
    """Q. A crash mid-sentence loses nothing and promotes nothing."""
    recognizer = ScriptedRecognizer(
        batches=[[started(1), guess(1, "I was in the middle of saying")]]
    )
    conversation = a_conversation(store)
    session, _, _ = a_session(store, recognizer, conversation_id=conversation)
    attach(session)
    session.feed(MARKER)
    # The process dies here: no close, no final, no submission.

    (found,) = interrupted(store)
    assert found.provisional_text == "I was in the middle of saying"
    assert found.state == "interrupted"
    assert found.conversation_id == conversation
    assert messages_of(store, conversation) == [], "nothing was promoted into the conversation"

    with store.connect() as connection:
        states = [
            row.state
            for row in connection.execute(
                text("select state from voice_recovery_journal order by entry")
            )
        ]
    assert states == ["provisional", "interrupted"], "marked by appending, never by rewriting"
    assert interrupted(store) == (), "a second restart does not report it again"


# =============================================================================
# R. Resume before Val delivers
# =============================================================================


def test_r_resuming_inside_the_window_gives_one_intended_owner_turn(
    store: Engine,
) -> None:
    """R. One human utterance, spoken in two breaths, is one message.

    Nothing has been submitted yet, so nothing needs cancelling: the halves are
    simply the one thing he meant to say.
    """
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1), final(1, "Ask the cook about dinner")],
            [started(2), final(2, "and tell her the guests are late.")],
        ]
    )
    conversation = a_conversation(store)
    session, _, clock = a_session(store, recognizer, conversation_id=conversation)

    session.feed(MARKER)
    clock.tick(0.4)  # well inside the resume window
    session.feed(MARKER)
    settle(session, clock)

    said = messages_of(store, conversation)
    assert said[0] == "Ask the cook about dinner and tell her the guests are late."
    assert len([line for line in said if "cook" in line]) == 1, "one owner message, not two"

    (turn,) = session.snapshot().turns
    assert turn.utterance.merged_from == (1,)
    with store.connect() as connection:
        merged = connection.execute(
            text("select merged_from from voice_message_provenance where message_id = :id"),
            {"id": turn.message_id},
        ).scalar_one()
    assert merged == [1], "the record says which breath was absorbed"


def test_r_resuming_after_submission_supersedes_the_half_heard_exchange(
    store: Engine,
) -> None:
    """R, the harder half: submitted, not yet delivered, and he carries on.

    **Amended 25 September 2026 (owner acceptance, WP3 §1.1).** This used to assert
    that the owner's message was *revised* and Val's answer left standing, marked as
    having answered the earlier wording. Owner acceptance showed what that does in
    the room: every one of five spoken turns had its words relabelled underneath an
    answer to something else, because the house — not he — had split one sentence in
    two and answered the first half.

    So the exchange is superseded instead: the obsolete answer is never spoken, the
    pair is **withdrawn** with all its evidence intact, and the complete wording is
    submitted as a new turn. The `messages` row is still never rewritten — what
    changes is that the answer is never bound to wording that moved underneath it.
    """
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1), final(1, "Ask the cook about dinner")],
            [started(2), final(2, "and tell her the guests are late.")],
        ]
    )
    conversation = a_conversation(store)
    adapter = ScriptedAdapter([ok("At once, my lord."), ok("I will tell her, my lord.")])
    session, _, clock = a_session(store, recognizer, adapter=adapter, conversation_id=conversation)

    session.feed(MARKER)
    settle(session, clock)  # the turn is submitted and answered
    (first,) = session.snapshot().turns

    session.feed(MARKER)  # he resumes; Val has not spoken aloud
    settle(session, clock)

    combined = "Ask the cook about dinner and tell her the guests are late."
    turns = session.snapshot().turns
    superseded = next(turn for turn in turns if turn.message_id == first.message_id)
    assert superseded.superseded_by == combined, "the half-heard exchange is superseded"
    assert superseded.revised_to is None, "and not relabelled under the old answer"

    fresh = next(turn for turn in turns if turn.message_id != first.message_id)
    assert fresh.utterance.text == combined, "the complete wording became its own turn"
    assert fresh.answer_message_id is not None, "and it was answered on its own account"

    # The original row is untouched, and no revision was ever written.
    said = messages_of(store, conversation)
    assert said[0] == "Ask the cook about dinner", "the original row is untouched"
    # A retraction's row carries no content; a revision's does. There is no content.
    assert revisions_of(store, first.message_id) == [None], "no revision relabelled his words"

    # The pair is withdrawn — preserved, marked, and out of the working conversation.
    with store.connect() as connection:
        kinds = [
            row.kind
            for row in connection.execute(
                text(
                    "select kind from message_revisions where message_id = :id "
                    " order by revision_number"
                ),
                {"id": first.message_id},
            )
        ]
        # Exactly as assembly reads it: a withdrawn message and the answer to a
        # withdrawn message both leave the working conversation.
        live = connection.execute(
            text(
                "select count(*) from messages_current where conversation_id = :c "
                "  and state <> 'withdrawn' and coalesce(answered_state, '') <> 'withdrawn'"
            ),
            {"c": conversation},
        ).scalar_one()
    assert kinds == ["retraction"], "withdrawn, not rewritten"
    assert live == 2, "the working conversation holds the complete turn and its answer"


def test_r_once_val_has_delivered_the_next_utterance_is_its_own_turn(
    store: Engine,
) -> None:
    """R's boundary. He has heard her; what he says next is a reply."""
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1), final(1, "Ask the cook about dinner.")],
            [started(2), final(2, "And the wine.")],
        ]
    )
    conversation = a_conversation(store)
    # Two spoken turns, two answers, and no classifier reply between them: a
    # sealed conversation makes no classifier call at all (§2.3).
    adapter = ScriptedAdapter([ok("At once, my lord."), ok("And the wine, my lord.")])
    session, _, clock = a_session(store, recognizer, adapter=adapter, conversation_id=conversation)

    session.feed(MARKER)
    settle(session, clock)
    (first,) = session.snapshot().turns
    session.deliver(first.message_id)

    session.feed(MARKER)
    settle(session, clock)

    assert said_by_the_owner(store, conversation) == [
        "Ask the cook about dinner.",
        "And the wine.",
    ]
    assert len(session.snapshot().turns) == 2


def test_r_a_turn_anchoring_a_decision_is_never_rewritten_to_fake_continuity(
    store: Engine,
) -> None:
    """R's refusal. Continuity is not worth falsifying a recorded deliberation.

    The resumed speech becomes its own turn, and the refusal is on the record
    rather than swallowed.

    **Amended 24 September 2026 (Voice work package 3 §1.7).** The anchoring blind
    position is now written directly by this test rather than produced by the turn,
    because a spoken turn can no longer produce one: a sealed conversation makes no
    classifier call, so the consequential machinery does not run in it, which is the
    consequence the owner knowingly accepted. The behaviour under test is unchanged
    and is what matters — **a message anchoring a recorded decision is never
    rewritten to make a resumed sentence look continuous** — and the durable state
    that triggers it is constructed here instead of being arrived at. The refusal is
    kept as a guard whose production reachability from voice is currently nil; that
    is reported to the owner rather than being quietly deleted with the test.
    """
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1), final(1, "I think we should open on the wide shot. How should it open?")],
            [started(2), final(2, "And keep it short.")],
        ]
    )
    conversation = a_conversation(store)
    adapter = ScriptedAdapter([ok("On the wide shot, my lord.")])
    session, _, clock = a_session(store, recognizer, adapter=adapter, conversation_id=conversation)

    session.feed(MARKER)
    settle(session, clock)
    (first,) = session.snapshot().turns
    with store.begin() as connection:
        # The durable state whose consequence is under test: this message anchors
        # an enforced blind position. Anchored to the call the turn really made and
        # the persona really active, so nothing here is a dangling reference.
        call_id = connection.execute(
            text(
                "select id from model_calls where conversation_id = :id "
                " order by created_at desc limit 1"
            ),
            {"id": conversation},
        ).scalar_one()
        persona_id = connection.execute(
            text("select id from personas where is_active")
        ).scalar_one()
        connection.execute(
            text(
                "insert into blind_positions (conversation_id, message_id, model_call_id, "
                "  persona_id, position, confidence, reasoning, stripped_content, ordering, "
                "  classification, classified_by) "
                "values (:conversation, :message, :call, :persona, 'Open wide.', 'medium', "
                "  'Because the room is the subject.', 'How should it open?', 'enforced', "
                "  'consequential', 'automatic')"
            ),
            {
                "conversation": conversation,
                "message": first.message_id,
                "call": call_id,
                "persona": persona_id,
            },
        )
    with store.connect() as connection:
        blinds = connection.execute(
            text("select count(*) from blind_positions where message_id = :id"),
            {"id": first.message_id},
        ).scalar_one()
    assert blinds == 1, "this turn anchors an enforced blind position"

    session.feed(MARKER)
    session.advance()

    # **Amended 25 September 2026 (WP3 §1.1).** The rule this test was written for —
    # a message anchoring a recorded decision refuses *revision* — is unchanged and
    # still holds. What changed is that the voice path no longer asks for a revision:
    # it withdraws the exchange, which the same doctrine permits precisely because a
    # retraction rewrites nothing and "never invalidates evidence valid when
    # produced". So the words a decision was made about are still never rewritten,
    # and the blind position still stands exactly as it was.
    turn = session.snapshot().turns[0]
    assert turn.revised_to is None, "the wording was not rewritten"
    assert turn.superseded_by is not None, "the half-heard exchange was superseded"
    assert revisions_of(store, first.message_id) == [None], "a retraction, not a revision"
    with store.connect() as connection:
        surviving = connection.execute(
            text("select position, ordering from blind_positions where message_id = :id"),
            {"id": first.message_id},
        ).one()
    assert surviving.position == "Open wide.", "the recorded position is untouched"
    assert surviving.ordering == "enforced", "and still says how it was formed"


# =============================================================================
# S-V. Consequence safety, text behaviour, and the two negatives
# =============================================================================


def test_s_the_classifier_sees_settled_text_and_never_a_guess(store: Engine) -> None:
    """S. Consequential handling operates on the final transcription only.

    Proved where it matters: the classification call's own payload. A guess never
    reaches `send`, so it cannot reach the classifier by any route.
    """
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1), guess(1, "Wire fifty thousand")],
            [guess(1, "Wire fifteen thousand")],
            [final(1, "Wire fifteen thousand pounds to the builder.")],
        ]
    )
    conversation = a_conversation(store)
    adapter = ScriptedAdapter(full_script())
    session, _, clock = a_session(store, recognizer, adapter=adapter, conversation_id=conversation)

    session.feed(MARKER)
    session.feed(MARKER)
    # Two guesses have been made and the classifier has not run: it cannot,
    # because there is nothing settled to classify.
    assert adapter.sent == [], "no consequential machinery ran on a guess"

    session.feed(MARKER)
    settle(session, clock)

    classified = "\n".join(message.content for message in adapter.sent[0].messages)
    assert "Wire fifteen thousand pounds to the builder." in classified
    assert "Wire fifty thousand" not in classified, "the wrong guess never reached the classifier"


def test_t_typed_turns_are_completely_unchanged(store: Engine) -> None:
    """T. Nothing about a typed turn learned that microphones exist.

    Including its classification: an ordinary typed turn in an unsealed
    conversation still classifies on its cloud structured route, exactly as before
    the live-voice seal existed (§2.7's clean boundary). The two scripted replies
    are that fact, and the assertion below checks the record rather than the script.
    """
    adapter = ScriptedAdapter([classifier_says("not_consequential"), ok("Cobalt, my lord.")])
    outcome = deliberated_send(
        store,
        build_gateway(store, adapter),
        "What colour is the hall?",
        catalogue=load_catalogue(store),
        signals=ProjectSignals(explicit_selection="Project Alpha"),
    )
    assert isinstance(outcome.turn, Turn)
    with store.connect() as connection:
        provenance = connection.execute(
            text("select count(*) from voice_message_provenance where message_id = :id"),
            {"id": outcome.turn.user_message.id},
        ).scalar_one()
        sessions = connection.execute(text("select count(*) from voice_sessions")).scalar_one()
        classification = connection.execute(
            text(
                "select established, verdict, not_run_reason from classifications "
                " where message_id = :id"
            ),
            {"id": outcome.turn.user_message.id},
        ).one()
    assert provenance == 0, "a typed message gains no voice provenance"
    assert sessions == 0, "and opens no voice session"
    assert classification.not_run_reason is None, "and its classification ran, as it always did"
    assert (classification.established, classification.verdict) == (True, "not_consequential")


def test_u_no_cloud_speech_recognition_is_reachable_from_this_path() -> None:
    """U. Proved structurally rather than promised.

    Comments and docstrings are stripped first, so the modules' own
    *prohibitions* are not mistaken for the thing they prohibit.
    """
    import inspect
    import io
    import tokenize

    from val_gateway import voice as gateway_voice
    from val_providers import whisper_recognizer

    for module in (whisper_recognizer, gateway_voice):
        code = "".join(
            token.string
            for token in tokenize.generate_tokens(io.StringIO(inspect.getsource(module)).readline)
            if token.type not in (tokenize.COMMENT, tokenize.STRING)
        ).lower()
        for forbidden in (
            "http://",
            "https://",
            "requests",
            "urllib",
            "httpx",
            "deepgram",
            "assemblyai",
            "azure",
            "omni",
        ):
            assert forbidden not in code, f"{forbidden!r} must not appear in executable code"


def test_v_no_raw_audio_is_persisted_anywhere(store: Engine) -> None:
    """V. The whole store is searched for the bytes that were fed in.

    Every text and binary column in every table, not only the voice ones: the
    claim is that the audio is nowhere, and checking only the places it was never
    going to be would prove nothing.
    """
    recognizer = ScriptedRecognizer(
        batches=[[started(1), guess(1, "Something spoken"), final(1, "Something spoken aloud.")]]
    )
    conversation = a_conversation(store)
    session, _, clock = a_session(store, recognizer, conversation_id=conversation)
    attach(session)

    for _ in range(4):
        session.feed(MARKER)
    settle(session, clock)
    session.close()

    needle = MARKER[:16]
    with store.connect() as connection:
        columns = connection.execute(
            text(
                "select table_name, column_name, data_type from information_schema.columns "
                " where table_schema = 'public' and data_type in "
                "   ('bytea', 'text', 'character varying', 'jsonb')"
            )
        ).all()
        for row in columns:
            if row.data_type == "bytea":
                found = connection.execute(
                    text(
                        f'select count(*) from "{row.table_name}" '  # noqa: S608 - names from the catalogue
                        f'where "{row.column_name}" like :needle'
                    ),
                    {"needle": b"%" + needle + b"%"},
                ).scalar_one()
            else:
                found = connection.execute(
                    text(
                        f'select count(*) from "{row.table_name}" '  # noqa: S608 - names from the catalogue
                        f'where cast("{row.column_name}" as text) like :needle'
                    ),
                    {"needle": f"%{needle.hex()}%"},
                ).scalar_one()
            assert found == 0, f"audio reached {row.table_name}.{row.column_name}"

        blobs = connection.execute(text("select count(*) from blobs")).scalar_one()
    assert blobs == 0, "no attachment blob was created by speaking"


def test_the_session_closes_its_recognizer_and_its_record(store: Engine) -> None:
    """A subprocess is not left behind, and an open session is not left open."""
    recognizer = ScriptedRecognizer(batches=[[started(1)]])
    conversation = a_conversation(store)
    session, _, _ = a_session(store, recognizer, conversation_id=conversation)
    attach(session)

    session.close("the owner finished speaking")

    assert recognizer.stopped is True
    with store.connect() as connection:
        row = connection.execute(
            text("select state, closed_at, closed_reason from voice_sessions")
        ).one()
    assert row.state == "closed"
    assert row.closed_at is not None
    assert row.closed_reason == "the owner finished speaking"


def test_a_voice_session_is_not_a_second_conversation(store: Engine) -> None:
    """Two sessions on one conversation add no conversations, ever."""
    conversation = a_conversation(store)
    for _ in range(2):
        recognizer = ScriptedRecognizer(batches=[[started(1), final(1, "A word.")]])
        session, _, clock = a_session(store, recognizer, conversation_id=conversation)
        session.feed(MARKER)
        settle(session, clock)
        session.close()

    with store.connect() as connection:
        conversations = connection.execute(text("select count(*) from conversations")).scalar_one()
        sessions = connection.execute(text("select count(*) from voice_sessions")).scalar_one()
    assert conversations == 1, "one conversation"
    assert sessions == 2, "two sessions of listening to it"


def test_an_utterance_merges_without_rewriting_either_half() -> None:
    """The domain's own join: two breaths, one turn, and the record says which."""
    first = VoiceUtterance(session_id=uuid4(), utterance=1, text="Ask the cook", reason="silence")
    second = VoiceUtterance(
        session_id=first.session_id, utterance=2, text="about dinner.", reason="silence"
    )
    merged = first.merged_with(second)
    assert merged.text == "Ask the cook about dinner."
    assert merged.merged_from == (1,)
    assert merged.utterance == 2
    assert first.text == "Ask the cook", "the halves are unchanged"
    assert second.text == "about dinner."


def test_a_failure_writing_provenance_is_reported_not_swallowed(store: Engine) -> None:
    """The turn happened; its provenance did not. That is a state he must see.

    Found by restarting the live service on a store that had not yet taken the
    migration: the write ran on a worker thread whose exception nobody observed,
    so the session went on looking healthy while the record was incomplete.
    """
    recognizer = ScriptedRecognizer(batches=[[started(1), final(1, "Note that down.")]])
    conversation = a_conversation(store)
    session, _, clock = a_session(store, recognizer, conversation_id=conversation)
    with store.begin() as connection:
        connection.execute(text("alter table voice_message_provenance rename to provenance_gone"))
    try:
        session.feed(MARKER)
        # The turn completes; the provenance write is what fails, so this returns
        # rather than raising — which is exactly why it has to be reported.
        settle(session, clock)
    finally:
        with store.begin() as connection:
            connection.execute(
                text("alter table provenance_gone rename to voice_message_provenance")
            )

    view = session.snapshot()
    assert view.state is VoiceSessionState.ERROR
    assert view.error is not None
    assert "voice provenance could not be recorded" in view.error
    assert said_by_the_owner(store, conversation) == ["Note that down."], (
        "the turn itself happened and is not pretended away"
    )


def test_r_speech_resumed_inside_the_window_holds_the_waiting_utterance_until_it_settles(
    store: Engine,
) -> None:
    """R, the case his session of 25 September (20:15) found — owner order, 26 Sept 2026.

    He resumed 0.5 s after he stopped, well inside the grace, but was still speaking
    when the grace expired. The waiting utterance was submitted on its own, the rest
    could not join a turn already in cognition, and it waited 41 s for that turn's
    whole answer. The waiting utterance is now held while the resumed speech is still
    being heard, and the two become one message.
    """
    recognizer = ScriptedRecognizer(
        batches=[
            [
                started(1, at=10.0),
                final(1, "Is there a way to go faster?", at=10.9, endpoint_at=10.7),
            ],
            [started(2, at=10.5)],  # he carries on, 0.5 s after he stopped speaking
            [final(2, "I'd like it a little faster.", at=13.2, endpoint_at=13.0)],
        ]
    )
    conversation = a_conversation(store)
    session, _, clock = a_session(store, recognizer, conversation_id=conversation)

    session.feed(MARKER)
    session.feed(MARKER)  # the resumed speech is being heard
    clock.tick(RESUME_GRACE_SECONDS * 3)  # the grace expires while he is still speaking
    session.advance()
    assert messages_of(store, conversation) == [], "nothing went out while he was speaking"

    session.feed(MARKER)  # the resumed speech settles
    settle(session, clock)
    said = messages_of(store, conversation)
    assert said[0] == "Is there a way to go faster? I'd like it a little faster."
    assert len([line for line in said if "faster" in line and "?" in line]) == 1


def test_r_speech_that_began_after_the_window_is_still_a_new_turn(store: Engine) -> None:
    """The bound: speech that began later than the grace does not hold anything."""
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1, at=10.0), final(1, "Good evening, Val.", at=10.9, endpoint_at=10.7)],
            [started(2, at=10.7 + RESUME_GRACE_SECONDS + 1.0)],
        ]
    )
    conversation = a_conversation(store)
    session, _, clock = a_session(store, recognizer, conversation_id=conversation)
    session.feed(MARKER)
    session.feed(MARKER)
    clock.tick(RESUME_GRACE_SECONDS * 3)
    session.advance()
    session.await_turn(timeout=10)
    assert messages_of(store, conversation)[0] == "Good evening, Val.", "submitted on its own"
