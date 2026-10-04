"""Typed onset through the scratch service — T3 (sustained) and T4 (first use), service level.

Usage: typed_timing.py sustained|cold MODEL LABEL OUT.json SERVICE_LOG

`sustained`: after the typed prime reports, twelve differing turns in ONE conversation,
history growing, three seconds apart (the desktop's ordinary rhythm). `cold`: one turn
sent the moment the service answers /health — nothing resident, nothing prepared — so
the wait includes the model's start and whatever preparation runs.

Onset is Send → the first non-blank answer text received by this harness on the
loopback (**harness receipt, not desktop display**); completion is the settled event.
Both the monotonic and the wall clock are kept so a system sleep is visible.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8766"
TURNS = [
    "Suggest a name for a small secondhand bookshop.",
    "Why that one?",
    "What is the difference between a producer and an executive producer?",
    "Give me a title for a film about an orchard.",
    "Which of those titles do you prefer, and why?",
    "What should I say when I answer the phone at the studio?",
    "How long should a cold open be?",
    "Name a famous ghost story.",
    "And who wrote it?",
    "What is the capital of Australia?",
    "Give me one sentence I could open tomorrow's crew meeting with.",
    "Thank you.",
]

# A longer conversation with substantial answers, so the history reaches several thousand
# tokens: does onset stay flat well past the first few messages? (Frozen 3 October 2026
# before it was run.)
LONG = [
    *TURNS[:11],
    "Develop a short scene in prose, about two hundred words: a location scout arrives at a farm at dawn.",
    "Now the same scene from the farmer's point of view, about two hundred words.",
    "Which of the two versions is stronger, and why?",
    "Explain, conversationally, what a line producer does on a small film.",
    "And how is that different from a unit production manager?",
    "Give me five possible titles for the farm film.",
    "Which one would you pick?",
    "Write a logline for it using that title.",
    "Tighten that logline to under twenty-five words.",
    "Explain the difference between coverage and a master shot.",
    "When would you skip coverage altogether?",
    "Draft a three-sentence note thanking the crew for a hard night shoot.",
    "Make it warmer, but no longer.",
    "What are three common mistakes in a first short film?",
    "Which of those is hardest to fix in the edit?",
    "Summarise what we have discussed about the farm film so far, in four sentences.",
    "What was the first thing I asked you in this conversation?",
    "Suggest what I should work on tomorrow morning, in two sentences.",
    "Thank you.",
]


def wait_for_prime(log: Path, deadline_s: float = 300.0) -> dict:
    started = time.monotonic()
    while time.monotonic() - started < deadline_s:
        for line in log.read_text(errors="replace").splitlines():
            if "typed prime:" in line:
                return json.loads(line.split("typed prime: ", 1)[1])
        time.sleep(0.5)
    raise SystemExit("the typed prime did not report within the deadline")


def turn(client: httpx.Client, conversation: str | None, text: str) -> dict:
    body: dict[str, object] = (
        {"content": text, "conversation_id": conversation}
        if conversation
        else {"content": text, "no_project": True}
    )
    sent_wall, sent = time.time(), time.monotonic()
    first = None
    settled: dict = {}
    with client.stream("POST", f"{BASE}/turns/stream", json=body, timeout=900) as response:
        event = None
        for raw in response.iter_lines():
            if raw.startswith("event: "):
                event = raw[7:].strip()
            elif raw.startswith("data: "):
                if event == "delta" and first is None:
                    if json.loads(raw[6:]).get("text", "").strip():
                        first = time.monotonic()
                elif event == "settled":
                    settled = json.loads(raw[6:])
                elif event in ("error", "refused"):
                    settled = {"kind": event, **json.loads(raw[6:])}
    done, done_wall = time.monotonic(), time.time()
    message = settled.get("val_message") or {}
    return {
        "text": text,
        "onset_s": round(first - sent, 3) if first else None,
        "complete_s": round(done - sent, 3),
        "sleep_suspected": abs((done_wall - sent_wall) - (done - sent)) > 5.0,
        "outcome": settled.get("kind"),
        "answer_chars": len(message.get("content") or ""),
        "conversation_id": (settled.get("conversation") or {}).get("id"),
        "timing": settled.get("timing"),
        "error": settled.get("detail") or settled.get("error"),
    }


def main() -> int:
    mode, model, label, out, log = (
        sys.argv[1],
        sys.argv[2],
        sys.argv[3],
        Path(sys.argv[4]),
        Path(sys.argv[5]),
    )
    client = httpx.Client()
    rows: list[dict] = []
    result: dict = {"mode": mode, "model": model, "label": label}
    if mode == "cold":
        rows.append(turn(client, None, TURNS[0]))
        print(json.dumps(rows[-1]), flush=True)
    else:
        result["prime"] = wait_for_prime(log)
        conversation = None
        for text in LONG if mode == "long" else TURNS:
            row = turn(client, conversation, text)
            conversation = conversation or row["conversation_id"]
            rows.append(row)
            print(json.dumps(row), flush=True)
            time.sleep(3)
        onsets = [r["onset_s"] for r in rows if r["onset_s"] is not None]
        result["onset_median_s"] = round(statistics.median(onsets), 3)
        result["onset_max_s"] = max(onsets)
        half = len(onsets) // 2
        result["first_half_median_s"] = round(statistics.median(onsets[:half]), 3)
        result["second_half_median_s"] = round(statistics.median(onsets[half:]), 3)
        result["last_five_median_s"] = round(statistics.median(onsets[-5:]), 3)
        result["final_prompt_tokens"] = (rows[-1].get("timing") or {}).get("prompt_tokens")
    result["rows"] = rows
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
