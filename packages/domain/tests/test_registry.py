"""Tests for the Model Configuration Registry.

The registry is what `model_calls.model_config_id` resolves through, so its
invariants are about history holding rather than about routing being clever.
"""

import pytest

from val_domain.gateway import Classification
from val_domain.registry import REGISTRY, active, by_id, by_slug, cheapest


def test_ids_and_slugs_are_unique() -> None:
    """Two entries sharing either key would make history ambiguous."""
    assert len({c.id for c in REGISTRY}) == len(REGISTRY)
    assert len({c.slug for c in REGISTRY}) == len(REGISTRY)


def test_every_entry_carries_a_slug_beside_its_uuid() -> None:
    """Lord Armand reads slugs; the database stores UUIDs. Both, always."""
    for config in REGISTRY:
        assert config.slug
        assert config.id


def test_at_least_two_providers_are_configured() -> None:
    """WP-0.4 requires two providers minimum, both Protected-eligible."""
    assert len({c.provider for c in active()}) >= 2


def test_every_active_route_is_protected_eligible() -> None:
    """Layer 0's guarantee is structural: no ineligible route exists (§1.1)."""
    for config in active():
        assert Classification.PROTECTED in config.eligible_classifications


def test_no_route_claims_restricted_eligibility() -> None:
    """Restricted routes to local inference only, which arrives at Layer 1."""
    for config in REGISTRY:
        assert Classification.RESTRICTED not in config.eligible_classifications


def test_every_rate_is_positive() -> None:
    """A zero rate would silently record every call as free."""
    for config in REGISTRY:
        assert config.cost_per_mtok_in_usd > 0
        assert config.cost_per_mtok_out_usd > 0


def test_cheapest_is_the_least_expensive_active_route() -> None:
    """The strip step of 04-layer-0.md §4 runs here until Layer 1."""
    assert cheapest().cost_per_mtok_in_usd == min(c.cost_per_mtok_in_usd for c in active())


def test_retired_entries_still_resolve() -> None:
    """A retired configuration must still resolve historically (§2.2)."""
    for config in REGISTRY:
        assert by_id(config.id) is config
        assert by_slug(config.slug) is config


def test_unknown_lookups_return_none_rather_than_raising() -> None:
    """A missing id is a data question, not a crash."""
    from uuid import uuid4

    assert by_id(uuid4()) is None
    assert by_slug("no-such-route") is None


@pytest.mark.parametrize("config", REGISTRY, ids=lambda c: c.slug)
def test_slug_is_stable_and_readable(config: object) -> None:
    """Slugs are lower-case and hyphenated — the ModelConfig pattern enforces it."""
    assert isinstance(getattr(config, "slug", None), str)


# --- an adapter is not a live provider (01-architecture.md §5.2.1) ------------


def test_live_and_enabled_are_different_states() -> None:
    """Enabled routes and proven routes are tracked separately, on purpose."""
    from val_domain.registry import live_routes, unproven_routes

    assert set(live_routes()) | set(unproven_routes()) == set(active())
    assert not (set(live_routes()) & set(unproven_routes()))


def test_only_a_real_answer_marks_a_route_live() -> None:
    """gpt-5-5 answered on 15 August; the Anthropic routes never have."""
    from val_domain.registry import live_routes, unproven_routes

    assert {c.slug for c in live_routes()} == {"gpt-5-5"}
    assert {c.slug for c in unproven_routes()} == {"opus-5", "haiku-4-5"}


def test_an_unproven_route_is_still_enabled_and_eligible() -> None:
    """Not-live never silently disables a route or weakens its eligibility."""
    from val_domain.registry import unproven_routes

    for config in unproven_routes():
        assert config in active()
        assert Classification.PROTECTED in config.eligible_classifications
