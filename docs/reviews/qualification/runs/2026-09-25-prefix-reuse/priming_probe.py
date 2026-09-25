"""Information only: would a persona-boundary checkpoint be reused? (Not deployable here.)

Same isolation as `mechanism_check.py`: LM Studio's installed engine in a separate
process, sequential mode. The engine stores a checkpoint 11 tokens before the end of
each prompt and reuses a stored entry only when it is an exact prefix of a new prompt.
A priming prompt whose checkpoint lands exactly on the stable boundary — the system
block and the opening of the next user message — would put such an entry in place.
This measures whether later changed-suffix requests then reuse it. It is a VAL-side
behaviour change (an extra inference request, and parallel 1), not a serving control,
and relies on an engine-internal constant; it is measured to inform a later ruling.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import mechanism_check as base
from mlx_engine.generate import create_generator, load_model

kit = load_model(base.MODEL, max_kv_size=base.CONTEXT, max_seq_nums=1)
tok = kit.tokenizer


def tokens_of(messages: list[dict]) -> list[int]:
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                   reasoning_effort="medium")
    return list(kit.tokenize(text))


a1, b1 = tokens_of(base.A1), tokens_of(base.B1)
boundary = base.common_prefix(a1, b1)
# Back off to the start of the first user message: the stable, content-free boundary.
stable = max(i for i in range(boundary) if tok.decode(a1[i:i + 1]) == "<|start|>")
priming = a1[:stable] + a1[stable:stable + 3] + [a1[stable + 3]] * 11
rows = []
for label, prompt in [("priming", priming), ("B1 changed suffix", b1),
                      ("C1 changed suffix", tokens_of(base.C1)), ("A2 next turn", tokens_of(base.A2))]:
    before = len(base.lookups)
    started = time.monotonic()
    first = None
    for result in create_generator(kit, prompt, max_tokens=16, temp=0.0):
        if first is None and result.tokens:
            first = time.monotonic() - started
    used = base.lookups[before:]
    rows.append({"request": label, "prompt_tokens": len(prompt),
                 "engine_took_from_cache": max((u["from_cache"] for u in used), default=0),
                 "first_token_s": round(first or -1, 3)})
    print(rows[-1], flush=True)
Path(sys.argv[2]).write_text(json.dumps({"stable_boundary_tokens": stable, "rows": rows}, indent=1))
