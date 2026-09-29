"""Where an ordinary turn's wait goes — the critical path, 28 Sept 2026 (owner's follow-up).

For every counted ordinary (MEDIUM, conversation route) turn of the named runs — S1–S4,
not spoken over her audio, not the turn to be replaced, first real playback attributed by
identity — the interval from his speech ending (the driver's exact wall time) to her
first real playback (the playback worklet's own `started`) is cut at successive marks of
the service's own turn timeline, so the pieces are consecutive on the critical path and
sum to the whole: nothing is counted twice. Work that overlaps the path (synthesis of
later segments, generation continuing while the first segment is voiced, the refresh
prime) is off the path by construction and is not added.

  endpoint       speech end -> endpoint (the recognizer's silence rule)
  confirmation   endpoint -> turn submitted (final decode, the resume window)
  core           submitted -> provider dispatch (persist, assembly, egress, preflight,
                 runtime check — and any wait behind maintenance)
  prefill        dispatch -> first streamed chunk, split with the hook's own measurement
                 of the engine's update_cache (cache restore + prefill) where matched
  reasoning      first chunk -> first visible text (hidden reasoning)
  segment        first visible text -> first usable segment queued
  synthesis      segment queued -> first audio at the sink
  playback       sink -> first real playback (desktop poll, merge-window hold, start)

Usage: wait_decomposition.py OUT.json RUN [RUN ...]   (reads voice-bench-RUN.json,
voice-bench-RUN-session-N.json, service-RUN.log and hook-RUN.log beside this file)
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
out, *runs = sys.argv[1:]
PIECES = ("endpoint", "confirmation", "core", "prefill", "reasoning", "segment", "synthesis", "playback")
rows = []
for run in runs:
    extracted = json.loads((HERE / f"voice-bench-{run}.json").read_text())
    timelines = {}
    for line in (HERE / f"service-{run}.log").read_text().splitlines():
        if "voice turn timeline: {" in line:
            d = json.loads(line.split("voice turn timeline: ", 1)[1])
            if d.get("message_id") and d.get("anchor") == "endpoint":
                timelines[d["message_id"]] = (
                    datetime.fromisoformat(d["anchor_wall"]).timestamp() * 1000,
                    {k: v["first_ms"] for k, v in d["marks"].items()},
                )
    hook = []
    for line in (HERE / f"hook-{run}.log").read_text().splitlines():
        if " request {" in line:
            at = time.mktime(time.strptime(line[:19], "%Y-%m-%dT%H:%M:%S")) * 1000
            hook.append((at, json.loads(line.split(" request ", 1)[1])))
    speech_end = {}
    for index in range(5):
        path = HERE / f"voice-bench-{run}-session-{index}.json"
        if path.exists():
            session = json.loads(path.read_text())
            for position, turn in enumerate(session["turns"]):
                speech_end[(session["session"], position)] = turn["speech_end_wall"]
    positions: dict[str, int] = {}
    for turn in extracted["turns"]:
        position = positions.get(turn["session"], 0)
        positions[turn["session"]] = position + 1
        if (turn["class"] != "ordinary" or turn["session"].startswith("S5") or turn["spoken_over_her_audio"]
                or turn["label"] == "to be replaced" or turn["worklet_attribution"] != "identity"
                or not turn["routes"] or turn["routes"][-1] != "conversation"):
            continue
        found = timelines.get(turn["message_id"])
        end = speech_end.get((turn["session"], position))
        if found is None or end is None or turn["worklet_ms"] is None:
            rows.append({"run": run, "label": turn["label"], "missing": "timeline or speech end"})
            continue
        anchor, m = found
        need = ("owner_turn_submitted", "provider_dispatch", "provider_chunk", "speech_first_visible_text",
                "speech_segment_queued", "audio_at_sink")
        if any(m.get(k) is None for k in need):
            rows.append({"run": run, "label": turn["label"], "missing": [k for k in need if m.get(k) is None]})
            continue
        playback = end + turn["worklet_ms"]
        piece = {
            "endpoint": anchor - end,
            "confirmation": m["owner_turn_submitted"],
            "core": m["provider_dispatch"] - m["owner_turn_submitted"],
            "prefill": m["provider_chunk"] - m["provider_dispatch"],
            "reasoning": m["speech_first_visible_text"] - m["provider_chunk"],
            "segment": m["speech_segment_queued"] - m["speech_first_visible_text"],
            "synthesis": m["audio_at_sink"] - m["speech_segment_queued"],
            "playback": playback - (anchor + m["audio_at_sink"]),
        }
        cache = (turn["stages"] or {}).get("engine_cache") or {}
        dispatch_wall = anchor + m["provider_dispatch"]
        matched = [h for at, h in hook if h.get("total") == cache.get("prompt_tokens")
                   and dispatch_wall - 1500 <= at <= anchor + m["provider_chunk"] + 1500]
        rows.append({
            "run": run, "session": turn["session"], "label": turn["label"], "total": turn["worklet_ms"],
            "pieces": {k: round(v) for k, v in piece.items()},
            "sum_check": round(sum(piece.values()) - turn["worklet_ms"]),
            "engine_update_cache_ms": matched[0].get("update_cache_ms") if len(matched) == 1 else None,
            "uncached_tokens": cache.get("fully_cached_suffix_tokens"),
            "preflight_wait_ms": (turn["stages"] or {}).get("preflight_wait_ms"),
        })

good = [r for r in rows if "pieces" in r]


def dist(values: list) -> dict:
    values = sorted(v for v in values if v is not None)
    if not values:
        return {"n": 0}
    return {"n": len(values), "median": round(statistics.median(values)),
            "p90": round(values[min(len(values) - 1, round(0.9 * (len(values) - 1)))]), "max": round(values[-1])}


summary = {
    "runs": runs, "turns": len(good), "missing": [r for r in rows if "pieces" not in r],
    "total_ms": dist([r["total"] for r in good]),
    "pieces_ms": {k: dist([r["pieces"][k] for r in good]) for k in PIECES},
    "share_of_summed_medians": None,
    "mean_ms": {k: round(statistics.mean(r["pieces"][k] for r in good)) for k in PIECES} if good else {},
    "engine_update_cache_ms": dist([r["engine_update_cache_ms"] for r in good]),
    "uncached_tokens": dist([r["uncached_tokens"] for r in good]),
    "sum_check_ms": dist([abs(r["sum_check"]) for r in good]),
}
total_mean = sum(summary["mean_ms"].values()) or 1
summary["share_of_mean"] = {k: round(v / total_mean, 3) for k, v in summary["mean_ms"].items()}
del summary["share_of_summed_medians"]
Path(out).write_text(json.dumps({"summary": summary, "turns": rows}, indent=1) + "\n")
print(json.dumps(summary, indent=1))
