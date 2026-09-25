"""What the capture pipeline does to recognition — WP3 repair pass §2.

Two candidate defects, tested against the **same** recognizer the application
uses: the same pinned whisper.cpp build, the same admitted ggml-small.en and
Silero models, the same helper, the same endpoint configuration. It is driven
directly over the helper's framed protocol so this probe runs inside the voice
runtime, which is the only environment holding numpy — production's dependencies
are untouched.

The material is the existing frozen fixture. **No owner audio is involved**, no
audio is written anywhere, and no model is downloaded or changed.

**Candidate 1 — chunk ordering.** The desktop forwarded each 20 ms chunk with
`void this.forward(pcm)`: fifty concurrent, unawaited POSTs per second whose
arrival order at the service is not guaranteed. This feeds the recognizer audio
with small local reorderings and measures what they do to the transcript.

**Candidate 2 — resampling.** The AudioWorklet decimated by *picking* every Nth
sample with no low-pass filter, while its own comment claimed a decimating
average. Picking folds everything above 8 kHz back into the speech band.
"""

from __future__ import annotations

import json
import math
import os
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
FIXTURE = ROOT / "infrastructure/voice/fixtures/frozen-utterance.wav"
HELPER = ROOT / "infrastructure/voice/whisper_listen.py"
VENV = Path.home() / ".val-runtimes" / "voice-venv" / "bin" / "python"
LIBRARY = Path.home() / ".val-runtimes" / "whisper.cpp" / "build" / "bin" / "libwhisper.dylib"
MODELS = Path.home() / ".val-models" / "whisper"
SAMPLE_RATE = 16_000
BLOCK = 320  # 20 ms, exactly the desktop's chunk

#: The production endpoint configuration, as shipped.
ENDPOINT = {
    "threshold": 0.5,
    "min_speech_ms": 220,
    "min_silence_ms": 650,
    "speech_pad_ms": 80,
    "max_utterance_s": 30.0,
}

FRAME_AUDIO, FRAME_CONTROL = 0, 1


def listen(blocks: list[np.ndarray], *, endpoint: dict | None = None) -> dict:
    """Run the real helper over these blocks and return what it reported."""
    configuration = json.dumps(
        {
            "model": str(MODELS / "ggml-small.en.bin"),
            "vad_model": str(MODELS / "ggml-silero-v6.2.0.bin"),
            "endpoint": endpoint or ENDPOINT,
        }
    )
    process = subprocess.Popen(
        [str(VENV), str(HELPER), configuration],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "VAL_WHISPER_LIB": str(LIBRARY)},
    )
    assert process.stdin and process.stdout
    events: list[dict] = []

    def send(kind: int, payload: bytes) -> None:
        process.stdin.write(struct.pack("<II", kind, len(payload)) + payload)
        process.stdin.flush()

    # The helper announces itself when the models are loaded.
    while True:
        line = process.stdout.readline()
        if not line:
            raise SystemExit("the helper exited before it was ready")
        event = json.loads(line)
        events.append(event)
        if event.get("event") == "ready":
            break
        if event.get("event") == "error":
            raise SystemExit(f"the helper refused to start: {event}")

    for block in blocks:
        send(FRAME_AUDIO, (np.clip(block, -1, 1) * 32767.0).astype("<i2").tobytes())
    # A tail of true silence so the endpoint fires on its own.
    silence = np.zeros(BLOCK, dtype=np.float32)
    for _ in range(80):
        send(FRAME_AUDIO, silence.astype("<i2").tobytes())
    send(FRAME_CONTROL, json.dumps({"action": "flush"}).encode())
    deadline = time.monotonic() + 90
    finals: list[dict] = []
    while time.monotonic() < deadline:
        line = process.stdout.readline()
        if not line:
            break
        event = json.loads(line)
        events.append(event)
        if event.get("event") == "final":
            finals.append(event)
            break
    send(FRAME_CONTROL, json.dumps({"action": "stop"}).encode())
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
    return {
        "transcript": " ".join((f.get("text") or "").strip() for f in finals).strip(),
        "utterances": sum(1 for e in events if e.get("event") == "final"),
        "endpoints": [e.get("reason") for e in events if e.get("event") == "speech_end"],
        "speech_starts": sum(1 for e in events if e.get("event") == "speech_start"),
    }


