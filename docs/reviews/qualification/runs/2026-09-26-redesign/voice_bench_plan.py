"""The compact representative Voice set, rendered to speech — owner order of 27 September 2026, §6.

Three sessions, each a short conversation, spoken by the macOS voice the earlier harness
used (so the recognizer's known mishearings are the same in every condition). A phrase
written `A || B` is one utterance with a natural pause inside it (`PAUSE_S`); the pause is
real silence in the audio. Each turn says when it is spoken:

- `after_playback` (default): `gap_s` after her answer to the previous turn has finished
  playing — 1.0 s is an ordinary reply, 0.3 s an immediate one, and 1.8 s lands just after
  maintenance (which waits a full second of idleness) has begun;
- `after_speech`: `gap_s` after the previous turn's speech ended, whatever she is doing —
  the replacement case, spoken while the earlier answer is still being made.

Classes: `social` (greetings, thanks and farewells), `ordinary` (factual, conversational,
substantive, follow-up, and the pause/continuation/correction/replacement cases, which are
ordinary requests spoken with a pause or a change of mind).

Usage: voice_bench_plan.py OUT.json
"""

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
    ("S1-greeting-factual-substantive", [
        ("greeting", "social", "Good evening.", "after_playback", 1.0),
        ("factual", "ordinary", "What is the capital of Portugal?", "after_playback", 1.0),
        ("thanks after an answer", "social", "Thank you.", "after_playback", 1.0),
        ("substantive", "ordinary", "Explain the difference between suspense and surprise in a scene.", "after_playback", 1.0),
        ("follow-up", "ordinary", "Which of those works better in a short story?", "after_playback", 1.0),
        ("farewell after an answer", "social", "Good night.", "after_playback", 1.0),
    ]),
    ("S2-pauses-and-corrections", [
        ("greeting", "social", "Hello.", "after_playback", 1.0),
        ("conversational", "ordinary", "How long should a first chapter be?", "after_playback", 1.0),
        ("continuation after a pause", "ordinary", "Tell me about a good opening line, || and why it works.", "after_playback", 1.0),
        ("hesitation", "ordinary", "I was wondering, || um, || whether prologues are useful.", "after_playback", 1.0),
        ("correction after a pause", "ordinary", "Name a famous mystery novel. || No, a famous ghost story.", "after_playback", 1.0),
        ("thanks after an answer", "social", "Thanks.", "after_playback", 1.0),
    ]),
    ("S3-collisions-and-replacement", [
        ("ordinary", "ordinary", "Name two ways to end a chapter.", "after_playback", 1.0),
        ("follow-up, quick", "ordinary", "Which of those is better at night?", "after_playback", 0.3),
        ("factual, into maintenance", "ordinary", "What is a caesura?", "after_playback", 1.8),
        ("to be replaced", "ordinary", "Describe a haunted house in one sentence.", "after_playback", 1.0),
        ("explicit replacement", "ordinary", "Actually, never mind. Describe a lighthouse instead.", "after_speech", 2.0),
        ("thanks after an answer, into maintenance", "social", "Thank you.", "after_playback", 1.8),
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


def render(text: str) -> tuple[array.array, list[float]]:
    pcm = array.array("h")
    pauses: list[float] = []
    for index, part in enumerate(p.strip() for p in text.split("||")):
        if index:
            pcm.extend([0] * int(PAUSE_S * RATE))
            pauses.append(PAUSE_S)
        pcm.extend(spoken(part))
    return pcm, pauses


plan = {"rate": RATE, "voice": VOICE, "pause_s": PAUSE_S, "sessions": []}
for name, turns in SESSIONS:
    rendered = []
    for label, klass, text, when, gap in turns:
        pcm, pauses = render(text)
        rendered.append({
            "label": label, "class": klass, "text": text.replace(" || ", " "), "when": when,
            "gap_s": gap, "duration_s": round(len(pcm) / RATE, 3), "internal_pauses_s": pauses,
            "pcm16_b64": base64.b64encode(pcm.tobytes()).decode("ascii"),
        })
    plan["sessions"].append({"name": name, "turns": rendered})
Path(sys.argv[1]).write_text(json.dumps(plan) + "\n")
print(json.dumps([{"session": s["name"], "turns": [(t["label"], t["duration_s"]) for t in s["turns"]]} for s in plan["sessions"]]))
