"""The contiguous-tail history budget — ruling of 7 September 2026.

Each ruled demonstration as a pure test, in the system's own accounting
(`raw_input_bound`: bytes plus framing, an upper bound): a conversation that
fits whole; long messages where fewer exchanges than the forty-message
maximum fit; a newest exchange that alone exceeds the budget and is preserved
whole; the tail stopping at the first exchange that does not fit rather than
skipping it; and a tail that never begins on a Val message whose triggering
user message was dropped.
"""

from __future__ import annotations

from dataclasses import dataclass

from val_policy.budget import FRAMING_TOKENS_PER_MESSAGE, raw_input_bound
from val_policy.history import (
    HISTORY_MESSAGE_LIMIT,
    HISTORY_TOKEN_BUDGET_DEFAULT,
    select_history_tail,
)


@dataclass(frozen=True)
class Msg:
    role: str
    content: str


def of_bound(role: str, tokens: int) -> Msg:
    """A message whose byte bound is exactly `tokens` (ASCII: one byte per char)."""
    return Msg(role, "x" * (tokens - FRAMING_TOKENS_PER_MESSAGE))


def exchange(user_tokens: int, val_tokens: int) -> list[Msg]:
    return [of_bound("user", user_tokens), of_bound("val", val_tokens)]


def conversation(exchanges: int, user_tokens: int, val_tokens: int) -> list[Msg]:
    """`exchanges` complete exchanges, then the current turn's own user message."""
    history: list[Msg] = []
    for _ in range(exchanges):
        history.extend(exchange(user_tokens, val_tokens))
    history.append(of_bound("user", 100))
    return history


def test_the_budget_is_measured_in_the_systems_own_accounting() -> None:
    """The same figure the preflight and the reservation use: bytes plus framing."""
    message = of_bound("user", 1_000)
    assert raw_input_bound([message.content]) == 1_000


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
    """Twelve exchanges of 10,000; with the current message, only five older ones fit."""
    history = conversation(12, 5_000, 5_000)
    selection = select_history_tail(history, budget=64_000)
    # 100 current + 6 * 10,000 = 60,100 fits; a seventh would reach 70,100.
    assert selection.retained_messages == 13
    assert selection.retained_tokens == 60_100
    assert history[selection.retained_from].role == "user"
    fates = [decision.retained for decision in selection.decisions]
    assert fates == [True] * 6 + [False] * 6
    seventh = selection.decisions[6]
    assert "does not fit" in seventh.reason and "no older exchange is substituted" in seventh.reason
    assert all("not considered" in d.reason for d in selection.decisions[7:])


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
    assert "not considered" in selection.decisions[2].reason


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
    # 1 current + 19 exchanges of 2 = 39; a twentieth would make 41.
    assert selection.retained_messages == 39
    assert history[selection.retained_from].role == "user"
    assert any("message maximum" in d.reason for d in selection.decisions)


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
