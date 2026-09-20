"""Admission reads the bytes, and transmission is decided before the reservation.

Attachment Substrate v1.2 §3.3 and §8. Every image here is generated in the
test, so what is admitted is known exactly rather than asserted about a fixture
nobody reads.
"""

import hashlib
import io
import math
from datetime import date

import pytest
from PIL import Image

from val_domain.gateway import (
    HouseImagePolicy,
    ImageInputSupport,
    ImagePart,
    ProviderImageLimits,
    ProviderRequestImageLimits,
)
from val_domain.registry import by_slug
from val_policy.attachments import (
    DERIVED_BY,
    MAX_DECODED_PIXELS,
    REQUEST_PAYLOAD_MEASURE,
    SUPPORTED_MEDIA_TYPES,
    AdmissionRefusedError,
    admit_image,
    check_request_limits,
    data_uri_bytes,
    derivation_required,
    fit_within_limits,
    patch_count,
    plan_transmission,
    request_load,
    within_provider_limits,
)
from val_policy.budget import (
    IMAGE_RESERVATION_MARGIN_TOKENS,
    image_input_tokens,
    upper_bound_image_tokens,
)


def house(**overrides: object) -> HouseImagePolicy:
    fields: dict[str, object] = {
        "max_byte_size": 50_000_000,
        "reason": "test",
        "request_payload_measure": "data_uri_bytes",
        "request_payload_measure_reason": "test",
    }
    fields.update(overrides)
    return HouseImagePolicy(**fields)  # type: ignore[arg-type]


def request_limits(**overrides: object) -> ProviderRequestImageLimits:
    fields: dict[str, object] = {
        "max_images_per_request": 1_500,
        "max_total_payload_bytes": 512_000_000,
        "payload_unit_is_documented": False,
        "verified_on": date(2026, 9, 20),
        "source": "test",
    }
    fields.update(overrides)
    return ProviderRequestImageLimits(**fields)  # type: ignore[arg-type]


def support(**provider: object) -> ImageInputSupport:
    """Sol's real documented facts unless a test deliberately narrows one."""
    limits: dict[str, object] = {
        "media_types": frozenset({"image/png", "image/jpeg"}),
        "detail": "high",
        "max_long_edge_pixels": 2048,
        "patch_pixels": 32,
        "patch_budget": 2500,
        "token_multiplier": 1.2,
        "verified_on": date(2026, 9, 20),
        "source": "test",
    }
    limits.update(provider)
    return ImageInputSupport(
        provider=ProviderImageLimits(**limits),  # type: ignore[arg-type]
        provider_request=request_limits(),
        house=house(),
    )


SUPPORT = support()


def make(fmt: str, size: tuple[int, int] = (64, 48), colour: str = "navy") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, colour).save(buffer, format=fmt)
    return buffer.getvalue()


def animated_gif() -> bytes:
    buffer = io.BytesIO()
    frames = [Image.new("RGB", (8, 8), c).convert("P") for c in ("red", "blue")]
    frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:])
    return buffer.getvalue()


# --- §3.3 admission ------------------------------------------------------------


@pytest.mark.parametrize(
    ("fmt", "media_type"),
    [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("GIF", "image/gif"), ("WEBP", "image/webp")],
)
def test_the_media_type_comes_from_the_bytes(fmt: str, media_type: str) -> None:
    payload = make(fmt)
    admitted = admit_image(payload)
    assert admitted.media_type == media_type
    assert media_type in SUPPORTED_MEDIA_TYPES
    assert (admitted.width, admitted.height) == (64, 48)
    assert admitted.byte_size == len(payload)
    assert admitted.sha256 == hashlib.sha256(payload).hexdigest()
    assert admitted.content is payload, "the admitted original is the bytes given, untouched"


def test_a_filename_never_decides_the_media_type() -> None:
    """A PNG named `.jpg` is a PNG; admission never consults the name at all."""
    assert admit_image(make("PNG")).media_type == "image/png"
    assert admit_image(make("JPEG")).media_type == "image/jpeg"


