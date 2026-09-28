"""Does a greeting that disagrees with the house clock lengthen the light route? — §4.

The 27 September record attributed the afternoon's longer LOW reasoning (73–259 hidden
tokens for a greeting or thanks, against about 32 at night) to "Good evening" at two in
the afternoon drawing deliberation. Controlled test: one Tier-1 request exactly as Core
built it in stage C (`stage-C.json` body 2 — persona whole, the Tier-1 record state, the
contract, his words), with only two things varied: his greeting and the clock's
`current_time.local` value. The persona prefix is primed first so prefill is identical;
each condition is sampled N times with the route's own settings (reasoning_effort low,
no sampling override), interleaved so drift in the machine falls on every condition.
Measured: hidden reasoning tokens, time to first visible text, the answer. Local, $0.

Phase `omit` (run only if the clock is shown to matter): the same requests with
`current_time` removed from the state — the candidate projection for a turn whose words
do not need it; recorded as a test, not adopted.

Usage: time_of_day.py stage-C.json OUT.json [clock|omit] [N]
"""

from __future__ import annotations

import copy
import json
import plistlib
import statistics
import sys
import time
from pathlib import Path

import httpx

SOURCE, OUT = Path(sys.argv[1]), Path(sys.argv[2])
PHASE = sys.argv[3] if len(sys.argv) > 3 else "clock"
N = int(sys.argv[4]) if len(sys.argv) > 4 else 4
TOKEN = plistlib.loads((Path.home() / "Library/LaunchAgents/house.armand.val.api.plist").read_bytes())[
    "EnvironmentVariables"
]["VAL_LMSTUDIO_API_TOKEN"]
base = json.loads(SOURCE.read_text())["bodies"][2]["body"]
# The adapter joins consecutive user messages (17 September ruling): state, contract and
# his words arrive as one message, his words its last paragraph.
assert base["reasoning_effort"] == "low" and base["messages"][-1]["content"].endswith("\n\nGood evening, Val.")
GREETINGS = ("Good morning, Val.", "Good evening, Val.", "Good night, Val.", "Hello, Val.")
CLOCKS = ("09:15", "14:00", "21:30")


def body_for(greeting: str, clock: str | None) -> dict:
    body = copy.deepcopy(base)
    marker, _, document = body["messages"][1]["content"].partition("\n")
    state_text, sep, rest = document.partition("\n\nVAL-TIER1-INSTRUCTION-V1")
    rest = rest.rsplit("\n\n", 1)[0] + "\n\n" + greeting
    state = json.loads(state_text)
    if clock is None:
        del state["record_state"]["current_time"]
    else:
        state["record_state"]["current_time"]["local"] = f"Monday 28 September 2026, {clock}"
    body["messages"][1]["content"] = (
        marker + "\n" + json.dumps(state, ensure_ascii=False, indent=2) + sep + rest
    )
    return body


def send(body: dict) -> dict:
    began = time.perf_counter()
    first_text = None
    reasoning, content, usage = [], [], {}
    with httpx.stream("POST", "http://127.0.0.1:1234/v1/chat/completions",
                      headers={"Authorization": f"Bearer {TOKEN}"},
                      json=dict(body, stream=True, stream_options={"include_usage": True}), timeout=300) as reply:
        for line in reply.iter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            event = json.loads(line[6:])
            usage = event.get("usage") or usage
            for choice in event.get("choices", []):
                delta = choice.get("delta", {})
                if delta.get("reasoning"):
                    reasoning.append(delta["reasoning"])
                if delta.get("content"):
                    first_text = first_text or time.perf_counter() - began
                    content.append(delta["content"])
    return {"first_text_s": round(first_text or 0, 3), "total_s": round(time.perf_counter() - began, 3),
            "completion_tokens": usage.get("completion_tokens"), "reasoning_chunks": len(reasoning),
            "reasoning": "".join(reasoning), "answer": "".join(content)}


send(dict(body_for(GREETINGS[0], CLOCKS[0]), max_tokens=1))  # the persona prefix, warm
clocks = CLOCKS if PHASE == "clock" else (None,)
rows = []
for sample in range(N):
    for greeting in GREETINGS:
        for clock in clocks:
            result = send(body_for(greeting, clock))
            rows.append({"greeting": greeting, "clock": clock, "sample": sample, **result})
            print(greeting, clock, result["reasoning_chunks"], result["first_text_s"], repr(result["answer"][:70]), flush=True)
summary = {}
for greeting in GREETINGS:
    for clock in clocks:
        cell = [r for r in rows if r["greeting"] == greeting and r["clock"] == clock]
        summary[f"{greeting} @ {clock}"] = {
            "reasoning_chunks_median": statistics.median(r["reasoning_chunks"] for r in cell),
            "reasoning_chunks": [r["reasoning_chunks"] for r in cell],
            "first_text_s_median": round(statistics.median(r["first_text_s"] for r in cell), 3),
        }
OUT.write_text(json.dumps({"phase": PHASE, "n": N, "summary": summary, "rows": rows}, indent=1, ensure_ascii=False) + "\n")
print(json.dumps(summary, indent=1))
