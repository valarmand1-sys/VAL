"""The integrated service, exercised end to end in isolation — 3 October 2026.

The real application with `VAL_TYPED_MODEL` set (StyleTune V2 for ordinary typing, GPT-OSS
MEDIUM as the deliberate deep-reasoning route, regular Gemma for Voice), driven through
its own API on the scratch store. What is measured and checked:

  A  start → the typed model ready (loaded and its prefix prepared);
  B  ordinary typed turns once ready;
  C  a deliberate change to deep reasoning (prepared off any message), deep turns, and
     the deliberate change back;
  D  the same changes when he simply sends a message in the other mode: the wait is
     announced (`preparing_model`), the message is kept and answered once;
  E  Voice opened and closed, then a typed message sent at once, then another;
  F  a message cancelled while its model is being prepared;
  G  the same submission sent twice.

Onset is Send → first non-blank answer text at this harness (loopback; not the desktop).
Which model answered is read from the service's own log for each turn.

Usage: integrated_bench.py OUT.json SERVICE_LOG
"""

from __future__ import annotations

# ruff: noqa: S101
import json
import re
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8766"
OUT, LOG = Path(sys.argv[1]), Path(sys.argv[2])
client = httpx.Client()
T0 = time.monotonic()
EVENTS: list[dict] = []


def note(kind: str, **facts: object) -> dict:
    row = {"at_s": round(time.monotonic() - T0, 1), "kind": kind, **facts}
    EVENTS.append(row)
    print(json.dumps(row), flush=True)
    return row


def state() -> dict:
    return client.get(f"{BASE}/cognition", timeout=30).json()


def wait_ready(key: str, limit_s: float = 240.0) -> float:
    began = time.monotonic()
    while time.monotonic() - began < limit_s:
        if state().get(key):
            return round(time.monotonic() - began, 2)
        time.sleep(0.25)
    raise SystemExit(f"{key} did not become true within {limit_s} s: {state()}")


def routes_since(offset: int) -> tuple[list[str], int]:
    text = LOG.read_text(errors="replace")
    return re.findall(r"unmetered local route ([a-z0-9-]+):", text[offset:]), len(text)


def turn(
    label: str,
    text: str,
    conversation: str | None,
    *,
    deep: bool = False,
    request_id: str | None = None,
) -> dict:
    body: dict[str, object] = {
        "content": text,
        "progress": True,
        "deep_reasoning": deep,
        "request_id": request_id or uuid.uuid4().hex,
    }
    body.update({"conversation_id": conversation} if conversation else {"no_project": True})
    offset = len(LOG.read_text(errors="replace"))
    sent = time.monotonic()
    first, stages, settled = None, [], {}
    with client.stream("POST", f"{BASE}/turns/stream", json=body, timeout=900) as response:
        if response.status_code != 200:
            response.read()
            return note(label, status=response.status_code, detail=response.json().get("detail"))
        event = None
        for raw in response.iter_lines():
            if raw.startswith("event: "):
                event = raw[7:].strip()
            elif raw.startswith("data: "):
                data = json.loads(raw[6:])
                if event == "stage":
                    stages.append(data.get("stage"))
                elif event == "delta" and first is None and data.get("text", "").strip():
                    first = time.monotonic()
                elif event in ("settled", "error", "refused"):
                    settled = {"kind": event, **data} if event != "settled" else data
    done = time.monotonic()
    time.sleep(0.3)
    routes, _ = routes_since(offset)
    answer = (settled.get("val_message") or {}).get("content")
    return note(
        label,
        text=text,
        deep=deep,
        onset_s=round(first - sent, 2) if first else None,
        complete_s=round(done - sent, 2),
        outcome=settled.get("kind"),
        error_kind=settled.get("error_kind"),
        stages=stages,
        answered_by=[r for r in routes if "prime" not in r],
        answer_chars=len(answer) if answer else None,
        conversation_id=(settled.get("conversation") or {}).get("id"),
    )


