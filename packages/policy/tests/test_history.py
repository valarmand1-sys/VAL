"""The contiguous-tail history budget — ruling of 7 September 2026.

Each ruled demonstration as a pure test, sized by the local estimator in
provider-context-token scale (`val_policy.tokens`): a conversation that
fits whole; long messages where fewer exchanges than the forty-message
maximum fit; a newest exchange that alone exceeds the budget and is preserved
whole; the tail stopping at the first exchange that does not fit rather than
skipping it; and a tail that never begins on a Val message whose triggering
user message was dropped.
"""

from __future__ import annotations

from dataclasses import dataclass

from val_policy.history import (
    HISTORY_MESSAGE_LIMIT,
    HISTORY_TOKEN_BUDGET_DEFAULT,
    select_history_tail,
)
from val_policy.tokens import CHARS_PER_TOKEN_ESTIMATE, estimate_tokens


@dataclass(frozen=True)
class Msg:
    role: str
    content: str


def of_bound(role: str, tokens: int) -> Msg:
    """A message whose estimate is exactly `tokens`."""
    return Msg(role, "x" * int(tokens * CHARS_PER_TOKEN_ESTIMATE))


def exchange(user_tokens: int, val_tokens: int) -> list[Msg]:
    return [of_bound("user", user_tokens), of_bound("val", val_tokens)]


def conversation(exchanges: int, user_tokens: int, val_tokens: int) -> list[Msg]:
    """`exchanges` complete exchanges, then the current turn's own user message."""
    history: list[Msg] = []
    for _ in range(exchanges):
        history.extend(exchange(user_tokens, val_tokens))
    history.append(of_bound("user", 100))
    return history


def test_the_budget_is_measured_in_estimated_provider_tokens() -> None:
    """The same estimator recall uses; never the byte upper bound."""
    message = of_bound("user", 1_000)
    assert estimate_tokens(message.content) == 1_000
    assert len(message.content.encode()) == 3_600, "bytes are not the unit"


def test_a_short_conversation_is_retained_whole() -> None:
    history = conversation(5, 500, 500)
    selection = select_history_tail(history, budget=HISTORY_TOKEN_BUDGET_DEFAULT)
    assert selection.retained_from == 0
    assert selection.retained_messages == 11
    assert all(decision.retained for decision in selection.decisions)


def test_the_current_user_message_is_always_retained() -> None:
    only = [of_bound("user", 50_000)]
    selection = select_history_tail(only, budget=1_000)
    assert selection.retained_from == 0
    assert selection.retained_messages == 1
    assert selection.retained_tokens == 50_000


