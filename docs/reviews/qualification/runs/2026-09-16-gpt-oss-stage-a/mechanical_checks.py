"""The frozen mechanical checks of the Stage A benchmark — one implementation.

Moved out of the harness on 18 September 2026 so the affected-call reruns use
exactly the code the first runs used; the rules themselves live in
`benchmark.json`, frozen at 60b65b7, and are not changed here.
"""

from __future__ import annotations

import re

NUMBERED = re.compile(r"^\s*\d+[.)]\s+\S", re.M)
BULLET = re.compile(r"^\s*(?:[-*•]\s+|\d+[.)]\s+)\S", re.M)
STAGE = re.compile(r"\*[^*\n]{2,}\*")
WORD = re.compile(r"\S+")


def check(answer: str, rule: dict) -> tuple[bool, str]:  # type: ignore[type-arg]  # noqa: C901
    kind = rule["type"]
    low = answer.lower()
    if kind == "max_words":
        n = len(WORD.findall(answer))
        return n <= rule["max"], f"{n} words (max {rule['max']})"
    if kind == "min_words":
        n = len(WORD.findall(answer))
        return n >= rule["min"], f"{n} words (min {rule['min']})"
    if kind == "contains_all":
        missing = [v for v in rule["values"] if v.lower() not in low]
        return not missing, "all present" if not missing else f"missing {missing}"
    if kind == "contains_any":
        return any(v.lower() in low for v in rule["values"]), f"any of {rule['values']}"
    if kind == "excludes_all":
        present = [v for v in rule["values"] if v.lower() in low]
        return not present, "none present" if not present else f"present {present}"
    if kind == "excludes_regex":
        m = re.search(rule["pattern"], answer)
        return m is None, "no match" if m is None else f"matched {m.group(0)!r}"
    if kind == "pattern_count_max":
        n = len(re.findall(rule["pattern"], answer))
        return n <= rule["max"], f"{n} matches (max {rule['max']})"
    if kind == "numbered_items":
        n = len(NUMBERED.findall(answer))
        return n == rule["exactly"], f"{n} numbered items (exactly {rule['exactly']})"
    if kind == "first_numbered_item_contains":
        lines = [ln for ln in answer.splitlines() if NUMBERED.match(ln)]
        first = lines[0].lower() if lines else ""
        return any(v.lower() in first for v in rule["values"]), f"first item: {first[:80]!r}"
    if kind == "text_after_list":
        lines = answer.rstrip().splitlines()
        idx = max((i for i, ln in enumerate(lines) if NUMBERED.match(ln)), default=-1)
        tail = "\n".join(lines[idx + 1 :]).strip()
        return bool(tail), "text follows the list" if tail else "nothing after the list"
    if kind == "no_list":
        n = len(BULLET.findall(answer))
        return n == 0, "no list lines" if n == 0 else f"{n} list lines"
    if kind == "no_heading":
        bad = [ln for ln in answer.splitlines() if ln.startswith("#") or re.match(r"^\*\*[^*]+\*\*\s*$", ln)]
        return not bad, "no heading" if not bad else f"heading-like line {bad[0][:60]!r}"
    if kind == "no_stage_directions":
        m = STAGE.search(answer)
        return m is None, "none" if m is None else f"found {m.group(0)[:60]!r}"
    if kind == "address_count_max":
        n = low.count("my lord")
        return n <= rule["max"], f"'my lord' × {n} (max {rule['max']})"
    if kind == "max_nonempty_lines":
        n = len([ln for ln in answer.splitlines() if ln.strip()])
        return n <= rule["max"], f"{n} non-empty lines (max {rule['max']})"
    if kind == "max_paragraphs":
        n = len([p for p in re.split(r"\n\s*\n", answer.strip()) if p.strip()])
        return n <= rule["max"], f"{n} paragraphs (max {rule['max']})"
    raise ValueError(kind)


