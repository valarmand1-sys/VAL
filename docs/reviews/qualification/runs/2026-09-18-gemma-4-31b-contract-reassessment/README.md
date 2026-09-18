# Gemma 4 31B — fresh serving-contract reassessment — 18 September 2026

Owner request of 18 September 2026. Research and contract analysis only: **nothing was downloaded, nothing was loaded, no inference ran, no registry, adapter or routing change was made, Mistral was not deleted.** Gemma 4 31B remains NOT_ADMITTED and not downloaded. This supersedes the pre-download screen of 17 September for technical facts; the two serving seams found since (adjacent same-role ingress; historical-assistant end-of-sequence) are closed in Val's local adapter and are not carried forward as Gemma blockers.

Evidence classes used below: **[DOC]** documented fact from a primary source; **[SRC]** read from the repository or source at a named revision; **[LOCAL]** read-only inspection of this machine; **[INF]** inference; **[OPEN]** unresolved until a live proof.

## 1. Upstream contract — `google/gemma-4-31B-it`

- **Revision inspected [SRC]:** `842da3794eaa0b77d5f08bae87a17459d91ff475`, last modified 20 July 2026; ungated; licence tag `apache-2.0`. Template history on `main`: `68abe48010cb` (15 July 2026) "fix: chat template — null handling, reasoning preservation, turn-tag balance, input validation"; `fcf2302760ae` (18 May), `145dc2508c48` (28 April), `e51e7dcdb6fe` (10 April). A byte copy of the template at this revision is kept beside this file (`official-chat_template@842da37.jinja`, SHA-256 `ae53464bf3be25802b3a5b37def7fd89667067d7577049b3b2d74c4d8de4c6d4`).
- **Thinking defaults [SRC]:** `enable_thinking | default(false)` and `preserve_thinking | default(false)` (template lines 186–187). With `enable_thinking` true the template emits `<|think|>` at the start of the system turn; with it false and a generation prompt, the template pre-closes an empty thought channel (`<|channel>thought\n<channel|>`).
- **Prior thoughts [SRC][DOC]:** a historical assistant message's thinking is rendered only after the last user message, or when `preserve_thinking` is true *and* the message carries tool calls (`thinking_gate`, line 240); a `strip_thinking` macro removes channel blocks from historical text. The model card: thoughts from previous turns must not be added before the next user turn. Val's contract — visible answer persists, reasoning never persists or re-enters history, `preserve_thinking = false` — is the upstream default behaviour.
- **System role [SRC]:** native; a leading `system`/`developer` message renders in its own turn.
- **Sampling [SRC]:** `generation_config.json` at the same revision: `temperature 1.0`, `top_p 0.95`, `top_k 64`, `do_sample true`.
- **Attention shape [SRC]:** 60 layers — 50 sliding-window (window 1,024; 16 KV heads × 256) and 10 global (4 KV heads × 512); 262,144 positions.

## 2. Serving paths

### LM Studio (MLX or GGUF) — INCOMPATIBLE on thinking governance
- **[DOC]** `/v1/chat/completions` documents `model, top_p, top_k, messages, temperature, max_tokens, stream, stop, presence_penalty, frequency_penalty, logit_bias, repeat_penalty, seed` — no `chat_template_kwargs`, no thinking field; the API changelog lists no 2026 entry adding one. Independent reports state LM Studio does not pass `chat_template_kwargs.enable_thinking` through to the template. Thinking is a per-model custom field ("Enable Thinking", default true) set in the app — a UI preset Core cannot declare per request. Under the owner's rule that is CONTRACT-INCOMPATIBLE, for MLX and GGUF alike.
- **[DOC]** The native `/api/v1/chat` does take `reasoning: "off" | "low" | "medium" | "high" | "on"` per request, but its only conversational input is `input` plus `previous_response_id` — stateful, with no caller-supplied assistant history — so Core could not remain authoritative over history. Not viable.
- **[LOCAL]** Installed: LM Studio 0.4.24+1, MLX engine 1.11.0, llama.cpp engines 2.33.0–2.40.0; macOS 26.6.2 (the request named 26.2; the machine reports 26.6.2).
- **MLX reasoning risk:** `lmstudio-ai/mlx-engine#337` is still open (14 June 2026, no maintainer response), names only the 26B-A4B QAT build, and reports thinking never terminating on MLX while GGUF terminates. The 31B is not named there. Classification: **CURRENT RISK — NEEDS LIVE PROOF**, and moot while the governance gate fails.
- **Context:** the MLX path substitutes context upward (observed twice on this machine; `lmstudio-bug-tracker#2250` open); the GGUF path is reported to honour the configured value.

