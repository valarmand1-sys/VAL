"""Automatic provider caching, priced — ruling, 14 September 2026.

GPT-5.6 caches on its own: no lifetime is requested, and the provider reports
what it read and wrote. The registry carries the one verified automatic write
rate beside the read rate; settlement prices the three disjoint input figures
at base, read and write; the cold bound prices the whole input at the write
rate; the long-context transition stacks on all three. Anthropic's requested-
lifetime semantics are untouched.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from val_domain.gateway import (
    AdapterStatus,
    Admission,
    CacheTtl,
    Classification,
    ModelConfig,
    PricingFeature,
    ReasoningEffort,
)
from val_domain.provider import ProviderResult, TerminalState
from val_domain.registry import by_slug
from val_gateway.gateway import compute_cost, cost_components
from val_policy.budget import maximum_cost, upper_bound_input_tokens, upper_bound_output_tokens


def sol() -> ModelConfig:
    config = by_slug("gpt-5-6-sol-medium")
    assert config is not None
    return config


def opus() -> ModelConfig:
    config = by_slug("opus-5-medium")
    assert config is not None
    return config


# --- the registry entry -----------------------------------------------------------


def test_sol_declares_verified_automatic_caching_at_the_documented_rates() -> None:
    config = sol()
    assert config.caching is PricingFeature.AVAILABLE and config.caches_automatically
    assert config.cache_write_auto_per_mtok_in_usd == 5.00
    assert config.cache_read_per_mtok_in_usd == 0.40
    assert config.cache_minimum_prefix_tokens == 1_024
    assert config.cache_write_5m_per_mtok_in_usd is None
    assert config.cache_write_1h_per_mtok_in_usd is None


def test_anthropic_routes_are_untouched() -> None:
    config = opus()
    assert not config.caches_automatically
    assert config.cache_write_auto_per_mtok_in_usd is None
    assert (config.cache_write_5m_per_mtok_in_usd, config.cache_write_1h_per_mtok_in_usd) == (
        6.25,
        10.0,
    )


def _entry(**overrides: object) -> ModelConfig:
    base: dict[str, object] = dict(
        id=uuid4(),
        slug="shape-check",
        provider="openai",
        model_identifier="x",
        display_name="x",
        context_window_tokens=1_000,
        max_output_tokens=100,
        reasoning_effort=ReasoningEffort.NONE,
        cost_per_mtok_in_usd=4.0,
        cost_per_mtok_out_usd=20.0,
        caching=PricingFeature.AVAILABLE,
        cache_read_per_mtok_in_usd=0.4,
        cache_minimum_prefix_tokens=1_024,
        eligible_classifications=frozenset({Classification.PUBLIC}),
        capability_profiles=frozenset(),
        fallback_slug=None,
        admission=Admission.NOT_ADMITTED,
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=date(2026, 9, 14),
        rates_verified_on=date(2026, 9, 14),
    )
    base.update(overrides)
    return ModelConfig(**base)  # type: ignore[arg-type]


def test_the_two_cache_shapes_are_exclusive_and_each_complete() -> None:
    _entry(cache_write_auto_per_mtok_in_usd=5.0)
    _entry(cache_write_5m_per_mtok_in_usd=5.0, cache_write_1h_per_mtok_in_usd=8.0)
    with pytest.raises(ValueError, match="missing or mixed"):
        _entry()  # verified, but no write rate of either shape
    with pytest.raises(ValueError, match="missing or mixed"):
        _entry(cache_write_auto_per_mtok_in_usd=5.0, cache_write_1h_per_mtok_in_usd=8.0)
    with pytest.raises(ValueError, match="missing or mixed"):
        _entry(cache_write_5m_per_mtok_in_usd=5.0)  # half a requested pair
    with pytest.raises(ValueError, match="unverified route"):
        _entry(caching=PricingFeature.NOT_VERIFIED, cache_write_auto_per_mtok_in_usd=5.0)


# --- settlement -------------------------------------------------------------------


def test_no_cache_input_is_priced_at_base() -> None:
    assert compute_cost(sol(), 1_000, 100) == pytest.approx(1_000 * 4 / 1e6 + 100 * 20 / 1e6)


def test_an_automatic_write_is_priced_at_the_write_rate_only() -> None:
    uncached, writes, reads, output = cost_components(sol(), 500, 100, cache_write_auto=2_000)
    assert uncached == pytest.approx(500 * 4 / 1e6)
    assert writes == pytest.approx(2_000 * 5 / 1e6), "written tokens at 1.25x base, once"
    assert reads == 0
    assert output == pytest.approx(100 * 20 / 1e6)


def test_an_automatic_read_is_priced_at_the_read_rate_only() -> None:
    uncached, writes, reads, _ = cost_components(sol(), 500, 100, cache_read=2_000)
    assert uncached == pytest.approx(500 * 4 / 1e6)
    assert writes == 0
    assert reads == pytest.approx(2_000 * 0.4 / 1e6)


def test_mixed_usage_prices_each_figure_once_and_sums_the_input() -> None:
    components = cost_components(sol(), 464, 300, cache_read=1_024, cache_write_auto=512)
    expected = (464 * 4 / 1e6, 512 * 5 / 1e6, 1_024 * 0.4 / 1e6, 300 * 20 / 1e6)
    assert components == pytest.approx(expected)
    assert compute_cost(sol(), 464, 300, cache_read=1_024, cache_write_auto=512) == round(
        sum(expected), 6
    )


def test_the_adapters_three_input_figures_are_disjoint_so_nothing_is_double_counted() -> None:
    """The mapping the OpenAI adapter performs, as the gateway consumes it."""
    result = ProviderResult(
        "x",
        TerminalState.COMPLETE,
        464,
        300,
        "r",
        cache_read_tokens=1_024,
        cache_write_auto_tokens=512,
    )
    assert result.total_input_tokens == 2_000
    total = compute_cost(
        sol(),
        result.tokens_in,
        result.tokens_out or 0,
        cache_read=result.cache_read_tokens or 0,
        cache_write_auto=result.cache_write_auto_tokens or 0,
    )
    twice = compute_cost(sol(), 2_000, 300, cache_read=1_024, cache_write_auto=512)
    assert total < twice, "written and read tokens are not also charged as uncached input"


def test_long_context_multiplies_base_read_and_write_rates_alike() -> None:
    config = sol()
    assert config.long_context_threshold_tokens == 272_000
    uncached, writes, reads, output = cost_components(
        config, 100_000, 1_000, cache_read=100_000, cache_write_auto=100_000
    )
    assert uncached == pytest.approx(100_000 * 8 / 1e6)
    assert writes == pytest.approx(100_000 * 10 / 1e6)
    assert reads == pytest.approx(100_000 * 0.8 / 1e6)
    assert output == pytest.approx(1_000 * 30 / 1e6)


def test_missing_usage_stays_unknown() -> None:
    result = ProviderResult("x", TerminalState.COMPLETE, None, None, "r")
    assert result.total_input_tokens is None
    assert result.cache_write_auto_tokens is None and result.cache_read_tokens is None


def test_an_unverified_route_prices_reported_figures_at_base_never_cheaper() -> None:
    terra = by_slug("gpt-5-6-terra")
    assert terra is not None and terra.caching is PricingFeature.NOT_VERIFIED
    uncached, writes, reads, _ = cost_components(
        terra, 100, 10, cache_read=100, cache_write_auto=100
    )
    assert uncached == writes == reads == pytest.approx(100 * 2 / 1e6)


# --- the cold bound -----------------------------------------------------------------


def test_the_cold_bound_prices_every_input_token_at_the_automatic_write_rate() -> None:
    config = sol()
    parts = ("x" * 10_000,)
    tokens_in = upper_bound_input_tokens(parts, config)
    tokens_out = upper_bound_output_tokens(4_096, config)
    bound = maximum_cost(config, parts, 4_096)
    assert bound == pytest.approx((tokens_in * 5.0 + tokens_out * 20.0) / 1e6)
    assert bound > (tokens_in * 4.0 + tokens_out * 20.0) / 1e6
    assert maximum_cost(config, parts, 4_096, CacheTtl.ONE_HOUR) == pytest.approx(bound), (
        "a requested lifetime changes nothing on an automatically caching route"
    )


def test_the_cold_bound_covers_a_call_that_writes_everything() -> None:
    config = sol()
    parts = ("x" * 10_000,)
    bound = maximum_cost(config, parts, 4_096)
    tokens_in = upper_bound_input_tokens(parts, config)
    settled = compute_cost(config, 0, 4_096, cache_write_auto=tokens_in)
    assert settled <= bound


def test_the_cold_bound_stacks_the_long_context_multiplier_on_the_write_rate() -> None:
    config = sol()
    parts = ("x" * 300_000,)
    tokens_in = upper_bound_input_tokens(parts, config)
    assert tokens_in > 272_000
    tokens_out = upper_bound_output_tokens(4_096, config)
    assert maximum_cost(config, parts, 4_096) == pytest.approx(
        (tokens_in * 10.0 + tokens_out * 30.0) / 1e6
    )


def test_anthropic_bounds_are_unchanged() -> None:
    config = opus()
    parts = ("x" * 10_000,)
    tokens_in = upper_bound_input_tokens(parts, config)
    tokens_out = upper_bound_output_tokens(4_096, config)
    assert maximum_cost(config, parts, 4_096) == pytest.approx(
        (tokens_in * 5.0 + tokens_out * 25.0) / 1e6
    )
    assert maximum_cost(config, parts, 4_096, CacheTtl.ONE_HOUR) == pytest.approx(
        (tokens_in * 10.0 + tokens_out * 25.0) / 1e6
    )
