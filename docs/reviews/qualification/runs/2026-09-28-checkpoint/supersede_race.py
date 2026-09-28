"""Does a superseded stream always end? — 28 Sept 2026, found in the integrated run (C1a).

In C1a an early-submitted turn was superseded by resumed speech 2 s after dispatch —
the moment the engine's 1.4 s prefill ended — and its thread never returned: no
"failed with superseded" record, still in flight four minutes later, although the
engine logged the client's disconnect. This probe drives the real adapter
(`LMStudioAdapter.stream(cancelled=...)`) against the experiment instance with a real
request (stage C's, its history made uncached by a marker so every trial prefills for
about 1–3 s) and supersedes it at a random moment spread across the prefill's end. A
stream that has not ended 20 s after the cancel is a hang; every thread's stack is then
dumped. Local, $0.

Usage: supersede_race.py stage-C.json OUT.json [TRIALS]
"""

from __future__ import annotations

import json
import plistlib
import random
import sys
import threading
import time
import traceback
from pathlib import Path

from val_domain.gateway import Message
from val_domain.registry import by_slug
from val_providers.lmstudio_adapter import LMStudioAdapter

SOURCE, OUT = Path(sys.argv[1]), Path(sys.argv[2])
TRIALS = int(sys.argv[3]) if len(sys.argv) > 3 else 30
TOKEN = plistlib.loads((Path.home() / "Library/LaunchAgents/house.armand.val.api.plist").read_bytes())[
    "EnvironmentVariables"
]["VAL_LMSTUDIO_API_TOKEN"]
body = [b["body"] for b in json.loads(SOURCE.read_text())["bodies"] if b["body"].get("max_tokens") == 6144][6]
system = body["messages"][0]["content"]
rest = [Message(role=m["role"], content=m["content"]) for m in body["messages"][1:]]
config = by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio-partner").model_copy(
    update={"model_identifier": "val-exp-gpt-oss-20b"}
)
adapter = LMStudioAdapter(token=TOKEN, read_native_models=False)
rng = random.Random(28)
rows = []
for trial in range(TRIALS):
    marker = f"[{trial}-{rng.random():.6f}] "
    messages = (Message(role=rest[0].role, content=marker + rest[0].content), *rest[1:])
    flag = threading.Event()
    outcome: dict = {}

    def consume() -> None:
        try:
            for _ in adapter.stream(config, messages, system, 256, cancelled=flag.is_set):
                pass
            outcome["end"] = "completed"
        except Exception as error:  # the supersession is an exception by design
            outcome["end"] = f"{type(error).__name__}: {str(error)[:60]}"
        outcome["at"] = time.monotonic()

    worker = threading.Thread(target=consume, daemon=True)
    dispatched = time.monotonic()
    worker.start()
    delay = rng.uniform(0.2, 3.5)
    time.sleep(delay)
    flag.set()
    cancelled_at = time.monotonic()
    worker.join(timeout=20)
    row = {"trial": trial, "cancel_after_s": round(delay, 3)}
    if worker.is_alive():
        row["hang"] = True
        frames = sys._current_frames()
        row["stacks"] = {
            thread.name: "".join(traceback.format_stack(frames[thread.ident]))[-2500:]
            for thread in threading.enumerate() if thread.ident in frames and thread is not threading.main_thread()
        }
    else:
        row["hang"] = False
        row["end"] = outcome.get("end")
        row["cancel_to_end_ms"] = round((outcome["at"] - cancelled_at) * 1000, 1)
    rows.append(row)
    print(json.dumps({k: v for k, v in row.items() if k != "stacks"}), flush=True)
    time.sleep(1.5)  # let the engine finish any prefill it could not abandon
OUT.write_text(json.dumps(rows, indent=1) + "\n")
print("hangs:", sum(r["hang"] for r in rows), "of", len(rows))
