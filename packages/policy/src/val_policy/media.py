"""Admitting media that is not a still image — owner execution order, 22 September 2026.

The image admission of `val_policy.attachments` is unchanged and still owns
images. This module adds the two modalities the owner's path now carries, on the
same terms: **the media type is established from the bytes, never from the
filename**, the structure is checked rather than trusted, and a refusal names its
reason because *"attachment failed"* is not something anyone can act on.

**What can honestly be checked without a new dependency, and what cannot.**

- **WAV** is checked properly. Python's `wave` module is in the standard library
  and parses the RIFF header, the `fmt ` chunk and the `data` chunk, so channels,
  sample rate, sample width and frame count are read from the file rather than
  assumed, and the duration is computed from them. A file that does not open is
  refused.
- **MP4** is checked *structurally*. There is no MP4 decoder in the standard
  library and this order does not authorise adding one to Val's pinned
  environment, so this module walks the top-level box structure — `ftyp` first,
  with a brand this house recognises, and a `moov` present — and reads the
  duration from `mvhd` when it is there. **That is a container check, not a
  decode**, and it is recorded as one: a file that passes here can still turn out
  to be unreadable by the perception runtime, which then fails closed and says
  so. Claiming more than a container check would be claiming a decode that did
  not happen.

The ceilings are house policy, stated rather than left to whatever a library
happens to tolerate: bytes arriving from outside are untrusted, and a header
promising four hours of video costs nothing to write.
"""

from __future__ import annotations

import hashlib
import io
import struct
import wave
from dataclasses import dataclass, field
from typing import Final, Literal

from val_policy.attachments import AdmissionRefusedError, admit_image

#: The modalities the owner's attachment path carries. Each is admitted by its
#: own rule and perceived by its own admitted specialist.
Modality = Literal["image", "video", "audio"]

#: The video container this order puts into production tonight. One, on purpose:
#: a format that cannot be checked is a format that should not be admitted.
SUPPORTED_VIDEO_MEDIA_TYPES: Final[frozenset[str]] = frozenset({"video/mp4"})

#: The audio container this order puts into production tonight. WAV is chosen
#: over the compressed formats precisely because it can be verified here with
#: nothing but the standard library.
SUPPORTED_AUDIO_MEDIA_TYPES: Final[frozenset[str]] = frozenset({"audio/wav"})

#: House ceilings on an admitted original. Generous enough for real material and
#: bounded enough that a malformed header cannot ask the machine for everything.
MAX_VIDEO_BYTES: Final[int] = 512 * 1024 * 1024
MAX_AUDIO_BYTES: Final[int] = 128 * 1024 * 1024
MAX_VIDEO_SECONDS: Final[float] = 600.0
MAX_AUDIO_SECONDS: Final[float] = 3600.0

