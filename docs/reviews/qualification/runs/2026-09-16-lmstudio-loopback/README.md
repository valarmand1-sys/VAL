# LM Studio loopback proof — the first local cognition provider, evaluation only — 16 September 2026

Owner rulings of 16 September 2026. Run through **`CandidateGateway.converse_candidate` on the scratch store `val_test`**, pinned to the `NOT_ADMITTED` entry `gpt-oss-20b-mxfp4-mlx-lmstudio` (`aac13204-3b27-477d-8bc4-ced543f61ae3`), provider `lmstudio`, model `openai/gpt-oss-20b` (MXFP4, Apple MLX). Persona v1.8 whole, the record-state and capability-state envelopes, the retained history — assembled by Val Core's own `open_turn` / `assemble_turn`, settled by `settle_turn`. **No cloud provider was called: no classification, strip or blind call; provider/API cost $0.** Harness: `harness_loopback.py` (non-mutating transport observer for first-chunk timing; reasoning text never read). Raw output: `results-cold.json`, `results-warm.json`. Code: the commit that carries this record.

**These are adapter smoke, dialect, telemetry, latency, context and accounting evidence. They are not a Partner qualification packet, not admission evidence, and confer no profile.**

## The condition the measurements were taken under

`lms ps` showed the model loaded at a 32,768-token context before the runs (a manual load). For the COLD run the model was unloaded (`lms unload`) so the first turn would pay the just-in-time load; **LM Studio's JIT reload brought the model back at its per-model default context, 8,192** — the server's listing reports `loaded_context_length: 8192` on the WARM run's rows. Every measured turn therefore ran at an 8,192 window. The 5,417-token prompt fit and the answers (528–712 tokens) fit; a longer answer would have met the window. The registry entry's `context_window_tokens` is set to 8,192 as a result (fail closed); raising the model's *default* context in LM Studio is the owner's act.

## The request shape (identical on every T1)

Persona v1.8 (whole) as the system message; the record-state envelope; the turn: *"Good evening, Val. I want your own view, in about three paragraphs, on how a house should keep a written record of the decisions it makes…"*. Three messages sent; **server-reported prompt: 5,417 tokens** (the house estimator said 6,939; the byte bound 20,7xx). Output ceiling 6,144 (the conversation default). `reasoning_effort: medium` sent and accepted.

## Measurements

| | COLD T1 (JIT load) | WARM T1 (resident) |
|---|---|---|
| Model state before | `not-loaded` | `loaded` |
| Prompt tokens (server) | 5,417 | 5,417 |
| First chunk of any kind (load + prefill) | **13.45 s** | **7.38 s** |
| ⇒ JIT load component (difference) | ≈ **6.1 s** | — |
| ⇒ Prefill of 5,417 tokens | ≈ 7.4 s (≈ 730 tok/s) | 7.38 s (≈ 734 tok/s) |
| First *visible* text at the Core boundary | **16.13 s** | **14.01 s** |
| Reasoning before visible text | 156 tokens in 2.7 s | 399 tokens in 6.6 s |
| Output tokens (visible + reasoning) | 528 (372 + 156) | 712 (313 + 399) |
| Visible characters | 1,895 | 1,515 |
| Generation after first chunk | 8.4 s (≈ 63 tok/s) | 11.4 s (≈ 62 tok/s) |
| Total completion (Core call) | **21.88 s** | **18.82 s** |
| Terminal / finish | `complete` / `stop` | `complete` / `stop` |
| Reported model echo | `openai/gpt-oss-20b` | `openai/gpt-oss-20b` |
| Streamed | yes | yes |
| Provider/API cost | **$0.000000, KNOWN** | **$0.000000, KNOWN** |
| Reservation max / settled | $0 / $0 | $0 / $0 |

An earlier COLD run (before the native-listing read was corrected): first chunk 14.15 s, first visible 20.46 s, total 25.04 s, 677 output (378 reasoning), 1,551 chars — the same shape.

**T2 and T3 on every run were refused by the house preflight before anything was sent:** *"context window is 32,768 tokens; this request's input bound (26,8xx) plus its requested output (6,144) cannot fit — refused locally, nothing routed, reserved or transmitted."* The byte-based input bound is ≈5× the server's real token count for this prompt; with the registry now at 8,192 the same rule refuses T1 as well. That is the bound doing what it exists to do; it is also the local usable-context limitation this run establishes.

## Dialect facts established by the live server (not by the unit tests)

