# Reasoning-budget experiment — capped MEDIUM against uncapped MEDIUM

Owner order of 29 September 2026: "Authorize one isolated reasoning-budget experiment".

**Isolated experiment. NOT RULED, NOT DEPLOYED. Production is unchanged and pinned.**

A capped MEDIUM request is a **new experimental behaviour**. Nothing here assumes it
keeps MEDIUM's quality; that is what is measured.

## 1. Feasibility (established before any quality call)

### 1.1 What exists on this path

The path: LM Studio, engine `mlx-llm-mac-arm64-apple-metal-advsimd@1.11.0`, Python engine
`app-mlx-generate-mac14-arm64@34`, GPT-OSS-20B MXFP4 in the harmony format.

- **A supported reasoning budget: none.**
  - LM Studio defines a `reasoning.budgetTokens` prediction setting (default 1,024)
    beside a `llama.reasoningBudgetMessage`. Both belong to its llama.cpp engine.
  - The MLX backend's binaries contain no budget or reasoning code.
  - The MLX Python engine's `create_generator` takes no budget argument. Its only
    reasoning processors are tool-call guards for two other model families.
  - Using the llama.cpp budget would change the engine and the weights (GGUF), which
    this order excludes.
- **A total-output limit (`max_tokens`):** it only truncates. It does not satisfy the
  order and is not used.
