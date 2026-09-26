"""How long to wait for him to continue — adaptive turn completion, owner order §7.

The fixed resume window (1.1 s after the recognizer's endpoint) exists so that a
sentence he pauses inside is not answered in two halves. It is also, on every turn,
1.1 s of silence after he has plainly finished. The transcript itself says a good
deal about which case this is: "Good evening, Val." is complete; "Good evening, Val,
and" is not; "Good evening Val" without a mark is uncertain.

Deterministic cues on the final transcript, and nothing else: no model, no detector.
(The LiveKit turn detector the order named is licensed only for use with LiveKit
Agents and so is not integrated; see the redesign record.) Failure of a cue is a
longer wait, never a shorter one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: A final word that says the sentence is not over.
_CONTINUING_TAIL = re.compile(
    r"\b(and|but|or|so|because|then|although|though|while|if|when|that|which|who|to|of|"
    r"for|with|by|at|in|on|the|a|an|my|your|our|his|her|their|is|are|was|were|be|"
    r"um|uh|er|erm|like)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Completion:
    #: `complete`, `uncertain` or `continuing`.
    state: str
    #: The resume window to wait, in seconds.
    grace_seconds: float
    reason: str


def completion_of(final_text: str, default_grace: float) -> Completion:
    """The resume window this utterance deserves, from its own final transcript."""
    words = final_text.strip()
    if not words:
        return Completion("uncertain", default_grace, "nothing recognised")
    body = words.rstrip("\"')]}")
    last_word = re.sub(r"[^\w']+$", "", body).split()[-1] if body.split() else ""
    if body.endswith((",", ";", ":", "—", "-", "…")):
        return Completion("continuing", default_grace * 1.5, "ends on a pause mark")
    if _CONTINUING_TAIL.search(last_word):
        return Completion("continuing", default_grace * 1.5, f"ends on {last_word!r}")
    if body.endswith((".", "!", "?")):
        return Completion("complete", default_grace * 0.4, "ends a sentence")
    return Completion("uncertain", default_grace, "no terminal mark")
