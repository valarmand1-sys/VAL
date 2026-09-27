"""The narrow LOW admission: the Tier-1 request and nothing else — Milestone A §1, 26 Sept 2026.

`VAL_TIER1_ROUTE=low` promotes the evaluation-only LOW entry to the `light` floor for
this process. It must never make LOW eligible for Val's substantive work: routing for
a conversation, a blind position, or any structured task must still choose exactly the
configurations it chooses today, and the registry on disk must be unchanged.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from test_deliberation_machinery import ScriptedAdapter, build_gateway, clean_personas, store

import val_domain.registry as registry
from val_domain.gateway import Admission, CapabilityProfile, Classification, TaskType
from val_gateway.startup import enable_light_candidate

LOW = "gpt-oss-20b-mxfp4-mlx-lmstudio-low"


@pytest.fixture
def low_tier1() -> Iterator[None]:
    before = registry.REGISTRY
    enable_light_candidate("low")
    try:
        yield
    finally:
        registry.REGISTRY = before


def test_low_carries_the_light_floor_only(low_tier1: None) -> None:
    low = registry.by_slug(LOW)
    assert low is not None
    assert low.capability_profiles == frozenset({CapabilityProfile.LIGHT})


@pytest.mark.parametrize(
    "task",
    [TaskType.CONVERSATION, TaskType.BLIND_POSITION, TaskType.CLASSIFICATION, TaskType.STRIP],
)
def test_substantive_and_structured_routing_never_selects_low(
    store: Engine, low_tier1: None, task: TaskType
) -> None:
    gateway = build_gateway(store, ScriptedAdapter([]))
    with_low = gateway.select_configuration(
        Classification.PROTECTED, ("Draft the reply to the reader.",), 1024, task_type=task
    )
    assert with_low.slug != LOW
    promoted = registry.REGISTRY
    try:
        registry.REGISTRY = tuple(c for c in promoted if c.slug != LOW)
        without_low = gateway.select_configuration(
            Classification.PROTECTED, ("Draft the reply to the reader.",), 1024, task_type=task
        )
    finally:
        registry.REGISTRY = promoted
    assert with_low.slug == without_low.slug, "the promotion changed a non-Tier-1 route"


def test_only_the_light_task_reaches_low(store: Engine, low_tier1: None) -> None:
    gateway = build_gateway(store, ScriptedAdapter([]))
    chosen = gateway.select_configuration(
        Classification.PROTECTED,
        ("Good evening, Val.",),
        1024,
        task_type=TaskType.LIGHT_CONVERSATION,
    )
    assert chosen.slug == LOW


def test_the_registry_on_disk_is_untouched() -> None:
    low = registry.by_slug(LOW)
    assert low is not None and low.admission is Admission.NOT_ADMITTED
    assert low.capability_profiles == frozenset()
