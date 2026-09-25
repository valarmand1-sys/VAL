"""Priming through LM Studio's own request path, on an ISOLATED instance.

Priming-cache pass, 25 September 2026, §4, §5, §6, §7, §8, §16, §17, §19, §22, §23.

Isolation: the admitted artifact cloned byte-for-byte (APFS clone, SHA-256 identical)
under a different LM Studio model key, `val-experiment/gpt-oss-20b`, loaded as
`val-exp`. Production resolves only `openai/gpt-oss-20b` — by identifier or model key
in its exact preflight, by key, path, identifier or id in its readiness check — and
names it in every request, so nothing of production can reach this instance and
nothing here can reach production.

Requests are built by VAL's own `LMStudioAdapter._request` (the canonical wire form,
MEDIUM) with only the model identifier pointed at the experiment. Token identity
(CLAIM A) is LM Studio's own template rendering and tokenizer via the SDK; cache use
(CLAIM B) is the engine's own "Prompt cache: using X/Y tokens" line in LM Studio's
server log. The service's environment is read from its launchd definition and never
printed. Scratch content only; nothing is stored.

Usage: lmstudio_probe.py PERSONA.txt OUT.json
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import sys
import time
from datetime import date
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    for name, value in plistlib.load(handle)["EnvironmentVariables"].items():
        os.environ.setdefault(name, value)

import lmstudio  # noqa: E402

from val_domain.gateway import Message  # noqa: E402
from val_domain.registry import by_slug  # noqa: E402
from val_providers.lmstudio_adapter import LMStudioAdapter, _chat_turns  # noqa: E402
from val_providers.lmstudio_inspector import INGRESS_RENDER_OPTIONS  # noqa: E402

IDENTIFIER = os.environ.get("VAL_PRIME_EXPERIMENT", "val-exp")
PERSONA = Path(sys.argv[1]).read_text().strip()
OUT = Path(sys.argv[2])
TOKEN = os.environ["VAL_LMSTUDIO_API_TOKEN"]
LOG = Path.home() / f".lmstudio/server-logs/{date.today():%Y-%m}/{date.today():%Y-%m-%d}.1.log"
CACHE_LINE = re.compile(r"Prompt cache: using (\d+)/(\d+) tokens")

config = by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio-partner").model_copy(update={"model_identifier": IDENTIFIER})
adapter = LMStudioAdapter(token=TOKEN, read_native_models=False)
sdk = lmstudio.Client("127.0.0.1:1234", api_token=TOKEN)
handle = next(h for h in sdk.llm.list_loaded() if h.get_info().identifier == IDENTIFIER)


def envelope(conversation: str, prior: int, minute: str, project: str | None) -> str:
    return "Prior record state:\n" + json.dumps(
        {"current_time": {"local": f"Friday 25 September 2026, {minute}",
                          "timezone": "CDT (UTC-0500)"},
         "same_conversation_history": {"state": "available" if prior else "zero",
                                       "prior_messages": prior},
         "project": project, "conversation": conversation,
         "external_egress": {"state": "local_only", "reasons": ["conversation_sealed"]}},
        indent=1)


def turn(env: str, owner: str, history: list[tuple[str, str]] = ()) -> tuple[Message, ...]:
    return (*(Message(role=r, content=t) for r, t in history),
            Message(role="user", content=env), Message(role="user", content=owner))


def tokens(messages: tuple[Message, ...], system: str) -> list[int]:
    chat = lmstudio.Chat()
    for item in _chat_turns(messages, system):
        {"system": chat.add_system_prompt, "user": chat.add_user_message,
         "assistant": chat.add_assistant_response}[item["role"]](item["content"])
    rendered = handle.apply_prompt_template(chat, dict(INGRESS_RENDER_OPTIONS))
    return list(handle.tokenize(rendered))


def log_offset() -> int:
    return LOG.stat().st_size if LOG.exists() else 0


def send(label: str, messages: tuple[Message, ...], system: str, max_tokens: int = 24) -> dict:
    kwargs = adapter._request(config, messages, system, max_tokens, None)
    start_at = log_offset()
    started = time.monotonic()
    first = None
    usage = None
    stream = adapter._client.chat.completions.create(
        stream=True, stream_options={"include_usage": True}, **kwargs)
    for chunk in stream:
        if first is None and chunk.choices:
            first = time.monotonic() - started
        if getattr(chunk, "usage", None) is not None:
            usage = chunk.usage
    total = time.monotonic() - started
    time.sleep(0.3)
    with LOG.open("rb") as fh:
        fh.seek(start_at)
        appended = fh.read().decode("utf-8", "replace")
    hits = CACHE_LINE.findall(appended)
    cached, of = (int(hits[-1][0]), int(hits[-1][1])) if hits else (None, None)
    details = getattr(usage, "prompt_tokens_details", None) if usage else None
    row = {"request": label, "engine_cached": cached, "engine_prompt_tokens": of,
           "usage_prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
           "usage_cached_tokens": getattr(details, "cached_tokens", None) if details else None,
           "first_output_s": None if first is None else round(first, 3),
           "request_s": round(total, 3), "max_tokens": max_tokens}
    print(json.dumps(row), flush=True)
    return row


def common(a: list[int], b: list[int]) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


# --- the stable boundary, from LM Studio's own rendering ---------------------------
R1 = turn(envelope("A", 0, "09:18", None), "Good evening, Val.")
R2 = turn(envelope("B", 0, "09:19", None), "What should we look at this morning?")
R3 = turn(envelope("C", 0, "09:21", "Project Alpha"), "Is the house quiet tonight?")
R4 = turn(envelope("A", 2, "09:20", None), "Tell me what is on the calendar.",
          [("user", "Good evening, Val."), ("assistant", "Good evening, my lord.")])
t1, t2 = tokens(R1, PERSONA), tokens(R2, PERSONA)
chat = lmstudio.Chat()
chat.add_system_prompt(PERSONA)
chat.add_user_message("\u0001")
rendered_probe = handle.apply_prompt_template(chat, dict(INGRESS_RENDER_OPTIONS))
boundary_text = rendered_probe[: rendered_probe.index("\u0001")]
S = len(list(handle.tokenize(boundary_text)))
assert t1[:S] == t2[:S], "the stable boundary is not token-identical across turns"
print("stable boundary S =", S, "| R1/R2 common prefix =", common(t1, t2), flush=True)


def prime_messages(n: int) -> tuple[Message, ...]:
    return (Message(role="user", content=" ".join(["ok"] * n)),)


# Calibrate: the prime's checkpoint (its length less 11) must land exactly on S, and
# its first S tokens must be the real turns' first S tokens.
calibrated = None
for n in range(1, 40):
    tp = tokens(prime_messages(n), PERSONA)
    if len(tp) - 11 == S and tp[:S] == t1[:S]:
        calibrated = n
        break
assert calibrated is not None, "no filler length puts the checkpoint on the boundary"
print("filler words:", calibrated, flush=True)

rows: list[dict] = []
report: dict = {"stable_boundary_tokens": S, "filler_words": calibrated,
                "prompt_tokens": {"R1": len(t1), "R2": len(t2)},
                "claim_A_common_prefix_R1_R2": common(t1, t2)}
rows.append(send("R1 unprimed (sequential control)", R1, PERSONA))
for max_tokens in (0, 1):
    try:
        rows.append(send(f"prime max_tokens={max_tokens}", prime_messages(calibrated), PERSONA,
                         max_tokens))
        report["minimum_prime_max_tokens"] = max_tokens
        break
    except Exception as failure:  # noqa: BLE001 - recorded, then the next size is tried
        rows.append({"request": f"prime max_tokens={max_tokens}", "refused": type(failure).__name__})
rows.append(send("R2 changed suffix, new conversation", R2, PERSONA))
rows.append(send("R3 changed suffix, other project", R3, PERSONA))
rows.append(send("R4 same conversation, next turn", R4, PERSONA))
rows.append(send("refresh (prime again, hot)", prime_messages(calibrated), PERSONA,
                 report.get("minimum_prime_max_tokens", 1)))
# Eviction: ordinary turns without refresh until the stable entry is gone.
for i in range(12):
    row = send(f"eviction probe turn {i + 1}",
               turn(envelope(f"E{i}", 0, f"10:{i:02d}", None), f"Question number {i + 7}?"),
               PERSONA)
    rows.append(row)
    if (row["engine_cached"] or 0) < S:
        report["stable_entry_evicted_after_ordinary_turns"] = i + 1
        break
# Mutations after a fresh prime.
rows.append(send("re-prime", prime_messages(calibrated), PERSONA,
                 report.get("minimum_prime_max_tokens", 1)))
mutated = PERSONA.replace("Val", "Vel", 1)
rows.append(send("persona changed by one word", turn(envelope("M", 0, "10:30", None),
                                                      "Is the house quiet tonight?"), mutated))
tm = tokens(turn(envelope("M", 0, "10:30", None), "x"), mutated)
report["claim_A_mutated_common_prefix_with_boundary"] = common(tm, t1[:S])
rows.append(send("ordinary request after mutation (prime still valid?)", R2, PERSONA))
report["rows"] = rows
OUT.write_text(json.dumps(report, indent=1) + "\n")
