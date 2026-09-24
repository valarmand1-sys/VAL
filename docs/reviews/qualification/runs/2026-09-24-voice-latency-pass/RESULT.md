# Pre-WP3 voice latency pass — decomposition and no-quality-loss optimization — 24 September 2026

Every figure below is labelled by how it was obtained. The four categories are kept
apart, as the order requires:

**DIRECTLY OBSERVED** · **ARITHMETIC DERIVATION** · **HYPOTHESIS** ·
**NOT DIRECTLY OBSERVABLE**

**No stage in this record is an arithmetic residual.** Every stage figure is the
interval between two marks that were both reached; a span with only one end is
reported as absent and never as zero. The only arithmetic here is deltas,
medians and percentages *between* observed figures — **ARITHMETIC DERIVATION**,
labelled where it matters — and there is consequently no
**UNATTRIBUTED RESIDUAL** to report. Nothing was named by subtracting one clock
from an unrelated one.

Production remains `gpt-oss-20b-mxfp4-mlx-lmstudio-partner` at **MEDIUM**. Persona
v1.9 revision 8, voice `val-established-v1`, LOW still `NOT_ADMITTED`. Nothing
about what Val is, how she reasons, what she sounds like or what the model sees was
changed by this pass.

---

## 1. What the request path is actually made of

Three production-shaped trials, real composition root, real recognizer, real
classification, production MEDIUM GPT-OSS, real `val-established-v1` Qwen3-TTS,
ephemeral sink, scratch store. **Every boundary below is a directly observed mark**,
not a subtraction. Medians of three; every trial is in `baseline-before.json`.

| stage | median | category |
|---|---|---|
| end of fixture speech → turn start | 1.451 s | DIRECTLY OBSERVED |
| turn start → message persisted | 0.008 s | DIRECTLY OBSERVED |
| turn start → classification start | 0.010 s | DIRECTLY OBSERVED |
| **classification** | **1.172 s** | DIRECTLY OBSERVED |
| classification end → assembly start | 0.003 s | DIRECTLY OBSERVED |
| context/recall/record-state assembly | 0.009 s | DIRECTLY OBSERVED |
| local runtime readiness | 0.254 s | DIRECTLY OBSERVED |
| exact preflight | 0.033 s | DIRECTLY OBSERVED |
| preflight end → provider dispatch | 0.003 s | DIRECTLY OBSERVED |
| **provider dispatch → first provider chunk (pre-generation)** | **9.389 s** | DIRECTLY OBSERVED |
| **first chunk → first Core-visible text (hidden reasoning)** | **4.976 s** | DIRECTLY OBSERVED |
| first visible text → speech-safe segment ready | 0.183 s | DIRECTLY OBSERVED |
| segment ready → TTS start | 0.002 s | DIRECTLY OBSERVED |
| **TTS synthesis of the first segment** | **4.900 s** | DIRECTLY OBSERVED |
| TTS return → first audio at the sink | 0.000 s | DIRECTLY OBSERVED |
| **end of fixture speech → first audio at the sink** | **22.714 s** | DIRECTLY OBSERVED |
| first Core-visible text → first audio | 5.086 s | DIRECTLY OBSERVED |

**"Request start" is now defined, by code and not by interpretation:** the first
instruction of `val_gateway.deliberate.send` — **before** the owner's message is
persisted, **before** classification, **before** context assembly, and long before
any provider is contacted. The mark is `turn_start`.

**Where the 22.7 seconds sits.** 19.3 s of it is provider and voice *generation*
(pre-generation 9.4, hidden reasoning 5.0, TTS 4.9). Of the ~3.1 s of house work,
**1.1 s is the deliberate resume window** — the interval that makes a resumed
sentence one turn instead of two — and 1.17 s is the classification call. Assembly,
recall and record-state together cost 9 milliseconds.

**There was no redundant work to remove.** Every diagnostic mark that could repeat
was counted: one classification, one assembly, one readiness check, one exact
preflight, one provider dispatch per turn. DIRECTLY OBSERVED, all three trials.

