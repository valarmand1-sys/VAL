"""Eight frozen prompts through Val Core's typed path, one model at a time — 2 October 2026.

Usage: compare_bench.py MODEL LABEL forward|reverse OUT.json SERVICE_LOG

Each prompt opens its own unassigned conversation (as the desktop's New chat does) and is
sent to `POST /turns/stream`. Recorded per prompt: the persisted answer verbatim, the
harness's receipt of the first visible text and of the settled answer (**harness receipt
on the loopback, not desktop display**), the service's own timing block, and both the
monotonic and the wall clock, so a system sleep during a turn is visible rather than
mistaken for a stall. The bench waits for the typed prime before the first prompt, so
cold readiness (model load or server start, prime) is separated from warm response timing;
the run script records the cold figures from the service log.
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8766"
HERE = Path(__file__).resolve().parent


def wait_for_prime(log: Path, deadline_s: float = 240.0) -> dict:
    """Block until the service's typed prime has a result, and return it."""
    started = time.monotonic()
    while time.monotonic() - started < deadline_s:
        for line in log.read_text(errors="replace").splitlines():
            if "typed prime:" in line:
                stamp = float(line.split(" ", 1)[0])
                body = json.loads(line.split("typed prime: ", 1)[1])
                return {"at": stamp, **body}
        time.sleep(0.5)
    raise SystemExit("the typed prime did not report within the deadline")


def answer_of(payload: dict) -> str | None:
    message = payload.get("val_message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    if payload.get("kind") == "truncated":
        return payload.get("partial_text")
    return None


def one(client: httpx.Client, prompt: dict) -> dict:
    body = {"content": prompt["message"], "no_project": True}
    sent_wall = time.time()
    sent = time.monotonic()
    first = None
    settled = None
    with client.stream("POST", f"{BASE}/turns/stream", json=body, timeout=900) as response:
        event = None
        for raw in response.iter_lines():
            if raw.startswith("event: "):
                event = raw[7:].strip()
            elif raw.startswith("data: "):
                if event == "delta" and first is None:
                    first = time.monotonic()
                elif event == "settled":
                    settled = json.loads(raw[6:])
                elif event in ("error", "refused"):
                    settled = {"kind": event, **json.loads(raw[6:])}
    done = time.monotonic()
    done_wall = time.time()
    payload = settled or {}
    text = answer_of(payload)
    row = {
        "id": prompt["id"],
        "kind": prompt["kind"],
        "sent_at_utc": datetime.fromtimestamp(sent_wall, UTC).isoformat(timespec="seconds"),
        "first_visible_s": round(first - sent, 3) if first else None,
        "complete_s": round(done - sent, 3),
        "complete_wall_s": round(done_wall - sent_wall, 3),
        "sleep_suspected": abs((done_wall - sent_wall) - (done - sent)) > 5.0,
        "outcome": payload.get("kind"),
        "answer": text,
        "answer_chars": len(text) if text else None,
        "timing": payload.get("timing"),
        "error": payload.get("detail") or payload.get("error"),
    }
    return row


def main() -> int:
    model, label, order, out, log = (
        sys.argv[1],
        sys.argv[2],
        sys.argv[3],
        Path(sys.argv[4]),
        Path(sys.argv[5]),
    )
    prompts = json.loads((HERE / "prompts.json").read_text())["prompts"]
    if order == "reverse":
        prompts = list(reversed(prompts))
    client = httpx.Client()
    prime = wait_for_prime(log)
    print(json.dumps({"prime": prime}), flush=True)
    rows = []
    for prompt in prompts:
        row = one(client, prompt)
        rows.append(row)
        shown = {k: v for k, v in row.items() if k not in ("answer",)}
        print(json.dumps(shown), flush=True)
        time.sleep(3)
    slugs = sorted(
        set(re.findall(r"unmetered local route ([a-z0-9-]+):", log.read_text(errors="replace")))
    )
    out.write_text(
        json.dumps(
            {
                "model": model,
                "label": label,
                "order": order,
                "prime": prime,
                "routes_seen": slugs,
                "rows": rows,
            },
            indent=1,
        )
        + "\n"
    )
    print(json.dumps({"routes_seen": slugs}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
