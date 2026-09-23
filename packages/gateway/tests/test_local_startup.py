"""Startup wiring for the local provider — ruling of 16 September 2026.

When the LM Studio token is required, and when it is not: `start()` builds
adapters for the providers of `active()` routes, and an evaluation-only entry
is not active, so the production service does not need the token while no
local route is admitted; any construction of the `lmstudio` adapter — the
candidate and evaluation harnesses — requires it and refuses without it. The
base URL comes from `VAL_LMSTUDIO_BASE_URL` and a non-loopback host is a
stated startup problem, never a running adapter.
"""

from __future__ import annotations

import inspect

import pytest

from val_domain.gateway import CapabilityProfile
from val_domain.registry import active, under_evaluation
from val_gateway import startup
from val_gateway.startup import (
    KEY_VARIABLES,
    LMSTUDIO_BASE_URL_SETTING,
    build_adapters,
    configured_lmstudio_base_url,
)
from val_policy.routing import satisfies_profile
from val_providers.lmstudio_adapter import DEFAULT_BASE_URL, LMStudioAdapter


@pytest.fixture(autouse=True)
def _no_native_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never touch the network from a unit test."""
    monkeypatch.setattr(LMStudioAdapter, "_read_native_models", lambda self: {})


def test_the_token_variable_is_named_and_the_base_url_defaults_to_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert KEY_VARIABLES["lmstudio"] == "VAL_LMSTUDIO_API_TOKEN"
    monkeypatch.delenv(LMSTUDIO_BASE_URL_SETTING, raising=False)
    assert configured_lmstudio_base_url() == DEFAULT_BASE_URL == "http://127.0.0.1:1234/v1"


def test_production_startup_now_requires_the_local_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owner admission ruling, 21 September 2026 — and this test says the opposite of before.

    While the only local entry was evaluation-only, the production service built
    no `lmstudio` adapter and needed no token; that was this test's subject and
    it was correct. Admitting a local Partner route reverses it: `start()` builds
    adapters for `active()` providers, the local route is now one of them, and a
    service without the token stops rather than running without the route Val
    thinks on. The deployment consequence is that the token belongs in the
    installed LaunchAgent, which is where it is.
    """
    # The set `start()` actually passes. Since 22 September 2026 it excludes
    # perception and speech routes, which have no `ProviderAdapter` and are not
    # conversation routes — a specialist never has to pretend to be a chat
    # provider to get past that line. Everything else here is unchanged.
    specialists = (CapabilityProfile.PERCEPTION, CapabilityProfile.SPEECH)
    production = {
        config.provider
        for config in active()
        if not any(satisfies_profile(config, profile) for profile in specialists)
    }
    assert "lmstudio" in production, "the admitted local Partner route is in production"
    assert "mlxvlm" not in production, "the perception route is not a conversation adapter"
    assert "mlxaudio" not in production, "the speech route is not a conversation adapter"
    # The candidates are still evaluation-only beside it, and still absent here.
    assert "lmstudio" in {config.provider for config in under_evaluation()}
    source = inspect.getsource(startup.start)
    assert "build_adapters(" in source and "CapabilityProfile.PERCEPTION" in source
    monkeypatch.delenv("VAL_LMSTUDIO_API_TOKEN", raising=False)
    monkeypatch.setenv("VAL_ANTHROPIC_API_KEY", "not-a-real-value")
    monkeypatch.setenv("VAL_OPENAI_API_KEY", "not-a-real-value")
    adapters, problems = build_adapters(production)
    # Without the token the service refuses to start, naming the reason. It does
    # not come up quietly with Val's own route missing, because that is a house
    # with no local cognition pretending to be a working one.
    assert "lmstudio" not in adapters
    assert len(problems) == 1 and "VAL_LMSTUDIO_API_TOKEN" in problems[0]


def test_constructing_the_local_adapter_requires_the_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VAL_LMSTUDIO_API_TOKEN", raising=False)
    adapters, problems = build_adapters({"lmstudio"})
    assert adapters == {}
    assert len(problems) == 1 and "VAL_LMSTUDIO_API_TOKEN is not set" in problems[0]


def test_a_non_loopback_base_url_is_a_stated_startup_problem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VAL_LMSTUDIO_API_TOKEN", "not-a-real-value")
    monkeypatch.setenv(LMSTUDIO_BASE_URL_SETTING, "http://192.168.1.20:1234/v1")
    adapters, problems = build_adapters({"lmstudio"})
    assert adapters == {}
    assert len(problems) == 1 and "must name this machine" in problems[0]
    assert "not-a-real-value" not in problems[0]


def test_with_the_token_and_a_loopback_url_the_adapter_is_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VAL_LMSTUDIO_API_TOKEN", "not-a-real-value")
    monkeypatch.delenv(LMSTUDIO_BASE_URL_SETTING, raising=False)
    adapters, problems = build_adapters({"lmstudio"})
    assert problems == []
    assert (
        isinstance(adapters["lmstudio"], LMStudioAdapter)
        and adapters["lmstudio"].name == "lmstudio"
    )


def test_core_never_imports_the_local_adapter() -> None:
    import val_gateway.deliberate
    import val_gateway.gateway
    import val_gateway.loop

    for module in (val_gateway.gateway, val_gateway.loop, val_gateway.deliberate):
        assert "lmstudio" not in inspect.getsource(module).lower()


# --- the second LOCAL provider (owner ruling, 18 September 2026) -------------------------------


def test_llamacpp_has_its_own_dedicated_key_and_a_loopback_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from val_gateway.startup import LLAMACPP_BASE_URL_SETTING, configured_llamacpp_base_url

    assert KEY_VARIABLES["llamacpp"] == "VAL_LLAMACPP_API_KEY"
    assert KEY_VARIABLES["llamacpp"] != KEY_VARIABLES["lmstudio"], "never the LM Studio token"
    monkeypatch.delenv(LLAMACPP_BASE_URL_SETTING, raising=False)
    assert configured_llamacpp_base_url() == "http://127.0.0.1:8766/v1"


def test_constructing_the_llamacpp_adapter_requires_its_key_and_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from val_gateway.startup import LLAMACPP_BASE_URL_SETTING
    from val_providers.llamacpp_adapter import LlamaCppAdapter

    monkeypatch.delenv("VAL_LLAMACPP_API_KEY", raising=False)
    adapters, problems = build_adapters({"llamacpp"})
    assert adapters == {} and "VAL_LLAMACPP_API_KEY is not set" in problems[0]
    monkeypatch.setenv("VAL_LLAMACPP_API_KEY", "not-a-real-value")
    adapters, problems = build_adapters({"llamacpp"})
    assert problems == [] and isinstance(adapters["llamacpp"], LlamaCppAdapter)
    monkeypatch.setenv(LLAMACPP_BASE_URL_SETTING, "http://192.168.1.20:8766/v1")
    adapters, problems = build_adapters({"llamacpp"})
    assert adapters == {} and "must name this machine" in problems[0]


def test_production_startup_builds_no_llamacpp_adapter() -> None:
    assert "llamacpp" not in {config.provider for config in active()}
