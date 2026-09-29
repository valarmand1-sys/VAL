# Feasibility proposal — Val's cognition on a dedicated local GPU machine

Owner order of 29 September 2026 ("Prepare one concrete, priced feasibility proposal for
the dedicated-GPU option").

> **Corrected 29 September 2026 (owner order, later the same day), without new
> benchmarks.** Four corrections, marked where they apply:
>
> - warm-prefix reuse is a mandatory pass condition, and the no-reuse outcome is defined
>   separately (§3.4, §4.1);
> - published empty-context rates are kept apart from the onset estimate (§2.1, §4);
> - the fallback policy and its memory cost are stated (§2.3);
> - prices are provisional (§6).
>
> This proposal is preserved as an alternative. No purchase, rental, seal amendment or
> deployment is authorised.

**A proposal. Nothing is authorised by it and nothing was done for it** beyond reading
published material and the house's own records:

- no purchase, rental, download, model call, benchmark or deployment;
- no change to the rule that a private Voice conversation never leaves this Mac.

Figures are labelled **measured** (house records), **published** (with source and limits)
or **estimate**.

## 1. What the evidence does and does not establish

- **No tested configuration on this Mac has demonstrated both** his response-time goal and
  his quality requirements.
- That is a statement about the configurations tested. It does not show that every
  possible local architecture must fail.
- **`envelope_in_system` is not approved.** Under it, GPT-OSS MEDIUM followed an instruction
  planted in Core's record content in 1 of 5 samples (29 September). Nothing here uses
  that construction.
- **The avatar** is the locally rendered, continuously responsive character of
  `01-architecture.md` §8.2 (amended 29 September; the loop design kept there as superseded
  history). Its implementation, fidelity, memory, GPU use and concurrent performance
  require prototype qualification. **Avatar headroom on this Mac is unverified** until the
  prototype is measured concurrently with Voice.
- **Evaluating this hardware does not mean about three seconds is accepted as
  completion.** His goal is approximately one second.

## 2. The recommended configuration

| | |
|---|---|
| **GPU** | NVIDIA GeForce RTX 5090, 32 GB |
| **Host** | a complete prebuilt desktop: AMD Ryzen 7 9800X3D, 32 GB DDR5, 2 TB NVMe, 1,200 W 80+ Gold supply, gigabit Ethernet (the ZOTAC MEK listing of §6) |
| **Operating system** | Ubuntu 24.04 LTS, headless, replacing the supplied Windows 11 |
| **Runtime** | llama.cpp `llama-server`, official CUDA build, one pinned build for the measurement and any later use |
| **Model artifact** | `ggml-org/gpt-oss-20b-GGUF`, file `gpt-oss-20b-MXFP4.gguf`, 12.11 GB, sha256 `27cd6c43…`, repository revision `ef9b12f2ff56c69cf32153a02784e7a3c88bf524` |
| **Quantization** | MXFP4, the model's native format, the same format production runs under MLX |
| **Context** | 32,768 configured (`--ctx-size 32768`), one slot (`--parallel 1`) |

**Which build to pin.**

- The house already runs official llama.cpp builds on this Mac (b10360; v0.4.1 build
  10964).
- llama.cpp's guide states gpt-oss needs build 6123 or later.
- The pin is chosen at measurement time from the builds that publish a Linux CUDA binary,
  and recorded. I did not verify which exist today.

**Why this card, in one line:** llama.cpp's guide reports the model needing 14.9 GB at 8k
context and more at larger windows. A 16 GB card would be at its limit at 32,768 and
leaves nothing for anything else.

### 2.1 Why this runtime is credible, and what is still uncertain

- **The published figures are from this runtime.** llama.cpp's maintainers publish
  `llama-bench` results for this exact file on this card:

| published, llama.cpp, `gpt-oss-20b-mxfp4.gguf` | RTX 5090 | this Mac, **measured**, MLX |
|---|---|---|
| generation | 282.5 tokens/s (`tg128`) | 62–65 tokens/s |
| prompt processing, 8,192 tokens | 8,834 tokens/s | about 650–750 tokens/s |
| prompt processing, 32,768 tokens | 6,290 tokens/s | not measured |

- **These are empty-context rates. They do not establish MEDIUM answer onset at Val's
  occupied context,** and no estimate below is derived from them. The estimates use the
  gate's own thresholds.
- **What those figures do not show:**
  - `tg128` generates from an empty context. The rate with about 6,000 tokens occupied is
    not published.
  - Nothing is published about `llama-server` reusing a cached prefix for this model
    across turns whose endings differ. On MLX, this model's sliding-window layers made
    cached prefixes hard to reuse.
  - Time to a first answer sentence at MEDIUM effort is not published.
- **Figures I am not using:** NVIDIA's "up to 256 tokens per second" states no runtime or
  settings, and the vLLM paper measures several simultaneous requests.

### 2.2 How MEDIUM and Val's sampling would be applied

- **MEDIUM:** llama.cpp sets reasoning effort through the chat template
  (`chat_template_kwargs: {"reasoning_effort": "medium"}`), per request.
- **Sampling,** sent per request, the values production runs with (observed at the engine
  on 29 September): temperature 0.8, top-p 0.8, top-k 40, min-p 0.05, repeat penalty 1.1.
- **Verified at execution, not from accepted parameters:**
  - the server's own reported generation settings for each request;
  - the rendered prompt's "Reasoning: medium" line.
- **Two implementation differences to requalify:**
  - the repeat penalty's window: llama.cpp's default look-back is 64 tokens, and the MLX
    engine's is 20;
  - llama.cpp's template handling against the pinned template.

### 2.3 What moves, and how Val Core keeps authority

**Cognition alone would move:** the generation of one answer from one request.

| stays on this Mac | would run on the dedicated machine |
|---|---|
| Val Core: request assembly, persona, record state, the seal, routing, budget, preflight, persistence, delivery | `llama-server` and the model weights |
| PostgreSQL, the authoritative store, and backups | nothing durable |
| microphone, recognition (Whisper), the voice (Qwen3-TTS), the desktop, the avatar | |
| every tool, credential and action path (none exists in Layer 0) | |

- **Request authority:** Core assembles each request whole and sends it. The machine
  receives text and returns text.
- **Record authority:** the machine stores nothing.
  - No prompt logging and no slot saving to disk.
  - Its only copy of a conversation is the prompt cache in memory, gone at restart.
- **Answer authority:** the stream returns to Core's sink, as now. Core settles, records
  and delivers it. Hidden reasoning is discarded at the adapter, as now.
- **Action authority:** the machine has no tools and no route to anything but this Mac.
- **Failure and fallback — a choice, not a free benefit.** The two cannot both be had:

| fallback policy | memory on this Mac | what a failure costs |
|---|---|---|
| keep GPT-OSS loaded here | its about 12 GB stays occupied: **no memory is freed** for the avatar or anything else | the next turn is answered at today's speed |
| unload it here | about 12 GB freed | the first fallback turn waits for a cold load and a cold prime: about 9 s + about 7 s (**measured** here), then today's speed |
| no local fallback | about 12 GB freed | Voice stops honestly and degrades to text until the machine returns |

  - Which policy is right depends on the avatar's measured demand, which is unknown.
  - Every fallback is recorded.

**Transport:** one wired link, encrypted, accepting this Mac's address only. The machine
has no internet route in operation.

**This is the part that requires his seal amendment.** A Voice conversation's text would
cross a cable to a second machine in the house. It is not authorised, and nothing in the
measurement below depends on it.

## 3. The smallest useful pre-purchase measurement

### 3.1 Can it be answered without spending?

| source | what it answers | cost |
|---|---|---|
| llama.cpp's published results (§2.1) | raw generation and prompt-processing rates on this card and runtime | $0, already in hand |
| **a borrowed machine** with an RTX 5090, or an RTX 4090 as a lower bound (published 225 tokens/s) | everything in §3.3 | $0 |
| an hourly rental of an RTX 5090 | everything in §3.3 | **ceiling $5** |

- **The published results alone are not enough.** They leave open the rate at Val's
  occupied context, warm-prefix reuse, and time to the first answer sentence at MEDIUM.
- **If he or someone he trusts has such a machine,** that answers it at no cost, and I
  recommend it first.
- **Otherwise the rental.** Published prices on 27 September 2026: $0.35–0.99 per GPU-hour
  (median $0.67 across 16 providers).

### 3.2 What may leave this Mac for it

**Public or synthetic material only.**

- A system message of public-domain text, about 5,050 tokens: the persona's size, none of
  its words.
- A synthetic block of generic JSON, about 900 tokens, in the new turn: the record state's
  size, none of its fields.
- Twelve ordinary questions written for the test (for example "Explain the difference
  between suspense and surprise in a scene").
- **Never:** the persona, house records, conversations, credentials, Voice audio, or any
  word of his.

### 3.3 What is measured

One active request at a time, `--parallel 1`, window 32,768.

1. **Memory:** GPU memory after load and at peak, with the window configured at 32,768.
   The **occupied** context is reported per request (expected about 5,900–6,200 tokens).
2. **Cold prefill:** a fresh server and the whole prompt. Tokens evaluated and seconds,
   from the server's own timings.
3. **Warm-prefix reuse,** measured three ways:
   - a new conversation after the static prefix has been processed once;
   - the next turn of the same conversation;
   - a turn after a *different* conversation has used the slot.
   For each: tokens reused, tokens re-evaluated, seconds.
4. **Reasoning generation rate:** tokens per second while the model reasons at MEDIUM, at
   that occupied context.
   - The model reasons as long as it naturally does on each question.
   - No reasoning length is forced, and none is presented as conversational behaviour.
5. **Time to the first final-answer segment:** request sent → the first complete answer
   sentence, per question, with that question's own reasoning-token count.
6. **Settings as executed:** the rendered effort line, and the server's reported sampling.

About 40 requests. Under one hour of GPU time, plus the 12 GB download.

### 3.4 Pass, fail and stopping (fixed now)

**Pass requires all of:**

| measure | threshold |
|---|---|
| reasoning generation rate at about 6,000 tokens occupied | ≥ 200 tokens/s |
| cold prefill of the whole prompt | ≤ 1.2 s |
| warm turn: tokens re-evaluated | no more than the new suffix plus 64 |
| warm turn: prefill time | ≤ 0.3 s |
| GPU memory at peak, 32,768 window | ≤ 24 GB |
| effort and sampling as executed | as requested |

- **Reported, not a pass condition:** time to the first answer segment, as a distribution.
  The test's questions are not his conversation, so the *rate* is what transfers.
- **Warm-prefix reuse is mandatory.** If it fails, **the gate has not passed**, whatever
  the other measures show.
- **A separately defined outcome, "no reuse",** fixed now so it cannot be fitted afterwards:
  - **It applies when** warm reuse fails and every other threshold is met.
  - **Its own condition:** cold prefill of the whole prompt in ≤ 1.0 s on every measured
    turn.
  - **It is not a pass.** It is reported as a different configuration with a slower
    estimate (§4.1), and whether to continue on it is his decision.
- **Stopping rule:**
  - stop at the first of $5 spent, 3 hours elapsed, or the 40 requests complete;
  - stop at once if the runtime cannot load the file or honour MEDIUM;
  - the instance and its storage are deleted at the end.
- **No further paid work** follows without his decision.

## 4. What passing would imply for speech end → first audio

**Estimate, at the gate's thresholds.**

- The Mac-side parts are **measured** medians (28 September, through the real desktop).
- The cognition parts apply the gate's pass thresholds to his real turns' reasoning
  (**measured**, production: median 269 tokens, 90th percentile 440). They do not use the
  published empty-context rates.
- A faster result would need measured rates above the thresholds. None is assumed.

| part | where | today, measured median | if the gate passes, estimate |
|---|---|---|---|
| endpoint (silence rule) | Mac | 0.47 s | 0.47 s |
| recognition's final decode and the confirmation window | Mac | 0.26 s | 0.26 s |
| Core: assembly, preflight, dispatch | Mac | 0.06 s | 0.06 s |
| transport, wired | link | none | about 0.01 s |
| prefill, warm | cognition | 1.49 s | ≤ 0.3 s |
| hidden reasoning, 269 tokens at ≥ 200 tokens/s | cognition | 3.04 s | ≤ 1.35 s |
| first answer segment | cognition | 0.21 s | about 0.1 s |
| speech synthesis to first audio | Mac | 0.78 s | 0.78 s |
| playback start | Mac | 0.05 s | 0.05 s |
| **speech end → first audio** | | **6.3 s** | **about 3.4 s at the thresholds** |

- **Slower turns** (reasoning at his 90th percentile, 440 tokens, ≤ 2.2 s): about 4.2 s.
- **Not included, because unmeasured:** whether synthesis on this Mac speeds up once
  cognition no longer shares its GPU.
- **This is more than three seconds. It is not his approximately one-second goal.**

### 4.1 The "no reuse" outcome, recalculated

If warm reuse fails and the separately defined outcome of §3.4 holds, every turn pays a
cold prefill of ≤ 1.0 s in place of ≤ 0.3 s:

- **speech end → first audio: about 4.1 s** at the thresholds;
- slower turns about 4.9 s.

### 4.2 What would still be needed to approach one second

These are kept out of the estimate above. Each is a separate decision.

| further change | possible saving | status |
|---|---|---|
| faster first audio: synthesis on the GPU machine, or a faster streaming path | about 0.5 s | **unproven.** Published first-audio figures of 0.10–0.15 s are third-party implementations on an RTX 4090. The voice would need his ear, and its audio would also cross the link |
| a shorter turn boundary: no confirmation window, an earlier endpoint | about 0.3–0.5 s | **unproven on his speech.** She would sometimes start answering while he is still mid-thought, then stop |
| less hidden reasoning | up to about 1 s | **closed or unproven.** LOW and the cap are closed. The model's repository also holds a speculative-decoding companion (`eagle3-gpt-oss-20b`); whether llama.cpp uses it for this model, and what it gains, is unverified |

- **Even if the first two both worked,** the estimate is about 2.4–2.6 s at the gate's
  thresholds.
- MEDIUM's reasoning alone is about 1 s at the published rate. **Approximately one second
  is not reachable by any change identified here while MEDIUM's reasoning is kept.**

## 5. Avatar headroom

- Moving cognition off this Mac would free about 12 GB and the generation load.
- **Whether what remains is enough for the real-time avatar is unverified.** Recognition
  and synthesis stay on this Mac's GPU, and the renderer's demand is unknown.
- The prototype's concurrent measurement (`01-architecture.md` §8.2) is still required.
  This proposal does not replace it.

## 6. Cost

**Every hardware price here is provisional.** No purchasable configuration and complete
price, with tax, delivery and return terms, has been verified. That verification comes
before any purchase decision.

| item | cost | basis |
|---|---|---|
| **complete machine (provisional):** ZOTAC MEK desktop (RTX 5090 32 GB, Ryzen 7 9800X3D, 32 GB DDR5, 2 TB NVMe, 1,200 W, Windows 11 Pro), Amazon listing B0H867K574 | **$4,499.99** before tax | **published**, as reported in search results on 29 September 2026. I could not load the live listing: **to be confirmed before any purchase** |
| comparable complete RTX 5090 desktops | about $4,400–4,700; vendor-configured systems $8,500–9,200 (Corsair, listed) | published |
| the graphics card alone | about $4,400–4,830 street | published, 23 August 2026 |
| Ethernet cable or adapter; optional battery backup | about $30; about $200 | estimate |
| electricity | under load about 700–900 W at the wall (published, for training load); idle draw not sourced. Voice draws in short bursts | published and unknown |
| the pre-purchase measurement | $0 borrowed, or a ceiling of $5 rented | §3 |

**Integration work: about 5–7 working days (estimate).**

- **The llama.cpp adapter.** It exists (18 September), but today it:
  - refuses a graded reasoning effort;
  - sends no min-p or repeat penalty;
  - is ruled loopback-only and candidate-only;
  - enforces no output schema. That matters only if typed conversation's consequential
    path ever moved; Voice conversations are sealed and have none.
- **The encrypted link,** and the machine's firewall.
- **A supervisor:** start, health, and the fallback to this Mac.
- **A registry entry,** NOT_ADMITTED until he rules.
- **Requalification of MEDIUM on the new runtime:**
  - the frozen Stage A corpus;
  - the decisive cases at five samples (nonexistent work, unavailable capability,
    instruction boundary, corrections);
  - one desktop comparison against this Mac.

**Ongoing requirements:**

- an always-on second machine: noise, heat, power;
- operating-system, driver and runtime updates, each a pinned and re-verified change;
- disk encryption, and no prompt logs;
- monitoring;
- a machine that is not macOS to maintain.

## 7. The decisions needed from him

**Now:**

1. **Whether to run the pre-purchase measurement of §3,** and how:
   - on a borrowed machine ($0); or
   - on an hourly rental, **ceiling $5**, public and synthetic material only.

**Only if it passes, and each separately:**

2. **The purchase:** provisionally $4,499.99 before tax; a purchasable configuration and
   its complete price verified first.
3. **The seal amendment:** whether a Voice conversation's text may cross an encrypted cable
   to a second machine in the house. Without it the machine cannot serve Voice.
4. **The provider ruling:** the llama.cpp provider is loopback-only and candidate-only
   today.
5. **Requalification of MEDIUM on the new runtime,** before any spoken use.

**Not decided by any of these:** that about three seconds completes Voice. The changes of
§4.2 remain separate, and his one-second goal remains unmet by anything measured.

## 8. Sources

- [llama.cpp gpt-oss guide and published benchmarks, discussion #15396](https://github.com/ggml-org/llama.cpp/discussions/15396)
- [ggml-org/gpt-oss-20b-GGUF](https://huggingface.co/ggml-org/gpt-oss-20b-GGUF)
- [ZOTAC MEK RTX 5090 desktop, Amazon listing](https://www.amazon.com/ZOTAC-Gaming-Desktop-9800X3D-NVIDIA/dp/B0H867K574)
- [Corsair RTX 5090 desktops](https://www.corsair.com/us/en/c/gaming-computers/nvidia/rtx-5090)
- [AI workstation build 2026, card prices and power (Petronella, 23 August 2026)](https://petronellatech.com/blog/how-to-build-custom-ai-workstation-2026/)
- [RTX 5090 cloud pricing, 16 providers (getdeploying.com)](https://getdeploying.com/gpus/nvidia-rtx-5090)
- [RTX 5090 rental, Vast.ai](https://vast.ai/pricing/gpu/RTX-5090)
- [RTX 5090 rental, RunPod](https://www.runpod.io/gpu-models/rtx-5090)
- [NVIDIA: OpenAI's open models on RTX](https://blogs.nvidia.com/blog/rtx-ai-garage-openai-oss) (not used for estimates)
- [Private LLM inference on consumer Blackwell GPUs, arXiv 2601.09527](https://arxiv.org/html/2601.09527v1) (not used for estimates)
- [Qwen3-TTS technical report, arXiv 2601.15621](https://arxiv.org/pdf/2601.15621)
