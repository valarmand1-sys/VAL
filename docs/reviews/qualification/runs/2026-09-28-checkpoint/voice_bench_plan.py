"""The Voice bench set — remaining latency work, 28 September 2026.

S1–S5 as on 27 September, unchanged (sessions 0–4). Added for §5, barge-in after
synthesis has finished (sessions 5–7): a long answer, then his words spoken while it is
still playing — `after_synthesis` (1.5 s after the service has offered all of her audio)
for a replacement and for a plain stop; B2 the same with the desktop's playback reports
delayed 1.5 s (a report arriving after the cut); B3 the in-flight control, spoken 3 s
after her first audio, while she is still being synthesised.

(The 27 September docstring follows.)

The Voice bench set for the live cache experiment — remaining latency work, 27 September 2026.

Sessions S1–S3 are the earlier compact set, unchanged. Two are added from the same
phrases rather than a new suite: S4 alternates social (LOW) and ordinary (MEDIUM) turns
fourteen times, past the engine's known eviction cycle; S5 resumes a request at several
points of the merge window (a pause of 0.8, 1.2 and 1.6 s of silence — the last near the
window's end — and 2.3 s, past it), for a continuation, a correction and a greeting
followed by a request.

(The earlier docstring follows.)

The compact representative Voice set, rendered to speech — owner order of 27 September 2026, §6.

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
    ("S4-sustained-alternation", [
        ("greeting", "social", "Good evening.", "after_playback", 1.0),
        ("factual", "ordinary", "What is the capital of Portugal?", "after_playback", 1.0),
        ("thanks after an answer", "social", "Thank you.", "after_playback", 1.0),
        ("factual", "ordinary", "What is a caesura?", "after_playback", 1.0),
        ("thanks after an answer", "social", "Thanks.", "after_playback", 1.0),
        ("conversational", "ordinary", "How long should a first chapter be?", "after_playback", 1.0),
        ("thanks after an answer", "social", "Thank you.", "after_playback", 1.0),
        ("ordinary", "ordinary", "Name two ways to end a chapter.", "after_playback", 1.0),
        ("thanks after an answer", "social", "Thanks.", "after_playback", 1.0),
        ("follow-up, quick", "ordinary", "Which of those is better at night?", "after_playback", 0.3),
        ("thanks after an answer, into maintenance", "social", "Thank you.", "after_playback", 1.8),
        ("substantive", "ordinary", "Explain the difference between suspense and surprise in a scene.", "after_playback", 1.0),
        ("thanks after an answer", "social", "Thanks.", "after_playback", 1.0),
        ("farewell after an answer", "social", "Good night.", "after_playback", 1.0),
    ]),
    ("S5-merge-window", [
        ("continuation, pause 0.8 s", "ordinary", "Tell me about a good opening line. || And why it works.", "after_playback", 1.0, 0.8),
        ("correction, pause 1.2 s", "ordinary", "Name a famous mystery novel. || No, a famous ghost story.", "after_playback", 1.0, 1.2),
        ("greeting then request, pause 1.2 s", "ordinary", "Good evening. || What is a sonnet?", "after_playback", 1.0, 1.2),
        ("continuation, pause 1.6 s (window end)", "ordinary", "Tell me about a good closing line. || And why it works.", "after_playback", 1.0, 1.6),
        ("correction, pause 1.6 s (window end)", "ordinary", "Name a famous ghost story. || No, a famous mystery novel.", "after_playback", 1.0, 1.6),
        ("greeting then request, pause 1.6 s (window end)", "ordinary", "Hello. || What is a haiku?", "after_playback", 1.0, 1.6),
        ("correction, pause 2.3 s (past the window)", "ordinary", "Name a famous poem. || No, a famous play.", "after_playback", 1.0, 2.3),
        ("thanks after an answer", "social", "Thank you.", "after_playback", 1.0),
    ]),
    *[
        (name, [
            ("long answer", "ordinary", "Tell me a story about a lighthouse keeper, in eight sentences.", "after_playback", 1.0),
            ("barge-in, replacement", "ordinary", "Wait. Tell me about the sea instead.", when, gap),
            ("long answer", "ordinary", "Describe a walk through an old library, in eight sentences.", "after_playback", 1.0),
            ("barge-in, stop", "ordinary", "Stop there.", when, gap),
            ("thanks after an answer", "social", "Thank you.", "after_playback", 1.0),
        ], options)
        for name, when, gap, options in (
            ("B1-barge-after-synthesis", "after_synthesis", 1.5, {}),
            ("B2-barge-after-synthesis-delayed-reports", "after_synthesis", 1.5, {"delay_reports_ms": 1500}),
            ("B3-barge-in-flight-control", "during_playback", 3.0, {}),
        )
    ],
    # Session 8: the resume case that stalled in C1a, eight times over.
    ("R-resume-repeated", [
        (f"continuation, pause 0.8 s ({topic})", "ordinary", f"Tell me about {topic}. || And why it works.",
         "after_playback", 1.0, 0.8)
        for topic in ("a good opening line", "a good closing line", "a strong title", "a quiet scene",
                      "a memorable villain", "a short chapter", "a plain sentence", "a sudden ending")
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
