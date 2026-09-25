# Prompt-prefix reuse on the installed stack — UNSUPPORTED; production unchanged

Owner order "PROMPT-REUSE PERFORMANCE PASS — TEST, QUALIFY, AND DEPLOY IF PROVEN",
25 September 2026. Starting point `60e4e81`. **WP3 remains PARTIAL.**

## 1. The installed stack (recorded before anything else)

| | |
|---|---|
| LM Studio | 0.4.24+1 |
| Inference engine | `mlx-llm-mac-arm64-apple-metal-advsimd@1.11.0` (selected); vendored `app-mlx-generate-mac14-arm64@34` — `mlx_engine`, `mlx` 0.32.0, `mlx_lm` 0.31.3 — under CPython 3.11 (`cpython3.11-mac-arm64@10`) |
| Model | `openai/gpt-oss-20b` → `~/.lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8`, its own `tokenizer.json` and `chat_template.jinja` (Harmony) |
| Production load | `lms load openai/gpt-oss-20b --context-length 32768 --ttl 3600 --yes` — parallel not specified, so the default of 4, which the engine serves with its **`BatchedModelKit`** (LM Studio's log: "BatchedModelKit loaded successfully") |
| Cache controls exposed | **none.** The CLI offers `--parallel`, `--ttl`, `--context-length`, GPU offload, identifier and speculative-decoding flags; no prompt- or KV-cache setting exists in the CLI, LM Studio's settings, or the engine's bindings |
| Cache inspection | none exposed; the engine logs "Prompt cache: using N/M tokens" in sequential mode only |

No component was upgraded.

## 2. Isolation

A second instance inside LM Studio was **rejected**: production resolves its instance by
model key, path, identifier or id (`lmstudio_runtime._instance`), and a second instance
of the same key is precisely what once made production's exact preflight fail closed.
Loading one could route production traffic to the experiment or break its preflight.

**Used instead: the installed engine itself, in a separate process.** LM Studio's own
vendored interpreter ran LM Studio's own `mlx_engine` package, unmodified, with its
own copy of the admitted model and its own cache. It never contacted the LM Studio
server, so it could not load, unload, evict, reconfigure or share state with
production. The engine's cache lookup was *wrapped* to record what it returned; nothing
else was touched. Production's model was unloaded throughout (idle TTL) and was never
loaded, changed or reconfigured by this pass.

## 3. How the engine caches (read from the installed source, then measured)

- **Batched mode (production):** an in-memory `LRUPromptCache` keyed by *prompt plus
  generated tokens*. Reuse is possible only for an exact hit, a stored entry that is a
  strict prefix of the new prompt, or a longer entry that can be **trimmed** back.
- **Sequential mode (`--parallel 1`):** `CacheWrapper` with a 10-entry
  `LRUPromptCache`, storing a checkpoint **11 tokens before the end of each prompt** and
  one after each generation.
- **GPT-OSS's cache cannot be trimmed back.** Its sliding-window layers (window 128)
  use `RotatingKVCache`, trimmable only while it holds fewer than 128 tokens; VAL's
  prompts are ~5,200–5,900 tokens.
- **Core's order** is persona → history → recall → record-state envelope → current
  turn. Two turns diverge right after the persona (different conversations) or right
  after the older history (the same conversation) — never within the last 11 tokens.

So no stored entry is ever a prefix of a real next turn, and none can be cut back to
one.

**Storage and retention, both modes:** RAM (unified memory) inside the engine process
only; deep-copied KV snapshots; up to 10 entries; evicted by LRU; gone on unload or
process exit; no disk. Entries include KV state derived from **generated** tokens,
reasoning included — true of production's batched mode today, in memory only. No
candidate was enabled, so no retention question arose for production.

## 4. Supported-mechanism check (`mechanism_check.py`, `mechanism-check.json`)

Persona: the active production persona (version 8, v1.9, source
`33831189…`) read from the live store; model's own chat template at MEDIUM; 16
generated tokens per request, none kept. Scratch fixtures only.

| Request | Tokens | CLAIM A shared leading tokens | CLAIM B from cache — batched | first token | CLAIM B — sequential | first token |
|---|---|---|---|---|---|---|
| A1 first (establishes cache) | 5,182 | 0 | 0 | 6.89 s | 0 | 8.66 s |
| B1 new conversation, changed suffix | 5,185 | 5,074 | **0** | 6.51 s | **0** | 6.49 s |
| A2 same conversation, next turn | 5,206 | 5,048 | **0** | 6.59 s | **0** | 6.45 s |
| C1 new conversation, changed suffix | 5,183 | 5,074 | **0** | 6.50 s | **0** | 6.46 s |
| M1 persona changed by one word | 5,183 | 91 | 0 | 6.53 s | 0 | 6.50 s |
| A2 again, fully identical (diagnostic) | 5,206 | 5,206 | 0 | 6.58 s | 5,195 | **0.18 s** |

Claim A (token identity) is proven from the engine's own tokenisation; claim B (use)
is the engine's own cache lookup result. **Production-shaped turns share ~97% of their
tokens and reuse none, in either mode.** The only reuse — sequential mode, fully
identical request — never happens in real use. The one-token persona change and the
cross-conversation cases show reuse never crossing a divergence (none occurred at
all). Prompt evaluation dominates first-token time here (the engine's own progress
reports cover 5,182 tokens in 2,048-token chunks); the production figure of ~7.9–8.1 s
is for 5,872 tokens through LM Studio.

**Both candidates — the current batched mode and sequential (`--parallel 1`) — fail
§11(4): no reuse with an identical prefix and a changed suffix.** They were rejected
before the full benchmark, as the order requires. No production change was made; none
qualified under §15.

## 5. For information only: a VAL-side priming request (`priming_probe.py`)

Sequential mode reuses a stored entry that is an exact prefix. A priming prompt whose
checkpoint lands exactly on the stable boundary (the system block and the opening of
the next user message: 5,048 tokens) makes one:

| Request (isolated, sequential) | from cache | first token |
|---|---|---|
| priming (5,059 tokens) | 0 | 6.28 s |
| B1 changed suffix | **5,048** | **0.41 s** |
| C1 changed suffix | **5,048** | **0.41 s** |
| A2 next turn | **5,048** | **0.44 s** |

**Not deployed and not deployable under this order:** it is not a serving setting. It
would be a new class of local model call issued by VAL itself (with its own capture in
the execution record), served sequentially (`--parallel 1`), renewed as the 10-entry
LRU evicts it, and dependent on an undocumented engine constant — harmless if that
changes (reuse is exact-prefix only) but silently useless. It also has to reach the
engine through LM Studio's templating so the checkpoint lands on the boundary, which
this isolated probe did not exercise. It is recorded as the one demonstrated way to
remove most of the ~7–8 s, for a separate ruling.

## 6. Status

Prompt reuse by serving configuration: **UNSUPPORTED** on the installed stack.
Production: unchanged (serving configuration, model, artifact, MEDIUM, persona, route,
context, local-only semantics, LOW NOT_ADMITTED). No experimental process remains.
