"""Print the mechanical, structural and economic results of the three v1.4 runs side by side."""
import json, sys
from pathlib import Path
D = Path(sys.argv[1])
runs = {e: json.load(open(D / f"run_{e}.json")) for e in ("high", "medium", "low")}
print("configuration:", {e: (r["configuration"]["effort"], r["configuration"]["persona_semantic_version"], r["configuration"]["persona_source_sha256"][:12]) for e, r in runs.items()})
print("prompts:", {e: len(r["prompts"]) for e, r in runs.items()}, "errors:", {e: [p for p, v in r["prompts"].items() if v.get("error")] for e, r in runs.items()})
print("\nmechanical:")
for pid in ["I1", "I2", "I3", "I4", "I5", "I6", "O11"]:
    print(f"  {pid:4}", {e: (r["prompts"][pid]["mechanical"]["pass"], r["prompts"][pid]["mechanical"]["note"][:70]) for e, r in runs.items()})
print("  L1  ", {e: r["prompts"]["L1"]["mechanical"] for e, r in runs.items()})
print("\nstructural (C1-C6):")
for e, r in runs.items():
    rows = [r["prompts"][c]["structural"] for c in ("C1", "C2", "C3", "C4", "C5", "C6")]
    print(f"  {e:6} blind_enforced={[s['blind_enforced'] for s in rows]} delib={[s['deliberation_row'] for s in rows]} same_config={[s['same_configuration'] for s in rows]} cache={[s['cache_rows'] for s in rows]} strip={[s['strip_states'] for s in rows]}")
    print(f"         blind cfg={sorted({s['blind_config'] for s in rows})} response cfg={sorted({s['response_config'] for s in rows})}")
print("\nclassification / strip per prompt (consequential captures):")
for e, r in runs.items():
    print(f"  {e:6}", {p: v["strip_states"] for p, v in r["prompts"].items() if v.get("captured_as")})
print("\nO11 / I4 answers:")
for e, r in runs.items():
    print(f"  {e:6} O11={r['prompts']['O11']['answer']!r}")
    print(f"  {e:6} I4 =\n{r['prompts']['I4']['answer']}\n")
print("economics:")
for e, r in runs.items():
    o = [r["prompts"][p]["wall_ms"] for p in ["O1","O2","O3","O4","O5","O6","O7","O8","O9","O10","O11","O12"]]; c = [r["prompts"][p]["wall_ms"] for p in ["C1","C2","C3","C4","C5","C6"]]
    calls = [m for p in r["prompts"].values() for m in p["model_calls"]]
    print(f"  {e:6} total ${r['total_cost']:.4f} calls={len(calls)} ordinary median {sorted(o)[6]/1000:.1f}s max {max(o)/1000:.1f}s; consequential median {sorted(c)[3]/1000:.1f}s max {max(c)/1000:.1f}s; L1 {r['prompts']['L1']['wall_ms']/1000:.1f}s")
