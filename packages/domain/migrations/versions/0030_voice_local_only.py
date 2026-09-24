"""The live-voice seal — owner execution order, 24 September 2026.

Voice work package 3 §1.5, §2.1, §2.2 and §2.3. Two facts the store could not
previously hold, both of them owner rulings rather than engineering conveniences.

**A conversation can be local-only.** Once live-microphone-derived text becomes a
canonical message in a conversation, nothing from that conversation may ever be
transmitted off this machine — not by that turn, not by a later typed turn, and
not by being recalled somewhere else. `conversation_egress_seals` is that fact,
one row per conversation, append-only, written **in the same transaction as the
message that causes it** so no observable state exists in which the message is
present and the seal is not.

It is deliberately *not* a column on `conversations`, and deliberately *not*
`Classification.RESTRICTED`. Restricted would either strand a spoken turn with no
eligible route — the local configurations are registered as Restricted-ineligible
— or force local eligibility to be widened to Restricted, which is a reserved
owner ruling nobody has made. It would also change how spoken conversations are
recalled, and a spoken turn is an ordinary turn (§1.6). Only egress differs, so
only egress is recorded.

The seal is not created by turning Voice on. The transient rule — that a live
Voice session blocks egress for as long as it lasts — is live state in one
process, and a durable row asserting "Voice is on" that survived a crash would be
precisely the stored preference §4.2 forbids.

**A classification can honestly not have run.** A sealed turn may not call the
cloud classifier, so its consequentiality was never assessed. Val's doctrine is
that absence and a negative result are different states, and `classifications`
could only say `not_consequential`, `uncertain`, `consequential`, or
"unestablished after N attempts" — all four of which claim an attempt was made.
Its `attempts >= 1` check said so out loud. So `not_run_reason` is added, the
check is relaxed *only* where that reason is present, and a constraint holds a
not-run row to the truth: no attempts, no verdict, no model calls.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030_voice_local_only"
down_revision: str | None = "0029_speech_delivery"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    """The durable seal, a classification that can say it never ran, and physical sound."""
    uuid = postgresql.UUID(as_uuid=True)

    # --- a conversation the machine may not speak of -----------------------------------
    op.create_table(
        "conversation_egress_seals",
        sa.Column("id", uuid, nullable=False, server_default=sa.text("uuidv7()")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # One row per conversation: the seal is a fact about the conversation, and
        # applying it twice is not a second fact.
        sa.Column("conversation_id", uuid, nullable=False),
        # The canonical message that caused it — the first live-microphone-derived
        # text in this conversation. Recorded so the seal can always answer *why*
        # rather than merely *that*, and so the atomicity rule is checkable after
        # the fact: this message and this row were committed together.
        sa.Column("message_id", uuid, nullable=False),
        # Which route to canonical applied it (§2.1's "every route" rule): an
        # ordinary finalized utterance, the resume-before-delivery merge, or an
        # owner-adopted recovered fragment.
        sa.Column("applied_by", sa.Text(), nullable=False),
        # The owner ruling in its own words, carried with the row rather than
        # left in a document the database cannot see.
        sa.Column("reason", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_conversation_egress_seals"),
        sa.UniqueConstraint("conversation_id", name="uq_conversation_egress_seals_conversation"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_conversation_egress_seals_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name="fk_conversation_egress_seals_message"
        ),
        sa.CheckConstraint(
            "applied_by IN ('utterance_finalized', 'resume_merge', 'recovered_fragment_adopted')",
            name="applied_by_is_a_known_route",
        ),
        sa.CheckConstraint("length(reason) > 0", name="a_seal_says_why"),
    )
    op.create_index(
        "ix_conversation_egress_seals_message", "conversation_egress_seals", ["message_id"]
    )
    op.execute(
        "CREATE TRIGGER conversation_egress_seals_forbid_hard_delete "
        "BEFORE DELETE OR TRUNCATE ON conversation_egress_seals "
        "FOR EACH STATEMENT EXECUTE FUNCTION val_forbid_hard_delete()"
    )
    # There is no unseal control (§1.5), and an UPDATE would be one by another
    # name: the row is evidence, not settings.
    op.execute(
        "CREATE TRIGGER conversation_egress_seals_rows_are_evidence "
        "BEFORE UPDATE ON conversation_egress_seals "
        "FOR EACH ROW EXECUTE FUNCTION val_rows_are_evidence()"
    )

    # --- what the speakers actually did -------------------------------------------------
    #
    # Work package 2 recorded delivery up to the point where audio reached an
    # in-process sink. That is not the same fact as **sound in the room**, and the
    # difference is exactly what work package 3 adds: bytes handed to a desktop are
    # not bytes a speaker played. One row per transition, append-only, so a segment
    # that was handed over and never played cannot later read as heard.
    op.create_table(
        "speech_playbacks",
        sa.Column("id", uuid, nullable=False, server_default=sa.text("uuidv7()")),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("message_id", uuid, nullable=False),
        sa.Column("voice_session_id", uuid, nullable=True),
        # Which segment of the answer this is, counted from one, matching
        # `speech_generations.segment_index`.
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("event", sa.Integer(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        # The text this segment spoke, so the physical record can be compared with
        # the delivered prefix without joining through generation.
        sa.Column("text", sa.Text(), nullable=False),
        # Milliseconds from the segment being offered to the desktop to the state
        # this row records. NULL on the offering row itself, which is the origin.
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        # Why an interrupted or failed playback ended that way; required for those
        # two and forbidden otherwise, exactly as delivery does it.
        sa.Column("reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_speech_playbacks"),
        sa.UniqueConstraint(
            "message_id", "segment_index", "event", name="uq_speech_playbacks_event"
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], name="fk_speech_playbacks_message"
        ),
        sa.ForeignKeyConstraint(
            ["voice_session_id"], ["voice_sessions.id"], name="fk_speech_playbacks_session"
        ),
        sa.CheckConstraint(
            "state IN ('available_to_desktop', 'playback_started', 'playback_completed', "
            "'playback_interrupted', 'playback_failed')",
            name="state_is_known",
        ),
        sa.CheckConstraint(
            "(state IN ('playback_interrupted', 'playback_failed')) = (reason IS NOT NULL)",
            name="a_state_and_its_reason_agree",
        ),
        sa.CheckConstraint("event > 0", name="event_is_counted_from_one"),
        sa.CheckConstraint("segment_index > 0", name="segment_index_is_counted_from_one"),
        sa.CheckConstraint("elapsed_ms IS NULL OR elapsed_ms >= 0", name="elapsed_is_not_negative"),
    )
    op.create_index("ix_speech_playbacks_message", "speech_playbacks", ["message_id"])
    op.execute(
        "CREATE TRIGGER speech_playbacks_forbid_hard_delete "
        "BEFORE DELETE OR TRUNCATE ON speech_playbacks "
        "FOR EACH STATEMENT EXECUTE FUNCTION val_forbid_hard_delete()"
    )
    op.execute(
        "CREATE TRIGGER speech_playbacks_rows_are_evidence BEFORE UPDATE ON speech_playbacks "
        "FOR EACH ROW EXECUTE FUNCTION val_rows_are_evidence()"
    )

    # --- a classification that never ran, said so ---------------------------------------
    op.add_column("classifications", sa.Column("not_run_reason", sa.Text(), nullable=True))
    # The original check asserted that classification was attempted at least
    # once, which was true of every row that could then exist. It is relaxed
    # only for a row that positively states it did not run.
    # The bare name: the metadata naming convention supplies the
    # `ck_classifications_` prefix, and passing the full name would ask for it
    # twice.
    op.drop_constraint(
        "classification_attempted_at_least_once",
        "classifications",
        type_="check",
    )
    op.create_check_constraint(
        "attempted_once_or_says_it_did_not",
        "classifications",
        "attempts >= 1 OR not_run_reason IS NOT NULL",
    )
    # And a not-run row may not also carry the traces of a run. Without this the
    # new column would be a comment rather than a state.
    op.create_check_constraint(
        "not_run_claims_nothing",
        "classifications",
        "not_run_reason IS NULL OR ("
        "attempts = 0 AND verdict IS NULL AND established = false "
        "AND resolving_model_call_id IS NULL AND cardinality(model_call_ids) = 0)",
    )


def downgrade() -> None:
    """Reversible, as WP-0.2 requires.

    The `attempts >= 1` check is restored only when no row relies on the
    relaxation. A not-run row cannot be given an attempt to satisfy the old
    constraint — inventing a classifier call that never happened is the exact
    fabrication §2.3 forbids — so the downgrade stops and says so.
    """
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM classifications WHERE not_run_reason IS NOT NULL) THEN "
        "RAISE EXCEPTION 'Refusing to downgrade: classifications exist that record NOT RUN. "
        "Restoring attempts >= 1 would require inventing a classifier attempt that never "
        "happened (work package 3 section 2.3). Remove those rows deliberately first.'; "
        "END IF; END $$"
    )
    op.drop_constraint("not_run_claims_nothing", "classifications", type_="check")
    op.drop_constraint(
        "attempted_once_or_says_it_did_not",
        "classifications",
        type_="check",
    )
    op.create_check_constraint(
        "classification_attempted_at_least_once",
        "classifications",
        "attempts >= 1",
    )
    op.drop_column("classifications", "not_run_reason")

    op.execute("DROP TRIGGER IF EXISTS speech_playbacks_rows_are_evidence ON speech_playbacks")
    op.execute("DROP TRIGGER IF EXISTS speech_playbacks_forbid_hard_delete ON speech_playbacks")
    op.drop_table("speech_playbacks")

    op.execute(
        "DROP TRIGGER IF EXISTS conversation_egress_seals_rows_are_evidence "
        "ON conversation_egress_seals"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS conversation_egress_seals_forbid_hard_delete "
        "ON conversation_egress_seals"
    )
    op.drop_table("conversation_egress_seals")
