"""Planning a prefix prime — owner order, 25 September 2026 (priming-cache pass).

The installed engine's sequential kit keeps a checkpoint of each prompt 11 tokens
before its end and reuses a stored checkpoint only when it is an exact token prefix
of a later prompt. The plan sizes one short user message so that checkpoint lands
exactly on the boundary every real turn renders identically — and refuses, leaving
ordinary cognition untouched, whenever that cannot be established.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from val_domain.registry import by_slug
from val_providers.lmstudio_adapter import (
    PRIME_CHECKPOINT_TAIL_TOKENS,
    PRIME_QUALIFIED_ENGINE,
    PRIME_QUALIFIED_PACKAGE,
    LMStudioAdapter,
)

CONFIG = by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio-partner")
assert CONFIG is not None
PERSONA = "You are Val."
OPENING = list(range(100))  # the runtime header, the persona and the next role tokens
TAIL = [7001, 7002, 7003]  # what the template closes a user message with


class Runtime:
    def __init__(self, engine: dict[str, Any] | None = None, parallel: int | None = 1) -> None:
        self.engine = engine or {
            "name": PRIME_QUALIFIED_ENGINE[0],
            "version": PRIME_QUALIFIED_ENGINE[1],
            "vendor_packages": [PRIME_QUALIFIED_PACKAGE],
        }
        self.parallel = parallel

    def engine_identity(self) -> dict[str, Any] | None:
        return self.engine

    def serving_parallel(self, model_identifier: str) -> int | None:
        return self.parallel

    def ensure_ready(self, config: object) -> Mapping[str, object]:
        return {}


class Inspector:
    """Renders a prime as opening + one token per filler word + the closing tail."""

    def __init__(self, opening: list[int] | None = None) -> None:
        self.opening = opening if opening is not None else OPENING
        self.rendered = 0

    def opening_tokens(self, model_identifier: str, system: str) -> list[int]:
        return list(OPENING)

    def tokens(self, model_identifier: str, turns: Sequence[Mapping[str, str]]) -> list[int]:
        self.rendered += 1
        words = turns[-1]["content"].split()
        return [*self.opening, *[9000 + i for i in range(len(words))], *TAIL]


def adapter(runtime: Runtime | None = None, inspector: Inspector | None = None) -> LMStudioAdapter:
    return LMStudioAdapter(
        "http://127.0.0.1:1234/v1",
        "a-token",
        read_native_models=False,
        inspector=inspector or Inspector(),  # type: ignore[arg-type]
        runtime=runtime or Runtime(),  # type: ignore[arg-type]
    )


def test_the_checkpoint_is_placed_exactly_on_the_shared_boundary() -> None:
    plan = adapter().plan_prefix_prime(CONFIG, PERSONA)
    assert plan.refused is None
    assert plan.boundary_tokens == len(OPENING)
    # Its checkpoint — the prompt less the engine's tail — is the boundary, exactly.
    assert plan.prime_tokens - PRIME_CHECKPOINT_TAIL_TOKENS == len(OPENING)
    assert plan.filler.split() == ["ok"] * (PRIME_CHECKPOINT_TAIL_TOKENS - len(TAIL))
    assert len(plan.boundary_sha256) == 64


def test_an_engine_other_than_the_qualified_one_is_not_primed() -> None:
    other = {
        "name": PRIME_QUALIFIED_ENGINE[0],
        "version": "1.12.0",
        "vendor_packages": [PRIME_QUALIFIED_PACKAGE],
    }
    plan = adapter(Runtime(engine=other)).plan_prefix_prime(CONFIG, PERSONA)
    assert plan.refused is not None and "qualified" in plan.refused
    assert plan.filler == ""


def test_a_different_vendored_package_is_not_primed_either() -> None:
    other = {
        "name": PRIME_QUALIFIED_ENGINE[0],
        "version": PRIME_QUALIFIED_ENGINE[1],
        "vendor_packages": ["_amphibian/app-mlx-generate-mac14-arm64@35"],
    }
    assert adapter(Runtime(engine=other)).plan_prefix_prime(CONFIG, PERSONA).refused


def test_a_batched_instance_is_not_primed() -> None:
    plan = adapter(Runtime(parallel=4)).plan_prefix_prime(CONFIG, PERSONA)
    assert plan.refused is not None and "sequentially" in plan.refused


def test_a_prime_whose_prefix_differs_from_the_boundary_is_refused() -> None:
    drifted = Inspector(opening=[*OPENING[:-1], 99_999])  # one token differs
    plan = adapter(inspector=drifted).plan_prefix_prime(CONFIG, PERSONA)
    assert plan.refused is not None and "token identity" in plan.refused


def test_the_plan_is_remembered_rather_than_recalibrated() -> None:
    inspector = Inspector()
    subject = adapter(inspector=inspector)
    first = subject.plan_prefix_prime(CONFIG, PERSONA)
    rendered = inspector.rendered
    assert subject.plan_prefix_prime(CONFIG, PERSONA) == first
    assert inspector.rendered == rendered
    # A different persona is a different boundary, and is planned afresh.
    subject.plan_prefix_prime(CONFIG, PERSONA + " Changed.")
    assert inspector.rendered > rendered
