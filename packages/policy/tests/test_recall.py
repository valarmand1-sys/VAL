"""The hybrid count-and-token recall bound — ruling of 7 September 2026.

Each ruled demonstration case as a pure test: six short messages that all
fit; long messages where fewer than six fit; a top-ranked message that alone
exceeds the budget and is preserved whole; and the next-ranked message not
fitting, proving a shorter lower-ranked candidate is not substituted.
"""

from __future__ import annotations

from dataclasses import dataclass

from val_policy.recall import (
    CHARS_PER_TOKEN_ESTIMATE,
    RECALL_MESSAGE_LIMIT,
    estimate_tokens,
    select_within_budget,
)


@dataclass(frozen=True)
class Candidate:
    content: str


def of_tokens(tokens: int) -> Candidate:
    """A candidate whose estimate is exactly `tokens`."""
    return Candidate("x" * int(tokens * CHARS_PER_TOKEN_ESTIMATE))


def test_the_estimate_is_local_and_rounds_up() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 2  # 4 / 3.6 -> 1.1 -> 2
    assert estimate_tokens("x" * 36) == 10


def test_six_short_relevant_messages_all_fit() -> None:
    selection = select_within_budget([of_tokens(1_000)] * 6, budget=16_000)
    assert selection.admitted_positions == (1, 2, 3, 4, 5, 6)
    assert selection.admitted_tokens == 6_000
    assert all(decision.admitted for decision in selection.decisions)


def test_long_messages_admit_fewer_than_six_in_rank_order() -> None:
    selection = select_within_budget([of_tokens(6_000)] * 6, budget=16_000)
    assert selection.admitted_positions == (1, 2)
    assert selection.admitted_tokens == 12_000
    third = selection.decisions[2]
    assert not third.admitted and "does not fit" in third.reason
    assert all(not d.admitted for d in selection.decisions[3:])
    assert all("not considered" in d.reason for d in selection.decisions[3:])


def test_a_top_ranked_message_that_alone_exceeds_the_budget_admits_nothing() -> None:
    """Ruled 10 September 2026: the budget is an aggregate ceiling, never a per-message
    allowance. The former top-candidate bypass is superseded: nothing is admitted from
    the ranking, nothing is truncated, no shorter lower-ranked candidate is substituted,
    and the event is named."""
    selection = select_within_budget([of_tokens(20_000), of_tokens(100)], budget=16_000)
    assert selection.admitted_positions == ()
    assert selection.admitted_tokens == 0
    assert selection.top_candidate_exceeded is True
    assert selection.decisions[0].reason.startswith("top_candidate_exceeds_budget")
    assert not selection.decisions[1].admitted, "the shorter candidate is not substituted"
    assert "not considered" in selection.decisions[1].reason


def test_a_top_ranked_message_within_the_budget_is_admitted_whole() -> None:
    selection = select_within_budget([of_tokens(15_000), of_tokens(2_000)], budget=16_000)
    assert selection.admitted_positions == (1,)
    assert selection.top_candidate_exceeded is False
    assert "does not fit" in selection.decisions[1].reason


def test_a_shorter_lower_ranked_candidate_is_never_substituted_for_one_that_did_not_fit() -> None:
    ranked = [of_tokens(10_000), of_tokens(7_000), of_tokens(500), of_tokens(500)]
    selection = select_within_budget(ranked, budget=16_000)
    assert selection.admitted_positions == (1,), "position 2 did not fit, so selection stopped"
    assert selection.admitted_tokens == 10_000
    assert "does not fit" in selection.decisions[1].reason
    assert "not considered" in selection.decisions[2].reason
    assert "not considered" in selection.decisions[3].reason


def test_the_message_limit_still_holds_when_everything_fits() -> None:
    selection = select_within_budget([of_tokens(10)] * 8, budget=16_000)
    assert selection.admitted_positions == tuple(range(1, RECALL_MESSAGE_LIMIT + 1))
    assert [d.reason for d in selection.decisions[6:]] == ["beyond the message limit of 6"] * 2


def test_size_never_affects_order_only_admission() -> None:
    """A huge second candidate stops selection; a tiny fourth is not promoted past it."""
    ranked = [of_tokens(100), of_tokens(50_000), of_tokens(100), of_tokens(1)]
    selection = select_within_budget(ranked, budget=16_000)
    assert selection.admitted_positions == (1,)
