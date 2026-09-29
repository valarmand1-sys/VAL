# Speculative decoding, the independent latency components, and the fastest qualified Voice configuration

Owner order of 29 September 2026 (after the corrected Qwen comparison).

**NOT RULED, NOT DEPLOYED. Production is unchanged and pinned. No physical test.**

## 1. Standing rulings recorded

- **Qwen3-30B-A3B-Instruct-2507 is removed from consideration for production Voice.**
  - Both screening runs are preserved (`2026-09-29-qwen3-30b/`): production construction
    §4, and the corrected construction §12.
  - There will be no prompt tuning, sampling change or further Qwen qualification.
  - Its weights, model definition and NOT_ADMITTED registry entry stay on disk only
    until he rules on their removal.
- **`envelope_in_system` is excluded from any proposed production release** until its
  authority boundary is repaired and qualified.
  - In the corrected comparison, GPT-OSS MEDIUM followed an instruction planted in Core's
    record content in 1 of 5 samples.
  - The earlier 0-of-19 wrong-turn result does not erase that failure.
- **Six to seven seconds of ordinary onset does not complete Voice.**

## 2. Speculative decoding: closed (the installed runtime cannot support it safely)

**Starting point: 23 September** (`VAL_Voice_Delivery_WP2_Record.md` §10), "NO COMPATIBLE
PATH":

- no speculator or draft model on the machine;
- no `draft_model` field in Val's pinned request contract.

**What has changed since:** nothing relevant in the engine or the models.

- **The engine:** `mlx-llm-mac-arm64-apple-metal-advsimd@1.11.0`, installed 8 September;
  vendored Python engine `app-mlx-generate-mac14-arm64@34`, installed 16 September.
- **Models on the machine:**
  - GPT-OSS-20B (production's, and its byte-identical clone);
  - Qwen3-4B;
  - Qwen3-30B-A3B;
  - no GPT-OSS-family draft.
- This check read the engine's own draft-model code, which the 23 September check had not.
  It found three exact reasons, each sufficient.

1. **Speculative generation needs a trimmable prompt cache, and GPT-OSS's is not trimmable
   at Val's prompt lengths.**
   - `mlx_lm.generate.speculative_generate_step` checks
     `cache.can_trim_prompt_cache(model_cache)` and otherwise raises "Speculative
     decoding requires a trimmable prompt cache". A rejected draft token must be rewound
     (`_rewind_cache` → `trim_prompt_cache`).
   - GPT-OSS (`mlx_lm/models/gpt_oss.py`, `make_cache`) keeps 12 of its 24 layers
     (`layer_types`: `sliding_attention`) in `RotatingKVCache(max_size=128)`.
   - `RotatingKVCache.is_trimmable()` returns `offset < max_size`, that is, only while
     the context is under 128 tokens.
   - Val's Voice prompts are about 5,900 tokens (the persona alone is about 5,000), so
     **every Voice turn would raise**, whatever draft model is loaded.
2. **A draft model disables the static-prefix cache.**
   - Loading one resets the cache wrapper's history (`CacheWrapper.set_draft_model`:
     `self._history = self._make_history()`).
   - `update_cache` then writes no prefix checkpoint at all ("Only checkpoint the
     main-model path": `checkpoint_prefix_len` is set only when
     `self._draft_model is None`).
   - The persona prime, which saves about 6–7 s of prefill on every turn, would stop
     working.
3. **No tokenizer-compatible draft exists to fit beside it.**
   - The engine's check (`ModelKit._is_draft_model_compatible`) requires an identical
     vocabulary size. GPT-OSS's is 201,088 (o200k_harmony).
   - The only other model with that tokenizer is GPT-OSS-120B, which is larger than the
     model it would draft for.
   - EAGLE-style GPT-OSS speculators are published for other engines (not verified
     here). This engine's speculative path takes a full draft language model, not an
     EAGLE head.

**The mixture of experts** (context only; it did not decide this): verifying several draft
tokens in one pass activates the union of their experts in every layer. That reads more
expert weights per verified step than single-token decoding, so the gain on this
bandwidth-bound model would be smaller than for a dense model of the same active size.

**Decisions and scope:**

- Setting parallelism to 1 was not treated as making anything compatible. The sequential
  kit is the one that supports drafts, and it is the cache type that refuses.
- Nothing was downloaded and the engine was not modified.
- **Speculative decoding is closed.** No further investigation, no engine project, no
  model search.

## 3. The latency-candidate components, and which stand apart from `envelope_in_system`

