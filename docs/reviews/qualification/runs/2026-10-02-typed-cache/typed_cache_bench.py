"""Typed prefix preparation, measured — owner authorisation, 2 October 2026.

Drives the scratch service (port 8766, the scratch store, GPT-OSS addressed as an
isolated second instance of production's model) through a short sequence of differing
typed turns in one conversation, including a follow-up, then a Voice session opened and
closed with nothing said (the Voice→typed transition: Gemma loaded, the Partner released
and brought back), then more typed turns. For each turn: send → first visible text
(the first `delta` event), the runtime's own prompt-cache figure for that request from
LM Studio's log ("Prompt cache: using N/M tokens"), and the measured prefill time.

Usage: typed_cache_bench.py LABEL OUT.json
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8766"
LOGS = Path.home() / ".lmstudio/server-logs"

TURNS_BEFORE = [
    "Suggest a name for a small secondhand bookshop.",
    "Why that one?",
    "What is the difference between a producer and an executive producer?",
    "Give me a title for a film about an orchard.",
]
TURNS_AFTER = [
    "Which of those titles do you prefer, and why?",
    "What should I say when I answer the phone at the studio?",
]


def newest_log() -> Path:
    return max(LOGS.glob("*/*.log"), key=lambda p: p.stat().st_mtime)


def log_lines_since(path: Path, offset: int) -> tuple[list[str], int]:
    data = path.read_text(errors="replace")
    return data[offset:].splitlines(), len(data)


def cache_facts(lines: list[str]) -> dict:
    using = [
        m for m in (re.search(r"Prompt cache: using (\d+)/(\d+)", line) for line in lines) if m
    ]
    progress = [line for line in lines if "Prompt processing progress" in line]
    stamps = [re.search(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\]", line) for line in progress]
    first = next((s.group(1) for s in stamps if s), None)
    last = next((s.group(1) for s in reversed(stamps) if s), None)
    return {
        "cache_used": int(using[-1].group(1)) if using else None,
        "prompt_tokens": int(using[-1].group(2)) if using else None,
        "prefill_first_stamp": first,
        "prefill_last_stamp": last,
    }


def typed_turn(
    client: httpx.Client, conversation: str | None, text: str, log: Path, offset: int
) -> tuple[dict, int]:
    body = {"content": text, "no_project": True}
    if conversation:
        body["conversation_id"] = conversation
    sent = time.monotonic()
    first_delta = None
    settled = None
    with client.stream("POST", f"{BASE}/turns/stream", json=body, timeout=600) as response:
        event = None
        for raw in response.iter_lines():
            if raw.startswith("event: "):
                event = raw[7:].strip()
            elif raw.startswith("data: "):
                if event == "delta" and first_delta is None:
                    first_delta = time.monotonic()
                elif event == "settled":
                    settled = json.loads(raw[6:])
    done = time.monotonic()
    time.sleep(0.5)
    lines, offset = log_lines_since(log, offset)
    facts = cache_facts(lines)
    timing = (settled or {}).get("timing", {})
    row = {
        "text": text,
        "send_to_first_visible_s": round(first_delta - sent, 3) if first_delta else None,
        "send_to_complete_s": round(done - sent, 3),
        "gateway_first_output_ms": timing.get("gateway_first_output_ms"),
        **facts,
        "conversation_id": (settled or {}).get("conversation", {}).get("id") if settled else None,
    }
    return row, offset


def main() -> int:
    label, out = sys.argv[1], Path(sys.argv[2])
    client = httpx.Client()
    log = newest_log()
    offset = len(log.read_text(errors="replace"))
    rows: list[dict] = []
    conversation = None
    t0 = time.monotonic()
    for text in TURNS_BEFORE:
        row, offset = typed_turn(client, conversation, text, log, offset)
        row["phase"] = "before_voice"
        row["at_s"] = round(time.monotonic() - t0, 1)
        conversation = conversation or row["conversation_id"]
        rows.append(row)
        print(json.dumps(row), flush=True)
        time.sleep(3)
    # The transition: a Voice session opened on this conversation and closed with
    # nothing said. The service loads the Voice model (releasing the Partner) and, on
    # close, brings the Partner back — and, under the setting, primes it.
    opened = client.post(
        f"{BASE}/voice/sessions",
        json={"no_project": True, "conversation_id": conversation},
        timeout=120,
    )
    session = opened.json()["session"]
    voice_on = time.monotonic()
    for _ in range(600):
        view = client.get(f"{BASE}/voice/sessions/{session}", timeout=30).json()
        if view.get("readiness", {}).get("ready"):
            break
        time.sleep(0.5)
    ready_s = round(time.monotonic() - voice_on, 1)
    time.sleep(2)
    client.post(f"{BASE}/voice/sessions/{session}/close", timeout=60)
    closed = time.monotonic()
    # Wait for the Partner to be back (and any prime to finish) as the service reports it.
    time.sleep(2)
    transition = {"voice_on_to_ready_s": ready_s, "closed_at_s": round(closed - t0, 1)}
    print(json.dumps({"transition": transition}), flush=True)
    # The first typed turn right after Voice: how long it waits.
    for index, text in enumerate(TURNS_AFTER):
        if index == 0:
            time.sleep(1.0)
        row, offset = typed_turn(client, conversation, text, log, offset)
        row["phase"] = "after_voice"
        row["at_s"] = round(time.monotonic() - t0, 1)
        row["seconds_after_voice_closed"] = round(time.monotonic() - closed, 1)
        rows.append(row)
        print(json.dumps(row), flush=True)
        time.sleep(3)
    out.write_text(
        json.dumps({"label": label, "rows": rows, "transition": transition}, indent=1) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