### Standalone llama.cpp server + GGUF — COMPATIBLE, NEEDS LIVE PROOF
Stable inspected: Homebrew `llama.cpp` stable **b10360** (release exists; not installed here) **[LOCAL][SRC]**.
- **Thinking declared per request [SRC]:** `chat_template_kwargs` is read from the request body and merged over the server default (`server-common.cpp` 1073–1076); `enable_thinking` is parsed as a boolean and a string is rejected; `reasoning_effort: "none"` also disables thinking. `preserve_thinking` travels through the same kwargs as an ordinary template variable.
- **Verification of the executed mode [SRC]:** `POST /apply-template` runs the **same** `oaicompat_chat_params_parse` as chat completions (`server-context.cpp` 4903–4911), so the identical request body — messages plus `chat_template_kwargs` — returns the exact rendered prompt: Core can see `<|think|>` present or absent before inference. `GET /props` returns the active `chat_template`, `n_ctx`, `model_path`, `bos_token` and `build_info`, so the template in force can be hashed against the pinned official revision.
- **Reasoning separation [SRC]:** a dedicated Gemma 4 format, `COMMON_CHAT_FORMAT_PEG_GEMMA4`, with `thinking_start_tag "<|channel>thought"` and end tag `<channel|>`; with `--reasoning-format auto` (default) reasoning is extracted into `reasoning_content`, which Val's local adapter already treats as discard-and-record. No regex surgery in Core.
- **Exact preflight [SRC][DOC]:** `POST /v1/chat/completions/input_tokens` — documented at this tag as token counting that "accepts a chat completion body as input" — parses the same body with the same function and returns `input_tokens` from `tokenize_mixed(..., add_special=true, parse_special=true)`. One canonical request body, counted by the serving process itself, then sent unchanged for inference; no SDK, no template clone, no offset. Parity with `usage.prompt_tokens` is **[OPEN]** until the first call.
- **Context [SRC]:** `-c 32768` with `-np 1`; `/props` and `/slots` report `n_ctx` before inference. Any automatic fitting must be off or verified; a value other than 32,768 stops the run.
- **Security and transport [DOC]:** `--host` default `127.0.0.1`; `--api-key`; OpenAI-compatible `/v1/chat/completions` with SSE streaming and `usage`; `--no-mmproj` keeps the vision projector unloaded.
- **Sampling [DOC]:** `temperature`, `top_p`, `top_k` accepted per request.
- **Known risk [OPEN]:** `ggml-org/llama.cpp` discussion 21338 (April 2026, builds b8638–8738) reported thinking could not be disabled on Gemma 4 26B-A4B and 31B until `--reasoning off`; no maintainer confirmation in the thread; b10360 is far newer. Thinking OFF therefore needs its own live proof; thinking ON needs proof of termination within the 6,144 reserve.
- **Template pin:** GGUF conversions embed whatever template existed at conversion time; serving with `--chat-template-file` pointed at the official template @842da37 makes the rendering independent of the conversion and verifiable through `/props`.

## 3. Thinking ON or OFF
Both modes are contract-controllable on llama.cpp. **Recommended initial qualification mode: thinking ON, `preserve_thinking` false.** Reasons: upstream positions the model as a configurable reasoner and publishes its sampling for that use; the Stage A failures of the two earlier candidates were multi-constraint fidelity failures (planning over supplied facts), where deliberate reasoning is the more plausible help; the visibility and history contract is met without Core storing anything; the cost is latency (reasoning tokens at dense-31B decode speed), which is recorded, not a gate. Thinking OFF remains a legitimate second configuration with its own entry and proof.

## 4. Artifacts (nothing downloaded)

| Path | Repository / file | Size | Checksum | Note |
|---|---|---|---|---|
| GGUF Q6_K | `lmstudio-community/gemma-4-31B-it-GGUF` / `gemma-4-31B-it-Q6_K.gguf` | 25.20 GB | SHA-256 in HF LFS metadata (`3baf863a64af732e…`) | recommended |
| GGUF Q6_K | `unsloth/gemma-4-31B-it-GGUF` / `gemma-4-31B-it-Q6_K.gguf` | 25.20 GB | `4660692bca96f1d9…` | alternative converter |
| GGUF UD-Q6_K_XL | `unsloth/gemma-4-31B-it-GGUF` | 27.52 GB | `7f56eb37d53b0435…` | |
| GGUF Q8_0 | `ggml-org/gemma-4-31B-it-GGUF` / `gemma-4-31B-it-Q8_0.gguf` | 32.64 GB | `fcd52cebacb165a9…` | too tight on 48 GB |
| MLX 6-bit | `lmstudio-community/gemma-4-31B-it-MLX-6bit` | 26.12 GB | per-shard LFS hashes | LM Studio path, incompatible |
| MLX 8-bit | `lmstudio-community/gemma-4-31B-it-MLX-8bit` | 33.80 GB | per-shard LFS hashes | too tight; incompatible path |

