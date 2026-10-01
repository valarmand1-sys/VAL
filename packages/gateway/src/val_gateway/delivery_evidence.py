"""What the player says about an answer, laid beside what delivery recorded.

Owner order, 1 October 2026 (delivery accounting). On 30 September an answer of six
segments was recorded `completed 6/6` while the desktop played only its first: the other
five were handed over and thrown away unplayed, and the next turn was told he had heard
all of it.

Two records describe one spoken answer, and they are about different things:

- `speech_deliveries` — the **service's** side: text became audio and the audio left for
  the ear. With a desktop collecting it, "left for the ear" means *handed to the desktop*.
  Its `completed` is "every segment was voiced and offered".
- `speech_playbacks` — the **player's** side: a segment was made available to the desktop
  (the service's own row), and then the desktop's reports of what its output device did
  with it: started, completed, interrupted, failed.

Five facts are kept apart here and never inferred from one another: audio **generated**
(the delivery's segment count), **handed over** (`available_to_desktop`), playback
**started**, playback **completed**, and playback **cut** (interrupted or failed).

**Completed delivery is claimed only on the player's evidence.** Where the player reported
less than delivery recorded — and playback of the answer is known to be over — the
answer is read as heard only as far as the player says. Where the player's evidence is
missing or still arriving, that is what the reading says; nothing is upgraded and nothing
is guessed. Nothing is rewritten: both records stay exactly as they were written, and
this is a reading of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import Connection, text

Player = Literal[
    # No hand-off rows at all: the answer was not delivered through a desktop (a direct
    # sink, or a record older than the playback record). Delivery's own word stands.
    "none",
    # Every handed-over segment was reported completed.
    "confirmed",
    # Every handed-over segment was reported started; an end report is missing. He heard
    # it begin; whether its last segment finished is not on record.
    "end_unconfirmed",
    # Playback may still be under way: nothing says it is over.
    "in_progress",
    # Over, and only some of what was generated was reported started.
    "partial",
    # Over, handed to the desktop, and the player reported nothing about it. Not
    # evidence that it was silent; evidence that nothing confirms he heard it.
    "not_reported",
]

#: Playback rows this old with nothing since are read as over, when nothing else says so.
STALE_AFTER_SECONDS = 300.0

_SEGMENTS = text(
    "select segment_index, "
    "       bool_or(state = 'available_to_desktop') as handed, "
    "       bool_or(state = 'playback_started') as started, "
    "       bool_or(state = 'playback_completed') as completed, "
    "       bool_or(state in ('playback_interrupted', 'playback_failed')) as cut, "
    "       max(text) as text "
    "  from speech_playbacks where message_id = :id "
    " group by segment_index order by segment_index"
)

#: Whether playback of this answer is known to be over, apart from a cut on one of its
#: own segments: its Voice session has ended, a later answer of the conversation has
#: begun to play, or its last playback row is old.
_OVER = text(
    "select "
    "  exists (select 1 from speech_playbacks p join voice_sessions v "
    "            on v.id = p.voice_session_id "
    "           where p.message_id = :id and v.closed_at is not null) as session_closed, "
    "  exists (select 1 from speech_playbacks later join messages newer "
    "            on newer.id = later.message_id join messages mine on mine.id = :id "
    "           where newer.conversation_id = mine.conversation_id "
    "             and newer.sequence > mine.sequence "
    "             and later.state = 'playback_started') as later_answer_started, "
    "  coalesce((select extract(epoch from now() - max(recorded_at)) "
    "              from speech_playbacks where message_id = :id), 0) as idle_seconds"
)


@dataclass(frozen=True)
class PlayerEvidence:
    """The player's account of one answer."""

    player: Player
    segments_handed_over: int
    segments_started: int
    segments_completed: int
    #: The text of the segments reported started, in order: what he can be said to have
    #: begun to hear. Empty when the player reported nothing.
    heard_prefix: str
    #: In words, when the player's account is less than delivery recorded; else None.
    shortfall: str | None

    @property
    def supports_completed(self) -> bool:
        """May a `completed` delivery be claimed as heard to its end?"""
        return self.player in ("none", "confirmed")

    @property
    def contradicts_completed(self) -> bool:
        """Does the player's account show a `completed` delivery was not heard whole?"""
        return self.player in ("partial", "not_reported")


def player_evidence(
    connection: Connection, message_id: UUID, *, segments_total: int | None
) -> PlayerEvidence:
    """Read the player's account of one answer. Read-only."""
    rows = connection.execute(_SEGMENTS, {"id": message_id}).all()
    handed = [row for row in rows if row.handed]
    if not handed:
        return PlayerEvidence("none", 0, 0, 0, "", None)
    started = [row for row in handed if row.started]
    completed = [row for row in handed if row.completed]
    cut = [row for row in handed if row.cut]
    heard_prefix = "".join(row.text or "" for row in started)
    generated = segments_total if segments_total is not None else len(handed)
    everything_handed = len(handed) >= generated
    if everything_handed and len(completed) == len(handed) and not cut:
        return PlayerEvidence(
            "confirmed", len(handed), len(started), len(completed), heard_prefix, None
        )
    over_facts = connection.execute(_OVER, {"id": message_id}).one()
    over = bool(
        cut
        or over_facts.session_closed
        or over_facts.later_answer_started
        or float(over_facts.idle_seconds) >= STALE_AFTER_SECONDS
    )
    if not over:
        return PlayerEvidence(
            "in_progress", len(handed), len(started), len(completed), heard_prefix, None
        )
    if not started:
        return PlayerEvidence(
            "not_reported",
            len(handed),
            0,
            0,
            "",
            (
                f"{len(handed)} of {generated} segment(s) were handed to the desktop and the "
                "player reported nothing about them: nothing confirms any of it was heard"
            ),
        )
    if everything_handed and len(started) == len(handed) and not cut:
        return PlayerEvidence(
            "end_unconfirmed",
            len(handed),
            len(started),
            len(completed),
            heard_prefix,
            None,
        )
    never = [row.segment_index for row in handed if not row.started]
    unhanded = max(0, generated - len(handed))
    parts = [
        f"the player reported playback of segment(s) "
        f"{', '.join(str(row.segment_index) for row in started)} of {generated}"
    ]
    if cut:
        parts.append("segment(s) " + ", ".join(str(row.segment_index) for row in cut) + " cut off")
    if never:
        parts.append(
            "segment(s) "
            + ", ".join(str(index) for index in never)
            + " handed over and never played"
        )
    if unhanded:
        parts.append(f"{unhanded} segment(s) never handed over")
    return PlayerEvidence(
        "partial",
        len(handed),
        len(started),
        len(completed),
        heard_prefix,
        "; ".join(parts),
    )
