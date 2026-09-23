"""Admitting video and audio — owner execution order, 22 September 2026.

The rule under test is the same one images have had since Track C: **the media
type comes from the bytes, never from the filename**, and a refusal names its
reason. What is added here is the honesty about depth — a WAV is genuinely
parsed, an MP4 container is genuinely walked, and neither claims to be the other.
"""

from __future__ import annotations

import io
import struct
import wave

import pytest
from PIL import Image

from val_policy.attachments import AdmissionRefusedError
from val_policy.media import (
    MAX_AUDIO_SECONDS,
    MAX_VIDEO_SECONDS,
    admit_media,
    modality_of,
)


def png(colour: str = "navy") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), colour).save(buffer, format="PNG")
    return buffer.getvalue()


def wav(seconds: float = 1.0, rate: int = 16_000, channels: int = 1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(b"\x00\x00" * int(rate * seconds) * channels)
    return buffer.getvalue()


def box(name: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body) + 8) + name + body


def mvhd(duration_seconds: float, timescale: int = 1000) -> bytes:
    body = (
        bytes([0, 0, 0, 0])  # version 0, flags
        + struct.pack(">I", 0)  # creation time
        + struct.pack(">I", 0)  # modification time
        + struct.pack(">I", timescale)
        + struct.pack(">I", int(duration_seconds * timescale))
        + b"\x00" * 80
    )
    return box(b"mvhd", body)


def mp4(brand: bytes = b"isom", duration_seconds: float = 9.0, moov: bool = True) -> bytes:
    ftyp = box(b"ftyp", brand + struct.pack(">I", 512) + b"isomiso2mp41")
    parts = [ftyp, box(b"mdat", b"\x00" * 64)]
    if moov:
        parts.insert(1, box(b"moov", mvhd(duration_seconds)))
    return b"".join(parts)


# --- the modality comes from the bytes ---------------------------------------------


def test_each_medium_is_recognised_from_its_own_signature() -> None:
    assert admit_media(png()).modality == "image"
    assert admit_media(mp4()).modality == "video"
    assert admit_media(wav()).modality == "audio"


def test_the_filename_is_never_consulted() -> None:
    """A WAV named `.mp4` is still a WAV, and the record says so."""
    admitted = admit_media(wav())
    assert admitted.media_type == "audio/wav"
    assert admitted.modality == "audio"


def test_modality_of_refuses_rather_than_guessing() -> None:
    assert modality_of("image/png") == "image"
    assert modality_of("video/mp4") == "video"
    assert modality_of("audio/wav") == "audio"
    with pytest.raises(AdmissionRefusedError, match="no admitted modality"):
        modality_of("application/pdf")


# --- what each check actually proves -----------------------------------------------


def test_a_wav_is_genuinely_parsed_and_its_length_computed() -> None:
    admitted = admit_media(wav(seconds=2.5, rate=16_000))
    assert admitted.verified == "decoded_header", "the header really was read"
    assert admitted.duration_seconds == pytest.approx(2.5)
    assert admitted.byte_size == len(admitted.content)
    assert admitted.width == 0 and admitted.height == 0, "a recording has no pixels"


def test_an_mp4_is_checked_structurally_and_says_so() -> None:
    """The honesty that matters: a container walk is not a decode.

    Claiming `decoded` here would claim work that did not happen, and the record
    would then be unable to tell a checked file from a trusted one.
    """
    admitted = admit_media(mp4(duration_seconds=9.0))
    assert admitted.verified == "container_structure"
    assert admitted.media_type == "video/mp4"
    assert admitted.duration_seconds == pytest.approx(9.0)


def test_an_image_is_still_genuinely_decoded() -> None:
    admitted = admit_media(png())
    assert admitted.verified == "decoded"
    assert (admitted.width, admitted.height) == (64, 48)
    assert admitted.duration_seconds is None, "a still image has no duration"


# --- refusals name their reason ------------------------------------------------------


def test_an_mp4_without_track_metadata_is_refused() -> None:
    with pytest.raises(AdmissionRefusedError, match="no `moov` box"):
        admit_media(mp4(moov=False))


def test_a_container_this_house_does_not_admit_as_mp4_is_refused() -> None:
    """QuickTime often wears the same extension. It is a different container."""
    with pytest.raises(AdmissionRefusedError, match="does not admit"):
        admit_media(mp4(brand=b"qt  ").replace(b"isomiso2mp41", b"qt  qt  qt  "))


def test_a_box_claiming_more_bytes_than_the_file_holds_is_refused() -> None:
    """Untrusted input, so a malformed length is a refusal and not a loop."""
    broken = bytearray(mp4())
    broken[0:4] = struct.pack(">I", 1 << 30)
    with pytest.raises(AdmissionRefusedError, match="the file does not contain"):
        admit_media(bytes(broken))


def test_bytes_announcing_wave_that_do_not_parse_are_refused() -> None:
    with pytest.raises(AdmissionRefusedError, match="do not parse as one"):
        admit_media(b"RIFF" + b"\x00\x00\x00\x08" + b"WAVE" + b"rubbish")


def test_a_recording_with_no_frames_is_refused() -> None:
    with pytest.raises(AdmissionRefusedError, match="no audio frames"):
        admit_media(wav(seconds=0))


def test_an_empty_file_is_refused_whatever_it_claims_to_be() -> None:
    with pytest.raises(AdmissionRefusedError, match="empty file"):
        admit_media(b"")


def test_material_over_the_house_ceiling_is_refused_by_its_own_header() -> None:
    """The ceiling is checked against what the container states, before any read."""
    with pytest.raises(AdmissionRefusedError, match="second ceiling"):
        admit_media(mp4(duration_seconds=MAX_VIDEO_SECONDS + 1))
    assert MAX_AUDIO_SECONDS == 3600.0, "the audio ceiling is stated, not implied"


def test_an_unsupported_file_falls_through_to_the_image_refusal() -> None:
    """A PDF is neither audio nor video, so it meets the image signature rule."""
    with pytest.raises(AdmissionRefusedError, match="supported image signature"):
        admit_media(b"%PDF-1.7 not an image")
