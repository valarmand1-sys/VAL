"""The MEDIUM/LOW side-by-side owner review packet — WP2 §3.3.

No numerical quality score, no self-grading, no cloud judge, no winner. The two
answers to the same task, the frozen mechanical checks as they landed, the
objective differences, and the latency each effort bought. The reading is Lord
Armand's.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = json.loads(
    (HERE.parent / "2026-09-16-gpt-oss-stage-a" / "benchmark.json").read_text()
)
MEDIUM = json.loads((HERE / "results-medium.json").read_text())
LOW = json.loads((HERE / "results-low.json").read_text())

AREAS = {t["id"]: t["area"] for t in BENCH["tasks"]}


def turns(results):
    out = {}
    for task in results["tasks"]:
        for turn in task["turns"]:
            out[(task["id"], turn["turn"])] = turn
    return out


M, L = turns(MEDIUM), turns(LOW)
keys = sorted(M, key=lambda k: (list(AREAS).index(k[0]), k[1]))

lines: list[str] = []
w = lines.append

w("# GPT-OSS reasoning effort — paired current-system review packet")
w("")
w("Owner execution order, Voice mode work package 2 §3. The frozen twelve-task "
  "Stage A corpus of commit `60b65b7`, run once at **MEDIUM** and once at **LOW** on "
  "the **current** system — persona v1.9, current Core, the same artifact, "
  "quantization, runtime, 32,768-token context, sampling and output ceiling. "
  "**Only reasoning effort differs.**")
w("")
w("The MEDIUM run here is a **comparison baseline for LOW**. It does not reopen, "
  "repeat or revisit GPT-OSS MEDIUM's qualification or its production admission, "
  "and it cannot change MEDIUM's standing.")
w("")
w("**No quality score is computed. No winner is declared. Production remains "
  "MEDIUM.** What follows is the two answers, the frozen checks as they landed, and "
  "the latency each effort bought, for Lord Armand's reading.")
w("")

# --- the run identities -----------------------------------------------------------------
w("## The two runs")
w("")
w("| | MEDIUM | LOW |")
w("|---|---|---|")
for label, key in (
    ("Registry entry", "candidate_slug"),
):
    w(f"| {label} | `{MEDIUM[key]}` | `{LOW[key]}` |")
for label, key in (
    ("Declared reasoning effort", "reasoning_effort"),
    ("Model", "model_identifier"),
    ("Quantization", "quantization"),
    ("Runtime", "runtime"),
    ("Loaded context", "actual_loaded_context"),
    ("Persona", "persona_version"),
):
    w(f"| {label} | {MEDIUM['provenance'].get(key)} | {LOW['provenance'].get(key)} |")
w(f"| Turns answered | {sum(1 for t in M.values() if t['outcome'] == 'answered')}"
  f"/{len(M)} | {sum(1 for t in L.values() if t['outcome'] == 'answered')}/{len(L)} |")
w("")

# --- mechanical checks ------------------------------------------------------------------
def checks(turn):
    return [(c["rule"], c["passed"], c["detail"]) for c in turn["mechanical_checks"]]


w("## The frozen mechanical checks, as they landed")
w("")
w("The checks are the ones frozen with each task in `benchmark.json`. Neither run "
  "was tuned, and no check was modified.")
w("")
w("| Task | Area | MEDIUM | LOW | differs |")
w("|---|---|---|---|---|")
differing = []
for key in keys:
    m, l = M[key], L[key]
    mc, lc = checks(m), checks(l)
    mp = sum(1 for _, p, _ in mc if p)
    lp = sum(1 for _, p, _ in lc if p)
    diff = [r for (r, p, _), (_, q, _) in zip(mc, lc, strict=False) if p != q]
    if diff:
        differing.append((key, diff))
    w(f"| {key[0]} T{key[1]} | {AREAS[key[0]]} | {mp}/{len(mc)} | {lp}/{len(lc)} | "
      f"{', '.join(f'`{r[chr(0x74)+chr(0x79)+chr(0x70)+chr(0x65)]}`' for r in diff) if diff else '—'} |")
w("")
m_total = sum(1 for k in keys for _, p, _ in checks(M[k]) if p)
m_all = sum(1 for k in keys for _ in checks(M[k]))
l_total = sum(1 for k in keys for _, p, _ in checks(L[k]) if p)
l_all = sum(1 for k in keys for _ in checks(L[k]))
w(f"**Totals as measured:** MEDIUM {m_total}/{m_all} · LOW {l_total}/{l_all}. "
  "A count of frozen checks is not a quality score and is not offered as one.")
w("")

# --- latency ----------------------------------------------------------------------------
w("## Latency, per turn")
w("")
w("| Task | first visible MEDIUM | first visible LOW | faster by | total MEDIUM | "
  "total LOW | reasoning tokens M/L | visible tokens M/L |")
w("|---|---|---|---|---|---|---|---|")
for key in keys:
    m, l = M[key], L[key]
    mv = m["timing_s"]["first_visible_content"]
    lv = l["timing_s"]["first_visible_content"]
    faster = None if mv is None or lv is None else round(mv - lv, 3)
    mcall = m["calls"][0] if m["calls"] else {}
    lcall = l["calls"][0] if l["calls"] else {}
    w(f"| {key[0]} T{key[1]} | {mv} s | {lv} s | {faster} s | "
      f"{m['timing_s']['core_call_total']} s | {l['timing_s']['core_call_total']} s | "
      f"{mcall.get('reasoning_tokens')}/{lcall.get('reasoning_tokens')} | "
      f"{mcall.get('visible_tokens')}/{lcall.get('visible_tokens')} |")
w("")
mv = [M[k]["timing_s"]["first_visible_content"] for k in keys]
lv = [L[k]["timing_s"]["first_visible_content"] for k in keys]
mt = [M[k]["timing_s"]["core_call_total"] for k in keys]
lt = [L[k]["timing_s"]["core_call_total"] for k in keys]
mr = [M[k]["calls"][0]["reasoning_tokens"] for k in keys if M[k]["calls"]]
lr = [L[k]["calls"][0]["reasoning_tokens"] for k in keys if L[k]["calls"]]
w(f"**First visible text, median:** MEDIUM {sorted(mv)[len(mv)//2]} s · "
  f"LOW {sorted(lv)[len(lv)//2]} s. **Mean:** {round(sum(mv)/len(mv),2)} s · "
  f"{round(sum(lv)/len(lv),2)} s.")
w("")
w(f"**Total, median:** MEDIUM {sorted(mt)[len(mt)//2]} s · LOW {sorted(lt)[len(lt)//2]} s. "
  f"**Mean:** {round(sum(mt)/len(mt),2)} s · {round(sum(lt)/len(lt),2)} s.")
w("")
w(f"**Hidden reasoning tokens, total:** MEDIUM {sum(mr)} · LOW {sum(lr)}. "
  "Counts only; no hidden reasoning text was read, stored or printed anywhere.")
w("")

# --- the engineer's read ----------------------------------------------------------------
w("## The engineer's read — observations, not a verdict")
w("")
w("The named GPT-OSS weakness classes the original corpus was built to expose, "
  "inspected explicitly in both runs. Where nothing was found, that is said.")
w("")
w("**Preservation of user corrections — one real difference, and it is LOW's.** On "
  "F1 T2 the owner says the pub fell through and the dinner is now at the barn. "
  "LOW's redraft names the venue as *\"The Barn (previously the Fox & Hounds)\"*, "
  "putting the withdrawn venue back into the invitation he would send. MEDIUM drops "
  "it entirely. The frozen `excludes_all` check caught it, which is what that check "
  "was frozen for.")
w("")
w("**Explicit instruction boundaries — LOW is looser on B1.** The requirement named "
  "*7am to 7pm* and *after 6pm*; LOW converted all three to 24-hour time "
  "(`07:00`, `19:00`, `18:00`), which is why the frozen `contains_all` reports "
  "`missing ['6']`. LOW also appended *\"Please let me know if any additional "
  "details are required.\"* to a task that said *give me the message only, nothing "
  "before or after it*. MEDIUM met both.")
w("")
w("**A2 goes the other way, and the check is the reason.** MEDIUM italicised the "
  "word *Ledger* and the frozen `no_stage_directions` rule matched the italics. "
  "That is the check finding formatting rather than a stage direction; it is "
  "reported exactly as it landed and is not re-graded here. Both efforts answered "
  "the question in prose as asked.")
w("")
w("**Shared, and therefore not a difference between the efforts:** A1 "
  "`no_stage_directions` flagged an italicised phrase in *both* runs, and F2 T3 ran "
  "to three paragraphs against a maximum of two in *both*. Neither is evidence "
  "about reasoning effort.")
w("")
w("**Unsupported factual invention:** none found in either run on this corpus. "
  "**Invented access to system logs or observations:** none. MEDIUM's E2 answer "
  "tells the owner to consult his own system logs and backup scheduler, which is "
  "the opposite failure and correct. **Arithmetic and date reasoning:** no error "
  "found in either run here; the 16 September Stage A finding stands on its own "
  "evidence and is not revisited. **Contradiction of supplied context:** none "
  "beyond the F1 T2 correction failure above. **Material omission:** the B1 time "
  "conversion above; nothing else.")
w("")
w("**What this does not establish.** Sixteen turns at each effort is one paired "
  "run, not a distribution: neither the two LOW failures nor the one MEDIUM "
  "failure is shown to be reproducible, and the corpus was never built to measure "
  "reasoning effort. Both efforts answered every turn, neither refused, neither "
  "truncated, and no hidden-reasoning marker reached a visible answer.")
w("")
w("**Production remains MEDIUM.** Nothing here changes that, and nothing here is "
  "a recommendation. The decision is Lord Armand's.")
w("")

# --- the answers ------------------------------------------------------------------------
w("## The two answers, task by task")
w("")
w("Exactly as persisted. Read these rather than the counts above.")
w("")
for key in keys:
    task_id, index = key
    m, l = M[key], L[key]
    w(f"### {task_id} T{index} — {AREAS[task_id]}")
    w("")
    w("**Prompt**")
    w("")
    w("> " + m["user_prompt"].replace("\n", "\n> "))
    w("")
    for name, turn in (("MEDIUM", m), ("LOW", l)):
        call = turn["calls"][0] if turn["calls"] else {}
        w(f"**{name}** — first visible {turn['timing_s']['first_visible_content']} s, "
          f"total {turn['timing_s']['core_call_total']} s, "
          f"reasoning {call.get('reasoning_tokens')} tok, "
          f"visible {call.get('visible_tokens')} tok, "
          f"terminal `{call.get('terminal_state')}`, cost {call.get('cost')}")
        w("")
        body = turn["visible_answer"] or f"*(no answer: {turn['refusal']})*"
        w("> " + body.replace("\n", "\n> "))
        w("")
        failed = [(r, d) for r, p, d in checks(turn) if p is False]
        if failed:
            w(f"*{name} frozen checks not met:*")
            for rule, detail in failed:
                w(f"- `{rule['type']}` — {detail}")
            w("")
    w("")

out = HERE / "review-packet.md"
out.write_text("\n".join(lines) + "\n")
print("written:", out, len(lines), "lines")
print("checks differing on:", [f"{k[0]} T{k[1]}: {d}" for k, d in differing])
