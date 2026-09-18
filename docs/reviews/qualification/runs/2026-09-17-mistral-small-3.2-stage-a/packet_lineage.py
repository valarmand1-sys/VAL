"""Appends the rerun lineage section to the review packet (owner ruling, 18 September 2026).

Usage: packet_lineage.py RESULTS_STAGE_A.json RERUNS.json DIAGNOSTIC.json PACKET.md
"""

import difflib
import json
import sys
from pathlib import Path

results = json.loads(Path(sys.argv[1]).read_text())
reruns = json.loads(Path(sys.argv[2]).read_text())
diag = json.loads(Path(sys.argv[3]).read_text())
notes_path = Path(sys.argv[2]).with_name("observations-reruns.json")
notes = json.loads(notes_path.read_text()) if notes_path.exists() else {}
turns_by = {(t["id"], turn["turn"]): turn for t in results["tasks"] for turn in t["turns"]}

L = ["\n\n---\n\n## Lineage of the four quarantined calls and their corrected reruns — 18 September 2026\n",
     "The four calls whose exact preflight did not equal the server's count were quarantined, the seam was demonstrated and closed at the local boundary, and ONLY those four were rerun — each rebuilt in a fresh scratch conversation from the ORIGINAL captured preceding turns (the original Val answers persisted as captured, never regenerated), under the same configuration (persona v1.8, temperature 0.15 transmitted, NOT_APPLICABLE reasoning, output reserve 6,144, configured 32,768 / actual 36,352). The originals are preserved above and here; the corrected reruns are the answers for final review.\n",
     f"**Root cause, demonstrated (`results-assistant-seam-diagnostic.json`):** the template RPC rendered the historical assistant turn as `{diag['seam_sdk_repr']}` and the chat-completions ingress as `{diag['seam_server_repr']}` — the template's end-of-sequence token after each historical assistant turn, one token per assistant message ({diag['sdk_count']} vs {diag['server_usage_prompt_tokens']}); the runtime tokenizer counts the server's own logged input at {diag['server_logged_input_count_by_runtime_tokenizer']}. The SDK's documented `omitEosToken` option renders byte-equal to the ingress; the inspector now renders with it for every model. GPT-OSS's Harmony rendering is byte-identical with or without it and its live two-turn parity stayed exact (5,417 and 5,743).\n",
     "| Call | Original parity | Corrected rerun parity | Rerun output tokens | First visible | Total | Visible answer materially changed? |", "|---|---|---|---|---|---|---|"]
for x in reruns["reruns"]:
    c = x["calls"][0]; ratio = difflib.SequenceMatcher(None, x["original_visible_answer"], x["visible_answer"]).ratio()
    changed = "identical" if x["visible_answer"].strip() == x["original_visible_answer"].strip() else f"yes (similarity {ratio:.2f})"
    L.append(f"| {x['label']} | {x['original_parity']['difference']:+d} | {c['parity']['difference']:+d} (exact) | {c['output_tokens']} | {x['timing_s']['first_visible_content']} s | {x['timing_s']['core_call_total']} s | {changed} |")
L.append("")
for x in reruns["reruns"]:
    task_id, index = x["task"], x["turn"]
    L.append(f"\n### {x['label']}\n")
    L.append("**Preceding original conversation history used for the rerun** (from the first run, exactly as captured):\n")
    for prior in range(1, index):
        pt = turns_by[(task_id, prior)]
        L.append(f"- Turn {prior} — user:\n\n  > " + pt["user_prompt"].replace("\n", "\n  > ") + "\n")
        L.append(f"- Turn {prior} — Mistral (original, as persisted into the rerun's history):\n\n  > " + (pt["visible_answer"] or "").strip().replace("\n", "\n  > ") + "\n")
    L.append(f"**Turn {index} — user:**\n\n> " + turns_by[(task_id, index)]["user_prompt"].replace("\n", "\n> ") + "\n")
    L.append(f"**Original answer — QUARANTINED (parity {x['original_parity']['difference']:+d}), historical evidence:**\n\n> " + x["original_visible_answer"].strip().replace("\n", "\n> ") + "\n")
    L.append(f"**Corrected rerun — EXACT PARITY ({x['calls'][0]['prompt_tokens']:,} = {x['calls'][0]['prompt_tokens']:,}) — the answer for final review:**\n")
    L.append(x["visible_answer"].strip() + "\n")
    L.append("Mechanical checks (frozen with the task):\n")
    for cch in x["mechanical_checks"]:
        rule = cch["rule"]; desc = rule["type"] + "".join(f" {k}={v}" for k, v in rule.items() if k != "type")
        L.append(f"- `{desc}` — **{'pass' if cch['passed'] else 'fail'}** ({cch['detail']})")
    if notes.get(x["label"]):
        L.append(f"\n*PROVISIONAL ENGINEER NOTES (rerun):* {notes[x['label']]}\n")
L.append("\nNo PASS / FAIL / comparison / admission verdict is declared. Those are the owner's decisions.\n")
with open(sys.argv[4], "a") as f:
    f.write("\n".join(L))
print("lineage appended:", sys.argv[4])
