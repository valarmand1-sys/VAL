# Gemma 4 31B — qualification on the llama.cpp provider — 18 September 2026

Owner rulings of 18 September 2026 (qualification authorised; security amendment on artifact provenance). **Status: template gate closed by owner ruling; both pre-suite proofs passed; the frozen Stage A suite completed, sixteen of sixteen calls at exact parity; owner review packet delivered; NO VERDICT.** (First stop, preserved: STOPPED BEFORE ANY INFERENCE at the template-hash gate.) Gemma remains `NOT_ADMITTED`; Sol remains the production Partner. Machine provenance: Apple M4 Pro, arm64, 48 GB, **macOS 26.6.2** (the live value; an earlier request named 26.2).

## ARTIFACT PROVENANCE AND INTEGRITY

Verification time: 2026-09-18T22:10:54Z. Hugging Face is treated as transport only; identity rests on the cryptographic and structural checks below.

**Transport success (not proof of authenticity).** `curl` exit 0; downloaded over HTTPS with resume from `https://huggingface.co/lmstudio-community/gemma-4-31B-it-GGUF/resolve/main/gemma-4-31B-it-Q6_K.gguf`; nothing else was downloaded (no other quantization, no vision projector, no repository code; nothing from the repository was executed).

**Repository provenance.** Repository `lmstudio-community/gemma-4-31B-it-GGUF`; filename `gemma-4-31B-it-Q6_K.gguf`; repository revision **`67a72ce462184ca84e9531dfe657ee73b4ecc89d`** (last modified 2026-07-20; the download URL resolves to the same commit, response header `x-repo-commit`); the file itself was uploaded in commit `ee3d3771b445` (2026-04-13) and is unchanged since. Licence tag `apache-2.0`.

**Cryptographic verification.** The published identity was obtained in steps separate from the download and from the local hash, from two independent publications at that revision — the API tree entry and the git-LFS pointer file — which agree with each other and with the `x-linked-etag` header.

    EXPECTED SHA-256:
    3baf863a64af732e1fc597baf1c6ea147d4b1c30f5d1203e0f8018ad258bb1ac

    LOCAL SHA-256:
    3baf863a64af732e1fc597baf1c6ea147d4b1c30f5d1203e0f8018ad258bb1ac

    MATCH:
    TRUE

Expected bytes 25,201,483,424; local bytes 25,201,483,424.

**Structural verification (read-only parse of the GGUF header by a minimal local parser; nothing executed).** GGUF version 3; 833 tensors; 43 metadata keys; `general.architecture gemma4`; `general.name "Gemma 4 31B"`; `general.size_label 31B`; `general.type model`; `general.file_type 18` (Q6_K); `general.quantization_version 2`; `gemma4.block_count 60`; `gemma4.embedding_length 5376`; `gemma4.attention.head_count 32`; `gemma4.attention.sliding_window 1024`; `gemma4.context_length 262144`. An embedded chat template is present (16,448 characters, SHA-256 `85a08664d16d8f3be4416c92427b3ac10df1024ac566cc0b4bc3bab409393f98`) — an April 2026 conversion's template, **not used**: the server is launched with the pinned official template file. Consistent with Gemma 4 31B Instruct, Q6_K GGUF.

**Canonical local path.** `/Users/josepharmand/Models/val-llamacpp/gemma-4-31B-it-Q6_K.gguf`. *Finalization, stated plainly:* the temporary `.part` name was removed after the byte-size and SHA-256 match of the original download step and **before** the owner's security amendment arrived; the repository-revision provenance and the GGUF structural inspection above were performed afterwards, on the same bytes, and the server had by then loaded the file. No generation of any kind had occurred (server counters below).

