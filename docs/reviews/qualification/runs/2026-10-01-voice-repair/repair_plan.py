"""The repair bench plan — owner order of 1 October 2026, §7. Rendering as voice_bench_plan.py."""

from __future__ import annotations

import array
import base64
import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

RATE = 16_000
NOISE = 33
PAUSE_S = 0.8
VOICE = "Daniel"

SESSIONS = [
    # The physical failure of 30 September 2026, reproduced: an older answer playing while
    # a newer one exists; his voice over it, twice; a clear stop; then an ordinary request.
    ("O1-overlapping-answers", [
        ("long answer A", "ordinary", "Tell me a story about a lighthouse keeper, in eight sentences.", "after_playback", 1.0),
        ("second request before A is heard", "ordinary", "What is a good name for a sheepdog?", "after_speech", 1.7),
        ("his own words, over A while B waits", "ordinary", "No, Donald. No, no, no, no, no.", "during_playback", 4.0),
        ("again", "ordinary", "No.", "after_speech", 1.5),
        ("a clear stop", "ordinary", "Stop.", "after_speech", 2.5),
        ("ordinary request after the stops", "ordinary", "What is the capital of Australia?", "after_speech", 3.0),
        ("long answer C", "ordinary", "Describe a walk through an old library, in eight sentences.", "after_playback", 1.0),
        ("replacement at the playback-start boundary", "ordinary", "Wait. Tell me about the sea instead.", "during_playback", 0.0),
        ("request", "ordinary", "Name a famous ghost story.", "after_playback", 1.0),
        ("continuation while being made", "ordinary", "And who wrote it?", "after_speech", 1.6),
        ("thanks", "social", "Thank you.", "after_playback", 1.0),
    ]),
    # His conversational checks, spoken: the opening-line question, an explanation, a
    # detailed request, and a numeral.
    ("O2-conversation", [
        ("example", "ordinary", "What is a good opening line for a film?", "after_playback", 1.0),
        ("explanation", "ordinary", "What makes a good opening line for a film?", "after_playback", 1.0),
        ("detail", "ordinary", "Walk me through, in detail, how the first ten minutes of a film should establish its protagonist.", "after_playback", 1.0),
        ("stop the detailed answer", "ordinary", "Stop.", "during_playback", 6.0),
        ("numeral", "ordinary", "Repeat after me. We begin at Chapter Four, with Donald the Second.", "after_speech", 3.0),
        ("fact", "ordinary", "What is the capital of Australia?", "after_playback", 1.0),
    ]),
]


def spoken(phrase: str) -> array.array:
    with tempfile.TemporaryDirectory() as scratch:
        target = Path(scratch) / "speech.wav"
        subprocess.run(
            ["say", "-v", VOICE, "-o", str(target), f"--data-format=LEI16@{RATE}", phrase],
            check=True,
        )
        with wave.open(str(target)) as handle:
            speech = array.array("h", handle.readframes(handle.getnframes()))
    loud = [i for i, sample in enumerate(speech) if abs(sample) > NOISE]
    return speech[loud[0] : loud[-1] + 1]


def render(text: str, pause_s: float = PAUSE_S) -> tuple[array.array, list[float]]:
    pcm = array.array("h")
    pauses: list[float] = []
    for index, part in enumerate(p.strip() for p in text.split("||")):
        if index:
            pcm.extend([0] * int(pause_s * RATE))
            pauses.append(pause_s)
        pcm.extend(spoken(part))
    return pcm, pauses


plan = {"rate": RATE, "voice": VOICE, "pause_s": PAUSE_S, "sessions": []}
for name, turns, *extra in SESSIONS:
    rendered = []
    for label, klass, text, when, gap, *pause in turns:
        pcm, pauses = render(text, pause[0] if pause else PAUSE_S)
        rendered.append({
            "label": label, "class": klass, "text": text.replace(" || ", " "), "when": when,
            "gap_s": gap, "duration_s": round(len(pcm) / RATE, 3), "internal_pauses_s": pauses,
            "pcm16_b64": base64.b64encode(pcm.tobytes()).decode("ascii"),
        })
    plan["sessions"].append({"name": name, "turns": rendered, **(extra[0] if extra else {})})
Path(sys.argv[1]).write_text(json.dumps(plan) + "\n")
print(json.dumps([{"session": s["name"], "turns": [(t["label"], t["duration_s"]) for t in s["turns"]]} for s in plan["sessions"]]))
