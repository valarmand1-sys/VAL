"""The authoritative store's schema, exactly as `04-layer-0.md` §2 specifies it.

Fourteen tables, in §2's order — seven from the original §2, two added by the
15 August 2026 amendments (`execution_events.reaction` and the idea tables of
§2.4), `budget_reservations` added by the 17 August 2026 amendment (§2.5),
`blind_positions` by the 19 August 2026 ruling, `classifications` by the
3 September 2026 ruling, and `classification_labels` and
`classification_reviews` by the 7 September 2026 ruling (§2.2).
No table exists here that §2 does not name, and no column exists that §2 does
not list. Where §2 is silent, the silence is recorded in a comment rather than
filled in.

Two conventions applied throughout, both following from §2 rather than added to it:

- **NOT NULL is the default.** §2 marks specific columns nullable — `project_id`
  on conversations and model_calls, `reason`, `what_changed_her_mind`,
  `both_positions`, `predictions`. That marking means nothing unless everything
  else is required.
- **Nothing cascades and nothing deletes.** §2.3 requires that execution_events
  and deliberations outlive the conversation that produced them, and that no
  table permits hard delete at Layer 0. Foreign keys therefore use NO ACTION, and
  a trigger refuses DELETE and TRUNCATE on every table (see the migration).

`reason_source` and `ordering` carry no default. A record that cannot distinguish
a reason Lord Armand stated from one Val inferred, or a blind position from a
contaminated one, is worse than no record, because it looks like evidence. The
writer must state them; the database will not guess.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Named constraints so that a migration can drop what it created, by name, in
# either direction. The `ck` entry wraps whatever name a CheckConstraint is
# given, so check constraints are declared with the short half only — writing the
# full name would produce `ck_<table>_ck_<table>_...`.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base carrying the naming convention."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# --- Attachment Substrate v1.2 (19 September 2026) ---------------------------
#
# `restricted` is deliberately absent: §3.3 refuses it *at the act*, and a value
# that cannot be written is stronger than a rule saying it must not be.
AttachmentActClassification = Enum(
    "public", "internal", "protected", name="attachment_act_classification"
)
AttachmentProcessingEventType = Enum(
    "started", "succeeded", "failed", name="attachment_processing_event"
)
#: §3.6 — explicit discrimination, so no reader has to interpret a NULL.
ModelCallImageInputKind = Enum("original", "representation", name="model_call_image_input_kind")


# --- enumerated types --------------------------------------------------------
#
# Every value here is one §2 names. None is invented, and none carries a default.

MessageRole = Enum("user", "val", "system", name="message_role")
ModelCallTaskType = Enum(
    "conversation",
    "classification",
    "strip",
    "blind_position",
    "title",
    name="model_call_task_type",
)
ModelCallStatus = Enum("ok", "error", "refused", name="model_call_status")
# Owner ruling, 22 September 2026 — local visual perception (migration 0025).
# `audio` is deliberately absent: not qualified, not admitted, and a value that
# cannot be written is stronger than a rule saying it must not be.
# `audio` joined on 22 September 2026 (migration 0026), when an admitted provider
# could finally hear. A member here is a modality some specialist perceives.
PerceptionModality = Enum("image", "video", "audio", name="perception_modality")
# How the cognition provider was told to treat the current turn's media.
# `bound` keeps its Track C meaning exactly — raw media supplied directly to the
# cognition provider — and every historical row keeps it too.
PerceptionState = Enum("perceived", "bound", name="perception_state")
# §2.2 amendment, 17 August 2026. A provider attempt has three accounting
# outcomes and only two of them are rows: NOT_SENT writes nothing at all, because
# no call occurred. `known` and `unknown` distinguish the other two, and `unknown`
# is the reason `cost` may be NULL — a call that reached the provider consumed
# input tokens, so recording zero would be recording a figure that is known to be
# false rather than one that is merely unknown.
ModelCallCostCertainty = Enum("known", "unknown", name="model_call_cost_certainty")
# Independent-review correction, 18 August 2026 (migration `0010`). How the
# provider call actually ended, durably — `status` collapses TRUNCATED into
# `ok`, and the distinction decides whether the text was ever Val's utterance.
# NULL is reserved for rows that predate the contract; a trigger closes it to
# new rows, the same shape as `cost_certainty` and `project_attribution`.
ModelCallTerminalState = Enum(
    "complete",
    "refused",
    "truncated",
    "filtered",
    "unknown",
    "failed",
    name="model_call_terminal_state",
)
# §2.2 amendment, 18 August 2026, WP-0.6 corrective round. What a stored
# `project_id` *means*. A NULL alone cannot say whether somebody decided this
# exchange was outside every project or whether the row simply predates the
# distinction — and both exist in this table.
ModelCallProjectAttribution = Enum(
    "resolved", "explicit_none", "legacy_unknown", name="model_call_project_attribution"
)
# §2.5 amendment, 17 August 2026. The lifecycle of one budget reservation.
BudgetReservationState = Enum(
    "reserved", "settled", "released", "expired", name="budget_reservation_state"
)
ExecutionEventType = Enum(
    "accepted", "rejected", "revision_requested", "corrected", name="execution_event_type"
)
ExecutionEventReaction = Enum(
    "negative",
    "neutral",
    "interested",
    "enthusiastic",
    "strongly_enthusiastic",
    name="execution_event_reaction",
)
IdeaLifecycleState = Enum(
    "mentioned",
    "discussed",
    "researching",
    "prototyped",
    "approved",
    "implemented",
    "superseded",
    "rejected",
    "abandoned",
    name="idea_lifecycle_state",
)
ReasonSource = Enum("stated", "inferred", "absent", name="reason_source")
DeliberationConfidence = Enum("high", "medium", "low", name="deliberation_confidence")
DeliberationOrdering = Enum("enforced", "contaminated", name="deliberation_ordering")
DeliberationOutcome = Enum(
    "updated", "held", "overridden", "agreed_from_start", name="deliberation_outcome"
)
DeliberationClassification = Enum("consequential", "uncertain", name="deliberation_classification")
DeliberationClassifiedBy = Enum("automatic", "user", "val", name="deliberation_classified_by")
# Ruling, 3 September 2026: the classifier's full declared vocabulary, so the
# classification evidence record can say "ordinary" as well as "captured".
ClassificationVerdict = Enum(
    "consequential", "uncertain", "not_consequential", name="classification_verdict"
)
# Ruling, 7 September 2026: Lord Armand's own verdict, the review conclusion,
# and the tuning state of a classifier-was-wrong conclusion.
HumanClassification = Enum(
    "consequential", "uncertain", "not_consequential", name="human_classification"
)
ReviewConclusion = Enum(
    "label_upheld_classifier_wrong",
    "classifier_upheld_label_wrong",
    "ambiguous_needs_ruling",
    name="review_conclusion",
)
TuningState = Enum("tuning_required", "tuning_verified", name="tuning_state")
# Ruling, 12 September 2026: a fact about one of Lord Armand's messages.
MessageRevisionKind = Enum("revision", "retraction", name="message_revision_kind")
ConversationRemovalKind = Enum("removed", "reinstated", name="conversation_removal_kind")


# Primary keys are time-ordered UUIDs. PostgreSQL 18's `uuidv7()` sorts by
# creation time, which keeps insertion local and makes the Layer 3 relocation
# (`01-architecture.md` §9.4) a merge of globally unique keys rather than a
# renumbering.


# --- §2.1 Core ---------------------------------------------------------------


class Project(Base):
    """§2.1 — `projects`."""

    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # §2 names `status` but does not enumerate its values, so this is text rather
    # than an invented vocabulary. Surfaced, not filled in.
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    # Presentation scoping only — hidden from default listings, nothing more.
    # Lifecycle-class and mutable, like `title` on conversations. NEVER
    # evidentiary: the first rows marked are cited gate evidence (§2.1
    # amendment, 31 August 2026; migration 0012).
    archived_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("slug", name="uq_projects_slug"),)


class Conversation(Base):
    """§2.1 — `conversations`.

    `project_id` is nullable because "no project" is a real, explicit state and
    not a null accident (§2.1).

    **A NULL here means an explicit no-project decision, and WP-0.7 is what
    makes that true rather than merely convenient.** `model_calls` needed a
    `project_attribution` column because its NULLs were not all decisions — nine
    rows predated the distinction and no rule could separate them afterwards.
    `conversations` had **zero rows** when WP-0.7 began, so the clean set starts
    at the first row, and the only writer — `val_gateway.conversations.create` —
    takes a `ProjectScope`. `AmbiguousProject` is not of that type, so a
    conversation cannot be created without scope having been settled first.

    **No attribution column, and that is now a demonstrated choice rather than a
    deferral.** One was not added because the ambiguity `0006` had to repair
    never arose here: there is no historical set to disambiguate, and every NULL
    from the first row onward is a decision by construction. Adding a column to
    record a distinction that cannot occur would be machinery for its own sake.

    `last_message_at` is metadata, never the ordering authority. `sequence` on
    `messages` is the order (WP-0.7 §6); this is kept transactionally consistent
    with append so it never points earlier than the newest committed message.
    """

    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="NO ACTION"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    last_message_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    # Presentation scoping only; see the same column on Project. An archived
    # conversation still resumes, still recalls, and is still evidence.
    archived_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        # WP-0.7 retrieval filters by project *inside* the query, before ranking.
        # This index is what makes the correct order the cheap one — without it,
        # scoping to a project meant scanning every conversation in the house.
        Index("ix_conversations_project_id", "project_id"),
    )
    # Scope immutability is a trigger, not a constraint: the rule is about the
    # transition (`project_id` may not change), and a check constraint cannot see
    # what the row held before. See migration `0008`.


class Message(Base):
    """§2.1 — `messages`. Every message resolves to a conversation (§2.3)."""

    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="NO ACTION"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(MessageRole, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        # Ordering that is stable and gapless under concurrent writes is WP-0.7's
        # criterion; uniqueness per conversation is what makes it provable.
        UniqueConstraint(
            "conversation_id", "sequence", name="uq_messages_conversation_id_sequence"
        ),
        CheckConstraint("sequence > 0", name="sequence_positive"),
        # WP-0.7 recall. A GIN index over the same expression the retrieval query
        # uses; `english` is named rather than inherited because an index
        # expression must be immutable (migration `0008`).
        Index(
            "ix_messages_content_fts",
            text("to_tsvector('english', content)"),
            postgresql_using="gin",
        ),
    )


class Persona(Base):
    """§2.1 — `personas`. Editing creates a version; it never mutates a row.

    **Two version scales, deliberately separate** (§2.1 clarification, 17 August
    2026, and the executive decision of 17 August authorising WP-0.5):

    - `version` is the **persistence revision** — `1`, `2`, `3`, … It counts rows.
    - `semantic_version` is the **authored label** — `1.2`. It counts authorship.

    They are not the same measurement and neither may stand in for the other. The
    row seeded from the v1.2 document is persistence revision `1`, and an
    interface showing "Persona v1" over it would display a state the record does
    not support (invariant 29).

    **What is immutable, and what may move.** Content, identity, the authored
    label, and the provenance of the document it came from are fixed at
    insertion; a `BEFORE UPDATE` trigger refuses to change any of them (see the
    migration). `is_active` and `activated_at` are lifecycle state and may
    change, because which persona is live is a different fact from what any
    persona says.
    """

    __tablename__ = "personas"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    #: The persistence revision. Monotonic, immutable, and never renumbered.
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The authored label the document carries, canonicalised without its "v" —
    #: `1.2`, not `v1.2`. NOT NULL: a row that cannot say which authored version
    #: it holds is the ambiguity this column exists to remove.
    semantic_version: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    #: SHA-256 of the exact bytes of the governing document this row was seeded
    #: from, and the repository-relative path it was read from. The path is
    #: relative deliberately — an absolute path is a fact about one machine, and
    #: making it authoritative would make the record unverifiable anywhere else.
    source_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    #: When the row was written. Distinct from `activated_at`, which moves.
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: Nullable since WP-0.5: NULL means *this revision has never been active*.
    #: A revision created but not yet activated carries no activation instant,
    #: and inventing one would put a time in the record for an event that never
    #: happened.
    activated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    authored_by: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("version", name="uq_personas_version"),
        # WP-0.5 loads "the active personas row", singular. At most one may be it.
        Index(
            "uq_personas_single_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        CheckConstraint("version > 0", name="version_positive"),
        # The authored label, canonical: digits and dots, no leading "v". Parsing
        # it out of the document is deterministic; storing it loosely would undo
        # that at the last step.
        CheckConstraint(
            r"semantic_version ~ '^[0-9]+(\.[0-9]+)*$'",
            name="semantic_version_is_canonical",
        ),
        CheckConstraint("source_sha256 ~ '^[0-9a-f]{64}$'", name="source_sha256_is_a_digest"),
        # An active revision has been activated. The converse does not hold: a
        # revision that was active and is not still carries the instant it was.
        CheckConstraint(
            "NOT is_active OR activated_at IS NOT NULL",
            name="active_requires_activated_at",
        ),
    )


# --- §2.2 Capture ------------------------------------------------------------
#
# These three tables are the point of the layer. They feed machinery that does
# not exist until Layers 3 and 5, and they cannot be backfilled.


class ModelCall(Base):
    """§2.2 — `model_calls`. Per-call cost attribution."""

    __tablename__ = "model_calls"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    # §2 requires "the configuration, not a bare model string". §2 names no
    # configuration table, so this carries no foreign key at Layer 0. The Model
    # Configuration Registry arrives at WP-0.4 (01-architecture.md §5.2), and
    # adding the reference is a migration at that point.
    model_config_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    # Denormalised deliberately — a retired config must still resolve historically.
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model_identifier: Mapped[str] = mapped_column(Text, nullable=False)
    # Nullable since the 17 August 2026 amendment, and NULL means exactly one
    # thing: the provider was contacted and did not tell us. See `cost_certainty`.
    tokens_in: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Stored, not derived. Provider pricing changes, and a historical record that
    # silently re-prices itself is not a record.
    cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
    # `known` | `unknown`, or NULL on a row written before 17 August 2026, when
    # the distinction did not exist. NULL is not a third state; it is an absence
    # of one, and it is left rather than backfilled because guessing which of the
    # two an old row deserves would be inventing evidence (the 0002 precedent).
    cost_certainty: Mapped[str | None] = mapped_column(ModelCallCostCertainty, nullable=True)
    terminal_state: Mapped[str | None] = mapped_column(ModelCallTerminalState, nullable=True)
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="NO ACTION"), nullable=True
    )
    # WP-0.6 corrective round. `resolved` | `explicit_none` | `legacy_unknown`,
    # and the third is reserved to rows written before 18 August 2026 — a check
    # constraint refuses it on anything newer, so it cannot become the way new
    # code avoids deciding scope.
    project_attribution: Mapped[str] = mapped_column(ModelCallProjectAttribution, nullable=False)
    task_type: Mapped[str] = mapped_column(ModelCallTaskType, nullable=False)
    conversation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="NO ACTION"), nullable=True
    )
    message_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="NO ACTION"), nullable=True
    )
    # WP-0.5. Which persona revision was assembled into this call's context.
    # A stable reference rather than a copy of the content: the persona is
    # immutable once stored, so the reference resolves to exactly the text that
    # was sent, and later activating a different revision cannot rewrite it.
    #
    # Nullable for two honest reasons, not one lazy one: rows written before
    # WP-0.5 carry no persona, and a call on a path that legitimately assembles
    # none — classification, strip, a title — is not a call to attribute.
    # 19 August 2026: blind_position calls carry the persona and attribute it;
    # once a persona is assembled, NULL would mean "assembled and failed to
    # attribute" — a false record, not a missing feature.
    persona_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("personas.id", ondelete="NO ACTION"), nullable=True
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_request_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(ModelCallStatus, nullable=False)

    __table_args__ = (
        CheckConstraint("tokens_in >= 0", name="tokens_in_non_negative"),
        CheckConstraint("tokens_out >= 0", name="tokens_out_non_negative"),
        CheckConstraint("cost >= 0", name="cost_non_negative"),
        CheckConstraint("latency_ms >= 0", name="latency_ms_non_negative"),
        # `known` must carry figures, `unknown` must not. Without both halves the
        # column would be a label rather than a guarantee: an `unknown` row
        # carrying a zero cost is exactly the false factual zero this amendment
        # exists to make unwritable.
        CheckConstraint(
            "cost_certainty <> 'known' OR "
            "(cost IS NOT NULL AND tokens_in IS NOT NULL AND tokens_out IS NOT NULL) OR "
            # Ruling, 16 September 2026 (`0022`): an unmetered LOCAL provider's
            # monetary cost is a known $0 whether or not the runtime reported
            # tokens; the provider is named so every metered provider keeps the
            # original guard against a fabricated zero.
            # Owner ruling, 18 September 2026 (`0023`): the second ruled LOCAL
            # provider joins the clause by name; metered providers are untouched.
            "(cost = 0 AND provider IN ('lmstudio', 'llamacpp'))",
            name="known_cost_is_recorded",
        ),
        CheckConstraint(
            "cost_certainty <> 'unknown' OR "
            "(cost IS NULL AND tokens_in IS NULL AND tokens_out IS NULL)",
            name="unknown_cost_is_not_a_zero",
        ),
        # §2.2 amendment, 17 August 2026. No row written from that date may leave
        # its cost certainty unstated. This is what makes a NULL `cost_certainty`
        # mean exactly one thing — *written before the distinction existed* — and
        # keeps it meaning that permanently. Without it the rule that supersedes
        # the five fabricated zeroes of 15 August could silently widen to cover
        # rows it was never written for. See migration `0004_supersede_zero_costs`.
        CheckConstraint(
            "cost_certainty IS NOT NULL OR created_at < TIMESTAMPTZ '2026-08-17T00:00:00+00:00'",
            name="certainty_required_after_the_amendment",
        ),
        # WP-0.6 corrective round. The attribution and the id must agree, or the
        # row asserts something it cannot support.
        CheckConstraint(
            "(project_attribution = 'resolved') = (project_id IS NOT NULL)",
            name="resolved_attribution_has_a_project",
        ),
    )
    # `legacy_unknown` is reserved to history by a **trigger**, not a constraint
    # — see migration `0007_legacy_attribution_closed`. `0006` used a check on
    # `created_at`, which a direct writer controls: a row inserted today with a
    # backdated timestamp satisfied it. The rule being enforced is about the
    # *operation* — this value may persist but may not be acquired — and a check
    # constraint cannot see whether it is looking at an INSERT or an UPDATE.


class ExecutionEvent(Base):
    """§2.2 — `execution_events`. Every acceptance, rejection, revision, correction.

    Cascades on nothing. It outlives the conversation that produced it (§2.3).
    """

    __tablename__ = "execution_events"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    # Nullable to match `conversations.project_id`. §2 marks that column nullable
    # and marks `model_calls.project_id` "nullable, matching conversations", but
    # says nothing here. NOT NULL would make an event in a no-project
    # conversation unrecordable, and failing to capture is the one outcome Layer 0
    # cannot afford. Flagged for ruling.
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="NO ACTION"), nullable=True
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="NO ACTION"),
        nullable=False,
    )
    message_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="NO ACTION"), nullable=False
    )
    # Nullable since the 15 August 2026 amendment: a reaction with no event is a
    # real record. "He loved the idea" and "he approved the work" are different
    # facts, and conflating them poisons Layer 5 distillation with false
    # approvals.
    event_type: Mapped[str | None] = mapped_column(ExecutionEventType, nullable=True)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    # The reason, in Lord Armand's words where he gave one. Nullable, but a null
    # reason is a defect to be surfaced, not a normal state.
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # No default. A reason Val inferred and a reason Lord Armand stated are
    # different evidence, and Layer 5 must be able to weight them differently.
    reason_source: Mapped[str] = mapped_column(ReasonSource, nullable=False)
    # Never inferred from wording alone, and enthusiasm is never evidence of
    # approval (§2.2 amendment, 15 August 2026).
    reaction: Mapped[str | None] = mapped_column(ExecutionEventReaction, nullable=True)

    __table_args__ = (
        # The two fields cannot disagree. A stated reason that is absent, or an
        # absent reason that has text, would make the distinction untrustworthy
        # exactly where it is load-bearing.
        CheckConstraint(
            "(reason IS NULL) = (reason_source = 'absent')",
            name="reason_matches_source",
        ),
        # A row that says nothing is not a record. Reaction-only rows are the
        # point of the amendment; empty rows are noise wearing its shape.
        CheckConstraint(
            "event_type IS NOT NULL OR reaction IS NOT NULL",
            name="event_or_reaction_present",
        ),
    )


class BlindPosition(Base):
    """§2.2 — `blind_positions`, amendment of 19 August 2026.

    The blind position is the primary evidence that Val formed a genuinely
    independent judgment, and it exists before the exchange resolves — the
    `deliberations` row cannot be written until the outcome is known. It is
    therefore captured as an append-only evidence row, **persisted before step
    3 of `04-layer-0.md` §4 begins**: not mutable interim state, complete when
    written, no UPDATE, no hard delete (migration `0011`).

    Cascades on nothing. It outlives the conversation that produced it (§2.3).
    """

    __tablename__ = "blind_positions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    # Nullable for the same reason as on execution_events, above.
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="NO ACTION"), nullable=True
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="NO ACTION"),
        nullable=False,
    )
    message_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="NO ACTION"), nullable=False
    )
    # The blind call itself. NOT NULL: this row exists only because a recorded
    # call produced it, and evidence that cannot name its call is not evidence.
    model_call_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("model_calls.id", ondelete="NO ACTION"), nullable=False
    )
    # The persona revision assembled into the blind call — WP-0.5's 19 August
    # 2026 amendment: the position must be Val's position, so the call carries
    # her persona and attributes it.
    persona_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("personas.id", ondelete="NO ACTION"), nullable=False
    )
    position: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(DeliberationConfidence, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    stripped_content: Mapped[str] = mapped_column(Text, nullable=False)
    # No default, same as on deliberations: whether the position was genuinely
    # blind is the whole mechanism.
    ordering: Mapped[str] = mapped_column(DeliberationOrdering, nullable=False)
    classification: Mapped[str] = mapped_column(DeliberationClassification, nullable=False)
    classified_by: Mapped[str] = mapped_column(DeliberationClassifiedBy, nullable=False)


class Deliberation(Base):
    """§2.2 — `deliberations`, per `02-partner-systems.md` §4.7.

    Cascades on nothing. It outlives the conversation that produced it (§2.3).
    """

    __tablename__ = "deliberations"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    # Nullable for the same reason as on execution_events, above.
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="NO ACTION"), nullable=True
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="NO ACTION"),
        nullable=False,
    )
    message_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="NO ACTION"), nullable=False
    )
    position: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(DeliberationConfidence, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    stripped_content: Mapped[str] = mapped_column(Text, nullable=False)
    # No default. Whether the blind position was genuinely blind is the whole
    # mechanism; a contaminated position labelled clean is the failure the
    # ordering guarantee exists to prevent.
    ordering: Mapped[str] = mapped_column(DeliberationOrdering, nullable=False)
    user_response: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(DeliberationOutcome, nullable=False)
    what_changed_her_mind: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The seed of the prediction ledger. Populated on compromise.
    both_positions: Mapped[str | None] = mapped_column(Text, nullable=True)
    predictions: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification: Mapped[str] = mapped_column(DeliberationClassification, nullable=False)
    classified_by: Mapped[str] = mapped_column(DeliberationClassifiedBy, nullable=False)
    # 19 August 2026: the exact blind-position evidence this record resolves.
    # Nullable — a deliberation recorded manually, or one whose exchange
    # carried no preference to strip, has no blind call behind it.
    blind_position_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("blind_positions.id", ondelete="NO ACTION"),
        nullable=True,
    )

    __table_args__ = (
        # §2 states the rule: required when outcome = 'updated'.
        CheckConstraint(
            "outcome <> 'updated' OR what_changed_her_mind IS NOT NULL",
            name="updated_requires_what_changed_her_mind",
        ),
    )


class Classification(Base):
    """§2.2 — `classifications`, ruling of 3 September 2026.

    One row per turn's §4.8 classification, written when classification
    concludes — established or not — and before any strip or response call.
    It exists because the classifier's verdict and declared reason were never
    persisted and its calls carry no turn provenance (the 18 August rule,
    provenance iff conversation, is kept intact): the turn linkage lives here,
    and `model_calls` stays as it was. Append-only evidence like every other
    capture table: no UPDATE, no hard delete (migration `0013`).

    `verdict` and `hard_exclusion` are the classifier's declared structured
    reason, never inferred. `established` is False when every permitted
    attempt failed to state a verdict. `model_call_ids` names every
    classification call made for the turn, in order; the array may be empty
    when no attempt reached a provider (a pre-contact refusal writes no call).
    """

    __tablename__ = "classifications"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="NO ACTION"), nullable=True
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="NO ACTION"),
        nullable=False,
    )
    message_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="NO ACTION"), nullable=False
    )
    established: Mapped[bool] = mapped_column(Boolean, nullable=False)
    verdict: Mapped[str | None] = mapped_column(ClassificationVerdict, nullable=True)
    hard_exclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    model_call_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PG_UUID(as_uuid=True)), nullable=False)
    resolving_model_call_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("model_calls.id", ondelete="NO ACTION"), nullable=True
    )
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # A verdict exists exactly when the classification was established.
        CheckConstraint("established = (verdict IS NOT NULL)", name="established_iff_verdict"),
        CheckConstraint("attempts >= 1", name="classification_attempted_at_least_once"),
    )


class ClassificationLabel(Base):
    """§2.2 — `classification_labels`, ruling of 7 September 2026.

    One original blind hand-label per classification — Lord Armand's verdict
    under the §4.8 contract, committed before the classifier's verdict is
    revealed to him and never overwritten (migration `0014`). The evidence
    the fifty-exchange criterion collects. `exclusion_determination` is
    present iff the label is `not_consequential` and names one of the six
    hard exclusions or the explicit `none_fails_inclusion_test`; an omitted
    determination is refused by the writer, never read as "none".
    """

    __tablename__ = "classification_labels"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    classification_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("classifications.id", ondelete="NO ACTION"),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(HumanClassification, nullable=False)
    exclusion_determination: Mapped[str | None] = mapped_column(Text, nullable=True)
    labelled_by: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("classification_id", name="uq_classification_labels_classification_id"),
        CheckConstraint(
            "(label = 'not_consequential') = (exclusion_determination IS NOT NULL)",
            name="determination_iff_not_consequential",
        ),
    )


class ClassificationReview(Base):
    """§2.2 — `classification_reviews`, ruling of 7 September 2026.

    An adjudication appended after the reveal: what was concluded on comparing
    the label with the classifier, with a stated reason. A conclusion that
    the classifier was wrong carries a tuning state that starts
    `tuning_required` and is closed only by a later row citing the engineering
    change and its verification — never by viewing. Append-only (`0014`).
    """

    __tablename__ = "classification_reviews"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    classification_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("classifications.id", ondelete="NO ACTION"),
        nullable=False,
    )
    label_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("classification_labels.id", ondelete="NO ACTION"),
        nullable=False,
    )
    conclusion: Mapped[str] = mapped_column(ReviewConclusion, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    tuning_state: Mapped[str | None] = mapped_column(TuningState, nullable=True)
    tuning_change: Mapped[str | None] = mapped_column(Text, nullable=True)
    tuning_verification: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "(conclusion = 'label_upheld_classifier_wrong') = (tuning_state IS NOT NULL)",
            name="tuning_state_iff_classifier_wrong",
        ),
        CheckConstraint(
            "(tuning_state = 'tuning_verified') = "
            "(tuning_change IS NOT NULL AND tuning_verification IS NOT NULL)",
            name="verified_cites_change",
        ),
    )


# --- §2.4 Ideas — amendment, 15 August 2026 ----------------------------------
#
# An idea's history cannot be reconstructed later: the same capture argument as
# §2.2. Layer 0 records it with manual marking only — no automatic idea
# detection, no classification calls.


class Idea(Base):
    """§2.4 — `ideas`. `lifecycle_state` mirrors the newest lineage row.

    Two rules bind every writer and Layer 5 distillation: `implemented` is never
    inferred from discussion of how something might be built, and `approved` is
    never inferred from enthusiasm.
    """

    __tablename__ = "ideas"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="NO ACTION"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(IdeaLifecycleState, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class IdeaStateChange(Base):
    """§2.4 — `idea_state_changes`. Append-only lineage; history is the record."""

    __tablename__ = "idea_state_changes"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    idea_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("ideas.id", ondelete="NO ACTION"), nullable=False
    )
    # Null marks creation: the idea's first state has no predecessor.
    from_state: Mapped[str | None] = mapped_column(IdeaLifecycleState, nullable=True)
    to_state: Mapped[str] = mapped_column(IdeaLifecycleState, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        # A change that changes nothing is not lineage, it is noise.
        CheckConstraint(
            "from_state IS DISTINCT FROM to_state",
            name="state_change_changes_state",
        ),
    )


# --- §2.5 Budget reservations — amendment, 17 August 2026 --------------------
#
# The ceiling is enforced against the cost of the call being proposed, not
# against history (`01-architecture.md` §5.7 as amended). That requires an
# authoritative record of what is committed but not yet settled, and it requires
# it in PostgreSQL rather than in a process: two processes each holding their own
# counter both observe the same room and together breach the ceiling, and an
# in-memory lock protects nothing across `api` and `worker`.


class BudgetReservation(Base):
    """§2.5 — `budget_reservations`. One row per admitted call, cradle to grave.

    **Lifecycle**, and every transition is an UPDATE of `state` on an existing
    row rather than a new row, because the reservation is one fact changing
    state and not four facts:

    | State | Means | Counts against the ceiling |
    |---|---|---|
    | `reserved` | Admitted; the provider is being contacted | Yes, at `max_cost` |
    | `settled` | The attempt finished | Yes, at `settled_cost` |
    | `released` | No provider request occurred | No |
    | `expired` | The process died holding it | **Yes, at `max_cost`** |

    **Why `expired` still counts.** A reservation whose process vanished may or
    may not have reached the provider, and nothing on this machine can tell which.
    Freeing it would hand back money that may well have been spent — an unknown
    consequential outcome treated as a successful non-event, which
    `00-charter.md` §4 forbids in as many words. It stays committed, it is
    reported, and it clears when the month's ceiling resets. That bounds the
    damage of a crash to one month without ever silently increasing available
    spend, which is the pair of properties this state has to hold at once.

    **Why `settled_cost` may exceed `max_cost`.** It should never happen: the
    reserved figure is an upper bound computed from byte lengths, not an
    estimate. If it does, the row is written truthfully anyway — recording the
    real figure and leaving `max_cost < settled_cost` visible is the evidence.
    Clamping the record to the reservation would hide a breached ceiling behind a
    tidy number, which is the one outcome worse than the breach.
    """

    __tablename__ = "budget_reservations"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    #: When the row last changed state. Distinct from `created_at`, which is what
    #: the monthly window is measured against — a reservation belongs to the month
    #: it was admitted in, whatever month it happened to settle in.
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    state: Mapped[str] = mapped_column(BudgetReservationState, nullable=False)
    #: Which configuration the reservation was taken against, denormalised for
    #: the same reason `model_calls` denormalises: a retired configuration must
    #: still resolve historically.
    model_config_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model_identifier: Mapped[str] = mapped_column(Text, nullable=False)
    task_type: Mapped[str] = mapped_column(ModelCallTaskType, nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="NO ACTION"), nullable=True
    )
    #: The most this call was authorised to consume. The figure the ceiling was
    #: enforced against, kept so the decision can be re-examined afterwards.
    max_cost: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    #: What it actually consumed. NULL until settlement, and on an `unknown`-cost
    #: settlement this holds `max_cost` — the conservative charge — while
    #: `model_calls.cost` stays NULL. The two disagree deliberately: the ledger
    #: records what must be assumed spent, the call record records what is known.
    settled_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
    cost_certainty: Mapped[str | None] = mapped_column(ModelCallCostCertainty, nullable=True)
    #: The call this reservation paid for, once one exists. NULL on a released
    #: reservation, because no call was made.
    model_call_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("model_calls.id", ondelete="NO ACTION"), nullable=True
    )
    #: Why a reservation was released or expired, in words. Not nullable-by-
    #: laziness: a release with no stated reason is the shape a silent budget
    #: leak takes.
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Ruling, 13 September 2026 (`0020`): the user exchange this reservation
    #: belongs to — the conversation and the persisted user message — so every
    #: call an exchange caused can be summed against it. Both or neither; NULL
    #: for work that belongs to no exchange and for rows written before 0020.
    #: Identity: pinned by the reservation guard like the columns above.
    exchange_conversation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="NO ACTION"), nullable=True
    )
    exchange_message_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="NO ACTION"), nullable=True
    )

    __table_args__ = (
        CheckConstraint("max_cost >= 0", name="max_cost_non_negative"),
        CheckConstraint("settled_cost IS NULL OR settled_cost >= 0", name="settled_non_negative"),
        # Settled means settled: a figure and a certainty, both present, and
        # neither present in any other state.
        CheckConstraint(
            "(state = 'settled') = (settled_cost IS NOT NULL)",
            name="settled_has_a_cost",
        ),
        CheckConstraint(
            "(state = 'settled') = (cost_certainty IS NOT NULL)",
            name="settled_has_a_certainty",
        ),
        CheckConstraint(
            "state = 'reserved' OR resolution IS NOT NULL",
            name="resolved_states_say_why",
        ),
        CheckConstraint(
            "(exchange_conversation_id IS NULL) = (exchange_message_id IS NULL)",
            name="exchange_both_or_neither",
        ),
        Index("ix_budget_reservations_state_created_at", "state", "created_at"),
        Index("ix_budget_reservations_exchange_message_id", "exchange_message_id"),
    )


class ModelCallCacheUsage(Base):
    """§2.2 — `model_call_cache_usage`, ruling of 8 September 2026.

    The prompt-cache evidence for one call: the lifetime requested, the four
    usage figures as the provider reported them, the outcome, and the four
    billed components at the configuration's verified cache rates — computed
    at call time and never recomputed. At most one row per `model_calls` row,
    present exactly when caching was requested and usage was reported.
    `model_calls` itself is unchanged. Append-only (`0015`).
    """

    __tablename__ = "model_call_cache_usage"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    model_call_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("model_calls.id", ondelete="NO ACTION"),
        nullable=False,
        unique=True,
    )
    requested_ttl: Mapped[str] = mapped_column(Text, nullable=False)
    uncached_input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cache_write_5m_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cache_write_1h_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cache_read_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    cost_uncached: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    cost_cache_write: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    cost_cache_read: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    cost_output: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)

    __table_args__ = (
        CheckConstraint("requested_ttl in ('5m', '1h')", name="requested_ttl_documented"),
        CheckConstraint(
            "outcome in ('hit', 'created', 'hit_and_created', 'not_cached')",
            name="outcome_named",
        ),
        CheckConstraint(
            "uncached_input_tokens >= 0 and cache_write_5m_tokens >= 0 and "
            "cache_write_1h_tokens >= 0 and cache_read_tokens >= 0",
            name="token_counts_non_negative",
        ),
        CheckConstraint(
            "(outcome = 'hit') = (cache_read_tokens > 0 and cache_write_5m_tokens = 0 "
            "and cache_write_1h_tokens = 0)",
            name="hit_means_read_only",
        ),
        CheckConstraint(
            "(outcome = 'not_cached') = (cache_read_tokens = 0 and cache_write_5m_tokens = 0 "
            "and cache_write_1h_tokens = 0)",
            name="not_cached_means_nothing_cached",
        ),
    )


class ModelCallMeasurement(Base):
    """§2.2 — `model_call_measurements`, ruling of 13 September 2026 (`0020`).

    Per-call measurement the provider comparison needs exactly rather than by
    inference: the exchange the call belongs to, whether it streamed, time to
    the first generated-text delta at the Val Core boundary, generated-text
    characters, and — only where the provider exposes them — reasoning presence,
    reasoning tokens, and prompt-cache reads and writes as reported. At most one
    row per `model_calls` row, written in the same transaction. `model_calls`
    itself is unchanged. Append-only.
    """

    __tablename__ = "model_call_measurements"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    model_call_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("model_calls.id", ondelete="NO ACTION"),
        nullable=False,
        unique=True,
    )
    exchange_conversation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="NO ACTION"), nullable=True
    )
    exchange_message_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="NO ACTION"), nullable=True
    )
    streamed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    first_text_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text_output_chars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning_present: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reasoning_output_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_cached_input_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_cache_write_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Ruling, 15 September 2026 (`0021`): the prompt-cache key the request
    # carried and the provider's cache diagnostics, verbatim — what was asked of
    # the cache, what it echoed, the read/write split, and any miss reason or
    # reusable/missed counts a provider returns. NULL where the provider or the
    # call mode exposes neither; never inferred.
    prompt_cache_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    cache_diagnostics: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    # Ruling, 16 September 2026 (`0022`): the model identifier the provider's
    # own response named (an adapter refuses a mismatch, so on a recorded call
    # it equals the requested identifier or is NULL where the provider names
    # none), and the runtime's account of the call with the entry's hosting
    # axis — a local server's loaded model, context length and timing figures,
    # verbatim. NULL where nothing was exposed; never inferred.
    provider_reported_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    runtime_diagnostics: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "(exchange_conversation_id IS NULL) = (exchange_message_id IS NULL)",
            name="exchange_both_or_neither",
        ),
        CheckConstraint(
            "first_text_ms IS NULL OR (streamed AND first_text_ms >= 0)",
            name="first_text_only_when_streamed",
        ),
        CheckConstraint(
            "(text_output_chars IS NULL OR text_output_chars >= 0) AND "
            "(reasoning_output_tokens IS NULL OR reasoning_output_tokens >= 0) AND "
            "(provider_cached_input_tokens IS NULL OR provider_cached_input_tokens >= 0) AND "
            "(provider_cache_write_tokens IS NULL OR provider_cache_write_tokens >= 0)",
            name="measurements_non_negative",
        ),
        Index("ix_model_call_measurements_exchange_message_id", "exchange_message_id"),
    )


class MessageRevision(Base):
    """§2.1 amendment, 12 September 2026 — `message_revisions`.

    A revision or retraction of one of Lord Armand's own messages, as an
    appended fact: the `messages` row is never touched. `after_sequence` is the
    conversation's highest message sequence when the fact was recorded, read
    under the conversation row lock, so the turn whose message has sequence *s*
    sees exactly the facts with `after_sequence < s`. A coherence trigger
    refuses a Val message, a mismatched conversation, a stale `after_sequence`,
    a skipped `revision_number`, and a revision of a deliberated message.
    Append-only (`0016`); `messages_current` derives current state from it.
    """

    __tablename__ = "message_revisions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="NO ACTION"),
        nullable=False,
    )
    message_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="NO ACTION"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    after_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(MessageRevisionKind, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    authored_by: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("revision_number > 0", name="revision_number_positive"),
        CheckConstraint("after_sequence > 0", name="after_sequence_positive"),
        CheckConstraint("(kind = 'revision') = (content IS NOT NULL)", name="content_iff_revision"),
        CheckConstraint(
            "content IS NULL OR length(btrim(content)) > 0", name="revision_says_something"
        ),
        CheckConstraint("length(btrim(authored_by)) > 0", name="authored_by_named"),
        UniqueConstraint("message_id", "revision_number"),
        Index(
            "ix_message_revisions_conversation_id_after_sequence",
            "conversation_id",
            "after_sequence",
        ),
    )


class ConversationRemoval(Base):
    """§2.1 amendment, 12 September 2026 — `conversation_removals`.

    Remove and Reinstate as appended facts. A removed conversation is excluded
    from both recall paths and cannot be resumed; nothing in it is touched.
    `event_number` is the next number under the conversation row lock; a
    coherence trigger refuses a skipped number, a double removal and a
    reinstatement of a live conversation. Append-only (`0017`);
    `val_conversation_removed_at` derives the state.
    """

    __tablename__ = "conversation_removals"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="NO ACTION"),
        nullable=False,
    )
    event_number: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(ConversationRemovalKind, nullable=False)
    authored_by: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("event_number > 0", name="event_number_positive"),
        CheckConstraint("length(btrim(authored_by)) > 0", name="authored_by_named"),
        UniqueConstraint("conversation_id", "event_number"),
    )


class ConversationScopeTransition(Base):
    """§2.1 amendment, 12 September 2026 — `conversation_scope_transitions`.

    An explicit move of an existing conversation, as an appended fact.
    `conversations.project_id` stays the immutable origin; the newest
    transition with `after_sequence < q` gives the scope a message at sequence
    *q* was written in (`val_effective_project_id`). NULL on either project
    column means explicitly no project. A coherence trigger refuses a skipped
    number, a stale `after_sequence`, a `from_project_id` that is not the
    effective scope, and a move of a removed conversation. Append-only (`0018`).
    """

    __tablename__ = "conversation_scope_transitions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="NO ACTION"),
        nullable=False,
    )
    transition_number: Mapped[int] = mapped_column(Integer, nullable=False)
    after_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    from_project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="NO ACTION"), nullable=True
    )
    to_project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="NO ACTION"), nullable=True
    )
    authored_by: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("transition_number > 0", name="transition_number_positive"),
        CheckConstraint("after_sequence >= 0", name="after_sequence_not_negative"),
        CheckConstraint(
            "from_project_id IS DISTINCT FROM to_project_id", name="a_move_changes_scope"
        ),
        CheckConstraint("length(btrim(authored_by)) > 0", name="authored_by_named"),
        # Explicit names: the conventional ones exceed PostgreSQL's 63-character limit.
        UniqueConstraint(
            "conversation_id",
            "transition_number",
            name="uq_scope_transitions_conversation_number",
        ),
        Index("ix_scope_transitions_conversation_after", "conversation_id", "after_sequence"),
    )


class AnswerRecallSource(Base):
    """WP-0.7 amendment, 13 September 2026 — `answer_recall_sources`.

    One House Recall source admitted to the response call that produced a Val
    answer: which answer, which call, which source message, and exactly which
    wording of it (`source_revision_number`, NULL for the original). Provenance
    only — no excerpt content. Append-only (`0019`); a coherence trigger refuses
    an answer that is not Val's, a source in the answer's own conversation, and a
    revision number that is not a revision of the source.
    """

    __tablename__ = "answer_recall_sources"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="NO ACTION"), nullable=False
    )
    answer_message_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="NO ACTION"), nullable=False
    )
    model_call_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("model_calls.id", ondelete="NO ACTION"), nullable=False
    )
    retrieval_path: Mapped[str] = mapped_column(Text, nullable=False)
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    source_message_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="NO ACTION"), nullable=False
    )
    source_conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="NO ACTION"), nullable=False
    )
    source_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_revision_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="NO ACTION"), nullable=True
    )
    source_sent_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    source_conversation_title: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("retrieval_path = 'house_recall'", name="retrieval_path_ruled"),
        CheckConstraint("rank_position > 0", name="rank_position_positive"),
        CheckConstraint(
            "source_revision_number IS NULL OR source_revision_number > 0",
            name="source_revision_number_positive",
        ),
        UniqueConstraint(
            "answer_message_id", "source_message_id", name="uq_answer_recall_sources_answer_source"
        ),
        Index("ix_answer_recall_sources_answer_message_id", "answer_message_id"),
    )


# --- Attachment Substrate v1.2 — the six append-only tables ------------------
#
# Owner ruling, 19 September 2026 (Track C resumed). The governing contract is
# `docs/contracts/VAL_Attachment_Substrate_v1.md`; migration `0024` builds this.
# Designed once for all four modalities: images are the first consumer, and
# documents, audio and video inherit the same identity, provenance and binding
# without a second evidence system.


class Blob(Base):
    """§3.1 — one content-addressed byte store; originals and derived bytes alike.

    The primary key **is** the digest of the content, and a check constraint says
    so: PostgreSQL's `sha256()` is immutable, so a row whose key does not match
    its bytes cannot exist. `media_type` is established by the admission
    preflight from the bytes themselves, never from a filename or EXIF, so it
    lives with the bytes it describes.
    """

    __tablename__ = "blobs"

    sha256: Mapped[str] = mapped_column(Text, primary_key=True)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[bytes] = mapped_column("bytes", BYTEA, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("sha256 = encode(sha256(bytes), 'hex')", name="sha256_is_the_digest"),
        CheckConstraint("byte_size = length(bytes)", name="byte_size_is_the_length"),
        CheckConstraint("byte_size > 0", name="byte_size_positive"),
        CheckConstraint(
            "media_type ~ '^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$'",
            name="media_type_is_a_media_type",
        ),
    )


class Attachment(Base):
    """§3.2 — the immutable original: one content instance per distinct bytes.

    Deliberately thin, and staying so. `blobs.sha256` means *these exact bytes
    exist*; `attachments.id` means *these bytes were admitted as an original
    conversational attachment and are the root of this provenance tree*. Two
    different facts, so two different keys.
    """

    __tablename__ = "attachments"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    sha256: Mapped[str] = mapped_column(
        Text, ForeignKey("blobs.sha256", ondelete="NO ACTION"), nullable=False
    )

    __table_args__ = (UniqueConstraint("sha256", name="uq_attachments_sha256"),)


class MessageAttachment(Base):
    """§3.3 — the act: this attachment accompanied this user message, here.

    Identity is the content; the **act** is what carries a classification, and it
    carries its own. Re-using an attachment on a later turn is a new act with a
    new statement, defaulting to `protected` again — never inheriting a weaker
    class from an earlier one. Evidence begins at the successful send commit:
    a failed admission writes nothing at all.
    """

    __tablename__ = "message_attachments"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    attached_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    message_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="NO ACTION"), nullable=False
    )
    attachment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("attachments.id", ondelete="NO ACTION"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The name as provided *at this act* — display, never identity.
    given_filename: Mapped[str] = mapped_column(Text, nullable=False)
    stated_classification: Mapped[str] = mapped_column(AttachmentActClassification, nullable=False)

    __table_args__ = (
        UniqueConstraint("message_id", "position", name="uq_message_attachments_message_position"),
        # §5.3a — an input row's act is tied to its own attachment by a key.
        UniqueConstraint("id", "attachment_id", name="uq_message_attachments_id_attachment"),
        CheckConstraint("position > 0", name="position_positive"),
        CheckConstraint("length(btrim(given_filename)) > 0", name="given_filename_present"),
        Index("ix_message_attachments_message_id", "message_id"),
    )


class AttachmentRepresentation(Base):
    """§3.4 — a typed derived view, resolving to the one attachment it belongs to.

    Complete at insert: a row exists only for a derivation that succeeded. v1
    declares exactly one type, `model_input_image` — the bytes actually
    transmitted when they differ from the original. The locator columns are
    declared now, unused by images, so the documents sibling inherits them rather
    than inventing a second provenance model.
    """

    __tablename__ = "attachment_representations"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    attachment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("attachments.id", ondelete="NO ACTION"), nullable=False
    )
    #: NULL = derived directly from the original.
    parent_representation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    representation_type: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(
        Text, ForeignKey("blobs.sha256", ondelete="NO ACTION"), nullable=False
    )
    #: 1-based page/slide within the parent; NULL = the whole parent.
    locator_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: `x0,y0,x1,y1` in the parent's pixel coordinates; NULL = the whole of it.
    locator_region: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Tool and pinned version. The derived digest carries identity.
    derived_by: Mapped[str] = mapped_column(Text, nullable=False)
    #: Non-null exactly when a model produced the representation. v1 derivations
    #: are local, so both stay NULL.
    model_config_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    model_call_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("model_calls.id", ondelete="NO ACTION"), nullable=True
    )

    __table_args__ = (
        # §5.1 and §5.3 — the device that keeps one file's tree one file's tree.
        UniqueConstraint("id", "attachment_id", name="uq_attachment_representations_id_attachment"),
        ForeignKeyConstraint(
            ["parent_representation_id", "attachment_id"],
            ["attachment_representations.id", "attachment_representations.attachment_id"],
            name="fk_attachment_representations_parent",
        ),
        CheckConstraint(
            "representation_type IN ('model_input_image')", name="representation_type_declared"
        ),
        CheckConstraint(
            "parent_representation_id IS NULL OR parent_representation_id <> id",
            name="no_self_parent",
        ),
        CheckConstraint(
            "locator_ordinal IS NULL OR locator_ordinal > 0", name="locator_ordinal_positive"
        ),
        CheckConstraint("length(btrim(derived_by)) > 0", name="derived_by_present"),
        CheckConstraint(
            "(model_config_id IS NULL) = (model_call_id IS NULL)",
            name="model_provenance_is_paired",
        ),
        Index("ix_attachment_representations_attachment_id", "attachment_id"),
    )


class AttachmentProcessingEvent(Base):
    """§3.5 — attempts, honestly. Current state is derived, never mutated.

    `started` with no terminal event means exactly that, and never "currently
    processing": a crash after `started` leaves the same durable sequence as a
    live attempt, and the record does not pretend to know the difference. One
    `started` per attempt and at most one terminal event are partial unique
    indexes; that a terminal event matches its `started` is a trigger.
    """

    __tablename__ = "attachment_processing_events"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    attachment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("attachments.id", ondelete="NO ACTION"), nullable=False
    )
    #: Durable attempt identity: all events of one attempt share it.
    attempt_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    intent: Mapped[str] = mapped_column(Text, nullable=False)
    event: Mapped[str] = mapped_column(AttachmentProcessingEventType, nullable=False)
    representation_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # §3.5 rule 5 — a produced representation belongs to the same attachment.
        ForeignKeyConstraint(
            ["representation_id", "attachment_id"],
            ["attachment_representations.id", "attachment_representations.attachment_id"],
            name="fk_attachment_processing_events_representation",
        ),
        CheckConstraint("intent IN ('derive:model_input_image', 'verify')", name="intent_declared"),
        CheckConstraint("(event = 'failed') = (error IS NOT NULL)", name="failed_states_why"),
        # Correction, 20 September 2026: stated in both directions, so a
        # succeeded derivation cannot claim to have produced nothing.
        CheckConstraint(
            "CASE WHEN event = 'succeeded' AND intent LIKE 'derive:%' "
            "THEN representation_id IS NOT NULL ELSE representation_id IS NULL END",
            name="succeeded_derivation_produces",
        ),
        Index("ix_attachment_processing_events_attachment_id", "attachment_id"),
        Index(
            "ux_attachment_processing_events_one_started",
            "attempt_id",
            unique=True,
            postgresql_where=text("event = 'started'"),
        ),
        Index(
            "ux_attachment_processing_events_one_terminal",
            "attempt_id",
            unique=True,
            postgresql_where=text("event IN ('succeeded', 'failed')"),
        ),
    )


class ModelCallImageInput(Base):
    """§3.6 — which exact image bytes were bound to a recorded call, through which act.

    The name is deliberate at every step: v1.0's `model_call_sight` overclaimed
    sight and v1.1's `model_call_inputs` overclaimed being the record of *all* a
    call's inputs. This row proves a **binding**. Sight is this row together with
    the call's `terminal_state = 'complete'` (§4) — a refusal can come from a
    safety layer that never ran vision, and claiming otherwise is exactly the
    invariant 29 failure.

    The chain, complete: call → image input → attachment act → attachment →
    original blob.
    """

    __tablename__ = "model_call_image_inputs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    model_call_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("model_calls.id", ondelete="NO ACTION"), nullable=False
    )
    #: The exact participating act — same attachment used `internal` on Monday
    #: and `protected` on Thursday: this names which act supplied the image here.
    message_attachment_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    attachment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("attachments.id", ondelete="NO ACTION"), nullable=False
    )
    input_kind: Mapped[str] = mapped_column(ModelCallImageInputKind, nullable=False)
    representation_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    #: The exact bytes bound to this call. One lookup, no reconstruction.
    transmitted_sha256: Mapped[str] = mapped_column(
        Text, ForeignKey("blobs.sha256", ondelete="NO ACTION"), nullable=False
    )
    #: Read from the decoded bytes, never EXIF — these priced the call (§8).
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    #: Any provider option that changes pricing or interpretation; empty when none.
    provider_options: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    #: Copied from the participating act at send, so the egress record is
    #: self-contained even though the act is named directly.
    stated_classification: Mapped[str] = mapped_column(AttachmentActClassification, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "model_call_id", "position", name="uq_model_call_image_inputs_model_call_position"
        ),
        # §5.3 and §5.3a — the representation and the act both belong to this
        # row's own attachment, by key rather than by application care.
        ForeignKeyConstraint(
            ["representation_id", "attachment_id"],
            ["attachment_representations.id", "attachment_representations.attachment_id"],
            name="fk_model_call_image_inputs_representation",
        ),
        ForeignKeyConstraint(
            ["message_attachment_id", "attachment_id"],
            ["message_attachments.id", "message_attachments.attachment_id"],
            name="fk_model_call_image_inputs_act",
        ),
        CheckConstraint("position > 0", name="position_positive"),
        CheckConstraint(
            "(input_kind = 'representation') = (representation_id IS NOT NULL)",
            name="kind_matches_representation",
        ),
        CheckConstraint("width > 0 AND height > 0", name="dimensions_positive"),
        CheckConstraint(
            "media_type ~ '^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$'",
            name="media_type_is_a_media_type",
        ),
        Index("ix_model_call_image_inputs_model_call_id", "model_call_id"),
    )


#: Every table §2 names, and nothing else. The schema test asserts against this.
# ---------------------------------------------------------------------------
# Local visual perception
# ---------------------------------------------------------------------------
#
# Owner ruling, 22 September 2026, on Qwen3.5-9B's qualification; migration
# `0025` builds these. Val perceives media on her own machine and hands the
# cognition provider grounded observations rather than pixels, so the record has
# to hold a kind of act the cognition tables were not built for: evidence
# derived from SOURCE MEDIA plus the OWNER'S QUESTION. Three tables say what it
# was, what it looked at, and who received it.


class PerceptionRun(Base):
    """One perception run: the provider, the artifact, the question, the answer.

    Not a `model_calls` row, and deliberately not. That table accounts for calls
    that buy thinking — tokens, reservations, cache splits, metered rates — and
    this buys none of them. What it produces is evidence, and evidence has to be
    able to say what it came from.
    """

    __tablename__ = "perception_runs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="NO ACTION"), nullable=False
    )
    #: One perception per turn, and the unique constraint below makes §22's "run
    #: perception once" a key rather than a convention.
    message_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="NO ACTION"), nullable=False
    )
    model_config_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model_identifier: Mapped[str] = mapped_column(Text, nullable=False)
    #: The immutable revision. A perception record that cannot say which weights
    #: produced it is not provenance.
    model_revision: Mapped[str] = mapped_column(Text, nullable=False)
    quantization: Mapped[str] = mapped_column(Text, nullable=False)
    runtime: Mapped[str] = mapped_column(Text, nullable=False)
    runtime_version: Mapped[str] = mapped_column(Text, nullable=False)
    #: The generation settings in force, read back from the runtime rather than
    #: restated from the registry.
    generation: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    #: His actual words, and the exact instruction transmitted. Both, because the
    #: second is derived from the first and a record holding only the derivation
    #: cannot show what it was derived from.
    owner_question: Mapped[str] = mapped_column(Text, nullable=False)
    perception_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    observation: Mapped[str] = mapped_column(Text, nullable=False)
    current_perception_state: Mapped[str] = mapped_column(PerceptionState, nullable=False)
    local: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    #: §14's observation-discipline finding, per run rather than assumed once.
    reasoning_separated: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (
        UniqueConstraint("message_id", name="uq_perception_runs_message"),
        CheckConstraint("length(btrim(perception_prompt)) > 0", name="prompt_present"),
        CheckConstraint("length(btrim(observation)) > 0", name="observation_present"),
        CheckConstraint("duration_ms >= 0", name="duration_not_negative"),
        #: A local run bills nothing, said as a constraint rather than as a habit.
        CheckConstraint("(local AND cost_usd = 0) OR NOT local", name="local_costs_nothing"),
        Index("ix_perception_runs_conversation", "conversation_id"),
    )


class PerceptionSource(Base):
    """What one run looked at — the SOURCE → OBSERVATION relationship.

    The act and the attachment are nullable together, for a house-internal source
    that never arrived on a message; a trigger holds them to the same file
    whenever they are set, so a source row cannot name one file's act and another
    file's bytes.
    """

    __tablename__ = "perception_sources"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    perception_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("perception_runs.id", ondelete="NO ACTION"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    message_attachment_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("message_attachments.id", ondelete="NO ACTION"),
        nullable=True,
    )
    attachment_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("attachments.id", ondelete="NO ACTION"), nullable=True
    )
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    modality: Mapped[str] = mapped_column(PerceptionModality, nullable=False)
    #: `original` for this slice: the local runtime reads the admitted bytes and
    #: does its own preprocessing, so nothing is derived for transmission.
    representation: Mapped[str] = mapped_column(Text, nullable=False)
    #: Time-based media say how long they are; a still image says NULL (0026).
    duration_seconds: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    #: **How far admission actually went** (0026): `decoded` for an image that was
    #: really decoded, `decoded_header` for a WAV whose header the standard
    #: library parsed, `container_structure` for an MP4 whose boxes were walked
    #: and whose frames were not. One word for all three would claim a decode
    #: that did not happen.
    verified: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: What was reported about THIS source, so a multi-image turn can say which
    #: observation belongs to which file.
    observation: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "perception_run_id", "position", name="uq_perception_sources_run_position"
        ),
        CheckConstraint("position > 0", name="position_positive"),
        CheckConstraint("byte_size > 0", name="byte_size_positive"),
        CheckConstraint("length(sha256) = 64", name="sha256_is_a_digest"),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0", name="duration_not_negative"
        ),
        CheckConstraint(
            "(message_attachment_id IS NULL) = (attachment_id IS NULL)",
            name="act_and_attachment_together",
        ),
        Index("ix_perception_sources_run", "perception_run_id"),
    )


class PerceptionHandoff(Base):
    """Which cognition call received this perception — OBSERVATION → COGNITION.

    Two rows naming one run is exactly the proof §22 asks for: on a consequential
    turn the blind position and the final answer were grounded in the same frozen
    observation, and the record can show it without re-reading either payload.
    """

    __tablename__ = "perception_handoffs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    perception_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("perception_runs.id", ondelete="NO ACTION"),
        nullable=False,
    )
    model_call_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("model_calls.id", ondelete="NO ACTION"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "perception_run_id", "model_call_id", name="uq_perception_handoffs_run_call"
        ),
        Index("ix_perception_handoffs_run", "perception_run_id"),
        Index("ix_perception_handoffs_call", "model_call_id"),
    )


# ---------------------------------------------------------------------------
# Local speech output
# ---------------------------------------------------------------------------
#
# Owner execution order, 22 September 2026; migration `0027` builds these. Two
# tables, and the split is the point: a voice is an identity, written once, and
# an utterance is an event, written each time. Neither is a `model_calls` row —
# that table accounts for calls that buy thinking, and speech buys none.


class SpeechVoice(Base):
    """Who Val is when she speaks, and where that came from.

    The reference recording lives on disk at a fixed governed path; what lives
    here is its digest and everything needed to say honestly what the voice is —
    including, deliberately, what is **not** claimed about it.
    """

    __tablename__ = "speech_voices"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    reference_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    reference_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reference_sample_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_duration_seconds: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    #: Supplied explicitly to the clone path. No automatic transcription
    #: produced it, and the record holds the words as well as their digest.
    reference_text: Mapped[str] = mapped_column(Text, nullable=False)
    reference_text_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    #: The frozen description the voice was designed from — the only thing a
    #: future rebuild of this voice would need.
    voice_description: Mapped[str] = mapped_column(Text, nullable=False)
    voice_description_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    designed_by_model: Mapped[str] = mapped_column(Text, nullable=False)
    designed_by_revision: Mapped[str] = mapped_column(Text, nullable=False)
    designed_by_quantization: Mapped[str] = mapped_column(Text, nullable=False)
    designed_by_runtime: Mapped[str] = mapped_column(Text, nullable=False)
    designed_generation: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    #: Where the reference came from, and what is not claimed about it.
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    identity_claim: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("reference_sha256", name="uq_speech_voices_reference"),
        CheckConstraint("length(btrim(name)) > 0", name="name_present"),
        CheckConstraint("length(reference_sha256) = 64", name="reference_is_a_digest"),
        CheckConstraint("length(btrim(reference_text)) > 0", name="reference_text_present"),
        CheckConstraint("length(btrim(voice_description)) > 0", name="voice_description_present"),
        CheckConstraint("reference_bytes > 0", name="reference_bytes_positive"),
        CheckConstraint("reference_sample_rate > 0", name="reference_sample_rate_positive"),
    )


class SpeechGeneration(Base):
    """One utterance: Val's finished words, and the waveform of exactly those.

    `final_text` is copied verbatim from what Val already said. The provider
    spoke it and decided none of it, so a reader can check later that the voice
    said what the record says — which is the whole reason the text is here and
    not merely referenced.
    """

    __tablename__ = "speech_generations"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    voice_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("speech_voices.id", ondelete="NO ACTION"), nullable=False
    )
    #: NULL for a house-internal utterance, which reads differently from an
    #: utterance with no source at all.
    message_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="NO ACTION"), nullable=True
    )
    model_config_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    final_text: Mapped[str] = mapped_column(Text, nullable=False)
    final_text_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model_identifier: Mapped[str] = mapped_column(Text, nullable=False)
    model_revision: Mapped[str] = mapped_column(Text, nullable=False)
    quantization: Mapped[str] = mapped_column(Text, nullable=False)
    runtime: Mapped[str] = mapped_column(Text, nullable=False)
    runtime_version: Mapped[str] = mapped_column(Text, nullable=False)
    generation: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    #: The reusable identity anchor. Equal across utterances is the proof that
    #: the voice did not drift between them.
    clone_prompt_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    audio_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    #: NULL for ordinary live speech, which is generated, delivered and released
    #: (work package 2 §10). `audio_retained` says which, and a check constraint
    #: holds the two together so a row can neither claim a file that does not
    #: exist nor hide one that does.
    audio_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_retained: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    #: Progressive delivery makes one generation per speech-safe segment. NULL is a
    #: whole-utterance generation, which is every row written before 23 September 2026.
    segment_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    segment_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sample_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    local: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("length(btrim(final_text)) > 0", name="final_text_present"),
        CheckConstraint("length(final_text_sha256) = 64", name="final_text_is_a_digest"),
        CheckConstraint("length(audio_sha256) = 64", name="audio_is_a_digest"),
        CheckConstraint("audio_bytes > 0", name="audio_bytes_positive"),
        CheckConstraint("sample_rate > 0", name="sample_rate_positive"),
        CheckConstraint("duration_seconds > 0", name="duration_positive"),
        CheckConstraint("elapsed_ms >= 0", name="elapsed_not_negative"),
        CheckConstraint("(local AND cost_usd = 0) OR NOT local", name="local_costs_nothing"),
        CheckConstraint(
            "audio_retained = (audio_path IS NOT NULL)", name="retained_names_its_file"
        ),
        CheckConstraint(
            "segment_index IS NULL OR segment_index > 0",
            name="segment_index_is_counted_from_one",
        ),
        CheckConstraint(
            "(segment_index IS NULL) = (segment_reason IS NULL)",
            name="a_segment_says_why_it_ended",
        ),
        Index("ix_speech_generations_voice", "voice_id"),
        Index("ix_speech_generations_message", "message_id"),
        Index(
            "uq_speech_generations_message_segment",
            "message_id",
            "segment_index",
            unique=True,
            postgresql_where=text("message_id IS NOT NULL AND segment_index IS NOT NULL"),
        ),
    )


class VoiceSession(Base):
    """One live listening session, attached to an existing conversation.

    A voice session is **not a second conversation**; it is an input modality on
    one. It carries no audio of any kind: the recognizer's buffers are volatile
    process state, and what survives is the text they produced.

    The only table in the voice set with a lifecycle. Everything that identifies
    the session — above all which recognizer and which models heard it — is
    immutable in the store; only `state`, `closed_at` and `closed_reason` move.
    """

    __tablename__ = "voice_sessions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="NO ACTION"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    closed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    closed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Exactly what heard this. *You typed* and *the recognizer heard* are
    #: different claims, and the difference should survive a model upgrade.
    recognizer: Mapped[str] = mapped_column(Text, nullable=False)
    recognizer_version: Mapped[str] = mapped_column(Text, nullable=False)
    recognizer_commit: Mapped[str] = mapped_column(Text, nullable=False)
    asr_model: Mapped[str] = mapped_column(Text, nullable=False)
    asr_model_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    vad_model: Mapped[str] = mapped_column(Text, nullable=False)
    vad_model_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    #: The endpointing figures actually in force, so a transcript's boundaries are
    #: readable from the record rather than from whatever the code says today.
    endpoint_configuration: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "state IN ('listening', 'hearing', 'thinking', 'closed', 'error')",
            name="state_is_known",
        ),
        CheckConstraint(
            "(state IN ('closed', 'error')) = (closed_at IS NOT NULL)",
            name="closed_exactly_when_it_ended",
        ),
        CheckConstraint("recognizer = 'whisper.cpp'", name="recognizer_is_the_local_one"),
        CheckConstraint("length(asr_model_sha256) = 64", name="asr_model_is_a_digest"),
        CheckConstraint("length(vad_model_sha256) = 64", name="vad_model_is_a_digest"),
        Index("ix_voice_sessions_conversation", "conversation_id"),
    )


class VoiceMessageProvenance(Base):
    """How a finalized voice-origin turn arrived. One row per message.

    A sidecar rather than columns on `messages`, because a spoken turn is an
    ordinary turn and the core table should not learn about microphones to say so.
    The visible message text is untouched: none of this appears in it.

    Only ever written for `final` transcription. A rolling guess is not a message
    and so can have no provenance row.
    """

    __tablename__ = "voice_message_provenance"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    message_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="NO ACTION"), nullable=False
    )
    voice_session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("voice_sessions.id", ondelete="NO ACTION"), nullable=False
    )
    input_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="voice")
    transcription_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="final")
    finalized_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    utterance: Mapped[int] = mapped_column(Integer, nullable=False)
    endpoint_reason: Mapped[str] = mapped_column(Text, nullable=False)
    #: Evidence that the provisional path ran, kept without keeping the guesses.
    provisional_events: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    #: Utterances this turn absorbed when the owner resumed before Val answered.
    merged_from: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default=text("'{}'::integer[]")
    )

    __table_args__ = (
        UniqueConstraint("message_id", name="uq_voice_message_provenance_message"),
        CheckConstraint("input_mode = 'voice'", name="input_mode_is_voice"),
        CheckConstraint("transcription_status = 'final'", name="only_final_is_a_message"),
        CheckConstraint("utterance > 0", name="utterance_is_counted_from_one"),
        CheckConstraint("provisional_events >= 0", name="provisional_events_not_negative"),
        CheckConstraint(
            "endpoint_reason IN ('silence', 'maximum_length', 'flush')",
            name="endpoint_reason_is_known",
        ),
        Index("ix_voice_message_provenance_session", "voice_session_id"),
    )


class VoiceRecoveryJournalEntry(Base):
    """A crash-recovery note for an unfinished spoken utterance. **Text only.**

    Not authoritative conversation, and structurally unable to become it: recall
    and history read `messages_current`, which this table has no part in. Nothing
    here is ever `final` — recovered words are provisional, and promoting them to
    a canonical statement is a thing the owner does, not a thing a restart does.

    Append-only: the next state of an entry is the next entry.
    """

    __tablename__ = "voice_recovery_journal"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    voice_session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("voice_sessions.id", ondelete="NO ACTION"), nullable=False
    )
    #: Carried directly as well as through the session, because recovery runs when
    #: the process that knew the connection between them has died.
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="NO ACTION"),
        nullable=False,
    )
    utterance: Mapped[int] = mapped_column(Integer, nullable=False)
    entry: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The owner's words as last heard — never audio, never a path to audio.
    provisional_text: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    #: The link runs journal → message and never the other way, so conversation
    #: history never gains a reference to a guess.
    superseded_by_message_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="NO ACTION"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "voice_session_id", "utterance", "entry", name="uq_voice_recovery_journal_entry"
        ),
        CheckConstraint(
            "state IN ('provisional', 'superseded', 'abandoned', 'interrupted')",
            name="state_is_known_and_never_final",
        ),
        CheckConstraint(
            "(state = 'superseded') = (superseded_by_message_id IS NOT NULL)",
            name="superseded_names_its_message",
        ),
        CheckConstraint("utterance > 0", name="utterance_is_counted_from_one"),
        CheckConstraint("entry > 0", name="entry_is_counted_from_one"),
        Index("ix_voice_recovery_journal_session", "voice_session_id"),
        Index(
            "ix_voice_recovery_journal_open",
            "conversation_id",
            postgresql_where=text("state = 'provisional'"),
        ),
    )


class SpeechDelivery(Base):
    """One transition in what the owner actually heard. Append-only.

    Core can finish writing text he never hears, because he interrupts her. This
    table is the difference between *what Val generated* and *what delivery
    delivered* — one row per transition, each carrying the exact prefix delivered
    at that moment. A delivery's state is its highest-numbered row; there is no
    UPDATE, so `interrupted` cannot quietly become `completed`.

    The original assistant message is never rewritten to make the record tidy.
    """

    __tablename__ = "speech_deliveries"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    message_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="NO ACTION"), nullable=False
    )
    #: NULL for a house-internal delivery — an acceptance run — which reads
    #: differently from a delivery with no session at all.
    voice_session_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("voice_sessions.id", ondelete="NO ACTION"), nullable=True
    )
    event: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    #: **The exact prefix he heard**, and its length. An interrupted answer is
    #: truthfully half-heard, and the half is written down rather than
    #: reconstructed later from a guess.
    delivered_prefix: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    delivered_characters: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    segments_delivered: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    #: NULL while Val is still writing: the number is not known yet, and 0 would
    #: be a claim rather than an absence.
    segments_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Required for `interrupted` and `failed`, forbidden otherwise, so a state and
    #: its reason cannot disagree.
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_audio_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("message_id", "event", name="uq_speech_deliveries_event"),
        CheckConstraint(
            "state IN ('not_started', 'started', 'completed', 'interrupted', 'failed')",
            name="state_is_known",
        ),
        CheckConstraint(
            "(state IN ('interrupted', 'failed')) = (reason IS NOT NULL)",
            name="a_state_and_its_reason_agree",
        ),
        CheckConstraint("event > 0", name="event_is_counted_from_one"),
        CheckConstraint(
            "delivered_characters >= 0 AND segments_delivered >= 0",
            name="counts_are_not_negative",
        ),
        CheckConstraint(
            "segments_total IS NULL OR segments_total >= segments_delivered",
            name="segments_delivered_fit_the_total",
        ),
        CheckConstraint(
            "length(delivered_prefix) = delivered_characters",
            name="the_prefix_and_its_length_agree",
        ),
        CheckConstraint(
            "state <> 'not_started' OR (delivered_characters = 0 AND segments_delivered = 0)",
            name="nothing_delivered_before_start",
        ),
        Index("ix_speech_deliveries_message", "message_id"),
        Index("ix_speech_deliveries_session", "voice_session_id"),
    )


SPECIFIED_TABLES = frozenset(
    {
        "projects",
        "conversations",
        "answer_recall_sources",
        "conversation_removals",
        "conversation_scope_transitions",
        "messages",
        "message_revisions",
        "personas",
        "model_calls",
        "model_call_cache_usage",
        "model_call_measurements",
        "execution_events",
        "deliberations",
        "blind_positions",
        "classifications",
        "classification_labels",
        "classification_reviews",
        "ideas",
        "idea_state_changes",
        "budget_reservations",
        # Attachment Substrate v1.2, migration 0024 (19 September 2026).
        "blobs",
        "attachments",
        "message_attachments",
        "attachment_representations",
        "attachment_processing_events",
        "model_call_image_inputs",
        # Local visual perception, migration 0025 (22 September 2026).
        "perception_runs",
        "perception_sources",
        "perception_handoffs",
        # Local speech output, migration 0027 (22 September 2026).
        "speech_voices",
        "speech_generations",
        # Live voice input, migration 0028 (23 September 2026). No audio column
        # appears in any of the three, by construction.
        "voice_sessions",
        "voice_message_provenance",
        "voice_recovery_journal",
        # What the owner actually heard, migration 0029 (23 September 2026).
        "speech_deliveries",
    }
)
