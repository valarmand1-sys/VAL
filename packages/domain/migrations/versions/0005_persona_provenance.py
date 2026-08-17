"""Persona provenance and per-call attribution — WP-0.5.

Authorised by Lord Armand on 17 August 2026, with two of the four executive
decisions landing directly here: the authored semantic version is stored
explicitly and separately from the integer persistence revision, and every model
call becomes attributable to the persona revision that produced it.

**`personas` gains four columns and loses one false NOT NULL.**

- `semantic_version` — the authored label, canonical and **NOT NULL**. §2.1's
  clarification proposed it nullable; it is required instead, because a row that
  cannot say which authored version it holds is exactly the ambiguity the column
  exists to remove, and every row that will ever exist is written by a seeder
  that knows the answer. Narrowing a proposal is permitted; widening one is not.
- `source_sha256`, `source_path` — which governing document produced this row.
  The path is **repository-relative**: an absolute path is a fact about one
  machine, and making it authoritative would leave the record unverifiable
  anywhere else.
- `created_at` — when the row was written, which `activated_at` cannot say once
  activation starts moving.
- `activated_at` becomes **nullable**. NULL means *never activated*. Before this,
  a revision created and not yet activated had to carry an activation instant for
  an event that had not happened.

**Immutability is enforced by the database, not by discipline.** A `BEFORE
UPDATE` trigger refuses any change to `version`, `semantic_version`, `content`,
`source_sha256`, `source_path`, `created_at`, or `authored_by`. `is_active` and
`activated_at` are deliberately outside it: activation is lifecycle state and
moves, and which persona is live is a different fact from what any persona says.

This is the layer the guarantee belongs at. Service code can be bypassed by the
next caller; a trigger cannot, and `personas` is the one table whose historical
content the whole of Layer 5 will later be reading back.

**`model_calls` gains `persona_id`.** A stable reference, never a copy of the
content. The persona is immutable once stored, so the reference resolves to
exactly the text that was sent, and activating a different revision later cannot
rewrite the attribution of a call already made. Nullable for two honest reasons:
rows written before WP-0.5 carry no persona, and a call on a path that
legitimately assembles none is not a Val utterance to attribute.

**Effect on existing rows.** `personas` is empty, so its NOT NULL additions cost
nothing and require no backfill. The six `model_calls` rows keep everything they
hold and take `persona_id = NULL`, meaning *made before a persona existed* —
which is true, and is the same NULL-rather-than-a-neutral-value precedent as
`0002` and `0003`.

**Downgrade is clean while no persona has been seeded, and refuses afterwards.**
Dropping `semantic_version` from a table that holds seeded rows would discard the
authored provenance of records that cannot be reconstructed from the integer
revision — so the downgrade checks, and stops. A rollback that silently
disconnects a stored persona from the document it came from is not a rollback.

Revision ID: 0005_persona_provenance
Revises: 0004_supersede_zero_costs
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from val_domain.migrations_support import ACCOUNTED_VIEW

revision: str = "0005_persona_provenance"
down_revision: str | None = "0004_supersede_zero_costs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Columns a persona row may never change after insertion. `is_active` and
#: `activated_at` are absent on purpose — they are the lifecycle half.
IMMUTABLE_COLUMNS = (
    "version",
    "semantic_version",
    "content",
    "source_sha256",
    "source_path",
    "created_at",
    "authored_by",
)

_GUARD_FUNCTION = """
CREATE OR REPLACE FUNCTION val_persona_content_is_immutable()
RETURNS trigger AS $$
BEGIN
    IF {comparisons} THEN
        RAISE EXCEPTION
            'personas.% is immutable: editing a persona creates a new revision, '
            'it never rewrites one (04-layer-0.md 2.1). is_active and '
            'activated_at may change; nothing else may.',
            'authored content';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


def _guard_sql() -> str:
    comparisons = "\n        OR ".join(
        f"NEW.{column} IS DISTINCT FROM OLD.{column}" for column in IMMUTABLE_COLUMNS
    )
    return _GUARD_FUNCTION.format(comparisons=comparisons)


