# Qwen3.5-9B (4-bit MLX) — acceptance test result: **PASS**

**Case A passed. Case C passed. Machine fit passed.** The fifth candidate is the
first to pass both visual cases, and it is admitted as Val's local
visual-perception provider for **image and video perception only**.

Nothing was tuned to get here. The generation configuration was frozen and
committed at `f0c81dd` **before either case ran**; no prompt, criterion, fixture,
sampling setting or quantization was touched; no case was re-run; no exam repair
was proposed or performed. Each case ran once.

One judgement call is recorded in full below, under Case C. It is the only place
in this run where the answer did not use the criterion's own words.

---

## Artifact and runtime

Repository `lmstudio-community/Qwen3.5-9B-MLX-4bit`, immutable revision
`b455506b0f574c74616dbcd56879bde38fafcff3`. Base model `Qwen/Qwen3.5-9B`.
**Every hashed file matches the source exactly.**

| File | Bytes | SHA-256 |
|---|---|---|
| `model-00001-of-00002.safetensors` | 5,349,771,292 | `973cc1efdedb4d327993fb9c27865f0bcfd9015897d5f0ca9ffb6cda6a0768e5` |
| `model-00002-of-00002.safetensors` | 600,449,850 | `597dae0ed72b60acc07382e8ea0cdb9509c54128e07b0eaa9cf4996373d5ca7d` |
| `tokenizer.json` | 19,989,325 | `06b9509352d2af50381ab2247e083b80d32d5c0aba91c272ca9ff729b6a0e523` |

Plus `config.json`, `chat_template.jinja`, `preprocessor_config.json`,
**`video_preprocessor_config.json`**, `processor_config.json`,
`model.safetensors.index.json`, `tokenizer_config.json`, `vocab.json`,
`README.md` — all small and non-LFS. Weight total 5,950,221,142 bytes;
**installed footprint 5.57 GB**; the isolated runtime environment adds 596 MB.

`model_type: qwen3_5`, quantization **4-bit, group size 64, mode affine**. The
exact 4-bit MLX artifact at the pinned revision — **no 8-bit, no bf16, no other
Qwen3.5 size, no other publisher, no backup quantization was downloaded.**

Vision configuration: `temporal_patch_size` 2, `spatial_merge_size` 2,
`patch_size` 16, `image_token_id` 248056, `video_token_id` 248057, mrope
sections `[11, 11, 10]`. Text context `max_position_embeddings` 262,144.

**Runtime, unchanged and not updated.** mlx-vlm **0.7.2**, mlx 0.32.2,
transformers 5.17.0, opencv-python 5.0.0.93, numpy 2.5.3, Python 3.12.13, in the
existing isolated environment at `~/.val-runtimes/mlx-vlm-venv`. **No bounded
runtime update was taken and none was needed.** Val's production Python
environment and its pinned dependencies were not touched.

**Generation configuration:** frozen and committed before the cases in
[`GENERATION_CONFIGURATION.md`](GENERATION_CONFIGURATION.md). Library defaults —
max 2,048 output tokens, temperature 0.0 (greedy), top-p 1.0, top-k 0, min-p 0.0,
**no repetition penalty**, stop at the model's own eos tokens
`[248044, 248046]`. The runner read these back from the runtime and recorded
them, so the record shows what governed rather than what was intended:
`results/qwen35_result.json` → `generation_settings_in_force`, with
`kwargs_passed_to_generate: []`.

Model load **0.99 s**.

---

## Case A — image: **PASS**

Source: the genuine Track C attachment (`01a0c109-8993-7842-b309-73b169e4a27c`),
digest verified `7fc13a7c5072b69acc119d20a16beb6523dc21aa4ba6a4ef950c7ba748c12db0`
before inference. Frozen prompt unchanged. Criterion as repaired and frozen in
`../2026-09-22-qwen2_5-vl/EXAM_REPAIR_CASE_A.md`. Latency **28.1 s**.

> **People Present:** Three people are present: one adult male, one adult female,
> and one child.
>
> **Child's Clothing:** The child is wearing a black top hat with a white band.
> The child is wearing **a black cape with a red lining**. The child is wearing a
> black jacket or coat with a high collar.
>
> **Actions:** The adult male is kneeling and hugging the child from the left
> side. The adult female is kneeling and hugging the child from the right side.
> The child is being hugged by both adults and is leaning into them with eyes
> closed. …
>
> **Setting:** The scene takes place in a living room. There is a beige sofa with
> multiple pillows (beige, pink, and gray) behind the people. A wooden coffee
> table is in the foreground with books on it. To the left, there is a wooden side
> table with books and a vase of flowers. To the right, there is another wooden
> side table with a lamp and a small potted plant. In the background, there is a
> window with curtains, a floor lamp, and a bookshelf. A framed picture hangs on
> the wall to the far left.

