# Qwen3.5-9B — the frozen generation configuration

**Recorded before either substantive case is run**, and committed before any
inference, so the record shows the settings preceded the results. §8 of the
owner's order of 22 September 2026 governs.

**One configuration governs both Case A and Case C.** Nothing below is changed
between the cases, and nothing is changed after either result is seen.

---

## What governs

**Normal supported runtime behaviour: the MLX-VLM library defaults.** Nothing is
passed to `generate()` to steer sampling. This is the same untuned posture used
for MiniCPM-o 4.5, Qwen3-Omni, Qwen2.5-VL and Qwen3-VL, so the five candidates
are comparable.

| Setting | Value | Where it comes from |
|---|---|---|
| Maximum output tokens | **2,048** | `DEFAULT_MAX_TOKENS`, `mlx_vlm/generate/common.py:22` |
| Temperature | **0.0** (greedy argmax, deterministic) | `DEFAULT_TEMPERATURE`, `common.py:23` |
| top-p | **1.0** (no nucleus truncation) | `DEFAULT_TOP_P`, `common.py:24` |
| top-k | **0** (disabled) | `DEFAULT_TOP_K`, `common.py:25` |
| min-p | **0.0** (disabled) | `DEFAULT_MIN_P`, `common.py:26` |
| Repetition penalty | **None — not applied** | `generate_step(..., repetition_penalty=None)`, `generate/ar.py:189` |
| Presence / frequency penalty | **None — not applied** | `generate/ar.py:191,193` |
| Repetition context size | 20 (inert while no penalty is applied) | `DEFAULT_REPETITION_CONTEXT_SIZE`, `common.py:27` |
| Prefill step size | 2,048 | `DEFAULT_PREFILL_STEP_SIZE`, `common.py:28` |
| KV quantisation | off (`kv_bits` None) | `generate/ar.py` |
| Seed | not set; irrelevant at temperature 0 | `generate_step(..., seed=None)` |
| Thinking budget / `enable_thinking` | not passed; `enable_thinking` defaults **False** | `generate/dispatch.py:844` |

**Stop conditions.** `generate()` resets the tokenizer's stopping criteria to
the model's own `eos_token_id` — **248044** for this artifact
(`config.json` → `text_config.eos_token_id`); the tokenizer's `eos_token` is
`<|im_end|>`. No custom `eos_tokens` and no custom `stopping_criteria` are
supplied. Generation therefore ends at the model's own end-of-turn token, or at
the 2,048-token ceiling, whichever comes first.

**The model ships no generation settings of its own.** The repository at the
pinned revision contains **no `generation_config.json`**, and `config.json`
carries no `temperature`, `top_p`, `top_k`, `repetition_penalty` or `do_sample`.
There is nothing model-specified to honour, so the library defaults are the
whole of it.

---

## What is deliberately *not* done

- **No repetition penalty is introduced because Qwen3-VL looped.** Qwen3-VL's
  Case A answer degenerated into a repetition loop under these same defaults and
  was failed for it. Adding a penalty now would be tuning the runtime against a
  previous candidate's failure and would make this candidate's result
  incomparable with the four before it. The defaults stand.
- **No artificially small output budget.** 2,048 tokens is the library default
  and is what every earlier candidate had. Lowering it would hide generation
  instability rather than measure it — the loop would be truncated instead of
  observed.
- **No sampling temperature is raised or lowered**, no top-p or top-k narrowing,
  no min-p floor, no logit bias, no custom stop strings.
- **Nothing changes between Case A and Case C**, and nothing changes after
  either answer is read.

---

## Runtime identity

| | |
|---|---|
| Environment | `~/.val-runtimes/mlx-vlm-venv` (isolated; not Val's production Python environment) |
| Python | 3.12.13 |
| mlx-vlm | 0.7.2 |
| mlx | 0.32.2 |
| transformers | 5.17.0 |
| opencv-python | 5.0.0.93 |
| numpy | 2.5.3 |

Unchanged from the Qwen3-VL run. **No bounded runtime update was taken and none
was needed.** Val's production Python environment and its pinned dependencies
are untouched.

## Artifact under test

`lmstudio-community/Qwen3.5-9B-MLX-4bit`, immutable revision
`b455506b0f574c74616dbcd56879bde38fafcff3`. `model_type: qwen3_5`, quantisation
4-bit, group size 64, mode affine. Per-file sizes and SHA-256 digests are
verified against the source and recorded in `RESULT.md`.

## Video sampling

`mlx_vlm.utils.load_video` **defaults**, exactly as for every earlier candidate —
nothing is passed to change frame count, rate or selection. What the runtime
actually delivers is recorded and compared against the frozen Part 1 sampling
record before Case C is judged.
