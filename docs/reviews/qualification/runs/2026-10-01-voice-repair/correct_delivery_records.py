"""Historical delivery statuses, corrected only where the player's record supports it.

Owner order, 1 October 2026 (§3). Before the repair, `completed` in `speech_deliveries`
meant "every segment was voiced and handed to the desktop". Where the desktop's own
playback reports show that less was played, this appends ONE corrective row per answer:
the original events stay exactly as written (the table is append-only), and the new row
carries what the player reported and why the correction was made.

Corrected (2 October 2026): only answers whose latest delivery state is `completed`, whose
playback record covers every generated segment, and for which **the player itself
reported a segment interrupted or failed**. Listed and left alone: every answer whose
reports are merely missing — a missing report is not a report of silence, the table has
no state that says "unconfirmed", and the reading (`delivery_for`) states that instead.

Dry run by default (read-only transaction). `--apply` writes; that is the owner's step.

    uv run python correct_delivery_records.py <database-url> [--apply]
"""

from __future__ import annotations

import sys

from sqlalchemy import create_engine, text

from val_gateway.delivery_evidence import player_evidence

_LATEST = text(
    "select distinct on (message_id) message_id, voice_session_id, event, state, "
    "       segments_delivered, segments_total, delivered_characters, recorded_at "
    "  from speech_deliveries order by message_id, event desc"
)
_APPEND = text(
    "insert into speech_deliveries "
    "  (message_id, voice_session_id, event, state, delivered_prefix, delivered_characters, "
    "   segments_delivered, segments_total, reason) "
    "values (:message_id, :voice_session_id, :event, 'interrupted', :prefix, :characters, "
    "        :segments, :total, :reason)"
)


def main() -> int:
    url = sys.argv[1]
    apply = "--apply" in sys.argv[2:]
    engine = create_engine(url)
    corrected = uncertain = confirmed = 0
    with engine.begin() as connection:
        if not apply:
            connection.execute(text("set transaction read only"))
        for row in connection.execute(_LATEST).all():
            if row.state != "completed":
                continue
            evidence = player_evidence(
                connection, row.message_id, segments_total=row.segments_total
            )
            stamp = f"{row.recorded_at:%Y-%m-%d %H:%M:%S%z} {row.message_id}"
            whole_record = evidence.segments_handed_over >= (row.segments_total or 0)
            if evidence.contradicts_completed and whole_record:
                # The player itself reported a cut: the one case a correction is
                # supported. The appended row follows the table's own rule for a cut
                # (the prefix runs through the segment that was sounding); how much of
                # that segment was heard is not recorded, and the reason says so.
                corrected += 1
                reason = (
                    "Corrected 2 October 2026 from the player's record: "
                    f"{evidence.shortfall}. Event {row.event} recorded completed "
                    f"{row.segments_delivered}/{row.segments_total}, which described audio "
                    "handed to the desktop, not audio played. The original events are kept."
                )
                print(f"CORRECT   {stamp}: {reason}")
                if apply:
                    connection.execute(
                        _APPEND,
                        {
                            "message_id": row.message_id,
                            "voice_session_id": row.voice_session_id,
                            "event": row.event + 1,
                            "prefix": evidence.begun_prefix,
                            "characters": len(evidence.begun_prefix),
                            "segments": evidence.segments_started,
                            "total": row.segments_total,
                            "reason": reason,
                        },
                    )
            elif evidence.completion == "unconfirmed":
                # Missing reports are not contrary reports. No row can say "unconfirmed"
                # (the table has no such state), and none is appended: the reading
                # (`delivery_for`, the next turn's context) states the uncertainty.
                uncertain += 1
                print(
                    f"UNCONFIRMED {stamp}: player={evidence.player} — {evidence.shortfall} "
                    "— no row appended"
                )
            elif evidence.contradicts_completed:
                uncertain += 1
                print(
                    f"UNCONFIRMED {stamp}: a cut was reported but the playback record does "
                    f"not cover every segment ({evidence.shortfall}) — no row appended"
                )
            else:
                confirmed += 1
    print(
        f"\n{'APPLIED' if apply else 'DRY RUN (nothing written)'}: {corrected} to correct, "
        f"{uncertain} unconfirmed and left as recorded, {confirmed} confirmed by the player"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
