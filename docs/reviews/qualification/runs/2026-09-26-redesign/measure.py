"""Candidate qualification runs — copied 26 September 2026 from the onset run for the
latency redesign. `VAL_FAST_ROUTE_TIERS` and `VAL_SCRATCH_*` pass through to the scratch
service; each answer is read back with the task type of the call that produced it.

Originally: Voice-mode repair §8, 25 September 2026.

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
SERVE = Path(os.environ["VAL_MEASURE_SERVE"]) if "VAL_MEASURE_SERVE" in os.environ else (
    checkout / "docs/reviews/qualification/runs/2026-09-25-priming/serve_scratch.py"
)
PHRASES = json.loads(os.environ["VAL_MEASURE_PHRASES"]) if "VAL_MEASURE_PHRASES" in os.environ else [
    "Good evening, Val.",
    "I'm testing your voice right now. How do I sound to you?",
    "Tell me, in a few sentences, what you would like us to work on this week.",
]
#: Qualification (owner order §10, 26 September 2026): `VAL_MEASURE_PLAN` names the
#: qualification phrase file; each session then speaks one row of its `sessions.plan`
#: (group:index references, expanded here), and SESSIONS counts rows, not repeats.
PLAN: list[list[str]] | None = None
GROUP_OF: dict[str, str] = {}
if "VAL_MEASURE_PLAN" in os.environ:
    _q = json.loads(Path(os.environ["VAL_MEASURE_PLAN"]).read_text())
    PLAN = []
    for _row in _q["sessions"]["plan"]:
        _phrases = []
        for _ref in _row:
            _group, _index = _ref.split(":")
            _phrase = _q[_group][int(_index)]
            GROUP_OF[_phrase] = _group
            _phrases.append(_phrase)
        PLAN.append(_phrases)
    if "VAL_MEASURE_PLAN_ROWS" in os.environ:
        _first, _last = (int(x) for x in os.environ["VAL_MEASURE_PLAN_ROWS"].split(":"))
        PLAN = PLAN[_first:_last]
    sessions = len(PLAN)
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
        phrases = PLAN[index - 1] if PLAN is not None else PHRASES
        driven = subprocess.run(
            ["uv", "run", "python", str(HERE / "drive_session.py"), f"{condition} session {index}",
             str(target), str(PAUSE_S), *phrases],
            cwd=HERE.parents[4], env=env, capture_output=True, text=True,
        )
        if driven.returncode != 0 or not target.exists():
            runs.append({"label": f"{condition} session {index}", "failed": True,
                         "phrases": phrases, "stderr": driven.stderr[-2000:]})
            print(f"session {index} failed: {driven.stderr[-400:]}", file=sys.stderr)
            continue
        run = json.loads(target.read_text())
        for turn in run["turns"]:
            turn["group"] = GROUP_OF.get(turn["phrase"])
        runs.append(run)
        target.unlink()
        time.sleep(3)  # the session's release and the last refresh settle
finally:
    sampling.set()
    server.send_signal(signal.SIGINT)
    server.wait(timeout=30)

# The scratch conversation's text (synthetic; never the owner's store), for reading
# what she said — the self-knowledge check reads her answers, not only their timing.
def scratch_rows(sql: str) -> list:
    """One JSON document from the scratch store (synthetic content; never the owner's)."""
    out = subprocess.run(
        ["psql", "-h", "localhost", "-p", "5433", "-d", "val_test", "-At", "-c",
         f"select coalesce(json_agg(r), '[]'::json) from ({sql}) r"],
        capture_output=True, text=True,
    ).stdout
    return json.loads(out) if out.strip() else []


# Every message with the route of the call that produced it (a val message's calls
# are attached to the user message before it), so the transcript the router saw and
# the route it chose are read back together.
dialogue = scratch_rows(
    "select m.id, m.conversation_id, m.sequence, m.role::text, m.content, m.created_at, "
    "  (select string_agg(distinct c.task_type::text || '@' || c.model_config_id::text, ',') "
    "     from model_calls c where c.message_id = (select u.id from messages u where "
    "     u.conversation_id = m.conversation_id and u.sequence = m.sequence - 1)) as route, "
    "  (select string_agg(distinct c.task_type::text || '@' || c.model_config_id::text, ',') "
    "     from model_calls c where c.message_id = m.id) as own_calls "
    "from messages m order by m.created_at"
)
preparations = scratch_rows(
    "select p.*, c.status::text as call_status, c.tokens_in, c.tokens_out "
    "from speculative_preparations p left join model_calls c on c.id = p.model_call_id "
    "order by p.created_at"
)
calls = scratch_rows(
    "select id, task_type::text, model_config_id, conversation_id, message_id, status::text, "
    "  tokens_in, tokens_out, cost, latency_ms, created_at, terminal_state::text from model_calls order by id"
)
lines = log_path.read_text().splitlines()
timelines = [json.loads(line.split("voice turn timeline: ", 1)[1])
             for line in lines if "voice turn timeline: " in line]
primes = [json.loads(line.split("voice prime: ", 1)[1]) | {"wall": float(line.split()[0])}
          for line in lines if "voice prime: " in line]
warms = [line for line in lines if "voice warm" in line or "warmed" in line][:20]


def logged(prefix: str) -> list[dict]:
    """Every `prefix` log line as its JSON document, with the wall clock it was written at."""
    found = []
    for line in lines:
        if prefix in line:
            payload = line.split(prefix, 1)[1].strip()
            try:
                found.append({"wall": float(line.split()[0]), **json.loads(payload)})
            except (ValueError, TypeError):
                found.append({"wall": float(line.split()[0]), "text": payload})
    return found


routes = logged("fast route: ")
completions = logged("turn completion: ")
speculation_lines = [
    {"wall": float(line.split()[0]), "text": line.split("speculation: ", 1)[1].strip()}
    for line in lines if "speculation: " in line
]


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
        "first_segment_to_first_audio_ms": gap(marks, "speech_segment_queued", "audio_at_sink"),
        "first_visible_to_first_audio_ms": gap(marks, "speech_first_visible_text", "audio_at_sink"),
        "request_ready_to_first_audio_ms": gap(marks, "owner_turn_submitted", "audio_at_sink"),
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
    "serve": str(SERVE),
    "first_pause": os.environ.get("VAL_SCRATCH_FIRST_PAUSE", "on"),
    "dialogue": dialogue,
    "preparations": preparations,
    "calls": calls,
    "routes": routes,
    "completions": completions,
    "speculation_log": speculation_lines,
    "fast_route_tiers": os.environ.get("VAL_FAST_ROUTE_TIERS", ""),
    "speculation": os.environ.get("VAL_SPECULATION", ""),
    "adaptive_grace": os.environ.get("VAL_ADAPTIVE_GRACE", ""),
    "plan": os.environ.get("VAL_MEASURE_PLAN", ""),
}
out.write_text(json.dumps(report, indent=1) + "\n")
for run in runs:
    for turn in run.get("turns", []):
        print(json.dumps(turn["speech_end_to"]))
print(json.dumps(report["machine"]))
