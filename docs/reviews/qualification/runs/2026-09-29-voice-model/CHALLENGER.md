# One bounded challenger comparison — 29 September 2026

Owner order of 29 September 2026 (evening): keep Gemma 4 26B-A4B as the working Voice
candidate; before tuning it further, spend at most 45 minutes on current primary sources to
decide whether **one** challenger has a concrete, stated advantage; screen it only if it
does; stop it the moment a confirmed result disqualifies it or rules the advantage out.

Gemma's record, evidence and staged release (`VOICE_MODEL.md`) are unchanged by this
document.

## 1. The review (20:36–20:45 CDT, 9 of the 45 minutes)

Sources read: the Qwen3.6-35B-A3B model card (Hugging Face), its llama.cpp discussion
thread, Artificial Analysis's model pages and the two-model comparison (both variants), and
the AA-Omniscience hallucination-rate leaderboard as republished on 29 September 2026.

### 1.1 What the remaining delay allows a model to change

Measured on Gemma through the desktop (VOICE_MODEL.md §7.3, medians): endpoint 0.46 s,
confirmation 0.26 s, Core 0.06 s, **prefill 0.17 s, first speech-safe sentence 0.22 s**,
synthesis 0.71 s, hold 0.39 s. The model's share of a 2.3 s onset is about 0.4 s. A
challenger that generated twice as fast would move audible onset by **about 0.2 s at
most**; one with 3 B active parameters on the same runtime is expected to be within
±0.1 s of Gemma. **No challenger can be justified on onset.** The justification, if any,
is quality or memory.

### 1.2 The candidates considered

| candidate | non-thinking execution | active / total | file (Q4_K_M) | what the sources say | credible advantage over Gemma? |
|---|---|---|---|---|---|
| **Qwen3.6-35B-A3B** (the selected fallback) | documented: `enable_thinking: false` via template kwargs; `--reasoning off` reported working in llama.cpp (May 2026) | 3 B / 35 B | 20.4 GB | AA-Omniscience **hallucination rate 50.5%** against Gemma 4 26B-A4B's **86.4%** (leaderboard of 29 September 2026); Omniscience index −60 against Gemma's −51 (reasoning) / −62 (non-reasoning); Intelligence Index 15 against 13–17 | **yes, one:** it declines to answer far more often when it does not know. That bears directly on absolute requirements 1 and 2 (fabricated work, unavailable information), which a 32-sample screen permits but cannot establish universally |
| Qwen3.5-35B-A3B | yes | 3 B / 35 B | ~20 GB | hallucination rate 85.4% — no better than Gemma | no |
| Gemma 4 31B (dense) | yes | 31 B dense | ~19 GB | 85.0%; failed the Partner bar here on 18 September; dense — several times Gemma-26B's prefill time | no |
| Gemma 4 12B (dense) | yes | 12 B dense | ~7 GB | 81.0%; about 11 GB less memory, but a dense 12 B prefills roughly three times slower than 3.8 B active, and its quality for Val is unknown | memory only, at a latency cost that the order does not want; not selected |
| Nemotron 3 Nano 30B-A3B | reasoning on/off | 3.5 B / 30 B | ~18 GB | 83.3%; hybrid Mamba architecture, runtime support on this Mac unverified | no |
| GPT-OSS-20B | no (reasoning model) | 3.6 B / 21 B | 12 GB | 94.1%; the incumbent, its reasoning is the delay | no |
| Qwen3-30B-A3B-2507, Qwen3-4B, Mistral Small 3.2 | — | — | — | closed here on quality (VOICE_MODEL.md §2.2); not reopened | no |

**Limits of the evidence.** The hallucination-rate figures are a third party's benchmark
of general factual questions, not of Val's cases; the leaderboard does not say whether
Qwen3.6's figure was measured with thinking on or off, and thinking generally lowers
hallucination — so the advantage may shrink or vanish with thinking off. That is exactly
what the screen would test. The accuracy figures returned by the page reader were
inconsistent between fetches and are not relied on.

### 1.3 Selection

**Challenger: Qwen3.6-35B-A3B, non-thinking**, the fallback already named on
29 September (`ggml-org/Qwen3.6-35B-A3B-GGUF` @ `baec3ebe…`, `Qwen3.6-35B-A3B-Q4_K_M.gguf`,
20.4 GB, sha256 `671e47e0…40c7`), on the same installed llama.cpp, with the publisher's
non-thinking sampling (temperature 0.7, top-p 0.8, top-k 20, presence penalty 1.5).

