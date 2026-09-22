# Qwen2.5-VL-7B-Instruct (4-bit MLX) — acceptance test result: **FAIL**

**Both cases failed.** Case A misses the cape and invents a tie; Case C loses the
movement and reads one moving square as two. The candidate is not admitted,
nothing was connected, production image behaviour is untouched, and no standing
Sol image exception was created.

Stopped at the failure: no case re-run with a different prompt, no fixture
changed, no quantization switched, no sampling tuned, no other Qwen2.5-VL size
tried, no model substituted. The MiniCPM-o and Qwen3-Omni artifacts were left
untouched throughout.

---

## Artifact and runtime

Repository `mlx-community/Qwen2.5-VL-7B-Instruct-4bit`, revision
`fdcc572e8b05ba9daeaf71be8c9e4267c826ff9b`. Both weight shards match the
source's own SHA-256 exactly.

| File | Bytes | SHA-256 |
|---|---|---|
| `model-00001-of-00002.safetensors` | 5,330,940,405 | `f80072ac0e82a2ace0740eab995f6f9ae2623adb55e6906e21c2f8edca537803` |
| `model-00002-of-00002.safetensors` | 306,561,369 | `016bd9d3596e9b824f5a527875e5830414552c950eee794e98efb44c1cd8dc6a` |
| `tokenizer.json` | 11,421,896 | `9c5ae00e602b8860cbd784ba82a8aa14e8feecec692e7076590d014d7b7fdafa` |

Plus `config.json`, `chat_template.json`, `preprocessor_config.json`,
`model.safetensors.index.json`, `merges.txt`, `vocab.json`,
`added_tokens.json`, `special_tokens_map.json`, `tokenizer_config.json` — all
small and non-LFS. Quantization **4-bit, group size 64**, declared in
`config.json` alongside `model_type: qwen2_5_vl`. Installed footprint **5.3 GB**;
the runtime environment adds 595 MB.

Runtime: **mlx-vlm 0.7.2**, **mlx 0.32.2**, transformers 5.17.0, opencv 5.0.0,
Python 3.12.13, in an isolated virtual environment at
`~/.val-runtimes/mlx-vlm-venv` so the production environment and its pinned
dependencies were not touched. Apple M4 Pro, 48 GB; 31.2 GB free plus inactive
after the run, no memory pressure, nothing swapped out by the run. GPT-OSS was
not resident, so the two never needed to be held together.

Generation was **not tuned**: library defaults throughout, nothing passed to
steer sampling, nothing changed between the two cases.

**Reasoning behaviour:** both answers are plain prose. No thinking channel, no
`<think>` block, no reasoning markup — the observation output is clean and needs
no separation step.

## Preflight, before download

Verified from the installed runtime rather than inferred from the architecture:
`qwen2_5_vl` is an implemented model module; text accompanies image and video
input; video is a first-class path (`load_video`, `VideoSampling` defaulting to
2 fps with a 4–768 frame clamp, `VideoMetadata` carrying `frames_indices` and
per-frame `timestamps`); frame order and timing are preserved into the model by a
3D patch embedding over frame pairs (`temporal_patch_size: 2`) and mrope with a
temporal axis (`video_grid_thw`); opencv is present to decode; and the 4-bit
artifact's declared `model_type` matches the runtime's module.

---

## Case A — image: **FAIL**

The genuine Track C attachment from the governed store, digest `7fc13a7c…`. The
**frozen prompt was used unchanged**. The criterion is the repaired one recorded
in `EXAM_REPAIR_CASE_A.md`, committed in `035b6e6` before this candidate ran.
Latency **20.8 s**.

> There are three people in the image. The child is wearing **a black suit with a
> red tie** and a black top hat. The two adults, a man and a woman, are hugging
> the child. The setting appears to be a cozy living room with a beige sofa,
> cushions, a coffee table with books, and a side table with a lamp and a vase of
> flowers.

| Repaired criterion | Result |
|---|---|
| three people are present | met |
| **the child wears a top hat and a cape** | **not met** — top hat yes, cape no |
| the people are embracing/hugging | met |
| indoor living-room or home setting | met |
| no material central object invented | **not met** — there is no tie |

