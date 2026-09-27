"""Gather one desktop-integration run's evidence — release-gaps order of 26 September 2026, §6.

Three sources, kept apart in the output: the scratch service's own log (readiness,
primes, the fast-route decision, the turn timelines, and the **desktop's own timing
report** as it posted it), the scratch store (messages, the model call each took, the
delivery and playback records), and the DOM observation the driver made in the browser
(what the frontend displayed and when, on the page's clock). None of them is an
acoustic measurement, and the summary says which boundary each figure belongs to.

Usage: desktop_integration_extract.py CASE SCRATCH_DIR SERVICE_LOG OUT.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import psycopg

case, scratch, log_path, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
URL = "postgresql://localhost:5433/val_test"

log_events: list[dict] = []
for line in log_path.read_text(errors="replace").splitlines():
    m = re.match(
        r"(\d+\.\d+) INFO:val\.[a-z_.]+:(voice readiness|voice warm|voice prime|voice desktop timing|"
        r"voice turn timeline|fast route|voice endpoint|voice precedence)(?:: (.*))?",
        line,
    )
    if not m:
        continue
    t, kind, body = float(m.group(1)), m.group(2), (m.group(3) or "")
    entry: dict = {"wall": t, "kind": kind}
    try:
        entry["data"] = json.loads(body) if body.startswith("{") else body[:400]
    except ValueError:
        entry["data"] = body[:400]
    log_events.append(entry)

with psycopg.connect(URL, options="-c default_transaction_read_only=on") as connection:
    messages = connection.execute(
        "select m.id::text, m.conversation_id::text, m.sequence, m.role::text, mc.content, "
        "extract(epoch from m.created_at) from messages m join messages_current mc on mc.id = m.id "
        "order by m.created_at"
    ).fetchall()
    calls = connection.execute(
        "select id::text, message_id::text, model_config_id, task_type::text, status::text, "
        "terminal_state::text, latency_ms, extract(epoch from created_at) from model_calls order by created_at"
    ).fetchall()
    deliveries = connection.execute(
        "select message_id::text, event, state, first_audio_ms, segments_delivered, segments_total, "
        "reason, extract(epoch from recorded_at) from speech_deliveries order by recorded_at"
    ).fetchall()
    playbacks = connection.execute(
        "select message_id::text, segment_index, event, state, elapsed_ms, reason, "
        "extract(epoch from recorded_at) from speech_playbacks order by recorded_at"
    ).fetchall()

dom = json.loads((scratch / "dom.json").read_text()) if (scratch / "dom.json").exists() else {}
plan = json.loads((scratch / "owner.plan.json").read_text()) if (scratch / "owner.plan.json").exists() else {}

# Readiness on the service's clock: first `ready` after Voice On.
click_wall = (dom.get("voice_on_click_wall") or 0) / 1000.0
ready_lines = [e for e in log_events if e["kind"] == "voice readiness" and isinstance(e["data"], dict)]
first_ready = next((e["wall"] for e in ready_lines if e["data"].get("ready") is True), None)
# Readiness as displayed: the first DOM observation after the click with no "Warming up" line.
dom_events = dom.get("dom_events", [])
after_click = [e for e in dom_events if e["wall"] >= dom.get("voice_on_click_wall", 0)]
first_warming = next((e for e in after_click if e.get("progress") and "warming up" in e["progress"].lower()), None)
# Displayed ready: the first observation after the warming line first appeared in which the
# progress area is empty and the voice label is the plain listening state (no turn under
# way) — the display cannot show readiness while a turn's own stage line occupies it.
first_displayed_ready = next(
    (
        e
        for e in after_click
        if first_warming is not None
        and e["wall"] > first_warming["wall"]
        and not e.get("progress")
        and e.get("voice") == "Voice On · Mic Listening"
    ),
    None,
)

summary = {
    "case": case,
    "plan": plan,
    "voice_on_click_wall": dom.get("voice_on_click_wall"),
    "service_clock": {
        "voice_on_to_ready_s": None if first_ready is None or not click_wall else round(first_ready - click_wall, 3),
        "readiness_lines": [{"wall": e["wall"], **e["data"]} for e in ready_lines],
        "warm": [e["data"] for e in log_events if e["kind"] == "voice warm"],
        "primes": [e["data"] for e in log_events if e["kind"] == "voice prime"],
        "fast_route": [e["data"] for e in log_events if e["kind"] == "fast route"],
        "endpoints": [e["data"] for e in log_events if e["kind"] == "voice endpoint"],
        "desktop_timing_reports": [e["data"] for e in log_events if e["kind"] == "voice desktop timing"],
        "precedence": [{"wall": e["wall"], **e["data"]} for e in log_events if e["kind"] == "voice precedence" and isinstance(e["data"], dict)],
        "turn_timelines": [
            {k: v for k, v in e["data"].items() if k != "marks"}
            | {"marks": {k: v["first_ms"] for k, v in e["data"]["marks"].items()}}
            for e in log_events
            if e["kind"] == "voice turn timeline" and isinstance(e["data"], dict)
        ],
    },
    "desktop_display": {
        "voice_on_to_warming_shown_s": None if first_warming is None else round((first_warming["wall"] - dom["voice_on_click_wall"]) / 1000, 3),
        "voice_on_to_ready_displayed_s": None if first_displayed_ready is None else round((first_displayed_ready["wall"] - dom["voice_on_click_wall"]) / 1000, 3),
        "events": dom_events,
        "console": dom.get("console", [])[:80],
    },
    "store": {
        "messages": [
            {"id": i, "conversation": c, "sequence": s, "role": r, "content": t, "created": round(w, 3)}
            for i, c, s, r, t, w in messages
        ],
        "model_calls": [
            {"id": i, "message_id": m, "config": cfg, "task": task, "status": st, "terminal": term, "latency_ms": lat, "created": round(w, 3)}
            for i, m, cfg, task, st, term, lat, w in calls
        ],
        "deliveries": [
            {"message_id": m, "event": ev, "state": st, "first_audio_ms": fa, "segments": f"{sd}/{stot}", "reason": r, "recorded": round(w, 3)}
            for m, ev, st, fa, sd, stot, r, w in deliveries
        ],
        "playbacks": [
            {"message_id": m, "segment": si, "event": ev, "state": st, "elapsed_ms": el, "reason": r, "recorded": round(w, 3)}
            for m, si, ev, st, el, r, w in playbacks
        ],
    },
}
out.write_text(json.dumps(summary, indent=1, default=str) + "\n")
brief = {
    "voice_on_to_ready_service_s": summary["service_clock"]["voice_on_to_ready_s"],
    "voice_on_to_ready_displayed_s": summary["desktop_display"]["voice_on_to_ready_displayed_s"],
    "messages": [(m["role"], m["content"][:60]) for m in summary["store"]["messages"]],
    "calls": [(c["config"], c["task"], c["status"], c["latency_ms"]) for c in summary["store"]["model_calls"]],
    "desktop_timing": summary["service_clock"]["desktop_timing_reports"],
    "fast_route": summary["service_clock"]["fast_route"],
    "playback_states": [(p["segment"], p["state"], p["elapsed_ms"]) for p in summary["store"]["playbacks"]],
    "dom_events": len(dom_events),
    "precedence": summary["service_clock"]["precedence"],
    "supersession_lines_displayed": sorted({e["progress"] for e in dom_events if e.get("progress") and ("Stopped at your word" in e["progress"] or "set aside" in e["progress"])}),
}
print(json.dumps(brief, default=str))
