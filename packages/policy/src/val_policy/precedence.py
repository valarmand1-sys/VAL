"""What his next words are to the answer still being made (owner orders, 26 and 27 September 2026).

When he speaks again while her answer to his previous words is still being generated and
none of it has been heard, the relationship between the two utterances decides what
happens to that answer — and it is **his words** that decide it, deterministically, never
the fact that words arrived:

* a **stop** — "Stop.", "Never mind.", "Forget it." — with nothing else in it ends the
  obsolete answer and asks for nothing new;
* a **replacement**, correction or redirection — "Actually, never mind. Tell me about
  the venue instead.", "No, the second one.", "Wait — I meant the reader." — ends the
  obsolete answer and is answered on its own;
* a **continuation** or added request — "And after that, tell me about the orchard.",
  "Also, the seating." — leaves the earlier request in force; both are answered, in
  order;
* anything else is **ambiguous**, and ambiguity never cancels: the earlier answer is
  finished and the new words wait, as they always did.

**Corrected 27 September 2026.** The first rule read broad leading words and markers
anywhere in the utterance as cancellation, and so cancelled on "No rush, take your
time.", "Do not forget the invitation.", "What does 'never mind' mean?", "Actually, that
sounds good." and "Can you explain why she said 'start over'?" — and read "And actually,
never mind. Stop." as a continuation because it opened with "and". None of those is
cancellation intent. The rule is now clause-based and recognises only **explicit**
cancellation or replacement of the pending answer:

- quoted spans are data and are removed before anything is matched;
- a clause that is a question is never a marker (it may be the new request after one);
- a clause that opens with a negation ("don't", "do not", "must not", "never" before a
  verb) is never a marker;
- a stop phrase must be the **whole** clause, once politeness and her name are set
  aside — "Stop the reading list at ten." and "Cancel that meeting." are requests, not
  stops — and the weak pauses "wait" and "hold on" count only alone or before an
  explicit correction;
- "actually", "sorry", "no rush", "take your time" and the like are discourse markers
  and mean nothing here;
- a clause is a replacement only in an explicit form: "I meant …", "I mean …", "that's
  not what I meant", "let me rephrase", "start over", "not that one", "not the …",
  a request that ends in "instead", a bare "no" followed by a correction, or a stop
  followed by a new request;
- a stop or replacement clause anywhere in the utterance decides, so a leading "and"
  never turns an explicit stop into a continuation; a continuation is only an utterance
  that opens (or closes) as an addition and contains no such clause.

When uncertain, the earlier request is preserved. No model is asked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Kind = Literal["stop", "replacement", "continuation", "ambiguous"]

#: Her name, and the small politenesses that carry no meaning here.
_ADDRESS = re.compile(r"\b(?:val|please|there|thank you|thanks)\b", re.IGNORECASE)
#: Quoted spans: data, whatever they say. Straight single quotes count only as a pair
#: around a span that begins after a space (so "don't" keeps its apostrophe).
_QUOTED = re.compile(
    r"[\"\u201c\u201d]([^\"\u201c\u201d]{1,120})[\"\u201c\u201d]"
    r"|(?:(?<=\s)|^)'([^']{1,120})'(?=[\s.,;:!?]|$)"
    r"|\u2018([^\u2019]{1,120})\u2019"
)
#: Discourse markers at the front of a clause, set aside repeatedly.
_DISCOURSE = re.compile(
    r"^(?:actually|sorry|well|oh|hmm|um|erm|okay|ok|right|so|no rush|no hurry|no worries|"
    r"no problem|take your time|and|but|then|also|now|look|listen)(?=$|[\s,:;-])",
    re.IGNORECASE,
)
#: A stop, and nothing else, in a clause.
_STOP = re.compile(
    r"^(?:stop|never ?mind|never mind that|forget (?:it|that|about it)|scratch that|"
    r"cancel (?:that|it)|that(?:'s| is) enough|enough|leave it|drop it|belay that|not now|"
    r"(?:don't|do not) bother|no need|let it go|"
    # 1 October 2026: the plain ways of telling someone to stop speaking.
    r"(?:please )?stop (?:it|that|talking|speaking|now|please)|(?:please )?(?:be )?quiet|"
    r"hush|sh+|silence|pause|that(?:'ll| will) do)$",
    re.IGNORECASE,
)
#: The weak pauses: a stop only alone, or before an explicit correction.
_WEAK_STOP = re.compile(r"^(?:wait|hold (?:on|it)|one moment|hang on)$", re.IGNORECASE)
#: A clause that opens with a negation is an instruction or a statement, never a marker.
_NEGATED = re.compile(
    r"^(?:don't|do not|never(?! ?mind)|please don't|you mustn't|must not|mustn't|no longer|"
    r"it(?:'s| is) not|that(?:'s| is) not (?!what i meant))",
    re.IGNORECASE,
)
#: A clause that is a question: never a marker.
_QUESTION = re.compile(
    r"^(?:what|why|how|when|where|who|whom|whose|which|can you|could you|would you|will you|"
    r"do you|does|did|is|are|was|were|shall|should|may i|might)\b",
    re.IGNORECASE,
)
#: Explicit replacement or correction openers.
_REPLACEMENT_OPENER = re.compile(
    r"^(?:i meant|i mean|that(?:'s| is) not what i meant|let me rephrase|"
    r"let me put it another way|start (?:over|again)|make that|change that to|not that one|"
    r"not the |not that |rather the |forget (?:the|about the|about) |never ?mind the |"
    r"never ?mind about )",
    re.IGNORECASE,
)
#: A request that ends in "instead".
_INSTEAD = re.compile(r"\binstead$", re.IGNORECASE)
#: A bare "no" (or "nope"): a correction only when what follows corrects.
_BARE_NO = re.compile(r"^(?:no|nope|not)$", re.IGNORECASE)
_CORRECTION_FOLLOWS = re.compile(
    r"^(?:the|that|this|those|these|a|an|my|our|his|her|its|tell|give|explain|show|read|"
    r"describe|make|draft|send|find|look|list|name|use|put|take|try|do|let)\b",
    re.IGNORECASE,
)
#: Courtesy that follows a bare "no": a decline, not a correction.
_COURTESY = re.compile(
    r"^(?:thank you|thanks|that(?:'s| is) (?:all|fine|kind)|i(?:'m| am) fine)$", re.IGNORECASE
)
_CONTINUATION_OPENER = re.compile(
    r"^(?:and|also|then|after that|afterwards|as well|plus|next|additionally|on top of that|"
    r"while you'?re at it|in addition|once you'?ve done that|when you'?re done|following that|"
    r"and then|after you'?ve done that)(?=$|[\s,])",
    re.IGNORECASE,
)
_CONTINUATION_CLOSER = re.compile(r"\b(?:too|as well|also|after that|afterwards)$", re.IGNORECASE)


@dataclass(frozen=True)
class FollowUp:
    kind: Kind
    reason: str
    #: For a continuation only (2 October 2026): whether his words **complete or qualify
    #: the same request** — a fragment that cannot stand alone ("and why it works", "and
    #: also the orchard") — rather than **add a request of their own** ("And who wrote
    #: it?", "Also, name a fruit."). The first makes an unheard answer to the shorter
    #: request obsolete; the second leaves it valid.
    completes: bool = False

    @property
    def supersedes(self) -> bool:
        """Whether these words set aside an answer he has not begun to hear."""
        return self.kind in ("stop", "replacement")


def _prepare(text: str) -> str:
    prepared = text.strip().replace(chr(0x2019), "'")
    prepared = prepared.replace(chr(0x2014), " - ").replace(chr(0x2013), " - ")
    return _QUOTED.sub(" ", prepared)


def _clauses(text: str) -> list[tuple[str, bool]]:
    """Clauses, oldest first, each with her name and its discourse markers set aside,
    and whether the clause ended with a question mark."""
    out: list[tuple[str, bool]] = []
    for piece in re.finditer(r"[^.!?;:]+[.!?;:]*", text):
        raw = piece.group(0)
        asked = raw.rstrip().endswith("?")
        for part in re.split(r"\s+-\s+|,\s*|\s+\band\b\s+|\s+\bbut\b\s+", raw.rstrip(".!?;: ")):
            clause = _ADDRESS.sub(" ", part or "")
            clause = re.sub(r"\s+", " ", clause).strip(" ,")
            while True:
                stripped = _DISCOURSE.sub("", clause).strip(" ,:-")
                if stripped == clause:
                    break
                clause = stripped
            if clause:
                out.append((clause, asked))
    return out


#: A refusal and nothing else: "No.", "No, no, no." — with at most one other word among
#: them (a name). Read as a stop only when it was spoken over her answer.
_REFUSAL_WORD = re.compile(r"^(?:no|nope|nah)$", re.IGNORECASE)


def _refusal_only(lowered: str) -> bool:
    words = re.findall(r"[a-z']+", lowered)
    refusals = sum(1 for word in words if _REFUSAL_WORD.match(word))
    return refusals >= 1 and len(words) - refusals <= 1 and (refusals >= 2 or len(words) == 1)


#: After the additive opener, words that begin a request able to stand on its own: a
#: direct question by inversion, or an instruction. A wh-word alone does not decide it
#: ("and why it works" is a fragment; "And who wrote it?" is a question) — there the
#: recognizer's question mark does.
_STANDALONE_OPENER = re.compile(
    r"^(?:can|could|would|will|do|does|did|is|are|was|were|shall|should|may|might|have|has|"
    r"please|tell|give|explain|show|read|describe|make|draft|send|find|look|list|name|write|"
    r"say|check|remind|let|put|take|try|use|add|what about|how about)\b",
    re.IGNORECASE,
)


def _stands_alone(utterance: str, opening: str) -> bool:
    if utterance.strip().endswith("?"):
        return True
    remainder = opening
    while True:
        stripped = _CONTINUATION_OPENER.sub("", remainder, count=1).strip(" ,")
        if stripped == remainder:
            break
        remainder = stripped
    return bool(_STANDALONE_OPENER.match(remainder))


def follow_up(utterance: str, *, interrupting: bool = False) -> FollowUp:
    """The relationship of his new words to the request still being answered.

    `interrupting` (1 October 2026): his speech cut an answer he was hearing, or follows
    a stop he has just made. Only then is a bare refusal — "No.", "No, no, no." — read as
    a stop: said over her, it tells her to stop; said after she has finished, it is an
    answer to her and stays ambiguous.
    """
    lowered = _prepare(utterance).lower()
    if interrupting and _refusal_only(lowered):
        return FollowUp("stop", "a refusal and nothing else, spoken over her answer")
    clauses = _clauses(lowered)
    if not clauses:
        return FollowUp("ambiguous", "nothing said, or only discourse markers")
    stops: list[int] = []
    weak_stops: list[int] = []
    replacements: list[int] = []
    requests: list[int] = []  # substantive clauses: the new request, if any
    for index, (clause, asked) in enumerate(clauses):
        question = asked or bool(_QUESTION.match(clause))
        if not question and _STOP.match(clause):
            stops.append(index)
            continue
        if _NEGATED.match(clause):
            requests.append(index)
            continue
        if not question and _WEAK_STOP.match(clause):
            weak_stops.append(index)
            continue
        if not question and (_REPLACEMENT_OPENER.match(clause) or _INSTEAD.search(clause)):
            replacements.append(index)
            continue
        if not question and _BARE_NO.match(clause):
            following = clauses[index + 1][0] if index + 1 < len(clauses) else ""
            if (
                following
                and _CORRECTION_FOLLOWS.match(following)
                and not _COURTESY.match(following)
            ):
                replacements.append(index)
            continue
        requests.append(index)
    if replacements:
        return FollowUp(
            "replacement",
            "an explicit correction, withdrawal or redirection of the earlier request",
        )
    if stops:
        if requests:
            return FollowUp("replacement", "an explicit stop followed by a new request")
        return FollowUp("stop", f"a stop and nothing else: {clauses[stops[0]][0]!r}")
    if weak_stops and not requests:
        return FollowUp("stop", f"a pause and nothing else: {clauses[weak_stops[0]][0]!r}")
    opening = _ADDRESS.sub(" ", re.split(r"[.!?;:,]", lowered.strip())[0]).strip()
    if _CONTINUATION_OPENER.match(opening) or _CONTINUATION_CLOSER.search(clauses[-1][0]):
        if _stands_alone(utterance, opening):
            return FollowUp(
                "continuation", "an added request of its own, after the earlier one", False
            )
        return FollowUp(
            "continuation", "a fragment that completes or qualifies the earlier request", True
        )
    return FollowUp("ambiguous", "neither an explicit stop or replacement nor a clear continuation")
