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
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from val_domain.classification_review import (
    Agreement,
    ClassificationLabelRecord,
    ClassificationReviewRecord,
    HumanClassification,
    ReviewConclusion,
    TuningState,
)
from val_domain.conversation import (
    ConversationRecord,
    MessageRecord,
    MessageRevisionRecord,
    ScopeTransitionRecord,
    StoredRole,
    WorkingMessage,
)
from val_domain.deliberation import (
    BlindPositionRecord,
    ClassificationRecord,
    ClassificationVerdict,
    ClassifiedBy,
    Confidence,
    DeliberationClassification,
    DeliberationRecord,
    Ordering,
    Outcome,
)
from val_domain.execution import ExecutionEventRecord, ExecutionEventType, Reaction
from val_domain.project import ProjectRecord
from val_gateway.attachments import AttachmentAct
from val_gateway.classification_review import (
    LabelledExchange,
    QueuedExchange,
    ReviewProgress,
)
from val_gateway.speech import SpokenText
from val_policy.budget import CONVERSATION_MAX_OUTPUT_TOKENS

# =============================================================================
# Reads: projections of records, nothing else
# =============================================================================


class RemovalRequest(BaseModel):
    """Remove or reinstate a conversation — ruling, 12 September 2026. The note is optional."""

    model_config = ConfigDict(frozen=True)

    note: str | None = None


class MoveRequest(BaseModel):
    """Move a conversation — ruling, 12 September 2026. Exactly one destination.

    `project_id` names a project; `no_project: true` moves it out of every
    project. Stating both, or neither, is refused rather than guessed.
    """

    model_config = ConfigDict(frozen=True)

    project_id: UUID | None = None
    no_project: bool = False
    note: str | None = None


class ScopeTransitionView(BaseModel):
    """One explicit move, from the record. NULL means explicitly no project."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    transition_number: int
    after_sequence: int
    from_project_id: UUID | None
    to_project_id: UUID | None
    note: str | None
    authored_by: str
    created_at: datetime

    @classmethod
    def of(cls, record: ScopeTransitionRecord) -> ScopeTransitionView:
        return cls(
            id=record.id,
            transition_number=record.transition_number,
            after_sequence=record.after_sequence,
            from_project_id=record.from_project_id,
            to_project_id=record.to_project_id,
            note=record.note,
            authored_by=record.authored_by,
            created_at=record.created_at,
        )


class RenameRequest(BaseModel):
    """Set a conversation's title — ruling, 12 September 2026. Presentation only."""

    model_config = ConfigDict(frozen=True)

    title: str


class ProjectCreateRequest(BaseModel):
    """Create a project by name — ruled 7 September 2026, the smallest proper path.

    Name only. The slug is derived mechanically, the status is `active`, the
    description is empty. Anything more is project management, which no
    contract asks for.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=200)


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
    #: Ruling, 12 September 2026: removed from active use — no recall, no new
    #: turns, nothing destroyed. Reinstating reverses it.
    removed: bool = False
    #: Ruling, 12 September 2026: `project_id` is the scope that governs the
    #: next turn — where an explicit move put the conversation, else where it
    #: began. `origin_project_id` is where it began, immutable. They differ only
    #: after a move; NULL on either means explicitly no project.
    origin_project_id: UUID | None = None

    @classmethod
    def of(cls, record: ConversationRecord) -> ConversationView:
        return cls(
            id=record.id,
            project_id=record.current_project_id,
            origin_project_id=record.project_id,
            title=record.title,
            started_at=record.started_at,
            last_message_at=record.last_message_at,
            archived=record.archived_at is not None,
            removed=record.removed_at is not None,
        )


class RevisionView(BaseModel):
    """One appended revision or retraction fact — ruling, 12 September 2026."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    message_id: UUID
    revision_number: int
    kind: str
    content: str | None
    note: str | None
    authored_by: str
    created_at: datetime

    @classmethod
    def of(cls, record: MessageRevisionRecord) -> RevisionView:
        return cls(
            id=record.id,
            message_id=record.message_id,
            revision_number=record.revision_number,
            kind=record.kind.value,
            content=record.content,
            note=record.note,
            authored_by=record.authored_by,
            created_at=record.created_at,
        )


