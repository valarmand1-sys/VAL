"""GPT-5.6 Sol is registered as a partner candidate and cannot serve — ruling, 13 September 2026.

Registering the candidate admits nothing. It is `NOT_ADMITTED` with no
capability profile: routing never selects it for any profile, the pinned path
refuses it for the partner floor, the evaluation door refuses the two tasks in
which Val speaks, it is no route's fallback, and startup builds no adapter
because of it. Anthropic remains the partner route.
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
    ReasoningEffort,
    TaskType,
    TerminalState,
)
from val_domain.project import ProjectAttribution
from val_domain.registry import REGISTRY, active, by_slug
from val_policy.routing import candidates
from val_providers.base import ProviderResult

SOL = "gpt-5-6-sol-medium"


def _sol() -> object:
    config = by_slug(SOL)
    assert config is not None
    return config


def _blind_request() -> GatewayRequest:
    return GatewayRequest(
        task_type=TaskType.BLIND_POSITION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="State your position."),),
        system="persona",
        output_schema={"type": "object"},
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
        persona=PersonaAttribution(persona_id=uuid4()),
    )


def test_the_entry_is_the_ruled_candidate_configuration() -> None:
    sol = by_slug(SOL)
    assert sol is not None
    assert (sol.provider, sol.model_identifier) == ("openai", "gpt-5.6-sol")
    assert sol.reasoning_effort is ReasoningEffort.MEDIUM
    assert sol.admission is Admission.NOT_ADMITTED
    assert sol.capability_profiles == frozenset()
    assert sol.fallback_slug is None
    assert (sol.cost_per_mtok_in_usd, sol.cost_per_mtok_out_usd) == (4.00, 20.00)
    assert sol.long_context_threshold_tokens == 272_000


def test_sol_is_never_a_route_or_a_fallback() -> None:
    assert by_slug(SOL) not in active()
    assert all(config.fallback_slug != SOL for config in REGISTRY)
    partner = by_slug("opus-5-medium")
    assert partner is not None and partner in active()
    assert CapabilityProfile.PARTNER in partner.capability_profiles
    for profile in CapabilityProfile:
        chosen = candidates(
            REGISTRY,
            Classification.PROTECTED,
            lambda config: True,
            lambda config: True,
            profile=profile,
            cost_bound=lambda config: config.cost_per_mtok_in_usd,
        )
        assert SOL not in {config.slug for config in chosen}, profile


@pytest.mark.parametrize("task_type", [TaskType.CONVERSATION, TaskType.BLIND_POSITION])
def test_the_pinned_path_refuses_sol_for_the_partner_floor(task_type: TaskType) -> None:
    """The check `converse(configuration=...)` and the pinned blind call both run."""
    adapter = StubAdapter(ProviderResult("{}", TerminalState.COMPLETE, 1, 1, "r"), name="openai")
    gateway, rows, _, _ = build(adapters={"anthropic": adapter, "openai": adapter})
    with pytest.raises(GatewayError) as caught:
        gateway._verify_named_configuration(
            _sol(),  # type: ignore[arg-type]
            Classification.PROTECTED,
            task_type,
        )
    assert caught.value.kind is GatewayErrorKind.NO_ELIGIBLE_ROUTE
    assert "not admitted" in caught.value.detail
    assert adapter.calls == 0 and rows == []


@pytest.mark.parametrize("task_type", [TaskType.BLIND_POSITION])
def test_the_evaluation_door_refuses_sol_for_a_task_in_which_val_speaks(
    task_type: TaskType,
) -> None:
    adapter = StubAdapter(ProviderResult("{}", TerminalState.COMPLETE, 1, 1, "r"), name="openai")
    gateway, rows, _, _ = build(adapters={"anthropic": adapter, "openai": adapter})
    with pytest.raises(GatewayError) as caught:
        gateway.evaluate_with_configuration(_blind_request(), _sol())  # type: ignore[arg-type]
    assert caught.value.kind is GatewayErrorKind.INVALID_REQUEST
    assert adapter.calls == 0 and rows == []


def test_startup_needs_nothing_from_sol() -> None:
    """Startup builds adapters for the providers of `active()`; Sol is not in it."""
    assert all(config.slug != SOL for config in active())
