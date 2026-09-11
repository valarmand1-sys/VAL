"""One deliberated turn — WP-0.9's orchestration half.

`04-layer-0.md` WP-0.9 and `02-partner-systems.md` §4.1/§4.8, under the
rulings of 19 August 2026. The order, per turn, each step gating the next:

    1. open the turn                 WP-0.7's shared phases (`loop.open_turn`)
    2. classify                      one small call, cheapest route, every turn
       (not captured — an ordinary WP-0.7 turn from here on)
    3. strip                         strip route; only an enforceable payload
                                     continues (no preference, or a strip
                                     that cannot establish one — steps
                                     collapse to one ordinary call)
    4. select the configuration      ONCE, for both remaining calls
    5. blind position                pinned; carries the persona; payload logged
    6. persist blind_positions row   evidence, durable BEFORE step 7 exists
    7. response                      pinned to the same configuration;
                                     receives the recorded position; must
                                     reconcile explicitly, prose + typed verdict
    8. settle the turn               her prose becomes her message
    9. record the deliberation       outcome from her explicit verdict, linked
                                     to the exact blind evidence it resolves

## What is structural rather than asserted

**Ordering.** The blind call's payload is built from the stripped question
only, and the exact payload is logged before transmission — the WP-0.9
criterion is that inspection of that payload shows no preference-bearing
content. Where separation fails, no blind call is made at all (ruling,
10 September 2026): the strip's attempts stand in `model_calls` and on the
outcome, no `blind_positions` row is written, and the turn takes the ordinary
partner-response path. `ordering = contaminated` remains in the domain for the
historical rows written before that ruling; nothing claims an independence
that did not happen.

**Same configuration.** Selected once (`Gateway.select_configuration`), then
both calls run pinned, each still passing admission, eligibility, and budget
on its own account. A mid-turn failure of the pinned route leaves the turn
unanswered rather than falling back — a silent configuration change between
the two calls would produce a clean paper trail of an independence that never
existed (ruling, 19 August 2026).

**Outcome stated, never parsed out of prose.** The response returns prose plus
a typed reconciliation verdict; `held`, `updated`, and `agreed_from_start`
come from Val's own explicit reconciliation (which §4.1 already requires),
`updated` requires what changed her mind, and `overridden` is never accepted
from this channel — an override is Lord Armand's explicit decision, recorded
manually.

## What degrades, and how

**Unknown classification is never treated as ordinary classification** —
ruling, 3 September 2026. The classification decides whether the safeguard
applies, so a classification that fails must not switch the safeguard off:
until that ruling, a classifier failure was logged as a capture miss and the
turn proceeded as an ordinary WP-0.7 turn, which meant the mechanism that
decides whether the anti-sycophancy structure runs disabled that structure
exactly when it failed. Real use found it failing on most exchanges — a
correct verdict followed by prose, prose followed by a fenced verdict — and
zero captures had ever occurred. The repair is in two halves: the request is
schema-constrained and framed as data (`val_policy.deliberation`), and the
recovery here is **bounded**: one retry, then an honest failure. The turn
ends as `UnansweredTurn`, the user's message stays in the record, no `val`
message is written, and every classification call that was made is on
`model_calls`. Retroactive marking (§4.8) remains for a turn that ends this
way, as for any other.

The remaining fallbacks are honest ones. A strip failure — truncated, failed,
invalid after its bounded retry, or inseparable — is a failed separation:
recorded as such, no blind call, the ordinary path. An unparseable blind
position is retried once and then ends the turn unanswered (8 September
2026), and the `model_calls` rows keep the honest account of what was paid. An
unparseable reconciliation verdict settles the turn but records no outcome —
never a guessed one. Nothing on any path fabricates a record.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Engine

from val_domain.conversation import StoredRole
from val_domain.deliberation import (
    BlindPositionRecord,
    ClassificationRecord,
    ClassifiedBy,
    DeliberationClassification,
    DeliberationRecord,
    Ordering,
)
from val_domain.gateway import (
    Classification,
    GatewayError,
    GatewayErrorKind,
    GatewayRequest,
    GatewayResponse,
    Message,
    ModelConfig,
    PersonaAttribution,
    TaskType,
    TerminalState,
    TurnReference,
)
from val_domain.project import ProjectScope, attribution_of, attribution_state_of
from val_domain.provider import DeltaSink
from val_gateway import conversations
from val_gateway.deliberation import (
    record_blind_position,
    record_classification,
    record_deliberation,
)
from val_gateway.exchange import ClarificationNeeded
from val_gateway.gateway import Gateway
from val_gateway.loop import (
    OpenedTurn,
    TruncatedTurn,
    Turn,
    UnansweredTurn,
    assemble_turn,
    open_turn,
    settle_turn,
    unanswered_or_raise,
)
from val_gateway.memory import DEFAULT_LIMIT
from val_gateway.persona import DatabasePersonaLoader
from val_gateway.projects import ProjectSession
from val_policy.deliberation import (
    BLIND_POSITION_INSTRUCTION,
    BLIND_POSITION_OUTPUT_SCHEMA,
    CLASSIFIER_INSTRUCTION,
    CLASSIFIER_OUTPUT_SCHEMA,
    STRIP_INSTRUCTION,
    STRIP_OUTPUT_SCHEMA,
    BlindOutcome,
    ClassifierVerdict,
    ReconciliationStream,
    RemovedSpan,
    StripOutcome,
    StripValidation,
    classifier_envelope,
    parse_blind_outcome,
    parse_classifier_verdict,
    parse_strip_outcome,
    reconciliation_envelope,
    same_text,
    split_reconciled,
    validate_strip,
)
from val_policy.project_resolution import ProjectCatalogue, ProjectSignals

_LOGGER = logging.getLogger("val.deliberation")

#: Output caps for the machinery calls. The classifier and blind position emit
#: small JSON; the strip must return the message's own text twice over in the
#: worst case, so its cap scales with nothing hidden — a message longer than
#: this cap's worth of output is refused by the model-limits check like any
#: other oversized request, visibly.
CLASSIFIER_MAX_OUTPUT_TOKENS = 256
STRIP_MAX_OUTPUT_TOKENS = 4096
#: Ruling, 9 September 2026: a completed strip result that contradicts itself
#: or the message is *invalid* and may be retried exactly once on the same
#: configuration; a valid "not separable" is never retried in search of
#: separability. Ruling, 10 September 2026: a reply that ended `truncated` is
#: never retried, and no strip outcome short of `enforceable` produces a
#: blind call — the exchange collapses to the ordinary path.
STRIP_ATTEMPTS = 2
#: Ruling, 7 September 2026: the blind position's ceiling matches the response
#: allowance. It is an output ceiling, not a request for a long position — the
#: 1,024 that preceded it was calibrated when the cheapest route served the
#: blind call, and the partner route's schema-constrained position exceeded it.
BLIND_MAX_OUTPUT_TOKENS = 4096

#: The bound on blind-position attempts per consequential exchange (ruling,
#: 7 September 2026). Two: the first call, and one retry of the identical
#: request — same configuration, schema, stripped input, and cap. A truncated
#: or otherwise invalid position may never let a consequential exchange
#: proceed as an ordinary turn; after the second failure it ends unanswered.
BLIND_ATTEMPTS = 2

#: The bound on classification attempts per exchange (ruling, 3 September
#: 2026). Two: the first call, and one retry of the identical request. A
#: schema-constrained reply that still fails to parse or complete is not a
#: transient the house should keep paying to re-ask; after the second, the
#: classification is unestablished and the turn ends honestly.
CLASSIFIER_ATTEMPTS = 2


@dataclass(frozen=True)
class ClassificationAttempts:
    """What the bounded classification did — the verdict, or why there is none.

    `model_call_ids` names every classification call made, in order, including
    calls that failed after reaching a provider; `resolving_model_call_id` is
    the call the verdict came from, or the final recorded attempt where none
    did. `reasons` says, per failed attempt, what the record supports; `kind`
    is the last gateway failure's kind where the final attempt never got an
    answer, and `INVALID_OUTPUT` where it got one that stated no verdict.
    """

    verdict: ClassifierVerdict | None
    attempts: int
    model_call_ids: tuple[UUID, ...]
    resolving_model_call_id: UUID | None
    reasons: tuple[str, ...]
    kind: GatewayErrorKind

    def as_error(self) -> GatewayError:
        return GatewayError(
            self.kind,
            f"the exchange could not be classified: {self.attempts} classification "
            f"attempt(s) established no verdict ({'; '.join(self.reasons)}). No "
            "response was requested, because an exchange whose classification is "
            "unknown is not treated as ordinary (ruling, 3 September 2026). The "
            "message is in the record; saying it again is an ordinary next turn.",
            model_call_ids=self.model_call_ids,
        )


@dataclass(frozen=True)
class DeliberatedTurn:
    """One completed turn, with whatever the deliberation machinery captured.

    `captured_as` is None when the exchange was not captured — either the
    classifier said so, or it failed and the miss is logged. `blind` is the
    evidence row when a blind call ran; `deliberation` is the resolved record
    when Val's response carried a valid reconciliation verdict. Each may be
    present without the next: the record never claims more than happened.

    `blind_payload` is the exact payload of the blind call — the same content
    that was logged — so the WP-0.9 inspection criterion can be checked from
    the returned object as well as from the log.
    """

    turn: Turn | TruncatedTurn
    captured_as: DeliberationClassification | None
    hard_exclusion: str | None
    blind: BlindPositionRecord | None
    deliberation: DeliberationRecord | None
    blind_payload: str | None
    #: The turn's classification evidence row (ruling, 3 September 2026) —
    #: always present on a deliberated turn, since the turn cannot reach a
    #: response without an established classification on the record.
    classification: ClassificationRecord
    #: Ruling, 9 September 2026: the validation state of every strip attempt,
    #: in order (`enforceable`, `not_separable`, `no_preference`, `invalid`),
    #: so an invalid first attempt and its bounded retry are visible.
    strip_states: tuple[str, ...] = ()


DeliberatedOutcome = DeliberatedTurn | UnansweredTurn | ClarificationNeeded


def send(
    engine: Engine,
    gateway: Gateway,
    content: str,
    *,
    catalogue: ProjectCatalogue,
    signals: ProjectSignals | None = None,
    session: ProjectSession | None = None,
    conversation_id: UUID | None = None,
    title: str | None = None,
    classification: Classification = Classification.PROTECTED,
    recall_limit: int = DEFAULT_LIMIT,
    max_output_tokens: int = 4096,
    on_delta: DeltaSink | None = None,
) -> DeliberatedOutcome:
    """Say one thing to Val, with the §4.8 classification deciding what is captured.

    The same signature and scope doctrine as `loop.send` — the turn phases are
    shared, not duplicated. What this adds is everything between persisting
    the message and calling the provider: classification on every exchange,
    and the strip / blind / reconcile structure on the captured ones.
    """
    opened = open_turn(
        engine,
        content,
        catalogue=catalogue,
        signals=signals,
        session=session,
        conversation_id=conversation_id,
        title=title,
    )
    if isinstance(opened, ClarificationNeeded):
        return opened

    # 2. Classify, before any position is formed (§4.8: the classification runs
    #    first, because it decides whether the blind call happens at all).
    #    Whatever it concluded is evidence, written now (ruling, 3 September
    #    2026) — before any strip or response call, and whether or not a
    #    verdict was established — so the record can say how this turn was
    #    classified, and why, from the classifier's own declared reason.
    classified = _classify(gateway, content, opened.scope, classification)
    verdict = classified.verdict
    record = record_classification(
        engine,
        conversation_id=opened.conversation.id,
        message_id=opened.user_message.id,
        verdict=None if verdict is None else verdict.verdict,
        hard_exclusion=None if verdict is None else verdict.hard_exclusion,
        attempts=classified.attempts,
        model_call_ids=classified.model_call_ids,
        resolving_model_call_id=classified.resolving_model_call_id,
        resolution=None if verdict is not None else "; ".join(classified.reasons),
    )
    if verdict is None:
        # Ruling, 3 September 2026: unknown classification is not ordinary
        # classification. The turn ends here, honestly — the message is in
        # the record, every classification call is on `model_calls`, and no
        # response call is made on an exchange the house could not classify.
        return unanswered_or_raise(opened, classified.as_error())
    captured_as = verdict.captured_as
    hard_exclusion = verdict.hard_exclusion

    if captured_as is None:
        # A valid verdict of not-consequential, or a named hard exclusion: an
        # ordinary WP-0.7 turn from here on.
        outcome = _ordinary(
            engine, gateway, opened, classification, recall_limit, max_output_tokens, on_delta
        )
        if isinstance(outcome, UnansweredTurn):
            return outcome
        return DeliberatedTurn(
            turn=outcome,
            captured_as=None,
            hard_exclusion=hard_exclusion,
            blind=None,
            deliberation=None,
            blind_payload=None,
            classification=record,
        )

    # 3. Strip. Ruling, 9 September 2026: the strip's structured result is
    #    validated deterministically against the message before anything is
    #    built from it. Only an `enforceable` validation — preference present,
    #    separable, every span resolved exactly, at least one preference span,
    #    the derivation actually changing the message — may produce a blind
    #    call, and that call is `ordering = enforced`. Ruling, 10 September
    #    2026: nothing else produces a blind call at all. A strip that cannot
    #    establish an enforceable blind payload — truncated, failed, invalid
    #    after its bounded retry, or a valid `separable = false` — records
    #    the strip/capture failure honestly (every attempt's state on the
    #    outcome, every call on model_calls) and collapses to the ordinary
    #    partner-response path: no blind-position call, no `blind_positions`
    #    row, no fabricated deliberation. A position formed with the
    #    preference in view is the thing the machinery exists to avoid, and
    #    paying a partner call to record one was spending on the failure
    #    mode. Historical `contaminated` rows stand as what they were.
    #    Ruling, 11 September 2026: the record against which declared record
    #    evidence is grounded is the conversation's own — every message Val
    #    has spoken in it, from the authoritative store, never a claim.
    spoken_by_val = tuple(
        message.content
        for message in conversations.history(engine, opened.conversation.id)
        if message.role is StoredRole.VAL
    )
    stripped = _strip(gateway, content, opened.scope, classification, record=spoken_by_val)
    validation = stripped.validation
    if not validation.enforceable or validation.residue is None:
        if validation.state == "no_preference":
            # §4.1: no preference present — steps collapse to one call. There
            # is no blindness to enforce and no stated view to reconcile
            # with; the exchange resolves later (his response arrives in a
            # later turn) and is recorded then, through the writer, against
            # this capture.
            pass
        else:
            _LOGGER.warning(
                "strip could not establish an enforceable blind payload (attempts: %s; %s); "
                "the capture failure is recorded and the turn proceeds on the ordinary "
                "partner-response path — no blind position is formed and no blind_positions "
                "row is written (ruling, 10 September 2026)",
                ", ".join(stripped.states),
                "; ".join(validation.reasons) or validation.state,
            )
        outcome = _ordinary(
            engine, gateway, opened, classification, recall_limit, max_output_tokens, on_delta
        )
        if isinstance(outcome, UnansweredTurn):
            return outcome
        return DeliberatedTurn(
            turn=outcome,
            captured_as=captured_as,
            hard_exclusion=None,
            blind=None,
            deliberation=None,
            blind_payload=None,
            classification=record,
            strip_states=stripped.states,
        )

    # Ruling, 3 September 2026: the blind question is DERIVED from the
    # original message and the accepted spans — mechanically, no semantic
    # judgment — never taken from the strip's own "question". The validation
    # above is the proof that the derivation removed preference-bearing
    # material; without it, no enforcement — and now, no blind call.
    if stripped.outcome is not None and not same_text(
        stripped.outcome.question, validation.residue
    ):
        _LOGGER.warning(
            "strip's own question was not the verbatim remainder (a paraphrase); "
            "the derived remainder is used and the paraphrase is discarded"
        )
    question = validation.residue
    removed = "\n".join(span.text for span in validation.spans)
    withheld: tuple[RemovedSpan, ...] = validation.spans
    ordering = Ordering.ENFORCED

    # 4. One configuration for both remaining calls (ruling, 19 August 2026).
    persona = DatabasePersonaLoader(engine).active()
    messages, recalled = assemble_turn(engine, opened, recall_limit=recall_limit)
    sizing = (*(message.content for message in messages), persona.content)
    try:
        config = gateway.select_configuration(
            classification, sizing, max_output_tokens, task_type=TaskType.CONVERSATION
        )
    except GatewayError as failure:
        return unanswered_or_raise(opened, failure)

    # 5. The blind position, pinned, carrying the persona, payload logged.
    blind_message = Message(
        role="user", content=f"{BLIND_POSITION_INSTRUCTION}\n\nThe question:\n{question}"
    )
    blind_payload = _log_blind_payload(config, persona.id, blind_message, withheld=withheld)
    blind_request = GatewayRequest(
        task_type=TaskType.BLIND_POSITION,
        classification=classification,
        messages=(blind_message,),
        # The persona, whole, exactly once — and attributed, verified against
        # the active row by the gateway before transmission.
        system=persona.content,
        persona=PersonaAttribution(persona_id=persona.id),
        max_output_tokens=BLIND_MAX_OUTPUT_TOKENS,
        # Provider-enforced shape (3 September 2026): the evidence row must
        # not be lost to a fenced-JSON-plus-commentary habit.
        output_schema=BLIND_POSITION_OUTPUT_SCHEMA,
        project_id=attribution_of(opened.scope),
        project_attribution=attribution_state_of(opened.scope),
    )
    blind_outcome: BlindOutcome | None = None
    blind_response: GatewayResponse | None = None
    blind_calls: list[UUID] = []
    reasons: list[str] = []
    for attempt in range(1, BLIND_ATTEMPTS + 1):
        try:
            blind_response = gateway.complete_with_configuration(blind_request, config)
        except GatewayError as failure:
            # The pinned route could not answer. No fallback — the turn is
            # unanswered rather than deliberated on a silently different route.
            # Not retried here either: a route refusal (ceiling, provider
            # error, unverified persona) is not an invalid position, and the
            # retry the ruling grants is for the position, not the route.
            return unanswered_or_raise(opened, failure)
        if blind_response.model_call_id is not None:
            blind_calls.append(blind_response.model_call_id)
        blind_outcome = _blind_outcome_from(blind_response.text, blind_response.terminal)
        if blind_outcome is not None:
            break
        if blind_response.terminal not in (TerminalState.COMPLETE, TerminalState.REFUSED):
            reasons.append(f"attempt {attempt}: reply ended {blind_response.terminal.value}")
        else:
            reasons.append(f"attempt {attempt}: reply stated no parseable position")
        _LOGGER.warning(
            "blind position attempt %d of %d on %s stated no valid position (terminal=%s); "
            "a fragment is not a position and nothing is recorded from it",
            attempt,
            BLIND_ATTEMPTS,
            config.slug,
            blind_response.terminal.value,
        )

    if blind_outcome is None or blind_response is None:
        # Ruling, 7 September 2026: never the ordinary path. The user message
        # stays; no Val response, no fabricated position, no deliberation;
        # every attempt is preserved in model_calls under its own terminal
        # state and is named here so the cause is truthful and traceable.
        _LOGGER.warning(
            "blind position unestablished after %d attempts on %s; the consequential "
            "turn ends unanswered rather than proceeding as ordinary",
            BLIND_ATTEMPTS,
            config.slug,
        )
        return unanswered_or_raise(
            opened,
            GatewayError(
                GatewayErrorKind.INVALID_OUTPUT,
                f"the blind position could not be established: {BLIND_ATTEMPTS} attempts on "
                f"{config.slug} with an output ceiling of {BLIND_MAX_OUTPUT_TOKENS} tokens "
                f"({'; '.join(reasons)}). The exchange was classified consequential and "
                "is not answered as an ordinary one; no position and no deliberation were "
                "recorded, and the attempts stand in model_calls.",
                model_call_ids=tuple(blind_calls),
            ),
        )

    # 6. The evidence row — durable BEFORE the response call exists (0011).
    if blind_response.model_call_id is None:
        raise RuntimeError(
            "the gateway's recorder returned no model_calls id, so the blind "
            "position cannot name its call. Evidence that cannot name its call "
            "is not written; fix the recorder wiring rather than relaxing the row."
        )
    blind_row = record_blind_position(
        engine,
        conversation_id=opened.conversation.id,
        message_id=opened.user_message.id,
        model_call_id=blind_response.model_call_id,
        persona_id=persona.id,
        position=blind_outcome.position,
        confidence=blind_outcome.confidence,
        reasoning=blind_outcome.reasoning,
        stripped_content=removed,
        ordering=ordering,
        classification=captured_as,
        classified_by=ClassifiedBy.AUTOMATIC,
    )

    # 7. The response, pinned to the same configuration, with the recorded
    #    position to reconcile against. The envelope is the last message, after
    #    the conversation ending on his turn.
    envelope = Message(
        role="user",
        content=reconciliation_envelope(
            blind_outcome, contaminated=ordering is Ordering.CONTAMINATED
        ),
    )
    # Val Core Phase 1 (11 September 2026): the response stage may stream, but
    # only through the core's own filter — the typed reconciliation verdict is
    # machinery output and is withheld from presentation; her prose is what
    # streams. The blind call above never receives a sink: it is evidence, not
    # presentation, and nothing of it is shown before it is recorded.
    withholding = ReconciliationStream(on_delta) if on_delta is not None else None
    try:
        response = gateway.converse(
            (*messages, envelope),
            scope=opened.scope,
            classification=classification,
            turn=TurnReference(
                conversation_id=opened.conversation.id, message_id=opened.user_message.id
            ),
            max_output_tokens=max_output_tokens,
            configuration=config,
            on_delta=withholding.feed if withholding is not None else None,
        )
        if withholding is not None:
            withholding.close()
    except GatewayError as failure:
        # The evidence row stays: the position was formed and recorded, and
        # the exchange going unanswered does not unhappen it.
        return unanswered_or_raise(opened, failure)

    # 8. Her prose becomes her message; the verdict is machinery output,
    #    checked against the recorded position (ruling, 7 September 2026).
    prose, reconciliation, problem = split_reconciled(response.text, blind_outcome.position)
    turn = settle_turn(
        engine,
        opened,
        recalled,
        response,
        spoken_text=prose if reconciliation is not None else None,
    )
    if isinstance(turn, UnansweredTurn):
        # Ruling, 8 September 2026: no valid assistant content — the blind
        # evidence row stays, no deliberation is written, nothing is spoken.
        return turn

    # 9. The deliberation, complete, from her explicit verdict — or not at all.
    deliberation = None
    if isinstance(turn, Turn) and reconciliation is not None:
        deliberation = record_deliberation(
            engine,
            conversation_id=opened.conversation.id,
            message_id=opened.user_message.id,
            position=blind_outcome.position,
            confidence=blind_outcome.confidence,
            reasoning=blind_outcome.reasoning,
            stripped_content=removed,
            ordering=ordering,
            user_response=content,
            outcome=reconciliation.outcome,
            what_changed_her_mind=reconciliation.what_changed_her_mind,
            classification=captured_as,
            classified_by=ClassifiedBy.AUTOMATIC,
            blind_position_id=blind_row.id,
        )
    elif isinstance(turn, Turn):
        _LOGGER.warning(
            "response carried no valid reconciliation verdict (%s); the turn is "
            "settled but no deliberation outcome is recorded — never an invented one. "
            "The blind evidence stands, and the exchange can be resolved manually "
            "(§4.8 override).",
            problem,
        )

    return DeliberatedTurn(
        turn=turn,
        captured_as=captured_as,
        hard_exclusion=None,
        blind=blind_row,
        deliberation=deliberation,
        blind_payload=blind_payload,
        classification=record,
        strip_states=stripped.states,
    )


def _ordinary(
    engine: Engine,
    gateway: Gateway,
    opened: OpenedTurn,
    classification: Classification,
    recall_limit: int,
    max_output_tokens: int,
    on_delta: DeltaSink | None = None,
) -> Turn | TruncatedTurn | UnansweredTurn:
    """The WP-0.7 turn, from an already-opened state."""
    messages, recalled = assemble_turn(engine, opened, recall_limit=recall_limit)
    try:
        response = gateway.converse(
            messages,
            scope=opened.scope,
            classification=classification,
            turn=TurnReference(
                conversation_id=opened.conversation.id, message_id=opened.user_message.id
            ),
            max_output_tokens=max_output_tokens,
            on_delta=on_delta,
        )
    except GatewayError as failure:
        return unanswered_or_raise(opened, failure)
    return settle_turn(engine, opened, recalled, response)


def _classify(
    gateway: Gateway, content: str, scope: ProjectScope, classification: Classification
) -> ClassificationAttempts:
    """The §4.8 classification on the cheapest eligible route, bounded.

    Routed through `complete`, whose attempt order is cheapest-first among the
    admitted, eligible, ready, and affordable — the routing already is the
    "cheapest eligible operational configuration" the ruling names.

    The request is schema-constrained and the exchange is framed as data
    (3 September 2026). A reply that still states no verdict — or does not
    complete, or never arrives — is retried once, identically; after
    `CLASSIFIER_ATTEMPTS` the classification is **unestablished**, which the
    caller ends the turn on. Nothing here guesses a verdict, and nothing here
    proceeds without one. Every call made is named in the result, including
    calls that failed after reaching a provider, so the evidence record can
    cite them rather than infer them.
    """
    request = GatewayRequest(
        task_type=TaskType.CLASSIFICATION,
        classification=classification,
        messages=(Message(role="user", content=classifier_envelope(content)),),
        system=CLASSIFIER_INSTRUCTION,
        max_output_tokens=CLASSIFIER_MAX_OUTPUT_TOKENS,
        output_schema=CLASSIFIER_OUTPUT_SCHEMA,
        project_id=attribution_of(scope),
        project_attribution=attribution_state_of(scope),
    )
    reasons: list[str] = []
    calls: list[UUID] = []
    kind = GatewayErrorKind.INVALID_OUTPUT
    for attempt in range(1, CLASSIFIER_ATTEMPTS + 1):
        try:
            response = gateway.complete(request)
        except GatewayError as failure:
            calls.extend(failure.model_call_ids)
            kind = failure.kind
            # The failure's own words travel with the kind: a ceiling refusal
            # must read as the ceiling, not as an anonymous failed attempt.
            reasons.append(f"attempt {attempt}: {failure.kind.value}: {failure}")
            _LOGGER.warning(
                "classification attempt %d of %d failed (%s)",
                attempt,
                CLASSIFIER_ATTEMPTS,
                failure.kind.value,
            )
            continue
        if response.model_call_id is not None:
            calls.append(response.model_call_id)
        kind = GatewayErrorKind.INVALID_OUTPUT
        if response.terminal is not TerminalState.COMPLETE:
            reasons.append(f"attempt {attempt}: reply ended {response.terminal.value}")
            _LOGGER.warning(
                "classification attempt %d of %d ended %s, not complete; no verdict taken "
                "from a fragment",
                attempt,
                CLASSIFIER_ATTEMPTS,
                response.terminal.value,
            )
            continue
        verdict = parse_classifier_verdict(response.text)
        if verdict is None:
            reasons.append(f"attempt {attempt}: reply stated no parseable verdict")
            _LOGGER.warning(
                "classification attempt %d of %d answered unparseably; never repaired "
                "into a verdict",
                attempt,
                CLASSIFIER_ATTEMPTS,
            )
            continue
        return ClassificationAttempts(
            verdict=verdict,
            attempts=attempt,
            model_call_ids=tuple(calls),
            resolving_model_call_id=response.model_call_id,
            reasons=tuple(reasons),
            kind=kind,
        )
    _LOGGER.warning(
        "classification unestablished after %d attempts; the turn ends unanswered "
        "rather than proceeding as ordinary (ruling, 3 September 2026)",
        CLASSIFIER_ATTEMPTS,
    )
    return ClassificationAttempts(
        verdict=None,
        attempts=CLASSIFIER_ATTEMPTS,
        model_call_ids=tuple(calls),
        resolving_model_call_id=calls[-1] if calls else None,
        reasons=tuple(reasons),
        kind=kind,
    )


@dataclass(frozen=True)
class StripAttempts:
    """The strip's outcome after at most `STRIP_ATTEMPTS` calls.

    `validation` is the deterministic reading of the last result (ruling,
    9 September 2026); `outcome` is that result as parsed, or None; `states`
    records every attempt's validation state in order, so an invalid first
    attempt followed by a valid retry is visible as such.
    """

    validation: StripValidation
    outcome: StripOutcome | None
    states: tuple[str, ...]


def _strip(
    gateway: Gateway,
    content: str,
    scope: ProjectScope,
    classification: Classification,
    *,
    configuration: ModelConfig | None = None,
    evaluation: bool = False,
    record: Sequence[str] = (),
) -> StripAttempts:
    """The §4.1 strip on the cheapest eligible route — validated, bounded.

    `record` is the conversation's own record of what Val said — the content
    of her messages — against which any record evidence the strip declares
    is grounded (ruling, 11 September 2026). Empty when there is no record.

    A failed call (the route could not answer) establishes no separation and
    is not retried, as before. A reply whose provider terminal state is
    **`truncated`** is a determinate failure of the attempt, not a transient
    one, and receives **no identical retry** (ruling, 10 September 2026: an
    identical request against the same ceiling truncates identically, as the
    live 18:25 turn showed — 4,096 tokens of thinking twice). A **completed**
    reply whose structured result is invalid — unparseable, or contradicting
    itself or the message under `validate_strip` — keeps its one bounded
    retry on the same route (9 September 2026); a second invalid result is
    exhausted. A valid `not_separable` is final: it is never retried in
    search of separability. Whatever the attempts establish, the caller
    builds a blind payload only from an `enforceable` validation; every
    attempt's state is on the result.

    `configuration`, when given, pins the call to that exact configuration
    (the conformance harness); the running application routes. `evaluation`
    is the harness's declaration that the pinned configuration is registered
    for evaluation only and is to be reached through the gateway's evaluation
    door, which is narrower than the pinned path; the running application
    never passes it.
    """
    request = GatewayRequest(
        task_type=TaskType.STRIP,
        classification=classification,
        messages=(Message(role="user", content=content),),
        system=STRIP_INSTRUCTION,
        max_output_tokens=STRIP_MAX_OUTPUT_TOKENS,
        # Provider-enforced shape (3 September 2026), after the first real
        # demonstration recorded `contaminated` by parse failure — a fenced
        # object with nulls, then commentary — rather than by verdict.
        output_schema=STRIP_OUTPUT_SCHEMA,
        project_id=attribution_of(scope),
        project_attribution=attribution_state_of(scope),
    )
    states: list[str] = []
    outcome: StripOutcome | None = None
    validation = StripValidation("invalid", None, (), ("no attempt was made",))
    for attempt in range(1, STRIP_ATTEMPTS + 1):
        try:
            if configuration is None:
                response = gateway.complete(request)
            elif evaluation:
                response = gateway.evaluate_with_configuration(request, configuration)
            else:
                response = gateway.complete_with_configuration(request, configuration)
        except GatewayError as failure:
            _LOGGER.warning(
                "strip call failed (%s); separation not established and no blindness "
                "is claimed from it.",
                failure.kind.value,
            )
            states.append("failed")
            return StripAttempts(
                StripValidation("invalid", None, (), (f"strip call failed: {failure.kind.value}",)),
                None,
                tuple(states),
            )
        complete = response.terminal is TerminalState.COMPLETE
        # Ruling, 10 September 2026 (Option A) and 11 September 2026 (the
        # completeness guard, stated in the contract): a reply that did not
        # complete is a fragment. The terminal state is the provider's own and
        # is already on the model_calls row; an identical retry against the
        # same ceiling is the same failure bought twice. The guard lives in
        # `validate_strip`, so the contract fails closed before any parse of
        # the fragment is trusted; nothing from it enters a blind payload.
        outcome = parse_strip_outcome(response.text) if complete else None
        validation = validate_strip(
            content,
            outcome,
            record=record,
            complete=complete,
            terminal=response.terminal.value,
        )
        states.append(validation.state)
        if not complete:
            _LOGGER.warning(
                "strip attempt %d ended %s (output ceiling %d tokens); separation not "
                "established, and an incomplete attempt is not retried",
                attempt,
                response.terminal.value,
                STRIP_MAX_OUTPUT_TOKENS,
            )
            return StripAttempts(validation, None, tuple(states))
        if validation.state == "ungrounded":
            _LOGGER.warning(
                "strip attempt %d declared record evidence the conversation's record does "
                "not contain (%s); an alleged quotation is not trusted evidence, and the "
                "result is final",
                attempt,
                "; ".join(validation.reasons),
            )
            return StripAttempts(validation, outcome, tuple(states))
        if validation.state != "invalid":
            return StripAttempts(validation, outcome, tuple(states))
        _LOGGER.warning(
            "strip attempt %d of %d returned an invalid structured result (%s)%s",
            attempt,
            STRIP_ATTEMPTS,
            "; ".join(validation.reasons),
            "; retrying once on the same route" if attempt < STRIP_ATTEMPTS else "; exhausted",
        )
    return StripAttempts(validation, outcome, tuple(states))


def _blind_outcome_from(text: str, terminal: TerminalState) -> BlindOutcome | None:
    """The parsed blind position, honouring the terminal state.

    A truncated or filtered reply is a fragment, and a fragment of a position
    is not a position — the same doctrine that keeps fragments out of Val's
    message history keeps them out of the evidence table.
    """
    if terminal not in (TerminalState.COMPLETE, TerminalState.REFUSED):
        return None
    return parse_blind_outcome(text)


def _log_blind_payload(
    config: ModelConfig,
    persona_id: UUID,
    message: Message,
    *,
    withheld: tuple[RemovedSpan, ...] = (),
) -> str:
    """Log the exact payload of the blind call, before transmission.

    The WP-0.9 criterion: inspection of this payload must show no
    preference-bearing content — and, since 7 September 2026, no framing that
    presupposes a prior position for Val. The variable content — the messages
    — is logged verbatim. The system prompt is the persona, whole; it is
    logged by its immutable revision id rather than repeated in full, because
    the row it names cannot change (`0005`) and twenty kilobytes of fixed
    identity per call would bury the part inspection is for.

    What the strip **withheld**, and of which kind, is logged as a second
    line rather than inside the payload: the payload line must be exactly
    what was transmitted, so that inspecting it for preference-bearing
    content means what it says.
    """
    payload = json.dumps(
        {
            "task_type": "blind_position",
            "configuration": config.slug,
            "system": f"persona:{persona_id}",
            "messages": [{"role": message.role, "content": message.content}],
            "max_output_tokens": BLIND_MAX_OUTPUT_TOKENS,
        },
        ensure_ascii=False,
    )
    _LOGGER.info("blind position payload: %s", payload)
    _LOGGER.info(
        "blind position withheld: %s",
        json.dumps(
            [
                {"kind": span.kind, "occurrence": span.occurrence, "text": span.text}
                for span in withheld
            ],
            ensure_ascii=False,
        ),
    )
    return payload
