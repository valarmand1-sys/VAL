"""Control for the Voice memory question — 3 October 2026.

The same Voice transition the integrated bench makes (a typed turn, Voice opened and made
ready, closed, a typed turn), driven against whichever configuration the service runs:
with `VAL_TYPED_MODEL` unset this is production's own configuration (GPT-OSS typed,
released for regular Gemma during Voice). Run under the same one-second memory sampler, it
says whether the Voice warm-up's dip belongs to Voice on this machine today or to the
candidate.

Usage: voice_control.py OUT.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8766"
client = httpx.Client()
T0 = time.monotonic()
EVENTS: list[dict] = []


def note(kind: str, **facts: object) -> None:
    row = {
        "at_s": round(time.monotonic() - T0, 1),
        "epoch": round(time.time(), 1),
        "kind": kind,
        **facts,
    }
    EVENTS.append(row)
    print(json.dumps(row), flush=True)


def turn(text: str, conversation: str | None) -> str | None:
    body: dict[str, object] = {"content": text}
    body.update({"conversation_id": conversation} if conversation else {"no_project": True})
    sent = time.monotonic()
    reply = client.post(f"{BASE}/turns", json=body, timeout=900).json()
    note("typed", kind_of=reply.get("kind"), seconds=round(time.monotonic() - sent, 1))
    return (reply.get("conversation") or {}).get("id")


conversation = turn("Suggest a name for a small secondhand bookshop.", None)
time.sleep(3)
opened = client.post(
    f"{BASE}/voice/sessions",
    json={"no_project": True, "conversation_id": conversation},
    timeout=180,
)
session = opened.json()["session"]
note("voice_on")
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
note("voice_ready", seconds=round(time.monotonic() - began, 1))
time.sleep(5)
client.post(f"{BASE}/voice/sessions/{session}/close", timeout=60)
note("voice_off")
time.sleep(1)
turn("And why that one?", conversation)
Path(sys.argv[1]).write_text(json.dumps({"events": EVENTS}, indent=1) + "\n")