#: `ftyp` brands this house recognises as MP4. QuickTime (`qt  `) is deliberately
#: absent: it is a different container that often carries the same extension, and
#: admitting it under `video/mp4` would make the record say something untrue.
_MP4_BRANDS: Final[frozenset[bytes]] = frozenset(
    {b"isom", b"iso2", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1", b"dash", b"M4V "}
)


@dataclass(frozen=True)
class AdmittedMedia:
    """Ephemeral candidate bytes that passed admission — **not yet evidence**.

    The union of what the three modalities can say about themselves. `width` and
    `height` are the image facts and are 0 elsewhere; `duration_seconds` is the
    time-based fact and is `None` for a still image, and `None` for a video whose
    container did not state one.

    `verified` records **how far the check actually went**, so a reader can tell
    a decoded file from a structurally-checked one without reading this module.
    """

    content: bytes = field(repr=False)
    sha256: str
    byte_size: int
    media_type: str
    modality: Modality
    width: int = 0
    height: int = 0
    duration_seconds: float | None = None
    verified: str = "decoded"


def modality_of(media_type: str) -> Modality:
    """The modality of an admitted media type. Raises rather than guessing."""
    if media_type in SUPPORTED_VIDEO_MEDIA_TYPES:
        return "video"
    if media_type in SUPPORTED_AUDIO_MEDIA_TYPES:
        return "audio"
    if media_type.startswith("image/"):
        return "image"
    raise AdmissionRefusedError(f"{media_type!r} belongs to no admitted modality")


def admit_media(candidate: bytes) -> AdmittedMedia:
    """Admit one candidate file of any admitted modality, or refuse it by name.

    Images keep their existing admission exactly — same decode, same dimension
    read, same refusals — so nothing about Track C's behaviour moves.
    """
    if not candidate:
        raise AdmissionRefusedError("empty file")
    if _is_mp4(candidate):
        return _admit_mp4(candidate)
    if _is_wav(candidate):
        return _admit_wav(candidate)
    image = admit_image(candidate)
    return AdmittedMedia(
        content=image.content,
        sha256=image.sha256,
        byte_size=image.byte_size,
        media_type=image.media_type,
        modality="image",
        width=image.width,
        height=image.height,
        verified="decoded",
    )


# --- video ---------------------------------------------------------------------------


def _is_mp4(candidate: bytes) -> bool:
    """Whether the leading bytes are an MP4 `ftyp` box. Signature only."""
    return len(candidate) >= 12 and candidate[4:8] == b"ftyp"


def _admit_mp4(candidate: bytes) -> AdmittedMedia:
    if len(candidate) > MAX_VIDEO_BYTES:
        raise AdmissionRefusedError(
            f"the file is {len(candidate):,} bytes, over this house's "
            f"{MAX_VIDEO_BYTES:,}-byte ceiling for an admitted video"
        )
    brand = candidate[8:12]
    compatible = _compatible_brands(candidate)
    if brand not in _MP4_BRANDS and not (compatible & _MP4_BRANDS):
        named = brand.decode("latin-1").strip()
        raise AdmissionRefusedError(
            f"the container announces the brand {named!r}, which this house does not admit "
            f"as MP4 ({', '.join(sorted(b.decode().strip() for b in _MP4_BRANDS))})"
        )

    boxes = _top_level_boxes(candidate)
    if "moov" not in boxes:
        raise AdmissionRefusedError(
            "the MP4 container has no `moov` box, so it carries no track metadata and "
            "is not a playable file"
        )
    duration = _mp4_duration(candidate, boxes["moov"])
    if duration is not None and duration > MAX_VIDEO_SECONDS:
        raise AdmissionRefusedError(
            f"the container states {duration:,.1f} seconds, over this house's "
            f"{MAX_VIDEO_SECONDS:,.0f}-second ceiling for an admitted video"
        )
    return AdmittedMedia(
        content=candidate,
        sha256=hashlib.sha256(candidate).hexdigest(),
        byte_size=len(candidate),
        media_type="video/mp4",
        modality="video",
        duration_seconds=duration,
        # Said plainly: the container was walked, the frames were not decoded.
        verified="container_structure",
    )


def _compatible_brands(candidate: bytes) -> frozenset[bytes]:
    """The `ftyp` box's compatible-brands list, which is where mp4 often hides."""
    try:
        size = struct.unpack(">I", candidate[0:4])[0]
    except struct.error:
        return frozenset()
    if size < 16 or size > len(candidate):
        return frozenset()
    body = candidate[16:size]
    return frozenset(body[index : index + 4] for index in range(0, len(body) - 3, 4))


def _top_level_boxes(candidate: bytes) -> dict[str, tuple[int, int]]:
    """Every top-level box, by type, as (offset, size). Bounded and defensive.

    A malformed length is a refusal rather than a loop: a box claiming zero bytes
    would otherwise walk this parser forever over untrusted input.
    """
    boxes: dict[str, tuple[int, int]] = {}
    offset = 0
    total = len(candidate)
    while offset + 8 <= total:
        size = struct.unpack(">I", candidate[offset : offset + 4])[0]
        name = candidate[offset + 4 : offset + 8].decode("latin-1")
        if size == 1:
            if offset + 16 > total:
                break
            size = struct.unpack(">Q", candidate[offset + 8 : offset + 16])[0]
        elif size == 0:
            size = total - offset  # "to end of file", per the specification
        if size < 8 or offset + size > total:
            raise AdmissionRefusedError(
                f"the MP4 box {name!r} declares a length the file does not contain; "
                "the container is malformed"
            )
        boxes.setdefault(name, (offset, size))
        offset += size
    return boxes


def _mp4_duration(candidate: bytes, moov: tuple[int, int]) -> float | None:
    """Seconds, from `moov`'s `mvhd` header, or `None` if it does not say."""
    offset, size = moov
    body = candidate[offset + 8 : offset + size]
    marker = body.find(b"mvhd")
    if marker < 0 or marker + 24 > len(body):
        return None
    version = body[marker + 4]
    try:
        if version == 1:
            timescale, duration = struct.unpack(">IQ", body[marker + 24 : marker + 36])
        else:
            timescale, duration = struct.unpack(">II", body[marker + 16 : marker + 24])
    except struct.error:
        return None
    if timescale <= 0:
        return None
    return round(float(duration) / float(timescale), 3)


# --- audio ---------------------------------------------------------------------------


def _is_wav(candidate: bytes) -> bool:
    return len(candidate) >= 12 and candidate[:4] == b"RIFF" and candidate[8:12] == b"WAVE"


def _admit_wav(candidate: bytes) -> AdmittedMedia:
    if len(candidate) > MAX_AUDIO_BYTES:
        raise AdmissionRefusedError(
            f"the file is {len(candidate):,} bytes, over this house's "
            f"{MAX_AUDIO_BYTES:,}-byte ceiling for an admitted recording"
        )
    try:
        with wave.open(io.BytesIO(candidate)) as reader:
            channels = reader.getnchannels()
            rate = reader.getframerate()
            frames = reader.getnframes()
            width = reader.getsampwidth()
    except (wave.Error, EOFError, OSError, ValueError) as refused:
        raise AdmissionRefusedError(
            f"the bytes announce WAVE but do not parse as one: {type(refused).__name__}"
        ) from refused

    if channels <= 0 or rate <= 0 or width <= 0:
        raise AdmissionRefusedError(
            f"the recording declares {channels} channel(s) at {rate} Hz and "
            f"{width}-byte samples, which is not a readable format"
        )
    if frames <= 0:
        raise AdmissionRefusedError("the recording contains no audio frames")
    duration = round(frames / rate, 3)
    if duration > MAX_AUDIO_SECONDS:
        raise AdmissionRefusedError(
            f"the recording is {duration:,.1f} seconds, over this house's "
            f"{MAX_AUDIO_SECONDS:,.0f}-second ceiling"
        )
    return AdmittedMedia(
        content=candidate,
        sha256=hashlib.sha256(candidate).hexdigest(),
        byte_size=len(candidate),
        media_type="audio/wav",
        modality="audio",
        duration_seconds=duration,
        # The RIFF header, the format chunk and the frame count were all read.
        verified="decoded_header",
    )
