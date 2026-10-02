"""Speech-only formatting (owner authorisation, 2 October 2026): recognised Markdown
formatting is not spoken; every word, number and literal symbol is."""

from __future__ import annotations

import re

import pytest

from val_policy.spoken_format import spoken_format


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9']+", text)


@pytest.mark.parametrize(
    ("written", "spoken"),
    [
        ("This is **important**, my lord.", "This is important, my lord."),
        ("It is *not* the same.", "It is not the same."),
        ("Call it __final__ and _only_ then.", "Call it final and only then."),
        ("**Late Fruit** or **The Orchard Year**.", "Late Fruit or The Orchard Year."),
        ("names such as **I** or **II**", "names such as I or II"),
    ],
)
def test_emphasis_markers_go_and_the_words_stay(written: str, spoken: str) -> None:
    assert spoken_format(written) == spoken


def test_headings_keep_their_words_and_gain_a_pause() -> None:
    written = "## The First Phase: Discovery\n\nBefore a single person is hired, define the scope."
    assert spoken_format(written) == (
        "The First Phase: Discovery.\n\nBefore a single person is hired, define the scope."
    )
    assert spoken_format("**The Internal Compass**\nBefore we see them act.") == (
        "The Internal Compass.\nBefore we see them act."
    )


def test_list_items_lose_the_bullet_keep_the_words_and_pause_between_items() -> None:
    written = (
        "You need three things:\n- access\n- power\n* **Light:** how it changes\n"
        "1. Scout first\n2. Then book"
    )
    assert spoken_format(written) == (
        "You need three things:\naccess.\npower.\nLight: how it changes.\n"
        "1. Scout first\n2. Then book"
    )


def test_rules_and_quote_markers_are_formatting_and_code_ticks_only_lose_the_ticks() -> None:
    assert spoken_format("First part.\n\n---\n\nSecond part.") == "First part.\n\n\n\nSecond part."
    assert spoken_format("> Before anything else, thank you.") == "Before anything else, thank you."
    assert spoken_format("Run `git status` and read it.") == "Run git status and read it."


@pytest.mark.parametrize(
    "literal",
    [
        "Two * three is six.",
        "2 * 3 = 6 and 2**3 = 8.",
        "Write a*b, not a x b.",
        "It is issue #42 in C#, my lord.",
        "The variable is snake_case_name here.",
        "Use `**kwargs` and `_private_` as written.",
        "A footnote* follows.",
        "Take 5 - 3 and you have 2.",
        "Chapter 4 costs $12, or 3 for $30.",
    ],
)
def test_literal_symbols_and_numbers_are_left_as_written(literal: str) -> None:
    expected = literal.replace("`", "")
    assert spoken_format(literal) == expected


def test_a_pair_split_across_two_segments_is_still_formatting() -> None:
    assert spoken_format("**The Third Phase: The Schedule", at_line_start=True) == (
        "The Third Phase: The Schedule"
    )
    assert spoken_format("and the Call Sheet**\n\n", at_line_start=False) == (
        "and the Call Sheet\n\n"
    )


def test_emphasis_split_around_a_quotation_is_formatting_at_the_segment_edges() -> None:
    assert spoken_format('**"The sun had not yet risen."') == '"The sun had not yet risen."'
    assert spoken_format("**\n\nThis works well for a period piece;", at_line_start=False) == (
        "\n\nThis works well for a period piece;"
    )
    assert spoken_format('*"The snow settled."') == '"The snow settled."'
    assert spoken_format('and "it stopped."*') == 'and "it stopped."'
    assert spoken_format('For example, *"Even the shadows were for sale."') == (
        'For example, "Even the shadows were for sale."'
    )
    assert spoken_format("* You have established a world.", at_line_start=False) == (
        " You have established a world."
    )
    # …but an asterisk beside a bare word, or in the middle, is left alone.
    assert spoken_format("See the footnote*") == "See the footnote*"
    assert spoken_format("*footnote: prices exclude tax") == "*footnote: prices exclude tax"


def test_a_hyphen_mid_line_is_not_a_bullet() -> None:
    assert spoken_format("- five to ten of them.", at_line_start=False) == "- five to ten of them."


def test_no_word_is_ever_removed_or_reordered() -> None:
    """Closing offers, alternatives and headings' own words are content, not formatting."""
    written = (
        "**The Fourth Phase: Contingency**\n\n"
        "*   **Weather:** have an indoor scene ready.\n"
        "*   **Kit:** know the nearest rental house.\n\n"
        "If you have a specific location in mind, my lord, I can help you draft a checklist."
    )
    assert _words(spoken_format(written)) == _words(written)
    assert "*" not in spoken_format(written)
