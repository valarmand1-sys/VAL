"""One turn of a persisted conversation, start to finish — WP-0.7.

`04-layer-0.md` WP-0.7: *"a real conversation persists across a full application
restart and Val recalls prior context within a project."*

`exchange.py` holds WP-0.6's deterministic scope resolution and nothing
provider-bearing; this module is the conversation boundary. The conversation is
a row, the turn is a row, and what Val is sent is assembled from rows.

## The order, and what each step gates

    1. resolve scope                 deterministic, local, no provider
       (unresolved stops here — no conversation, no row, no call)
    2. create or resume conversation scope comes from the record on resume
    3. persist the user's message    it was said; it is history from now on
    4. load the active persona       WP-0.5, from `personas`, per call
    5. read same-conversation history in `sequence` order, ending on step 3
    6. recall project material       filtered by project inside the query
    7. assemble                      persona whole; memory as a serialised envelope
    8. Restricted preflight          over the **assembled** request, memory included
    9. budget, routing, provider     the ceiling sees the final payload
   10. persist Val's message         only if a complete answer came back
       (a refusal is complete; a truncated fragment is returned as evidence,
        never persisted as her reply — closure pass, 18 August 2026)

**Step 3 before step 9 is the important ordering.** The user's message is
persisted before the provider is called, so a provider failure leaves a real
record of an unanswered turn rather than losing what was said. History that is
missing a question because the answer failed is worse than history showing a
question that went unanswered — the second is what actually happened.

**Step 8 is where WP-0.7 changes the risk.** Until now, preflight examined what
the user typed. Now the outbound request also carries stored material that
somebody wrote at some earlier time, so the check has to cover the assembled
whole. It does, and not because this module repeats it: `Gateway.complete` runs
`_refuse_restricted` over `content_parts(request)`, which is every message plus
the system prompt. Memory enters as a message, so it is examined by construction.
The same is true of the budget ceiling, which is computed from those same parts —
so the ceiling sees the payload that will actually be sent, memory included,
rather than the payload before assembly.

## What this module does not do

**No fabricated answer.** If the provider fails, no `val` message is written. A
turn with no reply is a turn with no reply.

**A Restricted refusal is raised, not returned.** Only *provider* failures become
an `UnansweredTurn`. Refusing to transmit is a different event from failing to
transmit, and collapsing the two would hide the one outcome that must never be
quiet — especially now, since with memory the offending content may be something
stored long ago rather than something the user just typed.

**No exactly-once machinery, no outbox, no workflow engine.** WP-0.7 asks for a
durable conversation, not a distributed transaction. `00-charter.md` §8 rejected
Temporal early and `CLAUDE.md` forbids building a later layer's capability
because its design exists. A failure here is visible in the record and re-runs as
an ordinary next turn.

**No promotion of history to truth.** Retrieved conversation is quoted as
recorded discussion and framed as such. Nothing here decides that something said
earlier is now the case; that is a later layer's, and inventing it now would be
inventing exactly the machinery `02-partner-systems.md` reserves.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Connection, Engine

from val_domain.conversation import (
    ConversationRecord,
    MessageRecord,
    MessageState,
    StoredRole,
    WorkingThread,
)
from val_domain.gateway import (
    CapabilityProfile,
    Classification,
    GatewayError,
    GatewayErrorKind,
    GatewayResponse,
    ImagePart,
    Message,
    ModelConfig,
    TaskType,
    TerminalState,
    TurnReference,
)
from val_domain.perception import PerceptionRefusedError, PerceptionUnavailableError
from val_domain.project import AmbiguousProject, ExplicitNoProject, ProjectCandidate, ProjectScope
from val_domain.provider import DeltaSink
from val_domain.registry import active
from val_gateway import conversations
from val_gateway.attachments import (
    AttachmentAct,
    BoundImage,
    CandidateAttachment,
    admit_all,
    bind_to_call,
    commit_acts,
    earlier_image_count,
    prepare,
    strictest,
)
from val_gateway.context import (
    PriorRecordState,
    recall_block,
    record_state_block,
    select_conversation,
)
from val_gateway.exchange import ClarificationNeeded, RestrictedContentRefusedError, resolve_scope
from val_gateway.gateway import Gateway
from val_gateway.grounding import grounded_answers, record_answer_sources
from val_gateway.memory import (
    DEFAULT_LIMIT,
    RecalledMessage,
    RecallOutcome,
    house_recall_with_state,
    recall_with_state,
)
from val_gateway.perception import TurnPerception, perceive_turn, record_handoff
from val_gateway.projects import ProjectSession
from val_policy.budget import CONVERSATION_MAX_OUTPUT_TOKENS
from val_policy.project_resolution import ProjectCatalogue, ProjectSignals
from val_policy.recall_gate import ThreadContext, gate_house_recall, gate_recall
from val_policy.restricted import preflight, refusal_message
from val_policy.routing import is_admitted, is_eligible, satisfies_profile

_LOGGER = logging.getLogger("val.loop")


@dataclass(frozen=True)
class Turn:
    """One completed turn, with everything needed to check it afterwards.

    Carries the retrieved messages themselves rather than a count. WP-0.7 §13
    requires that the house can say which persisted messages were selected for a
    response; returning them means a test — or a person — can name the exact rows
    without a second query that might not reproduce the same selection.
    """

    conversation: ConversationRecord
    scope: ProjectScope
    user_message: MessageRecord
    val_message: MessageRecord
    response: GatewayResponse
    recalled: tuple[RecalledMessage, ...]


@dataclass(frozen=True)
class UnansweredTurn:
    """The user's message was persisted; the provider did not answer.

    Returned rather than raised so a caller cannot mistake it for nothing having
    happened. Something did happen: a message was recorded, and it is now part of
    the conversation whether or not a reply ever arrives.
    """

    conversation: ConversationRecord
    scope: ProjectScope
    user_message: MessageRecord
    error: Exception


@dataclass(frozen=True)
class TruncatedTurn:
    """The provider produced a fragment — cut off by the output cap or the filter.

    *Closure pass, 18 August 2026.* The user's message is persisted — it was
    said. Val's fragment is **not** persisted as her reply: a message record is
    the record of what she said, and she did not finish saying this. The
    fragment rides along as `partial_text` so the caller can inspect it, and
    the `model_calls` row records the call honestly (it happened and was paid
    for). Retrying with a larger cap is the caller's ordinary next turn.
    """

    conversation: ConversationRecord
    scope: ProjectScope
    user_message: MessageRecord
    partial_text: str
    response: GatewayResponse


TurnOutcome = Turn | UnansweredTurn | TruncatedTurn | ClarificationNeeded


@dataclass(frozen=True)
class OpenedTurn:
    """A turn whose scope is resolved and whose user message is now history.

    The state after steps 1-3, shared by the ordinary path (`send`) and the
    deliberated path (`val_gateway.deliberate.send`) — WP-0.9 factored these
    phases out rather than duplicating the scope/persistence doctrine, which
    is how two copies of it would drift.
    """

    conversation: ConversationRecord
    scope: ProjectScope
    user_message: MessageRecord
    #: Owner ruling, 19 September 2026: the attachment acts committed with this
    #: turn, in order. Empty on an ordinary text turn, which is every turn the
    #: house had before today.
    attachments: tuple[AttachmentAct, ...] = ()


#: The two forms of an explicit current-interaction scope choice. WP-0.6 put
#: them in one authority class — level 2 — because *"select Project Beta"* and
#: *"this is not for a project"* are the same act: the user stating scope now.
#:
#: A *mention* of a project is not one of these. `trusted_reference` and
#: `untrusted_candidate` sit at level 5 and below established conversation
#: scope, so naming Beta in passing inside an Alpha conversation is not a
#: switch — which is the whole difference between saying where you are and
#: talking about somewhere else.
def _states_scope_now(signals: ProjectSignals) -> bool:
    """Whether the user has just stated scope, in either of its two forms."""
    return signals.explicit_selection is not None or signals.explicit_no_project


@dataclass(frozen=True)
class VisualTurn:
    """What a turn's attachments mean for the calls it is about to make.

    Owner ruling, 19 September 2026 (Track C). Produced once, before the
    reservation, and used by **every** call of the turn — the ordinary response,
    and on a consequential turn both the blind position and the final answer.
    That is Attachment Substrate v1.2 §7's "derive once, reuse" made structural:
    the two calls cannot independently resize, because neither of them chooses.

    Owner ruling, 22 September 2026, amending it: when a local visual-perception
    route is admitted, a turn carrying media no longer pins an image-capable
    Partner and derives pixels for it. Val perceives the media herself, once, and
    the frozen observation travels to the cognition calls instead. `perception`
    then holds the run and `bound` is empty; when no perception route is wired
    the Track C behaviour below is exactly as it was.
    """

    classification: Classification
    #: The route the bytes were derived for. `None` when the turn carries no
    #: media, and `None` under local perception, where routing proceeds exactly
    #: as it does for an ordinary text turn because no pixels are transmitted.
    configuration: ModelConfig | None
    bound: tuple[BoundImage, ...]
    #: This turn's frozen local perception, run once, handed to every call.
    perception: TurnPerception | None = None

    @property
    def images(self) -> tuple[ImagePart, ...]:
        return tuple(image.part for image in self.bound)

    @property
    def blocks(self) -> tuple[Message, ...]:
        """The envelopes this turn's media contribute to every cognition call."""
        return () if self.perception is None else (self.perception.block(),)


