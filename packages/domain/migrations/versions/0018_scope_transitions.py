"""Explicit scope transitions with immutable history — ruling of 12 September 2026.

`04-layer-0.md` §2.1 amendment of 12 September 2026, item 8 (Option B). Lord
Armand may move an existing conversation into a project, out of one, or between
projects. **`conversations.project_id` stays the immutable origin scope** —
`0008`'s guard is untouched and nothing here updates that column. A move is an
appended fact that establishes the **effective scope** for everything after it;
the scope under which earlier messages and calls occurred is never rewritten.
This amends WP-0.6's forward-only doctrine for this one explicit, user-initiated
case; a scope stated inside a turn still starts a new conversation.

## What is added

**`conversation_scope_transitions`** — append-only, undeletable:
`conversation_id`; a per-conversation `transition_number`; `after_sequence`, the
conversation's highest message sequence when the move was recorded, read under
the conversation row lock; `from_project_id` and `to_project_id` (NULL meaning
explicitly no project, as everywhere); `authored_by`; an optional `note`. A
coherence trigger refuses a skipped number, a stale `after_sequence`, a
`from_project_id` that is not the conversation's effective scope at that moment,
a move to the scope it already has, and a move of a removed conversation.

**`val_effective_project_id(conversation_id, at_sequence)`** — the one derivation
of scope: the `to_project_id` of the newest transition with
`after_sequence < at_sequence`, or the origin when there is none. A message at
sequence *q* was written in `val_effective_project_id(conversation, q)`; the scope
for the next turn is the value at the largest sequence. Sequence-based, never
timestamp-based, for the same reason as `message_revisions` (`0016`).

**`val_scope_transitions(conversation_id)`** — how many transitions the
conversation has, so a reader can tell a moved conversation from one that never was.

## Downgrade

Refuses once any transition exists. Clean on an empty table (CI).

Revision ID: 0018_scope_transitions
Revises: 0017_conversation_removals
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_scope_transitions"
down_revision: str | None = "0017_conversation_removals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "conversation_scope_transitions"

EFFECTIVE = """
CREATE OR REPLACE FUNCTION val_effective_project_id(target uuid, at_sequence bigint)
RETURNS uuid AS $$
    SELECT CASE WHEN t.id IS NULL THEN c.project_id ELSE t.to_project_id END
      FROM conversations c
      LEFT JOIN LATERAL (
            SELECT s.id, s.to_project_id
              FROM conversation_scope_transitions s
             WHERE s.conversation_id = c.id
               AND s.after_sequence < at_sequence
             ORDER BY s.transition_number DESC
             LIMIT 1) t ON true
     WHERE c.id = target
$$ LANGUAGE sql STABLE
"""

COUNT = """
CREATE OR REPLACE FUNCTION val_scope_transitions(target uuid)
RETURNS integer AS $$
    SELECT count(*)::integer FROM conversation_scope_transitions WHERE conversation_id = target
$$ LANGUAGE sql STABLE
"""

COHERENCE = """
CREATE OR REPLACE FUNCTION val_scope_transition_is_coherent()
RETURNS trigger AS $$
DECLARE
    next_number integer;
    highest bigint;
    current_scope uuid;
BEGIN
    SELECT coalesce(max(transition_number), 0) + 1 INTO next_number
      FROM conversation_scope_transitions WHERE conversation_id = NEW.conversation_id;
    IF NEW.transition_number <> next_number THEN
        RAISE EXCEPTION 'transition_number % is not the next number % for conversation %',
            NEW.transition_number, next_number, NEW.conversation_id;
    END IF;
    SELECT coalesce(max(sequence), 0) INTO highest
      FROM messages WHERE conversation_id = NEW.conversation_id;
    IF NEW.after_sequence <> highest THEN
        RAISE EXCEPTION
            'after_sequence % is not the conversation''s highest sequence %; it must be '
            'read under the conversation row lock (ruling, 12 September 2026)',
            NEW.after_sequence, highest;
    END IF;
    current_scope := val_effective_project_id(NEW.conversation_id, 9223372036854775807);
    IF NEW.from_project_id IS DISTINCT FROM current_scope THEN
        RAISE EXCEPTION
            'from_project_id % is not conversation %''s effective scope %; a move starts '
            'from where the conversation actually is',
            NEW.from_project_id, NEW.conversation_id, current_scope;
    END IF;
    IF val_conversation_removed_at(NEW.conversation_id) IS NOT NULL THEN
        RAISE EXCEPTION 'conversation % is removed; reinstate it before moving it',
            NEW.conversation_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


def upgrade() -> None:
    """Create the transition table, its guards, and the two scope derivations."""
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
        sa.Column("transition_number", sa.Integer(), nullable=False),
        sa.Column("after_sequence", sa.BigInteger(), nullable=False),
        sa.Column("from_project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("to_project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("authored_by", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint("transition_number > 0", name="transition_number_positive"),
        sa.CheckConstraint("after_sequence >= 0", name="after_sequence_not_negative"),
        sa.CheckConstraint(
            "from_project_id IS DISTINCT FROM to_project_id", name="a_move_changes_scope"
        ),
        sa.CheckConstraint("length(btrim(authored_by)) > 0", name="authored_by_named"),
        sa.PrimaryKeyConstraint("id", name=f"pk_{TABLE}"),
        sa.UniqueConstraint(
            "conversation_id",
            "transition_number",
            name="uq_scope_transitions_conversation_number",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=f"fk_{TABLE}_conversation_id",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["from_project_id"],
            ["projects.id"],
            name=f"fk_{TABLE}_from_project_id",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["to_project_id"],
            ["projects.id"],
            name=f"fk_{TABLE}_to_project_id",
            ondelete="NO ACTION",
        ),
    )
    op.create_index(
        "ix_scope_transitions_conversation_after", TABLE, ["conversation_id", "after_sequence"]
    )
    op.execute(EFFECTIVE)
    op.execute(COUNT)
    op.execute(COHERENCE)
    op.execute(
        f"CREATE TRIGGER {TABLE}_is_coherent BEFORE INSERT ON {TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION val_scope_transition_is_coherent()"
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
    """Refuse once a transition exists; otherwise remove the derivations and the table."""
    count = op.get_bind().execute(sa.text(f"select count(*) from {TABLE}")).scalar_one()  # noqa: S608
    if count:
        raise RuntimeError(
            f"{TABLE} holds {count} scope transition(s); every message and call after "
            "them is attributed to the scope they established. A downgrade would destroy "
            "that history. Refused."
        )
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_rows_are_evidence ON {TABLE}")
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_forbid_hard_delete ON {TABLE}")
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_is_coherent ON {TABLE}")
    op.execute("DROP FUNCTION IF EXISTS val_scope_transition_is_coherent()")
    op.execute("DROP FUNCTION IF EXISTS val_scope_transitions(uuid)")
    op.execute("DROP FUNCTION IF EXISTS val_effective_project_id(uuid, bigint)")
    op.drop_index("ix_scope_transitions_conversation_after", table_name=TABLE)
    op.drop_table(TABLE)
