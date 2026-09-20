"""Image admission and transmission planning — Attachment Substrate v1.2, §3.3 and §8.

Owner ruling, 19 September 2026 (Track C). Two deterministic decisions live
here, both pure functions over bytes, both made *before* anything is persisted
or reserved:

1. **Admission** (§3.3). The media type is established from the bytes
   themselves — never from the filename, never from EXIF — the image is decoded,
   and the dimensions are read from the decoded image. Malformed, unsupported,
   and implausibly large input is refused deterministically. **A failed
   admission writes nothing**: no blob, no attachment, no association, no
   processing event, and no user message from that send. That is why this
   function returns a value or raises, and touches no store.

2. **Transmission planning** (§8). The order is binding: *admit → derive if
   needed → reserve from the dimensions of the bytes that will actually be
   sent → call.* Reserving from the original's dimensions while sending a resize
   would be an invented number. So the plan is produced here, before the
   reservation, and the same plan is what the gateway binds to the call and, on
   a consequential turn, to the blind-position call as well (§7, derive once and
   reuse — the two calls must never independently resize).

**No provider adapter resizes anything.** An adapter receives the bytes this
module selected, already derived, and transmits them unchanged. That is the
whole reason resize policy is not in the adapter: two adapters resizing
independently is how the blind call and the final call come to see different
pixels while the ledger says they agreed.

Pillow is the one pinned image library (12.3.0), and it is used only to decode
and re-encode. The magic-number sniff below is deliberately independent of it:
the media type is established by an explicit rule over the leading bytes, and
Pillow's own detection must then agree. One library's guess is not a fact.
"""

from __future__ import annotations

import hashlib
import io
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import PIL
from PIL import Image, UnidentifiedImageError

from val_domain.gateway import ImageInputSupport

#: Magic numbers, as an explicit rule over the bytes. Order matters only in that
#: every prefix here is unambiguous; WEBP is checked on both of its markers.
_SIGNATURES: Final[tuple[tuple[str, str, bytes], ...]] = (
    ("image/png", "PNG", b"\x89PNG\r\n\x1a\n"),
    ("image/jpeg", "JPEG", b"\xff\xd8\xff"),
    ("image/gif", "GIF", b"GIF87a"),
    ("image/gif", "GIF", b"GIF89a"),
)

#: The still-image formats v1 admits. Animation is not admitted: flattening it
#: to a frame would silently change what the record says was sent, and moving
#: pictures are a later modality with their own governance (§18 of the ruling).
SUPPORTED_MEDIA_TYPES: Final[frozenset[str]] = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp"}
)

#: A decompression bound, stated rather than left to a library default. Bytes
#: arriving from outside the house are untrusted, and a 200-megapixel header
#: costs nothing to write and a great deal to decode.
MAX_DECODED_PIXELS: Final[int] = 80_000_000

#: The tool and version recorded on every derived representation (§3.4).
DERIVED_BY: Final[str] = f"Pillow {PIL.__version__}"


class AdmissionRefusedError(Exception):
    """The candidate bytes were not admitted. Nothing was written (§3.3)."""


@dataclass(frozen=True)
class AdmittedImage:
    """Ephemeral candidate bytes that passed the preflight — **not yet evidence**.

    The attachment identity does not exist at this point and no temporary row is
    invented so that the probe can record itself: the admission probe is
    pre-commit validation, which is exactly why `attachment_processing_events`
    has no `probe` intent (§3.5, correction 1).
    """

    content: bytes
    sha256: str
    byte_size: int
    media_type: str
    width: int
    height: int


@dataclass(frozen=True)
class Transmission:
    """The exact bytes that will be sent, decided before the reservation (§8).

    `derived` is False when the admitted original is transmitted unchanged, and
    True when a `model_input_image` representation had to be produced to satisfy
    the route's declared limits. Either way `sha256`, `width` and `height`
    describe **what leaves the house** — the figures that price the call and the
    figures that land on the `model_call_image_inputs` row, one set of facts.
    """

    content: bytes
    sha256: str
    byte_size: int
    media_type: str
    width: int
    height: int
    derived: bool
    #: Tool and pinned version; set only on a derived representation.
    derived_by: str | None

    @property
    def pixels(self) -> int:
        return self.width * self.height