#: What the detail says when a message cannot be rewritten (ruling, 12 September 2026).
DELIBERATED_REVISION_REFUSAL = (
    "This message is part of a recorded decision exchange and cannot be rewritten. "
    "Send a correction as a new message, or remove the exchange from the conversation."
)


class AttachmentInput(BaseModel):
    """One image offered with a turn: the bytes, the name, and what is said of it.

    Owner ruling, 19 September 2026 (Track C §13). Deliberately provider-neutral:
    base64 rather than any provider's own image syntax, and a `classification`
    the sender states per act. Nothing here is trusted about the content — the
    media type is established from the bytes by the admission preflight, and the
    filename is display only.
    """

    model_config = ConfigDict(frozen=True)

    filename: str = Field(min_length=1)
    content_base64: str = Field(min_length=1)
    #: Per act, defaulting to the strictest ordinary class. `restricted` is not
    #: a value: it is refused at the act (Attachment Substrate v1.2 §3.3).
    classification: Literal["public", "internal", "protected"] = "protected"


class SpeechView(BaseModel):
    """One generated utterance, as a client needs to play and cite it.

    Owner execution order, 22 September 2026. The client gets the digest rather
    than a path: the bytes are fetched by their own content address, exactly as
    an attachment's are, so nothing here makes Val's voice addressable to
    anything outside this machine.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    voice_id: UUID
    #: The content-addressed key the waveform is fetched by.
    audio_sha256: str
    sample_rate: int
    duration_seconds: float
    #: The reusable voice conditioning this utterance was anchored to. Equal
    #: across utterances is what says the voice did not drift between them.
    clone_prompt_sha256: str
    local: bool
    cost_usd: float

    @classmethod
    def of(cls, spoken: SpokenText) -> SpeechView:
        return cls(
            id=spoken.generation_id,
            voice_id=spoken.voice_id,
            audio_sha256=spoken.audio_sha256,
            sample_rate=spoken.sample_rate,
            duration_seconds=spoken.duration_seconds,
            clone_prompt_sha256=spoken.clone_prompt_sha256,
            local=spoken.local,
            cost_usd=spoken.cost_usd,
        )


class AttachmentView(BaseModel):
    """One committed attachment act, as a client needs to render and refetch it."""

    model_config = ConfigDict(frozen=True)

    #: The act. Re-using the same file on a later turn is a different act over
    #: the same content, so this is what identifies *this* association.
    id: UUID
    attachment_id: UUID
    position: int
    filename: str
    classification: str
    media_type: str
    width: int
    height: int
    byte_size: int
    #: Owner execution order, 22 September 2026: what kind of medium this is —
    #: `image`, `video` or `audio` — established from the bytes at admission.
    #: The interface renders from this rather than guessing from the filename.
    modality: str = "image"
    #: How long it runs. `None` for a still image, and `None` for a video whose
    #: container did not state one.
    duration_seconds: float | None = None
    #: The content-addressed key the bytes are fetched by.
    sha256: str

    @classmethod
    def of(cls, act: AttachmentAct) -> AttachmentView:
        return cls(
            id=act.act_id,
            attachment_id=act.attachment_id,
            position=act.position,
            filename=act.given_filename,
            classification=act.stated_classification.value,
            media_type=act.media_type,
            width=act.width,
            height=act.height,
            byte_size=act.byte_size,
            modality=act.modality,
            duration_seconds=act.duration_seconds,
            sha256=act.sha256,
        )


class MessageView(BaseModel):
    """One message. In a conversation detail, `content` is the wording in force.

    Ruling, 12 September 2026, additive: `state` is `current`, `corrected` or
    `withdrawn`; `original_content` is what Lord Armand first sent, present when
    the wording in force differs; `answered_state` is, for a Val message, the
    state of the message she immediately answered — her words stay attached to
    the wording she received; `revisions` lists the appended facts;
    `revision_refusal` says why a message cannot be rewritten. A message outside
    a detail (a turn's own messages) carries the defaults, which are true of it.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    role: str
    content: str
    sequence: int
    created_at: datetime
    state: str = "current"
    original_content: str | None = None
    answered_state: str | None = None
    revisions: list[RevisionView] = Field(default_factory=list)
    revision_refusal: str | None = None
    #: Owner ruling, 19 September 2026: the attachment acts of this message, in
    #: the order they were attached. Empty on every message that carries none,
    #: which is every message the house held before today.
    attachments: list[AttachmentView] = Field(default_factory=list)

    @classmethod
    def of(cls, record: MessageRecord) -> MessageView:
        return cls(
            id=record.id,
            role=record.role.value,
            content=record.content,
            sequence=record.sequence,
            created_at=record.created_at,
        )

    @classmethod
    def of_working(
        cls,
        message: WorkingMessage,
        *,
        deliberated: bool,
        attachments: tuple[AttachmentAct, ...] = (),
    ) -> MessageView:
        record = message.record
        return cls(
            id=record.id,
            role=record.role.value,
            content=message.content,
            sequence=record.sequence,
            created_at=record.created_at,
            state=message.state.value,
            original_content=record.content if message.content != record.content else None,
            answered_state=None if message.answered_state is None else message.answered_state.value,
            revisions=[RevisionView.of(fact) for fact in message.revisions],
            revision_refusal=(
                DELIBERATED_REVISION_REFUSAL
                if deliberated and record.role is StoredRole.USER
                else None
            ),
            attachments=[AttachmentView.of(act) for act in attachments],
        )


class RevisionRequest(BaseModel):
    """A corrected wording for one of Lord Armand's messages. The note is optional."""

    model_config = ConfigDict(frozen=True)

    content: str
    note: str | None = None


class RetractionRequest(BaseModel):
    """Remove one of Lord Armand's messages from the conversation. The note is optional."""

    model_config = ConfigDict(frozen=True)

    note: str | None = None


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


class ClassificationView(BaseModel):
    """A turn's classification as recorded — ruling, 3 September 2026.

    `verdict` and `hard_exclusion` are the classifier's declared reason,
    verbatim from the row; `established` False means no verdict was stated in
    any permitted attempt and `resolution` says why. Nothing here is derived.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    message_id: UUID
    established: bool
    verdict: ClassificationVerdict | None
    hard_exclusion: str | None
    attempts: int
    model_call_ids: list[UUID]
    resolving_model_call_id: UUID | None
    resolution: str | None
    created_at: datetime

    @classmethod
    def of(cls, record: ClassificationRecord) -> ClassificationView:
        return cls(
            id=record.id,
            message_id=record.message_id,
            established=record.established,
            verdict=record.verdict,
            hard_exclusion=record.hard_exclusion,
            attempts=record.attempts,
            model_call_ids=list(record.model_call_ids),
            resolving_model_call_id=record.resolving_model_call_id,
            resolution=record.resolution,
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
    #: Ruling, 12 September 2026: every explicit move, in order. A message with
    #: sequence above a move's `after_sequence` (until the next) was written in
    #: that move's destination.
    scope_transitions: list[ScopeTransitionView] = Field(default_factory=list)
    #: Ruling, 3 September 2026: how each turn was classified, from the
    #: evidence record, so the answer is readable here and not only in SQL.
    classifications: list[ClassificationView]
    blind_positions: list[BlindPositionView]
    deliberations: list[DeliberationView]
    execution_events: list[ExecutionEventView]


# =============================================================================
# Classification review — ruling, 7 September 2026
# =============================================================================


class QueuedExchangeView(BaseModel):
    """One exchange awaiting Lord Armand's label. **Carries no verdict.**

    The queue is blind by construction: the service does not send the
    classifier's verdict or hard exclusion until the label is durably stored,
    the same doctrine as the blind position, applied to him.
    """

    model_config = ConfigDict(frozen=True)

    classification_id: UUID
    conversation_id: UUID
    conversation_title: str
    message_id: UUID
    content: str
    classified_at: datetime

    @classmethod
    def of(cls, item: QueuedExchange) -> QueuedExchangeView:
        return cls(
            classification_id=item.classification_id,
            conversation_id=item.conversation_id,
            conversation_title=item.conversation_title,
            message_id=item.message_id,
            content=item.content,
            classified_at=item.classified_at,
        )


class LabelRequest(BaseModel):
    """The original blind label. `exclusion_determination` is required for
    not_consequential — one of the six, or the explicit
    `none_fails_inclusion_test` — and forbidden otherwise. Omitted is refused,
    never read as none."""

    model_config = ConfigDict(frozen=True)

    classification_id: UUID
    label: HumanClassification
    exclusion_determination: str | None = None


class ClassificationLabelView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    label: HumanClassification
    exclusion_determination: str | None
    labelled_by: str
    created_at: datetime

    @classmethod
    def of(cls, record: ClassificationLabelRecord) -> ClassificationLabelView:
        return cls(
            id=record.id,
            label=record.label,
            exclusion_determination=record.exclusion_determination,
            labelled_by=record.labelled_by,
            created_at=record.created_at,
        )


class ClassificationReviewView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    conclusion: ReviewConclusion
    reason: str
    tuning_state: TuningState | None
    tuning_change: str | None
    tuning_verification: str | None
    created_at: datetime

    @classmethod
    def of(cls, record: ClassificationReviewRecord) -> ClassificationReviewView:
        return cls(
            id=record.id,
            conclusion=record.conclusion,
            reason=record.reason,
            tuning_state=record.tuning_state,
            tuning_change=record.tuning_change,
            tuning_verification=record.tuning_verification,
            created_at=record.created_at,
        )


class LabelledExchangeView(BaseModel):
    """A labelled exchange with the verdict revealed and agreement derived on read."""

    model_config = ConfigDict(frozen=True)

    classification_id: UUID
    conversation_id: UUID
    conversation_title: str
    message_id: UUID
    content: str
    label: ClassificationLabelView
    verdict: ClassificationVerdict
    hard_exclusion: str | None
    agreement: Agreement
    open_disagreement: bool
    reviews: list[ClassificationReviewView]

    @classmethod
    def of(cls, item: LabelledExchange) -> LabelledExchangeView:
        return cls(
            classification_id=item.classification_id,
            conversation_id=item.conversation_id,
            conversation_title=item.conversation_title,
            message_id=item.message_id,
            content=item.content,
            label=ClassificationLabelView.of(item.label),
            verdict=item.verdict,
            hard_exclusion=item.hard_exclusion,
            agreement=item.agreement,
            open_disagreement=item.open_disagreement,
            reviews=[ClassificationReviewView.of(review) for review in item.reviews],
        )


class ReviewRequest(BaseModel):
    """An adjudication after the reveal, appended, with its stated reason."""

    model_config = ConfigDict(frozen=True)

    classification_id: UUID
    conclusion: ReviewConclusion
    reason: str = Field(min_length=1)
    tuning_state: TuningState | None = None
    tuning_change: str | None = None
    tuning_verification: str | None = None


class ReviewProgressView(BaseModel):
    model_config = ConfigDict(frozen=True)

    labelled: int
    target: int
    agreements: int
    inclusion_disagreements: int
    zero_tolerance_failures: int
    open_disagreements: int
    eligible_unlabelled: int

    @classmethod
    def of(cls, item: ReviewProgress) -> ReviewProgressView:
        return cls(
            labelled=item.labelled,
            target=item.target,
            agreements=item.agreements,
            inclusion_disagreements=item.inclusion_disagreements,
            zero_tolerance_failures=item.zero_tolerance_failures,
            open_disagreements=item.open_disagreements,
            eligible_unlabelled=item.eligible_unlabelled,
        )


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
    #: Ruling, 15 September 2026: the final conversation call's default ceiling
    #: is the policy's, 6,144 total output tokens (reasoning and visible text
    #: share it on a reasoning route). A client may still state its own.
    max_output_tokens: int = Field(default=CONVERSATION_MAX_OUTPUT_TOKENS, gt=0)
    #: Owner ruling, 19 September 2026: images attached to THIS turn. They are
    #: admitted before anything is written, and bound to this turn's calls only.
    attachments: list[AttachmentInput] = Field(default_factory=list)
    #: Ruling, 13 September 2026: on the streamed route, also send `stage`
    #: events as the house begins each stage of the turn. Opt-in, so the stream
    #: a client did not ask to change is unchanged. Ignored by `POST /turns`.
    progress: bool = False


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


# =============================================================================
# Live voice input — Voice mode work package 1, 23 September 2026
# =============================================================================


class VoiceSessionRequest(BaseModel):
    """Open a session for listening, on a conversation or on a new one.

    A voice session is an input modality attached to a conversation, never a
    second conversation. Omitting `conversation_id` is how a new chat begins: the
    conversation is created by the first spoken turn itself, exactly as a typed
    one is, and the session attaches to it then.
    """

    model_config = ConfigDict(frozen=True)

    conversation_id: UUID | None = None
    project: str | None = None
    no_project: bool = False


class VoiceTurnView(BaseModel):
    """One canonical owner turn that arrived by voice.

    `text` is the settled transcription that became the message — never a guess.
    `revised_to` is present only when the owner resumed before delivery and the
    wording was corrected through the append-only revision machinery.
    """

    model_config = ConfigDict(frozen=True)

    message_id: UUID
    conversation_id: UUID
    text: str
    utterance: int
    endpoint_reason: str
    provisional_events: int
    merged_from: list[int]
    revised_to: str | None
    merge_refused: str | None
    #: True once audible delivery of this answer has begun (work package 2 §12).
    delivered: bool
    #: What delivery did, from the record, when this answer was spoken at all.
    delivery: DeliveryView | None = None
    #: The answer, in the same shape `POST /turns` returns, so a caller has one
    #: way to read a turn whether it was typed or spoken.
    answer: TurnResponse


class VoiceSessionView(BaseModel):
    """What a session is doing, for the desktop to poll.

    `provisional` and `turns` are separate fields on purpose. A provisional
    transcript is mutable working state and **not a message**: it is here to be
    shown as the owner speaks and to be superseded. A caller that renders it as
    conversation has to have chosen to.
    """

    model_config = ConfigDict(frozen=True)

    session: UUID
    voice_session_id: UUID | None
    conversation_id: UUID | None
    state: str
    utterance: int
    #: The rolling guess. Never history, never recall, never Partner context.
    provisional: str
    hearing: bool
    #: A settled utterance waiting out the resume window, or in flight.
    pending: str
    turns: list[VoiceTurnView]
    error: str | None
    recognizer: dict[str, str]
    endpoint: dict[str, float]
    #: Present while Val is speaking an answer, absent otherwise.
    delivery: LiveDeliveryView | None = None
    #: Every barge-in this session performed, in milliseconds, service-side.
    cancellations_ms: list[float] = Field(default_factory=list)


class DeliveryView(BaseModel):
    """What speech delivery actually did for one answer.

    From the append-only record, newest event first. `delivered_prefix` is exactly
    what the owner heard — never the whole answer, and never a guess at where he
    stopped listening.
    """

    model_config = ConfigDict(frozen=True)

    message_id: UUID
    state: Literal["not_started", "started", "completed", "interrupted", "failed"]
    delivered_prefix: str
    delivered_characters: int
    segments_delivered: int
    segments_total: int | None
    reason: str | None
    events: int


class LiveDeliveryView(BaseModel):
    """Speech delivery for the answer being spoken now, as the session sees it."""

    model_config = ConfigDict(frozen=True)

    state: str
    #: True from the **first** piece of audio, which is the delivered boundary:
    #: after it, new owner speech is a fresh turn rather than a continuation.
    audible: bool
    active: bool
    segments_delivered: int
    delivered_characters: int
    #: Service-side only: from the recognizer's speech_start reaching delivery
    #: control to the sink stopping. **Not** a claim about when a physical speaker
    #: falls silent, which needs the speakers and belongs to work package 3.
    cancellation_ms: float | None


class SpokenAudioView(BaseModel):
    """One synthesised segment on its way to the Mac's speakers.

    Owner execution order, 24 September 2026 (§11). The audio travels as base64
    inside this object rather than as a bare body, because the desktop needs the
    segment's identity and its exact text with the bytes: it reports playback
    against the index, and the text is what the record says was spoken.

    **Ephemeral.** The service held these bytes only until this response was
    written, and holds nothing afterwards. There is no path to fetch them again.
    """

    model_config = ConfigDict(frozen=True)

    message_id: UUID
    segment_index: int
    #: Exactly the text this audio speaks — a contiguous slice of Val's visible
    #: answer, never a paraphrase of it.
    text: str
    audio_format: str
    sample_rate: int
    duration_seconds: float
    audio_bytes: int
    #: The waveform, base64-encoded for transport over the existing loopback JSON
    #: contract. Not stored at either end beyond playing it.
    audio_base64: str


class SpeechOfferView(BaseModel):
    """What the desktop should do about speech right now — one poll, two questions.

    Owner execution order, 24 September 2026 (§11, §12). A desktop that asked only
    "is a segment waiting?" would learn about an interruption one poll too late and
    keep a buffer sounding after Val had been told to stop. So the same answer
    carries the instruction to stop.

    `stop` is true when delivery was interrupted, failed, or is no longer active
    with audio still unplayed. It means **halt the buffer now and discard the
    queue**, which is the physical half of barge-in.
    """

    model_config = ConfigDict(frozen=True)

    #: `not_started`, `started`, `completed`, `interrupted`, `failed`, or `none`
    #: when no answer is being delivered at all.
    delivery_state: str
    stop: bool
    #: Why, when `stop` is true. Carried so the desktop can record the same reason
    #: the house recorded.
    reason: str | None = None
    segment: SpokenAudioView | None = None


class PlaybackReport(BaseModel):
    """What the desktop's output device actually did with one segment."""

    model_config = ConfigDict(frozen=True)

    message_id: UUID
    segment_index: int
    #: `playback_started`, `playback_completed`, `playback_interrupted` or
    #: `playback_failed`. `available_to_desktop` is the service's own to record and
    #: is refused here: a desktop cannot report that the service handed it something.
    state: str
    #: Milliseconds from the desktop collecting the segment to this state.
    elapsed_ms: int | None = None
    reason: str | None = None


class PlaybackEventView(BaseModel):
    """One physical-playback transition, from the append-only record."""

    model_config = ConfigDict(frozen=True)

    segment_index: int
    event: int
    state: str
    text: str
    elapsed_ms: int | None
    reason: str | None


class AdoptedFragmentRequest(BaseModel):
    """A guess a restart found open, which the owner has chosen to adopt.

    Owner execution order, 24 September 2026 (§2.1's third route to canonical).
    The words are the owner's own, offered back to him as a guess and adopted
    deliberately — never promoted by the house. They are live-microphone-derived
    text, so adopting them applies the conversation's local-only seal in the same
    transaction as the message they become.
    """

    model_config = ConfigDict(frozen=True)

    conversation_id: UUID
    content: str


class InterruptedUtteranceView(BaseModel):
    """A guess a crash left open. **Provisional, and labelled so.**

    Offered back as the words the recognizer had reached, never as something the
    owner said. Nothing submits it and nothing acts on it.
    """

    model_config = ConfigDict(frozen=True)

    voice_session_id: UUID
    conversation_id: UUID
    utterance: int
    provisional_text: str
    state: Literal["interrupted"] = "interrupted"
