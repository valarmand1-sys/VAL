"""The service's typed request and response contracts — WP-0.10.

Every response model here is a projection of authoritative records, and only
that. Nothing in these shapes can express a state the database does not
support (`00-charter.md` invariant 29): a deliberation outcome exists in a
response exactly when a `deliberations` row exists, a blind position carries
its recorded `ordering` verbatim so a contaminated position can never be
presented as independently formed, and a turn that got no answer is a shape
that says so rather than a message that was never said.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from val_domain.conversation import ConversationRecord, MessageRecord
from val_domain.deliberation import (
    BlindPositionRecord,
    ClassifiedBy,
    Confidence,
    DeliberationClassification,
    DeliberationRecord,
    Ordering,
    Outcome,
)
from val_domain.execution import ExecutionEventRecord, ExecutionEventType, Reaction
from val_domain.project import ProjectRecord

# =============================================================================
# Reads: projections of records, nothing else
# =============================================================================


class ProjectView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str
    slug: str
    status: str
    #: Presentation scoping only, never evidentiary (§2.1 amendment, 31 August
    #: 2026): hidden from default listings, and nothing else may be inferred.
    archived: bool = False

    @classmethod
    def of(cls, record: ProjectRecord) -> ProjectView:
        return cls(
            id=record.id,
            name=record.name,
            slug=record.slug,
            status=record.status,
            archived=record.archived_at is not None,
        )


class ConversationView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    project_id: UUID | None
    title: str
    started_at: datetime
    last_message_at: datetime
    #: Same rule as on ProjectView: display scoping, no evidentiary meaning.
    archived: bool = False

    @classmethod
    def of(cls, record: ConversationRecord) -> ConversationView:
        return cls(
            id=record.id,
            project_id=record.project_id,
            title=record.title,
            started_at=record.started_at,
            last_message_at=record.last_message_at,
            archived=record.archived_at is not None,
        )


class MessageView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    role: str
    content: str
    sequence: int
    created_at: datetime

    @classmethod
    def of(cls, record: MessageRecord) -> MessageView:
        return cls(
            id=record.id,
            role=record.role.value,
            content=record.content,
            sequence=record.sequence,
            created_at=record.created_at,
        )


class BlindPositionView(BaseModel):
    """A recorded blind position, `ordering` verbatim from the row.

    `independently_formed` is derived from `ordering` alone — the one field
    that says whether the blindness actually held — so no rendering layer has
    to remember the rule to be truthful about it.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    message_id: UUID
    position: str
    confidence: Confidence
    reasoning: str
    stripped_content: str
    ordering: Ordering
    independently_formed: bool
    classification: DeliberationClassification
    classified_by: ClassifiedBy
    created_at: datetime

    @classmethod
    def of(cls, record: BlindPositionRecord) -> BlindPositionView:
        return cls(
            id=record.id,
            message_id=record.message_id,
            position=record.position,
            confidence=record.confidence,
            reasoning=record.reasoning,
            stripped_content=record.stripped_content,
            ordering=record.ordering,
            independently_formed=record.ordering is Ordering.ENFORCED,
            classification=record.classification,
            classified_by=record.classified_by,
            created_at=record.created_at,
        )


