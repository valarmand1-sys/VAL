"""The authoritative store's schema, exactly as `04-layer-0.md` §2 specifies it.

Seven tables, in §2's order. No table exists here that §2 does not name, and no
column exists that §2 does not list. Where §2 is silent, the silence is recorded
in a comment rather than filled in.

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
ExecutionEventType = Enum(
    "accepted", "rejected", "revision_requested", "corrected", name="execution_event_type"
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
    not a null accident (§2.1). The distinction between "explicitly none" and
    "not yet resolved" is not expressible in this schema; WP-0.6 requires it to
    be queryable, and the resolution is recorded there, not invented here.
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
    )


class Persona(Base):
    """§2.1 — `personas`. Editing creates a version; it never mutates a row."""

    __tablename__ = "personas"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    activated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
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
    tokens_in: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tokens_out: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Stored, not derived. Provider pricing changes, and a historical record that
    # silently re-prices itself is not a record.
    cost: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="NO ACTION"), nullable=True
    )
    task_type: Mapped[str] = mapped_column(ModelCallTaskType, nullable=False)
    conversation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="NO ACTION"), nullable=True
    )
    message_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="NO ACTION"), nullable=True
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_request_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(ModelCallStatus, nullable=False)

    __table_args__ = (
        CheckConstraint("tokens_in >= 0", name="tokens_in_non_negative"),
        CheckConstraint("tokens_out >= 0", name="tokens_out_non_negative"),
        CheckConstraint("cost >= 0", name="cost_non_negative"),
        CheckConstraint("latency_ms >= 0", name="latency_ms_non_negative"),
    )


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
    event_type: Mapped[str] = mapped_column(ExecutionEventType, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    # The reason, in Lord Armand's words where he gave one. Nullable, but a null
    # reason is a defect to be surfaced, not a normal state.
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # No default. A reason Val inferred and a reason Lord Armand stated are
    # different evidence, and Layer 5 must be able to weight them differently.
    reason_source: Mapped[str] = mapped_column(ReasonSource, nullable=False)

    __table_args__ = (
        # The two fields cannot disagree. A stated reason that is absent, or an
        # absent reason that has text, would make the distinction untrustworthy
        # exactly where it is load-bearing.
        CheckConstraint(
            "(reason IS NULL) = (reason_source = 'absent')",
            name="reason_matches_source",
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
    }
)
