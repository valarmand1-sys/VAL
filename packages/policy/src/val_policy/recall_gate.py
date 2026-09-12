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
            anchors.append(f"token {word!r}")
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


# =============================================================================
# House Recall — the explicitly triggered cross-conversation path
# (ruling, 12 September 2026)
# =============================================================================
#
# A second gate, independent of `gate_recall`, which it never alters. Automatic
# recall stays project-scoped and an unassigned conversation stays a clean room
# for it; House Recall is the one authorised exception: it runs only when the
# message contains an explicit cross-conversation reference from the closed,
# version-controlled inventory below, and never when that reference is
# demonstrably satisfied by the retained thread. No provider call, no
# semantics beyond token sequences; ambiguity is a non-match, and a non-match
# is *not run*.

#: Explicit references to earlier conversation, as token sequences. Every
#: variant is spelled out; nothing is inflected or inferred.
HOUSE_RECALL_PHRASES: tuple[tuple[str, ...], ...] = (
    ("we", "discussed"), ("we", "have", "discussed"), ("we've", "discussed"),
    ("we", "talked", "about"), ("we", "have", "talked"), ("we've", "talked"),
    ("we", "decided"), ("we", "have", "decided"), ("we've", "decided"),
    ("we", "settled"), ("we", "have", "settled"), ("we've", "settled"),
    ("we", "agreed"), ("we", "have", "agreed"), ("we've", "agreed"),
    ("remember", "when"), ("do", "you", "remember"), ("what", "do", "you", "remember"),
    ("what", "did", "we"),
    ("in", "another", "project"), ("from", "another", "project"),
    ("from", "a", "different", "project"), ("from", "the", "other", "project"),
    ("across", "my", "projects"), ("across", "your", "projects"), ("across", "our", "projects"),
    ("across", "my", "conversations"), ("across", "your", "conversations"),
    ("across", "our", "conversations"),
)  # fmt: skip

#: "you said / told me / mentioned" is a cross-conversation reference only with
#: a temporal marker somewhere in the message; alone it may be about this thread.
HOUSE_RECALL_ATTRIBUTION_PHRASES: tuple[tuple[str, ...], ...] = (
    ("you", "said"), ("you", "told", "me"), ("you", "mentioned"),
)  # fmt: skip
HOUSE_RECALL_TEMPORAL_TOKENS: frozenset[str] = frozenset(
    {"earlier", "before", "previously", "last", "once", "yesterday"}
)

#: "<earlier|previous|prior|past|other> conversation(s)".
HOUSE_RECALL_CONVERSATION_ADJECTIVES: frozenset[str] = frozenset(
    {"earlier", "previous", "prior", "past", "other"}
)
HOUSE_RECALL_CONVERSATION_NOUNS: frozenset[str] = frozenset({"conversation", "conversations"})

#: An explicit request to search earlier conversations: a search verb and the
#: noun anywhere in the message.
HOUSE_RECALL_SEARCH_TOKENS: frozenset[str] = frozenset({"search", "searching"})


@dataclass(frozen=True)
class HouseGateDecision:
    """Whether House Recall runs, and the positive reason either way."""

    run: bool
    #: ``no_cross_conversation_reference`` | ``tier_one`` | ``thread_grounded``
    #: when ``run`` is False; None when it runs.
    reason: str | None
    #: What established the decision, for the log and the record.
    detail: str


def _phrase_in(tokens: list[str], phrase: tuple[str, ...]) -> bool:
    n = len(phrase)
    return any(tuple(tokens[i : i + n]) == phrase for i in range(len(tokens) - n + 1))


def _house_matches(tokens: list[str]) -> tuple[str, ...]:
    """Every inventory form present, in a stable order. Empty means no match."""
    found: list[str] = []
    for phrase in HOUSE_RECALL_PHRASES:
        if _phrase_in(tokens, phrase):
            found.append(" ".join(phrase))
    if any(t in HOUSE_RECALL_TEMPORAL_TOKENS for t in tokens):
        for phrase in HOUSE_RECALL_ATTRIBUTION_PHRASES:
            if _phrase_in(tokens, phrase):
                found.append(" ".join(phrase) + " (with a temporal marker)")
    for i in range(len(tokens) - 1):
        if (
            tokens[i] in HOUSE_RECALL_CONVERSATION_ADJECTIVES
            and tokens[i + 1] in HOUSE_RECALL_CONVERSATION_NOUNS
        ):
            found.append(f"{tokens[i]} {tokens[i + 1]}")
    if any(t in HOUSE_RECALL_SEARCH_TOKENS for t in tokens) and any(
        t in HOUSE_RECALL_CONVERSATION_NOUNS for t in tokens
    ):
        found.append("search … conversations")
    return tuple(found)


def gate_house_recall(message: str, context: ThreadContext) -> HouseGateDecision:
    """Decide whether the explicitly triggered House Recall runs for this turn.

    Runs only on an inventory match; never on a Tier One form; and not when
    every quoted span in the message is found verbatim in the retained thread,
    because a reference the thread already satisfies is thread-local. This
    function never consults, and never alters, `gate_recall`.
    """
    tokens = [t.lower() for t in _tokens(message)]
    matched = _house_matches(tokens)
    if not matched:
        return HouseGateDecision(
            False, "no_cross_conversation_reference", "no inventory form is present"
        )
    if _tier_one(message) is not None:
        return HouseGateDecision(False, "tier_one", "a Tier One closed form")
    spans = _quoted_spans(message)
    if spans and context.retained:
        thread_lower = context.text.lower()
        if all(span.lower() in thread_lower for span in spans):
            return HouseGateDecision(
                False,
                "thread_grounded",
                "every quoted span occurs verbatim in the retained thread",
            )
    return HouseGateDecision(
        True, None, "explicit cross-conversation reference: " + ", ".join(matched)
    )
