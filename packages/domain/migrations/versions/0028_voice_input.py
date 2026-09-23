"""Val listens, and the record stays text — owner execution order, 23 Sept 2026.

Three append-only tables, and what is *absent* from all three is as deliberate as
what is present: **there is no audio column anywhere here**, of any type. Raw
microphone audio is volatile session state, never a database field, never a file,
never conversation history, never recall evidence and never a project asset. The
canonical record of a spoken turn is the same thing as the record of a typed one
— text in `messages` — and these tables only say how that text came to be.

    voice_sessions            one live listening session: which conversation it
                              belongs to, what it is doing, and exactly which
                              recognizer and models heard it. A voice session is
                              **not a second conversation**; it is an input
                              modality attached to an existing one.

                              It is the one table here with a genuine lifecycle —
                              a session opens and later closes — so it takes the
                              `budget_reservations` treatment of `0009` rather
                              than the frozen one: everything that *identifies*
                              the session, above all which recognizer and which
                              models heard it, is immutable, and only the
                              lifecycle columns may move.

    voice_message_provenance  a sidecar on a finalized voice-origin message. A
                              sidecar rather than columns on `messages`, because
                              a spoken turn is an ordinary turn and the core
                              table should not learn about microphones to say so.
                              One row per message, and only ever for `final`
                              transcription.

    voice_recovery_journal    **text only.** A crash during an unfinished spoken
                              utterance should not lose the words, but recovered
                              words are *provisional*, not something Val may act
                              on. Append-only: superseding an entry writes the
                              next entry, and nothing is ever updated in place —
                              so `interrupted` can never be mistaken for
                              `superseded` by a later rewrite.

**The journal is structurally excluded from recall.** Recall reads the
`messages_current` view; a separate table is not reachable from it by any query
that exists, which is a stronger guarantee than a flag a future change could
forget to check.

All three are under the standing Layer 0 guards: no hard delete, no truncate, no
update.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_voice_input"
down_revision: str | None = "0027_local_speech"
branch_labels: None = None
depends_on: None = None


def _no_hard_delete(table: str) -> None:
    op.execute(
        f"CREATE TRIGGER {table}_forbid_hard_delete "
        f"BEFORE DELETE OR TRUNCATE ON {table} "
        "FOR EACH STATEMENT EXECUTE FUNCTION val_forbid_hard_delete()"
    )


def _guard(table: str) -> None:
    """The standing Layer 0 guards: no hard delete, no truncate, no update."""
    _no_hard_delete(table)
    op.execute(
        f"CREATE TRIGGER {table}_rows_are_evidence BEFORE UPDATE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION val_rows_are_evidence()"
    )


#: What identifies a voice session, as opposed to what happens to it. Above all
#: the recognizer and the two model digests: a session that could be re-labelled
#: afterwards as having been heard by something else would prove nothing.
SESSION_IDENTITY = (
    "id",
    "conversation_id",
    "started_at",
    "recognizer",
    "recognizer_version",
    "recognizer_commit",
    "asr_model",
    "asr_model_sha256",
    "vad_model",
    "vad_model_sha256",
    "endpoint_configuration",
)

_SESSION_GUARD = """
CREATE OR REPLACE FUNCTION val_voice_session_identity_is_immutable()
RETURNS trigger AS $$
BEGIN
    IF {comparisons} THEN
        RAISE EXCEPTION
            'voice_sessions identity columns are immutable: which conversation '
            'was heard, when listening began, and exactly which recognizer and '
            'models heard it are the facts the lifecycle moves AROUND. Only '
            'state, closed_at and closed_reason may change. (Voice mode work '
            'package 1, 23 September 2026.)';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


def _session_guard_sql() -> str:
    comparisons = "\n        OR ".join(
        f"NEW.{column} IS DISTINCT FROM OLD.{column}" for column in SESSION_IDENTITY
    )
    return _SESSION_GUARD.format(comparisons=comparisons)