def prepare_visual(
    engine: Engine,
    gateway: Gateway,
    opened: OpenedTurn,
    classification: Classification,
    max_output_tokens: int,
) -> VisualTurn:
    """Perceive this turn's media once, or — with no perception route — pin a route.

    The effective classification is the strictest of the text's and every act's
    (§6), and it governs either way: perception is local, but a local provider is
    checked for eligibility exactly as a remote one is, and Restricted is refused
    on both paths.

    **Under local perception, no route is pinned and no pixels are derived.** The
    cognition call that follows is an ordinary text call: it receives grounded
    observations, so the image-capable filter has nothing to filter for. That is
    the whole of §19 — an image turn no longer reaches a paid image-capable
    Partner merely because it contains an image.
    """
    effective = strictest(classification, opened.attachments)
    if not opened.attachments:
        return VisualTurn(classification=effective, configuration=None, bound=())

    perception_route = perception_configuration(effective)
    if perception_route is not None and gateway.perception is not None:
        # Failure raises. The caller fails the turn closed and says so; it does
        # not quietly send the owner's media to a paid provider instead.
        perceived = perceive_turn(
            engine,
            gateway.perception,
            perception_route,
            conversation_id=opened.conversation.id,
            message_id=opened.user_message.id,
            question=opened.user_message.content,
            acts=opened.attachments,
        )
        return VisualTurn(
            classification=effective, configuration=None, bound=(), perception=perceived
        )

    pinned = gateway.select_configuration(
        effective,
        (opened.user_message.content,),
        max_output_tokens,
        task_type=TaskType.CONVERSATION,
        # This turn carries images, so only a route declaring image input may be
        # pinned for it (21 September 2026). Reached only when there are acts —
        # the branch above returns first when there are none.
        requires_image_input=True,
    )
    return VisualTurn(
        classification=effective,
        configuration=pinned,
        bound=prepare(engine, opened.attachments, pinned),
    )


