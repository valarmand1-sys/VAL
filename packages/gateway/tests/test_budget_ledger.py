"""The reservation ledger against a real PostgreSQL.

These are the only tests that can prove what the ledger is for. A fake cannot
demonstrate atomicity, and a test that used one would be proving the fake. Every
test here opens its own connections against the scratch database and lets
PostgreSQL arbitrate, exactly as `api` and `worker` would.

Rows are never cleaned up by deleting them — the no-hard-delete trigger of §2.3
covers `budget_reservations` too. Each test works within a month-to-date figure
it reads first, so accumulated rows change nothing it asserts.
"""

import threading
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from val_domain.gateway import CostCertainty, TaskType
from val_domain.registry import by_slug
from val_gateway.ledger import (
    DatabaseLedger,
    InvalidReservationTransitionError,
    Refusal,
    Reservation,
)
from val_policy.budget import CLOUD_CEILING_USD


def config() -> object:
    found = by_slug("haiku-4-5-20251001")
    assert found is not None
    return found


def reserve(ledger: DatabaseLedger, amount: float) -> Reservation | Refusal:
    return ledger.reserve(config(), amount, TaskType.CONVERSATION, None)  # type: ignore[arg-type]


def state_of(engine: Engine, reservation_id: UUID) -> tuple[str, Decimal | None, str | None]:
    with engine.connect() as connection:
        row = connection.execute(
            text("select state, settled_cost, resolution from budget_reservations where id = :id"),
            {"id": reservation_id},
        ).one()
    return row.state, row.settled_cost, row.resolution


# --- the arithmetic ----------------------------------------------------------


def test_a_reservation_immediately_counts_as_committed(ledger_engine: Engine) -> None:
    """Headroom is claimed at the moment of admission, not at settlement."""
    ledger = DatabaseLedger(ledger_engine)
    before = ledger.committed_usd()
    claim = reserve(ledger, 1.25)
    assert isinstance(claim, Reservation)
    assert ledger.committed_usd() == pytest.approx(before + 1.25)


def test_settling_below_the_reservation_returns_the_difference(
    ledger_engine: Engine,
) -> None:
    """Requirement E: actual cost below reservation frees the remainder."""
    ledger = DatabaseLedger(ledger_engine)
    before = ledger.committed_usd()
    claim = reserve(ledger, 4.00)
    assert isinstance(claim, Reservation)

    ledger.settle(claim.id, 0.25, CostCertainty.KNOWN, None)

    assert ledger.committed_usd() == pytest.approx(before + 0.25)
    state, settled, _ = state_of(ledger_engine, claim.id)
    assert state == "settled"
    assert settled == Decimal("0.250000")


def test_releasing_returns_the_whole_reservation(ledger_engine: Engine) -> None:
    """Requirement C: the call failed before the provider consumed anything."""
    ledger = DatabaseLedger(ledger_engine)
    before = ledger.committed_usd()
    claim = reserve(ledger, 3.00)
    assert isinstance(claim, Reservation)

    ledger.release(claim.id, "no provider request was made")

    assert ledger.committed_usd() == pytest.approx(before)
    state, settled, resolution = state_of(ledger_engine, claim.id)
    assert state == "released"
    assert settled is None
    assert resolution is not None, "a release with no stated reason is a silent leak"


def test_an_unknown_cost_settles_at_the_full_reservation(ledger_engine: Engine) -> None:
    """Adversarial proof 3: the provider was reached and would not say."""
    ledger = DatabaseLedger(ledger_engine)
    before = ledger.committed_usd()
    claim = reserve(ledger, 2.50)
    assert isinstance(claim, Reservation)

    ledger.settle(claim.id, None, CostCertainty.UNKNOWN, None)

    assert ledger.committed_usd() == pytest.approx(before + 2.50), "budget was silently freed"
    state, settled, resolution = state_of(ledger_engine, claim.id)
    assert state == "settled"
    assert settled == Decimal("2.500000")
    assert resolution is not None and "unverified" in resolution


def test_a_known_settlement_must_carry_a_figure(ledger_engine: Engine) -> None:
    """`known` with no cost is the false-zero bug wearing a different hat."""
    ledger = DatabaseLedger(ledger_engine)
    claim = reserve(ledger, 0.10)
    assert isinstance(claim, Reservation)
    with pytest.raises(ValueError):
        ledger.settle(claim.id, None, CostCertainty.KNOWN, None)


# --- the ceiling, enforced against the proposed call -------------------------


def test_a_call_larger_than_the_remainder_is_refused(ledger_engine: Engine) -> None:
    """Adversarial proof 1, at the ledger: `committed < ceiling` is not enough."""
    ledger = DatabaseLedger(ledger_engine)
    headroom = CLOUD_CEILING_USD - ledger.committed_usd()

    # Fill everything but a cent, then ask for more than a cent.
    filler = reserve(ledger, headroom - 0.01)
    assert isinstance(filler, Reservation)
    assert ledger.committed_usd() == pytest.approx(CLOUD_CEILING_USD - 0.01)

    refused = reserve(ledger, 0.02)
    assert isinstance(refused, Refusal), "a call larger than the remainder was admitted"
    assert refused.committed_usd == pytest.approx(CLOUD_CEILING_USD - 0.01)

    # And something that does fit is still admitted.
    fits = reserve(ledger, 0.005)
    assert isinstance(fits, Reservation)

    ledger.release(filler.id, "test teardown")
    ledger.release(fits.id, "test teardown")


