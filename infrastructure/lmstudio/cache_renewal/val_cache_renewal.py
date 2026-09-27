"""Recency on hit for the MLX engine's prompt-cache history — owner order of 27 September 2026.

**What it corrects.** LM Studio's MLX engine (`mlx-llm-mac-arm64-apple-metal-advsimd@1.11.0`,
vendored `app-mlx-generate-mac14-arm64@34`) keeps prompt checkpoints in
`mlx_lm.models.cache.LRUPromptCache(max_size=10)` through `mlx_engine.cache_wrapper.CacheWrapper`.
Only `insert_cache` moves an entry to the back of its queue; `fetch_nearest_cache` reads
without renewing. The "LRU" is therefore first-in-first-out per cache type, so Val's two
static persona checkpoints — inserted once, used on every turn — are always the oldest
checkpoints and are evicted after about four turns, and a ~7 s cold prime follows
(`docs/reviews/qualification/runs/2026-09-26-redesign/ORDINARY_TURN.md` §12).

**The change, and nothing else.** After `fetch_nearest_cache` returns an entry, that
entry is moved to the back of its own queue, exactly as `insert_cache` would move a
re-inserted key. Capacity (10 entries), cache types, the eviction order between types,
exact-prefix matching, what is stored and when: all unchanged. No content is added, kept
longer than the store's own rules keep it, or read by anything but the engine.

**Where it applies.** Only to model instances loaded from a directory listed in
`~/.lmstudio/val-cache-renewal.json` (`{"model_paths": [...], "renewal": true}`); every
other instance — production's included — runs the engine exactly as shipped, and the
hook logs that it declined. `"renewal": false` turns the behaviour off per call without a
reload, for A/B measurement. Any failure inside the hook leaves the engine unchanged.

Installed and removed by `install.py` beside this file, which refuses an engine whose
files do not match the digests this was written against.
"""

from __future__ import annotations

import importlib.abc
import importlib.util
import json
import os
import sys
import time

VERSION = "1"
ALLOWLIST = os.path.expanduser("~/.lmstudio/val-cache-renewal.json")
LOG = os.path.expanduser("~/.lmstudio/val-cache-renewal.log")
TARGET = "mlx_engine.model_kit.model_kit"

_allowlist_cache: tuple[float, dict] = (-1.0, {})


def _log(message: str) -> None:
    try:
        with open(LOG, "a") as handle:
            handle.write(
                f"{time.strftime('%Y-%m-%dT%H:%M:%S')} pid={os.getpid()} v{VERSION} {message}\n"
            )
    except OSError:
        pass


def _allowlist() -> dict:
    global _allowlist_cache
    try:
        mtime = os.stat(ALLOWLIST).st_mtime
    except OSError:
        return {}
    if mtime != _allowlist_cache[0]:
        try:
            with open(ALLOWLIST) as handle:
                _allowlist_cache = (mtime, json.load(handle))
        # Two clauses, not a tuple: the formatter's py314 target would unparenthesise a
        # tuple, and this module runs inside the engine's Python 3.11.
        except OSError:
            _allowlist_cache = (mtime, {})
        except ValueError:
            _allowlist_cache = (mtime, {})
    return _allowlist_cache[1]


def _listed(model_path: str) -> bool:
    wanted = {os.path.realpath(p) for p in _allowlist().get("model_paths", [])}
    return os.path.realpath(model_path) in wanted


def _renewal_on() -> bool:
    return bool(_allowlist().get("renewal", False))


def _install_on(history: object) -> None:
    """Wrap one instance's `fetch_nearest_cache` so the entry it returns is renewed."""
    from mlx_lm.models.cache import can_trim_prompt_cache

    original = history.fetch_nearest_cache
    counts = {"hits": 0, "renewed": 0}

    def fetch_nearest_cache(model, tokens):  # noqa: ANN001, ANN202 - the engine's own signature
        cache, rest = original(model, tokens)
        if cache is None or not _renewal_on():
            return cache, rest
        try:
            result = history._trie.search(model, tokens)
            key = None
            if result.exact is not None:
                key = result.exact
            else:
                short_length = len(result.shorter) if result.shorter is not None else 0
                longer_entry = (
                    history._trie.get(result.model, result.longer)
                    if result.longer is not None and result.common_prefix > short_length
                    else None
                )
                if longer_entry is not None and can_trim_prompt_cache(longer_entry.prompt_cache):
                    key = result.longer
                elif short_length > 0:
                    key = result.shorter
            counts["hits"] += 1
            if key is not None:
                entry = history._trie.get(model, key)
                history._lru.remove(model, key)
                history._lru.push(model, key, entry.cache_type)
                counts["renewed"] += 1
        except Exception as error:
            _log(f"renewal skipped: {type(error).__name__}: {error}")
        return cache, rest

    history.fetch_nearest_cache = fetch_nearest_cache
    history._val_renewal_counts = counts


def _patch(module: object) -> None:
    model_kit = module.ModelKit
    original = model_kit._full_model_init

    def _full_model_init(self, model_path, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        original(self, model_path, *args, **kwargs)
        try:
            if _listed(str(model_path)):
                _install_on(self.cache_wrapper._history)
                _log(f"renewal on hit installed for {model_path}")
            else:
                _log(f"declined (not allowlisted): {model_path}")
        except Exception as error:
            _log(f"install failed, engine unchanged: {type(error).__name__}: {error}")

    model_kit._full_model_init = _full_model_init


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None) -> object:  # noqa: ANN001
        if name != TARGET:
            return None
        sys.meta_path.remove(self)
        try:
            spec = importlib.util.find_spec(name)
        finally:
            sys.meta_path.insert(0, self)
        if spec is None or spec.loader is None:
            return None
        exec_module = spec.loader.exec_module

        def patched_exec(module):  # noqa: ANN001, ANN202
            exec_module(module)
            try:
                _patch(module)
            except Exception as error:
                _log(f"patch failed, engine unchanged: {type(error).__name__}: {error}")

        spec.loader.exec_module = patched_exec  # type: ignore[method-assign]
        return spec


def activate() -> None:
    if not any(isinstance(finder, _Finder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _Finder())
        _log("hook active in this interpreter")
