"""Message revision and retraction as appended facts — ruling of 12 September 2026.

`04-layer-0.md` §2.1 required Lord Armand be able to correct and retract his own
messages, bounded by *correction and retraction, never erasure*. The ruling of
12 September 2026 (the §2.1 amendment of that date, on
`VAL_Conversation_Management_Diagnostic.md` §3) chose the representation.

## What is added

**`message_revisions`** — one append-only, undeletable sidecar. No column is
added to `messages`, and no `messages` row is ever touched: the original stays
exactly what was said.

- `message_id` — the **user** message this fact is about; Val's words are never
  revised or retracted;
- `revision_number` — 1, 2, 3 … per message, the next number under the lock;
- `after_sequence` — the conversation's highest `messages.sequence` **when the
  fact was recorded, read while holding the conversation row lock**;
- `kind` — `revision` or `retraction`;
- `content` — the corrected wording, present exactly for a revision;
- `authored_by`, `note` — who recorded it; an optional note, never required.

**Why `after_sequence` and not a timestamp.** The turn whose user message has
sequence *s* sees every fact with `after_sequence < s`, and none after. Both
appends and revisions take the same conversation row lock, so the number is
exact under concurrency; a timestamp comparison is not (`model_calls.created_at`
is settlement time, and `now()` is transaction start). This is what makes a
revision incapable of altering the reconstructed input of any earlier call.

**The coherence trigger** refuses, at insert: a message that is not a user
message; a conversation that is not the message's; an `after_sequence` that is
not the conversation's current highest sequence; a `revision_number` that is not
the next one; and a **revision** of a message that anchors an `enforced` blind
position or any deliberation (the ruling's §9.1 option 1 — retraction remains
permitted). The writer checks the same things first, in words; the trigger is
the backstop that holds for any writer.

**`messages_current`** — the single authoritative derivation of current state,
stated once: each message's current wording, its state (`current` |
`corrected` | `withdrawn`), and, for a Val message, the state of the user
message it immediately answered, with `live` false for a withdrawn message and
its immediate answer. A view: it holds no state and mutates nothing.

Frozen by the standing guards `val_forbid_hard_delete` and `val_rows_are_evidence`.

## Downgrade

Refuses once any fact exists. Clean on an empty table (CI).

Revision ID: 0016_message_revisions
Revises: 0015_model_call_cache_usage
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_message_revisions"
down_revision: str | None = "0015_model_call_cache_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "message_revisions"
KIND = "message_revision_kind"

COHERENCE = """
CREATE OR REPLACE FUNCTION val_message_revision_is_coherent()
RETURNS trigger AS $$
DECLARE
    stored_role text;
    stored_conversation uuid;
    highest bigint;
    next_number integer;
BEGIN
    SELECT m.role::text, m.conversation_id INTO stored_role, stored_conversation
      FROM messages m WHERE m.id = NEW.message_id;
    IF stored_role IS NULL THEN
        RAISE EXCEPTION 'message % does not exist; a revision is of something said', NEW.message_id;
    END IF;
    IF stored_role <> 'user' THEN
        RAISE EXCEPTION
            'message % is a % message. Only Lord Armand''s own messages may be '
            'revised or retracted; Val''s words are hers (04-layer-0.md 2.1).',
            NEW.message_id, stored_role;
    END IF;
    IF stored_conversation <> NEW.conversation_id THEN
        RAISE EXCEPTION 'message % belongs to conversation %, not %',
            NEW.message_id, stored_conversation, NEW.conversation_id;
    END IF;
    SELECT max(sequence) INTO highest FROM messages WHERE conversation_id = NEW.conversation_id;
    IF NEW.after_sequence IS DISTINCT FROM highest THEN
        RAISE EXCEPTION
            'after_sequence % is not the conversation''s highest sequence %; it must be '
            'read under the conversation row lock (ruling, 12 September 2026)',
            NEW.after_sequence, highest;
    END IF;
    SELECT coalesce(max(revision_number), 0) + 1 INTO next_number
      FROM message_revisions WHERE message_id = NEW.message_id;
    IF NEW.revision_number <> next_number THEN
        RAISE EXCEPTION 'revision_number % is not the next number % for message %',
            NEW.revision_number, next_number, NEW.message_id;
    END IF;
    IF NEW.kind = 'revision' AND (
        EXISTS (SELECT 1 FROM blind_positions b
                 WHERE b.message_id = NEW.message_id AND b.ordering = 'enforced')
        OR EXISTS (SELECT 1 FROM deliberations d WHERE d.message_id = NEW.message_id)
    ) THEN
        RAISE EXCEPTION
            'message % anchors a recorded decision exchange (an enforced blind position '
            'or a deliberation) and cannot be rewritten; it may be retracted '
            '(ruling, 12 September 2026)', NEW.message_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

