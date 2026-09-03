"""Writing `model_calls`, and reading month-to-date spend back out of it.

The gateway takes a recorder callable and a ledger so it stays testable without
a database. This is the pair that talks to the real store.

**Month-to-date spend is read from the record, not from a counter.** A separate
tally could drift, and the drift would be invisible until the ceiling failed to
fire. Summing is cheap at Layer 0 volumes and cannot disagree with itself. The
authoritative figure the ceiling is enforced against now lives in
`val_gateway.ledger`, which sums settled reservations, outstanding reservations,
expired holds, and any `model_calls` row written before the ledger existed;
`month_to_date_spend` here remains the plain "what did the calls cost" view.

**What errored calls contribute — corrected, 17 August 2026.** This module used
to state flatly that refused and errored calls count toward spend. That was true
of refusals and false of errors as implemented: the error path wrote
`tokens_in = 0, tokens_out = 0, cost = 0` for every failure, including failures
that happened after the request reached the provider. The claim and the code
disagreed, and the code was recording a figure known to be wrong rather than one
merely unknown. The truthful rule, by failure class:

| Failure | Provider reached | Recorded |
|---|---|---|
| Restricted preflight, ineligible route, no route, budget refusal | No | **No row.** Not a call. |
| No adapter configured | No | **No row.** Not a call. |
| Provider refused the content | Yes | Real usage, `cost_certainty = 'known'` |
| Provider returned an error carrying usage | Yes | Real usage, `known` |
| Timeout, connection failure, error without usage | Yes, or possibly | `unknown`, figures NULL |

`sum(cost)` therefore under-reports by exactly the unknown-cost calls, which is
why the ceiling is not enforced against it. The ledger charges those at their
reserved maximum instead.

**Everything here reads `model_calls_accounted`, never `model_calls` directly.**
The base table still holds five rows from 15 August 2026 whose `cost` is a
fabricated `0.000000` — preserved deliberately, because history is not rewritten
to make the present tidy. The view applies the exact rule that identifies them
and reports their cost as unknown. Querying the base table for money is how
those five come back as confirmed free calls; migration
`0004_supersede_zero_costs` explains the rule in full.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine, text

from val_gateway.gateway import CallRecord

#: One month-to-date sum over costs that are actually known.
#:
#: Reads `model_calls_accounted`, not `model_calls`. The difference is the whole
#: point of the 17 August §2.2 amendment: the base table still holds five rows
#: from 15 August whose `cost` is a fabricated `0.000000`, and summing the base
#: table counts them as confirmed free calls. `accounted_cost` is NULL for those
#: rows, so they contribute nothing to a total of what is *known* — and
#: `uncosted_calls` counts them, so no reader can mistake this sum for complete.
#:
#: This is a reporting figure; `ledger.committed_usd` is what the ceiling uses.
_MONTH_TO_DATE_SPEND = text(
    "select coalesce(sum(accounted_cost), 0) from model_calls_accounted "
    "where accounted_cost is not null "
    "and created_at >= date_trunc('month', now() at time zone 'utc') at time zone 'utc'"
)

#: Calls that reached a provider whose cost was never established — including
#: the superseded rows, via `effective_cost_certainty` rather than the stored
#: column, which is NULL on them.
_UNCOSTED_THIS_MONTH = text(
    "select count(*) from model_calls_accounted "
    "where effective_cost_certainty = 'unknown' "
    "and created_at >= date_trunc('month', now() at time zone 'utc') at time zone 'utc'"
)

#: Every superseded row, whenever written, for review rather than for arithmetic.
_SUPERSEDED_ZERO_CALLS = text(
    "select count(*) from model_calls_accounted where accounting_note is not null"
)

#: Month-to-date known spend, split by what the money was for. The WP-0.9
#: ruling of 19 August 2026 requires classification spend visible separately
#: from day one — read from the record, never inferred.
_SPEND_BY_TASK_TYPE = text(
    "select task_type, coalesce(sum(accounted_cost), 0) from model_calls_accounted "
    "where accounted_cost is not null "
    "and created_at >= date_trunc('month', now() at time zone 'utc') at time zone 'utc' "
    "group by task_type"
)

_INSERT_CALL = text(
    "insert into model_calls "
    "(model_config_id, provider, model_identifier, tokens_in, tokens_out, cost, "
    " cost_certainty, terminal_state, project_id, project_attribution, task_type, conversation_id, "
    " message_id, persona_id, latency_ms, provider_request_id, status) "
    "values (:model_config_id, :provider, :model_identifier, :tokens_in, :tokens_out, "
    " :cost, :cost_certainty, :terminal_state, :project_id, :project_attribution, :task_type, "
    " :conversation_id, :message_id, :persona_id, :latency_ms, :provider_request_id, "
    " :status) "
    "returning id"
)


def record_call(engine: Engine, record: CallRecord) -> UUID:
    """Write one `model_calls` row and return its id.

    Committed on its own connection rather than joined to a caller's
    transaction: the record of a call that was made must survive whatever
    happens to the work that prompted it. The id comes back so the reservation
    that paid for the call can point at it.
    """
    with engine.begin() as connection:
        new_id: UUID = connection.execute(
            _INSERT_CALL,
            {
                "model_config_id": record.model_config_id,
                "provider": record.provider,
                "model_identifier": record.model_identifier,
                # NULL, not zero, when the provider did not report usage. The
                # database refuses the zero outright (`unknown_cost_is_not_a_zero`).
                "tokens_in": record.tokens_in,
                "tokens_out": record.tokens_out,
                "cost": None if record.cost_usd is None else Decimal(str(record.cost_usd)),
                "cost_certainty": record.cost_certainty.value,
                "terminal_state": record.terminal_state,
                "project_id": record.project_id,
                # WP-0.6 corrective round: what that project_id *means*. A NULL
                # alone cannot distinguish a decision from a row that predates
                # the decision existing.
                "project_attribution": record.project_attribution.value,
                "task_type": record.task_type,
                "conversation_id": record.conversation_id,
                "message_id": record.message_id,
                # WP-0.5: which persona produced this call. A reference, never a
                # copy — the persona is immutable, so it resolves to exactly the
                # text that was sent.
                "persona_id": record.persona_id,
                "latency_ms": record.latency_ms,
                # §2 marks this NOT NULL. A provider that returned no reference
                # is recorded as such rather than as a null.
                "provider_request_id": record.provider_request_id or "",
                "status": record.status.value,
            },
        ).scalar_one()
    return new_id


def month_to_date_spend(engine: Engine) -> float:
    """Cloud spend so far this calendar month, in USD, as recorded.

    Known costs only. Not the ceiling's figure — see the module docstring — and
    never present it as a complete one while `uncosted_calls_this_month` is
    non-zero.
    """
    with engine.connect() as connection:
        total = connection.execute(_MONTH_TO_DATE_SPEND).scalar_one()
    return float(total)


def response_call_recorded(engine: Engine, message_id: UUID) -> bool:
    """Whether a conversation call for this user message reached the record.

    *Ruled 2 September 2026.* The interface may claim provider contact only
    where the durable call lifecycle supports it. A provider that was
    contacted and failed leaves a `model_calls` row for the turn (transit
    failures record `terminal_state = 'failed'`); a call refused before
    contact — budget, no eligible route, incoherent provenance — leaves none.
    This reads that fact from the record rather than inferring it from an
    error message.
    """
    with engine.connect() as connection:
        found = connection.execute(
            text(
                "select 1 from model_calls "
                "where message_id = :m and task_type = 'conversation' limit 1"
            ),
            {"m": message_id},
        ).first()
    return found is not None


def spend_by_task_type(engine: Engine) -> dict[str, float]:
    """This month's known spend, keyed by `task_type` — the cost view's split.

    *WP-0.9 ruling, 19 August 2026.* The §4.8 classifier runs on every
    exchange, so its recurring cost must be readable on its own line from day
    one: `spend_by_task_type(engine).get("classification", 0.0)` is that line,
    and if classification comes to dominate, it is seen here rather than
    inferred. Same caveat as `month_to_date_spend`: known costs only, honest
    alongside `uncosted_calls_this_month`.
    """
    with engine.connect() as connection:
        rows = connection.execute(_SPEND_BY_TASK_TYPE).all()
    return {str(task_type): float(total) for task_type, total in rows}


def uncosted_calls_this_month(engine: Engine) -> int:
    """How many of this month's calls reached a provider that never reported usage.

    Kept alongside the sum so no view can display month-to-date spend as though
    it were complete when it is not (`00-charter.md` invariant 29). Counts the
    superseded 15 August rows too: their stored certainty is NULL, but their
    *effective* certainty is `unknown`, and that is what this reads.
    """
    with engine.connect() as connection:
        return int(connection.execute(_UNCOSTED_THIS_MONTH).scalar_one())


def superseded_zero_calls(engine: Engine) -> int:
    """Rows whose recorded zero cost is known to be fabricated.

    Five as of 17 August 2026, all written on 15 August. Exposed as its own
    figure so the correction is visible rather than merely applied — a reader
    who wants to know whether any of this history is superseded can ask, instead
    of having to already know.
    """
    with engine.connect() as connection:
        return int(connection.execute(_SUPERSEDED_ZERO_CALLS).scalar_one())


def month_boundary_utc(now: datetime | None = None) -> datetime:
    """The instant the current month's ceiling began. Resets monthly (§5.5)."""
    moment = now or datetime.now(UTC)
    return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
