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


# --- The adaptive endpoint (owner order of 27 September 2026, §3) ---------------------
#
# The fixed path waits 650 ms of silence for the recognizer to endpoint, ~0.13 s for the
# final decode, then the 1.1 s resume window: about 1.9 s of silence before his words are
# submitted, on every turn. With the adaptive endpoint the recognizer endpoints after
# `ADAPTIVE_MIN_SILENCE_MS` and this policy sizes the window from what he actually said,
# so that the **total** silence before submission is:
#
# - about 0.65 s when the words are plainly finished (`complete`);
# - about the same 1.9 s as today when they are not clearly finished (`uncertain`) —
#   ambiguity never buys a shorter wait;
# - longer than today when they are plainly unfinished (`continuing`).
#
# `complete` is never read from punctuation alone: a terminal mark is necessary but not
# sufficient. It must come with a closed social form the frozen router recognises, a
# closed question of three words or more, or a closed sentence of four words or more —
# and with no trailing conjunction, preposition, article, auxiliary or hesitation. A
# resumption after an early submission is still caught: speech that resumes inside the
# original silence bound cancels the early turn and joins the two halves (voice session).

#: The recognizer's minimum silence under the adaptive endpoint (the fixed path: 650 ms).
ADAPTIVE_MIN_SILENCE_MS = 400
#: The total silence, from the end of his speech, that the fixed path allows before a
#: resumed stretch of speech is a new turn: 650 ms endpoint + 1.1 s window + ~0.13 s decode.
RESUME_SILENCE_BOUND_S = 1.9
_DECODE_S = 0.13
#: Windows after the final transcript, per state (the endpoint and decode come first).
COMPLETE_GRACE_S = 0.12
UNCERTAIN_GRACE_S = RESUME_SILENCE_BOUND_S - ADAPTIVE_MIN_SILENCE_MS / 1000 - _DECODE_S
CONTINUING_GRACE_S = UNCERTAIN_GRACE_S + 0.7

_HESITATION_TAIL = re.compile(
    r"\b(?:um+|uh+|er+|erm|hmm+|mm+|well|so|like|i mean|you know|let me think|let's see|"
    r"actually|basically)$",
    re.IGNORECASE,
)
_AUXILIARY_TAIL = re.compile(r"is|are|was|were|be|been", re.IGNORECASE)
#: Words that leave a clause open wherever they end it, not in the older tail list.
_OPEN_TAIL = re.compile(r"whether|about|into|from|than|onto|towards|toward|upon", re.IGNORECASE)
_QUESTION_OPENER = re.compile(
    r"^(?:what|why|how|when|where|who|whom|whose|which|can|could|would|will|shall|should|"
    r"do|does|did|is|are|was|were|have|has|had|may|might|must)\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[A-Za-z][A-Za-z']*")
_NAME = re.compile(r"\b(?:val|vowel)\b", re.IGNORECASE)


def _last_sentence(text: str) -> str:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p.strip()]
    return parts[-1] if parts else ""


def endpoint_completion(final_text: str) -> Completion:
    """The window after an adaptive endpoint, from the final transcript's own shape."""
    from val_policy.light_conversation import classify_sentence

    words = final_text.strip()
    if not words:
        return Completion("uncertain", UNCERTAIN_GRACE_S, "nothing recognised")
    body = words.rstrip("\"')]} ")
    bare_words = _WORD.findall(body)
    last_word = bare_words[-1] if bare_words else ""
    if body.endswith((",", ";", ":", "\u2014", "\u2013", "-", "\u2026", "...")):
        return Completion("continuing", CONTINUING_GRACE_S, "ends on a pause mark")
    closed = body.endswith((".", "!", "?"))
    # A final auxiliary before a terminal mark closes an embedded question ("what a
    # caesura is.", "how long should it be?"); without the mark it leaves one open.
    auxiliary = _AUXILIARY_TAIL.fullmatch(last_word) is not None
    if (_CONTINUING_TAIL.search(last_word) or _OPEN_TAIL.fullmatch(last_word)) and not (
        auxiliary and closed
    ):
        return Completion("continuing", CONTINUING_GRACE_S, f"ends on {last_word!r}")
    tail = re.sub(r"[.!?]+$", "", body).strip().lower()
    if _HESITATION_TAIL.search(tail):
        return Completion("continuing", CONTINUING_GRACE_S, "ends on a hesitation")
    if not body.endswith((".", "!", "?")):
        return Completion("uncertain", UNCERTAIN_GRACE_S, "no terminal mark")
    sentences = [p for p in re.split(r"(?<=[.!?])\s+", body) if p.strip()]
    # Greetings, thanks and farewells only: a bare "Yes." or "No." may open a correction.
    if sentences and all(classify_sentence(s)[0] == 1 for s in sentences):
        return Completion("complete", COMPLETE_GRACE_S, "a closed greeting, thanks or farewell")
    last = _last_sentence(body)
    counted = [w for w in _WORD.findall(last) if not _NAME.fullmatch(w)]
    if last.endswith("?") and _QUESTION_OPENER.match(last) and len(counted) >= 3:
        return Completion("complete", COMPLETE_GRACE_S, "a closed question")
    if len(counted) >= 4:
        return Completion("complete", COMPLETE_GRACE_S, "a closed sentence of four words or more")
    return Completion("uncertain", UNCERTAIN_GRACE_S, "a terminal mark on too few words to judge")
