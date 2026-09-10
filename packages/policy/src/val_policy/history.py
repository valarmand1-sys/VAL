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

**Hysteresis — ruled 10 September 2026.** Both ceilings stay. But a window
that fills to a ceiling and then drops one oldest exchange on every later turn
rewrites its own prefix every turn, which defeats the history-prefix cache and
costs the doubled write rate each time. So when appending would require rolling
eviction at a binding ceiling, the window is **rebased once** to a contiguous
newest tail at about 75% of that ceiling — about 48,000 tokens when the token
ceiling binds, about 30 messages under the same counting convention when the
count binds, the tighter of the two when both bind — and then appended to
normally until a ceiling is approached again.

"Rebase once" has real semantics without new state: the selection **replays**
the conversation's own stored sequence from its start, applying the same rule
at each turn, so the boundary chosen at a ceiling event is re-derived
identically on every later turn, after an application restart, and after a
database restart. Older pre-rebase exchanges are never refilled merely because
they would fit again. The replay is a pure function of the stored messages.
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

#: The fraction of a binding ceiling that a rebase retains (ruled 10 September 2026).
REBASE_FRACTION = 0.75


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
class HistoryRebase:
    """One ceiling event in the replay: where the window was rebased, and why."""

    #: The exchange (0-based, oldest first) whose arrival bound a ceiling.
    at_exchange: int
    #: ``tokens`` | ``messages`` | ``both``
    binding: str
    from_exchange: int
    to_exchange: int


@dataclass(frozen=True)
class HistorySelection:
    """The retained tail as index positions, and why each exchange was or was not kept."""

    retained_from: int
    decisions: tuple[HistoryDecision, ...]
    budget: int
    retained_tokens: int
    retained_messages: int
    #: Every rebase the replay performed, oldest first.
    rebases: tuple[HistoryRebase, ...] = ()


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
    """Apply the six rules with the ruled hysteresis, by replaying the stored sequence.

    `messages` is the stored history, oldest first, ending on the current turn's
    user message. Counting convention, unchanged: `limit` bounds the retained
    messages *including* the current turn's own message.
    """
    if not messages:
        return HistorySelection(0, (), budget, 0, 0)
    groups = _exchanges(messages)
    tokens_of = [_estimate(messages[a:b]) for a, b in groups]
    sizes = [b - a for a, b in groups]
    leading_val = messages[groups[0][0]].role != "user"
    first_valid = 1 if leading_val and len(groups) > 1 else 0

    def window(start: int, end: int) -> tuple[int, int]:
        return sum(tokens_of[start : end + 1]), sum(sizes[start : end + 1])

    start = first_valid
    rebases: list[HistoryRebase] = []
    token_target = int(budget * REBASE_FRACTION)
    count_target = int(limit * REBASE_FRACTION)
    for turn in range(first_valid, len(groups)):
        tokens, count = window(start, turn)
        tokens_bind = tokens > budget
        count_bind = count > limit
        if not (tokens_bind or count_bind):
            continue
        # A ceiling binds: rebase once to the newest contiguous tail within about
        # 75% of the binding ceiling(s). Rule 6 still holds — the newest complete
        # exchange (the one before this turn's group) is never dropped for size —
        # so the tail can shrink to that exchange plus the current group, no further.
        want_tokens = token_target if tokens_bind else budget
        want_count = count_target if count_bind else limit
        # The smallest permitted window is the newest complete exchange plus this
        # turn's group (rule 6). If the window is already that small, nothing can
        # be evicted: the exchange is retained whole and the preflight is the limit.
        floor = turn - 1 if turn - 1 >= first_valid else turn
        if start >= floor:
            continue
        new_start = floor
        for candidate in range(start + 1, floor + 1):
            t, n = window(candidate, turn)
            if t <= want_tokens and n <= want_count:
                new_start = candidate
                break
        binding = (
            "both" if tokens_bind and count_bind else ("tokens" if tokens_bind else "messages")
        )
        rebases.append(HistoryRebase(turn, binding, start, new_start))
        start = new_start

    retained_tokens, retained_count = window(start, len(groups) - 1)
    retained_from = groups[start][0]
    # Decisions, newest complete exchange first (index 1), as logged before.
    decisions: list[HistoryDecision] = []
    older = list(range(len(groups) - 1))
    evicted_by: dict[int, HistoryRebase] = {}
    for rebase in rebases:
        for g in range(rebase.from_exchange, rebase.to_exchange):
            evicted_by.setdefault(g, rebase)
    for index, g in enumerate(reversed(older), start=1):
        size, tokens = sizes[g], tokens_of[g]
        if g < first_valid:
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
        elif g >= start:
            if index == 1 and retained_tokens > budget:
                reason = "newest complete exchange, retained whole although it exceeds the budget"
            elif index == 1:
                reason = "newest complete exchange, retained whole"
            else:
                reason = "within the retained tail"
            decisions.append(HistoryDecision(index, size, tokens, True, reason))
        else:
            event = evicted_by.get(g)
            where = (
                f"evicted at the rebase on exchange {event.at_exchange} ({event.binding} ceiling)"
                if event is not None
                else "before the retained tail"
            )
            decisions.append(HistoryDecision(index, size, tokens, False, where))
    return HistorySelection(
        retained_from=retained_from,
        decisions=tuple(decisions),
        budget=budget,
        retained_tokens=retained_tokens,
        retained_messages=retained_count,
        rebases=tuple(rebases),
    )
