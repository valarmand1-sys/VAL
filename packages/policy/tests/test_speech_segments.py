"""The speech segmenter's exactness invariant — Voice work package 2 §7.

What is under test is one sentence: **every segment is a contiguous slice of Val's
visible answer, in order, and together they cover it completely.** Everything else
here is a corollary of that — nothing is paraphrased, summarised, rewritten,
reordered, normalised, padded with filler or dropped, because a slice of a string
cannot be any of those things.

The invariant is checked on prose, on one-word answers, on a sentence with no
terminal punctuation at all, on abbreviations and decimals that must not be
mistaken for full stops, and at **every possible chunk boundary** — because the
segmenter is fed a provider's stream, and a boundary rule that happens to work
when a sentence arrives whole is not a boundary rule.
"""

from __future__ import annotations

import pytest

from val_policy.deliberation import RECONCILIATION_VERDICT_MARKER
from val_policy.speech_segments import (
    HARD_LIMIT,
    LATER_MINIMUM,
    Segment,
    SpeechSegmenter,
    SpeechTextRefusedError,
    segment_all,
)

PROSE = (
    "Evening, my lord. The two readers disagree because they are answering different "
    "questions: one is asking whether the second act moves, the other whether it matters. "
    "Both can be true at once — a draft can drag and still be the best thing you have "
    "written, and cutting fifteen pages to settle the argument would be answering neither "
    "of them. I would ask Dr. Vance what she meant by drags; a scene that drags at 3.5 "
    "pages is a different problem from an act that drags across forty. What did the second "
    "reader single out?"
)

RUNAWAY = (
    "A single very long sentence with no terminal punctuation anywhere in it that simply "
    "keeps going and going, adding clause after clause, none of them ended by a full stop, "
    "so that the only way to cut it at all is at a comma or at a word gap, which is exactly "
    "what the long-sentence rule exists to do when a speaker would otherwise be left in "
    "silence waiting for a stop that never arrives"
)

ABBREVIATED = "Mr. Harding said 3.5 per cent at 4 p.m. Dr. Vance disagreed. J. Armand did not."

CASES = (PROSE, RUNAWAY, ABBREVIATED, "Yes.", "As you wish, my lord.", "No—not yet.")


def _drive(text: str, chunk: int) -> SpeechSegmenter:
    """Feed the text in fixed-size pieces, as a provider stream would."""
    segmenter = SpeechSegmenter()
    for start in range(0, len(text), chunk):
        segmenter.feed(text[start : start + chunk])
    segmenter.flush()
    return segmenter


def _raw(segmenter: SpeechSegmenter) -> str:
    return "".join(segmenter.source[s.start : s.end] for s in segmenter.segments)


# --- the invariant ---------------------------------------------------------------------


@pytest.mark.parametrize("text", CASES)
def test_the_segments_are_contiguous_slices_that_cover_the_whole_answer(text: str) -> None:
    """The invariant, stated three ways, on one finished answer."""
    segmenter = SpeechSegmenter()
    segmenter.feed(text)
    segmenter.flush()

    assert _raw(segmenter) == text, "the raw slices reassemble the answer byte for byte"
    assert segmenter.reconstructs(), "and the object says so about itself"
    ends = [0, *[s.end for s in segmenter.segments]]
    assert [s.start for s in segmenter.segments] == ends[:-1], "contiguous, in order"
    assert segmenter.segments[-1].end == len(text), "and complete"


@pytest.mark.parametrize("text", CASES)
def test_the_invariant_holds_at_every_chunk_boundary(text: str) -> None:
    """A stream arrives in arbitrary pieces; the boundaries must not depend on them."""
    for chunk in range(1, 40):
        segmenter = _drive(text, chunk)
        assert _raw(segmenter) == text, f"chunk size {chunk} broke the reconstruction"
        assert segmenter.reconstructs()


@pytest.mark.parametrize("text", CASES)
def test_the_spoken_words_differ_from_the_answer_only_in_boundary_whitespace(
    text: str,
) -> None:
    """What is spoken is what Val said. Not a word added, not a word removed."""
    segments = segment_all(text)
    spoken = " ".join(s.text for s in segments)
    assert "".join(spoken.split()) == "".join(text.split())
    for segment in segments:
        assert segment.text in text, "every segment is a substring of the answer"
        assert segment.text == text[segment.start : segment.end].strip()


@pytest.mark.parametrize("text", CASES)
def test_a_segment_never_ends_inside_a_word(text: str) -> None:
    for segment in segment_all(text):
        after = text[segment.end : segment.end + 1]
        before = text[segment.end - 1 : segment.end]
        if not after or after.isspace() or before.isspace():
            continue
        assert not (before.isalnum() and after.isalnum()), (
            f"cut inside a word at {segment.end}: {text[segment.end - 8 : segment.end + 8]!r}"
        )


def test_the_order_of_segments_is_the_order_of_the_answer() -> None:
    segments = segment_all(PROSE)
    assert [s.index for s in segments] == list(range(1, len(segments) + 1))
    assert segments == sorted(segments, key=lambda s: s.start)
    assert PROSE.index(segments[0].text) < PROSE.index(segments[-1].text)


# --- where it cuts, and where it refuses to ---------------------------------------------


