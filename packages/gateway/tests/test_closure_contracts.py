"""Current-version closure pass, 18 August 2026 — the new contracts, proved.

Each block corresponds to a section of the closure assignment. These are the
proofs that the repaired surface refuses what it used to permit; the regression
suites elsewhere prove that nothing the foundation already guaranteed was lost.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from gateway_fakes import FakeLedger, StubAdapter
from sqlalchemy import Engine, text
from test_persona import REPO_ROOT, clean_personas  # noqa: F401 - fixture reused

from val_domain.conversation import StoredRole
from val_domain.gateway import (
    Classification,
    ConversationProvenance,
    GatewayError,
    GatewayErrorKind,
    GatewayRequest,
    Message,
    TaskType,
    TerminalState,
    TurnReference,
)
from val_domain.project import ExplicitNoProject, ProjectAttribution
from val_domain.registry import by_slug
from val_gateway import conversations
from val_gateway.conversations import ConversationNotFoundError  # noqa: F401
from val_gateway.gateway import Gateway, compute_cost
from val_gateway.loop import TruncatedTurn, Turn, send
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader, seed
from val_gateway.projects import load_catalogue
from val_gateway.provenance import verifier
from val_policy.budget import effective_rates, limit_overrun, maximum_cost
from val_policy.project_resolution import ProjectSignals
from val_providers.base import ProviderResult

# --- fixtures -----------------------------------------------------------------


@pytest.fixture
def store(clean_personas: Engine) -> Engine:  # noqa: F811 - pytest fixture injection
    seed(clean_personas, REPO_ROOT)
    with clean_personas.begin() as connection:
        connection.execute(
            text(
                "insert into projects (name, slug, description, status) "
                "values ('Project Alpha', 'project-alpha', '', 'active')"
            )
        )
    return clean_personas


def conversational_gateway(engine: Engine, adapter: StubAdapter) -> Gateway:
    return Gateway(
        adapters={"anthropic": adapter, "openai": adapter},
        recorder=lambda record: record_call(engine, record),
        ledger=FakeLedger(),
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(engine),
        verify_provenance=verifier(engine),
    )


def a_turn(engine: Engine) -> TurnReference:
    conversation = conversations.create(engine, scope=ExplicitNoProject(), title="closure")
    message = conversations.append(engine, conversation.id, role=StoredRole.USER, content="Hello.")
    return TurnReference(conversation_id=conversation.id, message_id=message.id)


def classification_request(
    content: str = "classify this", max_output_tokens: int = 4096
) -> GatewayRequest:
    """A non-conversation request that can be *recorded* against a real store.

    The shared `request()` builder fabricates a random `project_id`, which is
    fine for gateways recording into a list and refused by the foreign key the
    moment a real recorder writes it. These closure tests record for real, so
    the request is explicitly outside every project.
    """
    return GatewayRequest(
        task_type=TaskType.CLASSIFICATION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content=content),),
        max_output_tokens=max_output_tokens,
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
    )


# =============================================================================
# §2 — the generic entrances refuse conversation
# =============================================================================


def test_complete_refuses_a_conversation_request(store: Engine) -> None:
    """§2 defect A. A hand-built conversation request cannot use the generic door."""
    turn = a_turn(store)
    active = DatabasePersonaLoader(store).active()
    handbuilt = GatewayRequest(
        task_type=TaskType.CONVERSATION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="Hello."),),
        system=active.content,
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
        conversation=ConversationProvenance(
            conversation_id=turn.conversation_id,
            message_id=turn.message_id,
            persona_id=active.id,
        ),
    )
    adapter = StubAdapter(ProviderResult("hi", TerminalState.COMPLETE, 1, 1, None))
    gateway = conversational_gateway(store, adapter)

    with pytest.raises(GatewayError) as caught:
        gateway.complete(handbuilt)

    assert "goes through `converse`" in str(caught.value)
    assert adapter.calls == 0


def test_complete_with_configuration_refuses_a_conversation_request(store: Engine) -> None:
    """§2 defect B. Naming a configuration is more deliberate, not more trusted."""
    turn = a_turn(store)
    active = DatabasePersonaLoader(store).active()
    handbuilt = GatewayRequest(
        task_type=TaskType.CONVERSATION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="Hello."),),
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
        conversation=ConversationProvenance(
            conversation_id=turn.conversation_id,
            message_id=turn.message_id,
            persona_id=active.id,
        ),
    )
    adapter = StubAdapter(ProviderResult("hi", TerminalState.COMPLETE, 1, 1, None))
    gateway = conversational_gateway(store, adapter)
    config = by_slug("haiku-4-5")
    assert config is not None

    with pytest.raises(GatewayError) as caught:
        gateway.complete_with_configuration(handbuilt, config)

    assert "goes through `converse`" in str(caught.value)
    assert adapter.calls == 0


def test_a_typed_persona_uuid_is_not_enough(store: Engine) -> None:
    """§2's required proof. Coherent-looking identity that no loader produced.

    Even reaching the private execution body directly — the strongest position
    an in-process caller can take — a conversation naming a persona that is not
    the active row is refused by the verifier before transmission.
    """
    turn = a_turn(store)
    forged = GatewayRequest(
        task_type=TaskType.CONVERSATION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="Hello."),),
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
        conversation=ConversationProvenance(
            conversation_id=turn.conversation_id,
            message_id=turn.message_id,
            persona_id=uuid4(),  # typed, not loaded
        ),
    )
    adapter = StubAdapter(ProviderResult("hi", TerminalState.COMPLETE, 1, 1, None))
    gateway = conversational_gateway(store, adapter)

    with pytest.raises(GatewayError) as caught:
        gateway._execute(forged)

    assert "typed, not loaded" in str(caught.value) or "active persona row" in str(caught.value)
    assert adapter.calls == 0


def test_non_conversation_work_still_flows_through_complete(store: Engine) -> None:
    """The generic entrance still serves what it exists for."""
    adapter = StubAdapter(ProviderResult("classified", TerminalState.COMPLETE, 5, 5, "r"))
    gateway = conversational_gateway(store, adapter)

    response = gateway.complete(classification_request())

    assert response.text == "classified"
    assert adapter.calls == 1


# =============================================================================
# §3 — the conversation task type is not caller-swappable
# =============================================================================


def test_converse_and_send_expose_no_task_type_parameter() -> None:
    """§3. The label is what the function is, not an argument."""
    import inspect

    assert "task_type" not in inspect.signature(Gateway.converse).parameters
    assert "task_type" not in inspect.signature(send).parameters


def test_a_persisted_turn_is_recorded_as_conversation(store: Engine) -> None:
    """And the row says so, from the fixed label rather than a caller's choice."""
    outcome = send(
        store,
        conversational_gateway(
            store, StubAdapter(ProviderResult("Good evening.", TerminalState.COMPLETE, 5, 5, "r"))
        ),
        "Good evening, Val.",
        catalogue=load_catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )
    assert isinstance(outcome, Turn)
    with store.connect() as connection:
        recorded = connection.execute(
            text("select task_type from model_calls order by created_at desc limit 1")
        ).scalar_one()
    assert recorded == "conversation"