def test_bytes_that_only_look_like_an_image_are_refused() -> None:
    with pytest.raises(AdmissionRefusedError, match="do not decode"):
        admit_image(b"\x89PNG\r\n\x1a\n" + b"not actually a png")


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b"", "empty file"),
        (b"%PDF-1.7 a document", "supported image signature"),
        (b"just text", "supported image signature"),
    ],
)
def test_unsupported_input_is_refused_by_a_named_reason(payload: bytes, expected: str) -> None:
    with pytest.raises(AdmissionRefusedError, match=expected):
        admit_image(payload)


def test_an_animated_image_is_not_admitted_in_v1() -> None:
    """Flattening animation to one frame would change what the record says was sent."""
    with pytest.raises(AdmissionRefusedError, match="animated"):
        admit_image(animated_gif())


def test_the_decode_bound_is_stated_rather_than_left_to_a_library_default() -> None:
    assert MAX_DECODED_PIXELS == 80_000_000
    assert Image.MAX_IMAGE_PIXELS is None or MAX_DECODED_PIXELS <= Image.MAX_IMAGE_PIXELS * 2


# --- §8 transmission planning ---------------------------------------------------


def test_an_image_within_both_documented_limits_is_transmitted_unchanged() -> None:
    admitted = admit_image(make("PNG", (400, 300)))
    plan = plan_transmission(admitted, SUPPORT)
    assert plan.derived is False
    assert plan.derived_by is None
    assert (plan.sha256, plan.width, plan.height) == (admitted.sha256, 400, 300)
    assert plan.content == admitted.content, "byte-identical on the wire"


# --- the fitting rule (owner correction, 20 September 2026) ----------------------


def test_a_sixteen_by_nine_frame_at_the_dimension_bound_is_not_reduced() -> None:
    """The case that condemned the old 1,600 rule.

    2048x1152 is 64 x 36 = 2,304 patches — already inside the 2,500 budget and
    on the 2,048 dimension bound, so the provider resizes nothing. The old rule
    shrank it to 1600x900 and threw away about a fifth of the linear resolution
    for no accounting reason.
    """
    assert patch_count(2048, 1152, SUPPORT) == 2304
    assert fit_within_limits(2048, 1152, SUPPORT) == (2048, 1152)
    admitted = admit_image(make("PNG", (2048, 1152)))
    assert derivation_required(admitted, SUPPORT) is False
    plan = plan_transmission(admitted, SUPPORT)
    assert plan.derived is False
    assert (plan.width, plan.height) == (2048, 1152)
    assert plan.content == admitted.content


def test_a_square_over_budget_reduces_to_the_largest_square_inside_it() -> None:
    assert fit_within_limits(2400, 2400, SUPPORT) == (1600, 1600)
    assert patch_count(1600, 1600, SUPPORT) == SUPPORT.provider.patch_budget
    assert not within_provider_limits(1632, 1632, SUPPORT), "one patch-step larger does not fit"


def test_a_wide_image_keeps_far_more_than_sixteen_hundred_horizontal_pixels() -> None:
    width, height = fit_within_limits(4096, 1024, SUPPORT)
    assert (width, height) == (2048, 512)
    assert width > 1600, "the old rule would have cut this to 1600"
    assert within_provider_limits(width, height, SUPPORT)


def test_a_tall_image_behaves_symmetrically() -> None:
    assert fit_within_limits(1024, 4096, SUPPORT) == (512, 2048)
    assert fit_within_limits(4096, 1024, SUPPORT) == (2048, 512)


@pytest.mark.parametrize(
    "size",
    [
        (2048, 2048),
        (2400, 2400),
        (3000, 2000),
        (2000, 3000),
        (4096, 1024),
        (1024, 4096),
        (2049, 2049),
        (6000, 17),
        (17, 6000),
        (2048, 1152),
        (1920, 1080),
        (5000, 5000),
    ],
)
def test_every_fitted_size_is_inside_both_limits_and_never_upscaled(
    size: tuple[int, int],
) -> None:
    width, height = size
    fitted = fit_within_limits(width, height, SUPPORT)
    assert within_provider_limits(*fitted, SUPPORT), f"{size} -> {fitted} escaped a limit"
    assert fitted[0] <= width and fitted[1] <= height, "never upscaled"
    assert min(fitted) >= 1


