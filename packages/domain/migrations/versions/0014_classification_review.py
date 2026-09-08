"""Hand-labelling of classifications — ruling of 7 September 2026.

WP-0.9's acceptance criterion needs fifty real exchanges hand-labelled by
Lord Armand, with hard exclusions never classified consequential and
inclusion-test disagreements reviewed and used to tune. Until this migration
nothing in the store could hold his label. The interface's review queue
withholds the classifier's verdict until his label is durably stored, so
this table is where that blind judgment lands.

## What is added

**`classification_labels`** — one original blind label per classification,
unique, never overwritten: the label, the explicit hard-exclusion
determination (present iff `not_consequential`: one of the six, or the
explicit `none_fails_inclusion_test`), and who labelled.

**`classification_reviews`** — adjudications appended after the reveal:
conclusion, stated reason, and for a classifier-was-wrong conclusion a tuning
state that is `tuning_required` until a later row cites the engineering
change and its verification.

Three enum types: `human_classification`, `review_conclusion`,
`tuning_state`. Both tables are frozen by the standing guards
`val_forbid_hard_delete` (`0001`) and `val_rows_are_evidence` (`0009`).

## Downgrade

Refuses once any label or review exists. Clean on an empty database (CI).

Revision ID: 0014_classification_review
Revises: 0013_classification_evidence
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_classification_review"
down_revision: str | None = "0013_classification_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS: dict[str, tuple[str, ...]] = {
    "human_classification": ("consequential", "uncertain", "not_consequential"),
    "review_conclusion": (
        "label_upheld_classifier_wrong",
        "classifier_upheld_label_wrong",
        "ambiguous_needs_ruling",
    ),
    "tuning_state": ("tuning_required", "tuning_verified"),
}


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def _uuid() -> sa.Column[object]:
    return sa.Column(
        "id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("uuidv7()")
    )


def _created_at() -> sa.Column[object]:
    return sa.Column(
        "created_at",
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def _freeze(table: str) -> None:
    op.execute(
        f"CREATE TRIGGER {table}_forbid_hard_delete "
        f"BEFORE DELETE OR TRUNCATE ON {table} "
        "FOR EACH STATEMENT EXECUTE FUNCTION val_forbid_hard_delete()"
    )
    op.execute(
        f"CREATE TRIGGER {table}_rows_are_evidence "
        f"BEFORE UPDATE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION val_rows_are_evidence()"
    )


def upgrade() -> None:
    """Create the three types and the two evidence tables, and freeze both."""
    for name, values in ENUMS.items():
        rendered = ", ".join(f"'{value}'" for value in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({rendered})")

    op.create_table(
        "classification_labels",
        _uuid(),
        _created_at(),
        sa.Column("classification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", _enum("human_classification"), nullable=False),
        sa.Column("exclusion_determination", sa.Text(), nullable=True),
        sa.Column("labelled_by", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "(label = 'not_consequential') = (exclusion_determination IS NOT NULL)",
            name="determination_iff_not_consequential",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_classification_labels"),
        sa.UniqueConstraint("classification_id", name="uq_classification_labels_classification_id"),
        sa.ForeignKeyConstraint(
            ["classification_id"],
            ["classifications.id"],
            name="fk_classification_labels_classification_id",
            ondelete="NO ACTION",
        ),
    )
    _freeze("classification_labels")

    op.create_table(
        "classification_reviews",
        _uuid(),
        _created_at(),
        sa.Column("classification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conclusion", _enum("review_conclusion"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("tuning_state", _enum("tuning_state"), nullable=True),
        sa.Column("tuning_change", sa.Text(), nullable=True),
        sa.Column("tuning_verification", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(conclusion = 'label_upheld_classifier_wrong') = (tuning_state IS NOT NULL)",
            name="tuning_state_iff_classifier_wrong",
        ),
        sa.CheckConstraint(
            "(tuning_state = 'tuning_verified') = "
            "(tuning_change IS NOT NULL AND tuning_verification IS NOT NULL)",
            name="verified_cites_change",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_classification_reviews"),
        sa.ForeignKeyConstraint(
            ["classification_id"],
            ["classifications.id"],
            name="fk_classification_reviews_classification_id",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["label_id"],
            ["classification_labels.id"],
            name="fk_classification_reviews_label_id",
            ondelete="NO ACTION",
        ),
    )
    _freeze("classification_reviews")


def downgrade() -> None:
    """Remove both tables — refused once either holds evidence."""
    bind = op.get_bind()
    for table in ("classification_reviews", "classification_labels"):
        held = bind.execute(sa.text(f"select count(*) from {table}")).scalar_one()  # noqa: S608
        if held:
            raise RuntimeError(
                f"Refusing to downgrade: {held} row(s) exist in {table}. They are Lord "
                "Armand's own hand-labelling evidence for WP-0.9's fifty-exchange "
                "criterion, and dropping them would destroy it outright. This migration "
                "reverses cleanly only on an empty database."
            )
    for table in ("classification_reviews", "classification_labels"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_rows_are_evidence ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_forbid_hard_delete ON {table}")
        op.drop_table(table)
    for name in reversed(list(ENUMS)):
        op.execute(f"DROP TYPE {name}")
