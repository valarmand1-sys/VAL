"""Feasibility probe for the reasoning budget (owner order of 29 September 2026, §2).

On the experimental instance only (`val-exp-hub`), over the loopback chat-completions
surface Val's adapter uses:

1. **uncapped** (control file disabled): one request, its reasoning and answer;
2. **capped** (enabled, the budget below): the same request. The budget must apply (the
   hook logs a forced transition; the runtime's reasoning-token count falls), the answer
   must be well formed (non-empty, `finish_reason: stop`, no harmony markers), and the
   reasoning must stay in the reasoning field, never in the answer text;
3. **cancellation**: a capped request closed during its reasoning, and another closed
   during its answer. Each must be followed at once by a request that starts promptly
   (a sequential instance would make it wait behind a generation that kept running).

The reasoning text itself is not recorded (as in the adapter): only its presence, length
and token count. Local, $0. Usage: budget_probe.py OUT.json
"""

from __future__ import annotations

import json
import plistlib
import sys
import time
from pathlib import Path

import httpx

OUT = Path(sys.argv[1])
BASE = "http://127.0.0.1:1234/v1"
INSTANCE = "val-exp-hub"
CONTROL = Path.home() / ".lmstudio/val-reasoning-budget.json"
BUDGET_LOG = Path.home() / ".lmstudio/val-reasoning-budget.log"
CLONE = str(Path.home() / ".lmstudio/models/val-experiment/gpt-oss-20b-MXFP4-Q8-renewal")
with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    TOKEN = plistlib.load(handle)["EnvironmentVariables"]["VAL_LMSTUDIO_API_TOKEN"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
PROMPT = (
    "Plan a three-day walking route through Kyoto for someone who dislikes crowds, "
    "then say which single day you would cut if only two were possible, and why."
)


def control(enabled: bool) -> None:
    CONTROL.write_text(json.dumps({"model_paths": [CLONE], "enabled": enabled,
                                   "budget_tokens": 128, "hard_tokens": 160}, indent=1) + "\n")


def call(prompt: str, *, stop_after: str | None = None, max_tokens: int = 2048) -> dict:
    body = {"model": INSTANCE, "messages": [{"role": "user", "content": prompt}], "stream": True,
            "max_tokens": max_tokens, "reasoning_effort": "medium", "stream_options": {"include_usage": True}}
    began = time.monotonic()
    row: dict = {"reasoning_chars": 0, "content": "", "first_reasoning_s": None, "first_content_s": None,
                 "finish_reason": None, "usage": None, "closed_early": None}
    with httpx.Client(timeout=600) as client, client.stream("POST", f"{BASE}/chat/completions",
                                                            headers=HEADERS, json=body) as response:
        for line in response.iter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            chunk = json.loads(line[6:])
            if chunk.get("usage"):
                row["usage"] = chunk["usage"]
            for choice in chunk.get("choices", []):
                delta = choice.get("delta") or {}
                reasoning = delta.get("reasoning") or delta.get("reasoning_content") or ""
                if reasoning:
                    row["reasoning_chars"] += len(reasoning)
                    row["first_reasoning_s"] = row["first_reasoning_s"] or round(time.monotonic() - began, 3)
                if delta.get("content"):
                    row["content"] += delta["content"]
                    row["first_content_s"] = row["first_content_s"] or round(time.monotonic() - began, 3)
                if choice.get("finish_reason"):
                    row["finish_reason"] = choice["finish_reason"]
            if stop_after == "reasoning" and row["reasoning_chars"] > 40:
                row["closed_early"] = "during reasoning"
                break
            if stop_after == "content" and row["content"]:
                row["closed_early"] = "during the answer"
                break
    row["total_s"] = round(time.monotonic() - began, 3)
    row["harmony_markers_in_answer"] = any(m in row["content"] for m in ("<|", "|>", "analysis", "assistantfinal"))
    return row


def budget_lines(since: int) -> list[str]:
    return BUDGET_LOG.read_text().splitlines()[since:]


result: dict = {"instance": INSTANCE, "budget_tokens": 128, "hard_tokens": 160, "prompt": PROMPT, "steps": []}
for label, enabled, stop in (
    ("warm-up (uncapped, not measured)", False, None),
    ("uncapped", False, None),
    ("capped", True, None),
    ("capped, closed during reasoning", True, "reasoning"),
    ("prompt follow-up after that close", False, None),
    ("capped, closed during the answer", True, "content"),
    ("prompt follow-up after that close", False, None),
):
    control(enabled)
    since = len(BUDGET_LOG.read_text().splitlines())
    prompt = "Say good evening in one short sentence." if label.startswith("prompt follow-up") else PROMPT
    row = call(prompt, stop_after=stop)
    time.sleep(0.5)
    row.update({"step": label, "enabled": enabled, "budget_log": budget_lines(since)})
    if label != "uncapped" and label != "capped":
        row["content"] = row["content"][:120]
    result["steps"].append(row)
    print(json.dumps({k: row[k] for k in ("step", "first_reasoning_s", "first_content_s", "total_s", "finish_reason",
                                         "harmony_markers_in_answer", "closed_early")}
                     | {"reasoning_tokens": ((row["usage"] or {}).get("completion_tokens_details") or {}).get("reasoning_tokens"),
                        "log": [line.split(" v1.0 ", 1)[-1] for line in row["budget_log"]]}), flush=True)
control(False)
OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
