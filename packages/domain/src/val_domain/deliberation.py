"""Deliberation records as the domain understands them — WP-0.9.

`04-layer-0.md` WP-0.9: consequential exchanges are classified per
`02-partner-systems.md` §4.8, a blind position is formed before exposure to
preference, and the record populates. §2.2 defines the table; this module
defines the vocabulary and the record shape the writer speaks.

**`ordering` is the load-bearing distinction.** A position formed before
exposure to Lord Armand's preference and one formed after are different
evidence, and everything in `02-partner-systems.md` §4 depends on knowing
which is which. `contaminated` records honestly that the blind position was
not genuinely blind — a contaminated position labelled clean is the failure
the whole mechanism exists to prevent (§4.1).

**`agreed_from_start` is not an approval.** The 15 August 2026 trap-question
amendment binds deliberation records to the same rule as execution events:
enthusiasm recorded in a deliberation, or an `agreed_from_start` outcome, is
never reported as an approval. A deliberation records how a position was
formed and what became of it — never that work was accepted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class Confidence(StrEnum):
    """How strongly Val holds the position, stated with it (§4.2).

    "I would push back hard on this" and "mild preference, could go either
    way" are different claims; collapsing them makes every opinion worthless,
    including the ones worth listening to.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Ordering(StrEnum):
    """Whether the blind position was genuinely blind (§4.1).

    | Value | Means |
    |---|---|
    | `ENFORCED` | formed from the stripped question only, before any exposure to preference |
    | `CONTAMINATED` | preference could not be cleanly separated; recorded, **not** independent |

    No default, deliberately. The writer must state it; the database will not
    guess (`val_domain.schema`).
    """

    ENFORCED = "enforced"
    CONTAMINATED = "contaminated"


class Outcome(StrEnum):
    """What became of the position once Lord Armand responded (§4.7).

    | Value | Means |
    |---|---|
    | `UPDATED` | she moved to his view, and said what moved her |
    | `HELD` | she kept her position and said why his argument did not land |
    | `OVERRIDDEN` | she held; he decided otherwise; she executes fully |
    | `AGREED_FROM_START` | her blind position already matched his preference |

    Every value except `AGREED_FROM_START` records a real disagreement, which
    is why the §4.7 drift signal — time since Val last disagreed — is computed
    by excluding exactly that one value.
    """

    UPDATED = "updated"
    HELD = "held"
    OVERRIDDEN = "overridden"
    AGREED_FROM_START = "agreed_from_start"


class DeliberationClassification(StrEnum):
    """Why this exchange was captured (§4.8).

    `UNCERTAIN` records a genuine borderline: captured rather than dropped,
    because a marked over-capture is fixable while a miss is not. Uncertain
    records are the primary material for tuning the trigger.
    """

    CONSEQUENTIAL = "consequential"
    UNCERTAIN = "uncertain"


class ClassifiedBy(StrEnum):
    """Who decided this exchange was worth capturing (§4.8).

    Manual override runs both directions and may be retroactive; a classifier
    miss corrected by hand is itself part of the record.
    """

    AUTOMATIC = "automatic"
    USER = "user"
    VAL = "val"


@dataclass(frozen=True)
class DeliberationRecord:
    """One persisted deliberation, as the authoritative store holds it.

    Insert-only: migration `0009` refuses UPDATE on `deliberations`, so a
    record is complete when written and immutable afterwards. `project_id` is
    the anchoring conversation's stored scope — derived, never caller-supplied.

    `both_positions` and `predictions` are populated together on a compromise
    and are the seed of the prediction ledger (§4.5, §4.6). Recording them
    costs almost nothing now; reconstructing them later is impossible.
    """

    id: UUID
    project_id: UUID | None
    conversation_id: UUID
    message_id: UUID
    position: str
    confidence: Confidence
    reasoning: str
    stripped_content: str
    ordering: Ordering
    user_response: str
    outcome: Outcome
    what_changed_her_mind: str | None
    both_positions: str | None
    predictions: str | None
    classification: DeliberationClassification
    classified_by: ClassifiedBy
    created_at: datetime