def test_long_messages_retain_fewer_exchanges_than_the_count_maximum() -> None:
    """Twelve exchanges of 10,000 under a 64,000 budget. The replay (ruled 10 September
    2026) rebases once when the seventh exchange binds the ceiling, to a newest tail
    within about 48,000, and appends from there; on the final turn the retained tail
    is contiguous, whole, and within the budget."""
    history = conversation(12, 5_000, 5_000)
    selection = select_history_tail(history, budget=64_000)
    assert selection.retained_tokens <= 64_000
    assert selection.retained_messages == 2 * (selection.retained_messages // 2) + 1
    assert history[selection.retained_from].role == "user"
    fates = [decision.retained for decision in selection.decisions]
    assert fates == sorted(fates, reverse=True), "the retained tail is contiguous, newest first"
    assert selection.rebases, "the ceiling bound at least once on the way to twelve exchanges"
    assert all("evicted at the rebase" in d.reason for d in selection.decisions if not d.retained)


def test_the_newest_exchange_is_preserved_whole_even_when_it_alone_exceeds_the_budget() -> None:
    history = [*exchange(500, 500), *exchange(40_000, 40_000), of_bound("user", 100)]
    selection = select_history_tail(history, budget=64_000)
    assert selection.retained_from == 2, "the 80,000-token newest exchange is kept whole"
    assert selection.retained_messages == 3
    assert "although it exceeds the budget" in selection.decisions[0].reason
    assert not selection.decisions[1].retained, "nothing older is added after that"


def test_the_tail_stops_at_the_first_exchange_that_does_not_fit() -> None:
    """A shorter, older exchange is never pulled past a larger one that did not fit."""
    history = [
        *exchange(100, 100),  # oldest, tiny — would fit, must not be reached
        *exchange(30_000, 30_000),  # too large once the newest is in
        *exchange(2_000, 2_000),  # newest complete exchange
        of_bound("user", 100),
    ]
    selection = select_history_tail(history, budget=10_000)
    assert selection.retained_from == 4
    assert selection.retained_messages == 3
    assert [d.retained for d in selection.decisions] == [True, False, False]
    assert "evicted" in selection.decisions[2].reason, "the tiny oldest exchange is not substituted"


def test_the_tail_never_begins_on_a_val_message_without_its_user_message() -> None:
    """A stored sequence that opens with Val (a leading run) can be dropped but never lead."""
    history = [
        Msg("val", "orphaned opening"),
        *exchange(500, 500),
        of_bound("user", 100),
    ]
    selection = select_history_tail(history, budget=64_000)
    assert selection.retained_from == 1
    assert history[selection.retained_from].role == "user"
    assert "cannot begin the tail" in selection.decisions[-1].reason


def test_the_forty_message_maximum_still_holds() -> None:
    history = conversation(30, 10, 10)  # 61 stored messages, all tiny
    selection = select_history_tail(history, budget=HISTORY_TOKEN_BUDGET_DEFAULT)
    assert selection.retained_messages <= HISTORY_MESSAGE_LIMIT
    assert history[selection.retained_from].role == "user"
    # Ruled 10 September 2026: when the count ceiling binds, the window is rebased once
    # to about 30 messages under the same convention and appended to from there.
    first = next(r for r in selection.rebases if r.binding == "messages")
    at_that_turn = history[: 2 * first.at_exchange + 1]  # up to that exchange's user message
    assert (
        select_history_tail(at_that_turn, budget=HISTORY_TOKEN_BUDGET_DEFAULT).retained_messages
        <= 31
    )


def test_hysteresis_rebases_once_and_then_holds_the_boundary() -> None:
    """Ruled 10 September 2026. At the token ceiling the window is rebased to a newest
    contiguous tail within about 75% of the ceiling; the boundary then stays put while
    new exchanges append, and is re-derived identically from the stored sequence alone."""
    history: list[Msg] = []
    boundaries: list[int] = []
    for _ in range(24):
        history += exchange(2_000, 2_000)
        selection = select_history_tail([*history, of_bound("user", 50)], budget=64_000)
        boundaries.append(selection.retained_from)
        assert selection.retained_tokens <= 64_000
    # Everything fits for the first fifteen exchanges; the sixteenth binds the ceiling.
    assert boundaries[:15] == [0] * 15
    first_rebase = boundaries[15]
    assert (
        0 < first_rebase
        and select_history_tail(
            [*history[:32], of_bound("user", 50)], budget=64_000
        ).retained_tokens
        <= 48_050
    )
    # Held across the next four appends without dropping one exchange per turn.
    assert boundaries[15:20] == [first_rebase] * 5
    # The next ceiling event rebases again, to a later boundary.
    assert boundaries[20] > first_rebase
    # Replay is a pure function of the stored sequence: the same input, the same boundary.
    again = select_history_tail([*history, of_bound("user", 50)], budget=64_000)
    assert again.retained_from == boundaries[-1]


def test_hysteresis_uses_the_tighter_boundary_when_both_ceilings_bind() -> None:
    history = conversation(30, 2_000, 2_000)  # 61 messages, 120,000 tokens
    selection = select_history_tail(history, budget=64_000)
    assert selection.retained_messages <= 40 and selection.retained_tokens <= 64_000
    assert selection.rebases
    # After the last rebase the tail satisfies both targets that bound at that event.
    last = selection.rebases[-1]
    assert last.binding in ("tokens", "messages", "both")


def test_hysteresis_preserves_whole_exchanges() -> None:
    history = conversation(20, 3_000, 3_000)
    selection = select_history_tail(history, budget=64_000)
    assert history[selection.retained_from].role == "user"
    assert selection.retained_messages % 2 == 1, "whole exchanges plus the current message"


def test_messages_are_never_truncated_or_reordered() -> None:
    """The selection is a start index into the stored order; nothing else is produced."""
    history = conversation(3, 1_000, 1_000)
    selection = select_history_tail(history, budget=2_500)
    retained = history[selection.retained_from :]
    assert retained == history[selection.retained_from :]
    assert [m.role for m in retained] == ["user", "val", "user"]
    assert all(m.content == h.content for m, h in zip(retained, history[-3:], strict=True))


def test_an_empty_history_selects_nothing() -> None:
    selection = select_history_tail([], budget=64_000)
    assert selection.retained_messages == 0 and selection.decisions == ()
