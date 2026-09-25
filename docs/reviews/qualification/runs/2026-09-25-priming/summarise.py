"""Per-trial rows and medians for the qualification matrix (priming-cache pass §20, §21)."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETS = {
    "A current production (batched, parallel 4)": [
        "matrix-A.json", "matrix-A-cold.json", "matrix-A-r2.json", "matrix-A-r3.json"],
    "B sequential, unprimed": ["matrix-B.json"],
    "C sequential + prime (final code)": [
        "matrix-C-final2.json", "matrix-C-final2-cold.json",
        "matrix-C-final2-r2.json", "matrix-C-final2-r3.json"],
}
FIELDS = [
    ("dispatch_to_first_provider_output_ms", "dispatch→first output"),
    ("ready_to_first_output_ms", "request-ready→first output"),
    ("request_ready_to_first_user_facing_text_ms", "request-ready→first text"),
    ("speech_end_to_owner_message_read_ms", "speech end→his message"),
    ("owner_message_to_playback_ms", "his message→playback"),
    ("speech_end_to_playback_ms", "speech end→playback"),
]
summary: dict = {}
for name, files in SETS.items():
    governing = []
    for file in files:
        rows = json.loads((HERE / file).read_text())["rows"]
        for row in rows[1:]:  # turns 2-4: model resident, changed suffix, after turn 1
            row = dict(row)
            row["ready_to_first_output_ms"] = round(
                row["request_ready_to_first_user_facing_text_ms"]
                - row["first_output_to_user_facing_text_ms"], 1)
            governing.append(row)
    summary[name] = {
        "trials": [{label: row[key] for key, label in FIELDS} | {"turn": row["turn"]}
                   for row in governing],
        "medians": {label: round(statistics.median(row[key] for row in governing), 1)
                    for key, label in FIELDS},
    }
(HERE / "matrix-summary.json").write_text(json.dumps(summary, indent=1) + "\n")
for name, block in summary.items():
    print(name, "n =", len(block["trials"]))
    for trial in block["trials"]:
        print("   ", {k: v for k, v in trial.items()})
    print("  MEDIANS", block["medians"])
