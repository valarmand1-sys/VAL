# Val's local voice — designed, cloned, installed

Owner execution order, 22 September 2026. Val speaks on her own machine, in a
voice that did not exist before tonight and that belongs to nobody.

**The blocker this replaces is not reopened.** The earlier Qwen3-TTS Base
attempt closed FAILED at its pre-download rights gate: every VAL voice recording
on this machine is ElevenLabs Output — five files across four locations, each
carrying `kMDItemWhereFroms = https://elevenlabs.io/` — and no agreement,
enterprise agreement or written permission anywhere in the owner's records
authorises using that Output as another AI model's input. That finding stands.
What changed is that the dependency was removed rather than reinterpreted: **the
reference is now generated locally**.

**No ElevenLabs audio, no Higgsfield audio, no third-party generated voice and
no real person's voice was used as conditioning input at any point.**

---

## The two artifacts

Both Apache-2.0, both verified against the source before use.

| | VoiceDesign | Base |
|---|---|---|
| Repository | `mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit` | `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit` |
| Revision | `f90d617701d9f7f4ca499291e0b57f2b3c2fd2ee` | `e7dd0585652209fa0d7783659aad4e8a324de11c` |
| `model.safetensors` | 2,393,308,931 B · `1a84179d87c972353ccdd9b48f3c4422509b3d1b11030d32358312fb0f3800d7` | 2,417,320,525 B · `b965c581ccf6aa852a4124feeb7a8a111542ee7b213139368b4cc7ba7fd4728b` |
| `speech_tokenizer/model.safetensors` | 682,293,092 B · `836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258` | same digest |
| Repository total | 3.08 GB | 3.10 GB |
| `tts_model_type` | `voice_design` | `base` |
| Quantization | 8-bit MLX, group size 64, affine | 8-bit MLX, group size 64, affine |

The Base `model.safetensors` digest is exactly the one the owner's order stated.
No 4-bit, 5-bit, 6-bit or bf16 build, no 0.6B, no CustomVoice, no other
publisher, no backup quantization was downloaded.

**Runtime:** a **dedicated** isolated environment at
`~/.val-runtimes/mlx-audio-venv` — mlx-audio **0.5.5** (the current release), mlx
0.32.2, numpy 2.5.3, Python 3.12.13. Val's production Python environment and its
pins are untouched, and so is the admitted *visual* runtime: mixing TTS into the
qualified perception environment would have put a future mlx-audio update in the
path of a qualified route.

**The installability gate was settled from the installed implementation, before
either download** — `generate_voice_design(text, instruct, language)` at
`qwen3_tts.py:2143`; the ICL clone path (`_generate_icl`,
`_prepare_icl_generation_inputs`, matching Qwen3-TTS's official
`generate_icl_prompt`) gated to `tts_model_type == "base"` with both `ref_audio`
and `ref_text`; reusable conditioning cached as `(ref_codes, ref_text_ids)`;
`english` supported on both.

---

## The frozen voice description

Used verbatim as the VoiceDesign instruction, digest
`d5f56a129b8cdd4fa662bae294238197dd055c269387f8ebdce74330454658b7`:

> Adult British woman. Kind, intelligent, warm, gentle, feminine and lady-like.
> Refined, clear diction and calm, measured pacing. A trusted scholarly advisor
> with quiet confidence and subtle emotional warmth. Modern natural speech with a
> faint old-world poise, but never archaic or medieval in wording or performance.
> Avoid theatricality, exaggerated poshness, breathiness, childishness, coldness,
> or robotic delivery.

**No ElevenLabs audio was inspected to derive acoustic characteristics, no model
was used to reverse-engineer the ElevenLabs voice, and the description was not
optimised.** It was frozen before generation and used once.

---

## 1. The canonical reference — **PASS**

**One** VoiceDesign generation. No audition batch, no seed search, no variations,
no regenerate-until-good loop. Reference text, digest `dcbcd4d3…`:

> Good evening, my lord. I have finished the work, and everything is ready for
> you. I will remain here if you need anything further.

Load 14.9 s, generation 19.4 s total. **`val-canonical-reference.wav`**, SHA-256
`9e92121b28888e7ed0dce9a09e2472b0a282b7294e21887e849dad310ca371fa`.

**Signal, measured from the waveform** (thresholds stated before measuring;
`reference_signal.json`):

| | |
|---|---|
| sample rate / channels | 24,000 Hz mono, 16-bit |
| duration | 8.240 s (expected band for 24 words: 8.0–17.1 s) |
| peak amplitude | 0.5456 — ample headroom |
| samples at or near full scale | **0** (0.000000 of the file) |
| longest near-silent run | 0.843 s, interior — a sentence pause, under the 2.0 s bound |
| leading / trailing silence | 0.027 s / 0.142 s |