**The concrete advantage claimed, before any download or test:** a materially lower
propensity to fabricate when the record does not support an answer. Not speed (§1.1), not
memory (it is 3.6 GB **larger** than Gemma, which already crossed the 20% free-memory
threshold on single samples at load — a registered risk against it).

### 1.4 Conditions for beating Gemma (registered before measuring)

The challenger replaces Gemma only if **all** of these hold; the first confirmed failure
stops it.

1. **Configuration verified first:** rendered prompt (persona verbatim in the system turn,
   record state in the newest user turn, no thinking block), the sampling the server
   reports for the request, the window; timing capture working. Differences from Gemma's
   settings are documented, not forced to match.
2. **Absolute requirements (VOICE_MODEL.md §3.1):** the same 32 critical samples, **zero**
   confirmed failures. One failure ends it.
3. **Comparative quality (§3.2):** the same 8 ordinary cases against GPT-OSS MEDIUM's
   existing answers: zero material regressions (Gemma had zero; more than zero is worse
   than Gemma).
4. **The advantage demonstrated:** an extended fabrication-pressure set — 10 new cases
   (nonexistent work, information absent from the record, capabilities Val lacks), written
   before either model sees them, run on **both** Gemma and the challenger under identical
   construction, three samples each. The advantage is demonstrated only if the challenger
   fabricates in fewer cases than Gemma **and** Gemma fabricates in at least one. If both
   are clean, no advantage is shown and Gemma is retained. Gemma's existing 32 samples are
   reused as they stand; only the new set is run on it.
5. **Timing (§3.3):** dispatch → first speech-safe sentence, ordinary first requests,
   median ≤ 2.0 s and within 0.3 s of Gemma's 1.90 s; p90 ≤ 3.5 s.
6. **Resources (§3.3):** with recognition and synthesis resident, free memory sustained
   ≥ 20% and swap growth ≤ 2 GB over the screen; the lowest sample recorded separately, as
   for Gemma.
7. **Desktop (order §4), only if 1–6 pass:** sessions 1–4 of the plan, hold kept, early
   audio off; the challenger must be within 0.3 s of Gemma's medians (2.33 s ordinary,
   2.56 s simple) with no fallback and no continuation broken, and its preparation and
   first-turn readiness reported alongside Gemma's.

## 2. Status — blocked before download: no disk

- The file is 20.4 GB. Free space on this Mac at 20:45: **16 GB**.
- Reclaimable, all re-downloadable and all from closed work:
  - the Qwen3-30B-A3B MLX weights in LM Studio (17 GB: `~/.lmstudio/models/mlx-community/Qwen3-30B-A3B-Instruct-2507-4bit`,
    plus the byte-identical clone `val-experiment/…-exp`), the candidate he removed from
    consideration — **the right item**: it alone frees enough;
  - `~/.val-models/llamacpp-exp/eagle3-gpt-oss-20b-BF16.gguf` (1.6 GB), the closed EAGLE3
    draft. **Not** `gpt-oss-20b-MXFP4.gguf` beside it: that 11 GB file is the GPT-OSS MEDIUM
    comparator the screen runs on llama.cpp, and the comparison needs it;
  - the desktop build target in the release tree (0.9 GB).
- **I did not delete any of them.** My first attempt — the EAGLE3 directory's weights,
  which I then realised included the comparator file — was refused by the automatic
  review as irreversible local destruction, and I am not pursuing deletion by another
  route. The deletion, or a `VAL_LLAMACPP_MODELS_DIR` on another volume, is
  his to do or authorise.
- Nothing about the challenger has been measured. Conditions 1–7 stand as registered.

## 3. What continued meanwhile

The Gemma release checks that need no disk (VOICE_MODEL.md §10): the resident-together
measurement failed its swap threshold and a repair now sits behind `VAL_VOICE_RELEASES_PARTNER`;
CI is green on the release branch; the underrun did not recur in 66 further turns.

## 4. Recommendation as it stands

**Retain Gemma.** The challenger's one credible advantage — abstention — is unmeasured for
Val and cannot be measured until 20.4 GB of disk exists; every other axis (onset, memory)
favours Gemma or is neutral. If he frees the space (§2), the screen is ready to run as
registered (§1.4): `voice_screen.py qwen36 verify|critical|pressure|ordinary`, then
`voice_screen.py gemma pressure` for the paired set — about 90 minutes of machine time,
$0. If he does not, this comparison is closed with the review as its record and Gemma
goes forward alone.