def test_exactly_filling_the_ceiling_is_admitted(ledger_engine: Engine) -> None:
    """The rule is `<=`. A call that fits exactly fits."""
    ledger = DatabaseLedger(ledger_engine)
    headroom = CLOUD_CEILING_USD - ledger.committed_usd()
    claim = reserve(ledger, headroom)
    assert isinstance(claim, Reservation)
    assert ledger.committed_usd() == pytest.approx(CLOUD_CEILING_USD)

    assert isinstance(reserve(ledger, 0.000001), Refusal)
    ledger.release(claim.id, "test teardown")


# --- concurrency -------------------------------------------------------------


def test_two_simultaneous_calls_cannot_both_take_insufficient_budget(
    ledger_engine: Engine,
) -> None:
    """Adversarial proof 2, and the reason this is a database and not a counter.

    Two threads, each on its own connection, race for headroom that fits exactly
    one of them. Without the advisory lock both read the same committed figure,
    both decide there is room, and together they breach the ceiling by the size
    of one call. With it, exactly one wins.
    """
    ledger = DatabaseLedger(ledger_engine)
    headroom = CLOUD_CEILING_USD - ledger.committed_usd()

    # Leave room for exactly one of the two contenders.
    contender = headroom * 0.6
    filler = reserve(ledger, headroom - contender)
    assert isinstance(filler, Reservation)

    results: list[Reservation | Refusal] = []
    barrier = threading.Barrier(2)

    def attempt() -> None:
        own = DatabaseLedger(ledger_engine)
        barrier.wait()
        results.append(reserve(own, contender))

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    admitted = [r for r in results if isinstance(r, Reservation)]
    refused = [r for r in results if isinstance(r, Refusal)]

    assert len(admitted) == 1, f"{len(admitted)} of 2 admitted; the ceiling was breached"
    assert len(refused) == 1
    assert ledger.committed_usd() <= CLOUD_CEILING_USD + 1e-9

    for winner in admitted:
        ledger.release(winner.id, "test teardown")
    ledger.release(filler.id, "test teardown")


def test_many_simultaneous_calls_never_exceed_the_ceiling(ledger_engine: Engine) -> None:
    """The same property under more pressure: eight contenders, room for three."""
    ledger = DatabaseLedger(ledger_engine)
    headroom = CLOUD_CEILING_USD - ledger.committed_usd()
    each = headroom / 3.5  # room for exactly three

    results: list[Reservation | Refusal] = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def attempt() -> None:
        own = DatabaseLedger(ledger_engine)
        barrier.wait()
        outcome = reserve(own, each)
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    admitted = [r for r in results if isinstance(r, Reservation)]
    assert len(admitted) == 3, f"{len(admitted)} admitted where three fit"
    assert ledger.committed_usd() <= CLOUD_CEILING_USD + 1e-9

    for winner in admitted:
        ledger.release(winner.id, "test teardown")


# --- stale reservations ------------------------------------------------------


def test_a_stale_reservation_expires_without_freeing_budget(
    ledger_engine: Engine,
) -> None:
    """Requirement D: recovered, reported, and still charged.

    The process that took this reservation never came back. Whether it reached
    the provider cannot be established here, so the amount stays committed —
    recovery is not forgiveness.
    """
    ledger = DatabaseLedger(ledger_engine)
    before = ledger.committed_usd()
    claim = reserve(ledger, 1.75)
    assert isinstance(claim, Reservation)

    # Nothing outstanding is stale yet.
    assert ledger.expire_stale(older_than_seconds=3600) == []
    assert state_of(ledger_engine, claim.id)[0] == "reserved"

    # Treat everything older than an instant as abandoned.
    reported = ledger.expire_stale(older_than_seconds=0)

    assert any(str(claim.id) in line for line in reported), "the expiry was not reported"
    assert state_of(ledger_engine, claim.id)[0] == "expired"
    assert ledger.committed_usd() == pytest.approx(before + 1.75), (
        "expiring a stale reservation silently increased available spend"
    )


def test_an_expired_reservation_is_not_settled_or_released(
    ledger_engine: Engine,
) -> None:
    """It leaves `reserved` so it stops looking like a call in flight, and stops there."""
    ledger = DatabaseLedger(ledger_engine)
    claim = reserve(ledger, 0.50)
    assert isinstance(claim, Reservation)
    ledger.expire_stale(older_than_seconds=0)

    state, settled, resolution = state_of(ledger_engine, claim.id)
    assert state == "expired"
    assert settled is None
    assert resolution is not None and "committed" in resolution

    # And it can no longer be settled — loudly. *Closure pass, 18 August 2026:*
    # this used to assert the settlement silently did nothing, which enshrined
    # the defect: the caller believed a transition the ledger did not perform.
    with pytest.raises(InvalidReservationTransitionError, match="already 'expired'"):
        ledger.settle(claim.id, 0.01, CostCertainty.KNOWN, None)
    assert state_of(ledger_engine, claim.id)[0] == "expired"


