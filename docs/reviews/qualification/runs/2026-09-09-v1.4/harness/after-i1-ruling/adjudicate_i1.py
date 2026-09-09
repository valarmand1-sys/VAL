"""I1 adjudication under the ruled word-count definition (9 September 2026) — from captured outputs only.
Adds `mechanical_adjudicated` beside the unaltered `mechanical` on I1 of each v1.4 run record."""
import json, sys
from val_policy.words import count_words, lexical_spans
for e in ("high", "medium", "low"):
    p = f"{sys.argv[1]}/run_{e}.json"; r = json.load(open(p)); rec = r["prompts"]["I1"]
    n = count_words(rec["answer"] or "")
    rec["mechanical_adjudicated"] = {"pass": n <= 20, "note": f"{n} words under the ruled lexical definition",
        "ruling": "Lord Armand, 9 September 2026: the criterion says ≤ 20 words; a standalone em dash is punctuation, not a word; the harness's whitespace-token count was a harness-scoring defect, demonstrable independently of which configuration produced the answer. Original mechanical result preserved unaltered beside this.",
        "as_run": dict(rec["mechanical"]), "spans": list(lexical_spans(rec["answer"] or ""))}
    json.dump(r, open(p, "w"), indent=2, ensure_ascii=False, default=str)
    print(e, "as run:", rec["mechanical"], "| adjudicated:", rec["mechanical_adjudicated"]["pass"], rec["mechanical_adjudicated"]["note"])
