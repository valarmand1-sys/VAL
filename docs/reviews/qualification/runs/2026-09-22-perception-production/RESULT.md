# Image, video and audio perception in production — three smokes, all PASS

Owner execution order, 22 September 2026. **No new model qualification was run.**
The settled evidence stands as it was: Qwen3.5's two visual cases and machine
fit (`../2026-09-22-qwen3_5-9b/`), and Qwen3-Omni's frozen Case B audio pass
(`../2026-09-21-qwen3-omni/`, whose Case C video failure also stands, unchanged
and unreinterpreted). What is proved here is narrower and different: **the
installed production application actually works.**

Each smoke runs through `val_gateway.startup.start` — the real composition root,
the same one the service runs — which builds the adapters and wires both
perception specialists itself. **Nothing was injected.** Governed scratch store,
so no manufactured history entered the owner's real conversation record.

Harness: `smoke.py`. Raw audio evidence: `audio_smoke.json`.

---

## What the composition root wired, before any turn

```
startup warnings: []
perception providers:
  MLXVLMPerception     modalities: image, video
  OmniAudioPerception  modalities: audio
```

Two specialists, each declaring what it is admitted for. No terminal, no manual
load, no manual provider selection, no manual unload — `start(engine)` and then
one ordinary `send`.

---

## IMAGE — **PASS**

The genuine Track C attachment, digest verified `7fc13a7c…`. Turn 36.8 s, of
which perception 24.3 s.

> **Owner:** Is the boy's hat on straight?
>
> **Qwen3.5, locally:** "No, the boy's hat is not on straight; it is tilted to the
> right side. The hat is a black top hat with a white band around its base… He is
> being hugged by a man and a woman… They are in a living room with a beige
> couch, a wooden coffee table, and a lamp in the background."
>
> **Val:** "No, the hat is tilted to the right side."

| | |
|---|---|
| perception state | `perceived` |
| provider / revision | `mlxvlm` / `b455506b0f574c74616dbcd56879bde38fafcff3` |
| runtime | mlx-vlm 0.7.2 |
| source | `image/png`, `verified: decoded` |
| handoffs | 1 |

**Negative proof.** One provider call in the interval — `conversation` on
`gpt-oss-20b-mxfp4-mlx-lmstudio-partner`, **$0.000000** — total provider cost
**$0**; perception cost **$0**; **0** raw media bound to any cognition call
(`model_call_image_inputs` written in the interval: zero); **no paid visual
call**; 615 distinct processes sampled during the turn and **none** matching
whisper, vosk, deepgram, assembly, openai, curl or wget.

## VIDEO — **PASS**

The repaired frozen fixture as an ordinary owner MP4 attachment, digest verified
`6925c05c…`. Turn 29.6 s, of which perception 12.6 s.

> **Owner:** What happens in this clip, and in what order?
>
> **Qwen3.5, locally:** "A red square is initially positioned on the left side of
> the screen. The square then moves to the right, and as it does, a blue circle
> appears below the square. The square continues to move to the right until it is
> positioned on the right side of the screen, with the blue circle still below
> it."
>
> **Val:** "1. A red square appears on the left side of the screen. 2. The square
> moves horizontally toward the right. 3. While it is moving, a blue circle
> materialises beneath the square. 4. The square continues its motion until it
> reaches the right side of the frame…"

| | |
|---|---|
| perception state | `perceived` |
| source | `video/mp4`, 9.000 s, `verified: container_structure` |
| handoffs | 1 |

`container_structure` rather than `decoded` because that is what admission
actually did: the `ftyp` brand, the box structure and `moov` were walked, and the
frames were not decoded. The perception runtime decodes them; admission does not
claim to have.

**Negative proof.** One provider call — `conversation`, local partner,
**$0.000000**; total **$0**; **0** raw media bound to any cognition call; no paid
visual call.

## AUDIO — **PASS**

The frozen Case B recording as an ordinary owner WAV attachment, digest verified
`d73733ae…`, 22.383 s. Turn 42.4 s, of which perception 27.3 s (a 19 GB model
loaded, perceived and exited inside that).

> **Owner:** Which envelope should she bring, and what is the number?
>
> **Qwen3-Omni, locally:** "The red envelope, and the number is 42."
>
> **Val:** "My lord, I shall bring the red envelope; its number is 42."

| | |
|---|---|
| perception state | `perceived` |
| provider / revision | `llamacpp-omni` / `6e35a28f4a19b18730f8949b0c579c6429649ab8` |
| runtime | llama.cpp 0.4.1 (build 10964, commit `b29c606e2`) |
| source | `audio/wav`, 22.383 s, `verified: decoded_header` |
| handoffs | 1 |

**Negative proof, including the no-transcription claim the order asks for by
name.** One provider call — `conversation` on the local partner, **$0.000000**;
total **$0**; perception **$0**; **0** raw media bound to any cognition call.
623 distinct processes sampled while the turn was in flight: the only perception
binary among them was **`/opt/homebrew/bin/llama-mtmd-cli`**, and **none** matched
whisper, vosk, deepgram, assembly, openai, curl or wget. **No Whisper, no separate
transcription model, no cloud service, no paid audio API.** The recording and the
instruction went in together through the model's own native multimodal path.

The process sampler is deliberately crude — it names *everything* running rather
than looking only where it expected to find nothing — because the claim being
proved is a negative one.

---

## Operations after all three

GPT-OSS resident at its full registered **32,768**-token window; memory **89 %**
free. Swap grew from 235 MB to 1,227 MB across the audio run, as a 19 GB model
mapped and exited, and the machine stayed nominal throughout — recorded because
it is true, not as a gate: the machine-fit gate belonged to Qwen3.5's
qualification and was settled there.

| | |
|---|---|
| Full mirror | green, all 15 steps |
| GitHub CI | green on `01af008` |
| Service | `{"status":"running","warnings":[]}` on the new code |
| Live store | `0026_local_audio_perception` |
| Persona | v1.9 revision 8, intact |

---

## What these smokes do not establish

They are three turns, not a qualification, and they carry exactly the scope the
underlying evidence carries.

- **Audio:** clean single-speaker speech only — the frozen Case B scope. Nothing
  about overlapping speakers, music under dialogue, noisy production audio,
  speaker identification or tonal judgement.
- **Video:** one short, deterministic clip. Nothing about long or complex
  material, and MP4 admission remains a container check rather than a decode.
- **A turn mixing audio with visual material fails closed**, by name, and is
  supported only as separate turns.
- The consequential classifier remains **text-only**, so media contribute
  nothing to how a turn is classified.
