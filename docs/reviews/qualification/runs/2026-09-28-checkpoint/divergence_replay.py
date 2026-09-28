"""The divergence checkpoint, replayed on the engine's own store — 28 September 2026, §2 and §3.

Drives the vendored `mlx_lm.models.cache.LRUPromptCache` (import only; the engine's Python
3.11, `-B`, its site-packages on PYTHONPATH) through a replica of `CacheWrapper`'s rules —
flush the previous live cache as a snapshot, restore the longest stored prefix (retrying an
untrimmable exact hit one token short), store one checkpoint at `total - tail`, keep
prompt + generated as the live cache — with the hook's own `choose_boundary` deciding the
tail when the divergence checkpoint is on. Token bookkeeping only; no model.

Three request layouts, each a Voice conversation of turns with the refresh of both
persona entries between them and a correction of his third message part-way through:

- `as_is`: persona, history, then one user message of the state block and his words;
- `envelope_in_system`: persona and the whole state block, then history, then his words;
- `split_state`: persona and the steady state, then history, then his words and this
  turn's state.

Reports, per turn, the tokens reused, and checks that every persona checkpoint stays
exactly where the primes put it.

    PYTHONPATH=<engine site-packages> <engine>/bin/python3.11 -B divergence_replay.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import importlib.util  # noqa: E402

# The repository's hook, by path: the engine's own interpreter has already imported the
# *installed* one through its `.pth` line, so a plain import would test that instead.
_spec = importlib.util.spec_from_file_location(
    "val_cache_renewal_repo",
    Path(__file__).resolve().parents[5] / "infrastructure/lmstudio/cache_renewal/val_cache_renewal.py",
)
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)
assert hook.VERSION == "2", "the replay tests the version being proposed"

from mlx_lm.models.cache import LRUPromptCache  # noqa: E402

TAIL = 11
PERSONA = list(range(5000))
MEDIUM, LOW = [1], [2]
SEP = [3] * 40
STEADY = [4] * 700  # the state that holds steady (split layout)
TURN_STATE = 60  # this turn's state: counts, clock (split) — or the whole block's change


class Entry:
    nbytes = 1

    def is_trimmable(self) -> bool:
        return False


class Engine:
    def __init__(self, divergence: bool) -> None:
        hook._renewal_on = lambda: True
        self.history = LRUPromptCache(max_size=10)
        hook._install_on(self.history)
        self.divergence = divergence
        self.live: list[int] | None = None
        self.checkpoints: list[int] = []

    def _restore(self, prompt: list[int]) -> int:
        cache, rest = self.history.fetch_nearest_cache("m", prompt)
        if cache is not None and len(rest) > 0:
            return len(prompt) - len(rest)
        shorter = prompt[:-1]
        cache, rest = self.history.fetch_nearest_cache("m", shorter)
        return 0 if cache is None else len(shorter) - len(rest)

    def request(self, prompt: list[int], generated: list[int]) -> tuple[int, int | None]:
        tail = TAIL
        if self.divergence:
            decision = hook.choose_boundary(self.history, "m", prompt, self.live)
            if decision.get("boundary") is not None:
                tail = len(prompt) - decision["boundary"]
        if self.live:
            self.history.insert_cache("m", list(self.live), [Entry()], cache_type="assistant")
        cached = self._restore(prompt)
        checkpoint = len(prompt) - tail
        stored = None
        if checkpoint > cached and checkpoint > 0:
            self.history.insert_cache("m", prompt[:checkpoint], [Entry()], cache_type="user")
            stored = checkpoint
        self.live = prompt + generated[:-1]
        return cached, stored


def words(k: int, corrected: bool = False) -> list[int]:
    return [10_000 + k * 7 + (3 if corrected else 0)] * 15


def answer(k: int) -> list[int]:
    return [20_000 + k] * 250  # the final channel, as history renders it


def turn_state(k: int) -> list[int]:
    return [30_000 + k] * TURN_STATE


def history(k: int, corrected_at: int | None) -> list[int]:
    out: list[int] = []
    for j in range(k):
        out += [5] + words(j, corrected=corrected_at is not None and j == corrected_at) + [6] + answer(j) + [7]
    return out


def prompt(layout: str, k: int, corrected_at: int | None) -> list[int]:
    h = history(k, corrected_at)
    tail = [8, 9, 9, 9]  # <|end|><|start|>assistant...
    if layout == "as_is":
        return MEDIUM + PERSONA + SEP[:1] + h + [5] + STEADY + turn_state(k) + words(k) + tail
    if layout == "envelope_in_system":
        return MEDIUM + PERSONA + SEP + STEADY[:340] + turn_state(k) + STEADY[340:] + h + [5] + words(k) + tail
    return MEDIUM + PERSONA + SEP + STEADY + h + [5] + words(k) + turn_state(k) + tail


def prime(header: list[int], layout: str) -> list[int]:
    boundary = header + PERSONA + (SEP if layout != "as_is" else SEP[:1])
    return boundary + [99] * TAIL


def run(layout: str, divergence: bool, turns: int = 14, correct_at: int = 3) -> dict:
    engine = Engine(divergence)
    for header in (LOW, MEDIUM):
        engine.request(prime(header, layout), [0])
    persona_keys = {tuple(prime(h, layout)[:-TAIL]) for h in (LOW, MEDIUM)}
    reused: list[int] = []
    corrected_at = None
    for k in range(turns):
        if k == correct_at + 2:
            corrected_at = correct_at  # he corrects an earlier message: history changes
        cached, _ = engine.request(prompt(layout, k, corrected_at), [0] * 400)
        reused.append(cached)
        for header in (LOW, MEDIUM):
            engine.request(prime(header, layout), [0])
    keys = {tuple(key) for _, key in engine.history._lru._lrus["user"]}
    return {
        "reused_per_turn": reused,
        "persona_checkpoints_intact": persona_keys <= keys,
        "entries": len(engine.history),
    }


out = {}
for layout in ("as_is", "envelope_in_system", "split_state"):
    for divergence in (False, True):
        result = run(layout, divergence)
        out[f"{layout} divergence={'on' if divergence else 'off'}"] = result
        print(f"{layout:19s} divergence={'on ' if divergence else 'off'} intact={result['persona_checkpoints_intact']} "
              f"reused={result['reused_per_turn']}")
Path(sys.argv[1] if len(sys.argv) > 1 else "divergence-replay.json").write_text(json.dumps(out, indent=1) + "\n")
