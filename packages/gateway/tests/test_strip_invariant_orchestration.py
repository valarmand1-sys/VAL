# ruff: noqa: F811, F401 - `store` and `clean_personas` are fixtures imported by name
"""The strip invariant through the orchestrator — ruling of 9 September 2026.

Real PostgreSQL, scripted adapter. An invalid structured strip result is
retried exactly once on the same route; a second invalid result is
contaminated; a valid "not separable" is never retried; and no path from an
invalid result can produce an `ordering = enforced` blind row.
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
from val_gateway.deliberate import DeliberatedTurn

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


def test_s7_contradiction_is_retried_once_and_a_valid_not_separable_is_contaminated(
    store: Engine,
) -> None:
    adapter = ScriptedAdapter(
        [
            classifier_says("consequential"),
            _contradictory(),
            strip_says(separable=False, question=S7),
            blind_says(CLOSE_UP),
            reconciled("Held.", "held"),
        ]
    )
    outcome = deliberate(store, adapter, S7)
    assert isinstance(outcome, DeliberatedTurn)
    assert _strip_calls(adapter) == 2, "one bounded retry"
    assert outcome.strip_states == ("invalid", "not_separable")
    assert outcome.blind is not None and outcome.blind.ordering is Ordering.CONTAMINATED
    assert adapter.sent[3].messages[0].content.endswith(S7), "the blind input is the whole message"


def test_two_invalid_results_fail_closed_as_contaminated(store: Engine) -> None:
    adapter = ScriptedAdapter(
        [
            classifier_says("consequential"),
            _contradictory(),
            _contradictory(),
            blind_says(CLOSE_UP),
            reconciled("Held.", "held"),
        ]
    )
    outcome = deliberate(store, adapter, S7)
    assert isinstance(outcome, DeliberatedTurn)
    assert _strip_calls(adapter) == 2, "never a third attempt"
    assert outcome.strip_states == ("invalid", "invalid")
    assert outcome.blind is not None and outcome.blind.ordering is Ordering.CONTAMINATED


def test_a_valid_not_separable_is_never_retried(store: Engine) -> None:
    adapter = ScriptedAdapter(
        [
            classifier_says("consequential"),
            strip_says(separable=False, question=S7),
            blind_says(CLOSE_UP),
            reconciled("Held.", "held"),
        ]
    )
    outcome = deliberate(store, adapter, S7)
    assert isinstance(outcome, DeliberatedTurn)
    assert _strip_calls(adapter) == 1
    assert outcome.strip_states == ("not_separable",)
    assert outcome.blind is not None and outcome.blind.ordering is Ordering.CONTAMINATED


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
