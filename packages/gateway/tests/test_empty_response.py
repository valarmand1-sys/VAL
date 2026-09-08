"""A provider result with no valid user-visible text never becomes a Val message.

Ruling, 8 September 2026. Four cases through the real orchestrator against
real PostgreSQL, with a scripted adapter: textual success; a zero-output
refusal; zero output with a recognised terminal reason; zero output with no
recognised reason. In every empty case the user message and the model call
stay, no assistant message is written, and the surfaced cause is the
provider's observed terminal fields, never an invented explanation.
"""

# ruff: noqa: F811 - `store` and `clean_personas` are fixtures imported by name
from __future__ import annotations

from sqlalchemy import Engine, text
from test_deliberation_machinery import (
    ScriptedAdapter,
    blind_positions_for,
    classifier_says,
    deliberate,
    full_script,
    ok,
    store,  # noqa: F401 - fixture reused
)
from test_persona import clean_personas  # noqa: F401 - fixture reused

from val_domain.gateway import GatewayError, GatewayErrorKind, TerminalState
from val_gateway.deliberate import DeliberatedTurn
from val_gateway.loop import Turn, UnansweredTurn
from val_providers.base import ProviderResult

ORDINARY = "What time does the read-through start on Thursday?"


def _val_messages(store: Engine, conversation_id: object) -> list[str]:
    with store.connect() as connection:
        return list(
            connection.execute(
                text("select content from messages where role = 'val' and conversation_id = :c"),
                {"c": conversation_id},
            ).scalars()
        )


def _conversation_calls(store: Engine) -> list[tuple[str, str]]:
    with store.connect() as connection:
        return [
            (row.terminal_state, row.status)
            for row in connection.execute(
                text(
                    "select terminal_state::text, status::text from model_calls "
                    "where task_type = 'conversation' order by created_at"
                )
            ).all()
        ]


def test_textual_success_is_persisted_as_before(store: Engine) -> None:
    adapter = ScriptedAdapter([classifier_says("not_consequential"), ok("Two o'clock, my lord.")])
    outcome = deliberate(store, adapter, ORDINARY)
    assert isinstance(outcome, DeliberatedTurn) and isinstance(outcome.turn, Turn)
    assert _val_messages(store, outcome.turn.conversation.id) == ["Two o'clock, my lord."]


def test_a_zero_output_refusal_ends_unanswered_with_the_providers_reason(store: Engine) -> None:
    refused = ProviderResult(
        "",
        TerminalState.REFUSED,
        6_000,
        0,
        "req",
        stop_reason="refusal",
        stop_details="{'category': 'reasoning_extraction'}",
    )
    adapter = ScriptedAdapter([classifier_says("not_consequential"), refused])
    outcome = deliberate(store, adapter, ORDINARY)

    assert isinstance(outcome, UnansweredTurn)
    assert isinstance(outcome.error, GatewayError)
    assert outcome.error.kind is GatewayErrorKind.REFUSAL
    cause = str(outcome.error)
    assert "refused" in cause and "stop_reason: refusal" in cause
    assert "reasoning_extraction" in cause, "the provider's own detail is surfaced"
    assert len(outcome.error.model_call_ids) == 1, "the call is named"
    assert _val_messages(store, outcome.conversation.id) == [], "no Val message"
    assert _conversation_calls(store) == [("refused", "refused")], "the call is recorded"


def test_zero_output_with_a_recognised_terminal_reason_names_it(store: Engine) -> None:
    cut_off = ProviderResult(
        "", TerminalState.TRUNCATED, 6_000, 0, "req", stop_reason="max_tokens", stop_details=None
    )
    adapter = ScriptedAdapter([classifier_says("not_consequential"), cut_off])
    outcome = deliberate(store, adapter, ORDINARY)

    assert isinstance(outcome, UnansweredTurn)
    assert isinstance(outcome.error, GatewayError)
    assert outcome.error.kind is GatewayErrorKind.INVALID_OUTPUT
    assert "truncated" in str(outcome.error) and "stop_reason: max_tokens" in str(outcome.error)
    assert "refus" not in str(outcome.error)
    assert _val_messages(store, outcome.conversation.id) == []


def test_zero_output_with_no_recognised_reason_states_only_the_fact(store: Engine) -> None:
    empty = ProviderResult(
        "   ", TerminalState.COMPLETE, 6_000, 0, "req", stop_reason="end_turn", stop_details=None
    )
    adapter = ScriptedAdapter([classifier_says("not_consequential"), empty])
    outcome = deliberate(store, adapter, ORDINARY)

    assert isinstance(outcome, UnansweredTurn)
    assert isinstance(outcome.error, GatewayError)
    assert outcome.error.kind is GatewayErrorKind.INVALID_OUTPUT
    cause = str(outcome.error)
    assert "no valid assistant content" in cause and "stop_reason: end_turn" in cause
    assert "refus" not in cause, "no refusal explanation is invented"
    assert "None was recognised" not in cause or "none is invented" in cause
    assert _val_messages(store, outcome.conversation.id) == []
    assert _conversation_calls(store) == [("complete", "ok")]


def test_an_empty_consequential_response_keeps_the_blind_row_and_writes_nothing_else(
    store: Engine,
) -> None:
    script = full_script()
    refused = ProviderResult(
        "", TerminalState.REFUSED, 6_000, 0, "req", stop_reason="refusal", stop_details=None
    )
    adapter = ScriptedAdapter([*script[:3], refused])
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, UnansweredTurn)
    assert isinstance(outcome.error, GatewayError)
    assert outcome.error.kind is GatewayErrorKind.REFUSAL
    assert len(blind_positions_for(store, outcome.conversation.id)) == 1, "the blind row stays"
    with store.connect() as connection:
        deliberations = connection.execute(text("select count(*) from deliberations")).scalar_one()
    assert deliberations == 0
    assert _val_messages(store, outcome.conversation.id) == []
