"""The hybrid count-and-size recall bound — rulings of 7, 10 and 13 September 2026.

Amended 13 September 2026: the ruling replaced the estimated-token budget with a
16,000-byte limit over the exact serialized recall envelope, so these tests no
longer pass token estimates; each rule is exercised through a `measure` over the
cumulative envelope. The ruled cases are unchanged in shape: short messages that
all fit; long messages where fewer than six fit; a top-ranked message that alone
does not fit and admits nothing; and a next-ranked message that does not fit,
proving a shorter lower-ranked candidate is not substituted. Tests against the
real serializer live with it, in `packages/gateway/tests/test_recall_envelope_bound.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pytest

from val_policy.recall import (
    RECALL_ENVELOPE_BYTES_DEFAULT,
    RECALL_MESSAGE_LIMIT,
    RecallSelection,
    select_within_envelope,
)

#: A stand-in envelope: a fixed header counted once, and per excerpt a fixed
#: framing plus the content's UTF-8 bytes.
HEADER = 100
FRAMING = 20


@dataclass(frozen=True)
class Candidate:
    content: str


def envelope(items: Sequence[Candidate]) -> int:
    if not items:
        return 0
    return HEADER + sum(FRAMING + len(item.content.encode("utf-8")) for item in items)


def of_bytes(total: int) -> Candidate:
    """A candidate that adds exactly `total` bytes to the stand-in envelope."""
    return Candidate("x" * (total - FRAMING))


def select(
    candidates: Sequence[Candidate],
    limit_bytes: int = 16_000,
    admitted_before: Sequence[Candidate] = (),
) -> RecallSelection:
    return select_within_envelope(
        candidates, limit_bytes=limit_bytes, measure=envelope, admitted_before=admitted_before
    )


def test_the_default_limit_is_sixteen_thousand_bytes() -> None:
    assert RECALL_ENVELOPE_BYTES_DEFAULT == 16_000


def test_six_short_relevant_messages_all_fit() -> None:
    selection = select([of_bytes(1_000)] * 6)
    assert selection.admitted_positions == (1, 2, 3, 4, 5, 6)
    assert selection.envelope_bytes == HEADER + 6_000
    assert all(decision.admitted for decision in selection.decisions)


def test_long_messages_admit_fewer_than_six_in_rank_order() -> None:
    selection = select([of_bytes(6_000)] * 6)
    assert selection.admitted_positions == (1, 2)
    assert selection.envelope_bytes == HEADER + 12_000
    third = selection.decisions[2]
    assert not third.admitted and "does not fit" in third.reason
    assert third.envelope_bytes == HEADER + 18_000, "the misfit is measured as the whole envelope"
    assert all(not d.admitted for d in selection.decisions[3:])
    assert all("not considered" in d.reason for d in selection.decisions[3:])
    assert all(d.envelope_bytes is None for d in selection.decisions[3:])


def test_a_top_ranked_message_that_alone_exceeds_the_limit_admits_nothing() -> None:
    """Ruled 10 September 2026: the bound is an aggregate ceiling, never a per-message
    allowance. Nothing is admitted from the ranking, nothing is truncated, no shorter
    lower-ranked candidate is substituted, and the event is named."""
    selection = select([of_bytes(20_000), of_bytes(100)])
    assert selection.admitted_positions == ()
    assert selection.envelope_bytes == 0
    assert selection.top_candidate_exceeded is True
    assert selection.decisions[0].reason.startswith("top_candidate_exceeds_budget")
    assert not selection.decisions[1].admitted, "the shorter candidate is not substituted"
    assert "not considered" in selection.decisions[1].reason


def test_a_top_ranked_message_within_the_limit_is_admitted_whole() -> None:
    selection = select([of_bytes(15_000), of_bytes(2_000)])
    assert selection.admitted_positions == (1,)
    assert selection.top_candidate_exceeded is False
    assert "does not fit" in selection.decisions[1].reason


def test_a_shorter_lower_ranked_candidate_is_never_substituted_for_one_that_did_not_fit() -> None:
    ranked = [of_bytes(10_000), of_bytes(7_000), of_bytes(500), of_bytes(500)]
    selection = select(ranked)
    assert selection.admitted_positions == (1,), "position 2 did not fit, so selection stopped"
    assert selection.envelope_bytes == HEADER + 10_000
    assert "does not fit" in selection.decisions[1].reason
    assert "not considered" in selection.decisions[2].reason
    assert "not considered" in selection.decisions[3].reason


def test_the_message_limit_still_holds_when_everything_fits() -> None:
    selection = select([of_bytes(30)] * 8)
    assert selection.admitted_positions == tuple(range(1, RECALL_MESSAGE_LIMIT + 1))
    assert [d.reason for d in selection.decisions[6:]] == ["beyond the message limit of 6"] * 2


def test_size_never_affects_order_only_admission() -> None:
    """A huge second candidate stops selection; a tiny fourth is not promoted past it."""
    ranked = [of_bytes(100), of_bytes(50_000), of_bytes(100), of_bytes(21)]
    selection = select(ranked)
    assert selection.admitted_positions == (1,)


def test_the_envelope_is_measured_cumulatively_never_candidate_by_candidate() -> None:
    """The fixed header counts once, and the comparison is of the whole envelope."""
    seen: list[int] = []

    def recording(items: Sequence[Candidate]) -> int:
        seen.append(len(items))
        return envelope(items)

    select_within_envelope([of_bytes(1_000)] * 3, limit_bytes=16_000, measure=recording)
    assert seen == [1, 2, 3], "each trial measures everything admitted plus the next candidate"


@pytest.mark.parametrize(("limit", "admitted"), [(HEADER + 2_000, (1, 2)), (HEADER + 1_999, (1,))])
def test_exactly_at_the_limit_fits_and_one_byte_over_does_not(
    limit: int, admitted: tuple[int, ...]
) -> None:
    selection = select([of_bytes(1_000), of_bytes(1_000)], limit_bytes=limit)
    assert selection.admitted_positions == admitted


def test_excerpts_already_in_the_envelope_count_against_the_limit() -> None:
    """A second selection sharing the envelope admits only what still fits after them."""
    before = (of_bytes(9_000),)
    selection = select([of_bytes(5_000), of_bytes(3_000)], admitted_before=before)
    assert selection.admitted_positions == (1,)
    assert selection.envelope_bytes == HEADER + 14_000
    assert "does not fit" in selection.decisions[1].reason


def test_a_top_candidate_that_no_longer_fits_after_earlier_excerpts_admits_nothing() -> None:
    selection = select([of_bytes(8_000), of_bytes(10)], admitted_before=(of_bytes(9_000),))
    assert selection.admitted_positions == ()
    assert selection.top_candidate_exceeded is True
    assert selection.envelope_bytes == HEADER + 9_000, "the earlier excerpts are still there"
