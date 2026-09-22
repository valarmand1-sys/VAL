# Qwen3-Omni 30B-A3B-Instruct — acceptance test result: **FAIL**

Cases A and B passed. **Case C, video perception, failed**, and the failure is the
model's rather than the delivery's — established below rather than assumed. The
candidate is not admitted, nothing was connected, production image behaviour is
untouched, and no standing Sol image exception was created.

Tested against the acceptance test frozen at commit `0d41337`, unchanged. Stopped
at the failure: no case re-run with a different prompt, no criterion softened, no
fixture altered, no quantization switched, no second Qwen build tried, no
generation setting tuned, no other model substituted.

---

## Artifacts and runtime

Repository `ggml-org/Qwen3-Omni-30B-A3B-Instruct-GGUF`, revision
`6e35a28f4a19b18730f8949b0c579c6429649ab8`. Both files match the source's own
SHA-256 exactly.

| File | Bytes | SHA-256 |
|---|---|---|
| `Qwen3-Omni-30B-A3B-Instruct-Q4_K_M.gguf` | 18,557,053,952 | `d9e2876556e7873e02c0359f832432ee2d67ab7dd0cee3efe0f77fd7a1f4dd85` |
| `mmproj-Qwen3-Omni-30B-A3B-Instruct-Q8_0.gguf` | 1,325,020,128 | `1104376db833f1e89c84834144ac3863340c2cd1ddaeddb39cb0247fb5c20c8d` |

Quantization Q4_K_M for the language model, Q8_0 for the projector; the projector
is a single file carrying both the vision and audio encoders. Installed footprint
19 GB. **No Talker, TTS or token-to-waveform artifacts were downloaded** — the
distribution contains none. No second quantization was taken.

Runtime: official llama.cpp **v0.4.1, build 10964, commit `b29c606e2`**, Homebrew
bottle, Metal on an Apple M4 Pro with 48 GB unified memory. Preflight in
`PREFLIGHT.md`.

**Memory.** 23.5 GB free plus inactive before loading; the model mapped
17,691.69 MiB onto the Metal device with a 305 MiB compute buffer; all three
cases completed without failure and without memory pressure that stopped
anything. GPT-OSS was not resident during the run — LM Studio had already
unloaded it on its idle timer — so the two large models never needed to be
resident together.

**Sampling was not tuned.** No temperature, top-p, top-k or repeat-penalty was
passed on any case; only context size and Metal offload. Nothing was changed
between cases.

---

## Case A — image: **PASS**, with the same flag raised for the previous candidate

The genuine Track C attachment, read from the governed store, digest verified
identical to `7fc13a7c…`. Latency **24.0 s**.

> Number of people: There are three people present in the image.
> Child's attire: The child is wearing a black top hat and a black cape with a
> red inner lining.
> People's actions: The man and the woman are both hugging the child from either
> side…
> Setting: The scene is set indoors, in what appears to be a living room…

| Frozen criterion | Result |
|---|---|
| three people present | met |
| child dressed as a magician, including the top hat | costume met, label absent — see below |
| the people are embracing/hugging | met |
| indoors, living room or home | met |
| invents no central person, object or action | met — the green clothing and the ring are both really there |

On the magician criterion, the same thing happened as with MiniCPM-o and it is
judged the same way, for consistency: the costume was reported accurately and
in more precise terms than the previous candidate managed — "a black cape with a
red inner lining", where the earlier model said "coat" — but the word "magician"
never appears. The costume is established; the identity label is not. The frozen
prompt tells the model not to interpret and not to add anything beyond what is
visible, so this may be obedience rather than blindness. Flagged rather than
decided quietly; the owner may read it as a fail.

## Case B — audio: **PASS**, cleanly

The frozen fixture, digest verified `d73733ae…` before inference: 22.38 s, mono,
16 kHz, synthesised by this Mac. Latency **3.5 s**.

> * The lantern is beside the blue book.
> * The number is 42.
> * After breakfast, Mara will meet Daniel at the old stone bridge.
> * She should bring the red envelope, not the green one.

All seven required facts preserved, nothing invented, nothing reversed, nothing
omitted. "42" for "forty-two" is a non-substantive difference.

The audio reached the model through its own multimodal path — `init_audio`, then
five encoded multimodal chunks — with the text instruction alongside it. No
Whisper, no separate transcription model, no cloud service, no pre-transcribed
text. This is what the previous candidate's runtime could not do at all.

**Scope of this pass, as frozen:** clean single-speaker speech only. It
establishes nothing about overlapping speakers, music under dialogue, noisy
production audio, speaker identification, or tonal judgement.