def upgrade() -> None:
    """Give a persona row its provenance, and make its authored half unwritable."""
    # --- personas: provenance -------------------------------------------------
    #
    # `personas` is empty, so NOT NULL needs no server_default scaffolding and no
    # backfill. If it were not empty this migration would have to stop and ask
    # which authored version each existing row held, because nothing in the
    # record could answer that — which is the whole reason for the column.
    op.add_column("personas", sa.Column("semantic_version", sa.Text(), nullable=False))
    op.add_column("personas", sa.Column("source_sha256", sa.Text(), nullable=False))
    op.add_column("personas", sa.Column("source_path", sa.Text(), nullable=False))
    op.add_column(
        "personas",
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # NULL now means "never activated" rather than being unrepresentable.
    op.alter_column("personas", "activated_at", nullable=True)

    op.create_check_constraint("version_positive", "personas", "version > 0")
    op.create_check_constraint(
        "semantic_version_is_canonical",
        "personas",
        r"semantic_version ~ '^[0-9]+(\.[0-9]+)*$'",
    )
    op.create_check_constraint(
        "source_sha256_is_a_digest", "personas", "source_sha256 ~ '^[0-9a-f]{64}$'"
    )
    op.create_check_constraint(
        "active_requires_activated_at", "personas", "NOT is_active OR activated_at IS NOT NULL"
    )

    # --- personas: the authored half is unwritable ----------------------------
    op.execute(_guard_sql())
    op.execute(
        "CREATE TRIGGER personas_content_is_immutable "
        "BEFORE UPDATE ON personas "
        "FOR EACH ROW EXECUTE FUNCTION val_persona_content_is_immutable()"
    )

    # --- model_calls: which persona produced this call ------------------------
    op.add_column(
        "model_calls",
        sa.Column("persona_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_model_calls_persona_id",
        "model_calls",
        "personas",
        ["persona_id"],
        ["id"],
        ondelete="NO ACTION",
    )

    # `model_calls_accounted` was defined with `mc.*`, which expanded to the
    # columns that existed when `0004` created it. Adding one to the base table
    # does not reach the view, and a view that silently stops exposing a base
    # column becomes a second, lesser record — readers would have to know which
    # of the two to ask. Dropped and recreated rather than replaced: CREATE OR
    # REPLACE cannot insert a column ahead of the view's computed ones.
    op.execute("DROP VIEW model_calls_accounted")
    op.execute(ACCOUNTED_VIEW)


def downgrade() -> None:
    """Reverse it — and refuse once a persona has been seeded.

    Clean on a database that has never held a persona, which is CI and any fresh
    checkout. Against a seeded store it stops, because dropping
    `semantic_version` would discard the authored provenance of rows whose
    integer revision cannot reconstruct it. The same argument as `0002` and
    `0003`: a rollback that destroys what was captured is not a rollback.
    """
    seeded = op.get_bind().execute(sa.text("select count(*) from personas")).scalar_one()
    if seeded:
        raise RuntimeError(
            f"Refusing to downgrade: {seeded} persona revision(s) are stored. Dropping "
            "semantic_version, source_sha256, and source_path would disconnect them from "
            "the authored documents they were seeded from, and the integer persistence "
            "revision cannot reconstruct that. Retire the revisions deliberately first."
        )

    # The view selects `mc.*`, so it depends on `persona_id` and PostgreSQL
    # refuses to drop the column while the view exists. Dropped first, recreated
    # after the column is gone — which also puts it back exactly as `0004` had it.
    op.execute("DROP VIEW model_calls_accounted")
    op.drop_constraint("fk_model_calls_persona_id", "model_calls", type_="foreignkey")
    op.drop_column("model_calls", "persona_id")
    op.execute(ACCOUNTED_VIEW)

    op.execute("DROP TRIGGER IF EXISTS personas_content_is_immutable ON personas")
    op.execute("DROP FUNCTION IF EXISTS val_persona_content_is_immutable()")

    op.drop_constraint("ck_personas_active_requires_activated_at", "personas")
    op.drop_constraint("ck_personas_source_sha256_is_a_digest", "personas")
    op.drop_constraint("ck_personas_semantic_version_is_canonical", "personas")
    op.drop_constraint("ck_personas_version_positive", "personas")

    op.alter_column("personas", "activated_at", nullable=False)
    op.drop_column("personas", "created_at")
    op.drop_column("personas", "source_path")
    op.drop_column("personas", "source_sha256")
    op.drop_column("personas", "semantic_version")