def perception_configuration(classification: Classification) -> ModelConfig | None:
    """The admitted local visual-perception route, or `None` if there is none.

    Deterministic, and it names no model: the perception profile is the only
    thing consulted, exactly as every other capability floor works. A route that
    is not admitted, not eligible for this classification, or does not declare
    the profile is not returned — and no route means the caller falls back to the
    Track C path rather than inventing one.
    """
    for config in active():
        if (
            is_admitted(config)
            and is_eligible(config, classification)
            and satisfies_profile(config, CapabilityProfile.PERCEPTION)
        ):
            return config
    return None


def bind_response(engine: Engine, response: GatewayResponse, visual: VisualTurn) -> None:
    """Record what reached this call, once it has a call to name.

    Two shapes, because there are two kinds of grounding. Transmitted pixels get
    a `model_call_image_inputs` binding (§3.6); a local perception gets a handoff
    row naming the frozen run, which is what proves the blind position and the
    final answer were grounded identically.
    """
    if response.model_call_id is None:
        return
    if visual.bound and visual.configuration is not None:
        bind_to_call(engine, response.model_call_id, visual.bound, visual.configuration)
    record_handoff(engine, visual.perception, response.model_call_id)


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
    max_output_tokens: int = CONVERSATION_MAX_OUTPUT_TOKENS,
    on_delta: DeltaSink | None = None,
    attachments: tuple[CandidateAttachment, ...] = (),
) -> TurnOutcome:
    """Say one thing to Val, in a conversation that outlives this process.

    Pass `conversation_id` to continue an existing conversation; omit it to start
    one. Continuing takes its scope from the stored row — `signals` and `session`
    are not consulted, because the conversation's own record is the authority on
    what it is about (WP-0.7 §18). Starting one resolves scope the WP-0.6 way.

    `on_delta` (Val Core Phase 1, 11 September 2026) receives Val's generated
    text as it is produced, through the gateway, when the route can stream.
    Presentation only: the turn is settled from the completed response exactly
    as without it — a truncated reply is still not spoken, and the persisted
    message is the settled text, never the sum of the deltas.
    """
    opened = open_turn(
        engine,
        content,
        catalogue=catalogue,
        signals=signals,
        session=session,
        conversation_id=conversation_id,
        title=title,
        attachments=attachments,
    )
    if isinstance(opened, ClarificationNeeded):
        return opened

    # Owner ruling, 19 September 2026 (Track C). A turn carrying images needs the
    # route decided BEFORE the bytes are chosen, because what may be transmitted
    # depends on what that route accepts (Attachment Substrate v1.2 §8: admit →
    # derive if needed → reserve from the bytes that will actually be sent →
    # call). This is the same "selected once" device WP-0.9 already uses for the
    # blind position and the response, and for the same reason: two calls that
    # could pick different routes could send different pixels.
    #
    # The effective classification is the strictest of the text's and every
    # act's (§6), so routing and eligibility run on what is actually leaving.
    try:
        visual = prepare_visual(engine, gateway, opened, classification, max_output_tokens)
    except GatewayError as failure:
        return unanswered_or_raise(opened, failure)
    except (PerceptionUnavailableError, PerceptionRefusedError) as failure:
        # Owner ruling, 22 September 2026 §19: fail closed, honestly. The local
        # visual route has already made its one bounded recovery attempt. The
        # media are NOT sent to a paid image-capable Partner instead — that would
        # be a decision nobody made — so the turn ends with the reason on record
        # and the user's message preserved as the unanswered turn it is.
        return unanswered_or_raise(
            opened,
            GatewayError(GatewayErrorKind.LOCAL_PERCEPTION_UNAVAILABLE, str(failure)),
        )

    messages, recalled = assemble_turn(
        engine,
        opened,
        recall_limit=recall_limit,
        images=visual.images,
        perception=visual.perception,
    )

    # 8-9. Preflight over the assembled whole, budget over the same parts, then
    #      the provider. All three happen inside `converse`/`complete`.
    #
    #      Only `GatewayError` is caught. A `PersonaUnavailableError` propagates:
    #      Val having no identity to speak from is not a provider outage, and
    #      WP-0.5 is explicit that there is no degraded mode. Returning it as an
    #      unanswered turn would present a misconfigured house as a bad night on
    #      the network.
    try:
        response = gateway.converse(
            messages,
            scope=opened.scope,
            classification=visual.classification,
            # One object rather than two loose ids — and `persona_id` is filled
            # in by `assemble`, which is where the persona is known. The gateway
            # verifies the three agree with the records before transmitting.
            turn=TurnReference(
                conversation_id=opened.conversation.id, message_id=opened.user_message.id
            ),
            max_output_tokens=max_output_tokens,
            on_delta=on_delta,
            # Pinned to the route the bytes were derived for. Pinning changes
            # which route, never which checks: admission, eligibility, the
            # quality floor and the budget all run on their own account.
            configuration=visual.configuration,
        )
    except GatewayError as failure:
        return unanswered_or_raise(opened, failure)

    # §3.6 — which exact bytes reached which call, through which act. Written
    # after the call is recorded, from the same plan that was transmitted; it is
    # a binding, never a claim of sight.
    bind_response(engine, response, visual)

    return settle_turn(engine, opened, recalled, response)


