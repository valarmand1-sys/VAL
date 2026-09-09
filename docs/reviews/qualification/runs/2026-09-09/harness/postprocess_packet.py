"""Repair the packet runs' evidence without re-running anything.

The first capture keyed model-call rows on the user message, so it recorded only the
response call. The low run's scratch store survived and was recomputed from the rows
(keyed by isolation project). The high and medium stores were reset by the later runs,
so their Opus calls are reconstructed from the per-call settlement lines the harness
captured from the gateway log ('prompt cache: … on opus-5 … cost $x'), and the two
configuration-independent calls per prompt (Haiku classification, Sonnet strip) are
carried as ESTIMATES from the low run's rows for the same prompt, labelled as such.
The I4 check is re-applied with the corrected 'nothing else' rule to all three runs.
"""
import json, re, sys
from pathlib import Path
S = Path(sys.argv[1]); low = json.load(open(S / "run_low.json")); low_costs = json.load(open(S / "low_task_costs.json"))
LINE = re.compile(r"prompt cache: (\w+) on opus-5 \(ttl (\w+)\): uncached=(\d+) write_5m=(\d+) write_1h=(\d+) read=(\d+); cost \$([0-9.]+)")

def check_I4(a):
    lines = [l for l in (a or "").splitlines() if l.strip()]
    heads = [i for i, l in enumerate(lines) if re.match(r"^\s*(#+\s*|\*\*)?(Cast|Weather)(\*\*)?\s*:?\s*$", l)]
    first_is_head = bool(lines) and bool(heads) and heads[0] == 0
    nothing_else = first_is_head and not any(re.match(r"^\s*(-{3,}|\*{3,})\s*$", l) for l in lines) and not any(re.match(r"^\s*My lord", l) for l in lines[1:])
    return (len(heads) == 2 and first_is_head and nothing_else), f"{len(heads)} headings; first line heading={first_is_head}; nothing else={nothing_else}"

for effort in ("high", "medium"):
    d = json.load(open(S / "first_attempt" / f"run_{effort}.json"))
    exact = est = 0.0
    for pid, rec in d["prompts"].items():
        opus = []
        for l in rec.get("logs", []):
            m = LINE.search(l)
            if m: opus.append({"task": None, "model_identifier": "claude-opus-5", "cache": m.group(1), "uncached": int(m.group(3)), "w1h": int(m.group(5)), "read": int(m.group(6)), "cost": float(m.group(7)), "source": "gateway log settlement line"})
        # the blind call precedes the response call; a C prompt has two Opus lines, everything else one
        if len(opus) == 2: opus[0]["task"] = "blind_position"; opus[1]["task"] = "conversation"
        elif len(opus) == 1: opus[0]["task"] = "conversation"
        conv = rec["model_calls"][0] if rec.get("model_calls") else None
        if conv and opus:
            assert abs(opus[-1]["cost"] - conv["cost"]) < 1e-6, (effort, pid, opus[-1]["cost"], conv["cost"])
            opus[-1].update({k: conv[k] for k in ("config_id", "tokens_in", "tokens_out", "latency_ms", "terminal", "created_at") if k in conv}); opus[-1]["source"] = "store row (first capture) + log settlement line"
        estimates = []
        for task in ("classification", "strip"):
            v = low_costs.get(f"{pid}|{task}")
            if v: estimates.append({"task": task, "cost_estimate": round(sum(v) / len(v), 6), "basis": f"low run's {task} row(s) for {pid}; configuration-independent route (not Opus), same prompt"})
        rec["model_calls"] = opus; rec["estimated_calls"] = estimates
        rec["turn_cost_opus"] = round(sum(c["cost"] for c in opus), 6); rec["turn_cost_estimated_other"] = round(sum(e["cost_estimate"] for e in estimates), 6)
        rec["turn_cost"] = round(rec["turn_cost_opus"] + rec["turn_cost_estimated_other"], 6)
        exact += rec["turn_cost_opus"]; est += rec["turn_cost_estimated_other"]
        if pid.startswith("C"):
            blind_line = next((l for l in rec["logs"] if "blind position payload" in l), "")
            rec["structural"].update(same_configuration=(len(opus) == 2 and '"configuration": "opus-5"' in blind_line and opus[0]["cache"] in ("created", "hit") and opus[1]["cache"] == "hit"),
                                      same_configuration_evidence="log + mechanism: the store was reset before the corrected capture; the blind payload names configuration opus-5, both Opus settlement lines are on opus-5, and the harness registry held one active partner configuration (opus-5 at this effort), whose pinned completion refuses a mismatch. Not a row-level proof.",
                                      cache_rows=all(c["cache"] in ("created", "hit") for c in opus))
    d["total_cost_opus"] = round(exact, 4); d["total_cost_estimated_other"] = round(est, 4); d["total_cost"] = round(exact + est, 4)
    d["evidence_note"] = ("Model-call evidence reconstructed on 9 September 2026: the first capture keyed rows on the user message and so recorded only the response call; this run's scratch store was reset by a later run before the capture was corrected. "
                          "Opus calls (blind position, response) are taken from the gateway's per-call settlement lines captured in the log, and the response call is additionally the store row from the first capture (the two agree to the cent). "
                          "The classification (Haiku) and strip (Sonnet) calls are not in this run's evidence; their cost is carried as an estimate from the low run's rows for the same prompt and labelled as such. Answers, blind rows and deliberation rows are as first captured.")
    for pid in ("I4",):
        ok, note = check_I4(d["prompts"][pid]["answer"]); d["prompts"][pid]["mechanical"] = {"pass": ok, "note": note}
    json.dump(d, open(S / f"run_{effort}.json", "w"), indent=2, ensure_ascii=False, default=str)
    print(effort, "opus", d["total_cost_opus"], "est other", d["total_cost_estimated_other"], "total", d["total_cost"], "I4", d["prompts"]["I4"]["mechanical"], "C same-config", [d["prompts"][c]["structural"]["same_configuration"] for c in ("C1","C2","C3","C4","C5","C6")])
ok, note = check_I4(low["prompts"]["I4"]["answer"]); low["prompts"]["I4"]["mechanical"] = {"pass": ok, "note": note}
json.dump(low, open(S / "run_low.json", "w"), indent=2, ensure_ascii=False, default=str)
print("low total", low["total_cost"], "I4", low["prompts"]["I4"]["mechanical"])
