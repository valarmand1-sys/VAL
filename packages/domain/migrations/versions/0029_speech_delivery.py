"""What the owner actually heard — owner execution order, 23 September 2026.

Voice mode work package 2 §10 and §11. Two facts this migration makes
representable, both of which the store could previously only lie about.

**Live speech is ephemeral.** `speech_generations.audio_path` was NOT NULL,
which assumed every utterance leaves a file behind. Qualification samples do and
should. Ordinary live conversation must not: turning every spoken answer into a
waveform on disk would make Val's voice an archive of the household's talk. So
the column becomes nullable and gains a companion that *says which it is* —
`audio_retained` — held to the path by a check constraint, so a row can never
claim a file that does not exist nor hide one that does. The digest, duration and
byte count stay: they are facts about audio that really was produced, and they
remain true after the bytes are released.

**Delivery is not generation.** Core can finish writing text the owner never
hears, because he interrupts her. Nothing durable may later behave as though the
unheard part was delivered. `speech_deliveries` is the append-only record of what
delivery actually did: one row per transition, each carrying the exact delivered
prefix at that moment. The state of a delivery is its highest-numbered row —
never an UPDATE, so `interrupted` can never be quietly promoted to `completed`.

The original assistant message is untouched by all of this. What Core generated
and what delivery delivered are two facts, and this migration is how the second
one stops being a guess.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029_speech_delivery"
down_revision: str | None = "0028_voice_input"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    """Ephemeral speech, segment ordering, and the delivery record."""
    uuid = postgresql.UUID(as_uuid=True)
    now = sa.text("now()")
    uuidv7 = sa.text("uuidv7()")

    # --- live speech leaves no file behind --------------------------------------------
    #
    # Every existing row is a qualification or verification sample whose waveform
    # is on disk, so the default is `true` and the historical evidence keeps
    # saying exactly what it said.
    op.add_column(
        "speech_generations",
        sa.Column("audio_retained", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.alter_column("speech_generations", "audio_path", nullable=True)
    op.create_check_constraint(
        "retained_names_its_file",
        "speech_generations",
        "audio_retained = (audio_path IS NOT NULL)",
    )
    # Progressive delivery makes one generation per speech-safe segment, so a
    # message has several. NULL means a whole-utterance generation, which is what
    # every row written before this migration is.
    op.add_column("speech_generations", sa.Column("segment_index", sa.Integer(), nullable=True))
    op.add_column("speech_generations", sa.Column("segment_reason", sa.Text(), nullable=True))
    op.create_check_constraint(
        "segment_index_is_counted_from_one",
        "speech_generations",
        "segment_index IS NULL OR segment_index > 0",
    )
    op.create_check_constraint(
        "a_segment_says_why_it_ended",
        "speech_generations",
        "(segment_index IS NULL) = (segment_reason IS NULL)",
    )
    # One row per segment of a message. Partial, because the historical
    # whole-utterance rows carry no segment number and several may share a message.
    op.create_index(
        "uq_speech_generations_message_segment",
        "speech_generations",
        ["message_id", "segment_index"],
        unique=True,
        postgresql_where=sa.text("message_id IS NOT NULL AND segment_index IS NOT NULL"),
    )

    # --- what the owner actually received ---------------------------------------------
    op.create_table(
        "speech_deliveries",
        sa.Column("id", uuid, nullable=False, server_default=uuidv7),
        sa.Column(
            "recorded_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=now
        ),
        # The assistant message whose words were being spoken.
        sa.Column("message_id", uuid, nullable=False),
        # The listening session this delivery belonged to, when there was one.
        # NULL for a house-internal delivery — an acceptance run — which reads
        # differently from a delivery with no session at all.
        sa.Column("voice_session_id", uuid, nullable=True),
        # Append-only supersession: the next state of a delivery is the next
        # event, numbered explicitly so the order is recorded rather than inferred.
        sa.Column("event", sa.Integer(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        # **The exact prefix the owner heard**, and its length. This is the whole
        # point of the table: an interrupted answer is truthfully half-heard, and
        # the half is written down rather than reconstructed later from a guess.
        sa.Column("delivered_prefix", sa.Text(), nullable=False, server_default=""),
        sa.Column("delivered_characters", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("segments_delivered", sa.Integer(), nullable=False, server_default="0"),
        # How many segments the answer came to in the end. NULL while Val is still
        # writing, because the number is not known yet and 0 would be a claim.
        sa.Column("segments_total", sa.Integer(), nullable=True),
        # Why an interrupted or failed delivery ended that way. Required for those
        # two states and forbidden for the others, so a state and its reason
        # cannot disagree.
        sa.Column("reason", sa.Text(), nullable=True),
        # From the request that produced the text to the first audio handed to the
        # delivery sink; and how long delivery lasted.
        sa.Column("first_audio_ms", sa.Integer(), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_speech_deliveries"),
        sa.UniqueConstraint("message_id", "event", name="uq_speech_deliveries_event"),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name="fk_speech_deliveries_message"
        ),
        sa.ForeignKeyConstraint(
            ["voice_session_id"], ["voice_sessions.id"], name="fk_speech_deliveries_session"
        ),
        sa.CheckConstraint(
            "state IN ('not_started', 'started', 'completed', 'interrupted', 'failed')",
            name="state_is_known",
        ),
        sa.CheckConstraint(
            "(state IN ('interrupted', 'failed')) = (reason IS NOT NULL)",
            name="a_state_and_its_reason_agree",
        ),
        sa.CheckConstraint("event > 0", name="event_is_counted_from_one"),
        sa.CheckConstraint(
            "delivered_characters >= 0 AND segments_delivered >= 0",
            name="counts_are_not_negative",
        ),
        sa.CheckConstraint(
            "segments_total IS NULL OR segments_total >= segments_delivered",
            name="segments_delivered_fit_the_total",
        ),
        sa.CheckConstraint(
            "length(delivered_prefix) = delivered_characters",
            name="the_prefix_and_its_length_agree",
        ),
        # Nothing was delivered before delivery started.
        sa.CheckConstraint(
            "state <> 'not_started' OR (delivered_characters = 0 AND segments_delivered = 0)",
            name="nothing_delivered_before_start",
        ),
    )
    op.create_index("ix_speech_deliveries_message", "speech_deliveries", ["message_id"])
    op.create_index("ix_speech_deliveries_session", "speech_deliveries", ["voice_session_id"])
    op.execute(
        "CREATE TRIGGER speech_deliveries_forbid_hard_delete "
        "BEFORE DELETE OR TRUNCATE ON speech_deliveries "
        "FOR EACH STATEMENT EXECUTE FUNCTION val_forbid_hard_delete()"
    )
    op.execute(
        "CREATE TRIGGER speech_deliveries_rows_are_evidence BEFORE UPDATE ON speech_deliveries "
        "FOR EACH ROW EXECUTE FUNCTION val_rows_are_evidence()"
    )


def downgrade() -> None:
    """Reversible, as WP-0.2 requires.

    The nullability is restored only when no row actually relies on it: an
    ephemeral generation has no path to put back, and inventing one would be
    exactly the fabrication §10 forbids.
    """
    op.execute("DROP TRIGGER IF EXISTS speech_deliveries_rows_are_evidence ON speech_deliveries")
    op.execute("DROP TRIGGER IF EXISTS speech_deliveries_forbid_hard_delete ON speech_deliveries")
    op.drop_table("speech_deliveries")

    op.drop_index("uq_speech_generations_message_segment", table_name="speech_generations")
    op.drop_constraint("a_segment_says_why_it_ended", "speech_generations", type_="check")
    op.drop_constraint(
        "segment_index_is_counted_from_one",
        "speech_generations",
        type_="check",
    )
    op.drop_column("speech_generations", "segment_reason")
    op.drop_column("speech_generations", "segment_index")
    op.drop_constraint("retained_names_its_file", "speech_generations", type_="check")
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM speech_generations WHERE audio_path IS NULL) THEN "
        "RAISE EXCEPTION 'Refusing to downgrade: ephemeral speech generations exist with no "
        "audio file. Restoring NOT NULL would require inventing a path to a file that was "
        "never written (work package 2 §10). Remove those rows deliberately first.'; "
        "END IF; END $$"
    )
    op.alter_column("speech_generations", "audio_path", nullable=False)
    op.drop_column("speech_generations", "audio_retained")
