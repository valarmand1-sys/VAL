"""Nothing but the owner can reach a device, at the service — 24 September 2026.

Voice work package 3 §1.1, §1.2, §15 and §19, for the part of the claim that is
about `val_api`. It lives here rather than beside the gateway's half because the
dependency direction runs api → gateway and never back (`01-architecture.md` §3),
and a structural test is not a reason to bend that.

What is asserted: the service opens no device, its device-facing routes require a
live owner-started session, and **provider output cannot change device state** —
nothing anywhere inspects a model's text for an instruction.
"""

from __future__ import annotations

import inspect
import io
import tokenize

import val_api.app as service_app

#: Every way a browser or a native layer acquires a microphone, and every way an
#: application records one. None of these belongs in the service.
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
    "arecord",
)


def _code(module: object) -> str:
    """The module's executable text, with comments and strings removed.

    The module's own prohibitions are written in comments, and a search that counted
    those would find the thing it was looking for in the sentence forbidding it.
    """
    source = inspect.getsource(module)  # type: ignore[arg-type]
    return "".join(
        token.string
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type not in (tokenize.COMMENT, tokenize.STRING)
    )


def test_the_service_opens_no_microphone() -> None:
    code = _code(service_app)
    for call in DEVICE_CALLS:
        assert call not in code, f"the service reaches for a device: {call}"


def test_provider_output_cannot_change_device_state() -> None:
    """§15's last clause: a magic string in a reply is not a command."""
    code = _code(service_app).replace(" ", "")
    for pattern in ('if"voice', 'startswith("/', '=="voice_on', "eval(", "exec("):
        assert pattern not in code, f"the service dispatches on text: {pattern}"
    # The device-facing routes take their arguments from the request path and body
    # only, which is what makes them the desktop's and not the model's.
    assert "defopen_voice_session(request:VoiceSessionRequest)" in code
    assert "defcollect_speech(session:UUID)" in code


def test_every_device_facing_route_requires_a_live_owner_started_session() -> None:
    """§1.2. With no session there is no sink, so nothing can be played."""
    code = _code(service_app)
    assert "voice_session_or_404" in code
    for route in ("collect_speech", "report_playback"):
        marker = f"def{route}("
        assert marker in code, f"{route} is not defined"
        body = code.split(marker, 1)[1][:800]
        assert "voice_session_or_404" in body, f"{route} does not require a live session"
