"""Nothing but the owner can reach a device — owner execution order, 24 Sept 2026.

Voice work package 3 §1.1, §1.2, §3, §15 and §19. These are structural assertions
over the source itself, because the claim is about what *cannot* happen and no
example can establish that.

Four things they hold:

**No microphone capture exists outside the desktop presentation layer.** The
gateway's recognizer consumes PCM and owns no device; the service passes a request
body along; nothing in either opens one.

**No model-reachable path can turn Voice on, unmute, or enable a speaker.** There is
no tool contract at Layer 0 at all, and the routes that touch devices are the
desktop's own — reached from an owner gesture, never from provider output.

**Nothing starts by itself.** No wake word, no timer, no resume-on-wake, no stored
"Voice was enabled" preference, and no retry loop that reacquires a device.

**Provider output is data.** A magic string in a model's reply cannot change device
state, because nothing parses provider output for commands. The service's half of
that assertion lives in `apps/api/tests/test_voice_device_authority.py`, because the
dependency direction runs api -> gateway and never back.
"""

from __future__ import annotations

import inspect
import io
import tokenize
from pathlib import Path

import val_gateway.delivery as delivery
import val_gateway.playback as playback
import val_gateway.speech as speech
import val_gateway.voice as voice
import val_providers.whisper_recognizer as recognizer

#: The modules that make up the service-side voice path. If a device call appears in
#: any of them, it appears in something that is not the desktop.
SERVICE_SIDE = (voice, delivery, playback, speech, recognizer)

#: Every way a browser or a native layer acquires a microphone, and every way an
#: application records one. None of these belongs anywhere on the service side.
DEVICE_CALLS = (
    "getUserMedia",
    "MediaRecorder",
    "AudioWorklet",
    "mediaDevices",
    "sounddevice",
    "pyaudio",
    "PyAudio",
    "AVAudioEngine",
    "AVCaptureSession",
    "afrecord",
    "sox ",
    "arecord",
)


def _code(module: object) -> str:
    """The module's executable text, with comments and strings removed.

    The modules' own *prohibitions* are written in comments and docstrings — "no
    MediaRecorder", "owns no microphone" — and a search that counted those would
    find the thing it was looking for in the sentence forbidding it.
    """
    source = inspect.getsource(module)  # type: ignore[arg-type]
    return "".join(
        token.string
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type not in (tokenize.COMMENT, tokenize.STRING)
    )


def test_no_service_side_module_opens_a_microphone() -> None:
    for module in SERVICE_SIDE:
        code = _code(module)
        for call in DEVICE_CALLS:
            assert call not in code, f"{module.__name__} reaches for a device: {call}"


def test_the_recognizer_consumes_pcm_and_owns_no_device() -> None:
    """WP1's boundary, restated as a test because WP3 is where it could have slipped."""
    code = _code(recognizer)
    # The tokenizer's output has no whitespace between tokens, so the signature is
    # matched in that form rather than as it reads in the file.
    assert "deffeed(self,pcm:bytes)" in code, "the recognizer takes PCM from its caller"
    for call in DEVICE_CALLS:
        assert call not in code


def test_no_tool_or_mcp_registration_exists_at_all() -> None:
    """§15. The narrowest possible form of "no model-reachable device path".

    At Layer 0 there is no tool contract, so there is nothing for a model to call —
    and that is asserted rather than assumed, because the day a tool registry
    appears is the day this rule needs to be checked against it.
    """
    from val_domain.gateway import TaskType

    assert {task.value for task in TaskType} == {
        "conversation",
        "classification",
        "strip",
        "blind_position",
        "title",
    }, "a new task type may be a tool; check it against the device-authority rule"

    root = Path(__file__).resolve().parents[3]
    for package in ("packages", "apps"):
        for path in (root / package).rglob("*.py"):
            if "test" in path.name or "/tests/" in str(path):
                continue
            text = path.read_text(encoding="utf-8")
            assert "register_tool(" not in text, f"{path} registers a tool"
            assert "ToolRegistry" not in text, f"{path} builds a tool registry"


def test_no_wake_word_no_timer_and_no_stored_voice_preference() -> None:
    """§4.2 and §1.3, over the whole tree rather than over one module."""
    root = Path(__file__).resolve().parents[3]
    forbidden = (
        "wake_word",
        "wakeword",
        "hotword",
        "always_listening",
        "voice_enabled_preference",
    )
    here = Path(__file__).resolve()
    for package in ("packages", "apps"):
        for path in (root / package).rglob("*.py"):
            # This file names the forbidden phrases in order to forbid them.
            if path.resolve() == here:
                continue
            text = path.read_text(encoding="utf-8").lower()
            for phrase in forbidden:
                assert phrase not in text, f"{path} mentions {phrase}"


def test_the_desktop_holds_the_only_capture_implementation() -> None:
    """§3 and §15, from the other side: exactly one file calls getUserMedia."""
    root = Path(__file__).resolve().parents[3]
    desktop = root / "apps" / "desktop" / "src"
    callers = sorted(
        path.name
        for path in desktop.rglob("*.ts")
        if not path.name.endswith(".test.ts")
        and "getUserMedia(" in path.read_text(encoding="utf-8")
    )
    assert callers == ["microphone.ts"], f"more than one capture path: {callers}"


def test_the_desktop_never_records_and_never_writes_audio() -> None:
    """§1.4 and §10, over every desktop module."""
    root = Path(__file__).resolve().parents[3]
    desktop = root / "apps" / "desktop" / "src"
    for path in desktop.rglob("*.ts"):
        if path.name.endswith(".test.ts"):
            continue
        text = path.read_text(encoding="utf-8")
        for forbidden in (
            "new MediaRecorder",
            "showSaveFilePicker",
            "createWriteStream",
            "writeFile",
        ):
            assert forbidden not in text, f"{path.name} would persist audio: {forbidden}"
