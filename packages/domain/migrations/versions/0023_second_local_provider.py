"""The known-$0 clause names the second unmetered LOCAL provider — ruling of 18 September 2026.

`0022` let a `known` cost of zero stand without token figures for the one
unmetered local provider, by name, so that every metered provider kept the
original guard against a fabricated zero. The owner has now authorised a second
LOCAL provider — a standalone llama.cpp server, candidate-only — under the same
`LOCAL_NO_METERED_COST` accounting. The clause is widened by exactly that name;
nothing else about the check changes, and no metered provider is affected.

Revision ID: 0023_second_local_provider
Revises: 0022_runtime_provenance
Create Date: 2026-09-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0023_second_local_provider"
down_revision: str | None = "0022_runtime_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KNOWN_COST_BEFORE = (
    "cost_certainty <> 'known' OR "
    "(cost IS NOT NULL AND tokens_in IS NOT NULL AND tokens_out IS NOT NULL) OR "
    "(cost = 0 AND provider = 'lmstudio')"
)
KNOWN_COST_AFTER = (
    "cost_certainty <> 'known' OR "
    "(cost IS NOT NULL AND tokens_in IS NOT NULL AND tokens_out IS NOT NULL) OR "
    "(cost = 0 AND provider IN ('lmstudio', 'llamacpp'))"
)


def upgrade() -> None:
    op.drop_constraint("known_cost_is_recorded", "model_calls", type_="check")
    op.create_check_constraint("known_cost_is_recorded", "model_calls", KNOWN_COST_AFTER)


def downgrade() -> None:
    # Refuses (check violation) while any known-$0 `llamacpp` row without tokens
    # exists, by design: a downgrade never rewrites the record of a call.
    op.drop_constraint("known_cost_is_recorded", "model_calls", type_="check")
    op.create_check_constraint("known_cost_is_recorded", "model_calls", KNOWN_COST_BEFORE)
