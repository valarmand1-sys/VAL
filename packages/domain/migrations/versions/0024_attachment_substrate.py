"""Attachment Substrate v1.2 — the six append-only tables. Owner ruling, 19 September 2026.

`docs/contracts/VAL_Attachment_Substrate_v1.md` has been the governing contract
since 2 September 2026 with nothing built beneath it; the storage question it
blocked on was ruled on 7 September (image bytes stay in PostgreSQL), and Track C
resumed by the owner ruling of 19 September. This migration implements the
contract's persistence model exactly, and nothing beyond it.

## The six tables

- **`blobs`** — one content-addressed byte store, originals and derived bytes
  alike. Content addressing is not a convention here but a **check constraint**:
  `encode(sha256(bytes), 'hex') = sha256`, and `byte_size = length(bytes)`.
  PostgreSQL's `sha256()` is immutable, so the store cannot hold a row whose key
  is not its content's digest.
- **`attachments`** — the immutable original: identity of a *content instance*,
  one per distinct bytes (`sha256` unique).
- **`message_attachments`** — the **act**: this attachment accompanied this user
  message at this position, under a classification stated *for this act*.
  `restricted` is refused at the act by not existing in the type.
- **`attachment_representations`** — typed derived views, each resolving to one
  attachment, optionally to a parent representation within the same attachment.
- **`attachment_processing_events`** — attempts, honestly: one `started` per
  attempt, at most one terminal event, terminal matching its `started`.
- **`model_call_image_inputs`** — which exact bytes were bound to which call,
  through which act. §4's sight rule reads this **together with**
  `model_calls.terminal_state = 'complete'`; a row here is a binding, never a
  claim that she saw anything.

## What the database enforces rather than trusts

Every §5 integrity rule is structural. The composite foreign keys are the
device: `attachment_representations` and `message_attachments` each carry a
`(id, attachment_id)` unique constraint, so a representation's parent, an input
row's representation, and an input row's *act* cannot silently point at another
file's tree. Rule 4 (`transmitted_sha256` equals the digest of the named
original or representation) is a trigger, because it spans tables.

No column is added to any existing table. Every reference to `messages` or
`model_calls` is a foreign key from the sidecar side, NO ACTION throughout, with
the standing hard-delete and evidence guards on all six.

## Downgrade

Refuses once any attachment evidence exists — bytes and their provenance are not
destroyed to move a schema backwards. Clean on empty tables, which is what CI
exercises.

Revision ID: 0024_attachment_substrate
Revises: 0023_second_local_provider
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_attachment_substrate"
down_revision: str | None = "0023_second_local_provider"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "blobs",
    "attachments",
    "message_attachments",
    "attachment_representations",
    "attachment_processing_events",
    "model_call_image_inputs",
)

#: §3.3 — per act, and `restricted` is refused at the act by never being a value.
ACT_CLASSIFICATIONS = ("public", "internal", "protected")
#: §3.4 — v1 declares exactly one. Additive values are permitted by §9 without
#: re-ruling; they arrive as a deliberate migration rather than free text.
REPRESENTATION_TYPES = ("model_input_image",)
#: §3.5 — what is being attempted. Never `probe`: the admission probe is
#: pre-commit and ephemeral, and the identity this table needs does not exist yet.
PROCESSING_INTENTS = ("derive:model_input_image", "verify")
PROCESSING_EVENTS = ("started", "succeeded", "failed")
#: §3.6 — explicit discrimination, no semantic NULL.
INPUT_KINDS = ("original", "representation")

#: §3.3 — the act accompanies a **user** message. Val's own messages carry no
#: attachments in v1, and the store says so rather than the application.
ACT_COHERENCE = """
CREATE OR REPLACE FUNCTION val_message_attachment_is_coherent()
RETURNS trigger AS $$
DECLARE
    message_role text;
BEGIN
    SELECT role::text INTO message_role FROM messages WHERE id = NEW.message_id;
    IF message_role IS DISTINCT FROM 'user' THEN
        RAISE EXCEPTION
            'an attachment act accompanies a user message; message % is %',
            NEW.message_id, coalesce(message_role, 'missing');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

