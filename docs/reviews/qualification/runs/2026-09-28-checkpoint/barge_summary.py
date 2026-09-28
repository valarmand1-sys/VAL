"""Barge-in after synthesis, through the real desktop and player — 28 Sept 2026, §5.

For each barge-in turn of a bench run (`voice_bench.mjs`, sessions B1–B3): whether her
answer had been wholly offered before he spoke and was still sounding; his words' start
→ the desktop's first `stop` poll and → the playback worklet's own `stopped`; any piece
of the stopped answer offered after the stop (a late piece; pieces not yet bound to a
message are not counted against it); and her audio sounding again within 2 s. Then, from
the scratch store, every delivery row of each answer that ended interrupted beside the
desktop's own playback reports for it — the record must follow what the desktop says it
cut, and an answer the desktop reports completed must stay completed.

Usage: barge_summary.py OUT.json voice-bench-RUN-session-N.json [...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

out, *paths = sys.argv[1:]
turns = []
for path in paths:
    run = json.loads(Path(path).read_text())
    for turn in run["turns"]:
        if not turn.get("barge"):
            continue
        start = turn["speech_start_wall"]
        stops = [o for o in run["offers"] if o["stop"] and o["wall"] >= start - 100]
        first_stop = stops[0] if stops else None
        cut = first_stop["message_id"] if first_stop else None
        late = [
            o for o in run["offers"]
            if first_stop and cut and o["wall"] > first_stop["wall"] and o["message_id"] == cut
            and o["segment"] is not None
        ]
        stopped_at = turn.get("worklet_stopped_wall")
        again = [
            e for e in run["playback_events"]
            if stopped_at and e["type"] == "started" and stopped_at < e["wall"] < stopped_at + 2000
        ]
        barge = turn["barge"]
        turns.append({
            "session": run["session"], "label": turn["label"], "delay_reports_ms": run["delay_reports_ms"],
            "all_offered_before_speech_ms": start - barge["all_offered_wall"] if barge.get("all_offered_wall") else None,
            "still_playing_when_spoken": barge.get("still_playing"),
            "speech_start_to_stop_poll_ms": first_stop["wall"] - start if first_stop else None,
            "speech_start_to_worklet_stopped_ms": turn.get("speech_start_to_stopped_ms"),
            "stop_reason": first_stop["reason"] if first_stop else None,
            "late_pieces_of_stopped_answer": len(late),
            "her_audio_again_within_2s": len(again),
        })
engine = create_engine("postgresql+psycopg://localhost:5433/val_test")
with engine.connect() as connection:
    ids = [r[0] for r in connection.execute(text(
        "select distinct message_id from speech_deliveries where state = 'interrupted' "
        "or reason like '%stop%' order by 1"))]
    records = []
    for message_id in ids:
        rows = connection.execute(text(
            "select state, segments_delivered, segments_total, delivered_characters, reason, "
            "recorded_at from speech_deliveries where message_id = :m order by event"), {"m": message_id}).all()
        reports = connection.execute(text(
            "select segment_index, state, recorded_at from speech_playbacks where message_id = :m "
            "and state <> 'available_to_desktop' order by recorded_at"), {"m": message_id}).all()
        records.append({
            "message_id": str(message_id),
            "deliveries": [{"state": r[0], "segments_delivered": r[1], "segments_total": r[2],
                            "characters": r[3], "reason": r[4], "at": r[5].isoformat()} for r in rows],
            "desktop_reports": [{"segment": r[0], "state": r[1], "at": r[2].isoformat()} for r in reports],
        })
Path(out).write_text(json.dumps({"turns": turns, "records": records}, indent=1, ensure_ascii=False) + "\n")
for t in turns:
    print(t["session"][:3], t["label"], "| offered-all %s ms before | playing %s | stop poll %s ms | worklet stopped %s ms | late %d | again %d"
          % (t["all_offered_before_speech_ms"], t["still_playing_when_spoken"], t["speech_start_to_stop_poll_ms"],
             t["speech_start_to_worklet_stopped_ms"], t["late_pieces_of_stopped_answer"], t["her_audio_again_within_2s"]))
for r in records:
    print(r["message_id"][-6:], [d["state"] for d in r["deliveries"]], "| desktop:",
          [(d["segment"], d["state"].replace("playback_", "")) for d in r["desktop_reports"]][-3:],
          "|", (r["deliveries"][-1]["reason"] or "")[:90])
