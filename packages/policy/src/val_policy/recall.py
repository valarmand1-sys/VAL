"""The recall selection rules — hybrid count and token bound, ruled 7 September 2026.

Pure, like everything in `policy`: the ranking has already happened in
PostgreSQL, and this module decides which of the ranked candidates are
admitted to the prompt. The rules, verbatim from the ruling:

1. Rank candidates for relevance exactly as today. Message size must not
   affect relevance ranking.
2. Always include the highest-ranked relevant message whole, even if that one
   message exceeds the soft budget, subject only to the provider context
   preflight that already protects the call.
3. Consider subsequent messages strictly in relevance order.
4. Add a subsequent whole message only when it fits within the remaining
   soft budget.
5. If the next more-relevant candidate does not fit, stop. Do not skip it to
   include shorter, lower-ranked messages.
6. Maximum remains six messages.
7. Never summarize, paraphrase, or truncate a recalled message to satisfy
   the budget.

The 16,000-token value is a recall-context target, not a capability or
spending limit. Tokens are estimated locally from characters — no provider is
asked to count, because counting would be a network call per turn — at a
ratio calibrated on a measured live call (34,365 provider-reported tokens
for 123,676 characters of persona, envelope, and message on 7 September
2026: 3.6 characters per token). The estimate errs toward admitting less.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

#: The soft recall budget, in estimated tokens. Configuration, not a buried
#: literal: `val_gateway.memory.token_budget()` reads `VAL_RECALL_TOKEN_BUDGET`
#: from the environment and falls back to this.
RECALL_TOKEN_BUDGET_DEFAULT = 16_000

#: The maximum number of recalled messages, unchanged from WP-0.7.
RECALL_MESSAGE_LIMIT = 6

#: Characters per token for the local estimate. See the module docstring.
CHARS_PER_TOKEN_ESTIMATE = 3.6


def estimate_tokens(content: str) -> int:
    """A local, deterministic token estimate — never a provider call."""
    return math.ceil(len(content) / CHARS_PER_TOKEN_ESTIMATE)


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


def select_within_budget(
    candidates: Sequence[Ranked], *, budget: int, limit: int = RECALL_MESSAGE_LIMIT
) -> RecallSelection:
    """Apply the seven rules to candidates already in relevance order."""
    decisions: list[RecallDecision] = []
    admitted: list[int] = []
    spent = 0
    stopped = False
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
            admitted.append(position)
            spent += tokens
            reason = (
                "highest-ranked, admitted whole"
                if tokens <= budget
                else "highest-ranked, admitted whole although it alone exceeds the budget"
            )
            decisions.append(RecallDecision(position, tokens, True, reason))
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
    )
