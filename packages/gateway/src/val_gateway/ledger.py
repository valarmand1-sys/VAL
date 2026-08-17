"""The budget reservation ledger: the authoritative pre-call spending control.

`00-charter.md` invariant 24 — *budget ceilings are enforced before a call is
made, never reported after* — has two halves, and only the first was implemented
before 17 August 2026. Checking `month_to_date_spend < CEILING` happens before
the call, certainly, but it enforces the ceiling against **history** rather than
against the call being proposed. At $199.99 of $200 it admits a call authorised
to spend $40, and the ceiling is discovered breached by reading the record
afterwards. That is reporting after, one indirection removed.

The rule this module implements:

    admit the call  ⟺  committed + maximum_cost(this call) ≤ CEILING

**Why it lives in PostgreSQL.** `committed` is a fact about the house, not about
a process. `api` and `worker` share one gateway implementation but not one
address space, and two of them each holding a local counter would each observe
the same $0.50 of headroom and each admit a $0.40 call. A process-local counter,
an in-memory mutex, and an optimistic UI number all fail the same way and fail
silently. The authoritative store is the only place that can answer for both.

**How concurrency is actually made safe.** Admission runs inside one transaction
holding `pg_advisory_xact_lock` on a fixed key. Sum, decide, and insert are one
atomic step across every process on the machine, and the lock releases with the
transaction whether it commits, rolls back, or the connection dies. Two
simultaneous requests therefore serialise: the first sees the true committed
figure and reserves; the second sees the first's reservation already counted and
is refused. The lock is held for the arithmetic and the insert only — never
across the provider call, which would serialise every call Val makes.

**What `committed` sums.** Three things, because all three are money that may
already be gone:

1. Reservations still `reserved` — in flight, at their authorised maximum.
2. Reservations `settled` — at what they actually cost, or at the conservative
   figure where the cost is unknown.
3. Reservations `expired` — see below.
4. Reservation-less `model_calls` rows, at their **accounted** cost — read
   through `model_calls_accounted`, never through the base table. These are the
   six rows written on 15 August 2026, before this ledger existed. Excluding
   them would quietly forgive real spending; reading them raw would do something
   subtler and worse, because five of the six carry a fabricated `$0.00` that
   the base table cannot distinguish from a genuine one. The view reports those
   five as unknown, so they add nothing to a figure that claims to be known —
   and `unaccounted_calls` says how many are missing, so the figure is never
   presented as complete. Migration `0004` explains the rule.

**Why `expired` still counts.** A reservation whose process died may or may not
have reached the provider. Nothing on this machine can tell which, and
`00-charter.md` §4 is explicit that an unknown consequential outcome is
*unverified*, not *successful*. Freeing it would hand back money that may well
have been spent. It stays committed, `expire_stale` reports it in words, and it
falls out of the sum when the month's ceiling resets — so a crash costs at most
the remainder of one month and never silently widens what may be spent. Those
two properties have to hold at once, and this is the state that holds both.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy import Engine, text

from val_domain.gateway import CostCertainty, ModelConfig, TaskType
from val_policy.budget import admits

#: The advisory-lock key every budget admission serialises on. Arbitrary, fixed,
#: and shared by every process: two processes choosing different keys would each
#: hold "the" lock and neither would be excluded, which is the failure this
#: mechanism exists to prevent, reintroduced by a typo.
BUDGET_LOCK_KEY = 0x7641_4C30_4255_4447  # "VAL0BUDG"

#: How long a reservation may sit `reserved` before it is treated as abandoned.
#: Longer than any plausible provider call — a request that has been outstanding
#: for an hour is not slow, it is orphaned — and short enough that a crash does
#: not hold headroom for the rest of the month.
STALE_AFTER_SECONDS = 3600


@dataclass(frozen=True)
class Reservation:
    """An admitted claim on the month's budget, before the provider is contacted."""

    id: UUID
    max_cost_usd: float
    committed_before_usd: float


@dataclass(frozen=True)
class Refusal:
    """An admission refused, with the arithmetic that refused it."""

    committed_usd: float
    max_cost_usd: float


class BudgetLedger(Protocol):
    """What the gateway needs of a ledger, and nothing more.

    A Protocol so the gateway's own tests can drive a deterministic fake, while
    the running system uses `DatabaseLedger`. The fake proves the gateway calls
    the ledger correctly; only the database implementation proves the ledger is
    safe under concurrency, and `test_budget_ledger.py` tests that against a real
    PostgreSQL rather than against the fake.
    """

    def committed_usd(self) -> float:
        """Everything already spent or claimed this month."""
        ...

    def reserve(
        self,
        config: ModelConfig,
        max_cost_usd: float,
        task_type: TaskType,
        project_id: UUID | None,
    ) -> Reservation | Refusal:
        """Claim headroom for one call, atomically, or refuse."""
        ...

    def settle(
        self,
        reservation_id: UUID,
        actual_cost_usd: float | None,
        certainty: CostCertainty,
        model_call_id: UUID | None,
    ) -> None:
        """Close a reservation against what the call actually consumed."""
        ...

    def release(self, reservation_id: UUID, reason: str) -> None:
        """Return headroom because no provider request occurred."""
        ...


