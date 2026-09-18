"""The hosting axis, unmetered pricing and the first local entry — ruling of 16 September 2026."""

from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

from val_domain.gateway import (
    Admission,
    Classification,
    Hosting,
    Metering,
    ModelConfig,
    PricingFeature,
    QualificationTarget,
    ReasoningEffort,
)
from val_domain.registry import REGISTRY, active, by_slug, live_routes, under_evaluation

LOCAL = "gpt-oss-20b-mxfp4-mlx-lmstudio"


def _local() -> ModelConfig:
    config = by_slug(LOCAL)
    assert config is not None
    return config


def _entry(**overrides: object) -> ModelConfig:
    base = _local().model_dump()
    base.update(overrides)
    return ModelConfig(**base)


# --- validators ------------------------------------------------------------------------


def test_a_zero_rate_on_a_metered_route_is_refused() -> None:
    sol = by_slug("gpt-5-6-sol-medium")
    assert sol is not None
    with pytest.raises(ValueError, match="fabricated cost"):
        ModelConfig(**{**sol.model_dump(), "cost_per_mtok_in_usd": 0.0})
    with pytest.raises(ValueError, match="fabricated cost"):
        ModelConfig(**{**sol.model_dump(), "cost_per_mtok_out_usd": 0.0})


def test_unmetered_requires_exactly_zero_rates_local_hosting_and_no_cache_pricing() -> None:
    assert _local().metering is Metering.LOCAL_NO_METERED_COST
    with pytest.raises(ValueError, match="exactly zero"):
        _entry(cost_per_mtok_in_usd=0.5)
    with pytest.raises(ValueError, match="LOCAL hosting"):
        _entry(hosting=Hosting.CLOUD)
    with pytest.raises(ValueError, match="no cache pricing"):
        _entry(
            caching=PricingFeature.AVAILABLE,
            cache_write_auto_per_mtok_in_usd=1.0,
            cache_read_per_mtok_in_usd=0.1,
            cache_minimum_prefix_tokens=1024,
        )


def test_an_unmetered_cloud_entry_is_not_a_thing_the_registry_can_describe() -> None:
    with pytest.raises(ValueError):
        _entry(provider="openai", hosting=Hosting.CLOUD)


def test_defaults_are_cloud_and_metered() -> None:
    sol = by_slug("gpt-5-6-sol-medium")
    assert sol is not None
    assert sol.hosting is Hosting.CLOUD and sol.metering is Metering.METERED
    assert all(c.hosting is Hosting.CLOUD for c in REGISTRY if c.provider != "lmstudio")
    assert all(c.metering is Metering.METERED for c in REGISTRY if c.provider != "lmstudio")


# --- the registered local entry --------------------------------------------------------


def test_the_local_entry_is_exactly_as_ruled() -> None:
    config = _local()
    assert config.id == UUID("aac13204-3b27-477d-8bc4-ced543f61ae3")
    assert config.provider == "lmstudio"
    assert config.model_identifier == "openai/gpt-oss-20b"
    assert config.hosting is Hosting.LOCAL
    assert config.metering is Metering.LOCAL_NO_METERED_COST
    assert (config.cost_per_mtok_in_usd, config.cost_per_mtok_out_usd) == (0.0, 0.0)
    assert config.admission is Admission.NOT_ADMITTED
    assert config.capability_profiles == frozenset(), "no production profile"
    assert config.qualification_targets == frozenset({QualificationTarget.PARTNER})
    assert config.fallback_slug is None
    assert config.caching is PricingFeature.NOT_VERIFIED and not config.caches_automatically
    assert config.activated_on == date(2026, 9, 16) and config.rates_verified_on == date(
        2026, 9, 16
    )
    assert config.last_live_call_on is None, "set only from an observed live-store row"
    assert config.owner_authorization is None


def test_eligibility_is_exactly_the_incumbent_partner_routes_non_restricted_set() -> None:
    incumbent = by_slug("opus-5-medium")
    sol = by_slug("gpt-5-6-sol-medium")
    assert incumbent is not None and sol is not None
    assert _local().eligible_classifications == incumbent.eligible_classifications
    assert _local().eligible_classifications == sol.eligible_classifications
    assert Classification.RESTRICTED not in _local().eligible_classifications
    assert _local().eligible_classifications == frozenset(
        {Classification.PUBLIC, Classification.INTERNAL, Classification.PROTECTED}
    )


