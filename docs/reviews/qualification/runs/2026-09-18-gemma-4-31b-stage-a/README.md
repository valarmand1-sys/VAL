# Gemma 4 31B — qualification on the llama.cpp provider — 18 September 2026

Owner rulings of 18 September 2026 (qualification authorised; security amendment on artifact provenance). **Status: STOPPED BEFORE ANY INFERENCE at the template-hash gate.** Gemma remains `NOT_ADMITTED`; Sol remains the production Partner. Machine provenance: Apple M4 Pro, arm64, 48 GB, **macOS 26.6.2** (the live value; an earlier request named 26.2).

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

## THE OPEN GATE — official template hash

| | SHA-256 |
|---|---|
| Pinned official template file (`google/gemma-4-31B-it` @ `842da3794eaa`), 18,681 bytes | `ae53464bf3be25802b3a5b37def7fd89667067d7577049b3b2d74c4d8de4c6d4` |
| Active template reported by the server (`/props`), 18,680 characters | `6a1015c47ccfcfa67c3b772385bccee357a4d37c3cda37bd202e9047f391ab82` |
| The pinned file with its single final newline byte removed | `6a1015c47ccfcfa67c3b772385bccee357a4d37c3cda37bd202e9047f391ab82` |

**The hashes differ, so the ruled gate says STOP, and it has.** A byte-for-byte comparison finds exactly one differing region: the official file ends `{%- endif -%}\n` and the server's active template ends `{%- endif -%}` — llama.cpp drops the file's terminal newline when it reads `--chat-template-file`. Every other byte is identical. Neither template was modified to force equality. (That final newline follows a `-%}` tag, whose whitespace control discards it at render time; this is stated as context, not as a reason to pass the gate.) Whether equality up to that one terminal newline satisfies the pin is the owner's decision.

## Not yet done

No thinking-OFF proof, no thinking-ON proof, no Stage A call, no registry entry for Gemma (the served identity is now known; the entry waits with the gate). The proof script (`proof_llamacpp.py`) and the Stage A harness's llama.cpp branch compare the active template hash with the pinned file's hash and would themselves stop as written.
