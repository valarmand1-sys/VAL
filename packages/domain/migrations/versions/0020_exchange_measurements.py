"""Exchange identity on reservations, and per-call measurement — ruling of 13 September 2026.

The cognition-cost diagnostic of 13 September 2026 found that a user exchange
could be reassembled only through `classifications.model_call_ids`,
`blind_positions.model_call_id` and reservation timing: classification, strip
and blind-position calls carry no conversation or message, and the strip call
has no durable link at all. It also found that time to first text, visible
output size and reasoning presence were not recorded, so hidden reasoning had
to be inferred from character counts.

## What is added

**`budget_reservations.exchange_conversation_id` / `exchange_message_id`** —
nullable, both or neither: the conversation and the persisted user message
whose exchange the reserved call belongs to. NULL means the call belongs to no
user exchange (a harness, a title) or was reserved before this migration;
existing rows are not backfilled. Both are identity, so the standing
reservation identity guard (`0009`) is widened to pin them.

**`model_call_measurements`** — an append-only sidecar, at most one row per
`model_calls` row, written in the same transaction as the call it describes:

- `exchange_conversation_id`, `exchange_message_id` — the exchange, both or
  neither;
- `streamed` — whether the call ran as a stream;
- `first_text_ms` — milliseconds from the start of the provider call to the
  first non-empty generated-text delta at the Val Core boundary; NULL when the
  call was not streamed or produced no text;
- `text_output_chars` — characters of generated text the provider returned
  (never thinking); NULL when no response arrived;
- `reasoning_present` — whether the provider's response carried reasoning or
  thinking output, where the provider exposes that fact; NULL otherwise;
- `reasoning_output_tokens` — reasoning tokens the provider reported inside its
  output count, where it reports them; NULL otherwise, never inferred;
- `provider_cached_input_tokens`, `provider_cache_write_tokens` — input the
  provider reported reading from and writing to its prompt cache, as reported,
  whether or not this house requested caching; NULL when not reported.

Latency, token totals and cost stay on `model_calls`; the priced cache split
stays in `model_call_cache_usage`. **No column on `model_calls` changes.**

## Downgrade

Refuses once any measurement row or any exchange-attributed reservation exists.
Clean on an empty database (CI).

Revision ID: 0020_exchange_measurements
Revises: 0019_answer_recall_sources
Create Date: 2026-09-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_exchange_measurements"
down_revision: str | None = "0019_answer_recall_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "model_call_measurements"

_IDENTITY_BEFORE = (
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
_IDENTITY_AFTER = (*_IDENTITY_BEFORE, "exchange_conversation_id", "exchange_message_id")

_GUARD = """
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


def _guard(columns: Sequence[str]) -> str:
    comparisons = "\n        OR ".join(
        f"NEW.{column} IS DISTINCT FROM OLD.{column}" for column in columns
    )
    return _GUARD.format(comparisons=comparisons)


