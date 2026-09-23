"""Audio joins the perception record — owner execution order, 22 September 2026.

Additive, and deliberately small. The three tables of `0025` already hold
everything §7 of the order requires of an audio perception — source identity and
digest, the owner's question, the exact prompt, provider, model and revision,
quantization, runtime and version, the grounded observation, `local`, cost, and
both provenance edges — so nothing is rebuilt and nothing is renamed.

Three things change.

1. **`audio` joins the modality vocabulary.** It was absent because no admitted
   provider could hear; Qwen3-Omni now can, on the Case B evidence already on
   record, so the value is added rather than the column widened to free text.
2. **`duration_seconds`**, nullable. A still image has no duration and says so
   with NULL; a recording or a clip does, and a record that cannot distinguish a
   three-second clip from a three-minute one is thinner than it needs to be.
3. **`verified`**, nullable, recording *how far admission actually went* — a WAV
   whose header was parsed by the standard library says `decoded_header`, an MP4
   whose container was walked but whose frames were not decoded says
   `container_structure`, and an image that was genuinely decoded says
   `decoded`. Claiming a uniform "verified" over all three would claim a decode
   that did not happen.

Historical rows are untouched, `perceived` is not renamed, and the existing
visual states keep their meanings exactly.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0026_local_audio_perception"
down_revision: str | None = "0025_local_visual_perception"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    """Widen the modality vocabulary; add the two honest media facts."""
    # PostgreSQL 12+ permits ADD VALUE inside a transaction so long as the new
    # value is not *used* in the same transaction. Nothing below uses it.
    op.execute("ALTER TYPE perception_modality ADD VALUE IF NOT EXISTS 'audio'")
    op.add_column(
        "perception_sources", sa.Column("duration_seconds", sa.Numeric(10, 3), nullable=True)
    )
    op.add_column("perception_sources", sa.Column("verified", sa.Text(), nullable=True))
    op.create_check_constraint(
        "duration_not_negative",
        "perception_sources",
        "duration_seconds IS NULL OR duration_seconds >= 0",
    )


def downgrade() -> None:
    """Reversible, as WP-0.2 requires.

    The two columns drop cleanly. The enum value does not: PostgreSQL cannot
    remove one, so the type is rebuilt without it — which is safe precisely
    because a downgrade past this revision is a downgrade past the point where
    any audio row could exist, and the rebuild would fail loudly rather than
    quietly if one did.
    """
    op.drop_constraint("ck_perception_sources_duration_not_negative", "perception_sources")
    op.drop_column("perception_sources", "verified")
    op.drop_column("perception_sources", "duration_seconds")
    op.execute("ALTER TYPE perception_modality RENAME TO perception_modality_with_audio")
    op.execute("CREATE TYPE perception_modality AS ENUM ('image', 'video')")
    op.execute(
        "ALTER TABLE perception_sources ALTER COLUMN modality TYPE perception_modality "
        "USING modality::text::perception_modality"
    )
    op.execute("DROP TYPE perception_modality_with_audio")