def open_turn(
    engine: Engine,
    content: str,
    *,
    catalogue: ProjectCatalogue,
    signals: ProjectSignals | None = None,
    session: ProjectSession | None = None,
    conversation_id: UUID | None = None,
    title: str | None = None,
    attachments: tuple[CandidateAttachment, ...] = (),
) -> OpenedTurn | ClarificationNeeded:
    """Steps 1-3: preflight what was typed, resolve scope, persist the message."""
    # 1. Restricted, on what the user just typed, before anything is stored.
    #    The assembled request is checked again at step 8; this one is so that
    #    obvious Restricted material is refused before it becomes history.
    finding = preflight((content,))
    if finding is not None:
        raise RestrictedContentRefusedError(refusal_message(finding))

    # 1b. Admission, over the ephemeral candidate bytes, **before any scope is
    #     resolved and before any conversation exists** (Attachment Substrate
    #     v1.2 §3.3). A refusal raises the way a Restricted refusal does, and for
    #     the same reason: the send did not happen, so nothing it would have
    #     written — conversation, message, blob, attachment, act, processing
    #     event — is written. Remove-before-send accumulates no evidence of
    #     things never sent.
    admitted = admit_all(attachments)

    # 2. Scope, and the conversation it belongs to.
    #
    # Three cases, in authority order:
    #
    #   resuming, nothing stated   -> the conversation's own record decides
    #   resuming, scope stated now -> the statement wins; a NEW conversation
    #   not resuming               -> resolve the WP-0.6 way
    stated = signals or ProjectSignals()
    switching = conversation_id is not None and _states_scope_now(stated)

    if conversation_id is not None and not switching:
        # The conversation's stored scope is the authority. Session state is not
        # consulted at all — a session pointing elsewhere is stale relative to
        # the conversation actually open (WP-0.7 §18) — and a mere *mention* of
        # another project is lower authority than established conversation scope,
        # so it does not reach here either.
        conversation, scope = conversations.resume(engine, conversation_id)
    else:
        # **An explicit choice made now outranks the conversation being resumed.**
        # *Corrected 18 August 2026, after independent review.* Resuming used to
        # drop `signals` entirely, so "switch to Project Beta" typed inside an
        # Alpha conversation was answered inside Alpha. WP-0.6 settled that
        # naming a project and declining one are one authority class, and that
        # both outrank established conversation state — they are a decision being
        # made in this breath, not a record of an older one.
        #
        # The resolver decides, not this function, so two contradictory
        # statements at once conflict and ask rather than being picked between.
        #
        # `session` is passed only when starting fresh. On a switch it is
        # deliberately withheld: the user has just said where they are, and a
        # stale session has nothing to add to that.
        resolution = resolve_scope(stated, catalogue, None if switching else session)
        if isinstance(resolution, AmbiguousProject):
            # Nothing is created. An unresolved exchange has no conversation to
            # belong to, and inventing one would be inventing its scope.
            return ClarificationNeeded(
                question=resolution.question,
                reason=resolution.reason,
                candidates=tuple(ProjectCandidate.of(p) for p in resolution.candidates),
            )
        scope = resolution
        # **Forward-only.** A switch starts a new conversation and never rewrites
        # the one being left — whose `project_id` is immutable in the database
        # anyway (migration `0008`).
        conversation = conversations.create(
            engine, scope=scope, title=title or _title_from(content)
        )

    # 3. The user's message becomes history now, before any provider is involved —
    #    and, since 19 September 2026, so does every attachment admitted with it.
    #    Attachment Substrate v1.2 §3.3: admission first, over ephemeral candidate
    #    bytes; then ONE transaction holding the blob, the attachment, the act and
    #    the message. A refused admission never reaches this line, so it leaves no
    #    blob, no attachment, no association, no processing event, and no message.
    acts: tuple[AttachmentAct, ...] = ()
    if attachments:

        def _commit(connection: Connection, message_id: UUID) -> None:
            nonlocal acts
            acts = commit_acts(connection, message_id, attachments, admitted)

        user_message = conversations.append(
            engine, conversation.id, role=StoredRole.USER, content=content, also=_commit
        )
    else:
        user_message = conversations.append(
            engine, conversation.id, role=StoredRole.USER, content=content
        )

    return OpenedTurn(
        conversation=conversation, scope=scope, user_message=user_message, attachments=acts
    )


