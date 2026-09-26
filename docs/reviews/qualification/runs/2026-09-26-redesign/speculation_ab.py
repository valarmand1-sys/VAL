"""Speculation on against off, same sessions — §6. Usage: speculation_ab.py Q-low-summary.json S-low-spec-summary.json S-low-spec.json"""
from __future__ import annotations
import json, statistics, sys
from pathlib import Path
full = json.loads(Path(sys.argv[1]).read_text()); spec = json.loads(Path(sys.argv[2]).read_text()); raw = json.loads(Path(sys.argv[3]).read_text())
by_phrase_full = {t["phrase"]: t for t in full["turns_detail"]}
def q(v):
    v = sorted(x for x in v if x is not None)
    return None if not v else f"n={len(v)} median {statistics.median(v):.0f} p90 {v[int(0.9*(len(v)-1))]:.0f} max {v[-1]:.0f}"
for route in ("light", "substantive"):
    on = [t for t in spec["turns_detail"] if t["route"] == route]
    off = [by_phrase_full[t["phrase"]] for t in on if t["phrase"] in by_phrase_full and by_phrase_full[t["phrase"]]["route"] == route]
    print(f"{route}: speculation ON  {q([t['speech_end_to_first_playback_ms'] for t in on])}")
    print(f"{route}: speculation OFF {q([t['speech_end_to_first_playback_ms'] for t in off])} (same phrases, same route in both)")
print("routes on:", {r: sum(1 for t in spec['turns_detail'] if t['route']==r) for r in ('light','substantive','fallback','none')})
print("FP on:", spec["substantive_false_positives"]); print("FN on:", [(f['phrase'], f['transcript']) for f in spec["false_negatives"]])
print("preparations:", spec["speculation_outcomes"], "prepared_ms", spec["speculation_prepared_ms"])
for t in spec["turns_detail"]:
    if "||" in t["phrase"]:
        print("resumed:", t["phrase"], "heard", repr(t["transcript"]), t["route"], t["speech_end_to_first_playback_ms"], "->", repr((t["answer"] or "")[:80]))
# did a discarded preparation delay the corrected request? the resumed turns' onset against the full run's
for p in raw["preparations"]:
    print("  prep", p["outcome"], p["prepared_ms"], "ms", p.get("detail"))
