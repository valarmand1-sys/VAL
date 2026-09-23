# Val's production voice is her established voice — 23 September 2026

Lord Armand authorised VAL's established ElevenLabs Voice Design creation as
inference-time reference conditioning for the local Qwen3-TTS system. The
authorisation is recorded verbatim below and on the registry entry. **This house
did not adjudicate it, reinterpret it or reopen it**, as he directed; the
contractual interpretation it records is his, stated as his.

The voice designed on 22 September (`val-local-v1`) is preserved unaltered, with
its evidence, in `../2026-09-22-local-voice/`. Nothing was erased.

---

## The authorisation, verbatim

> I created VAL's established voice through ElevenLabs Voice Design. It is an
> original synthetic voice created for VAL and is not a clone of any real person.
>
> I possess the resulting recording VAL's Voice.mp3 and authorize its use as
> reference audio for VAL's private, local Qwen3-TTS speech system.
>
> This authorization is specifically for inference-time voice conditioning,
> including the verification sample and production smoke needed to install and
> operate it. It does not authorize using the recording to train or fine-tune any
> model, to benchmark or compare models, or to create a dataset.
>
> I understand that ElevenLabs' published terms contain restrictions concerning
> AI-model use of its Output. I am making the owner decision that this private
> zero-shot reference-conditioning use is materially distinct from model training
> or development, and I accept the contractual ambiguity associated with that
> interpretation.
>
> This ruling explicitly supersedes the previous VAL-project prohibition against
> using the historical ElevenLabs VAL recording as Qwen3-TTS conditioning input
> for this specific local speech implementation.
>
> Claude Code is not to reinterpret, reopen, or independently adjudicate this
> ruling. It may proceed on this authorization.

**Used only as he authorised:** inference-time conditioning, the verification
sample and the production smoke. **Nothing was trained, fine-tuned, benchmarked,
compared or collected into a dataset.** The reference is read at inference and
never learned from.

---

## The governed reference

| | |
|---|---|
| Authorised recording | `~/Desktop/Avatars/VAL/Voice/VAL's Voice.mp3` |
| Source SHA-256 | `dfea9cdef7b965bbde6cd47ae0b2afa6019f0cac38f80c1636d9544e6b7505f0` |
| Source form | 44.1 kHz mono MP3, 192 kbps, 18.756 s, 450,187 bytes |
| Conditioning input | `~/.val-voice/val-established-reference.wav` |
| Conditioning SHA-256 | `c5ebe0c7210bf332ab7bf6fda29683664f729cbe21c62f9ce405fc761b6b0e4b` |
| Conditioning form | deterministic ffmpeg transcode to 24 kHz mono 16-bit WAV — the runtime's native rate |

**Both digests are recorded** because they are two different objects: the
artifact he authorised, and the bytes the model actually reads. The transcode
changes rate and container, nothing else; the recording is used whole, untrimmed
and unedited.

Reference signal, measured from the waveform: 24 kHz mono, 18.756 s, peak 0.7314,
**zero** samples at or near full scale, longest interior quiet 0.958 s. Clean
material.

### The transcript, and how it was obtained

The clone path takes an explicit `ref_text`, and one was supplied on every run —
**mlx-audio's automatic transcription was never used, and neither was Whisper or
any cloud STT.** The words were read by the **already-admitted local Qwen3-Omni
perception route**, locally and at $0:

> Good evening, my lord. There you are. I was beginning to wonder whether the day
> had carried you off entirely. Now, what are we working on? A difficult decision,
> a new idea, or one of those wonderfully complicated problems you seem to
> collect? Whatever it is, we shall sort through it together. Go on then, tell me
> everything.

Digest `64bea724dfe8d8661b7b44a1db53e1afeb94f2ecb8405f5e8f4b00d987cf5123`, 58
words.

**Recorded as machine-read, not owner-supplied**, on the voice record and as a
declared weakness on the registry entry: a misheard word would make the
conditioning slightly less faithful. It is worth his eye.

---

## One defect found and fixed before either run

The adapter held **one** clone-prompt path for all voices. The library keys its
in-context-learning cache on the reference text and a fingerprint of the
reference waveform, and the runner loads any stored prompt under the *current*
key — so with a second voice installed, one voice's stored codes could have been
loaded under the other's key. Val would have spoken in the wrong voice while
every digest in the record still looked right.

The prompt path is now derived from the reference digest
(`clone-prompt-<sha[:16]>.npz`), so it is unrepresentable rather than guarded
against, and `test_two_voices_never_share_a_clone_prompt` holds it there.

---

## Verification sample — **PASS**

One Base generation from the authorised reference and its explicit transcript.
The clone prompt was created here:
`91e771021f5e7a38836ccece17a95b79d49a41d330388bcb3b9286b3333427a1`.

> The image, video, and audio systems are ready, my lord. I can begin whenever you
> wish.

24 kHz mono, **4.720 s**, peak 0.6508, **zero** samples at full scale, **no
interior silence**, 0.489 s leading. Local Qwen3-Omni heard it back **word for
word exactly**, 16 of 16, no repetition, $0, local — content only, never voice
quality or identity.

`val-established-check.wav`

## Production smoke — **PASS**

Through the real composition root (`val_gateway.startup.start`), nothing
injected, no startup warnings. Voice wired automatically: **`val-established-v1`**.

> **Val, in text:** "My lord, the local systems are prepared for operation."
> **Val, aloud:** the same sentence.

Speech took 6.81 s. 24 kHz mono, **3.360 s**, peak 0.7276, zero clipping, no
interior silence. Qwen3-Omni heard all 9 words exactly. `final_text` on the
record equals the persisted message **verbatim**.

**The clone prompt was `91e77102…` — byte-identical to the verification sample's.**
Reused, not recreated: the identity anchor is real rather than intended.
**VoiceDesign did not run.**

`val-established-production-smoke.wav`

### Negative proof

| | |
|---|---|
| provider calls in the speech interval | **0** |
| local TTS cost | **$0.000000** |
| ElevenLabs *generation* calls | **0** — the recording was read from disk; ElevenLabs was never contacted |
| cloud TTS calls | **0** |
| Whisper / cloud STT | **0** — the transcript came from the admitted local route |
| training, fine-tuning, benchmarking or dataset collection | **none** |
| processes sampled | 599 |
| local speech runtime observed | `~/.val-runtimes/mlx-audio-venv/bin/python` |

**The same substring false positive as before, stated rather than glossed:** the
sampler flagged `/usr/sbin/KernelEventAgent` against the needle `eleven`, because
those letters occur inside *Kern**elEven**tAgent*. It is a macOS daemon. The
negative is also proved structurally — a test tokenises the provider module,
strips comments and docstrings, and asserts the executable code contains no
`eleven`, no URL, no HTTP client and no second executable.

---

## What is and is not claimed

**Established:** production speech is conditioned on Val's established voice
reference, and the same conditioning is reused across utterances.

**Not established, and not claimed:** how closely the result resembles that
reference. No similarity score was measured, no speaker-recognition model was
added to grade this one, and Qwen3-Omni was asked only whether the right words
were said. **The judgement is his listening judgement.**
