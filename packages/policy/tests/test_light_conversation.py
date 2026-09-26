"""The fast route's eligibility — owner order, 26 September 2026 (§5, §10).

Every case in the fixture is judged as the service judges it: the whole utterance
and the conversation's state, deterministically. **Zero false positives** is the
standard: not one ineligible case may reach a light tier, whatever the tier
switches; the two positive groups must each reach their tier when it is enabled and
fall to MEDIUM when it is not.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from val_policy.light_conversation import ConversationState, FastRoute, decide

FIXTURES = Path(__file__).parent / "fixtures"
BOTH = frozenset({1, 2})


def load(name: str) -> dict[str, list[object]]:
    return json.loads((FIXTURES / name).read_text())


def state_of(case: object) -> tuple[str, ConversationState]:
    if isinstance(case, str):
        return case, ConversationState(previous_answer=None, prior_turns=0)
    assert isinstance(case, dict)
    return str(case["text"]), ConversationState(
        previous_answer=str(case.get("previous")) if case.get("previous") else None,
        prior_turns=1,
    )


CASES = load("light_conversation_cases.json")
HELD_OUT_FILE = FIXTURES / "light_conversation_heldout.json"
HELD_OUT: dict[str, list[object]] = load(HELD_OUT_FILE.name) if HELD_OUT_FILE.exists() else {}


@pytest.mark.parametrize("case", CASES["tier_1"], ids=lambda c: str(c)[:40])
def test_tier_1_cases_take_tier_1(case: object) -> None:
    text, state = state_of(case)
    assert decide(text, state, BOTH).tier == 1, decide(text, state, BOTH).reason


@pytest.mark.parametrize("case", CASES["tier_2"], ids=lambda c: str(c)[:40])
def test_tier_2_cases_take_tier_2(case: object) -> None:
    text, state = state_of(case)
    assert decide(text, state, BOTH).tier == 2, decide(text, state, BOTH).reason
    # Tier 2 disabled: they fall to MEDIUM rather than to tier 1.
    assert decide(text, state, frozenset({1})).tier is None


@pytest.mark.parametrize(
    "case", CASES["ineligible"] + HELD_OUT.get("ineligible", []), ids=lambda c: str(c)[:40]
)
def test_ineligible_cases_never_take_a_light_tier(case: object) -> None:
    text, state = state_of(case)
    assert decide(text, state, BOTH).tier is None, decide(text, state, BOTH).reason


#: Held-out eligible cases the frozen rules send to MEDIUM — false negatives found on
#: the held-out set, 26 September 2026, and recorded rather than tuned away (§10: the
#: held-out cases are not used to tune the router). Each is a safe miss: the turn
#: takes the substantive route. Strict, so a rule change that starts catching one is
#: itself recorded here.
HELD_OUT_FALSE_NEGATIVES = frozenset(
    {
        # "done" is a work word (the completed-work rule), so the farewell is missed.
        "I'm done for the evening. Goodnight.",
        # "out tonight" is not among the pleasantry statement's admitted tails.
        "It's windy out tonight.",
    }
)


def _held_out(tier: int) -> list[object]:
    return [
        pytest.param(
            case,
            marks=(
                pytest.mark.xfail(strict=True, reason="held-out false negative, recorded")
                if (case if isinstance(case, str) else case["text"]) in HELD_OUT_FALSE_NEGATIVES  # type: ignore[index]
                else ()
            ),
            id=str(case)[:40],
        )
        for case in HELD_OUT.get(f"tier_{tier}", [])
    ]


@pytest.mark.parametrize("case", _held_out(1))
def test_held_out_tier_1(case: object) -> None:
    text, state = state_of(case)
    assert decide(text, state, BOTH).tier == 1, decide(text, state, BOTH).reason


@pytest.mark.parametrize("case", _held_out(2))
def test_held_out_tier_2(case: object) -> None:
    text, state = state_of(case)
    assert decide(text, state, BOTH).tier == 2, decide(text, state, BOTH).reason


def test_the_fixture_is_as_large_as_the_order_requires() -> None:
    assert len(CASES["tier_1"]) >= 30
    assert len(CASES["tier_2"]) >= 30
    assert len(CASES["ineligible"]) >= 30


def test_disabled_routes_nothing_and_the_setting_parses() -> None:
    quiet = ConversationState(previous_answer=None, prior_turns=0)
    assert decide("Good evening, Val.", quiet, frozenset()).tier is None
    assert FastRoute.parse("").tiers == frozenset()
    assert FastRoute.parse("1").tiers == frozenset({1})
    assert FastRoute.parse("1,2").tiers == frozenset({1, 2})
    with pytest.raises(ValueError, match="tiers"):
        FastRoute.parse("3")
    assert not FastRoute().enabled and FastRoute(frozenset({1})).enabled


def test_a_short_affirmation_is_light_only_when_she_asked_nothing() -> None:
    assert decide("Yes.", ConversationState("The lamps are lit, my lord.", 1), BOTH).tier == 2
    assert decide("Yes.", ConversationState("Shall I send it tonight?", 1), BOTH).tier is None
    assert decide("Yes, do it.", ConversationState("The lamps are lit.", 1), BOTH).tier is None
