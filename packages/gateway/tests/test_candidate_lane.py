"""The candidate lane — ruling, 14 September 2026.

A `NOT_ADMITTED` configuration carrying a `QualificationTarget` may speak as Val
only through a `CandidateGateway` that the scratch-store factory built, on the
deliberation path with every ordinary check in force, recorded under its own
identity. Nothing here makes it routable, and nothing here reaches it from
production. Real PostgreSQL for the turn-level tests; scripted adapters; no
provider.

Since Sol's admission on 14 September 2026 the registry holds no partner
candidate, so these tests exercise the lane on a synthetic one: an unadmitted,
profile-less copy of Sol under a fresh id, supplied through the lane's own
registry lookup (`val_gateway.candidate.by_id`, and the gateway's, patched for
the test). The lane's refusal of the real, admitted Sol is in
`test_sol_production_route.py`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, text
from test_conversation_memory import catalogue, clean_personas, store

from val_domain.deliberation import Confidence
from val_domain.gateway import (
    Admission,
    CacheTtl,
    CapabilityProfile,
    Classification,
    GatewayError,
    GatewayErrorKind,
    GatewayRequest,
    Message,
    ModelConfig,
    PersonaAttribution,
    QualificationTarget,
    TaskType,
    TerminalState,
    TurnReference,
)
from val_domain.project import ExplicitNoProject, ProjectAttribution
from val_domain.provider import ProviderResult
from val_domain.registry import REGISTRY, active, by_slug, under_evaluation
from val_gateway import deliberate
from val_gateway.candidate import (
    CandidateGateway,
    ScratchStoreRequiredError,
    candidate_gateway_for_scratch_store,
    scratch_store_or_refuse,
)
from val_gateway.gateway import Gateway
from val_gateway.ledger import DatabaseLedger
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader
from val_gateway.provenance import verifier
from val_policy.deliberation import RECONCILIATION_VERDICT_MARKER
from val_policy.project_resolution import ProjectSignals
from val_policy.routing import candidates, required_profile, satisfies_profile

__all__ = ["clean_personas", "store"]

SOL = "test-partner-candidate"
CANDIDATE_ID = UUID("7d1a0c4e-2f4b-4c1e-9a5c-1d2e3f4a5b6c")


def sol() -> ModelConfig:
    """The synthetic partner candidate (the name is kept so the tests read as written)."""
    base = by_slug("gpt-5-6-sol-medium")
    assert base is not None
    return base.model_copy(
        update={
            "id": CANDIDATE_ID,
            "slug": SOL,
            "display_name": "synthetic partner candidate (tests only)",
            "admission": Admission.NOT_ADMITTED,
            "capability_profiles": frozenset(),
            "qualification_targets": frozenset({QualificationTarget.PARTNER}),
            "owner_authorization": None,
            "known_weaknesses": (),
        }
    )


@pytest.fixture(autouse=True)
def _registry_holds_the_synthetic_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    """The lane and the gateway look the candidate up by id in the registry."""
    from val_domain import registry as registry_module
    from val_gateway import candidate as candidate_module
    from val_gateway import gateway as gateway_module

    candidate = sol()
    real_by_id = registry_module.by_id

    def by_id(config_id: UUID) -> ModelConfig | None:
        return candidate if config_id == CANDIDATE_ID else real_by_id(config_id)

    monkeypatch.setattr(candidate_module, "by_id", by_id)
    monkeypatch.setattr(gateway_module, "by_id", by_id)


# --- scripted providers --------------------------------------------------------------


def ok(body: str) -> ProviderResult:
    return ProviderResult(body, TerminalState.COMPLETE, 20, 10, "req")


PREFERENCE = "I think we should open on the wide shot."
QUESTION = "How should the film open?"
MIXED = f"{PREFERENCE} {QUESTION}"
CLOSE_UP = "Open on the close-up: the film is about her hands."


def script() -> list[ProviderResult | Exception]:
    verdict = json.dumps(
        {
            "recorded_prior": CLOSE_UP,
            "final_position": CLOSE_UP,
            "changed_from_recorded_prior": False,
            "recorded_prior_agreed_with_stated_preference": False,
            "outcome": "held",
            "what_changed_her_mind": None,
        }
    )
    return [
        ok(json.dumps({"verdict": "consequential", "hard_exclusion": None})),
        ok(
            json.dumps(
                {
                    "preference_present": True,
                    "attributed_prior_present": False,
                    "separable": True,
                    "question": QUESTION,
                    "removed": [{"text": PREFERENCE, "occurrence": 1, "kind": "preference"}],
                    "record_evidence": [],
                }
            )
        ),
        ok(json.dumps({"position": CLOSE_UP, "confidence": "medium", "reasoning": "Hands."})),
        ok(f"I hold, my lord.\n{RECONCILIATION_VERDICT_MARKER}\n{verdict}"),
    ]


@dataclass
class Recording:
    """One scripted provider registered under both names, remembering each call."""

    steps: list[ProviderResult | Exception]
    name: str = "scripted"
    calls: int = 0
    sent: list[tuple[str, str | None, bool]] = field(default_factory=list)

    def complete(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> ProviderResult:
        self.calls += 1
        self.sent.append((config.slug, system, output_schema is not None))
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def lane(engine: Engine, adapter: Recording) -> CandidateGateway:
    return candidate_gateway_for_scratch_store(
        engine,
        adapters={"anthropic": adapter, "openai": adapter},
        recorder=lambda record: record_call(engine, record),
        ledger=DatabaseLedger(engine),
        persona_loader=DatabasePersonaLoader(engine),
        verify_provenance=verifier(engine),
        observe_block=lambda message: None,
    )


def plain(engine: Engine, adapter: Recording) -> Gateway:
    return Gateway(
        adapters={"anthropic": adapter, "openai": adapter},
        recorder=lambda record: record_call(engine, record),
        ledger=DatabaseLedger(engine),
        persona_loader=DatabasePersonaLoader(engine),
        verify_provenance=verifier(engine),
        observe_block=lambda message: None,
    )


# --- the qualification target is not a capability --------------------------------------


def test_a_qualification_target_never_equals_or_hashes_as_a_capability_profile() -> None:
    assert QualificationTarget.PARTNER != CapabilityProfile.PARTNER
    assert QualificationTarget.PARTNER != "partner"
    assert CapabilityProfile.PARTNER not in frozenset({QualificationTarget.PARTNER})
    assert QualificationTarget.PARTNER not in frozenset({CapabilityProfile.PARTNER})


def test_qualification_metadata_satisfies_no_production_requirement() -> None:
    config = sol()
    assert config.qualification_targets == frozenset({QualificationTarget.PARTNER})
    assert config.capability_profiles == frozenset()
    for task in TaskType:
        assert not satisfies_profile(config, required_profile(task)), task


def test_qualification_metadata_does_not_make_the_entry_active_or_routable() -> None:
    config = sol()
    assert config not in active()
    assert config.admission is Admission.NOT_ADMITTED and config.fallback_slug is None
    assert all(other.fallback_slug != SOL for other in REGISTRY)
    for profile in CapabilityProfile:
        chosen = candidates(
            (*REGISTRY, config),  # even offered alongside the whole registry
            Classification.PROTECTED,
            lambda c: True,
            lambda c: True,
            profile=profile,
            cost_bound=lambda c: c.cost_per_mtok_in_usd,
        )
        assert SOL not in {c.slug for c in chosen}, profile
    # Pin moved 16 September 2026, and again later that day under the owner ruling
    # authorising the one Local Partner challenger: the registry holds exactly the
    # two local LM Studio evaluation entries carrying a target — GPT-OSS-20B and the
    # Qwen3.8-27B challenger — both NOT_ADMITTED with no profile, and no other.
    with_targets = [entry for entry in under_evaluation() if entry.qualification_targets]
    # ...and again on 17 September 2026 for the Category-A Mistral challenger.
    # ...and on 18 September 2026 for Gemma 4 31B on the second LOCAL provider.
    assert sorted(entry.slug for entry in with_targets) == [
        "gemma-4-31b-q6k-llamacpp",
        "gpt-oss-20b-mxfp4-mlx-lmstudio",
        "mistral-small-3-2-24b-8bit-mlx-lmstudio",
        "qwen3-8-27b-mlx-6bit-lmstudio",
    ]
    assert all(entry.admission is Admission.NOT_ADMITTED for entry in with_targets)
    assert all(entry.capability_profiles == frozenset() for entry in with_targets)


def test_the_registry_refuses_a_target_on_an_admitted_or_profiled_entry() -> None:
    opus = by_slug("opus-5-medium")
    assert opus is not None
    with pytest.raises(ValueError, match="qualification targets belong to a NOT_ADMITTED"):
        ModelConfig(**{**opus.model_dump(), "qualification_targets": {QualificationTarget.PARTNER}})
    with pytest.raises(ValueError, match="qualification targets belong to a NOT_ADMITTED"):
        ModelConfig(
            **{
                **sol().model_dump(),
                "capability_profiles": {CapabilityProfile.STRUCTURED},
            }
        )
    admitted_sol = by_slug("gpt-5-6-sol-medium")
    assert admitted_sol is not None and admitted_sol.qualification_targets == frozenset()


def test_no_serving_route_carries_a_qualification_target() -> None:
    assert all(config.qualification_targets == frozenset() for config in active())


# --- production cannot reach the lane -------------------------------------------------------


def test_a_plain_gateway_has_no_candidate_method_and_refuses_a_candidate(store: Engine) -> None:
    adapter = Recording(script())
    gateway = plain(store, adapter)
    assert not isinstance(gateway, CandidateGateway)
    assert not hasattr(gateway, "converse_candidate")
    with pytest.raises(GatewayError) as refused:
        deliberate.send(
            store,
            gateway,
            MIXED,
            catalogue=catalogue(store),
            signals=ProjectSignals(explicit_no_project=True),
            candidate=sol(),
        )
    assert refused.value.kind is GatewayErrorKind.INVALID_REQUEST
    assert adapter.calls == 0
    with store.connect() as connection:
        assert connection.execute(text("select count(*) from messages")).scalar_one() == 0


def test_the_pinned_production_path_still_refuses_the_candidate(store: Engine) -> None:
    gateway = plain(store, Recording(script()))
    for task in (TaskType.CONVERSATION, TaskType.BLIND_POSITION):
        with pytest.raises(GatewayError) as refused:
            gateway._verify_named_configuration(sol(), Classification.PROTECTED, task)
        assert refused.value.kind is GatewayErrorKind.NO_ELIGIBLE_ROUTE


def test_the_structured_evaluation_door_still_refuses_tasks_in_which_val_speaks(
    store: Engine,
) -> None:
    adapter = Recording(script())
    gateway = lane(store, adapter)
    request = GatewayRequest(
        task_type=TaskType.BLIND_POSITION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="q"),),
        system="persona",
        output_schema={"type": "object"},
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
        persona=PersonaAttribution(persona_id=uuid4()),
    )
    with pytest.raises(GatewayError) as refused:
        gateway.evaluate_with_configuration(request, sol())
    assert refused.value.kind is GatewayErrorKind.INVALID_REQUEST
    assert adapter.calls == 0


def test_production_startup_builds_a_plain_gateway_only() -> None:
    import inspect

    from val_gateway import startup

    source = inspect.getsource(startup)
    assert "CandidateGateway" not in source and "candidate_gateway_for_scratch_store" not in source
    assert "Gateway(" in source


# --- the scratch-store requirement ----------------------------------------------------------


def test_the_factory_refuses_a_store_that_is_not_scratch() -> None:
    live_shaped = create_engine("postgresql+psycopg://refused.invalid/val")
    with pytest.raises(ScratchStoreRequiredError, match="_test"):
        scratch_store_or_refuse(live_shaped)
    with pytest.raises(ScratchStoreRequiredError):
        candidate_gateway_for_scratch_store(
            live_shaped,
            adapters={},
            recorder=lambda record: None,
            ledger=DatabaseLedger(live_shaped),
            persona_loader=DatabasePersonaLoader(live_shaped),
            verify_provenance=lambda request: None,
        )
    scratch_store_or_refuse(create_engine("postgresql+psycopg://refused.invalid/val_test"))


# --- the lane's own refusals -----------------------------------------------------------------


def _blind_request(persona_id: object) -> GatewayRequest:
    return GatewayRequest(
        task_type=TaskType.BLIND_POSITION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="State your position."),),
        system="persona",
        output_schema={"type": "object"},
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
        persona=PersonaAttribution(persona_id=persona_id),  # type: ignore[arg-type]
    )


def test_the_lane_refuses_unmarked_copied_retired_and_admitted_configurations(
    store: Engine,
) -> None:
    adapter = Recording(script())
    gateway = lane(store, adapter)
    persona_id = DatabasePersonaLoader(store).active().id
    unmarked = by_slug("gpt-5-6-terra")
    admitted = by_slug("opus-5-medium")
    retired = next(c for c in REGISTRY if c.retired)
    assert unmarked is not None and admitted is not None
    copied = sol().model_copy(update={"cost_per_mtok_in_usd": 0.01})
    for config, expected in (
        (unmarked, "no qualification target"),
        (admitted, "not a candidate"),
        (retired, "retired"),
        (copied, "not the Model Configuration Registry's entry"),
    ):
        with pytest.raises(GatewayError) as refused:
            gateway.complete_candidate(_blind_request(persona_id), config)
        assert refused.value.kind is GatewayErrorKind.NO_ELIGIBLE_ROUTE
        assert expected in refused.value.detail, config.slug
    assert adapter.calls == 0
    with store.connect() as connection:
        assert connection.execute(text("select count(*) from model_calls")).scalar_one() == 0


def test_the_lane_refuses_a_stale_persona_attribution(store: Engine) -> None:
    adapter = Recording(script())
    gateway = lane(store, adapter)
    with pytest.raises(GatewayError) as refused:
        gateway.complete_candidate(_blind_request(uuid4()), sol())
    assert "active persona" in refused.value.detail
    assert adapter.calls == 0


def test_the_lane_refuses_a_task_that_is_not_partner_class(store: Engine) -> None:
    gateway = lane(store, Recording(script()))
    request = GatewayRequest(
        task_type=TaskType.STRIP,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="q"),),
        output_schema={"type": "object"},
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
    )
    with pytest.raises(GatewayError) as refused:
        gateway.complete_candidate(request, sol())
    assert refused.value.kind is GatewayErrorKind.INVALID_REQUEST


def test_the_lane_refuses_restricted_content_before_any_call(store: Engine) -> None:
    adapter = Recording(script())
    gateway = lane(store, adapter)
    with pytest.raises(GatewayError) as refused:
        gateway.converse_candidate(
            (Message(role="user", content="my key is sk-ant-api03-" + "a" * 40),),
            scope=ExplicitNoProject(),
            turn=TurnReference(conversation_id=uuid4(), message_id=uuid4()),
            configuration=sol(),
        )
    assert refused.value.kind is GatewayErrorKind.RESTRICTED_CONTENT
    assert adapter.calls == 0


# --- a candidate exchange, end to end ------------------------------------------------------


def test_a_deliberated_exchange_pins_only_the_partner_calls_to_the_candidate(
    store: Engine,
) -> None:
    adapter = Recording(script())
    gateway = lane(store, adapter)
    outcome = deliberate.send(
        store,
        gateway,
        MIXED,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
        candidate=sol(),
    )
    assert isinstance(outcome, deliberate.DeliberatedTurn)
    assert outcome.blind is not None and outcome.deliberation is not None
    assert outcome.deliberation.outcome.value == "held"

    slugs = [slug for slug, _, _ in adapter.sent]
    assert slugs[0] == "haiku-4-5-20251001", "classification on its normal structured route"
    assert slugs[1] == "sonnet-5-low", "strip on its designated route"
    assert slugs[2:] == [SOL, SOL], "only the blind position and the response are pinned"
    assert PREFERENCE not in "\n".join(m for m in [adapter.sent[2][1] or ""]), "persona only"

    persona_id = DatabasePersonaLoader(store).active().id
    with store.connect() as connection:
        rows = connection.execute(
            text(
                "select m.task_type::text, m.model_config_id::text, m.persona_id::text, "
                "       m.status::text, m.cost::text, x.exchange_message_id is not null "
                "  from model_calls m join model_call_measurements x on x.model_call_id = m.id "
                " order by m.created_at"
            )
        ).all()
        reservations = connection.execute(
            text(
                "select task_type::text, slug, state::text, exchange_message_id is not null "
                "from budget_reservations order by created_at"
            )
        ).all()
    assert [r[0] for r in rows] == ["classification", "strip", "blind_position", "conversation"]
    for task, config_id, persona, status, cost, in_exchange in rows[2:]:
        assert config_id == str(sol().id), f"{task} recorded under the candidate's own identity"
        assert persona == str(persona_id), "the active persona, attributed"
        assert status == "ok" and cost is not None and in_exchange
    assert [(r[0], r[1], r[2]) for r in reservations][2:] == [
        ("blind_position", SOL, "settled"),
        ("conversation", SOL, "settled"),
    ]
    assert all(r[3] for r in reservations)
    assert outcome.blind.confidence is Confidence.MEDIUM


def test_the_candidate_response_carries_val_core_state(store: Engine) -> None:
    """Persona whole, record state and capability state — the same request as production."""
    from val_gateway.context import STATE_ENVELOPE_MARKER

    captured: list[tuple[Message, ...]] = []

    class Capturing(Recording):
        def complete(
            self,
            config: ModelConfig,
            messages: tuple[Message, ...],
            system: str | None,
            max_output_tokens: int,
            output_schema: Mapping[str, object] | None = None,
            cache_ttl: CacheTtl | None = None,
        ) -> ProviderResult:
            captured.append(messages)
            return super().complete(
                config, messages, system, max_output_tokens, output_schema, cache_ttl
            )

    adapter = Capturing(script())
    deliberate.send(
        store,
        lane(store, adapter),
        MIXED,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
        candidate=sol(),
    )
    response_messages = captured[3]
    state = next(m for m in response_messages if m.content.startswith(STATE_ENVELOPE_MARKER))
    document = json.loads(state.content.split("\n", 1)[1])["prior_record_state"]
    assert document["capability_state"] == {"books": "unavailable"}
    persona = DatabasePersonaLoader(store).active()
    assert adapter.sent[3][1] == persona.content, "the whole active persona, verbatim"


def test_a_candidate_failure_is_visible_recorded_and_never_retried_elsewhere(
    store: Engine,
) -> None:
    steps = script()
    steps[2] = GatewayError(GatewayErrorKind.PROVIDER_ERROR, "sol is down")
    steps.insert(3, GatewayError(GatewayErrorKind.PROVIDER_ERROR, "sol is down"))
    adapter = Recording(steps)
    outcome = deliberate.send(
        store,
        lane(store, adapter),
        MIXED,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
        candidate=sol(),
    )
    assert isinstance(outcome, deliberate.UnansweredTurn)
    assert outcome.error.kind is GatewayErrorKind.PROVIDER_ERROR
    slugs = [slug for slug, _, _ in adapter.sent]
    assert slugs[2:] == [SOL], "one blind attempt on the candidate; no other route was tried"
    with store.connect() as connection:
        failed = connection.execute(
            text(
                "select model_config_id::text, status::text, cost_certainty::text "
                "from model_calls where task_type = 'blind_position'"
            )
        ).all()
    assert failed == [(str(sol().id), "error", "unknown")], "the failure is on the record"
