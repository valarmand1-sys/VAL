"""Evidence rows cannot be edited — current-version closure pass, 18 August 2026.

The charter says corrections preserve lineage, audit is append-only, and no
component rewrites its own history (`00-charter.md` §6). Until now most of that
was convention: `messages.content` was never updated because nothing updated it,
and a `model_calls` row was rewriteable evidence the moment anyone chose to.
The closure audit's table-by-table mutation review made the split explicit, and
this migration enforces the half the doctrine owns.

## The mutation matrix this migration enforces

| Table | Kind | UPDATE after this migration |
|---|---|---|
| `messages` | conversation record | **refused** — a message is what was said |
| `model_calls` | call evidence | **refused** — a completed call is evidence |
| `idea_state_changes` | append-only lineage | **refused** — §2.4: lineage is never overwritten |
| `execution_events` | append-only audit | **refused** — "audit is append-only" |
| `deliberations` | append-only capture | **refused** — same doctrine |
| `budget_reservations` | state machine | transitions only; **identity columns refused** |
| `conversations` | lifecycle | `title`, `last_message_at` mutable; `project_id` guarded (`0008`) |
| `personas` | versioned identity | activation mutable; authored columns already guarded (`0005`) |
| `projects` | mutable current-state record | unchanged |
| `ideas` | mutable current-state record (lineage lives in `idea_state_changes`) | unchanged |

Audited before writing: **no application code updates any of the five frozen
tables.** The only writers are INSERTs, so this removes a capability nothing
legitimate was using — which is exactly when to remove one.

## Why UPDATE is refused outright rather than column-by-column

`messages` and `model_calls` have no lifecycle half: every column is a fact
about an event that has finished happening. A column-by-column guard would be a
list somebody has to keep complete; refusing the operation is the doctrine
stated once. A wrong figure in evidence is corrected the way the charter says
everything is corrected — with a new record that supersedes it visibly (the
`0004` accounting view is the worked example) — never by editing the original.

**This supersedes `0007`'s narrower stance for `model_calls`**, which allowed
non-attribution columns of historical rows to be corrected in place ("closed to
new members, not frozen"). The closure ruling is that a completed call is
evidence in all its columns. `0007`'s trigger stays — it still guards INSERT,
which this one does not cover — and fires first on the update path it also
covers (trigger order is alphabetical), so its more specific message survives
for the case it names.

`execution_events` and `deliberations` have no writers until WP-0.8/0.9. They
are frozen now because the charter already calls them append-only; if an
accepted later design needs a field completed after insert (a rejection reason
supplied on prompting, say), that design changes this with its own visible
migration — an explicit decision, not a quiet UPDATE that was always possible.

## Downgrade

Refuses whenever any frozen table holds rows, which the authoritative store
always does. Dropping these guards would make every persisted message and call
silently rewriteable again; that is not a rollback of machinery, it is the
removal of what keeps the history honest. Clean on an empty database (CI).

Revision ID: 0009_evidence_is_immutable
Revises: 0008_conversation_scope_recall
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_evidence_is_immutable"
down_revision: str | None = "0008_conversation_scope_recall"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Every column is a fact about a finished event. UPDATE is the wrong verb.
FROZEN_TABLES = (
    "messages",
    "model_calls",
    "idea_state_changes",
    "execution_events",
    "deliberations",
)

_FROZEN_GUARD = """
CREATE OR REPLACE FUNCTION val_rows_are_evidence()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'UPDATE refused: % rows are evidence and cannot be edited. Corrections '
        'preserve lineage (00-charter.md): supersede with a new record that '
        'names what it corrects, as the 0004 accounting view does — never '
        'rewrite the original. (Current-version closure pass, 18 August 2026.)',
        TG_TABLE_NAME;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql
"""

#: The state machine's transitions change exactly these; nothing may change the
#: rest. `updated_at` moves with every transition and is lifecycle, not identity.
_RESERVATION_IDENTITY = (
    "id",
    "model_config_id",
    "slug",
    "provider",
    "model_identifier",
    "task_type",
    "project_id",
    "max_cost",
    "created_at",
)

_RESERVATION_GUARD = """
CREATE OR REPLACE FUNCTION val_reservation_identity_is_immutable()
RETURNS trigger AS $$
BEGIN
    IF {comparisons} THEN
        RAISE EXCEPTION
            'budget_reservations identity columns are immutable: what was '
            'reserved, for which route, at what maximum, and when are the facts '
            'the state machine transitions AROUND. Only state, settled_cost, '
            'cost_certainty, model_call_id, resolution and updated_at may '
            'change. (Current-version closure pass, 18 August 2026.)';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


def _reservation_guard_sql() -> str:
    comparisons = "\n        OR ".join(
        f"NEW.{column} IS DISTINCT FROM OLD.{column}" for column in _RESERVATION_IDENTITY
    )
    return _RESERVATION_GUARD.format(comparisons=comparisons)


def upgrade() -> None:
    """Freeze the evidence tables; pin the reservation identity columns."""
    op.execute(_FROZEN_GUARD)
    for table in FROZEN_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_rows_are_evidence "
            f"BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION val_rows_are_evidence()"
        )

    op.execute(_reservation_guard_sql())
    op.execute(
        "CREATE TRIGGER budget_reservations_identity_is_immutable "
        "BEFORE UPDATE ON budget_reservations "
        "FOR EACH ROW EXECUTE FUNCTION val_reservation_identity_is_immutable()"
    )


def downgrade() -> None:
    """Remove the guards — refused wherever they are already protecting rows."""
    protected = 0
    for table in (*FROZEN_TABLES, "budget_reservations"):
        protected += int(
            op.get_bind().execute(sa.text(f"select count(*) from {table}")).scalar_one()  # noqa: S608
        )
    if protected:
        raise RuntimeError(
            f"Refusing to downgrade: {protected} row(s) exist across the guarded "
            "tables. Dropping these triggers would make persisted messages, call "
            "records, and lineage silently rewriteable again — the removal of what "
            "keeps the history honest, not a rollback of machinery. This migration "
            "reverses cleanly only on an empty database."
        )

    op.execute(
        "DROP TRIGGER IF EXISTS budget_reservations_identity_is_immutable ON budget_reservations"
    )
    op.execute("DROP FUNCTION IF EXISTS val_reservation_identity_is_immutable()")
    for table in FROZEN_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_rows_are_evidence ON {table}")
    op.execute("DROP FUNCTION IF EXISTS val_rows_are_evidence()")
