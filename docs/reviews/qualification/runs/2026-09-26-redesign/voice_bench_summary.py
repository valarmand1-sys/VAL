"""The Voice bench, summarised per condition and class — owner order of 27 September 2026, §6.

Reads every `voice-bench-<run>.json` named on the command line. Reports, per condition and
per class (social / ordinary): turns, turns with a played answer, the median, 90th
percentile and worst speech-end-to-first-playback — **primary: the driver's exact speech
end to the first audio the real playback worklet started** (both on the page's clock);
beside it the desktop's own report, and the store's first `playback_started` row, which a
pre-existing race can lose (two held reports for one segment computing the same event
number; the loser is refused), so a lost first-segment row makes the store figure one
segment late — counted, never used as the headline — plus the failures and waits that sit beside them:
turns with no played answer, early fragments withdrawn, precedence and resumption
decisions, cold primes, maintenance waits before dispatch, and readiness — kept apart
from the turn figures so a delay moved before "Ready" cannot improve them.

Usage: voice_bench_summary.py OUT.json voice-bench-RUN1.json [...]
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

out, *paths = sys.argv[1:]
runs = [json.loads(Path(p).read_text()) for p in paths]


def dist(values: list[float]) -> dict:
    values = sorted(v for v in values if v is not None)
    if not values:
        return {"n": 0}
    p90 = values[min(len(values) - 1, round(0.9 * (len(values) - 1)))]
    return {
        "n": len(values),
        "median_ms": round(statistics.median(values)),
        "p90_ms": round(p90),
        "max_ms": round(values[-1]),
    }


summary: dict = {}
for condition in sorted({r["condition"] for r in runs}):
    mine = [r for r in runs if r["condition"] == condition]
    # A turn the plan speaks after her answer has played, but which was spoken while her
    # audio was still sounding (the driver gave up waiting 150 s — a runaway segment, or
    # a very long answer), was spoken over her: it measures a barge-in, not this turn.
    # Excluded, and named. A turn spoken after a driver timeout once her audio had ended
    # is an ordinary measurement and stays.
    all_turns = [t for r in mine for t in r["turns"]]
    turns = [t for t in all_turns if not t["spoken_over_her_audio"]]
    block: dict = {"runs": [r["run"] for r in mine]}
    block["excluded_spoken_over_her_audio"] = [
        {"run": t["run"], "session": t["session"], "label": t["label"]}
        for t in all_turns
        if t["spoken_over_her_audio"]
    ]
    block["kept_after_driver_timeout"] = [
        {"run": t["run"], "session": t["session"], "label": t["label"]}
        for t in turns
        if t.get("spoken_after_driver_timeout")
    ]
    for klass in ("social", "ordinary"):
        rows = [t for t in turns if t["class"] == klass and t["label"] != "to be replaced"]
        block[klass] = {
            "turns": len(rows),
            "answered_and_played": sum(1 for t in rows if t["worklet_ms"] is not None),
            "worklet": dist([t["worklet_ms"] for t in rows]),
            "store_record": dist([t["exact_ms"] for t in rows]),
            "store_record_late_by_over_300ms": sum(
                1
                for t in rows
                if t["exact_ms"] is not None
                and t["worklet_ms"] is not None
                and t["exact_ms"] - t["worklet_ms"] > 300
            ),
            "desktop": dist([t["desktop_ms"] for t in rows]),
            "routes": {
                route: sum(1 for t in rows if t["routes"] and t["routes"][-1] == route)
                for route in ("light_conversation", "conversation")
            },
        }
    by_label: dict = {}
    for t in turns:
        by_label.setdefault(t["label"], []).append(t["worklet_ms"])
    block["by_label_worklet"] = {k: dist(v) for k, v in by_label.items()}
    block["no_played_answer"] = [
        {
            "run": r["run"],
            "label": t["label"],
            "heard": t["heard"],
            "routes": t["routes"],
            "statuses": t["call_statuses"],
        }
        for r in mine
        for t in r["turns"]
        if t["worklet_ms"] is None
        and t["label"] != "to be replaced"
        and not t["spoken_over_her_audio"]
    ]
    block["replaced_turn_played"] = [
        {"run": r["run"], "worklet_ms": t["worklet_ms"], "store_ms": t["exact_ms"]}
        for r in mine
        for t in r["turns"]
        if t["label"] == "to be replaced"
    ]
    block["withdrawn_early_fragments"] = sum(t["withdrawn_fragments"] for t in turns)
    block["resumptions"] = sum(len(r["resumptions"]) for r in mine)
    block["precedence_decisions"] = [
        {k: p.get(k) for k in ("relation", "outcome", "answer_heard")}
        for r in mine
        for p in r["precedence"]
        if "relation" in p
    ]
    primes = [p for r in mine for p in r["primes"] if p.get("seconds") is not None]
    block["primes"] = {
        "total": len(primes),
        "cold_over_3s": sum(1 for p in primes if p["seconds"] > 3.0),
        "cold_seconds": [p["seconds"] for p in primes if p["seconds"] > 3.0],
    }
    waits = [
        tl["preflight_wait_ms"]
        for r in mine
        for tl in r["timelines"]
        if tl.get("preflight_wait_ms") is not None
    ]
    block["preflight_wait_ms"] = {
        "n": len(waits),
        "over_300ms": sorted(w for w in waits if w > 300),
        "max": max(waits) if waits else None,
    }
    block["endpoint_to_submitted_ms"] = dist(
        [tl["endpoint_to_submitted_ms"] for r in mine for tl in r["timelines"]]
    )
    block["dispatch_to_visible_ms"] = dist(
        [tl["dispatch_to_visible_ms"] for r in mine for tl in r["timelines"]]
    )
    block["readiness_s"] = [
        x["voice_on_to_ready_displayed_s"] for r in mine for x in r["readiness"]
    ]
    # Where the time goes, per route, from each turn's own timeline (matched by message id).
    for route in ("light_conversation", "conversation"):
        routed = [t for t in turns if t["routes"] and t["routes"][-1] == route and t.get("stages")]
        block[f"stages_{route}"] = {
            key: dist([t["stages"].get(key) for t in routed])
            for key in (
                "to_submitted_ms",
                "preflight_wait_ms",
                "dispatch_to_first_chunk_ms",
                "dispatch_to_visible_ms",
                "visible_to_segment_ms",
                "segment_to_audio_ms",
            )
        }
        cache = [t["stages"].get("engine_cache") for t in routed if t["stages"].get("engine_cache")]
        block[f"stages_{route}"]["engine_cache"] = {
            "turns_seen": len(cache),
            "cold": sum(1 for c in cache if c["cold"]),
        }
    cold_turns = [
        t
        for t in turns
        if (t.get("stages") or {}).get("engine_cache") and t["stages"]["engine_cache"]["cold"]
    ]
    block["cold_prefill_turns"] = [
        {"run": t["run"], "label": t["label"], "worklet_ms": t["worklet_ms"]} for t in cold_turns
    ]
    warm = [
        t["worklet_ms"]
        for t in turns
        if t["class"] == "ordinary"
        and t["worklet_ms"] is not None
        and (t.get("stages") or {}).get("engine_cache")
        and not t["stages"]["engine_cache"]["cold"]
    ]
    block["ordinary_worklet_warm_checkpoint_only"] = dist(warm)
    block["underruns"] = sum((t.get("underruns") or 0) for t in turns)
    summary[condition] = block
Path(out).write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
for condition, block in summary.items():
    print(f"== {condition} ({len(block['runs'])} runs)")
    for klass in ("social", "ordinary"):
        b = block[klass]
        print(
            f"  {klass:8s} turns={b['turns']} played={b['answered_and_played']} worklet={b['worklet']} desktop={b['desktop']} store={b['store_record']} (late {b['store_record_late_by_over_300ms']}) routes={b['routes']}"
        )
    print(
        f"  no played answer: {len(block['no_played_answer'])}; withdrawn early fragments: {block['withdrawn_early_fragments']}; resumptions: {block['resumptions']}"
    )
    print(
        f"  primes: {block['primes']['total']} ({block['primes']['cold_over_3s']} cold); preflight waits >300 ms: {block['preflight_wait_ms']['over_300ms']}"
    )
    print(
        f"  endpoint→submitted: {block['endpoint_to_submitted_ms']}; dispatch→visible: {block['dispatch_to_visible_ms']}"
    )
    print(f"  readiness (s): {block['readiness_s']}")
    print(
        f"  cold-prefill turns: {len(block['cold_prefill_turns'])}; ordinary with a warm checkpoint: {block['ordinary_worklet_warm_checkpoint_only']}; underruns: {block['underruns']}"
    )
    for route in ("light_conversation", "conversation"):
        print(
            f"  stages {route}: "
            + json.dumps(
                {
                    k: (v.get("median_ms") if isinstance(v, dict) and "median_ms" in v else v)
                    for k, v in block[f"stages_{route}"].items()
                }
            )
        )