All Apache 2.0. The vision projector files (`mmproj-*`) are not needed and would not be downloaded.

**Memory [INF]:** KV cache at 32,768 in f16 with a sliding-window cache ≈ 0.84 GB (50 layers × 1,024 × 16 × 256 × 2 × 2 bytes) + 2.68 GB (10 layers × 32,768 × 4 × 512 × 2 × 2 bytes) ≈ 3.5 GB. Q6_K resident ≈ 25.2 + 3.5 + ≈1.5 compute ≈ **30 GB** of 48, inside macOS's default GPU working set; Q8_0 ≈ 38 GB would not be. No same-hardware measurement exists; decode speed for a dense 31B at Q6_K on this chip is expected in the single digits to about ten tokens per second by bandwidth, to be measured, not assumed.

## 5. What the llama.cpp path would require from Val (not begun)
1. An owner ruling admitting a second LOCAL provider (loopback-only, keyed) beside `lmstudio`, with its eligibility entry.
2. A small adapter dialect reusing the local wire canonicalization and reasoning boundary, carrying `chat_template_kwargs` and sampling on the one canonical body; an HTTP inspector implementing the existing `ContextInspectingAdapter` contract through `/v1/chat/completions/input_tokens` and `/props`.
3. A truthful registry declaration for a boolean thinking state and for `top_p`/`top_k` — the present `ModelConfig` has `ReasoningEffort` and `temperature` only. This is a schema decision for the owner, not something to improvise.
4. A managed `llama-server` process with fixed flags (model, `-c 32768`, `-np 1`, loopback, key, `--no-mmproj`, pinned template file).

## 6. Proposed pre-suite proofs (after download, none run)
1. **Governance and rendering, no generation:** send the one canonical Val-shaped body to `/apply-template` and to `/v1/chat/completions/input_tokens`; require the persona as a system turn, the canonical merged user message, `<|think|>` present for ON (absent for OFF), no prior thoughts, the `/props` template hash equal to the pinned official template, `n_ctx` exactly 32,768.
2. **One harmless two-turn call:** `input_tokens == usage.prompt_tokens` on both turns (difference 0, the second turn carrying the first answer in history); `reasoning_content` populated and no channel text in visible deltas or the persisted reply; visible content non-empty within the 6,144 reserve; transmitted `temperature 1.0`, `top_p 0.95`, `top_k 64`, `enable_thinking true`, `preserve_thinking false` observed on the wire. Any failure stops.

## 7. Storage
[LOCAL] Free now 82 GiB. Mistral's directory is 24 GiB; GPT-OSS 11 GiB. Deleting Mistral and then downloading the Q6_K file (25.20 GB ≈ 23.5 GiB) is roughly space-neutral, leaving ≈ 83 GiB free; downloading without deleting would leave ≈ 58 GiB.

## Sources
Official repository and files at `842da3794eaa`: https://huggingface.co/google/gemma-4-31B-it · LM Studio chat completions: https://lmstudio.ai/docs/developer/openai-compat/chat-completions · LM Studio REST chat: https://lmstudio.ai/docs/developer/rest/chat · LM Studio API changelog: https://lmstudio.ai/docs/developer/api-changelog · mlx-engine 337: https://github.com/lmstudio-ai/mlx-engine/issues/337 · LM Studio bug tracker 2250: https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/2250 · llama.cpp tag b10360 (`tools/server/server.cpp`, `server-context.cpp`, `server-common.cpp`, `common/chat.cpp`, `tools/server/README.md`): https://github.com/ggml-org/llama.cpp/tree/b10360 · llama.cpp discussion 21338: https://github.com/ggml-org/llama.cpp/discussions/21338 · artifact listings via the Hugging Face API for `ggml-org/gemma-4-31B-it-GGUF`, `unsloth/gemma-4-31B-it-GGUF`, `lmstudio-community/gemma-4-31B-it-GGUF`, `lmstudio-community/gemma-4-31B-it-MLX-6bit`, `lmstudio-community/gemma-4-31B-it-MLX-8bit`.
