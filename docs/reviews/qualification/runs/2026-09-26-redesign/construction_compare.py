"""Side by side: the two request constructions on the matched contexts — release-gaps §4.

Usage: construction_compare.py construction-as_is.json construction-envelope_in_system.json
Prints every final answer in both conditions for reading, then the measured medians
(input tokens, runtime time to first token, Core's first visible text, reasoning tokens,
output length). Judging the answers is done by reading, not here.
"""

from __future__ import annotations

import json
import statistics
import sys

a = json.load(open(sys.argv[1]))
b = json.load(open(sys.argv[2]))
ra = {r["label"]: r for r in a["rows"]}
rb = {r["label"]: r for r in b["rows"]}
for label in ra:
    print(f"\n### {label}\n  history: {[h['said'] for h in ra[label]['history']]}\n  utterance: {ra[label]['utterance']!r}")
    print(f"  AS-IS   : {ra[label]['answer'][:300]!r}")
    print(f"  IN-SYS  : {rb[label]['answer'][:300]!r}")
def med(rows, key):
    vals = [r.get(key) for r in rows if r.get(key) is not None]
    return round(statistics.median(vals), 3) if vals else None
print("\n### measured (medians over the final calls)")
for key in ("tokens_in", "runtime_prompt_tokens", "ttft_s", "first_text_ms", "reasoning_output_tokens", "text_output_chars", "latency_ms"):
    print(f"  {key:26s} as_is={med(a['rows'], key)}  envelope_in_system={med(b['rows'], key)}")
print("\n### rendered last user block, as_is:\n", (a.get("rendered_last_user_block") or "")[:500])
print("\n### rendered last user block, envelope_in_system:\n", (b.get("rendered_last_user_block") or "")[:500])
tail = b.get("rendered_input_tail") or ""
print("\n### envelope_in_system: is the envelope inside the developer/system block?", "VAL-STATE-V1" in tail and tail.find("VAL-STATE-V1") < tail.rfind("<|start|>user<|message|>"))
