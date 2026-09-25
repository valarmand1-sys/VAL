# Prefix priming — qualified through LM Studio against current production; deployed

Owner order "PRIMING-CACHE PERFORMANCE PASS — QUALIFY THROUGH LM STUDIO; DEPLOY
AUTOMATICALLY IF THE COMPLETE PRODUCTION CONFIGURATION WINS", 25 September 2026.
Starting point `dd44430`. **WP3 remains PARTIAL.**

## 1. Isolation (§4)

The admitted artifact (`mlx-community/gpt-oss-20b-MXFP4-Q8`) was **APFS-cloned** to a
second LM Studio model key, `val-experiment/gpt-oss-20b` — SHA-256 identical, file by
file — and loaded as `val-exp`. Production resolves only `openai/gpt-oss-20b`: its exact
preflight matches identifier or model key, its readiness check key, path, identifier
or id, and every production request names it. The experiment's key, path and
identifier match none of those, so neither side could reach the other. The scratch VAL
service overrode its own process's registry entry to `val-exp`; nothing on disk changed.

Production's model was **unloaded throughout** (idle TTL): LM Studio's log shows no
load or unload of `openai/gpt-oss-20b` between 10:13 (the previous pass) and deployment,
and every unload during this pass names an experimental identifier. The resets used
`lms unload --all`, which would have evicted production had it been loaded; it was
not, and the deployment and verification used explicit identifiers. No Voice session
or turn reached production during the pass. The clone and the instance were removed
afterwards.

## 2. The mechanism through LM Studio (`lmstudio_probe.py`, `lmstudio-probe.json`)

Requests built by VAL's own adapter (`_request`, canonical wire form, MEDIUM), the real
persona (version 8), scratch envelopes.

- **Stable boundary: 5,048 tokens** — LM Studio's own header, the whole persona, and the
  tokens opening the next user message (`<|start|>user<|message|>`), which every real
  turn renders identically. No conversation, project, recall, record-state or owner
  content lies inside it (§5).
- **Prime:** the persona plus eight filler words, 5,059 tokens, so the engine's
  checkpoint (11 tokens before the end) lands exactly on the boundary. **Minimum
  generation: 1 token** — `max_tokens=0` is refused by LM Studio.
- **CLAIM A** (token identity): LM Studio's own template and tokenizer through the SDK;
  the first 5,048 tokens of the prime and of real turns are identical. **CLAIM B**
  (use): the engine's own "Prompt cache: using X/Y tokens" line in LM Studio's log —
  usage reports no cached count.

| Request | from cache | first output |
|---|---|---|
| unprimed (sequential) | 0 / 5,163 | 6.99 s |
| prime | 0 / 5,059 | 6.42 s |
| changed suffix: new conversation / other project / same conversation next turn | **5,048** | **0.70–0.80 s** |
| refresh, prime still held | 5,048 / 5,059 | 0.22 s |
| persona changed by one word | **0** | 6.85 s — reuse does not cross the divergence |
| ordinary turn afterwards | 5,048 | 0.69 s |

**Lifetime:** the stable entry survived **two** ordinary turns and was gone on the
third (a 10-entry LRU, two entries per turn) — hence a refresh after every turn.

## 3. The implementation that was qualified (and deployed)