def test_an_abbreviation_a_decimal_and_an_initial_are_not_sentence_ends() -> None:
    """A full stop is not always a full stop."""
    segments = segment_all(ABBREVIATED)
    spoken = [s.text for s in segments]
    assert not any(s.endswith("Mr.") for s in spoken)
    assert not any(s.endswith("Dr.") for s in spoken)
    assert not any(s.endswith("J.") for s in spoken)
    assert not any(s.endswith("3.") for s in spoken)
    assert "3.5 per cent" in " ".join(spoken)


def test_a_sentence_with_no_full_stop_is_still_cut_before_the_hard_limit() -> None:
    """A runaway sentence cannot hold speech silent indefinitely."""
    segments = segment_all(RUNAWAY)
    assert len(segments) >= 2, "it was cut"
    assert segments[0].reason == "long_sentence"
    assert segments[0].end <= HARD_LIMIT
    assert _joined(segments) == "".join(RUNAWAY.split())


def test_a_clause_mark_is_a_boundary_a_reader_pauses_at() -> None:
    text = "Three things, my lord: the schedule, the cost, and the readers. That is all."
    reasons = [s.reason for s in segment_all(text)]
    assert "clause" in reasons
    assert _joined(segment_all(text)) == "".join(text.split())


def test_a_full_stop_after_two_words_does_not_become_its_own_utterance() -> None:
    """A stream of tiny utterances is worse to listen to than one unhurried sentence.

    The first segment is deliberately allowed to be short, so Val begins speaking
    promptly; what must not happen is a separate utterance per full stop.
    """
    text = "Yes. No. Quite. I would keep the pages and ask the second reader what he meant."
    segments = segment_all(text)
    spoken = [s.text for s in segments]
    assert "Yes." not in spoken and "No." not in spoken, "the short stops were taken together"
    assert all(s.characters >= LATER_MINIMUM for s in segments[1:])
    assert _joined(segments) == "".join(text.split())


def test_a_short_answer_is_one_segment_flushed_exactly() -> None:
    segments = segment_all("As you wish, my lord.")
    assert [s.text for s in segments] == ["As you wish, my lord."]
    assert segments[0].reason == "flush"


def test_the_terminal_suffix_is_flushed_exactly() -> None:
    """Whatever is left when Val stops writing is spoken, unchanged."""
    segmenter = SpeechSegmenter()
    segmenter.feed("The first sentence is complete. And this tail has no full stop")
    before = list(segmenter.segments)
    (last,) = segmenter.flush()
    assert last.reason == "flush"
    assert last.text == "And this tail has no full stop"
    assert segmenter.reconstructs()
    assert len(segmenter.segments) == len(before) + 1


def test_an_empty_segment_is_never_produced_and_coverage_still_holds() -> None:
    """A trailing newline is not something to say — and is not dropped either.

    Found by this test: `flush` emitted an empty segment for a whitespace-only
    tail, which would have been handed to the voice. The whitespace now joins the
    previous segment's slice, so nothing empty is spoken and the slices still
    cover the answer completely.
    """
    segmenter = SpeechSegmenter()
    assert segmenter.feed("   \n  ") == []
    assert segmenter.flush() == [], "whitespace alone is nothing to say"
    assert segmenter.segments == []

    segmenter = SpeechSegmenter()
    segmenter.feed("The work is finished, my lord.\n\n")
    assert segmenter.flush() == []
    assert [s.text for s in segmenter.segments] == ["The work is finished, my lord."]
    assert segmenter.reconstructs(), "the trailing newline is still covered"
    assert _raw(segmenter) == segmenter.source
    assert all(s.text for s in segmenter.segments), "no segment is empty"


# --- what must never be spoken ----------------------------------------------------------


@pytest.mark.parametrize(
    "forbidden",
    [
        RECONCILIATION_VERDICT_MARKER,
        "<|channel|>",
        "<think>",
        "</think>",
        "<|message|>",
    ],
)
def test_text_that_must_never_be_spoken_stops_speech_rather_than_being_filtered(
    forbidden: str,
) -> None:
    """Core withholds these from the speech sink.

    Their arrival is a boundary failure upstream, so it raises. Stripping them
    would hide the failure and keep speaking as though nothing were wrong.
    """
    segmenter = SpeechSegmenter()
    with pytest.raises(SpeechTextRefusedError, match="must never be spoken"):
        segmenter.feed(f"Certainly, my lord. {forbidden} and then some.")


def test_a_marker_split_across_two_deltas_is_still_caught() -> None:
    """The stream does not get to smuggle it in two pieces."""
    segmenter = SpeechSegmenter()
    segmenter.feed("Certainly, my lord. The answer is plain enough. <|chan")
    with pytest.raises(SpeechTextRefusedError, match="must never be spoken"):
        segmenter.feed("nel|> hidden")


def test_speech_cannot_be_fed_after_it_is_flushed() -> None:
    segmenter = SpeechSegmenter()
    segmenter.feed("Done, my lord.")
    segmenter.flush()
    with pytest.raises(SpeechTextRefusedError, match="already flushed"):
        segmenter.feed(" And one more thing.")


# --- helpers ----------------------------------------------------------------------------


def _joined(segments: list[Segment]) -> str:
    return "".join("".join(s.text.split()) for s in segments)
