"""Supersede the fabricated zero costs without touching them — §2.2 amendment.

Five `model_calls` rows written on 15 August 2026 carry `tokens_in = 0`,
`tokens_out = 0`, `cost = 0.000000`, `status = 'error'`, and a NULL
`cost_certainty`. Migration `0003` correctly left them alone: rewriting history
to match a better present is what `00-charter.md` invariant 14 forbids.

**But leaving them alone is not the same as leaving them readable.** As they
stand, `sum(cost)` counts them as five confirmed free calls, and any future
reader — an accounting view, Layer 5 distillation, or Lord Armand running a
query by hand — has no way to know the zero was fabricated. A false figure that
nobody can identify as false is worse than a missing one.

**The correction, and why it needs no new state.** The superseded implementation
wrote `0, 0, 0` on *every* `GatewayError`, unconditionally, and wrote real usage
on every success and refusal. The rule that identifies the fabricated rows is
therefore **exact rather than heuristic**:

    cost_certainty IS NULL AND status = 'error'   ->  cost is UNKNOWN
    cost_certainty IS NULL AND status <> 'error'  ->  cost is KNOWN

Two things follow, and together they are the whole mechanism:

1. **A check constraint bounds the legacy set permanently.** No row created from
   this migration onward may omit its cost certainty. NULL certainty therefore
   means *written before 17 August 2026* and can never mean anything else, so
   the rule above cannot silently widen to cover rows it was not written for.
2. **A view applies the rule in one place.** `model_calls_accounted` projects
   every column of `model_calls` plus a non-null `effective_cost_certainty`, an
   `accounted_cost` that is NULL when the cost is not known, and a per-row
   `accounting_note` saying so in words. SQL, Python, and Layer 5 all read the
   same interpretation because there is only one.

**Nothing is mutated and nothing is deleted.** `model_calls` is untouched by
this migration — no UPDATE, no DELETE, not one row rewritten.

**Both halves stay reconstructable, which was the requirement.** The original
evidence is the base table, exactly as written on 15 August, `cost = 0.000000`
still there to be read. The correction is this migration file: dated,
attributable, in git, and append-only in the way migrations are. `SELECT * FROM
model_calls` gives you what was recorded; `SELECT * FROM model_calls_accounted`
gives you what it means. Neither is derived from the other's absence.

**Why a view and not an eleventh table.** A correction table would record the
same fact this rule computes, but it would add state that must itself be kept
correct, and it would put a row-per-correction in a layer whose scope discipline
is the point. The view adds no state at all: it cannot drift from the base table
because it *is* the base table, read through a rule. `04-layer-0.md` §2.2 names
it, so it is not slipping in unnamed.

Revision ID: 0004_supersede_zero_costs
Revises: 0003_budget_reservations
Create Date: 2026-08-17
"""

from collections.abc import Sequence

from alembic import op

from val_domain.migrations_support import ACCOUNTED_VIEW

revision: str = "0004_supersede_zero_costs"
down_revision: str | None = "0003_budget_reservations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The instant from which stating cost certainty became mandatory. Every row
#: written before it predates the distinction; every row after it must state it.
#: Existing rows were written 15 August 2026 and satisfy this as they stand.
CERTAINTY_REQUIRED_FROM = "2026-08-17T00:00:00+00:00"


def upgrade() -> None:
    """Bound the legacy set, and publish the rule that reads it correctly."""
    # No row from here on may leave its cost certainty unstated. This is what
    # makes "NULL certainty" mean exactly one thing forever.
    op.create_check_constraint(
        "certainty_required_after_the_amendment",
        "model_calls",
        f"cost_certainty IS NOT NULL OR created_at < TIMESTAMPTZ '{CERTAINTY_REQUIRED_FROM}'",
    )
    op.execute(ACCOUNTED_VIEW)


def downgrade() -> None:
    """Remove the view and the constraint. No row is affected either way.

    This downgrade is clean against real data, unlike `0002` and `0003`. It has
    nothing to destroy: it created no state, so removing it destroys none. The
    fabricated zeroes are still in `model_calls` afterwards, exactly as they
    were before this migration and exactly as they were on 15 August — which is
    the point of having corrected them this way rather than in place.
    """
    op.execute("DROP VIEW IF EXISTS model_calls_accounted")
    op.drop_constraint("ck_model_calls_certainty_required_after_the_amendment", "model_calls")
