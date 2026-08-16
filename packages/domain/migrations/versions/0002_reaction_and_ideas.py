"""Reaction is not intent, and the idea lifecycle — 04-layer-0.md §2 amendments.

Two amendments of 15 August 2026, from external architecture review:

- `execution_events` gains a nullable `reaction`, and `event_type` becomes
  nullable so that *reaction: strongly_enthusiastic, no acceptance event* is a
  representable, queryable record. At least one of the two must be present.
- `ideas` and `idea_state_changes` capture the idea lifecycle with append-only
  lineage. Manual marking only at Layer 0.

**Effect on existing rows:** none are modified. Every existing `execution_events`
row keeps its `event_type`, and `reaction` backfills as NULL — which means "not
recorded", not "neutral". A NULL reaction on a pre-amendment row is an honest
absence; writing `neutral` into history would be inventing evidence.

**The downgrade fails loudly on reaction-only rows, deliberately.** Restoring
NOT NULL on `event_type` cannot succeed while rows with a null `event_type`
exist, and this migration will not delete or fabricate them to make the
downgrade succeed — destroying capture records to satisfy a schema rollback is the
exact outcome Layer 0 exists to prevent. On a database that has never held a
reaction-only row — CI, or a fresh checkout — the downgrade is clean.

Revision ID: 0002_reaction_and_ideas
Revises: 0001_layer_0_schema
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_reaction_and_ideas"
down_revision: str | None = "0001_layer_0_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_ENUM_TYPES: dict[str, tuple[str, ...]] = {
    "execution_event_reaction": (
        "negative",
        "neutral",
        "interested",
        "enthusiastic",
        "strongly_enthusiastic",
    ),
    "idea_lifecycle_state": (
        "mentioned",
        "discussed",
        "researching",
        "prototyped",
        "approved",
        "implemented",
        "superseded",
        "rejected",
        "abandoned",
    ),
}

NEW_TABLES: tuple[str, ...] = ("ideas", "idea_state_changes")


def _enum(name: str) -> postgresql.ENUM:
    """Reference an already-created type rather than creating it inline."""
    return postgresql.ENUM(*NEW_ENUM_TYPES[name], name=name, create_type=False)


def upgrade() -> None:
    """Add reaction to execution_events; create the idea tables."""
    for name, values in NEW_ENUM_TYPES.items():
        rendered = ", ".join(f"'{value}'" for value in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({rendered})")

    # --- execution_events: reaction, independent of event_type ---------------

    op.add_column(
        "execution_events",
        sa.Column("reaction", _enum("execution_event_reaction"), nullable=True),
    )
    # Existing rows are untouched: event_type keeps its value, reaction is NULL —
    # "not recorded", never backfilled to "neutral".
    op.alter_column("execution_events", "event_type", nullable=True)
    op.create_check_constraint(
        "event_or_reaction_present",
        "execution_events",
        "event_type IS NOT NULL OR reaction IS NOT NULL",
    )

    # --- §2.4: the idea lifecycle --------------------------------------------

    op.create_table(
        "ideas",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        # Nullable — the same rule as everywhere: "no project" is explicit.
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("lifecycle_state", _enum("idea_lifecycle_state"), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ideas"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_ideas_project_id", ondelete="NO ACTION"
        ),
    )

    op.create_table(
        "idea_state_changes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("idea_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Null marks creation: the first state has no predecessor.
        sa.Column("from_state", _enum("idea_lifecycle_state"), nullable=True),
        sa.Column("to_state", _enum("idea_lifecycle_state"), nullable=False),
        sa.Column(
            "changed_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_idea_state_changes"),
        sa.ForeignKeyConstraint(
            ["idea_id"], ["ideas.id"], name="fk_idea_state_changes_idea_id", ondelete="NO ACTION"
        ),
        sa.CheckConstraint(
            "from_state IS DISTINCT FROM to_state", name="state_change_changes_state"
        ),
    )

    # The same no-hard-delete guard every Layer 0 table carries (§2.3). The
    # function already exists from 0001.
    for table in NEW_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_forbid_hard_delete "
            f"BEFORE DELETE OR TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION val_forbid_hard_delete()"
        )


def downgrade() -> None:
    """Remove the amendment. Fails loudly if reaction-only rows exist — see above."""
    for table in NEW_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_forbid_hard_delete ON {table}")
    op.drop_table("idea_state_changes")
    op.drop_table("ideas")

    op.drop_constraint("ck_execution_events_event_or_reaction_present", "execution_events")
    # Refuses (NOT NULL violation) while reaction-only rows exist, by design:
    # a rollback must not destroy or fabricate capture records to succeed.
    op.alter_column("execution_events", "event_type", nullable=False)
    op.drop_column("execution_events", "reaction")

    for name in reversed(list(NEW_ENUM_TYPES)):
        op.execute(f"DROP TYPE {name}")