class DeliberationView(BaseModel):
    """A resolved deliberation. This shape existing at all means the row does."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    message_id: UUID
    position: str
    confidence: Confidence
    reasoning: str
    stripped_content: str
    ordering: Ordering
    independently_formed: bool
    user_response: str
    outcome: Outcome
    what_changed_her_mind: str | None
    both_positions: str | None
    predictions: str | None
    classification: DeliberationClassification
    classified_by: ClassifiedBy
    blind_position_id: UUID | None
    created_at: datetime

    @classmethod
    def of(cls, record: DeliberationRecord) -> DeliberationView:
        return cls(
            id=record.id,
            message_id=record.message_id,
            position=record.position,
            confidence=record.confidence,
            reasoning=record.reasoning,
            stripped_content=record.stripped_content,
            ordering=record.ordering,
            independently_formed=record.ordering is Ordering.ENFORCED,
            user_response=record.user_response,
            outcome=record.outcome,
            what_changed_her_mind=record.what_changed_her_mind,
            both_positions=record.both_positions,
            predictions=record.predictions,
            classification=record.classification,
            classified_by=record.classified_by,
            blind_position_id=record.blind_position_id,
            created_at=record.created_at,
        )


class ExecutionEventView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    message_id: UUID
    event_type: ExecutionEventType | None
    subject: str
    reason: str | None
    reason_source: str
    reaction: Reaction | None
    created_at: datetime

    @classmethod
    def of(cls, record: ExecutionEventRecord) -> ExecutionEventView:
        return cls(
            id=record.id,
            message_id=record.message_id,
            event_type=record.event_type,
            subject=record.subject,
            reason=record.reason,
            reason_source=record.reason_source.value,
            reaction=record.reaction,
            created_at=record.created_at,
        )


class ConversationDetail(BaseModel):
    """One conversation with everything the records hold about it.

    Blind positions and deliberations are separate lists on purpose: a blind
    position with no deliberation resolving it is a real state — position
    recorded, outcome **pending** — and collapsing the two would force a
    display to either hide the position or invent its outcome. The
    `blind_position_id` link says which evidence a deliberation resolves.
    """

    model_config = ConfigDict(frozen=True)

    conversation: ConversationView
    messages: list[MessageView]
    blind_positions: list[BlindPositionView]
    deliberations: list[DeliberationView]
    execution_events: list[ExecutionEventView]


# =============================================================================
# The turn
# =============================================================================


class TurnRequest(BaseModel):
    """One thing said to Val.

    `project` is an explicit select-or-switch statement (a name or slug);
    `no_project` is the explicit statement that this is for no project. They
    are the two forms of stating scope now (WP-0.6); passing neither means the
    resumed conversation's own record — or, on a fresh conversation, the
    resolver's question — decides.
    """

    content: str
    conversation_id: UUID | None = None
    project: str | None = None
    no_project: bool = False
    title: str | None = None
    max_output_tokens: int = Field(default=4096, gt=0)


class DeliberationGlimpse(BaseModel):
    """What the just-finished turn's machinery actually recorded — WP-0.10.

    The visibility Lord Armand ruled on: when a turn is consequential, the
    position, its confidence, and what became of it are shown where they
    happen. Every field is a projection of a row created this turn:
    `blind` of the `blind_positions` evidence, `deliberation` of the
    `deliberations` row. `deliberation` is None whenever that row does not
    exist — the outcome is then **pending**, and no other value may be shown
    (invariant 29).
    """

    model_config = ConfigDict(frozen=True)

    captured_as: DeliberationClassification | None
    hard_exclusion: str | None
    blind: BlindPositionView | None
    deliberation: DeliberationView | None


class TurnAnswered(BaseModel):
    kind: str = "answered"
    conversation: ConversationView
    user_message: MessageView
    val_message: MessageView
    glimpse: DeliberationGlimpse


class CandidateView(BaseModel):
    """One project offered in a clarification — stable identity, no status.

    `status` is deliberately absent, matching `ProjectCandidate`: it has no
    settled semantics, and a field with no meaning does not belong in a payload
    whose whole job is to identify.
    """

    model_config = ConfigDict(frozen=True)

    project_id: UUID
    name: str
    slug: str


class TurnClarification(BaseModel):
    """Scope could not be resolved; nothing was created and nothing was sent."""

    kind: str = "clarification"
    question: str
    reason: str
    candidates: list[CandidateView]


class TurnUnanswered(BaseModel):
    """The message is history; no answer exists. No Val message was written.

    *Ruled 2 September 2026.* `provider_contacted` is read from the durable
    call lifecycle — a `model_calls` row for this turn's conversation call —
    never inferred from the error text. A pre-contact refusal (budget, no
    eligible route) carries `False`, and the interface must not say "the
    provider did not answer" over it: no provider was asked.
    """

    kind: str = "unanswered"
    conversation: ConversationView
    user_message: MessageView
    error: str
    error_kind: str
    provider_contacted: bool


class TurnTruncated(BaseModel):
    """The provider produced a fragment. It is evidence, not her message."""

    kind: str = "truncated"
    conversation: ConversationView
    user_message: MessageView
    partial_text: str
    glimpse: DeliberationGlimpse


TurnResponse = TurnAnswered | TurnClarification | TurnUnanswered | TurnTruncated


# =============================================================================
# Recording: execution events and manual deliberations
# =============================================================================


class ExecutionEventRequest(BaseModel):
    conversation_id: UUID
    message_id: UUID
    subject: str
    event_type: ExecutionEventType | None = None
    reaction: Reaction | None = None
    reason: str | None = None
    reason_inferred: bool = False
    declined_to_give_reason: bool = False


class ManualDeliberationRequest(BaseModel):
    """Marking an exchange consequential by hand — §4.8's override, both ways.

    `classified_by` is restricted to `user` and `val` at the endpoint: this is
    the manual channel, and a hand-entered record claiming the classifier made
    it would be false provenance.
    """

    conversation_id: UUID
    message_id: UUID
    position: str
    confidence: Confidence
    reasoning: str
    stripped_content: str = ""
    ordering: Ordering = Ordering.CONTAMINATED
    user_response: str
    outcome: Outcome
    what_changed_her_mind: str | None = None
    both_positions: str | None = None
    predictions: str | None = None
    classification: DeliberationClassification = DeliberationClassification.CONSEQUENTIAL
    classified_by: ClassifiedBy = ClassifiedBy.USER
    blind_position_id: UUID | None = None


# =============================================================================
# The cost view and the drift signal
# =============================================================================


class CostView(BaseModel):
    """Month-to-date spend, honestly incomplete when it is.

    `complete` is False whenever any call this month reached a provider whose
    cost was never established; the figures are then what is *known*, and the
    view says so rather than presenting them as the whole (invariant 29).
    `by_task_type` carries classification spend on its own line from day one
    (WP-0.9 ruling).
    """

    model_config = ConfigDict(frozen=True)

    month_to_date_usd: float
    by_task_type: dict[str, float]
    uncosted_calls: int
    complete: bool


class DisagreementSignal(BaseModel):
    """§4.7's one derived number: when Val last disagreed, or never."""

    model_config = ConfigDict(frozen=True)

    last_disagreement_at: datetime | None


class Health(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    warnings: list[str]
