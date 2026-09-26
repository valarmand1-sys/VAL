"""Which configuration carries the Tier-1 request in a candidate build — owner order of
26 September 2026 ("COMPARE EXISTING TIER-1 OPTIONS"). The selector promotes exactly one
entry for this process, never on disk; `low` is the same GPT-OSS instance at LOW and is
not an admission of LOW; without the fast-route switch nothing is promoted at all.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

import val_domain.registry as registry
from val_domain.gateway import Admission, CapabilityProfile, ReasoningEffort
from val_gateway.startup import (
    TIER1_ROUTES,
    configured_tier1_route,
    enable_light_candidate,
)


@pytest.fixture
def restored_registry() -> Iterator[None]:
    before = registry.REGISTRY
    try:
        yield
    finally:
        registry.REGISTRY = before


def test_the_selector_defaults_to_qwen_and_refuses_anything_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VAL_TIER1_ROUTE", raising=False)
    assert configured_tier1_route() == ("qwen", None)
    monkeypatch.setenv("VAL_TIER1_ROUTE", "LOW")
    assert configured_tier1_route() == ("low", None)
    monkeypatch.setenv("VAL_TIER1_ROUTE", "high")
    assert configured_tier1_route()[1] is not None


@pytest.mark.parametrize("route", sorted(TIER1_ROUTES))
def test_each_route_promotes_one_entry_to_the_light_floor(
    route: str, restored_registry: None
) -> None:
    promoted = enable_light_candidate(route)
    assert promoted.slug == TIER1_ROUTES[route]
    assert CapabilityProfile.LIGHT in promoted.capability_profiles
    assert promoted.admission is Admission.PROVISIONALLY_ADMITTED
    light = [c for c in registry.active() if CapabilityProfile.LIGHT in c.capability_profiles]
    assert [c.slug for c in light] == [promoted.slug], "exactly one light configuration"


def test_low_is_the_same_instance_at_low_effort_and_medium_keeps_its_partner_profile(
    restored_registry: None,
) -> None:
    low = enable_light_candidate("low")
    medium = registry.by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio-partner")
    assert medium is not None
    assert low.model_identifier == medium.model_identifier == "openai/gpt-oss-20b"
    assert low.reasoning_effort is ReasoningEffort.LOW
    assert medium.reasoning_effort is ReasoningEffort.MEDIUM
    assert CapabilityProfile.PARTNER not in low.capability_profiles, "LOW carries no partner work"
    registry.REGISTRY = registry.REGISTRY  # the fixture restores it below
    promoted_medium = enable_light_candidate("medium")
    assert CapabilityProfile.PARTNER in promoted_medium.capability_profiles
    assert CapabilityProfile.LIGHT in promoted_medium.capability_profiles


def test_the_registry_on_disk_is_unchanged_afterwards() -> None:
    low = registry.by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio-low")
    assert low is not None and low.admission is Admission.NOT_ADMITTED
    assert low.capability_profiles == frozenset()
    medium = registry.by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio-partner")
    assert medium is not None and CapabilityProfile.LIGHT not in medium.capability_profiles
