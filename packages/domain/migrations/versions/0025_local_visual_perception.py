"""Local visual perception: the record of what Val looked at, and what she saw.

Owner ruling, Lord Armand, 22 September 2026, on Qwen3.5-9B's qualification.
Val stops handing raw media to a cognition provider and starts perceiving it
locally; the cognition provider receives grounded observations. §26 of that
order says what must be persisted, and these three tables are that list, made
structural.

**Why this is not a `model_calls` row.** A perception run is a different kind of
act from a cognition call. `model_calls` accounts for calls that buy thinking —
tokens in, tokens out, reservations, cache splits, metered rates — and a
perception run buys none of that. What it produces is *evidence derived from
source media plus the owner's question*, and evidence has to say what it came
from. Forcing it into the cognition table would have meant either a task type
that lies about what happened or six nullable columns on the most load-bearing
table in the house. Neither is worth it, and neither is permitted: §5 of the
Track C constraint still forbids a new column on the seven core tables.

    perception_runs       one run: the provider, the artifact, the exact prompt,
                          the owner's question, what it cost (nothing), where it
                          ran (here).
    perception_sources    which media it looked at, by digest, in order — the
                          SOURCE → OBSERVATION relationship.
    perception_handoffs   which cognition calls received it — the OBSERVATION →
                          COGNITION relationship, and the proof that a
                          consequential turn's blind position and final answer
                          were grounded in the same frozen perception.

All three are append-only under the standing Layer 0 guards: no hard delete, no
truncate, no update. A perception record that could be edited afterwards would
not be evidence of anything.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_local_visual_perception"
down_revision: str | None = "0024_attachment_substrate"
branch_labels: None = None
depends_on: None = None

#: The admitted modalities, and only those. `audio` is absent because it is not
#: qualified and not admitted (§27): a value here would be a capability waiting
#: for someone to use it.
MODALITIES = ("image", "video")

#: How the cognition provider was told to treat the current turn's media.
#: `perceived` is the state this ruling adds; `bound` is named here only so the
#: two can be told apart in the record, and its meaning is untouched — raw media
#: supplied directly to the cognition provider, which is what Track C did and
#: what every historical row means.
PERCEPTION_STATES = ("perceived", "bound")


#: A source row must belong to the same attachment as the act it names. The same
#: device §5.3a uses: the relationship is a key, not application care.
SOURCE_COHERENCE = """
CREATE OR REPLACE FUNCTION val_perception_source_is_coherent() RETURNS trigger AS $$
DECLARE
    act_attachment uuid;
    act_sha text;
