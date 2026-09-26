"""Condition E against condition A on the same phrases — 26 September 2026 (§10, §11).

Pairs each phrase's turn in the two summaries and reports, per group, the speech end →
first playback figures side by side; on the ineligible group both conditions take the
substantive route, so that pairing is the measure of what the resident light model and
the candidate machinery cost the substantive route (§10: "test substantive-route
regressions from residency"). Usage: compare_conditions.py A-summary.json E-summary.json
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path


def q(values: list[float]) -> str:
    values = sorted(v for v in values if v is not None)
    if not values:
        return "n=0"
    p90 = values[min(len(values) - 1, int(round(0.9 * (len(values) - 1))))]
    return f"n={len(values)} median {statistics.median(values) / 1000:.2f} s  p90 {p90 / 1000:.2f} s  max {values[-1] / 1000:.2f} s"


a = json.loads(Path(sys.argv[1]).read_text())
e = json.loads(Path(sys.argv[2]).read_text())
by_phrase_a = {t["phrase"]: t for t in a["turns_detail"] if not t.get("session_failed")}
by_phrase_e = {t["phrase"]: t for t in e["turns_detail"] if not t.get("session_failed")}
common = sorted(set(by_phrase_a) & set(by_phrase_e))
print(f"paired phrases: {len(common)}")
out: dict[str, object] = {"paired": len(common), "groups": {}}
for group in ("tier_1", "tier_2", "ineligible"):
    mine = [p for p in common if by_phrase_e[p]["group"] == group]
    la = [by_phrase_a[p]["speech_end_to_first_playback_ms"] for p in mine]
    le = [by_phrase_e[p]["speech_end_to_first_playback_ms"] for p in mine]
    diffs = [
        by_phrase_e[p]["speech_end_to_first_playback_ms"] - by_phrase_a[p]["speech_end_to_first_playback_ms"]
        for p in mine
        if by_phrase_a[p]["speech_end_to_first_playback_ms"] is not None
        and by_phrase_e[p]["speech_end_to_first_playback_ms"] is not None
    ]
    light_e = [by_phrase_e[p]["speech_end_to_first_playback_ms"] for p in mine if by_phrase_e[p]["route"] == "light"]
    la_light = [by_phrase_a[p]["speech_end_to_first_playback_ms"] for p in mine if by_phrase_e[p]["route"] == "light"]
    routes_a = {r: sum(1 for p in mine if by_phrase_a[p]["route"] == r) for r in ("light", "substantive", "fallback", "none")}
    print(f"\n{group} ({len(mine)} paired)")
    print(f"  A routes {routes_a}")
    print(f"  A (production routing)     {q(la)}")
    print(f"  E (candidate)              {q(le)}")
    if light_e:
        print(f"  E light-route turns only   {q(light_e)}")
        print(f"  A on those same phrases    {q(la_light)}")
    if diffs:
        print(f"  E - A per phrase           median {statistics.median(diffs) / 1000:+.2f} s  (min {min(diffs) / 1000:+.2f}, max {max(diffs) / 1000:+.2f})")
    out["groups"][group] = {
        "paired": len(mine), "a_routes": routes_a,
        "a_ms": la, "e_ms": le, "e_light_ms": light_e, "a_on_e_light_phrases_ms": la_light,
        "e_minus_a_ms": diffs,
    }
# Answer length, as a proxy for what the two routes make her say to a greeting.
for group in ("tier_1", "tier_2"):
    mine = [p for p in common if by_phrase_e[p]["group"] == group]
    print(f"\n{group} answer length (chars): A median {statistics.median(len(by_phrase_a[p]['answer'] or '') for p in mine):.0f}"
          f"   E median {statistics.median(len(by_phrase_e[p]['answer'] or '') for p in mine):.0f}")
print("\nmachine A:", json.dumps(a["machine"]))
print("machine E:", json.dumps(e["machine"]))
Path(sys.argv[2]).with_name("comparison-A-vs-E.json").write_text(json.dumps(out, indent=1) + "\n")