- **Serving:** `lms load … --parallel 1` (the sequential kit). `SERVING_PARALLEL = 1`.
- **Plan** (`LMStudioAdapter.plan_prefix_prime`): refuses unless the selected engine is
  exactly `mlx-llm-mac-arm64-apple-metal-advsimd@1.11.0` with vendored
  `_amphibian/app-mlx-generate-mac14-arm64@34` (the 11-token checkpoint is that
  engine's behaviour, not a contract, §7), the instance serves at parallel 1, and a
  filler is found whose prime is token-identical to the boundary and places the
  checkpoint on it. Refusal means no prime and ordinary cognition. Correctness never
  depends on the guard: the engine reuses exact token prefixes only.
- **Call** (`Gateway.prime_prefix`): the spoken turn's own first route; the runtime
  made ready; `still_wanted` asked **before planning and again before sending**; one
  governed call through `_attempt` — budgeted, preflighted, persona-attributed —
  recorded in `model_calls` as **`prefix_prime`** (migration `0031`), no conversation,
  no message; its one token discarded.
- **Schedule** (`VoiceSession`): the session's first prime when **his first utterance
  settles** (overlapping only the resume window); a refresh when **each turn is
  over**; never while any part of his turn is under way (settled and waiting,
  thinking, or being voiced); one run at a time; each run logged content-free.

Three schedule defects were found by qualification and fixed before the final runs:
priming at Voice On overlapped his speaking and slowed Whisper's final decode from
~0.1 s to ~0.6 s (his message ~0.5 s later); refreshing after cognition overlapped her
first synthesis and slowed it from 2.6 s to 7.6 s; and planning, which renders through
the runtime, competed with a cold first turn (+3 s) until it too waited its turn.

## 4. The matrix (`matrix.py`, `matrix-*.json`, `matrix-summary.json`)

The real VAL service, desktop-shaped client, the same four genuinely different
utterances in the same order in every run. Governing trials: turns 2–4 (model
resident, changed suffix). A = production-equivalent batched (parallel 4; the plan
refused to prime it, as designed). B = sequential without priming. C = the final code.

| Median (governing) | A production (n=12) | B sequential unprimed (n=3) | **C sequential + prime (n=12)** |
|---|---|---|---|
| dispatch → first output | 7.94 s | 7.71 s | **1.56 s** |
| request-ready → first output | 8.02 s | 7.80 s | **1.64 s** |
| request-ready → first text | 11.78 s | 13.11 s | **7.50 s** |
| speech end → his message | 2.08 s | 2.07 s | 2.08 s |
| his message → playback | 15.96 s | 16.15 s | **11.09 s** |
| speech end → playback | 18.03 s | 18.13 s | **13.18 s** |

Ranges, request-ready → first output: A 7.86–8.82 s, C 0.56–1.76 s — no overlap.
Speech end → playback: A 15.20–27.03 s, C 10.82–19.32 s. Every individual trial is in
`matrix-summary.json`. Decode rate is the same in all conditions (62–68 chunks/s);
text arrives later than first output by the reasoning, whose length varies widely
between answers and is sampled identically in both kits (the engine builds both
samplers with the same `create_sampler`).

**First turn (§15):**

| Case | A | C |
|---|---|---|
| model resident, cache cold (request during/after the settle-time prime) | ready→first output 8.20–8.25 s; speech end→playback 14.73–15.58 s | 7.67, 7.38 s; 15.48, 15.28 s |
| model resident, cache warm | — | 1.65 s; 9.53 s |
| model cold (load), quick utterance | 15.45 s ready→text; 20.06 s | 14.01 s; 18.72 s |
| speech end → his message | 2.04–2.07 s | 2.05–2.16 s |

**No material first-turn regression.** On a cold cache the first turn is as fast as
production and every later turn is ~6.4 s faster to first output.

**Concurrency (§12, `concurrency_probe.py`):** two simultaneous requests — batched: both
first outputs at ~13.5 s; sequential: 7.3 s and 6.7 s. Nothing in VAL depends on
simultaneous local generation (the blind position and the answer are sequential; warming
does no inference); a coincident request queues rather than fails.

**Retention (§23):** RAM only, inside the engine process, 10-entry LRU, gone on unload —
no disk-cache lines in LM Studio's log for this model, no new files, the API history
empty. Entries include state derived from generated tokens, as production's batched
cache already did; no change to what is kept or where.

## 5. Gate

All §24 conditions met: isolated; LM Studio supports it; substantial reuse on changed
suffixes; material, repeatable net improvement over **current production** (not only
over sequential); matched readiness; prime and refresh costs included (the owner-visible
waits are in the first-turn figures); no first-turn or waiting regression; Core
assembles every request whole; reuse never crosses a divergence; isolation fixtures
pass; prime output never enters any record; execution history records it; model,
artifact, MEDIUM, persona, route, context, local-only semantics unchanged; LOW
NOT_ADMITTED; no upgrade; resources fine; the deployed code is the code measured.

## 6. Deployment and post-deployment verification

**Deployed 25 September 2026, 17:40 CDT**, source `6cb3901` (CI run 36197347337 green on
all six jobs): live store migrated `0030 → 0031` (`model_call_task_type` gains
`prefix_prime`), service restarted and healthy. Rollback state recorded beforehand:
source `dd44430`, live head `0030`, production model not loaded (it previously loaded at
the default parallel 4). Desktop code unchanged; no rebuild.

**Verified on the production runtime itself** — the scratch service on the scratch
store, addressing `openai/gpt-oss-20b`, so no owner record was touched
(`matrix-P-postdeploy.json`). The model was loaded by the new readiness code as
`openai/gpt-oss-20b`, **parallel 1**, 32,768 context, one instance.

| Turn | request-ready → first output | dispatch → first output | speech end → his message | speech end → playback |
|---|---|---|---|---|
| 1 (model cold) | 10.06 s | 7.74 s | 2.13 s | 17.74 s |
| 2 | **0.59 s** | 0.50 s | 2.17 s | 10.77 s |
| 3 | **1.62 s** | 1.54 s | 2.07 s | 12.59 s |
| 4 | **1.61 s** | 1.52 s | 2.08 s | 13.47 s |

LM Studio's own log: real turns `5048/5873` and `5048/5863` tokens from cache; primes
`5048/5059`. The first prime stood aside for his waiting request on the cold turn and
was established afterwards (6.68 s); later ones cost 0.45 s. Seven `prefix_prime` rows,
all persona-attributed, none attached to a conversation, $0; no prime text in any
message. **The improvement survived deployment; no rollback.**