def upgrade() -> None:
    """The session, the provenance, and the journal."""
    uuid = postgresql.UUID(as_uuid=True)
    now = sa.text("now()")
    uuidv7 = sa.text("uuidv7()")

    # --- the session ------------------------------------------------------------------
    op.create_table(
        "voice_sessions",
        sa.Column("id", uuid, nullable=False, server_default=uuidv7),
        sa.Column("conversation_id", uuid, nullable=False),
        sa.Column(
            "started_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=now
        ),
        # Present exactly when the session is over, so "still listening" and
        # "finished listening" are different shapes rather than the same shape
        # with a different word in it.
        sa.Column("closed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        # The state the session reached. A session row is written once and closed
        # once; the live state a desktop polls is process state, not this column.
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("closed_reason", sa.Text(), nullable=True),
        # Exactly what heard this. Recorded on the session rather than looked up
        # later, because *you typed* and *the recognizer heard* are different
        # claims and the difference should survive a model upgrade.
        sa.Column("recognizer", sa.Text(), nullable=False),
        sa.Column("recognizer_version", sa.Text(), nullable=False),
        sa.Column("recognizer_commit", sa.Text(), nullable=False),
        sa.Column("asr_model", sa.Text(), nullable=False),
        sa.Column("asr_model_sha256", sa.Text(), nullable=False),
        sa.Column("vad_model", sa.Text(), nullable=False),
        sa.Column("vad_model_sha256", sa.Text(), nullable=False),
        # The endpointing figures actually in force, so a transcript's boundaries
        # are readable from the record rather than from whatever the code says today.
        sa.Column("endpoint_configuration", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_voice_sessions"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], name="fk_voice_sessions_conversation"
        ),
        sa.CheckConstraint(
            "state IN ('listening', 'hearing', 'thinking', 'closed', 'error')",
            name="state_is_known",
        ),
        # A closed session has an end; an open one does not pretend to.
        sa.CheckConstraint(
            "(state IN ('closed', 'error')) = (closed_at IS NOT NULL)",
            name="closed_exactly_when_it_ended",
        ),
        sa.CheckConstraint("recognizer = 'whisper.cpp'", name="recognizer_is_the_local_one"),
        sa.CheckConstraint("length(asr_model_sha256) = 64", name="asr_model_is_a_digest"),
        sa.CheckConstraint("length(vad_model_sha256) = 64", name="vad_model_is_a_digest"),
    )
    op.create_index("ix_voice_sessions_conversation", "voice_sessions", ["conversation_id"])
    _no_hard_delete("voice_sessions")
    op.execute(_session_guard_sql())
    op.execute(
        "CREATE TRIGGER voice_sessions_identity_is_immutable BEFORE UPDATE ON voice_sessions "
        "FOR EACH ROW EXECUTE FUNCTION val_voice_session_identity_is_immutable()"
    )

    # --- the provenance sidecar -------------------------------------------------------
    op.create_table(
        "voice_message_provenance",
        sa.Column("id", uuid, nullable=False, server_default=uuidv7),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=now
        ),
        sa.Column("message_id", uuid, nullable=False),
        sa.Column("voice_session_id", uuid, nullable=False),
        # Stated rather than implied. A reader asking "how did this turn arrive?"
        # gets an answer in the row, not from the table's name.
        sa.Column("input_mode", sa.Text(), nullable=False, server_default="voice"),
        # **Only ever `final`.** A provisional guess is not a message, so it can
        # have no provenance row; the constraint below is what makes that true of
        # the store rather than only of the code.
        sa.Column("transcription_status", sa.Text(), nullable=False, server_default="final"),
        sa.Column("finalized_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        # Which breath of the session this was, and why it ended.
        sa.Column("utterance", sa.Integer(), nullable=False),
        sa.Column("endpoint_reason", sa.Text(), nullable=False),
        # How many rolling guesses preceded the settled text. Evidence that the
        # provisional path ran, kept without keeping the guesses themselves.
        sa.Column("provisional_events", sa.Integer(), nullable=False, server_default="0"),
        # The utterance numbers this turn absorbed when the owner resumed before
        # Val answered. Empty on an ordinary turn.
        sa.Column(
            "merged_from",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default=sa.text("'{}'::integer[]"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_voice_message_provenance"),
        # One message, one provenance. Two rows would be two answers to "how did
        # this arrive?", and a message arrives exactly once.
        sa.UniqueConstraint("message_id", name="uq_voice_message_provenance_message"),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name="fk_voice_message_provenance_message"
        ),
        sa.ForeignKeyConstraint(
            ["voice_session_id"],
            ["voice_sessions.id"],
            name="fk_voice_message_provenance_session",
        ),
        sa.CheckConstraint("input_mode = 'voice'", name="input_mode_is_voice"),
        sa.CheckConstraint("transcription_status = 'final'", name="only_final_is_a_message"),
        sa.CheckConstraint("utterance > 0", name="utterance_is_counted_from_one"),
        sa.CheckConstraint("provisional_events >= 0", name="provisional_events_not_negative"),
        sa.CheckConstraint(
            "endpoint_reason IN ('silence', 'maximum_length', 'flush')",
            name="endpoint_reason_is_known",
        ),
    )
    op.create_index(
        "ix_voice_message_provenance_session", "voice_message_provenance", ["voice_session_id"]
    )
    _guard("voice_message_provenance")

    # --- the text-only recovery journal -----------------------------------------------
    op.create_table(
        "voice_recovery_journal",
        sa.Column("id", uuid, nullable=False, server_default=uuidv7),
        sa.Column(
            "recorded_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=now
        ),
        sa.Column("voice_session_id", uuid, nullable=False),
        # Carried directly as well as through the session, because recovery runs
        # when the process that knew the connection between them has died.
        sa.Column("conversation_id", uuid, nullable=False),
        sa.Column("utterance", sa.Integer(), nullable=False),
        # Append-only supersession: the next state of an entry is the next entry,
        # counted explicitly so ordering is a recorded fact rather than an
        # inference from a timestamp.
        sa.Column("entry", sa.Integer(), nullable=False),
        # **Text only.** The owner's words as last heard — never audio, never a
        # path to audio, never a spectrogram, never a feature vector.
        sa.Column("provisional_text", sa.Text(), nullable=False),
        # `provisional` while it is being spoken; `superseded` once the settled
        # turn exists; `abandoned` when the session ended without one;
        # `interrupted` when a later startup found it open. Nothing here is ever
        # `final`: this table holds no canonical statement by anybody.
        sa.Column("state", sa.Text(), nullable=False),
        # The canonical message that replaced this guess, when one exists. The
        # link runs journal → message and never the other way, so conversation
        # history does not gain a reference to a guess.
        sa.Column("superseded_by_message_id", uuid, nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_voice_recovery_journal"),
        sa.UniqueConstraint(
            "voice_session_id", "utterance", "entry", name="uq_voice_recovery_journal_entry"
        ),
        sa.ForeignKeyConstraint(
            ["voice_session_id"], ["voice_sessions.id"], name="fk_voice_recovery_journal_session"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_voice_recovery_journal_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_message_id"],
            ["messages.id"],
            name="fk_voice_recovery_journal_message",
        ),
        sa.CheckConstraint(
            "state IN ('provisional', 'superseded', 'abandoned', 'interrupted')",
            name="state_is_known_and_never_final",
        ),
        # A superseding entry names the turn that superseded it; nothing else may
        # claim one. This is what stops recovered provisional text from being
        # promoted to a canonical statement by writing a state and no message.
        sa.CheckConstraint(
            "(state = 'superseded') = (superseded_by_message_id IS NOT NULL)",
            name="superseded_names_its_message",
        ),
        sa.CheckConstraint("utterance > 0", name="utterance_is_counted_from_one"),
        sa.CheckConstraint("entry > 0", name="entry_is_counted_from_one"),
    )
    op.create_index(
        "ix_voice_recovery_journal_session", "voice_recovery_journal", ["voice_session_id"]
    )
    # Startup recovery asks one question: which conversations have an open guess?
    op.create_index(
        "ix_voice_recovery_journal_open",
        "voice_recovery_journal",
        ["conversation_id"],
        postgresql_where=sa.text("state = 'provisional'"),
    )
    _guard("voice_recovery_journal")


def downgrade() -> None:
    """Reversible, as WP-0.2 requires."""
    for table in ("voice_recovery_journal", "voice_message_provenance"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_rows_are_evidence ON {table}")
    op.execute("DROP TRIGGER IF EXISTS voice_sessions_identity_is_immutable ON voice_sessions")
    for table in ("voice_recovery_journal", "voice_message_provenance", "voice_sessions"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_forbid_hard_delete ON {table}")
    op.drop_table("voice_recovery_journal")
    op.drop_table("voice_message_provenance")
    op.drop_table("voice_sessions")
    op.execute("DROP FUNCTION IF EXISTS val_voice_session_identity_is_immutable()")
