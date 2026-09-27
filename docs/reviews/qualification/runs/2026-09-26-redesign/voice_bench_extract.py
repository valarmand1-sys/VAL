"""Per-turn figures of one Voice bench run — owner order of 27 September 2026, §6.

Joins the driver's exact speech times (`voice_bench.mjs`), the scratch store (his messages,
their withdrawals, her answers, the model calls, the desktop's playback reports) and the
service log (the desktop's own timing reports, routes, completion windows, resumptions,
precedence decisions, primes, per-turn timelines).

**The turn's message is found by identity, not by time alone:** the last live (not
withdrawn) message of his created between this turn's speech start and the next turn's;
its answer is the next message of hers in the conversation; the first real playback is
the earliest `playback_started` the frontend reported for that answer. So a replaced or
joined turn is never credited with another answer's audio.

Two latencies per turn, both to the frontend's first playback of the answer:
- `exact_ms`: from the driver's exact end of speech (the last sound it played);
- `desktop_ms`: the frontend's own report (its speech end is the recognizer's estimate).

Usage: voice_bench_extract.py CONDITION RUN_LABEL SERVICE.log BENCH_S1.json [BENCH_S2.json ...]
Writes voice-bench-<RUN_LABEL>.json beside the logs.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import psycopg

condition, label, log_path, *bench_paths = sys.argv[1:]
URL = "postgresql://localhost:5433/val_test"
benches = [json.loads(Path(p).read_text()) for p in bench_paths]

log: list[dict] = []
for line in Path(log_path).read_text(errors="replace").splitlines():
    m = re.match(
        r"(\d+\.\d+) INFO:val\.[a-z_.]+:(voice desktop timing|fast route|turn completion|voice resume|"
        r"voice precedence|voice prime|voice turn timeline|voice readiness|voice endpoint)(?:: (.*))?",
        line,
    )
    if not m:
        continue
    body = m.group(3) or ""
    try:
        data = json.loads(body) if body.startswith("{") else body
    except ValueError:
        data = body
    if m.group(2) == "voice endpoint" and isinstance(data, str) and " {" in data:
        idx, js = data.split(" ", 1)
        try:
            data = {"utterance": int(idx.split("=")[1]), **json.loads(js)}
        except ValueError:
            pass
    log.append({"wall": float(m.group(1)), "kind": m.group(2), "data": data})

with psycopg.connect(URL, options="-c default_transaction_read_only=on") as c:
    messages = c.execute(
        "select m.id::text, m.conversation_id::text, m.sequence, m.role::text, mc.content, "
        "extract(epoch from m.created_at), mc.state::text "
        "from messages m join messages_current mc on mc.id = m.id order by m.conversation_id, m.sequence"
    ).fetchall()
    calls = c.execute(
        "select message_id::text, task_type::text, status::text, terminal_state::text, latency_ms, "
        "coalesce(x.runtime_diagnostics->'superseded'->>'reason', '') "
        "from model_calls mc left join model_call_measurements x on x.model_call_id = mc.id "
        "where message_id is not null order by mc.created_at"
    ).fetchall()
    playbacks = c.execute(
        "select message_id::text, segment_index, state, extract(epoch from recorded_at) "
        "from speech_playbacks order by recorded_at"
    ).fetchall()
    deliveries = c.execute(
        "select message_id::text, state, reason from speech_deliveries order by recorded_at"
    ).fetchall()

# The engine's own verdict per request: "Prompt cache: using N/M tokens from cache", local
# time to the second. A turn's request is the one dispatched with it whose prompt is larger
# than any prime's.
import glob
import time as _time

engine_lines: list[tuple[float, int, int]] = []
for path in sorted(glob.glob(str(Path.home() / ".lmstudio/server-logs/2026-09/2026-09-2*.log"))):
    for line in open(path, errors="replace"):
        hit = re.match(
            r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\].*Prompt cache: using (\d+)/(\d+) tokens", line
        )
        if hit:
            at = _time.mktime(_time.strptime(hit.group(1), "%Y-%m-%d %H:%M:%S"))
            engine_lines.append((at, int(hit.group(2)), int(hit.group(3))))

timeline_by_message: dict[str, dict] = {}
for e in log:
    if (
        e["kind"] == "voice turn timeline"
        and isinstance(e["data"], dict)
        and e["data"].get("message_id")
    ):
        d = e["data"]
        anchor = datetime.fromisoformat(d["anchor_wall"]).timestamp()
        timeline_by_message[d["message_id"]] = {
            "anchor": anchor,
            "anchor_kind": d["anchor"],
            "marks": {k: v["first_ms"] for k, v in d["marks"].items()},
        }


def stages(message_id: str | None) -> dict:
    t = timeline_by_message.get(message_id or "")
    if t is None:
        return {}
    m = t["marks"]

    def gap(a, b):
        return None if m.get(a) is None or m.get(b) is None else round(m[b] - m[a])

    dispatch = m.get("provider_dispatch")
    cached = None
    if dispatch is not None:
        at = t["anchor"] + dispatch / 1000
        near = [x for x in engine_lines if at - 1.5 <= x[0] <= at + 1.5 and x[2] > 5300]
        if near:
            cached = {
                "cached_tokens": near[0][1],
                "prompt_tokens": near[0][2],
                "cold": near[0][1] < 5000,
            }
    return {
        "anchor": t["anchor_kind"],
        "to_submitted_ms": m.get("owner_turn_submitted"),
        "preflight_wait_ms": gap("exact_preflight_start", "exact_preflight_end"),
        "dispatch_to_first_chunk_ms": gap("provider_dispatch", "provider_chunk"),
        "dispatch_to_visible_ms": gap("provider_dispatch", "provider_visible_text"),
        "visible_to_segment_ms": gap("provider_visible_text", "speech_segment_queued"),
        "segment_to_audio_ms": gap("speech_segment_queued", "audio_at_sink"),
        "engine_cache": cached,
    }


first_play: dict[str, float] = {}
for mid, _seg, state, at in playbacks:
    if state == "playback_started" and mid not in first_play:
        first_play[mid] = float(at)
by_conversation: dict[str, list] = {}
for row in messages:
    by_conversation.setdefault(row[1], []).append(row)
calls_by_message: dict[str, list] = {}
for row in calls:
    calls_by_message.setdefault(row[0], []).append(row[1:])
desktop_reports = [
    e
    for e in log
    if e["kind"] == "voice desktop timing"
    and isinstance(e["data"], dict)
    and e["data"].get("speech_end_to_playback_start_ms") is not None
]


def spoken_over_her_audio(bench: dict, turn: dict) -> bool:
    """Her audio was still sounding when he began: the last playback event before his
    speech started is a start with no completion or stop after it. Such a turn was
    spoken over her (a barge-in), not after her answer as the plan intended."""
    before = [
        e
        for e in bench.get("playback_events", [])
        if e["wall"] < turn["speech_start_wall"]
        and e.get("type") in ("started", "completed", "stopped")
    ]
    return bool(before) and before[-1]["type"] == "started"


rows = []
all_turns = [(b, t) for b in benches for t in b["turns"]]
for index, (bench, turn) in enumerate(all_turns):
    start = turn["speech_start_wall"] / 1000
    end = turn["speech_end_wall"] / 1000
    same_session_next = index + 1 < len(all_turns) and all_turns[index + 1][0] is bench
    nxt = (
        all_turns[index + 1][1]["speech_start_wall"] / 1000
        if same_session_next
        else bench["voice_off_wall"] / 1000
    )
    mine = [m for m in messages if m[3] == "user" and start <= float(m[5]) < nxt]
    live = [m for m in mine if (m[6] or "current") not in ("withdrawn",)]
    msg = live[-1] if live else None
    answer = None
    if msg is not None:
        seq = by_conversation[msg[1]]
        after = [m for m in seq if m[2] > msg[2]]
        if after and after[0][3] == "val":
            answer = after[0]
    play = first_play.get(answer[0]) if answer else None
    route = [c[0] for c in calls_by_message.get(msg[0], [])] if msg else []
    statuses = [c[1] for c in calls_by_message.get(msg[0], [])] if msg else []
    desk = next(
        (
            e["data"]["speech_end_to_playback_start_ms"]
            for e in desktop_reports
            if end < e["wall"] < nxt + 5
        ),
        None,
    )
    completion = next(
        (
            e["data"]
            for e in log
            if e["kind"] == "turn completion" and end - 1 < e["wall"] < end + 6
        ),
        None,
    )
    rows.append(
        {
            "condition": condition,
            "run": label,
            "session": bench["session"],
            "label": turn["label"],
            "class": turn["class"],
            "said": turn["text"],
            "heard": msg[4] if msg else None,
            "withdrawn_fragments": len(mine) - len(live),
            "answer": answer[4][:160] if answer else None,
            "routes": route,
            "call_statuses": statuses,
            "exact_ms": None if play is None else round((play - end) * 1000),
            "worklet_ms": None
            if turn.get("worklet_first_started_wall") is None
            else turn["worklet_first_started_wall"] - turn["speech_end_wall"],
            "underruns": turn.get("worklet_underruns"),
            "desktop_ms": desk,
            "completion": completion,
            "spoken_after_driver_timeout": bool(turn.get("previous_wait_timed_out")),
            "spoken_over_her_audio": spoken_over_her_audio(bench, turn),
            "message_id": msg[0] if msg else None,
            "stages": stages(msg[0] if msg else None),
        }
    )

readiness = [
    {"session": b["session"], "voice_on_to_ready_displayed_s": b["voice_on_to_ready_displayed_s"]}
    for b in benches
]
primes = [e["data"] for e in log if e["kind"] == "voice prime" and isinstance(e["data"], dict)]
timelines = []
for e in log:
    if e["kind"] == "voice turn timeline" and isinstance(e["data"], dict):
        m = {k: v["first_ms"] for k, v in e["data"]["marks"].items()}
        timelines.append(
            {
                "utterance": e["data"]["utterance"],
                "endpoint_to_submitted_ms": m.get("owner_turn_submitted"),
                "preflight_wait_ms": None
                if m.get("exact_preflight_end") is None
                else round(m["exact_preflight_end"] - m["exact_preflight_start"]),
                "dispatch_to_first_chunk_ms": None
                if m.get("provider_chunk") is None or m.get("provider_dispatch") is None
                else round(m["provider_chunk"] - m["provider_dispatch"]),
                "dispatch_to_visible_ms": None
                if m.get("provider_visible_text") is None or m.get("provider_dispatch") is None
                else round(m["provider_visible_text"] - m["provider_dispatch"]),
                "endpoint_to_segment_ms": m.get("speech_segment_queued"),
                "endpoint_to_audio_ms": m.get("audio_at_sink"),
            }
        )
report = {
    "condition": condition,
    "run": label,
    "turns": rows,
    "readiness": readiness,
    "primes": [
        {
            "kind": p.get("kind"),
            "seconds": p.get("seconds"),
            "partner": (p.get("result") or {}).get("outcome"),
            "light": ((p.get("result") or {}).get("light") or {}).get("outcome"),
        }
        for p in primes
    ],
    "timelines": timelines,
    "resumptions": [e["data"] for e in log if e["kind"] == "voice resume"],
    "precedence": [e["data"] for e in log if e["kind"] == "voice precedence"],
    "fast_route": [e["data"] for e in log if e["kind"] == "fast route"],
    "deliveries_interrupted": [d for d in deliveries if d[1] == "interrupted"],
}
out = Path(log_path).with_name(f"voice-bench-{label}.json")
out.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str) + "\n")
for r in rows:
    print(
        f"{r['label'][:34]:34s} {str(r['exact_ms']):>6s} {str(r['worklet_ms']):>6s} {str(r['desktop_ms']):>7s} {','.join(r['routes'])[:40]:40s} heard={str(r['heard'])[:50]!r}"
    )
print("readiness:", readiness)
