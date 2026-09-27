"""The live cache experiment, summarised per condition — remaining latency work, 27 Sept 2026, §3.

Reads every `voice-bench-<run>.json` named. Per condition (renewal_off / renewal_on):

- speech end → first real playback of **the intended answer** (identity-attributed; an
  uncertain attribution is counted and kept out), social and ordinary, median / p90 /
  worst — excluding turns spoken over her still-sounding audio, which are barge-ins;
- cache reuse **by identity**: per turn, whether the engine's own line for that call
  reused the persona checkpoint; uncertain lines are counted, never used;
- primes: count, cold by identity, their seconds — work kept apart from turn figures;
- waiting: preflight waits over 1 s (a request queued behind maintenance);
- memory: lowest free percentage and swap growth during the run;
- reliability, apart: bound-reached speech, turns without a played answer, driver
  timeouts, turns spoken over her audio;
- S4 (sustained alternation): ordinary MEDIUM first-audio by position, to show whether
  the wait grows as history grows;
- S5 (merge window): per pause, what became of the early fragment — kept out of the
  latency distributions, since a continuation kept after the window waits by policy for
  the whole earlier answer.

Usage: cache_bench_summary.py OUT.json voice-bench-RUN.json [...]
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

out, *paths = sys.argv[1:]
runs = [json.loads(Path(p).read_text()) for p in paths]


def dist(values: list) -> dict:
    values = sorted(v for v in values if v is not None)
    if not values:
        return {"n": 0}
    p90 = values[min(len(values) - 1, round(0.9 * (len(values) - 1)))]
    return {"n": len(values), "median_ms": round(statistics.median(values)), "p90_ms": round(p90),
            "max_ms": round(values[-1])}


summary: dict = {}
for condition in sorted({r["condition"] for r in runs}):
    mine = [r for r in runs if r["condition"] == condition]
    turns = [t for r in mine for t in r["turns"]]
    # Latency is measured on S1–S4. S5 tests what the merge window does with his words,
    # and a continuation kept after the window waits, by policy, for the whole earlier
    # answer to play: a semantics result, reported on its own below.
    counted = [t for t in turns if not t["spoken_over_her_audio"] and t["label"] != "to be replaced"
               and not t["session"].startswith("S5")]
    block: dict = {"runs": [r["run"] for r in mine]}
    for klass in ("social", "ordinary"):
        rows = [t for t in counted if t["class"] == klass]
        ident = [t for t in rows if t["worklet_attribution"] == "identity"]
        block[klass] = {
            "turns": len(rows),
            "identity_attributed": len(ident),
            "uncertain_or_no_sound": [{"run": t["run"], "label": t["label"], "attribution": t["worklet_attribution"]}
                                      for t in rows if t["worklet_attribution"] != "identity"],
            "first_real_playback": dist([t["worklet_ms"] for t in ident]),
            "desktop_report": dist([t["desktop_ms"] for t in ident]),
            "routes": {route: sum(1 for t in ident if t["routes"] and t["routes"][-1] == route)
                       for route in ("light_conversation", "conversation")},
        }
    by_route: dict = {}
    for route in ("light_conversation", "conversation"):
        rows = [t for t in counted if t["routes"] and t["routes"][-1] == route and t["worklet_attribution"] == "identity"]
        cache = [(t["stages"] or {}).get("engine_cache") or {} for t in rows]
        by_route[route] = {
            "first_real_playback": dist([t["worklet_ms"] for t in rows]),
            "cache_identity": sum(1 for c in cache if c.get("attribution") == "identity"),
            "cache_uncertain": sum(1 for c in cache if c.get("attribution") != "identity"),
            "cold_by_identity": sum(1 for c in cache if c.get("attribution") == "identity" and c["cold"]),
            "uncached_suffix_tokens": dist([c.get("fully_cached_suffix_tokens") for c in cache if c.get("attribution") == "identity"]),
            "dispatch_to_first_chunk_ms": dist([(t["stages"] or {}).get("dispatch_to_first_chunk_ms") for t in rows]),
            "dispatch_to_visible_ms": dist([(t["stages"] or {}).get("dispatch_to_visible_ms") for t in rows]),
            "segment_to_audio_ms": dist([(t["stages"] or {}).get("segment_to_audio_ms") for t in rows]),
            "to_submitted_ms": dist([(t["stages"] or {}).get("to_submitted_ms") for t in rows]),
        }
    block["by_route"] = by_route
    cold_turns = [{"run": t["run"], "session": t["session"], "label": t["label"], "worklet_ms": t["worklet_ms"],
                   "cached": ((t["stages"] or {}).get("engine_cache") or {}).get("cached_tokens")}
                  for t in counted if ((t["stages"] or {}).get("engine_cache") or {}).get("cold")]
    block["cold_turns"] = cold_turns
    waits = [{"run": t["run"], "label": t["label"], "wait_ms": (t["stages"] or {}).get("preflight_wait_ms"),
              "worklet_ms": t["worklet_ms"]}
             for t in counted if ((t["stages"] or {}).get("preflight_wait_ms") or 0) > 1000]
    block["waits_over_1s"] = waits
    affected = [t for t in counted if ((t["stages"] or {}).get("engine_cache") or {}).get("cold")
                or ((t["stages"] or {}).get("preflight_wait_ms") or 0) > 1000]
    block["unaffected"] = {
        klass: dist([t["worklet_ms"] for t in counted if t["class"] == klass and t not in affected
                     and t["worklet_attribution"] == "identity"])
        for klass in ("social", "ordinary")
    }
    block["affected"] = dist([t["worklet_ms"] for t in affected if t["worklet_attribution"] == "identity"])
    primes = [p for r in mine for p in r["prime_calls"]]
    block["primes"] = {
        "calls": len(primes),
        "identity": sum(1 for p in primes if p["attribution"] == "identity"),
        "cold_by_identity": sum(1 for p in primes if p["attribution"] == "identity" and p["cached_tokens"] < 5000),
        "latency_ms_warm": dist([p["latency_ms"] for p in primes if p["attribution"] == "identity" and p["cached_tokens"] >= 5000]),
        "latency_ms_cold": dist([p["latency_ms"] for p in primes if p["attribution"] == "identity" and p["cached_tokens"] < 5000]),
    }
    block["readiness_s"] = [x["voice_on_to_ready_displayed_s"] for r in mine for x in r["readiness"]]
    memory = [m for r in mine for m in r["memory"]]
    block["memory"] = {
        "lowest_free_percent": min((m["free_percent"] for m in memory), default=None),
        "swap_used_mb": sorted({m["swap_used_mb"] for m in memory})[-1:] if memory else None,
        "swap_growth_mb_per_run": [
            round(max(m["swap_used_mb"] for m in r["memory"]) - min(m["swap_used_mb"] for m in r["memory"]), 1)
            for r in mine if r["memory"]
        ],
    }
    block["effort_on_the_wire"] = sorted({(b.get("reasoning_effort"), b.get("max_tokens")) for r in mine for b in r["request_bodies"]})
    block["models_called"] = sorted({m for r in mine for m in r["call_models"]})
    block["reliability"] = {
        # Counted from each answer's final delivery state, which names the bound.
        "speech_bound_reached": sum(
            1 for r in mine for d in r["deliveries_not_completed"] if "speech length bound reached" in (d[2] or "")
        ),
        "deliveries_failed": [d[2][:160] for r in mine for d in r["deliveries_not_completed"]],
        "no_played_answer": [{"run": t["run"], "label": t["label"], "statuses": t["call_statuses"]}
                             for t in counted if t["worklet_ms"] is None],
        "driver_timeouts": sum(1 for t in turns if t["spoken_after_driver_timeout"]),
        "spoken_over_her_audio": [{"run": t["run"], "label": t["label"]} for t in turns if t["spoken_over_her_audio"]],
        "deliveries_not_completed": sum(len(r["deliveries_not_completed"]) for r in mine),
    }
    s4 = [t for t in counted if t["session"].startswith("S4") and t["class"] == "ordinary"]
    block["s4_ordinary_by_position"] = [
        {"run": t["run"], "label": t["label"], "worklet_ms": t["worklet_ms"],
         "uncached_tokens": ((t["stages"] or {}).get("engine_cache") or {}).get("fully_cached_suffix_tokens"),
         "first_chunk_ms": (t["stages"] or {}).get("dispatch_to_first_chunk_ms")}
        for t in s4
    ]
    s5 = [t for t in turns if t["session"].startswith("S5")]
    block["s5_merge_window"] = [
        {"run": t["run"], "label": t["label"], "pauses": t["internal_pauses_s"], "heard": t["heard"],
         "withdrawn_fragments": t["withdrawn_fragments"], "worklet_ms": t["worklet_ms"],
         "attribution": t["worklet_attribution"], "answer": (t["answer"] or "")[:100]}
        for t in s5
    ]
    summary[condition] = block

Path(out).write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
for condition, b in summary.items():
    print(f"== {condition} {b['runs']}")
    for klass in ("social", "ordinary"):
        print(f"  {klass:8s} {b[klass]['first_real_playback']}  uncertain={len(b[klass]['uncertain_or_no_sound'])} routes={b[klass]['routes']}")
    print(f"  unaffected: {b['unaffected']}; affected: {b['affected']}")
    for route, r in b["by_route"].items():
        print(f"  {route}: cold {r['cold_by_identity']}/{r['cache_identity']} (uncertain {r['cache_uncertain']}), "
              f"uncached {r['uncached_suffix_tokens'].get('median_ms')}, first chunk {r['dispatch_to_first_chunk_ms'].get('median_ms')}, "
              f"visible {r['dispatch_to_visible_ms'].get('median_ms')}")
    print(f"  primes {b['primes']}")
    print(f"  waits>1s {len(b['waits_over_1s'])}; readiness {b['readiness_s']}; memory {b['memory']}")
    print(f"  effort {b['effort_on_the_wire']}; models {b['models_called']}; reliability {json.dumps(b['reliability'])[:300]}")
