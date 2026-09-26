"""Cross-effort cache interference, measured by the runtime's own prediction stats — §4.

`lms log stream --source model --json` reports, for every prediction, the rendered
input (with its `Reasoning:` line), `promptTokensCount`, `timeToFirstTokenSec` and the
output. Time to first token on a 5.7k-token prompt is the prefill, so it says directly
whether the prompt's prefix was found in the runtime's cache. The stream is captured
for the whole run and each prediction is attributed to the step that made it.

Sequences (each repeated), all through the real Core on the scratch store, every call
LOCAL and $0, the light route promoted to LOW for this process only:

  P  prime (the production pattern: the Partner route and the light route, in that order)
  M  ordinary MEDIUM over a fresh conversation (persona + envelope + one message)
  L  the Tier-1 request at LOW over a fresh conversation
  Mg ordinary MEDIUM answering the same greeting (the control for L)

  S1  P M          warm MEDIUM baseline
  S2  P L M        does a LOW call disturb MEDIUM's checkpoint?
  S3  P Mg M       the same, with MEDIUM in L's place
  S4  P L P M      the production pattern: re-primed after the Tier-1 turn
  S5  P L L        a second LOW behind a first: LOW's own reuse
  S6  M L          LOW after MEDIUM with no prime at all (cold?)

Usage: low_boundary2.py OUT.json [repeats]
"""

from __future__ import annotations

import json
import os
import plistlib
import statistics
import subprocess
import sys
import time
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    for name, value in plistlib.load(handle)["EnvironmentVariables"].items():
        if name != "VAL_DATABASE_URL":
            os.environ[name] = value
URL = "postgresql+psycopg://localhost:5433/val_repro_test"
os.environ["VAL_DATABASE_URL"] = URL
os.environ["VAL_FAST_ROUTE_TIERS"] = "1"
os.environ["VAL_TIER1_ROUTE"] = "low"
for key in ("VAL_SPECULATION", "VAL_ADAPTIVE_GRACE"):
    os.environ.pop(key, None)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from val_gateway.deliberate import send  # noqa: E402
from val_gateway.persona import seed  # noqa: E402
from val_gateway.projects import load_catalogue  # noqa: E402
from val_gateway.seal import SealRoute  # noqa: E402
from val_gateway.startup import start  # noqa: E402
from val_policy.light_conversation import FastRoute  # noqa: E402
from val_policy.project_resolution import ProjectSignals  # noqa: E402

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(sys.argv[1])
REPEATS = int(sys.argv[2]) if len(sys.argv) > 2 else 3
GREETING = "Good evening, Val."
SUBSTANTIVE = "Explain three ways to make a film scene feel tense without using dialogue."


def fresh_store() -> None:
    engine = create_engine(URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "packages/domain/migrations"))
    config.set_main_option("sqlalchemy.url", URL)
    command.upgrade(config, "head")


fresh_store()
engine = create_engine(URL)
seed(engine, ROOT)
started = start(engine)
gateway = started.gateway
catalogue = load_catalogue(engine)
NO_PROJECT = ProjectSignals(explicit_no_project=True)
LIGHT = FastRoute(frozenset({1}))
NONE = FastRoute()

stream = subprocess.Popen(
    ["lms", "log", "stream", "--source", "model", "--json"],
    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
)
# Read the stream as it comes: a 27 KB rendered input per prediction fills a pipe in
# two entries, and a blocked writer drops what follows (the first run captured 2 of ~60).
import threading  # noqa: E402

captured: list[str] = []


def _drain() -> None:
    assert stream.stdout is not None
    for line in stream.stdout:
        captured.append(line)


threading.Thread(target=_drain, daemon=True).start()
time.sleep(1.5)
steps: list[dict] = []


def step(label: str, sequence: str, repeat: int, fn) -> None:  # noqa: ANN001
    started_at = time.time()
    result = fn()
    steps.append({"label": label, "sequence": sequence, "repeat": repeat,
                  "start": started_at, "end": time.time(), "result": result})
    time.sleep(0.4)


def P() -> dict:  # noqa: N802
    r = dict(gateway.prime_prefix())
    return {"medium": r.get("outcome"), "low": (r.get("light") or {}).get("outcome")}


