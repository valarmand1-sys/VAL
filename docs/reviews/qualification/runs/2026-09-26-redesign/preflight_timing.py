"""Where the light route's exact preflight spends its time — 26 September 2026.

The pilot's timelines put 2.7-3.2 s between `exact_preflight_start` and
`exact_preflight_end` on the Qwen3-4B route against 33 ms on GPT-OSS for the same
persona. This times each read-only inspector call separately, on each loaded handle,
with the active persona as the system prompt and one short user turn. Nothing is
generated, nothing is loaded; the service environment is read from launchd and not
printed. Run on an otherwise idle LM Studio.

Usage: preflight_timing.py [repeats]
"""

from __future__ import annotations

import json
import os
import plistlib
import statistics
import sys
import time
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    for name, value in plistlib.load(handle)["EnvironmentVariables"].items():
        os.environ.setdefault(name, value)

import lmstudio  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from val_providers.lmstudio_inspector import INGRESS_RENDER_OPTIONS, inspector_host_of  # noqa: E402

repeats = int(sys.argv[1]) if len(sys.argv) > 1 else 5
engine = create_engine(os.environ["VAL_DATABASE_URL"].replace("postgresql://", "postgresql+psycopg://"))
with engine.connect() as connection:
    persona = connection.execute(
        text("select content from personas where is_active order by activated_at desc limit 1")
    ).scalar_one()
engine.dispose()

host = inspector_host_of(os.environ.get("VAL_LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1"))
client = lmstudio.Client(host, api_token=os.environ["VAL_LMSTUDIO_API_TOKEN"])
handles = {str(h.get_info().identifier): h for h in client.llm.list_loaded()}
print("loaded:", sorted(handles))


def timed(label: str, fn, repeats: int = repeats):  # noqa: ANN001, ANN201
    samples = []
    result = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = fn()
        samples.append((time.perf_counter() - started) * 1000)
    print(f"  {label:34s} median {statistics.median(samples):8.1f} ms  max {max(samples):8.1f} ms")
    return result


for identifier, handle in sorted(handles.items()):
    print(identifier)
    chat = lmstudio.Chat()
    chat.add_system_prompt(persona)
    chat.add_user_message("Good evening, Val.")
    timed("list_loaded", lambda: list(client.llm.list_loaded()))
    timed("get_info", handle.get_info)
    timed("get_context_length", handle.get_context_length)
    rendered = timed(
        "apply_prompt_template(persona)",
        lambda: handle.apply_prompt_template(chat, dict(INGRESS_RENDER_OPTIONS)),
    )
    print(f"  rendered chars {len(rendered)}")
    timed("count_tokens(rendered)", lambda: handle.count_tokens(rendered))
    timed("tokenize(rendered)", lambda: handle.tokenize(rendered))
    short = lmstudio.Chat()
    short.add_user_message("Good evening, Val.")
    short_rendered = handle.apply_prompt_template(short, dict(INGRESS_RENDER_OPTIONS))
    timed("apply_prompt_template(short)", lambda: handle.apply_prompt_template(short, dict(INGRESS_RENDER_OPTIONS)))
    timed("count_tokens(short)", lambda: handle.count_tokens(short_rendered))
    timed("count_tokens(persona raw)", lambda: handle.count_tokens(persona))
client.close()
print(json.dumps({"persona_chars": len(persona)}))
