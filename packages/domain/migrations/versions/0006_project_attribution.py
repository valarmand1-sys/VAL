"""What a stored project_id means — §2.2 amendment, WP-0.6 corrective round.

Independent source review of `VAL_Source_Snapshot_8cc0413.zip` found that
WP-0.6's central claim was not globally true. It said *"`project_id IS NULL` is
exactly the explicit-none set"*, and that held for everything the resolver wrote
and failed for the table as a whole, in two separate ways:

1. **Nine rows predate WP-0.6.** Six were written on 15 August 2026 during
   WP-0.4's live verification, before `projects` had a single row. Three were
   written on 17 August during WP-0.5's persona work, before project scope
   existed as a concept. All nine carry NULL, and **not one of them is a
   decision** — nobody chose to work outside every project, because there was
   nothing to choose between.
2. **The generic `GatewayRequest` still defaulted `project_id` to `None`.** Any
   caller could write a fresh, semantically empty NULL without deciding
   anything, which is the same defect the corrected `converse` signature had
   already removed from the conversational path.

**A NULL cannot carry two meanings, so the meaning is stored beside it.**

| `project_attribution` | `project_id` | Means |
|---|---|---|
| `resolved` | a real id | Deterministically identified |
| `explicit_none` | NULL | Somebody decided this is outside every project |
| `legacy_unknown` | NULL | Written before the distinction existed. **Nobody decided.** |

**Why a column and not a view.** `0004` used a view for the fabricated zero
costs, and that was right there: the rule identifying them was *exact* — the
superseded code wrote `0/0/$0` on every error, unconditionally — so it could be
computed from data already present. **No such rule exists here.** Distinguishing
a deliberate no-project decision from a pre-WP-0.6 NULL requires knowing *when
the concept existed*, and a view could express that only as a date comparison —
a rule nobody reading a single row could apply, and one that would silently
misclassify any future row that happened to be backdated. The fact is not
derivable, so it is recorded.

**The backfill is exact, not a guess.** Every existing NULL predates project
scope entirely; every existing non-NULL was written by the corrected WP-0.6 path
and is a real resolution. So:

    project_id IS NOT NULL  ->  'resolved'
    project_id IS NULL      ->  'legacy_unknown'

**No `project_id` is rewritten.** Not one. The nine stay NULL; the two stay
pointed at Project Alpha. Lineage is untouched — what is added is a statement
about what was already there, which is the difference between annotating history
and editing it (`00-charter.md` invariant 14).

**`legacy_unknown` is reserved to history by constraint**, not by convention.
`ck_model_calls_legacy_attribution_is_reserved_to_history` refuses it on any row
created from 18 August 2026 onward, the same shape of guarantee that
`certainty_required_after_the_amendment` gives `cost_certainty`. Without it the
value would become exactly what it must never be: a convenient way for new code
to avoid deciding scope.

**Downgrade is clean only while nothing irreplaceable has been captured, and it
checks.** *Corrected 18 August 2026 after independent review.* The original
claim here — that this column "adds interpretation but stores no fact of its
own" — is true exactly until the first `explicit_none` row is written. After
that it stores something nothing else does: a NULL `project_id` marked
`explicit_none` and a NULL marked `legacy_unknown` are **identical once the
column is gone**, and no rule can tell them apart afterwards. That is a captured
decision destroyed by a rollback, which is the thing `0002`, `0003`, and `0005`
all refuse to do. So this refuses too, once there is something to lose.

Revision ID: 0006_project_attribution
Revises: 0005_persona_provenance
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from val_domain.migrations_support import ACCOUNTED_VIEW

revision: str = "0006_project_attribution"
down_revision: str | None = "0005_persona_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ATTRIBUTION_ENUM = "model_call_project_attribution"
ATTRIBUTION_VALUES = ("resolved", "explicit_none", "legacy_unknown")

#: From this instant, every row must state a real attribution. Rows written
#: before it are the historical set, and `legacy_unknown` belongs only to them.
ATTRIBUTION_REQUIRED_FROM = "2026-08-18T00:00:00+00:00"


def upgrade() -> None:
    """Record what each project_id means. Rewrite none of them."""
    rendered = ", ".join(f"'{value}'" for value in ATTRIBUTION_VALUES)
    op.execute(f"CREATE TYPE {ATTRIBUTION_ENUM} AS ENUM ({rendered})")

    # Added nullable, backfilled by the exact rule above, then made NOT NULL.
    # Three steps rather than one so the backfill is visible as its own act
    # rather than hidden inside a server_default nobody reads.
    op.add_column(
        "model_calls",
        sa.Column(
            "project_attribution",
            sa.Enum(*ATTRIBUTION_VALUES, name=ATTRIBUTION_ENUM, create_type=False),
            nullable=True,
        ),
    )
    # Written out rather than interpolated. Nothing here comes from input, and a
    # literal is one less thing for a reader to check when the question is
    # "which rows did this touch, and what did it write".
    op.execute(
        "UPDATE model_calls SET project_attribution = CASE "
        "WHEN project_id IS NOT NULL "
        "THEN 'resolved'::model_call_project_attribution "
        "ELSE 'legacy_unknown'::model_call_project_attribution END"
    )
    op.alter_column("model_calls", "project_attribution", nullable=False)

    op.create_check_constraint(
        "resolved_attribution_has_a_project",
        "model_calls",
        "(project_attribution = 'resolved') = (project_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "legacy_attribution_is_reserved_to_history",
        "model_calls",
        "project_attribution <> 'legacy_unknown' "
        f"OR created_at < TIMESTAMPTZ '{ATTRIBUTION_REQUIRED_FROM}'",
    )

    # `model_calls_accounted` selects `mc.*`, which expanded to the columns that
    # existed when it was last created. A view that silently stops exposing a
    # base column becomes a second, lesser record — and this is the column a
    # future reader most needs, since it is the one that stops a legacy NULL
    # being read as a deliberate no-project decision.
    op.execute("DROP VIEW model_calls_accounted")
    op.execute(ACCOUNTED_VIEW)


def downgrade() -> None:
    """Remove the annotation — and refuse once it holds something irreplaceable.

    **Clean on a database with no `explicit_none` row**, which is CI and any
    fresh checkout: there, every attribution is derivable again from
    `project_id` alone, so dropping the column loses an interpretation and no
    evidence.

    **Refuses once a deliberate no-project decision has been recorded.** Such a
    row is `project_id` NULL with `explicit_none`; a legacy row is `project_id`
    NULL with `legacy_unknown`. Drop the column and they become the same row,
    permanently — the decision is not recoverable from anything that remains.
    Rolling that back is destroying a captured fact, and it is refused for the
    same reason `0002` refuses on reaction-only rows and `0005` on seeded
    personas.

    Nothing is deleted, rewritten, or coerced to make the downgrade succeed.
    """
    decisions = (
        op.get_bind()
        .execute(
            sa.text("select count(*) from model_calls where project_attribution = 'explicit_none'")
        )
        .scalar_one()
    )
    if decisions:
        raise RuntimeError(
            f"Refusing to downgrade: {decisions} model_calls row(s) record a deliberate "
            "no-project decision (project_id NULL, project_attribution 'explicit_none'). "
            "Dropping project_attribution would make them indistinguishable from the "
            "legacy rows that carry NULL because they predate the distinction, and "
            "nothing left in the table could tell them apart afterwards. Retire those "
            "records deliberately first; this migration will not coerce or delete them."
        )

    op.execute("DROP VIEW model_calls_accounted")

    # `0007` may have replaced this constraint with a trigger, so the drop is
    # conditional: a downgrade must not fail on the absence of something a later
    # migration legitimately removed.
    op.execute(
        "ALTER TABLE model_calls DROP CONSTRAINT IF EXISTS "
        "ck_model_calls_legacy_attribution_is_reserved_to_history"
    )
    op.drop_constraint("ck_model_calls_resolved_attribution_has_a_project", "model_calls")
    op.drop_column("model_calls", "project_attribution")

    op.execute(ACCOUNTED_VIEW)
    op.execute(f"DROP TYPE {ATTRIBUTION_ENUM}")