def main() -> int:
    # A — start
    note("A_typed_ready_after_start", seconds=wait_ready("typed_ready"), state=state())

    # B — ordinary typing
    first = turn("B_ordinary_1", "Suggest a name for a small secondhand bookshop.", None)
    conversation = first["conversation_id"]
    turn("B_ordinary_2", "Why that one?", conversation)
    turn("B_ordinary_3", "Give me a title for a film about an orchard.", conversation)

    # C — deliberate change to deep reasoning and back
    began = time.monotonic()
    client.post(f"{BASE}/cognition/prepare", json={"deep": True}, timeout=30)
    note(
        "C_to_deep_prepared",
        seconds=wait_ready("deep_ready"),
        since_request_s=round(time.monotonic() - began, 2),
        state=state(),
    )
    deep = turn(
        "C_deep_1",
        "Reason step by step: is it cheaper to shoot three days on location or two days on a stage, if the stage costs twice as much per day? State what you would need to know.",
        None,
        deep=True,
    )
    turn(
        "C_deep_2",
        "Now assume the location needs a generator at a fixed cost. Does that change the answer?",
        deep["conversation_id"],
        deep=True,
    )
    began = time.monotonic()
    client.post(f"{BASE}/cognition/prepare", json={"deep": False}, timeout=30)
    note(
        "C_back_to_typed_prepared",
        seconds=wait_ready("typed_ready"),
        since_request_s=round(time.monotonic() - began, 2),
        state=state(),
    )
    turn(
        "C_ordinary_after_return",
        "Thank you. One more title for the orchard film, please.",
        conversation,
    )

    # D — the change made by a message itself
    turn(
        "D_deep_sent_while_typed_resident",
        "Reason carefully: what are the risks of shooting at night with one generator?",
        deep["conversation_id"],
        deep=True,
    )
    turn(
        "D_ordinary_sent_while_deep_resident",
        "And a short toast for the wrap dinner, please.",
        conversation,
    )
    turn("D_ordinary_next", "Shorter.", conversation)

    # E — Voice, then typing at once
    opened = client.post(
        f"{BASE}/voice/sessions",
        json={"no_project": True, "conversation_id": conversation},
        timeout=180,
    )
    session = opened.json()["session"]
    began = time.monotonic()
    for _ in range(600):
        if (
            client.get(f"{BASE}/voice/sessions/{session}", timeout=30)
            .json()
            .get("readiness", {})
            .get("ready")
        ):
            break
        time.sleep(0.5)
    note("E_voice_ready", seconds=round(time.monotonic() - began, 1), state=state())
    refused = turn("E_typed_during_voice", "A typed message while Voice is on.", conversation)
    assert refused.get("status") == 409, refused
    time.sleep(2)
    client.post(f"{BASE}/voice/sessions/{session}/close", timeout=60)
    closed = time.monotonic()
    time.sleep(0.5)
    turn(
        "E_first_typed_after_voice",
        "What should I say when I answer the phone at the studio?",
        conversation,
    )
    note(
        "E_typed_ready_after_voice",
        seconds_after_close=round(time.monotonic() - closed, 1),
        state=state(),
    )
    turn("E_second_typed_after_voice", "And if it is the composer calling?", conversation)

    # F — cancel while the model is being prepared
    client.post(f"{BASE}/cognition/prepare", json={"deep": True}, timeout=30)
    wait_ready("deep_ready")
    request_id = uuid.uuid4().hex
    result: list[dict] = []
    worker = threading.Thread(
        target=lambda: result.append(
            turn(
                "F_cancelled_during_changeover",
                "This message is cancelled while the text model loads.",
                conversation,
                request_id=request_id,
            )
        )
    )
    worker.start()
    time.sleep(2.0)
    cancelled = client.post(
        f"{BASE}/turns/cancel", json={"request_id": request_id}, timeout=30
    ).json()
    worker.join(timeout=300)
    detail = client.get(f"{BASE}/conversations/{conversation}", timeout=30).json()
    messages = detail.get("messages", [])
    note(
        "F_after_cancel",
        cancel=cancelled,
        last_message_role=messages[-1]["role"] if messages else None,
        last_message_kept=bool(messages)
        and messages[-1]["content"].startswith("This message is cancelled"),
        typed_ready_after_s=wait_ready("typed_ready"),
    )
    turn(
        "F_ordinary_after_cancel",
        "A plain question after the cancel: name one apple variety.",
        conversation,
    )

    # G — the same submission twice
    request_id = uuid.uuid4().hex
    both: list[dict] = []
    one = threading.Thread(
        target=lambda: both.append(
            turn("G_first", "Name a second apple variety.", conversation, request_id=request_id)
        )
    )
    one.start()
    time.sleep(0.4)
    both.append(
        turn("G_duplicate", "Name a second apple variety.", conversation, request_id=request_id)
    )
    one.join(timeout=300)
    detail = client.get(f"{BASE}/conversations/{conversation}", timeout=30).json()
    asked = [
        m
        for m in detail.get("messages", [])
        if m["role"] == "user" and m["content"] == "Name a second apple variety."
    ]
    note("G_submitted_once", user_messages_with_that_text=len(asked))

    OUT.write_text(json.dumps({"events": EVENTS, "final_state": state()}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
