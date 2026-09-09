"""The ruled word-count definition (9 September 2026), with the required examples."""

import pytest

from val_policy.words import count_words, lexical_spans

REQUIRED_EXAMPLES = [
    ("—", 0),
    ("don't", 1),
    ("state-of-the-art", 1),
    ("20-year-old", 1),
    ("1,250", 1),
    ("3.5", 1),
    ("harbour—workshop", 2),
]


@pytest.mark.parametrize(("text", "expected"), REQUIRED_EXAMPLES)
def test_the_required_examples(text: str, expected: int) -> None:
    assert count_words(text) == expected


def test_standalone_punctuation_and_symbols_are_zero_words() -> None:
    assert count_words("\u2014 \u2013 \u2026 ; : ! ? ( ) * & %") == 0
    assert count_words("") == 0
    assert count_words("   ") == 0


def test_an_en_dash_separates_like_an_em_dash() -> None:
    assert count_words("harbour\u2013workshop") == 2
    assert count_words("pacing \u2013 tone") == 2


def test_attached_punctuation_does_not_make_or_break_a_word() -> None:
    assert count_words("(harbour).") == 1
    assert count_words('"Harbour!"') == 1
    assert count_words("workshop,") == 1


def test_curly_apostrophes_and_hyphens_keep_a_word_whole() -> None:
    assert count_words("don\u2019t") == 1
    assert count_words("read-through") == 1
    assert count_words("twenty-one—twenty-two") == 2


def test_numerals_are_words_with_their_internal_punctuation() -> None:
    assert count_words("1,250,000") == 1
    assert count_words("£3.50") == 1
    assert count_words("9/10") == 1
    assert lexical_spans("1,250 3.5") == ("1,250", "3.5")


def test_an_underscore_alone_is_not_lexical() -> None:
    assert count_words("_") == 0
    assert count_words("snake_case") == 1


def test_the_v14_i1_answers_count_as_ruled() -> None:
    """The three captured I1 answers of 9 September 2026: 18, 20, 20 words."""
    high = (
        "To hear the script aloud — pacing, jokes, and dead weight reveal themselves "
        "before money is spent shooting them."
    )
    medium = (
        "To hear the script aloud — pacing, tone, and dead lines reveal themselves in "
        "performance long before they do on paper."
    )
    low = (
        "They surface pacing, tone, and dialogue problems while changes are still cheap — "
        "before cameras, crew, and schedule make them costly."
    )
    assert count_words(high) == 18
    assert count_words(medium) == 20
    assert count_words(low) == 20