#: §3.5 — the valid-sequence rules that a partial unique index cannot express:
#: a terminal event requires its `started`, and matches its attachment and intent.
PROCESSING_COHERENCE = """
CREATE OR REPLACE FUNCTION val_attachment_processing_event_is_coherent()
RETURNS trigger AS $$
DECLARE
    started_attachment uuid;
    started_intent text;
BEGIN
    IF NEW.event = 'started' THEN
        RETURN NEW;
    END IF;
    SELECT attachment_id, intent INTO started_attachment, started_intent
      FROM attachment_processing_events
     WHERE attempt_id = NEW.attempt_id AND event = 'started';
    IF started_attachment IS NULL THEN
        RAISE EXCEPTION
            'terminal event % for attempt % has no started event',
            NEW.event, NEW.attempt_id;
    END IF;
    IF started_attachment IS DISTINCT FROM NEW.attachment_id
       OR started_intent IS DISTINCT FROM NEW.intent THEN
        RAISE EXCEPTION
            'terminal event for attempt % does not match its started attachment and intent',
            NEW.attempt_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

#: §5 rule 4 — the transmitted digest IS the named original's or representation's.
#: One lookup at read time is only trustworthy if this cannot drift at write time.
INPUT_COHERENCE = """
CREATE OR REPLACE FUNCTION val_model_call_image_input_is_coherent()
RETURNS trigger AS $$
DECLARE
    expected text;
BEGIN
    -- A BEFORE ROW trigger runs ahead of the table's CHECK constraints, so this
    -- steps aside when the kind/representation pairing is what is wrong: each
    -- rule then reports its own violation instead of masking the other's.
    IF (NEW.input_kind = 'representation') <> (NEW.representation_id IS NOT NULL) THEN
        RETURN NEW;
    END IF;
    IF NEW.input_kind = 'original' THEN
        SELECT sha256 INTO expected FROM attachments WHERE id = NEW.attachment_id;
    ELSE
        SELECT sha256 INTO expected
          FROM attachment_representations WHERE id = NEW.representation_id;
    END IF;
    IF expected IS DISTINCT FROM NEW.transmitted_sha256 THEN
        RAISE EXCEPTION
            'transmitted_sha256 does not match the % it names',
            NEW.input_kind;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


def _guard(table: str) -> None:
    """The standing Layer 0 guards: no hard delete, no truncate, no update."""
    op.execute(
        f"CREATE TRIGGER {table}_forbid_hard_delete "
        f"BEFORE DELETE OR TRUNCATE ON {table} "
        "FOR EACH STATEMENT EXECUTE FUNCTION val_forbid_hard_delete()"
    )
    op.execute(
        f"CREATE TRIGGER {table}_rows_are_evidence BEFORE UPDATE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION val_rows_are_evidence()"
    )


