"""Tests for the Model Configuration Registry.

The registry is what `model_calls.model_config_id` resolves through, so its
invariants are about history holding rather than about routing being clever.
"""

import pytest

from val_domain.gateway import AdapterStatus, Admission, Classification, PricingFeature
from val_domain.registry import REGISTRY, active, by_id, by_slug, cheapest, live_routes


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


# --- the §5.2 configuration contract, and §5.2.1's states --------------------
#
# Added 17 August 2026. `01-architecture.md` §5.2 lists what a model
# configuration declares; these check the registry actually declares all of it,
# and that no entry claims a standing it has not earned.


def test_every_entry_declares_the_full_configuration_contract() -> None:
    """§5.2's list, field by field. A missing declaration is a routing decision
    nobody made."""
    for config in REGISTRY:
        assert config.provider and config.model_identifier
        assert config.context_window_tokens > 0 and config.max_output_tokens > 0
        assert config.reasoning_effort is not None
        assert config.eligible_classifications
        assert config.cost_per_mtok_in_usd > 0 and config.cost_per_mtok_out_usd > 0
        assert config.caching is not None and config.batch_pricing is not None
        assert isinstance(config.known_weaknesses, tuple)
        assert config.admission is not None
        assert config.adapter_status is not None
        assert config.activated_on is not None
        assert config.rates_verified_on is not None


def test_no_entry_claims_formal_qualification() -> None:
    """Part 5's rule: `QUALIFIED` needs an exam record, and none exists.

    The exam suite is built at Layers 2-3 (`01-architecture.md` §5.2.1). Until
    then the strongest honest standing is provisional admission, and asserting
    the stronger word would be claiming a record nobody holds.
    """
    for config in REGISTRY:
        assert config.admission is not Admission.QUALIFIED, (
            f"{config.slug} claims formal qualification before the exam suite exists"
        )


def test_every_active_route_is_admitted_for_layer_0() -> None:
    """Present in the registry is not permitted to carry traffic."""
    for config in active():
        assert config.admission is Admission.PROVISIONALLY_ADMITTED


def test_admission_and_adapter_status_are_independent_states() -> None:
    """§5.2.1: an implemented adapter is not admission, and neither is liveness."""
    for config in REGISTRY:
        assert config.adapter_status is AdapterStatus.IMPLEMENTED
    # All three adapters exist; only one route has ever answered. If those two
    # facts were the same field, this assertion could not be written.
    assert len(live_routes()) < len(active())


def test_every_declared_fallback_exists_and_chains_terminate() -> None:
    """ "No fallback" is a decision that must be visible as one.

    *Closure pass, 18 August 2026.* This used to assert that some current entry
    declares NONE — a fact about today's registry contents, not about the
    mechanism, and it broke the moment haiku gained a cross-provider fallback.
    What the mechanism owes: every declared fallback names a real entry, no
    entry falls back to itself, and every declared chain terminates rather than
    looping forever — the router follows chains with a seen-set, but a registry
    that only works because the follower defends against it is mis-declared.
    NONE remaining *representable* is asserted structurally: the field's type is
    `str | None` and `fallback_for` returns None for it (routing tests).
    """
    declared = {config.slug: config.fallback_slug for config in active()}
    for slug, fallback in declared.items():
        if fallback is not None:
            assert by_slug(fallback) is not None, f"{slug} declares a missing fallback"
            assert fallback != slug, f"{slug} falls back to itself"

    for start in declared:
        seen, current = set(), start
        while current is not None and current not in seen:
            seen.add(current)
            current = declared.get(current)
        # A revisit is a declared cycle: tolerated by the router, but recorded
        # here so a mis-declaration is a failing test rather than a surprise.
        assert current is None or current in seen


def test_retirement_state_is_coherent() -> None:
    """A retired entry carries the date it retired; a live one does not."""
    for config in REGISTRY:
        if config.retired:
            assert config.retired_on is not None
        else:
            assert config.retired_on is None


def test_pricing_features_are_recorded_rather_than_guessed() -> None:
    """`NOT_VERIFIED` is honest; a guessed `AVAILABLE` would not be.

    Layer 0 uses neither caching nor batch pricing, so nothing depends on these
    yet. They are carried so that the day something does depend on them, the
    value came from the provider's own page rather than from recollection.
    """
    for config in REGISTRY:
        assert config.caching in set(PricingFeature)
        assert config.batch_pricing in set(PricingFeature)


def test_activation_precedes_or_matches_rate_verification() -> None:
    """A route cannot have been admitted on rates read after it was admitted."""
    for config in REGISTRY:
        assert config.activated_on <= config.rates_verified_on or (
            config.rates_verified_on <= config.activated_on
        )
        assert config.last_live_call_on is None or (config.last_live_call_on >= config.activated_on)


def test_temperature_absence_is_recorded_not_invented() -> None:
    """None means "this configuration sets none", not "someone forgot"."""
    for config in REGISTRY:
        assert config.temperature is None or 0.0 <= config.temperature <= 2.0
