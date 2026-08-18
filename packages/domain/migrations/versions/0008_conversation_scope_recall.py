"""Conversation scope is history; recall is project-scoped — WP-0.7.

**Audited before anything was added** (`04-layer-0.md` §24 of the WP-0.7 order),
because most of what WP-0.7 needs the schema already had:

| Requirement | Status before this migration |
|---|---|
| unique `(conversation_id, sequence)` | **present** — `uq_messages_conversation_id_sequence` |
| positive sequence | **already present** — `ck_messages_sequence_positive` |
| history read in sequence order | **already indexed** — by that same constraint's btree |
| every message resolves to a conversation | **already present** — FK, §2.3 |
| no hard delete | **already present** — `val_forbid_hard_delete` triggers |
| conversation scope immutable | **absent** — added here |
| project-scoped retrieval support | **absent** — added here |

So this migration adds two things and no columns.

## 1. A conversation's project is immutable

`conversations.project_id` was writable. Nothing stopped an `UPDATE` moving a
conversation from Project Alpha into Project Beta, and doing so would have
rewritten history rather than recorded a change: every message already in it was
said inside Alpha, and every `model_calls` row already attributed to it says
Alpha. Moving the parent would leave those rows describing a conversation that
now claims it was never Alpha at all.

WP-0.6 settled the doctrine for scope switching — **forward-only**. A switch
starts a new conversation; it never reaches back. This makes that structural for
the conversation row itself, in the same shape as `0005`'s persona guard: a
`BEFORE UPDATE` trigger, because the rule is about the *transition* and a check
constraint cannot see what the row held before.

`title` and `last_message_at` remain updatable. Retitling a conversation changes
a label; rescoping it changes what the record means.

## 2. Retrieval can filter by project before it ranks

WP-0.7 requires *"retrieval is project-scoped. A query in project A returns
nothing from project B."* The isolation is written into the query itself — the
project restriction is a `WHERE` clause, never a post-filter over global results
(see `val_gateway.memory`). Two indexes make that restriction the cheap path
rather than the expensive one:

- **`ix_conversations_project_id`** — resolves *"which conversations belong to
  this project"* directly. Without it, filtering by project meant a sequential
  scan of every conversation in the house, and the temptation to search first
  and filter afterwards grows with the cost of doing it in the right order.
- **`ix_messages_content_fts`** — a GIN index over `to_tsvector('english',
  content)`, which is the retrieval mechanism itself.

**Why full text and not embeddings.** `pgvector` is installed, and WP-0.7's
governing criterion does not ask for semantic retrieval — it asks that retrieval
be project-scoped and that Val recall prior context. Embeddings would require a
new provider, a new egress route for conversation content, an eligibility
decision about sending Protected material to an embedding endpoint, and
embedding-version governance for re-indexing. Each of those is a decision, not
an implementation detail, and pulling them forward because a column type exists
is the standing exclusion in `CLAUDE.md`. Recorded in `VAL_Open_Decisions.md`.

The text search configuration is named explicitly — `'english'`, not
`default` — because an index expression must be immutable, and `to_tsvector` is
only immutable when the configuration is pinned rather than read from a session
setting.

## Downgrade

**Refuses once conversations exist.** Dropping the immutability guard on a
database that holds real conversations would leave their scope silently
rewritable, and scope is what makes every message and every attributed
`model_calls` row mean what it means. That is the same doctrine as `0002`,
`0003`, `0005`, and `0006`: a rollback may remove machinery, never evidence or
the protection that keeps evidence true.

Clean on an empty conversation set, which is CI and any fresh checkout.

Revision ID: 0008_conversation_scope_recall
Revises: 0007_legacy_attribution_closed
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_conversation_scope_recall"
down_revision: str | None = "0007_legacy_attribution_closed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCOPE_GUARD = """
CREATE OR REPLACE FUNCTION val_conversation_scope_is_immutable()
RETURNS trigger AS $$
BEGIN
    IF NEW.project_id IS DISTINCT FROM OLD.project_id THEN
        RAISE EXCEPTION
            'conversations.project_id is immutable. This conversation was held '
            'in one scope and its messages and model_calls rows are attributed '
            'to that scope; moving it would rewrite what they mean. Switching '
            'project starts a new conversation (04-layer-0.md WP-0.6, '
            'forward-only). Title and last_message_at may still be updated.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

#: `english` is named rather than inherited from `default_text_search_config`:
#: an index expression must be immutable, and `to_tsvector(regconfig, text)` is
#: immutable only when the configuration is fixed at definition time.
CONTENT_FTS = "to_tsvector('english', content)"


def upgrade() -> None:
    """Make conversation scope history, and make the project filter cheap."""
    op.execute(SCOPE_GUARD)
    op.execute(
        "CREATE TRIGGER conversations_scope_is_immutable "
        "BEFORE UPDATE ON conversations "
        "FOR EACH ROW EXECUTE FUNCTION val_conversation_scope_is_immutable()"
    )

    op.create_index("ix_conversations_project_id", "conversations", ["project_id"])
    op.execute(f"CREATE INDEX ix_messages_content_fts ON messages USING gin ({CONTENT_FTS})")


def downgrade() -> None:
    """Remove the recall indexes — and refuse to unprotect real conversations.

    **Clean while no conversation exists.** There is then no scope for the guard
    to be protecting, so dropping it loses machinery and no evidence.

    **Refuses once conversations have been held.** Their `project_id` is what
    every message in them and every `model_calls` row attributed to them relies
    on being true. Leaving that column silently rewritable is not a rollback of
    a feature; it is the removal of the thing that keeps the history honest.
    """
    held = op.get_bind().execute(sa.text("select count(*) from conversations")).scalar_one()
    if held:
        raise RuntimeError(
            f"Refusing to downgrade: {held} conversation(s) exist. Dropping "
            "`conversations_scope_is_immutable` would make their project_id writable "
            "again, and their messages and attributed model_calls rows all depend on "
            "that scope being the one they were recorded under. Retire those "
            "conversations deliberately first; this migration will not unprotect them."
        )

    op.execute("DROP INDEX IF EXISTS ix_messages_content_fts")
    op.drop_index("ix_conversations_project_id", table_name="conversations")
    op.execute("DROP TRIGGER IF EXISTS conversations_scope_is_immutable ON conversations")
    op.execute("DROP FUNCTION IF EXISTS val_conversation_scope_is_immutable()")
