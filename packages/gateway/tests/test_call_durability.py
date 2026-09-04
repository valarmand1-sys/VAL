"""No provider call without durable evidence — WP-0.4 crash-boundary proofs.

The criterion: *"Every call writes a `model_calls` row… Zero calls without a
row."* The mechanism that makes this true across process death is not the
`model_calls` INSERT — it is the **budget reservation**, which `04-layer-0.md`
§2.5 already defines for exactly this window:

- `ledger.reserve()` commits **its own transaction before the adapter is
  called**, so by the time the provider boundary can be crossed, authoritative
  PostgreSQL durably holds the attempt: route, task, project, and authorised
  maximum. The attempt cannot disappear from history.
- `reserved` means *"admitted; the provider is being contacted"* and `expired`
  means *"the process died holding it — may or may not have reached the
  provider"* (§2.5's own words). "May have been sent" is representable, and it
  is never reported as "definitely sent" or "definitely not".
- Startup reconciliation (`expire_stale`, run by `start()`) moves abandoned
  reservations to `expired`, keeps their maximum committed, reports each in
  words — and **never contacts a provider**. An indeterminate consequential
  action is not retried (`00-charter.md` §4).

These tests inject failure at each boundary by performing the real sequence up
to the crash point against real PostgreSQL, then simulating restart with a
fresh ledger and running the real reconciliation. What is asserted afterwards:
the database state is truthful, the budget is conservative, nothing is
duplicated, and nothing is blindly retried.

A refinement — a set-once transmission marker that would let recovery
distinguish *provably never sent* (releasable) from *may have been sent* — is
recorded on the Layer 0 gate list: it requires a column §2.5 does not
enumerate, which is a baseline amendment, not an implementation choice. The
conservative behaviour proved here is correct without it; the marker would only
return money sooner in one crash case.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from gateway_fakes import StubAdapter
from sqlalchemy import Engine, text
from test_persona import REPO_ROOT, clean_personas  # noqa: F401 - fixture reused

from val_domain.gateway import (
    CallStatus,
    Classification,
    CostCertainty,
    GatewayRequest,
    Message,
    TaskType,
    TerminalState,
)
from val_domain.project import ProjectAttribution
from val_domain.registry import by_slug
from val_gateway.gateway import CallRecord, Gateway, compute_cost
from val_gateway.ledger import DatabaseLedger
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader, seed
from val_gateway.provenance import verifier
from val_providers.base import ProviderResult


@pytest.fixture
def store(clean_personas: Engine) -> Engine:  # noqa: F811 - pytest fixture injection
    seed(clean_personas, REPO_ROOT)
    return clean_personas


def a_request(content: str = "classify this") -> GatewayRequest:
    return GatewayRequest(
        task_type=TaskType.CLASSIFICATION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content=content),),
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
    )


def reservations(engine: Engine) -> list[tuple[str, float, str | None]]:
    with engine.connect() as connection:
        return [
            (row.state, float(row.max_cost), row.resolution)
            for row in connection.execute(
                text(
                    "select state, max_cost, resolution from budget_reservations "
                    "order by created_at"
                )
            ).all()
        ]


def call_rows(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text("select count(*) from model_calls")).scalar_one())


class _ProbingAdapter(StubAdapter):
    """Asserts, at the moment of transmission, that the attempt is already durable.

    This is the ordering proof itself: `complete()` runs a query against
    authoritative PostgreSQL from *inside* the provider boundary and requires a
    committed `reserved` row to exist. If the gateway ever contacted a provider
    before durably reserving, this adapter would fail the call.
    """

    def __init__(self, engine: Engine, result: ProviderResult) -> None:
        super().__init__(result)
        self._engine = engine
        self.durable_at_transmission: bool | None = None

    def complete(
        self,
        config: object,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
    ) -> ProviderResult:
        with self._engine.connect() as connection:
            reserved = connection.execute(
                text("select count(*) from budget_reservations where state = 'reserved'")
            ).scalar_one()
        self.durable_at_transmission = reserved == 1
        return super().complete(config, messages, system, max_output_tokens, output_schema)


def test_the_attempt_is_durable_before_the_provider_boundary(store: Engine) -> None:
    """Property 1, observed from inside the boundary rather than asserted about it."""
    adapter = _ProbingAdapter(store, ProviderResult("ok", TerminalState.COMPLETE, 5, 5, "r"))
    gateway = Gateway(
        adapters={"anthropic": adapter, "openai": adapter},
        recorder=lambda record: record_call(store, record),
        ledger=DatabaseLedger(store),
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(store),
        verify_provenance=verifier(store),
    )

    gateway.complete(a_request())

    assert adapter.durable_at_transmission is True, (
        "the provider boundary was crossed before the attempt was durable"
    )
    # And the healthy path closes the loop: settled reservation, evidence row.
    assert [state for state, _, _ in reservations(store)] == ["settled"]
    assert call_rows(store) == 1


def test_crash_after_reserve_before_transmission(store: Engine) -> None:
    """Boundary 1: durable pre-call state written, process dies before the call.

    The 'crash' is real in the only sense that matters: the reservation was
    committed by its own transaction, and nothing that follows it ever ran.
    Restart is a fresh ledger over the same database, running the same
    reconciliation `start()` runs.
    """
    config = by_slug("haiku-4-5-20251001")
    assert config is not None
    ledger = DatabaseLedger(store)
    claim = ledger.reserve(config, 0.05, TaskType.CLASSIFICATION, None)
    committed_at_crash = ledger.committed_usd()
    # -- process dies here: no transmission, no record, no settlement --
    del ledger, claim

    restarted = DatabaseLedger(store)
    warnings = restarted.expire_stale(older_than_seconds=0)

    state, _, resolution = reservations(store)[0]
    assert state == "expired"
    # Truthful: it does not claim transmission occurred, and does not claim it
    # did not — nothing on this machine can establish which (§2.5).
    assert warnings and "Check the provider's own record" in warnings[0]
    assert resolution is not None and "cannot be established" in resolution
    # Budget-safe: the maximum stays committed; nothing was freed on a guess.
    assert restarted.committed_usd() == pytest.approx(committed_at_crash)
    # Zero calls without a row is not violated: zero calls, zero rows — and the
    # ATTEMPT is in history as the expired reservation.
    assert call_rows(store) == 0


def test_crash_after_transmission_before_call_evidence(store: Engine) -> None:
    """Boundary 2: the provider was (or may have been) reached; the process dies
    before `model_calls` is written.

    The spend cannot vanish: the reservation holds it at the authorised
    maximum, forever attributed to the route and task that reserved it. No
    `model_calls` row is fabricated — a row asserts a call *happened*, and
    nothing on this machine can establish that it did. And recovery never
    retries: an indeterminate consequential action stops.
    """
    config = by_slug("haiku-4-5-20251001")
    assert config is not None
    adapter = StubAdapter(ProviderResult("answered", TerminalState.COMPLETE, 5, 5, "r"))
    ledger = DatabaseLedger(store)
    claim = ledger.reserve(config, 0.05, TaskType.CLASSIFICATION, None)
    adapter.complete(config, (Message(role="user", content="x"),), None, 100)
    calls_before_crash = adapter.calls
    # -- process dies here: transmission happened, evidence never written --
    del ledger, claim

    restarted = DatabaseLedger(store)
    restarted.expire_stale(older_than_seconds=0)

    state, max_cost, _ = reservations(store)[0]
    assert state == "expired"
    assert max_cost == pytest.approx(0.05)
    assert restarted.committed_usd() >= 0.05, "spend that may have happened was freed"
    assert call_rows(store) == 0, "recovery fabricated a call row for an indeterminate call"
    # No blind retry: reconciliation is bookkeeping, not a second attempt.
    assert adapter.calls == calls_before_crash


def test_crash_after_call_evidence_before_settlement(store: Engine) -> None:
    """Boundary 3: the immutable evidence row exists; the process dies before
    the reservation settles.

    The evidence row stands untouched (migration `0009` would refuse anything
    else). The reservation expires at its maximum — conservative, since the
    maximum is an upper bound on the row's real cost — and recovery neither
    duplicates the row nor invents a linkage the crash destroyed.
    """
    config = by_slug("haiku-4-5-20251001")
    assert config is not None
    ledger = DatabaseLedger(store)
    claim = ledger.reserve(config, 0.05, TaskType.CLASSIFICATION, None)
    cost = compute_cost(config, 5, 5)
    record_call(
        store,
        CallRecord(
            model_config_id=config.id,
            slug=config.slug,
            provider=config.provider,
            model_identifier=config.model_identifier,
            tokens_in=5,
            tokens_out=5,
            cost_usd=cost,
            cost_certainty=CostCertainty.KNOWN,
            terminal_state="complete",
            project_id=None,
            project_attribution=ProjectAttribution.EXPLICIT_NONE,
            task_type="classification",
            conversation_id=None,
            message_id=None,
            persona_id=None,
            latency_ms=12,
            provider_request_id="r",
            status=CallStatus.OK,
        ),
    )
    # -- process dies here: evidence written, settlement lost --
    del ledger, claim

    restarted = DatabaseLedger(store)
    restarted.expire_stale(older_than_seconds=0)

    assert call_rows(store) == 1, "the evidence row did not survive, or was duplicated"
    state, max_cost, _ = reservations(store)[0]
    assert state == "expired"
    # Conservative, never understated: the held maximum covers the row's cost.
    assert max_cost >= cost
    assert restarted.committed_usd() >= cost
    # Truthful together: one real call with known cost, one expired hold that
    # over-covers it until the month resets. Nothing claims what it cannot know.