**`input_speech_end → turn start` of 1.451 s** breaks down as DIRECTLY OBSERVED
marks: transcript final at 0.45 s (whisper's final decode, ~0.33 s after the last
block) and turn submitted at 1.554 s — the 1.1 s between them being
`RESUME_GRACE_SECONDS`. Not waste; a designed wait.

---

## 2. The exact request differential — §5

**Read-only. No provider call was made by this investigation.** Rendered through
the existing exact-preflight machinery: the loaded runtime's own chat template and
tokenizer. No new approximate renderer was built.

**Labelled CURRENT RECONSTRUCTION.** The historical WP2 request bytes were not
retained, so what is compared is the current equivalent through the same governed
path. It is not claimed to be the historical bytes.

### BRANCH B — the two requests are byte-identical

Two successive A1 turns, each in its own fresh conversation, rendered seconds
apart:

| | |
|---|---|
| Serialized prompt | **27,007 bytes / 26,930 characters, identical** |
| SHA-256 | `52c96d3d…f0f1b6a` on **both** |
| Tokens | **5,752 on both** |
| First differing byte / character / token | **none** |

DIRECTLY OBSERVED. The record-state clock is minute-granular (`%H:%M`), so two
turns inside one minute render the same prompt exactly.

**Consequence for the WP2 evidence:** the warm-up and the measured MEDIUM call ran
seconds apart, so their prompts were almost certainly byte-identical too. The
absence of improvement therefore **cannot** be attributed to prompt-byte
divergence.

### The smallest real change two turns can make

Forcing the clock forward one minute:

| | |
|---|---|
| First differing byte | 25,408 |
| First differing character | 25,333 |
| **First differing token** | **5,352 of 5,752** |
| **Stable prefix** | **93.05 % of tokens** |
| Tokens after the divergence | 400 |
| Component | **the record-state envelope's clock** |
| Is the divergence after the persona? | **yes** |

DIRECTLY OBSERVED. The excerpt is `…13:00"` against `…13:01"`, inside
`prior_record_state`. This is the architecture behaving exactly as
`record_state_block`'s own docstring says it must: "the counts and the clock change
every turn, so this block must not sit inside the cached prefix." **No reordering
was proposed and none is needed.**

### §5.3 — the 5,752 tokens, by component

Differences between real template renders through the runtime's own tokenizer, so
each figure includes that component's template wrapper. Stated rather than hidden:
there is no way to price a message without its wrapper while still using the
runtime's own template.

| component | tokens | share |
|---|---|---|
| **Persona, net of scaffolding** | **4,984** | **86.65 %** |
| Template scaffolding (empty system render) | 63 | 1.1 % |
| System prompt render, total | 5,047 | 87.7 % |
| Record-state envelope alone | 637 | 11.1 % |
| The owner's own words alone | 72 | 1.3 % |
| Final user message render, total | 705 | 12.3 % |
| History | **none — this is the first message of a fresh conversation** | — |

DIRECTLY OBSERVED under the current GPT-OSS tokenizer. The prior Sol figure
(~4,821 tokens for persona v1.8 on the OpenAI tokenizer) and the earlier parity
figure (~5,417) are consistent with it but are not the same measurement, and are
not substituted for it.

---

## 3. What this serving path can reuse — §6

Read-only first, and then settled outright by the authorized probe.

**Read-only evidence.** LM Studio 0.4.24+1, CLI commit `ff50809`; the production
model served over the OpenAI-compatible `/v1` surface on loopback; the resident
instance's load configuration is `{contextLength: 32768}` and nothing else. The
SDK's own load-configuration schema exposes `keepModelInMemory`,
`offloadKVCacheToGpu`, `useFp16ForKVCache` and the two llama.cpp K/V quantization
options — **none of which is cross-request prompt reuse**, and the three K/V ones
are llama.cpp fields while this model is MLX. The prediction-configuration schema
exposes no cache or reuse field at all. No cache counter, metric or diagnostic
field appears anywhere in the server's listing or the instance info. That is
absence of a *knob*, which is not proof of absence of *behaviour* — so the probe
was run.

