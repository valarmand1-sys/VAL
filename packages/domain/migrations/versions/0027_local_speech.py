"""Val's voice, on the record — owner execution order, 22 September 2026.

Two append-only tables, and the split between them is the point.

    speech_voices       who Val is when she speaks, and where that came from.
                        The canonical locally designed reference by digest, its
                        transcript, the frozen textual description it was
                        designed from, and the VoiceDesign model that produced
                        it. Written once per voice, not once per sentence,
                        because the voice is an identity rather than a setting.

    speech_generations  one utterance: the exact final text that was spoken, the
                        Base model that spoke it, the reusable clone prompt it
                        was conditioned on, and the waveform it produced.

Nothing here is a `model_calls` row, for the same reason `perception_runs` is
not: that table accounts for calls that buy thinking, and this buys none. And
nothing here holds wording Val did not already settle — `final_text` is her
finished answer, copied verbatim, so a reader can check months later that the
voice said exactly what the record says she said.

Both tables are under the standing Layer 0 guards: no hard delete, no truncate,
no update.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_local_speech"
down_revision: str | None = "0026_local_audio_perception"
branch_labels: None = None
depends_on: None = None


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
    """The voice, and what it said."""
    uuid = postgresql.UUID(as_uuid=True)
    now = sa.text("now()")
    uuidv7 = sa.text("uuidv7()")

    # --- the voice --------------------------------------------------------------------
    op.create_table(
        "speech_voices",
        sa.Column("id", uuid, nullable=False, server_default=uuidv7),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=now
        ),
        sa.Column("name", sa.Text(), nullable=False),
        # The canonical locally generated reference, by digest. The bytes live
        # on disk at a fixed governed path; the digest is what makes a later run
        # provably the same voice rather than a similar one.
        sa.Column("reference_sha256", sa.Text(), nullable=False),
        sa.Column("reference_bytes", sa.BigInteger(), nullable=False),
        sa.Column("reference_sample_rate", sa.Integer(), nullable=False),
        sa.Column("reference_duration_seconds", sa.Numeric(10, 3), nullable=False),
        # The transcript supplied explicitly to the clone path. Held in full and
        # by digest: no automatic transcription produced it, and the record
        # should be able to show the words as well as prove they are unchanged.
        sa.Column("reference_text", sa.Text(), nullable=False),
        sa.Column("reference_text_sha256", sa.Text(), nullable=False),
        # The frozen textual description the voice was designed from — the
        # nearest thing this voice has to an origin story, and the only thing a
        # future rebuild would need.
        sa.Column("voice_description", sa.Text(), nullable=False),
        sa.Column("voice_description_sha256", sa.Text(), nullable=False),
        # The VoiceDesign model that produced the reference, distinct from the
        # Base model that speaks with it.
        sa.Column("designed_by_model", sa.Text(), nullable=False),
        sa.Column("designed_by_revision", sa.Text(), nullable=False),
        sa.Column("designed_by_quantization", sa.Text(), nullable=False),
        sa.Column("designed_by_runtime", sa.Text(), nullable=False),
        sa.Column("designed_generation", postgresql.JSONB(), nullable=False),
        # Where the reference came from, and what is NOT claimed about it. Both
        # in the record rather than in a commit message, because both are things
        # a reader in a year will need and will not otherwise have.
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("identity_claim", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_speech_voices"),
        # One row per distinct reference: re-registering the same voice is the
        # same voice, and two rows would invite two answers to "which voice?".
        sa.UniqueConstraint("reference_sha256", name="uq_speech_voices_reference"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="name_present"),
        sa.CheckConstraint("length(reference_sha256) = 64", name="reference_is_a_digest"),
        sa.CheckConstraint("length(btrim(reference_text)) > 0", name="reference_text_present"),
        sa.CheckConstraint(
            "length(btrim(voice_description)) > 0", name="voice_description_present"
        ),
        sa.CheckConstraint("reference_bytes > 0", name="reference_bytes_positive"),
        sa.CheckConstraint("reference_sample_rate > 0", name="reference_sample_rate_positive"),
    )
    _guard("speech_voices")

    # --- what it said -----------------------------------------------------------------
    op.create_table(
        "speech_generations",
        sa.Column("id", uuid, nullable=False, server_default=uuidv7),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=now
        ),
        sa.Column("voice_id", uuid, nullable=False),
        # The message whose finished text was spoken, when there is one. NULL for
        # a house-internal utterance (an acceptance run), which is a different
        # thing from an utterance with no source and should read differently.
        sa.Column("message_id", uuid, nullable=True),
        sa.Column("model_config_id", uuid, nullable=False),
        # Val's finished words, verbatim, and their digest. The provider spoke
        # these and decided none of them.
        sa.Column("final_text", sa.Text(), nullable=False),
        sa.Column("final_text_sha256", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model_identifier", sa.Text(), nullable=False),
        sa.Column("model_revision", sa.Text(), nullable=False),
        sa.Column("quantization", sa.Text(), nullable=False),
        sa.Column("runtime", sa.Text(), nullable=False),
        sa.Column("runtime_version", sa.Text(), nullable=False),
        sa.Column("generation", postgresql.JSONB(), nullable=False),
        # The reusable identity anchor this utterance was conditioned on. Equal
        # across utterances is the proof that the voice did not drift.
        sa.Column("clone_prompt_sha256", sa.Text(), nullable=False),
        # The waveform: its digest, where it was staged, and what it is.
        sa.Column("audio_sha256", sa.Text(), nullable=False),
        sa.Column("audio_path", sa.Text(), nullable=False),
        sa.Column("audio_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sample_rate", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Numeric(10, 3), nullable=False),
        sa.Column("local", sa.Boolean(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_speech_generations"),
        sa.CheckConstraint("length(btrim(final_text)) > 0", name="final_text_present"),
        sa.CheckConstraint("length(final_text_sha256) = 64", name="final_text_is_a_digest"),
        sa.CheckConstraint("length(audio_sha256) = 64", name="audio_is_a_digest"),
        sa.CheckConstraint("audio_bytes > 0", name="audio_bytes_positive"),
        sa.CheckConstraint("sample_rate > 0", name="sample_rate_positive"),
        sa.CheckConstraint("duration_seconds > 0", name="duration_positive"),
        sa.CheckConstraint("elapsed_ms >= 0", name="elapsed_not_negative"),
        # Local speech bills nothing, said as a constraint rather than a habit.
        sa.CheckConstraint("(local AND cost_usd = 0) OR NOT local", name="local_costs_nothing"),
        sa.ForeignKeyConstraint(
            ["voice_id"], ["speech_voices.id"], name="fk_speech_generations_voice"
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name="fk_speech_generations_message"
        ),
    )
    op.create_index("ix_speech_generations_voice", "speech_generations", ["voice_id"])
    op.create_index("ix_speech_generations_message", "speech_generations", ["message_id"])
    _guard("speech_generations")


def downgrade() -> None:
    """Reversible, as WP-0.2 requires."""
    for table in ("speech_generations", "speech_voices"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_rows_are_evidence ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_forbid_hard_delete ON {table}")
    op.drop_table("speech_generations")
    op.drop_table("speech_voices")