_COMMITTED = text(
    """
    select
      coalesce((
        select sum(case
          when state in ('reserved', 'expired') then max_cost
          when state = 'settled' then settled_cost
          else 0
        end)
        from budget_reservations
        where state <> 'released'
          and created_at >= date_trunc('month', now() at time zone 'utc')
      ), 0)
      +
      coalesce((
        select sum(mc.accounted_cost)
        from model_calls_accounted mc
        where mc.created_at >= date_trunc('month', now() at time zone 'utc')
          and mc.accounted_cost is not null
          and not exists (
            select 1 from budget_reservations br where br.model_call_id = mc.id
          )
      ), 0)
    """
)

_INSERT_RESERVATION = text(
    """
    insert into budget_reservations
      (state, model_config_id, slug, provider, model_identifier, task_type,
       project_id, max_cost)
    values
      ('reserved', :model_config_id, :slug, :provider, :model_identifier, :task_type,
       :project_id, :max_cost)
    returning id
    """
)

_SETTLE = text(
    """
    update budget_reservations
       set state = 'settled',
           settled_cost = :settled_cost,
           cost_certainty = :cost_certainty,
           model_call_id = :model_call_id,
           resolution = :resolution,
           updated_at = now()
     where id = :id and state = 'reserved'
    """
)

_RELEASE = text(
    """
    update budget_reservations
       set state = 'released', resolution = :resolution, updated_at = now()
     where id = :id and state = 'reserved'
    """
)

_EXPIRE = text(
    """
    update budget_reservations
       set state = 'expired', resolution = :resolution, updated_at = now()
     where state = 'reserved'
       and created_at < now() - make_interval(secs => :seconds)
    returning id, slug, max_cost, created_at
    """
)

#: Calls this ledger cannot account for: they reached a provider, no reservation
#: covers them, and their cost was never established. The five superseded rows of
#: 15 August 2026 are exactly this. Reported rather than silently absorbed.
_UNACCOUNTED = text(
    """
    select count(*)
      from model_calls_accounted mc
     where mc.effective_cost_certainty = 'unknown'
       and mc.created_at >= date_trunc('month', now() at time zone 'utc')
       and not exists (
         select 1 from budget_reservations br where br.model_call_id = mc.id
       )
    """
)

_OVERRUNS = text(
    """
    select id, slug, max_cost, settled_cost, created_at
      from budget_reservations
     where state = 'settled' and settled_cost > max_cost
     order by created_at
    """
)