### §6.1 — the decisive probe

Two requests, **confirmed byte-identical before either was sent**
(`cb6a361f…0bf62f` on both), sent in immediate succession, locally, at production
MEDIUM, at $0. Diagnostic, recorded as evaluation evidence, **excluded from every
latency comparison**, nothing in the owner's conversation history.

| | call 1 | call 2 |
|---|---|---|
| **pre-generation interval** | **7.758 s** | **7.622 s** |
| request start → first Core-visible text | 9.567 s | 14.255 s |
| prompt tokens | 5,752 | 5,752 |

**Delta: 0.136 s — 1.8 %.** The materiality threshold was set beforehand at 33 %,
because reuse of a 93 % stable prefix would be far larger than that and ordinary
run-to-run noise on this machine is far smaller.

### **NO USEFUL CROSS-REQUEST PREFIX REUSE WAS OBSERVED UNDER THE TESTED CURRENT SERVING CONFIGURATION**

DIRECTLY OBSERVED. The ~7.6–9.4 s pre-generation interval was paid on every
independent request measured here, and the 93 % stable prefix bought nothing
under the configuration tested.

**Corrected 24 September 2026 (WP3 §0.1).** This section first read
"CROSS-REQUEST PREFIX REUSE NOT SUPPORTED ON THIS SERVING PATH", which claims
more than the evidence carries. What was measured is an *absence of useful
reuse* in one configuration — the loaded model, its load settings, this server
build, independent requests over the OpenAI-compatible surface. That is not
evidence that LM Studio, MLX or the underlying runtime is **incapable** of
prompt or KV reuse, and no such incapacity is claimed. A different serving mode,
load configuration or session shape was not tested and may behave differently.
The `reuse-probe.json` artifact is preserved exactly as the probe produced it,
carrying the original over-strong wording in its `finding` field; where the two
differ, this record governs.

The WP2 statement that "the warm-up did not materially reduce the pre-generation
interval" is confirmed. The earlier phrasing "LM Studio did not reuse a prefix
cache" was a HYPOTHESIS; what is now DIRECTLY OBSERVED is the absence of a
useful reduction between two byte-identical independent requests in the tested
configuration — which is a fact about the measurement, not about the runtime's
capabilities. **Prefill itself remains NOT DIRECTLY OBSERVABLE** — the server
reports no separate prefill figure, and no prefill number is derived by
subtraction. The correct term stays **pre-generation interval**.

---

## 4. The text-to-audio region — §9 and §10

**§9.** Directly observed, and it settles the WP2 hypothesis that "Qwen is
responsible for almost all of the 8.578 s": first Core-visible text → segment ready
**0.183 s**, segment ready → TTS start **0.002 s**, **TTS synthesis 4.900 s**, TTS
return → audio at sink **0.000 s**. So the first segment's boundary is established
almost immediately after the first visible characters, and essentially the whole
interval is synthesis. The hypothesis is now DIRECTLY OBSERVED.

**§10 — and it refuted the optimization I expected to make.** Same phrase, the
established voice only, nothing saved beyond the call:

| | wall clock | audio produced | real-time factor |
|---|---|---|---|
| A. first synthesis after a fresh provider | 2.946 s | 2.72 s | 1.08 |
| B. immediate repeat | 2.961 s | 2.64 s | 1.12 |
| B. again | 2.962 s | 2.48 s | 1.19 |
| C. **while GPT-OSS was generating** | **4.064 s** | 2.56 s | 1.59 |

**Cold penalty: −0.015 s. There is none.** So the §12 option of keeping the speech
provider warm for a session's lifetime **buys nothing and was not implemented** —
the evidence refused it. Each call is already a fresh subprocess that loads,
speaks and exits, and that load is not the cost; the synthesis is, at roughly
real time.

