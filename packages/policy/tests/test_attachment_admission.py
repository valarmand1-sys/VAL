"""Admission reads the bytes, and transmission is decided before the reservation.

Attachment Substrate v1.2 §3.3 and §8. Every image here is generated in the
test, so what is admitted is known exactly rather than asserted about a fixture
nobody reads.
"""

import hashlib
import io
from datetime import date

import pytest
from PIL import Image

from val_domain.gateway import ImageInputSupport
from val_policy.attachments import (
    DERIVED_BY,
    MAX_DECODED_PIXELS,
    SUPPORTED_MEDIA_TYPES,
    AdmissionRefusedError,
    admit_image,
    plan_transmission,
)

SUPPORT = ImageInputSupport(
    media_types=frozenset({"image/png", "image/jpeg"}),
    max_long_edge_pixels=512,
    max_byte_size=200_000,
    verified_on=date(2026, 9, 19),
    source="test",
)


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


def test_an_image_within_the_route_limits_is_transmitted_unchanged() -> None:
    admitted = admit_image(make("PNG", (400, 300)))
    plan = plan_transmission(admitted, SUPPORT)
    assert plan.derived is False
    assert plan.derived_by is None
    assert (plan.sha256, plan.width, plan.height) == (admitted.sha256, 400, 300)
    assert plan.content == admitted.content


def test_an_oversized_image_is_derived_down_before_the_reservation() -> None:
    admitted = admit_image(make("PNG", (2048, 1024)))
    plan = plan_transmission(admitted, SUPPORT)
    assert plan.derived is True
    assert plan.derived_by == DERIVED_BY
    assert max(plan.width, plan.height) == SUPPORT.max_long_edge_pixels
    assert (plan.width, plan.height) == (512, 256), "aspect ratio preserved"
    assert plan.sha256 != admitted.sha256, "different bytes, different identity"
    assert plan.sha256 == hashlib.sha256(plan.content).hexdigest()


def test_the_recorded_dimensions_are_measured_from_the_derived_bytes() -> None:
    """§8 — the figures that price the call are read from what will be sent."""
    plan = plan_transmission(admit_image(make("JPEG", (1600, 900))), SUPPORT)
    with Image.open(io.BytesIO(plan.content)) as sent:
        assert sent.size == (plan.width, plan.height)
        assert sent.format == "JPEG", "a JPEG source stays a JPEG"
    assert plan.media_type == "image/jpeg"
    assert plan.byte_size == len(plan.content)


def test_a_format_the_route_does_not_accept_is_re_encoded_to_one_it_does() -> None:
    admitted = admit_image(make("WEBP", (100, 100)))
    plan = plan_transmission(admitted, SUPPORT)
    assert plan.derived is True
    assert plan.media_type == "image/png", "PNG is lossless and every approved route takes it"
    assert (plan.width, plan.height) == (100, 100), "no needless resize"


def test_a_route_that_takes_neither_the_image_nor_png_refuses_before_transmission() -> None:
    jpeg_only = SUPPORT.model_copy(update={"media_types": frozenset({"image/jpeg"})})
    with pytest.raises(AdmissionRefusedError, match="this route accepts"):
        plan_transmission(admit_image(make("WEBP")), jpeg_only)


def test_a_payload_still_too_large_after_derivation_is_refused_not_sent() -> None:
    tiny_budget = SUPPORT.model_copy(update={"max_byte_size": 8})
    with pytest.raises(AdmissionRefusedError, match="after derivation"):
        plan_transmission(admit_image(make("PNG", (900, 900))), tiny_budget)


def test_planning_is_deterministic_so_two_calls_bind_the_same_bytes() -> None:
    """§7 — derive once and reuse; if the two calls could differ, the ledger is theatre."""
    admitted = admit_image(make("PNG", (1500, 1000)))
    first = plan_transmission(admitted, SUPPORT)
    second = plan_transmission(admitted, SUPPORT)
    assert first.sha256 == second.sha256
    assert first.content == second.content
