"""Prompt-cache evidence per call — ruling of 8 September 2026.

Prompt caching is enabled on the partner route's stable prefix (the persona,
whole). The ruling requires enough persisted evidence to distinguish a hit, a
miss, a cache creation, the cached and uncached token counts, and the actual
billed cost — and `model_calls` keeps its shape: `tokens_in` becomes the total
input the provider processed (uncached plus cached), and `cost` the total
billed at call time, exactly as before. The split lives here, in a sidecar row
written in the same transaction as the call it describes.

## What is added

**`model_call_cache_usage`** — at most one row per `model_calls` row, present
exactly when caching was requested on that call and the provider reported
usage: the lifetime requested, the four usage figures as the provider
reported them, the outcome, and the four billed components at the
configuration's verified rates — computed at call time, never recomputed.

Frozen by the standing guards `val_forbid_hard_delete` (`0001`) and
`val_rows_are_evidence` (`0009`). No column on `model_calls` changes.

## Downgrade

Refuses once any row exists. Clean on an empty database (CI).

Revision ID: 0015_model_call_cache_usage
Revises: 0014_classification_review
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_model_call_cache_usage"
down_revision: str | None = "0014_classification_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "model_call_cache_usage"


def upgrade() -> None:
    """Create the evidence table and freeze it."""
    op.create_table(
        TABLE,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("model_call_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_ttl", sa.Text(), nullable=False),
        sa.Column("uncached_input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cache_write_5m_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cache_write_1h_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cache_read_tokens", sa.BigInteger(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("cost_uncached", sa.Numeric(14, 6), nullable=False),
        sa.Column("cost_cache_write", sa.Numeric(14, 6), nullable=False),
        sa.Column("cost_cache_read", sa.Numeric(14, 6), nullable=False),
        sa.Column("cost_output", sa.Numeric(14, 6), nullable=False),
        sa.CheckConstraint("requested_ttl in ('5m', '1h')", name="requested_ttl_documented"),
        sa.CheckConstraint(
            "outcome in ('hit', 'created', 'hit_and_created', 'not_cached')",
            name="outcome_named",
        ),
        sa.CheckConstraint(
            "uncached_input_tokens >= 0 and cache_write_5m_tokens >= 0 and "
            "cache_write_1h_tokens >= 0 and cache_read_tokens >= 0",
            name="token_counts_non_negative",
        ),
        sa.CheckConstraint(
            "(outcome = 'hit') = (cache_read_tokens > 0 and cache_write_5m_tokens = 0 "
            "and cache_write_1h_tokens = 0)",
            name="hit_means_read_only",
        ),
        sa.CheckConstraint(
            "(outcome = 'not_cached') = (cache_read_tokens = 0 and cache_write_5m_tokens = 0 "
            "and cache_write_1h_tokens = 0)",
            name="not_cached_means_nothing_cached",
        ),
        sa.PrimaryKeyConstraint("id", name=f"pk_{TABLE}"),
        sa.UniqueConstraint("model_call_id", name=f"uq_{TABLE}_model_call_id"),
        sa.ForeignKeyConstraint(
            ["model_call_id"],
            ["model_calls.id"],
            name=f"fk_{TABLE}_model_call_id",
            ondelete="NO ACTION",
        ),
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
    """Refuse once evidence exists; otherwise remove the table."""
    connection = op.get_bind()
    count = connection.execute(sa.text(f"select count(*) from {TABLE}")).scalar_one()  # noqa: S608
    if count:
        raise RuntimeError(
            f"{TABLE} holds {count} evidence row(s); a downgrade would destroy them. Refused."
        )
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_rows_are_evidence ON {TABLE}")
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_forbid_hard_delete ON {TABLE}")
    op.drop_table(TABLE)
