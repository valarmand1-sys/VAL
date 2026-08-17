"""Pre-call budget reservations, and truthful cost — 04-layer-0.md §2 amendments.

Two amendments of 17 August 2026, both ordered by Lord Armand after an external
review found the budget guard did not enforce what it claimed to.

**§2.5 — `budget_reservations`.** The ceiling was checked as
`month_to_date_spend < CEILING`, which says nothing about the call being asked
for: at $199.99 of $200 it admitted a call of any size, and the breach was
discovered by reading the record afterwards. Invariant 24 requires the ceiling to
be enforced *before* a call, so the admission decision now has to know what the
proposed call may consume — and what other calls in flight have already claimed.
That is a fact about the whole house, not about one process, so it lives in the
authoritative store. `api` and `worker` each keeping a counter would each observe
the same room and together breach the ceiling; an in-memory lock spans neither.

**§2.2 — `model_calls.cost_certainty`, and cost becoming nullable.** The old
error path wrote `tokens_in = 0, tokens_out = 0, cost = 0` for every failure,
including failures that occurred after the request reached the provider. That is
not an unknown recorded as unknown; it is a false figure recorded as a fact, and
it flowed straight into the month-to-date sum the ceiling was enforced against.
A call that reached the provider consumed input tokens whether or not the
response survived the trip. `cost_certainty = 'unknown'` with NULL figures says
what is actually true, and a pair of check constraints makes the false zero
unwritable rather than merely discouraged.

**Effect on existing rows: none are modified.** `cost_certainty` backfills as
NULL, which means "written before this distinction existed" — the 0002
precedent, approved as standing: NULL rather than a neutral value, because
choosing `known` or `unknown` for an old row would be inventing evidence about
what an earlier implementation could see. The six rows written on 15 August 2026
keep every figure they were written with.

**The downgrade fails loudly once an unknown-cost row exists**, exactly as 0002
does on reaction-only rows. Restoring NOT NULL on `cost` cannot succeed while a
row honestly records that its cost is unknown, and this migration will not
delete the row or fabricate a zero to make the rollback tidy. Destroying capture
records to satisfy a schema change is the outcome Layer 0 exists to prevent. On a
database that has never recorded an unknown cost — CI, or a fresh checkout — the
downgrade is clean.

Revision ID: 0003_budget_reservations
Revises: 0002_reaction_and_ideas
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_budget_reservations"
down_revision: str | None = "0002_reaction_and_ideas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_ENUM_TYPES: dict[str, tuple[str, ...]] = {
    "model_call_cost_certainty": ("known", "unknown"),
    "budget_reservation_state": ("reserved", "settled", "released", "expired"),
}

NEW_TABLES: tuple[str, ...] = ("budget_reservations",)


def _enum(name: str) -> postgresql.ENUM:
    """Reference an already-created type rather than creating it inline."""
    return postgresql.ENUM(*NEW_ENUM_TYPES[name], name=name, create_type=False)


def upgrade() -> None:
    """Add the reservation ledger; make an unknown cost recordable as unknown."""
    for name, values in NEW_ENUM_TYPES.items():
        rendered = ", ".join(f"'{value}'" for value in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({rendered})")

    # --- §2.2: cost certainty ------------------------------------------------

    op.add_column(
        "model_calls",
        sa.Column("cost_certainty", _enum("model_call_cost_certainty"), nullable=True),
    )
    # Existing rows keep every figure they hold; only the column's nullability
    # changes, so an unknown cost becomes recordable from here on.
    op.alter_column("model_calls", "tokens_in", nullable=True)
    op.alter_column("model_calls", "tokens_out", nullable=True)
    op.alter_column("model_calls", "cost", nullable=True)
    op.create_check_constraint(
        "known_cost_is_recorded",
        "model_calls",
        "cost_certainty <> 'known' OR "
        "(cost IS NOT NULL AND tokens_in IS NOT NULL AND tokens_out IS NOT NULL)",
    )
    op.create_check_constraint(
        "unknown_cost_is_not_a_zero",
        "model_calls",
        "cost_certainty <> 'unknown' OR "
        "(cost IS NULL AND tokens_in IS NULL AND tokens_out IS NULL)",
    )

    # --- §2.5: the reservation ledger ----------------------------------------

    op.create_table(
        "budget_reservations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("state", _enum("budget_reservation_state"), nullable=False),
        sa.Column("model_config_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model_identifier", sa.Text(), nullable=False),
        sa.Column(
            "task_type",
            postgresql.ENUM(name="model_call_task_type", create_type=False),
            nullable=False,
        ),
        # Nullable — the same rule as everywhere: "no project" is explicit.
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("max_cost", sa.Numeric(14, 6), nullable=False),
        sa.Column("settled_cost", sa.Numeric(14, 6), nullable=True),
        sa.Column("cost_certainty", _enum("model_call_cost_certainty"), nullable=True),
        sa.Column("model_call_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_budget_reservations"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_budget_reservations_project_id",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["model_call_id"],
            ["model_calls.id"],
            name="fk_budget_reservations_model_call_id",
            ondelete="NO ACTION",
        ),
        sa.CheckConstraint("max_cost >= 0", name="max_cost_non_negative"),
        sa.CheckConstraint(
            "settled_cost IS NULL OR settled_cost >= 0", name="settled_non_negative"
        ),
        sa.CheckConstraint(
            "(state = 'settled') = (settled_cost IS NOT NULL)", name="settled_has_a_cost"
        ),
        sa.CheckConstraint(
            "(state = 'settled') = (cost_certainty IS NOT NULL)", name="settled_has_a_certainty"
        ),
        sa.CheckConstraint(
            "state = 'reserved' OR resolution IS NOT NULL", name="resolved_states_say_why"
        ),
    )
    op.create_index(
        "ix_budget_reservations_state_created_at",
        "budget_reservations",
        ["state", "created_at"],
    )

    # The same no-hard-delete guard every Layer 0 table carries (§2.3). The
    # function already exists from 0001. A reservation is a spending record, and
    # a spending record that can be deleted is a spending record that will be.
    for table in NEW_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_forbid_hard_delete "
            f"BEFORE DELETE OR TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION val_forbid_hard_delete()"
        )


def downgrade() -> None:
    """Remove the amendment. Fails loudly on unknown-cost rows — see above."""
    for table in NEW_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_forbid_hard_delete ON {table}")
    op.drop_index("ix_budget_reservations_state_created_at", table_name="budget_reservations")
    op.drop_table("budget_reservations")

    op.drop_constraint("ck_model_calls_unknown_cost_is_not_a_zero", "model_calls")
    op.drop_constraint("ck_model_calls_known_cost_is_recorded", "model_calls")
    op.drop_column("model_calls", "cost_certainty")
    # Each of these refuses (NOT NULL violation) while any honestly-unknown row
    # exists, by design. The alternative is a rollback that writes zeroes over
    # the record of calls whose cost was never established.
    op.alter_column("model_calls", "cost", nullable=False)
    op.alter_column("model_calls", "tokens_out", nullable=False)
    op.alter_column("model_calls", "tokens_in", nullable=False)

    for name in reversed(list(NEW_ENUM_TYPES)):
        op.execute(f"DROP TYPE {name}")
