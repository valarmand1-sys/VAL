"""A bounded hidden-reasoning budget for GPT-OSS in LM Studio's MLX engine — isolated experiment.

Owner order of 29 September 2026 ("Authorize one isolated reasoning-budget experiment").
Separate from the prompt-cache hook (`val_cache_renewal`): its own module, its own
control file, its own log, its own install and removal.

**Why a custom mechanism.** No supported reasoning budget exists on this path: LM Studio's
`reasoning.budgetTokens` prediction setting is implemented for its llama.cpp engine, and
neither the MLX backend (`mlx-llm-mac-arm64-apple-metal-advsimd@1.11.0`) nor its Python
engine (`app-mlx-generate-mac14-arm64@34`) contains any budget code. A total-output limit
(`max_tokens`) would only truncate. This is the third thing: a protocol-correct transition.

**The mechanism.** GPT-OSS writes its hidden reasoning in the harmony `analysis` channel
and its answer in the `final` channel; the model itself moves from one to the other by
emitting `<|end|><|start|>assistant<|channel|>final<|message|>`. After the budget, a logits
processor (the engine's own extension point, the one its reasoning guards use) waits for
the reasoning to reach the end of a sentence, or the hard limit, and then makes exactly
that six-token transition the only admissible continuation, one token at a time. Nothing
else is altered: the answer that follows is sampled by the engine as shipped, and the
runtime's harmony parser sees the same token stream a natural transition produces.

- The processor does nothing and reads nothing until the budget is reached (it counts
  from the array's shape, so the engine's asynchronous pipeline is not synchronised).
- It does nothing if the reasoning has already ended, or if the output is not in the
  analysis channel.
- `<|end|>` is not a stop token for this model (generation config: 200002, 199999,
  200012), so the transition cannot end generation.

**Where it applies.** Only to models loaded from a directory listed in
`~/.lmstudio/val-reasoning-budget.json`, and only while that file sets `"enabled": true`
(`{"model_paths": [...], "enabled": true, "budget_tokens": N, "hard_tokens": M}`). The
file is read per request, so conditions can alternate call by call on one instance.
Every other model, production's included, runs the engine exactly as shipped. Any
failure inside the hook leaves that request unchanged. Each request's outcome is logged
with its prompt length, for attribution.
"""

from __future__ import annotations

import importlib.abc
import importlib.util
import json
import os
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

VERSION = "1.0"
CONTROL = os.path.expanduser("~/.lmstudio/val-reasoning-budget.json")
LOG = os.path.expanduser("~/.lmstudio/val-reasoning-budget.log")
TARGET = "mlx_engine.generate"

#: Harmony special tokens (o200k_harmony), checked against the tokenizer at use.
START, END, MESSAGE, CHANNEL = 200006, 200007, 200008, 200005
#: The model's own transition from reasoning to answer.
TRANSITION_TEXT = "<|end|><|start|>assistant<|channel|>final<|message|>"
ANALYSIS_TEXT = "analysis"

_control_cache: tuple[float, dict] = (-1.0, {})
_local = threading.local()
_sentence_ends: dict[int, frozenset[int]] = {}
_declined: set[str] = set()


def _log(message: str) -> None:
    try:
        with open(LOG, "a") as handle:
            stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
            handle.write(f"{stamp} pid={os.getpid()} v{VERSION} {message}\n")
    except OSError:
        pass


def _control() -> dict:
    global _control_cache
    try:
        mtime = os.stat(CONTROL).st_mtime_ns
    except OSError:
        return {}
    if mtime != _control_cache[0]:
        try:
            with open(CONTROL) as handle:
                _control_cache = (mtime, json.load(handle))
        except OSError:
            _control_cache = (mtime, {})
        except ValueError:
            _control_cache = (mtime, {})
    return _control_cache[1]


def _listed(model_path: str, control: dict) -> bool:
    wanted = {os.path.realpath(p) for p in control.get("model_paths", [])}
    return os.path.realpath(model_path) in wanted