def read_fixture() -> np.ndarray:
    with wave.open(str(FIXTURE), "rb") as handle:
        assert handle.getframerate() == SAMPLE_RATE and handle.getnchannels() == 1
        raw = handle.readframes(handle.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def blocks_of(samples: np.ndarray) -> list[np.ndarray]:
    return [samples[i : i + BLOCK] for i in range(0, samples.size, BLOCK)]


def reordered(blocks: list[np.ndarray], distance: int) -> list[np.ndarray]:
    """What unordered concurrent POSTs do: a block arrives `distance` late."""
    out = list(blocks)
    for index in range(0, len(out) - distance, distance + 1):
        out[index], out[index + distance] = out[index + distance], out[index]
    return out


def upsample(samples: np.ndarray, factor: int) -> np.ndarray:
    source = np.arange(samples.size)
    target = np.linspace(0, samples.size - 1, samples.size * factor)
    return np.interp(target, source, samples).astype(np.float32)


def decimate_by_picking(samples: np.ndarray, ratio: float) -> np.ndarray:
    """The shipped worklet: advance an accumulator and keep one sample per bin."""
    out, position = [], 0.0
    for value in samples:
        position += 1
        if position < ratio:
            continue
        position -= ratio
        out.append(float(value))
    return np.asarray(out, dtype=np.float32)


def decimate_by_average(samples: np.ndarray, ratio: float) -> np.ndarray:
    """The fix: average every sample in the bin — a box low-pass, then decimate."""
    out, position, total, count = [], 0.0, 0.0, 0
    for value in samples:
        total += float(value)
        count += 1
        position += 1
        if position < ratio:
            continue
        position -= ratio
        out.append(total / count)
        total, count = 0.0, 0
    return np.asarray(out, dtype=np.float32)


def band_energy(samples: np.ndarray, low: float, high: float) -> float:
    spectrum = np.abs(np.fft.rfft(samples * np.hanning(samples.size)))
    freqs = np.fft.rfftfreq(samples.size, 1 / SAMPLE_RATE)
    band = (freqs >= low) & (freqs < high)
    return float(np.sum(spectrum[band] ** 2))


def main() -> None:
    original = read_fixture()
    report: dict[str, object] = {
        "probe": "capture pipeline against the production recognizer",
        "recognizer": "whisper.cpp v1.9.4 927cfce3, ggml-small.en, Silero v6.2.0, CPU",
        "endpoint": ENDPOINT,
        "fixture": FIXTURE.name,
        "fixture_seconds": round(original.size / SAMPLE_RATE, 3),
        "expected": "And so, my fellow Americans,",
        "owner_audio_involved": False,
    }

    report["baseline"] = listen(blocks_of(original))

    ordering: dict[str, object] = {}
    for distance in (1, 2, 4):
        ordering[f"a_block_arrives_{distance}_late"] = listen(reordered(blocks_of(original), distance))
    report["chunk_reordering"] = ordering

    at48 = upsample(original, 3)
    picked = decimate_by_picking(at48, 3.0)
    averaged = decimate_by_average(at48, 3.0)
    report["resampling"] = {
        "device_rate": 48_000,
        "original_energy_4k_8k": round(band_energy(original, 4000, 8000), 3),
        "picked": {
            **listen(blocks_of(picked)),
            "energy_4k_8k": round(band_energy(picked, 4000, 8000), 3),
        },
        "averaged": {
            **listen(blocks_of(averaged)),
            "energy_4k_8k": round(band_energy(averaged, 4000, 8000), 3),
        },
    }

    # A tone only aliasing can move: 10 kHz at 48 kHz folds to 6 kHz when picked.
    tone = np.sin(2 * math.pi * 10_000 * np.arange(48_000) / 48_000).astype(np.float32)
    report["aliasing_probe"] = {
        "tone_hz": 10_000,
        "folds_to_hz": 6_000,
        "picked_energy_at_6k": round(band_energy(decimate_by_picking(tone, 3.0), 5800, 6200), 3),
        "averaged_energy_at_6k": round(band_energy(decimate_by_average(tone, 3.0), 5800, 6200), 3),
    }

    (HERE / "pipeline-probe.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
