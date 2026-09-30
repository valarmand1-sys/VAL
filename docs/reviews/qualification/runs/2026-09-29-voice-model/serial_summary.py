"""Summarise one typed-during-Voice run (VOICE_MODEL.md §10.8–§10.9): transitions, the typed
answer, the spoken turns around it, and memory before, during and after.

Usage: python serial_summary.py RUN_LABEL
"""

from __future__ import annotations

import json
import re
import statistics as st
import sys
from pathlib import Path

label = sys.argv[1]
here = Path(__file__).resolve().parent
typed = json.loads((here / f"typed-during-voice-{label}.json").read_text())
t0, t1 = typed["sent_at"], typed["answered_at"]
response = typed["response"]
print(f"typed request: {response.get('kind')} in {t1 - t0:.1f} s — "
      f"{(response.get('val_message') or {}).get('content') or response.get('error', '')[:120]!r}")

print("\nservice log around it:")
for line in (here / f"service-{label}.log").read_text(errors="replace").splitlines():
    m = re.match(r"(\d+\.\d+) (.*)", line)
    if not m:
        continue
    ts = float(m.group(1))
    text = m.group(2)
    if t0 - 1 <= ts <= t1 + 90 and any(
        k in text for k in ("model transition", "local runtime ready: state=started",
                            "local runtime ready: server_found", "returning", "voice endpoint",
                            "voice turn timeline")
    ):
        print(f"  {ts - t0:+7.2f} {text[:150]}")

bench = json.loads((here / f"voice-bench-{label}.json").read_text())
session = json.loads((here / f"voice-bench-{label}-session-3.json").read_text())
print("\nS4 turns (speech end relative to the typed request; onset = speech end → first audio):")
s4 = [t for t in bench["turns"] if t["session"].startswith("S4")]
for i, (x, raw) in enumerate(zip(s4, session["turns"])):
    rel = raw["speech_end_wall"] / 1000 - t0
    onset = x["worklet_ms"] / 1000 if x.get("worklet_ms") else None
    first = (x.get("stages") or {}).get("dispatch_to_first_chunk_ms")
    print(f"  {i:2d} {x['label'][:30]:30s} end {rel:+7.1f} s  onset {onset}  first chunk {first} ms")
for name in ("S1", "S4"):
    v = [x["worklet_ms"] / 1000 for x in bench["turns"]
         if x["session"].startswith(name) and x.get("worklet_ms") and not x.get("spoken_over_her_audio")]
    print(f"{name}: n {len(v)} median {st.median(v):.2f} p90 {sorted(v)[int(0.9 * (len(v) - 1))]:.2f} max {max(v):.2f}")
print("underruns", sum(x.get("worklet_underruns") or 0 for x in bench["turns"]),
      "no audio", sum(1 for x in bench["turns"] if not x.get("worklet_ms")),
      "call statuses", sorted({str(x.get("call_statuses")) for x in bench["turns"]}),
      "readiness", [(r["session"][:2], round(r["voice_on_to_ready_displayed_s"], 1)) for r in bench["readiness"]])

rows = [l.split("\t") for l in (here / f"memory-{label}.tsv").read_text().splitlines()[1:]]


def stats(selection: list[list[str]], name: str) -> None:
    free = [int(r[1]) for r in selection if r[1]]
    swap = [float(r[2]) / 1024 for r in selection]
    both = sum(1 for r in selection if r[3].strip() and "val-exp-hub" in r[4])
    print(f"{name}: samples {len(selection)}, free min/median {min(free)}/{sorted(free)[len(free) // 2]}%, "
          f"swap min/max {min(swap):.2f}/{max(swap):.2f} GB, samples with both models {both}")


stats(rows, "whole run")
stats([r for r in rows if float(r[0]) < t0 - 2], "before the typed request")
stats([r for r in rows if t0 - 2 <= float(r[0]) <= t1 + 45], "typed request → return")
stats([r for r in rows if float(r[0]) > t1 + 45], "after")
print("\nmemory by 5 s sample around the typed request:")
for r in rows:
    rel = float(r[0]) - t0
    if -10 <= rel <= 75:
        print(f"  {rel:+6.0f} s free {r[1]:>3}% swap {float(r[2]) / 1024:5.2f} GB llama {r[3]:>8} lms [{r[4].strip()}]")
