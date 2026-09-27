"""His next words against an answer not yet heard — release-gaps order of 26 September 2026, §1.

The decision is his words', never the arrival's: a stop or a replacement supersedes, a
continuation or anything ambiguous leaves the earlier request in force. The supplied
test of Milestone B treated "And after that, tell me about the orchard." as a
cancellation; it is the continuation regression case here.
"""

from __future__ import annotations

import pytest

from val_policy.precedence import follow_up


@pytest.mark.parametrize(
    "words",
    [
        "Actually, never mind. Tell me about the venue instead.",
        "No, the second one.",
        "Wait — I meant the reader, not the venue.",
        "Scratch that. What time is the reading?",
        "Never mind the invitation, Val. Where did we leave the third chapter?",
        "Hold on, not that one.",
        "Sorry, I mean the orchard.",
        "Tell me about the orchard instead.",
        "Let me rephrase: which venue seats sixty?",
        "Forget the venue. Tell me about the invitation.",
    ],
)
def test_a_clear_replacement_supersedes(words: str) -> None:
    got = follow_up(words)
    assert got.kind == "replacement" and got.supersedes, (words, got.reason)


@pytest.mark.parametrize(
    "words",
    [
        "Stop.",
        "Never mind.",
        "Forget it, Val.",
        "Scratch that.",
        "Cancel that, please.",
        "That's enough.",
        "Hold on.",
        "Wait.",
        "Leave it.",
        "Don't bother.",
    ],
)
def test_a_stop_alone_supersedes_and_asks_for_nothing(words: str) -> None:
    got = follow_up(words)
    assert got.kind == "stop" and got.supersedes, (words, got.reason)


@pytest.mark.parametrize(
    "words",
    [
        "And after that, tell me about the orchard.",
        "Also, the seating for the reading.",
        "Then the invitation, please.",
        "As well as the venue, the caterer.",
        "Plus the date, Val.",
        "Tell me about the orchard too.",
        "Next, the third chapter.",
        "While you're at it, the caterer.",
    ],
)
def test_a_continuation_never_supersedes(words: str) -> None:
    got = follow_up(words)
    assert got.kind == "continuation" and not got.supersedes, (words, got.reason)


@pytest.mark.parametrize(
    "words",
    [
        "What time is the reading?",
        "Tell me about the orchard.",
        "Good evening, Val.",
        "Where should the reading stop for the interval?",
        "Is the second act ready?",
        "The one with the poet.",
    ],
)
def test_ambiguous_speech_never_supersedes(words: str) -> None:
    got = follow_up(words)
    assert got.kind == "ambiguous" and not got.supersedes, (words, got.reason)


def test_nothing_said_is_ambiguous() -> None:
    assert follow_up("  ").kind == "ambiguous"
    assert follow_up("Val.").kind == "ambiguous"