| component | switch or artefact | depends on `envelope_in_system`? |
|---|---|---|
| engine cache renewal and divergence checkpoint | `infrastructure/lmstudio/cache_renewal/` (hook v2.3, `3773168d…`) | **No.** It changes which cached prefixes survive, not what the request says. Its checkpoints follow whatever the request construction renders. |
| Tier-1 LOW for courtesy turns | `VAL_FAST_ROUTE_TIERS=1`, `VAL_TIER1_ROUTE=low` | **No.** The Tier-1 request (`val_gateway/tier1.py`) keeps the persona alone as the system message; its reduced state block and Core's contract are user-role messages. |
| owner precedence | `VAL_OWNER_PRECEDENCE=on` | **No.** Turn supersession by his words (`val_policy.precedence`). |
| adaptive endpoint | `VAL_ADAPTIVE_ENDPOINT=on` | **No.** Turn-taking, before the request exists. |
| speech-length bound | `VAL_TTS_LENGTH_BOUND=on` | **No.** Delivery safety. |
| combined continuations | `VAL_COMBINE_CONTINUATIONS=on` | **No.** Turn-taking. |
| envelope in the developer block | `VAL_REQUEST_CONSTRUCTION=envelope_in_system` | **It is the excluded component.** Its prime boundary (`developer_end`) goes with it. |

**Caveat:** no desktop measurement exists of the independent components *without*
`envelope_in_system`. Every integrated run since 27 September included it, and the
27 September runs used a clone that ignored reasoning effort and used generic sampling.
The measurement below fills that gap.

## 4. Registration of the measurement (fixed before it runs)

**Purpose:** to give the fastest configuration whose cognition holds the quality floor —
GPT-OSS MEDIUM, with Tier-1 LOW for courtesy turns as qualified on 26 September — with a
*measured* ordinary audible response time. This is a measurement of a changed
configuration, not a new qualification.

- **Conditions,** both on `val-exp-hub` (the clone under the model definition whose effort
  mapping, template and sampling sections are byte-identical to production's), reloaded
  before each run:
  - **baseline:** every switch unset, production's construction, the engine cache as
    shipped (renewal and divergence off).
  - **independent:** production's construction and the components of §3 other than
    `envelope_in_system`: renewal and divergence on, Tier-1 LOW, owner precedence,
    adaptive endpoint, speech-length bound, combined continuations.
- **Harness:** the established desktop bench.
  - Scratch service on port 8766 and scratch store `val_test`.
  - The real desktop frontend and player in headless Brave, with only `getUserMedia`
    replaced.
  - The 28 September session plan (`voice-bench-plan.json`): ordinary multi-turn
    conversation, social turns, corrections, continuations, an interruption, a longer
    history.
  - Production's voice, pace, TTS and endpoint policy in the baseline.
- **Order:** baseline, independent, independent, baseline. Sessions 0–4 in each run.
- **Headline:** ordinary turns, speech end → first real playback, median / p90 / worst,
  first use and mixed conversation. Repeated identical requests are not in the plan.
- **Also reported:**
  - social turns;
  - the first turn apart from later turns;
  - Voice On → ready;
  - the critical-path decomposition (endpoint, confirmation, Core, prefill, reasoning,
    first segment, synthesis, playback);
  - failures, missing audio, underruns and runaway segments from the player's records;
  - memory and swap growth, with recognition and synthesis resident.
- **Not changed:** no acknowledgement is spoken, and the voice and pace are unchanged.

## 5. The measurement was stopped by his order — INCOMPLETE, not a balanced comparison

**Stopped at 14:49 on 29 September 2026** by the owner's order: the independent
configuration leaves ordinary conversation on GPT-OSS MEDIUM, whose hidden reasoning
remains the main delay.

| run | condition | state |
|---|---|---|
| F-B1 | baseline | complete, 13:32–13:56; sessions 0–4 |
| F-I1 | independent | complete, 13:57–14:17; sessions 0–4 |
| F-I2 | independent | complete, 14:17–14:38; sessions 0–4 |
| F-B2 | baseline | **stopped during session 1 of 5.** Session 0 complete (`voice-bench-F-B2-session-0.json`); session 1's driver was killed |

**Preserved:**

- every completed run's driver logs, service logs, session files, extracted
  `voice-bench-<run>.json`, hook log, memory samples and store dump (`*.dump`, local
  only);
- for F-B2, its service log, memory samples, session 0, `hook-F-B2-partial.log` and
  `store-F-B2-partial.dump`.

**After the stop,** the instance was unloaded and the cache-renewal allowlist restored.
The balanced order (B, I, I, B) was not completed, so **no comparison is drawn.**

**Raw figures, unbalanced, for the record only** (`incomplete-raw-figures.json`; speech end
→ first real playback, identity-attributed, excluding turns spoken over her audio):

- **Tier-1 LOW courtesy turns** in the two independent runs: median **2.97 s**, p90 3.65 s
  (16 turns). These are the first desktop figures for real LOW on the Tier-1 route: the
  instance honoured effort.
- **MEDIUM "ordinary"-class turns:**
  - independent runs: median 7.26 s, p90 11.02 s (48 turns);
  - the one complete baseline: median 9.85 s, p90 14.95 s (24 turns).
- No underruns in any completed run.

## 6. Continuation

`FAST_PATH_PROPOSAL.md` was not approved. `DECISION.md` closes it and holds the unresolved
decision: whether Val's cognition may run on a dedicated local machine in the house.