def _sniff(candidate: bytes) -> tuple[str, str]:
    """The media type and expected decoder format, from the bytes alone."""
    for media_type, pillow_format, signature in _SIGNATURES:
        if candidate.startswith(signature):
            return media_type, pillow_format
    # RIFF....WEBP — the only two-part signature here.
    if len(candidate) >= 12 and candidate[:4] == b"RIFF" and candidate[8:12] == b"WEBP":
        return "image/webp", "WEBP"
    raise AdmissionRefusedError(
        "the bytes do not begin with a supported image signature "
        f"({', '.join(sorted(SUPPORTED_MEDIA_TYPES))}); the filename is not consulted"
    )


def admit_image(candidate: bytes) -> AdmittedImage:
    """§3.3's admission preflight over ephemeral candidate bytes.

    Hash, byte size, actual media type, decodability, dimensions, format
    support — and a refusal that names its reason, because "attachment failed"
    is not something the owner can act on.
    """
    if not candidate:
        raise AdmissionRefusedError("empty file")
    media_type, expected_format = _sniff(candidate)

    try:
        with Image.open(io.BytesIO(candidate)) as probe:
            probe.verify()  # structural check; invalidates the object, so reopen below
        with Image.open(io.BytesIO(candidate)) as image:
            detected = image.format
            width, height = image.size
            frames = getattr(image, "n_frames", 1)
            if width * height > MAX_DECODED_PIXELS:
                raise AdmissionRefusedError(
                    f"{width}x{height} exceeds the {MAX_DECODED_PIXELS:,}-pixel decode bound"
                )
            image.load()  # the decode itself must succeed, not merely the header
    except AdmissionRefusedError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as refused:
        raise AdmissionRefusedError(
            f"the bytes announce {media_type} but do not decode as one: {type(refused).__name__}"
        ) from refused

    if detected != expected_format:
        raise AdmissionRefusedError(
            f"the signature says {expected_format} and the decoder says {detected}; "
            "the two must agree before bytes are admitted"
        )
    if frames > 1:
        raise AdmissionRefusedError(
            f"an animated {media_type} ({frames} frames) is not admitted in v1: deriving a "
            "single frame would change what the record says was sent"
        )
    if width <= 0 or height <= 0:
        raise AdmissionRefusedError(f"decoded dimensions are not positive: {width}x{height}")

    return AdmittedImage(
        content=candidate,
        sha256=hashlib.sha256(candidate).hexdigest(),
        byte_size=len(candidate),
        media_type=media_type,
        width=width,
        height=height,
    )


def _reencode(image: Image.Image, media_type: str) -> tuple[bytes, str]:
    """Re-encode a resized image, keeping the source format where it survives.

    GIF and WEBP are re-encoded as PNG: both are lossless for the still images
    v1 admits, and PNG is the format every approved route accepts, so the
    derived bytes do not depend on a provider's less common decoder.
    """
    buffer = io.BytesIO()
    if media_type == "image/jpeg":
        image.convert("RGB").save(buffer, format="JPEG", quality=90, optimize=True)
        return buffer.getvalue(), "image/jpeg"
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), "image/png"


#: The quantity the house counts against the provider's request payload ceiling.
#: **A house interpretation of an ambiguous provider fact** (owner ruling,
#: 20 September 2026): the provider caps "512 MB total payload per request" and
#: nowhere says what is measured against it.
REQUEST_PAYLOAD_MEASURE = "data_uri_bytes"

#: The fixed parts of the data URI the adapter builds: `data:` + the media type
#: + `;base64,` + the encoding itself.
_DATA_URI_PREFIX = len("data:") + len(";base64,")