def test_no_overruns_are_reported_on_a_healthy_ledger(ledger_engine: Engine) -> None:
    """The reserved figure is an upper bound, so this list should stay empty."""
    ledger = DatabaseLedger(ledger_engine)
    claim = reserve(ledger, 5.00)
    assert isinstance(claim, Reservation)
    ledger.settle(claim.id, 0.02, CostCertainty.KNOWN, None)
    assert ledger.overruns() == []


def test_an_overrun_is_reported_rather_than_clamped(ledger_engine: Engine) -> None:
    """If the bound ever fails, the record says so instead of tidying it away."""
    ledger = DatabaseLedger(ledger_engine)
    claim = reserve(ledger, 0.01)
    assert isinstance(claim, Reservation)
    ledger.settle(claim.id, 5.00, CostCertainty.KNOWN, None)

    reported = ledger.overruns()
    assert any(str(claim.id) in line for line in reported)
    assert any("INVARIANT 24 VIOLATION" in line for line in reported)

    _, settled, _ = state_of(ledger_engine, claim.id)
    assert settled == Decimal("5.000000"), "the record was clamped to the reservation"


# --- reservations cannot be deleted ------------------------------------------


def test_a_reservation_cannot_be_hard_deleted(ledger_engine: Engine) -> None:
    """A spending record that can be deleted is one that will be (§2.3)."""
    ledger = DatabaseLedger(ledger_engine)
    claim = reserve(ledger, 0.01)
    assert isinstance(claim, Reservation)
    with pytest.raises(Exception, match="hard delete"):
        with ledger_engine.begin() as connection:
            connection.execute(
                text("delete from budget_reservations where id = :id"), {"id": claim.id}
            )


def test_an_unknown_reservation_id_is_refused_by_name(ledger_engine: Engine) -> None:
    """A transition naming nothing is an error, not a no-op.

    *Closure pass, 18 August 2026.* The old assertion — that releasing a
    made-up id left the committed figure unchanged — was true and useless: it
    proved the SQL was scoped, while the caller walked away believing a release
    happened. The ledger now says so.
    """
    ledger = DatabaseLedger(ledger_engine)
    before = ledger.committed_usd()
    with pytest.raises(InvalidReservationTransitionError, match="does not exist"):
        ledger.release(uuid4(), "nothing by this id exists")
    assert ledger.committed_usd() == pytest.approx(before)


def test_a_settled_reservation_cannot_settle_or_release_again(ledger_engine: Engine) -> None:
    """The double-settlement and hidden-release cases, named individually."""
    ledger = DatabaseLedger(ledger_engine)
    claim = reserve(ledger, 1.00)
    assert isinstance(claim, Reservation)
    ledger.settle(claim.id, 0.10, CostCertainty.KNOWN, None)
    committed = ledger.committed_usd()

    with pytest.raises(InvalidReservationTransitionError, match="already 'settled'"):
        ledger.settle(claim.id, 0.99, CostCertainty.KNOWN, None)
    with pytest.raises(InvalidReservationTransitionError, match="already 'settled'"):
        ledger.release(claim.id, "trying to hide the spend")

    # The first settlement stands, to the cent.
    assert ledger.committed_usd() == pytest.approx(committed)
    state, settled, _ = state_of(ledger_engine, claim.id)
    assert state == "settled"
    assert settled is not None and float(settled) == pytest.approx(0.10)


def test_concurrent_settle_and_release_admit_exactly_one_winner(
    ledger_engine: Engine,
) -> None:
    """The race §6 names: two transitions, one row, one winner, one loud loser.

    Ten threads on independent connections all try to close the same
    reservation — half settling, half releasing. The `where state='reserved'`
    guard makes the transition atomic; the closure-pass rowcount check makes
    the losers *know* they lost.
    """
    from concurrent.futures import ThreadPoolExecutor

    ledger = DatabaseLedger(ledger_engine)
    claim = reserve(ledger, 1.00)
    assert isinstance(claim, Reservation)

    def contend(index: int) -> str:
        try:
            if index % 2:
                ledger.settle(claim.id, 0.05, CostCertainty.KNOWN, None)
            else:
                ledger.release(claim.id, "racing release")
            return "won"
        except InvalidReservationTransitionError:
            return "refused"

    with ThreadPoolExecutor(max_workers=10) as pool:
        outcomes = list(pool.map(contend, range(10)))

    assert outcomes.count("won") == 1, f"expected one winner, got {outcomes}"
    assert outcomes.count("refused") == 9
    assert state_of(ledger_engine, claim.id)[0] in ("settled", "released")
