"""Tests for the Model Configuration Registry.

The registry is what `model_calls.model_config_id` resolves through, so its
invariants are about history holding rather than about routing being clever.
"""

from datetime import date

import pytest

from val_domain.gateway import AdapterStatus, Admission, Classification, ModelConfig, PricingFeature
from val_domain.registry import (
    REGISTRY,
    active,
    by_id,
    by_slug,
    cheapest,
    declared_chain_violations,
    live_routes,
)


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
    """A route is live only when it has actually answered under its identifier.

    *Independent-review correction, 18 August 2026.* Every historical live call
    was made under the retired `gpt-5.5` alias configuration, whose recorded
    fact (first live answer, 15 August) is preserved on the retired entry. The
    pinned successors have never themselves answered, and saying otherwise
    would be inventing history — so all three active routes are unproven until
    a real call lands on them. WP-0.4's second-live-provider tracking continues
    against the new entries.
    """
    from val_domain.registry import by_slug, live_routes, unproven_routes

    assert {c.slug for c in live_routes()} == set()
    assert {c.slug for c in unproven_routes()} == {
        "opus-5",
        "haiku-4-5-20251001",
        "gpt-5-5-20260423",
    }
    retired_alias = by_slug("gpt-5-5")
    assert retired_alias is not None and retired_alias.last_live_call_on is not None


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


def test_every_declared_chain_terminates() -> None:
    """Every declared fallback chain must end at an explicit NONE.

    *Independent-review correction, 18 August 2026.* The previous version of
    this test walked each chain with a seen-set and then asserted
    `current is None or current in seen` — which is the loop's own exit
    condition restated, true for every input including a cycle. It passed on a
    REAL declared cycle (haiku ↔ gpt) in the production registry. The check is
    now `declared_chain_violations`, shared with `startup_violations` so a
    declared cycle also stops the service at boot, and it is proven falsifiable
    by the synthetic fixtures in the two tests below.
    """
    assert declared_chain_violations(active()) == []


def _synthetic(slug: str, fallback: str | None, price: float = 1.0) -> ModelConfig:
    """A minimal entry for exercising the chain validator with bad registries."""
    from uuid import uuid4

    from val_domain.gateway import (
        AdapterStatus,
        Admission,
        Classification,
        PricingFeature,
        ReasoningEffort,
    )

    return ModelConfig(
        id=uuid4(),
        slug=slug,
        provider="anthropic",
        model_identifier=f"synthetic-{slug}",
        display_name=slug,
        context_window_tokens=1000,
        max_output_tokens=100,
        reasoning_effort=ReasoningEffort.NOT_APPLICABLE,
        cost_per_mtok_in_usd=price,
        cost_per_mtok_out_usd=price,
        caching=PricingFeature.NOT_VERIFIED,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=frozenset({Classification.INTERNAL}),
        known_weaknesses=(),
        fallback_slug=fallback,
        admission=Admission.PROVISIONALLY_ADMITTED,
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=date(2026, 8, 18),
        rates_verified_on=date(2026, 8, 18),
    )


def test_the_chain_validator_rejects_a_declared_cycle() -> None:
    """The negative fixture the review required: A -> B -> A must be refused.

    This is what makes the test above evidence rather than reassurance — the
    detector demonstrably fails on the shape it exists to catch, which the
    previous tautology never could.
    """
    cyclic = (_synthetic("a", "b"), _synthetic("b", "a"))
    problems = declared_chain_violations(cyclic)
    assert problems, "a declared A -> B -> A cycle was accepted"
    assert any("cycle" in problem for problem in problems)

    self_cycle = (_synthetic("a", "a"),)
    assert any("cycle" in problem for problem in declared_chain_violations(self_cycle))


def test_the_chain_validator_rejects_a_dangling_fallback() -> None:
    """And the other bad shape: a fallback naming nothing."""
    dangling = (_synthetic("a", "ghost"),)
    problems = declared_chain_violations(dangling)
    assert problems and any("names no entry" in problem for problem in problems)


def test_a_terminating_chain_is_accepted() -> None:
    """The healthy shape, so the detector is known to pass what it should."""
    healthy = (_synthetic("a", "b"), _synthetic("b", None))
    assert declared_chain_violations(healthy) == []


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


def test_rate_verification_is_current_as_of_activation() -> None:
    """`rates_verified_on` never lags `activated_on`.

    *Independent-review correction, 18 August 2026.* The previous assertion was
    `A <= B or B <= A`, which is true for every pair of comparable dates — a
    test that could never fail. The actual domain invariant: activating a route
    requires reading its rates from the provider's documentation at activation
    time, so `rates_verified_on` starts equal to `activated_on` and only ever
    moves LATER, on re-verification. A verification date earlier than
    activation would mean a route went live on rates nobody had confirmed were
    still current.
    """
    for config in REGISTRY:
        assert config.activated_on <= config.rates_verified_on, (
            f"{config.slug}: activated {config.activated_on} on rates last "
            f"verified {config.rates_verified_on} — stale at the moment it went live"
        )
        assert config.last_live_call_on is None or (config.last_live_call_on >= config.activated_on)


def test_the_date_invariant_is_falsifiable() -> None:
    """The negative fixture: a config activated after its last verification."""
    stale_at_activation = _synthetic("stale", None)
    stale_at_activation = stale_at_activation.model_copy(
        update={"activated_on": date(2026, 8, 20), "rates_verified_on": date(2026, 8, 10)}
    )
    assert not (stale_at_activation.activated_on <= stale_at_activation.rates_verified_on)


def test_temperature_absence_is_recorded_not_invented() -> None:
    """None means "this configuration sets none", not "someone forgot"."""
    for config in REGISTRY:
        assert config.temperature is None or 0.0 <= config.temperature <= 2.0
