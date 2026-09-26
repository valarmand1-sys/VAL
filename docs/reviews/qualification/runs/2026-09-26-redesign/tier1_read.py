"""Read the four-way comparison's answers side by side — §3's inspection, made legible.

Mechanical flags only, so the reading is not delegated to a model: a persona example
line reproduced verbatim; the previous answer repeated; a claim of completed work or
an invented scene (a fixed word list, reported as a flag to read, not a verdict);
length; a cap hit or empty answer; the route the record says was taken. The verdicts
are written by hand in TIER1_COMPARISON.md after reading every answer here.
Usage: tier1_read.py tier1-compare-A.json tier1-compare-B.json ...
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

ECHO = [
    "I have no book on",
    "I do not have that in the record I can see",
    "I remain unconvinced",
    "Put it in front of me",
    "What shall we turn our attention to",
]
INVENTION = re.compile(
    r"\b(fire|hearth|window|snow|weather|rain|schedule|invitation|venue|completed|finished|"
    r"draft is ready|volume on|page \d+|yesterday|last night|this morning's)\b",
    re.IGNORECASE,
)

conditions = {}
for arg in sys.argv[1:]:
    doc = json.loads(Path(arg).read_text())
    conditions[doc["condition"]] = doc

ids = [r["id"] for r in next(iter(conditions.values()))["results"]]
summary: dict[str, dict] = {}
for name, doc in conditions.items():
    rows = doc["results"]
    lengths = [len(r["answer"] or "") for r in rows if r["answer"]]
    light = [r for r in rows if any(c.get("task_type") == "light_conversation" for c in r["calls"])]
    summary[name] = {
        "answers": len(rows),
        "light_route": len(light),
        "persona_echo": sum(1 for r in rows if any(e in (r["answer"] or "") for e in ECHO)),
        "repeats_previous": sum(
            1
            for r in rows
            if r["history"] and r["answer"] and r["history"][-1]["answer"]
            and (r["answer"].strip()[:50] == r["history"][-1]["answer"].strip()[:50])
        ),
        "invention_flag": sum(1 for r in rows if INVENTION.search(r["answer"] or "")),
        "over_200_chars": sum(1 for r in rows if len(r["answer"] or "") > 200),
        "not_complete": sum(
            1 for r in rows if r["kind"] != "Turn" or not (r["answer"] or "").strip()
        ),
        "answer_chars_median": statistics.median(lengths) if lengths else None,
        "core_seconds_median": round(statistics.median(r["core_seconds"] for r in rows), 2),
        "tokens_out_median": statistics.median(
            [c["tokens_out"] for r in rows for c in r["calls"] if c.get("tokens_out") is not None]
            or [0]
        ),
        "latency_ms_median": statistics.median(
            [c["latency_ms"] for r in rows for c in r["calls"] if c.get("latency_ms") is not None]
            or [0]
        ),
    }
print(json.dumps(summary, indent=1))
print()
for case_id in ids:
    print(f"=== {case_id}")
    for name, doc in conditions.items():
        row = next(r for r in doc["results"] if r["id"] == case_id)
        if name == next(iter(conditions)):
            if row["history"]:
                print(f"    history: {row['history'][-1]['said']!r} -> {(row['history'][-1]['answer'] or '')[:120]!r}")
            print(f"    said: {row['utterance']!r}")
        flags = []
        if any(e in (row["answer"] or "") for e in ECHO):
            flags.append("ECHO")
        if INVENTION.search(row["answer"] or ""):
            flags.append("invention?")
        if row["kind"] != "Turn":
            flags.append(row["kind"])
        calls = ",".join(f"{c.get('task_type','?')[:5]}:{c.get('tokens_out')}t/{c.get('latency_ms')}ms" for c in row["calls"])
        print(f"  {name} [{calls}] {' '.join(flags)}\n      {(row['answer'] or '').strip()!r}")
Path(sys.argv[1]).with_name("tier1-compare-summary.json").write_text(json.dumps(summary, indent=1) + "\n")
