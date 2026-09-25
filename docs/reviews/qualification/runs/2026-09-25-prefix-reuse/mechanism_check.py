"""Supported-mechanism check for prompt-prefix reuse, on the INSTALLED engine, isolated.

Prompt-reuse pass, 25 September 2026, §4, §5, §8, §11, §13.

**Isolation by construction.** This runs LM Studio's own installed MLX engine —
`mlx_engine` from `app-mlx-generate-mac14-arm64@34`, the package the running
`mlx-llm-mac-arm64-apple-metal-advsimd@1.11.0` backend loads, under LM Studio's own
vendored CPython 3.11 — in a **separate process** with its own copy of the admitted
model and its own cache. It never talks to the LM Studio server, so it cannot load,
unload, evict, reconfigure or share state with production's instance. Nothing in the
engine is modified: its cache lookup is *wrapped* to record what it returned.

**What it measures, per request:** the token count; the longest leading token
sequence it shares with any earlier request in the same engine (CLAIM A — identity);
the number of prompt tokens the engine actually took from its cache (CLAIM B — use,
read from the engine's own lookup result); and the time to the first generated token.

The requests follow Core's ruled order — persona (system) → history → record-state
envelope → current turn — using the **active production persona text** (read-only
from the live store) and the model's own chat template at MEDIUM reasoning. They are
scratch fixtures: no production prompt, record or persona is changed. Only the first
16 generated tokens are drawn, and none is printed, stored or compared.

Usage (LM Studio's vendored interpreter):
    PYTHONPATH=<site-packages> python3.11 mechanism_check.py PERSONA.txt OUT.json
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

from mlx_engine.generate import create_generator, load_model
from mlx_lm.models import cache as mlx_cache

MODEL = Path.home() / ".lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8"
CONTEXT = 32_768
persona = Path(sys.argv[1]).read_text().strip()
OUT = Path(sys.argv[2])

logging.basicConfig(level=logging.WARNING)

# --- observe the engine's own cache lookups, without changing them ------------------
lookups: list[dict] = []
_fetch = mlx_cache.LRUPromptCache.fetch_nearest_cache


def observed_fetch(self, model, tokens):  # noqa: ANN001, ANN202
    cache, rest = _fetch(self, model, tokens)
    lookups.append({"prompt_tokens": len(tokens), "from_cache": len(tokens) - len(rest)
                    if cache is not None else 0})
    return cache, rest


mlx_cache.LRUPromptCache.fetch_nearest_cache = observed_fetch


def envelope(conversation: str, prior: int, minute: str) -> str:
    """The record-state envelope's shape, as Core serialises it (scratch values)."""
    return "Prior record state:\n" + json.dumps(
        {
            "current_time": {"local": f"Friday 25 September 2026, {minute}",
                             "timezone": "CDT (UTC-0500)"},
            "same_conversation_history": {"state": "available" if prior else "zero",
                                          "prior_messages": prior},
            "retrieved_excerpts": {"state": "not_run", "count": 0},
            "external_egress": {"state": "local_only", "reasons": ["conversation_sealed"],
                                "conversation": conversation},
        },
        indent=1,
    )


def request(system: str, history: list[tuple[str, str]], env: str, owner: str) -> list[dict]:
    messages = [{"role": "system", "content": system}]
    messages += [{"role": role, "content": text} for role, text in history]
    # Consecutive user messages are joined with one blank line (local wire rule).
    messages.append({"role": "user", "content": f"{env}\n\n{owner}"})
    return messages


A1 = request(persona, [], envelope("A", 0, "09:18"), "Good evening, Val.")
B1 = request(persona, [], envelope("B", 0, "09:19"), "What should we look at this morning?")
A2 = request(
    persona,
    [("user", "Good evening, Val."), ("assistant", "Good evening, my lord.")],
    envelope("A", 2, "09:20"),
    "Tell me what is on the calendar.",
)
C1 = request(persona, [], envelope("C", 0, "09:21"), "Is the house quiet tonight?")
PERSONA_MUTATED = persona.replace("Val", "Vel", 1)  # one-word change inside the prefix
M1 = request(PERSONA_MUTATED, [], envelope("D", 0, "09:22"), "Is the house quiet tonight?")
SEQUENCE = [
    ("A1 first request (establishes cache)", A1),
    ("B1 different conversation, same persona, changed suffix", B1),
    ("A2 same conversation, next turn", A2),
    ("C1 another new conversation, changed suffix", C1),
    ("M1 persona mutated by one word", M1),
    ("A2 again, fully identical (diagnostic only)", A2),
]


def common_prefix(a: list[int], b: list[int]) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def run(mode: str, max_seq_nums: int) -> dict:
    lookups.clear()
    loaded_at = time.monotonic()
    kit = load_model(MODEL, max_kv_size=CONTEXT, max_seq_nums=max_seq_nums)
    load_s = round(time.monotonic() - loaded_at, 3)
    tokenizer = kit.tokenizer
    seen: list[list[int]] = []
    rows = []
    for label, messages in SEQUENCE:
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, reasoning_effort="medium"
        )
        tokens = list(kit.tokenize(text))
        shared = max((common_prefix(tokens, earlier) for earlier in seen), default=0)
        before = len(lookups)
        started = time.monotonic()
        first = None
        count = 0
        for result in create_generator(kit, tokens, max_tokens=16, temp=0.0):
            if first is None and result.tokens:
                first = time.monotonic() - started
            count += len(result.tokens)
        total = time.monotonic() - started
        used = lookups[before:]
        rows.append({
            "request": label,
            "prompt_tokens": len(tokens),
            "claim_A_longest_shared_leading_tokens_with_any_earlier": shared,
            "claim_B_engine_took_from_cache": used[-1]["from_cache"] if used else None,
            "engine_lookups": used,
            "first_token_s": None if first is None else round(first, 3),
            "request_s": round(total, 3),
            "generated_tokens": count,
        })
        seen.append(tokens)
        print(mode, rows[-1]["request"], rows[-1]["prompt_tokens"],
              rows[-1]["claim_A_longest_shared_leading_tokens_with_any_earlier"],
              rows[-1]["claim_B_engine_took_from_cache"], rows[-1]["first_token_s"], flush=True)
    kind = type(kit).__name__
    del kit
    return {"mode": mode, "max_seq_nums": max_seq_nums, "model_kit": kind,
            "load_s": load_s, "requests": rows}


if __name__ == "__main__":
    import mlx_engine

    report = {
        "engine_package": str(Path(mlx_engine.__file__).parent),
        "model": str(MODEL),
        "context": CONTEXT,
        "runs": [run("batched (production: parallel 4)", 4), run("sequential (parallel 1)", 1)],
    }
    OUT.write_text(json.dumps(report, indent=1) + "\n")
