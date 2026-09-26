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

MAX_WORDS = 12


@dataclass(frozen=True)
class ConversationState:
    """What of the conversation eligibility may look at."""

    #: Her most recent answer, wording in force; None when she has said nothing yet.
    previous_answer: str | None
    prior_turns: int


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
    highest = 0
    for sentence in sentences:
        tier, reason = classify_sentence(sentence)
        if tier is None:
            return RouteDecision(None, reason)
        if "?" in sentence and not _PLEASANTRY_QUESTION.match(_core(sentence)):
            return RouteDecision(None, "a question outside the admitted pleasantries")
        if reason == "acknowledgement":
            previous = state.previous_answer or ""
            last = _sentences(previous)[-1] if _sentences(previous) else previous
            if previous and _OPEN_QUESTION.search(last):
                return RouteDecision(None, "answers a question she left open")
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