# =============================================================================
# §4 — terminal states
# =============================================================================


def test_a_truncated_answer_is_not_persisted_as_val_speaking(store: Engine) -> None:
    """§4. Half a sentence must not enter the record as though she finished it."""
    adapter = StubAdapter(
        ProviderResult("The answer begins but—", TerminalState.TRUNCATED, 50, 4096, "r")
    )
    outcome = send(
        store,
        conversational_gateway(store, adapter),
        "Tell me everything.",
        catalogue=load_catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )

    assert isinstance(outcome, TruncatedTurn)
    assert outcome.partial_text == "The answer begins but—"
    with store.connect() as connection:
        roles = connection.execute(text("select role from messages order by sequence")).scalars()
        assert list(roles) == ["user"], "a fragment was persisted as Val's message"
        # The call itself is honest evidence: it happened and is costed.
        row = connection.execute(
            text("select status, cost_certainty from model_calls order by created_at desc limit 1")
        ).one()
        assert row.status == "ok"
        assert row.cost_certainty == "known"


def test_a_refusal_is_val_s_deliberate_answer_and_is_persisted(store: Engine) -> None:
    """§4. A refusal is complete; it joins the record as her reply."""
    adapter = StubAdapter(
        ProviderResult("I will not do that, my lord.", TerminalState.REFUSED, 10, 10, "r")
    )
    outcome = send(
        store,
        conversational_gateway(store, adapter),
        "Do the thing.",
        catalogue=load_catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )

    assert isinstance(outcome, Turn)
    assert outcome.val_message.content == "I will not do that, my lord."
    with store.connect() as connection:
        status = connection.execute(
            text("select status from model_calls order by created_at desc limit 1")
        ).scalar_one()
    assert status == "refused"


def test_an_unknown_terminal_state_fails_closed(store: Engine) -> None:
    """§4. An unrecognised outcome is unverified, not successful.

    The call is recorded and costed — it happened — but the text is never
    handed onward, and no Val message exists.
    """
    adapter = StubAdapter(
        ProviderResult("who knows what this is", TerminalState.UNKNOWN, 10, 10, "r")
    )
    outcome = send(
        store,
        conversational_gateway(store, adapter),
        "Hello?",
        catalogue=load_catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )

    # The gateway raised; the loop preserved the unanswered user turn.
    from val_gateway.loop import UnansweredTurn

    assert isinstance(outcome, UnansweredTurn)
    assert isinstance(outcome.error, GatewayError)
    assert outcome.error.kind is GatewayErrorKind.INVALID_OUTPUT
    with store.connect() as connection:
        row = connection.execute(
            text("select status, cost_certainty from model_calls order by created_at desc limit 1")
        ).one()
        roles = list(connection.execute(text("select role from messages")).scalars())
    assert row.status == "error"
    assert row.cost_certainty == "known", "usage was reported, so the cost is known"
    assert "val" not in roles


