"""Conversation Remove and Reinstate as appended facts — ruling of 12 September 2026.

`04-layer-0.md` §2.1 amendment of 12 September 2026, item 7. Archive hides a
conversation from the default listing and nothing else. **Remove** withdraws a
conversation from active use: it is excluded from automatic recall and from
House Recall, and it cannot be resumed for new turns — while every message,
evidence row, judgment and cost stays exactly as it was. Reinstating is another
appended fact. The ordinary label is Remove, never Delete; true erasure is a
separate operation outside this scope, and nothing here weakens the no-delete
guards.

## What is added

**`conversation_removals`** — append-only, undeletable: `conversation_id`, a
per-conversation `event_number` (the next number, under the conversation row
lock), `kind` (`removed` | `reinstated`), `authored_by`, and an optional `note`.
A coherence trigger refuses a skipped number, removing a removed conversation,
and reinstating one that is not removed.

**`val_conversation_removed_at(conversation_id)`** — the one derivation of
removal state: the instant of the newest `removed` fact when that is the newest
fact, otherwise NULL. A stable SQL function, read inside the recall queries and
the conversation reads; it holds no state and mutates nothing.

No column is added to `conversations`.

## Downgrade

Refuses once any fact exists. Clean on an empty table (CI).

Revision ID: 0017_conversation_removals
Revises: 0016_message_revisions
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_conversation_removals"
down_revision: str | None = "0016_message_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "conversation_removals"
KIND = "conversation_removal_kind"

REMOVED_AT = """
CREATE OR REPLACE FUNCTION val_conversation_removed_at(target uuid)
RETURNS timestamptz AS $$
    SELECT CASE WHEN r.kind = 'removed' THEN r.created_at END
      FROM conversation_removals r
     WHERE r.conversation_id = target
     ORDER BY r.event_number DESC
     LIMIT 1
$$ LANGUAGE sql STABLE
"""

COHERENCE = """
CREATE OR REPLACE FUNCTION val_conversation_removal_is_coherent()
RETURNS trigger AS $$
DECLARE
    next_number integer;
    newest text;
BEGIN
    SELECT coalesce(max(event_number), 0) + 1 INTO next_number
      FROM conversation_removals WHERE conversation_id = NEW.conversation_id;
    IF NEW.event_number <> next_number THEN
        RAISE EXCEPTION 'event_number % is not the next number % for conversation %',
            NEW.event_number, next_number, NEW.conversation_id;
    END IF;
    SELECT kind::text INTO newest FROM conversation_removals
     WHERE conversation_id = NEW.conversation_id
     ORDER BY event_number DESC LIMIT 1;
    IF NEW.kind = 'removed' AND newest = 'removed' THEN
        RAISE EXCEPTION 'conversation % is already removed', NEW.conversation_id;
    END IF;
    IF NEW.kind = 'reinstated' AND coalesce(newest, 'reinstated') <> 'removed' THEN
        RAISE EXCEPTION 'conversation % is not removed; there is nothing to reinstate',
            NEW.conversation_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


def upgrade() -> None:
    """Create the kind, the fact table and its guards, and the removal derivation."""
    op.execute(f"CREATE TYPE {KIND} AS ENUM ('removed', 'reinstated')")
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
        sa.Column("event_number", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM("removed", "reinstated", name=KIND, create_type=False),
            nullable=False,
        ),
        sa.Column("authored_by", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint("event_number > 0", name="event_number_positive"),
        sa.CheckConstraint("length(btrim(authored_by)) > 0", name="authored_by_named"),
        sa.PrimaryKeyConstraint("id", name=f"pk_{TABLE}"),
        sa.UniqueConstraint(
            "conversation_id", "event_number", name=f"uq_{TABLE}_conversation_id_event_number"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=f"fk_{TABLE}_conversation_id",
            ondelete="NO ACTION",
        ),
    )
    op.execute(COHERENCE)
    op.execute(
        f"CREATE TRIGGER {TABLE}_is_coherent BEFORE INSERT ON {TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION val_conversation_removal_is_coherent()"
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
    op.execute(REMOVED_AT)


def downgrade() -> None:
    """Refuse once a fact exists; otherwise remove the derivation, the table and the kind."""
    count = op.get_bind().execute(sa.text(f"select count(*) from {TABLE}")).scalar_one()  # noqa: S608
    if count:
        raise RuntimeError(
            f"{TABLE} holds {count} removal fact(s); a downgrade would destroy them. Refused."
        )
    op.execute("DROP FUNCTION IF EXISTS val_conversation_removed_at(uuid)")
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_rows_are_evidence ON {TABLE}")
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_forbid_hard_delete ON {TABLE}")
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_is_coherent ON {TABLE}")
    op.execute("DROP FUNCTION IF EXISTS val_conversation_removal_is_coherent()")
    op.drop_table(TABLE)
    op.execute(f"DROP TYPE IF EXISTS {KIND}")