def local_now() -> datetime:
    """The gateway's clock, in the machine's local zone. Replaced in tests."""
    return datetime.now().astimezone()


def assemble_turn(
    engine: Engine,
    opened: OpenedTurn,
    *,
    recall_limit: int = DEFAULT_LIMIT,
    images: tuple[ImagePart, ...] = (),
    perception: TurnPerception | None = None,
) -> tuple[tuple[Message, ...], tuple[RecalledMessage, ...]]:
    """Steps 4-7: history and recall, assembled into the outbound messages."""
    # 4-6. This conversation's own history — never gated — then cross-conversation
    #    recall, behind the deterministic necessity gate (ruled 10 September 2026).
    #
    #    Ruling, 12 September 2026: the history is the working conversation **as
    #    of this turn's own sequence** — messages up to and including this turn's
    #    message, and only the revision facts recorded before it
    #    (`after_sequence < s`). Corrected messages carry their wording in force;
    #    a withdrawn message and Val's immediate answer to it are left out. A
    #    fact recorded after this turn was opened cannot reach it, and a later
    #    reconstruction of this turn yields exactly what it received.
    thread = conversations.working(
        engine, opened.conversation.id, as_of_sequence=opened.user_message.sequence
    )
    history = thread.live_records()
    turns, selection = select_conversation(history)
    prior, current = turns[:-1], turns[-1:]
    corrected_after_answer, withdrawn_after = revision_facts(thread, selection.retained_from)
    # Ruling, 13 September 2026: which retained Val answers were grounded in House
    # Recall when given, and in which sources — provenance only, no content.
    grounded = grounded_answers(engine, thread, selection.retained_from)
    earlier = earlier_image_count(engine, opened.conversation.id, opened.user_message.id)
    # Four states, never collapsed: bound now, only earlier, none at all, or —
    # when this turn admitted attachments that produced no bound image — not
    # established, which fails toward doubt rather than toward sight.
    #
    # Owner ruling, 22 September 2026, adds a fifth: `perceived`. It is checked
    # first because it is the one state that says what actually happened on this
    # turn under local perception — the House looked at the media, and the
    # cognition model is receiving grounded observations rather than pixels.
    # `bound` is untouched and keeps its Track C meaning exactly: raw media
    # supplied directly to the cognition provider. Historical rows are not
    # reinterpreted, and nothing collapses the two.
    if perception is not None:
        visual_state = "perceived"
    elif images:
        visual_state = "bound"
    elif opened.attachments:
        visual_state = "uncertain"
    elif earlier:
        visual_state = "earlier_only"
    else:
        visual_state = "none"
    now = local_now()
    current_local_time = now.strftime("%A %-d %B %Y, %H:%M")
    context = ThreadContext(
        retained=tuple((m.role, m.content) for m in prior),
        envelope_facts=(current_local_time, now.strftime("%H:%M")),
    )
    decision = gate_recall(
        opened.user_message.content,
        no_project=isinstance(opened.scope, ExplicitNoProject),
        context=context,
    )
    _LOGGER.info(
        "recall gate: %s",
        json.dumps({"run": decision.run, "reason": decision.reason, "detail": decision.detail}),
    )
    if decision.run:
        outcome = recall_with_state(
            engine,
            scope=opened.scope,
            query=opened.user_message.content,
            exclude_conversation=opened.conversation.id,
            limit=recall_limit,
        )
    else:
        outcome = RecallOutcome(state="not_run", detail=decision.reason)
    recalled = outcome.items

    # House Recall (ruling, 12 September 2026): the explicitly triggered
    # cross-conversation path, gated independently, never altering the
    # automatic decision above. Runs only on an explicit reference to earlier
    # conversation; searches everything except this conversation; excerpts
    # already admitted by automatic recall are not admitted twice, and they
    # count against the one envelope's byte limit (ruling, 13 September 2026).
    house_decision = gate_house_recall(opened.user_message.content, context)
    _LOGGER.info(
        "house recall gate: %s",
        json.dumps(
            {
                "run": house_decision.run,
                "reason": house_decision.reason,
                "detail": house_decision.detail,
            }
        ),
    )
    if house_decision.run:
        house = house_recall_with_state(
            engine,
            query=opened.user_message.content,
            exclude_conversation=opened.conversation.id,
            exclude_message_ids=frozenset(item.message_id for item in recalled),
            admitted_before=recalled,
            limit=recall_limit,
        )
    else:
        house = RecallOutcome(state="not_run", detail=house_decision.reason)
    recalled = (*recalled, *house.items)

    # 7. Assemble, in the ruled order (10 September 2026): persona (system) →
    #    retained history, its last message carrying the cache breakpoint →
    #    recalled excerpts, if any → the record-state envelope → the current
    #    turn. The current message is already the last thing in `history`.
    prior_count = sum(1 for record in history if record.role.value in ("user", "val")) - 1
    state = PriorRecordState(
        current_local_time=current_local_time,
        current_timezone=now.strftime("%Z (UTC%z)"),
        history_state="available" if prior_count > 0 else "zero",
        history_prior_messages=max(prior_count, 0),
        history_retained_messages=len(prior),
        retrieval_state=outcome.state,
        retrieval_excerpts=len(outcome.items),
        retrieval_detail=outcome.detail,
        house_recall_state=house.state,
        house_recall_count=len(house.items),
        house_recall_detail=house.detail,
        corrected_after_answer=corrected_after_answer,
        withdrawn_after_positions=withdrawn_after,
        grounded_answers=grounded,
        # Owner ruling, 19 September 2026: current-turn visual binding, stated
        # deterministically. `earlier` counts this conversation's attachment
        # acts outside this turn — they are in the record and not in view.
        visual_state=visual_state,
        visual_bound_to_this_turn=len(images),
        visual_perceived_this_turn=(0 if perception is None else len(perception.sources)),
        visual_earlier_in_conversation=earlier,
    )
    _LOGGER.info("prior record state: %s", json.dumps(state.as_document()))
    excerpts = recall_block(recalled)
    # Owner ruling, 19 September 2026: CURRENT-TURN visual binding. The images
    # admitted with this turn join this turn's message, after its words, and are
    # never silently retransmitted on a later turn. Earlier images stay in the
    # record — their bytes, provenance, acts and historical bindings all survive
    # — but they are not in view, and the record-state envelope above says so
    # deterministically rather than leaving Val to infer it from prose.
    if images:
        current = tuple(
            message.model_copy(update={"parts": (*message.parts, *images)})
            if index == len(current) - 1
            else message
            for index, message in enumerate(current)
        )
    messages = (
        *prior,
        *((excerpts,) if excerpts is not None else ()),
        record_state_block(state),
        # The grounded observations, after the record state and before the turn
        # they describe: the envelope has just said current perception is
        # `perceived`, and this is what that state refers to.
        *((perception.block(),) if perception is not None else ()),
        *current,
    )
    return messages, recalled


