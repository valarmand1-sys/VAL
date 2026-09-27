"""Compose the fake microphone's input for the desktop-integration run — 26 September 2026.

Release-gaps order §6: the changed readiness and routing flow is exercised through the
real desktop frontend, driven headlessly in a Chromium browser whose microphone is this
file (`--use-file-for-fake-audio-capture`). The file is fixed before the run, so the
gaps between the owner's phrases are planned, generously, from the harness's measured
turn times; a phrase that landed while she was still speaking would be a barge-in, which
this run does not set out to measure. 16 kHz mono int16, the desktop's capture rate; the
driver's voice is the same macOS voice the qualification harness spoke with.

Usage: desktop_owner_audio.py OUT.wav LEAD_S PHRASE GAP_S PHRASE GAP_S ... PHRASE TAIL_S
"""

from __future__ import annotations

import array
import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

RATE = 16_000
NOISE = 33


def spoken(phrase: str) -> array.array:
    with tempfile.TemporaryDirectory() as scratch:
        target = Path(scratch) / "speech.wav"
        subprocess.run(
            ["say", "-v", "Daniel", "-o", str(target), f"--data-format=LEI16@{RATE}", phrase],
            check=True,
        )
        with wave.open(str(target)) as handle:
            speech = array.array("h", handle.readframes(handle.getnframes()))
    loud = [i for i, sample in enumerate(speech) if abs(sample) > NOISE]
    return speech[loud[0] : loud[-1] + 1]


def main() -> None:
    out = Path(sys.argv[1])
    items = sys.argv[2:]
    samples = array.array("h")
    plan: list[dict[str, object]] = []
    cursor = 0.0
    for index, item in enumerate(items):
        if index % 2 == 0:  # a silence, in seconds
            seconds = float(item)
            samples.extend([0] * int(seconds * RATE))
            cursor += seconds
        else:
            speech = spoken(item)
            plan.append(
                {
                    "phrase": item,
                    "speech_start_s": round(cursor, 3),
                    "speech_end_s": round(cursor + len(speech) / RATE, 3),
                }
            )
            samples.extend(speech)
            cursor += len(speech) / RATE
    with wave.open(str(out), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(samples.tobytes())
    out.with_suffix(".plan.json").write_text(
        json.dumps({"total_s": round(cursor, 3), "phrases": plan}, indent=1) + "\n"
    )
    print(json.dumps({"total_s": round(cursor, 3), "phrases": plan}))


if __name__ == "__main__":
    main()
