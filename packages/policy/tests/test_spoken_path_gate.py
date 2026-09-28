"""The gate for the spoken-path facts — owner order, 26 September 2026.

Included whenever he asks about her speed, timing, voice or the path; left out of
turns that do not, which saves recomputing 470 tokens before her first word.
Every question from his sessions and from the paraphrased checks must pass.
"""

from __future__ import annotations

import pytest

from val_policy.spoken_path import asks_about_the_spoken_path

ASKS = [
    # His own, 25 September 2026.
    "I'm checking your voice model.",
    "Do you feel as though that you can speak quickly enough to carry a flow that is "
    "conversational?",
    "What's the tuning on that? How fast are you supposed to respond to me after receiving "
    "a message?",
    "Do you know of any way to increase the speed of the conversation? Because that last one was "
    "about 13 seconds before you were able to respond.",
    "I'd like it a little bit faster if possible.",
    # The paraphrased checks.
    "What is the normal wait before you start talking back to me?",
    "Can you measure how long you take and tell me the number? Is my wifi slowing you down?",
    "What could we change on my side to make you respond in about a second?",
    "How long is the usual delay before you begin answering me?",
    "Could you time your own replies and tell me the figure? Is my internet the problem?",
    "What would it take for you to answer me within a second?",
    "How quickly should you normally begin replying after I stop talking?",
    "Please time how long you take and give me the number. Is my connection the cause?",
    "Could you record a demonstration of your latency?",
]

ORDINARY = [
    "Good evening, Val.",
    "Tell me about the garden.",
    "What should we look at this evening?",
    "Is the house quiet tonight?",
]


@pytest.mark.parametrize("text", ASKS)
def test_a_question_about_the_spoken_path_gets_the_facts(text: str) -> None:
    assert asks_about_the_spoken_path(text)


@pytest.mark.parametrize("text", ORDINARY)
def test_an_ordinary_turn_does_not_carry_them(text: str) -> None:
    assert not asks_about_the_spoken_path(text)


# --- Remaining latency work, 28 September 2026 (§4): a speed or time word that governs a
# piece of work is about the work. In the cache experiment "Give me one line of advice on
# pacing a chase sequence" drew ~490 tokens of her voice-performance facts (~0.65 s).

ABOUT_THE_WORK = [
    "Give me one line of advice on pacing a chase sequence.",
    "How should I pace a film scene?",
    "Can you help me with the pacing of a film scene?",
    "Is the second act too slow?",
    "Make the opening chapter faster.",
    "How long should a first chapter be?",
    "What tempo suits a montage?",
    "Should the chase feel rushed?",
    "Should the reveal come faster?",
]

ABOUT_HER = [
    "How fast are you, Val?",
    "You were so slow just now.",
    "Why was your answer about the chapter so slow?",
    "Can you hear me?",
    "Your voice sounds different today.",
    "How long did that take?",
    "Wait a second, Val.",
    "Can you pace your replies a little faster?",
]


@pytest.mark.parametrize("text", ABOUT_THE_WORK)
def test_a_speed_word_about_a_piece_of_work_does_not_carry_them(text: str) -> None:
    assert not asks_about_the_spoken_path(text)


@pytest.mark.parametrize("text", ABOUT_HER)
def test_the_same_words_about_her_still_carry_them(text: str) -> None:
    assert asks_about_the_spoken_path(text)


def test_a_short_follow_up_to_a_question_about_her_carries_them() -> None:
    assert asks_about_the_spoken_path("Why?", previous="Why are you so slow tonight?")
    assert asks_about_the_spoken_path("Is that normal?", previous="How long did that take?")
    assert not asks_about_the_spoken_path("Why?", previous="Tell me about the garden.")
    # A long new request after one is judged on its own words.
    assert not asks_about_the_spoken_path(
        "Now give me one line of advice on pacing a chase sequence, please, Val.",
        previous="How fast are you, Val?",
    )