def revision_facts(
    thread: WorkingThread, retained_from: int
) -> tuple[tuple[tuple[int, int], ...], tuple[int, ...]]:
    """The record-state facts about corrections and withdrawals for one request.

    Ruling, 12 September 2026. Positions count the retained prior messages of
    this request from 1, oldest first — the same messages, in the same order,
    that precede the envelope. A message corrected after Val answered it is
    named with her answer's position; a withdrawn exchange that stood inside the
    retained span — after the last live message not retained — is named by how
    many retained messages precede where it was.
    Facts outside the retained span describe nothing in this request and are
    not stated.
    """
    conversational = tuple(
        message
        for message in thread.live()
        if message.record.role in (StoredRole.USER, StoredRole.VAL)
    )
    retained = conversational[retained_from:]
    prior = retained[:-1]
    corrected: list[tuple[int, int]] = []
    for index, message in enumerate(prior[:-1]):
        answer = prior[index + 1]
        if (
            message.state is MessageState.CORRECTED
            and answer.record.role is StoredRole.VAL
            and answer.answered_state is MessageState.CORRECTED
        ):
            corrected.append((index + 1, index + 2))
    withdrawn: list[int] = []
    if retained:
        # The retained span begins just after the last live message that was not
        # retained (or at the start of the conversation when all were).
        boundary = conversational[retained_from - 1].record.sequence if retained_from > 0 else 0
        for message in thread.messages:
            if (
                message.record.role is StoredRole.USER
                and message.state is MessageState.WITHDRAWN
                and message.record.sequence > boundary
            ):
                withdrawn.append(
                    sum(1 for kept in prior if kept.record.sequence < message.record.sequence)
                )
    return tuple(corrected), tuple(withdrawn)


