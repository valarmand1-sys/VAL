"""Execution events as the domain understands them — WP-0.8.

`04-layer-0.md` WP-0.8: *"every acceptance, rejection, revision, and correction
writes an `execution_events` row with its reason."* §2.2 defines the table;
this module defines the vocabulary and the record shape the writer speaks.

**The two facts this table refuses to conflate**, per the 15 August 2026
amendment: *reaction is not intent.* "He loved the idea" and "he approved the
work" are different facts, so `event_type` and `reaction` are independent
fields, either may stand alone, and enthusiasm is never evidence of approval.

**`reason_source` is the load-bearing distinction.** A reason Lord Armand
stated and a reason Val inferred are different evidence, and Layer 5
distillation must weight them differently. `absent` records that no reason was
given — a fact, never a fabrication — and §2.2 is explicit that a null reason
is *a defect to be surfaced, not a normal state*.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ExecutionEventType(StrEnum):
    """What Lord Armand did with a piece of Val's work."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"
    CORRECTED = "corrected"


class ReasonSource(StrEnum):
    """Where the recorded reason came from. No default, deliberately.

    | Value | Means |
    |---|---|
    | `STATED` | Lord Armand said why, and `reason` holds his words |
    | `INFERRED` | Val inferred why, and `reason` says what she inferred |
    | `ABSENT` | No reason was given, and none was invented |
    """

    STATED = "stated"
    INFERRED = "inferred"
    ABSENT = "absent"


class Reaction(StrEnum):
    """How Lord Armand reacted — independent of whether he decided anything.

    Recorded only when observed, **never inferred from wording alone**
    (§2.2 amendment, 15 August 2026).
    """

    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    INTERESTED = "interested"
    ENTHUSIASTIC = "enthusiastic"
    STRONGLY_ENTHUSIASTIC = "strongly_enthusiastic"


@dataclass(frozen=True)
class ExecutionEventRecord:
    """One persisted execution event, as the authoritative store holds it.

    Insert-only: migration `0009` refuses UPDATE on `execution_events`, so a
    record is complete when written and immutable afterwards. `project_id` is
    the anchoring conversation's stored scope — derived, never caller-supplied,
    so an event cannot claim a project its conversation was not in.
    """

    id: UUID
    project_id: UUID | None
    conversation_id: UUID
    message_id: UUID
    event_type: ExecutionEventType | None
    subject: str
    reason: str | None
    reason_source: ReasonSource
    reaction: Reaction | None
    created_at: datetime
