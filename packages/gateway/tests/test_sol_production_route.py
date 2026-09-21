"""GPT-5.6 Sol admitted to the partner profile — owner ruling, 14 September 2026.

Production evidence: Sol is an active partner configuration; an ordinary
eligible PARTNER request resolves to it through the ordinary router and the
ordinary cost selection; qualification metadata is gone from the entry; the
candidate lane refuses it (an admitted configuration is served through
routing, never through the lane); no HTTP option reaches the lane; fallback
semantics are unchanged; the incumbent remains registered under its existing
state. Persona v1.8 is part of the admitted configuration.
"""

from __future__ import annotations

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
    PricingFeature,
    ReasoningEffort,
    TaskType,
    TerminalState,
)
from val_domain.project import ProjectAttribution
from val_domain.registry import active, by_slug, fallback_for, under_evaluation
from val_gateway.candidate import CandidateGateway
from val_policy.routing import attempt_order, required_profile, satisfies_profile
from val_providers.base import ProviderResult

SOL = "gpt-5-6-sol-medium"


def sol() -> object:
    config = by_slug(SOL)
    assert config is not None
    return config


def test_sol_is_an_active_partner_configuration_in_the_incumbents_admission_state() -> None:
    config = sol()
    assert config in active() and config not in under_evaluation()
    assert config.admission is Admission.PROVISIONALLY_ADMITTED
    assert config.capability_profiles == frozenset({CapabilityProfile.PARTNER})
    assert config.qualification_targets == frozenset(), "qualification metadata is gone"
    assert config.model_identifier == "gpt-5.6-sol"
    assert config.reasoning_effort is ReasoningEffort.MEDIUM
    assert config.caching is PricingFeature.AVAILABLE and config.caches_automatically
    assert (
        config.owner_authorization and "ADMISSION RULING BY EXCEPTION" in config.owner_authorization
    )
    assert "NOT MET" in config.owner_authorization, "the two statuses are never collapsed"
    assert any("I6" in weakness for weakness in config.known_weaknesses), (
        "the residual is on the entry"
    )
    incumbent = by_slug("opus-5-medium")
    assert incumbent is not None and incumbent.admission is config.admission


def test_sol_is_no_longer_the_ordinary_partner_route_but_is_still_one() -> None:
    """Owner admission ruling, 21 September 2026 — and this test used to say the reverse.

    It asserted that an ordinary partner request resolves to Sol, which was true
    and is the evidence of Sol's cutover of 14 September. What changed is not Sol
    and not the router: a local partner route was admitted at a cost of zero, and
    cost ranks what the floor has already admitted. Sol stays registered,
    partner-profiled and eligible — the route an owner-approved escalation would
    name — and is simply no longer the cheapest. Its admission evidence in this
    file is untouched.
    """
    order = attempt_order(
        active(),
        Classification.PROTECTED,
        is_ready=lambda config: True,
        is_affordable=lambda config: True,
        resolve_fallback=fallback_for,
        profile=required_profile(TaskType.CONVERSATION),
        cost_bound=lambda config: config.cost_per_mtok_in_usd + config.cost_per_mtok_out_usd,
    )
    assert order and order[0].slug == "gpt-oss-20b-mxfp4-mlx-lmstudio-partner"
    assert all(satisfies_profile(config, CapabilityProfile.PARTNER) for config in order)
    # The order is the cheapest partner route plus its declared chain. The local
    # route declares no fallback, so it stands alone: an undeclared fallback is
    # no fallback, which is what keeps a paid route from being reached by
    # accident when the local one fails.
    assert len(order) == 1

    sol = by_slug(SOL)
    assert sol is not None and sol in active()
    assert CapabilityProfile.PARTNER in sol.capability_profiles
    incumbent = by_slug("opus-5-medium")
    assert incumbent is not None and incumbent in active()
    assert CapabilityProfile.PARTNER in incumbent.capability_profiles


def test_the_gateway_now_selects_the_local_partner_for_an_ordinary_conversation() -> None:
    """The same selection this file used to pin to Sol, at the gateway seam."""
    answering = StubAdapter(
        ProviderResult("Good evening, my lord.", TerminalState.COMPLETE, 20, 5, "r")
    )
    gateway, _, _, _ = build(
        adapters={"anthropic": answering, "openai": answering, "lmstudio": answering}
    )
    chosen = gateway.select_configuration(
        Classification.PROTECTED, ("persona", "hello"), 4096, task_type=TaskType.CONVERSATION
    )
    assert chosen.slug == "gpt-oss-20b-mxfp4-mlx-lmstudio-partner"
    assert chosen.provider == "lmstudio"


def test_the_blind_position_pins_to_the_same_partner_configuration() -> None:
    answering = StubAdapter(ProviderResult("{}", TerminalState.COMPLETE, 20, 5, "r"))
    gateway, _, _, _ = build(
        adapters={"anthropic": answering, "openai": answering, "lmstudio": answering}
    )
    chosen = gateway.select_configuration(
        Classification.PROTECTED, ("persona", "q"), 4096, task_type=TaskType.CONVERSATION
    )
    assert satisfies_profile(chosen, required_profile(TaskType.BLIND_POSITION))


def test_structured_work_does_not_route_to_sol() -> None:
    answering = StubAdapter(ProviderResult("{}", TerminalState.COMPLETE, 20, 5, "r"))
    gateway, _, _, _ = build(
        adapters={"anthropic": answering, "openai": answering, "lmstudio": answering}
    )
    for task in (TaskType.CLASSIFICATION, TaskType.TITLE, TaskType.STRIP):
        chosen = gateway.select_configuration(Classification.PROTECTED, ("x",), 256, task_type=task)
        assert chosen.slug != SOL, task


def test_the_candidate_lane_refuses_the_admitted_configuration() -> None:
    answering = StubAdapter(ProviderResult("{}", TerminalState.COMPLETE, 20, 5, "r"), name="openai")
    gateway, rows, _, _ = build(
        adapters={"anthropic": answering, "openai": answering, "lmstudio": answering}
    )
    lane = CandidateGateway.__new__(CandidateGateway)
    lane.__dict__.update(gateway.__dict__)
    with __import__("pytest").raises(GatewayError) as refused:
        lane._verify_candidate_configuration(
            sol(),  # type: ignore[arg-type]
            Classification.PROTECTED,
            TaskType.CONVERSATION,
        )
    assert refused.value.kind is GatewayErrorKind.NO_ELIGIBLE_ROUTE
    assert "not a candidate" in refused.value.detail
    assert answering.calls == 0 and rows == []


def test_fallback_semantics_are_unchanged() -> None:
    assert sol().fallback_slug is None, "no new fallback was invented for the migration"
    incumbent = by_slug("opus-5-medium")
    assert incumbent is not None and incumbent.fallback_slug == "haiku-4-5-20251001"
    assert all(config.fallback_slug != SOL for config in active()), "Sol is nobody's fallback"


def test_no_request_contract_reaches_the_candidate_lane() -> None:
    import inspect

    from val_gateway import startup

    assert "CandidateGateway" not in inspect.getsource(startup)


def test_the_blind_request_shape_still_requires_persona_attribution_on_sol() -> None:
    request = GatewayRequest(
        task_type=TaskType.BLIND_POSITION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="q"),),
        system="persona",
        output_schema={"type": "object"},
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
        persona=PersonaAttribution(persona_id=__import__("uuid").uuid4()),
    )
    assert request.persona is not None
