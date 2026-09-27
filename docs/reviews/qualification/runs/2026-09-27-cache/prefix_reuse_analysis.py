"""Where consecutive ordinary requests first differ, at the rendered-token level — §8.

Remaining latency work, 27 September 2026, section 8: before any ordering variant is
built, examine two consecutive ordinary requests as the model receives them. Each
conversation here is sent live through the real Core path (`send`, spoken and sealed, so
every call is local and $0; the fast route off, so every turn is ordinary MEDIUM) against
the EXPERIMENT instance with cache renewal on, in both constructions — the request as it
stands (`as_is`) and the candidate's envelope-in-developer-block (`envelope_in_system`).

For every consecutive pair it records, from the **rendered model input** the runtime
itself reports (`lms log stream --source model`, `llm.prediction.input`) tokenized by the
instance's own tokenizer:

- the first token at which request k+1 differs from request k;
- the checkpoint request k left (the engine stores exactly one per request, at its
  prompt length less 11 tokens — `mlx_engine.cache_wrapper`, `checkpoint_tail_tokens`) and
  whether it is a prefix of request k+1 — the only way history could be reused, because a
  GPT-OSS cache cannot be trimmed back to a shorter prefix;
- the longest prefix any stored entry offers, and the engine's own "Prompt cache: using
  N/M" for request k+1, which must agree;
- where request k+1's uncached tokens lie: the Core state block, the history, his new
  words, the template's tail.

Usage: prefix_reuse_analysis.py OUT.json
"""

from __future__ import annotations

import glob
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
URL = "postgresql+psycopg://localhost:5433/val_prefix_test"
os.environ["VAL_DATABASE_URL"] = URL
for key in ("VAL_FAST_ROUTE_TIERS", "VAL_TIER1_ROUTE", "VAL_SPECULATION", "VAL_ADAPTIVE_GRACE",
            "VAL_OWNER_PRECEDENCE", "VAL_REQUEST_CONSTRUCTION", "VAL_ADAPTIVE_ENDPOINT"):
    os.environ.pop(key, None)

import lmstudio  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

import val_domain.registry as registry  # noqa: E402
import val_gateway.context as context  # noqa: E402
from val_gateway import conversations  # noqa: E402
from val_gateway.deliberate import send  # noqa: E402
from val_gateway.persona import seed  # noqa: E402
from val_gateway.projects import load_catalogue  # noqa: E402
from val_gateway.seal import SealRoute  # noqa: E402
from val_gateway.startup import start  # noqa: E402
from val_policy.light_conversation import FastRoute  # noqa: E402
from val_policy.project_resolution import ExplicitNoProject  # noqa: E402

EXPERIMENT = "val-exp-gpt-oss-20b"
registry.REGISTRY = tuple(
    c.model_copy(update={"model_identifier": EXPERIMENT}) if c.model_identifier == "openai/gpt-oss-20b" else c
    for c in registry.REGISTRY
)
ROOT = Path(__file__).resolve().parents[5]
TAIL = 11  # the engine's checkpoint_tail_tokens

TURNS = [
    "Name two ways to end a chapter so the reader turns the page.",
    "Which of those works best in a night scene?",
    "Give me one line of advice on pacing a chase sequence.",
    "Explain the difference between suspense and surprise in a scene.",
    "Which of those works better in a short story?",
    "What is a caesura?",
]


def fresh_store() -> None:
    subprocess.run(["dropdb", "-h", "localhost", "-p", "5433", "--if-exists", "val_prefix_test"], check=True)
    subprocess.run(["createdb", "-h", "localhost", "-p", "5433", "val_prefix_test"], check=True)
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