def test_the_local_entry_is_under_evaluation_and_nowhere_near_routing() -> None:
    config = _local()
    assert config in under_evaluation()
    assert config not in active()
    assert config not in live_routes()
    assert {c.slug for c in live_routes()} == {"gpt-5-6-sol-medium"}, "production unchanged"
    assert all(c.fallback_slug != LOCAL for c in REGISTRY), "nobody's fallback"


# --- the Qwen3.8-27B challenger entry (owner ruling, 16 September 2026) ----------------------


def test_the_qwen_challenger_is_evaluation_only_local_unmetered_and_medium() -> None:
    config = by_slug("qwen3-8-27b-mlx-6bit-lmstudio")
    assert config is not None
    assert config.provider == "lmstudio"
    # LM Studio's own canonical runtime id for lmstudio-community/Qwen3.8-27B-MLX-6bit.
    assert config.model_identifier == "qwen3.8-27b-mlx"
    assert config.hosting is Hosting.LOCAL
    assert config.metering is Metering.LOCAL_NO_METERED_COST
    assert config.cost_per_mtok_in_usd == 0.0 and config.cost_per_mtok_out_usd == 0.0
    assert config.admission is Admission.NOT_ADMITTED
    assert config.capability_profiles == frozenset(), "no production profile"
    assert config.qualification_targets == frozenset({QualificationTarget.PARTNER})
    assert config.fallback_slug is None
    assert config.reasoning_effort is ReasoningEffort.MEDIUM, "never xhigh, never low"
    assert config.temperature is None, "no VAL-specific sampling override"
    assert config.context_window_tokens == 32_768
    incumbent_local = by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio")
    assert incumbent_local is not None
    assert config.eligible_classifications == incumbent_local.eligible_classifications


def test_the_local_entries_are_distinct_evaluation_only_entries() -> None:
    # Pin moved 17 September 2026 (owner ruling): the Category-A Mistral challenger
    # joins the two earlier local evaluation entries; all three NOT_ADMITTED, no profile.
    local = [c for c in REGISTRY if c.provider == "lmstudio"]
    assert {c.slug for c in local} == {
        "gpt-oss-20b-mxfp4-mlx-lmstudio",
        "qwen3-8-27b-mlx-6bit-lmstudio",
        "mistral-small-3-2-24b-8bit-mlx-lmstudio",
    }
    assert len({c.id for c in local}) == 3 and len({c.model_identifier for c in local}) == 3
    assert all(c.admission is Admission.NOT_ADMITTED and not c.capability_profiles for c in local)


# --- the Mistral Small 3.2 Category-A challenger (owner ruling, 17 September 2026) --------


def test_the_mistral_challenger_is_category_a_local_unmetered_and_evaluation_only() -> None:
    config = by_slug("mistral-small-3-2-24b-8bit-mlx-lmstudio")
    assert config is not None
    assert config.provider == "lmstudio"
    # LM Studio's own canonical runtime id for
    # lmstudio-community/Mistral-Small-3.2-24B-Instruct-2506-MLX-8bit.
    assert config.model_identifier == "mistral-small-3.2-24b-instruct-2506-mlx"
    assert config.reasoning_effort is ReasoningEffort.NOT_APPLICABLE, "Category A: no control"
    assert config.temperature is None, "no VAL-specific sampling override"
    assert config.hosting is Hosting.LOCAL
    assert config.metering is Metering.LOCAL_NO_METERED_COST
    assert config.cost_per_mtok_in_usd == 0.0 and config.cost_per_mtok_out_usd == 0.0
    assert config.admission is Admission.NOT_ADMITTED
    assert config.capability_profiles == frozenset()
    assert config.qualification_targets == frozenset({QualificationTarget.PARTNER})
    assert config.fallback_slug is None
    assert config.context_window_tokens == 32_768
