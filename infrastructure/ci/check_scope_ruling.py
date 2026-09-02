"""CLAUDE.md's "Current work" restates the newest scope ruling, or CI is red.

Approved by Lord Armand, 1 September 2026, after an external reviewer found
`CLAUDE.md` still saying "Layer 0 only" while the 31 August ruling in the
baselines permitted Layer 1 presence in parallel — two governing documents in
contradiction, found the most expensive way anything is found. A convention
("update both in the same commit") is not a control; this is the control.

## The marker convention

Every scope-affecting ruling recorded in `docs/baselines/` carries a
machine-readable marker line, invisible in rendered Markdown:

    <!-- scope-ruling: 2026-08-31 -->

`CLAUDE.md` carries the marker of the ruling its "Current work" section
restates. This check fails when the newest marker anywhere in the baselines is
newer than the one `CLAUDE.md` carries — the exact moment a recorded ruling
has not been brought into step — and when either side carries no marker at
all, so the mechanism cannot be silently retired by deleting its inputs.

The comparison is exact dates, no prose parsing: a ruling is in step or it is
not, and the failure message says which document moved.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The marker every scope-affecting ruling carries. ISO dates compare
#: correctly as strings, which is the whole trick.
MARKER = re.compile(r"<!--\s*scope-ruling:\s*(\d{4}-\d{2}-\d{2})\s*-->")


def markers_in(text: str) -> list[str]:
    """Every scope-ruling date in one document, as written."""
    return MARKER.findall(text)


def check(baselines_dir: Path, claude_md: Path) -> list[str]:
    """Everything out of step, as printable problems. Empty means in step."""
    problems: list[str] = []

    newest_date = ""
    newest_where = ""
    for path in sorted(baselines_dir.glob("*.md")):
        for date in markers_in(path.read_text(encoding="utf-8")):
            if date > newest_date:
                newest_date, newest_where = date, path.name
    if not newest_date:
        problems.append(
            f"no scope-ruling marker found anywhere in {baselines_dir}: the "
            "tripwire has no baseline input. Every scope-affecting ruling "
            "carries `<!-- scope-ruling: YYYY-MM-DD -->` (ruling, 1 September 2026)."
        )

    stated = markers_in(claude_md.read_text(encoding="utf-8"))
    if not stated:
        problems.append(
            f"{claude_md.name} carries no scope-ruling marker: its Current work "
            "section must name the ruling it restates."
        )

    if problems:
        return problems

    newest_stated = max(stated)
    if newest_stated < newest_date:
        problems.append(
            f"{claude_md.name} restates the scope ruling of {newest_stated}, but "
            f"{newest_where} records a newer one dated {newest_date}. Bring "
            "CLAUDE.md's Current work section into step with the ruling — the "
            "baselines govern, and a stale restatement is a governing document "
            "contradicting another."
        )
    elif newest_stated > newest_date:
        problems.append(
            f"{claude_md.name} claims a scope ruling dated {newest_stated} that no "
            "baseline records (newest recorded: "
            f"{newest_date} in {newest_where}). The restatement cannot be "
            "ahead of the record."
        )
    return problems


def main() -> int:
    problems = check(REPO_ROOT / "docs" / "baselines", REPO_ROOT / "CLAUDE.md")
    if problems:
        print("CLAUDE.md is out of step with the recorded scope ruling:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print("CLAUDE.md restates the newest recorded scope ruling.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