def upgrade() -> None:
    """Add exchange identity to reservations and create the measurement sidecar."""
    uuid = postgresql.UUID(as_uuid=True)
    op.add_column("budget_reservations", sa.Column("exchange_conversation_id", uuid, nullable=True))
    op.add_column("budget_reservations", sa.Column("exchange_message_id", uuid, nullable=True))
    op.create_foreign_key(
        "fk_budget_reservations_exchange_conversation_id",
        "budget_reservations",
        "conversations",
        ["exchange_conversation_id"],
        ["id"],
        ondelete="NO ACTION",
    )
    op.create_foreign_key(
        "fk_budget_reservations_exchange_message_id",
        "budget_reservations",
        "messages",
        ["exchange_message_id"],
        ["id"],
        ondelete="NO ACTION",
    )
    op.create_check_constraint(
        "exchange_both_or_neither",
        "budget_reservations",
        "(exchange_conversation_id IS NULL) = (exchange_message_id IS NULL)",
    )
    op.create_index(
        "ix_budget_reservations_exchange_message_id",
        "budget_reservations",
        ["exchange_message_id"],
    )
    op.execute(_guard(_IDENTITY_AFTER))

    op.create_table(
        TABLE,
        sa.Column("id", uuid, nullable=False, server_default=sa.text("uuidv7()")),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("model_call_id", uuid, nullable=False),
        sa.Column("exchange_conversation_id", uuid, nullable=True),
        sa.Column("exchange_message_id", uuid, nullable=True),
        sa.Column("streamed", sa.Boolean(), nullable=False),
        sa.Column("first_text_ms", sa.Integer(), nullable=True),
        sa.Column("text_output_chars", sa.Integer(), nullable=True),
        sa.Column("reasoning_present", sa.Boolean(), nullable=True),
        sa.Column("reasoning_output_tokens", sa.BigInteger(), nullable=True),
        sa.Column("provider_cached_input_tokens", sa.BigInteger(), nullable=True),
        sa.Column("provider_cache_write_tokens", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "(exchange_conversation_id IS NULL) = (exchange_message_id IS NULL)",
            name="exchange_both_or_neither",
        ),
        sa.CheckConstraint(
            "first_text_ms IS NULL OR (streamed AND first_text_ms >= 0)",
            name="first_text_only_when_streamed",
        ),
        sa.CheckConstraint(
            "(text_output_chars IS NULL OR text_output_chars >= 0) AND "
            "(reasoning_output_tokens IS NULL OR reasoning_output_tokens >= 0) AND "
            "(provider_cached_input_tokens IS NULL OR provider_cached_input_tokens >= 0) AND "
            "(provider_cache_write_tokens IS NULL OR provider_cache_write_tokens >= 0)",
            name="measurements_non_negative",
        ),
        sa.PrimaryKeyConstraint("id", name=f"pk_{TABLE}"),
        sa.UniqueConstraint("model_call_id", name=f"uq_{TABLE}_model_call_id"),
        sa.ForeignKeyConstraint(
            ["model_call_id"], ["model_calls.id"], name=f"fk_{TABLE}_model_call_id"
        ),
        sa.ForeignKeyConstraint(
            ["exchange_conversation_id"],
            ["conversations.id"],
            name=f"fk_{TABLE}_exchange_conversation_id",
        ),
        sa.ForeignKeyConstraint(
            ["exchange_message_id"], ["messages.id"], name=f"fk_{TABLE}_exchange_message_id"
        ),
    )
    op.create_index(f"ix_{TABLE}_exchange_message_id", TABLE, ["exchange_message_id"])
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
    """Refuse once measurement or exchange attribution exists; otherwise remove both."""
    bind = op.get_bind()
    measured = bind.execute(sa.text(f"select count(*) from {TABLE}")).scalar_one()  # noqa: S608
    attributed = bind.execute(
        sa.text("select count(*) from budget_reservations where exchange_message_id is not null")
    ).scalar_one()
    if measured or attributed:
        raise RuntimeError(
            f"{measured} measurement row(s) and {attributed} exchange-attributed reservation(s) "
            "exist; a downgrade would destroy that evidence. Refused."
        )
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_rows_are_evidence ON {TABLE}")
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_forbid_hard_delete ON {TABLE}")
    op.drop_index(f"ix_{TABLE}_exchange_message_id", table_name=TABLE)
    op.drop_table(TABLE)
    op.execute(_guard(_IDENTITY_BEFORE))
    op.drop_index("ix_budget_reservations_exchange_message_id", table_name="budget_reservations")
    op.drop_constraint("exchange_both_or_neither", "budget_reservations", type_="check")
    op.drop_constraint(
        "fk_budget_reservations_exchange_message_id", "budget_reservations", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_budget_reservations_exchange_conversation_id",
        "budget_reservations",
        type_="foreignkey",
    )
    op.drop_column("budget_reservations", "exchange_message_id")
    op.drop_column("budget_reservations", "exchange_conversation_id")
