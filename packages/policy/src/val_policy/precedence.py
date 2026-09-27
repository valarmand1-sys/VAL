"""What his next words are to the answer still being made — owner order of 26 September 2026.

"CORRECT THE RELEASE GAPS…", §1. When he speaks again while her answer to his previous
words is still being generated and none of it has been heard, the relationship between
the two utterances decides what happens to that answer — and it is **his words** that
decide it, deterministically, never the fact that words arrived:

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

The rules are closed, cheap and readable; no model is asked. They fail toward keeping
both requests: a marker has to be at the front of what he said (or be one of the few
that mean replacement wherever they stand) before an answer is set aside.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Kind = Literal["stop", "replacement", "continuation", "ambiguous"]

#: The name, as he says it, and the small politenesses that carry no meaning here.
_ADDRESS = re.compile(r"\b(?:val|please|there|thank you|thanks)\b", re.IGNORECASE)

#: A stop with nothing else in it.
_STOP = re.compile(
    r"^(?:stop|never mind|nevermind|forget (?:it|that|about it)|scratch that|cancel(?: that| it)?|"
    r"that(?:'s| is| will be) enough|enough|hold (?:on|it)|wait|belay that|leave it|"
    r"don'?t bother|no need|not now|drop it|let it go|never mind that)$",
    re.IGNORECASE,
)

#: Markers that mean replacement wherever they stand in the utterance.
_REPLACEMENT_ANYWHERE = re.compile(
    r"\b(?:instead|never ?mind|forget (?:it|that|about|the)|scratch that|cancel that|belay that|"
    r"i meant|i mean|let me rephrase|start (?:over|again)|not that one|rather than that)\b",
    re.IGNORECASE,
)
#: Markers that mean replacement when they open what he says.
_REPLACEMENT_LEADING = re.compile(
    r"^(?:actually|no|nope|wait|hold on|sorry|correction|not that|stop|rather|on second thought|"
    r"change of plan|different(?:ly)?|make that|let me change that)\b",
    re.IGNORECASE,
)
#: Openings that add to the earlier request rather than replace it.
_CONTINUATION_LEADING = re.compile(
    r"^(?:and|also|then|after that|afterwards|as well|plus|next|too|additionally|on top of that|"
    r"while you'?re at it|in addition|once you'?ve done that|when you'?re done|and then|"
    r"after you'?ve done that|following that)\b",
    re.IGNORECASE,
)
_CONTINUATION_TRAILING = re.compile(
    r"\b(?:too|as well|also|after that|afterwards)[.!?]*$", re.IGNORECASE
)


@dataclass(frozen=True)
class FollowUp:
    kind: Kind
    reason: str

    @property
    def supersedes(self) -> bool:
        """Whether these words set aside an answer he has not begun to hear."""
        return self.kind in ("stop", "replacement")


def _bare(text: str) -> str:
    lowered = text.strip().lower().replace(chr(0x2019), "'").replace(chr(0x2014), " ")
    lowered = _ADDRESS.sub(" ", lowered)
    lowered = re.sub(r"[,.!?;:" + chr(0x2026) + r"]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def follow_up(utterance: str) -> FollowUp:
    """The relationship of his new words to the request still being answered."""
    bare = _bare(utterance)
    if not bare:
        return FollowUp("ambiguous", "nothing said")
    if _STOP.match(bare):
        return FollowUp("stop", f"a stop and nothing else: {bare!r}")
    if _CONTINUATION_LEADING.match(bare):
        return FollowUp("continuation", "opens as an addition to the earlier request")
    if _REPLACEMENT_LEADING.match(bare) or _REPLACEMENT_ANYWHERE.search(bare):
        return FollowUp(
            "replacement", "a correction, withdrawal or redirection of the earlier request"
        )
    if _CONTINUATION_TRAILING.search(bare):
        return FollowUp("continuation", "closes as an addition to the earlier request")
    return FollowUp("ambiguous", "neither a clear replacement nor a clear continuation")
