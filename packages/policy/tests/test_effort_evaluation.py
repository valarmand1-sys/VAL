"""The LOW reasoning-effort entry serves nothing — Voice work package 2 §2.

It was registered so a bounded latency measurement could put two reasoning
efforts on one identical request path. That is the whole of its purpose, and
these tests are the guard that it stays that way: **production text cognition is
MEDIUM**, and nothing in routing can reach LOW to change that.

The other half is the comparison's own validity: the two entries must differ in
reasoning effort and in nothing else that could explain a latency difference.
That is asserted here mechanically rather than trusted to a reading of the
registry.
"""

from __future__ import annotations

from val_domain.gateway import Admission, CapabilityProfile, Classification, ReasoningEffort
from val_domain.registry import REGISTRY, active, by_slug, under_evaluation
from val_policy.routing import candidates, is_admitted, satisfies_profile

MEDIUM = "gpt-oss-20b-mxfp4-mlx-lmstudio"
LOW = "gpt-oss-20b-mxfp4-mlx-lmstudio-low"
PRODUCTION = "gpt-oss-20b-mxfp4-mlx-lmstudio-partner"


def test_production_text_cognition_is_medium_and_this_package_did_not_move_it() -> None:
    """The one fact the whole measurement is not allowed to change."""
    production = by_slug(PRODUCTION)
    assert production is not None
    assert production.reasoning_effort is ReasoningEffort.MEDIUM
    assert production.admission is Admission.PROVISIONALLY_ADMITTED
    assert CapabilityProfile.PARTNER in production.capability_profiles
    assert production in active()


def test_the_low_entry_is_evaluation_only_and_reaches_no_profile() -> None:
    low = by_slug(LOW)
    assert low is not None
    assert low.reasoning_effort is ReasoningEffort.LOW
    assert low.admission is Admission.NOT_ADMITTED
    assert low.capability_profiles == frozenset(), "no production profile, of any kind"
    assert low.fallback_slug is None
    assert low not in active(), "an evaluation entry is not a route"
    assert low in under_evaluation()


def test_no_routing_decision_can_select_the_low_entry() -> None:
    """Offered the whole registry, every profile, every classification: never LOW."""
    for profile in CapabilityProfile:
        for classification in Classification:
            chosen = candidates(
                REGISTRY,
                classification,
                lambda config: True,
                lambda config: True,
                profile=profile,
                cost_bound=lambda config: config.cost_per_mtok_in_usd,
            )
            assert LOW not in {config.slug for config in chosen}, (profile, classification)


def test_the_low_entry_satisfies_no_capability_floor() -> None:
    low = by_slug(LOW)
    assert low is not None
    assert not is_admitted(low)
    for profile in CapabilityProfile:
        assert not satisfies_profile(low, profile), profile


def test_the_two_measured_configurations_differ_in_reasoning_effort_and_nothing_else() -> None:
    """The comparison is only worth anything if this holds.

    Identity fields — the id, the slug, the display name and the two dates —
    differ because they are two registry rows. Everything that could explain a
    latency difference must be identical, and this says which is which rather
    than asserting a hand-written list of sameness.
    """
    medium, low = by_slug(MEDIUM), by_slug(LOW)
    assert medium is not None and low is not None
    identity = {"id", "slug", "display_name", "activated_on", "rates_verified_on"}
    differing = {
        name for name in type(medium).model_fields if getattr(medium, name) != getattr(low, name)
    }
    assert differing - identity == {"reasoning_effort"}, (
        f"the two entries differ in more than effort: {sorted(differing - identity)}"
    )
    assert medium.model_identifier == low.model_identifier == "openai/gpt-oss-20b"
    assert medium.context_window_tokens == low.context_window_tokens == 32_768
    assert medium.max_output_tokens == low.max_output_tokens
    assert medium.eligible_classifications == low.eligible_classifications
    assert medium.temperature is low.temperature is None, "no sampling override on either"


def test_the_evaluation_entry_and_the_production_entry_are_separate_records() -> None:
    """Measuring MEDIUM did not reach into the admitted route to do it."""
    evaluation, production = by_slug(MEDIUM), by_slug(PRODUCTION)
    assert evaluation is not None and production is not None
    assert evaluation.id != production.id
    assert evaluation.admission is Admission.NOT_ADMITTED
    assert evaluation.capability_profiles == frozenset()
    assert production.capability_profiles == {CapabilityProfile.PARTNER}
    # Same artifact, same runtime, same window: what makes the baseline comparable.
    assert evaluation.model_identifier == production.model_identifier
    assert evaluation.provider == production.provider
    assert evaluation.context_window_tokens == production.context_window_tokens
    assert evaluation.reasoning_effort is production.reasoning_effort


# --- the latency pass changed none of this — pre-WP3 pass §19 --------------------------


def test_the_latency_pass_left_the_established_voice_alone() -> None:
    """A latency change must not become a voice change."""
    from val_domain.gateway import CapabilityProfile as Profile

    speech = [
        config
        for config in active()
        if is_admitted(config) and satisfies_profile(config, Profile.SPEECH)
    ]
    assert [config.model_identifier for config in speech] == [
        "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit"
    ]
    assert len(speech) == 1, "one admitted voice, and it is the established one"


def test_no_cloud_speech_route_exists_at_all() -> None:
    """Neither recognition nor speech may reach a cloud service."""
    from val_domain.registry import REGISTRY

    for config in REGISTRY:
        assert "eleven" not in config.model_identifier.lower()
        assert "eleven" not in config.provider.lower()
        assert "whisper" not in config.provider.lower(), (
            "recognition is a local library, never a registered provider route"
        )


def test_the_local_partner_route_is_the_cheapest_and_is_therefore_what_a_turn_selects() -> None:
    """Why warming the *cheapest* partner route is warming the one a turn uses."""
    partner = [
        config
        for config in active()
        if is_admitted(config) and satisfies_profile(config, CapabilityProfile.PARTNER)
    ]
    cheapest = min(partner, key=lambda config: config.cost_per_mtok_in_usd)
    assert cheapest.slug == PRODUCTION
    assert cheapest.cost_per_mtok_in_usd == 0.0
    assert cheapest.context_window_tokens == 32_768
