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
