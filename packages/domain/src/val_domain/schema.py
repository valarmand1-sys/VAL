"""The authoritative store's schema, exactly as `04-layer-0.md` §2 specifies it.

Ten tables, in §2's order — seven from the original §2, two added by the
15 August 2026 amendments (`execution_events.reaction` and the idea tables of
§2.4), and `budget_reservations` added by the 17 August 2026 amendment (§2.5).
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
    Index,
    Integer,
    MetaData,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
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
# §2.2 amendment, 17 August 2026. A provider attempt has three accounting
# outcomes and only two of them are rows: NOT_SENT writes nothing at all, because
# no call occurred. `known` and `unknown` distinguish the other two, and `unknown`
# is the reason `cost` may be NULL — a call that reached the provider consumed
# input tokens, so recording zero would be recording a figure that is known to be
# false rather than one that is merely unknown.
ModelCallCostCertainty = Enum("known", "unknown", name="model_call_cost_certainty")
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
    # none — a strip step, a title — is not a Val utterance to attribute.
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
            "(cost IS NOT NULL AND tokens_in IS NOT NULL AND tokens_out IS NOT NULL)",
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

    __table_args__ = (
        # §2 states the rule: required when outcome = 'updated'.
        CheckConstraint(
            "outcome <> 'updated' OR what_changed_her_mind IS NOT NULL",
            name="updated_requires_what_changed_her_mind",
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
        Index("ix_budget_reservations_state_created_at", "state", "created_at"),
    )


#: Every table §2 names, and nothing else. The schema test asserts against this.
SPECIFIED_TABLES = frozenset(
    {
        "projects",
        "conversations",
        "messages",
        "personas",
        "model_calls",
        "execution_events",
        "deliberations",
        "ideas",
        "idea_state_changes",
        "budget_reservations",
    }
)
