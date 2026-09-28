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

v2.3 (same day, integrated run C1): with divergence checkpoints a turn is served from a
longer entry, so the persona checkpoint beneath it was never renewed and aged out;
`persona_survives` shows it evicted under the earlier hook and kept under v2.3, which
renews every stored prefix of the entry used, shortest last.

Usage (engine interpreter, site-packages on PYTHONPATH):
  python3.11 -B hook_regression.py hook_v2_reconstructed.py <the repository's hook>

`hook_v2_reconstructed.py` is the frozen candidate's hook (a5d9680) with the one-line
copy undone — v2's renewal exactly, since v2 itself was replaced in place when installed.
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


def persona_survives(hook_path: str) -> dict:
    """v2.3: turns served from longer entries must keep the persona checkpoint alive.

    One persona checkpoint, then a conversation whose every turn reuses the previous
    turn's longer checkpoint (never the persona entry itself) and stores two more
    entries, as the engine does — past the store's capacity several times over.
    """
    spec = importlib.util.spec_from_file_location("hook_under_test", hook_path)
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    hook._renewal_on = lambda: True
    hook._divergence_on = lambda: True
    history = LRUPromptCache(max_size=6)
    hook._install_on(history)
    persona = list(range(100, 140))
    history.insert_cache("session", persona, [Fake()], cache_type="user")
    conversation = list(persona)
    for turn in range(12):
        conversation += [1000 + 10 * turn + i for i in range(5)]
        history.fetch_nearest_cache("session", list(conversation) + [7, 8])
        history.insert_cache("session", list(conversation), [Fake()], cache_type="user")
        history.insert_cache("session", list(conversation) + [7, 8, 9], [Fake()], cache_type="assistant")
    kept = history._trie.search("session", persona).exact is not None
    return {"persona_checkpoint_kept": kept, "consistent": consistent(history)}


print(json.dumps({"v2": run(sys.argv[1]), "v2.1+": run(sys.argv[2]),
                  "persona_survives": {"before (argv 1)": persona_survives(sys.argv[1]),
                                       "v2.3 (argv 2)": persona_survives(sys.argv[2])}}, indent=1))
