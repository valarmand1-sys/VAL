"""§8: does closing the connection during *prefill* release the engine? — 26 September 2026.

A fresh ~8k-token prompt (cold) is requested as a stream and the connection is closed
0.5 s in — during prefill, before any token; a tiny request follows at once. If prefill
ran on regardless, the tiny request waits ~10 s behind it. Local, $0.
"""
from __future__ import annotations
import json, os, plistlib, sys, time
from pathlib import Path
import httpx
with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    for name, value in plistlib.load(handle)["EnvironmentVariables"].items():
        os.environ.setdefault(name, value)
BASE = os.environ.get("VAL_LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
client = httpx.Client(base_url=BASE, timeout=180.0, headers={"Authorization": f"Bearer {os.environ['VAL_LMSTUDIO_API_TOKEN']}"})
MODEL = "openai/gpt-oss-20b"
filler = " ".join(f"Entry {i}: the western orchard's yield this season, weighed and noted by the steward." for i in range(430))
msgs = [{"role": "system", "content": "You are a careful archivist. " + filler}, {"role": "user", "content": "Acknowledge in one word."}]
t = time.monotonic(); got = 0
try:
    with client.stream("POST", "/chat/completions", json={"model": MODEL, "messages": msgs, "max_tokens": 50, "stream": True}, timeout=httpx.Timeout(180.0, read=0.5)) as r:
        for line in r.iter_lines():
            got += 1
except httpx.ReadTimeout:
    pass
closed_after = round(time.monotonic() - t, 3)
t2 = time.monotonic()
r2 = client.post("/chat/completions", json={"model": MODEL, "messages": [{"role": "user", "content": "Say yes."}], "max_tokens": 4, "stream": False})
tiny = round(time.monotonic() - t2, 3)
out = {"closed_after_s": closed_after, "chunks_before_close": got, "tiny_request_seconds": tiny, "tiny_status": r2.status_code}
print(json.dumps(out)); Path(sys.argv[1]).write_text(json.dumps(out, indent=1) + "\n")
