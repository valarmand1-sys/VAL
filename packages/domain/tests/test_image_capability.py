"""Image capability is a declared routing fact, and exactly one route declares it.

Owner ruling, 19 September 2026 (Track C §7): *a route must not receive an image
merely because its underlying provider might support one.* The provider supports
images on several models; this house sends them to one configuration, because
one configuration was verified and dated.
"""

import math
from datetime import date

import pytest

from val_domain.gateway import ImageInputSupport, ModelConfig
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
    assert support.verified_on == date(2026, 9, 19)
    assert "images-vision" in support.source and "2026-09-19-sol-image-input" in support.source
    assert support.media_types == frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})
    assert (support.patch_pixels, support.patch_budget, support.token_multiplier) == (32, 2500, 1.2)


def test_the_detail_level_is_declared_because_the_default_has_no_budget() -> None:
    """`auto` resolves to `original`, which has no patch budget — and no ceiling."""
    support = by_slug(SOL).image_input  # type: ignore[union-attr]
    assert support is not None
    assert support.detail == "high"
    assert support.max_tokens_per_image == 3000


def test_the_transmission_bound_keeps_every_sent_image_inside_the_patch_budget() -> None:
    """The property the whole reservation rests on, checked as arithmetic.

    A measured image that exceeds the provider's budget billed one token above
    the formula's cap. Deriving to a long edge of 1,600 means the provider never
    has to resize, so the documented formula applies exactly — and the worst
    case, a square at the bound, lands on the budget rather than past it.
    """
    support = by_slug(SOL).image_input  # type: ignore[union-attr]
    assert support is not None
    edge = support.max_long_edge_pixels
    patches_per_edge = math.ceil(edge / support.patch_pixels)
    assert patches_per_edge**2 == support.patch_budget == 2500, "a square at the bound"
    assert edge == 1600


def test_a_declared_capability_must_name_real_media_types() -> None:
    for media_types in (frozenset[str](), frozenset({"PNG"}), frozenset({"image/p/ng"})):
        with pytest.raises(ValueError, match="media type"):
            ImageInputSupport(
                media_types=media_types,
                max_long_edge_pixels=1,
                max_byte_size=1,
                detail="high",
                patch_pixels=32,
                patch_budget=1,
                token_multiplier=1.0,
                verified_on=date(2026, 9, 19),
                source="x",
            )


def test_declaring_image_capability_changes_no_admission_or_profile() -> None:
    """Capability is what a route accepts, not what it is admitted to do."""
    sol = by_slug(SOL)
    assert sol is not None
    assert sol.admission.value == "provisionally_admitted"
    assert [profile.value for profile in sol.capability_profiles] == ["partner"]