**Contention penalty: 1.103 s (37 %)** — DIRECTLY OBSERVED, and the first segment
in the live path is synthesised at exactly the moment GPT-OSS is generating
hardest, which is consistent with the live 4.9 s against this isolated 2.95 s. That
the *whole* difference is contention is a HYPOTHESIS; the 1.103 s is measured.

One limit stated: "cold" here means the first call after the provider object
existed, with the model file already warm in the operating system's page cache. A
genuinely cold machine was not measured.

---

## 5. What was implemented, and what the evidence was

Two changes. Both are inside the current architecture, neither touches the persona,
the model, the effort, the voice, the prompt, message ordering, classification,
memory, project truth, provenance or egress.

### O1 — residency is observed over HTTP, not by spawning the CLI

`LMStudioRuntime.loaded()` shelled out to `lms ps --json` on every turn: a
subprocess spawn of LM Studio's Node CLI, on the critical path. The server's own
`/api/v0/models` listing already reports each model's `state` and
`loaded_context_length`. **The CLI remains the fallback**, so a server that cannot
answer, a changed surface or a malformed reply falls back to exactly the old
behaviour — nothing is weakened.

Both sources were checked to agree on this machine before the change was kept.

| | before (CLI) | after (HTTP) |
|---|---|---|
| three runs | 0.2449 / 0.1449 / 0.1426 s | 0.0131 / 0.0083 / 0.0073 s |
| **median** | **0.1449 s** | **0.0083 s** |
| delta | — | **−136.6 ms, 94.3 %** |

DIRECTLY OBSERVED, three runs each, measured at the stage that changed.

### O2 — the cognition runtime is warmed when a voice session opens

The local model carries a one-hour idle TTL, so the first turn after an idle hour
pays its load while the owner waits. `Gateway.warm_cognition()` performs the same
readiness call the turn will perform, on the session's own thread, from
`VoiceSession.start()` — while he is still speaking. **The turn still asks, and the
turn's answer still governs**; warming is an optimisation and never a gate, and a
warming failure is reported and swallowed.

Measured directly at the stage, from a genuinely unloaded model, three runs each:

| | three runs | median | absorbed |
|---|---|---|---|
| A. no warming | 8.734 / 5.163 / 5.180 s | **5.180 s** | — |
| B. warming, 3 s head start (a short utterance) | 2.175 / 2.262 / 2.202 s | **2.202 s** | **2.978 s** |
| C. warming, 12 s head start (an ordinary sentence) | 0.021 / 0.022 / 0.020 s | **0.021 s** | **5.159 s** |

DIRECTLY OBSERVED. The effect scales with how long he speaks: a 2.6-second fixture
absorbs about three seconds of the load, an ordinary spoken sentence absorbs all of
it. **This is why the pipeline measurement alone could not show it** — the fixture
is shorter than the load — and why it was measured at the stage instead.

### The defect O2 exposed, and the fix

Warming raced the turn that followed it, **both issued `lms load`, and LM Studio
loaded the model twice**. The exact preflight then found *two* instances answering
to one model identifier, correctly refused to choose between them, and failed
closed onto the conservative byte bound — losing the exact measurement the
16 September ruling makes a hard gate. DIRECTLY OBSERVED in the first corrected
run, in the server log and in the missing preflight marks.

`ensure_ready` is now **serialised**: the lock covers observation and action
together, because a decision to load taken before another caller's load finishes is
the whole of the bug. The second caller waits, observes again, and finds the model
resident. A test drives two callers through a slow load and asserts exactly one
load, both callers answered, and the second reporting `model_loaded: false`.

**This defect was already reachable before this pass** — by two turns in flight
together — so the fix stands on its own account. It also strictly *reduces* peak
residency, since it prevents a second twelve-gigabyte instance.

### A defect in O2 itself, caught by its own test

The first version warmed the **first admitted partner route the registry listed** —
`opus-5-medium`, a paid cloud route with no local runtime — and so warmed nothing
that mattered. Routes are now ranked cheapest-first, exactly as a turn ranks them,
and only a route with a local runtime is warmed. The measurement run made before
the fix is preserved as `baseline-http-only.json`, with its `warmed: false` records
intact, rather than deleted.

