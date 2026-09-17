"""Renders the owner review packet from the Stage-A results and the engineer's read.

Usage: packet_stage_a.py RESULTS.json OBSERVATIONS.json OUT.md

The packet shows, per task: the task ID, capability area, the user turn
sequence, GPT-OSS's exact visible response per turn, the objective
observations (mechanical checks as recorded by the harness, and the
engineer's read — a human reading of the answer against the frozen notes,
never a model grading itself and never a cloud judge), and the latency and
token summary. Hidden reasoning never appears. An aggregate mechanical
summary closes the packet. No verdict is declared: those are the owner's.
"""

import json
import statistics
import sys
from pathlib import Path

results = json.loads(Path(sys.argv[1]).read_text())
observations = json.loads(Path(sys.argv[2]).read_text())
out: list[str] = []
w = out.append

prov = results["provenance"]
w("# GPT-OSS Partner-quality qualification — Stage A owner review packet — 16 September 2026\n")
w("Local candidate lane on the scratch store, $0 cloud spend. No verdict is declared here; the responses are for the owner's reading.\n")
w("**Configuration under evaluation:** "
  f"`{prov['model_identifier']}` ({prov['quantization']}, {prov['compatibility_type']}, {prov['architecture']}) on {prov['runtime']} "
  f"{prov['lmstudio_app_version']}; SDK {prov['lmstudio_sdk_version']} (inspection only); loaded context {prov['loaded_context_native']:,} "
  f"of {prov['max_context_length']:,}; reasoning effort **{prov['reasoning_effort']}**; output reserve {prov['output_reserve_tokens']:,}; "
  f"persona v{prov['persona_version']}; registry entry `{prov['configuration_id']}` (NOT_ADMITTED).\n")

OBS_KEYS = [
    ("constraints", "All explicit constraints followed"),
    ("invention", "Unsupported factual invention detected"),
    ("omission", "Material requested information omitted"),
    ("contradiction", "Contradicted supplied context"),
    ("correction_preserved", "User correction preserved on later turns"),
    ("refused_answerable", "Refused despite task being answerable locally"),
    ("truncated", "Completion truncated"),
    ("technical_failure", "Technical/runtime failure"),
]

first_visible: list[float] = []
totals: list[float] = []
completed = 0
constraints_yes = 0
invention_yes = 0
omission_yes = 0
correction: dict[str, int] = {}

for task in results["tasks"]:
    obs = observations.get(task["id"], {})
    w(f"\n---\n\n## {task['id']} — {task['area']}\n")
    for turn in task["turns"]:
        n = len(task["turns"])
        label = f"Turn {turn['turn']}" if n > 1 else "Prompt"
        w(f"**{label} — user:**\n")
        w("> " + turn["user_prompt"].replace("\n", "\n> ") + "\n")
        w(f"**{label} — GPT-OSS visible response:**\n")
        if turn["visible_answer"] is None:
            w(f"*No answer. {turn['refusal']}*\n")
        else:
            w(turn["visible_answer"].strip() + "\n")
    # objective observations
    w("**Objective observations**\n")
    mech_all = [c for turn in task["turns"] for c in turn["mechanical_checks"]]
    mech_pass = all(c["passed"] for c in mech_all) if mech_all else None
    tech_fail = task["failed"]
    trunc = any(bool(turn.get("truncated")) for turn in task["turns"])
    auto = {
        "constraints": obs.get("constraints", "YES" if mech_pass else ("NO" if mech_pass is False else "AMBIGUOUS")),
        "invention": obs.get("invention", "—"),
        "omission": obs.get("omission", "—"),
        "contradiction": obs.get("contradiction", "—"),
        "correction_preserved": obs.get("correction_preserved", "N/A" if len(task["turns"]) == 1 else "—"),
        "refused_answerable": obs.get("refused_answerable", "YES" if any(t["outcome"] == "refused" for t in task["turns"]) else "NO"),
        "truncated": "YES" if trunc else "NO",
        "technical_failure": "YES" if tech_fail else "NO",
    }
    w("| Observation | Result |\n|---|---|")
    for key, title in OBS_KEYS:
        w(f"| {title} | **{auto[key]}** |")
    w("")
    if mech_all:
        w("Mechanical checks (frozen with the task):\n")
        for turn in task["turns"]:
            for c in turn["mechanical_checks"]:
                mark = "pass" if c["passed"] else ("fail" if c["passed"] is False else "not run")
                rule = c["rule"]
                desc = rule["type"] + "".join(f" {k}={v}" for k, v in rule.items() if k != "type")
                w(f"- T{turn['turn']} `{desc}` — **{mark}** ({c['detail']})")
        w("")
    if obs.get("note"):
        w(f"Engineer's read: {obs['note']}\n")
    # latency / tokens
    w("**Latency / tokens**\n")
    w("| Turn | Prompt tokens (preflight = server) | Output (visible + reasoning) | First visible | Total | Terminal | Cost |\n|---|---|---|---|---|---|---|")
    for turn in task["turns"]:
        pf = turn["exact_preflight"] or {}
        if turn["calls"]:
            c = turn["calls"][0]
            parity = c["parity"] or {}
            par = "exact" if parity.get("exact") else f"diff {parity.get('difference')}"
            w(f"| {turn['turn']} | {pf.get('prompt_tokens')} / {c['prompt_tokens']} ({par}) | {c['output_tokens']} ({c['visible_tokens']} + {c['reasoning_tokens']}) "
              f"| {turn['timing_s']['first_visible_content']} s | {turn['timing_s']['core_call_total']} s | {c['terminal_state']} | ${c['cost']} {c['cost_certainty']} |")
            if turn["timing_s"]["first_visible_content"] is not None:
                first_visible.append(turn["timing_s"]["first_visible_content"])
            totals.append(turn["timing_s"]["core_call_total"])
        else:
            w(f"| {turn['turn']} | {pf.get('prompt_tokens')} / — | — | — | {turn['timing_s']['core_call_total']} s | {turn['outcome']} | — |")
    w("")
    if not tech_fail:
        completed += 1
    if auto["constraints"] == "YES":
        constraints_yes += 1
    if auto["invention"] == "YES":
        invention_yes += 1
    if auto["omission"] == "YES":
        omission_yes += 1
    correction[auto["correction_preserved"]] = correction.get(auto["correction_preserved"], 0) + 1

n = len(results["tasks"])
w("\n---\n\n## Aggregate mechanical summary\n")
w(f"- {completed}/{n} completed without technical failure")
w(f"- {constraints_yes}/{n} followed all objectively testable explicit constraints")
w(f"- {invention_yes}/{n} with detected unsupported invention (engineer's read)")
w(f"- {omission_yes}/{n} with material omissions (engineer's read)")
w(f"- correction preservation: " + ", ".join(f"{k} × {v}" for k, v in sorted(correction.items())))
w(f"- median first-visible latency: {statistics.median(first_visible):.2f} s over {len(first_visible)} answered turns" if first_visible else "- no first-visible latencies")
w(f"- median total latency: {statistics.median(totals):.2f} s over {len(totals)} turns" if totals else "- no totals")
t = results.get("totals", {})
w(f"- total local provider/API spend: ${t.get('cost_sum')} across {t.get('model_calls')} calls (providers: {t.get('providers')}); cloud spend $0")
w("\nNo PASS / FAIL / comparison / admission verdict is declared. Those are the owner's decisions.\n")
Path(sys.argv[3]).write_text("\n".join(out))
print("packet written:", sys.argv[3])
