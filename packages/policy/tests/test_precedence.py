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


# Corrected 27 September 2026: the five false cancellations Astra reproduced with the first
# rule, and fresh negative cases near them. None of these may set an answer aside.
@pytest.mark.parametrize(
    "words",
    [
        "No rush, take your time.",
        "Do not forget the invitation.",
        "What does 'never mind' mean?",
        "Actually, that sounds good.",
        "Can you explain why she said 'start over'?",
        # fresh negatives nearby
        "Please don't stop the reading list.",
        "The invitation must not be cancelled.",
        "I actually liked the second ending.",
        "Instead of worrying, tell me a story.",
        "No, thank you.",
        "Wait, was that the second act?",
        "Stop the reading list at ten.",
        "Cancel that meeting for Tuesday.",
        "She told me to forget it.",
        "It's enough for tonight, thank you.",
        "Hold on, is the venue confirmed?",
        "Never mind what she said — is the chapel free?",
        "Actually, yes, please continue.",
        "Do you mean the second one?",
        "That's enough detail on the venue; what about the date?",
    ],
)
def test_the_reproduced_false_cancellations_and_their_neighbours_keep_the_request(
    words: str,
) -> None:
    got = follow_up(words)
    assert not got.supersedes, (words, got.kind, got.reason)


def test_a_leading_and_does_not_override_an_explicit_stop() -> None:
    got = follow_up("And actually, never mind. Stop.")
    assert got.kind == "stop", got.reason
    got = follow_up("And no, never mind that. Tell me about the venue.")
    assert got.kind == "replacement", got.reason


@pytest.mark.parametrize(
    "words",
    [
        "Okay, never mind.",
        "That's not what I meant — the chapel.",
        "Cancel that. When is the reading?",
        "Never mind the invitation, Val. Where did we leave the third chapter?",
    ],
)
def test_mixed_clauses_with_an_explicit_marker_supersede(words: str) -> None:
    assert follow_up(words).supersedes, words


# --- Owner order, 1 October 2026: the plain ways of telling her to stop ----------------


@pytest.mark.parametrize(
    "words",
    [
        "Stop it.",
        "Stop that.",
        "Stop talking.",
        "Val, stop talking.",
        "Please stop speaking.",
        "Quiet.",
        "Be quiet.",
        "Hush.",
        "Shh.",
        "Pause.",
        "Thank you, that will do.",
        "That'll do.",
    ],
)
def test_the_plain_ways_of_telling_her_to_stop_are_stops(words: str) -> None:
    assert follow_up(words).kind == "stop"


@pytest.mark.parametrize(
    "words",
    [
        "Stop the recording at noon tomorrow.",
        "Don't stop.",
        "Can you stop?",
        "Pause the film at the second act.",
        "Quiet scenes work better there.",
        "Is that a quiet street?",
    ],
)
def test_a_request_that_merely_contains_a_stop_word_is_not_a_stop(words: str) -> None:
    assert follow_up(words).kind != "stop"


@pytest.mark.parametrize(
    "words",
    # The first two are his own words in the physical check of 30 September 2026.
    ["No, Donald. No, no, no, no, no.", "No.", "No, no, no.", "Nope.", "No, Val, no."],
)
def test_a_bare_refusal_is_a_stop_only_when_spoken_over_her(words: str) -> None:
    assert follow_up(words, interrupting=True).kind == "stop"
    assert follow_up(words).kind == "ambiguous", "after she has finished it is his answer"


@pytest.mark.parametrize(
    "words",
    [
        "No, just name a famous play.",
        "No thank you.",
        "No, the second one.",
        "No, I meant the barn.",
        "No Donald is the first.",
    ],
)
def test_a_refusal_with_a_request_is_never_reduced_to_a_stop(words: str) -> None:
    assert follow_up(words, interrupting=True).kind != "stop"


def test_stock_is_not_stop() -> None:
    """2 October 2026: the bench's "Stop." once came back as "stock."; that one
    transcription is not evidence, and an interruption about stock is a request."""
    for words in ("stock.", "Stock", "Check the stock.", "What about the stock?"):
        assert follow_up(words, interrupting=True).kind != "stop", words


@pytest.mark.parametrize(
    "words",
    [
        "No, the barn is on Saturday.",
        "No, I said the orchard.",
        "No, make it shorter.",
        "No no, tell me about the sea.",
        "No, not that one, the second title.",
        "No. Donald the First founded the house.",
    ],
)
def test_a_substantive_correction_beginning_with_no_is_never_a_stop(words: str) -> None:
    assert follow_up(words, interrupting=True).kind != "stop"
    assert follow_up(words).kind != "stop"


@pytest.mark.parametrize(
    "words",
    ["And why it works.", "And also the orchard.", "Also the stables.", "And in two sentences."],
)
def test_a_fragment_completes_the_same_request(words: str) -> None:
    relation = follow_up(words)
    assert relation.kind == "continuation" and relation.completes is True


@pytest.mark.parametrize(
    "words",
    [
        "And who wrote it?",
        "Also, what is the capital of Australia?",
        "And also name a fruit, if you would.",
        "And then tell me about the orchard.",
        "Also could you check the date.",
    ],
)
def test_an_added_request_of_its_own_does_not_complete_the_earlier_one(words: str) -> None:
    relation = follow_up(words)
    assert relation.kind == "continuation" and relation.completes is False
    assert relation.supersedes is False


# --- Owner order, 2 October 2026: clear modifiers of an unheard answer ------------------


@pytest.mark.parametrize(
    "words",
    [
        "In two sentences.",
        "But shorter.",
        "Shorter.",
        "For a horror film.",
        "Without the jokes.",
        "More formal.",
        "A bit shorter, please.",
        "But in plain words.",
        "Just in one line.",
        "Val, in two sentences.",
    ],
)
def test_a_clear_modifier_completes_the_request_without_any_conjunction(words: str) -> None:
    relation = follow_up(words)
    assert relation.kind == "continuation" and relation.completes is True, relation


@pytest.mark.parametrize(
    "words",
    [
        "What is the capital of Australia?",
        "In two days we leave for Rome.",
        "For whom?",
        "Thank you.",
        "Very good.",
        "Yes.",
        "Indeed.",
        "With you I never know.",
        "About the barn, is it booked?",
        "Like I said, the orchard matters more to me than the barn does.",
        "Name a fruit.",
        "From now on call him Donald the First.",
        "From now on call him Donald.",
        "For now keep the barn.",
        "In that case tell her Thursday.",
    ],
)
def test_what_is_not_a_bare_modifier_is_not_read_as_one(words: str) -> None:
    relation = follow_up(words)
    assert not (relation.kind == "continuation" and relation.completes), relation
