"""Before and after, on one path — Voice-mode repair §8, 25 September 2026.

Starts the real VAL service on the scratch store and port 8766 from a given checkout
(`serve_scratch.py` of the priming pass, unchanged), addressing the **production**
model instance (`openai/gpt-oss-20b`, loaded by the service's own readiness code at
parallel 1, as deployed), and drives it with `drive_session.py`: whole Voice sessions,
several turns each, the first soon after Voice On. Nothing touches the owner's store.

While it runs it samples the machine once a second — free memory as `memory_pressure`
reports it, swap in use, and the resident size of every speech runtime process — so
the resident speech worker's cost is measured rather than assumed (§5).

Every call a spoken turn makes is local (the conversation is sealed): $0.

Usage: measure.py CONDITION CHECKOUT SESSIONS OUT.json
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
condition, checkout, sessions, out = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3]), Path(sys.argv[4])
SERVE = checkout / "docs/reviews/qualification/runs/2026-09-25-priming/serve_scratch.py"
PHRASES = [
    "Good evening, Val.",
    "I'm testing your voice right now. How do I sound to you?",
    "Tell me, in a few sentences, what you would like us to work on this week.",
]
PAUSE_S = 2.0
log_path = HERE / f"service-{condition}.log"


def healthy() -> bool:
    try:
        return urllib.request.urlopen("http://127.0.0.1:8766/health", timeout=1).status == 200
    except OSError:
        return False


samples: list[dict[str, object]] = []
sampling = threading.Event()


def sample_machine() -> None:
    while not sampling.is_set():
        at = time.time()
        pressure = subprocess.run(["memory_pressure", "-Q"], capture_output=True, text=True).stdout
        free = re.search(r"free percentage:\s*(\d+)%", pressure)
        swap = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True).stdout
        used = re.search(r"used = ([\d.]+)M", swap)
        ps = subprocess.run(["ps", "-axo", "pid=,rss=,command="], capture_output=True, text=True).stdout
        speech = [
            {"pid": int(line.split()[0]), "rss_mb": round(int(line.split()[1]) / 1024, 1),
             "serve": line.rstrip().endswith(" serve")}
            for line in ps.splitlines()
            if "qwen_tts_speak.py" in line
        ]
        samples.append({
            "wall": round(at, 3),
            "free_percent": int(free.group(1)) if free else None,
            "swap_used_mb": float(used.group(1)) if used else None,
            "speech_processes": speech,
        })
        time.sleep(1.0)


env = {**os.environ, "VAL_SCRATCH_MODEL_IDENTIFIER": "openai/gpt-oss-20b", "DRIVE_LEAD_S": "1.0"}
with log_path.open("w") as log:
    server = subprocess.Popen(
        ["uv", "run", "--project", str(checkout), "python", str(SERVE)],
        cwd=checkout, stdout=log, stderr=subprocess.STDOUT, env=env,
    )
sampler = threading.Thread(target=sample_machine, daemon=True)
runs = []
try:
    deadline = time.monotonic() + 180
    while not healthy():
        assert time.monotonic() < deadline, "the scratch service did not start"
        assert server.poll() is None, "the scratch service exited"
        time.sleep(0.5)
    sampler.start()
    for index in range(1, sessions + 1):
        target = HERE / f"session-{condition}-{index}.json"
        subprocess.run(
            ["uv", "run", "python", str(HERE / "drive_session.py"), f"{condition} session {index}",
             str(target), str(PAUSE_S), *PHRASES],
            cwd=HERE.parents[4], env=env, check=True, capture_output=True,
        )
        runs.append(json.loads(target.read_text()))
        target.unlink()
        time.sleep(3)  # the session's release and the last refresh settle
finally:
    sampling.set()
    server.send_signal(signal.SIGINT)
    server.wait(timeout=30)

lines = log_path.read_text().splitlines()
timelines = [json.loads(line.split("voice turn timeline: ", 1)[1])
             for line in lines if "voice turn timeline: " in line]
primes = [json.loads(line.split("voice prime: ", 1)[1]) | {"wall": float(line.split()[0])}
          for line in lines if "voice prime: " in line]
warms = [line for line in lines if "voice warm" in line or "warmed" in line][:20]


def gap(marks: dict, a: str, b: str) -> float | None:
    if a not in marks or b not in marks:
        return None
    return round(marks[b]["first_ms"] - marks[a]["first_ms"], 1)


components = []
for timeline in timelines:
    marks = timeline["marks"]
    components.append({
        "anchor_wall": timeline["anchor_wall"],
        "request_ready_to_first_output_ms": gap(marks, "owner_turn_submitted", "provider_chunk"),
        "first_output_to_visible_text_ms": gap(marks, "provider_chunk", "provider_visible_text"),
        "request_ready_to_first_speech_text_ms": gap(marks, "owner_turn_submitted", "speech_first_visible_text"),
        "first_tts_ms": gap(marks, "tts_synthesize_start", "tts_synthesize_return"),
        "cognition_complete_ms": gap(marks, "owner_turn_submitted", "message_persisted"),
        "marks": sorted(marks),
    })
report = {
    "condition": condition,
    "checkout": str(checkout),
    "revision": subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"],
                               capture_output=True, text=True).stdout.strip(),
    "dirty": bool(subprocess.run(["git", "-C", str(checkout), "status", "--porcelain",
                                  "--untracked-files=no"], capture_output=True, text=True).stdout.strip()),
    "sessions": runs,
    "service_components": components,
    "primes": primes,
    "machine": {
        "samples": len(samples),
        "min_free_percent": min((s["free_percent"] for s in samples if s["free_percent"] is not None), default=None),
        "swap_used_mb_first": samples[0]["swap_used_mb"] if samples else None,
        "swap_used_mb_last": samples[-1]["swap_used_mb"] if samples else None,
        "max_resident_speech_rss_mb": max(
            (p["rss_mb"] for s in samples for p in s["speech_processes"] if p["serve"]), default=None),
        "max_one_shot_speech_rss_mb": max(
            (p["rss_mb"] for s in samples for p in s["speech_processes"] if not p["serve"]), default=None),
        "resident_alive_after_close": bool(samples and any(p["serve"] for p in samples[-1]["speech_processes"])),
    },
    "measured_at": datetime.now().isoformat(timespec="seconds"),
}
out.write_text(json.dumps(report, indent=1) + "\n")
for run in runs:
    for turn in run["turns"]:
        print(json.dumps(turn["speech_end_to"]))
print(json.dumps(report["machine"]))
