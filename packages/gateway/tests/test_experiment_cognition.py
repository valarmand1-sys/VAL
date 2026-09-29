"""The experiment cognition switch — owner order of 29 September 2026 (isolated
qualification of Qwen3-30B-A3B-Instruct-2507). Unset, the registry is exactly as written;
set, the candidate carries the partner profile and the admitted GPT-OSS entry does not,
in this process only; an unknown value refuses to start.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

import val_domain.registry as registry
from val_domain.gateway import Admission, CapabilityProfile, Hosting, ReasoningEffort
from val_gateway.startup import (
    EXPERIMENT_COGNITION,
    PARTNER_SLUG,
    configured_experiment_cognition,
    enable_experiment_cognition,
)

CANDIDATE = "qwen3-30b-a3b-instruct-2507-mlx-lmstudio"


@pytest.fixture
def restored_registry() -> Iterator[None]:
    before = registry.REGISTRY
    try:
        yield
    finally:
        registry.REGISTRY = before


def partners() -> list[str]:
    """The local partner routes: the metered cloud ones are never reached silently."""
    return [
        c.slug
        for c in registry.active()
        if CapabilityProfile.PARTNER in c.capability_profiles and c.hosting is Hosting.LOCAL
    ]


def test_unset_means_the_registry_as_written(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VAL_EXPERIMENT_COGNITION", raising=False)
    assert configured_experiment_cognition() == (None, None)
    assert CANDIDATE not in {c.slug for c in registry.active()}
    candidate = registry.by_slug(CANDIDATE)
    assert candidate is not None
    assert candidate.admission is Admission.NOT_ADMITTED
    assert candidate.capability_profiles == frozenset()
    assert PARTNER_SLUG in partners()


def test_an_unknown_value_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAL_EXPERIMENT_COGNITION", "qwen3-235b")
    assert configured_experiment_cognition()[1] is not None
    monkeypatch.setenv("VAL_EXPERIMENT_COGNITION", " Qwen3-30B-A3B ")
    assert configured_experiment_cognition() == ("qwen3-30b-a3b", None)


def test_set_the_candidate_is_the_only_local_partner_in_this_process(
    restored_registry: None,
) -> None:
    written = registry.by_slug(CANDIDATE)
    promoted = enable_experiment_cognition("qwen3-30b-a3b")
    assert promoted.slug == EXPERIMENT_COGNITION["qwen3-30b-a3b"] == CANDIDATE
    assert promoted.admission is Admission.PROVISIONALLY_ADMITTED
    assert partners() == [CANDIDATE]
    gpt_oss = registry.by_slug(PARTNER_SLUG)
    assert gpt_oss is not None
    assert CapabilityProfile.PARTNER not in gpt_oss.capability_profiles
    # The candidate differs from the entry as written only in admission and profile.
    assert written is not None
    same = {"admission", "capability_profiles", "qualification_targets"}
    for field in type(written).model_fields:
        if field not in same:
            assert getattr(promoted, field) == getattr(written, field), field


def test_the_candidate_declares_no_effort_and_the_documented_temperature() -> None:
    candidate = registry.by_slug(CANDIDATE)
    assert candidate is not None
    assert candidate.reasoning_effort is ReasoningEffort.NOT_APPLICABLE
    assert candidate.temperature == 0.7
    # Top-p and top-k cannot be carried by the LM Studio request (ruled): they come
    # from the model definition and are observed at the engine.
    assert candidate.top_p is None and candidate.top_k is None
    assert candidate.provider == "lmstudio"