BEGIN
    IF NEW.message_attachment_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT ma.attachment_id, a.sha256 INTO act_attachment, act_sha
      FROM message_attachments ma JOIN attachments a ON a.id = ma.attachment_id
     WHERE ma.id = NEW.message_attachment_id;
    IF act_attachment IS NULL THEN
        RAISE EXCEPTION 'perception source names attachment act % , which does not exist',
            NEW.message_attachment_id;
    END IF;
    IF NEW.attachment_id IS DISTINCT FROM act_attachment THEN
        RAISE EXCEPTION 'perception source names act % and attachment %, which are not one file',
            NEW.message_attachment_id, NEW.attachment_id;
    END IF;
    IF NEW.sha256 IS DISTINCT FROM act_sha THEN
        RAISE EXCEPTION 'perception source digest % is not the digest of the attachment it names',
            NEW.sha256;
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
    """Three append-only tables, their integrity, and their guards."""
    uuid = postgresql.UUID(as_uuid=True)
    now = sa.text("now()")
    uuidv7 = sa.text("uuidv7()")

    bind = op.get_bind()
    for name, values in (
        ("perception_modality", MODALITIES),
        ("perception_state", PERCEPTION_STATES),
    ):
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=False)
    modality = postgresql.ENUM(*MODALITIES, name="perception_modality", create_type=False)
    state = postgresql.ENUM(*PERCEPTION_STATES, name="perception_state", create_type=False)

    # --- the run ----------------------------------------------------------------------
    op.create_table(
        "perception_runs",
        sa.Column("id", uuid, nullable=False, server_default=uuidv7),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=now
        ),
        sa.Column("conversation_id", uuid, nullable=False),
        # The turn this perception belongs to. One perception per consequential
        # turn is enforced by the unique constraint below: §22's "run perception
        # once" is a key, not a convention.
        sa.Column("message_id", uuid, nullable=False),
        sa.Column("model_config_id", uuid, nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model_identifier", sa.Text(), nullable=False),
        sa.Column("model_revision", sa.Text(), nullable=False),
        sa.Column("quantization", sa.Text(), nullable=False),
        sa.Column("runtime", sa.Text(), nullable=False),
        sa.Column("runtime_version", sa.Text(), nullable=False),
        # The generation settings actually in force, read back from the runtime.
        sa.Column("generation", postgresql.JSONB(), nullable=False),
        # The owner's actual question, and the exact instruction transmitted.
        # Both, because the second is derived from the first and a record that
        # holds only the derivation cannot show what it was derived from.
        sa.Column("owner_question", sa.Text(), nullable=False),
        sa.Column("perception_prompt", sa.Text(), nullable=False),
        sa.Column("observation", sa.Text(), nullable=False),
        sa.Column("current_perception_state", state, nullable=False),
        sa.Column("local", sa.Boolean(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("reasoning_separated", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_perception_runs"),
        # §22 — one perception per turn, frozen and reused. Two rows for one
        # message would mean two cognition calls could be grounded differently.
        sa.UniqueConstraint("message_id", name="uq_perception_runs_message"),
        sa.CheckConstraint("length(btrim(perception_prompt)) > 0", name="prompt_present"),
        sa.CheckConstraint("length(btrim(observation)) > 0", name="observation_present"),
        sa.CheckConstraint("duration_ms >= 0", name="duration_not_negative"),
        # A local run bills nothing, and the record says so as a constraint
        # rather than as a habit. A metered perception route would be a
        # different ruling and would need a different shape.
        sa.CheckConstraint("(local AND cost_usd = 0) OR NOT local", name="local_costs_nothing"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], name="fk_perception_runs_conversation"
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], name="fk_perception_runs_message"),
    )
    op.create_index("ix_perception_runs_conversation", "perception_runs", ["conversation_id"])
    _guard("perception_runs")

    # --- what it looked at: SOURCE -> OBSERVATION -------------------------------------
    op.create_table(
        "perception_sources",
        sa.Column("id", uuid, nullable=False, server_default=uuidv7),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=now
        ),
        sa.Column("perception_run_id", uuid, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        # The act this medium arrived on, and the file it is. Nullable together
        # for a house-internal source that never came through an attachment; the
        # coherence trigger holds them to the same file whenever they are set.
        sa.Column("message_attachment_id", uuid, nullable=True),
        sa.Column("attachment_id", uuid, nullable=True),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("modality", modality, nullable=False),
        # Which representation was perceived. `original` for this slice: the
        # local runtime reads the admitted bytes and does its own preprocessing,
        # so nothing is derived for transmission the way a cloud route needs.
        sa.Column("representation", sa.Text(), nullable=False),
        # What was reported about THIS source. The run's `observation` is the
        # whole; this is the part, so a multi-image turn can say which
        # observation belongs to which file.
        sa.Column("observation", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_perception_sources"),
        sa.UniqueConstraint(
            "perception_run_id", "position", name="uq_perception_sources_run_position"
        ),
        sa.CheckConstraint("position > 0", name="position_positive"),
        sa.CheckConstraint("byte_size > 0", name="byte_size_positive"),
        sa.CheckConstraint("length(sha256) = 64", name="sha256_is_a_digest"),
        sa.CheckConstraint(
            "(message_attachment_id IS NULL) = (attachment_id IS NULL)",
            name="act_and_attachment_together",
        ),
        sa.ForeignKeyConstraint(
            ["perception_run_id"], ["perception_runs.id"], name="fk_perception_sources_run"
        ),
        sa.ForeignKeyConstraint(
            ["message_attachment_id"],
            ["message_attachments.id"],
            name="fk_perception_sources_act",
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id"], ["attachments.id"], name="fk_perception_sources_attachment"
        ),
    )
    op.create_index("ix_perception_sources_run", "perception_sources", ["perception_run_id"])
    op.execute(SOURCE_COHERENCE)
    op.execute(
        "CREATE TRIGGER perception_sources_is_coherent BEFORE INSERT ON perception_sources "
        "FOR EACH ROW EXECUTE FUNCTION val_perception_source_is_coherent()"
    )
    _guard("perception_sources")

    # --- who received it: OBSERVATION -> COGNITION ------------------------------------
    op.create_table(
        "perception_handoffs",
        sa.Column("id", uuid, nullable=False, server_default=uuidv7),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=now
        ),
        sa.Column("perception_run_id", uuid, nullable=False),
        sa.Column("model_call_id", uuid, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_perception_handoffs"),
        # One row per call. Two cognition calls on a consequential turn produce
        # two rows naming ONE run, which is exactly the proof §22 asks for.
        sa.UniqueConstraint(
            "perception_run_id", "model_call_id", name="uq_perception_handoffs_run_call"
        ),
        sa.ForeignKeyConstraint(
            ["perception_run_id"], ["perception_runs.id"], name="fk_perception_handoffs_run"
        ),
        sa.ForeignKeyConstraint(
            ["model_call_id"], ["model_calls.id"], name="fk_perception_handoffs_call"
        ),
    )
    op.create_index("ix_perception_handoffs_run", "perception_handoffs", ["perception_run_id"])
    op.create_index("ix_perception_handoffs_call", "perception_handoffs", ["model_call_id"])
    _guard("perception_handoffs")


def downgrade() -> None:
    """Reversible, as WP-0.2 requires. The guards go before the tables they guard."""
    for table in ("perception_handoffs", "perception_sources", "perception_runs"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_rows_are_evidence ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_forbid_hard_delete ON {table}")
    op.execute("DROP TRIGGER IF EXISTS perception_sources_is_coherent ON perception_sources")
    op.drop_table("perception_handoffs")
    op.drop_table("perception_sources")
    op.drop_table("perception_runs")
    op.execute("DROP FUNCTION IF EXISTS val_perception_source_is_coherent()")
    bind = op.get_bind()
    for name in ("perception_state", "perception_modality"):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
