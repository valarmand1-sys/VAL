"""The history window — a contiguous chronological tail under a soft budget.

Ruled 7 September 2026. The count-only bound (forty messages) let sustained
long messages grow the window past a provider's context and hard-fail.
The forty-message maximum stays, and a configurable soft budget of 64,000
tokens is added, **in provider-context-token scale**, estimated locally by
`val_policy.tokens.estimate_tokens` — the same documented estimator recall
uses. (The first cut of this module measured the budget in the byte upper
bound the preflight uses, which is about four times the provider's count;
that admitted a quarter of the ruled magnitude and was corrected the same
day. The byte bound stays where it belongs: the context-window preflight.)
The number is configuration (`VAL_HISTORY_TOKEN_BUDGET`), not a buried
literal, precisely so it can be re-ruled without code.

The rules, verbatim from the ruling:

1. Start with the newest historical exchange and work backward.
2. Preserve whole messages, and complete user/Val exchange boundaries
   wherever the stored sequence permits — the retained tail must not begin
   with a Val answer whose triggering message was dropped.
3. Add older complete exchanges while the result stays within the soft
   budget and the forty-message maximum.
4. When adding the next older exchange would exceed the budget, stop. Do
   not skip it to include still-older shorter material.
5. Never relevance-rank history, create holes in the retained tail,
   summarize, paraphrase, or truncate messages.
6. If the newest complete exchange alone exceeds the budget, preserve it
   whole and include no older history, subject to the existing
   provider-context preflight.

History ends on the current turn's own user message, already persisted; that
message is always retained — it is the question being asked — and the
"newest complete exchange" is the exchange before it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from val_policy.tokens import estimate_tokens

#: The soft history budget, in estimated provider-context tokens. See above.
HISTORY_TOKEN_BUDGET_DEFAULT = 64_000

#: The maximum number of historical messages, unchanged from WP-0.7.
HISTORY_MESSAGE_LIMIT = 40


class Stored(Protocol):
    """What the selector needs of a stored message."""

    @property
    def role(self) -> str: ...

    @property
    def content(self) -> str: ...


@dataclass(frozen=True)
class HistoryDecision:
    """One exchange's fate, in the evidence the ruling asks to be logged."""

    exchange_index: int
    message_count: int
    estimated_tokens: int
    retained: bool
    reason: str


@dataclass(frozen=True)
class HistorySelection:
    """The retained tail as index positions, and why each exchange was or was not kept."""

    retained_from: int
    decisions: tuple[HistoryDecision, ...]
    budget: int
    retained_tokens: int
    retained_messages: int


def _estimate(messages: Sequence[Stored]) -> int:
    return sum(estimate_tokens(message.content) for message in messages)


def _exchanges(messages: Sequence[Stored]) -> list[tuple[int, int]]:
    """Split a chronological message list into exchanges: (start, end) index pairs.

    An exchange starts at a user message and runs to just before the next user
    message, so it contains that message and every Val reply to it. A leading
    run of Val messages with no triggering user message forms its own leading
    group, which can only ever be dropped, never be the start of the tail.
    """
    starts = [index for index, message in enumerate(messages) if message.role == "user"]
    if not starts:
        return [(0, len(messages))] if messages else []
    groups: list[tuple[int, int]] = []
    if starts[0] > 0:
        groups.append((0, starts[0]))
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(messages)
        groups.append((start, end))
    return groups


def select_history_tail(
    messages: Sequence[Stored],
    *,
    budget: int,
    limit: int = HISTORY_MESSAGE_LIMIT,
) -> HistorySelection:
    """Apply the six rules. `messages` is the stored history, oldest first, ending
    on the current turn's user message."""
    if not messages:
        return HistorySelection(0, (), budget, 0, 0)
    groups = _exchanges(messages)
    # The current turn: the last group, which begins with the just-persisted
    # user message. Always retained.
    current_start, current_end = groups[-1]
    current_tokens = _estimate(messages[current_start:current_end])
    spent = current_tokens
    count = current_end - current_start
    retained_from = current_start
    decisions: list[HistoryDecision] = []
    stopped = False
    older = groups[:-1]
    for offset, (start, end) in enumerate(reversed(older)):
        index = offset + 1  # 1 = the newest complete exchange, counting backward
        tokens = _estimate(messages[start:end])
        size = end - start
        if stopped:
            decisions.append(
                HistoryDecision(
                    index, size, tokens, False, "not considered: a newer exchange did not fit"
                )
            )
            continue
        leads_with_val = messages[start].role != "user"
        if leads_with_val:
            stopped = True
            decisions.append(
                HistoryDecision(
                    index,
                    size,
                    tokens,
                    False,
                    "dropped: a leading run of Val messages with no triggering user message "
                    "cannot begin the tail",
                )
            )
            continue
        if count + size > limit:
            stopped = True
            decisions.append(
                HistoryDecision(
                    index, size, tokens, False, f"would exceed the {limit}-message maximum"
                )
            )
            continue
        if index == 1:
            # Rule 6: the newest complete exchange is preserved whole even if it
            # alone exceeds the budget; the provider preflight is the only limit.
            retained_from = start
            spent += tokens
            count += size
            reason = (
                "newest complete exchange, retained whole"
                if spent <= budget
                else "newest complete exchange, retained whole although it exceeds the budget"
            )
            decisions.append(HistoryDecision(index, size, tokens, True, reason))
            continue
        if spent + tokens <= budget:
            retained_from = start
            spent += tokens
            count += size
            decisions.append(
                HistoryDecision(index, size, tokens, True, "fits the remaining budget")
            )
        else:
            stopped = True
            decisions.append(
                HistoryDecision(
                    index,
                    size,
                    tokens,
                    False,
                    f"does not fit: {tokens} would exceed the remaining {budget - spent}; "
                    "the tail stops here and no older exchange is substituted",
                )
            )
    return HistorySelection(
        retained_from=retained_from,
        decisions=tuple(decisions),
        budget=budget,
        retained_tokens=spent,
        retained_messages=count,
    )
