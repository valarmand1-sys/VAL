"""A prefix prime is a model call, and the record says so — owner order, 25 September 2026.

Priming-cache pass §3, §9. To let the local runtime reuse the computation of Val's
persona across turns, VAL sends it one small request whose only purpose is to leave
that computation in the runtime's memory: a **local infrastructure model call**. It
is not a conversation turn, not an answer and not memory, and it attaches to no
conversation or message — but it is a real invocation of the model, and Layer 0
captures every invocation. `model_calls.task_type` therefore gains `prefix_prime`,
which is also the task type its budget reservation carries.

Forward only in intent. PostgreSQL cannot remove a value from an enum type, and the
columns carrying this one feed views, so the downgrade does not pretend to: it
**refuses** if any prime has been recorded — removing it would rewrite those rows into
something they were not — and otherwise leaves the unused value in the type, which
changes nothing any query can see. Upgrading again is idempotent.
"""

from __future__ import annotations

from alembic import op

revision: str = "0031_prefix_prime"
down_revision: str | None = "0030_voice_local_only"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.execute("ALTER TYPE model_call_task_type ADD VALUE IF NOT EXISTS 'prefix_prime'")


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM model_calls WHERE task_type::text = 'prefix_prime') "
        "OR EXISTS (SELECT 1 FROM budget_reservations WHERE task_type::text = 'prefix_prime') "
        "THEN RAISE EXCEPTION 'Refusing to downgrade: prefix_prime calls are recorded, and "
        "removing the value would rewrite them into something they were not.'; "
        "END IF; END $$"
    )
    # The unused value stays in the type: PostgreSQL has no DROP VALUE, and nothing reads it.
