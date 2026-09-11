# ruff: noqa: F811, F401 - `store` and `clean_personas` are fixtures imported by name
"""The strip invariant through the orchestrator — ruling of 9 September 2026.

Real PostgreSQL, scripted adapter. An invalid structured strip result is
retried exactly once on the same route; a second invalid result is exhausted;
a valid "not separable" is never retried; and no path from an invalid result
can produce an `ordering = enforced` blind row. Ruling, 10 September 2026: no
path short of `enforceable` produces a blind call at all — the exchange
collapses to the ordinary partner-response path with the attempts on record.
"""

from __future__ import annotations

import json

from sqlalchemy import Engine
from test_deliberation_machinery import (
    CLOSE_UP,
    ScriptedAdapter,
    blind_says,
    classifier_says,
    deliberate,
    ok,
    reconciled,
    store,
    strip_says,
)
from test_persona import clean_personas

from val_domain.deliberation import Ordering
from val_domain.gateway import TerminalState
from val_gateway.deliberate import DeliberatedTurn
from val_policy.deliberation import BLIND_POSITION_OUTPUT_SCHEMA
from val_providers.base import ProviderResult

QUESTION = "Which lens for the harbour, the wide or the long?"
MESSAGE = f"{QUESTION} I'd go long now."
S7 = "Why is the wide shot the right opening for episode three?"


def _strip_calls(adapter: ScriptedAdapter) -> int:
    return sum(1 for call in adapter.sent if (call.system or "").startswith("You separate"))


def _contradictory() -> object:
    """S7: preference present, separable, nothing removed."""
    return ok(
        json.dumps(
            {
                "preference_present": True,
                "attributed_prior_present": False,
                "separable": True,
                "question": S7,
                "removed": [],
            }
        )
    )


def _blind_calls(adapter: ScriptedAdapter) -> int:
    return sum(1 for call in adapter.sent if call.output_schema == BLIND_POSITION_OUTPUT_SCHEMA)


def test_s7_contradiction_is_retried_once_and_a_valid_not_separable_collapses(
    store: Engine,
) -> None:
    adapter = ScriptedAdapter(
        [
            classifier_says("consequential"),
            _contradictory(),
            strip_says(separable=False, question=S7),
            ok("The wide shot, my lord."),
        ]
    )
    outcome = deliberate(store, adapter, S7)
    assert isinstance(outcome, DeliberatedTurn)
    assert _strip_calls(adapter) == 2, "one bounded retry"
    assert outcome.strip_states == ("invalid", "not_separable")
    assert outcome.blind is None and _blind_calls(adapter) == 0, "no blind call (10 September 2026)"
    assert len(adapter.sent) == 4, "classifier, strip, strip retry, ordinary response"


def test_two_invalid_results_exhaust_the_retry_and_collapse(store: Engine) -> None:
    adapter = ScriptedAdapter(
        [
            classifier_says("consequential"),
            _contradictory(),
            _contradictory(),
            ok("The wide shot, my lord."),
        ]
    )
    outcome = deliberate(store, adapter, S7)
    assert isinstance(outcome, DeliberatedTurn)
    assert _strip_calls(adapter) == 2, "never a third attempt"
    assert outcome.strip_states == ("invalid", "invalid")
    assert outcome.blind is None and _blind_calls(adapter) == 0


def test_a_valid_not_separable_is_never_retried(store: Engine) -> None:
    adapter = ScriptedAdapter(
        [
            classifier_says("consequential"),
            strip_says(separable=False, question=S7),
            ok("The wide shot, my lord."),
        ]
    )
    outcome = deliberate(store, adapter, S7)
    assert isinstance(outcome, DeliberatedTurn)
    assert _strip_calls(adapter) == 1
    assert outcome.strip_states == ("not_separable",)
    assert outcome.blind is None and _blind_calls(adapter) == 0


def test_a_truncated_strip_is_not_retried_and_collapses(store: Engine) -> None:
    """Ruling, 10 September 2026, Option A — through the orchestrator."""
    truncated = ProviderResult(
        '{"preference_present": true, "attributed_prior_present": false, "separable": true, "qu',
        TerminalState.TRUNCATED,
        20,
        4096,
        "req",
        stop_reason="max_tokens",
    )
    adapter = ScriptedAdapter(
        [classifier_says("consequential"), truncated, ok("The wide shot, my lord.")]
    )
    outcome = deliberate(store, adapter, MESSAGE)
    assert isinstance(outcome, DeliberatedTurn)
    assert _strip_calls(adapter) == 1, "exactly one strip provider call"
    assert outcome.strip_states == ("truncated",)
    assert outcome.blind is None and _blind_calls(adapter) == 0
    assert len(adapter.sent) == 3


def test_preference_absent_with_spans_is_invalid_then_the_retry_governs(store: Engine) -> None:
    adapter = ScriptedAdapter(
        [
            classifier_says("consequential"),
            strip_says(present=False, removed="I'd go long now.", question=QUESTION),
            strip_says(present=False, question=MESSAGE),
            ok("An ordinary answer, my lord."),
        ]
    )
    outcome = deliberate(store, adapter, MESSAGE)
    assert isinstance(outcome, DeliberatedTurn)
    assert _strip_calls(adapter) == 2
    assert outcome.strip_states == ("invalid", "no_preference")
    assert outcome.blind is None, "no preference: no blind row"


def test_a_non_verbatim_span_is_invalid_and_the_valid_retry_is_enforced(store: Engine) -> None:
    adapter = ScriptedAdapter(
        [
            classifier_says("consequential"),
            strip_says(removed="I would go long now.", question=QUESTION),
            strip_says(removed="I'd go long now.", question=QUESTION),
            blind_says(CLOSE_UP),
            reconciled("Held.", "held"),
        ]
    )
    outcome = deliberate(store, adapter, MESSAGE)
    assert isinstance(outcome, DeliberatedTurn)
    assert outcome.strip_states == ("invalid", "enforceable")
    assert outcome.blind is not None and outcome.blind.ordering is Ordering.ENFORCED
    assert adapter.sent[3].messages[0].content.endswith(QUESTION)
    assert "I'd go long now." not in adapter.sent[3].messages[0].content


def test_a_declared_attributed_prior_without_its_span_is_invalid(store: Engine) -> None:
    message = "You chose the wide last time. I'd go long now. Which lens?"
    adapter = ScriptedAdapter(
        [
            classifier_says("consequential"),
            strip_says(attributed=True, removed="I'd go long now.", question=message),
            strip_says(
                attributed=True,
                question="Which lens?",
                spans=[
                    {
                        "text": "You chose the wide last time.",
                        "occurrence": 1,
                        "kind": "attributed_prior",
                    },
                    {"text": "I'd go long now.", "occurrence": 1, "kind": "preference"},
                ],
            ),
            blind_says(CLOSE_UP),
            reconciled("Held.", "held"),
        ]
    )
    outcome = deliberate(store, adapter, message)
    assert isinstance(outcome, DeliberatedTurn)
    assert outcome.strip_states == ("invalid", "enforceable")
    assert adapter.sent[3].messages[0].content.endswith("Which lens?")
