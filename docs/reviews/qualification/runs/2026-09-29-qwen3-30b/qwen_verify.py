"""Verify Qwen3-30B-A3B-Instruct-2507 through Val Core before any quality call.

Owner order of 29 September 2026, §2 and §3. With `VAL_EXPERIMENT_COGNITION=qwen3-30b-a3b`
the candidate is the only local Partner route in this process; production's own request
construction (the record-state envelope and his words as one user message, the persona
whole as the system message) and production's switches are otherwise unchanged. A scratch
store; spoken, sealed conversations, so nothing is metered and nothing leaves this Mac.

Checked, each from the runtime's own records rather than the request we sent:

1. **Routing**: the call row names the candidate's configuration.
2. **Role handling and the persona**: the rendered prompt (`lms log stream`, the model's
   own input) has one system block, and it is the persona in full, byte for byte;
   then user and assistant turns in the stored order. The last user turn carries Core's
   record-state envelope ahead of his words.
3. **Token accounting**: the call succeeded, which means the exact preflight's count
   matched the server's `prompt_tokens` (a hard gate in the adapter); the count is recorded.
4. **Stop and streaming**: the runtime's stop reason is the model's own end of turn; the
   answer arrived as a stream (first visible text before completion).
5. **The static persona prime**: its plan and outcome (the persona and fixed framing
   only; no conversation content).
6. **Cache reuse and invalidation**: the engine's own "Prompt cache: using N/M" line for
   each call — the prime, a first turn, the next turn in the same conversation (which
   should reuse that conversation's earlier prompt), and a turn in another conversation
   (which should reuse the persona prefix only).
7. **Effective sampling**: the read-only observer's line for each call.

Local, $0. Usage: qwen_verify.py OUT.json
"""

from __future__ import annotations

import hashlib
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
URL = "postgresql+psycopg://localhost:5433/val_qwen_test"
os.environ["VAL_DATABASE_URL"] = URL
for key in ("VAL_FAST_ROUTE_TIERS", "VAL_TIER1_ROUTE", "VAL_SPECULATION", "VAL_ADAPTIVE_GRACE",
            "VAL_OWNER_PRECEDENCE", "VAL_REQUEST_CONSTRUCTION", "VAL_COMBINE_CONTINUATIONS",
            "VAL_ORDINARY_LOW", "VAL_ADAPTIVE_ENDPOINT", "VAL_TTS_LENGTH_BOUND"):
    os.environ.pop(key, None)
os.environ["VAL_EXPERIMENT_COGNITION"] = "qwen3-30b-a3b"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

import val_domain.registry as registry  # noqa: E402
from val_domain import timings  # noqa: E402
from val_domain.conversation import StoredRole  # noqa: E402
from val_gateway import conversations  # noqa: E402
from val_gateway.deliberate import send  # noqa: E402
from val_gateway.persona import seed  # noqa: E402
from val_gateway.projects import load_catalogue  # noqa: E402
from val_gateway.seal import SealRoute  # noqa: E402
from val_gateway.startup import start  # noqa: E402
from val_policy.light_conversation import FastRoute  # noqa: E402
from val_policy.project_resolution import ExplicitNoProject  # noqa: E402

OUT = Path(sys.argv[1])
ROOT = Path(__file__).resolve().parents[5]
LMS = str(Path.home() / ".lmstudio/bin/lms")
OBSERVER_LOG = Path.home() / ".lmstudio/val-runtime-observer.log"


