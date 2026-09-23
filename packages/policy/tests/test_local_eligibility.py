"""Local provider eligibility and the zero bound — ruling of 16 September 2026.

Local is not a policy bypass: the ruled providers include `lmstudio`, a local
provider must declare the local hosting axis and only a local provider may,
Restricted stays refused for every route, and the monetary bound of an
unmetered route is zero without weakening anything the ceiling protects.
"""

from __future__ import annotations

from val_domain.gateway import Classification, GatewayErrorKind, Hosting, ModelConfig
from val_domain.registry import REGISTRY, active, by_slug, under_evaluation
from val_policy.budget import CLOUD_CEILING_USD, admits, maximum_cost
from val_policy.eligibility import (
    LOCAL_PROVIDERS,
    RULED_PROVIDERS,
    refusal_for,
    startup_violations,
)
from val_policy.routing import is_eligible


def _local() -> ModelConfig:
    config = by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio")
    assert config is not None
    return config


def test_lmstudio_is_a_ruled_local_provider_and_the_rosters_agree() -> None:
    assert "lmstudio" in RULED_PROVIDERS and "lmstudio" in LOCAL_PROVIDERS
    assert LOCAL_PROVIDERS <= RULED_PROVIDERS
    assert {"anthropic", "openai", "google"} <= RULED_PROVIDERS - LOCAL_PROVIDERS


def test_the_whole_registry_passes_the_startup_rules_including_the_evaluation_entry() -> None:
    assert startup_violations(list(active()) + list(under_evaluation())) == []
    assert startup_violations([c for c in REGISTRY if not c.retired]) == []


def test_a_local_provider_without_the_local_axis_or_the_reverse_is_a_violation() -> None:
    cloud_wearing_local = ModelConfig(
        **{
            **_local().model_dump(),
            "provider": "openai",
            "metering": "metered",
            "cost_per_mtok_in_usd": 1.0,
            "cost_per_mtok_out_usd": 1.0,
        }
    )
    problems = startup_violations([cloud_wearing_local])
    assert any("hosting axis disagree" in p for p in problems)
    sol = by_slug("gpt-5-6-sol-medium")
    assert sol is not None
    local_provider_cloud_axis = ModelConfig(
        **{**sol.model_dump(), "provider": "lmstudio", "hosting": Hosting.CLOUD}
    )
    problems = startup_violations([local_provider_cloud_axis])
    assert any("hosting axis disagree" in p for p in problems)


def test_restricted_stays_refused_for_the_local_route_and_the_check_is_unmodified() -> None:
    assert is_eligible(_local(), Classification.PROTECTED)
    assert is_eligible(_local(), Classification.INTERNAL)
    assert not is_eligible(_local(), Classification.RESTRICTED)
    refusal = refusal_for(Classification.RESTRICTED, _local())
    assert refusal is not None and refusal[0] is GatewayErrorKind.RESTRICTED_CONTENT
    assert "separate ruling not yet made" in refusal[1]
    assert refusal_for(Classification.PROTECTED, _local()) is None


def test_the_monetary_bound_of_an_unmetered_route_is_zero_and_the_ceiling_still_binds_others() -> (
    None
):
    parts = ("persona " * 2_000, "history " * 3_000)
    assert maximum_cost(_local(), parts, 6_144) == 0.0
    assert admits(CLOUD_CEILING_USD, 0.0), "a zero bound fits even at the ceiling"
    sol = by_slug("gpt-5-6-sol-medium")
    assert sol is not None
    assert maximum_cost(sol, parts, 6_144) > 0.0
    assert not admits(CLOUD_CEILING_USD, maximum_cost(sol, parts, 6_144)), "metered still refused"


# --- the second ruled LOCAL provider (owner ruling, 18 September 2026) ------------------------


def _llamacpp() -> ModelConfig:
    return ModelConfig(
        **{
            **_local().model_dump(),
            "provider": "llamacpp",
            "slug": "llamacpp-test-entry",
            "reasoning_effort": "not_applicable",
        }
    )


def test_llamacpp_is_a_ruled_local_provider_beside_lmstudio() -> None:
    # Four, since 22 September 2026: the two local text runtimes, `mlxvlm` (the
    # visual-perception runtime) and `llamacpp-omni` (the audio one). The last
    # two are local in the strongest sense available — subprocesses of this
    # machine, with no socket at all.
    assert {"lmstudio", "llamacpp", "llamacpp-omni", "mlxvlm"} == set(LOCAL_PROVIDERS)
    assert "llamacpp" in RULED_PROVIDERS and LOCAL_PROVIDERS <= RULED_PROVIDERS


def test_a_llamacpp_entry_follows_the_same_local_contract() -> None:
    config = _llamacpp()
    assert startup_violations([config]) == []
    assert is_eligible(config, Classification.PROTECTED)
    assert not is_eligible(config, Classification.RESTRICTED), "Restricted stays excluded"
    wearing_cloud = ModelConfig(
        **{
            **config.model_dump(),
            "hosting": Hosting.CLOUD,
            "metering": "metered",
            "cost_per_mtok_in_usd": 1.0,
            "cost_per_mtok_out_usd": 1.0,
        }
    )
    assert any("hosting axis disagree" in p for p in startup_violations([wearing_cloud]))
