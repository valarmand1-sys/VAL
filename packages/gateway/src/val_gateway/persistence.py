"""Writing `model_calls`, and reading month-to-date spend back out of it.

The gateway takes a recorder callable and a spend callable so it stays testable
without a database. This is the pair that talks to the real store.

**Month-to-date spend is read from `model_calls`, not from a counter.** The
table is the record; a separate tally could drift from it, and the drift would
be invisible until the ceiling failed to fire. Summing is cheap at Layer 0
volumes and cannot disagree with itself.

Refused and errored calls count toward spend. A refusal still consumed input
tokens at the provider, and an error may have. Excluding them would let a
failing loop spend past the ceiling while the guard reported room
(`00-charter.md` invariant 24).
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Engine, text

from val_gateway.gateway import CallRecord

#: One month-to-date sum, over cloud calls only. Local inference never counts
#: against the ceiling (`01-architecture.md` §5.5) — there is none until Layer 1,
#: so today this is every row.
_MONTH_TO_DATE_SPEND = text(
    "select coalesce(sum(cost), 0) from model_calls "
    "where created_at >= date_trunc('month', now() at time zone 'utc')"
)

_INSERT_CALL = text(
    "insert into model_calls "
    "(model_config_id, provider, model_identifier, tokens_in, tokens_out, cost, "
    " project_id, task_type, conversation_id, message_id, latency_ms, "
    " provider_request_id, status) "
    "values (:model_config_id, :provider, :model_identifier, :tokens_in, :tokens_out, "
    " :cost, :project_id, :task_type, :conversation_id, :message_id, :latency_ms, "
    " :provider_request_id, :status)"
)


def record_call(engine: Engine, record: CallRecord) -> None:
    """Write one `model_calls` row.

    Committed on its own connection rather than joined to a caller's
    transaction: the record of a call that was made must survive whatever
    happens to the work that prompted it.
    """
    with engine.begin() as connection:
        connection.execute(
            _INSERT_CALL,
            {
                "model_config_id": record.model_config_id,
                "provider": record.provider,
                "model_identifier": record.model_identifier,
                "tokens_in": record.tokens_in,
                "tokens_out": record.tokens_out,
                "cost": Decimal(str(record.cost_usd)),
                "project_id": record.project_id,
                "task_type": record.task_type,
                "conversation_id": record.conversation_id,
                "message_id": record.message_id,
                "latency_ms": record.latency_ms,
                # §2 marks this NOT NULL. A provider that returned no reference
                # is recorded as such rather than as a null.
                "provider_request_id": record.provider_request_id or "",
                "status": record.status.value,
            },
        )


def month_to_date_spend(engine: Engine) -> float:
    """Cloud spend so far this calendar month, in USD, summed from the record."""
    with engine.connect() as connection:
        total = connection.execute(_MONTH_TO_DATE_SPEND).scalar_one()
    return float(total)


def month_boundary_utc(now: datetime | None = None) -> datetime:
    """The instant the current month's ceiling began. Resets monthly (§5.5)."""
    moment = now or datetime.now(UTC)
    return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
