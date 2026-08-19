"""The provider's terminal state is durable evidence — independent-review correction.

The closure pass introduced the provider-neutral terminal-state contract
(COMPLETE / REFUSED / TRUNCATED / FILTERED / UNKNOWN) — and left it living only
in runtime response objects. `model_calls.status` collapses it: a TRUNCATED
call writes `ok`, exactly as a COMPLETE one does, so after a restart the
evidence row cannot say whether the provider finished speaking — even though
that distinction is what decides whether the text was allowed into Val's
history as her message. "The runtime caller knew it" is not reconstruction.

## What is added

`model_calls.terminal_state` — a new enum column:

| Value | Meaning |
|---|---|
| `complete` | the provider finished naturally |
| `refused` | the model's deliberate refusal (its complete utterance) |
| `truncated` | the output cap cut generation off |
| `filtered` | the provider's content filter cut generation off |
| `unknown` | a stop state the adapter did not recognise; failed closed |
| `failed` | no provider terminal state exists — the call errored in transit |

`failed` is the durable name for the path `_settle_unknown` records: a
provider exception or timeout produced no response object, so there is no
provider terminal state to record, and inventing one would be guessing.

## Historical rows stay NULL, and NULL is closed to new rows

The 40 existing rows predate the terminal-state contract. Their exact terminal
state was never captured and **is not guessed**: a `status = ok` row from July
might have been truncated for all this column knows, and writing `complete`
onto it would manufacture evidence. They stay NULL — the same legacy shape as
`cost_certainty` (`0003`) and `project_attribution` (`0006`).

NULL is then closed by trigger, the `0007` pattern: every row inserted after
this migration must state its terminal state. A trigger rather than NOT NULL
because NOT NULL would force a backfill value onto history, and a trigger
rather than a `created_at` cutoff because a timestamp is caller-supplied data
(the exact bypass `0007` closed for attribution).

## The accounted view

`model_calls_accounted` selects `mc.*`, so it is dropped and recreated — the
`0006` lesson: a view that silently stops exposing a base column becomes a
second, lesser record.

## Downgrade

Refuses once any row carries a non-NULL terminal state: dropping the column
would collapse TRUNCATED and COMPLETE back into `status = ok`, destroying the
captured distinction that decides whether a reply was ever an utterance. Clean
while no terminal state has been captured (fresh checkout, CI).

Revision ID: 0010_terminal_state_is_evidence
Revises: 0009_evidence_is_immutable
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from val_domain.migrations_support import ACCOUNTED_VIEW

revision: str = "0010_terminal_state_is_evidence"
down_revision: str | None = "0009_evidence_is_immutable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TERMINAL_ENUM = "model_call_terminal_state"
TERMINAL_VALUES = ("complete", "refused", "truncated", "filtered", "unknown", "failed")

_REQUIRED_GUARD = """
CREATE OR REPLACE FUNCTION val_terminal_state_is_required()
RETURNS trigger AS $$
BEGIN
    IF NEW.terminal_state IS NULL THEN
        RAISE EXCEPTION
            'model_calls.terminal_state is required on every new row: how the '
            'provider call actually ended is evidence, and it decides whether '
            'the text was ever an utterance. NULL is reserved for the rows '
            'that predate the terminal-state contract (current-version '
            'closure, independent-review correction, 18 August 2026).';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


def upgrade() -> None:
    """Record how every future call actually ended; leave history honestly NULL."""
    rendered = ", ".join(f"'{value}'" for value in TERMINAL_VALUES)
    op.execute(f"CREATE TYPE {TERMINAL_ENUM} AS ENUM ({rendered})")

    op.add_column(
        "model_calls",
        sa.Column(
            "terminal_state",
            sa.Enum(*TERMINAL_VALUES, name=TERMINAL_ENUM, create_type=False),
            nullable=True,
        ),
    )
    # No backfill, deliberately: the historical rows' terminal states were never
    # captured and are not guessed. NULL means exactly "not captured".

    op.execute(_REQUIRED_GUARD)
    # 0009 froze model_calls against UPDATE; this trigger guards INSERT, which
    # 0009 does not touch. Adding the column itself is DDL, not an UPDATE.
    op.execute(
        "CREATE TRIGGER model_calls_terminal_state_is_required "
        "BEFORE INSERT ON model_calls "
        "FOR EACH ROW EXECUTE FUNCTION val_terminal_state_is_required()"
    )

    op.execute("DROP VIEW model_calls_accounted")
    op.execute(ACCOUNTED_VIEW)


def downgrade() -> None:
    """Remove the column — refused once it holds captured evidence."""
    captured = (
        op.get_bind()
        .execute(sa.text("select count(*) from model_calls where terminal_state is not null"))
        .scalar_one()
    )
    if captured:
        raise RuntimeError(
            f"Refusing to downgrade: {captured} model_calls row(s) have a captured "
            "terminal state. Dropping the column would collapse truncated and "
            "complete back into status='ok', destroying the recorded distinction "
            "that decides whether a reply was ever Val's utterance. This migration "
            "reverses cleanly only before any terminal state has been captured."
        )

    op.execute("DROP TRIGGER IF EXISTS model_calls_terminal_state_is_required ON model_calls")
    op.execute("DROP FUNCTION IF EXISTS val_terminal_state_is_required()")
    op.execute("DROP VIEW model_calls_accounted")
    op.drop_column("model_calls", "terminal_state")
    op.execute(ACCOUNTED_VIEW)
    op.execute(f"DROP TYPE {TERMINAL_ENUM}")
