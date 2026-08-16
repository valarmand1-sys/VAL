"""Tests for the Model Gateway.

Every provider is a stub here: these test the gateway's own guarantees — one
normalized contract, a row per call, budget before the call, Restricted refused
without a row — not whether Anthropic's SDK works.
"""

from datetime import date
from uuid import UUID, uuid4

import pytest

from val_domain.gateway import (
    CallStatus,
    Classification,
    GatewayError,
    GatewayErrorKind,
    GatewayRequest,
    Message,
    ModelConfig,
    TaskType,
)
from val_domain.registry import by_slug
from val_gateway.gateway import CallRecord, Gateway, check_startup, compute_cost
from val_providers.base import ProviderResult


class StubAdapter:
    """A provider that returns what the test tells it to."""

    def __init__(
        self, result: ProviderResult | None = None, error: Exception | None = None
    ) -> None:
        self.name = "anthropic"
        self._result = result
        self._error = error
        self.calls = 0

    def complete(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
    ) -> ProviderResult:
        self.calls += 1
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def config() -> ModelConfig:
    found = by_slug("opus-5")
    assert found is not None
    return found


def request(classification: Classification = Classification.PROTECTED) -> GatewayRequest:
    return GatewayRequest(
        task_type=TaskType.CONVERSATION,
        classification=classification,
        messages=(Message(role="user", content="Good evening."),),
        project_id=uuid4(),
    )


def build(adapter: StubAdapter, spend: float = 0.0) -> tuple[Gateway, list[CallRecord]]:
    rows: list[CallRecord] = []
    return Gateway({"anthropic": adapter}, rows.append, lambda: spend), rows


# --- cost is computed at call time, from the configuration's rates ------------


def test_cost_is_computed_from_the_configuration_rates() -> None:
    """1M in and 1M out on Opus 5 is $5 + $25."""
    assert compute_cost(config(), 1_000_000, 1_000_000) == pytest.approx(30.00)


def test_cost_scales_linearly() -> None:
    """A thousandth of the tokens is a thousandth of the cost."""
    assert compute_cost(config(), 1_000, 1_000) == pytest.approx(0.030)


# --- every call writes a row -------------------------------------------------


def test_a_successful_call_writes_one_row_with_cost_project_and_task_type() -> None:
    """The WP-0.4 criterion: cost, project, and task type populated."""
    adapter = StubAdapter(ProviderResult("Good evening, my lord.", 1000, 500, "req_1", False))
    gateway, rows = build(adapter)
    response = gateway.complete(request(), config())

    assert len(rows) == 1
    row = rows[0]
    assert row.cost_usd == pytest.approx(compute_cost(config(), 1000, 500))
    assert row.project_id is not None
    assert row.task_type == "conversation"
    assert row.status is CallStatus.OK
    assert row.slug == "opus-5"
    assert response.cost_usd == row.cost_usd


def test_a_provider_error_still_writes_a_row() -> None:
    """Zero calls without a row — including the failures."""
    adapter = StubAdapter(error=GatewayError(GatewayErrorKind.TIMEOUT, "timed out"))
    gateway, rows = build(adapter)
    with pytest.raises(GatewayError) as caught:
        gateway.complete(request(), config())
    assert caught.value.kind is GatewayErrorKind.TIMEOUT
    assert len(rows) == 1
    assert rows[0].status is CallStatus.ERROR


def test_a_refusal_is_recorded_as_refused_not_as_an_error() -> None:
    """A refusal is a content outcome; the call happened and cost money."""
    adapter = StubAdapter(ProviderResult("", 800, 0, "req_2", True))
    gateway, rows = build(adapter)
    gateway.complete(request(), config())
    assert rows[0].status is CallStatus.REFUSED


# --- the guards --------------------------------------------------------------


def test_restricted_content_is_refused_and_writes_no_row() -> None:
    """It was never a call: no provider contacted, nothing to cost (WP-0.4)."""
    adapter = StubAdapter(ProviderResult("x", 1, 1, None, False))
    gateway, rows = build(adapter)
    with pytest.raises(GatewayError) as caught:
        gateway.complete(request(Classification.RESTRICTED), config())
    assert caught.value.kind is GatewayErrorKind.RESTRICTED_CONTENT
    assert rows == []
    assert adapter.calls == 0


def test_the_hard_stop_fires_before_the_call() -> None:
    """Seeded above the ceiling: cloud routing stops, provider never contacted."""
    adapter = StubAdapter(ProviderResult("x", 1, 1, None, False))
    gateway, rows = build(adapter, spend=250.00)
    with pytest.raises(GatewayError) as caught:
        gateway.complete(request(), config())
    assert caught.value.kind is GatewayErrorKind.BUDGET_EXCEEDED
    assert "ceiling" in str(caught.value)
    assert adapter.calls == 0
    assert rows == []


def test_just_under_the_ceiling_still_calls() -> None:
    """The stop is at the ceiling, not near it."""
    adapter = StubAdapter(ProviderResult("ok", 10, 10, None, False))
    gateway, _ = build(adapter, spend=199.99)
    gateway.complete(request(), config())
    assert adapter.calls == 1


def test_an_unconfigured_provider_is_an_error_not_a_crash() -> None:
    """A missing adapter is a configuration problem, reported as one."""
    gateway = Gateway({}, lambda record: None, lambda: 0.0)
    with pytest.raises(GatewayError) as caught:
        gateway.complete(request(), config())
    assert caught.value.kind is GatewayErrorKind.INVALID_REQUEST


# --- startup -----------------------------------------------------------------


def test_startup_passes_on_the_committed_registry() -> None:
    """Every configured route is Protected-eligible by construction."""
    violations, _ = check_startup(date(2026, 8, 15))
    assert violations == []


def test_startup_warns_but_does_not_fail_on_stale_rates() -> None:
    """Stale rates degrade a record; they do not make the system unsafe to run."""
    violations, warnings = check_startup(date(2026, 12, 1))
    assert violations == []
    assert warnings
    assert all("rates last verified" in w for w in warnings)


def test_slug_appears_in_every_recorded_row() -> None:
    """Any cost view Lord Armand reads displays the slug, not the UUID."""
    adapter = StubAdapter(ProviderResult("x", 1, 1, None, False))
    gateway, rows = build(adapter)
    gateway.complete(request(), config())
    assert rows[0].slug == "opus-5"
    assert isinstance(rows[0].model_config_id, UUID)
