"""Prompt-cache diagnostics reach the measurement sidecar; the turn ceiling — 15 September 2026.

Through the real turn path on real PostgreSQL with a scripted adapter: the
cache key and the diagnostics a provider result carries are written on the
call's `model_call_measurements` row, verbatim, in the same transaction; a
result carrying none writes NULLs, never a guess; and a turn request that
states no ceiling receives the policy's 6,144 for its final conversation call.
"""

from __future__ import annotations

from sqlalchemy import Engine, text
from test_service import ScriptedAdapter, a_turn, classifier_says, client

from val_api.contracts import TurnRequest
from val_domain.gateway import TerminalState
from val_domain.provider import ProviderResult
from val_policy.budget import CONVERSATION_MAX_OUTPUT_TOKENS

DIAGNOSTICS = {
    "requested": {
        "prompt_cache_key": "val:gpt-5-6-sol-medium:0123456789abcdef",
        "prompt_cache_options": {"mode": "implicit", "ttl": "30m"},
    },
    "reported": {
        "prompt_cache_key": "val:gpt-5-6-sol-medium:0123456789abcdef",
        "prompt_cache_options": {"mode": "implicit", "ttl": "30m"},
        "prompt_cache_retention": None,
        "cached_tokens": 4_821,
        "cache_write_tokens": 500,
    },
}


def _measurement_rows(engine: Engine) -> list[tuple[str, object, object]]:
    with engine.connect() as connection:
        return [
            (row[0], row[1], row[2])
            for row in connection.execute(
                text(
                    "select c.task_type::text, m.prompt_cache_key, m.cache_diagnostics "
                    "  from model_calls c join model_call_measurements m on m.model_call_id = c.id "
                    " order by c.created_at"
                )
            ).all()
        ]


def test_the_key_and_diagnostics_are_persisted_verbatim_and_absence_is_null(store: Engine) -> None:
    answer = ProviderResult(
        "Two o'clock, my lord.",
        TerminalState.COMPLETE,
        3,
        21,
        "resp",
        cache_read_tokens=4_821,
        cache_write_auto_tokens=500,
        prompt_cache_key="val:gpt-5-6-sol-medium:0123456789abcdef",
        cache_diagnostics=DIAGNOSTICS,
    )
    api = client(store, ScriptedAdapter([classifier_says("not_consequential"), answer]))
    a_turn(api, "What time is it?")

    rows = _measurement_rows(store)
    assert [task for task, _, _ in rows] == ["classification", "conversation"]
    classification, conversation = rows
    assert classification[1] is None and classification[2] is None, (
        "the scripted classifier reports nothing about a cache; NULL, never inferred"
    )
    assert conversation[1] == "val:gpt-5-6-sol-medium:0123456789abcdef"
    assert conversation[2] == DIAGNOSTICS, "verbatim, as JSON"


def test_a_turn_request_defaults_to_the_policy_ceiling() -> None:
    assert TurnRequest(content="x").max_output_tokens == CONVERSATION_MAX_OUTPUT_TOKENS == 6_144
    assert TurnRequest(content="x", max_output_tokens=4_096).max_output_tokens == 4_096, (
        "a client may still state its own"
    )
