"""Milestone B §7: the conversation-prefix prefill experiment — 26 September 2026.

On this runtime a prefill is a one-token generation request (`ORDINARY_TURN.md` §7).
After each turn of a scripted scratch conversation, the exact prefix the *next* ordinary
request will share — persona (system) and the retained history as Core assembles it,
nothing of the envelope or the next turn, no hidden reasoning — is sent as such a
request with `max_tokens: 1`, its token discarded. The next turn's time to first token
is then read from the runtime's own log, against the same conversation replayed without
the prefill. Also measured: the prefill's own cost, whether it evicted the persona
checkpoints (the prime's duration afterwards), and what happens when the history changes
(a revision) between prefill and turn — the prefill must then simply be stale, never
used. Scratch store, scripted content, local, $0. Usage: prefix_prefill_experiment.py OUT.json
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

import httpx  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from val_gateway import conversations  # noqa: E402
from val_gateway.deliberate import send  # noqa: E402
from val_gateway.persona import seed  # noqa: E402
from val_gateway.projects import load_catalogue  # noqa: E402
from val_gateway.seal import SealRoute  # noqa: E402
from val_gateway.startup import start  # noqa: E402
from val_policy.light_conversation import FastRoute  # noqa: E402
from val_policy.project_resolution import ProjectSignals  # noqa: E402
from val_providers.lmstudio_adapter import canonicalize_turns  # noqa: E402

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(sys.argv[1])


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
OFF = FastRoute()
BASE = os.environ.get("VAL_LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
client = httpx.Client(base_url=BASE, timeout=180.0,
                      headers={"Authorization": f"Bearer {os.environ['VAL_LMSTUDIO_API_TOKEN']}"})
MODEL = "openai/gpt-oss-20b"

# the runtime's own prediction stats, drained continuously
stream = subprocess.Popen(["lms", "log", "stream", "--source", "model", "--json"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
captured: list[str] = []
def _drain() -> None:
    assert stream.stdout is not None
    for line in stream.stdout:
        captured.append(line)
threading.Thread(target=_drain, daemon=True).start()
time.sleep(1.5)
steps: list[dict] = []


def step(label: str, fn):  # noqa: ANN001, ANN201
    t = time.time(); result = fn(); steps.append({"label": label, "start": t, "end": time.time(), "result": result}); time.sleep(0.4); return result


def persona_content() -> str:
    with engine.connect() as c:
        return c.execute(text("select content from personas where is_active order by activated_at desc limit 1")).scalar_one()


def prefill_prefix(conversation_id) -> dict:  # noqa: ANN001
    """One-token request over persona + the retained history exactly as Core holds it."""
    thread = conversations.working(engine, conversation_id)
    turns = [{"role": "system", "content": persona_content()}]
    for record in thread.live_records():
        if record.role.value in ("user", "val"):
            turns.append({"role": "user" if record.role.value == "user" else "assistant", "content": record.content})
    body = {"model": MODEL, "messages": canonicalize_turns(turns), "max_tokens": 1, "stream": False}
    t = time.monotonic(); r = client.post("/chat/completions", json=body); return {"status": r.status_code, "seconds": round(time.monotonic() - t, 3), "prompt_tokens": (r.json().get("usage") or {}).get("prompt_tokens")}


def turn(conversation_id, words: str):  # noqa: ANN001, ANN201
    got = send(engine, gateway, words, catalogue=catalogue, signals=NO_PROJECT if conversation_id is None else None,
               conversation_id=conversation_id, spoken=True, seal_route=SealRoute.UTTERANCE_FINALIZED, fast_route=OFF)
    return got.turn.conversation.id


SCRIPT = ["Explain three ways to make a film scene feel tense without using dialogue.",
          "Which of those works best in a night scene?",
          "Name two ways to end a chapter so the reader turns the page.",
          "Which is stronger to open a chapter, dialogue or description?"]
for condition in ("without_prefill", "with_prefill"):
    step(f"{condition}: prime", lambda: dict(gateway.prime_prefix()).get("outcome"))
    conversation = None
    for i, words in enumerate(SCRIPT):
        conversation = step(f"{condition}: turn {i + 1}", lambda: turn(conversation, words))
        if condition == "with_prefill" and i < len(SCRIPT) - 1:
            step(f"{condition}: prefill after turn {i + 1}", lambda: prefill_prefix(conversation))
        step(f"{condition}: prime after turn {i + 1}", lambda: {"seconds": (lambda t: (gateway.prime_prefix(), round(time.monotonic() - t, 3))[1])(time.monotonic())})
# invalidation: a prefill, then a revision of the last message, then the turn (the prefill is stale)
from val_gateway.revisions import revise  # noqa: E402
conv = step("stale: turn 1", lambda: turn(None, SCRIPT[0]))
step("stale: prefill", lambda: prefill_prefix(conv))
with engine.connect() as c:
    last_user = c.execute(text("select id from messages where conversation_id = :c and role = 'user' order by sequence desc limit 1"), {"c": conv}).scalar_one()
revise(engine, last_user, "Explain three ways to make a stage scene feel tense without using dialogue.", note="experiment")
step("stale: turn 2 after revision", lambda: turn(conv, SCRIPT[1]))
time.sleep(2.0); stream.terminate()
try: stream.wait(timeout=10)
except subprocess.TimeoutExpired: stream.kill()
predictions = []; pending = None
for line in captured:
    try: e = json.loads(line)
    except ValueError: continue
    d = e.get("data", {})
    if d.get("type") == "llm.prediction.input": pending = {"chars": len(d.get("input", ""))}
    elif d.get("type") == "llm.prediction.output":
        s = d.get("stats", {}); predictions.append({"timestamp": e.get("timestamp"), "prompt_tokens": s.get("promptTokensCount"), "ttft_s": s.get("timeToFirstTokenSec"), "out": s.get("predictedTokensCount")}); pending = None
for p in predictions:
    t = (p["timestamp"] or 0) / 1000.0
    m = next((s for s in steps if s["start"] - 0.5 <= t <= s["end"] + 0.5), None); p["step"] = None if m is None else m["label"]
report = {"steps": steps, "predictions": predictions}
OUT.write_text(json.dumps(report, indent=1, default=str) + "\n")
for p in predictions:
    if p["prompt_tokens"] and p["prompt_tokens"] > 1000: print(f"{(p['step'] or '-'):40s} prompt {p['prompt_tokens']} ttft {p['ttft_s']} out {p['out']}")
for s in steps:
    if "prime after" in s["label"] or "prefill" in s["label"]: print(s["label"], s["result"])
