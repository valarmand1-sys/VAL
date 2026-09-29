# EAGLE3 speculative decoding for GPT-OSS-20B on this Mac — feasibility and one small proof

Owner order of 29 September 2026 ("resolve one specific supported same-model acceleration
opportunity").

**Isolated. NOT RULED, NOT DEPLOYED. Production is unchanged and pinned.** Everything is
local, at $0.

This proof decides whether further qualification is justified. It admits nothing and
says nothing about audio.

## 1. Scope of the earlier closure

The speculative-decoding closure of 29 September (`2026-09-29-fastest-config/RESULT.md` §2)
applies to **the installed MLX engine** and its cache restrictions. It does not apply to
other runtimes. llama.cpp is a different runtime with its own EAGLE3 implementation.

## 2. Feasibility (documentation, implementation, known issues; 16:12–16:20)

| check | finding |
|---|---|
| the pairing is documented | llama.cpp's `docs/speculative.md` lists `RedHatAI/gpt-oss-20b-speculator.eagle3` as a supported EAGLE3 draft (`--spec-type draft-eagle3`) |
| target and draft artifacts match | `ggml-org/gpt-oss-20b-GGUF` @ `ef9b12f2…` holds both, converted together by llama.cpp's own tool: draft source `RedHatAI/gpt-oss-20b-speculator.eagle3` @ `c2825cb4…`, target `openai/gpt-oss-20b` @ `6cee5e81…`. The draft reads target layers 2, 12 and 21 of 24 and uses the target's tokenizer |
| a supported build exists here | the official build already installed (Homebrew llama.cpp 0.4.1, build 10964, commit `b29c606e2`, Metal) lists `draft-eagle3`. EAGLE3 was merged upstream on 12 June 2026 (PR #18039). No build is needed |
| Metal support | **not established by any document.** The PR's tests were on CUDA. One open issue reports a different speculative method (MTP) as a net loss on Metal, on an M1 Max. Only a run can settle it |
| sliding-window cache | llama.cpp treats this model as sliding-window (`openai-moe`). The build offers `--swa-full` (a full-size cache) and context checkpoints. The proof uses `--swa-full` in both conditions, so a cached prefix can be reused and rejected draft tokens rolled back |
| static-prefix reuse | the server reuses the slot's common prefix with the previous request. Measured in the proof, not assumed |
| MEDIUM, sampling, streaming | effort through the chat template; temperature, top-p, top-k, min-p and repeat penalty per request; streamed reasoning and answer separately |
| target sampling under drafting | llama.cpp accepts a drafted token only when it equals the token the target's own sampler draws at that position (`common_sampler_sample_and_accept_n`, read in a local source tree of a related version). So the answer is sampled by the target with Val's settings. Observed in the proof through the server's acceptance counts, not assumed |
| memory | target 12.1 GB + draft 1.7 GB + cache: about 15–17 GB (estimate). With recognition (0.5 GB) and synthesis (2.9 GB): about 19–21 GB. Production's model is not loaded at present; were it loaded during the proof, about 31–33 GB |

**Known reasons to expect little:**

- **The PR's own result for the larger sibling:** GPT-OSS-120B gained 0.83–1.08×, sometimes
  a loss. The discussion attributes it to the mixture of experts: verifying several tokens
  at once activates more experts.
- **The published acceptance figures are at greedy sampling** (1.88–2.43 accepted of 3).
  Val samples at temperature 0.8.
- **The draft was trained on chat data.** Val's wait is mostly the hidden reasoning
  channel.

**Verdict:** no concrete incompatibility, and no implementation work is needed. The checks
that documents can settle are settled. The rest needs the run. The proof proceeds.

## 3. Registration (fixed before the first measured request)

### 3.1 Configuration, identical in both conditions except the draft

- **Build:** `/opt/homebrew/bin/llama-server`, llama.cpp 0.4.1 (build 10964), on the
  loopback interface, port 8099, with a throwaway key.
- **Target:** `gpt-oss-20b-MXFP4.gguf`, sha256 `27cd6c43…5901`.
- **Draft (on only):** `eagle3-gpt-oss-20b-BF16.gguf`, sha256 `b82e890a…65aa`. BF16 is the
  documented conversion output. The Q8 file is not tried.
- **Flags:** `--ctx-size 32768 --parallel 1 --jinja -ngl 999 --swa-full -b 2048 -ub 2048`,
  MEDIUM through `--chat-template-kwargs`.
  - On adds `-md … --spec-type draft-eagle3 -ngld 999`.
  - The draft's own settings are the runtime's defaults. No acceptance setting is chosen
    to flatter it.
- **Request:** through Val Core.
  - The persona whole; production's request construction (`envelope_in_system` is not
    used); Core's output allowance.
  - Spoken, sealed conversations in a scratch store (`val_eagle_test`).
  - Sampling per request: temperature 0.8, top-p 0.8, top-k 40, min-p 0.05, repeat penalty
    1.1.
- **The adapter:** the house's llama.cpp adapter, loopback. For this proof only, the harness
  adds what that adapter does not transmit (the graded effort, min-p, the repeat penalty)
  in the one function whose body the preflight counts and the call sends. No package code
  changes.
- **Prefix preparation:** before every measured request, in both conditions, one request of
  the persona and a short filler, one token generated.
- **Residency:** nothing else loaded in LM Studio. Production's service is running, idle
  and untouched. The proof does not start if production Voice has been used since the last
  check, and it unloads nothing of production's.

### 3.2 The 16 measured requests

Seven fixed cases, each once per condition (14), and one cancellation check per condition
(2).

| block | cases |
|---|---|
| A | O1 an ordinary substantive question; O2 a follow-up on earlier discussion; C6 the nonexistent contract review; C1 the correction (barn, 6 pm, no plus-ones) |
| B | O3 a creative request; C5 the second act that is not in the record; C2 the withdrawn fact; then the cancellation check |

**Order:** off A, on A, on B, off B. Each block is a fresh server.

### 3.3 Measured

- dispatch → first streamed chunk (prefill), → first visible answer text, → the first
  complete speech-safe segment;
- the server's own lines per request: prompt tokens evaluated and reused, generation rate,
  drafted and accepted tokens;
- reasoning duration and tokens;
- the server's memory footprint and swap growth per block;
- stream integrity: the streamed text against the settled answer, and no reasoning or
  channel markup in the answer;
- cancellation: a stream closed mid-answer, then the time for the next request to return.

### 3.4 Stopping and the decision rule

**Stop at once if:**

- the server fails to load the pairing, or exits;
- a request is unanswered;
- an answer's stream is not intact;
- the on condition reports no drafting at all;
- swap grows by more than 2 GB in a block;
- 45 minutes of measurement have passed.

**Stop after block "on A"** if its median dispatch → first segment is not at least 0.5 s
better than "off A". Blocks B are then not run.

**Material improvement,** the only outcome that justifies further qualification: over the
seven cases, the median of the paired differences (on − off) in dispatch → first
speech-safe segment is **≤ −1.0 s**, with:

- no case's stream damaged;
- cancellation working;
- no critical answer failure in the on condition that the off condition does not show.
  Every answer is read. One sample per case cannot qualify anything.

**Compared afterwards with the existing Mac evidence** (MLX, GPT-OSS MEDIUM, production
construction, 29 September screen): first speech-safe segment median 5.9 s overall and 6.1
s on first samples. Any lost cache benefit is counted.

**If it fails or the gain is insufficient,** the path is closed at once. No other draft, no
other settings.