**The exact failed criterion is the second.** The child wears a black cape with
red trim over a stand-up collar; the fixture was inspected directly to be certain
before judging. The model reported "a black suit with a red tie": it read the
cape's red front trim as a necktie and the cape itself as a suit. The cape is the
most prominent garment in the costume and the one the repaired criterion names,
and it is not established. The invented tie fails the fifth point on its own
account.

This is not the ambiguity the exam repair was made to remove. The two earlier
candidates described the garment correctly and only withheld the interpretive
label; this one misdescribes the garment itself.

## Case C — video: **FAIL**

The frozen video fixture, unmodified, digest `23551e4a…`. The frozen prompt
unchanged. Latency **5.6 s**.

> The video starts with a single red square on a light gray background. Then, a
> second red square appears to the right of the first red square. Finally, a blue
> circle appears below the second red square.

| Frozen criterion | Result |
|---|---|
| one red square starts on the left | partly — "a single red square", no side given |
| that same square moves through the centre | **not met** |
| that same square ends on the right | **not met** |
| the blue circle appears afterward | met |
| the circle is beneath the square | met |

Three named fail conditions: it **loses the movement**, it **treats the moving
square as several unrelated squares**, and it **fails to preserve left → centre →
right**. The signature is almost identical to Qwen3-Omni's — one square in
motion read as a second square appearing beside the first.

### What the runtime delivered, and one defect of mine that it exposed

| | |
|---|---|
| Source | 8.0 s, 640×480, 1 fps, 8 frames |
| Sampled | **1.0 fps** — the source rate, not resampled |
| Frames delivered | **8** |
| Frame indices | 0, 1, 2, 3, 4, 5, 6, 7 |
| Timestamps | 0.0 … 7.0 s, one per frame, in order |
| Frames array | shape (8, 3, 480, 640) |
| Temporal representation | 3D patch embedding over frame pairs, mrope temporal axis |

Every frame of the fixture was delivered, in order, with a timestamp each. Those
same eight frames were verified earlier to carry the whole sequence — left on
frames 1–3, centre on 4–5, right on 6–8, the circle on 7–8. **The sequence was
delivered intact and the model did not read it.** The fixture was not altered.

**A defect of mine, found and corrected before judging.** The first attempt
passed `num_videos=1` to `apply_chat_template`, which has no such parameter — it
went silently into `**kwargs`, no video placeholder was emitted, and the model
was handed a bare question about a video it had never been shown. It said so
("I need a specific video link…") and answered in 1.1 s. The correct argument is
`video=<path>`, which triggers the video message formatter for this model type.
Corrected as an installation defect that stopped the intended input reaching the
model, which the order permits; the answer above is from the corrected run, and
the failed first attempt is recorded rather than hidden.

---

## Whole-test requirements

| Requirement | Status |
|---|---|
| Case A passes | **no** |
| Case C passes | **no** |
| both inferences local | yes — MLX on this Mac, local files, no network call |
| no cloud perception or cognition call | yes — zero provider calls in the interval |
| provider inference cost $0 | yes |
| no silent fallback | yes |
| clean grounded observation, not inseparable reasoning | yes |
| source media unambiguously identified | yes |
| runtime completes without disqualifying failure | yes |

Latency: Case A 20.8 s, Case C 5.6 s. Model load 0.5 s.

---

## Consequence

**Overall: FAIL.** Not admitted; no visual-perception configuration registered;
no routing changed; no record-state value added; no perception prompt, handoff or
integration built. Production image behaviour is exactly as before, and **no
standing Sol image exception was created** — that remains the pre-existing state.
Historical Sol, Track C, MiniCPM-o and Qwen3-Omni evidence is untouched, and the
two earlier candidates' artifacts remain on disk, unconnected, as instructed.

The artifacts (5.3 GB) and the MLX runtime environment (595 MB) remain on disk,
wired into nothing.

**Carried forward.** Three candidates have now failed the same video case, and
the delivery has been verified intact for the last two — 32 ordered frames with a
time reference for Qwen3-Omni, 8 ordered frames with per-frame timestamps here.
The common failure is not plumbing: each model read one square in motion as
several squares appearing. That is worth weighing when the next candidate is
chosen, and it may be worth asking whether the frozen fixture's abstract shapes
are the hardest possible case for models trained on natural video.
