"""The local route through Val Core: known $0, telemetry, provenance, the lane — 16 September 2026.

Real PostgreSQL scratch store, a scripted `lmstudio` adapter (no network). What
is pinned: an unmetered local call reserves $0, settles at a KNOWN $0 whether
or not usage was reported, records tokens only when reported, carries persona
attribution and full provenance and measurement rows; a failed local attempt
is a known $0 too; the metered protections against a fabricated zero are
untouched; the candidate lane admits the entry only through its qualification
target; and — Ruling 3a — the number of provider calls one exchange can make on
a $0 route is bounded by the orchestration itself, not by money.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

import pytest
from sqlalchemy import Engine, text
from test_candidate_lane import (
    MIXED,
    QUESTION,
    ok,
    script,
)
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
    TaskType,
    TerminalState,
    TurnReference,
)
from val_domain.project import ExplicitNoProject
from val_domain.provider import ProviderResult
from val_domain.registry import by_slug
from val_gateway import conversations, deliberate
from val_gateway.candidate import CandidateGateway, candidate_gateway_for_scratch_store
from val_gateway.deliberate import DeliberatedTurn
from val_gateway.ledger import DatabaseLedger
from val_gateway.loop import TruncatedTurn, UnansweredTurn
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader
from val_gateway.provenance import verifier
from val_policy.project_resolution import ProjectSignals

LOCAL = "gpt-oss-20b-mxfp4-mlx-lmstudio"


_REGISTERED: ModelConfig | None = by_slug(LOCAL)
assert _REGISTERED is not None
#: The entry as a test exercises it: the registered entry (32,768, the verified
#: live runtime state of 16 September 2026) unless a test takes `wide_window`,
#: which installs the same entry at the model's architectural context in the
#: registry lookups exactly as `test_candidate_lane` installs its synthetic
#: candidate. The orchestration-bound tests take it because they prove call
#: counts, not the window: at 32,768 the house byte bound refuses the
#: consequential response call itself — pinned below as evidence.
_ACTIVE: ModelConfig = _REGISTERED


def local() -> ModelConfig:
    return _ACTIVE


@pytest.fixture
def wide_window(monkeypatch: pytest.MonkeyPatch) -> ModelConfig:
    global _ACTIVE
    from val_gateway import candidate as candidate_module
    from val_gateway import gateway as gateway_module

    wide = _REGISTERED.model_copy(update={"context_window_tokens": 131_072})
    original = candidate_module.by_id

    def by_id(identifier: object) -> ModelConfig | None:
        return wide if identifier == wide.id else original(identifier)  # type: ignore[arg-type]

    monkeypatch.setattr(candidate_module, "by_id", by_id)
    monkeypatch.setattr(gateway_module, "by_id", by_id)
    _ACTIVE = wide
    yield wide
    _ACTIVE = _REGISTERED


@dataclass
class Recording:
    """One scripted provider registered under every provider name, remembering each call."""

    steps: list[ProviderResult | Exception]
    name: str = "scripted"
    calls: int = 0
    sent: list[tuple[str, str | None, int]] = field(default_factory=list)

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
        self.sent.append((config.slug, system, max_output_tokens))
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def lane(engine: Engine, adapter: Recording) -> CandidateGateway:
    return candidate_gateway_for_scratch_store(
        engine,
        adapters={"anthropic": adapter, "openai": adapter, "lmstudio": adapter},
        recorder=lambda record: record_call(engine, record),
        ledger=DatabaseLedger(engine),
        persona_loader=DatabasePersonaLoader(engine),
        verify_provenance=verifier(engine),
        observe_block=lambda message: None,
    )


def local_answer(
    text_body: str = "Good evening, my lord.", *, usage: bool = True
) -> ProviderResult:
    return ProviderResult(
        text_body,
        TerminalState.COMPLETE,
        6_000 if usage else None,
        120 if usage else None,
        None,
        reasoning_present=True,
        reasoning_tokens=40 if usage else None,
        provider_reported_model="openai/gpt-oss-20b",
        runtime_diagnostics={"runtime": "LM Studio", "loaded_context_length": 32_768},
    )


def a_turn(engine: Engine) -> TurnReference:
    conversation = conversations.create(engine, scope=ExplicitNoProject(), title="local")
    message = conversations.append(engine, conversation.id, role=StoredRole.USER, content="Hello.")
    return TurnReference(conversation_id=conversation.id, message_id=message.id)


def _rows(engine: Engine) -> list[dict[str, object]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "select c.provider, c.model_identifier, c.model_config_id, c.cost, "
                "       c.cost_certainty::text as certainty, c.status::text as status, "
                "       c.tokens_in, c.tokens_out, c.persona_id, "
                "       c.terminal_state::text as terminal, "
                "       m.reasoning_present, m.reasoning_output_tokens, m.streamed, "
                "       m.first_text_ms, "
                "       m.provider_reported_model, m.runtime_diagnostics, m.text_output_chars, "
                "       r.max_cost, r.settled_cost, r.state::text as reservation "
                "  from model_calls c "
                "  join model_call_measurements m on m.model_call_id = c.id "
                "  left join budget_reservations r on r.model_call_id = c.id "
                " order by c.created_at"
            )
        ).mappings()
        return [dict(row) for row in rows]


def _converse(engine: Engine, adapter: Recording) -> object:
    gateway = lane(engine, adapter)
    turn = a_turn(engine)
    return gateway.converse_candidate(
        (Message(role="user", content="Hello."),),
        scope=ExplicitNoProject(),
        classification=Classification.PROTECTED,
        turn=turn,
        configuration=local(),
        max_output_tokens=6_144,
    )


# --- known $0 with full telemetry and provenance -----------------------------------


def test_a_local_call_settles_at_a_known_zero_with_tokens_and_provenance(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    adapter = Recording([local_answer()])
    response = _converse(store, adapter)
    assert getattr(response, "text", None) == "Good evening, my lord."
    (row,) = _rows(store)
    assert row["provider"] == "lmstudio" and row["model_identifier"] == "openai/gpt-oss-20b"
    assert row["model_config_id"] == local().id
    assert row["cost"] == Decimal("0.000000") and row["certainty"] == "known"
    assert (row["tokens_in"], row["tokens_out"]) == (6_000, 120), "telemetry recorded"
    assert row["reasoning_present"] is True and row["reasoning_output_tokens"] == 40
    assert row["persona_id"] is not None, "a candidate turn is a Val turn: persona attributed"
    assert row["status"] == "ok" and row["terminal"] == "complete"
    assert row["streamed"] is False and row["first_text_ms"] is None
    assert row["provider_reported_model"] == "openai/gpt-oss-20b"
    diagnostics = row["runtime_diagnostics"]
    assert diagnostics["hosting"] == "local" and diagnostics["runtime"] == "LM Studio"
    assert diagnostics["loaded_context_length"] == 32_768
    assert row["max_cost"] == Decimal("0.000000"), "a zero monetary reservation"
    assert row["settled_cost"] == Decimal("0.000000") and row["reservation"] == "settled"
    assert adapter.sent[0][1] is not None and len(adapter.sent[0][1]) > 1_000, "persona, whole"


def test_missing_usage_keeps_the_known_zero_and_records_tokens_as_unknown(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    adapter = Recording([local_answer(usage=False)])
    _converse(store, adapter)
    (row,) = _rows(store)
    assert row["cost"] == Decimal("0.000000") and row["certainty"] == "known"
    assert row["tokens_in"] is None and row["tokens_out"] is None
    assert row["reasoning_output_tokens"] is None, "token telemetry is its own fact"
    assert row["text_output_chars"] == len("Good evening, my lord.")
    assert row["settled_cost"] == Decimal("0.000000")


def test_a_failed_local_attempt_is_a_known_zero_and_still_a_row(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    adapter = Recording(
        [GatewayError(GatewayErrorKind.PROVIDER_ERROR, "lmstudio: cannot reach the local server")]
    )
    with pytest.raises(GatewayError) as failed:
        _converse(store, adapter)
    assert failed.value.kind is GatewayErrorKind.PROVIDER_ERROR
    (row,) = _rows(store)
    assert row["status"] == "error" and row["terminal"] == "failed"
    assert row["cost"] == Decimal("0.000000") and row["certainty"] == "known"
    assert row["tokens_in"] is None
    assert row["runtime_diagnostics"]["hosting"] == "local"


def test_the_metered_fabricated_zero_protection_is_untouched(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    """A metered route with missing usage is still UNKNOWN, settled at its maximum."""
    from gateway_fakes import StubAdapter

    from val_gateway.gateway import Gateway

    adapter = StubAdapter(
        ProviderResult("Two o'clock, my lord.", TerminalState.COMPLETE, None, None, "r"),
        name="openai",
    )
    gateway = Gateway(
        adapters={"anthropic": adapter, "openai": adapter, "lmstudio": adapter},
        recorder=lambda record: record_call(store, record),
        ledger=DatabaseLedger(store),
        persona_loader=DatabasePersonaLoader(store),
        verify_provenance=verifier(store),
        observe_block=lambda message: None,
    )
    turn = a_turn(store)
    metered = by_slug("gpt-5-6-sol-medium")
    assert metered is not None
    gateway.converse(
        (Message(role="user", content="Hello."),),
        scope=ExplicitNoProject(),
        turn=turn,
        max_output_tokens=6_144,
        # Named, not routed to: the ordinary partner route is local since 21
        # September 2026, and this test is about what a *metered* route records.
        configuration=metered,
    )
    (row,) = _rows(store)
    assert row["provider"] == "openai" and row["cost"] is None and row["certainty"] == "unknown"
    assert row["settled_cost"] == row["max_cost"] and row["max_cost"] > 0
    assert row["runtime_diagnostics"]["hosting"] == "cloud"


# --- the candidate lane's door -------------------------------------------------------


def test_the_lane_admits_the_local_entry_only_through_its_qualification_target(
    store: Engine,  # noqa: F811 - pytest fixture injection
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = Recording([local_answer()])
    gateway = lane(store, adapter)
    gateway._verify_candidate_configuration(
        local(), Classification.PROTECTED, TaskType.CONVERSATION
    )
    gateway._verify_candidate_configuration(
        local(), Classification.PROTECTED, TaskType.BLIND_POSITION
    )
    with pytest.raises(GatewayError) as restricted:
        gateway._verify_candidate_configuration(
            local(), Classification.RESTRICTED, TaskType.CONVERSATION
        )
    assert restricted.value.kind is GatewayErrorKind.NO_ELIGIBLE_ROUTE

    from val_gateway import candidate as candidate_module
    from val_gateway import gateway as gateway_module

    without_target = local().model_copy(update={"qualification_targets": frozenset()})
    monkeypatch.setattr(candidate_module, "by_id", lambda _id: without_target)
    monkeypatch.setattr(gateway_module, "by_id", lambda _id: without_target)
    with pytest.raises(GatewayError) as refused:
        gateway._verify_candidate_configuration(
            without_target, Classification.PROTECTED, TaskType.CONVERSATION
        )
    assert refused.value.kind is GatewayErrorKind.NO_ELIGIBLE_ROUTE
    assert "carries no qualification target" in refused.value.detail
    assert adapter.calls == 0


# --- Ruling 3a: what bounds calls on a zero-monetary-reservation route -----------------


def test_one_consequential_exchange_on_the_zero_route_makes_at_most_four_calls(
    store: Engine,  # noqa: F811 - pytest fixture injection
    wide_window: ModelConfig,
) -> None:
    """Classification, strip, blind position, response — the orchestration's fixed
    sequence, each step bounded in code; no step loops, and money never enters it."""
    steps = script()
    steps[2] = ok(
        '{"position": "Open on the close-up.", "confidence": "medium", "reasoning": "Hands."}'
    )
    adapter = Recording(steps)
    outcome = deliberate.send(
        store,
        lane(store, adapter),
        MIXED,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
        candidate=local(),
    )
    assert isinstance(outcome, DeliberatedTurn)
    assert adapter.calls == 4
    slugs = [slug for slug, _, _ in adapter.sent]
    assert slugs[2] == LOCAL and slugs[3] == LOCAL, "blind and response pinned to the candidate"
    assert slugs[0] != LOCAL and slugs[1] != LOCAL, "classification and strip on their own routes"
    rows = _rows(store)
    local_rows = [row for row in rows if row["provider"] == "lmstudio"]
    assert len(local_rows) == 2 and all(r["cost"] == Decimal("0.000000") for r in local_rows)
    assert all(r["certainty"] == "known" for r in local_rows)


def test_a_truncated_local_response_is_not_retried_on_the_zero_route(
    store: Engine,  # noqa: F811 - pytest fixture injection
    wide_window: ModelConfig,
) -> None:
    steps = script()[:3]
    steps.append(
        ProviderResult(
            "The feud begins with François, and—",
            TerminalState.TRUNCATED,
            6_000,
            6_144,
            None,
            provider_reported_model="openai/gpt-oss-20b",
        )
    )
    adapter = Recording(steps)
    outcome = deliberate.send(
        store,
        lane(store, adapter),
        MIXED,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
        candidate=local(),
    )
    assert isinstance(outcome, DeliberatedTurn) and isinstance(outcome.turn, TruncatedTurn)
    assert adapter.calls == 4, "no fifth call: a truncated response is a fragment, not a retry"
    with store.connect() as connection:
        assert (
            connection.execute(
                text("select count(*) from messages where role = 'val'")
            ).scalar_one()
            == 0
        )


def test_an_ordinary_exchange_on_the_zero_route_makes_at_most_two_calls(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    adapter = Recording(
        [
            ok('{"verdict": "not_consequential", "hard_exclusion": "no_choice_present"}'),
            local_answer(),
        ]
    )
    outcome = deliberate.send(
        store,
        lane(store, adapter),
        QUESTION,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
        candidate=local(),
    )
    assert isinstance(outcome, DeliberatedTurn)
    assert adapter.calls == 2, "classification, then one response — nothing else can run"


# --- the registered window fails closed -----------------------------------------------


def test_the_registered_window_refuses_an_oversized_turn_locally(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    """At the registered 32,768 window a request whose byte bound cannot fit beside the
    6,144 ceiling is refused before any call — nothing transmitted, nothing reserved, no
    row. The window is the registry's, never the server's to truncate around."""
    assert _REGISTERED.context_window_tokens == 32_768
    adapter = Recording([local_answer()])
    gateway = lane(store, adapter)
    turn = a_turn(store)
    with pytest.raises(GatewayError) as refused:
        gateway.converse_candidate(
            (Message(role="user", content="x" * 40_000),),
            scope=ExplicitNoProject(),
            classification=Classification.PROTECTED,
            turn=turn,
            configuration=local(),
            max_output_tokens=6_144,
        )
    assert refused.value.kind is GatewayErrorKind.INVALID_REQUEST
    assert "cannot fit" in refused.value.detail and "nothing was routed" in refused.value.detail
    assert adapter.calls == 0 and _rows(store) == []


def test_at_the_registered_window_the_consequential_response_call_is_refused_by_the_byte_bound(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    """Evidence for the preflight ruling, 16 September 2026: at 32,768 the response call of
    a consequential exchange — persona, envelopes and the reconciliation framing, bounded
    in bytes — cannot fit beside the 6,144 ceiling. Classification, strip and the blind
    call ran; the response was refused locally, no fourth call left the machine, no local
    row was written for it, and the turn ended unanswered. The guard is not weakened here;
    the bound's fit for local windows is the owner's ruling."""
    assert _REGISTERED.context_window_tokens == 32_768
    steps = script()
    steps[2] = ok(
        '{"position": "Open on the close-up.", "confidence": "medium", "reasoning": "Hands."}'
    )
    adapter = Recording(steps)
    outcome = deliberate.send(
        store,
        lane(store, adapter),
        MIXED,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
        candidate=_REGISTERED,
    )
    assert isinstance(outcome, UnansweredTurn)
    assert "cannot fit" in str(outcome.error) and "nothing was routed" in str(outcome.error)
    assert adapter.calls == 3, "classification, strip, blind — the response never left"
    assert [slug for slug, _, _ in adapter.sent][2] == LOCAL, "the blind call fit and ran locally"
    with store.connect() as connection:
        assert (
            connection.execute(
                text("select count(*) from messages where role = 'val'")
            ).scalar_one()
            == 0
        )
