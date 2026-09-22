# Qwen3-Omni 30B-A3B-Instruct — runtime and output preflight

Run before downloading twenty gigabytes, as the owner's order requires. Every
line below was read from the machine or from the source, not inferred from the
model's architecture.

**Outcome: the preflight passes.** All six gate requirements are available:
image, audio and video each with an arbitrary text prompt; preserved temporal
ordering for video; clean observation output separable from any reasoning; and
local Apple-Silicon execution.

---

## The machine, confirmed from the machine

| | |
|---|---|
| Chip | Apple M4 Pro |
| Unified memory | 48 GB |
| Metal device | `MTL0: Apple M4 Pro (38,338 MiB)` |
| Free + inactive + purgeable before load | 23.5 GB |
| GPT-OSS resident at the time | no — LM Studio had unloaded it on its idle TTL |

## The runtime

The installed build was llama.cpp **b10360** (`48d22e295`), which already
post-dates Qwen3-Omni support upstream — that landed on 12 April 2026 in
`21a4933` ("mtmd: qwen3 audio support (qwen3-omni and qwen3-asr)"), documented
the next day in `e974923`. But it was **604 commits behind** the current official
release, and video handling gained fixes in that window, including
`160c6b0` (24 August, "video: fix moov atom at the end of file") and `6de9cdb`
(9 September, "propagate video ID to bitmap").

The order permits one bounded update to the current official runtime in exactly
this situation, so that was taken: `brew upgrade llama.cpp`, from the official
Homebrew bottle, to

    llama.cpp v0.4.1 — build 10964, commit b29c606e2

No fork, no patch, no custom build. This runtime is separate from LM Studio,
which serves GPT-OSS, so the production cognition route was not touched.

## The six gate requirements

| Requirement | Available | How it was established |
|---|---|---|
| image + arbitrary text prompt | **yes** | `--image FILE` and `-p` are both first-class CLI arguments |
| audio + arbitrary text prompt | **yes** | `--audio FILE` shares that argument with `-p` |
| video + arbitrary text prompt | **yes** | `--video FILE`, same |
| preserved temporal ordering | **yes** | see below |
| reasoning separable from observation | **yes** | the Instruct build, not the Thinking build |
| local Apple-Silicon execution | **yes** | Metal device present, everything on disk |

**Temporal ordering.** The library carries a real video pipeline rather than a
frame dump: it starts `ffmpeg`, reports `%ux%u fps=%.2f duration=%.2fs
n_frames=%d`, reads frames in sequence (`read_next_frame`, `frame %d read OK`),
and merges frame pairs (`merging 2 frames at part index %zu and %zu`) — the
temporal merge Qwen3-VL's encoder expects. Upstream's video support commit
(`8f83d6c`, 8 June) lists "add timestamp" among its steps. The exact frame count,
sampled rate and ordering actually delivered are recorded per-case at run time,
because the order requires the delivered representation and not the documented
one.

This is the specific thing the previous candidate failed on, and it is worth
naming the difference: MiniCPM-o's supported runtime took the **first** eight
frames with no sampling filter and handed them over as plain images with no
temporal signal. This one samples across the file and merges pairs.

**The projector.** The mmproj header was read by HTTP range request, 256 KB, so
the question was settled before the twenty gigabytes were fetched. It is a single
projector carrying **both** encoders:

```
general.architecture      = clip
clip.has_vision_encoder   = True    clip.vision.projection_dim = 2048
clip.has_audio_encoder    = True    clip.audio.projection_dim  = 2048
clip.vision.image_size    = 768     clip.audio.num_mel_bins    = 128
clip.vision.block_count   = 27      clip.audio.block_count     = 32
clip.vision.spatial_merge_size = 2
clip.vision.is_deepstack_layers = (array)
```

One file for vision and audio, where MiniCPM-o split them and the multimodal
library could load only one of the two. The runtime's own symbol table carries
`qwen3vl` and `qwen3a`, the two projector families this file needs.

**Reasoning separation.** The candidate is the **Instruct** build, chosen by the
order rather than by me; the Thinking build is a separate repository and was not
downloaded. Whether the visible output is in fact clean is confirmed from the
actual answers and recorded with them, since a preflight cannot settle it.

## What was not downloaded

The distribution contains only language models (Q4_K_M, Q8_0, bf16), two
projectors, a README and `.gitattributes`. **It ships no Talker, speech-generation,
TTS or token-to-waveform files at all**, so there was nothing of that kind to
decline; the fact is recorded as the order asks. Only the Q4_K_M model and the
Q8_0 projector were fetched. No second quantization was taken as a backup.
