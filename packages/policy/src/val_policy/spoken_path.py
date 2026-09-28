"""Does this turn ask about how her spoken replies reach him? — the gate for `spoken_path`.

Owner order, 26 September 2026 (reduce the wait before Val speaks). The record-state
`spoken_path` facts (targeted voice latency order, 25 September) are 470 tokens that
every spoken turn recomputed before her first output — about 0.6 s on this Mac —
whether or not he had asked about her speed. The per-turn necessity rule
(`01-architecture.md` §5.5) says such context must justify running on every turn, and
where a deterministic gate settles it, be gated, failing toward inclusion when
ambiguous. They matter only when he asks about her speed, timing, voice or the path
itself, so they are included then — and on anything that looks like it.

Deterministic and closed: word stems, no model, no inference. A false positive costs a
few hundred tokens; a false negative risks her inventing again, so the list is broad.
"""

from __future__ import annotations

import re

#: Stems that make a turn one about the spoken path. Broad on purpose.
_ASKS = re.compile(
    r"\b("
    r"fast\w*|quick\w*|slow\w*|speed\w*|pace|pacing|rapid\w*|prompt\w*|"
    r"lag\w*|laten\w*|delay\w*|wait\w*|seconds?|minutes?|long|took|take[sn]?|"
    r"respon\w*|repl\w*|answer\w*\s+(?:me\s+)?(?:faster|sooner|quicker)|"
    r"tim(?:e|es|ed|ing|er)|clock|stopwatch|measur\w*|record\w*|demonstrat\w*|benchmark\w*|"
    r"network\w*|internet|wi-?fi|connection|bandwidth|hardware|gpu|cpu|processor|"
    r"voice\w*|speak\w*|spoke|speech|talk\w*|hear\w*|sound\w*|audio|tun(?:e|ed|ing)"
    r")\b",
    re.IGNORECASE,
)


#: What a piece of work is made of. A speed or time word that governs one of these is
#: about the work, not about her: "pacing a chase sequence", "too slow in act two",
#: "fast-paced opening" (remaining latency work, 28 September 2026, §4).
_WORK_OBJECT = (
    r"(?:scenes?|chases?|sequences?|chapters?|stor(?:y|ies)|films?|movies?|novels?|plots?|"
    r"acts?|sections?|narratives?|books?|scripts?|screenplays?|dialogues?|prose|reveals?|"
    r"endings?|openings?|burns?|builds?|beats?|paragraphs?|sentences?|lines?|poems?|verses?|"
    r"stanzas?|songs?|pieces?|drafts?|manuscripts?|pages?|essays?|episodes?|series|"
    r"montages?|climax\w*|thrillers?|tension|suspense|action|fight|battle|pursuit)"
)
#: A speed or time word followed, within four words, by a piece of work.
_ABOUT_THE_WORK = re.compile(
    r"\b(?:pac(?:e|ed|es|ing)|tempo|rhythm\w*|fast(?:er|est)?(?:-paced)?|quick\w*|slow\w*|"
    r"speed\w*|rapid\w*|long(?:er|est)?|time|timing|seconds?|minutes?|hours?)\b"
    r"(?:\W+\w+){0,4}?\W+" + _WORK_OBJECT + r"\b",
    re.IGNORECASE,
)
#: The same, with the piece of work first: "the second act is too slow", "make the
#: opening chapter faster".
_WORK_IS_SPEEDY = re.compile(
    r"\b" + _WORK_OBJECT + r"\b(?:\W+\w+){0,3}?\W+(?:pac(?:e|ed|es|ing)|fast\w*|quick\w*|slow\w*|"
    r"rush\w*|drag\w*|long(?:er|est)?|speed\w*|rapid\w*)\b",
    re.IGNORECASE,
)
#: Unmistakably about her: always included, whatever else the turn mentions.
_ABOUT_HER = re.compile(
    r"\byou(?:'re|\s+are|\s+were|\s+seem|\s+sound)?\s+(?:so\s+|too\s+|very\s+|a\s+bit\s+)?"
    r"(?:slow\w*|fast\w*|quick\w*|lagg\w*|delayed)\b|"
    r"\byour\s+(?:answers?|repl\w+|respon\w+|voice|speech|speaking|speed|timing|delay|"
    r"latency|pace|pacing|hearing|microphone|mic)\b|"
    r"\byou\s+(?:took|take|takes|taking|respond\w*|repl\w*|answer\w*|spoke|speak\w*|"
    r"talk\w*|sound\w*|hear\w*|listen\w*)\b|"
    r"\b(?:hear|hearing)\s+(?:me|you)\b|\b(?:time|timing|measure)\s+(?:you|your)\b",
    re.IGNORECASE,
)
#: "How long should a chapter be", "how long is the scene" — length of a thing, not a wait.
_LENGTH_OF_A_THING = re.compile(
    r"\bhow\s+long\s+(?:should|would|could|is|are|was|were|does|do|can|must)\s+"
    r"(?:a|an|the|my|this|his|her|their|our|each|every)\s+(?!wait|delay|pause|answer|reply|response)",
    re.IGNORECASE,
)
#: A short turn that follows one about her path is its follow-up: "Why?", "Can it be
#: better?", "Is that normal?".
FOLLOW_UP_WORDS = 8


def asks_about_the_spoken_path(text: str, previous: str | None = None) -> bool:
    """Whether the facts about her spoken path belong in this turn's record state.

    Remaining latency work, 28 September 2026 (§4): the gate stays broad — a false
    negative risks her inventing her own speed — with one contextual subtraction. A
    speed or time word that governs a piece of work ("advice on pacing a chase
    sequence", "is the second act too slow", "how long should a first chapter be")
    no longer counts; the same word about her, her replies or her voice still does.
    And a short follow-up to a turn that asked about her path ("Why?", "Is that
    normal?") carries the facts too, so the answer to it cannot invent them.
    """
    if previous is not None and len(text.split()) <= FOLLOW_UP_WORDS:
        if asks_about_the_spoken_path(previous):
            return True
    if _ABOUT_HER.search(text):
        return True
    # Every span about a piece of work, found on the original words (the patterns may
    # overlap — "the second act too slow"), removed together.
    spans = [
        match.span()
        for pattern in (_ABOUT_THE_WORK, _WORK_IS_SPEEDY, _LENGTH_OF_A_THING)
        for match in pattern.finditer(text)
    ]
    residue = "".join(
        " " if any(start <= index < end for start, end in spans) else character
        for index, character in enumerate(text)
    )
    return _ASKS.search(residue) is not None