- `/v1/chat/completions` streams usage on the final chunk under `stream_options.include_usage` — tokens present on every streamed row.
- Reasoning tokens are reported (`completion_tokens_details.reasoning_tokens`: 156 / 378 / 399) and the reasoning field is present; its text was discarded at the boundary and appears nowhere in the record.
- `reasoning_effort` is accepted on this surface.
- The response names the model (`openai/gpt-oss-20b`); the echo matched on every call.
- No `stats` object rides on `/v1` responses; prefill and generation figures come from the Core-boundary observer.
- `/api/v0/models` (native, same bearer token) reports `state`, `arch gpt_oss`, `compatibility_type mlx`, `quantization MXFP4`, `max_context_length 131072`, `loaded_context_length` — recorded on every measurement row as `runtime_diagnostics` with `hosting: local`.
- The installed token as first stored carried a leading typographic-quote character; the server's 401 named it "malformed"; the stored value was repaired in place without being displayed.

## Provenance and accounting rows (scratch store)

Every call: `model_calls` with `provider = lmstudio`, `model_identifier = openai/gpt-oss-20b`, `model_config_id = aac13204-…`, `persona_id` set, `cost = 0.000000`, `cost_certainty = known`, `terminal_state = complete`, `status = ok`, tokens recorded; `model_call_measurements` with `streamed`, `first_text_ms`, `text_output_chars`, `reasoning_present`, `reasoning_output_tokens`, `provider_reported_model`, `runtime_diagnostics`; `budget_reservations` at a $0 maximum, settled at $0. One `val` message persisted per completed turn — on the scratch store only.

## Reading

**Technically ready to proceed to Partner-quality benchmarking?** The adapter, accounting, provenance and Core governance work end to end on the real server. Two conditions precede any benchmark: the model's default context must be raised (8,192 cannot hold a Val-shaped exchange beyond its first turn under the house bound; 32,768 was refused by the byte bound from the second turn), and the house preflight's byte bound — ≈5× the real count on this tokenizer — needs a ruling for local windows.

**Fast enough on Val's real request shape to be worth it?** Warm: 7.4 s before the first token of anything and **14.0 s before the first visible text** on a three-paragraph request, then ≈62 tokens/s. The production Sol turns of 15 September showed first visible text at 13.2–18.8 s on reasoning-bearing House turns and 3.2 s on a greeting. On this shape the local route is in the same band as Sol for first visible text, slower to first token (prefill of the whole persona every turn, no prompt cache), and free. Reported plainly: not fast, not disqualifying.

## Reconciliation — later on 16 September 2026, Lord Armand