def upgrade() -> None:
    """Create the substrate: six append-only tables, their integrity, their guards."""
    uuid = postgresql.UUID(as_uuid=True)
    now = sa.text("now()")
    uuidv7 = sa.text("uuidv7()")

    # Created once, here, then referenced by the columns: `create_type=False` so
    # that building a table does not try to create a type that already exists
    # (the 0013 precedent).
    bind = op.get_bind()
    for name, values in (
        ("attachment_act_classification", ACT_CLASSIFICATIONS),
        ("attachment_processing_event", PROCESSING_EVENTS),
        ("model_call_image_input_kind", INPUT_KINDS),
    ):
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=False)
    act_classification = postgresql.ENUM(
        *ACT_CLASSIFICATIONS, name="attachment_act_classification", create_type=False
    )
    processing_event = postgresql.ENUM(
        *PROCESSING_EVENTS, name="attachment_processing_event", create_type=False
    )
    input_kind = postgresql.ENUM(
        *INPUT_KINDS, name="model_call_image_input_kind", create_type=False
    )

    # --- §3.1 blobs — content addressing, enforced ------------------------------------
    op.create_table(
        "blobs",
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("bytes", postgresql.BYTEA(), nullable=False),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=now
        ),
        sa.PrimaryKeyConstraint("sha256", name="pk_blobs"),
        # The key is the content's digest. Not a convention — a constraint.
        sa.CheckConstraint("sha256 = encode(sha256(bytes), 'hex')", name="sha256_is_the_digest"),
        sa.CheckConstraint("byte_size = length(bytes)", name="byte_size_is_the_length"),
        sa.CheckConstraint("byte_size > 0", name="byte_size_positive"),
        # Established from the bytes by the admission preflight, never from a filename.
        # Deliberately not a closed vocabulary: documents, audio and video inherit
        # this store, and policy — not the byte store — decides what is admissible.
        sa.CheckConstraint(
            "media_type ~ '^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$'",
            name="media_type_is_a_media_type",
        ),
    )

    # --- §3.2 attachments — the immutable original ------------------------------------
    op.create_table(
        "attachments",
        sa.Column("id", uuid, nullable=False, server_default=uuidv7),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=now
        ),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_attachments"),
        # One content instance per distinct bytes (§3.2).
        sa.UniqueConstraint("sha256", name="uq_attachments_sha256"),
        sa.ForeignKeyConstraint(["sha256"], ["blobs.sha256"], name="fk_attachments_sha256"),
    )

    # --- §3.3 message_attachments — the act -------------------------------------------
    op.create_table(
        "message_attachments",
        sa.Column("id", uuid, nullable=False, server_default=uuidv7),
        sa.Column(
            "attached_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=now
        ),
        sa.Column("message_id", uuid, nullable=False),
        sa.Column("attachment_id", uuid, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("given_filename", sa.Text(), nullable=False),
        sa.Column("stated_classification", act_classification, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_message_attachments"),
        sa.UniqueConstraint(
            "message_id", "position", name="uq_message_attachments_message_position"
        ),
        # §5.3a — lets an input row's act be tied to its own attachment by a key,
        # not by application care.
        sa.UniqueConstraint("id", "attachment_id", name="uq_message_attachments_id_attachment"),
        sa.CheckConstraint("position > 0", name="position_positive"),
        sa.CheckConstraint("length(btrim(given_filename)) > 0", name="given_filename_present"),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name="fk_message_attachments_message_id"
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id"], ["attachments.id"], name="fk_message_attachments_attachment_id"
        ),
    )
    op.create_index("ix_message_attachments_message_id", "message_attachments", ["message_id"])
    op.execute(ACT_COHERENCE)
    op.execute(
        "CREATE TRIGGER message_attachments_is_coherent BEFORE INSERT ON message_attachments "
        "FOR EACH ROW EXECUTE FUNCTION val_message_attachment_is_coherent()"
    )

    # --- §3.4 attachment_representations — typed derived views -------------------------
    op.create_table(
        "attachment_representations",
        sa.Column("id", uuid, nullable=False, server_default=uuidv7),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=now
        ),
        sa.Column("attachment_id", uuid, nullable=False),
        sa.Column("parent_representation_id", uuid, nullable=True),
        sa.Column("representation_type", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("locator_ordinal", sa.Integer(), nullable=True),
        sa.Column("locator_region", sa.Text(), nullable=True),
        sa.Column("derived_by", sa.Text(), nullable=False),
        sa.Column("model_config_id", uuid, nullable=True),
        sa.Column("model_call_id", uuid, nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_attachment_representations"),
        # §5.1 and §5.3 — the device that keeps one file's tree one file's tree.
        sa.UniqueConstraint(
            "id", "attachment_id", name="uq_attachment_representations_id_attachment"
        ),
        sa.CheckConstraint(
            "representation_type IN ('" + "', '".join(REPRESENTATION_TYPES) + "')",
            name="representation_type_declared",
        ),
        # §5.2 — no self-parent; cycles are impossible given insert-only rows
        # and a parent that must already exist.
        sa.CheckConstraint(
            "parent_representation_id IS NULL OR parent_representation_id <> id",
            name="no_self_parent",
        ),
        sa.CheckConstraint(
            "locator_ordinal IS NULL OR locator_ordinal > 0",
            name="locator_ordinal_positive",
        ),
        sa.CheckConstraint("length(btrim(derived_by)) > 0", name="derived_by_present"),
        # §3.4 — both non-null exactly when a model produced the representation.
        sa.CheckConstraint(
            "(model_config_id IS NULL) = (model_call_id IS NULL)",
            name="model_provenance_is_paired",
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id"],
            ["attachments.id"],
            name="fk_attachment_representations_attachment_id",
        ),
        sa.ForeignKeyConstraint(
            ["sha256"], ["blobs.sha256"], name="fk_attachment_representations_sha256"
        ),
        sa.ForeignKeyConstraint(
            ["parent_representation_id", "attachment_id"],
            ["attachment_representations.id", "attachment_representations.attachment_id"],
            name="fk_attachment_representations_parent",
        ),
        sa.ForeignKeyConstraint(
            ["model_call_id"],
            ["model_calls.id"],
            name="fk_attachment_representations_model_call_id",
        ),
    )
    op.create_index(
        "ix_attachment_representations_attachment_id",
        "attachment_representations",
        ["attachment_id"],
    )

    # --- §3.5 attachment_processing_events — attempts, honestly ------------------------
    op.create_table(
        "attachment_processing_events",
        sa.Column("id", uuid, nullable=False, server_default=uuidv7),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=now
        ),
        sa.Column("attachment_id", uuid, nullable=False),
        sa.Column("attempt_id", uuid, nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("event", processing_event, nullable=False),
        sa.Column("representation_id", uuid, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_attachment_processing_events"),
        sa.CheckConstraint(
            "intent IN ('" + "', '".join(PROCESSING_INTENTS) + "')",
            name="intent_declared",
        ),
        # §3.5 rule 4 — `failed` requires `error`, and nothing else carries one.
        sa.CheckConstraint(
            "(event = 'failed') = (error IS NOT NULL)",
            name="failed_states_why",
        ),
        # Owner correction, 20 September 2026, applied before this migration ever
        # touched the live store. The rule is now stated in both directions: a
        # SUCCEEDED derivation must name the representation it produced, and
        # nothing else may name one. Recording `derive:model_input_image
        # succeeded` with no representation would assert that a derivation
        # happened when none did. `verify` keeps its own meaning: it succeeds
        # without producing anything, and the database says so rather than
        # forcing an invented representation onto it.
        sa.CheckConstraint(
            "CASE WHEN event = 'succeeded' AND intent LIKE 'derive:%' "
            "THEN representation_id IS NOT NULL ELSE representation_id IS NULL END",
            name="succeeded_derivation_produces",
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id"],
            ["attachments.id"],
            name="fk_attachment_processing_events_attachment_id",
        ),
        # §3.5 rule 5 — a produced representation belongs to the same attachment.
        sa.ForeignKeyConstraint(
            ["representation_id", "attachment_id"],
            ["attachment_representations.id", "attachment_representations.attachment_id"],
            name="fk_attachment_processing_events_representation",
        ),
    )
    op.create_index(
        "ix_attachment_processing_events_attachment_id",
        "attachment_processing_events",
        ["attachment_id"],
    )
    # §3.5 rules 1 and 2, as indexes rather than hope.
    op.execute(
        "CREATE UNIQUE INDEX ux_attachment_processing_events_one_started "
        "ON attachment_processing_events (attempt_id) WHERE event = 'started'"
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_attachment_processing_events_one_terminal "
        "ON attachment_processing_events (attempt_id) WHERE event IN ('succeeded', 'failed')"
    )
    op.execute(PROCESSING_COHERENCE)
    op.execute(
        "CREATE TRIGGER attachment_processing_events_is_coherent "
        "BEFORE INSERT ON attachment_processing_events "
        "FOR EACH ROW EXECUTE FUNCTION val_attachment_processing_event_is_coherent()"
    )

    # --- §3.6 model_call_image_inputs — the binding ------------------------------------
    op.create_table(
        "model_call_image_inputs",
        sa.Column("id", uuid, nullable=False, server_default=uuidv7),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=now
        ),
        sa.Column("model_call_id", uuid, nullable=False),
        sa.Column("message_attachment_id", uuid, nullable=False),
        sa.Column("attachment_id", uuid, nullable=False),
        sa.Column("input_kind", input_kind, nullable=False),
        sa.Column("representation_id", uuid, nullable=True),
        sa.Column("transmitted_sha256", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("provider_options", postgresql.JSONB(), nullable=False),
        sa.Column("stated_classification", act_classification, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_model_call_image_inputs"),
        sa.UniqueConstraint(
            "model_call_id", "position", name="uq_model_call_image_inputs_model_call_position"
        ),
        sa.CheckConstraint("position > 0", name="position_positive"),
        # §3.6 — required iff `representation`, NULL iff `original`.
        sa.CheckConstraint(
            "(input_kind = 'representation') = (representation_id IS NOT NULL)",
            name="kind_matches_representation",
        ),
        # §8 — the dimensions that priced the call, read from decoded bytes.
        sa.CheckConstraint("width > 0 AND height > 0", name="dimensions_positive"),
        sa.CheckConstraint(
            "media_type ~ '^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$'",
            name="media_type_is_a_media_type",
        ),
        sa.ForeignKeyConstraint(
            ["model_call_id"], ["model_calls.id"], name="fk_model_call_image_inputs_model_call_id"
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id"], ["attachments.id"], name="fk_model_call_image_inputs_attachment_id"
        ),
        sa.ForeignKeyConstraint(
            ["transmitted_sha256"],
            ["blobs.sha256"],
            name="fk_model_call_image_inputs_transmitted_sha256",
        ),
        # §5.3 and §5.3a — the representation and the act both belong to this
        # row's own attachment, by key.
        sa.ForeignKeyConstraint(
            ["representation_id", "attachment_id"],
            ["attachment_representations.id", "attachment_representations.attachment_id"],
            name="fk_model_call_image_inputs_representation",
        ),
        sa.ForeignKeyConstraint(
            ["message_attachment_id", "attachment_id"],
            ["message_attachments.id", "message_attachments.attachment_id"],
            name="fk_model_call_image_inputs_act",
        ),
    )
    op.create_index(
        "ix_model_call_image_inputs_model_call_id", "model_call_image_inputs", ["model_call_id"]
    )
    op.execute(INPUT_COHERENCE)
    op.execute(
        "CREATE TRIGGER model_call_image_inputs_is_coherent "
        "BEFORE INSERT ON model_call_image_inputs "
        "FOR EACH ROW EXECUTE FUNCTION val_model_call_image_input_is_coherent()"
    )

    for table in TABLES:
        _guard(table)


def downgrade() -> None:
    """Refuse once any attachment evidence exists; otherwise remove the substrate."""
    bind = op.get_bind()
    held = {
        table: bind.execute(sa.text(f"select count(*) from {table}")).scalar_one()  # noqa: S608
        for table in TABLES
    }
    if any(held.values()):
        raise RuntimeError(
            "the attachment substrate holds evidence "
            f"({', '.join(f'{t}={n}' for t, n in held.items() if n)}); a downgrade would "
            "destroy admitted bytes and the record of what was bound to which call. Refused."
        )
    for table in reversed(TABLES):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_rows_are_evidence ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_forbid_hard_delete ON {table}")
    op.execute(
        "DROP TRIGGER IF EXISTS model_call_image_inputs_is_coherent ON model_call_image_inputs"
    )
    op.execute("DROP FUNCTION IF EXISTS val_model_call_image_input_is_coherent()")
    op.drop_index("ix_model_call_image_inputs_model_call_id", table_name="model_call_image_inputs")
    op.drop_table("model_call_image_inputs")

    op.execute(
        "DROP TRIGGER IF EXISTS attachment_processing_events_is_coherent "
        "ON attachment_processing_events"
    )
    op.execute("DROP FUNCTION IF EXISTS val_attachment_processing_event_is_coherent()")
    op.execute("DROP INDEX IF EXISTS ux_attachment_processing_events_one_terminal")
    op.execute("DROP INDEX IF EXISTS ux_attachment_processing_events_one_started")
    op.drop_index(
        "ix_attachment_processing_events_attachment_id", table_name="attachment_processing_events"
    )
    op.drop_table("attachment_processing_events")

    op.drop_index(
        "ix_attachment_representations_attachment_id", table_name="attachment_representations"
    )
    op.drop_table("attachment_representations")

    op.execute("DROP TRIGGER IF EXISTS message_attachments_is_coherent ON message_attachments")
    op.execute("DROP FUNCTION IF EXISTS val_message_attachment_is_coherent()")
    op.drop_index("ix_message_attachments_message_id", table_name="message_attachments")
    op.drop_table("message_attachments")

    op.drop_table("attachments")
    op.drop_table("blobs")
    for name in (
        "model_call_image_input_kind",
        "attachment_processing_event",
        "attachment_act_classification",
    ):
        op.execute(f"DROP TYPE IF EXISTS {name}")
