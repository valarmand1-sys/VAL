"""Courtesy against genuine pending work — owner order of 26 September 2026, Milestone A §4.

Three sets, kept apart: the two wrong-turn contexts found in the LOW qualification run
(regression), the development cases the decision was designed against, and a fresh set
written before the decision was implemented. The hard requirement on every set is
**zero inappropriate light routes**; coverage on the courtesy contexts is recorded, not
required. The fresh set was evaluated twice: once as written (one inappropriate light
route, p14, recorded in `FRESH_FIRST_EVALUATION`), then after the offer pattern was
tightened for what p14 showed — so the fresh set is no longer unseen for that one rule,
and the record says so.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from val_policy.light_conversation import ConversationState, decide

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = json.loads((FIXTURES / "courtesy_pending_fresh.json").read_text())
KNOWN = json.loads((FIXTURES / "courtesy_pending_known.json").read_text())
TIER_ONE = frozenset({1})

#: As found on the first evaluation of the fresh set, before any tightening.
FRESH_FIRST_EVALUATION = {
    "courtesy_light": 9,
    "courtesy_safe_misses": 11,
    "pending_inappropriate_light": ["p14"],
}
#: After the pending tightening (p14) and the withholding of bare thanks after a
#: greeting-only exchange (generated-answer verification, `courtesy-answers-2.json`):
#: the two withheld courtesy cases are c01 and c10.
FRESH_FINAL_EVALUATION = {
    "courtesy_light": 7,
    "courtesy_safe_misses": 13,
    "pending_inappropriate_light": [],
}


def route(case: dict) -> tuple[str, str]:
    verdict = decide(
        case["utterance"],
        ConversationState(
            previous_answer=case["previous_answer"],
            prior_turns=1,
            previous_owner_message=case["previous_owner"],
        ),
        TIER_ONE,
    )
    return ("light" if verdict.tier == 1 else "medium"), verdict.reason


@pytest.mark.parametrize("case", KNOWN["known_failures"], ids=lambda c: c["id"])
def test_the_two_wrong_turn_contexts_stay_on_medium(case: dict) -> None:
    got, reason = route(case)
    assert got == "medium", reason


@pytest.mark.parametrize(
    "case", [c for c in KNOWN["development"] if c["expect"] == "medium"], ids=lambda c: c["id"]
)
def test_development_pending_contexts_stay_on_medium(case: dict) -> None:
    got, reason = route(case)
    assert got == "medium", reason


@pytest.mark.parametrize(
    "case", [c for c in KNOWN["development"] if c["expect"] == "light"], ids=lambda c: c["id"]
)
def test_development_courtesy_contexts_may_take_the_route(case: dict) -> None:
    got, reason = route(case)
    assert got == "light", reason


@pytest.mark.parametrize("case", FRESH["pending_or_ambiguous"], ids=lambda c: c["id"])
def test_fresh_pending_contexts_never_take_the_route(case: dict) -> None:
    got, reason = route(case)
    assert got == "medium", reason


def test_fresh_courtesy_coverage_is_recorded_not_required() -> None:
    routed = {c["id"]: route(c) for c in FRESH["courtesy"]}
    light = [k for k, (got, _) in routed.items() if got == "light"]
    misses = {k: reason for k, (got, reason) in routed.items() if got == "medium"}
    # Every miss is a safe miss (MEDIUM); the count is evidence for the record.
    assert len(light) + len(misses) == len(FRESH["courtesy"])
    assert len(light) == FRESH_FINAL_EVALUATION["courtesy_light"], (light, misses)
    print(json.dumps({"fresh_courtesy_light": light, "fresh_courtesy_safe_misses": misses}))
