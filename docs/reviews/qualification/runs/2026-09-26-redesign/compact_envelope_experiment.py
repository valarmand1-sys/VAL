"""Milestone B §9: the same envelope in fewer words — 26 September 2026.

Matched contexts on the ordinary MEDIUM route, two processes: the envelope as it is,
and with `context.COMPACT_NOTES` (same fields, states and governing instructions;
shorter prose). Measured from the runtime's own log: prompt tokens and time to first
token per turn; and every answer printed for reading — substantive tasks, a
correction, a pending decision, the fabricated-completion context, a capability
question. Local, $0. Usage: compact_envelope_experiment.py as_is|compact OUT.json
"""

from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
import threading
import time
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    for name, value in plistlib.load(handle)["EnvironmentVariables"].items():
        if name != "VAL_DATABASE_URL":
            os.environ[name] = value
URL = "postgresql+psycopg://localhost:5433/val_repro_test"
os.environ["VAL_DATABASE_URL"] = URL
for key in ("VAL_FAST_ROUTE_TIERS", "VAL_TIER1_ROUTE", "VAL_SPECULATION", "VAL_ADAPTIVE_GRACE"):
    os.environ.pop(key, None)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

import val_gateway.context as context  # noqa: E402
from val_gateway.deliberate import send  # noqa: E402
from val_gateway.persona import seed  # noqa: E402
from val_gateway.projects import load_catalogue  # noqa: E402
from val_gateway.seal import SealRoute  # noqa: E402
from val_gateway.startup import start  # noqa: E402
from val_policy.light_conversation import FastRoute  # noqa: E402
from val_policy.project_resolution import ProjectSignals  # noqa: E402

CONDITION = sys.argv[1]
context.COMPACT_NOTES = CONDITION == "compact"
ROOT = Path(__file__).resolve().parents[5]


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
gateway = start(engine).gateway
catalogue = load_catalogue(engine)
NO_PROJECT = ProjectSignals(explicit_no_project=True)
OFF = FastRoute()
stream = subprocess.Popen(["lms", "log", "stream", "--source", "model", "--json"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
captured: list[str] = []
def _drain() -> None:
    assert stream.stdout is not None
    for line in stream.stdout:
        captured.append(line)
threading.Thread(target=_drain, daemon=True).start()
time.sleep(1.5)
gateway.prime_prefix()

CONVERSATIONS = [
    ["Explain three ways to make a film scene feel tense without using dialogue.", "Which of those works best in a night scene?", "Thank you, Val."],
    ["The venue is the hall.", "No, the chapel, not the hall.", "Where is the venue now?"],
    ["Should I send the letter tonight or tomorrow?", "Yes, do it."],
    ["Good evening, Val. Did you finish the invitation?", "Thank you, Val."],
    ["Are you able to remember what I said yesterday?", "How quickly can you answer me?"],
    ["Name two ways to end a chapter so the reader turns the page.", "Recap that in one sentence."],
]
steps = []; rows = []
for lines in CONVERSATIONS:
    conversation = None
    for words in lines:
        t = time.time()
        got = send(engine, gateway, words, catalogue=catalogue, signals=NO_PROJECT if conversation is None else None,
                   conversation_id=conversation, spoken=True, seal_route=SealRoute.UTTERANCE_FINALIZED, fast_route=OFF)
        conversation = got.turn.conversation.id
        with engine.connect() as c:
            call = c.execute(text("select tokens_in, tokens_out, latency_ms from model_calls where message_id = :m order by id desc limit 1"), {"m": got.turn.user_message.id}).first()  # type: ignore[attr-defined]
        steps.append({"label": words, "start": t, "end": time.time()})
        rows.append({"said": words, "answer": got.turn.val_message.content, "tokens_in": call[0], "tokens_out": call[1], "latency_ms": call[2]})  # type: ignore[attr-defined]
        print(json.dumps({"said": words, "tokens_in": call[0], "latency_ms": call[2], "answer": rows[-1]["answer"][:160]}, ensure_ascii=False))
        time.sleep(0.4)
        gateway.prime_prefix()
time.sleep(2.0); stream.terminate()
try: stream.wait(timeout=10)
except subprocess.TimeoutExpired: stream.kill()
for line in captured:
    try: e = json.loads(line)
    except ValueError: continue
    d = e.get("data", {})
    if d.get("type") == "llm.prediction.output":
        s = d.get("stats", {}); t = (e.get("timestamp") or 0) / 1000.0
        m = next((x for x in steps if x["start"] - 0.5 <= t <= x["end"] + 0.5), None)
        if m and (s.get("promptTokensCount") or 0) > 1000:
            for r in rows:
                if r["said"] == m["label"] and "ttft_s" not in r:
                    r["ttft_s"] = s.get("timeToFirstTokenSec"); r["runtime_prompt_tokens"] = s.get("promptTokensCount"); break
Path(sys.argv[2]).write_text(json.dumps({"condition": CONDITION, "rows": rows}, indent=1, ensure_ascii=False) + "\n")
import statistics
print(CONDITION, "prompt tokens median", statistics.median(r["tokens_in"] for r in rows), "ttft median", statistics.median([r.get("ttft_s") or 0 for r in rows]))