def fresh_store() -> None:
    admin = create_engine(URL.replace("/val_qwen_test", "/postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        if not connection.execute(text("select 1 from pg_database where datname = 'val_qwen_test'")).first():
            connection.execute(text("create database val_qwen_test"))
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
gateway = start(engine).gateway
catalogue = load_catalogue(engine)
OFF = FastRoute()
with engine.connect() as c:
    persona = c.execute(text("select content from personas where is_active order by activated_at desc limit 1")).scalar_one()

streams: dict[str, list[str]] = {"model": [], "runtime": []}
procs = []
for source in streams:
    proc = subprocess.Popen([LMS, "log", "stream", "--source", source, "--json"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    procs.append(proc)
    threading.Thread(target=lambda p=proc, s=source: [streams[s].append(x) for x in p.stdout], daemon=True).start()
time.sleep(1.5)


def mark() -> dict[str, int]:
    return {"model": len(streams["model"]), "runtime": len(streams["runtime"]),
            "observer": len(OBSERVER_LOG.read_text().splitlines()) if OBSERVER_LOG.exists() else 0}


def since(start: dict[str, int]) -> dict:
    time.sleep(1.0)
    inputs, outputs, caches = [], [], []
    for line in streams["model"][start["model"]:]:
        data = json.loads(line).get("data", {})
        if data.get("type") == "llm.prediction.input":
            inputs.append(data.get("input", ""))
        elif data.get("type") == "llm.prediction.output":
            outputs.append(data.get("stats") or {})
    for line in streams["runtime"][start["runtime"]:]:
        message = json.loads(line).get("data", {}).get("message", "")
        found = re.search(r"Prompt cache: using (\d+)/(\d+) tokens", message)
        if found:
            caches.append({"cached": int(found.group(1)), "total": int(found.group(2))})
    observed = [json.loads(line.split(" request ", 1)[1])
                for line in OBSERVER_LOG.read_text().splitlines()[start["observer"]:] if " request {" in line]
    return {"inputs": inputs, "outputs": outputs, "caches": caches, "observed": observed}


def outline(rendered: str) -> list[dict]:
    """The rendered prompt's structure: each block's role and size, never its text."""
    blocks = re.findall(r"<\|im_start\|>(\w+)\n(.*?)(?:<\|im_end\|>\n|$)", rendered, re.S)
    return [{"role": role, "chars": len(body), "sha256": hashlib.sha256(body.encode()).hexdigest()[:12]}
            for role, body in blocks]


steps: list[dict] = []
began = time.monotonic()
start_mark = mark()
prime = dict(gateway.prime_prefix())
steps.append({"step": "persona prime", "result": {k: v for k, v in prime.items() if k != "light"},
              "seconds": round(time.monotonic() - began, 3), "runtime": since(start_mark)})


def turn(label: str, conversation: object, words: str) -> dict:
    start_mark = mark()
    deltas: list[float] = []
    with timings.recording() as recorder:
        t0 = time.monotonic()
        got = send(engine, gateway, words, catalogue=catalogue, conversation_id=conversation, spoken=True,
                   seal_route=SealRoute.UTTERANCE_FINALIZED, fast_route=OFF,
                   on_delta=lambda piece: deltas.append(time.monotonic() - t0))
        total = time.monotonic() - t0
    answered = hasattr(got, "turn")
    user = got.turn.user_message.id if answered else got.user_message.id  # type: ignore[attr-defined]
    with engine.connect() as c:
        call = c.execute(text(
            "select mc.tokens_in, mc.tokens_out, mc.model_config_id, mc.terminal_state::text, x.reasoning_present, "
            "x.reasoning_output_tokens, x.first_text_ms from model_calls mc left join model_call_measurements x "
            "on x.model_call_id = mc.id where mc.message_id = :m and mc.task_type::text = 'conversation' "
            "order by mc.created_at desc limit 1"), {"m": user}).first()
    runtime = since(start_mark)
    rendered = runtime["inputs"][-1] if runtime["inputs"] else ""
    blocks = outline(rendered)
    config = registry.by_id(call[2]) if call else None
    return {
        "step": label, "answered": answered,
        "answer": got.turn.val_message.content if answered else None,  # type: ignore[attr-defined]
        "config": config.slug if config else None, "tokens_in": call[0] if call else None,
        "tokens_out": call[1] if call else None, "terminal": call[3] if call else None,
        "reasoning_present": call[4] if call else None, "reasoning_tokens": call[5] if call else None,
        "first_delta_s": round(deltas[0], 3) if deltas else None, "deltas": len(deltas), "total_s": round(total, 3),
        "rendered_outline": blocks,
        "system_blocks": sum(1 for b in blocks if b["role"] == "system"),
        "persona_whole_in_system": rendered.startswith(f"<|im_start|>system\n{persona}<|im_end|>\n"),
        "thinking_markup": "<think>" in rendered,
        "runtime_prompt_tokens": [o.get("promptTokensCount") for o in runtime["outputs"]],
        "stop_reason": [o.get("stopReason") for o in runtime["outputs"]],
        "tokens_per_second": [round(o.get("tokensPerSecond") or 0, 1) for o in runtime["outputs"]],
        "caches": runtime["caches"], "observed": runtime["observed"],
        "marks": [(n, round(at - recorder.started_at, 3)) for n, at in recorder.marks][:12],
    }


def conversation(history: list[tuple[str, str]], title: str) -> object:
    c = conversations.create(engine, scope=ExplicitNoProject(), title=title)
    for said, reply in history:
        conversations.append(engine, c.id, role=StoredRole.USER, content=said)
        conversations.append(engine, c.id, role=StoredRole.VAL, content=reply)
    return c.id


first = conversation([("Good evening, Val.", "Good evening, my lord.")], "verify A")
steps.append(turn("first turn (conversation A)", first, "Name two ways to end a chapter so the reader turns the page."))
steps.append(turn("next turn, same conversation (A)", first, "Which of those works best in a night scene?"))
other = conversation([("Good evening, Val.", "Good evening, my lord.")], "verify B")
steps.append(turn("a turn in another conversation (B)", other, "What do you think of the second act?"))
for proc in procs:
    proc.terminate()
result = {"instance": "qwen3-30b-a3b-instruct-2507", "persona_sha256": hashlib.sha256(persona.encode()).hexdigest(),
          "steps": steps}
OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False, default=str) + "\n")
for s in steps:
    print(json.dumps({k: v for k, v in s.items() if k not in ("rendered_outline", "marks", "answer")}, default=str))
    if s.get("answer"):
        print("   ANSWER:", s["answer"][:400])
