"""The three-condition qualification matrix — priming-cache pass §10, §15, §20, §21.

Runs the real VAL service (`serve_scratch.py`, scratch store, port 8766) against the
isolated `val-exp` instance, and drives it with `drive_turn.py` exactly as the desktop
does. One condition per invocation; the instance's serving mode is set by the caller
(`lms load … --parallel N`), and this script only switches VAL's priming on or off.

Usage: matrix.py CONDITION PRIMING(on|off) LEAD_SECONDS OUT.json
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PHRASES = [
    "Good evening, Val.",
    "What should we look at this morning?",
    "Is the house quiet tonight?",
    "Remind me what we decided yesterday.",
]
condition, priming, lead, out = sys.argv[1], sys.argv[2], float(sys.argv[3]), Path(sys.argv[4])
log_path = HERE / f"service-{condition}.log"


def healthy() -> bool:
    try:
        return urllib.request.urlopen("http://127.0.0.1:8766/health", timeout=1).status == 200
    except OSError:
        return False


env = {**os.environ, "VAL_SCRATCH_PRIMING": priming, "DRIVE_LEAD_S": str(lead)}
with log_path.open("w") as log:
    server = subprocess.Popen(["uv", "run", "python", str(HERE / "serve_scratch.py")],
                              cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env)
try:
    deadline = time.monotonic() + 120
    while not healthy():
        assert time.monotonic() < deadline, "the scratch service did not start"
        time.sleep(0.5)
    trials = []
    for index, phrase in enumerate(PHRASES, start=1):
        target = HERE / f"trial-{condition}-{index}.json"
        subprocess.run(["uv", "run", "python", str(HERE / "drive_turn.py"),
                        f"{condition} turn {index}", str(target), phrase],
                       cwd=ROOT, env=env, check=True, capture_output=True)
        trials.append(json.loads(target.read_text()))
        target.unlink()
        time.sleep(2)  # let the refresh and playback reports settle
finally:
    server.send_signal(signal.SIGINT)
    server.wait(timeout=30)

lines = log_path.read_text().splitlines()
timelines = [json.loads(line.split("voice turn timeline: ", 1)[1])
             for line in lines if "voice turn timeline: " in line]
primes = [json.loads(line.split("voice prime: ", 1)[1]) | {"wall": float(line.split()[0])}
          for line in lines if "voice prime: " in line]
rows = []
for trial, timeline in zip(trials, timelines):
    marks = timeline["marks"]
    first = lambda name: marks[name]["first_ms"] if name in marks else None  # noqa: E731
    anchor = datetime.fromisoformat(timeline["anchor_wall"]).timestamp()
    since_end = (anchor - trial["speech_end_wall"]) * 1000

    def gap(a: str, b: str) -> float | None:
        return None if first(a) is None or first(b) is None else round(first(b) - first(a), 1)

    rows.append({
        "turn": trial["label"],
        "request_ready_to_first_user_facing_text_ms": gap("owner_turn_submitted", "speech_first_visible_text"),
        "dispatch_to_first_provider_output_ms": gap("provider_dispatch", "provider_chunk"),
        "first_output_to_user_facing_text_ms": gap("provider_chunk", "provider_visible_text"),
        "cognition_dispatch_to_answer_text_complete_ms": gap("provider_dispatch", "provider_visible_text"),
        "readiness_ms": gap("runtime_ready_start", "runtime_ready_end"),
        "first_tts_ms": gap("tts_synthesize_start", "tts_synthesize_return"),
        "speech_end_to_owner_message_read_ms": trial["owner_facing"]["A_speech_end_to_owner_message_read_returned"],
        "owner_message_to_playback_ms": trial["owner_facing"]["B_owner_message_read_returned_to_playback_start"],
        "speech_end_to_playback_ms": trial["owner_facing"]["C_speech_end_to_playback_start"],
        "endpoint_from_speech_end_ms": round(since_end, 1),
        "request_ready_wall": anchor + first("owner_turn_submitted") / 1000,
    })
report = {"condition": condition, "priming": priming, "lead_s": lead, "rows": rows,
          "primes": primes}
out.write_text(json.dumps(report, indent=1) + "\n")
for row in rows:
    print(json.dumps({k: v for k, v in row.items() if k != "request_ready_wall"}))
for prime in primes:
    print("prime:", json.dumps(prime)[:300])
