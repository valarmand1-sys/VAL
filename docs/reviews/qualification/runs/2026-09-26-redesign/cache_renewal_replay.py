"""The engine's prompt-store rules replayed with and without recency renewal (27 Sep 2026).

Drives the vendored `mlx_lm.models.cache.LRUPromptCache` itself (import only; run with the
engine's Python 3.11, `-B`, its site-packages on PYTHONPATH) through a replica of
`CacheWrapper`'s insert, flush and restore rules, with `val_cache_renewal`'s own wrapper
installed on the history object. Token bookkeeping only; no model is loaded.
LATENCY_CANDIDATE.md §1.

    PYTHONPATH=<engine site-packages> <engine>/bin/python3.11 -B cache_renewal_replay.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[5] / "infrastructure/lmstudio/cache_renewal")
)

import val_cache_renewal as hook
from mlx_lm.models.cache import LRUPromptCache

#: A persona checkpoint counts as warm when the whole system block and header are reused.
BOUNDARY_TOKENS = 5048
PERSONA = list(range(5000))
LOW_HEADER, MEDIUM_HEADER = [1], [2]  # "Reasoning: low|medium" renders before the persona


class Entry:
    """A cache entry as the store sees it: one byte, untrimmable like GPT-OSS's."""

    nbytes = 1

    def is_trimmable(self) -> bool:
        return False


class Engine:
    """`CacheWrapper.update_cache`, `_flush_live_cache` and `_restore_cache`, tokens only."""

    def __init__(self, renewal: bool) -> None:
        hook._renewal_on = lambda: renewal
        self.history = LRUPromptCache(max_size=10)
        hook._install_on(self.history)
        self.live: list[int] | None = None

    def _restore(self, prompt: list[int]) -> int:
        cache, rest = self.history.fetch_nearest_cache("m", prompt)
        if cache is not None and len(rest) > 0:
            return len(prompt) - len(rest)
        if len(prompt) <= 1:
            return 0
        # An exact hit on an untrimmable cache is retried one token short, as the engine does.
        shorter = prompt[:-1]
        cache, rest = self.history.fetch_nearest_cache("m", shorter)
        return 0 if cache is None else len(shorter) - len(rest)

    def request(self, prompt: list[int], generated: list[int]) -> int:
        if self.live:
            self.history.insert_cache("m", list(self.live), [Entry()], cache_type="assistant")
        cached = self._restore(prompt)
        checkpoint = len(prompt) - 11
        if checkpoint > cached and checkpoint > 0:
            self.history.insert_cache("m", prompt[:checkpoint], [Entry()], cache_type="user")
        # The live cache holds the prompt and all but the last generated token.
        self.live = prompt + generated[:-1] if generated else prompt
        return cached


def boundary(header: list[int]) -> list[int]:
    return header + PERSONA + [3] * 47


def prime_prompt(header: list[int]) -> list[int]:
    return boundary(header) + [9] * 11


def verdict(cached: int) -> str:
    return "warm" if cached >= BOUNDARY_TOKENS else f"COLD({cached})"


def run(renewal: bool, pattern: str, turns: int = 16) -> list[tuple[str, str, str]]:
    engine = Engine(renewal)
    out = []
    for header in (LOW_HEADER, MEDIUM_HEADER):
        engine.request(prime_prompt(header), [0])
    for t in range(turns):
        header = LOW_HEADER if (pattern == "alternate" and t % 2 == 0) else MEDIUM_HEADER
        hit = engine.request(boundary(header) + [1000 + t] * 900, [5] * 300)
        low = engine.request(prime_prompt(LOW_HEADER), [0])
        medium = engine.request(prime_prompt(MEDIUM_HEADER), [0])
        out.append((verdict(hit), verdict(low), verdict(medium)))
    return out


for pattern in ("alternate", "medium-only"):
    for renewal in (False, True):
        log = run(renewal, pattern)
        cold = sum(1 for row in log for x in row if x != "warm")
        label = "renewal" if renewal else "as shipped"
        print(f"{pattern:11s} {label:10s} cold={cold}", log[:8])
