"""Assistant-history seam diagnostic — owner ruling, 18 September 2026 (§5–§6).

One harmless synthetic fixture — system, user, assistant, user — with ordinary
visible assistant text and no reasoning, sent once through the real local
adapter (the same OpenAI-compatible path Val Core uses) with a tiny output
allowance, while LM Studio's own model-input log is captured. The SDK
inspector renders the identical canonical local sequence. The two renderings
are compared byte for byte to name the exact serialization difference. This
is serving-contract diagnostics only: not Stage A, not qualification, not
quality evidence. Provider/API spend $0.

Usage: diagnostic_assistant_seam.py OUT.json CANDIDATE_SLUG LOG_JSONL
(the log file is written by `lms log stream --source model --json`, started
by the caller before this script and stopped after it.)
"""

import difflib
import json
import os
import plistlib
import re
import sys
import time
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as f:
    env = plistlib.load(f)["EnvironmentVariables"]
os.environ["VAL_LMSTUDIO_API_TOKEN"] = env["VAL_LMSTUDIO_API_TOKEN"]

import lmstudio

from val_domain.gateway import Message
from val_domain.registry import by_slug
from val_gateway.startup import build_adapters
from val_providers.lmstudio_adapter import _chat_turns

OUT, SLUG, LOG = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
config = by_slug(SLUG)
assert config is not None
adapters, problems = build_adapters({"lmstudio"})
assert not problems, problems
adapter = adapters["lmstudio"]

SYSTEM = "You are a test fixture. Answer in one short sentence."
MESSAGES = (
    Message(role="user", content="Name one colour."),
    Message(role="assistant", content="Blue is a colour."),
    Message(role="user", content="Name another."),
)
turns = _chat_turns(MESSAGES, SYSTEM)

# A. the SDK authoritative rendering of the canonical sequence (read-only)
inst, handle = adapter._inspector.loaded_instance(config.model_identifier)
chat = lmstudio.Chat()
for t in turns:
    {"system": chat.add_system_prompt, "user": chat.add_user_message, "assistant": chat.add_assistant_response}[
        t["role"]
    ](t["content"])
sdk_rendered = handle.apply_prompt_template(chat)
sdk_count = handle.count_tokens(sdk_rendered)
feasibility = adapter.measure_context(config, MESSAGES, SYSTEM)
adapter._inspector.close()

# B. one real call through the adapter's chat-completions path, tiny output allowance
sent: dict[str, object] = {}
_real = adapter._client.chat.completions.create


def _observed(**kwargs):  # type: ignore[no-untyped-def]
    sent.update({k: v for k, v in kwargs.items() if k != "messages"})
    sent["messages"] = kwargs["messages"]
    return _real(**kwargs)


adapter._client.chat.completions.create = _observed  # type: ignore[method-assign]
result = adapter.complete(config, MESSAGES, SYSTEM, 16)
time.sleep(2)

# the server's own logged model input for that call
raw = LOG.read_text()
inputs = [json.loads('"' + m + '"') for m in re.findall(r'"type":"llm\.prediction\.input","input":"((?:[^"\\]|\\.)*)"', raw)]
server_input = inputs[-1] if inputs else None

report: dict[str, object] = {
    "fixture": {"system": SYSTEM, "messages": [m.model_dump() for m in MESSAGES]},
    "canonical_local_sequence": turns,
    "request_sent_messages": sent.get("messages"),
    "sdk_rendered": sdk_rendered,
    "sdk_count": sdk_count,
    "measure_context_prompt_tokens": feasibility.prompt_tokens,
    "server_usage_prompt_tokens": result.tokens_in,
    "server_logged_input": server_input,
    "server_logged_input_count_by_runtime_tokenizer": None,
    "difference_server_minus_sdk": (result.tokens_in or 0) - sdk_count,
}
if server_input is not None:
    inst, handle = adapter._inspector.loaded_instance(config.model_identifier)
    report["server_logged_input_count_by_runtime_tokenizer"] = handle.count_tokens(server_input)
    adapter._inspector.close()
    report["byte_equal"] = server_input == sdk_rendered
    report["unified_diff"] = "\n".join(
        difflib.unified_diff(sdk_rendered.splitlines(keepends=True), server_input.splitlines(keepends=True), "sdk", "server", lineterm="")
    )
    # the seam around the historical assistant turn
    a = "Blue is a colour."
    report["seam_sdk_repr"] = repr(sdk_rendered[sdk_rendered.find(a) - 12 : sdk_rendered.find(a) + len(a) + 24])
    report["seam_server_repr"] = repr(server_input[server_input.find(a) - 12 : server_input.find(a) + len(a) + 24])
OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
print(json.dumps({k: v for k, v in report.items() if k not in ("sdk_rendered", "server_logged_input", "unified_diff", "request_sent_messages")}, indent=1, ensure_ascii=False))
print("--- unified diff (sdk -> server)")
print(report.get("unified_diff"))