**Runtime verification (read-only; no inference).** llama.cpp **b10360 (`48d22e295`)**, Homebrew stable, built with AppleClang 21 for Darwin arm64; Metal device `MTL0: Apple M4 Pro` (38,338 MiB working set). Launch contract: `serve_gemma.sh` (loopback, key file, `--ctx-size 32768 --parallel 1 --fit off`, `--chat-template-file` the pinned official template, `--no-mmproj`, `--no-webui`, `--reasoning-format auto`). Listening socket: `127.0.0.1:8766` only. Authentication: `/props`, `/metrics`, `/apply-template` and `/v1/chat/completions` reject unauthenticated requests (401); `/health` and the model list `/v1/models` answer without a key by llama.cpp's design, on loopback only. Served identity `gemma-4-31b-it-q6_k` (the launch alias) with server metadata `n_params 30,697,345,596`, `ftype Q6_K`, `n_ctx_train 262,144`, model path the canonical path above; vision, video and audio modalities off. **Configured context 32,768; actual server context 32,768; one slot.** Server counters at verification: `prompt_tokens_total 0`, `tokens_predicted_total 0`, `n_decode_total 0` — **no inference occurred before or during this gate.**

## The template gate — CLOSED by owner ruling (18 September 2026)

The run first stopped here, as ruled, because the raw hashes differ. The owner then accepted **this specific one-byte terminal-LF normalization and nothing broader**: if and only if the pinned official file ends in exactly one LF, the active template is compared with the file minus that one byte. No `rstrip`, no whitespace, CRLF or Unicode normalization, no second newline, no interior difference, no semantic equivalence. The rule lives in `val_providers.llamacpp_inspector.compare_with_pinned_template`, is used by the proofs and by the Stage A harness's llama.cpp branch, and is pinned by seven tests. LM Studio behaviour is unchanged.

| | SHA-256 |
|---|---|
| A. Raw official template (`google/gemma-4-31B-it` @ `842da3794eaa`), 18,683 bytes, 18,681 characters | `ae53464bf3be25802b3a5b37def7fd89667067d7577049b3b2d74c4d8de4c6d4` |
| B. Canonical official template, the raw file minus its one terminal LF, 18,682 bytes | `6a1015c47ccfcfa67c3b772385bccee357a4d37c3cda37bd202e9047f391ab82` |
| C. Active server template (`/props`), 18,682 bytes | `6a1015c47ccfcfa67c3b772385bccee357a4d37c3cda37bd202e9047f391ab82` |

**RAW OFFICIAL != ACTIVE. CANONICAL OFFICIAL == ACTIVE.** The upstream hash is not rewritten. Correction of this file's earlier text: it gave the raw file as 18,681 *bytes*; that figure is its character count, and the byte count is 18,683. The hashes were and are right.

### Rendered-equivalence check (read-only, before any inference)

`rendered_equivalence.py`, evidence in `rendered-equivalence.json`. Only `/props`, `/v1/models`, `/apply-template`, the input-token count and `/metrics` were called.

- The running server was launched with `--chat-template-file` naming the raw pinned official file itself (read from the process table), so its rendering is this runtime's rendering of the pinned official template.
- One harmless canonical chat body, built by the adapter's own `wire_body` (system line, user, assistant, user; official sampling; output allowance 6,144), was rendered through `/apply-template` twice in each thinking state. Both renderings are recorded whole. Thinking OFF: SHA-256 `55a18eec16825ccb348c2b752dfa24b49867d6735f60ea0550396587ddfb42a0`, 52 input tokens, generation prompt ending in the pre-closed empty thought channel. Thinking ON: `2290b5be8dd4fd16db5a992059c0685a63ff108c5ffa1c3f7a3f7f49e21f1e9e`, 50 input tokens, `<|think|>` in the system turn. Each rendering was identical across its two calls.
- The one byte the runtime drops follows a right-trimming `-%}` tag, checked on the pinned bytes, so it cannot reach a rendering.
- **Rendered equivalence = TRUE** on that basis. **Limitation, stated plainly:** no second engine rendered the raw file independently. No Jinja engine is installed in the project or on the machine and none was added; llama.cpp b10360 accepts no per-request template, and its template debugging tool prints no rendering for this template. The server can only ever hold the form it read from the pinned file.

### Security gate closure

Repository provenance established; expected SHA-256 established independently; local SHA-256 exact match; byte size exact match; GGUF structural identity correct; Gemma 4 31B Q6_K identity correct; loopback-only listener confirmed; authentication confirmed; configured context 32,768; actual context 32,768; one slot; canonical official hash == active server hash; rendered equivalence confirmed; **no inference before closure**: every server counter read zero after the check (`prompt_tokens_total`, `tokens_predicted_total`, `n_decode_total`, `requests_processing` all 0). No repository code was executed. The GGUF and the raw official template file are untouched.

