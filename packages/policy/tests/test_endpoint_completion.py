"""The adaptive endpoint's completion policy — owner order of 27 September 2026, §3.

Complete only when the words are plainly finished — never from punctuation alone; an
unfinished or hesitating tail waits longer than today; everything else waits as long as
today. The totals are bounded by the fixed path's own silence bound.
"""

from __future__ import annotations

import pytest

from val_policy.turn_completion import (
    ADAPTIVE_MIN_SILENCE_MS,
    COMPLETE_GRACE_S,
    CONTINUING_GRACE_S,
    RESUME_SILENCE_BOUND_S,
    UNCERTAIN_GRACE_S,
    endpoint_completion,
)


@pytest.mark.parametrize(
    "words",
    [
        "Good evening, Val.",
        "Thank you.",
        "Good night.",
        "What time is the reading?",
        "Explain what a caesura is.",
        "Which of those works better in a short story?",
        "How long should a first chapter be?",
        "Tell me about the second act.",
    ],
)
def test_plainly_finished_words_are_complete(words: str) -> None:
    got = endpoint_completion(words)
    assert got.state == "complete", (words, got.reason)


@pytest.mark.parametrize(
    "words",
    [
        "Tell me about the invitation,",
        "Tell me about the invitation and",
        "I was wondering whether",
        "I was wondering, um",
        "Tell me about the... ",
        "Can you tell me about the",
        "So the second act is, uh.",
        "Explain the difference between suspense and surprise, and",
        "Let me think.",
        "Well.",
    ],
)
def test_unfinished_or_hesitating_words_wait_longer(words: str) -> None:
    got = endpoint_completion(words)
    assert got.state == "continuing", (words, got.reason)


@pytest.mark.parametrize(
    "words",
    [
        "The venue.",  # a terminal mark on two words: not enough to judge
        "Stop.",
        "Tell me about the invitation",  # no terminal mark
        "Val.",
        "",
        "Yes.",
    ],
)
def test_ambiguity_never_buys_a_shorter_wait(words: str) -> None:
    got = endpoint_completion(words)
    assert got.state == "uncertain", (words, got.reason)
    assert got.grace_seconds == UNCERTAIN_GRACE_S


def test_the_windows_keep_the_fixed_paths_silence_bound() -> None:
    endpoint = ADAPTIVE_MIN_SILENCE_MS / 1000
    assert endpoint + 0.13 + UNCERTAIN_GRACE_S == pytest.approx(RESUME_SILENCE_BOUND_S)
    assert endpoint + 0.13 + COMPLETE_GRACE_S < 0.7
    assert CONTINUING_GRACE_S > UNCERTAIN_GRACE_S
