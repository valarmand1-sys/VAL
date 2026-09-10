"""Counting words for qualification criteria stated in words.

Ruled by Lord Armand on 9 September 2026 after the packet v1.4 runs, where the
harness counted whitespace-separated tokens and so scored a standalone em dash
as a word — a stricter rule than the criterion ("≤ 20 words") specified, and a
defect demonstrable independently of which configuration produced the answer.

**The durable definition.** A countable word is a maximal lexical span containing
at least one Unicode letter or decimal digit. Standalone punctuation and symbols
count as zero words. Internal apostrophes and hyphen-minus joining lexical
material do not split a word. En dashes and em dashes are separators, not words.
Numerals count as words, with ordinary internal numeric punctuation retained as
part of the numeral.

    —                 → 0
    don't             → 1
    state-of-the-art  → 1
    20-year-old       → 1
    1,250             → 1
    3.5               → 1
    harbour—workshop  → 2

This module is pure and is the repository's single lexical word counter: the
qualification harness uses it for every criterion stated in words, and the
recall gate (`val_policy.recall_gate`, ruled 10 September 2026) uses it for its
length condition. Both rely on the definition above being the same function;
neither may be given a private variant. The counting semantics here are the
ruled definition and change only by ruling.
"""

import re

#: Spans are delimited by whitespace and by en/em dashes (U+2013, U+2014), which
#: the ruling names as separators rather than words. Nothing else splits a span:
#: an apostrophe or a hyphen-minus inside lexical material keeps the word whole,
#: and a numeral keeps its internal punctuation.
_SEPARATORS = re.compile("[\\s\u2013\u2014]+")

#: A span counts if it contains a Unicode letter or a decimal digit. `\w` also
#: admits the underscore, which is neither, so it is excluded explicitly.
_LEXICAL = re.compile(r"[^\W_]")


def count_words(text: str) -> int:
    """The number of countable words in `text` under the ruled definition."""
    return sum(1 for span in _SEPARATORS.split(text) if _LEXICAL.search(span))


def lexical_spans(text: str) -> tuple[str, ...]:
    """The countable spans themselves, in order — for a record that shows its work."""
    return tuple(span for span in _SEPARATORS.split(text) if _LEXICAL.search(span))