CURRENT_VIEW = """
CREATE VIEW messages_current AS
SELECT m.id,
       m.conversation_id,
       m.role,
       m.sequence,
       m.created_at,
       m.content AS original_content,
       CASE WHEN f.kind = 'revision' THEN f.content ELSE m.content END AS content,
       CASE WHEN f.kind IS NULL THEN 'current'
            WHEN f.kind = 'revision' THEN 'corrected'
            ELSE 'withdrawn' END AS state,
       f.revision_number AS newest_revision_number,
       f.created_at AS state_recorded_at,
       answered.id AS answered_message_id,
       CASE WHEN answered.id IS NULL THEN NULL
            WHEN af.kind IS NULL THEN 'current'
            WHEN af.kind = 'revision' THEN 'corrected'
            ELSE 'withdrawn' END AS answered_state,
       (coalesce(f.kind::text, '') <> 'retraction'
        AND coalesce(af.kind::text, '') <> 'retraction') AS live
  FROM messages m
  LEFT JOIN LATERAL (
        SELECT r.kind, r.content, r.revision_number, r.created_at
          FROM message_revisions r
         WHERE r.message_id = m.id
         ORDER BY r.revision_number DESC
         LIMIT 1) f ON true
  LEFT JOIN LATERAL (
        SELECT p.id, p.role
          FROM messages p
         WHERE p.conversation_id = m.conversation_id
           AND p.sequence < m.sequence
           AND p.role IN ('user', 'val')
         ORDER BY p.sequence DESC
         LIMIT 1) previous ON m.role = 'val'
  LEFT JOIN messages answered
         ON answered.id = previous.id AND previous.role = 'user'
  LEFT JOIN LATERAL (
        SELECT r.kind
          FROM message_revisions r
         WHERE r.message_id = answered.id
         ORDER BY r.revision_number DESC
         LIMIT 1) af ON true
"""


def upgrade() -> None:
    """Create the kind, the fact table and its guards, and the current-state view."""
    op.execute(f"CREATE TYPE {KIND} AS ENUM ('revision', 'retraction')")
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
        sa.Column(
            "kind",
            postgresql.ENUM("revision", "retraction", name=KIND, create_type=False),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("authored_by", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint("revision_number > 0", name="revision_number_positive"),
        sa.CheckConstraint("after_sequence > 0", name="after_sequence_positive"),
        sa.CheckConstraint(
            "(kind = 'revision') = (content IS NOT NULL)", name="content_iff_revision"
        ),
        sa.CheckConstraint(
            "content IS NULL OR length(btrim(content)) > 0", name="revision_says_something"
        ),
        sa.CheckConstraint("length(btrim(authored_by)) > 0", name="authored_by_named"),
        sa.PrimaryKeyConstraint("id", name=f"pk_{TABLE}"),
        sa.UniqueConstraint(
            "message_id", "revision_number", name=f"uq_{TABLE}_message_id_revision_number"
        ),
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
        "FOR EACH ROW EXECUTE FUNCTION val_message_revision_is_coherent()"
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
    op.execute(CURRENT_VIEW)


def downgrade() -> None:
    """Refuse once a fact exists; otherwise remove the view, the table and the kind."""
    count = op.get_bind().execute(sa.text(f"select count(*) from {TABLE}")).scalar_one()  # noqa: S608
    if count:
        raise RuntimeError(
            f"{TABLE} holds {count} fact(s) about what was said and later corrected or "
            "withdrawn; a downgrade would destroy them. Refused."
        )
    op.execute("DROP VIEW IF EXISTS messages_current")
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_rows_are_evidence ON {TABLE}")
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_forbid_hard_delete ON {TABLE}")
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_is_coherent ON {TABLE}")
    op.execute("DROP FUNCTION IF EXISTS val_message_revision_is_coherent()")
    op.drop_index(f"ix_{TABLE}_conversation_id_after_sequence", table_name=TABLE)
    op.drop_table(TABLE)
    op.execute(f"DROP TYPE IF EXISTS {KIND}")
