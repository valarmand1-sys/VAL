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

## 4. Result (16:42–16:45, 8 measured requests; `proof-off-A-NO-ONSET-harness-defect.json`, `proof-on-A.json`)

**The documented pairing loads and runs on this Mac through Metal, and it is about three
times slower than the same target without the draft. The path is closed.**

### 4.1 Conduct

- **Blocks run:** "off A" and "on A", four cases each. Blocks B were not run, by the
  registered stopping rule.
- **A harness defect, counted:** the house's llama.cpp adapter emits no timing marks, so
  the first block recorded no onset times. Its four requests count against the sixteen.
  The harness then timed onset from the moment Core is called. The comparison below
  rests on the server's own timing lines, which both blocks have.
- **Both blocks:**
  - every request answered through Val Core and routed to the experiment configuration;
  - every streamed answer identical to the settled answer;
  - no reasoning or channel markup in any answer;
  - swap unchanged (1,100 MB before and after);
  - nothing of production's was unloaded or touched.
- **Build as reported by the server:** `b10964-b29c606e2`, window 32,768.
- **Artifacts:** target sha256 `27cd6c43…5901`, draft sha256 `b82e890a…65aa`.

### 4.2 The server's own figures, case by case

| case | prefill (tokens evaluated) off / on | generation rate off / on | draft acceptance (accepted of drafted) | generation time off / on |
|---|---|---|---|---|
| O1 substantive | 1.22 s / 1.63 s (851) | 59.9 / 21.6 tokens/s | 10.9% (100 of 915) | 6.2 s / 18.8 s |
| O2 follow-up | 1.30 s / 1.33 s (910) | 60.1 / 22.6 | 13.4% (95 of 711) | 8.4 s / 14.7 s |
| C6 nonexistent work | 1.88 s / 1.93 s (1,334) | 59.9 / 20.5 | 9.3% (85 of 918) | 6.0 s / 19.1 s |
| C1 correction | 1.49 s / 1.52 s (1,045) | 60.1 / 23.4 | 14.7% (148 of 1,005) | 5.1 s / 20.6 s |

- **With the draft on,** Core call → first visible answer text: 7.0, 12.4, 19.6 and 18.7 s.
  First speech-safe segment: 7.5, 13.5, 20.1 and 19.6 s (median 16.5 s).
- **Why it loses:**
  - about nine in ten drafted tokens are rejected (mean accepted run 1.3–1.4 tokens);
  - each round still pays the draft and a multi-token verification on a
    mixture-of-experts target;
  - generation falls from 60 to about 22 tokens per second.
- **Prefix reuse works on this runtime,** in both conditions: with `--swa-full`, the 5,048
  tokens of the prepared persona prefix were reused on every request, and only the new
  851–1,334 tokens were evaluated.
- **Memory:** server footprint 8.8 GB reported with the draft on (the mapped weights are
  not all counted by that figure). No swap growth.

### 4.3 What was not established

- **Onset without the draft on llama.cpp** was not timed (the harness defect).
  Reconstructed from the server's figures, it is prefill plus reasoning at 60 tokens per
  second, the same rates MLX gives.
- **Effective per-request sampling** was not verified from the server. Only its defaults
  were read (top-p 0.95, repeat penalty 1.0, look-back 64). The harness sent Val's values
  in each request.
- **Cancellation** was not tested: it belonged to blocks B.
- **Answer quality:** one sample per case qualifies nothing. For the record, both
  conditions declined the nonexistent contract review and kept the correction. The
  draft-on invitation added the unsupported "Aldbury".

## 5. Against the existing Mac evidence

| configuration on this Mac, GPT-OSS MEDIUM | generation | prefill | first speech-safe text |
|---|---|---|---|
| MLX in LM Studio (production's runtime), measured 28–29 September | 62–65 tokens/s | about 650–750 tokens/s | 5.9 s median (screen); 3.3–4.5 s on shorter-reasoning cases |
| llama.cpp Metal, draft off | 60 tokens/s | about 700 tokens/s | not timed; the same rates |
| llama.cpp Metal, EAGLE3 on | 20–23 tokens/s | about 700 tokens/s | 16.5 s median |

- **llama.cpp on this Mac is no faster than MLX** for this model.
- **EAGLE3 makes it far slower.** No cache benefit was lost. The loss is entirely in
  generation.

## 6. Closure

**Closed on performance, by the registered rule.** No other draft file, draft setting or
runtime is tried.

- The closure is of **this pairing on this Mac through Metal at Val's settings**. It says
  nothing about EAGLE3 on other hardware.
- **Kept pending his ruling on removal:** the two downloaded files (13.8 GB,
  `~/.val-models/llamacpp-exp/`).
- **Unchanged:** no package code; production, its model definition and LM Studio's state.
- The server's logs held scratch-fixture prompts only and stay in the session's scratch
  directory.
