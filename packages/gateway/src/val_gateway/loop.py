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

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Engine

from val_domain.conversation import ConversationRecord, MessageRecord, StoredRole
from val_domain.gateway import (
    Classification,
    GatewayError,
    GatewayErrorKind,
    GatewayResponse,
    Message,
    TerminalState,
    TurnReference,
)
from val_domain.project import AmbiguousProject, ProjectCandidate, ProjectScope
from val_gateway import conversations
from val_gateway.context import conversation_messages, recall_block
from val_gateway.exchange import ClarificationNeeded, RestrictedContentRefusedError, resolve_scope
from val_gateway.gateway import Gateway
from val_gateway.memory import DEFAULT_LIMIT, RecalledMessage, recall
from val_gateway.projects import ProjectSession
from val_policy.project_resolution import ProjectCatalogue, ProjectSignals
from val_policy.restricted import preflight, refusal_message


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
) -> TurnOutcome:
    """Say one thing to Val, in a conversation that outlives this process.

    Pass `conversation_id` to continue an existing conversation; omit it to start
    one. Continuing takes its scope from the stored row — `signals` and `session`
    are not consulted, because the conversation's own record is the authority on
    what it is about (WP-0.7 §18). Starting one resolves scope the WP-0.6 way.
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

    messages, recalled = assemble_turn(engine, opened, recall_limit=recall_limit)

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
            classification=classification,
            # One object rather than two loose ids — and `persona_id` is filled
            # in by `assemble`, which is where the persona is known. The gateway
            # verifies the three agree with the records before transmitting.
            turn=TurnReference(
                conversation_id=opened.conversation.id, message_id=opened.user_message.id
            ),
            max_output_tokens=max_output_tokens,
        )
    except GatewayError as failure:
        return unanswered_or_raise(opened, failure)

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
) -> OpenedTurn | ClarificationNeeded:
    """Steps 1-3: preflight what was typed, resolve scope, persist the message."""
    # 1. Restricted, on what the user just typed, before anything is stored.
    #    The assembled request is checked again at step 8; this one is so that
    #    obvious Restricted material is refused before it becomes history.
    finding = preflight((content,))
    if finding is not None:
        raise RestrictedContentRefusedError(refusal_message(finding))

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

    # 3. The user's message becomes history now, before any provider is involved.
    user_message = conversations.append(
        engine, conversation.id, role=StoredRole.USER, content=content
    )

    return OpenedTurn(conversation=conversation, scope=scope, user_message=user_message)


def assemble_turn(
    engine: Engine,
    opened: OpenedTurn,
    *,
    recall_limit: int = DEFAULT_LIMIT,
) -> tuple[tuple[Message, ...], tuple[RecalledMessage, ...]]:
    """Steps 4-7: history and recall, assembled into the outbound messages."""
    # 4-6. Persona, this conversation's own history, and the project's.
    history = conversations.history(engine, opened.conversation.id)
    recalled = recall(
        engine,
        scope=opened.scope,
        query=opened.user_message.content,
        exclude_conversation=opened.conversation.id,
        limit=recall_limit,
    )

    # 7. Assemble. The recall block first, then the conversation ending on the
    #    turn just persisted — which is why the current message is not appended
    #    again: it is already the last thing in `history`.
    block = recall_block(recalled)
    turns = conversation_messages(history)
    messages = (block, *turns) if block is not None else turns
    return messages, recalled


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
) -> Turn | TruncatedTurn:
    """Step 10: what happens to the text depends on how the call actually ended.

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
        content=response.text if spoken_text is None else spoken_text,
    )

    return Turn(
        conversation=conversations.load(engine, opened.conversation.id),
        scope=opened.scope,
        user_message=opened.user_message,
        val_message=val_message,
        response=response,
        recalled=recalled,
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
