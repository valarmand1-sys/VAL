"""One deliberated turn — WP-0.9's orchestration half.

`04-layer-0.md` WP-0.9 and `02-partner-systems.md` §4.1/§4.8, under the
rulings of 19 August 2026. The order, per turn, each step gating the next:

    1. open the turn                 WP-0.7's shared phases (`loop.open_turn`)
    2. classify                      one small call, cheapest route, every turn
       (not captured — an ordinary WP-0.7 turn from here on)
    3. strip                         cheapest route; failure records contaminated
       (no preference present — steps collapse to one ordinary call)
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
content. Where separation fails, `ordering = contaminated` and nothing claims
an independence that did not happen, including the framing shown to Val.

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

Every fallback here is an honest one. A classifier failure or unparseable
verdict is a capture *miss*, logged, and the turn proceeds as an ordinary
WP-0.7 turn — manual retroactive marking remains (§4.8). A strip failure is a
failed separation and records `contaminated`. An unparseable blind position is
no position: nothing is recorded, the turn proceeds ordinarily, and the
`model_calls` row keeps the honest account of the call that was paid for. An
unparseable reconciliation verdict settles the turn but records no outcome —
never a guessed one. Nothing on any path fabricates a record.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Engine

from val_domain.deliberation import (
    BlindPositionRecord,
    ClassifiedBy,
    DeliberationClassification,
    DeliberationRecord,
    Ordering,
)
from val_domain.gateway import (
    Classification,
    GatewayError,
    GatewayRequest,
    Message,
    ModelConfig,
    PersonaAttribution,
    TaskType,
    TerminalState,
    TurnReference,
)
from val_domain.project import ProjectScope, attribution_of, attribution_state_of
from val_gateway.deliberation import record_blind_position, record_deliberation
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
    CLASSIFIER_INSTRUCTION,
    STRIP_INSTRUCTION,
    BlindOutcome,
    ClassifierVerdict,
    StripOutcome,
    parse_blind_outcome,
    parse_classifier_verdict,
    parse_strip_outcome,
    reconciliation_envelope,
    split_reconciled,
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
BLIND_MAX_OUTPUT_TOKENS = 1024


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
    verdict = _classify(gateway, content, opened.scope, classification)
    captured_as = None if verdict is None else verdict.captured_as
    hard_exclusion = None if verdict is None else verdict.hard_exclusion

    if captured_as is None:
        # Not captured — or the classifier failed, which is a logged miss, not
        # a reason to guess. An ordinary WP-0.7 turn from here on.
        outcome = _ordinary(
            engine, gateway, opened, classification, recall_limit, max_output_tokens
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
        )

    # 3. Strip. A failed or unparseable strip has not established separation,
    #    which is recorded as contaminated — never as a clean blindness.
    strip = _strip(gateway, content, opened.scope, classification)
    if strip is not None and not strip.preference_present:
        # §4.1: no preference present — steps collapse to one call. There is
        # no blindness to enforce and no stated view to reconcile with; the
        # exchange resolves later (his response arrives in a later turn) and
        # is recorded then, through the writer, against this capture.
        outcome = _ordinary(
            engine, gateway, opened, classification, recall_limit, max_output_tokens
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
        )

    if strip is not None and strip.separable:
        question, removed, ordering = strip.question, strip.removed, Ordering.ENFORCED
    else:
        # Preference present but not separable — or the strip itself failed.
        # The position will be formed with the preference in view, and the
        # record says exactly that.
        question, removed, ordering = content, "", Ordering.CONTAMINATED

    # 4. One configuration for both remaining calls (ruling, 19 August 2026).
    persona = DatabasePersonaLoader(engine).active()
    messages, recalled = assemble_turn(engine, opened, recall_limit=recall_limit)
    sizing = (*(message.content for message in messages), persona.content)
    try:
        config = gateway.select_configuration(classification, sizing, max_output_tokens)
    except GatewayError as failure:
        return unanswered_or_raise(opened, failure)

    # 5. The blind position, pinned, carrying the persona, payload logged.
    blind_message = Message(
        role="user", content=f"{BLIND_POSITION_INSTRUCTION}\n\nThe question:\n{question}"
    )
    blind_payload = _log_blind_payload(config, persona.id, blind_message)
    blind_request = GatewayRequest(
        task_type=TaskType.BLIND_POSITION,
        classification=classification,
        messages=(blind_message,),
        # The persona, whole, exactly once — and attributed, verified against
        # the active row by the gateway before transmission.
        system=persona.content,
        persona=PersonaAttribution(persona_id=persona.id),
        max_output_tokens=BLIND_MAX_OUTPUT_TOKENS,
        project_id=attribution_of(opened.scope),
        project_attribution=attribution_state_of(opened.scope),
    )
    try:
        blind_response = gateway.complete_with_configuration(blind_request, config)
    except GatewayError as failure:
        # The pinned route could not answer. No fallback — the turn is
        # unanswered rather than deliberated on a silently different route.
        return unanswered_or_raise(opened, failure)

    blind_outcome = _blind_outcome_from(blind_response.text, blind_response.terminal)
    if blind_outcome is None:
        _LOGGER.warning(
            "blind position call answered but stated no parseable position "
            "(terminal=%s). No evidence row is written — there is no position to "
            "record — and the turn proceeds as an ordinary one. The model_calls "
            "row keeps the honest account of the call.",
            blind_response.terminal.value,
        )
        outcome = _ordinary(
            engine, gateway, opened, classification, recall_limit, max_output_tokens
        )
        if isinstance(outcome, UnansweredTurn):
            return outcome
        return DeliberatedTurn(
            turn=outcome,
            captured_as=captured_as,
            hard_exclusion=None,
            blind=None,
            deliberation=None,
            blind_payload=blind_payload,
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
        )
    except GatewayError as failure:
        # The evidence row stays: the position was formed and recorded, and
        # the exchange going unanswered does not unhappen it.
        return unanswered_or_raise(opened, failure)

    # 8. Her prose becomes her message; the verdict is machinery output.
    prose, reconciliation = split_reconciled(response.text)
    turn = settle_turn(
        engine,
        opened,
        recalled,
        response,
        spoken_text=prose if reconciliation is not None else None,
    )

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
            "response carried no valid reconciliation verdict; the turn is "
            "settled but no deliberation outcome is recorded. The blind evidence "
            "stands, and the exchange can be resolved manually (§4.8 override)."
        )

    return DeliberatedTurn(
        turn=turn,
        captured_as=captured_as,
        hard_exclusion=None,
        blind=blind_row,
        deliberation=deliberation,
        blind_payload=blind_payload,
    )


def _ordinary(
    engine: Engine,
    gateway: Gateway,
    opened: OpenedTurn,
    classification: Classification,
    recall_limit: int,
    max_output_tokens: int,
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
        )
    except GatewayError as failure:
        return unanswered_or_raise(opened, failure)
    return settle_turn(engine, opened, recalled, response)


def _classify(
    gateway: Gateway, content: str, scope: ProjectScope, classification: Classification
) -> ClassifierVerdict | None:
    """One §4.8 classification call on the cheapest eligible route, or None.

    Routed through `complete`, whose attempt order is cheapest-first among the
    admitted, eligible, ready, and affordable — the routing already is the
    "cheapest eligible operational configuration" the ruling names. A failure
    is a logged capture miss, never a guessed verdict.
    """
    request = GatewayRequest(
        task_type=TaskType.CLASSIFICATION,
        classification=classification,
        messages=(Message(role="user", content=content),),
        system=CLASSIFIER_INSTRUCTION,
        max_output_tokens=CLASSIFIER_MAX_OUTPUT_TOKENS,
        project_id=attribution_of(scope),
        project_attribution=attribution_state_of(scope),
    )
    try:
        response = gateway.complete(request)
    except GatewayError as failure:
        _LOGGER.warning(
            "consequential classification failed (%s); this exchange is a capture "
            "miss, not a guessed verdict. Manual retroactive marking remains (§4.8).",
            failure.kind.value,
        )
        return None
    verdict = parse_classifier_verdict(response.text)
    if verdict is None:
        _LOGGER.warning(
            "consequential classification answered unparseably; treated as a "
            "capture miss and logged, never repaired into a verdict."
        )
    return verdict


def _strip(
    gateway: Gateway, content: str, scope: ProjectScope, classification: Classification
) -> StripOutcome | None:
    """One §4.1 strip call on the cheapest eligible route, or None.

    None — a failed call or an unparseable reply — means separation was not
    established, and the caller records `contaminated`: the honest reading,
    since an unestablished separation is an unestablished blindness.
    """
    request = GatewayRequest(
        task_type=TaskType.STRIP,
        classification=classification,
        messages=(Message(role="user", content=content),),
        system=STRIP_INSTRUCTION,
        max_output_tokens=STRIP_MAX_OUTPUT_TOKENS,
        project_id=attribution_of(scope),
        project_attribution=attribution_state_of(scope),
    )
    try:
        response = gateway.complete(request)
    except GatewayError as failure:
        _LOGGER.warning(
            "strip call failed (%s); separation not established, recording "
            "ordering=contaminated rather than an unearned blindness.",
            failure.kind.value,
        )
        return None
    return parse_strip_outcome(response.text)


def _blind_outcome_from(text: str, terminal: TerminalState) -> BlindOutcome | None:
    """The parsed blind position, honouring the terminal state.

    A truncated or filtered reply is a fragment, and a fragment of a position
    is not a position — the same doctrine that keeps fragments out of Val's
    message history keeps them out of the evidence table.
    """
    if terminal not in (TerminalState.COMPLETE, TerminalState.REFUSED):
        return None
    return parse_blind_outcome(text)


def _log_blind_payload(config: ModelConfig, persona_id: UUID, message: Message) -> str:
    """Log the exact payload of the blind call, before transmission.

    The WP-0.9 criterion: inspection of this payload must show no
    preference-bearing content. The variable content — the messages — is
    logged verbatim. The system prompt is the persona, whole; it is logged by
    its immutable revision id rather than repeated in full, because the row it
    names cannot change (`0005`) and twenty kilobytes of fixed identity per
    call would bury the part inspection is for.
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
    return payload