def unanswered_or_raise(opened: OpenedTurn, failure: GatewayError) -> UnansweredTurn:
    """A gateway failure, as WP-0.7 §15 requires it surfaced.

    **Restricted is not an unanswered turn.** It is a refusal, and it is
    raised. Returning it as "the provider did not answer" would be the
    opposite: the quiet outcome, indistinguishable from a rate limit, when
    what happened is that the assembled payload contained material that must
    never leave the machine. That distinction matters most precisely here,
    because with memory the offending content can be something written months
    ago rather than something the user just typed.

    Everything else the gateway normalises — timeout, rate limit, no eligible
    route, budget — is the provider not answering. No `val` row: writing one
    would fabricate the single thing this system exists to be able to prove it
    did not do.
    """
    if failure.kind is GatewayErrorKind.RESTRICTED_CONTENT:
        raise RestrictedContentRefusedError(str(failure)) from failure
    return UnansweredTurn(
        conversation=opened.conversation,
        scope=opened.scope,
        user_message=opened.user_message,
        error=failure,
    )


def settle_turn(
    engine: Engine,
    opened: OpenedTurn,
    recalled: tuple[RecalledMessage, ...],
    response: GatewayResponse,
    *,
    spoken_text: str | None = None,
) -> Turn | TruncatedTurn | UnansweredTurn:
    """Step 10: what happens to the text depends on how the call actually ended.

    **Ruling, 8 September 2026: a result with no valid user-visible text never
    becomes a Val message.** The 18 August doctrine below assumed a refusal
    carries words; a provider refusal with zero output tokens was persisted as
    an empty utterance — a false record, the same class as the classifier
    failing silently to ordinary. Now: if the text to be spoken is empty, the
    turn ends **unanswered**, the user message and the `model_calls` row stay,
    the provider's own terminal fields are surfaced as the observed cause
    outside Val's voice, and no assistant message is written. Where the
    provider gave a recognised reason (a refusal, a cut-off), the cause names
    it; where it gave none, the cause states only the observed fact.

    Closure pass, 18 August 2026. COMPLETE and REFUSED are both whole
    utterances (a deliberate refusal is Val's answer) and join the record.
    TRUNCATED is a fragment: the provider cut it off at the output cap, and
    persisting it as her message would put half a sentence in her mouth as
    though she finished it. The fragment is returned as evidence — the caller
    can see it, raise the cap, and ask again — and the user's turn stays in
    the record as asked-and-not-yet-answered, which is what actually happened.

    `spoken_text`, when given, is what enters history as Val's message in
    place of the raw response text — WP-0.9's deliberated path persists her
    prose without the machine-readable reconciliation verdict that rides after
    it. What she *said* is the prose; the verdict is machinery output, and the
    raw text stays inspectable on `response.text`.
    """
    spoken = response.text if spoken_text is None else spoken_text
    if not spoken.strip():
        return _no_valid_content(opened, response)

    if response.terminal in (TerminalState.TRUNCATED, TerminalState.FILTERED):
        # TRUNCATED: the output cap cut it off. FILTERED — independent-review
        # correction, 18 August 2026: the provider's content filter cut it off,
        # which the first closure pass mis-mapped to REFUSED and therefore
        # persisted as a finished utterance. Both are fragments; neither enters
        # history as Val's message. The precise state rides on
        # `outcome.response.terminal` and is durable on the model_calls row.
        return TruncatedTurn(
            conversation=opened.conversation,
            scope=opened.scope,
            user_message=opened.user_message,
            partial_text=response.text,
            response=response,
        )

    val_message = conversations.append(
        engine,
        opened.conversation.id,
        role=StoredRole.VAL,
        content=spoken,
    )
    # Ruling, 13 September 2026: bind the answer to the House Recall sources its
    # call received — provenance only, never content — so a later turn can know
    # it was grounded. Written after the message, failing toward no provenance.
    record_answer_sources(
        engine,
        conversation_id=opened.conversation.id,
        answer_message_id=val_message.id,
        model_call_id=response.model_call_id,
        recalled=recalled,
    )

    return Turn(
        conversation=conversations.load(engine, opened.conversation.id),
        scope=opened.scope,
        user_message=opened.user_message,
        val_message=val_message,
        response=response,
        recalled=recalled,
    )