def turn(words: str, fast: FastRoute) -> dict:
    outcome = send(engine, gateway, words, catalogue=catalogue, signals=NO_PROJECT,
                   spoken=True, seal_route=SealRoute.UTTERANCE_FINALIZED, fast_route=fast)
    with engine.connect() as connection:
        row = connection.execute(
            text("select task_type::text, latency_ms, tokens_out from model_calls where message_id = :m order by id desc limit 1"),
            {"m": outcome.turn.user_message.id},  # type: ignore[attr-defined]
        ).first()
    return {"task": row[0], "latency_ms": row[1], "tokens_out": row[2], "answer": outcome.turn.val_message.content[:80]}  # type: ignore[attr-defined]


SEQUENCES = {
    "S1 P M": [("P", P), ("M", lambda: turn(SUBSTANTIVE, NONE))],
    "S2 P L M": [("P", P), ("L", lambda: turn(GREETING, LIGHT)), ("M", lambda: turn(SUBSTANTIVE, NONE))],
    "S3 P Mg M": [("P", P), ("Mg", lambda: turn(GREETING, NONE)), ("M", lambda: turn(SUBSTANTIVE, NONE))],
    "S4 P L P M": [("P", P), ("L", lambda: turn(GREETING, LIGHT)), ("P", P), ("M", lambda: turn(SUBSTANTIVE, NONE))],
    "S5 P L L": [("P", P), ("L", lambda: turn(GREETING, LIGHT)), ("L", lambda: turn(GREETING, LIGHT))],
    "S6 M L": [("M", lambda: turn(SUBSTANTIVE, NONE)), ("L", lambda: turn(GREETING, LIGHT))],
}
for repeat in range(REPEATS):
    for name, plan in SEQUENCES.items():
        for label, fn in plan:
            step(label, name, repeat, fn)
        print(name, repeat, "done", file=sys.stderr)
time.sleep(2.0)
stream.terminate()
try:
    stream.wait(timeout=15)
except subprocess.TimeoutExpired:
    stream.kill()
time.sleep(0.5)
predictions = []
pending_input = None
for line in captured:
    try:
        entry = json.loads(line)
    except ValueError:
        continue
    data = entry.get("data", {})
    if data.get("type") == "llm.prediction.input":
        text_in = data.get("input", "")
        marker = "low" if "Reasoning: low" in text_in else "medium" if "Reasoning: medium" in text_in else "?"
        pending_input = {"reasoning": marker, "chars": len(text_in), "timestamp": entry.get("timestamp")}
    elif data.get("type") == "llm.prediction.output":
        stats = data.get("stats", {})
        predictions.append({
            "timestamp": entry.get("timestamp"), "model": data.get("modelIdentifier"),
            "reasoning": (pending_input or {}).get("reasoning"),
            "prompt_tokens": stats.get("promptTokensCount"),
            "ttft_s": stats.get("timeToFirstTokenSec"),
            "predicted_tokens": stats.get("predictedTokensCount"),
            "stop": stats.get("stopReason"),
        })
        pending_input = None
# Attribute each prediction to the step whose window it fell in (timestamps are ms).
for prediction in predictions:
    t = (prediction["timestamp"] or 0) / 1000.0
    match = next((s for s in steps if s["start"] - 0.5 <= t <= s["end"] + 0.5), None)
    prediction["step"] = None if match is None else f"{match['sequence']} #{match['repeat']} {match['label']}"


def q(values: list[float]) -> dict:
    values = sorted(v for v in values if v is not None)
    return {"n": len(values), "median": round(statistics.median(values), 3), "min": values[0], "max": values[-1]} if values else {"n": 0}


summary: dict[str, dict] = {}
for name in SEQUENCES:
    for label in ("M", "L", "Mg"):
        # the *last* step with that label in the sequence is the one under test
        mine = [p for p in predictions if p["step"] and p["step"].startswith(name) and p["step"].endswith(" " + label) and p["prompt_tokens"] and p["prompt_tokens"] > 1000]
        if mine:
            summary[f"{name} → {label}"] = {"ttft_s": q([p["ttft_s"] for p in mine]), "prompt_tokens": q([p["prompt_tokens"] for p in mine]), "reasoning": sorted({p["reasoning"] for p in mine})}
report = {"repeats": REPEATS, "summary": summary, "steps": steps, "predictions": predictions}
OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str) + "\n")
print(json.dumps(summary, indent=1))
