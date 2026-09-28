"""The renewal hook's exact-hit aliasing defect, reproduced and closed — 28 Sept 2026.

On an exact hit `PromptTrie.search` returns the very list the engine passed to
`fetch_nearest_cache`; `CacheWrapper._restore_cache` keeps that list as `_live_tokens`
and appends each generated token to it. Hook v2 pushed that list into the LRU queue, so
the queued key grew while the trie's did not, and a later eviction raised KeyError inside
`insert_cache` (four Tier-1 requests lost in time-of-day-clock.json; server log
2026-09-28.1.log, 12:18:14–12:19:54). v2.1 queues a copy.

The engine's own `LRUPromptCache` (its vendored mlx_lm) runs the engine's sequence —
flush the previous request, fetch (exact, then the one-shorter retry), keep the fetched
list as the live tokens and append to it, insert until eviction — under each hook
version, checking after every step that the queue and the trie hold the same keys.

Usage (engine interpreter, site-packages on PYTHONPATH):
  python3.11 -B hook_regression.py <hook v2 path> <hook v2.1 path>
"""

from __future__ import annotations

import importlib.util
import json
import sys

from mlx_lm.models.cache import LRUPromptCache


class Fake:
    """A cache layer the engine cannot trim (GPT-OSS's are not), 1 byte in size."""

    nbytes = 1
    offset = 0

    def is_trimmable(self) -> bool:
        return False


def keys_in_trie(history: LRUPromptCache) -> set[tuple]:
    found, stack = set(), [((), history._trie._trie.get("session", {}))]
    while stack:
        path, node = stack.pop()
        for token, child in node.items():
            if token == "__value__":
                found.add(path)
            else:
                stack.append((path + (token,), child))
    return found


def consistent(history: LRUPromptCache) -> bool:
    queued = [tuple(tokens) for lru in history._lru._lrus.values() for _, tokens in lru]
    return len(queued) == len(set(queued)) and set(queued) == keys_in_trie(history)


def run(hook_path: str) -> dict:
    spec = importlib.util.spec_from_file_location("hook_under_test", hook_path)
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    hook._renewal_on = lambda: True
    history = LRUPromptCache(max_size=4)
    hook._install_on(history)
    persona = list(range(100, 140))
    history.insert_cache("session", persona[:30], [Fake()], cache_type="user")
    steps = []
    try:
        for turn in range(8):
            prompt = persona + [900 + turn % 2]  # two prompts, each sent again and again
            if turn < 2:  # a one-token prime of each first: its flush stores the whole prompt
                history.insert_cache("session", list(prompt), [Fake()], cache_type="assistant")
            live = list(prompt)
            cache, rest = history.fetch_nearest_cache("session", live)  # the engine's first fetch
            if cache is not None and not rest:
                history.fetch_nearest_cache("session", live[:-1])  # the exact-hit retry
            live.extend([200005, 200006 + turn])  # generation appends to the same list
            # The next request's flush: the live cache holds every token but the last
            # generated one (never fed back), stored under `live[:cache_length]`.
            history.insert_cache("session", list(live[:-1]), [Fake()], cache_type="assistant")
            steps.append(consistent(history))
        return {"completed": True, "consistent_after_every_step": all(steps), "steps": steps}
    except KeyError as error:
        return {"completed": False, "error": f"KeyError: {error}", "steps": steps}


print(json.dumps({"v2": run(sys.argv[1]), "v2.1": run(sys.argv[2])}, indent=1))