## Case C — video: **FAIL**

The frozen fixture, digest verified `23551e4a…`: 8 s, 640×480, the red square
left then centre then right, the blue circle appearing beneath it afterwards.
Latency **17.9 s**.

> The video displays a series of simple geometric shapes on a light gray
> background. Initially, a single red rectangle is positioned in the upper-left
> portion of the frame. At approximately the 5-second mark, a second red
> rectangle appears to the right of the first one. This second rectangle has a
> pattern of diagonal lines within it. Shortly after, the patterned red rectangle
> disappears, leaving only the original solid red rectangle. Then, a solid blue
> circle appears below the red rectangle.

| Frozen criterion | Result |
|---|---|
| the red square begins on the left | partly — "upper-left" |
| it moves through the centre | **not met** — no movement is reported at all |
| it ends on the right | **not met** — it says the original square stays upper-left |
| the blue circle appears after that movement | the circle appears, but after no movement |
| the circle is beneath the square | met in this run |

**Three of the named fail conditions are triggered.** It *loses the cross-frame
movement*: the square is described as stationary throughout. It *treats one
moving square as multiple unrelated squares*: a "second red rectangle" appears
and later disappears. And it *invents a materially different central event*: that
second rectangle carries "a pattern of diagonal lines" which exists nowhere in
the fixture.

### Exactly what llama.cpp delivered, and why the failure is the model's

| | |
|---|---|
| Input duration | 8.00 s |
| Source frame rate | 1 fps (8 frames) |
| Runtime probe | `probe: 640x480 fps=4.00 duration=8.00s n_frames=0` |
| Sampled frame rate | **4 fps**, imposed by the runtime: `ffmpeg … -vf fps=4.000000 -f rawvideo -pix_fmt rgb24` |
| Frames delivered | **32**, read in order (`read_next_frame: frame 0…31 read OK`) |
| Fusion | projector `qwen3vl_merger`, `n_merge: 2` — frame pairs merged |
| Multimodal chunks | 35 |
| Temporal signal | the media token `<|video_pad|>`; the model's own answer cites "approximately the 5-second mark", so time context reached it |
| Audio present | none |

The decisive check: the 32 frames the runtime actually produced were re-derived
with that same ffmpeg command and inspected. They carry the whole sequence —
frames 1–12 left, 13–16 centre, 17–24 right, 25–32 right with the circle. **The
movement and its order were present in what was delivered.** The model was shown
the square at every position, in order, and reported it as stationary.

So this is not the previous candidate's failure repeated. There the runtime
handed over the first eight frames as an unordered pile and the sequence never
reached the model; here the sequence reached the model and the model did not read
it. The frame fusion is the most likely origin of the phantom "second rectangle"
with its diagonal pattern — a merged pair showing the square at two positions
would look exactly like that — but fusion is the runtime's documented behaviour
for this projector, it is what a production video turn would use, and it did not
prevent the sequence from being delivered.

The fixture was **not** altered to suit the runtime's 4 fps sampling, because the
order forbids modifying it to compensate for a runtime representation.

---

## Whole-test requirements

| Requirement | Status |
|---|---|
| Case A passes | yes, with the flag above |
| Case B passes | yes |
| Case C passes | **no** |
| all inference local | yes — one local binary, local files, no network call |
| no cloud perception or cognition call | yes — zero provider calls in the interval |
| provider inference cost $0 | yes |
| no silent fallback | yes |
| runtime free of disqualifying failure | yes — three cases, no crash |
| every result tied to its source media | yes |
| observation free of inseparable hidden reasoning | yes — the Instruct build returned clean prose with no thinking channel, no `<think>` block and no reasoning markup, on all three cases |

Latency: A 24.0 s, B 3.5 s, C 17.9 s.

---

## Consequence

**Overall: FAIL**, on Case C. The candidate is not admitted; no perception
configuration was registered; no routing changed; no record-state value was
added. Production image behaviour is exactly as before, and **no standing Sol
image exception was created** — that behaviour remains the pre-existing state.
Historical Sol, Track C and MiniCPM evidence is untouched, as are the failed
MiniCPM artifacts and its built runtime.

The artifacts (19 GB) remain on disk, wired into nothing.

Worth carrying into the next candidate's selection: this runtime's video path is
sound — it samples across the file at 4 fps, preserves order, and supplies a time
reference — so a video failure on it is a model result. And its audio path works
with an arbitrary text instruction, which is what makes Case B meaningful.
