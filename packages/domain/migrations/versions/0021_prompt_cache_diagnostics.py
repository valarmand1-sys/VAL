"""Prompt-cache diagnostics on the measurement sidecar — ruling of 15 September 2026.

Five production GPT-5.6 Sol calls on 15 September 2026 reported zero cache
reads — three of them inside the documented 30-minute minimum lifetime, and
contrary to the persona reads observed on 41 of 42 calls the day before under
the same code, persona and configuration. The record could establish the
misses and exclude every in-house cause it held (no code change, no persona
change, no retry, the ruled assembly order) but not the provider-side reason,
because nothing about the request's cache bucketing or the provider's account
of it was recorded.

## What is added

Two nullable columns on `model_call_measurements`; no row is backfilled and no
other table changes:

- `prompt_cache_key` — the stable prompt-cache key the request carried, where
  the provider supports one; NULL otherwise.
- `cache_diagnostics` (JSONB) — what was requested of the prompt cache and what
  the provider reported back about it, verbatim: the requested key and options,
  the provider's echo of the key, mode and lifetime it applied, the read/write
  token split, and any miss reason or reusable/missed counts a provider
  returns (none in the pinned OpenAI client 3.1.0; recorded under
  `reported.prompt_cache_diagnostics` if a response ever carries them). NULL
  where the provider or the call mode exposes nothing of the kind.

Cost settlement, the priced cache split (`model_call_cache_usage`) and the
existing measurement columns are unchanged. The sidecar remains append-only.

Revision ID: 0021_prompt_cache_diagnostics
Revises: 0020_exchange_measurements
Create Date: 2026-09-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_prompt_cache_diagnostics"
down_revision: str | None = "0020_exchange_measurements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "model_call_measurements"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("prompt_cache_key", sa.Text(), nullable=True))
    op.add_column(
        TABLE,
        sa.Column("cache_diagnostics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column(TABLE, "cache_diagnostics")
    op.drop_column(TABLE, "prompt_cache_key")