def data_uri_bytes(media_type: str, byte_size: int) -> int:
    """The exact length of the data URI the adapter will build, without building it.

    This is the house's conservative measure against the provider's undocumented
    "total payload" ceiling, and it is conservative because it is the **largest**
    image-attributable quantity the house actually puts on the wire:

        raw bytes  <  base64  <  the complete data URI

    Base64 is four characters per three bytes, and the URI adds its scheme, the
    media type and the marker on top of that. Counting the smaller quantities
    would let the house become more permissive than a limit whose meaning is not
    established, which is the one direction an ambiguous ceiling must not be
    read in.

    It is **not** a statement of how the provider meters the limit. If the
    documentation later defines the unit, this becomes a verified fact and the
    registry's `payload_unit_is_documented` flips deliberately.
    """
    return _DATA_URI_PREFIX + len(media_type) + 4 * ((byte_size + 2) // 3)


@dataclass(frozen=True)
class RequestImageLoad:
    """What one request's images amount to, measured before any are transmitted."""

    image_count: int
    payload_bytes: int
    measure: str = REQUEST_PAYLOAD_MEASURE


def request_load(transmitted: Sequence[tuple[str, int]]) -> RequestImageLoad:
    """The aggregate of `(media_type, byte_size)` pairs actually to be sent."""
    return RequestImageLoad(
        image_count=len(transmitted),
        payload_bytes=sum(data_uri_bytes(media_type, size) for media_type, size in transmitted),
    )


def check_request_limits(load: RequestImageLoad, support: ImageInputSupport) -> None:
    """Refuse a request whose aggregate exceeds a documented provider limit.

    Owner ruling, 20 September 2026. A turn whose images are each individually
    valid can still be an invalid request, and discovering that at the provider
    means the pixels have already left the machine. The refusal names the limit,
    the measured state, and which of the two was violated — and nothing here
    drops an attachment to make the turn fit, or splits one turn into several
    calls to slip past a request limit.
    """
    limits = support.provider_request
    if load.image_count > limits.max_images_per_request:
        raise AdmissionRefusedError(
            f"this turn carries {load.image_count:,} images and the provider accepts "
            f"{limits.max_images_per_request:,} per request (provider request limit: image "
            f"count). No image was transmitted."
        )
    if load.payload_bytes > limits.max_total_payload_bytes:
        qualifier = (
            ""
            if limits.payload_unit_is_documented
            else ", measured conservatively by the "
            "house as the data URIs it would send, because the provider does not define the unit"
        )
        raise AdmissionRefusedError(
            f"this turn's images come to {load.payload_bytes:,} bytes and the provider accepts "
            f"{limits.max_total_payload_bytes:,} per request (provider request limit: total "
            f"image data{qualifier}). No image was transmitted."
        )


def patch_count(width: int, height: int, support: ImageInputSupport) -> int:
    """The provider's patch count for these exact dimensions."""
    pixels = support.provider.patch_pixels
    return math.ceil(width / pixels) * math.ceil(height / pixels)


def within_provider_limits(width: int, height: int, support: ImageInputSupport) -> bool:
    """Both documented limits: the dimension bound **and** the patch budget."""
    return (
        max(width, height) <= support.provider.max_long_edge_pixels
        and patch_count(width, height, support) <= support.provider.patch_budget
    )


def fit_within_limits(width: int, height: int, support: ImageInputSupport) -> tuple[int, int]:
    """The largest aspect-preserving size that lands inside both documented limits.

    Owner correction, 20 September 2026. The earlier rule capped the long edge at
    1,600 — exactly right for a square and increasingly wrong as the aspect ratio
    departs from it. A 16:9 frame at 2048x1152 is 64 x 36 = 2,304 patches, already
    inside the budget, and the old rule shrank it to 1600x900 for no accounting
    reason at all. Storyboards, character sheets and production frames are
    precisely the material this slice exists for, so that resolution matters.

    **This does not reproduce the provider's own shrink.** Matching someone
    else's arithmetic is what produced the one-token discrepancy, and it would
    drift the moment they adjusted it. The only requirement is that the
    transmitted image land inside both documented limits, so the provider
    performs no resize and the documented formula applies exactly.

    **The rule, stated so it can be checked rather than inferred.** The long edge
    is the search variable. For a candidate long edge L, the short edge is the
    exact proportional value **floored**:

        short = max(1, floor(source_short * L / source_long))

    The chosen L is the **largest integer** in `[1, min(source_long,
    max_long_edge_pixels)]` for which both limits hold. Patch count is
    non-decreasing in L, so that maximum is unique and a binary search finds it.

    **The tie-break, because one is owed.** Each candidate L yields exactly one
    dimension pair, and the largest feasible L is taken; there is therefore no
    set of distinct pairs at the same maximal scale to choose between. Flooring
    the short edge is what makes the pair a function of L rather than of a
    rounding mood, and it never rounds *up* into the limit that was being
    respected. The consequence is what matters downstream: identical source
    bytes and identical capability facts always produce identical dimensions,
    and so identical derived bytes and an identical digest — which blind/final
    equality and provenance both rest on.
    """
    longest = max(width, height)
    shortest = min(width, height)
    ceiling = min(longest, support.provider.max_long_edge_pixels)

    def pair(long_edge: int) -> tuple[int, int]:
        short_edge = max(1, (shortest * long_edge) // longest)
        return (long_edge, short_edge) if width >= height else (short_edge, long_edge)

    low, high, best = 1, ceiling, None
    while low <= high:
        middle = (low + high) // 2
        candidate = pair(middle)
        if within_provider_limits(*candidate, support):
            best, low = candidate, middle + 1
        else:
            high = middle - 1
    if best is None:  # unreachable: a 1-pixel image is one patch
        raise AdmissionRefusedError(
            "no aspect-preserving size of this image fits the route's documented limits"
        )
    return best


def derivation_required(admitted: AdmittedImage, support: ImageInputSupport) -> bool:
    """Whether this route needs a `model_input_image` derived, without doing the work.

    Owner correction, 20 September 2026. Core must be able to answer this
    *before* recording a derivation attempt: writing `derive:model_input_image
    started -> succeeded` for an original transmitted unchanged records that a
    derivation succeeded when none occurred, which is a false statement in an
    evidence table whose whole purpose is honest attempts.

    `plan_transmission` reads the same predicate, so the decision and the work
    cannot drift apart.
    """
    return not (
        within_provider_limits(admitted.width, admitted.height, support)
        and admitted.byte_size <= support.house.max_byte_size
        and admitted.media_type in support.provider.media_types
    )


def plan_transmission(admitted: AdmittedImage, support: ImageInputSupport) -> Transmission:
    """What will actually be sent to this route, decided before the reservation.

    The original is transmitted unchanged when it already satisfies the route's
    declared limits. Otherwise a `model_input_image` is derived: scaled by the
    long edge, re-encoded once, and measured from the decoded result. A route
    that declares no support for the admitted media type refuses here rather
    than at the provider, because a refusal after transmission has already sent
    the pixels.
    """
    # A JPEG stays a JPEG when it has to be derived; everything else becomes PNG.
    # The route must accept the original or that target, or there is nothing to
    # send — and refusing here is refusing *before* the pixels leave the house.
    target = "image/jpeg" if admitted.media_type == "image/jpeg" else "image/png"
    accepted = support.provider.media_types
    if admitted.media_type not in accepted and target not in accepted:
        raise AdmissionRefusedError(
            f"this route accepts {', '.join(sorted(accepted))}; the image is "
            f"{admitted.media_type} and would be derived as {target}"
        )

    # Never upscale, and never derive an image that already satisfies both
    # documented limits and the house's own byte ceiling: it goes as it is.
    if not derivation_required(admitted, support):
        return Transmission(
            content=admitted.content,
            sha256=admitted.sha256,
            byte_size=admitted.byte_size,
            media_type=admitted.media_type,
            width=admitted.width,
            height=admitted.height,
            derived=False,
            derived_by=None,
        )

    width, height = fit_within_limits(admitted.width, admitted.height, support)
    with Image.open(io.BytesIO(admitted.content)) as image:
        image.load()
        unchanged = (width, height) == (admitted.width, admitted.height)
        resized = image if unchanged else image.resize((width, height), Image.Resampling.LANCZOS)
        content, media_type = _reencode(resized, admitted.media_type)

    # Measured from the derived bytes, never assumed from the arithmetic above:
    # these are the figures that price the call and land on the record.
    with Image.open(io.BytesIO(content)) as derived:
        derived.load()
        width, height = derived.size

    if len(content) > support.house.max_byte_size:
        raise AdmissionRefusedError(
            f"the image is {len(content):,} bytes after derivation and this house sends at "
            f"most {support.house.max_byte_size:,} per image"
        )
    return Transmission(
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        byte_size=len(content),
        media_type=media_type,
        width=width,
        height=height,
        derived=True,
        derived_by=DERIVED_BY,
    )