class DatabaseLedger:
    """The real ledger. PostgreSQL is the authority; this only asks it."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def committed_usd(self) -> float:
        """Settled spend, outstanding reservations, expired holds, legacy rows."""
        with self._engine.connect() as connection:
            return float(connection.execute(_COMMITTED).scalar_one())

    def reserve(
        self,
        config: ModelConfig,
        max_cost_usd: float,
        task_type: TaskType,
        project_id: UUID | None,
    ) -> Reservation | Refusal:
        """Admit or refuse one call, atomically.

        The advisory lock, the sum, the decision, and the insert are one
        transaction. Nothing between them can observe a stale figure, and no
        second caller can slip a reservation in between the sum and the insert —
        which is the exact window a check-then-act guard leaves open.
        """
        with self._engine.begin() as connection:
            connection.execute(text("select pg_advisory_xact_lock(:key)"), {"key": BUDGET_LOCK_KEY})
            committed = float(connection.execute(_COMMITTED).scalar_one())
            if not admits(committed, max_cost_usd):
                return Refusal(committed_usd=committed, max_cost_usd=max_cost_usd)

            reservation_id = connection.execute(
                _INSERT_RESERVATION,
                {
                    "model_config_id": config.id,
                    "slug": config.slug,
                    "provider": config.provider,
                    "model_identifier": config.model_identifier,
                    "task_type": task_type.value,
                    "project_id": project_id,
                    "max_cost": Decimal(str(round(max_cost_usd, 6))),
                },
            ).scalar_one()

        return Reservation(
            id=reservation_id,
            max_cost_usd=max_cost_usd,
            committed_before_usd=committed,
        )

    def settle(
        self,
        reservation_id: UUID,
        actual_cost_usd: float | None,
        certainty: CostCertainty,
        model_call_id: UUID | None,
    ) -> None:
        """Close the reservation against what was actually consumed.

        Known cost settles at the real figure, and the difference between it and
        the reservation becomes available again the instant this commits —
        nothing sweeps, nothing expires, the sum simply stops counting the
        maximum and starts counting the actual.

        **Unknown cost settles at the full reserved maximum.** The provider was
        contacted and would not say what it charged; releasing the difference
        would be treating "we do not know" as "nothing was spent". The
        `model_calls` row still records the cost as NULL, because the ledger's
        job is to be conservative about what may be gone and the call record's
        job is to be honest about what is known. They disagree on purpose.
        """
        if certainty is CostCertainty.UNKNOWN:
            charged, resolution = self._unknown_settlement(reservation_id)
        elif actual_cost_usd is None:
            raise ValueError("a settlement recorded as `known` must carry a cost figure")
        else:
            charged = Decimal(str(round(actual_cost_usd, 6)))
            resolution = "settled against reported provider usage"

        with self._engine.begin() as connection:
            connection.execute(
                _SETTLE,
                {
                    "id": reservation_id,
                    "settled_cost": charged,
                    "cost_certainty": certainty.value,
                    "model_call_id": model_call_id,
                    "resolution": resolution,
                },
            )

    def _unknown_settlement(self, reservation_id: UUID) -> tuple[Decimal, str]:
        """Charge the whole reservation, and say in the row why."""
        with self._engine.connect() as connection:
            reserved = connection.execute(
                text("select max_cost from budget_reservations where id = :id"),
                {"id": reservation_id},
            ).scalar_one()
        return (
            Decimal(reserved),
            "provider contacted; usage not reported. Charged at the reserved "
            "maximum rather than released — an unknown outcome is unverified, "
            "not free (00-charter.md §4).",
        )

    def release(self, reservation_id: UUID, reason: str) -> None:
        """Return the headroom. Only ever called when no request was sent."""
        with self._engine.begin() as connection:
            connection.execute(_RELEASE, {"id": reservation_id, "resolution": reason})

    def expire_stale(self, older_than_seconds: int = STALE_AFTER_SECONDS) -> list[str]:
        """Move abandoned reservations out of `reserved`, and report them.

        Recovery, not forgiveness. The row leaves `reserved` so it stops looking
        like a call in flight, and its amount stays committed because nothing
        here can establish that the money was not spent. Each one is returned in
        words so it surfaces rather than accumulating quietly.
        """
        with self._engine.begin() as connection:
            rows = connection.execute(
                _EXPIRE,
                {
                    "seconds": older_than_seconds,
                    "resolution": (
                        "held past the stale window with no settlement. The process "
                        "that took it did not finish, and whether the provider was "
                        "reached cannot be established here, so the amount stays "
                        "committed until the month resets."
                    ),
                },
            ).all()

        return [
            f"budget reservation {row.id} on {row.slug} (${float(row.max_cost):.4f}, taken "
            f"{row.created_at:%Y-%m-%d %H:%M} UTC) expired without settling. It remains "
            "committed against this month's ceiling. Check the provider's own record "
            "for whether the call was made."
            for row in rows
        ]

    def unaccounted_calls(self) -> int:
        """This month's calls whose cost is unknown and which no reservation covers.

        `committed_usd` cannot include what nobody knows, so it under-reports by
        exactly these. Returning the count separately is what stops that
        under-reporting from being invisible: a headroom figure paired with "and
        n calls are unaccounted for" is honest, while the same figure alone is a
        claim the records do not support (`00-charter.md` invariant 29).
        """
        with self._engine.connect() as connection:
            return int(connection.execute(_UNACCOUNTED).scalar_one())

    def overruns(self) -> list[str]:
        """Settlements that cost more than they were authorised to.

        This must not happen: the reserved figure is an arithmetic upper bound
        from byte lengths, not an estimate. If one appears, the row itself is the
        evidence — `max_cost` and `settled_cost` are both kept, and the record is
        written truthfully rather than clamped to the reservation. A tidy number
        hiding a breached ceiling is worse than the breach.
        """
        with self._engine.connect() as connection:
            rows = connection.execute(_OVERRUNS).all()

        return [
            f"INVARIANT 24 VIOLATION: reservation {row.id} on {row.slug} was authorised "
            f"for ${float(row.max_cost):.6f} and settled at ${float(row.settled_cost):.6f}, "
            f"taken {row.created_at:%Y-%m-%d %H:%M} UTC. The reserved figure is an upper "
            "bound, so this means the bound itself is wrong. Do not raise the ceiling; "
            "find why the bound failed."
            for row in rows
        ]


def month_boundary_utc(now: datetime | None = None) -> datetime:
    """The instant the current month's ceiling began. Resets monthly (§5.5)."""
    moment = now or datetime.now(UTC)
    return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
