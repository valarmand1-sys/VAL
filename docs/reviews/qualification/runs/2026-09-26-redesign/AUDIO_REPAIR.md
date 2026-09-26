# The audio regression: cause and repair — 26 September 2026

Owner order "IMPLEMENT AND QUALIFY THE LOCAL CONVERSATIONAL LATENCY REDESIGN", §8. His
physical test of the streamed build (`109e14b`) had clicks and altered audio quality.
This is a production correctness repair under the order's standing authorisation. The
files are in this directory.

## Two causes, both found

### 1. The streaming decoder started every sentence cold (`decoder_compare*.py`)

Method: the same speech codes for both paths, by seeding the sampler; only the decoder
path differs. Whole decode (the accepted, pre-streaming behaviour) against the
library's streaming decode. Log-mel distance per 10.7 ms frame; whole-vs-whole is 0.0.

| | log-mel distance to whole decode (median) | onset RMS, first 60 ms |
|---|---|---|
| cold streaming decoder (what `109e14b` shipped) | 0.11–0.50 | up to 0.065 (whole: 0.0015) |
| primed with last 25 reference codes | 0.08–0.18 | matches whole |
| primed with last 50 | 0.07–0.11 | matches whole |
| primed with all 235 reference codes | **0.000** (0.03–0.07 at 1 s chunk seams) | matches whole |

The library's whole path decodes the reference codes and the generated codes
together, then cuts the reference portion: the sentence is decoded by a decoder
already holding the voice. Its streaming path resets the decoder and decodes the
generated codes alone. The burst at the start of every sentence is the click; the
difference across the whole sentence is the altered quality.

Priming with all reference codes reproduces the whole path but cost 0.57 s per
segment (first piece 0.47 → 1.05 s). So the primed state — the decoder's KV cache and
every buffer its reset clears — is captured **once per reference** and restored per
segment (`decoder_snapshot.py`): restored generation is sample-identical to freshly
primed generation (four seeds, max difference 0.0), restore costs ~0.1 ms, and the
first piece is back to 0.45–0.48 s. The library file is untouched; the runner wraps
the decoder's own reset.

### 2. Each piece was decoded and scheduled on its own (desktop)

The player decoded each ~1 s WAV piece with `decodeAudioData`, which resamples each
piece independently to the context's rate, and scheduled it as its own source node —
a resampler restart and a scheduling edge at every seam. Not measurable from here (it
happens inside the desktop's audio engine), but a known mechanism for exactly this
symptom, and removed rather than argued about: a playback worklet now receives every
piece's samples and writes them to the device as one continuous signal; the context
is asked for the speech's own rate (24 kHz), and where the platform grants another
rate the worklet's resampler carries its state across pieces.

## What changed

- **Runner** (`qwen_tts_speak.py`): `speak_stream` primes the streaming decoder from
  a captured reference state; the worker primes at start when the governed voice is
  handed to it, and spends MLX's one-time compilation on a discarded short generation
  (never played, written or recorded — the standing the persona prime's discarded
  token has). Readiness at Voice On: 1.1 s → 2.3 s, reported, so that the session's
  first sentence pays neither (first piece 1.07 s → 0.47 s).
- **Desktop**: `public/pcm-playback-worklet.js`, one continuous stream; `speaker.ts`
  decodes WAV from the bytes and feeds the worklet; started/completed/underrun are the
  worklet's own events. Tests run the shipped worklet itself.
- **Feedback** (§8): the session reports the accepted turn's stage — thinking,
  writing, voicing, speaking — from its own facts, and whether his next words are
  queued behind it; the desktop shows it and it clears itself. It makes nothing faster.

## Status

Waveform checks and the real-worklet tests establish that the streamed output now
equals the whole decode and reaches the device as one signal. **Whether it sounds
clean in the room is his to judge**; this record claims software equivalence, not
physical acceptance. Fallback if he still hears artefacts: whole-segment synthesis is
the resident worker's path when streaming is unavailable, at 1.1–4.5 s to first audio
instead of ~0.5 s.
