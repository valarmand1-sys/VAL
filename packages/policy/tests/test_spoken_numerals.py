"""Speech-only Roman numerals — owner authorisation, 1 October 2026.

Two things are under test, and the second matters more than the first: a numeral
whose reading is settled by the word before it is spoken as a number, and
**everything else reaches the voice byte for byte as it was written**. Most of this
file is therefore a list of things that must not change.

The expected words in the property loop come from this file's own tables, not from
the module's, so the module is not being checked against itself.
"""

from __future__ import annotations

import pytest

from val_policy.spoken_numerals import (
    CASE_SENSITIVE_CUES,
    CUE_WORDS,
    REGNAL_NAMES,
    replacements,
    spoken_form,
)

_SMALL = (
    "One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen Fourteen "
    "Fifteen Sixteen Seventeen Eighteen Nineteen"
).split()
_SMALL_ORDINAL = (
    "First Second Third Fourth Fifth Sixth Seventh Eighth Ninth Tenth Eleventh Twelfth "
    "Thirteenth Fourteenth Fifteenth Sixteenth Seventeenth Eighteenth Nineteenth"
).split()
_DECADES = {
    20: ("Twenty", "Twentieth"),
    30: ("Thirty", "Thirtieth"),
    40: ("Forty", "Fortieth"),
    50: ("Fifty", "Fiftieth"),
    60: ("Sixty", "Sixtieth"),
    70: ("Seventy", "Seventieth"),
    80: ("Eighty", "Eightieth"),
    90: ("Ninety", "Ninetieth"),
}


def _roman(value: int) -> str:
    out = ""
    for amount, letters in (
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ):
        while value >= amount:
            out += letters
            value -= amount
    return out


def _words(value: int) -> str:
    if value == 100:
        return "One Hundred"
    if value < 20:
        return _SMALL[value - 1]
    decade, unit = value - value % 10, value % 10
    return _DECADES[decade][0] if unit == 0 else f"{_DECADES[decade][0]}-{_SMALL[unit - 1]}"


def _ordinal_words(value: int) -> str:
    if value == 100:
        return "One Hundredth"
    if value < 20:
        return _SMALL_ORDINAL[value - 1]
    decade, unit = value - value % 10, value % 10
    if unit == 0:
        return _DECADES[decade][1]
    return f"{_DECADES[decade][0]}-{_SMALL_ORDINAL[unit - 1]}"


REPLACED = (
    ("Chapter IV", "Chapter Four"),
    ("World War II was", "World War Two was"),
    ("Henry VIII", "Henry the Eighth"),
    ("Louis XIV", "Louis the Fourteenth"),
    ("Elizabeth II", "Elizabeth the Second"),
    ("Elizabeth I.", "Elizabeth the First."),
    ("Part I.", "Part One."),
    ("Chapter I.", "Chapter One."),
    ("Act III, Scene II", "Act Three, Scene Two"),
    ("Super Bowl LIV was played", "Super Bowl Fifty-Four was played"),
    ("Pope John Paul II spoke", "Pope John Paul the Second spoke"),
    ("Henry VIII's wives", "Henry the Eighth's wives"),
    ("Elizabeth I's reign", "Elizabeth the First's reign"),
    ("Chapter I. The Beginning", "Chapter One. The Beginning"),
    ("Chapter IV—the storm", "Chapter Four—the storm"),
    ('"Chapter XXI"', '"Chapter Twenty-One"'),
    ("(see Part II)", "(see Part Two)"),
    ("Title IX applies", "Title Nine applies"),
    ("Class II rapids", "Class Two rapids"),
    ("chapter IV", "chapter Four"),
    ("post-World War II Europe", "post-World War Two Europe"),
    ("Louis XXI", "Louis the Twenty-First"),
    ("Chapter C", "Chapter One Hundred"),
    ("Act V", "Act Five"),
    ("George V was king", "George the Fifth was king"),
)

UNCHANGED = (
    "chapter iv",
    "Elizabeth I think",
    "Part I think we should cut",
    "Plan X",
    "Vitamin C",
    "Malcolm X",
    "Mr. X",
    "Model X",
    "Generation X",
    "I am",
    "I. M. Pei",
    "C. S. Lewis",
    "J. R. R. Tolkien",
    "size XL",
    "XXL",
    "LIV Golf",
    "the III Corps",
    "IIII",
    "Chapter IIII",
    "Chapter VX",
    "Chapter IC",
    "Chapter IV-B",
    "Chapter IVs",
    "Section 4",
    "Book XIVb",
    "CIVIL",
    "Chapter CIVIL",
    "Chapter MIX",
    "MIX",
    "DIM",
    "CC",
    "III",
    # Plurals are not cues, and the gap is exactly one space.
    "Chapters IV",
    "Chapter  IV",
    "Chapter\nIV",
    # The case-sensitive cue and the regnal names, written otherwise.
    "title IX",
    "henry VIII",
    "HENRY VIII",
    # A lone "I" is a pronoun until the text says otherwise.
    "Part I'm thinking of cutting",
    "Part I'll keep",
    "Class I.",
    "Class I",
    # Initials after a name that happens to be regnal.
    "John C. Reilly",
    "George V. Higgins",
    "Mary L Trump",
    "James L. Brooks",
    "Mark V. Smith",
    "Louis C.K.",
    # Letter labels.
    "Appendix C",
    "Part C",
    "Table L",
    "USB Type C",
    "Series X",
    "Class X",
    # Code-like tokens.
    "Section IV.2",
    "Part II/III",
    "Chapter IV_draft",
    "docs/Chapter IV",
    "my_Part II",
    "user@Part II",
    "Rampart IV",
    "",
    "Nothing here is a numeral at all.",
)


