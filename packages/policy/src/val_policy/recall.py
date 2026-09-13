"""The recall selection rules — hybrid count and size bound.

Pure, like everything in `policy`: the ranking has already happened in
PostgreSQL, and this module decides which of the ranked candidates are
admitted to the prompt. The rules, from the ruling of 7 September 2026 as
amended on 10 and 13 September 2026:

1. Rank candidates for relevance exactly as today. Message size must not
   affect relevance ranking.
2. **Superseded 10 September 2026.** The highest-ranked candidate is admitted
   whole only when it fits the aggregate bound. If it does not, nothing from
   that ranking is admitted, nothing is truncated, and no lower-ranked
   candidate is substituted; the event is recorded as
   ``top_candidate_exceeds_budget``. The bound is an aggregate ceiling across
   all admitted excerpts, never a per-message allowance.
3. Consider subsequent messages strictly in relevance order.
4. Add a subsequent whole message only when it fits within the bound.
5. If the next more-relevant candidate does not fit, stop. Do not skip it to
   include shorter, lower-ranked messages.
6. Maximum remains six messages.
7. Never summarize, paraphrase, or truncate a recalled message to satisfy
   the bound.

**The unit — amended 13 September 2026.** The original bound was a soft
recall-context target of about 16,000 provider tokens under the local
estimator, meant to prevent crowding and single-source dominance; it was never
a capability or spending limit, nor a context-window guard. On 13 September the
estimator undercounted a screenplay-formatted excerpt and the recall envelope
became about three quarters of the input. Superseded: **recall admission is
governed by a conservative 16,000-byte limit over the exact serialized recall
envelope.** At each step the envelope that would be transmitted — everything
already admitted plus the next whole candidate — is serialized by the caller's
own serializer (`measure`) and its UTF-8 length compared with the limit. This
is an intentional reduction in recall capacity, not a 16,000-token budget, and
no provider is ever asked to count.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

#: The recall envelope limit, in UTF-8 bytes of the serialized envelope.
#: Configuration, not a buried literal: `val_gateway.memory.envelope_byte_limit()`
#: reads `VAL_RECALL_ENVELOPE_BYTES` from the environment and falls back to this.
RECALL_ENVELOPE_BYTES_DEFAULT = 16_000

#: The maximum number of recalled messages, unchanged from WP-0.7.
RECALL_MESSAGE_LIMIT = 6

__all__ = [
    "RECALL_ENVELOPE_BYTES_DEFAULT",
    "RECALL_MESSAGE_LIMIT",
    "Ranked",
    "RecallDecision",
    "RecallSelection",
    "select_within_envelope",
]


class Ranked(Protocol):
    """What the selector needs of a candidate: its text. Rank is the order given."""

    @property
    def content(self) -> str: ...


@dataclass(frozen=True)
class RecallDecision:
    """One candidate's fate, in the evidence the ruling asks to be logged.

    `envelope_bytes` is the measured size of the serialized envelope with this
    candidate added to everything admitted before it; `None` when the candidate
    was never measured (selection had already stopped, or it lay beyond the
    message limit).
    """

    rank_position: int
    envelope_bytes: int | None
    admitted: bool
    reason: str


@dataclass(frozen=True)
class RecallSelection:
    """Which candidates were admitted, why each was or was not, and the envelope size."""

    admitted_positions: tuple[int, ...]
    decisions: tuple[RecallDecision, ...]
    limit_bytes: int
    #: The serialized size of the envelope holding everything admitted — the
    #: excerpts admitted before this selection included — or 0 when it is empty.
    envelope_bytes: int
    #: Ruled 10 September 2026: set when the highest-ranked candidate did not
    #: fit the aggregate bound, so nothing was admitted from this ranking.
    top_candidate_exceeded: bool = False


def select_within_envelope[Candidate: Ranked](
    candidates: Sequence[Candidate],
    *,
    limit_bytes: int,
    measure: Callable[[Sequence[Candidate]], int],
    admitted_before: Sequence[Candidate] = (),
    limit: int = RECALL_MESSAGE_LIMIT,
) -> RecallSelection:
    """Apply the seven rules to candidates already in relevance order.

    `measure` returns the UTF-8 byte length of the serialized envelope that
    would carry exactly the excerpts given, in the order given — the same
    serializer that produces the transmitted envelope. `admitted_before` holds
    excerpts another selection already placed in the same envelope; they count
    against the limit and are never re-decided here.
    """
    decisions: list[RecallDecision] = []
    admitted: list[int] = []
    included: list[Candidate] = list(admitted_before)
    size = measure(included) if included else 0
    stopped = False
    top_exceeded = False
    for position, candidate in enumerate(candidates[:limit], start=1):
        if stopped:
            decisions.append(
                RecallDecision(
                    position, None, False, "not considered: a more relevant candidate did not fit"
                )
            )
            continue
        trial = measure([*included, candidate])
        if trial <= limit_bytes:
            admitted.append(position)
            included.append(candidate)
            size = trial
            decisions.append(
                RecallDecision(
                    position,
                    trial,
                    True,
                    "highest-ranked, admitted whole"
                    if position == 1
                    else "fits within the envelope limit",
                )
            )
            continue
        stopped = True
        if position == 1:
            top_exceeded = True
            decisions.append(
                RecallDecision(
                    position,
                    trial,
                    False,
                    f"top_candidate_exceeds_budget: the serialized envelope would be {trial} "
                    f"bytes, over the limit of {limit_bytes}; nothing is admitted from this "
                    "ranking, nothing is truncated, and no lower-ranked candidate is substituted",
                )
            )
        else:
            decisions.append(
                RecallDecision(
                    position,
                    trial,
                    False,
                    f"does not fit: the serialized envelope would be {trial} bytes, over the "
                    f"limit of {limit_bytes}; selection stops here and no lower-ranked "
                    "candidate is substituted",
                )
            )
    for position in range(len(candidates[:limit]) + 1, len(candidates) + 1):
        decisions.append(
            RecallDecision(position, None, False, f"beyond the message limit of {limit}")
        )
    return RecallSelection(
        admitted_positions=tuple(admitted),
        decisions=tuple(decisions),
        limit_bytes=limit_bytes,
        envelope_bytes=size,
        top_candidate_exceeded=top_exceeded,
    )
