"""Exact rendered token ids of the stage-C requests used by the numerical check (§3).

Each request body the adapter sent is rendered by the loaded instance's own template and
tokenized by its own tokenizer (the exact preflight's path); the count must equal the
prompt length the engine logged for it in stage C, or the target is refused.

Usage: render_targets.py stage-C.json targets.json
"""

from __future__ import annotations

import json
import plistlib
import sys
from pathlib import Path

import lmstudio

from val_providers.lmstudio_inspector import INGRESS_RENDER_OPTIONS

stage = json.loads(Path(sys.argv[1]).read_text())
env = plistlib.loads((Path.home() / "Library/LaunchAgents/house.armand.val.api.plist").read_bytes())
model = lmstudio.Client("127.0.0.1:1234", api_token=env["EnvironmentVariables"]["VAL_LMSTUDIO_API_TOKEN"]).llm.model(
    "val-exp-gpt-oss-20b"
)
medium = [b["body"] for b in stage["bodies"] if b["body"].get("max_tokens") == 6144]
engine_counts = {r["tokens"]: r for r in stage["requests"]}
targets = []
for index in (2, 3, 5, 6, 7, 8):
    body = medium[index]
    chat = lmstudio.Chat()
    for turn in body["messages"]:
        {"system": chat.add_system_prompt, "user": chat.add_user_message,
         "assistant": chat.add_assistant_response}[turn["role"]](turn["content"])
    rendered = model.apply_prompt_template(chat, dict(INGRESS_RENDER_OPTIONS))
    ids = [int(t) for t in model.tokenize(rendered)]
    logged = engine_counts.get(len(ids))
    targets.append({"index": index, "words": body["messages"][-1]["content"][:50], "ids": ids,
                    "engine_cached": None if logged is None else logged["cached"],
                    "matches_engine_length": logged is not None})
    print(index, len(ids), "engine length match", logged is not None, "cached", None if logged is None else logged["cached"])
Path(sys.argv[2]).write_text(json.dumps(targets) + "\n")
