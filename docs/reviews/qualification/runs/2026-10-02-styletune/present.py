"""Present two answer files as unlabelled pairs, and reveal them from the SAVED mapping.

Usage:
  present.py blind  FIRST.json SECOND.json OUTDIR   -> OUTDIR/BLIND.md, OUTDIR/mapping.json
  present.py reveal FIRST.json SECOND.json OUTDIR   -> OUTDIR/REVEAL.md (reads mapping.json)

Corrected 2 October 2026 (owner order §4). The earlier presenter drew the order and wrote
the reveal in one invocation, and a second invocation would have drawn again and
overwritten the mapping. Here the two are separate commands:

- `blind` draws the order once per prompt from the system's random source, writes the
  pairs and the mapping, and **refuses to run if a mapping already exists**;
- `reveal` never draws and never writes the mapping: it reads the saved one, checks that
  each answer shown in BLIND.md is the saved model's answer, and only then writes the
  reveal with the timings.

`BLIND.md` carries the prompt and the two answers verbatim: no model name, no timing, no
commentary. Timings are harness receipt on the loopback, not desktop display.
"""

from __future__ import annotations

# ruff: noqa: E501
import json
import random
import sys
from pathlib import Path

PROMPTS = Path(__file__).resolve().parent.parent / "2026-10-02-writing-comparison" / "prompts.json"


def load(first: Path, second: Path) -> tuple[list[dict], dict[str, dict[str, dict]]]:
    runs = [json.loads(first.read_text()), json.loads(second.read_text())]
    if runs[0]["model"] == runs[1]["model"]:
        raise SystemExit("the two files are the same model")
    return runs, {run["model"]: {row["id"]: row for row in run["rows"]} for run in runs}


def shown(row: dict) -> str:
    if row["answer"] is not None:
        return row["answer"]
    return f"[no answer: {row.get('outcome')} — {row.get('error')}]"


def blind(first: Path, second: Path, out: Path) -> int:
    mapping_file = out / "mapping.json"
    if mapping_file.exists():
        raise SystemExit(f"{mapping_file} exists: the pairs were already drawn; nothing changed")
    runs, by_model = load(first, second)
    prompts = json.loads(PROMPTS.read_text())["prompts"]
    rng = random.SystemRandom()
    mapping: dict[str, dict[str, str]] = {}
    lines = ["# Writing comparison — eight pairs\n"]
    for prompt in prompts:
        models = [runs[0]["model"], runs[1]["model"]]
        if rng.random() < 0.5:
            models.reverse()
        mapping[prompt["id"]] = {"A": models[0], "B": models[1]}
        lines.append(f"\n## {prompt['id']} — {prompt['kind']}\n")
        lines.append("**Prompt**\n")
        lines.append("\n".join("> " + line for line in prompt["message"].splitlines()) + "\n")
        for letter, model in zip("AB", models, strict=True):
            lines.append(f"\n**Answer {letter}**\n\n{shown(by_model[model][prompt['id']])}\n")
    out.mkdir(parents=True, exist_ok=True)
    (out / "BLIND.md").write_text("\n".join(lines))
    mapping_file.write_text(json.dumps(mapping, indent=1) + "\n")
    return 0


def reveal(first: Path, second: Path, out: Path) -> int:
    mapping_file = out / "mapping.json"
    if not mapping_file.exists():
        raise SystemExit(f"{mapping_file} does not exist: nothing was presented from here")
    mapping = json.loads(mapping_file.read_text())
    runs, by_model = load(first, second)
    prompts = json.loads(PROMPTS.read_text())["prompts"]
    presented = (out / "BLIND.md").read_text()
    for prompt in prompts:  # the saved mapping must describe what was actually shown
        section = presented.split(f"\n## {prompt['id']} — ", 1)[1].split("\n## ", 1)[0]
        for letter in "AB":
            answer = shown(by_model[mapping[prompt["id"]][letter]][prompt["id"]])
            after = section.split(f"**Answer {letter}**\n\n", 1)[1]
            if not after.startswith(answer):
                raise SystemExit(
                    f"{prompt['id']} Answer {letter}: the saved mapping does not match the text shown"
                )
    lines = [
        "# Reveal — models and timings (harness receipt on the loopback, not desktop display)\n"
    ]
    lines.append(
        "| prompt | A | B | first visible s (A / B) | complete s (A / B) | chars (A / B) |"
    )
    lines.append("|---|---|---|---|---|---|")
    for prompt in prompts:
        pid = prompt["id"]
        a, b = (by_model[mapping[pid][letter]][pid] for letter in "AB")
        lines.append(
            f"| {pid} | {mapping[pid]['A']} | {mapping[pid]['B']} | {a['first_visible_s']} / {b['first_visible_s']} | "
            f"{a['complete_s']} / {b['complete_s']} | {a['answer_chars']} / {b['answer_chars']} |"
        )
    for run in runs:
        lines.append(
            f"\n**{run['model']}** ({run['label']}, order {run['order']}): routes seen {run['routes_seen']}; prime {json.dumps(run['prime'])}"
        )
    (out / "REVEAL.md").write_text("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    command, first, second, out = (
        sys.argv[1],
        Path(sys.argv[2]),
        Path(sys.argv[3]),
        Path(sys.argv[4]),
    )
    raise SystemExit({"blind": blind, "reveal": reveal}[command](first, second, out))