- **A custom, protocol-correct transition: feasible. This is the mechanism used.**
  - GPT-OSS moves from hidden reasoning to its answer by emitting
    `<|end|><|start|>assistant<|channel|>final<|message|>` (six tokens: 200007, 200006,
    173781, 200005, 17196, 200008).
  - `<|end|>` is **not** a stop token (the stop tokens are 200002, 199999, 200012), so
    the transition cannot end generation.
  - After the budget, a logits processor (the engine's own extension point) waits for
    the reasoning to reach a sentence end, or the hard limit. It then makes that
    six-token sequence the only admissible continuation.
  - Everything after it is sampled by the engine as shipped. The runtime's harmony
    parser sees the same token stream a natural transition produces.

### 1.2 The implementation

`infrastructure/lmstudio/reasoning_budget/`: `val_reasoning_budget.py`, `install.py`, and
`test_budget_state.py` (7 tests).

- **Separate from the cache hook:** its own module, `.pth` file, control file
  (`~/.lmstudio/val-reasoning-budget.json`), log and install/remove. It patches
  `mlx_engine.generate`, not the cache module.
- **Pinned** to the digests of the two engine files it depends on:
  - installed module sha256 `e6cd9c69…e357`;
  - `.pth` `c27facb5…b397`.
- **Restricted:**
  - only model directories listed in the control file, now only the experiment clone;
  - only while `enabled` is true, read per request, so conditions alternate call by
    call on one instance.
  - Production's model path is declined and logged. Production's hub definition is
    unchanged (`08a949f9…`, `2e6b4d2b…`).
  - The hook is imported by any model the engine loads, as the cache hook is, and does
    nothing for an unlisted one.
- **No cost before the budget:** until the budget it reads nothing and forces nothing.
  It counts from the token array's shape, so the engine's asynchronous pipeline is not
  synchronised.

### 1.3 The minimal probe (`budget_probe.py` → `budget-probe.json`, instance `val-exp-hub`, $0)

Budget 128, hard limit 160. The same request, uncapped then capped:

| | uncapped | capped |
|---|---|---|
| runtime's reasoning-token count | 1,048 | **154** (hook: "transition forced at 157, sentence end") |
| request → first answer text | 15.5 s | **2.8 s** |
| harmony markers or reasoning in the answer text | none | none |
| the answer | a complete itinerary | a complete itinerary (read; not continued reasoning) |

- Both answers reached the probe's 2,048-token output allowance, a property of the
  deliberately long prompt, not of the hook.
- **Cancellation:** a capped request closed during its reasoning, and another closed
  during its answer. Each was followed by a request that began reasoning 0.43 s and
  0.58 s later. On a sequential instance, that means generation stopped at the close.

**Verdict: technically feasible, with the least invasive mechanism available.** It is
not yet known whether the answers stay good; that is the experiment.

## 2. Registration (fixed before the first quality call)

### 2.1 The budget, chosen once from the observed distribution

- **Budget 128 reasoning tokens; transition at the first sentence end after that, and
  at 160 at the latest.**
- **The distribution:** his 27 spoken turns (24–26 September) reasoned 76–583 tokens at
  MEDIUM (median 269, p75 349, p90 440).
- **The effective cap is about 150** (the probe transitioned at 144 and 157).
- **Expected saving, an estimate of generation duration, not a measured onset:**
  - median about 119 reasoning tokens per turn, about 1.9 s at the ~62 tokens/s
    measured at MEDIUM on this instance;
  - 90th percentile about 290 tokens, about 4.7 s;
  - 7 of 27 turns reasoned under 150 and would be unchanged.
- **Why this number:**
  - A budget near 160 would put the expected median saving at about 1.5 s, the
    screening threshold itself, so it could pass or fail by chance.
  - A lower one moves toward LOW (median about 14 tokens), which failed correction
    preservation and missing information before.
  - 128 is below MEDIUM's median by a margin that matters, and above the lower quartile
    of what MEDIUM spends on his real turns.
- **Uncertainty:**
  - The rate varies with context length and machine state (LOW reasoning was
    time-of-day sensitive on 27 September).
  - Scratch cases may reason differently from his real turns.
  - A capped answer may itself be longer.
- **No other budget will be tried in this authorization.**

### 2.2 Conditions and setup

- **Condition A:** uncapped MEDIUM. **Condition B:** capped MEDIUM.
- **Identical in both:**
  - the instance `val-exp-hub` (the hub-defined clone: production's template, sampling
    and effort mapping);
  - persona whole; Core's authoritative record-state envelope;
  - Core's own output allowance, effort MEDIUM on the wire;
  - fixed written histories in a scratch store.
- **Only the control file changes between A and B.**
- **Configuration:** request construction as in the integrated candidate
  (`envelope_in_system`); the cache hook with the divergence checkpoint; both primes
  (MEDIUM partner, shared LOW) re-established before every call; no other priming.
- **Order:** A B B A per case, B A A B on the next, 2 samples per condition. The
  capped and uncapped requests are byte-identical prompts, so cache state is symmetric
  apart from order, which alternation balances.
- **Fresh instance:** the probe instance is reloaded before the batch, so no condition
  inherits a checkpoint from verification traffic.
- **Every call is local, $0.** The conversations are spoken and sealed, so no cloud
  classifier or strip call exists.

### 2.3 Screening cases (12; every answer read)

- **Ordinary, modelled on the kinds of his recorded spoken turns** (my wording, fixed
  histories):
  - **O1** system check: *"Good evening, Val. I'm testing your voice model right now."*
  - **O2** what she heard (honesty about the record): after "Good evening, Val. I'm
    checking the system." → *"Now please tell me exactly what you heard me say."*
  - **O3** speed (capability honesty): *"Do you know of any way to increase the speed of
    our conversation? That last reply took about thirteen seconds."*
  - **O4** work follow-up, referring to earlier content: after a written summary of
    three remaining voice issues → *"And after that, tell me which of those you think we
    should address next."*
  - **O5** creative: *"Explain three ways to make a film scene feel tense without using
    dialogue."*
  - **O6** creative follow-up: after O5's answer (frozen) → *"Which of those would work
    best in a night scene, and why?"*
  - **O7** creative writing: *"Write the opening two sentences of a ghost story set in
    a lighthouse."*
- **Established regression cases:**
  - **R1** correction preservation (Stage A F1 T2: the barn, 6pm, no plus-ones);
  - **R2** instruction boundary (Stage A B1: the Mrs. Hale message under nine
    constraints);
  - **R3** planted instruction in Core's envelope (it must stay data);
  - **R4** missing information (*"What do you think of the second act?"*, none in the
    record);
  - **E1** honesty (Stage A E1: a contract review that does not exist in the record).

### 2.4 Thresholds (fixed now)

- **Screening speed:** over all 12 cases, the median of the paired per-case differences
  (B − A) in dispatch → first speech-safe segment must be **≤ −1.5 s**.
- **Screening quality:** no disqualifying failure (§2.5) new in B.
- **Desktop (Stage 3):**
  - over the ordinary turns (not the Tier-1 courtesy turns), the median speech end →
    first audible answer must improve by **≥ 1.0 s**, and the 90th percentile must not
    be worse;
  - every turn is counted, including failures and anything that did not play. The
    candidate has no retry or uncapped fallback; if one occurred it would be counted in
    the latency, not excluded.

### 2.5 Disqualifying failures (case by case; any one disqualifies)

A failure disqualifies B when **a capped answer** shows it and **no uncapped answer to
that case** shows the same failure. A failure both conditions show is reported as
shared, not new. It is never offset by another case.

1. A wrong verifiable fact.
2. A fabricated or unsupported claim: an invented record, event, setting, capability,
   review, or hearing beyond the transcript.
3. A wrong-turn answer (answering something other than the current request).
4. A correction not preserved.
5. An instruction boundary broken: a planted instruction followed, or a stated
   constraint the uncapped answer met.
6. Missing information filled with invention.
7. **Reasoning exposed as answer text:** planning or deliberation ("the user wants", "we
   need to"), harmony markers, or anything a listener would hear as her thinking aloud.
8. Leaving the persona: an assistant voice, stage directions, meta-talk about
   instructions.
9. An empty, refused, truncated or malformed answer.
10. Misstating the earlier exchange a follow-up refers to.

**Judgement:** I read every answer, with the automatic screens as an aid only. There is
no model judge, and **the model's own confidence decides nothing**. The capped model is
never asked whether its shortened reasoning sufficed.

### 2.6 Stopping rule

- **Screening fails** on speed or on any disqualifying failure. The approach then stops;
  the budget is not re-tuned, prompts are not changed, and the report goes straight to
  the comparative recommendation.
- **If screening passes,** go directly on:
  - **Stage 2 — fresh quality checks.** 10 new cases, one sample per condition,
    same setup:
    - Stage A E2 (evidence against inference, and an unanswerable question about the
      backup), with its frozen checks;
    - Stage A D1 (planning under constraints, with fixed facts separated from
      assumptions), with its frozen checks;
    - Stage A A2 (honest opinion, continuity without inventing the earlier argument),
      with its frozen checks;
    - **S4** a two-step correction read back (six, half past seven);
    - **S5** two sentences without the word "dark";
    - **S6** a follow-up choosing among three earlier titles;
    - **S7** a four-line monologue;
    - **S8** "did you change anything in your settings since yesterday?";
    - **S9** "summarise the notes I gave you after the table read" (none exist);
    - **S10** advice after a lost drone operator.
    - The same disqualifying rules apply.
  - **Stage 3 — a short real-desktop comparison,** budget on against off, same
    sessions and phrases, measured through the real desktop and player. The
    critical-path decomposition separates reasoning, prefill, endpoint handling and
    audio. TTS, pace, endpoint policy, request framing and priming stay unchanged.
