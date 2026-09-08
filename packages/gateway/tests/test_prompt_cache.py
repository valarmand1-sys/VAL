"""Prompt caching on the partner route — ruling, 8 September 2026.

The reservation assumes a miss at the write rate; settlement prices the
provider's four usage figures at the configuration's verified cache rates;
the split is persisted beside the call; caching is requested only when the
gateway is configured with a lifetime, the route's caching is verified, and
the stable prefix meets the model's minimum.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

import pytest
from gateway_fakes import FakeLedger, StubAdapter, build, config, request
from sqlalchemy import Engine, text

from val_domain.gateway import (
    CacheTtl,
    CostCertainty,
    Message,
    ModelConfig,
    PricingFeature,
    ProjectAttribution,
    TerminalState,
)
from val_gateway.gateway import CacheUsage, CallRecord, Gateway, compute_cost, cost_components
from val_gateway.persistence import record_call
from val_gateway.startup import CACHE_TTL_SETTING, configured_cache_ttl
from val_policy.budget import maximum_cost
from val_providers.base import ProviderResult

OPUS = config("opus-5")
HAIKU = config("haiku-4-5-20251001")
LONG_SYSTEM = "persona " * 3_000  # far above Opus 5's 512-token minimum
SHORT_SYSTEM = "You classify one exchange."


class CachingStub(StubAdapter):
    """A provider that reports cache figures, recording what it was asked."""

    def __init__(self, result: ProviderResult) -> None:
        super().__init__(result)
        self.name = "anthropic"


def cached(read: int, write_5m: int = 0, write_1h: int = 0, uncached: int = 40) -> ProviderResult:
    return ProviderResult(
        "ok",
        TerminalState.COMPLETE,
        uncached,
        30,
        "r",
        cache_read_tokens=read,
        cache_write_5m_tokens=write_5m,
        cache_write_1h_tokens=write_1h,
    )


# --- the bound ---------------------------------------------------------------


def test_the_reservation_assumes_a_miss_at_the_write_rate() -> None:
    parts = (LONG_SYSTEM, "hello")
    plain = maximum_cost(OPUS, parts, 1024)
    five = maximum_cost(OPUS, parts, 1024, CacheTtl.FIVE_MINUTES)
    hour = maximum_cost(OPUS, parts, 1024, CacheTtl.ONE_HOUR)
    assert plain < five < hour
    # Input priced at 1.25x and 2x respectively; output unchanged.
    out = 1024 * OPUS.cost_per_mtok_out_usd / 1e6
    tokens = (plain - out) * 1e6 / OPUS.cost_per_mtok_in_usd
    assert five == pytest.approx(out + tokens * 6.25 / 1e6)
    assert hour == pytest.approx(out + tokens * 10.0 / 1e6)


def test_the_bound_never_falls_below_the_uncached_bound() -> None:
    parts = ("x" * 5_000,)
    assert maximum_cost(OPUS, parts, 100, CacheTtl.FIVE_MINUTES) >= maximum_cost(OPUS, parts, 100)


# --- the settlement ----------------------------------------------------------


def test_cost_components_price_each_figure_at_its_verified_rate() -> None:
    uncached, write, read, out = cost_components(
        OPUS, 40, 30, cache_read=5_000, cache_write_5m=0, cache_write_1h=0
    )
    assert uncached == pytest.approx(40 * 5.0 / 1e6)
    assert write == 0
    assert read == pytest.approx(5_000 * 0.50 / 1e6)
    assert out == pytest.approx(30 * 25.0 / 1e6)
    assert compute_cost(OPUS, 40, 30, cache_read=5_000) == pytest.approx(
        round(uncached + read + out, 6)
    )


def test_a_cold_write_costs_more_than_uncached_and_a_warm_read_far_less() -> None:
    plain = compute_cost(OPUS, 5_040, 30)
    cold_1h = compute_cost(OPUS, 40, 30, cache_write_1h=5_000)
    cold_5m = compute_cost(OPUS, 40, 30, cache_write_5m=5_000)
    warm = compute_cost(OPUS, 40, 30, cache_read=5_000)
    assert warm < plain < cold_5m < cold_1h


def test_an_unverified_route_prices_cache_figures_at_the_base_rate() -> None:
    unverified = OPUS.model_copy(
        update={
            "caching": PricingFeature.NOT_VERIFIED,
            "cache_write_5m_per_mtok_in_usd": None,
            "cache_write_1h_per_mtok_in_usd": None,
            "cache_read_per_mtok_in_usd": None,
            "cache_minimum_prefix_tokens": None,
        }
    )
    assert compute_cost(unverified, 40, 30, cache_read=5_000) == compute_cost(unverified, 5_040, 30)


# --- when the gateway asks for a cache ---------------------------------------


def _gateway(adapter: StubAdapter, ttl: CacheTtl | None) -> tuple[Gateway, list[CallRecord]]:
    rows: list[CallRecord] = []
    gateway, _, _, _ = build(adapters={"anthropic": adapter, "openai": adapter})
    gateway._cache_ttl = ttl
    original = gateway._record

    def recording(record: CallRecord) -> object:
        rows.append(record)
        return original(record)

    gateway._record = recording
    return gateway, rows


def test_a_partner_call_with_a_long_system_asks_for_the_configured_ttl() -> None:
    adapter = CachingStub(cached(read=5_000))
    gateway, rows = _gateway(adapter, CacheTtl.ONE_HOUR)
    response = gateway.complete_with_configuration(request(system=LONG_SYSTEM), OPUS)
    assert adapter.sent_cache_ttl is CacheTtl.ONE_HOUR
    assert response.tokens_in == 5_040, "the response reports the total input"
    record = rows[-1]
    assert record.tokens_in == 5_040
    assert record.cost_usd == compute_cost(OPUS, 40, 30, cache_read=5_000)
    assert record.cost_certainty is CostCertainty.KNOWN
    usage = record.cache_usage
    assert isinstance(usage, CacheUsage)
    assert usage.outcome == "hit" and usage.cache_read_tokens == 5_000
    assert usage.requested_ttl is CacheTtl.ONE_HOUR
    assert usage.cost_cache_read_usd == pytest.approx(5_000 * 0.50 / 1e6)


def test_a_cold_call_is_recorded_as_created() -> None:
    adapter = CachingStub(cached(read=0, write_1h=5_000))
    gateway, rows = _gateway(adapter, CacheTtl.ONE_HOUR)
    gateway.complete_with_configuration(request(system=LONG_SYSTEM), OPUS)
    usage = rows[-1].cache_usage
    assert usage is not None and usage.outcome == "created"
    assert usage.cost_cache_write_usd == pytest.approx(5_000 * 10.0 / 1e6)


def test_a_request_the_provider_did_not_cache_is_recorded_as_not_cached() -> None:
    adapter = CachingStub(cached(read=0, uncached=5_040))
    gateway, rows = _gateway(adapter, CacheTtl.FIVE_MINUTES)
    gateway.complete_with_configuration(request(system=LONG_SYSTEM), OPUS)
    usage = rows[-1].cache_usage
    assert usage is not None and usage.outcome == "not_cached"
    assert rows[-1].cost_usd == compute_cost(OPUS, 5_040, 30)


def test_no_ttl_configured_means_no_cache_requested_and_no_usage_row() -> None:
    adapter = CachingStub(ProviderResult("ok", TerminalState.COMPLETE, 5_040, 30, "r"))
    gateway, rows = _gateway(adapter, None)
    gateway.complete_with_configuration(request(system=LONG_SYSTEM), OPUS)
    assert adapter.sent_cache_ttl is None
    assert rows[-1].cache_usage is None


def test_a_prefix_below_the_models_minimum_is_not_requested() -> None:
    """Haiku's minimum is 4,096 tokens; the classifier's system is a few hundred."""
    adapter = CachingStub(ProviderResult("ok", TerminalState.COMPLETE, 700, 30, "r"))
    gateway, rows = _gateway(adapter, CacheTtl.ONE_HOUR)
    gateway.complete_with_configuration(request(system=SHORT_SYSTEM), HAIKU)
    assert adapter.sent_cache_ttl is None
    assert rows[-1].cache_usage is None


def test_an_unverified_route_is_never_asked_to_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    unverified = OPUS.model_copy(
        update={
            "caching": PricingFeature.NOT_VERIFIED,
            "cache_write_5m_per_mtok_in_usd": None,
            "cache_write_1h_per_mtok_in_usd": None,
            "cache_read_per_mtok_in_usd": None,
            "cache_minimum_prefix_tokens": None,
        }
    )
    adapter = CachingStub(ProviderResult("ok", TerminalState.COMPLETE, 5_040, 30, "r"))
    gateway, _ = _gateway(adapter, CacheTtl.ONE_HOUR)
    assert gateway._cache_ttl_for(unverified, request(system=LONG_SYSTEM)) is None


def test_the_reservation_is_taken_at_the_write_rate() -> None:
    adapter = CachingStub(cached(read=5_000))
    gateway, _ = _gateway(adapter, CacheTtl.ONE_HOUR)
    ledger: FakeLedger = gateway._ledger  # type: ignore[assignment]
    req = request(system=LONG_SYSTEM)
    gateway.complete_with_configuration(req, OPUS)
    from val_gateway.gateway import content_parts

    expected = maximum_cost(OPUS, content_parts(req), req.max_output_tokens, CacheTtl.ONE_HOUR)
    assert list(ledger.entries.values())[-1].max_cost_usd == pytest.approx(expected)


# --- the evidence row, against the real store --------------------------------


def test_the_cache_usage_row_is_written_with_the_call(ledger_engine: Engine) -> None:
    record = CallRecord(
        model_config_id=OPUS.id,
        slug=OPUS.slug,
        provider=OPUS.provider,
        model_identifier=OPUS.model_identifier,
        tokens_in=5_040,
        tokens_out=30,
        cost_usd=compute_cost(OPUS, 40, 30, cache_read=5_000),
        cost_certainty=CostCertainty.KNOWN,
        terminal_state="complete",
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
        task_type="conversation",
        conversation_id=None,
        message_id=None,
        persona_id=None,
        latency_ms=12,
        provider_request_id="r",
        status=__import__("val_domain.gateway", fromlist=["CallStatus"]).CallStatus.OK,
        cache_usage=CacheUsage(
            requested_ttl=CacheTtl.ONE_HOUR,
            uncached_input_tokens=40,
            cache_write_5m_tokens=0,
            cache_write_1h_tokens=0,
            cache_read_tokens=5_000,
            outcome="hit",
            cost_uncached_usd=0.0002,
            cost_cache_write_usd=0.0,
            cost_cache_read_usd=0.0025,
            cost_output_usd=0.00075,
        ),
    )
    call_id = record_call(ledger_engine, record)
    with ledger_engine.connect() as connection:
        row = connection.execute(
            text(
                "select requested_ttl, cache_read_tokens, outcome, cost_cache_read "
                "from model_call_cache_usage where model_call_id = :id"
            ),
            {"id": call_id},
        ).one()
        total = connection.execute(
            text("select tokens_in, cost from model_calls where id = :id"), {"id": call_id}
        ).one()
    assert row.requested_ttl == "1h" and row.cache_read_tokens == 5_000 and row.outcome == "hit"
    assert row.cost_cache_read == Decimal("0.002500")
    assert total.tokens_in == 5_040
    with (
        pytest.raises(Exception, match=r"evidence|forbid|not allowed|denied"),
        ledger_engine.begin() as connection,
    ):
        connection.execute(
            text("update model_call_cache_usage set outcome = 'created' where model_call_id = :id"),
            {"id": call_id},
        )


# --- configuration -----------------------------------------------------------


def test_the_ttl_is_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CACHE_TTL_SETTING, raising=False)
    assert configured_cache_ttl() == (None, None)
    monkeypatch.setenv(CACHE_TTL_SETTING, "1h")
    assert configured_cache_ttl() == (CacheTtl.ONE_HOUR, None)
    monkeypatch.setenv(CACHE_TTL_SETTING, "5m")
    assert configured_cache_ttl() == (CacheTtl.FIVE_MINUTES, None)
    monkeypatch.setenv(CACHE_TTL_SETTING, "off")
    assert configured_cache_ttl() == (None, None)
    monkeypatch.setenv(CACHE_TTL_SETTING, "2h")
    ttl, problem = configured_cache_ttl()
    assert ttl is None and problem is not None and "2h" in problem


def test_the_registry_declares_verified_cache_rates_on_the_partner_route() -> None:
    assert OPUS.caching is PricingFeature.AVAILABLE
    assert (OPUS.cache_write_5m_per_mtok_in_usd, OPUS.cache_write_1h_per_mtok_in_usd) == (
        6.25,
        10.0,
    )
    assert OPUS.cache_read_per_mtok_in_usd == 0.5 and OPUS.cache_minimum_prefix_tokens == 512


def test_cache_rates_travel_only_with_verified_caching() -> None:
    with pytest.raises(ValueError, match="rates on an unverified route"):
        ModelConfig.model_validate(
            OPUS.model_dump() | {"caching": PricingFeature.NOT_VERIFIED, "id": OPUS.id}
        )
    with pytest.raises(ValueError, match="missing"):
        ModelConfig.model_validate(
            OPUS.model_dump() | {"cache_read_per_mtok_in_usd": None, "id": OPUS.id}
        )


def _unused(_: Mapping[str, object], __: Message) -> None:  # keeps the imports honest
    return None
