"""Cutting Val's visible answer into speech-safe pieces, without changing a word.

Owner execution order, Voice mode work package 2 §7. Progressive speech needs to
begin before Val has finished writing, which means something must decide where one
spoken piece ends and the next begins. That decision is *only* about where to cut.

**The exactness invariant, which is the whole of this module's contract:**

    every segment is a contiguous slice of the visible response, the slices are
    in order, and together they cover it completely.

So this never paraphrases, summarises, rewrites, reorders, normalises wording,
adds filler, invents an acknowledgement, or drops a word that carries meaning. A
segment's `text` is its slice with the boundary whitespace trimmed — and the raw
slices, kept as indices, reassemble the response byte for byte. That is asserted
rather than promised (`packages/policy/tests/test_speech_segments.py`).

**Speech is delivery, not authorship.** Nothing here decides what Val says. It is
handed the text she already said and finds the commas.

Three kinds of boundary, in the order the order names them:

  * a **sentence** ending — `.` `!` `?` — when it really ends a sentence and is not
    an abbreviation, an initial, a decimal point or an ellipsis mid-thought;
  * a **clause** marked by `;` or `:`, which a reader pauses at and so may a voice;
  * a **long-sentence** cut, when a sentence has grown long enough that waiting
    for its full stop would cost more in silence than the cut costs in phrasing.
    Taken at a comma, a dash or, failing those, a word gap — **never mid-word**.

A first segment is allowed to be short so Val begins speaking promptly; later ones
are held to a longer minimum, because a stream of three-word utterances is a
worse thing to listen to than one unhurried sentence.

**The first segment's own long-sentence rule** (owner order, 25 September 2026,
targeted voice latency). Nothing can be heard until the first segment has been
synthesised whole, and synthesis time grows with its length: his 13-second turn
spent 3.85 s voicing a 121-character opening sentence. So the first segment alone
takes the long-sentence cut much sooner — past `FIRST_SOFT_LIMIT` characters, at
its earliest comma, semicolon or dash that leaves at least `FIRST_CLAUSE_MINIMUM`
characters — while the rest of the sentence is synthesised as she speaks the first
part. Only at a pause a reader would make; never mid-word; later segments unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from val_policy.deliberation import RECONCILIATION_VERDICT_MARKER

#: Once a sentence passes this many characters without ending, a clause boundary
#: is taken if one is available. Conversational speech, not a reading of prose.
SOFT_LIMIT = 220

#: An absolute ceiling: past this, the cut is taken at the last word gap whatever
#: the punctuation says, so one runaway sentence cannot hold speech silent.
HARD_LIMIT = 420

#: The first segment may be this short, so Val starts speaking promptly.
FIRST_MINIMUM = 12

#: Every later segment must reach this, so a full stop after two words does not
#: produce its own utterance.
LATER_MINIMUM = 40

#: The first segment's long-sentence threshold: past this many characters without a
#: sentence ending, it is cut at its earliest pause (targeted voice latency order).
FIRST_SOFT_LIMIT = 60

#: A first-segment pause cut must leave at least this much — so "My lord," is never
#: spoken alone.
FIRST_CLAUSE_MINIMUM = 24

#: Text that must never reach speech. Core withholds the verdict block from the
#: streaming sink and discards hidden reasoning at the adapter boundary; this is
#: the tripwire for the day one of those stops being true.
FORBIDDEN = (
    RECONCILIATION_VERDICT_MARKER,
    "<|channel|>",
    "<|channel>",
    "<channel|>",
    "<|start|>",
    "<|message|>",
    "<think>",
    "<|think|>",
    "</think>",
)

#: Abbreviations whose full stop does not end a sentence. Deliberately short: a
#: long list is a guess, and a missed boundary only costs a slightly longer
#: segment while a wrong one cuts a sentence in half.
ABBREVIATIONS = (
    "mr",
    "mrs",
    "ms",
    "dr",
    "prof",
    "st",
    "mt",
    "jr",
    "sr",
    "vs",
    "etc",
    "no",
    "fig",
    "approx",
    "e.g",
    "i.e",
)

#: A single capital letter before the stop — an initial, as in "J. Armand".
_INITIAL = re.compile(r"(?:^|[\s(\"'])[A-Z]$")

#: The last word before a full stop, lower-cased, for the abbreviation check.
_LAST_WORD = re.compile(r"([A-Za-z.]+)$")

#: Where a long sentence may be cut, most preferred first. Val writes em dashes;
#: the en dash and the spaced hyphen are here because a quotation may not.
_CLAUSE_MARKS = (", ", "; ", " \u2014 ", " \u2013 ", " - ")

#: The first segment's pauses: the same marks, and the unspaced em dash Val writes
#: ("cadence\u2014roughly"), cut after the dash.
_FIRST_MARKS = (*_CLAUSE_MARKS, "\u2014")


class SpeechTextRefusedError(Exception):
    """Text that must not be spoken reached the segmenter.

    Raised rather than filtered: if a control marker or hidden reasoning is
    arriving here, a boundary upstream has failed, and quietly stripping it would
    hide that. Speech stops and says so.
    """


@dataclass(frozen=True)
class Segment:
    """One speech-safe piece, and exactly where it came from.

    `start` and `end` index the visible response. `text` is that slice with its
    boundary whitespace trimmed — what is handed to the voice. The indices are
    what make the exactness invariant checkable.
    """

    index: int
    start: int
    end: int
    text: str
    #: `sentence`, `clause`, `first_pause`, `long_sentence` or `flush`.
    reason: str

    @property
    def characters(self) -> int:
        return len(self.text)


def _ends_a_sentence(source: str, position: int) -> bool:
    """Is the punctuation at `position` really the end of a sentence?"""
    mark = source[position]
    if mark not in ".!?":
        return False
    before = source[:position]
    after = source[position + 1 :]
    # An ellipsis or a doubled mark: the boundary is at its last character.
    if after[:1] in ".!?":
        return False
    if mark == ".":
        # A decimal point: 3.5, £4.99.
        if before[-1:].isdigit() and after[:1].isdigit():
            return False
        if _INITIAL.search(before):
            return False
        word = _LAST_WORD.search(before)
        if word is not None and word.group(1).rstrip(".").lower() in ABBREVIATIONS:
            return False
    # A sentence ends where the next thing is space, a closing quote, or nothing.
    return after == "" or after[0].isspace() or after[0] in "\"')]}"


class SpeechSegmenter:
    """Feed it Val's visible text as it arrives; take speech-safe pieces out.

    Stateful and single-conversation-turn: one segmenter per assistant answer.
    """

    def __init__(
        self,
        *,
        soft_limit: int = SOFT_LIMIT,
        hard_limit: int = HARD_LIMIT,
        first_minimum: int = FIRST_MINIMUM,
        later_minimum: int = LATER_MINIMUM,
        first_soft_limit: int = FIRST_SOFT_LIMIT,
        first_clause_minimum: int = FIRST_CLAUSE_MINIMUM,
    ) -> None:
        self.soft_limit = soft_limit
        self.hard_limit = hard_limit
        self.first_minimum = first_minimum
        self.later_minimum = later_minimum
        self.first_soft_limit = first_soft_limit
        self.first_clause_minimum = first_clause_minimum
        #: Everything Core has made visible so far, exactly as it arrived.
        self.source = ""
        #: How much of `source` has already been emitted. The invariant lives here.
        self.emitted = 0
        self.segments: list[Segment] = []
        self._closed = False

    # --- the stream ------------------------------------------------------------------

    def feed(self, delta: str) -> list[Segment]:
        """Take one piece of newly visible text. Returns any segments it completed."""
        if self._closed:
            raise SpeechTextRefusedError("this answer's speech is already flushed")
        if not delta:
            return []
        for marker in FORBIDDEN:
            if marker in delta or marker in (self.source[-32:] + delta):
                raise SpeechTextRefusedError(
                    f"text that must never be spoken reached the segmenter ({marker!r}). "
                    "Core withholds it from the speech sink, so its arrival is a boundary "
                    "failure upstream and not something to filter away here."
                )
        self.source += delta
        produced: list[Segment] = []
        while True:
            cut = self._next_cut()
            if cut is None:
                break
            produced.append(self._emit(cut[0], cut[1]))
        return produced

    def flush(self) -> list[Segment]:
        """The exact remaining suffix, as the last segment. Closes the answer."""
        self._closed = True
        if self.emitted >= len(self.source):
            return []
        if not self.source[self.emitted :].strip():
            # A trailing newline is not something to say. **The coverage invariant
            # still has to hold**, so the whitespace is added to the previous
            # segment's slice rather than dropped — its spoken text is unchanged,
            # because trimming removes exactly what was added. With no previous
            # segment there is nothing to speak at all, and nothing is emitted.
            if self.segments:
                last = self.segments[-1]
                self.segments[-1] = replace(last, end=len(self.source))
                self.emitted = len(self.source)
            return []
        return [self._emit(len(self.source), "flush")]

    @property
    def spoken_text(self) -> str:
        """Every segment's words, joined by one space. Compare with `source`."""
        return " ".join(segment.text for segment in self.segments)

    def reconstructs(self) -> bool:
        """Do the raw slices reassemble the visible response byte for byte?

        The invariant, asked of the object itself rather than only of a test: the
        slices are contiguous, in order, and cover everything emitted.
        """
        rebuilt = "".join(self.source[s.start : s.end] for s in self.segments)
        return rebuilt == self.source[: self.emitted]

    # --- where to cut ----------------------------------------------------------------

    def _emit(self, end: int, reason: str) -> Segment:
        start = self.emitted
        raw = self.source[start:end]
        self.emitted = end
        segment = Segment(
            index=len(self.segments) + 1,
            start=start,
            end=end,
            text=raw.strip(),
            reason=reason,
        )
        self.segments.append(segment)
        return segment

    def _minimum(self) -> int:
        return self.first_minimum if not self.segments else self.later_minimum

    def _next_cut(self) -> tuple[int, str] | None:
        """The end index of the next segment, and why — or `None` to keep waiting."""
        pending = self.source[self.emitted :]
        if not pending.strip():
            return None
        minimum = self._minimum()

        # 1. A sentence that has actually ended.
        # 1. The EARLIEST stable boundary, of either kind — a sentence that has
        #    really ended, or a clause mark a reader pauses at. One scan rather
        #    than a preference order: preferring a sentence globally would hold a
        #    long opening clause silent until a full stop arrived much later, and a
        #    colon is a real pause, not a second-best one.
        for offset, character in enumerate(pending):
            position = self.emitted + offset
            if character in ".!?" and _ends_a_sentence(self.source, position):
                end = position + 1
                # Take any closing quotation or bracket with the sentence it closes.
                while end < len(self.source) and self.source[end] in "\"')]}":
                    end += 1
                reason = "sentence"
            elif character in ";:":
                end = position + 1
                if end < len(self.source) and not self.source[end].isspace():
                    continue
                reason = "clause"
            else:
                continue
            if end - self.emitted < minimum:
                continue
            # Only a *completed* boundary: something must follow it, or the answer
            # is finished, which `flush` handles rather than this.
            if end >= len(self.source):
                continue
            return end, reason

        # 2. The first segment, grown past its own threshold: its earliest pause.
        if not self.segments and len(pending) >= self.first_soft_limit:
            earliest: int | None = None
            for mark in _FIRST_MARKS:
                place = pending.find(mark, self.first_clause_minimum)
                if place < 0:
                    continue
                end = place + len(mark.rstrip())
                # A completed pause only: something must follow it.
                if self.emitted + end >= len(self.source):
                    continue
                if earliest is None or end < earliest:
                    earliest = end
            if earliest is not None:
                return self.emitted + earliest, "first_pause"

        # 3. A sentence that has grown too long to keep waiting on.
        if len(pending) >= self.soft_limit:
            window = pending[: self.hard_limit]
            for mark in _CLAUSE_MARKS:
                place = window.rfind(mark)
                if place >= minimum:
                    return self.emitted + place + len(mark.rstrip()), "long_sentence"
        if len(pending) >= self.hard_limit:
            gap = pending[: self.hard_limit].rfind(" ")
            if gap >= minimum:
                return self.emitted + gap, "long_sentence"
        return None


def segment_all(text: str, **options: int) -> list[Segment]:
    """The whole of a finished answer, in speech-safe pieces. For tests and proofs."""
    segmenter = SpeechSegmenter(**options)
    segmenter.feed(text)
    segmenter.flush()
    return segmenter.segments
