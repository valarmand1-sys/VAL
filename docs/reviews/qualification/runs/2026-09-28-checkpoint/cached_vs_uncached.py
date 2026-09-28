"""Cached against uncached execution of identical rendered requests — 28 Sept 2026, §3.

A cache hit must leave the model exactly where a full prefill would. This runtime returns
no log-probabilities, so this first check is the complete greedy output (temperature 0, a fixed
seed, the same output allowance): the hidden reasoning and the visible answer, compared
character for character, for the same exact request body sent three ways, each from a
freshly reloaded experiment instance (an empty cache):

- `uncached`: the request alone — every token prefilled;
- `persona`: after the route's own prime — the persona checkpoint reused, the path already
  qualified in production's design, as the control for numerical noise;
- `divergence`: after the two preceding turns of the same conversation — the divergence
  checkpoint reused (the engine's own line must show reuse beyond the persona).

The request bodies are the stage-C run's own (`stage-C.json`, captured from the adapter's
`_request`), so the rendered input is the one Core actually sent. Local, $0.

Finding: greedy text is NOT a valid correctness test here — the persona control, the
path production already relies on, differs from the uncached run too, because moving the
split point changes the floating-point summation order. The decisive check is
numerical_check.py (logits over every post-boundary position, with a no-cache noise
floor and a wrong-prefix negative control); this file records why it was needed.

Usage: cached_vs_uncached.py stage-C.json OUT.json
"""

from __future__ import annotations

import glob
import json
import plistlib
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

SOURCE, OUT = Path(sys.argv[1]), Path(sys.argv[2])
EXPERIMENT = "val-exp-gpt-oss-20b"
LMS = str(Path.home() / ".lmstudio/bin/lms")
TOKEN = plistlib.loads((Path.home() / "Library/LaunchAgents/house.armand.val.api.plist").read_bytes())[
    "EnvironmentVariables"
]["VAL_LMSTUDIO_API_TOKEN"]
bodies = [b["body"] for b in json.loads(SOURCE.read_text())["bodies"]]
medium = [b for b in bodies if b.get("max_tokens") == 6144 and b.get("reasoning_effort") == "medium"]
prime = next(b for b in bodies if b.get("max_tokens") == 1 and b.get("reasoning_effort") == "medium")


def reload() -> None:
    subprocess.run([LMS, "unload", EXPERIMENT], capture_output=True)
    subprocess.run([LMS, "load", "gpt-oss-20b-renewal", "--identifier", EXPERIMENT, "-c", "32768",
                    "--parallel", "1", "-y"], capture_output=True, check=True)


def send(body: dict, max_tokens: int) -> dict:
    request = dict(body, max_tokens=max_tokens, temperature=0, seed=7, stream=False)
    began = time.time()
    reply = httpx.post("http://127.0.0.1:1234/v1/chat/completions",
                       headers={"Authorization": f"Bearer {TOKEN}"}, json=request, timeout=600).json()
    message = reply["choices"][0]["message"]
    return {"reasoning": message.get("reasoning") or "", "content": message.get("content") or "",
            "prompt_tokens": reply.get("usage", {}).get("prompt_tokens"), "began": began}


def cached_tokens(prompt_tokens: int, after: float) -> int | None:
    for path in sorted(glob.glob(str(Path.home() / ".lmstudio/server-logs/2026-09/2026-09-2*.log")))[-1:]:
        # Forward from this request's own start: the first matching line after it is its
        # own (searching backwards returned a later run's line — corrected 28 September).
        for line in open(path, errors="replace").read().splitlines():
            hit = re.search(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\].*Prompt cache: using (\d+)/(\d+) tokens", line)
            if hit and int(hit.group(3)) == prompt_tokens:
                at = time.mktime(time.strptime(hit.group(1), "%Y-%m-%d %H:%M:%S"))
                if at >= after - 2:
                    return int(hit.group(2))
    return None


def first_difference(a: str, b: str) -> int | None:
    if a == b:
        return None
    return next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))


results = []
for target in (2, 3, 5, 6):
    body = medium[target]
    runs = {}
    reload()
    runs["uncached"] = send(body, 160)
    reload()
    send(prime, 1)
    runs["persona"] = send(body, 160)
    reload()
    send(medium[target - 2], 4)
    send(medium[target - 1], 4)
    runs["divergence"] = send(body, 160)
    for name, run in runs.items():
        run["cached"] = cached_tokens(run["prompt_tokens"], run["began"])
    text = {name: run["reasoning"] + "\n---\n" + run["content"] for name, run in runs.items()}
    row = {
        "target": target,
        "words": body["messages"][-1]["content"][:60],
        "prompt_tokens": runs["uncached"]["prompt_tokens"],
        "cached": {name: run["cached"] for name, run in runs.items()},
        "persona_equals_uncached": text["persona"] == text["uncached"],
        "divergence_equals_uncached": text["divergence"] == text["uncached"],
        "first_difference": {
            "persona": first_difference(text["persona"], text["uncached"]),
            "divergence": first_difference(text["divergence"], text["uncached"]),
        },
        "output_characters": len(text["uncached"]),
        "outputs": text,
    }
    results.append(row)
    print(json.dumps({k: row[k] for k in ("target", "words", "prompt_tokens", "cached", "persona_equals_uncached",
                                          "divergence_equals_uncached", "first_difference", "output_characters")}))
OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n")
