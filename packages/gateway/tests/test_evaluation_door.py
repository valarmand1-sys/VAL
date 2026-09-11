"""The evaluation door — ruling, 10 September 2026 (strip cost/latency correction).

A candidate for a capability floor is registered `NOT_ADMITTED` with no
profile, so routing never selects it and the pinned path refuses it; it is
reachable only through `Gateway.evaluate_with_configuration`, which is
narrower than the pinned path: schema-constrained structured work only, never
a task in which Val speaks, never an admitted configuration, never a caller's
copy of an entry, and eligibility by classification as for any call.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from gateway_fakes import StubAdapter, build

from val_domain.gateway import (
    Admission,
    CapabilityProfile,
    Classification,
    GatewayError,
    GatewayErrorKind,
    GatewayRequest,
    Message,
    PersonaAttribution,
    TaskType,
    TerminalState,
)
from val_domain.project import ProjectAttribution
from val_domain.registry import REGISTRY, active, by_id, by_slug, under_evaluation
from val_policy.deliberation import STRIP_INSTRUCTION, STRIP_OUTPUT_SCHEMA
from val_policy.routing import candidates, required_profile
from val_providers.base import ProviderResult

# `sonnet-5-low` left this set on 11 September 2026: designated for the strip.
CANDIDATES = ("sonnet-5-medium", "gpt-5-6-terra", "gpt-5-6-luna")


def strip_request(
    task_type: TaskType = TaskType.STRIP, *, with_schema: bool = True
) -> GatewayRequest:
    return GatewayRequest(
        task_type=task_type,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="Which lens? I'd go long."),),
        system=STRIP_INSTRUCTION,
        max_output_tokens=4096,
        output_schema=STRIP_OUTPUT_SCHEMA if with_schema else None,
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
        persona=(
            PersonaAttribution(persona_id=uuid4()) if task_type is TaskType.BLIND_POSITION else None
        ),
    )


def _answer() -> ProviderResult:
    return ProviderResult('{"preference_present": false}', TerminalState.COMPLETE, 30, 8, "r")


# --- the candidates are registered and never routable ------------------------


def test_the_four_candidates_are_registered_for_evaluation_only() -> None:
    assert {config.slug for config in under_evaluation()} == set(CANDIDATES)
    for slug in CANDIDATES:
        config = by_slug(slug)
        assert config is not None, slug
        assert config.admission is Admission.NOT_ADMITTED
        assert config.capability_profiles == frozenset()
        assert config.fallback_slug is None
        assert not config.retired
        assert config not in active(), "an evaluation entry is not a route"


def test_no_candidate_is_ever_a_routing_candidate_for_any_profile() -> None:
    for profile in CapabilityProfile:
        chosen = candidates(
            REGISTRY,  # even offered the whole registry, not just `active()`
            Classification.PROTECTED,
            lambda config: True,
            lambda config: True,
            profile=profile,
            cost_bound=lambda config: config.cost_per_mtok_in_usd,
        )
        assert not {config.slug for config in chosen} & set(CANDIDATES), profile


def test_the_pinned_path_refuses_a_candidate_for_the_floor() -> None:
    adapter = StubAdapter(_answer(), name="openai")
    gateway, rows, _, _ = build(adapters={"anthropic": adapter, "openai": adapter})
    terra = by_slug("gpt-5-6-terra")
    assert terra is not None
    with pytest.raises(GatewayError) as caught:
        gateway.complete_with_configuration(strip_request(), terra)
    assert caught.value.kind is GatewayErrorKind.NO_ELIGIBLE_ROUTE
    assert adapter.calls == 0 and rows == []


def test_routing_never_reaches_a_candidate_for_the_strip() -> None:
    """The cheapest entry in the registry is Luna; the strip does not go there."""
    adapter = StubAdapter(_answer(), name="openai")
    gateway, rows, _, _ = build(adapters={"anthropic": adapter, "openai": adapter})
    gateway.complete(strip_request())
    assert len(rows) == 1
    routed = by_id(rows[0].model_config_id)
    assert routed is not None
    assert routed.slug not in CANDIDATES
    assert required_profile(TaskType.STRIP) in routed.capability_profiles


# --- the door itself ---------------------------------------------------------


def test_the_door_runs_a_schema_constrained_strip_on_a_candidate() -> None:
    adapter = StubAdapter(_answer(), name="openai")
    gateway, rows, _, _ = build(adapters={"anthropic": adapter, "openai": adapter})
    terra = by_slug("gpt-5-6-terra")
    assert terra is not None

    response = gateway.evaluate_with_configuration(strip_request(), terra)

    assert response.terminal is TerminalState.COMPLETE
    assert adapter.calls == 1
    assert adapter.sent_output_schema == STRIP_OUTPUT_SCHEMA, "the schema reached the adapter"
    assert len(rows) == 1 and rows[0].model_config_id == terra.id, "recorded under the candidate"


def test_the_door_refuses_an_admitted_configuration() -> None:
    """A serving configuration is exercised through routing or the pinned path."""
    adapter = StubAdapter(_answer())
    gateway, rows, _, _ = build(adapters={"anthropic": adapter, "openai": adapter})
    sonnet = by_slug("sonnet-5")
    assert sonnet is not None and sonnet.admission is Admission.PROVISIONALLY_ADMITTED
    with pytest.raises(GatewayError) as caught:
        gateway.evaluate_with_configuration(strip_request(), sonnet)
    assert caught.value.kind is GatewayErrorKind.NO_ELIGIBLE_ROUTE
    assert "evaluation door" in str(caught.value)
    assert adapter.calls == 0 and rows == []


def test_the_door_refuses_a_callers_copy_of_a_candidate() -> None:
    adapter = StubAdapter(_answer(), name="openai")
    gateway, rows, _, _ = build(adapters={"anthropic": adapter, "openai": adapter})
    terra = by_slug("gpt-5-6-terra")
    assert terra is not None
    edited = terra.model_copy(update={"model_identifier": "gpt-6-astra"})
    with pytest.raises(GatewayError) as caught:
        gateway.evaluate_with_configuration(strip_request(), edited)
    assert caught.value.kind is GatewayErrorKind.NO_ELIGIBLE_ROUTE
    assert adapter.calls == 0 and rows == []


def test_the_door_refuses_a_task_in_which_val_speaks() -> None:
    adapter = StubAdapter(_answer(), name="openai")
    gateway, rows, _, _ = build(adapters={"anthropic": adapter, "openai": adapter})
    terra = by_slug("gpt-5-6-terra")
    assert terra is not None
    with pytest.raises(GatewayError) as caught:
        gateway.evaluate_with_configuration(strip_request(TaskType.BLIND_POSITION), terra)
    assert caught.value.kind is GatewayErrorKind.INVALID_REQUEST
    assert "Val speaks" in str(caught.value)
    assert adapter.calls == 0 and rows == []


def test_the_door_refuses_a_request_without_a_schema() -> None:
    adapter = StubAdapter(_answer(), name="openai")
    gateway, rows, _, _ = build(adapters={"anthropic": adapter, "openai": adapter})
    terra = by_slug("gpt-5-6-terra")
    assert terra is not None
    with pytest.raises(GatewayError) as caught:
        gateway.evaluate_with_configuration(strip_request(with_schema=False), terra)
    assert caught.value.kind is GatewayErrorKind.INVALID_REQUEST
    assert adapter.calls == 0 and rows == []


def test_the_door_refuses_restricted_content() -> None:
    adapter = StubAdapter(_answer(), name="openai")
    gateway, rows, _, _ = build(adapters={"anthropic": adapter, "openai": adapter})
    terra = by_slug("gpt-5-6-terra")
    assert terra is not None
    request = strip_request().model_copy(update={"classification": Classification.RESTRICTED})
    with pytest.raises(GatewayError) as caught:
        gateway.evaluate_with_configuration(request, terra)
    assert caught.value.kind is GatewayErrorKind.RESTRICTED_CONTENT
    assert adapter.calls == 0 and rows == []
