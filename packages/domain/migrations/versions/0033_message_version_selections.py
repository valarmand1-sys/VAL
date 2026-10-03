"""Continuing from an earlier version of a message — owner order, 2 October 2026 (§C).

A correction of one of Lord Armand's messages is a version of it, and each version keeps
the exchanges that followed it (`message_revisions`, 12 September 2026). This table
records the one further fact versions need: that he **continued from an earlier
version** — so the messages appended after that point belong to that version's
continuation, not to the newest wording's. Append-only, numbered under the
conversation row lock like a revision (`after_sequence`), never updated or deleted.
`revision_number` 0 names the original wording; any other value must be an existing
`revision`-kind fact of the same message.

Revision ID: 0033_message_version_selections
Revises: 0032_light_conversation
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033_message_version_selections"
down_revision: str | None = "0032_light_conversation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "message_version_selections"

COHERENCE = """
CREATE OR REPLACE FUNCTION val_message_version_selection_is_coherent()
RETURNS trigger AS $$
DECLARE
    message_role text;
    message_conversation uuid;
BEGIN
    SELECT role, conversation_id INTO message_role, message_conversation
      FROM messages WHERE id = NEW.message_id;
    IF message_role IS NULL THEN
        RAISE EXCEPTION 'message % does not exist', NEW.message_id;
    END IF;
    IF message_role <> 'user' THEN
        RAISE EXCEPTION 'only one of Lord Armand''s messages has versions (message %)',
            NEW.message_id;
    END IF;
    IF message_conversation <> NEW.conversation_id THEN
        RAISE EXCEPTION 'message % belongs to another conversation', NEW.message_id;
    END IF;
    IF NEW.revision_number <> 0 AND NOT EXISTS (
        SELECT 1 FROM message_revisions r
         WHERE r.message_id = NEW.message_id
           AND r.revision_number = NEW.revision_number
           AND r.kind = 'revision'
    ) THEN
        RAISE EXCEPTION 'message % has no revision % to continue from',
            NEW.message_id, NEW.revision_number;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuidv7()")
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("after_sequence", sa.BigInteger(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint("revision_number >= 0", name="revision_number_not_negative"),
        sa.CheckConstraint("after_sequence > 0", name="after_sequence_positive"),
        sa.PrimaryKeyConstraint("id", name=f"pk_{TABLE}"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=f"fk_{TABLE}_conversation_id",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name=f"fk_{TABLE}_message_id", ondelete="NO ACTION"
        ),
    )
    op.create_index(
        f"ix_{TABLE}_conversation_id_after_sequence", TABLE, ["conversation_id", "after_sequence"]
    )
    op.execute(COHERENCE)
    op.execute(
        f"CREATE TRIGGER {TABLE}_is_coherent BEFORE INSERT ON {TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION val_message_version_selection_is_coherent()"
    )
    op.execute(
        f"CREATE TRIGGER {TABLE}_forbid_hard_delete "
        f"BEFORE DELETE OR TRUNCATE ON {TABLE} "
        "FOR EACH STATEMENT EXECUTE FUNCTION val_forbid_hard_delete()"
    )
    op.execute(
        f"CREATE TRIGGER {TABLE}_rows_are_evidence "
        f"BEFORE UPDATE ON {TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION val_rows_are_evidence()"
    )


def downgrade() -> None:
    """Refuse once a fact exists; otherwise remove the table and its function."""
    bind = op.get_bind()
    count = bind.execute(sa.text(f"SELECT count(*) FROM {TABLE}")).scalar_one()  # noqa: S608
    if count:
        raise RuntimeError(
            f"{TABLE} holds {count} appended fact(s); a downgrade would erase history. Refused."
        )
    op.drop_table(TABLE)
    op.execute("DROP FUNCTION IF EXISTS val_message_version_selection_is_coherent()")
