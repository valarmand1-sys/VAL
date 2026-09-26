"""Adaptive turn completion from the transcript's own cues — owner order §7, 26 Sept 2026."""

from __future__ import annotations

import pytest

from val_policy.turn_completion import completion_of

GRACE = 1.1


@pytest.mark.parametrize(
    "text",
    ["Good evening, Val.", "Thank you!", "How are you this evening?", "That's all for tonight."],
)
def test_a_finished_sentence_earns_the_short_window(text: str) -> None:
    completion = completion_of(text, GRACE)
    assert completion.state == "complete"
    assert completion.grace_seconds == pytest.approx(GRACE * 0.4)


@pytest.mark.parametrize(
    "text",
    ["Good evening, Val, and", "Good evening, Val,", "Tell me about the", "I think that", "Um"],
)
def test_words_that_lead_on_earn_the_long_window(text: str) -> None:
    completion = completion_of(text, GRACE)
    assert completion.state == "continuing"
    assert completion.grace_seconds == pytest.approx(GRACE * 1.5)


@pytest.mark.parametrize("text", ["Good evening Val", "so the second act", ""])
def test_no_terminal_mark_keeps_the_default(text: str) -> None:
    completion = completion_of(text, GRACE)
    assert completion.grace_seconds == pytest.approx(GRACE)
    assert completion.state in ("uncertain", "continuing")