@pytest.mark.parametrize("size", [(2400, 2400), (3000, 2000), (2049, 1000), (6000, 17)])
def test_the_fitted_size_is_maximal_one_patch_step_larger_does_not_fit(
    size: tuple[int, int],
) -> None:
    """The rule takes the LARGEST long edge that fits; the next integer does not."""
    width, height = size
    fitted_long = max(fit_within_limits(width, height, SUPPORT))
    ceiling = min(max(width, height), SUPPORT.provider.max_long_edge_pixels)
    if fitted_long < ceiling:
        longest, shortest = max(width, height), min(width, height)
        nxt = fitted_long + 1
        short = max(1, (shortest * nxt) // longest)
        pair = (nxt, short) if width >= height else (short, nxt)
        assert not within_provider_limits(*pair, SUPPORT)


def test_identical_input_and_capability_always_give_identical_bytes() -> None:
    """Blind/final equality and provenance both rest on this."""
    payload = make("PNG", (3000, 2000))
    first = plan_transmission(admit_image(payload), SUPPORT)
    second = plan_transmission(admit_image(payload), SUPPORT)
    assert first.sha256 == second.sha256
    assert first.content == second.content
    assert (first.width, first.height) == (second.width, second.height)


@pytest.mark.parametrize("size", [(1951, 1300), (2049, 2049), (1633, 1633), (6000, 17)])
def test_a_rounding_boundary_gives_the_same_answer_every_time(size: tuple[int, int]) -> None:
    """The short edge is floored, so the pair is a function of the long edge alone."""
    answers = {fit_within_limits(*size, SUPPORT) for _ in range(5)}
    assert len(answers) == 1


def test_the_short_edge_is_floored_never_rounded_up_into_a_limit() -> None:
    width, height = fit_within_limits(3000, 2000, SUPPORT)
    assert (width, height) == (1921, 1280)
    assert height == (2000 * 1921) // 3000, "floored, exactly"
    assert within_provider_limits(width, height, SUPPORT)


def test_the_recorded_dimensions_are_measured_from_the_derived_bytes() -> None:
    """§8 — the figures that price the call are read from what will be sent."""
    plan = plan_transmission(admit_image(make("JPEG", (4000, 2250))), SUPPORT)
    assert plan.derived is True
    with Image.open(io.BytesIO(plan.content)) as sent:
        assert sent.size == (plan.width, plan.height)
        assert sent.format == "JPEG", "a JPEG source stays a JPEG"
    assert plan.media_type == "image/jpeg"
    assert plan.byte_size == len(plan.content)
    assert plan.derived_by == DERIVED_BY


def test_a_format_the_route_does_not_accept_is_re_encoded_to_one_it_does() -> None:
    admitted = admit_image(make("WEBP", (100, 100)))
    assert derivation_required(admitted, SUPPORT) is True, "re-encoding is a derivation"
    plan = plan_transmission(admitted, SUPPORT)
    assert plan.derived is True
    assert plan.media_type == "image/png", "PNG is lossless and every approved route takes it"
    assert (plan.width, plan.height) == (100, 100), "no needless resize"


def test_a_route_that_takes_neither_the_image_nor_png_refuses_before_transmission() -> None:
    jpeg_only = support(media_types=frozenset({"image/jpeg"}))
    with pytest.raises(AdmissionRefusedError, match="this route accepts"):
        plan_transmission(admit_image(make("WEBP")), jpeg_only)


def test_a_payload_still_too_large_after_derivation_is_refused_not_sent() -> None:
    tiny = ImageInputSupport(
        provider=SUPPORT.provider,
        provider_request=SUPPORT.provider_request,
        house=house(max_byte_size=8),
    )
    with pytest.raises(AdmissionRefusedError, match="this house sends at most"):
        plan_transmission(admit_image(make("PNG", (900, 900))), tiny)


def test_the_house_byte_ceiling_alone_makes_a_derivation_required() -> None:
    """A house limit is a real reason to derive, and is named as the house's."""
    small = ImageInputSupport(
        provider=SUPPORT.provider,
        provider_request=SUPPORT.provider_request,
        house=house(max_byte_size=500),
    )
    admitted = admit_image(make("PNG", (400, 300)))
    assert within_provider_limits(admitted.width, admitted.height, small)
    assert derivation_required(admitted, small) is True


# --- the reservation (owner ruling, 20 September 2026) ---------------------------


def test_the_reservation_is_computed_from_the_transmitted_dimensions() -> None:
    """§8 — reserve from the bytes that will actually be sent, never the original."""
    admitted = admit_image(make("PNG", (3000, 2000)))
    plan = plan_transmission(admitted, SUPPORT)
    assert (plan.width, plan.height) == (1921, 1280)
    assert image_input_tokens(plan.width, plan.height, SUPPORT) == math.ceil(2440 * 1.2)
    # The original's own figure is different, and is not what is reserved.
    assert image_input_tokens(admitted.width, admitted.height, SUPPORT) != image_input_tokens(
        plan.width, plan.height, SUPPORT
    )


def test_the_formula_is_the_documented_one_and_the_margin_is_separate() -> None:
    """The provider documents a one-token rounding; the margin is not the price."""
    part = ImagePart(sha256="a" * 64, media_type="image/png", width=2048, height=1152, content=b"x")
    formula = image_input_tokens(2048, 1152, SUPPORT)
    assert formula == math.ceil(2304 * 1.2)
    config = by_slug("gpt-5-6-sol-medium")
    assert config is not None
    bound = upper_bound_image_tokens([part], config)
    assert bound == image_input_tokens(2048, 1152, config.image_input) + 1  # type: ignore[arg-type]
    assert IMAGE_RESERVATION_MARGIN_TOKENS == 1


def test_a_route_declaring_no_image_input_cannot_bound_an_image() -> None:
    part = ImagePart(sha256="a" * 64, media_type="image/png", width=8, height=8, content=b"x")
    incumbent = by_slug("opus-5-medium")
    assert incumbent is not None and incumbent.image_input is None
    with pytest.raises(ValueError, match="declares no image input"):
        upper_bound_image_tokens([part], incumbent)


# --- request-wide limits (owner ruling, 20 September 2026) -----------------------


def test_the_measure_is_exactly_what_the_adapter_would_build() -> None:
    """The preflight and the wire must agree, or the guard measures a fiction."""
    from base64 import b64encode

    for media_type, size in (("image/png", 1), ("image/png", 1000), ("image/jpeg", 99_991)):
        payload = b"x" * size
        built = f"data:{media_type};base64,{b64encode(payload).decode()}"
        assert data_uri_bytes(media_type, size) == len(built)


def test_the_measure_is_the_largest_image_attributable_quantity() -> None:
    """Conservative by construction: raw bytes < base64 < the data URI."""
    from base64 import b64encode

    payload = b"y" * 3_000
    raw = len(payload)
    encoded = len(b64encode(payload))
    uri = data_uri_bytes("image/png", raw)
    assert raw < encoded < uri
    assert REQUEST_PAYLOAD_MEASURE == "data_uri_bytes"


def test_an_aggregate_inside_both_provider_limits_proceeds() -> None:
    load = request_load([("image/png", 1_000), ("image/png", 2_000), ("image/jpeg", 3_000)])
    assert load.image_count == 3
    assert load.measure == "data_uri_bytes"
    check_request_limits(load, SUPPORT)  # does not raise


def test_too_many_images_refuses_and_names_the_count_limit() -> None:
    narrow = ImageInputSupport(
        provider=SUPPORT.provider,
        provider_request=request_limits(max_images_per_request=2),
        house=house(),
    )
    load = request_load([("image/png", 10)] * 3)
    with pytest.raises(AdmissionRefusedError) as refused:
        check_request_limits(load, narrow)
    message = str(refused.value)
    assert "3 images" in message and "2 per request" in message
    assert "provider request limit: image count" in message
    assert "No image was transmitted" in message


def test_too_much_image_data_refuses_and_names_the_payload_limit() -> None:
    narrow = ImageInputSupport(
        provider=SUPPORT.provider,
        provider_request=request_limits(max_total_payload_bytes=1_000),
        house=house(),
    )
    load = request_load([("image/png", 900), ("image/png", 900)])
    with pytest.raises(AdmissionRefusedError) as refused:
        check_request_limits(load, narrow)
    message = str(refused.value)
    assert "provider request limit: total image data" in message
    assert f"{load.payload_bytes:,} bytes" in message
    assert "1,000 per request" in message
    # While the unit is undocumented, the refusal says whose reading it is.
    assert "measured conservatively by the house" in message
    assert "No image was transmitted" in message


def test_the_refusal_stops_saying_house_when_the_provider_defines_the_unit() -> None:
    """A documentation change flips the flag, and the wording follows it."""
    settled = ImageInputSupport(
        provider=SUPPORT.provider,
        provider_request=request_limits(
            max_total_payload_bytes=1_000, payload_unit_is_documented=True
        ),
        house=house(),
    )
    with pytest.raises(AdmissionRefusedError) as refused:
        check_request_limits(request_load([("image/png", 2_000)]), settled)
    assert "measured conservatively by the house" not in str(refused.value)


def test_the_count_limit_is_checked_before_the_payload_limit() -> None:
    """Both violated: the refusal names one limit, deterministically."""
    both = ImageInputSupport(
        provider=SUPPORT.provider,
        provider_request=request_limits(max_images_per_request=1, max_total_payload_bytes=10),
        house=house(),
    )
    with pytest.raises(AdmissionRefusedError, match="image count"):
        check_request_limits(request_load([("image/png", 900)] * 2), both)


# --- the reservation composes over every image -----------------------------------


def parts(*sizes: tuple[int, int]) -> list[ImagePart]:
    return [
        ImagePart(
            sha256=f"{index}".rjust(64, "0"),
            media_type="image/png",
            width=width,
            height=height,
            content=b"x",
        )
        for index, (width, height) in enumerate(sizes)
    ]


def test_two_images_both_contribute_to_the_reservation() -> None:
    config = by_slug("gpt-5-6-sol-medium")
    assert config is not None and config.image_input is not None
    support_facts = config.image_input
    both = parts((2048, 1152), (512, 512))
    expected = sum(
        image_input_tokens(p.width, p.height, support_facts) + IMAGE_RESERVATION_MARGIN_TOKENS
        for p in both
    )
    assert upper_bound_image_tokens(both, config) == expected
    # Neither image alone accounts for it.
    assert upper_bound_image_tokens(both, config) > upper_bound_image_tokens(both[:1], config)


@pytest.mark.parametrize("count", [1, 2, 3, 5, 12])
def test_the_reservation_composes_over_any_number_of_images(count: int) -> None:
    config = by_slug("gpt-5-6-sol-medium")
    assert config is not None and config.image_input is not None
    images = parts(*[(640, 480)] * count)
    one = image_input_tokens(640, 480, config.image_input) + IMAGE_RESERVATION_MARGIN_TOKENS
    assert upper_bound_image_tokens(images, config) == one * count


def test_the_margin_is_counted_once_per_image_not_once_per_request() -> None:
    config = by_slug("gpt-5-6-sol-medium")
    assert config is not None and config.image_input is not None
    images = parts((800, 600), (800, 600), (800, 600))
    formula_only = sum(image_input_tokens(p.width, p.height, config.image_input) for p in images)
    assert upper_bound_image_tokens(images, config) == formula_only + 3


def test_differently_sized_images_are_each_priced_on_their_own_dimensions() -> None:
    config = by_slug("gpt-5-6-sol-medium")
    assert config is not None and config.image_input is not None
    small, large = parts((320, 240), (2048, 1152))
    assert upper_bound_image_tokens([small, large], config) == (
        upper_bound_image_tokens([small], config) + upper_bound_image_tokens([large], config)
    )
