"""Unresolved work beyond the previous exchange — release-gaps order of 26 September 2026, §6.

The courtesy-versus-pending decision of Milestone A read his previous message and her
previous answer only. This set, written **before** the decision was widened and not
consulted while widening it, holds contexts of one to three exchanges: an unmet request
followed by a greeting or a remark about the weather and then courtesy (must stay on
MEDIUM); the action and offer boundaries tightened after p14 ("read", "show", "find",
"look up", "check", "I'll", "put it in front of me"); and informational earlier
exchanges that a social exchange does not turn into pending work (may take the route).
The hard requirement is again zero inappropriate light routes; coverage on the
courtesy contexts is recorded, not required, and every miss is a safe miss.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from val_policy.light_conversation import ConversationState, decide

FIXTURES = Path(__file__).parent / "fixtures"
WINDOW = json.loads((FIXTURES / "courtesy_pending_window.json").read_text())
TIER_ONE = frozenset({1})

#: The first and only evaluation of this set, as found — filled in after that run and
#: not adjusted since (the set is unseen evidence for the widened rule exactly once).
#: Found 26 September 2026: 12/12 pending contexts on MEDIUM; 9/10 courtesy contexts on
#: the route; the one miss (r10, "the guest **list**") is the known imprecision of the
#: action list matching an informational question — safe, and left as it is.
WINDOW_FIRST_EVALUATION: dict[str, object] = {
    "courtesy_light": 9,
    "courtesy_safe_misses": 1,
    "pending_inappropriate_light": [],
}
#: After the 27 September withholding of farewells after a greeting-only exchange (r01,
#: r04 become safe misses); the first evaluation above stays as history.
WINDOW_FINAL_EVALUATION: dict[str, object] = {
    "courtesy_light": 7,
    "courtesy_safe_misses": 3,
    "pending_inappropriate_light": [],
}


def route(case: dict) -> tuple[str, str]:
    exchanges = [tuple(pair) for pair in case["exchanges"]]
    owner, answer = exchanges[-1]
    verdict = decide(
        case["utterance"],
        ConversationState(
            previous_answer=answer,
            prior_turns=len(exchanges),
            previous_owner_message=owner,
            earlier_exchanges=tuple(exchanges[:-1]),
        ),
        TIER_ONE,
    )
    return ("light" if verdict.tier == 1 else "medium"), verdict.reason


@pytest.mark.parametrize("case", WINDOW["pending"], ids=lambda c: c["id"])
def test_earlier_unresolved_work_keeps_courtesy_on_medium(case: dict) -> None:
    got, reason = route(case)
    assert got == "medium", reason


def test_window_courtesy_coverage_is_recorded_not_required() -> None:
    routed = {c["id"]: route(c) for c in WINDOW["courtesy"]}
    light = [k for k, (got, _) in routed.items() if got == "light"]
    misses = {k: reason for k, (got, reason) in routed.items() if got == "medium"}
    assert len(light) + len(misses) == len(WINDOW["courtesy"])
    print(json.dumps({"window_courtesy_light": light, "window_courtesy_safe_misses": misses}))
    assert len(light) == WINDOW_FINAL_EVALUATION["courtesy_light"], (light, misses)


def test_a_social_exchange_does_not_settle_an_earlier_request() -> None:
    """The principle behind the set, stated once without the fixture."""
    state = ConversationState(
        previous_answer="It is, my lord.",
        prior_turns=2,
        previous_owner_message="Lovely evening.",
        earlier_exchanges=(("Send the invitation tonight.", "I will see to it, my lord."),),
    )
    verdict = decide("Thank you, Val.", state, TIER_ONE)
    assert verdict.tier is None and "earlier message of his" in verdict.reason


def test_his_own_later_work_moves_the_conversation_on() -> None:
    """A substantive message of his after the request means his courtesy answers that
    exchange; the request itself is not thereby settled (the reason names it)."""
    state = ConversationState(
        previous_answer="A pause within a line of verse, my lord.",
        prior_turns=2,
        previous_owner_message="Explain what a caesura is.",
        earlier_exchanges=(("Send the invitation tonight.", "I will see to it, my lord."),),
    )
    verdict = decide("Thank you, Val.", state, TIER_ONE)
    assert verdict.tier == 1, verdict.reason


def test_an_unresolved_request_stays_unresolved_however_many_social_exchanges_follow() -> None:
    """Release-gaps corrections of 27 September 2026 (§1): a bounded window is not evidence.

    The earlier test here allowed the route once a request fell outside a three-exchange
    lookback; that read the window as settlement. Social exchanges settle nothing,
    however many there are.
    """
    request = ("Send the invitation tonight.", "I will see to it, my lord.")
    for social_count in (1, 3, 4, 9):
        social = (("Good evening, Val.", "Good evening, my lord."),) * social_count
        state = ConversationState(
            previous_answer="It is, my lord.",
            prior_turns=social_count + 2,
            previous_owner_message="Quiet tonight.",
            earlier_exchanges=(request, *social),
        )
        verdict = decide("Good night, Val.", state, TIER_ONE)
        assert verdict.tier is None, (social_count, verdict.reason)
        assert "nothing establishes it settled" in verdict.reason


def test_her_claim_of_completion_settles_nothing() -> None:
    state = ConversationState(
        previous_answer="It is, my lord.",
        prior_turns=3,
        previous_owner_message="Lovely evening.",
        earlier_exchanges=(
            ("Send the invitation tonight.", "Done, my lord; it went out a moment ago."),
            ("Good evening, Val.", "Good evening, my lord."),
        ),
    )
    assert decide("Thank you, Val.", state, TIER_ONE).tier is None


def test_a_withdrawn_request_is_not_in_the_working_conversation() -> None:
    """Withdrawal is the authoritative settlement: the gateway hands the policy only live
    exchanges, so a retracted request never reaches it (the gateway-level test is in
    `test_tier1_request.py`). Here: the same context with the request absent."""
    social = (("Good evening, Val.", "Good evening, my lord."),) * 3
    state = ConversationState(
        previous_answer="It is, my lord.",
        prior_turns=4,
        previous_owner_message="Quiet tonight.",
        earlier_exchanges=social,
    )
    assert decide("Good night, Val.", state, TIER_ONE).tier == 1


def test_courtesy_after_an_unrelated_answered_question_names_the_older_request() -> None:
    """The route answers the most recent exchange; the older request is not inferred
    settled, and the reason says so."""
    state = ConversationState(
        previous_answer="A pause within a line of verse, my lord.",
        prior_turns=2,
        previous_owner_message="Explain what a caesura is.",
        earlier_exchanges=(("Send the invitation tonight.", "I will see to it, my lord."),),
    )
    verdict = decide("Thank you, Val.", state, TIER_ONE)
    assert verdict.tier == 1
    assert "1 earlier request of his remain on the record as they are" in verdict.reason


@pytest.mark.parametrize(
    ("answer", "courtesy"),
    [
        ("Good evening, my lord. How may I assist you tonight?", True),
        ("Good evening, my lord.", True),
        ("You're most welcome, my lord. Is there anything else you require?", False),
        ("Good night, my lord. Sleep well.", True),
        ("Either would serve, my lord. Which do you prefer?", False),
        ("I have no volume on that act in the house's record, my lord.", False),
        ("", False),
    ],
)
def test_an_answer_of_hers_is_read_for_its_shape(answer: str, courtesy: bool) -> None:
    from val_policy.light_conversation import answer_is_courtesy

    assert answer_is_courtesy(answer) is courtesy, answer
