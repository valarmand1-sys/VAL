"""What the player says about an answer, laid beside what delivery recorded.

Owner orders, 1 and 2 October 2026 (delivery accounting). On 30 September an answer of
six segments was recorded `completed 6/6` while the player reported only its first.

Two records describe one spoken answer, and they are about different things:

- `speech_deliveries` — the **service's** side: text became audio and the audio left for
  the ear. With a desktop collecting it, "left for the ear" means *handed to the desktop*.
  Its `completed` is "every segment was voiced and offered".
- `speech_playbacks` — the **player's** side: a segment was made available to the desktop
  (the service's own row), and then the desktop's reports of what its output device did
  with it: started, completed, interrupted, failed.

Five facts are kept apart and never inferred from one another: audio **generated**,
**handed over**, playback **started**, playback **completed**, playback **cut**.

**Three readings, and only three** (2 October 2026):

- *confirmed* — the player reported every segment completed. Only this supports claiming
  a completed delivery as heard to its end.
- *contradicted* — the player reported a segment interrupted or failed. Only an
  affirmative report contradicts.
- *unconfirmed* — everything else: no player rows at all, rows with no reports, a missing
  start or end report, playback still under way. **A missing report is not a report of
  silence**: it does not show the audio was heard, and it does not show it was not.
  Nothing is inferred from absence in either direction. This includes a delivery with no
  player rows: no production path delivers to a sink that is itself the listener, and a
  delivery row does not say which path it took, so missing desktop rows establish nothing.

**What was heard is bounded, not stated.** `confirmed_prefix` is the text of segments the
player reported completed — the most that can be said to have been heard. `begun_prefix`
runs through the last segment reported started: a segment that began and was cut, or
whose end was never reported, was heard *in part at most*, and is never handed on as
heard text. Nothing is rewritten: both records stay as written, and this is a reading.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import Connection, text

Player = Literal[
    # No player rows for this answer at all. Completion is unconfirmed: the absence of
    # desktop rows does not show how, or whether, the audio was played.
    "no_record",
    # Every generated segment was handed over and reported completed.
    "confirmed",
    # The player reported a segment of this answer interrupted or failed.
    "interrupted",
    # Every handed-over segment was reported started; an end report is missing.
    "end_unconfirmed",
    # Playback may still be under way: nothing says it is over.
    "in_progress",
    # Over; some segments have no playback-start report, and no cut was reported.
    "incomplete_reports",
    # Over; handed to the desktop, and the player reported nothing about it.
    "not_reported",
]

Completion = Literal["confirmed", "contradicted", "unconfirmed"]

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
    #: Text of the segments the player reported **completed**, in order: the most that
    #: can be said to have been heard.
    confirmed_prefix: str
    #: Text through the last segment reported **started**. Its tail — a segment cut off,
    #: or one whose end was never reported — was heard in part at most. An upper bound
    #: on what the player's reports cover; never heard text.
    begun_prefix: str
    #: Whether playback of this answer is known to be over.
    over: bool
    #: In words, what the player's rows do and do not show, when that is less than a
    #: confirmed whole; else None.
    shortfall: str | None

    @property
    def completion(self) -> Completion:
        if self.player == "confirmed":
            return "confirmed"
        if self.player == "interrupted":
            return "contradicted"
        return "unconfirmed"

    @property
    def supports_completed(self) -> bool:
        """May a `completed` delivery be claimed as heard to its end? Only on the
        player's affirmative report of every segment."""
        return self.player == "confirmed"

    @property
    def contradicts_completed(self) -> bool:
        """Does a player report show a `completed` delivery was cut? Only an
        affirmative report of interruption or failure; never a missing one."""
        return self.player == "interrupted"


def _join(rows: list) -> str:  # type: ignore[type-arg]
    return " ".join(row.text or "" for row in rows)


def _indices(rows: list) -> str:  # type: ignore[type-arg]
    return ", ".join(str(row.segment_index) for row in rows)


def player_evidence(
    connection: Connection, message_id: UUID, *, segments_total: int | None
) -> PlayerEvidence:
    """Read the player's account of one answer. Read-only."""
    rows = connection.execute(_SEGMENTS, {"id": message_id}).all()
    handed = [row for row in rows if row.handed]
    if not handed:
        return PlayerEvidence(
            "no_record",
            0,
            0,
            0,
            "",
            "",
            False,
            "no player record for this answer: completion is unconfirmed",
        )
    started = [row for row in handed if row.started]
    completed = [row for row in handed if row.completed]
    cut = [row for row in handed if row.cut]
    confirmed_prefix = _join(completed)
    begun_prefix = _join(started)
    generated = segments_total if segments_total is not None else len(handed)
    everything_handed = len(handed) >= generated
    counts = (len(handed), len(started), len(completed))
    if everything_handed and len(completed) == len(handed) and not cut:
        return PlayerEvidence("confirmed", *counts, confirmed_prefix, begun_prefix, True, None)

    no_start = [row for row in handed if not row.started]
    unhanded = max(0, generated - len(handed))
    parts: list[str] = []
    if started:
        parts.append(f"playback-start reports for segment(s) {_indices(started)} of {generated}")
    if cut:
        parts.append(
            f"segment(s) {_indices(cut)} reported cut off while playing "
            "(how much of a cut segment was heard is not recorded)"
        )
    ended = {row.segment_index for row in completed} | {row.segment_index for row in cut}
    open_ended = [row for row in started if row.segment_index not in ended]
    if open_ended:
        parts.append(f"no playback-end report for segment(s) {_indices(open_ended)}")
    if no_start:
        parts.append(f"no playback-start report for segment(s) {_indices(no_start)}")
    if unhanded:
        parts.append(f"no hand-over row for {unhanded} segment(s)")
    shortfall = "; ".join(parts)

    if cut:
        return PlayerEvidence(
            "interrupted", *counts, confirmed_prefix, begun_prefix, True, shortfall
        )
    over_facts = connection.execute(_OVER, {"id": message_id}).one()
    over = bool(
        over_facts.session_closed
        or over_facts.later_answer_started
        or float(over_facts.idle_seconds) >= STALE_AFTER_SECONDS
    )
    if not over:
        return PlayerEvidence(
            "in_progress", *counts, confirmed_prefix, begun_prefix, False, shortfall
        )
    if not started:
        return PlayerEvidence(
            "not_reported",
            *counts,
            "",
            "",
            True,
            f"{len(handed)} of {generated} segment(s) were handed to the desktop and the "
            "player reported nothing about them: nothing confirms they were heard, and "
            "nothing shows they were not",
        )
    if everything_handed and len(started) == len(handed):
        return PlayerEvidence(
            "end_unconfirmed", *counts, confirmed_prefix, begun_prefix, True, shortfall
        )
    return PlayerEvidence(
        "incomplete_reports", *counts, confirmed_prefix, begun_prefix, True, shortfall
    )
