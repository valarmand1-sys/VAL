"""The exact local context preflight through Val Core — ruling of 16 September 2026.

Real PostgreSQL scratch store, the candidate lane, a scripted `lmstudio`
adapter that also reports a scripted exact measurement (no SDK, no socket).
Pinned: the runtime's window governs, never the registry's nominal figure;
an unavailable measurement fails closed on the byte bound; the 6,144 reserve
is the whole output; parity is recorded on the row; cloud routes never take
the exact path; and the early refusal skips only calls that had not become
necessary.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

import pytest
from sqlalchemy import Engine, text
from test_candidate_lane import MIXED, QUESTION, ok, script
from test_conversation_memory import (  # noqa: F401 - pytest fixture injection
    catalogue,
    clean_personas,
    store,
)

from val_domain.conversation import StoredRole
from val_domain.gateway import (
    CacheTtl,
    Classification,
    GatewayError,
    GatewayErrorKind,
    Message,
    ModelConfig,
    TerminalState,
    TurnReference,
)
from val_domain.project import ExplicitNoProject
from val_domain.provider import (
    ContextFeasibility,
    ContextInspectionUnavailableError,
    ProviderResult,
)
from val_domain.registry import by_slug
from val_gateway import conversations, deliberate
from val_gateway.candidate import CandidateGateway, candidate_gateway_for_scratch_store
from val_gateway.deliberate import DeliberatedTurn
from val_gateway.gateway import Gateway
from val_gateway.ledger import DatabaseLedger
from val_gateway.loop import UnansweredTurn
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader
from val_gateway.provenance import verifier
from val_policy.project_resolution import ProjectSignals

LOCAL = "gpt-oss-20b-mxfp4-mlx-lmstudio"


def local() -> ModelConfig:
    config = by_slug(LOCAL)
    assert config is not None
    return config


@dataclass
class Measuring:
    """A scripted provider that also reports a scripted exact measurement."""

    steps: list[ProviderResult | Exception]
    prompt_tokens: int | None = 5_417
    context_tokens: int | None = 32_768
    name: str = "scripted"
    calls: int = 0
    measured: int = 0
    sent: list[tuple[str, str | None]] = field(default_factory=list)

    def measure_context(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int | None = None,
    ) -> ContextFeasibility:
        self.measured += 1
        if self.prompt_tokens is None or self.context_tokens is None:
            raise ContextInspectionUnavailableError("scripted: runtime unavailable")
        return ContextFeasibility(
            prompt_tokens=self.prompt_tokens,
            context_tokens=self.context_tokens,
            source="scripted",
            details={"instance_identifier": config.model_identifier},
        )

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
        self.sent.append((config.slug, system))
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def local_answer(prompt_tokens: int = 5_417) -> ProviderResult:
    return ProviderResult(
        "Good evening, my lord.",
        TerminalState.COMPLETE,
        prompt_tokens,
        120,
        None,
        reasoning_present=True,
        reasoning_tokens=40,
        provider_reported_model="openai/gpt-oss-20b",
    )


def lane(engine: Engine, adapter: Measuring) -> CandidateGateway:
    return candidate_gateway_for_scratch_store(
        engine,
        adapters={"anthropic": adapter, "openai": adapter, "lmstudio": adapter},
        recorder=lambda record: record_call(engine, record),
        ledger=DatabaseLedger(engine),
        persona_loader=DatabasePersonaLoader(engine),
        verify_provenance=verifier(engine),
        observe_block=lambda message: None,
    )


def a_turn(engine: Engine) -> TurnReference:
    conversation = conversations.create(engine, scope=ExplicitNoProject(), title="local")
    message = conversations.append(engine, conversation.id, role=StoredRole.USER, content="Hello.")
    return TurnReference(conversation_id=conversation.id, message_id=message.id)


def _converse(engine: Engine, adapter: Measuring, content: str = "Hello.") -> object:
    gateway = lane(engine, adapter)
    turn = a_turn(engine)
    return gateway.converse_candidate(
        (Message(role="user", content=content),),
        scope=ExplicitNoProject(),
        classification=Classification.PROTECTED,
        turn=turn,
        configuration=local(),
        max_output_tokens=6_144,
    )


def _diagnostics(engine: Engine) -> list[dict[str, object]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "select c.provider, c.cost, c.cost_certainty::text as certainty, c.tokens_in, "
                "       m.runtime_diagnostics "
                "  from model_calls c join model_call_measurements m on m.model_call_id = c.id "
                " order by c.created_at"
            )
        ).mappings()
        return [dict(row) for row in rows]


# --- runtime governs, registry is nominal ---------------------------------------------------


def test_registry_32768_with_runtime_32768_admits_and_records_agreement(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    assert local().context_window_tokens == 32_768
    adapter = Measuring([local_answer()], prompt_tokens=5_417, context_tokens=32_768)
    _converse(store, adapter)
    assert adapter.measured == 1 and adapter.calls == 1
    (row,) = _diagnostics(store)
    preflight = row["runtime_diagnostics"]["preflight"]
    assert preflight["source"] == "scripted" and preflight["prompt_tokens"] == 5_417
    assert preflight["context_tokens"] == 32_768 and preflight["registry_context_tokens"] == 32_768
    assert preflight["registry_agrees"] is True
    assert row["cost"] == Decimal("0.000000") and row["certainty"] == "known"


def test_registry_32768_with_runtime_8192_evaluates_against_8192_and_refuses(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    adapter = Measuring([local_answer()], prompt_tokens=5_417, context_tokens=8_192)
    with pytest.raises(GatewayError) as refused:
        _converse(store, adapter)
    assert refused.value.kind is GatewayErrorKind.INVALID_REQUEST
    assert "loaded context is 8,192" in refused.value.detail
    assert "5,417" in refused.value.detail and "6,144" in refused.value.detail
    assert adapter.calls == 0 and _diagnostics(store) == [], "nothing sent, nothing recorded"


def test_a_disagreement_between_runtime_and_registry_is_recorded_when_the_call_fits(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    adapter = Measuring(
        [local_answer(prompt_tokens=1_000)], prompt_tokens=1_000, context_tokens=8_192
    )
    _converse(store, adapter)
    (row,) = _diagnostics(store)
    preflight = row["runtime_diagnostics"]["preflight"]
    assert preflight["context_tokens"] == 8_192 and preflight["registry_context_tokens"] == 32_768
    assert preflight["registry_agrees"] is False, "observable, never normalised away"


# --- the 6,144 reserve is the whole generated output --------------------------------------------


def test_the_reserve_is_total_output_at_the_exact_boundary(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    fits = Measuring([local_answer(26_624)], prompt_tokens=26_624, context_tokens=32_768)
    _converse(store, fits)
    assert fits.calls == 1
    over = Measuring([local_answer()], prompt_tokens=26_625, context_tokens=32_768)
    with pytest.raises(GatewayError) as refused:
        _converse(store, over)
    assert "reasoning and visible text together" in refused.value.detail
    assert over.calls == 0


# --- fail closed --------------------------------------------------------------------------------


def test_an_unavailable_measurement_falls_back_to_the_byte_bound(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    adapter = Measuring([local_answer()], prompt_tokens=None, context_tokens=None)
    with pytest.raises(GatewayError) as refused:
        _converse(store, adapter, content="x" * 40_000)
    assert refused.value.kind is GatewayErrorKind.INVALID_REQUEST
    assert "input bound" in refused.value.detail, "the conservative bound, not a guess"
    assert adapter.measured == 1 and adapter.calls == 0


def test_a_missing_runtime_context_fails_closed_the_same_way(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    adapter = Measuring([local_answer()], prompt_tokens=5_417, context_tokens=None)
    with pytest.raises(GatewayError) as refused:
        _converse(store, adapter, content="x" * 40_000)
    assert "input bound" in refused.value.detail and adapter.calls == 0


# --- cloud unchanged ------------------------------------------------------------------------------


def test_a_metered_cloud_route_never_takes_the_exact_path(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    adapter = Measuring([ok("Two o'clock, my lord.")], prompt_tokens=10, context_tokens=10)
    adapter.name = "openai"
    gateway = Gateway(
        adapters={"anthropic": adapter, "openai": adapter},
        recorder=lambda record: record_call(store, record),
        ledger=DatabaseLedger(store),
        persona_loader=DatabasePersonaLoader(store),
        verify_provenance=verifier(store),
        observe_block=lambda message: None,
    )
    gateway.converse(
        (Message(role="user", content="Hello."),),
        scope=ExplicitNoProject(),
        turn=a_turn(store),
        max_output_tokens=6_144,
    )
    assert adapter.measured == 0, "a metered route is never measured; the byte bound governs"
    (row,) = _diagnostics(store)
    assert row["provider"] == "openai" and "preflight" not in row["runtime_diagnostics"]


# --- parity on the row ----------------------------------------------------------------------------


def test_parity_is_recorded_exact_when_the_server_count_matches(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    adapter = Measuring([local_answer(5_417)], prompt_tokens=5_417)
    _converse(store, adapter)
    (row,) = _diagnostics(store)
    assert row["runtime_diagnostics"]["parity"] == {
        "preflight_prompt_tokens": 5_417,
        "server_prompt_tokens": 5_417,
        "difference": 0,
        "exact": True,
    }


def test_parity_is_recorded_not_exact_when_the_server_count_differs(
    store: Engine,  # noqa: F811 - pytest fixture injection
    caplog: pytest.LogCaptureFixture,
) -> None:
    adapter = Measuring([local_answer(5_431)], prompt_tokens=5_417)
    _converse(store, adapter)
    (row,) = _diagnostics(store)
    parity = row["runtime_diagnostics"]["parity"]
    assert parity["difference"] == 14 and parity["exact"] is False
    assert "parity is not exact" in caplog.text


# --- early refusal, from what is known ------------------------------------------------------------


def test_impossible_known_material_refuses_before_any_call(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    adapter = Measuring(script(), prompt_tokens=30_000, context_tokens=32_768)
    outcome = deliberate.send(
        store,
        lane(store, adapter),
        MIXED,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
        candidate=local(),
    )
    assert isinstance(outcome, UnansweredTurn)
    assert "Skipped: classification, strip, blind position, response" in str(outcome.error)
    assert "30,000" in str(outcome.error)
    assert adapter.calls == 0, "no call left the machine"
    assert adapter.measured == 1
    assert _diagnostics(store) == []


def test_feasible_known_material_proceeds_through_the_full_sequence(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    steps = script()
    steps[2] = ok(
        '{"position": "Open on the close-up.", "confidence": "medium", "reasoning": "Hands."}'
    )
    adapter = Measuring(steps, prompt_tokens=5_417, context_tokens=32_768)
    outcome = deliberate.send(
        store,
        lane(store, adapter),
        MIXED,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
        candidate=local(),
    )
    assert isinstance(outcome, DeliberatedTurn)
    assert adapter.calls == 4, "classification, strip, blind, response — the bound unchanged"
    # measured: once before classification, once for the blind call, once for the response
    assert adapter.measured == 3


def test_the_final_response_is_checked_exactly_when_its_prompt_exists(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    """The blind position fits; the response prompt, known only after the blind call,
    does not: three calls ran, the fourth was refused before it left, the turn is
    unanswered, nothing was shortened."""
    steps = script()
    steps[2] = ok(
        '{"position": "Open on the close-up.", "confidence": "medium", "reasoning": "Hands."}'
    )
    adapter = Measuring(steps, prompt_tokens=5_417, context_tokens=32_768)
    counts = iter([5_417, 5_417, 27_000])  # early check, blind call, response call

    def measure(
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int | None = None,
    ) -> ContextFeasibility:
        adapter.measured += 1
        return ContextFeasibility(next(counts), 32_768, "scripted", {})

    adapter.measure_context = measure  # type: ignore[method-assign]
    outcome = deliberate.send(
        store,
        lane(store, adapter),
        MIXED,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
        candidate=local(),
    )
    assert isinstance(outcome, UnansweredTurn)
    assert "27,000" in str(outcome.error) and "nothing was routed" in str(outcome.error)
    assert adapter.calls == 3
    with store.connect() as connection:
        assert (
            connection.execute(
                text("select count(*) from messages where role = 'val'")
            ).scalar_one()
            == 0
        )


def test_an_ordinary_exchange_measures_once_early_and_once_at_the_call(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    adapter = Measuring(
        [
            ok('{"verdict": "not_consequential", "hard_exclusion": "no_choice_present"}'),
            local_answer(),
        ],
        prompt_tokens=5_417,
    )
    outcome = deliberate.send(
        store,
        lane(store, adapter),
        QUESTION,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
        candidate=local(),
    )
    assert isinstance(outcome, DeliberatedTurn) and adapter.calls == 2 and adapter.measured == 2