def _no_valid_content(opened: OpenedTurn, response: GatewayResponse) -> UnansweredTurn:
    """The provider returned no valid assistant text: unanswered, with the observed cause.

    Ruling, 8 September 2026. Nothing here invents an explanation. A refusal
    the provider declared is reported as a refusal with whatever category or
    detail it supplied; a cut-off is reported as the cut-off; a completed
    call with nothing in it is reported as exactly that.
    """
    observed = f"stop_reason: {response.stop_reason or 'not reported'}"
    if response.stop_details:
        observed += f"; details: {response.stop_details}"
    _LOGGER.warning(
        "no valid assistant content from %s (terminal=%s; %s; output tokens=%s); the turn "
        "ends unanswered and no Val message is written",
        response.slug,
        response.terminal.value,
        observed,
        response.tokens_out,
    )
    calls = () if response.model_call_id is None else (response.model_call_id,)
    if response.terminal is TerminalState.REFUSED:
        return UnansweredTurn(
            conversation=opened.conversation,
            scope=opened.scope,
            user_message=opened.user_message,
            error=GatewayError(
                GatewayErrorKind.REFUSAL,
                f"the provider refused to answer and returned no text ({observed}). "
                "Nothing was written in Val's voice; the call is recorded.",
                model_call_ids=calls,
            ),
        )
    if response.terminal in (TerminalState.TRUNCATED, TerminalState.FILTERED):
        return UnansweredTurn(
            conversation=opened.conversation,
            scope=opened.scope,
            user_message=opened.user_message,
            error=GatewayError(
                GatewayErrorKind.INVALID_OUTPUT,
                f"the provider ended the call {response.terminal.value} with no text "
                f"({observed}). Nothing was written in Val's voice; the call is recorded.",
                model_call_ids=calls,
            ),
        )
    return UnansweredTurn(
        conversation=opened.conversation,
        scope=opened.scope,
        user_message=opened.user_message,
        error=GatewayError(
            GatewayErrorKind.INVALID_OUTPUT,
            f"the provider returned no valid assistant content ({observed}). No reason was "
            "recognised, and none is invented; nothing was written in Val's voice, and the "
            "call is recorded.",
            model_call_ids=calls,
        ),
    )


#: How long a conversation's generated title may be. A label, not a summary.
TITLE_LENGTH = 60


def _title_from(content: str) -> str:
    """A plain title for a new conversation, taken from its first message.

    Deterministic and local — **no model call**. Titling is a `task_type` the
    schema anticipates, and asking a provider to name a conversation would mean
    sending its content somewhere before scope-aware assembly has run. A truncated
    first line is a worse title and a better default; a real one can be set later.

    This truncates a *title*, never a message. `messages.content` is stored whole.
    """
    first = content.strip().splitlines()[0] if content.strip() else "Untitled"
    if len(first) <= TITLE_LENGTH:
        return first
    return first[: TITLE_LENGTH - 1].rstrip() + "…"
