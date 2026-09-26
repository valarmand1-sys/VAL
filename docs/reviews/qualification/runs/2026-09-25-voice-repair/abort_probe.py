"""Does an aborted request free LM Studio for his next one? — Voice-mode repair §6.

A prime refresh that finds its cache entry evicted costs a full persona prefill
(6.7-6.9 s measured). If he speaks while it runs, his request waits behind it on the
sequential (parallel 1) instance. Before choosing a policy this measures, on the
installed engine, what his request actually waits:

- `alone`: a small request with nothing ahead of it;
- `behind`: the same request sent 2 s into an uncached ~5,000-token prefill left to run;
- `aborted`: the same, the prefill's connection closed just before his request is sent.

The long prompt is the persona file with a random first line, so it never matches a
cached entry. One generated token each; nothing is stored. The token is read from the
service's launchd definition and never printed. $0 (local).

Usage: abort_probe.py OUT.json [REPEATS]
"""

from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
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

LONG = """
import json, sys, httpx
url, token, body = sys.argv[1], sys.argv[2], sys.stdin.read()
with httpx.stream("POST", url, headers={"Authorization": "Bearer " + token,
                  "Content-Type": "application/json"}, content=body, timeout=120) as r:
    for _ in r.iter_lines():
        pass
"""


def long_body() -> str:
    return json.dumps({
        "model": MODEL,
        "stream": True,
        "max_tokens": 1,
        "messages": [
            {"role": "system", "content": f"{uuid.uuid4()}\n{PERSONA}"},
            {"role": "user", "content": "ok"},
        ],
    })


def small() -> float:
    """Seconds to the first streamed chunk of a short request."""
    started = time.monotonic()
    with httpx.stream(
        "POST", URL, headers={"Authorization": f"Bearer {TOKEN}"}, timeout=120,
        json={"model": MODEL, "stream": True, "max_tokens": 1,
              "messages": [{"role": "user", "content": "Say one word."}]},
    ) as response:
        for line in response.iter_lines():
            if line.startswith("data:"):
                return round(time.monotonic() - started, 3)
    return round(time.monotonic() - started, 3)


def start_long() -> subprocess.Popen[bytes]:
    process = subprocess.Popen(  # noqa: S603 - this interpreter, a fixed script
        [sys.executable, "-c", LONG, URL, TOKEN],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    assert process.stdin is not None
    process.stdin.write(long_body().encode())
    process.stdin.close()
    return process


def long_alone() -> float:
    started = time.monotonic()
    start_long().wait()
    return round(time.monotonic() - started, 3)


out = Path(sys.argv[1])
repeats = int(sys.argv[2]) if len(sys.argv) > 2 else 3
small()  # the model answers at all
rows: dict[str, list[float]] = {"alone": [], "long_alone": [], "behind": [], "aborted": [],
                                "long_after_abort_exit": []}
for _ in range(repeats):
    rows["alone"].append(small())
    rows["long_alone"].append(long_alone())
    process = start_long()
    time.sleep(2.0)
    rows["behind"].append(small())
    process.wait()
    process = start_long()
    time.sleep(2.0)
    process.kill()
    process.wait()
    rows["aborted"].append(small())
    time.sleep(8.0)  # let anything still running finish before the next repeat
out.write_text(json.dumps({"model": MODEL, "repeats": repeats, "seconds_to_first_chunk": rows,
                           "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, indent=1) + "\n")
print(json.dumps(rows))