@pytest.mark.parametrize("cue", CUE_WORDS + CASE_SENSITIVE_CUES)
def test_every_cue_word_reads_its_numeral_as_a_cardinal(cue: str) -> None:
    assert spoken_form(f"{cue} VII begins") == f"{cue} Seven begins"


@pytest.mark.parametrize("name", REGNAL_NAMES)
def test_every_regnal_name_reads_its_numeral_as_an_ordinal(name: str) -> None:
    assert spoken_form(f"{name} III reigned") == f"{name} the Third reigned"


@pytest.mark.parametrize(("written", "spoken"), REPLACED)
def test_unambiguous_numerals_are_spoken_as_numbers(written: str, spoken: str) -> None:
    assert spoken_form(written) == spoken


@pytest.mark.parametrize("written", UNCHANGED)
def test_anything_ambiguous_is_left_exactly_as_written(written: str) -> None:
    assert spoken_form(written) == written
    assert replacements(written) == ()


def test_text_without_a_numeral_is_the_same_object() -> None:
    text = "My lord, the draft is ready when you are."
    assert spoken_form(text) is text


def test_several_numerals_in_one_text() -> None:
    text = "In Book II, Chapter XIV, Henry VIII meets Louis XIV; I think Plan X fails."
    assert spoken_form(text) == (
        "In Book Two, Chapter Fourteen, Henry the Eighth meets Louis the Fourteenth; "
        "I think Plan X fails."
    )
    assert [written for _, _, written, _ in replacements(text)] == ["II", "XIV", "VIII", "XIV"]


def test_offsets_slice_the_original_to_the_written_numeral() -> None:
    text = "Act III, Scene II of Henry VIII. Then Part I."
    found = replacements(text)
    assert [spoken for _, _, _, spoken in found] == ["Three", "Two", "the Eighth", "One"]
    previous_end = 0
    for start, end, written, _spoken in found:
        assert text[start:end] == written
        assert start >= previous_end
        previous_end = end


def test_everything_outside_the_numerals_is_preserved_byte_for_byte() -> None:
    text = "  Chapter IV — “World War II”,\n\tthen Elizabeth II!  "
    found = replacements(text)
    assert len(found) == 3
    rebuilt = spoken_form(text)
    cursor_written = 0
    cursor_spoken = 0
    for start, end, _written, spoken in found:
        gap = text[cursor_written:start]
        assert rebuilt[cursor_spoken : cursor_spoken + len(gap)] == gap
        cursor_spoken += len(gap)
        assert rebuilt[cursor_spoken : cursor_spoken + len(spoken)] == spoken
        cursor_spoken += len(spoken)
        cursor_written = end
    assert rebuilt[cursor_spoken:] == text[cursor_written:]


@pytest.mark.parametrize("written", [written for written, _ in REPLACED] + list(UNCHANGED))
def test_the_spoken_form_is_idempotent(written: str) -> None:
    once = spoken_form(written)
    assert spoken_form(once) == once


def test_every_numeral_to_one_hundred_after_a_cue_word() -> None:
    for value in range(1, 101):
        assert spoken_form(f"Chapter {_roman(value)}") == f"Chapter {_words(value)}", value


def test_every_numeral_to_one_hundred_after_a_regnal_name() -> None:
    for value in range(2, 101):
        expected = f"Louis the {_ordinal_words(value)}"
        assert spoken_form(f"Louis {_roman(value)}") == expected, value


def test_a_lone_i_needs_the_end_of_the_text_or_punctuation() -> None:
    assert spoken_form("Elizabeth I") == "Elizabeth the First"
    assert spoken_form("Elizabeth I, who") == "Elizabeth the First, who"
    assert spoken_form("Part I: Origins") == "Part One: Origins"
    assert spoken_form("Is this Part I?") == "Is this Part One?"
    assert spoken_form("Elizabeth I was") == "Elizabeth I was"
    assert spoken_form("Part I was long") == "Part I was long"


def test_the_house_name_from_the_physical_check_is_read_as_regnal() -> None:
    """30 September 2026: "Donald II" was spoken as letters."""
    assert spoken_form("Donald II ended the feud.") == "Donald the Second ended the feud."
    assert spoken_form("Lord Donald III.") == "Lord Donald the Third."
