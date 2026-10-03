"""One table from the typed-cache bench runs. Usage: summarise.py bench-*.json"""

from __future__ import annotations

import json
import sys
from datetime import datetime


def prefill_seconds(row: dict) -> float | None:
    a, b = row.get("prefill_first_stamp"), row.get("prefill_last_stamp")
    if not a or not b:
        return None
    fmt = "%Y-%m-%d %H:%M:%S"
    return (datetime.strptime(b, fmt) - datetime.strptime(a, fmt)).total_seconds()


for path in sys.argv[1:]:
    data = json.load(open(path))
    print(f"\n== {data['label']}  transition: {data.get('transition')}")
    header = (
        f"{'phase':12} {'turn':58} {'first visible s':>15} {'cache used':>10} "
        f"{'prompt':>7} {'prefill s':>9}"
    )
    print(header)
    for row in data["rows"]:
        p = prefill_seconds(row)
        print(
            f"{row['phase']:12} {row['text'][:56]:58} {row['send_to_first_visible_s'] or 0:15.2f} "
            f"{row['cache_used'] if row['cache_used'] is not None else '-':>10} "
            f"{row['prompt_tokens'] or '-':>7} {p if p is not None else '-':>9}"
        )
