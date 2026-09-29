"""Verify the corrected LOW configuration before any batch (the owner's order, §3).

On the hub-defined clone (`val-exp-hub`: the renewal clone under a model definition
byte-identical in its reasoning, sampling and metadata sections to production's), through
the real Core, one request at a time on a sequential instance:

1. both primes: the shared LOW prime (its checkpoint on the prefix the Tier-1 and ordinary
   LOW requests share) and the MEDIUM prime;
2. an ordinary LOW turn — must reuse the shared LOW checkpoint;
3. an ordinary MEDIUM turn — must reuse the MEDIUM checkpoint;
4. a Tier-1 LOW turn — must reuse the shared LOW checkpoint;
5. a second MEDIUM turn after the LOW turns — must still reuse the MEDIUM checkpoint.

Request-attributed: each call's prompt-token count (`model_calls.tokens_in`, the server's
own count) is matched to exactly one engine hook line (`total`) and one rendered input
from `lms log stream` (the runtime's own prompt, read for its `Reasoning:` line only), in
order on a sequential instance; anything not matched exactly once is reported unmatched.
Local, $0. Usage: effort_verify.py OUT.json
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    for name, value in plistlib.load(handle)["EnvironmentVariables"].items():
        if name != "VAL_DATABASE_URL":
            os.environ[name] = value
URL = "postgresql+psycopg://localhost:5433/val_effort_test"
os.environ["VAL_DATABASE_URL"] = URL
for key in ("VAL_FAST_ROUTE_TIERS", "VAL_TIER1_ROUTE", "VAL_SPECULATION", "VAL_ADAPTIVE_GRACE",
            "VAL_OWNER_PRECEDENCE", "VAL_REQUEST_CONSTRUCTION", "VAL_COMBINE_CONTINUATIONS", "VAL_ORDINARY_LOW"):
    os.environ.pop(key, None)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

import val_domain.registry as registry  # noqa: E402
import val_gateway.context as context  # noqa: E402
import val_gateway.deliberate as core  # noqa: E402
from val_domain.conversation import StoredRole  # noqa: E402
from val_gateway import conversations  # noqa: E402
from val_gateway.deliberate import send  # noqa: E402
from val_gateway.persona import seed  # noqa: E402
from val_gateway.projects import load_catalogue  # noqa: E402
from val_gateway.seal import SealRoute  # noqa: E402
from val_gateway.startup import enable_light_candidate, enable_ordinary_low, start  # noqa: E402
from val_policy.light_conversation import FastRoute  # noqa: E402
from val_policy.project_resolution import ExplicitNoProject  # noqa: E402

OUT = Path(sys.argv[1])
ROOT = Path(__file__).resolve().parents[5]
INSTANCE = os.environ.get("VAL_EFFORT_INSTANCE", "val-exp-hub")
registry.REGISTRY = tuple(
    config.model_copy(update={"model_identifier": INSTANCE})
    if config.model_identifier == "openai/gpt-oss-20b" else config
    for config in registry.REGISTRY
)
HOOK_LOG = Path.home() / ".lmstudio/val-cache-renewal.log"


def fresh_store() -> None:
    admin = create_engine(URL.replace("/val_effort_test", "/postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        if not connection.execute(text("select 1 from pg_database where datname = 'val_effort_test'")).first():
            connection.execute(text("create database val_effort_test"))
    admin.dispose()
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
context.ENVELOPE_IN_SYSTEM = True
context.SPLIT_STATE = False
context.SHARED_LOW_PRIME = True
enable_light_candidate("low")
core.ORDINARY_LOW = enable_ordinary_low()
gateway = start(engine).gateway
catalogue = load_catalogue(engine)
TIER1 = FastRoute(tiers=frozenset({1}))
OFF = FastRoute()

stream = subprocess.Popen([str(Path.home() / ".lmstudio/bin/lms"), "log", "stream", "--source", "model", "--json"],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
events: list[str] = []
threading.Thread(target=lambda: [events.append(line) for line in stream.stdout], daemon=True).start()
time.sleep(1.5)
hook_from = len(HOOK_LOG.read_text().splitlines())


def conversation(history: list[tuple[str, str]]) -> object:
    c = conversations.create(engine, scope=ExplicitNoProject(), title="verify")
    for said, reply in history:
        conversations.append(engine, c.id, role=StoredRole.USER, content=said)
        conversations.append(engine, c.id, role=StoredRole.VAL, content=reply)
    return c.id


steps: list[dict] = []
began = time.monotonic()
prime = gateway.prime_prefix()
steps.append({"step": "primes", "result": {k: (v if not isinstance(v, dict) else dict(v)) for k, v in dict(prime).items()},
              "seconds": round(time.monotonic() - began, 3)})
GREETING = [("Good evening, Val.", "Good evening, my lord.")]
for label, words, route, history in (
    ("ordinary LOW (class C)", "Describe a lighthouse in one sentence.", OFF, GREETING),
    ("ordinary MEDIUM", "What do you think of the second act?", OFF, GREETING),
    ("Tier-1 LOW", "Thank you, Val.", TIER1, [("Name two ways to end a chapter.", "A door left ajar, my lord, or a door slammed.")]),
    ("ordinary MEDIUM after LOW", "Why do ghost stories work best in winter?", OFF, GREETING),
):
    t = time.monotonic()
    got = send(engine, gateway, words, catalogue=catalogue, conversation_id=conversation(history), spoken=True,
               seal_route=SealRoute.UTTERANCE_FINALIZED, fast_route=route)
    user = got.turn.user_message.id if hasattr(got, "turn") else got.user_message.id  # type: ignore[attr-defined]
    with engine.connect() as c:
        call = c.execute(text("select mc.tokens_in, mc.task_type::text, mc.model_config_id from model_calls mc "
                              "where mc.message_id = :m order by mc.created_at desc limit 1"), {"m": user}).first()
    steps.append({"step": label, "tokens_in": call[0], "task": call[1],
                  "config": registry.by_id(call[2]).slug if registry.by_id(call[2]) else str(call[2]),
                  "answered": hasattr(got, "turn"), "seconds": round(time.monotonic() - t, 3)})
    time.sleep(0.5)
time.sleep(2.0)
stream.terminate()
hooks = [json.loads(line.split(" request ", 1)[1]) for line in HOOK_LOG.read_text().splitlines()[hook_from:]
         if " request {" in line]
rendered = []
for line in events:
    try:
        data = json.loads(line).get("data", {})
    except ValueError:
        continue
    if data.get("type") == "llm.prediction.input":
        rendered.append({"reasoning": (re.findall(r"Reasoning:\s*\w+", data.get("input", "")) or [None])[0]})
    elif data.get("type") == "llm.prediction.output" and rendered:
        rendered[-1]["prompt_tokens"] = (data.get("stats") or {}).get("promptTokensCount")
for step in steps:
    if "tokens_in" not in step:
        continue
    matched = [h for h in hooks if h.get("total") == step["tokens_in"]]
    renders = [r for r in rendered if r.get("prompt_tokens") == step["tokens_in"]]
    step["engine"] = matched[0] if len(matched) == 1 else f"unmatched ({len(matched)} candidates)"
    step["rendered_reasoning"] = renders[0]["reasoning"] if len(renders) == 1 else f"unmatched ({len(renders)})"
prime_lines = [h for h in hooks if h.get("total", 0) < 5200]
result = {"instance": INSTANCE, "steps": steps, "prime_hook_lines": prime_lines,
          "store_after": {k: hooks[-1].get(k) for k in ("entries", "store_bytes", "active_memory")} if hooks else None}
OUT.write_text(json.dumps(result, indent=1) + "\n")
print(json.dumps(result, indent=1))
