"""The cross-conversation recall gate — deterministic, no model, fails toward recall.

Ruled 10 September 2026 (`01-architecture.md` §5.5, the per-turn necessity rule;
`04-layer-0.md` WP-0.7 amendment). Cross-conversation recall is no longer
universal: before retrieval is attempted, this gate decides *whether it runs*.
It never touches Val's model, effort, capability floor, persona, or reasoning;
it gates retrieval across other conversations and nothing else. Same-conversation
history is never gated. "No recall needed" never means "no context needed".

Three deterministic skip paths, in precedence order, each a positive state:

- ``no_project_scope`` — the conversation is explicitly outside every project.
  The unassigned pool is a clean room: it is not searched at all.
- ``tier_one`` — the *complete* normalised message is one of a finite family of
  closed forms that are intrinsically safe without cross-thread context. A
  whitelist, not a blacklist: the negative checks below are necessary, never
  sufficient.
- ``tier_two`` — the message's meaning depends on the current thread, and every
  referent it carries is mechanically grounded in context Val will actually
  receive on this call (the retained history and the record-state facts), with
  at least one positive anchor established. Every capitalised token outside the
  safe vocabulary must be grounded; the only orthographic exemption is the
  closed set "You" / "Please", and "It" solely at the head of ``It is <HH:MM>``.

Everything else recalls. When applicability is uncertain the gate says so by
letting retrieval run, never by guessing that it need not.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from val_policy.words import count_words

#: Tier One's finite grammar. These are the executable forms; the categories
#: they belong to (greeting, thanks, affirmation, negation, acknowledgement)
#: are explanatory only and are not matching rules. Nothing is inferred.
TIER_ONE_BASE_FORMS: tuple[tuple[str, ...], ...] = (
    ("hello",),
    ("hi",),
    ("thanks",),
    ("thank", "you"),
    ("yes",),
    ("no",),
    ("okay",),
    ("ok",),
)

#: The already-authorised direct addresses, combinable with a base form.
ADDRESS_FORMS: tuple[tuple[str, ...], ...] = (("val",), ("my", "lord"))

#: Every token Tier One may contain. "you" is here solely because "thank you"
#: needs it; a message containing "you" is not thereby eligible.
TIER_ONE_SAFE_VOCABULARY: frozenset[str] = frozenset(
    token for form in (*TIER_ONE_BASE_FORMS, *ADDRESS_FORMS) for token in form
)

#: The closed back-reference inventory, exactly as ruled. No inflections beyond
#: those listed; an absent form fails toward recall by not matching anything.
BACK_REFERENCE_TOKENS: frozenset[str] = frozenset(
    {
        "earlier", "before", "last", "yesterday", "remember", "recall", "recalled",
        "recalling", "discussed", "discuss", "discussing", "agreed", "agree",
        "agreeing", "decided", "decide", "deciding", "settled", "settle", "settling",
        "said", "say", "saying", "mentioned", "mention", "mentioning", "previously",
        "previous", "again",
    }
)  # fmt: skip
BACK_REFERENCE_PHRASES: tuple[tuple[str, ...], ...] = (("the", "other"), ("that", "one"))

#: The immediate-thread forms Tier Two may ground in the current thread. Every
#: other inventory item is an explicit cross-thread signal and recalls.
IMMEDIATE_THREAD_TOKENS: frozenset[str] = frozenset({"again"})
IMMEDIATE_THREAD_PHRASES: tuple[tuple[str, ...], ...] = (("the", "other"), ("that", "one"))

#: Tier One's length condition, in ruled lexical words.
TIER_ONE_MAX_WORDS = 15

#: Tier Two's closed orthographic exemption (ruled 10 September 2026): the only
#: capitalised tokens outside the safe vocabulary that need no grounding.
TIER_TWO_ORTHOGRAPHIC_EXEMPTION: frozenset[str] = frozenset({"You", "Please"})

#: The one syntactic form in which a sentence-initial "It" is nonreferential:
#: the local-time assertion of the captured regression, ``It is <HH:MM>``.
_TIME_ASSERTION = re.compile(r"It is \d{1,2}:\d{2}\b")

_WORD = re.compile("[^\\W_]+(?:['\u2019][^\\W_]+)*", re.UNICODE)
_QUOTED = re.compile('["\u201c]([^"\u201d]+)["\u201d]|\u2018([^\u2019]+)\u2019')
_DIGIT = re.compile(r"\d")


@dataclass(frozen=True)
class GateDecision:
    """Whether cross-conversation recall runs, and the positive reason when it does not."""

    run: bool
    #: One of ``no_project_scope`` | ``tier_one`` | ``tier_two`` when ``run`` is False.
    reason: str | None
    #: What established the decision, for the log.
    detail: str


@dataclass(frozen=True)
class ThreadContext:
    """What Val will actually receive on this call, for grounding."""

    #: The retained prior same-conversation messages, oldest first: (role, content).
    #: Only messages selected into the outbound history count.
    retained: Sequence[tuple[str, str]]
    #: Exact dynamic facts the record-state envelope will carry (the local time).
    envelope_facts: Sequence[str] = ()

    @property
    def previous_val_message(self) -> str | None:
        for role, content in reversed(self.retained):
            if role != "user":
                return content
        return None

    @property
    def text(self) -> str:
        return "\n".join(content for _, content in self.retained)


def _tokens(message: str) -> list[str]:
    return _WORD.findall(message)


def _has_quotation_marks(message: str) -> bool:
    if any(mark in message for mark in '"\u201c\u201d\u2018\u2019'):
        return True
    # A straight apostrophe is a quotation mark unless it sits inside a word.
    return re.search(r"(?<![^\W_])'|'(?![^\W_])", message) is not None


def _contains_back_reference(lower_tokens: list[str]) -> tuple[str, ...]:
    found = [t for t in lower_tokens if t in BACK_REFERENCE_TOKENS]
    for phrase in BACK_REFERENCE_PHRASES:
        n = len(phrase)
        windows = (tuple(lower_tokens[i : i + n]) for i in range(len(lower_tokens) - n + 1))
        if any(window == phrase for window in windows):
            found.append(" ".join(phrase))
    return tuple(found)


def _tier_one(message: str) -> str | None:
    """The finite grammar, with every necessary check stated explicitly."""
    if "?" in message:
        return None
    if _DIGIT.search(message):
        return None
    if _has_quotation_marks(message):
        return None
    if count_words(message) > TIER_ONE_MAX_WORDS:
        return None
    tokens = _tokens(message)
    if not tokens:
        return None
    lower = [t.lower() for t in tokens]
    if any(t[0].isupper() and t.lower() not in TIER_ONE_SAFE_VOCABULARY for t in tokens):
        return None  # sentence-initial position exempts nothing
    if _contains_back_reference(lower):
        return None
    if any(t not in TIER_ONE_SAFE_VOCABULARY for t in lower):
        return None
    forms = [(*base,) for base in TIER_ONE_BASE_FORMS]
    for base in forms:
        if lower == list(base):
            return f"form {' '.join(base)!r}"
        for address in ADDRESS_FORMS:
            if lower == [*base, *address]:
                return f"form {' '.join(base)!r} + address {' '.join(address)!r}"
            if lower == [*address, *base]:
                return f"address {' '.join(address)!r} + form {' '.join(base)!r}"
    return None


def _quoted_spans(message: str) -> list[str]:
    spans = []
    for match in _QUOTED.finditer(message):
        span = (match.group(1) or match.group(2) or "").strip()
        # Terminal punctuation inside the closing quote is orthography, not content.
        spans.append(span.rstrip(".,;:!"))
    return [s for s in spans if s]


def _tier_two(message: str, context: ThreadContext) -> str | None:
    """Positively grounded thread-local: every referent grounded, at least one anchor."""
    if "?" in message:
        return None
    if not context.retained:
        return None  # nothing in the thread to ground anything in
    thread = context.text
    thread_lower = thread.lower()
    anchors: list[str] = []

    # Quoted strings: each must occur verbatim in the retained history.
    for span in _quoted_spans(message):
        if span in thread:
            anchors.append(f"quote {span!r}")
        else:
            return None

    # Capitalised tokens outside quoted spans must be grounded exactly (case-
    # insensitive token identity) in the retained history or the envelope's
    # facts, or Tier Two fails toward recall. Ruled 10 September 2026: there is
    # no general sentence-initial exemption — a sentence-initial proper noun can
    # be a new external referent. The closed orthographic exemption is "You" and
    # "Please", plus the safe vocabulary; sentence-initial "It" is exempt only
    # when it begins the mechanically recognisable local-time assertion
    # ``It is <HH:MM>``, and nowhere else. Nothing infers whether an unknown
    # capitalised word is a proper noun.
    stripped = _QUOTED.sub(" . ", message)
    facts_lower = " ".join(context.envelope_facts).lower()
    for m in _WORD.finditer(stripped):
        word = m.group(0)
        if not word[0].isupper():
            continue
        if word.lower() in TIER_ONE_SAFE_VOCABULARY or word in TIER_TWO_ORTHOGRAPHIC_EXEMPTION:
            continue
        if word == "It" and _TIME_ASSERTION.match(stripped, m.start()):
            continue
        pattern = r"(?<![^\W_])" + re.escape(word.lower()) + r"(?![^\W_])"
        if re.search(pattern, thread_lower) or re.search(pattern, facts_lower):
            anchors.append(f"word {word!r}")
        else:
            return None

    # Back-references: only the immediate-thread forms, and only with a prior Val
    # message to refer to; any other inventory item is a cross-thread signal.
    lower = [t.lower() for t in _tokens(stripped)]
    found = _contains_back_reference(lower)
    for item in found:
        immediate = (
            item in IMMEDIATE_THREAD_TOKENS or tuple(item.split()) in IMMEDIATE_THREAD_PHRASES
        )
        if immediate and context.previous_val_message is not None:
            anchors.append(f"immediate back-reference {item!r}")
        else:
            return None

    # An exact dynamic fact from the envelope counts as an anchor.
    for fact in context.envelope_facts:
        if fact and fact in message:
            anchors.append(f"envelope fact {fact!r}")

    if not anchors:
        return None
    return "; ".join(anchors)


def gate_recall(message: str, *, no_project: bool, context: ThreadContext) -> GateDecision:
    """Decide whether cross-conversation recall runs for this turn.

    Precedence, exactly one primary reason: no_project_scope, then tier_one,
    then tier_two. Anything unmatched runs recall.
    """
    if no_project:
        return GateDecision(
            False,
            "no_project_scope",
            "explicit no-project scope: the unassigned pool is not searched",
        )
    tier_one = _tier_one(message)
    if tier_one is not None:
        return GateDecision(False, "tier_one", tier_one)
    tier_two = _tier_two(message, context)
    if tier_two is not None:
        return GateDecision(False, "tier_two", tier_two)
    return GateDecision(True, None, "no deterministic skip applies; recall runs")
