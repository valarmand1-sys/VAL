"""The seven intervals of one precedence run — release-gaps order §3.

Joins the driver's record (shared monotonic clock) with the service log's precedence
decisions and turn timelines and the scratch store's calls, deliveries and playbacks.
Usage: precedence_extract.py CASE DRIVE.json SERVICE.log
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import psycopg

case, drive_path, log_path = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
drive = json.loads(drive_path.read_text())
decisions, releases, timelines = [], [], []
for line in log_path.read_text(errors="replace").splitlines():
    m = re.match(r"(\d+\.\d+) INFO:val\.voice:voice (precedence|turn timeline): (.*)", line)
    if not m:
        continue
    wall, kind, body = float(m.group(1)), m.group(2), m.group(3)
    try:
        d = json.loads(body)
    except ValueError:
        continue
    if kind == "precedence" and "released_utterance" in d:
        releases.append({"wall": wall, **d})
    elif kind == "precedence":
        decisions.append({"wall": wall, **d})
    else:
        timelines.append({"wall": wall, "utterance": d["utterance"], "anchor_wall": d.get("anchor_wall"),
                          "marks": {k: v["first_ms"] for k, v in d["marks"].items()}})
with psycopg.connect("postgresql://localhost:5433/val_test", options="-c default_transaction_read_only=on") as c:
    calls = c.execute(
        "select m.content, mc.task_type::text, mc.status::text, mc.terminal_state::text, mc.tokens_out, mc.latency_ms, "
        "x.runtime_diagnostics->'superseded'->>'reason' from model_calls mc join messages m on m.id = mc.message_id "
        "left join model_call_measurements x on x.model_call_id = mc.id order by mc.created_at").fetchall()
    playbacks = c.execute("select message_id::text, segment_index, state, extract(epoch from recorded_at) from speech_playbacks order by recorded_at").fetchall()
    deliveries = c.execute("select message_id::text, state, reason, delivered_characters, extract(epoch from recorded_at) from speech_deliveries order by recorded_at").fetchall()

second_end = drive["speech_end_mono"][1] if len(drive["speech_end_mono"]) > 1 else None
decision = next((d for d in decisions if d.get("by_utterance") == 2), None)
release = next((r for r in releases if r.get("released_utterance") == 1), None)
# The replacement's own timeline (utterance 2) carries confirmation → dispatch → first audio.
second_tl = next((t for t in timelines if t["utterance"] == 2), None)
first_tl = next((t for t in timelines if t["utterance"] == 1), None)
views = drive["views"]
def first_view(pred):
    return next((v["mono"] for v in views if pred(v)), None)
confirmed = decision["decided_mono"] if decision else first_view(lambda v: v.get("committed") and v["committed"]["utterance"] == 2)
summary = {
    "case": case, "trigger": drive["trigger"], "phrases": drive["phrases"],
    "messages": [(m["role"], m["content"][:90]) for m in drive["messages"]],
    "decision": decision, "release": release,
    "first_turn_marks": first_tl["marks"] if first_tl else None,
    "second_turn_marks": second_tl["marks"] if second_tl else None,
    "intervals_s": {
        "second_speech_end_to_confirmation": None if not (second_end and confirmed) else round(confirmed - second_end, 3),
        "confirmation_to_supersession_decision": 0.0 if decision and decision.get("outcome") == "superseded" else None,
        "decision_to_stream_closed": None if not (first_tl and decision and first_tl["marks"].get("superseded_stream_closed") and first_tl["marks"].get("superseded_decided")) else round((first_tl["marks"]["superseded_stream_closed"] - first_tl["marks"]["superseded_decided"]) / 1000, 3),
        "decision_to_superseded_call_ended": None if not (release and decision) else round(release.get("superseded_call_ended_mono", release.get("lane_free_mono", 0)) - decision["decided_mono"], 3),
    },
    "calls": [dict(zip(("message", "task", "status", "terminal", "tokens_out", "latency_ms", "superseded_reason"), (c[0][:50], *c[1:]))) for c in calls],
    "playbacks": [dict(zip(("message_id", "segment", "state", "epoch"), p)) for p in playbacks],
    "deliveries": [dict(zip(("message_id", "state", "reason", "delivered_characters", "epoch"), d)) for d in deliveries],
    "handoffs": drive["handoffs"], "reports": drive["reports"], "events": drive["events"],
    "views": views,
}
# Wall-anchored intervals for the replacement turn: its timeline anchor is its endpoint (wall);
# the driver's clock is monotonic. Convert via the decision's (wall, mono) pair.
if decision and second_tl and second_tl.get("anchor_wall"):
    from datetime import datetime
    anchor = datetime.fromisoformat(second_tl["anchor_wall"]).timestamp()
    mono_of = lambda wall: decision["decided_mono"] + (wall - decision["wall"])  # noqa: E731
    endpoint_mono = mono_of(anchor)
    marks = second_tl["marks"]
    if second_end:
        summary["intervals_s"]["second_speech_end_to_endpoint"] = round(endpoint_mono - second_end, 3)
    for name in ("owner_turn_submitted", "runtime_ready_start", "model_dispatch", "provider_visible_text", "audio_at_sink"):
        if marks.get(name) is not None and second_end:
            summary["intervals_s"][f"second_speech_end_to_{name}"] = round(endpoint_mono + marks[name] / 1000 - second_end, 3)
    if release and marks.get("runtime_ready_start") is not None:
        summary["intervals_s"]["decision_to_replacement_dispatch"] = round(endpoint_mono + marks["runtime_ready_start"] / 1000 - decision["decided_mono"], 3)
out = drive_path.with_name(drive_path.stem + "-summary.json")
out.write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str) + "\n")
brief = {k: summary[k] for k in ("case", "trigger", "messages", "intervals_s")}
brief["decision"] = None if not decision else {k: decision[k] for k in ("relation", "outcome", "answer_heard")}
brief["calls"] = [(c["task"], c["status"], c["tokens_out"], bool(c["superseded_reason"])) for c in summary["calls"]]
brief["reports_http"] = [(r["state"], r["http"]) for r in summary["reports"]]
print(json.dumps(brief, ensure_ascii=False))
