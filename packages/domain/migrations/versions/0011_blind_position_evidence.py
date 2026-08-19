"""The blind position is durable evidence — WP-0.9, ruling of 19 August 2026.

`02-partner-systems.md` §4.1 requires the blind position to be *recorded before
step 3 begins*, and the `deliberations` row cannot carry it at that moment: the
record §4.7 describes is complete only when the outcome is known, and `0009`
made partial-insert-then-update unwritable on purpose. Until this migration the
position would have lived, between step 2 and resolution, only in process
memory and a log line.

Lord Armand's ruling: the blind position is the primary evidence that Val
formed a genuinely independent judgment — Layer 5 exists partly to determine
exactly that — and keeping the most load-bearing record in the least durable
place is backwards. It is captured as an **append-only evidence row**, on the
same footing as every other Layer 0 capture table. Not mutable interim state:
complete when written, no UPDATE, no hard delete.

## What is added

**`blind_positions`** — one row per blind call, persisted before the response
call is assembled: the exchange anchor (project derived from the conversation,
never supplied), the blind `model_calls` row it names, the persona revision
assembled into it (WP-0.5's 19 August 2026 amendment), the position /
confidence / reasoning as formed, what the strip step removed, the
enforced-or-contaminated ordering, and the §4.8 classification provenance.

**`deliberations.blind_position_id`** — the eventual deliberation names the
exact evidence it resolves. Nullable: a deliberation recorded manually, or one
whose exchange carried no preference to strip, has no blind call behind it.

Both guards reuse the standing functions: `val_forbid_hard_delete` (`0001`)
and `val_rows_are_evidence` (`0009`).

## Downgrade

Refuses once any blind position exists: dropping the table would destroy the
independence evidence outright. Clean on an empty database (CI).

Revision ID: 0011_blind_position_evidence
Revises: 0010_terminal_state_is_evidence
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_blind_position_evidence"
down_revision: str | None = "0010_terminal_state_is_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, values: tuple[str, ...]) -> postgresql.ENUM:
    """Reference an already-created type rather than creating it inline."""
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    """Create the evidence table, link deliberations to it, freeze both paths."""
    op.create_table(
        "blind_positions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_call_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("persona_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Text(), nullable=False),
        sa.Column(
            "confidence",
            _enum("deliberation_confidence", ("high", "medium", "low")),
            nullable=False,
        ),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("stripped_content", sa.Text(), nullable=False),
        sa.Column(
            "ordering",
            _enum("deliberation_ordering", ("enforced", "contaminated")),
            nullable=False,
        ),
        sa.Column(
            "classification",
            _enum("deliberation_classification", ("consequential", "uncertain")),
            nullable=False,
        ),
        sa.Column(
            "classified_by",
            _enum("deliberation_classified_by", ("automatic", "user", "val")),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_blind_positions"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_blind_positions_project_id",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_blind_positions_conversation_id",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name="fk_blind_positions_message_id",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["model_call_id"],
            ["model_calls.id"],
            name="fk_blind_positions_model_call_id",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["persona_id"],
            ["personas.id"],
            name="fk_blind_positions_persona_id",
            ondelete="NO ACTION",
        ),
    )

    op.add_column(
        "deliberations",
        sa.Column("blind_position_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_deliberations_blind_position_id",
        "deliberations",
        "blind_positions",
        ["blind_position_id"],
        ["id"],
        ondelete="NO ACTION",
    )

    # Same footing as every other capture table: §2.3's no-hard-delete, and
    # 0009's rows-are-evidence, both from the standing functions.
    op.execute(
        "CREATE TRIGGER blind_positions_forbid_hard_delete "
        "BEFORE DELETE OR TRUNCATE ON blind_positions "
        "FOR EACH STATEMENT EXECUTE FUNCTION val_forbid_hard_delete()"
    )
    op.execute(
        "CREATE TRIGGER blind_positions_rows_are_evidence "
        "BEFORE UPDATE ON blind_positions "
        "FOR EACH ROW EXECUTE FUNCTION val_rows_are_evidence()"
    )


def downgrade() -> None:
    """Remove the evidence table — refused once it holds evidence."""
    captured = op.get_bind().execute(sa.text("select count(*) from blind_positions")).scalar_one()
    if captured:
        raise RuntimeError(
            f"Refusing to downgrade: {captured} blind position(s) exist. This table "
            "is the primary evidence that Val formed independent judgments, and "
            "dropping it would destroy that evidence outright. This migration "
            "reverses cleanly only on an empty database."
        )
    op.execute("DROP TRIGGER IF EXISTS blind_positions_rows_are_evidence ON blind_positions")
    op.execute("DROP TRIGGER IF EXISTS blind_positions_forbid_hard_delete ON blind_positions")
    op.drop_constraint("fk_deliberations_blind_position_id", "deliberations", type_="foreignkey")
    op.drop_column("deliberations", "blind_position_id")
    op.drop_table("blind_positions")