The owner reloaded `openai/gpt-oss-20b` as the single canonical instance at a **32,768-token context** and ruled that the verified live runtime state (`lms ps`: `CONTEXT 32768`; the server's listing: `loaded_context_length: 32768`, `max_context_length: 131072`, `state: loaded`). The registry entry is reconciled from the fail-closed 8,192 to **32,768**, with the just-in-time-reload hazard recorded on the entry: an unload and JIT reload restores the model's per-model default, so the instance is not to be unloaded without amending the entry. The proof was **not** rerun: at 32,768 the house preflight's byte bound still refuses the second ordinary turn (≈26.8k + 6,144), and — shown by `test_at_the_registered_window_the_consequential_response_call_is_refused_by_the_byte_bound` — refuses the **response call of a consequential exchange on its first turn** (≈27.1k + 6,144): classification, strip and the blind call run, the response never leaves, the turn ends unanswered. Changing that preflight for local windows contradicts the 8 September 2026 ruling that placed the byte bound in the context-window preflight, so it is stopped for an owner ruling rather than altered.

## Exact preflight and parity — later on 16 September 2026, after the ruling

Owner rulings of 16 September 2026 (later): the local context preflight is exact, through the read-only LM Studio SDK inspector (`lmstudio==1.6.0b1`); the cloud byte bound is unchanged; parity between the inspector's count and the server's `usage.prompt_tokens` is a hard gate. Code: commit `306d1b6` and the commit that carries this section. Harness: `harness_loopback.py` (parity-aware); raw output: `results-parity.json`. **No cloud provider was called; provider/API cost $0.**

**Runtime verified before the run, without unloading (step 10 of the ruled sequence).** The machine had rebooted at ≈19:05 CDT and the instance was gone; the owner reloaded it. Then: `lms ps` — one instance, `openai/gpt-oss-20b`, `CONTEXT 32768`, `PARALLEL 4`, `IDLE`; the native listing — `state: loaded`, `loaded_context_length: 32768`, `max_context_length: 131072`, `arch gpt_oss`, `MXFP4`, `mlx`; the SDK inspector's own enumeration — exactly one matching loaded instance, `context_length 32768`, `format safetensors`, `architecture gpt_oss`. `lms ps` after the run: the same instance, still loaded at 32,768. Nothing was loaded, unloaded or reloaded by the house.

**Provenance.** LM Studio app 0.4.24+1 (Info.plist); `lmstudio` Python SDK 1.6.0b1; model identifier and model key `openai/gpt-oss-20b`; quantization MXFP4 (MLX); loaded context 32,768 of a 131,072 maximum; `reasoning_effort: medium`; output reserve 6,144 (reasoning and visible text together); registry window 32,768 (`registry_agrees: true` on every row).

**The parity rows — the SDK's count of the exact serialised prompt against the server's `usage.prompt_tokens`, as recorded by the gateway on each measurement row:**

| Turn | Messages sent | House estimator | Byte bound (before) | **SDK count** | **Server `prompt_tokens`** | Difference | Parity |
|---|---|---|---|---|---|---|---|
| T1 | 3 | 6,939 | ≈20.7k | **5,417** | **5,417** | 0 | **exact** |
| T2 | 5 | 7,430 | ≈26.8k (refused before) | **5,769** | **5,769** | 0 | **exact** |
| T3 | 7 | 7,821 | (never reached before) | **6,046** | **6,046** | 0 | **exact** |

Every row: `preflight.source lmstudio-sdk`, `context_tokens 32768`, `fits_with_reserve true`, `parity.exact true`; no "parity is not exact" warning was logged. The pre-call measurement the harness took through `measure_candidate_context` matched the gateway's own preflight on every turn.

**The multi-turn proof — the exchange the byte bound refused from T2 on now completes at 32,768:**

| | T1 | T2 | T3 |
|---|---|---|---|
| Prompt tokens (SDK = server) | 5,417 | 5,769 | 6,046 |
| First chunk of any kind (prefill) | 7.46 s | 7.79 s | 8.18 s |
| First *visible* text at the Core boundary | **10.42 s** | **11.29 s** | **15.32 s** |
| Output tokens (visible + reasoning) | 489 (314 + 175) | 467 (259 + 208) | 567 (143 + 424) |
| Visible characters | 1,576 | 1,322 | 709 |
| Generation after first chunk | 7.7 s | 7.4 s | 9.2 s |
| Total (Core call) | 15.54 s | 15.32 s | 17.40 s |
| Terminal / status / echo | complete / ok / `openai/gpt-oss-20b` | same | same |
| Cost / certainty / reserved / settled | $0 / KNOWN / $0 / $0 | same | same |

Three `val` messages persisted on the scratch store, one per turn. Prefill ≈ 730 tok/s and generation ≈ 62 tok/s as before; first visible text 10.4–15.3 s on this shape, the difference being reasoning length (175–424 tokens before the first visible token).

**What exact parity establishes, and what it does not.** For these three admitted calls the runtime's own rendering and tokenizer, reached through the SDK, agree exactly with the count the server billed against the context. Both hazards recorded in the inspector module were present in these requests — the record-state envelope and the user turn are consecutive user messages the SDK's `Chat` merges, and `reasoning_effort` was sent on the HTTP path — and parity held. **It does not prove that the SDK can never conservatively overcount a request that the preflight refuses before inference**: a refused request is never sent, so no server count exists to compare. Parity is not timeless: SDK or server drift can break it, which is why every row carries the versions.

**Early refusal.** Not exercised on this run: no turn was consequential (the harness makes no classification call), and every prompt fit. The behaviour is pinned by the gateway tests (`test_local_context_preflight.py`): a consequential exchange whose known material cannot fit the loaded context with the reserve ends unanswered before its classification call, with nothing shortened.

**History collision — measured, not fixed.** At 32,768 with the 6,144 reserve, 26,624 tokens are usable for the prompt; the persona, envelopes and first turn take 5,417, leaving **21,207 tokens of headroom for history**. Observed growth per exchange on this shape: +352 (T1→T2) and +277 (T2→T3). At that rate the forty-message maximum and the 64,000-estimated-token history budget bind long before the window does; a heavier shape (long answers, recall envelopes up to 16,000 bytes) would reach the window sooner, and the exact preflight would then refuse the turn rather than shorten it. No collision was reached on this run.
