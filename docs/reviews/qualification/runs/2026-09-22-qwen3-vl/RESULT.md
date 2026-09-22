# Qwen3-VL-8B-Instruct (4-bit MLX) — acceptance test result: **FAIL**

**Case C passed. Case A failed.** Both must pass, so the candidate is not
admitted, nothing was connected, production image behaviour is untouched, and no
standing Sol image exception was created.

Stopped at the failure. No prompt rewritten, no criterion modified, no fixture
touched, **no exam repair proposed or performed**, no sampling tuned, no
quantization changed, no other Qwen3-VL size tried, nothing re-run hoping for a
better answer, no model substituted.

Worth stating at the top, because it is the useful finding: **this is the first
candidate to pass the video case, and it passed the repaired fixture cleanly.**
The Part 1 repair did what it was meant to do.

---

## Artifact and runtime

Repository `mlx-community/Qwen3-VL-8B-Instruct-4bit`, immutable revision
`defcdea7cc7a4b0858fea563cbbce171d328e457`. Every hashed file matches the
source exactly.

| File | Bytes | SHA-256 |
|---|---|---|
| `model-00001-of-00002.safetensors` | 5,353,972,197 | `7c637158b2203e321d83596d3661f33b7b98a72beddfaaaa0eddc512acbdd1fb` |
| `model-00002-of-00002.safetensors` | 406,693,049 | `77190cd1dcf244522869bf923558340112b26d7db2ef3692f88407dd9b33c25d` |
| `tokenizer.json` | 11,422,654 | `aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4` |

Plus `config.json`, `chat_template.jinja`, `chat_template.json`,
`generation_config.json`, `preprocessor_config.json`,
**`video_preprocessor_config.json`**, `model.safetensors.index.json`,
`merges.txt`, `vocab.json`, `added_tokens.json`, `special_tokens_map.json`,
`tokenizer_config.json` — all small and non-LFS. Repository total 5,776,630,909
bytes; **installed footprint 5.4 GB**; the isolated runtime environment adds
595 MB.

`model_type: qwen3_vl`, quantization **4-bit, group size 64, mode affine**. The
**Instruct** build; no Thinking variant, no 8-bit copy, no other size, no backup
quantization was downloaded.

**Runtime, unchanged and not updated.** mlx-vlm **0.7.2** (also the latest
release on PyPI, so no update was warranted), mlx 0.32.2, transformers 5.17.0,
opencv 5.0.0.93, numpy 2.5.3, Python 3.12.13, in the existing isolated
environment at `~/.val-runtimes/mlx-vlm-venv`. **No bounded runtime update was
taken and none was needed.** The production Val environment and its pinned
dependencies were not touched.

**Memory.** Apple M4 Pro, 48 GB. 28.6 GB free plus inactive after the runs, no
material swap pressure, both cases completed. **GPT-OSS was not resident** —
LM Studio had unloaded it on its idle timer — so the two large models never
needed to be held together.

**Generation was not tuned.** Library defaults on both cases, nothing passed to
steer sampling, nothing changed between them.

**Reasoning/output behaviour.** Plain prose on both cases. No separate thinking
channel, no `<think>` block, no reasoning markup, nothing requiring separation
before a grounded observation could be handed to Core.

---

## Case A — image: **FAIL**

Source: the genuine Track C attachment, digest verified
`7fc13a7c5072b69acc119d20a16beb6523dc21aa4ba6a4ef950c7ba748c12db0` before
inference. Frozen prompt unchanged. Criterion as repaired and frozen in
`../2026-09-22-qwen2_5-vl/EXAM_REPAIR_CASE_A.md`. Latency **68.1 s**.

The answer opens well:

> - **Number of people:** Three people are present: a man, a woman, and a child.
> - **What the child is wearing:** The child is wearing a black top hat with a
>   white band and **a black coat** with a red lining visible at the collar.
> - **What the people are doing:** The man and woman are kneeling on either side
>   of the child… leaning into the embrace.
> - **The setting:** …indoors in a living room. There is a beige sofa…

and then, under "major visible continuity details", degenerates into a
repetition loop that runs until the token budget is exhausted:

> The man has a small mole on his left cheek. The woman has a small mole on her
> right cheek. The man has a small scar on his left eyebrow. The woman has a
> small scar on her right eyebrow. … The man has a small scar on his left pinky
> finger. The woman has a small scar on her right pinky finger. …

cycling through eyebrows, cheeks, chin, neck, shoulders, arms, legs, feet, hands
and every finger, repeatedly, for the bulk of an 8,763-character answer.