class BudgetState:
    """The decision, on plain token lists: pure, so it is testable without the engine.

    `step(generated_count, read_generated)` is called once per decoding step with the
    number of tokens generated so far; `read_generated()` returns them and is called only
    once the budget is reached. It returns the token to force, or None.
    """

    def __init__(
        self,
        *,
        budget: int,
        hard: int,
        transition: list[int],
        analysis: list[int],
        sentence_ends: frozenset[int],
    ) -> None:
        self.budget, self.hard = budget, hard
        self.transition = list(transition)
        self.analysis = list(analysis)
        self.sentence_ends = sentence_ends
        self.state = "counting"  # counting -> armed -> forcing -> done
        self.queue: list[int] = []
        self.outcome: dict[str, Any] = {"outcome": "under budget"}

    def _in_analysis(self, generated: list[int]) -> bool:
        header = [CHANNEL, *self.analysis, MESSAGE]
        if generated[: len(header)] != header:
            return False
        return END not in generated[len(header) :]

    def step(self, count: int, read_generated: Callable[[], list[int]]) -> int | None:
        if self.state == "done":
            return None
        if self.state == "forcing":
            token = self.queue.pop(0)
            if not self.queue:
                self.state = "done"
            return token
        if count < self.budget:
            return None
        generated = list(read_generated())
        if self.state == "counting":
            if not self._in_analysis(generated):
                self.state = "done"
                self.outcome = {"outcome": "not in reasoning at the budget", "at": count}
                return None
            self.state = "armed"
        if generated and generated[-1] == END:  # the model ended its reasoning itself
            self.state = "done"
            self.outcome = {"outcome": "ended naturally after the budget", "at": count}
            return None
        if count >= self.hard or (generated and generated[-1] in self.sentence_ends):
            self.state = "forcing"
            self.queue = list(self.transition)
            self.outcome = {
                "outcome": "transition forced",
                "at": count,
                "reason": "hard limit" if count >= self.hard else "sentence end",
            }
            return self.step(count, read_generated)
        return None


def sentence_end(text: str) -> bool:
    """A token that ends a sentence or a line of the reasoning."""
    return "\n" in text or text.rstrip(" ").endswith((".", "!", "?", ".)", '."', '?"', '!"'))


def _sentence_end_ids(tokenizer: object) -> frozenset[int]:
    key = id(tokenizer)
    if key not in _sentence_ends:
        fast = getattr(tokenizer, "_tokenizer", tokenizer)
        texts = fast.batch_decode([[i] for i in range(len(fast))])  # type: ignore[attr-defined]
        _sentence_ends[key] = frozenset(i for i, text in enumerate(texts) if sentence_end(text))
    return _sentence_ends[key]


class _Processor:
    """The engine-facing wrapper: an mlx-lm logits processor over `BudgetState`."""

    def __init__(self, state: BudgetState, total: int) -> None:
        self.state, self.total, self.start = state, total, None
        self.logged = False

    def __call__(self, tokens, logits):  # noqa: ANN001, ANN204 - mlx arrays, the engine's own signature
        import mlx.core as mx

        count_all = int(tokens.shape[0])
        if self.start is None:
            self.start = count_all  # the first call carries only the prompt's tail
        count = count_all - self.start
        start = self.start
        forced = self.state.step(count, lambda: tokens[start:].tolist())
        decided = self.state.outcome["outcome"] != "under budget"
        if decided and not self.logged:
            self.logged = True
            _log(f"request {json.dumps({'total': self.total, **self.state.outcome})}")
        if forced is None:
            return logits
        column = mx.arange(logits.shape[-1]) == forced
        blocked = mx.full(logits.shape, -mx.inf, dtype=logits.dtype)
        return mx.where(column, mx.zeros_like(logits), blocked)


def _patch(module) -> None:  # noqa: ANN001 - the engine module
    original_generation = module._sequential_generation
    original_stream = module.stream_generate

    def _sequential_generation(model_kit, prompt_tokens, **kwargs):  # noqa: ANN001, ANN003, ANN202
        path = str(getattr(model_kit, "model_path", ""))
        _local.request = (path, len(prompt_tokens), model_kit.tokenizer)
        try:
            yield from original_generation(model_kit, prompt_tokens, **kwargs)
        finally:
            _local.request = None

    def stream_generate(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        try:
            request = getattr(_local, "request", None)
            control = _control()
            listed = request is not None and _listed(request[0], control)
            if request is not None and not listed and request[0] not in _declined:
                _declined.add(request[0])
                _log(f"declined (not allowlisted): {request[0]}")
            if listed:
                _sentence_end_ids(request[2])  # built once per model, whichever condition is first
            if listed and control.get("enabled"):
                _, total, tokenizer = request
                budget = int(control["budget_tokens"])
                hard = int(control.get("hard_tokens", budget))
                transition = tokenizer.encode(TRANSITION_TEXT, add_special_tokens=False)
                analysis = tokenizer.encode(ANALYSIS_TEXT, add_special_tokens=False)
                shape = transition[:2] + transition[3:4] + transition[5:6]
                if len(transition) != 6 or shape != [END, START, CHANNEL, MESSAGE]:
                    raise ValueError(f"unexpected harmony tokens {transition}")
                state = BudgetState(
                    budget=budget,
                    hard=hard,
                    transition=transition,
                    analysis=analysis,
                    sentence_ends=_sentence_end_ids(tokenizer),
                )
                processors = list(kwargs.get("logits_processors") or [])
                processors.append(_Processor(state, total))
                kwargs["logits_processors"] = processors
                _log(f"armed {json.dumps({'total': total, 'budget': budget, 'hard': hard})}")
        except Exception as error:
            _log(f"not applied, request unchanged: {type(error).__name__}: {error}")
        return original_stream(*args, **kwargs)

    module._sequential_generation = _sequential_generation
    module.stream_generate = stream_generate
    _log("generation hook installed in this interpreter")


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
