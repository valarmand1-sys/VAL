"""Speech-only reading of unambiguous Roman numerals — owner authorisation, 1 October 2026.

The voice read "Chapter IV" letter by letter: "Chapter eye vee". The owner authorised
a narrow, speech-only normalisation, and this module is the whole of it: it produces
the *spoken form* of a segment — the text handed to the voice — in which a Roman
numeral whose reading is not in doubt has become English number words.

**The written text and its meaning are untouched.** Nothing here is applied to what
Val wrote, what is displayed, what is recorded or what is recalled. The caller keeps
the written segment; only what the voice is asked to say differs.

**Anything ambiguous is left exactly as written.** There is no blanket substitution
of letters, names or initials. "Plan X", "Vitamin C", "Malcolm X", "I. M. Pei",
"size XL" and "the III Corps" all reach the voice as they were written, because
nothing in the text settles that they are numbers. A numeral is read as a number
only when what precedes it says so:

  * a **cue word** — "Chapter IV", "Act II", "World War II" — read as a cardinal:
    "Chapter Four", "Act Two", "World War Two";
  * a **regnal or papal name** — "Henry VIII", "Louis XIV" — read as an ordinal with
    "the": "Henry the Eighth", "Louis the Fourteenth".

A missed numeral costs what it cost before this module existed: a few letters read
aloud. A wrong one puts a word in Val's mouth she did not write. So every doubtful
case falls toward leaving the text alone, and the doubtful cases are named below
where they are decided.

Pure and deterministic: no I/O, no state, no third-party import. `spoken_form` is
built from `replacements`, so what is reported and what is spoken cannot disagree.
"""

from __future__ import annotations

import re

#: The first value this module does not read. One to one hundred covers chapters,
#: acts, monarchs and Super Bowls; M and D are deliberately outside the alphabet,
#: which also keeps "MIX" and "DIM" from ever being candidates.
_LIMIT = 101

_UNITS = (
    "",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
    "Eleven",
    "Twelve",
    "Thirteen",
    "Fourteen",
    "Fifteen",
    "Sixteen",
    "Seventeen",
    "Eighteen",
    "Nineteen",
)

_UNIT_ORDINALS = (
    "",
    "First",
    "Second",
    "Third",
    "Fourth",
    "Fifth",
    "Sixth",
    "Seventh",
    "Eighth",
    "Ninth",
    "Tenth",
    "Eleventh",
    "Twelfth",
    "Thirteenth",
    "Fourteenth",
    "Fifteenth",
    "Sixteenth",
    "Seventeenth",
    "Eighteenth",
    "Nineteenth",
)

_TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")

