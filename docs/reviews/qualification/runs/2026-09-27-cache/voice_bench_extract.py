"""Per-turn figures of one Voice bench run, attributed by identity — remaining latency work, 27 Sept 2026.

Joins the driver's exact speech times (`voice_bench.mjs`), the scratch store (his messages,
their withdrawals, her answers, the model calls, the desktop's playback reports), the
service log, the engine's own log and the memory samples taken during the run.

What changed from the earlier extractor (`2026-09-26-redesign/voice_bench_extract.py`),
each because the owner's order of 27 September asked for attribution, not proximity:

- **First real playback is the intended answer's.** The playback worklet names each
  sound by the desktop's answer key and segment (`key` "A:S"); the desktop's own report
  names the same sound by message and segment. A worklet start is mapped to a message
  when a `playback_started` row for the same segment was recorded within 0.5 s of it,
  and an answer key to a message by those matches. A turn's figure is then the first
  worklet start of *its* answer — never simply the first sound after his speech ended.
  Where no mapping exists the figure is the first sound after his speech, marked
  `worklet_attribution: "uncertain"`.
- **An engine cache line is attributed to one call, or marked uncertain.** Each
  "Prompt cache: using N/M" line is read with the instance named on the line after it;
  a call matches a line when the instance is the call's model identifier, M equals the
  call's `tokens_in`, and the line falls inside the call's own span. Exactly one match
  is an attribution; none or several is `uncertain`, and an uncertain line proves nothing
  about any turn.
- **Primes are calls** (`prefix_prime`), attributed the same way, so cold primes are
  counted by identity, and their work is reported apart from turns.
- **Reliability is counted apart.** A turn spoken over her still-sounding audio measures
  a barge-in, not the turn, and is excluded from latency; runaway speech (the bound's
  own log line), driver timeouts and no-answer turns are counted as failures.

Usage: voice_bench_extract.py CONDITION RUN_LABEL SERVICE.log MEMORY.tsv BENCH_S1.json [...]
Writes voice-bench-<RUN_LABEL>.json beside the logs.
"""

from __future__ import annotations

import glob
import json
import re
import sys
import time as _time
from datetime import datetime
from pathlib import Path

import psycopg

condition, label, log_path, memory_path, *bench_paths = sys.argv[1:]
URL = "postgresql://localhost:5433/val_test"
benches = [json.loads(Path(p).read_text()) for p in bench_paths]
#: The persona checkpoint is at ~5,050–5,090 tokens; reusing less than this is a cold
#: prefill of the persona itself.
PERSONA_TOKENS = 5000

# --- the service log ----------------------------------------------------------------
log: list[dict] = []
bound_lines: list[str] = []
for line in Path(log_path).read_text(errors="replace").splitlines():
    if "speech length bound reached" in line:
        bound_lines.append(line[:300])
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

# --- the store ------------------------------------------------------------------------
with psycopg.connect(URL, options="-c default_transaction_read_only=on") as c:
    messages = c.execute(
        "select m.id::text, m.conversation_id::text, m.sequence, m.role::text, mc.content, "
        "extract(epoch from m.created_at), mc.state::text "
        "from messages m join messages_current mc on mc.id = m.id order by m.conversation_id, m.sequence"
    ).fetchall()
    calls = c.execute(
        "select mc.id::text, mc.message_id::text, mc.task_type::text, mc.status::text, "
        "mc.tokens_in, extract(epoch from mc.created_at), mc.latency_ms, mc.model_identifier, "
        "coalesce(x.runtime_diagnostics->'superseded'->>'reason', '') "
        "from model_calls mc left join model_call_measurements x on x.model_call_id = mc.id "
        "order by mc.created_at"
    ).fetchall()
    playbacks = c.execute(
        "select message_id::text, segment_index, state, extract(epoch from recorded_at) "
        "from speech_playbacks order by recorded_at"
    ).fetchall()
    deliveries = c.execute(
        "select message_id::text, state, reason from speech_deliveries order by recorded_at"
    ).fetchall()

# --- the engine's log: each cache line with the instance named on the next line --------
engine_lines: list[dict] = []
bodies: list[dict] = []
started_at = min(b["voice_on_click_wall"] for b in benches) / 1000 - 60
ended_at = max(b["voice_off_wall"] for b in benches) / 1000 + 60
for path in sorted(glob.glob(str(Path.home() / ".lmstudio/server-logs/2026-09/2026-09-2*.log"))):
    lines = open(path, errors="replace").read().splitlines()
    body: dict | None = None
    for index, line in enumerate(lines):
        stamp = re.match(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\]", line)
        at = _time.mktime(_time.strptime(stamp.group(1), "%Y-%m-%d %H:%M:%S")) if stamp else None
        if at is not None and not (started_at <= at <= ended_at):
            continue
        if "Received request: POST to /v1/chat/completions with body" in line:
            body = {"at": at}
            bodies.append(body)
            continue
        if body is not None:
            field = re.match(r'\s*"(model|reasoning_effort|max_tokens)": "?([^",]*)"?,?\s*$', line)
            if field:
                body[field.group(1)] = field.group(2)
            if stamp:
                body = None
        hit = re.search(r"Prompt cache: using (\d+)/(\d+) tokens", line)
        if hit and at is not None:
            instance = None
            for following in lines[index + 1 : index + 6]:
                named = re.search(r"\]\[INFO\]\[([^\]]+)\] Prompt processing progress", following)
                if named:
                    instance = named.group(1)
                    break
            engine_lines.append(
                {"at": at, "cached": int(hit.group(1)), "prompt": int(hit.group(2)), "instance": instance}
            )