The evaluation-only registry entry `gemma-4-31b-q6k-llamacpp` is added with the gate closed: provider `llamacpp`, identifier `gemma-4-31b-it-q6_k` as the server reports it, `NOT_ADMITTED`, no profile, no fallback, `PARTNER` target for the candidate lane only, known $0, thinking ON, `preserve_thinking` false, temperature 1.0, top_p 0.95, top_k 64, context 32,768.

## Server counters immediately before the first inference

`server-counters-before-first-inference.json`, read 18 September 2026 17:46:13 CDT: every counter zero — `prompt_tokens_total`, `tokens_predicted_total`, `n_decode_total`, `requests_processing`, `requests_deferred` and the rest. No prompt processing, no predicted tokens, no decode activity before the first proof.

## Thinking-OFF proof — PASSED (`proof-thinking-off.json`)

One harmless synthetic request, adapter-direct, nothing persisted. Thinking false and `preserve_thinking` false on the wire as `chat_template_kwargs`; temperature 1.0, top_p 0.95, top_k 64 verbatim; output reserve 6,144; no other thinking field sent; template identity under the one-terminal-LF rule; the rendering carries no `<|think|>` and ends in the template's pre-closed empty thought channel; preflight 37 == server `usage.prompt_tokens` 37 == recount 37; no reasoning returned; no thought marker in the visible answer; visible answer non-empty and complete; context still 32,768; the normalized result has no field that could carry reasoning text.

## Thinking-ON two-turn proof — PASSED (`proof-thinking-on.json`)

Two turns through the candidate lane on the scratch store under persona v1.8. On both turns: thinking true and `preserve_thinking` false on the wire; sampling verbatim; output reserve 6,144; template identity; exact parity (5,512 and 5,843); reasoning present in the provider's separate field; no thought marker in any visible streaming delta; the persisted message equal to the visible stream character for character (1,388 and 1,051); known $0; answer complete. Turn two's assembled assistant history is exactly turn one's persisted visible answer, the rendered history carries no thought channel, and the answer develops "your second point" of turn one correctly from that visible answer alone. Context still 32,768 afterwards.

## Stage A — completed, sixteen of sixteen (`results-stage-a.json`, `review-packet.md`)

Preconditions held at launch: security gate closed, both proofs passed, focused tests and the full mirror green, implementation committed (`2cb3cc8`, proofs `6c55331`), tree clean, `benchmark.json` byte-identical to freeze commit `60b65b7` (SHA-256 `a01bfb85ed26e744c80a4f1864ac1acb1c7d41e6392b5790e19a7af725787788`). Twelve tasks, sixteen calls, one pass in order, thinking ON, no prompt edit, no tuning, no hint, no retry, no regeneration, no cloud judge, no comparison during execution.

- **Parity:** difference 0 on all sixteen calls; actual context 32,768 on every call; every call `complete`; no hidden-thought marker in any visible answer; every frozen mechanical check passed.
- **Reasoning separation:** `reasoning_present` true on all sixteen; none persisted; F1 and F2 ran on visible history only.
- **Tokens:** prompts 5,487 to 6,646; completion 20,528 in total, of which 2,166 visible by the server's own tokenizer and 18,362 hidden thought and channel markers (derived, `reasoning-token-derivation.json`; llama.cpp reports no separate reasoning count).
- **Latency:** median first visible text 109.4 s, median total 141.1 s; slowest C1 at 449 s to first visible text and 470 s total.
- **Spend:** local $0.000000 KNOWN across sixteen calls; cloud $0.
- **Engineer's read:** `observations-engineer.json`, provisional and separated from the raw answers in the packet. It records, among other things, E2 stating the render's cause as fact rather than inference, F2 placing the dusk scene 15 before Daniel's 3pm Wednesday exit, D1 and D2 finding the scene 9 conflict and the one-day slack, and both F corrections preserved. These are readings for the owner, not a score.

**No verdict is declared. Gemma remains NOT_ADMITTED; no production route changed; Sol remains the production Partner.**
