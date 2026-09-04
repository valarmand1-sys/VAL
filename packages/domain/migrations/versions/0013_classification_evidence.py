"""A turn's classification is durable evidence — ruling of 3 September 2026.

Until this migration the §4.8 classifier's verdict and declared reason were
never persisted, and — by the 18 August rule that provenance is present iff
the task is a conversation — its `model_calls` rows carry no conversation or
message id. A turn's classification could therefore be tied to its call only
by timestamp, and for an ordinary turn nothing durable said how it had been
classified at all. The 3 September repair of the classifier contract made the
gap visible: every real consequential exchange to that date had been a
capture miss, and the record could not show which.

Lord Armand's ruling: add a separate, durable, per-turn classification
evidence record. Keep `model_calls` non-conversation; the evidence record
carries the turn linkage. It must answer, later, "how was this specific turn
classified, and why?" — for ordinary turns as well as consequential ones —
from the classifier's own declared structured reason, never reconstructed.
Nothing historical is retrofitted from timestamps.

## What is added

**`classifications`** — one row per turn, written when classification
concludes, established or not, before any strip or response call: the turn
anchor (project derived from the conversation), whether a verdict was
established, the verdict and hard exclusion as declared, the attempt count,
every classification `model_calls` id in order, the call the verdict came
from (or the final recorded attempt), and — where unestablished — why, per
attempt. Append-only through the standing guards `val_forbid_hard_delete`
(`0001`) and `val_rows_are_evidence` (`0009`).

**`classification_verdict`** — the classifier's full vocabulary, including
`not_consequential`; the existing `deliberation_classification` type is the
capturing subset and is unchanged.

## Downgrade

Refuses once any classification exists. Clean on an empty database (CI).

Revision ID: 0013_classification_evidence
Revises: 0012_archive_is_presentation
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_classification_evidence"
down_revision: str | None = "0012_archive_is_presentation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VERDICTS = ("consequential", "uncertain", "not_consequential")


def upgrade() -> None:
    """Create the verdict type and the evidence table, and freeze the table."""
    rendered = ", ".join(f"'{value}'" for value in VERDICTS)
    op.execute(f"CREATE TYPE classification_verdict AS ENUM ({rendered})")

    op.create_table(
        "classifications",
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
        sa.Column("established", sa.Boolean(), nullable=False),
        sa.Column(
            "verdict",
            postgresql.ENUM(*VERDICTS, name="classification_verdict", create_type=False),
            nullable=True,
        ),
        sa.Column("hard_exclusion", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "model_call_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False
        ),
        sa.Column("resolving_model_call_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.CheckConstraint("established = (verdict IS NOT NULL)", name="established_iff_verdict"),
        sa.CheckConstraint("attempts >= 1", name="classification_attempted_at_least_once"),
        sa.PrimaryKeyConstraint("id", name="pk_classifications"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_classifications_project_id",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_classifications_conversation_id",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name="fk_classifications_message_id",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["resolving_model_call_id"],
            ["model_calls.id"],
            name="fk_classifications_resolving_model_call_id",
            ondelete="NO ACTION",
        ),
    )

    # Same footing as every other capture table: §2.3's no-hard-delete, and
    # 0009's rows-are-evidence, both from the standing functions.
    op.execute(
        "CREATE TRIGGER classifications_forbid_hard_delete "
        "BEFORE DELETE OR TRUNCATE ON classifications "
        "FOR EACH STATEMENT EXECUTE FUNCTION val_forbid_hard_delete()"
    )
    op.execute(
        "CREATE TRIGGER classifications_rows_are_evidence "
        "BEFORE UPDATE ON classifications "
        "FOR EACH ROW EXECUTE FUNCTION val_rows_are_evidence()"
    )


def downgrade() -> None:
    """Remove the evidence table — refused once it holds evidence."""
    captured = op.get_bind().execute(sa.text("select count(*) from classifications")).scalar_one()
    if captured:
        raise RuntimeError(
            f"Refusing to downgrade: {captured} classification record(s) exist. They "
            "are the only durable account of how each turn was classified, and "
            "dropping them would destroy that evidence outright. This migration "
            "reverses cleanly only on an empty database."
        )
    op.execute("DROP TRIGGER IF EXISTS classifications_rows_are_evidence ON classifications")
    op.execute("DROP TRIGGER IF EXISTS classifications_forbid_hard_delete ON classifications")
    op.drop_table("classifications")
    op.execute("DROP TYPE classification_verdict")
