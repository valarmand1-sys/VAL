"""Read-only observation of the settings LM Studio's MLX engine actually executes with.

Owner order of 29 September 2026: "Verify the actual execution configuration before
starting qualification. Do not repeat the earlier mistake of trusting accepted client
parameters alone." The engine logs none of its sampling settings, and a client parameter
the server accepts is not proof of what the sampler received.

**What it does, and nothing else.** It wraps `mlx_engine.generate._sequential_generation`,
the one entry point every sequential request passes through. It writes the arguments
that call received to a log, then runs the original generator unchanged:

- temperature, top-p, top-k, min-p, min-tokens-to-keep;
- repetition penalty and its context size;
- the output allowance and the seed;
- the number of stop strings, and whether a JSON schema was given;
- the prompt length;
- the model's key-value cache settings.

It changes no argument, no token and no cache. It reads no prompt text and writes none.

**Where it applies.** Only to models loaded from a directory listed in
`~/.lmstudio/val-runtime-observer.json` (`{"model_paths": [...]}`); every other model runs
the engine as shipped, and the observer logs once that it declined. Any failure inside it
leaves the request unchanged. Separate from the prompt-cache hook and from the retired
reasoning-budget hook: its own module, allowlist, log and install/remove.
"""

from __future__ import annotations

import importlib.abc
import importlib.util
import json
import os
import sys
import time

VERSION = "1.0"
ALLOWLIST = os.path.expanduser("~/.lmstudio/val-runtime-observer.json")
LOG = os.path.expanduser("~/.lmstudio/val-runtime-observer.log")
TARGET = "mlx_engine.generate"
FIELDS = (
    "temp",
    "top_p",
    "top_k",
    "min_p",
    "min_tokens_to_keep",
    "repetition_penalty",
    "repetition_context_size",
    "max_tokens",
    "seed",
    "speculative_decoding_toggle",
    "num_draft_tokens",
)
_declined: set[str] = set()


def _log(message: str) -> None:
    try:
        with open(LOG, "a") as handle:
            stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
            handle.write(f"{stamp} pid={os.getpid()} v{VERSION} {message}\n")
    except OSError:
        pass


def _listed(model_path: str) -> bool:
    try:
        with open(ALLOWLIST) as handle:
            paths = json.load(handle).get("model_paths", [])
    # Two clauses, not a tuple: the formatter's py314 target would unparenthesise a tuple,
    # and this module runs inside the engine's Python 3.11.
    except OSError:
        return False
    except ValueError:
        return False
    return os.path.realpath(model_path) in {os.path.realpath(p) for p in paths}


def observed(model_kit, prompt_tokens, kwargs: dict) -> dict:  # noqa: ANN001
    """The record for one request: the arguments as received, nothing derived."""
    record = {name: kwargs.get(name) for name in FIELDS}
    stops = kwargs.get("stop_strings") or []
    record["stop_strings"] = len(stops)
    record["json_schema"] = kwargs.get("json_schema") is not None
    record["prompt_tokens"] = len(prompt_tokens)
    for attr in ("max_kv_size", "kv_bits", "kv_group_size", "quantized_kv_start"):
        record[attr] = getattr(model_kit, attr, None)
    return record


def _patch(module) -> None:  # noqa: ANN001 - the engine module
    original = module._sequential_generation

    def _sequential_generation(model_kit, prompt_tokens, **kwargs):  # noqa: ANN001, ANN003, ANN202
        try:
            path = str(getattr(model_kit, "model_path", ""))
            if _listed(path):
                _log(f"request {json.dumps(observed(model_kit, prompt_tokens, kwargs))}")
            elif path not in _declined:
                _declined.add(path)
                _log(f"declined (not allowlisted): {path}")
        except Exception as error:
            _log(f"not observed, request unchanged: {type(error).__name__}: {error}")
        yield from original(model_kit, prompt_tokens, **kwargs)

    module._sequential_generation = _sequential_generation
    _log("observer installed in this interpreter")


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):  # noqa: ANN001, ANN202
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
