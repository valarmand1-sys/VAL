"""The recall selection rules — hybrid count and token bound, ruled 7 September 2026.

Pure, like everything in `policy`: the ranking has already happened in
PostgreSQL, and this module decides which of the ranked candidates are
admitted to the prompt. The rules, verbatim from the ruling:

1. Rank candidates for relevance exactly as today. Message size must not
   affect relevance ranking.
2. **Superseded 10 September 2026.** The highest-ranked candidate is admitted
   whole only when it fits the aggregate budget. If it alone exceeds the
   budget, nothing from that ranking is admitted, nothing is truncated, and no
   lower-ranked candidate is substituted; the event is recorded as
   ``top_candidate_exceeds_budget``. The budget is an aggregate ceiling across
   all admitted excerpts, never a per-message allowance.
3. Consider subsequent messages strictly in relevance order.
4. Add a subsequent whole message only when it fits within the remaining
   soft budget.
5. If the next more-relevant candidate does not fit, stop. Do not skip it to
   include shorter, lower-ranked messages.
6. Maximum remains six messages.
7. Never summarize, paraphrase, or truncate a recalled message to satisfy
   the budget.

The 16,000-token value is a recall-context target in provider-context-token
scale, not a capability or spending limit. Tokens are estimated locally by
`val_policy.tokens.estimate_tokens` — the one documented estimator the
history budget also uses — never by asking a provider to count.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from val_policy.tokens import CHARS_PER_TOKEN_ESTIMATE, estimate_tokens

#: The soft recall budget, in estimated tokens. Configuration, not a buried
#: literal: `val_gateway.memory.token_budget()` reads `VAL_RECALL_TOKEN_BUDGET`
#: from the environment and falls back to this.
RECALL_TOKEN_BUDGET_DEFAULT = 16_000

#: The maximum number of recalled messages, unchanged from WP-0.7.
RECALL_MESSAGE_LIMIT = 6

__all__ = [
    "CHARS_PER_TOKEN_ESTIMATE",
    "RECALL_MESSAGE_LIMIT",
    "RECALL_TOKEN_BUDGET_DEFAULT",
    "Ranked",
    "RecallDecision",
    "RecallSelection",
    "estimate_tokens",
    "select_within_budget",
]


class Ranked(Protocol):
    """What the selector needs of a candidate: its text. Rank is the order given."""

    @property
    def content(self) -> str: ...


@dataclass(frozen=True)
class RecallDecision:
    """One candidate's fate, in the evidence the ruling asks to be logged."""

    rank_position: int
    estimated_tokens: int
    admitted: bool
    reason: str


@dataclass(frozen=True)
class RecallSelection:
    """Which candidates were admitted, why each was or was not, and the total."""

    admitted_positions: tuple[int, ...]
    decisions: tuple[RecallDecision, ...]
    budget: int
    admitted_tokens: int
    #: Ruled 10 September 2026: set when the highest-ranked candidate alone
    #: exceeded the aggregate budget, so nothing was admitted from this ranking.
    top_candidate_exceeded: bool = False


def select_within_budget(
    candidates: Sequence[Ranked], *, budget: int, limit: int = RECALL_MESSAGE_LIMIT
) -> RecallSelection:
    """Apply the seven rules to candidates already in relevance order."""
    decisions: list[RecallDecision] = []
    admitted: list[int] = []
    spent = 0
    stopped = False
    top_exceeded = False
    for position, candidate in enumerate(candidates[:limit], start=1):
        tokens = estimate_tokens(candidate.content)
        if stopped:
            decisions.append(
                RecallDecision(
                    position, tokens, False, "not considered: a more relevant candidate did not fit"
                )
            )
            continue
        if position == 1:
            if tokens <= budget:
                admitted.append(position)
                spent += tokens
                decisions.append(
                    RecallDecision(position, tokens, True, "highest-ranked, admitted whole")
                )
            else:
                stopped = True
                top_exceeded = True
                decisions.append(
                    RecallDecision(
                        position,
                        tokens,
                        False,
                        f"top_candidate_exceeds_budget: {tokens} exceeds the aggregate budget "
                        f"of {budget}; nothing is admitted from this ranking, nothing is "
                        "truncated, and no lower-ranked candidate is substituted",
                    )
                )
            continue
        if spent + tokens <= budget:
            admitted.append(position)
            spent += tokens
            decisions.append(RecallDecision(position, tokens, True, "fits the remaining budget"))
        else:
            stopped = True
            decisions.append(
                RecallDecision(
                    position,
                    tokens,
                    False,
                    f"does not fit: {tokens} would exceed the remaining {budget - spent}; "
                    "selection stops here and no lower-ranked candidate is substituted",
                )
            )
    for position in range(len(candidates[:limit]) + 1, len(candidates) + 1):
        decisions.append(
            RecallDecision(
                position,
                estimate_tokens(candidates[position - 1].content),
                False,
                f"beyond the message limit of {limit}",
            )
        )
    return RecallSelection(
        admitted_positions=tuple(admitted),
        decisions=tuple(decisions),
        budget=budget,
        admitted_tokens=spent,
        top_candidate_exceeded=top_exceeded,
    )
