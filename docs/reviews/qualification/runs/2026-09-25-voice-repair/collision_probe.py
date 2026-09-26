"""His turn arriving during a full re-prime — Voice-mode repair §6, measured, not assumed.

The installed engine (`mlx_engine` @34, `mlx_lm.LRUPromptCache(max_size=10)`) orders
its snapshots by insertion only; a read does not renew one, and a prime that hits
its checkpoint stores nothing. So the persona checkpoint ages out after about five
later conversation checkpoints whatever the refresh does, and the next refresh then
pays the full persona prefill (6.7-6.9 s measured). Cancelling it does not free the
runtime (`abort_probe.py`). The question is what his turn waits if he speaks during it.

Each trial uses a persona the runtime has never seen (a random first line), i.e. the
evicted state, and the same message shapes VAL sends: a prime (persona + eight
filler words, checkpoint on the boundary) and his turn (persona + a new question).

- `no_refresh`: his turn with the persona evicted and nothing running;
- `behind_refresh_at_T`: the prime sent T seconds before his turn;
- `held`: his turn after the prime has finished (the healthy case).

The figure is seconds from his request to the runtime's first streamed output. $0.

Usage: collision_probe.py OUT.json [REPEATS]
"""

from __future__ import annotations

import json
import plistlib
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
URL = "http://127.0.0.1:1234/v1/chat/completions"
MODEL = "openai/gpt-oss-20b"
with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    TOKEN = plistlib.load(handle)["EnvironmentVariables"]["VAL_LMSTUDIO_API_TOKEN"]
PERSONA = (ROOT / "docs/baselines/03-persona.md").read_text()
FILLER = " ".join(["ok"] * 8)
QUESTIONS = ["How do I sound to you?", "What should we look at this evening?",
             "Is the house quiet tonight?", "Tell me something about the garden."]


def first_output(system: str, user: str) -> float:
    started = time.monotonic()
    with httpx.stream(
        "POST", URL, headers={"Authorization": f"Bearer {TOKEN}"}, timeout=180,
        json={"model": MODEL, "stream": True, "max_tokens": 1,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": user}]},
    ) as response:
        for line in response.iter_lines():
            if line.startswith("data:"):
                return round(time.monotonic() - started, 3)
    return round(time.monotonic() - started, 3)


def fresh() -> str:
    return f"{uuid.uuid4()}\n{PERSONA}"


out = Path(sys.argv[1])
repeats = int(sys.argv[2]) if len(sys.argv) > 2 else 3
rows: dict[str, list[float]] = {}


def record(name: str, value: float) -> None:
    rows.setdefault(name, []).append(value)
    print(name, value, flush=True)


first_output("", "Say one word.")
for repeat in range(repeats):
    question = QUESTIONS[repeat % len(QUESTIONS)]
    record("prime_alone_evicted", first_output(fresh(), FILLER))
    record("no_refresh", first_output(fresh(), question))
    persona = fresh()
    first_output(persona, FILLER)
    record("held", first_output(persona, question))
    for lead in (0.5, 2.0, 4.0, 6.0):
        persona = fresh()
        prime = threading.Thread(target=first_output, args=(persona, FILLER))
        prime.start()
        time.sleep(lead)
        record(f"behind_refresh_at_{lead}", first_output(persona, question))
        prime.join()
out.write_text(json.dumps({"model": MODEL, "repeats": repeats,
                           "seconds_from_his_request_to_first_output": rows,
                           "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, indent=1) + "\n")
