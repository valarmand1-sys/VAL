"""One turn of a persisted conversation, start to finish — WP-0.7.

`04-layer-0.md` WP-0.7: *"a real conversation persists across a full application
restart and Val recalls prior context within a project."*

`exchange.py` is WP-0.6's boundary: it settles scope and answers once, holding
nothing. This is the same shape with a memory: the conversation is a row, the
turn is a row, and what Val is sent is assembled from rows.

## The order, and what each step gates

    1. resolve scope                 deterministic, local, no provider
       (unresolved stops here — no conversation, no row, no call)
    2. create or resume conversation scope comes from the record on resume
    3. persist the user's message    it was said; it is history from now on
    4. load the active persona       WP-0.5, from `personas`, per call
    5. read same-conversation history in `sequence` order, ending on step 3
    6. recall project material       filtered by project inside the query
    7. assemble                      persona whole; memory as delimited data
    8. Restricted preflight          over the **assembled** request, memory included
    9. budget, routing, provider     the ceiling sees the final payload
   10. persist Val's message         only if a real answer came back

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
    TaskType,
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


TurnOutcome = Turn | UnansweredTurn | ClarificationNeeded


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
    task_type: TaskType = TaskType.CONVERSATION,
    recall_limit: int = DEFAULT_LIMIT,
    max_output_tokens: int = 4096,
) -> TurnOutcome:
    """Say one thing to Val, in a conversation that outlives this process.

    Pass `conversation_id` to continue an existing conversation; omit it to start
    one. Continuing takes its scope from the stored row — `signals` and `session`
    are not consulted, because the conversation's own record is the authority on
    what it is about (WP-0.7 §18). Starting one resolves scope the WP-0.6 way.
    """
    # 1. Restricted, on what the user just typed, before anything is stored.
    #    The assembled request is checked again at step 8; this one is so that
    #    obvious Restricted material is refused before it becomes history.
    finding = preflight((content,))
    if finding is not None:
        raise RestrictedContentRefusedError(refusal_message(finding))

    # 2. Scope, and the conversation it belongs to.
    if conversation_id is not None:
        conversation, scope = conversations.resume(engine, conversation_id)
    else:
        resolution = resolve_scope(signals or ProjectSignals(), catalogue, session)
        if isinstance(resolution, AmbiguousProject):
            # Nothing is created. An unresolved exchange has no conversation to
            # belong to, and inventing one would be inventing its scope.
            return ClarificationNeeded(
                question=resolution.question,
                reason=resolution.reason,
                candidates=tuple(ProjectCandidate.of(p) for p in resolution.candidates),
            )
        scope = resolution
        conversation = conversations.create(
            engine, scope=scope, title=title or _title_from(content)
        )

    # 3. The user's message becomes history now, before any provider is involved.
    user_message = conversations.append(
        engine, conversation.id, role=StoredRole.USER, content=content
    )

    # 4-6. Persona, this conversation's own history, and the project's.
    history = conversations.history(engine, conversation.id)
    recalled = recall(
        engine,
        scope=scope,
        query=content,
        exclude_conversation=conversation.id,
        limit=recall_limit,
    )

    # 7. Assemble. The recall block first, then the conversation ending on the
    #    turn just persisted — which is why the current message is not appended
    #    again: it is already the last thing in `history`.
    block = recall_block(recalled)
    turns = conversation_messages(history)
    messages = (block, *turns) if block is not None else turns

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
            scope=scope,
            classification=classification,
            task_type=task_type,
            conversation_id=conversation.id,
            message_id=user_message.id,
            max_output_tokens=max_output_tokens,
        )
    except GatewayError as failure:
        # **Restricted is not an unanswered turn.** It is a refusal, and it is
        # raised. WP-0.7 §15 requires the failure be explicit, and returning it
        # as "the provider did not answer" would be the opposite: the quiet
        # outcome, indistinguishable from a rate limit, when what happened is
        # that the assembled payload contained material that must never leave the
        # machine. That distinction matters most precisely here, because with
        # memory the offending content can be something written months ago rather
        # than something the user just typed.
        if failure.kind is GatewayErrorKind.RESTRICTED_CONTENT:
            raise RestrictedContentRefusedError(str(failure)) from failure

        # Everything else the gateway normalises — timeout, rate limit, no
        # eligible route, budget — is the provider not answering. No `val` row:
        # writing one would fabricate the single thing this system exists to be
        # able to prove it did not do.
        return UnansweredTurn(
            conversation=conversation,
            scope=scope,
            user_message=user_message,
            error=failure,
        )

    # 10. A real answer, so it joins the record at the next sequence.
    val_message = conversations.append(
        engine, conversation.id, role=StoredRole.VAL, content=response.text
    )

    return Turn(
        conversation=conversations.load(engine, conversation.id),
        scope=scope,
        user_message=user_message,
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
