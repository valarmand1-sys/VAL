"""Light conversation, and its speculative preparation, are on the record — 26 Sept 2026.

Latency redesign §5, §6. A spoken greeting, thanks, farewell or pleasantry may be
carried by a fast local route in a candidate build (`light_conversation`), and may be
**prepared before the turn is confirmed** while the resume window still runs
(`speculative_light_conversation`). Both are real invocations of a model and Layer 0
captures every invocation: `model_calls.task_type` gains both values.

A preparation is not an answer. `speculative_preparations` records what became of
each one — accepted into a turn, or discarded because he resumed, because the
completed request no longer matched, or because the turn was not light after all —
with the call it made, so cost is attributed and nothing is inferred. It holds a
digest of the settled words, never the words: a preparation he did not confirm is
not his message.

Forward only in intent, as `0031_prefix_prime`: PostgreSQL cannot remove an enum
value, and the downgrade refuses if any such call is recorded rather than rewriting
what those rows were. The table is dropped only when empty.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032_light_conversation"
down_revision: str | None = "0031_prefix_prime"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.execute("ALTER TYPE model_call_task_type ADD VALUE IF NOT EXISTS 'light_conversation'")
    op.execute(
        "ALTER TYPE model_call_task_type ADD VALUE IF NOT EXISTS 'speculative_light_conversation'"
    )
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "speculative_preparations",
        sa.Column("id", uuid, nullable=False, server_default=sa.text("uuidv7()")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # The conversation it was prepared for; NULL when the words would have opened one.
        sa.Column("conversation_id", uuid, nullable=True),
        # A digest of the settled words, not the words.
        sa.Column("utterance_sha256", sa.Text(), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        # The speculative call, when one was made; NULL when nothing was sent.
        sa.Column("model_call_id", uuid, nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        # Set only when accepted: his message, and her answer built from the preparation.
        sa.Column("user_message_id", uuid, nullable=True),
        sa.Column("answer_message_id", uuid, nullable=True),
        sa.Column("prepared_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_speculative_preparations"),
        sa.ForeignKeyConstraint(
            ["model_call_id"], ["model_calls.id"], name="fk_speculative_preparations_call"
        ),
        sa.ForeignKeyConstraint(
            ["user_message_id"], ["messages.id"], name="fk_speculative_preparations_user"
        ),
        sa.ForeignKeyConstraint(
            ["answer_message_id"], ["messages.id"], name="fk_speculative_preparations_answer"
        ),
        sa.CheckConstraint(
            "outcome IN ('accepted', 'discarded_resumed', 'discarded_mismatch', "
            "'discarded_not_light', 'discarded_unused', 'failed')",
            name="outcome_is_known",
        ),
        sa.CheckConstraint("tier IN (1, 2)", name="tier_is_light"),
        sa.CheckConstraint(
            "(outcome = 'accepted') = "
            "(user_message_id IS NOT NULL AND answer_message_id IS NOT NULL)",
            name="accepted_names_both_messages",
        ),
        sa.CheckConstraint("length(utterance_sha256) = 64", name="digest_is_sha256"),
    )
    op.create_index(
        "ix_speculative_preparations_conversation",
        "speculative_preparations",
        ["conversation_id"],
    )
    op.execute(
        "CREATE TRIGGER speculative_preparations_forbid_hard_delete "
        "BEFORE DELETE OR TRUNCATE ON speculative_preparations "
        "FOR EACH STATEMENT EXECUTE FUNCTION val_forbid_hard_delete()"
    )
    op.execute(
        "CREATE TRIGGER speculative_preparations_rows_are_evidence "
        "BEFORE UPDATE ON speculative_preparations "
        "FOR EACH ROW EXECUTE FUNCTION val_rows_are_evidence()"
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM model_calls WHERE task_type::text IN "
        "  ('light_conversation', 'speculative_light_conversation')) "
        "OR EXISTS (SELECT 1 FROM budget_reservations WHERE task_type::text IN "
        "  ('light_conversation', 'speculative_light_conversation')) "
        "OR EXISTS (SELECT 1 FROM speculative_preparations) "
        "THEN RAISE EXCEPTION 'Refusing to downgrade: light or speculative calls are recorded, "
        "and removing them would rewrite what they were.'; "
        "END IF; END $$"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS speculative_preparations_rows_are_evidence "
        "ON speculative_preparations"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS speculative_preparations_forbid_hard_delete "
        "ON speculative_preparations"
    )
    op.drop_index("ix_speculative_preparations_conversation", table_name="speculative_preparations")
    op.drop_table("speculative_preparations")
    # The unused enum values stay in the type: PostgreSQL has no DROP VALUE.