# =============================================================================
# §5 — unknown usage never becomes zero
# =============================================================================


def test_missing_usage_is_recorded_unknown_not_zero(store: Engine) -> None:
    """§5. The OpenAI missing-usage path, formerly a fabricated known $0."""
    adapter = StubAdapter(
        ProviderResult("an answer with no usage block", TerminalState.COMPLETE, None, None, "r")
    )
    outcome = send(
        store,
        conversational_gateway(store, adapter),
        "Hello.",
        catalogue=load_catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )

    assert isinstance(outcome, Turn)
    assert outcome.response.cost_usd is None
    assert outcome.response.tokens_in is None
    with store.connect() as connection:
        row = connection.execute(
            text(
                "select tokens_in, tokens_out, cost, cost_certainty, status "
                "from model_calls order by created_at desc limit 1"
            )
        ).one()
    assert (row.tokens_in, row.tokens_out, row.cost) == (None, None, None)
    assert row.cost_certainty == "unknown"
    assert row.status == "ok"


def test_missing_usage_settles_the_reservation_at_its_maximum(store: Engine) -> None:
    """The ledger half: unknown is charged conservatively, never released."""
    adapter = StubAdapter(ProviderResult("no usage", TerminalState.COMPLETE, None, None, "r"))
    ledger = FakeLedger()
    gateway = Gateway(
        adapters={"anthropic": adapter, "openai": adapter},
        recorder=lambda record: record_call(store, record),
        ledger=ledger,
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(store),
        verify_provenance=verifier(store),
    )
    send(
        store,
        gateway,
        "Hello.",
        catalogue=load_catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )
    entries = list(ledger.entries.values())
    assert len(entries) == 1
    entry = entries[0]
    assert entry.state == "settled"
    assert entry.settled_cost_usd == pytest.approx(entry.max_cost_usd), (
        "an unknown settlement must charge the full reservation"
    )


# =============================================================================
# §7/§8 — registry-driven limits and long-context pricing
# =============================================================================


def test_an_over_cap_output_request_is_refused_not_clamped() -> None:
    """§8. Asking a 64k model for 100k output is refused in those words."""
    config = by_slug("haiku-4-5")
    assert config is not None
    reason = limit_overrun(config, ("hello",), 100_000)
    assert reason is not None and "at most" in reason


def test_an_oversized_payload_is_refused_before_any_route(store: Engine) -> None:
    """§8. Input bound + output cap beyond every window → local refusal, no call."""
    adapter = StubAdapter(ProviderResult("never", TerminalState.COMPLETE, 1, 1, None))
    gateway = conversational_gateway(store, adapter)
    vast = "x" * 2_000_000  # beyond every configured context window

    with pytest.raises(GatewayError) as caught:
        gateway.complete(classification_request(content=vast))

    assert caught.value.kind is GatewayErrorKind.NO_ELIGIBLE_ROUTE
    assert adapter.calls == 0


def test_the_budget_and_the_adapter_agree_on_max_output(store: Engine) -> None:
    """§8. The value budgeted is the value transmitted — no clamped estimate."""
    adapter = StubAdapter(ProviderResult("ok", TerminalState.COMPLETE, 5, 5, "r"))
    gateway = conversational_gateway(store, adapter)
    gateway.complete(classification_request(max_output_tokens=2048))
    assert adapter.sent_max_output_tokens == 2048


def test_long_context_pricing_reaches_the_bound_and_the_settlement() -> None:
    """§7. GPT-5.5's >272K threshold: 2x input, 1.5x output, in both figures."""
    config = by_slug("gpt-5-5")
    assert config is not None

    base_in, base_out = effective_rates(config, 100_000)
    assert (base_in, base_out) == (5.0, 30.0)

    long_in, long_out = effective_rates(config, 300_000)
    assert (long_in, long_out) == (10.0, 45.0)

    # The pre-call bound prices a >threshold payload at the multiplied rates.
    parts = ("y" * 400_000,)
    bound = maximum_cost(config, parts, 1_000)
    plain_rate_bound = (400_004 * 5.0 + 1_000 * 30.0) / 1e6
    assert bound > plain_rate_bound, "the ceiling under-reserved the largest calls"

    # And the settlement of a real >threshold call uses the same rates.
    settled = compute_cost(config, 300_000, 1_000)
    assert settled == pytest.approx((300_000 * 10.0 + 1_000 * 45.0) / 1e6)


def test_the_registry_context_window_is_the_window_not_the_threshold() -> None:
    """§7's named correction, pinned so it cannot regress."""
    config = by_slug("gpt-5-5")
    assert config is not None
    assert config.context_window_tokens == 1_050_000
    assert config.long_context_threshold_tokens == 272_000

    haiku = by_slug("haiku-4-5")
    assert haiku is not None
    assert haiku.model_identifier == "claude-haiku-4-5-20251001", (
        "the registry must pin the dated snapshot, not the movable alias"
    )