def attribute(call: tuple) -> dict:
    """The one engine line this call's prefill wrote, or `uncertain`."""
    _id, _message, _task, _status, tokens_in, created, latency_ms, model, _sup = call
    span_start = float(created) - (latency_ms or 0) / 1000 - 3
    span_end = float(created) + 1
    found = [
        e for e in engine_lines
        if e["instance"] == model and e["prompt"] == tokens_in and span_start <= e["at"] <= span_end
    ]
    if len(found) != 1:
        return {"attribution": "uncertain", "candidates": len(found)}
    e = found[0]
    return {
        "attribution": "identity",
        "cached_tokens": e["cached"],
        "prompt_tokens": e["prompt"],
        "cold": e["cached"] < PERSONA_TOKENS,
        "fully_cached_suffix_tokens": e["prompt"] - e["cached"],
    }


calls_by_message: dict[str, list] = {}
for call in calls:
    if call[1]:
        calls_by_message.setdefault(call[1], []).append(call)
prime_calls = [call for call in calls if call[2] == "prefix_prime"]

# --- the turn timelines ---------------------------------------------------------------
timeline_by_message: dict[str, dict] = {}
for e in log:
    if e["kind"] == "voice turn timeline" and isinstance(e["data"], dict) and e["data"].get("message_id"):
        d = e["data"]
        anchor = datetime.fromisoformat(d["anchor_wall"]).timestamp()
        timeline_by_message[d["message_id"]] = {
            "anchor": anchor, "anchor_kind": d["anchor"],
            "marks": {k: v["first_ms"] for k, v in d["marks"].items()},
        }


def stages(message_id: str | None) -> dict:
    t = timeline_by_message.get(message_id or "")
    if t is None:
        return {}
    m = t["marks"]

    def gap(a: str, b: str) -> float | None:
        return None if m.get(a) is None or m.get(b) is None else round(m[b] - m[a])

    conversation = [c for c in calls_by_message.get(message_id or "", [])
                    if c[2] in ("conversation", "light_conversation")]
    return {
        "anchor": t["anchor_kind"],
        "to_submitted_ms": m.get("owner_turn_submitted"),
        "preflight_wait_ms": gap("exact_preflight_start", "exact_preflight_end"),
        "dispatch_to_first_chunk_ms": gap("provider_dispatch", "provider_chunk"),
        "dispatch_to_visible_ms": gap("provider_dispatch", "provider_visible_text"),
        "visible_to_segment_ms": gap("provider_visible_text", "speech_segment_queued"),
        "segment_to_audio_ms": gap("speech_segment_queued", "audio_at_sink"),
        "engine_cache": attribute(conversation[-1]) if conversation else None,
    }


# --- worklet sounds, mapped to messages by the desktop's own reports ---------------------
started_rows = [(mid, seg, float(at)) for mid, seg, state, at in playbacks if state == "playback_started"]
key_votes: dict[str, dict[str, int]] = {}
for bench in benches:
    for event in bench["playback_events"]:
        if event.get("type") != "started" or not event.get("key"):
            continue
        answer_key, _, segment = str(event["key"]).partition(":")
        wall = event["wall"] / 1000
        for mid, seg, at in started_rows:
            if str(seg) == segment and abs(at - wall) <= 0.5:
                votes = key_votes.setdefault(f"{bench['session']}#{answer_key}", {})
                votes[mid] = votes.get(mid, 0) + 1
key_to_message = {k: max(v, key=v.get) for k, v in key_votes.items()}


def first_sound_of(bench: dict, message_id: str | None, after: float, before: float) -> tuple[float | None, str]:
    for event in bench["playback_events"]:
        if event.get("type") != "started" or not event.get("key"):
            continue
        answer_key = str(event["key"]).partition(":")[0]
        if message_id and key_to_message.get(f"{bench['session']}#{answer_key}") == message_id:
            return event["wall"], "identity"
    first = next(
        (e["wall"] for e in bench["playback_events"]
         if e.get("type") == "started" and after < e["wall"] < before),
        None,
    )
    return first, "uncertain"


def spoken_over_her_audio(bench: dict, turn: dict) -> bool:
    before = [
        e for e in bench.get("playback_events", [])
        if e["wall"] < turn["speech_start_wall"] and e.get("type") in ("started", "completed", "stopped")
    ]
    return bool(before) and before[-1]["type"] == "started"


by_conversation: dict[str, list] = {}
for row in messages:
    by_conversation.setdefault(row[1], []).append(row)
desktop_reports = [
    e for e in log if e["kind"] == "voice desktop timing" and isinstance(e["data"], dict)
    and e["data"].get("speech_end_to_playback_start_ms") is not None
]