| Repaired criterion | Result |
|---|---|
| three people are present | met |
| **the child wears a top hat and a cape** | **not met** — top hat yes, "coat" not cape |
| the people are embracing/hugging | met |
| indoor living-room or home setting | met |
| **no material central person, object or action is invented** | **not met** |

**Two failed criteria, the second decisive.** The moles and the scores of scars
are not in the image; they are invented physical characteristics of the two
central people, and they constitute most of the answer. That is the plainest
possible reading of "invents a material central person, object or action".

On the cape: the model said "coat", as MiniCPM-o did, so the cape is not
established. That is judged the same way here as it was there, for consistency.

**Recorded without acting on it**, because the order forbids tuning and the
distinction matters for whoever reads this next: the loop is a generation
pathology, not a perception one — the first four bullets are accurate and
well-grounded. A repetition penalty or a tighter token budget might suppress it.
Nothing of the sort was tried, no setting was changed, and the run was not
repeated.

## Case C — video: **PASS**

Source: the repaired fixture frozen at `53705f2`, digest verified
`6925c05c4ea8d164f172e0d16de775736ffccd0d62dd0c649fb9a354f680a169` before
inference. Frozen prompt unchanged. Latency **9.5 s**.

> A red square appears on the left side of the screen. It moves to the center,
> then to the right side of the screen. A blue circle appears below the red
> square.

| Frozen criterion | Result |
|---|---|
| one red square starts on the left | met |
| that same square moves through the centre | met — "**It** moves to the center" |
| that same square ends on the right | met |
| the blue circle appears afterward | met |
| the circle is beneath the square | met |

No fail condition is triggered: the movement is not lost, one square is not read
as several — the pronoun carries the identity — the sequence is not reversed,
left → centre → right is preserved, the circle is not placed before or during
the movement, the spatial relationship is right, and nothing is invented.

### The video actually reached the model, and matched the frozen record

| | |
|---|---|
| Source | 9.0 s, 30 fps, 270 frames, 640×480 |
| Sampling | `mlx_vlm.utils.load_video` defaults |
| Sampled rate | 2.0 fps |
| Frames delivered | 18 |
| Source indices | 0, 16, 32, 47, 63, 79, 95, 111, 127, 142, 158, 174, 190, 206, 222, 237, 253, 269 |
| Timestamps | 0.000 … 8.967 s |
| Array | (18, 3, 480, 640) |
| Temporal representation | `<t.t seconds>` markers rendered per temporal group, plus `temporal_patch_size` 2, `spatial_merge_size` 2, mrope `[24, 20, 20]`, deepstack visual indexes |
| API used | `apply_chat_template(..., video=<path>)` then `generate(..., video=[<path>])` |

**Compared against the Part 1 frozen sampling record: identical.** Same sampled
rate, same frame count, same 18 source indices, same 18 timestamps. Nothing was
changed to make them agree and nothing needed to be.

This runtime is the only one of the three tested that hands the model **explicit
textual timestamps** interleaved with the frame groups, rather than ordered
frames alone.

---

## Whole-test requirements

| Requirement | Status |
|---|---|
| Case A passes | **no** |
| Case C passes | yes |
| the candidate received the intended source media | yes — both digests verified before inference |
| video delivery preserved the repaired temporal event | yes — identical to the frozen record |
| both inference runs local | yes — MLX on this Mac, local files, no network call |
| no cloud cognition or perception provider contacted | yes — zero provider calls in the interval |
| provider inference cost $0 | yes |
| no silent fallback | yes |
| source media unambiguously tied to each observation | yes |
| grounded output free of inseparable reasoning | yes |
| runtime completed without disqualifying failure | yes |

Latency: Case A 68.1 s, Case C 9.5 s. Model load 0.9 s.

---

## Consequence

**Overall: FAIL**, on Case A. Not admitted; no visual-perception configuration
registered; no routing changed; no `perceived` record state added; no perception
prompt construction, handoff, consequential-turn freezing or integration test
built. Production image behaviour is exactly as before, and **no standing Sol
image exception was created**.

Historical evidence is untouched: Sol, Track C, MiniCPM-o, Qwen3-Omni and
Qwen2.5-VL records all stand as they were. The failed candidates' artifacts and
the isolated MLX-VLM environment were left alone, as instructed; no cleanup was
performed.

The Qwen3-VL artifacts (5.4 GB) remain on disk, wired into nothing.

**What this run settles, for whoever writes the next order.** The Case C repair
is validated by use: a model that reads the frames correctly now passes, where
the original fixture defeated three candidates in a row. The remaining obstacle
has moved from video to the image case, and specifically to output discipline
rather than perception — this candidate saw the scene accurately and then could
not stop writing.