---

## 6. Before and after, production-shaped

Three trials each, both from a warm model so the comparison is like for like.
`baseline-before.json` and `baseline-after.json`.

| stage | before | after | delta | attributable? |
|---|---|---|---|---|
| end of speech → turn start | 1.451 s | 1.458 s | +0.007 | no — unchanged code |
| classification | 1.172 s | 1.186 s | +0.014 | no — provider variance |
| assembly | 0.009 s | 0.008 s | −0.001 | no |
| **local runtime readiness** | **0.254 s** | **0.015 s** | **−0.239 s** | **yes — O1** |
| exact preflight | 0.033 s | 0.043 s | +0.010 | no |
| pre-generation | 9.389 s | 8.982 s | −0.407 | **no — provider variance** |
| hidden reasoning | 4.976 s | 6.124 s | +1.148 | **no — provider variance** |
| TTS first segment | 4.900 s | 2.666 s | −2.234 | **no — voice/contention variance** |
| **end of speech → first audio** | **22.714 s** | **20.899 s** | **−1.815 s** | **no — see below** |

Individual trials — before 23.466 / 22.714 / 21.587 s, after 21.178 / 18.572 /
20.899 s. The variance is not hidden behind the median.

**The end-to-end improvement is NOT claimed as this pass's result.** The house-side
work this pass changed is 0.239 s; the run-to-run swing in the model's own hidden
reasoning phase alone was 1.148 s and in TTS 2.234 s. Three trials cannot separate a
0.24 s change from that, and nothing here is offered as statistically significant.
**The attributable improvements are the two measured at their own stages: 136.6 ms
per turn always, and up to 5.159 s on the first turn after an idle hour.**

Cost: **$0.002538** for each three-trial run — three cloud classification calls at
$0.000846. Every local call, $0.

---

## 7. Machine fit — §17

Neither change holds an additional model resident. O2 loads the same single model
the turn would have loaded, only earlier; the TTL is untouched; nothing is kept
warm that was not already going to be. The double-load fix **reduces** peak
residency by preventing a second instance.

DIRECTLY OBSERVED after the pass: 32.73 GB free (68.2 %), wired 3.42 GB, **exactly
one resident instance** of `openai/gpt-oss-20b`. The warming measurement asserts
`never_more_than_one_resident_instance` across all nine of its runs. Nothing was
killed and nothing OOM'd.

Swap in use rose across the day's many deliberate load/unload cycles (1,900 MB at
the WP2 smoke, 5,021 MB now). That is the session's history of repeated
twelve-gigabyte loads, not a property of either change — neither retains anything
the previous code did not.

---

## 8. Tests

New: `packages/domain/tests/test_turn_timings.py` (10) — inert with no recorder;
monotonic and causally ordered; **a boundary that never happened reports absent and
never zero**; two turns in flight keep separate stopwatches; the record carries no
content; nothing in the module can persist anything.
`packages/gateway/tests/test_cognition_warming.py` (9) — warming reaches the route a
turn would use and not the first listed; a failure is reported and never raised; a
cloud-only route is left alone; routing, eligibility and the window are unchanged;
nothing is sent to any provider; a session warms once from `start`; a session with
nothing to warm simply listens; a warming failure does not stop it hearing him.
Four added to `packages/providers/tests/test_lmstudio_runtime.py` — residency read
over HTTP with no subprocess; a listed-but-not-loaded model is not treated as
resident; a failed listing and a malformed listing each fall back to the CLI; and
**two callers at once produce one load, not two**. Three added to
`packages/policy/tests/test_effort_evaluation.py` — the established voice is
untouched, no cloud speech route exists anywhere in the registry, and the local
partner route is the cheapest and therefore the one a turn selects.

