"""Runtime provenance on the measurement sidecar — ruling of 16 September 2026.

The first local cognition provider (LM Studio on the loopback interface) is
registered for evaluation only. A local runtime can answer with a model other
than the one requested (just-in-time loading keeps only the last loaded
model), can load a model at a smaller context length than the model supports,
and reports its own timing figures. None of that was recordable.

## What is added

Two nullable columns on `model_call_measurements`; no row is backfilled and no
other table changes:

- `provider_reported_model` — the model identifier the provider's own response
  named. An adapter refuses a response naming a different model than was
  requested, so on a recorded call this equals the requested identifier, or is
  NULL where the provider names none.
- `runtime_diagnostics` (JSONB) — the entry's hosting axis (`cloud` / `local`)
  and whatever the runtime reported about itself and the call, verbatim: for a
  local server, the loaded model and its context length, and the server's own
  prefill and generation figures where it returns them. NULL where nothing of
  the kind is exposed; never inferred.

**`model_calls.known_cost_is_recorded`, widened by one named clause.** The
0003 guard — a *known* cost requires recorded tokens — is the database's
protection against a fabricated zero. Ruling 3 of 16 September 2026: an
unmetered local route's provider/API cost is a known $0 whether or not the
runtime reported token usage, because token telemetry and monetary certainty
are separate facts. The clause admits exactly `cost = 0 AND provider =
'lmstudio'`; every metered provider keeps the original guard, and a second
local provider is added to the clause by its own ruling, visibly. No other
column of `model_calls` changes.

Cost settlement, the priced cache split and the existing measurement columns
are otherwise unchanged. The sidecar remains append-only.

Revision ID: 0022_runtime_provenance
Revises: 0021_prompt_cache_diagnostics
Create Date: 2026-09-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_runtime_provenance"
down_revision: str | None = "0021_prompt_cache_diagnostics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "model_call_measurements"


KNOWN_COST_BEFORE = (
    "cost_certainty <> 'known' OR "
    "(cost IS NOT NULL AND tokens_in IS NOT NULL AND tokens_out IS NOT NULL)"
)
KNOWN_COST_AFTER = (
    "cost_certainty <> 'known' OR "
    "(cost IS NOT NULL AND tokens_in IS NOT NULL AND tokens_out IS NOT NULL) OR "
    "(cost = 0 AND provider = 'lmstudio')"
)


def upgrade() -> None:
    op.drop_constraint("known_cost_is_recorded", "model_calls", type_="check")
    op.create_check_constraint("known_cost_is_recorded", "model_calls", KNOWN_COST_AFTER)
    op.add_column(TABLE, sa.Column("provider_reported_model", sa.Text(), nullable=True))
    op.add_column(
        TABLE,
        sa.Column("runtime_diagnostics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column(TABLE, "runtime_diagnostics")
    op.drop_column(TABLE, "provider_reported_model")
    # Refuses (check violation) while any known-$0 local row without tokens
    # exists, by design: a downgrade never rewrites the record of a call.
    op.drop_constraint("known_cost_is_recorded", "model_calls", type_="check")
    op.create_check_constraint("known_cost_is_recorded", "model_calls", KNOWN_COST_BEFORE)
