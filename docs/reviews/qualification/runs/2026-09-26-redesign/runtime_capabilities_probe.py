"""Two runtime questions for Milestone B, answered by observation — 26 September 2026.

§7: does the installed runtime support generation-free prefill? A chat completion with
`max_tokens: 0`, and with 1, against the loaded GPT-OSS instance: what it returns, what
`usage` says, and how long it takes (a 5k-token cold prompt makes prefill visible).
§8: does closing a streaming connection stop generation at the engine? A long answer is
requested as a stream and the connection is closed after ~1.5 s of tokens; a tiny
request follows at once, and its latency says whether the engine was still busy with
the abandoned one. Local, $0. Usage: runtime_capabilities_probe.py OUT.json
"""

from __future__ import annotations

import json
import os
import plistlib
import sys
import time
from pathlib import Path

import httpx

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    for name, value in plistlib.load(handle)["EnvironmentVariables"].items():
        os.environ.setdefault(name, value)
BASE = os.environ.get("VAL_LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
client = httpx.Client(base_url=BASE, timeout=180.0,
                      headers={"Authorization": f"Bearer {os.environ['VAL_LMSTUDIO_API_TOKEN']}"})
MODEL = "openai/gpt-oss-20b"
out: dict[str, object] = {}

# A distinct ~5k-token system prompt so the prefill is real and not a cache hit.
filler = " ".join(f"Item {i}: the ledger of the eastern granary for the month, recorded in full." for i in range(420))
sys_prompt = "You are a careful archivist. " + filler

def timed(body: dict) -> dict:
    t = time.monotonic()
    r = client.post("/chat/completions", json=body)
    elapsed = round(time.monotonic() - t, 3)
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text[:300]}
    return {"status": r.status_code, "seconds": elapsed, "usage": j.get("usage"), "finish": (j.get("choices") or [{}])[0].get("finish_reason"),
            "content_len": len(((j.get("choices") or [{}])[0].get("message") or {}).get("content") or ""), "error": j.get("error")}

# §7 — max_tokens 0 (cold prompt), then max_tokens 1 (now-warm prompt), then max_tokens 0 again
msgs = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": "Acknowledge."}]
out["max_tokens_0_cold"] = timed({"model": MODEL, "messages": msgs, "max_tokens": 0, "stream": False})
out["max_tokens_1_after"] = timed({"model": MODEL, "messages": msgs, "max_tokens": 1, "stream": False})
out["max_tokens_0_warm"] = timed({"model": MODEL, "messages": msgs, "max_tokens": 0, "stream": False})
print(json.dumps({k: v for k, v in out.items()}, indent=0))

# §8 — abandon a stream mid-generation, then measure a tiny request
long_msgs = [{"role": "user", "content": "Write a 600-word essay on the history of granaries, with no headings."}]
t = time.monotonic(); tokens_seen = 0
with client.stream("POST", "/chat/completions", json={"model": MODEL, "messages": long_msgs, "max_tokens": 900, "stream": True}) as r:
    for line in r.iter_lines():
        if line.startswith("data:") and "content" in line:
            tokens_seen += 1
        if time.monotonic() - t > 1.5:
            break
abandoned_at = round(time.monotonic() - t, 3)
t2 = time.monotonic()
tiny = timed({"model": MODEL, "messages": [{"role": "user", "content": "Say yes."}], "max_tokens": 4, "stream": False})
out["abandon_stream"] = {"chunks_before_close": tokens_seen, "closed_after_s": abandoned_at, "tiny_request_after_close": tiny}
# control: the same tiny request when nothing was abandoned
time.sleep(20)  # let any abandoned generation finish (900 tokens ≈ 15 s)
out["tiny_request_control"] = timed({"model": MODEL, "messages": [{"role": "user", "content": "Say yes."}], "max_tokens": 4, "stream": False})
print(json.dumps({k: out[k] for k in ("abandon_stream", "tiny_request_control")}, indent=0))
Path(sys.argv[1]).write_text(json.dumps(out, indent=1) + "\n")
