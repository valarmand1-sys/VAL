"""Is a reused checkpoint the state a full prefill would have produced? — 28 Sept 2026, §3.

Greedy text is not a valid test on this runtime: even the qualified persona reuse path
differs from an uncached run (cached-vs-uncached.json), because splitting the prefill at a
different place changes the floating-point summation order. The check is therefore made
inside the model, with the engine's own code (its vendored mlx and mlx_lm, the same model
files as the experiment instance), on the exact rendered token ids Core sent in stage C
(render_targets.py, lengths equal to the engine's own). For each request the logits at every prompt position after the
latest boundary compared (his words, the per-turn state, the generation prompt — at most
the last 768) are computed five ways, and compared position by position with `full`
(mean and largest KL divergence, argmax agreement, largest logit difference). The
first-output position alone is not a test: after the generation prompt the next token is
all but certain, so even a wrong state agrees there.

- `full`: the whole prompt prefilled in 2,048-token chunks from an empty cache;
- `persona`: prefill stopped at the MEDIUM prime's checkpoint (5,107 tokens in stage C), the cache deep-copied (as the engine
  stores and restores a snapshot) and the rest prefilled from the copy — the route's own
  qualified reuse path, the control for numerical noise;
- `divergence`: the same at the divergence boundary the engine reused in stage C;
- `divergence_no_copy`: the same split without the copy — must equal `divergence` exactly,
  or copying itself altered state;
- `full_chunk_1024` (the noise floor with no cache at all): the whole prompt again from
  an empty cache, in 1,024-token chunks — how far two uncached runs differ when only the
  summation order moves;
- `wrong_prefix` (negative control): the checkpoint of a *different* request at the same
  length, continued with this request's tokens — what reusing a state under the wrong key
  would give; the test must be able to see it.

Run with the engine's interpreter and site-packages, the experiment instance unloaded:
  PYTHONPATH=<engine site-packages> python3.11 -B numerical_check.py targets.json OUT.json
"""

from __future__ import annotations

import copy
import json
import sys
import time
from pathlib import Path

import mlx.core as mx
from mlx_lm import load
from mlx_lm.models.cache import make_prompt_cache

MODEL = Path.home() / ".lmstudio/models/val-experiment/gpt-oss-20b-MXFP4-Q8-renewal"
CHUNK = 2048

targets = json.loads(Path(sys.argv[1]).read_text())
model, _ = load(str(MODEL))


def prefill(cache, tokens: list[int], offset: int, keep_from: int, chunk: int = CHUNK) -> list[mx.array]:
    """Prefill in the engine's chunks; the logits of absolute positions >= keep_from."""
    kept = []
    for start in range(0, len(tokens), chunk):
        logits = model(mx.array(tokens[start : start + chunk])[None], cache=cache)[0]
        first = max(0, keep_from - offset - start)
        if first < logits.shape[0]:
            kept.append(logits[first:].astype(mx.float32))
        mx.eval([entry.state for entry in cache] + kept[-1:])
    return kept


def run(ids: list[int], boundary: int, keep_from: int, *, prefix: list[int] | None = None,
        deep: bool = True) -> mx.array:
    cache = make_prompt_cache(model)
    if boundary:
        prefill(cache, (prefix or ids)[:boundary], 0, len(ids))
        if deep:
            cache = copy.deepcopy(cache)
    return mx.concatenate(prefill(cache, ids[boundary:], boundary, keep_from))


def compare(a: mx.array, b: mx.array) -> dict:
    la, lb = a - mx.logsumexp(a, axis=-1, keepdims=True), b - mx.logsumexp(b, axis=-1, keepdims=True)
    kl = mx.sum(mx.exp(la) * (la - lb), axis=-1)
    agree = mx.argmax(a, axis=-1) == mx.argmax(b, axis=-1)
    return {
        "positions": a.shape[0],
        "mean_kl": float(f"{mx.mean(kl).item():.3e}"),
        "max_kl": float(f"{mx.max(kl).item():.3e}"),
        "argmax_agreement": round(mx.mean(agree.astype(mx.float32)).item(), 4),
        "max_abs_logit_difference": round(mx.max(mx.abs(a - b)).item(), 4),
    }


def common(a: list[int], b: list[int]) -> int:
    return next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))


persona = 5107
rows = []
for number, target in enumerate(targets):
    ids = target["ids"]
    boundary = target["engine_cached"]
    other = next(
        (u["ids"] for u in targets if u is not target and len(u["ids"]) > boundary
         and common(u["ids"], ids) < boundary),
        None,
    )
    keep_from = max(persona, boundary, len(ids) - 768)
    began = time.time()
    full = run(ids, 0, keep_from)
    runs = {
        "persona": run(ids, persona, keep_from),
        "divergence": run(ids, boundary, keep_from),
        "divergence_no_copy": run(ids, boundary, keep_from, deep=False),
        "full_chunk_1024": mx.concatenate(prefill(make_prompt_cache(model), ids, 0, keep_from, 1024)),
    }
    if other is not None:
        runs["wrong_prefix"] = run(ids, boundary, keep_from, prefix=other)
    row = {
        "index": target["index"],
        "words": target["words"],
        "tokens": len(ids),
        "persona_boundary": persona,
        "divergence_boundary": boundary,
        "against_full": {name: compare(full, logits) for name, logits in runs.items()},
        "divergence_copy_vs_no_copy_identical": bool(
            mx.array_equal(runs["divergence"], runs["divergence_no_copy"]).item()
        ),
        "seconds": round(time.time() - began, 1),
        "peak_memory_gb": round(mx.get_peak_memory() / 1e9, 2),
    }
    rows.append(row)
    print(json.dumps(row), flush=True)
Path(sys.argv[2]).write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
