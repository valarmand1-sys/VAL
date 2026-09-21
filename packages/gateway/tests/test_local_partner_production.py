"""GPT-OSS as Val's ordinary text cognition — owner admission ruling, 21 September 2026.

Only what this change made new or different. The model's behaviour is not
retested here: the Stage A record stands, the owner has ruled on suitability
knowing it, and nothing below scores a sentence. What is new is where ordinary
Partner work goes, what happens when it cannot go there, and that the support
calls are untouched by the rule that governs it.

Five things, and the third is the point of the other four:

1. ordinary conversation selects the owner-admitted local Partner route;
2. the consequential blind position pins to that same route, because the call
   where Val forms her own view is not a different model from the one that
   speaks;
3. **when the local route cannot carry Partner work, the turn stops** rather
   than reaching for a paid one — enforced in routing, not asked for in persona
   wording;
4. classification and stripping keep their structured cloud routes and are not
   caught by that stop;
5. the persona the house has activated reaches the local model by the ordinary
   path, whole.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from gateway_fakes import FakeLedger, StubAdapter, build
from sqlalchemy import Engine
from test_conversation_memory import answering, catalogue, store
from test_persona import REPO_ROOT, clean_personas

from val_domain.conversation import StoredRole
from val_domain.gateway import (
    CapabilityProfile,
    Classification,
    GatewayError,
    GatewayErrorKind,
    Message,
    ModelConfig,
    TaskType,
    TerminalState,
    TurnReference,
)
from val_domain.project import ExplicitNoProject
from val_domain.provider import LocalRuntimeUnavailableError
from val_domain.registry import active, by_slug
from val_gateway.gateway import CallRecord, Gateway
from val_gateway.loop import send
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader, seed
from val_gateway.provenance import verifier
from val_policy.project_resolution import ProjectSignals
from val_policy.routing import required_profile, satisfies_profile
from val_providers.base import ProviderResult

__all__ = ["clean_personas", "store"]

LOCAL = "gpt-oss-20b-mxfp4-mlx-lmstudio-partner"
SOL = "gpt-5-6-sol-medium"


def local_config() -> ModelConfig:
    config = by_slug(LOCAL)
    assert config is not None
    return config


# --- 1 and 2: Val's own two calls, on the house's own machine -------------------------


def test_ordinary_conversation_selects_the_owner_admitted_local_partner() -> None:
    answering_stub = StubAdapter(ProviderResult("As you say.", TerminalState.COMPLETE, 9, 3, "r"))
    gateway, _, _, _ = build(
        adapters={"anthropic": answering_stub, "openai": answering_stub, "lmstudio": answering_stub}
    )
    chosen = gateway.select_configuration(
        Classification.PROTECTED,
        ("persona", "good evening"),
        4_096,
        task_type=TaskType.CONVERSATION,
    )
    assert chosen.slug == LOCAL
    assert chosen.provider == "lmstudio"
    assert chosen.cost_per_mtok_in_usd == 0.0 and chosen.cost_per_mtok_out_usd == 0.0


def test_the_blind_position_requires_the_same_partner_floor_as_the_answer() -> None:
    """Not a separate model for the call where she forms her own view."""
    assert required_profile(TaskType.BLIND_POSITION) is required_profile(TaskType.CONVERSATION)
    assert satisfies_profile(local_config(), required_profile(TaskType.BLIND_POSITION))


def test_the_local_partner_is_the_cheapest_route_that_satisfies_the_partner_floor() -> None:
    partner = [c for c in active() if CapabilityProfile.PARTNER in c.capability_profiles]
    assert len(partner) >= 2, "the cloud partner routes remain registered for escalation"
    cheapest = min(
        partner, key=lambda c: (c.cost_per_mtok_in_usd + c.cost_per_mtok_out_usd, c.slug)
    )
    assert cheapest.slug == LOCAL


# --- 3: the stop before a paid Partner call -------------------------------------------


def test_partner_work_stops_rather_than_reaching_for_a_paid_route(store: Engine) -> None:
    """The local runtime is unreachable; the turn ends, and nothing is transmitted."""
    adapter = answering()
    gateway = Gateway(
        # No local adapter: the runtime is not there. Sol and the incumbent are,
        # and are the routes a silent fallback would have used.
        adapters={"anthropic": adapter, "openai": adapter},
        recorder=lambda record: record_call(store, record),
        ledger=FakeLedger(),
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(store),
        verify_provenance=verifier(store),
    )
    with pytest.raises(GatewayError) as caught:
        gateway.converse(
            (Message(role="user", content="Good evening, Val."),),
            scope=ExplicitNoProject(),
            turn=_a_turn(store),
        )
    assert caught.value.kind is GatewayErrorKind.LOCAL_PARTNER_UNAVAILABLE
    assert "Partner cognition runs locally" in str(caught.value)
    assert "needs his explicit approval" in str(caught.value)
    assert adapter.calls == 0, "no provider was contacted at all"


def test_the_stop_names_the_local_route_and_the_paid_one_it_refused() -> None:
    """An honest failure says what it would not do, so the owner can decide."""
    from val_policy.routing import paid_partner_refusal

    sol = by_slug(SOL)
    assert sol is not None
    refusal = paid_partner_refusal(sol, local_config(), profile=CapabilityProfile.PARTNER)
    assert refusal is not None
    assert LOCAL in refusal and SOL in refusal
    assert "Nothing was transmitted and nothing was charged" in refusal


def test_previous_cloud_use_is_not_approval() -> None:
    """There is no standing exception and no approve-and-retry path in this pass.

    The refusal is a pure function of the two routes and the floor. Nothing about
    history, habit or a previous turn enters it, which is what keeps "we used the
    cloud before" from quietly becoming "we may use it now".
    """
    from val_policy.routing import paid_partner_refusal

    sol = by_slug(SOL)
    assert sol is not None
    first = paid_partner_refusal(sol, local_config(), profile=CapabilityProfile.PARTNER)
    second = paid_partner_refusal(sol, local_config(), profile=CapabilityProfile.PARTNER)
    assert first == second and first is not None


def test_a_runtime_that_cannot_be_brought_up_ends_the_turn_and_does_not_escalate(
    store: Engine,
) -> None:
    class Refusing(StubAdapter):
        def ensure_runtime_ready(self, config: ModelConfig) -> Mapping[str, object]:
            raise LocalRuntimeUnavailableError("the server did not start")

    adapter = Refusing(ProviderResult("unused", TerminalState.COMPLETE, 1, 1, "r"))
    gateway = Gateway(
        adapters={"anthropic": adapter, "openai": adapter, "lmstudio": adapter},
        recorder=lambda record: record_call(store, record),
        ledger=FakeLedger(),
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(store),
        verify_provenance=verifier(store),
    )
    with pytest.raises(GatewayError) as caught:
        gateway.converse(
            (Message(role="user", content="Good evening."),),
            scope=ExplicitNoProject(),
            turn=_a_turn(store),
        )
    assert caught.value.kind is GatewayErrorKind.LOCAL_PARTNER_UNAVAILABLE
    assert "one bounded recovery attempt was made" in str(caught.value)
    assert adapter.calls == 0


# --- 4: the support calls are not caught by the Partner rule ---------------------------


def test_classification_and_strip_keep_their_structured_cloud_routes() -> None:
    """Left unchanged deliberately in this pass, and outside the Partner stop."""
    from val_policy.routing import candidates

    for task in (TaskType.CLASSIFICATION, TaskType.STRIP):
        chosen = candidates(
            active(),
            Classification.PROTECTED,
            lambda config: True,
            lambda config: True,
            profile=required_profile(task),
            cost_bound=lambda c: c.cost_per_mtok_in_usd + c.cost_per_mtok_out_usd,
        )
        assert chosen, f"{task.value} still has a route"
        assert chosen[0].provider != "lmstudio", "not localised in this pass"
        assert LOCAL not in {c.slug for c in chosen}


def test_the_stop_governs_partner_work_only() -> None:
    from val_policy.routing import paid_partner_refusal

    sol = by_slug(SOL)
    assert sol is not None
    for profile in (CapabilityProfile.STRUCTURED, CapabilityProfile.STRIP):
        assert paid_partner_refusal(sol, local_config(), profile=profile) is None


def test_a_request_the_local_route_could_not_have_carried_is_not_caught() -> None:
    """Image turns keep the behaviour Track C gave them, by capability and not by exception."""
    from val_policy.routing import can_carry_images, local_alternative

    assert not can_carry_images(local_config()), "the local model declares no image input"
    none_found = local_alternative(
        active(),
        Classification.PROTECTED,
        profile=CapabilityProfile.PARTNER,
        can_hold=can_carry_images,
    )
    assert none_found is None, "a turn carrying images finds no local alternative, so nothing stops"


# --- 5: the persona reaches the local model by the ordinary path -----------------------


def test_the_active_persona_reaches_the_local_partner_whole(clean_personas: Engine) -> None:
    seed(clean_personas, REPO_ROOT)
    persona = DatabasePersonaLoader(clean_personas).active()
    # The authored label is what the admission names; the persistence revision
    # is a fact about this fixture's store, not about the persona.
    assert persona.semantic_version == "1.9"

    adapter = answering()
    rows: list[CallRecord] = []
    gateway = Gateway(
        adapters={"anthropic": adapter, "openai": adapter, "lmstudio": adapter},
        recorder=lambda record: (rows.append(record), record_call(clean_personas, record))[1],
        ledger=FakeLedger(),
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(clean_personas),
        verify_provenance=verifier(clean_personas),
    )
    outcome = send(
        clean_personas,
        gateway,
        "Good evening, Val.",
        catalogue=catalogue(clean_personas),
        signals=ProjectSignals(explicit_no_project=True),
    )
    assert getattr(outcome, "response", None) is not None

    # The route, and the persona on it, from the record rather than from intent.
    conversation = [row for row in rows if row.slug == LOCAL]
    assert conversation, "the conversation call went to the local partner route"
    assert conversation[-1].persona_id == persona.id
    # Whole, not summarised: the governing document is what was sent.
    assert adapter.sent_system is not None
    assert adapter.sent_system.count(persona.content) == 1
    assert "Form follows the task" in adapter.sent_system


def test_local_inference_is_recorded_at_a_known_zero(clean_personas: Engine) -> None:
    """Already settled for the route; confirmed here for the reconnected path."""
    seed(clean_personas, REPO_ROOT)
    adapter = answering()
    rows: list[CallRecord] = []
    gateway = Gateway(
        adapters={"anthropic": adapter, "openai": adapter, "lmstudio": adapter},
        recorder=lambda record: (rows.append(record), record_call(clean_personas, record))[1],
        ledger=FakeLedger(),
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(clean_personas),
        verify_provenance=verifier(clean_personas),
    )
    send(
        clean_personas,
        gateway,
        "Good evening.",
        catalogue=catalogue(clean_personas),
        signals=ProjectSignals(explicit_no_project=True),
    )
    conversation = [row for row in rows if row.slug == LOCAL]
    assert conversation and conversation[-1].cost_usd == 0.0


def _a_turn(engine: Engine) -> TurnReference:
    from val_domain.gateway import TurnReference
    from val_gateway import conversations

    conversation = conversations.create(engine, scope=ExplicitNoProject(), title="local partner")
    message = conversations.append(
        engine, conversation.id, role=StoredRole.USER, content="Good evening."
    )
    return TurnReference(conversation_id=conversation.id, message_id=message.id)
