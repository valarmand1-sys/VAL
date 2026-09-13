"""House Recall grounding continuity as provenance — ruling of 13 September 2026.

On 13 September a House Recall turn supplied three excerpts and Val made factual
statements from them; on the next turn she received her own answer but nothing
saying it had been grounded, and rightly called her statements unverified. The
recall envelope is assembled per call and never persisted, and the selection was
only logged, so no durable record bound a response to the sources it received.

## What is added

**`answer_recall_sources`** — append-only, undeletable. One row per source that
House Recall admitted to the response call that produced a Val answer, written
when that answer is persisted:

- `conversation_id`, `answer_message_id`, `model_call_id` — the answer, and the
  response call that actually received the excerpts;
- `retrieval_path` — `house_recall` (the only path this ruling covers);
- `rank_position` — the source's place in that selection;
- `source_message_id`, `source_conversation_id`, `source_sequence` — the source;
- **`source_revision_number`** — the wording the response actually saw: NULL for
  the original message, otherwise the `message_revisions` fact in force at
  retrieval. A later revision cannot make this row point at different wording;
- `source_project_id` — the scope the source message was written in (NULL:
  unassigned);
- `source_sent_at` — when the source was said;
- `source_conversation_title` — the title at retrieval, a presentation snapshot
  only; identity is by id.

**No excerpt content is stored or carried forward.** Later turns receive the
provenance, never the wording. A coherence trigger refuses an answer that is not
Val's, a source in the answer's own conversation, a source whose conversation or
sequence disagrees with the message, a revision number that is not a revision of
that source, and a call from another conversation. Frozen by the standing guards.

Existing answers are not backfilled from logs or inference.

## Downgrade

Refuses once any row exists. Clean on an empty table (CI).

Revision ID: 0019_answer_recall_sources
Revises: 0018_scope_transitions
Create Date: 2026-09-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_answer_recall_sources"
down_revision: str | None = "0018_scope_transitions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "answer_recall_sources"

COHERENCE = """
CREATE OR REPLACE FUNCTION val_answer_recall_source_is_coherent()
RETURNS trigger AS $$
DECLARE
    answer_role text;
    answer_conversation uuid;
    source_conversation uuid;
    source_seq bigint;
    call_conversation uuid;
BEGIN
    SELECT role::text, conversation_id INTO answer_role, answer_conversation
      FROM messages WHERE id = NEW.answer_message_id;
    IF answer_role IS DISTINCT FROM 'val'
       OR answer_conversation IS DISTINCT FROM NEW.conversation_id THEN
        RAISE EXCEPTION 'answer % is not a Val message of conversation %',
            NEW.answer_message_id, NEW.conversation_id;
    END IF;
    SELECT conversation_id, sequence INTO source_conversation, source_seq
      FROM messages WHERE id = NEW.source_message_id;
    IF source_conversation IS DISTINCT FROM NEW.source_conversation_id
       OR source_seq IS DISTINCT FROM NEW.source_sequence THEN
        RAISE EXCEPTION 'source % does not match its stated conversation and sequence',
            NEW.source_message_id;
    END IF;
    IF NEW.source_conversation_id = NEW.conversation_id THEN
        RAISE EXCEPTION 'a House Recall source is never the answer''s own conversation';
    END IF;
    IF NEW.source_revision_number IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM message_revisions r
         WHERE r.message_id = NEW.source_message_id
           AND r.revision_number = NEW.source_revision_number
           AND r.kind = 'revision') THEN
        RAISE EXCEPTION 'source_revision_number % is not a revision of message %',
            NEW.source_revision_number, NEW.source_message_id;
    END IF;
    SELECT conversation_id INTO call_conversation FROM model_calls WHERE id = NEW.model_call_id;
    IF call_conversation IS DISTINCT FROM NEW.conversation_id THEN
        RAISE EXCEPTION 'model call % does not belong to conversation %',
            NEW.model_call_id, NEW.conversation_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


def upgrade() -> None:
    """Create the provenance sidecar, its coherence trigger and its guards."""
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        TABLE,
        sa.Column("id", uuid, nullable=False, server_default=sa.text("uuidv7()")),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("conversation_id", uuid, nullable=False),
        sa.Column("answer_message_id", uuid, nullable=False),
        sa.Column("model_call_id", uuid, nullable=False),
        sa.Column("retrieval_path", sa.Text(), nullable=False),
        sa.Column("rank_position", sa.Integer(), nullable=False),
        sa.Column("source_message_id", uuid, nullable=False),
        sa.Column("source_conversation_id", uuid, nullable=False),
        sa.Column("source_sequence", sa.BigInteger(), nullable=False),
        sa.Column("source_revision_number", sa.Integer(), nullable=True),
        sa.Column("source_project_id", uuid, nullable=True),
        sa.Column("source_sent_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("source_conversation_title", sa.Text(), nullable=False),
        sa.CheckConstraint("retrieval_path = 'house_recall'", name="retrieval_path_ruled"),
        sa.CheckConstraint("rank_position > 0", name="rank_position_positive"),
        sa.CheckConstraint(
            "source_revision_number IS NULL OR source_revision_number > 0",
            name="source_revision_number_positive",
        ),
        sa.PrimaryKeyConstraint("id", name=f"pk_{TABLE}"),
        sa.UniqueConstraint(
            "answer_message_id", "source_message_id", name="uq_answer_recall_sources_answer_source"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], name=f"fk_{TABLE}_conversation_id"
        ),
        sa.ForeignKeyConstraint(
            ["answer_message_id"], ["messages.id"], name=f"fk_{TABLE}_answer_message_id"
        ),
        sa.ForeignKeyConstraint(
            ["model_call_id"], ["model_calls.id"], name=f"fk_{TABLE}_model_call_id"
        ),
        sa.ForeignKeyConstraint(
            ["source_message_id"], ["messages.id"], name=f"fk_{TABLE}_source_message_id"
        ),
        sa.ForeignKeyConstraint(
            ["source_conversation_id"],
            ["conversations.id"],
            name=f"fk_{TABLE}_source_conversation_id",
        ),
        sa.ForeignKeyConstraint(
            ["source_project_id"], ["projects.id"], name=f"fk_{TABLE}_source_project_id"
        ),
    )
    op.create_index(f"ix_{TABLE}_answer_message_id", TABLE, ["answer_message_id"])
    op.execute(COHERENCE)
    op.execute(
        f"CREATE TRIGGER {TABLE}_is_coherent BEFORE INSERT ON {TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION val_answer_recall_source_is_coherent()"
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
    """Refuse once provenance exists; otherwise remove the sidecar."""
    count = op.get_bind().execute(sa.text(f"select count(*) from {TABLE}")).scalar_one()  # noqa: S608
    if count:
        raise RuntimeError(
            f"{TABLE} holds {count} provenance row(s) binding answers to the House records "
            "they drew on; a downgrade would destroy them. Refused."
        )
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_rows_are_evidence ON {TABLE}")
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_forbid_hard_delete ON {TABLE}")
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_is_coherent ON {TABLE}")
    op.execute("DROP FUNCTION IF EXISTS val_answer_recall_source_is_coherent()")
    op.drop_index(f"ix_{TABLE}_answer_message_id", table_name=TABLE)
    op.drop_table(TABLE)
