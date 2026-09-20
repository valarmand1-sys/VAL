"""Image capability is a declared routing fact, and exactly one route declares it.

Owner ruling, 19 September 2026 (Track C §7): *a route must not receive an image
merely because its underlying provider might support one.* The provider supports
images on several models; this house sends them to one configuration, because
one configuration was verified and dated.
"""

import math
from datetime import date

import pytest

from val_domain.gateway import ModelConfig, ProviderImageLimits
from val_domain.registry import REGISTRY, by_slug

SOL = "gpt-5-6-sol-medium"


def capable() -> list[ModelConfig]:
    return [config for config in REGISTRY if config.image_input is not None]


def test_exactly_one_configuration_is_image_capable_and_it_is_sol() -> None:
    assert [config.slug for config in capable()] == [SOL]


def test_no_local_or_incumbent_route_became_image_capable() -> None:
    """The first slice approved Sol alone; opus-5-medium was explicitly excluded."""
    for slug in ("opus-5-medium", "opus-5-high", "sonnet-5-low", "gpt-oss-20b-mxfp4-mlx-lmstudio"):
        config = by_slug(slug)
        if config is not None:
            assert config.image_input is None, f"{slug} must not be image-capable"


def test_sol_declares_the_facts_that_were_verified_against_the_provider() -> None:
    support = by_slug(SOL).image_input  # type: ignore[union-attr]
    assert support is not None
    provider = support.provider
    assert provider.verified_on == date(2026, 9, 20), "re-read first-party on the correction"
    assert "images-vision" in provider.source and "first-party" in provider.source
    assert provider.media_types == frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})
    assert (provider.patch_pixels, provider.patch_budget, provider.token_multiplier) == (
        32,
        2500,
        1.2,
    )
    assert provider.max_long_edge_pixels == 2048, "the provider's own bound, not a house choice"


def test_the_detail_level_is_declared_because_the_default_has_no_budget() -> None:
    """`auto` resolves to `original`, which has no patch budget — and no ceiling."""
    support = by_slug(SOL).image_input  # type: ignore[union-attr]
    assert support is not None
    assert support.provider.detail == "high"
    assert support.max_tokens_per_image == 3000


def test_the_dimension_bound_is_the_providers_own_not_a_transmission_choice() -> None:
    """Owner correction, 20 September 2026 — and this test changed with it.

    It previously asserted `edge == 1600` and `patches_per_edge ** 2 == 2500`.
    Both were true of the *old transmission rule*, not of the provider: 1,600 is
    the largest square inside the patch budget, and capping every image there
    threw away resolution on everything that is not square. The registry now
    carries the provider's documented bound, and fitting inside both limits is
    `val_policy.attachments.fit_within_limits`'s job, per image.
    """
    provider = by_slug(SOL).image_input.provider  # type: ignore[union-attr]
    assert provider.max_long_edge_pixels == 2048
    assert provider.patch_budget == 2500
    # The square case the old constant encoded is still true — as a consequence
    # of the two facts above, not as a rule of its own.
    assert math.ceil(1600 / provider.patch_pixels) ** 2 == provider.patch_budget


def test_a_house_limit_is_recorded_as_a_house_limit() -> None:
    """The provider documents no per-image size bound, so this one is ours."""
    support = by_slug(SOL).image_input  # type: ignore[union-attr]
    assert support is not None
    assert support.house.max_byte_size == 20_000_000
    assert "not a provider limit" in support.house.reason
    assert "PostgreSQL" in support.house.reason, "it says why, not merely that"
    # And the provider half carries no byte bound at all to be mistaken for one.
    assert not hasattr(support.provider, "max_byte_size")


def test_a_declared_capability_must_name_real_media_types() -> None:
    for media_types in (frozenset[str](), frozenset({"PNG"}), frozenset({"image/p/ng"})):
        with pytest.raises(ValueError, match="media type"):
            ProviderImageLimits(
                media_types=media_types,
                detail="high",
                max_long_edge_pixels=1,
                patch_pixels=32,
                patch_budget=1,
                token_multiplier=1.0,
                verified_on=date(2026, 9, 20),
                source="x",
            )


def test_declaring_image_capability_changes_no_admission_or_profile() -> None:
    """Capability is what a route accepts, not what it is admitted to do."""
    sol = by_slug(SOL)
    assert sol is not None
    assert sol.admission.value == "provisionally_admitted"
    assert [profile.value for profile in sol.capability_profiles] == ["partner"]
