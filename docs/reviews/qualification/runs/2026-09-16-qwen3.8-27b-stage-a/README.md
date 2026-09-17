# Qwen3.8-27B challenger — Stage A preparation, STOPPED at the ruled gates — 16–17 September 2026

Owner ruling of 16 September 2026 (the one authorised Local Partner challenger) and amendment of 17 September 2026 (the MLX auto-fit context exception). **The frozen Stage A suite (`60b65b7`) did not run against this candidate:** both ruled gates that precede it failed on the first transmitted call, and the ruling says STOP on either. Nothing here admits anything; Qwen remains `NOT_ADMITTED`, GPT-OSS remains `NOT_ADMITTED`, Sol remains the production Partner. Cloud spend $0; one local call, $0 KNOWN.

- `proof_boundary_parity.py` — the hidden-reasoning boundary and exact-preflight parity proof through the real candidate path (persona v1.8 whole, Core envelopes, retained history, exact preflight, OpenAI-compatible HTTP inference, scratch store). Nothing is loaded or unloaded by it; hidden reasoning text is never read, stored or printed.
- `results-boundary-parity.json` — the raw evidence of the one call that ran.

## Artifact and identity (read from LM Studio's own listings)

`lmstudio-community/Qwen3.8-27B-MLX-6bit`, obtained by its full Hugging Face URL (the Hub-style name does not resolve in `lms get`); 22,804,836,386 bytes (21.3 GiB on disk). LM Studio's canonical runtime identifier: **`qwen3.8-27b-mlx`** (`lms ls` model key, `/api/v0/models` id, `/v1/models` id), architecture `qwen3_5`, quantization `6bit`, MLX, maximum context 262,144, vision-capable. Registry entry `qwen3-8-27b-mlx-6bit-lmstudio` (`c7e2a5d1-4b6f-4e8a-9d3c-2f1b7a6e5d40`), commit `5801f11`.

## Runtime (verified read-only before the call, unchanged after it)

LM Studio 0.4.24+1 with MLX engine 1.11.0; SDK 1.6.0b1 for inspection only. **Configured context 32,768; actual loaded context 80,896 — a value substituted by the MLX runtime's auto-fit at load time, not owner-selected** (the CLI flag and the per-model configuration both request 32,768; the owner confirmed the same substitution in the app). Recorded on the row as `configured_context`, `actual_loaded_context`, `context_source`. The exact preflight used the actual 80,896 (`registry_agrees: false`, logged as a warning, the runtime governing). GPT-OSS was unloaded from memory for this work and remains on disk.

## Gate 1 — medium-reasoning / hidden-reasoning boundary: FAILED on effort

| Check | Result |
|---|---|
| `reasoning_effort=medium` transmitted by the adapter | **yes** — the request the transport sent: `model qwen3.8-27b-mlx`, `max_tokens 6144`, `reasoning_effort "medium"`, `stream true`, usage on |
| Honoured by the runtime | **NO** — LM Studio's own model input log for this call renders the system prompt as *"Reasoning effort is set to xhigh. Please think carefully through the task…"*; the SDK's template rendering of the same turns carries the identical `xhigh` line. The request ran at the preset's default, not at medium. |
| Visible content distinct from reasoning | yes — reasoning arrived in the separate `reasoning` field; no `<think>` text in any visible delta |
| Reasoning not persisted as visible content | yes — the persisted message equals the streamed visible text; no think tags |
| Reasoning not streamed through `on_delta` | yes |
| Second turn from persistence carries no hidden reasoning | not reached (the run stopped after turn 1) |
| Reasoning counts as diagnostic metadata only | yes — `reasoning_present true`, `reasoning_output_tokens 1,046` of 1,394 output |
| Not silently at `xhigh` | **NO** — see above |

## Gate 2 — exact preflight / server parity: FAILED by one token

| | SDK inspector | Server `usage.prompt_tokens` | Difference |
|---|---|---|---|
| Turn 1 | **5,560** | **5,561** | +1 |

**Likely officially-supported cause, established read-only and not compensated for:** tokenization agrees exactly — the runtime's own tokenizer counts LM Studio's logged input at 5,561 — so the difference is in the *rendering*. Both sides merge the two consecutive user messages (the record-state envelope and the user's turn) into one user block; LM Studio's server joins them with a blank line (`ENVELOPE\n\nTURN`), the SDK's `Chat` joins the parts with no separator at all (rendered `ENVELOPETURN` for a minimal two-message probe) — two characters, one token. This is the merge hazard recorded on the inspector module on 16 September 2026, now observed on the server side of the seam. Nothing was calibrated, offset, split or rewritten.

## The one call that ran

Prefill to first chunk 47.021 s; first visible text **147.82 s**; total **180.454 s**; 1,394 output tokens (348 visible + 1,046 reasoning, at the runtime's `xhigh`); terminal `complete`; model echo `qwen3.8-27b-mlx`; $0 KNOWN. Visible answer 1,774 characters (in `results-boundary-parity.json`). These figures are at `xhigh`, not the ruled medium, and are not Stage A evidence.

## Standing

STOPPED at the gates, returned to the owner. Two distinct incompatibilities: the runtime does not apply the transmitted `reasoning_effort` to this model's template on the OpenAI-compatible endpoint (the effort is baked into the template's system line at its default), and the SDK/server renderings of merged consecutive user messages differ by a separator. Neither is solved here; both would need a ruling.
