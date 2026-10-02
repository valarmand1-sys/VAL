"""How ordinary Markdown formatting is spoken: it is not.

Owner authorisation, 2 October 2026. A deterministic, **speech-only** step: the text the
voice is asked to say loses recognised Markdown *formatting* — emphasis markers, heading
markers, list bullets, rules, code ticks, quote markers — and keeps every word, number
and distinction, in order. The displayed and canonical answer is not touched; nothing is
removed because it is unnecessary, only because it is formatting. Whether the model
should have written a heading, an offer or a second suggestion is not this module's
business: their words are all still spoken.

**Recognised formatting only.** An asterisk, a hash or an underscore that is not
formatting stays as written: `2 * 3`, `a*b`, `2**3`, `C#`, `#42`, `snake_case`, a lone
`*`. Text inside code ticks is left literal (only the ticks go). Numbered list items
keep their numbers — the order is meaning.

**Pauses are kept.** A heading or a list item that ends without punctuation is given a
full stop, so the voice pauses where the layout did.

The voice receives one segment of the answer at a time, so a pair of emphasis markers
can be split across two segments. A double marker left open at the very start or the
very end of a segment is therefore formatting too; anywhere else an unpaired marker is
left alone.
"""

from __future__ import annotations

import re

_CODE = re.compile(r"`([^`\n]+)`")
_HOLD = "\x00{}\x00"
_HELD = re.compile(r"\x00(\d+)\x00")

# Paired emphasis: the markers hug the text they wrap and sit at word edges.
_STRONG = re.compile(r"(?<![\w*])(\*\*|__)(?=\S)(.+?)(?<=\S)\1(?![\w*])", re.DOTALL)
_EM_STAR = re.compile(r"(?<![\w*])\*(?=[^\s*])([^*\n]+?)(?<=[^\s*])\*(?![\w*])")
_EM_UNDER = re.compile(r"(?<![\w_])_(?=[^\s_])([^_\n]+?)(?<=[^\s_])_(?![\w_])")

_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$")
_BULLET = re.compile(r"^([ \t]*)(?:[-*+•])[ \t]+(?=\S)(.*)$")
_QUOTE = re.compile(r"^[ \t]{0,3}>[ \t]?")
_RULE = re.compile(r"^[ \t]{0,3}(?:-{3,}|\*{3,}|_{3,})[ \t]*$")
_ENDS_SPOKEN = re.compile(r"[.!?:;,—–-][\"'”’)\]]*$")  # noqa: RUF001 - the typographic marks are the point


def _pause(line: str) -> str:
    stripped = line.rstrip()
    if not stripped or _ENDS_SPOKEN.search(stripped):
        return line
    return stripped + "." + line[len(stripped) :]


def _line(line: str, *, is_line_start: bool) -> str:
    if not is_line_start:
        return line
    if _RULE.match(line):
        return ""
    line = _QUOTE.sub("", line, count=1)
    heading = _HEADING.match(line)
    if heading:
        return _pause(heading.group(1))
    bullet = _BULLET.match(line)
    if bullet:
        return _pause(bullet.group(2))
    return line


def spoken_format(text: str, *, at_line_start: bool = True) -> str:
    """`text` as the voice should be asked to say it. `at_line_start` says whether the
    text begins at the start of a line of the answer (a segment may begin mid-line, and
    a hyphen there is not a bullet)."""
    held: list[str] = []

    def hold(match: re.Match[str]) -> str:
        held.append(match.group(1))
        return _HOLD.format(len(held) - 1)

    working = _CODE.sub(hold, text)

    lines = working.split("\n")
    whole_line_strong = re.compile(r"^[ \t]*(\*\*|__)(?=\S)([^\n]+?)(?<=\S)\1[ \t]*$")
    out: list[str] = []
    for index, line in enumerate(lines):
        line = _line(line, is_line_start=index > 0 or at_line_start)
        # A line that is nothing but bold text is a heading in all but name.
        alone = whole_line_strong.match(line)
        if alone and (index > 0 or at_line_start):
            line = _pause(alone.group(2))
        out.append(line)
    working = "\n".join(out)

    working = _STRONG.sub(lambda m: m.group(2), working)
    working = _EM_STAR.sub(lambda m: m.group(1), working)
    working = _EM_UNDER.sub(lambda m: m.group(1), working)

    # A pair split by segmentation: a marker left open at the segment's very start or
    # very end. Only there. A double marker hugs a word, a quotation or the line's end;
    # a single asterisk is taken only beside a quotation mark or sentence punctuation,
    # never beside a bare word (a footnote's asterisk stays).
    working = re.sub(
        "^(\\s*)(?:(?:\\*\\*|__)(?=[\\w\"'\u201c\u2018(]|[ \\t]*(?:\\n|$))"
        '|\\*(?=["\u201c]|[ \\t]*(?:\\n|$)))',
        r"\1",
        working,
        count=1,
    )
    working = re.sub(
        '(?:(?<=[\\w.!?:;,)"\'\u201d\u2019])(?:\\*\\*|__)|(?<=[.!?"\u201d\u2019])\\*)(\\s*)$',
        r"\1",
        working,
        count=1,
    )

    # Emphasis wrapped around a quotation and split by segmentation: an asterisk directly
    # outside a quotation mark is never anything but formatting.
    working = re.sub('(?<![\\w*])\\*{1,2}(?=["\u201c])', "", working)
    working = re.sub('(?<=["\u201d])\\*{1,2}(?![\\w*])', "", working)
    # …and its closing marker stranded at the start of the next segment, mid-line.
    if not at_line_start:
        working = re.sub(r"^(\s*)\*{1,2}(?=\s)", r"\1", working, count=1)

    return _HELD.sub(lambda m: held[int(m.group(1))], working)