| Repaired criterion | Result |
|---|---|
| three people are present | met |
| the child wears a top hat **and a cape** | **met** — both named outright |
| the people are embracing/hugging | met |
| indoor living-room or home setting | met |
| no material central person, object or action is invented | met |

**On the cape, which defeated MiniCPM-o, Qwen2.5-VL and Qwen3-VL.** This answer
does not say "coat" in place of a cape. It says "a black cape with a red lining",
and closes by referring to "the child's costume (top hat and cape)". The cape is
actually established, in the criterion's own word. The additional hedged "black
jacket or coat with a high collar" is a further garment claim, not a substitute
for the cape; judged as detail rather than as a material central invention.

**Invention check, against the image itself.** Every scene element the answer
names is present: the beige sofa; beige, pink and grey pillows; the coffee table
with books; the left cabinet with books and white flowers; the right table with
lamp and small potted plant; the window with curtains; the floor lamp; the
bookshelf; the framed picture at far left; the warm light; the 3D-animated
style. Nothing central is invented. The one loose description is the woman, who
is crouching and leaning rather than strictly kneeling — a posture detail, not a
material misstatement of the central action.

**No repetition pathology.** The answer ends cleanly, well inside the 2,048-token
budget, under the same untuned settings that sent Qwen3-VL into a loop of
invented moles and scars. Colour, lining, fabric and style terms appear in the
answer but were **not** required and were **not** used as pass criteria, per §10.

## Case C — video: **PASS**

Source: the repaired fixture frozen at `53705f2`, digest verified
`6925c05c4ea8d164f172e0d16de775736ffccd0d62dd0c649fb9a354f680a169` before
inference. Frozen prompt unchanged. Latency **9.7 s**.

> Initially, a red square is positioned on the left side of the screen. As the
> video progresses, the red square moves horizontally to the right side of the
> screen. Following this, a blue circle appears below the red square on the right
> side of the screen. The video concludes with the red square and blue circle in
> their respective positions on the right side of the screen.

| Frozen criterion | Result |
|---|---|
| one red square starts on the left | met |
| **that same square moves through the centre** | **met — see below; the word "centre" is not used** |
| that same square ends on the right | met |
| the blue circle appears afterward | met |
| the circle is beneath the square | met |

