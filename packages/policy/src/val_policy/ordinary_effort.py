"""May this ordinary turn be answered at LOW reasoning effort? — the bounded experiment.

Owner order of 28 September 2026 (night), pre-registered in
`docs/reviews/qualification/runs/2026-09-28-checkpoint/EFFORT_EXPERIMENT.md` §2 to §3 before
this module existed. Isolated experiment only: nothing here is admitted, and production
never reaches it (the switch that uses it is unset there).

Two classes, both drawn from his spoken use:

- **F** — a self-contained factual question (a definition, a general-knowledge fact, a
  named work) whose answer depends on nothing in this conversation, the house or Val;
- **C** — a short, self-contained craft request with an explicitly small scope (one
  line, one sentence, two ways, a title, a tip), no deliverable, no constraints.

Everything else stays on MEDIUM. Deterministic and closed: word patterns, no model call.
The context condition (a settled conversation) is read by the caller from the
authoritative state, through the same `pending_matter` the light route uses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from val_policy.light_conversation import ConversationState, pending_matter

_ADDRESS = re.compile(r"^\s*(?:val|my dear val)\s*[,.]?\s*|\s*[,.]?\s*\bval\b\s*[.?!]?\s*$", re.I)

#: Class F: the factual forms.
_FACTUAL = re.compile(
    r"^(?:what\s+(?:is|are|was|were)\s+(?:a|an|the)?\s*\S.*"
    r"|who\s+(?:wrote|painted|composed|invented|discovered|won|was|is)\s+\S.*"
    r"|when\s+(?:was|were|did)\s+\S.*"
    r"|in\s+what\s+year\s+(?:was|were|did)\s+\S.*"
    r"|what\s+year\s+(?:was|were|did)\s+\S.*"
    r"|where\s+(?:is|was|are)\s+\S.*"
    r"|what\s+is\s+the\s+difference\s+between\s+\S.*"
    r"|name\s+(?:a|an|one)\s+(?:famous|well-known|classic)\s+\S.*"
    r")[?.]?$",
    re.I,
)
#: Class C: the short craft forms, each with its own small scope.
_CRAFT = re.compile(
    r"^(?:give\s+me\s+one\s+(?:line\s+of\s+advice|tip|piece\s+of\s+advice)\s+(?:on|for|about)\s+\S.*"
    r"|name\s+(?:two|three)\s+ways\s+to\s+\S.*"
    r"|describe\s+(?:a|an|the)\s+\S.*\s+in\s+one\s+(?:sentence|line)"
    r"|suggest\s+a\s+title\s+for\s+\S.*"
    r"|tell\s+me\s+about\s+a\s+good\s+(?:opening|closing)\s+line"
    r")[?.]?$",
    re.I,
)
#: Rule 2: a correction or replacement.
_CORRECTION = re.compile(
    r"\b(?:no|not|actually|instead|rather|change|correction|i\s+meant|never\s+mind|scratch\s+that)\b",
    re.I,
)
#: Rule 3: a reference to earlier content.
_REFERENCE = re.compile(
    r"\b(?:that|those|it|them|which\s+of|again|recap|earlier|you\s+said|above|previous|last\s+one)\b",
    re.I,
)
#: Rule 4: instruction constraints beyond the class's own scope.
_CONSTRAINT = re.compile(
    r"\b(?:only|exactly|must|do\s+not|don't|without|under\s+\d+|fewer\s+than|at\s+most|format|"
    r"bullet|list|in\s+(?:french|spanish|german|italian|latin)|sign\s+it|message\s+only|"
    r"keep\s+it|word\s+count)\b",
    re.I,
)
#: Rule 5: an action, a deliverable or a decision.
_ACTION = re.compile(
    r"\b(?:draft|send|email|e-mail|letter|message|invitation|invite|schedule|cancel|book|"
    r"remind|reminder|buy|pay|delete|save|note|record|should\s+i|shall\s+i|can\s+you\s+\w+\s+(?:it|this))\b",
    re.I,
)
#: Rule 6: about Val, the house or his own matters.
_SELF_OR_HOUSE = re.compile(
    r"\b(?:you|your|yours|yourself|my|mine|our|ours|we|us|time|date|today|tonight|tomorrow|"
    r"yesterday|now|weather|backup|system|the\s+house)\b",
    re.I,
)
#: Rule 7: a consequential subject.
_CONSEQUENTIAL = re.compile(
    r"\b(?:health|medical|medicine|dose|symptom|legal|law|lawyer|contract|money|price|cost|"
    r"invest|tax|bank|password|security|safety|danger|emergency)\b",
    re.I,
)


@dataclass(frozen=True)
class EffortDecision:
    #: "F" or "C" when LOW may carry the turn; None when it stays on MEDIUM.
    klass: str | None
    reason: str


def _one_request(text: str) -> bool:
    """One sentence, one request: no second sentence, no joined clause of a second ask."""
    sentences = [s for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s]
    if len(sentences) != 1:
        return False
    return not re.search(
        r"\b(?:and|also|then|plus)\s+(?:can|could|would|will|do|did|is|what|who|how|why|tell|give|name|describe|remind)\b",
        text,
        re.I,
    )


def request_class(text: str) -> EffortDecision:
    """Rules 1 to 7, on his words alone."""
    words = _ADDRESS.sub("", text.strip()).strip()
    if not words:
        return EffortDecision(None, "no words")
    if not _one_request(words):
        return EffortDecision(None, "more than one request or sentence")
    for pattern, reason in (
        (_CORRECTION, "a correction or replacement"),
        (_REFERENCE, "a reference to earlier content"),
        (_CONSTRAINT, "an instruction constraint"),
        (_ACTION, "an action, deliverable or decision"),
        (_SELF_OR_HOUSE, "about Val, the house or his own matters"),
        (_CONSEQUENTIAL, "a consequential subject"),
    ):
        if pattern.search(words):
            return EffortDecision(None, reason)
    if _FACTUAL.match(words):
        return EffortDecision("F", "a self-contained factual question")
    if _CRAFT.match(words):
        return EffortDecision("C", "a short, self-contained craft request")
    return EffortDecision(None, "not one of the defined classes")


def decide_effort(
    text: str,
    state: ConversationState,
    *,
    untrusted_content: bool,
    correction_sensitive: bool,
) -> EffortDecision:
    """Rules 1 to 9: his words, then the authoritative context, then the turn's content.

    `correction_sensitive` and `untrusted_content` are facts only the caller can read
    (a revised or withdrawn message in the thread; an attachment bound to the turn or
    retrieved excerpts / House Recall in the request); either keeps the turn on MEDIUM.
    """
    decision = request_class(text)
    if decision.klass is None:
        return decision
    if correction_sensitive:
        return EffortDecision(None, "correction-sensitive context")
    if untrusted_content:
        return EffortDecision(None, "untrusted or bound content in the request")
    open_matter = pending_matter(state)
    if open_matter is not None:
        return EffortDecision(None, f"the context is not settled: {open_matter}")
    return decision
