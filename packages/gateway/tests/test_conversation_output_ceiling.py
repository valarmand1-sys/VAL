"""The final PARTNER conversation call's output ceiling — ruling, 15 September 2026.

A genuine House Armand turn on GPT-5.6 Sol (medium) hit the 4,096-token
ceiling with 2,521 reasoning tokens inside it: about 1,575 visible tokens,
`incomplete_details.reason = max_output_tokens`, no persisted message. The
final conversation call's default ceiling is now 6,144 total output tokens.
The blind-position ceiling is unchanged; a truncated final response is still
never persisted as Val's message; and it is never retried automatically —
a retry would silently double the cost of an already expensive turn.
"""

from __future__ import annotations

from sqlalchemy import Engine, text
from test_deliberation_machinery import (
    ScriptedAdapter,
    _calls_by_task,
    deliberate,
    full_script,
    store,  # noqa: F401 - pytest fixture injection
)
from test_persona import clean_personas  # noqa: F401 - pytest fixture injection

from val_domain.gateway import TerminalState
from val_domain.provider import ProviderResult
from val_gateway.deliberate import BLIND_MAX_OUTPUT_TOKENS, DeliberatedTurn
from val_gateway.loop import TruncatedTurn
from val_policy.budget import CONVERSATION_MAX_OUTPUT_TOKENS


def test_the_final_conversation_call_receives_6144_and_the_blind_call_keeps_4096(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    adapter = ScriptedAdapter(full_script())
    outcome = deliberate(store, adapter)
    assert isinstance(outcome, DeliberatedTurn)
    classify, strip, blind, response = adapter.sent
    assert CONVERSATION_MAX_OUTPUT_TOKENS == 6_144
    assert response.max_output_tokens == 6_144, "the final conversation call"
    assert blind.max_output_tokens == BLIND_MAX_OUTPUT_TOKENS == 4_096, "unchanged"
    assert classify.max_output_tokens == 256 and strip.max_output_tokens == 4_096, "unchanged"


def test_a_truncated_final_response_is_not_retried_and_not_persisted(
    store: Engine,  # noqa: F811 - pytest fixture injection
) -> None:
    cut = ProviderResult(
        "The feud begins with François, and—",
        TerminalState.TRUNCATED,
        11_889,
        6_144,
        "resp_cut",
        stop_reason="incomplete",
        stop_details="incomplete_details.reason=max_output_tokens",
    )
    adapter = ScriptedAdapter([*full_script()[:3], cut])
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn)
    assert isinstance(outcome.turn, TruncatedTurn), "the fragment is returned as a fragment"
    assert outcome.turn.partial_text == "The feud begins with François, and—"
    assert len(adapter.sent) == 4, "classification, strip, blind, one response — no retry"
    assert _calls_by_task(store)["conversation"] == 1
    with store.connect() as connection:
        val_messages = connection.execute(
            text("select count(*) from messages where role = 'val'")
        ).scalar_one()
        recorded = connection.execute(
            text(
                "select terminal_state::text, tokens_out from model_calls "
                " where task_type = 'conversation'"
            )
        ).one()
    assert val_messages == 0, "a fragment never enters the record as her message"
    assert recorded == ("truncated", 6_144), "the call itself stands, honestly, on model_calls"