No fail condition is triggered: the movement is not lost ("the red square moves
horizontally"), one square is not read as several — the definite article carries
the identity throughout — the sequence is not reversed, the circle is not placed
before or during the movement ("Following this"), the spatial relation is right
("below the red square"), and nothing is invented.

### The one judgement call in this run, stated plainly

**The answer never says "centre".** What it says is that the square starts on the
left and, as the video progresses, *moves horizontally* to the right side.

I judged that this establishes criterion 2, and the reasoning is this: a
continuous horizontal traverse from a named left start to a named right end has
the centre on its path — the centre is entailed by the account, not absent from
it. That is a different situation from Case A's "coat", which is an affirmative
claim about a *different* garment and therefore cannot establish a cape. Here
there is no competing claim; the account is the correct one at coarser
resolution.

Recorded so it can be overruled on reading: had the answer said only that the
square *is* on the left and then *is* on the right, with no movement verb, I
would have failed it for losing the cross-frame movement, as Qwen2.5-VL and
Qwen3-Omni were failed. The movement verb, qualified as horizontal, is what
carries the point.

### The video actually reached the model, and matched the frozen record

| | |
|---|---|
| Source | 9.0 s, 30 fps, 270 frames, 640×480 |
| Sampling | `mlx_vlm.utils.load_video` defaults — nothing passed |
| Sampled rate | 2.0 fps |
| Frames delivered | 18 |
| Source indices | 0, 16, 32, 47, 63, 79, 95, 111, 127, 142, 158, 174, 190, 206, 222, 237, 253, 269 |
| Timestamps | 0.000 … 8.967 s |
| Array | (18, 3, 480, 640) |
| Temporal preprocessing | `temporal_patch_size` 2, `spatial_merge_size` 2, mrope `[11, 11, 10]` |
| API used | `apply_chat_template(..., video=<path>)` then `generate(..., video=[<path>])` |
| Prompt construction | `<\|vision_start\|><\|video_pad\|><\|vision_end\|>` followed by the frozen prompt |

**Compared against the Part 1 frozen sampling record: identical.** Same sampled
rate, same frame count, the same 18 source indices, the same 18 timestamps.
Nothing was changed to make them agree and nothing needed to be, so §12's STOP
condition was not reached. The delivered frames are the ones the owner personally
approved on the contact sheet: one square, ten intermediate positions, left →
centre → right, a right-side hold, and the circle appearing afterward beneath it.

---

## Observation discipline

**Plain prose on both cases.** The chat template opens an empty `<think>` block
and closes it immediately (`<think>\n\n</think>`) before the assistant turn, so
no reasoning content is produced at all. No `<think>` content, no reasoning
markup, no reasoning mixed into the observation. The grounded observation is
usable by Core as evidence exactly as returned, with nothing to strip.

---

## Machine fit: **PASS**

Apple M4 Pro, 48 GB unified memory, confirmed from the machine. Memory sampled
every 5 s across load, Case A and Case C — 30 samples,
`results/machine_fit.jsonl`, script `results/machine_fit_sample.sh`.

| | Before load | Worst observed | After |
|---|---|---|---|
| free + inactive + purgeable | 25.43 GB | **18.31 GB** | 28.86 GB |
| wired | 3.25 GB | **13.10 GB** | 2.97 GB |
| compressed | 1.67 GB | 1.67 GB | 1.67 GB |
| system free percentage | 90 % | **70 %** | 90 % |
| swap used | 235.38 MB | 235.38 MB | 235.38 MB |

| Machine-fit requirement | Result |
|---|---|
| model loads normally | yes — 0.99 s |
| both cases complete without OOM | yes |
| no process killed for memory | yes — no jetsam/memorystatus events, no new crash reports |
| no sustained critical/red memory pressure | yes — never below 70 % free; nominal throughout |
| **≤ 2 GB new sustained swap attributable to Qwen3.5** | yes — **0 bytes**; swap used was 235.38 MB before, during and after, byte-identical in all 30 samples |
| macOS and Val retain operating headroom | yes — worst case 18.31 GB available, 99 GB disk free |
| visual resources releasable after perception | yes — wired returned from 13.10 GB to 2.97 GB on process exit |
| **GPT-OSS can subsequently wake/reload and operate** | yes — see below |
| repeated ordinary use needs no manual memory intervention | yes — nothing was unloaded, purged or intervened in by hand at any point |

**GPT-OSS resume, proved through the production supervisor.** Immediately after
the visual run, `LMStudioRuntime.ensure_ready` was called for
`gpt-oss-20b-mxfp4-mlx-lmstudio-partner` — the same code path Val uses, not a
manual `lms` command:

```
server_found_running: true      model_found_loaded: false
server_started:       false     model_loaded:       true
requested_context_tokens: 32768  loaded_context_tokens: 32768   (10.74 s)
```

It loaded at the registered 32,768-token window, not a smaller just-in-time
default. With GPT-OSS resident afterwards the machine reports 88 % free and swap
still unchanged at 235.38 MB. **Sequential residency works as the architecture
intends**; the two models were never required to be resident together.

---

## Whole-qualification requirements

| Requirement | Status |
|---|---|
| Case A passes | **yes** |
| Case C passes | **yes** |
| the correct image reached Qwen3.5 | yes — digest verified before inference |
| the correct repaired video reached Qwen3.5 | yes — digest verified before inference |
| temporal delivery remains valid | yes — identical to the frozen record |
| output grounded and usable | yes |
| reasoning not inseparably mixed into observation | yes — no reasoning produced |
| all inference local | yes — MLX on this Mac, local files, no network call |
| provider inference cost $0 | yes |
| no cloud cognition or perception provider contacted | yes — zero provider calls in the interval |
| no silent fallback | yes |
| runtime stable | yes — no crash, no warning, both cases completed |
| **machine fit** | **PASS** |

**Overall: PASS.** Latency: Case A 28.1 s, Case C 9.7 s, model load 0.99 s,
GPT-OSS reload 10.7 s.

---

## What this settles, and what it does not

Admitted by this run: **image perception** and **video perception**, at this
artifact, this quantization, this runtime and this generation configuration.

**Not** established, and not claimed: audio of any kind; speech generation;
ordinary final-response cognition. Qwen3.5 is a perception provider. Val Core
remains Val, GPT-OSS remains the cognition provider, and Qwen3.5 owns no
identity, memory, conversation state, policy, permission, routing authority or
durable record.

The failed candidates' artifacts — MiniCPM-o, Qwen3-Omni, Qwen2.5-VL, Qwen3-VL —
were left untouched and unconnected throughout, and their records stand exactly
as they were. No cleanup was performed.
