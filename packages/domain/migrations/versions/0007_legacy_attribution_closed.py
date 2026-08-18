"""Close the legacy-attribution set for good — WP-0.6 corrective round two.

`0006` reserved `legacy_unknown` to history with a check constraint keyed on
`created_at`:

    project_attribution <> 'legacy_unknown' OR created_at < '2026-08-18'

Independent review found that this is not a guarantee, and demonstrated it:

    INSERT ... created_at = '2026-08-15', project_attribution = 'legacy_unknown'
    -> INSERT 0 1

**`created_at` is data, and a direct writer supplies it.** A row inserted today
with a backdated timestamp satisfies the constraint perfectly. The reservation
was therefore a convention wearing a constraint's clothing — which is worse than
an honest convention, because it reads as enforcement.

**The real invariant is about the set, not about time.** `0006` backfilled the
historical rows. That set is now closed: no *new* row may ever acquire
`legacy_unknown`, whatever timestamp it claims, and no existing row may be
changed into one.

A `BEFORE INSERT OR UPDATE` trigger says exactly that, and says it about the
operation rather than about a column the writer controls:

- **INSERT** with `legacy_unknown` — refused, unconditionally.
- **UPDATE** turning a non-legacy row into `legacy_unknown` — refused.
- **UPDATE** of a row that is already `legacy_unknown` and stays so — permitted,
  so the historical rows remain ordinary rows that other columns can be
  corrected on.

The nine historical rows are untouched: a trigger fires on writes, and nothing
here writes to them.

**Why this is not simply a stricter check constraint.** A check constraint sees
one row's values and cannot see whether it is looking at an INSERT or an UPDATE,
nor what the row held before. The distinction being enforced — *this value may
persist but may not be acquired* — is about the transition, so it needs a
trigger. The same reasoning as the persona immutability guard in `0005`.

Revision ID: 0007_legacy_attribution_closed
Revises: 0006_project_attribution
Create Date: 2026-08-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_legacy_attribution_closed"
down_revision: str | None = "0006_project_attribution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUARD = """
CREATE OR REPLACE FUNCTION val_legacy_attribution_is_closed()
RETURNS trigger AS $$
BEGIN
    IF NEW.project_attribution = 'legacy_unknown'
       AND (TG_OP = 'INSERT'
            OR OLD.project_attribution IS DISTINCT FROM 'legacy_unknown') THEN
        RAISE EXCEPTION
            'project_attribution ''legacy_unknown'' is closed to new rows. It '
            'describes model_calls written before project attribution existed, '
            'and migration 0006 has already backfilled that set. Resolve the '
            'exchange, or record it as an explicit no-project decision '
            '(04-layer-0.md WP-0.6). Backdating created_at does not reopen it.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


def upgrade() -> None:
    """Replace a timestamp the writer controls with a rule about the operation."""
    # The constraint went first in `0006` and is dropped here rather than kept
    # alongside: leaving a weaker guard beside a stronger one invites someone to
    # read the weak one and believe it.
    op.execute(
        "ALTER TABLE model_calls DROP CONSTRAINT IF EXISTS "
        "ck_model_calls_legacy_attribution_is_reserved_to_history"
    )
    op.execute(_GUARD)
    op.execute(
        "CREATE TRIGGER model_calls_legacy_attribution_is_closed "
        "BEFORE INSERT OR UPDATE ON model_calls "
        "FOR EACH ROW EXECUTE FUNCTION val_legacy_attribution_is_closed()"
    )


def downgrade() -> None:
    """Put `0006`'s constraint back and remove the trigger.

    Clean: this migration captured nothing. It swapped one form of enforcement
    for a stronger one, so reversing it restores the weaker guard rather than
    losing a record. `0006`'s own downgrade is where the refusal lives, because
    that is the migration whose column holds something irreplaceable.
    """
    op.execute("DROP TRIGGER IF EXISTS model_calls_legacy_attribution_is_closed ON model_calls")
    op.execute("DROP FUNCTION IF EXISTS val_legacy_attribution_is_closed()")
    op.create_check_constraint(
        "legacy_attribution_is_reserved_to_history",
        "model_calls",
        "project_attribution <> 'legacy_unknown' "
        "OR created_at < TIMESTAMPTZ '2026-08-18T00:00:00+00:00'",
    )