rows = []
all_turns = [(b, t) for b in benches for t in b["turns"]]
for index, (bench, turn) in enumerate(all_turns):
    start = turn["speech_start_wall"] / 1000
    end = turn["speech_end_wall"] / 1000
    same_session_next = index + 1 < len(all_turns) and all_turns[index + 1][0] is bench
    nxt = all_turns[index + 1][1]["speech_start_wall"] / 1000 if same_session_next else bench["voice_off_wall"] / 1000
    mine = [m for m in messages if m[3] == "user" and start <= float(m[5]) < nxt]
    live = [m for m in mine if (m[6] or "current") not in ("withdrawn",)]
    msg = live[-1] if live else None
    answer = None
    if msg is not None:
        seq = by_conversation[msg[1]]
        after = [m for m in seq if m[2] > msg[2]]
        if after and after[0][3] == "val":
            answer = after[0]
    first_wall, how = first_sound_of(bench, answer[0] if answer else None, turn["speech_end_wall"], nxt * 1000)
    route = [c[2] for c in calls_by_message.get(msg[0], [])] if msg else []
    statuses = [c[3] for c in calls_by_message.get(msg[0], [])] if msg else []
    desk = next((e["data"]["speech_end_to_playback_start_ms"] for e in desktop_reports if end < e["wall"] < nxt + 5), None)
    completion = next((e["data"] for e in log if e["kind"] == "turn completion" and end - 1 < e["wall"] < end + 6), None)
    rows.append({
        "condition": condition, "run": label, "session": bench["session"], "label": turn["label"],
        "class": turn["class"], "said": turn["text"], "heard": msg[4] if msg else None,
        "withdrawn_fragments": len(mine) - len(live),
        "answer_message_id": answer[0] if answer else None,
        "answer": answer[4][:200] if answer else None,
        "routes": route, "call_statuses": statuses,
        "worklet_ms": None if first_wall is None else round(first_wall - turn["speech_end_wall"]),
        "worklet_attribution": how if first_wall is not None else "no sound",
        "worklet_underruns": turn.get("worklet_underruns"),
        "desktop_ms": desk,
        "completion": completion,
        "spoken_after_driver_timeout": bool(turn.get("previous_wait_timed_out")),
        "spoken_over_her_audio": spoken_over_her_audio(bench, turn),
        "internal_pauses_s": turn.get("internal_pauses_s"),
        "message_id": msg[0] if msg else None,
        "stages": stages(msg[0] if msg else None),
    })

primes = [e["data"] for e in log if e["kind"] == "voice prime" and isinstance(e["data"], dict)]
memory = []
for line in Path(memory_path).read_text().splitlines():
    parts = line.split("\t")
    if len(parts) >= 3 and parts[1].isdigit():
        memory.append({"at": float(parts[0]), "free_percent": int(parts[1]), "swap_used_mb": float(parts[2])})
report = {
    "condition": condition, "run": label, "turns": rows,
    "readiness": [{"session": b["session"], "voice_on_to_ready_displayed_s": b["voice_on_to_ready_displayed_s"]} for b in benches],
    "primes": [{"kind": p.get("kind"), "seconds": p.get("seconds"),
                "partner": (p.get("result") or {}).get("outcome"),
                "light": ((p.get("result") or {}).get("light") or {}).get("outcome")} for p in primes],
    "prime_calls": [{"model": c[7], "tokens_in": c[4], "latency_ms": c[6], **attribute(c)} for c in prime_calls],
    "engine_lines_in_run": len(engine_lines),
    "request_bodies": [{k: b.get(k) for k in ("model", "reasoning_effort", "max_tokens")} for b in bodies],
    "call_models": sorted({c[7] for c in calls}),
    "timelines": [
        {"utterance": e["data"]["utterance"], "message_id": e["data"].get("message_id"),
         **{k: v["first_ms"] for k, v in e["data"]["marks"].items()}}
        for e in log if e["kind"] == "voice turn timeline" and isinstance(e["data"], dict)
    ],
    "resumptions": [e["data"] for e in log if e["kind"] == "voice resume"],
    "precedence": [e["data"] for e in log if e["kind"] == "voice precedence"],
    "fast_route": [e["data"] for e in log if e["kind"] == "fast route"],
    "deliveries_not_completed": [d for d in deliveries if d[1] != "completed"],
    "speech_bound_reached": bound_lines,
    "memory": memory,
}
out = Path(log_path).with_name(f"voice-bench-{label}.json")
out.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str) + "\n")
for r in rows:
    cache = (r["stages"] or {}).get("engine_cache") or {}
    print(f"{r['label'][:36]:36s} {str(r['worklet_ms']):>6s} {r['worklet_attribution'][:5]:5s} "
          f"{','.join(r['routes'])[:28]:28s} cache={cache.get('cached_tokens', cache.get('attribution'))} "
          f"heard={str(r['heard'])[:40]!r}")
print("prime calls:", [(p["model"][-10:], p.get("cached_tokens", p["attribution"])) for p in report["prime_calls"]])
print("models called:", report["call_models"])
