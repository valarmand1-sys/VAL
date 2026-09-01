"""`archived_at`, and the demonstration fixtures marked — 31 August 2026.

Approved by Lord Armand: `archived_at` on `projects` and `conversations`,
nullable, lifecycle-class (mutable, like `conversations.title`).

## What `archived_at` means, and what it does not mean

**It means exactly one thing: hidden from the interface's default listings.**
It is presentation scoping and carries **no evidentiary meaning whatsoever**.

**It must never be read as superseded, retracted, mistaken, or not real.**
Every row this migration marks is cited Layer 0 gate evidence: the
demonstration projects and conversations of 15-19 August 2026 are the real
live-provider acceptance runs behind the WP-0.6/0.7 audits, the trap-question
demonstrations, the closure smoke checks, and the WP-0.3 point-in-time
restore proof ("closure-smoke present: false"). They are archived because
they are *finished demonstrations*, not because anything about them is
doubted — a future reader, human or Val, who infers evidentiary status from
this flag is misreading it, and this docstring is the record saying so.

Archiving changes no behavior outside listings: an archived conversation
still resumes, an archived project still resolves by name and still scopes
recall, every capture table is untouched, and deletion remains impossible
(§2.3). Archiving exists precisely because deletion does not.

## The marked set is closed and enumerated

Seven projects and eighteen conversations, by id, from the live store —
the complete fixture era. The standing rule recorded with this change
(§2.1 amendment): demonstration fixtures never enter the live store again,
so this set cannot grow. On a database that never held the fixtures (CI,
scratch), the updates match nothing and do nothing.

## Downgrade

Drops the columns. The marks are presentation state, fully reconstructable
from this migration's own literals, so removing them loses no evidence —
which is the whole point of the column.

Revision ID: 0012_archive_is_presentation
Revises: 0011_blind_position_evidence
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_archive_is_presentation"
down_revision: str | None = "0011_blind_position_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The seven demonstration projects of 15-19 August 2026. Cited gate evidence.
FIXTURE_PROJECTS = (
    "01a0122f-fbc6-7601-94ed-9f2980298808",  # Project Alpha
    "01a0122f-fbc7-7a9b-a374-8b560a2203b4",  # Project Beta
    "01a0122f-fbc7-7ded-a649-3b20fe043df1",  # Winter Light (winter-light-series)
    "01a0122f-fbc8-704b-af93-251bc3e696e8",  # Winter Light (winter-light-short)
    "01a01580-02ca-7c0c-8bfe-353f13a9f07d",  # Lighthouse Restoration (wp07-lighthouse)
    "01a01580-02cb-7309-9e4b-200b455922c0",  # Harbour Survey (wp07-harbour)
    "01a0171d-ae57-7bfa-be54-eb0fe11637bc",  # Closure Smoke
)

#: The eighteen demonstration conversations. Cited gate evidence — the trap
#: and retrap runs, the WP-0.7 memory/isolation set, the switching
#: demonstration, and both closure-smoke conversations (the second anchors the
#: WP-0.3 PITR proof).
FIXTURE_CONVERSATIONS = (
    "01a01580-02cd-7386-817b-7eecb0bd1bd2",  # A1 — the Fresnel lens
    "01a01580-b53a-7f28-bfed-f6112410419c",  # A2 — checking the catalogue
    "01a01580-e0d2-70d2-989a-c2ac9176bf1a",  # B1 — the harbour lens
    "01a01580-e0db-7af0-b7b1-cd3bb40b0300",  # A3 — isolation check
    "01a01580-ea2e-7eed-bf12-379b254069c3",  # N1 — no project
    "01a01581-1ffa-7379-b31e-f5d95eb6fb70",  # T1 — the brass telescope
    "01a01581-1ffe-7a82-bd54-9012ac44cd05",  # T2 — the copper roof
    "01a01581-2001-7009-92bf-e4e15cb9f120",  # T3 — the foghorn
    "01a01581-2003-7d49-a7e7-b2d34b7b42ac",  # trap — never_approved
    "01a01581-3038-762d-b178-43345b398b35",  # trap — superseded
    "01a01581-3e7a-76bb-847e-3f291e1c8395",  # trap — abandoned
    "01a0169d-0f6d-7bd5-89a3-9ec920199934",  # retrap — never_approved
    "01a0169d-a42e-7594-a2c6-74e4b59f3b20",  # retrap — never_approved
    "01a0169d-b5c7-75e5-80fe-ebcdfe8a75a1",  # retrap — superseded
    "01a0169d-c497-7849-acba-163a3d806f2f",  # retrap — abandoned
    "01a0169e-3e43-7c5c-9b0a-8c562108f2a7",  # Switch to Harbour Survey, please.
    "01a0171d-ae59-7b96-ad85-6a965bcdb717",  # closure smoke (18 August)
    "01a01a69-9c26-7fbc-964e-9efc1f7e18df",  # closure smoke (19 August, PITR anchor)
)


def upgrade() -> None:
    """Add the presentation column; mark the closed fixture set by id."""
    for table in ("projects", "conversations"):
        op.add_column(
            table,
            sa.Column("archived_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        )

    bind = op.get_bind()
    bind.execute(
        sa.text("update projects set archived_at = now() where id = any(cast(:ids as uuid[]))"),
        {"ids": list(FIXTURE_PROJECTS)},
    )
    bind.execute(
        sa.text(
            "update conversations set archived_at = now() where id = any(cast(:ids as uuid[]))"
        ),
        {"ids": list(FIXTURE_CONVERSATIONS)},
    )


def downgrade() -> None:
    """Remove the presentation column. No evidence is involved either way."""
    op.drop_column("conversations", "archived_at")
    op.drop_column("projects", "archived_at")