_ROMAN_TENS = ("", "X", "XX", "XXX", "XL", "L", "LX", "LXX", "LXXX", "XC")
_ROMAN_UNITS = ("", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX")


def _roman(value: int) -> str:
    if value == 100:
        return "C"
    return _ROMAN_TENS[value // 10] + _ROMAN_UNITS[value % 10]


def _cardinal(value: int) -> str:
    if value == 100:
        return "One Hundred"
    if value < 20:
        return _UNITS[value]
    tens, unit = divmod(value, 10)
    return _TENS[tens] if unit == 0 else f"{_TENS[tens]}-{_UNITS[unit]}"


def _ordinal(value: int) -> str:
    if value == 100:
        return "One Hundredth"
    if value < 20:
        return _UNIT_ORDINALS[value]
    tens, unit = divmod(value, 10)
    if unit == 0:
        return _TENS[tens][:-1] + "ieth"
    return f"{_TENS[tens]}-{_UNIT_ORDINALS[unit]}"


#: The canonical numerals, and nothing else. Canonical form is decided by lookup, not
#: by a grammar: "IIII", "VX", "IC" and "CIVIL" are simply absent.
_VALUES: dict[str, int] = {_roman(value): value for value in range(1, _LIMIT)}

#: Words after which a numeral is a number. Matched case-insensitively. Plurals are
#: not cues ("Chapters IV" is left), and neither are "Plan", "Model", "Vitamin",
#: "Generation", "Mr." or "Dr.".
CUE_WORDS = (
    "Chapter",
    "Part",
    "Act",
    "Scene",
    "Book",
    "Volume",
    "Section",
    "Episode",
    "Phase",
    "Stage",
    "Appendix",
    "Article",
    "Canto",
    "Movement",
    "Season",
    "Series",
    "Level",
    "Round",
    "Tier",
    "Type",
    "Class",
    "Mark",
    "Figure",
    "Table",
    "Plate",
    "World War",
    "Super Bowl",
)

#: A cue only as written here: "Title IX" is a statute, "title IX" is nothing.
CASE_SENSITIVE_CUES = ("Title",)

#: Given names after which a numeral is regnal or papal. Matched exactly as
#: capitalised. A fixed list, because "any capitalised word" would include Malcolm.
REGNAL_NAMES = (
    "Henry",
    "Louis",
    "Charles",
    "George",
    "Edward",
    "Elizabeth",
    "Richard",
    "William",
    "James",
    "Mary",
    "John",
    "Paul",
    "Pius",
    "Benedict",
    "Leo",
    "Philip",
    "Frederick",
    "Catherine",
    "Napoleon",
    "Nicholas",
    "Alexander",
    "Peter",
    "Ivan",
    "Victoria",
    "Ferdinand",
    "Francis",
    "Gregory",
    "Clement",
    "Innocent",
    "Urban",
    "Boniface",
    "Constantine",
    "Ptolemy",
    "Ramesses",
    "Rameses",
    "Darius",
    "Xerxes",
    "Cyrus",
)

#: Cues after which a lone letter is ordinarily a *label*, not a number: "Appendix
#: C", "Part C", "Table L", "Type C". After these a lone "C" or "L" is left as
#: written. "Chapter C" is not a thing anyone writes; "Appendix C" is.
_LETTER_LABEL_CUES = frozenset(
    {
        "part",
        "section",
        "phase",
        "stage",
        "appendix",
        "series",
        "level",
        "round",
        "tier",
        "type",
        "class",
        "mark",
        "figure",
        "table",
        "plate",
        "title",
        "world war",
    }
)

#: Cues after which a lone "X" is as likely the letter as the number ten — "Series
#: X", "Type X", "Class X". Left as written.
_LETTER_X_CUES = frozenset({"series", "type", "class", "level", "tier"})

#: A lead (cue or regnal name), exactly one space, and a run of numeral letters. The
#: lookbehind keeps the lead a word of its own and out of code-like tokens:
#: "Rampart IV", "my_Part II" and "docs/Chapter IV" are not candidates. Lowercase
#: numerals never match — the numeral group is case-sensitive.
_CANDIDATE = re.compile(
    r"(?<![\w./@\\])"
    r"(?:(?P<cue>(?i:" + "|".join(CUE_WORDS) + r")|" + "|".join(CASE_SENSITIVE_CUES) + r")"
    r"|(?P<regnal>" + "|".join(REGNAL_NAMES) + r"))"
    r" (?P<numeral>[IVXLC]+)"
)

_DASHES = "—–"  # noqa: RUF001 - the typographic marks are the point
_APOSTROPHES = "'’"  # noqa: RUF001 - the typographic marks are the point
_CLOSERS = '.,;:!?)"”'


def _stands_alone(text: str, end: int, *, lone_i: bool) -> bool:
    """Whether the numeral ending at `end` is a token of its own.

    It is when followed by the end of the text, whitespace, a dash, or closing
    punctuation that is not itself glued to more of a token — so "IV-B", "IVs",
    "XIVb", "IV.2", "IV/2" and "IV_a" are all refused. A lone "I" is held to more:
    whitespace is not enough, because "Part I think" is a pronoun.
    """
    if end == len(text):
        return True
    following = text[end]
    after = text[end + 1 : end + 2]
    if following.isspace():
        return not lone_i
    if following in _DASHES:
        return True
    if following in _APOSTROPHES:
        # A possessive — "Henry VIII's", "Elizabeth I's" — or a closing quote. Never
        # "I'm", "I'll", "I've", "I'd".
        if after in ("s", "S"):
            return not text[end + 2 : end + 3].isalnum()
        return not after.isalnum()
    if following in _CLOSERS or following == "-":
        return not after.isalnum()
    return False


def _reads_as_initial(text: str, end: int) -> bool:
    """Whether a one-letter numeral after a *name* is more likely a middle initial.

    "John C. Reilly", "George V. Higgins", "Mary L Trump", "Mark V. Smith": a single
    capital, an optional full stop, then a capitalised word. Where a sentence merely
    ends on "Henry V." and the next begins, this also declines — the cost is the old
    behaviour, and the alternative is "John the Hundredth. Reilly".
    """
    rest = text[end:]
    if rest.startswith("."):
        rest = rest[1:]
    stripped = rest.lstrip()
    return stripped != rest and stripped[:1].isupper()


def _unambiguous(text: str, lead: str, numeral: str, end: int, *, regnal: bool) -> bool:
    if numeral not in _VALUES:
        return False
    single = len(numeral) == 1
    if not _stands_alone(text, end, lone_i=numeral == "I"):
        return False
    if not single:
        return True
    key = lead.lower()
    if regnal or key == "mark":
        if _reads_as_initial(text, end):
            return False
    if regnal:
        return True
    if key == "class" and numeral == "I":
        return False
    if numeral in ("C", "L") and key in _LETTER_LABEL_CUES:
        return False
    return not (numeral == "X" and key in _LETTER_X_CUES)


def replacements(text: str) -> tuple[tuple[int, int, str, str], ...]:
    """Every numeral that would be spoken as a number: `(start, end, written, spoken)`.

    In order, never overlapping, and `text[start:end] == written` for each. The span
    is the numeral alone — the cue word or name before it is not touched.
    """
    found: list[tuple[int, int, str, str]] = []
    for match in _CANDIDATE.finditer(text):
        numeral = match.group("numeral")
        regnal = match.group("regnal") is not None
        lead = match.group("regnal") if regnal else match.group("cue")
        if not _unambiguous(text, lead, numeral, match.end(), regnal=regnal):
            continue
        value = _VALUES[numeral]
        spoken = f"the {_ordinal(value)}" if regnal else _cardinal(value)
        found.append((match.start("numeral"), match.end(), numeral, spoken))
    return tuple(found)


def spoken_form(text: str) -> str:
    """The text to hand to the voice. The very same string when nothing is replaced."""
    found = replacements(text)
    if not found:
        return text
    pieces: list[str] = []
    cursor = 0
    for start, end, _written, spoken in found:
        pieces.append(text[cursor:start])
        pieces.append(spoken)
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)