stream = subprocess.Popen([str(Path.home() / ".lmstudio/bin/lms"), "log", "stream", "--source", "model", "--json"],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
captured: list[tuple[float, dict]] = []


def _drain() -> None:
    assert stream.stdout is not None
    for line in stream.stdout:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        captured.append((time.time(), event))


threading.Thread(target=_drain, daemon=True).start()
time.sleep(1.5)

client = lmstudio.Client("127.0.0.1:1234", api_token=os.environ["VAL_LMSTUDIO_API_TOKEN"])
model = client.llm.model(EXPERIMENT)


def tokens_of(rendered: str) -> list[int]:
    return [int(t) for t in model.tokenize(rendered)]


def engine_line_for(prompt_tokens: int, after: float) -> dict | None:
    for path in sorted(glob.glob(str(Path.home() / ".lmstudio/server-logs/2026-09/2026-09-2*.log")))[-1:]:
        for line in open(path, errors="replace"):
            hit = re.search(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\].*Prompt cache: using (\d+)/(\d+) tokens", line)
            if hit and int(hit.group(3)) == prompt_tokens:
                at = time.mktime(time.strptime(hit.group(1), "%Y-%m-%d %H:%M:%S"))
                if at >= after - 1:
                    return {"cached": int(hit.group(2)), "prompt": int(hit.group(3))}
    return None


requests: list[dict] = []
for condition in ("as_is", "envelope_in_system"):
    context.ENVELOPE_IN_SYSTEM = condition == "envelope_in_system"
    conversation = conversations.create(engine, scope=ExplicitNoProject(), title=f"prefix {condition}").id
    gateway.prime_prefix()
    for words in TURNS:
        mark = len(captured)
        began = time.time()
        got = send(engine, gateway, words, catalogue=catalogue, conversation_id=conversation, spoken=True,
                   seal_route=SealRoute.UTTERANCE_FINALIZED, fast_route=OFF, on_delta=lambda _s: None)
        time.sleep(0.8)
        inputs = [e["data"]["input"] for _, e in captured[mark:]
                  if e.get("data", {}).get("type") == "llm.prediction.input" and len(e["data"].get("input", "")) > 5000]
        stats = [e["data"].get("stats", {}) for _, e in captured[mark:]
                 if e.get("data", {}).get("type") == "llm.prediction.output"]
        stats = [s for s in stats if (s.get("promptTokensCount") or 0) > 1000]
        if not inputs:
            print("no rendered input captured for", condition, words)
            continue
        rendered = max(inputs, key=len)
        ids = tokens_of(rendered)
        answered = hasattr(got, "turn")
        requests.append({
            "condition": condition, "words": words, "began": began, "rendered": rendered, "ids": ids,
            "ttft_s": stats[-1].get("timeToFirstTokenSec") if stats else None,
            "runtime_prompt_tokens": stats[-1].get("promptTokensCount") if stats else None,
            "answered": answered,
            "answer": got.turn.val_message.content[:160] if answered else None,  # type: ignore[attr-defined]
        })
        print(condition, len(ids), stats[-1].get("timeToFirstTokenSec") if stats else None, words[:40])
context.ENVELOPE_IN_SYSTEM = False
stream.terminate()


def region_starts(rendered: str) -> dict[str, int]:
    """Token index at which each region of the rendered input begins."""
    marks = {
        "state_block": rendered.find("VAL-STATE-V1"),
        "last_user_message": rendered.rfind("<|start|>user<|message|>"),
        "first_history_message": rendered.find("<|start|>user<|message|>"),
        "developer_block": rendered.find("<|start|>developer"),
        "assistant_tail": rendered.rfind("<|start|>assistant"),
    }
    return {name: len(tokens_of(rendered[:at])) if at >= 0 else -1 for name, at in marks.items()}


def state_of(rendered: str) -> dict:
    """The record-state block's JSON, as rendered (the text after its marker)."""
    at = rendered.find("VAL-STATE-V1")
    if at < 0:
        return {}
    start = rendered.find("{", at)
    depth = 0
    for index in range(start, len(rendered)):
        if rendered[index] == "{":
            depth += 1
        elif rendered[index] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(rendered[start : index + 1])
                except ValueError:
                    return {}
    return {}


def flatten(value: object, prefix: str = "") -> dict[str, object]:
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for key, inner in value.items():
            out.update(flatten(inner, f"{prefix}.{key}" if prefix else str(key)))
        return out
    return {prefix: json.dumps(value, ensure_ascii=False)}


def changed_fields(before: str, after: str) -> list[str]:
    a, b = flatten(state_of(before)), flatten(state_of(after))
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def first_text_difference(before: str, after: str) -> dict:
    at = next((i for i, (x, y) in enumerate(zip(before, after)) if x != y), min(len(before), len(after)))
    return {"char": at, "before": before[max(0, at - 80): at + 60], "after": after[max(0, at - 80): at + 60]}


pairs: list[dict] = []
for condition in ("as_is", "envelope_in_system"):
    mine = [r for r in requests if r["condition"] == condition]
    stored: list[list[int]] = []
    for previous, current in zip(mine, mine[1:]):
        a, b = previous["ids"], current["ids"]
        first_difference = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        checkpoint = a[: len(a) - TAIL]
        stored.append(checkpoint)
        reusable = max((len(key) for key in stored if b[: len(key)] == key), default=0)
        line = engine_line_for(len(b), current["began"])
        regions = region_starts(current["rendered"])
        pairs.append({
            "condition": condition,
            "request": current["words"],
            "prompt_tokens": len(b),
            "first_difference_index": first_difference,
            "first_difference_region": next(
                (name for name, at in sorted(regions.items(), key=lambda kv: -kv[1]) if 0 <= at <= first_difference),
                "persona",
            ),
            "previous_checkpoint_tokens": len(checkpoint),
            "previous_checkpoint_is_prefix": b[: len(checkpoint)] == checkpoint,
            "longest_stored_request_checkpoint_prefix": reusable,
            "engine_cached_tokens": None if line is None else line["cached"],
            "regions": regions,
            "ttft_s": current["ttft_s"],
            "answer": current["answer"],
            "state_fields_changed": changed_fields(previous["rendered"], current["rendered"]),
            "first_text_difference": first_text_difference(previous["rendered"], current["rendered"]),
            "state_block_tokens": len(tokens_of(json.dumps(state_of(current["rendered"]), ensure_ascii=False, indent=1))) if state_of(current["rendered"]) else None,
        })
out = {"pairs": pairs, "requests": [{k: v for k, v in r.items() if k not in ("rendered", "ids")} | {"tokens": len(r["ids"])} for r in requests],
       "rendered_tail_example": {c: next((r["rendered"][-1800:] for r in requests if r["condition"] == c), None) for c in ("as_is", "envelope_in_system")}}
Path(sys.argv[1]).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
for p in pairs:
    print(json.dumps({k: p[k] for k in ("condition", "prompt_tokens", "first_difference_index", "first_difference_region",
                                        "previous_checkpoint_is_prefix", "engine_cached_tokens", "ttft_s", "state_fields_changed")}))
