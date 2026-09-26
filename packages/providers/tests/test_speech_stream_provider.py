"""Streamed synthesis through the resident worker — owner order, 26 September 2026.

A real child process speaks the worker's `speak_stream` protocol: one JSON line per
piece (a small WAV, base64), then the report with the digest of the whole. The
provider hands each piece over as it arrives, rebuilds the whole in memory, and
refuses a whole that does not match the digest the runner reported.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from test_speech_adapter import RecordingRunner, adapter, voice

from val_domain.speech import SpeechRequest
from val_providers.qwen_tts_speech import SpeechUnavailableError

STREAMER = """
import base64, hashlib, io, json, sys, wave
MODE = sys.argv[1]
def wav(frames):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(frames)
    return out.getvalue()
json.loads(sys.stdin.readline())
print(json.dumps({"ok": True, "mode": "ready", "load_seconds": 0.0}), flush=True)
for line in sys.stdin:
    request = json.loads(line)
    if request.get("mode") == "stop":
        break
    if MODE == "die_before":
        sys.exit(3)
    pieces = [bytes([n]) * 480 for n in (1, 2, 3)]
    for n, frames in enumerate(pieces):
        print(json.dumps({"chunk": n, "duration_seconds": 0.01,
                          "wav_base64": base64.b64encode(wav(frames)).decode()}), flush=True)
        if MODE == "die_after_first":
            sys.exit(3)
    whole = wav(b"".join(pieces))
    digest = hashlib.sha256(whole).hexdigest() if MODE != "wrong_digest" else "0" * 64
    print(json.dumps({"ok": True, "sample_rate": 24000, "duration_seconds": 0.03,
                      "audio_sha256": digest, "clone_prompt_sha256": "c" * 64,
                      "generation": {}}), flush=True)
"""


class StreamingRunner(RecordingRunner):
    def __init__(self, mode: str = "ok") -> None:
        super().__init__({})
        self.mode = mode

    def start(self, argv: list[str]) -> subprocess.Popen[str]:
        return subprocess.Popen(  # noqa: S603 - this interpreter, a fixed script
            [sys.executable, "-c", STREAMER, self.mode],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )


def speak(provider: object, pieces: list[tuple[int, float]]) -> object:
    return provider.synthesize_stream(  # type: ignore[attr-defined]
        SpeechRequest(text="My lord, good evening.", voice=voice()),
        lambda audio, seconds: pieces.append((len(audio), seconds)),
    )


def test_pieces_are_handed_over_as_they_arrive_and_reassemble(tmp_path: Path) -> None:
    provider = adapter(StreamingRunner(), tmp_path)
    provider.warm()
    pieces: list[tuple[int, float]] = []
    result = speak(provider, pieces)
    assert len(pieces) == 3
    assert result is not None
    assert result.generation["stream"] is True  # type: ignore[attr-defined]
    assert result.audio.startswith(b"RIFF")  # type: ignore[attr-defined]
    provider.release()


def test_with_no_worker_serving_the_caller_speaks_it_whole(tmp_path: Path) -> None:
    provider = adapter(StreamingRunner(), tmp_path)
    assert speak(provider, []) is None


def test_a_worker_that_fails_before_any_piece_leaves_the_whole_path(tmp_path: Path) -> None:
    provider = adapter(StreamingRunner("die_before"), tmp_path)
    provider.warm()
    pieces: list[tuple[int, float]] = []
    assert speak(provider, pieces) is None
    assert pieces == [] and not provider.resident


def test_a_failure_part_way_is_a_failure_not_a_silent_gap(tmp_path: Path) -> None:
    provider = adapter(StreamingRunner("die_after_first"), tmp_path)
    provider.warm()
    pieces: list[tuple[int, float]] = []
    with pytest.raises(SpeechUnavailableError, match="part-way"):
        speak(provider, pieces)
    assert len(pieces) == 1


def test_pieces_that_do_not_reassemble_to_the_reported_waveform_are_refused(
    tmp_path: Path,
) -> None:
    provider = adapter(StreamingRunner("wrong_digest"), tmp_path)
    provider.warm()
    with pytest.raises(SpeechUnavailableError, match="reassemble"):
        speak(provider, [])
    provider.release()
