"""Evict the persona checkpoints from the runtime's prompt cache — six unrelated prompts.

The engine keeps ten entries, two per distinct request, never renewed on a hit
(`TIER1_RELEASE.md` §8, `ORDINARY_TURN.md` §5); six distinct short prompts push both
persona checkpoints out, so the next turn prefills cold (~7 s). Local, $0, one token each.
"""

from __future__ import annotations

import os
import plistlib
from pathlib import Path

import httpx

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    env = plistlib.load(handle)["EnvironmentVariables"]
base = env.get("VAL_LMSTUDIO_BASE_URL", os.environ.get("VAL_LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1"))
client = httpx.Client(base_url=base, timeout=120.0, headers={"Authorization": f"Bearer {env['VAL_LMSTUDIO_API_TOKEN']}"})
for i in range(6):
    words = " ".join(f"unrelated prompt {i} token {j}" for j in range(40))
    r = client.post("/chat/completions", json={"model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": words}], "max_tokens": 1, "stream": False})
    print(i, r.status_code, (r.json().get("usage") or {}).get("prompt_tokens"))
