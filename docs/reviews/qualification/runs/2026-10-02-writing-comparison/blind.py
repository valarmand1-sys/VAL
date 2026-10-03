"""Blind pairs from the two answer files — 2 October 2026.

Usage: blind.py answers-A.json answers-B.json BLIND.md mapping.json [REVEAL.md]

For each prompt the two answers are shown as Answer A and Answer B, the order drawn
separately per prompt from the system's random source; the mapping is written to a
private file and never printed. `BLIND.md` carries the prompt and the two answers
verbatim — nothing else: no model name, no timing, no commentary. `REVEAL.md` (written
only when asked for, after the judgement) carries the mapping and the timings.
"""

from __future__ import annotations

# ruff: noqa: E501
import json
import random
import sys
from pathlib import Path


def main() -> int:
    first, second, blind_out, mapping_out = (Path(p) for p in sys.argv[1:5])
    reveal_out = Path(sys.argv[5]) if len(sys.argv) > 5 else None
    if mapping_out.exists():
        # Corrected 2 October 2026: a saved mapping is never redrawn or overwritten; the
        # reveal for pairs already shown is made by `present.py reveal` from that file.
        raise SystemExit(f"{mapping_out} exists: use present.py reveal; nothing was changed")
    runs = [json.loads(first.read_text()), json.loads(second.read_text())]
    by_id = [{row["id"]: row for row in run["rows"]} for run in runs]
    prompts = json.loads((Path(__file__).resolve().parent / "prompts.json").read_text())["prompts"]
    rng = random.SystemRandom()
    mapping: dict[str, dict[str, str]] = {}
    blind = ["# Blind writing comparison — eight pairs\n"]
    for prompt in prompts:
        pid = prompt["id"]
        order = [0, 1] if rng.random() < 0.5 else [1, 0]
        mapping[pid] = {"A": runs[order[0]]["model"], "B": runs[order[1]]["model"]}
        blind.append(f"\n## {pid} — {prompt['kind']}\n")
        blind.append("**Prompt**\n")
        blind.append("\n".join("> " + line for line in prompt["message"].splitlines()) + "\n")
        for letter, index in zip("AB", order, strict=True):
            row = by_id[index][pid]
            text = (
                row["answer"]
                if row["answer"] is not None
                else f"[no answer: {row.get('outcome')} — {row.get('error')}]"
            )
            blind.append(f"\n**Answer {letter}**\n\n{text}\n")
    blind_out.write_text("\n".join(blind))
    mapping_out.write_text(json.dumps(mapping, indent=1) + "\n")
    if reveal_out is not None:
        lines = [
            "# Reveal — models and timings (harness receipt on the loopback, not desktop display)\n"
        ]
        lines.append(
            "| prompt | A | B | first visible s (A / B) | complete s (A / B) | chars (A / B) |"
        )
        lines.append("|---|---|---|---|---|---|")
        for prompt in prompts:
            pid = prompt["id"]
            a_model, b_model = mapping[pid]["A"], mapping[pid]["B"]
            a = next(
                r for run in runs if run["model"] == a_model for r in run["rows"] if r["id"] == pid
            )
            b = next(
                r for run in runs if run["model"] == b_model for r in run["rows"] if r["id"] == pid
            )
            lines.append(
                f"| {pid} | {a_model} | {b_model} | {a['first_visible_s']} / {b['first_visible_s']} | "
                f"{a['complete_s']} / {b['complete_s']} | {a['answer_chars']} / {b['answer_chars']} |"
            )
        for run in runs:
            lines.append(
                f"\n**{run['model']}** ({run['label']}, order {run['order']}): routes seen {run['routes_seen']}; prime {json.dumps(run['prime'])}"
            )
        reveal_out.write_text("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