**No existing test was weakened.** One was *strengthened*: the runtime suite's
helper now disables the HTTP residency observation explicitly, with the reason
recorded, because those tests drive the CLI state machine — previously they passed
on a developer machine only because a deliberately wrong token made the HTTP probe
fail, which is an accident and not a test.

Full suite: **1,085** (providers, policy, domain) · **830** gateway · **96** API ·
**102** CI checks. Lint, format, types, secrets, pins, scope ruling and dependency
direction green.

---

## 9. The exact remaining latency, and what is not mine to decide

After this pass, the end-of-speech-to-first-audio interval is dominated by three
things, all DIRECTLY OBSERVED, none of them avoidable inside this order's
boundaries:

| contributor | median | why it is not mine |
|---|---|---|
| **Pre-generation, ~9.0 s** | 8.982 s | 5,752 prompt tokens processed with **no useful cross-request reuse observed in the tested configuration** (§6.1). 93 % of those tokens are a stable prefix that nothing reused there. |
| **Hidden reasoning before the first visible word, ~6.1 s** | 6.124 s | A property of MEDIUM effort. LOW is parked and remains NOT_ADMITTED; its correction-preservation regression stands. |
| **TTS of the first segment, ~2.7 s** | 2.666 s | Synthesis at roughly real time, with a measured 1.1 s contention penalty while GPT-OSS generates. No cold cost exists to remove. |
| Classification, 1.19 s | 1.186 s | Serial before the provider by construction; already under its own evidence-collection ruling. |
| Resume window, 1.1 s | — | Designed: it is what makes a resumed sentence one turn. |

**Everything Val's own code contributes, end to end, sums to 0.192 s** outside the
resume window and the two provider calls — every term directly observed: persisting
his message 0.007, reaching the classifier 0.007, classifier to assembly 0.002,
assembly 0.008, assembly to readiness 0.011, readiness 0.015, exact preflight 0.043,
preflight to dispatch 0.003, the speech-safe segment boundary 0.096, and the
TTS-to-sink hand-off 0.000.

### The one next improvement, and it is an owner decision

**Cross-request prompt reuse for the 93 % stable prefix.** It is by far the largest
single contributor (~9 s per turn), the prefix is already correctly positioned for
it, and no useful reuse appeared in the configuration tested here. Whether a
different serving mode or load configuration would provide it was not established
either way. Pursuing it requires one of the changes §12 reserves to Lord Armand:

- a **serving-configuration or serving-mode change** that enables prompt/KV reuse,
  if LM Studio offers one this pass did not find; or
- a **governed persistent local session** holding the KV cache across turns.

The second carries the §13 hazard directly: a persistent provider-side cache is
acceptable only as a performance artifact, never as hidden conversation state. Core
must stay authoritative, and such a session must not be able to give the model text
Core did not assemble, a withdrawn message, a stale project scope, a stale persona
revision or a stale record-state envelope. That is a real design question with a
real failure mode, and it is his to rule on, not mine to implement.

**No other latency reduction is safely available inside the authorized
boundaries.** The house-side path has no redundant work left in it.

---

## 10. What is not claimed

- **No physical-speaker latency and no acoustic claim.** Every figure ends at the
  in-memory delivery boundary. WP3 owns the audible moment.
- **No prefill figure.** NOT DIRECTLY OBSERVABLE on this runtime; the
  pre-generation interval is what was measured and what is reported.
- **No statistical significance.** Three trials avoid treating an outlier as a law;
  they establish nothing more.
- **No end-to-end improvement claim.** The 1.815 s the median moved is inside the
  provider's own run-to-run variance.
- **No reproducibility claim for the WP2 request bytes.** The reconstruction is
  labelled as current.
- **Speculative decoding was not reopened.** §21 closed it; nothing here revisits
  it. One incidental observation, recorded for accuracy and acted on in no way: the
  LM Studio *SDK's* prediction-configuration schema does expose `draftModel` and
  speculative fields. Val's inference path is the OpenAI-compatible HTTP surface,
  whose pinned request contract has no such field, so WP2's finding stands exactly
  as written.
