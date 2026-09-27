"""Which spoken turns may take the fast local route — owner order, 26 September 2026 (§5).

Two tiers, each enabled separately in a candidate build and never in production
without his ruling:

* **Tier 1** — a standalone greeting, thanks or farewell, with no instruction and no
  question in it.
* **Tier 2** — narrowly defined light conversation: a pleasantry about how one is, a
  remark about the weather or the hour, a brief acknowledgement that answers nothing.

Everything else goes to MEDIUM. **Eligibility is about the work a turn requires, not
its wording**: a greeting followed by a request is a request; "Yes, do it" is a
decision; "How fast are you?" asks about her capabilities, which need authoritative
state; a short affirmation answers whatever she last asked, and is only light when
she asked nothing. The rules are deterministic, closed and cheap — no model call —
and they fail toward MEDIUM whenever they do not recognise the whole utterance.

The fast provider has no tools, no writes and no egress; Core assembles, checks,
persists and delivers the answer exactly as for any turn. Only the route differs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Words that make a turn work rather than pleasantry, wherever they appear.
_WORK = re.compile(
    r"\b("
    # instructions, decisions, actions
    r"do|make|change|finish\w*|done|send|write|draft|book|schedule|plan\w*|remind\w*|"
    r"cancel|stop|start|open|close|save|delete|move|set|fix|check|look|find|search|"
    r"read|show|tell|explain|summar\w*|describe|list|compare|decide|decision|choose|"
    r"pick|go ahead|proceed|instead|rather|actually|play|"
    # judgment and advice
    r"should|ought|believe|think|opinion|advice|advise|recommend|suggest|better|best|"
    r"worse|wrong|agree|disagree|"
    # memory, record and project matter
    r"remember|recall|forget|yesterday|last (?:week|time|night)|earlier|before|"
    r"project|invitation|venue|reader|scene|act|chapter|page|note|"
    r"deadline|meeting|email|message|file|document|letter|"
    # her capabilities, performance and completed work
    r"can you|could you|will you|would you|are you able|do you know|did you|have you|"
    r"how (?:fast|quick|slow|long|many|much|far)|speed|faster|slower|latency|delay|"
    r"listen|record\w*|measure|tuning|model|voice model|capab\w*|"
    # negation of a prior instruction, corrections
    r"not that|no,? (?:not|the)|wait|hold on|never mind|correction|i meant|"
    r"\d"
    r")\b",
    re.IGNORECASE,
)

#: The name, as he says it, and the small forms of address a greeting may carry.
_ADDRESS = re.compile(r"\b(val|dear|there|again|to you|too|as well)\b", re.IGNORECASE)

_GREETING = re.compile(
    r"^(good (?:morning|afternoon|evening|day)|hello|hi|hey|greetings|evening|morning|"
    r"afternoon|welcome back|it'?s (?:me|only me))$",
    re.IGNORECASE,
)
_THANKS = re.compile(
    r"^((?:many |very many )?thanks?(?: you| so much| very much| a lot| kindly| for that| for "
    r"this| indeed)*|much obliged|much appreciated|cheers|that(?:'s| is| was) (?:very )?"
    r"(?:kind|helpful|lovely)(?: of you)?)$",
    re.IGNORECASE,
)
_FAREWELL = re.compile(
    r"^(goodbye|good ?bye|bye|bye for now|good night|goodnight|sleep well|farewell|"
    r"see you(?: later| tomorrow| soon| in the morning)?|until (?:tomorrow|later|next time|"
    r"the morning)|that(?:'s| is| will be) all(?: for now| for tonight| for today)?|"
    r"nothing (?:else|more)(?: for now| tonight| today)?|i(?:'m| am) (?:off|done)(?: for "
    r"(?:the )?(?:night|evening|day|now))?|talk (?:later|soon|tomorrow)|carry on)$",
    re.IGNORECASE,
)

#: Tier 2: how one is, and small talk that asks for no judgment.
_PLEASANTRY_QUESTION = re.compile(
    r"^(how are you(?: (?:this|tonight|today|this evening|this morning))?(?: (?:evening|"
    r"morning|afternoon))?|how(?:'s| is| has) your (?:evening|day|morning|night|afternoon)"
    r"(?: been| going)?|how(?:'s| is) everything|how do you do|(?:are you|all) well"
    r"(?: with you)?|"
    r"(?:is )?everything (?:all right|alright|well|fine)(?: with you)?|"
    r"how(?:'s| is) the (?:house|weather)(?: tonight| today)?|(?:is it|is the house) quiet"
    r"(?: tonight| today)?)$",
    re.IGNORECASE,
)
_PLEASANTRY_STATEMENT = re.compile(
    r"^(i(?:'m| am) (?:well|fine|good|all right|alright|tired|weary|glad|pleased|home|back)"
    r"(?: (?:tonight|today|this evening|this morning|now))?(?:,? thank you| thanks)?|"
    r"(?:it(?:'s| is|'s been| has been| was) )?(?:a )?(?:long|rough|quiet|busy|hard|good|"
    r"lovely|fine|pleasant|tiring|slow|cold|warm|wet|grey|gray|dark|late|early) "
    r"(?:day|week|night|evening|morning|afternoon|one)(?: (?:today|tonight|here|so far))?|"
    r"(?:it(?:'s| is) )?(?:raining|snowing|windy|cold|warm|hot|dark|late|quiet|lovely)"
    r"(?: (?:out|outside|tonight|today|here|this evening|this morning))?|"
    r"(?:the )?(?:weather|evening|night|day)(?:'s| is) (?:lovely|fine|dreadful|foul|"
    r"pleasant|cold|warm|quiet|beautiful)(?: (?:tonight|today|out|outside))?|"
    r"(?:lovely|nice|glad|good) to (?:hear (?:it|that|you|your voice|you'?re (?:well|there))|"
    r"see you|be back|be home)|glad (?:you'?re|to hear you'?re) (?:well|there)|"
    r"just (?:checking in|saying hello|passing through|popping in)|nothing much|"
    r"same as ever|as ever)$",
    re.IGNORECASE,
)
#: Brief acknowledgements: light only when she asked nothing (see `decide`).
_ACKNOWLEDGEMENT = re.compile(
    r"^(yes|no|indeed|quite|quite so|very good|very well|good|fine|all right|alright|"
    r"okay|ok|right|i see|understood|noted|of course|certainly|splendid|excellent|"
    r"lovely|wonderful|marvellous|fair enough|as you say|just so|good to know)$",
    re.IGNORECASE,
)
#: How she may have left a question or an offer open in her last answer.
_OPEN_QUESTION = re.compile(
    r"(\?\s*$|\b(?:shall i|would you like|do you want|may i|should i|which|whether)\b)",
    re.IGNORECASE,
)
#: What his previous message asked for, when it asked for an action or a decision:
#: the authoritative sign of pending work. Information he asked for and she gave
#: ("explain", "tell me about", "name two ways") is settled by the answer itself;
#: an action or a decision is not settled by anything she says about it.
_ACTION_REQUEST = re.compile(
    r"\b("
    r"do it|make|change|send|write|draft|book|schedule|plan|remind|cancel|move|set|fix|save|"
    r"delete|post|proceed|go ahead|remember|arrange|order|prepare|finish|start|stop|open|"
    r"close|put|add|remove|update|record|note down|read|show|find|look up|check|search|"
    r"play|list|summar\w*|"
    r"should i|shall i|which (?:one|reader|venue|ending|option|of)|decide|yes,? do|"
    r"not the|not that|i meant|never mind|instead|rather|actually|wait,"
    r")\b",
    re.IGNORECASE,
)
#: Her generic closings of courtesy: an offer of service in general, not of anything in
#: particular. A closing here leaves no matter open; anything else that asks or offers
#: does.
_COURTESY_CLOSING = re.compile(
    r"^(?:(?:and )?how (?:may|can|might) i (?:assist|attend to|serve|help)(?: you)?"
    r"(?: (?:this evening|tonight|today|this morning|further|this time|now))?|"
    r"what (?:shall|may|can) (?:we|i) (?:turn our attention to|attend to|do for you)"
    r"(?: (?:this evening|tonight|today|this time|this hour))?|"
    r"is there anything (?:else|further|more)(?: (?:you (?:require|need|would like)|i can do"
    r"(?: for you)?))?(?: (?:this evening|tonight|today))?|anything (?:else|further|more)"
    r"(?:,? my lord)?|how else may i serve(?: you)?|what (?:may|can) i do for you|"
    r"how may i be of service(?: (?:today|tonight|this evening))?|what shall we attend to"
    r"(?: (?:this evening|tonight|today|this time))?|how may i serve(?: you)?"
    r"(?: (?:this evening|tonight|today|this day))?)$",
    re.IGNORECASE,
)


#: How far back the decision looks for unresolved work: his previous message, and this
#: many exchanges before it (owner order of 26 September 2026, "CORRECT THE RELEASE
#: GAPS" §6: an earlier task is not settled merely because a later exchange was social).
#: Bounded, so a long conversation that has moved on does not lose courtesy for ever
#: over a request made an hour ago; wide enough that a greeting and a remark about the
#: weather after an unmet request do not make it look settled.
PENDING_WINDOW_EXCHANGES = 3


def _answer_leaves_open(answer: str) -> str | None:
    """Whether one answer of hers asks or offers something in particular (rule 2)."""
    for sentence in _sentences(answer):
        core = re.sub(r"[.!?,;:]+$", "", sentence.strip().replace(chr(0x2019), "'"))
        core = re.sub(r"\s+", " ", core)
        if _COURTESY_CLOSING.match(core.strip()):
            continue
        if "?" in sentence or _OPEN_QUESTION.search(sentence):
            return "asked or offered something in particular"
        # Tightened after the fresh set's first evaluation (26 September 2026,
        # case p14: "Put it in front of me and I'll read it now"): an offer in a
        # contraction, and an instruction to him, both leave the matter open.
        if re.search(
            r"\b(?:i(?: could| can| would| will| shall|'ll|'d) (?:suggest|draft|prepare|"
            r"begin|set|read|go on|adjust|arrange|have|keep|record|review|compare|do)|"
            r"if you wish|shall i|would you like|i propose|put it|give me|provide|"
            r"send me|let me know|specify|describe it|name the)\b",
            sentence,
            re.IGNORECASE,
        ):
            return "offered something in particular"
    return None


def pending_matter(state: ConversationState) -> str | None:
    """Why the context is not settled, or None when a social turn may be answered as such.

    Owner order of 26 September 2026 (Milestone A §4): a Core-owned decision in place of
    a blanket phrase list. Read in this order, each sufficient on its own:

    1. **His previous message asked for an action or a decision** (or was itself a
       correction or withdrawal). Nothing she said about it — that she did it, will
       do it, noted it, cannot do it — settles it here: a claim of action or completion
       is uncertain state, not proof, and a refusal leaves the matter with him.
    2. **Her previous answer asks or offers something in particular**: any sentence
       with a question mark or an offer that is not one of the generic closings of
       courtesy ("How may I assist you?", "Is there anything else you require?").
       Those closings are courtesy when nothing else is open; they never override
       an open matter found by rule 1.
    3. Nothing readable to decide on when there were earlier turns → uncertain → MEDIUM.
    4. **Earlier exchanges in the window** (release-gaps order of 26 September 2026,
       §6): rules 1 and 2 applied to each of the `PENDING_WINDOW_EXCHANGES` exchanges
       before the previous one, walking back from the most recent, **until a message
       of his that is itself work** — he moved on to something else, and his courtesy
       attaches to that. A message of his that the frozen router reads as social (a
       greeting, thanks, a farewell, a pleasantry, a bare acknowledgement) settles
       nothing, so an unmet request followed by "Good evening" and "Quiet tonight" is
       still unmet.
    """
    previous_owner = (state.previous_owner_message or "").strip()
    previous = (state.previous_answer or "").strip()
    if state.prior_turns > 0 and not previous:
        return "uncertain state: earlier turns but no answer of hers to read"
    if previous_owner and _ACTION_REQUEST.search(previous_owner):
        return "his previous message asked for an action or a decision, which nothing here settles"
    if previous:
        open_reason = _answer_leaves_open(previous)
        if open_reason is not None:
            return f"her last answer {open_reason}"
    following = previous_owner
    for owner, answer in reversed(state.earlier_exchanges[-PENDING_WINDOW_EXCHANGES:]):
        if following and _classify_core(_core(following))[0] is None:
            break  # what he said after this exchange was work of its own; it moved on
        if _ACTION_REQUEST.search(owner):
            return (
                "an earlier message of his asked for an action or a decision, and only "
                "social exchanges have followed it"
            )
        if answer:
            open_reason = _answer_leaves_open(answer)
            if open_reason is not None:
                return (
                    f"an earlier answer of hers {open_reason}, and only social exchanges "
                    "have followed it"
                )
        following = owner
    return None


#: A thanks alone (the class withheld after a greeting exchange, above).
_THANKS_ONLY = _THANKS

#: How she addresses him inside an answer; removed before an answer's shape is read.
_HER_ADDRESS = re.compile(r"\b(?:my lord|my lady|sir|madam)\b", re.IGNORECASE)


def answer_is_courtesy(answer: str) -> bool:
    """Whether an answer of hers is courtesy only — a greeting back, a closing of service.

    Release-gaps order of 26 September 2026 (§6): the Tier-1 request leaves out a
    previous exchange that was only a greeting pair, because LOW copies its own
    greeting from one. The desktop-integration run showed the omission failing when
    **his** words were misheard ("Good evening, Vowel." is not a greeting to the
    router) while **her** answer was still a greeting — and LOW answered "Good night,
    Val." with "Good evening, my lord." So the exchange's shape is read from her answer
    too: every sentence a greeting, thanks, farewell, pleasantry, bare acknowledgement
    or generic closing of courtesy, once her address to him is removed. Anything else
    in it is context, and the exchange stays.
    """
    sentences = _sentences(answer or "")
    if not sentences:
        return False
    for sentence in sentences:
        bare = re.sub(r"\s+", " ", _HER_ADDRESS.sub(" ", sentence)).strip()
        core = re.sub(r"[.!?,;:" + chr(0x2026) + r"]+$", "", bare.replace(chr(0x2019), "'"))
        core = re.sub(r"\s*,\s*", ", ", core).strip(" ,")
        if _COURTESY_CLOSING.match(core):
            continue
        if classify_sentence(core)[0] is not None:
            continue
        return False
    return True


MAX_WORDS = 12


@dataclass(frozen=True)
class ConversationState:
    """What of the conversation eligibility may look at."""

    #: Her most recent answer, wording in force; None when she has said nothing yet.
    previous_answer: str | None
    prior_turns: int
    #: His previous message, wording in force; None when this is his first.
    previous_owner_message: str | None = None
    #: The exchanges before the previous one, oldest first — (his message, her answer
    #: or None where none is readable) — as far back as the caller keeps them; the
    #: decision reads the last `PENDING_WINDOW_EXCHANGES` of them.
    earlier_exchanges: tuple[tuple[str, str | None], ...] = ()


@dataclass(frozen=True)
class RouteDecision:
    #: 1 or 2 when the fast route may carry the turn; None otherwise.
    tier: int | None
    reason: str


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?" + chr(0x2026) + r"])\s+|\n+", text.strip())
    return [part for part in (p.strip() for p in parts) if part]


def _core(sentence: str) -> str:
    """The sentence without its address to her, trailing punctuation, or doubled spaces."""
    lowered = sentence.strip().lower().replace(chr(0x2019), "'")
    lowered = re.sub(r"[.!?,;:" + chr(0x2026) + r"]+$", "", lowered)
    lowered = _ADDRESS.sub(" ", lowered)
    lowered = re.sub(r"[,.!]", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _classify_core(core: str) -> tuple[int | None, str]:
    if _GREETING.match(core) or _THANKS.match(core) or _FAREWELL.match(core):
        return 1, "greeting, thanks or farewell"
    if _PLEASANTRY_QUESTION.match(core) or _PLEASANTRY_STATEMENT.match(core):
        return 2, "pleasantry"
    if _ACKNOWLEDGEMENT.match(core):
        return 2, "acknowledgement"
    return None, ""


def classify_sentence(sentence: str) -> tuple[int | None, str]:
    """The tier one sentence belongs to on its own, and why.

    A sentence of two light clauses — "That was helpful, thank you", "Nothing else
    for now, thank you" — is light when **every** clause is; one clause outside the
    scope makes the sentence work.
    """
    core = _core(sentence)
    if not core:
        return None, "empty"
    tier, reason = _classify_core(core)
    if tier is not None:
        return tier, reason
    clauses = [part.strip() for part in re.split(r",|\band\b|;", sentence) if part.strip()]
    # A clause that is only her name or a form of address ("Good evening, Val, it's
    # me") is not a clause; the address is stripped from every clause alike. Found by
    # the qualification pilot of 26 September 2026 and corrected as a defect of the
    # splitting, not of the scope: nothing here admits any new wording.
    clauses = [clause for clause in clauses if _core(clause)]
    if len(clauses) > 1:
        tiers: list[int] = []
        reasons: list[str] = []
        for clause in clauses:
            clause_tier, clause_reason = _classify_core(_core(clause))
            if clause_tier is None:
                return None, f"not within the admitted light scope: {clause[:40]!r}"
            tiers.append(clause_tier)
            reasons.append(clause_reason)
        return max(tiers), ", ".join(reasons)
    return None, f"not within the admitted light scope: {sentence[:40]!r}"


def decide(text: str, state: ConversationState, tiers: frozenset[int]) -> RouteDecision:
    """Whether this whole utterance may take the fast route, under the enabled tiers."""
    if not tiers:
        return RouteDecision(None, "fast route disabled")
    stripped = text.strip()
    if len(stripped.split()) > MAX_WORDS:
        return RouteDecision(None, f"longer than {MAX_WORDS} words")
    if _WORK.search(stripped):
        return RouteDecision(None, "asks for work, judgment, memory or her capabilities")
    sentences = _sentences(stripped)
    if not sentences:
        return RouteDecision(None, "nothing said")
    # Owner order of 26 September 2026 ("COMPARE EXISTING TIER-1 OPTIONS", §2): a turn
    # spoken while her last answer left a question or an offer open is a pending-action
    # context whatever its wording — "thank you" after "shall I send it?" leaves the
    # matter live — and stays on ordinary MEDIUM. Narrower than before (the rule applied
    # to acknowledgements only); nothing is admitted by it.
    # Owner order of 26 September 2026 (Milestone A §4): courtesy against genuine
    # pending work is a Core-owned decision over his previous message and the whole of
    # her previous answer, not a phrase list. Uncertain → MEDIUM.
    open_matter = pending_matter(state)
    if open_matter is not None:
        return RouteDecision(None, open_matter)
    # Milestone A §4, from generated answers rather than routing alone: a bare thanks
    # spoken after an exchange that was itself only a greeting drew a greeting back
    # from LOW in verification ("Thank you, Val." → "Good evening, my lord."; 1 of 2
    # after the request was corrected, 3 of 7 before). Only that class is withheld:
    # farewells after a greeting exchange answered correctly every time, and thanks
    # after a settled substantive answer did too.
    previous_owner = (state.previous_owner_message or "").strip()
    if previous_owner and _THANKS_ONLY.match(_core(stripped)):
        previous_light = _classify_core(_core(previous_owner))[0]
        if previous_light is not None and _GREETING.match(_core(previous_owner)):
            return RouteDecision(
                None,
                "thanks after a greeting exchange: LOW answered it as a greeting in verification",
            )
    highest = 0
    for sentence in sentences:
        tier, reason = classify_sentence(sentence)
        if tier is None:
            return RouteDecision(None, reason)
        if "?" in sentence and not _PLEASANTRY_QUESTION.match(_core(sentence)):
            return RouteDecision(None, "a question outside the admitted pleasantries")
        highest = max(highest, tier)
    if highest not in tiers:
        return RouteDecision(None, f"tier {highest} is not enabled")
    reasons = ", ".join(classify_sentence(sentence)[1] for sentence in sentences)
    return RouteDecision(highest, f"tier {highest}: {reasons}")


@dataclass(frozen=True)
class FastRoute:
    """The candidate's enabled tiers. `frozenset()` is the production state: off."""

    tiers: frozenset[int] = frozenset()

    @property
    def enabled(self) -> bool:
        return bool(self.tiers)

    def decide(self, text: str, state: ConversationState) -> RouteDecision:
        return decide(text, state, self.tiers)

    @staticmethod
    def parse(setting: str) -> FastRoute:
        """`""` → off; `"1"` → tier 1; `"1,2"` → both. Anything else is refused."""
        tiers: set[int] = set()
        for part in setting.split(","):
            item = part.strip()
            if not item:
                continue
            if item not in ("1", "2"):
                raise ValueError(f"fast route tiers must be 1 and/or 2, not {item!r}")
            tiers.add(int(item))
        return FastRoute(frozenset(tiers))