**Content, verified once by the installed local Qwen3-Omni route** — content
only, as the order requires; it was not asked about voice quality, identity or
similarity. Every one of the 24 words present, nothing missing, no repetition,
$0, local. The only difference is an absent comma.

## 2. The consistent voice — **PASS**

The Base model loaded the canonical reference and its **explicit** transcript
(no automatic transcription, no Whisper, no STT of any kind) and produced the
reusable clone prompt: `~/.val-voice/val-clone-prompt.npz`, SHA-256
`4e0acd9c2024977be5adcb0704b04580e89e02536adc9575860ce561dd2f7e18`.

**One** Base generation on a different sentence, `val-clone-check.wav`:

> The image, video, and audio systems are ready, my lord. I can begin whenever
> you wish.

Load 1.2 s, generation 6.6 s. 24 kHz mono, **6.640 s**, peak 0.4830, **zero**
samples at full scale, **no interior silence at all**. Qwen3-Omni heard it back
**word for word exactly**, 16 of 16, no repetition, $0, local.

## 3. The production smoke — **PASS**

Through the **real** composition root (`val_gateway.startup.start`), nothing
injected. Startup warnings: none. Speech provider `QwenTTSSpeech` wired
automatically; voice `val-local-v1` loaded automatically.

An ordinary Val turn produced a finished response, and that message was spoken:

> **Val, in text:** "I do not have that in the record I can see."
> **Val, aloud:** the same sentence — `val-production-smoke.wav`, SHA-256
> `0197012b367d6bdf6c10c2ac9d2d1d51283d9eba402d70a90b0228f939a21455`

Speech took 4.35 s. 24 kHz mono, **2.880 s**, peak 0.4475, zero clipping, no
interior silence. Qwen3-Omni heard all 11 words exactly. `final_text` on the
record equals the persisted message **verbatim**.

**The clone prompt was `4e0acd9c…` — byte-identical to the one the acceptance
generation created.** It was *reused*, not recreated, which is the proof that
the reusable identity anchor is real rather than intended. `VoiceDesign` did not
run.

### Negative proof

| | |
|---|---|
| provider calls in the speech interval | **0** |
| local TTS cost | **$0.000000** |
| ElevenLabs generation calls | **0** |
| cloud TTS calls | **0** |
| Whisper / STT calls for reference transcription | **0** — the transcript was supplied explicitly on every clone run |
| external voice-conditioning audio | **none** |
| processes sampled during the run | 598 |
| local speech runtime observed | `~/.val-runtimes/mlx-audio-venv/bin/python` |

**One reported match needs stating rather than glossing.** The sampler's
substring test flagged `/usr/sbin/KernelEventAgent` against the needle
`eleven` — because the letters *eleven* occur inside *Kern**elEven**tAgent*. It
is a macOS system daemon present on every Mac, unrelated to ElevenLabs. The
negative is additionally proved structurally: `test_speech_adapter.py` tokenises
the provider module, strips comments and docstrings, and asserts that the
executable code contains no `eleven`, no `http://`, no `https://`, no HTTP
client and no second executable. A silent ElevenLabs call would need code that
does not exist.

---

## Machine health

Sequential loading throughout; nothing was forced to be resident together.

| | |
|---|---|
| model loads | normal — 14.9 s cold (VoiceDesign), 1.2 s warm (Base) |
| OOM / process kills | none |
| memory pressure | nominal; 77–90 % free across the runs |
| swap | unchanged by TTS at 1,219 MB used, the level the earlier 19 GB audio run left |
| GPT-OSS afterwards | resident and operating at its registered 32,768-token window |

---

## Voice identity — what is and is not claimed

**Val's local voice was independently created from her owner-defined textual
voice identity using Qwen VoiceDesign, then stabilised for repeated local speech
through Qwen Base voice cloning.**

It is **not** an acoustic clone of the historical ElevenLabs voice, and nothing
here claims it is. No similarity score was manufactured; no speaker-recognition
model was added to grade this one; no biometric equivalence was measured,
because none was measured. Qwen3-Omni was used **only** to check that the spoken
words match the text, which is within the capability its settled Case B already
demonstrated.

The historical ElevenLabs voice is preserved as external/historical VAL voice
continuity. Its records are untouched.

**The final judgement is the owner's listening judgement**, and it was not an
intermediate checkpoint: the installation was completed first.

---

## Scope of these passes

Three generations, one per model plus one production utterance — not a
qualification suite. Nothing is established about long passages, other
languages, emotional range, interruption, or how the voice holds across many
utterances. The registry entry carries both limits in the words they matter in.
