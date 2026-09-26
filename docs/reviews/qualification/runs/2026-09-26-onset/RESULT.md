# Reducing the wait before Val speaks — 26 September 2026

Owner order "REDUCE THE WAIT BEFORE VAL SPEAKS: COMPLETE REPAIR ORDER", an execution
pass. The starting point is `0f44d20` (production: desktop `e866a09`, service code
`642cb35`). The baseline is his 23:03 turn (WP3 Record §23): 18.0 s from speech end to
playback, including a 5.30 s first synthesis. **WP3 remains PARTIAL.**

## 1. First synthesis: contention, and a supported fix (`onset_probe.py`, `tts_side.py`)

Method: the same two first-segment texts (the 23:03 opening, 107 characters; message 8's
opening, 121), the resident model loaded once, the governed conditioning through the
stored clone prompt, three repeats per condition. "Under load" means GPT-OSS (the
production instance, parallel 1) generating an answer at the same time — the real
situation, since her first sentence is voiced while the rest of her answer is still
being written. Local, $0.

| | whole, alone | whole, under load | streamed first audio, alone | streamed first audio, under load |
|---|---|---|---|---|
| 107 chars | 2.64–2.77 s | 4.35–4.61 s | 0.48–0.49 s | 0.74–0.75 s |
| 121 chars | 2.85–3.17 s | 4.85–5.38 s | 0.48–0.49 s | 0.74–0.74 s |

**Contention is demonstrated in both directions:**

- Synthesis is 1.7–2.3 s slower under load.
- GPT-OSS streamed 55–61 chunks/s before speech, 41–44 while a whole sentence was
  voiced, and 48–49 while a streamed one was.

Serialising would not help: her text would wait for the voice, or the voice for her
text.

**The fix is the installed library's own incremental audio** (mlx-audio 0.5.5,
`_generate_icl(stream=True)`). Every `streaming_interval` of speech tokens is decoded by
its stateful streaming decoder and yielded. This is genuine incremental synthesis, not
a finished file sent in chunks.

- **Keeps ahead of playback:** at a 1.0 s interval, a whole sentence finished in
  3.4–4.7 s under load for 5.6–7.9 s of audio.
- **No seam:** chunk-boundary sample steps were 0.009–0.10, within the waveform's own
  99.9th-percentile step of 0.10–0.21.
- **Pace unchanged:** audio length per character is the same.
- **Real-model check** through the new provider path: first piece at 0.49 s, then
  pieces every 0.28 s, each carrying 0.96 s of audio. The reassembled waveform matched
  the runner's digest, and the stored clone prompt was the same as before.

## 2. What was repaired

1. **Streamed first audio.** The chain is: runner `speak_stream` mode (resident worker
   only; pieces go out as base64 WAV lines on stdout, and nothing is written to a file)
   → provider `synthesize_stream` (whole rebuilt in memory and checked against the
   runner's digest) → delivery (each segment's first piece is the delivered boundary; a
   closing empty piece ends the segment; recorded once per segment) → API (`chunk`,
   `last`; `available_to_desktop` once per segment) → desktop player (the pieces of a
   segment are scheduled back to back on the audio clock; a segment starts once,
   completes after its last piece, the next waits; a stop silences everything
   scheduled).
   - **Fallbacks:** with no resident worker, or a failure before the first piece, the
     segment is voiced whole as before. A failure part-way is a delivery failure, never
     a silent hole.
   - **Queue:** the hand-off queue deepened from 8 to 64, since a dropped piece would be
     a hole in a sentence.
2. **Resume held while he is still speaking.** A settled utterance is not submitted
   while speech that began inside its grace window is still being heard. This
   implements the existing resume rule; it is not a new one. His 20:15 case (resumed
   0.5 s after he stopped, then queued 41 s behind a half-question's answer) now yields
   one message and one answer.
3. **`spoken_path` facts gated.** The 470 tokens (the house's own tokenizer) are now
   included only when the turn asks about speed, timing, voice or the path
   (`val_policy.spoken_path`: broad stems, failing toward inclusion). The decision is
   logged either way.
4. **Provisional-timing error.** The figure is taken only when the session's settled
   words are his current utterance's, never while he is speaking again over a turn
   still in flight. That was the −4,239 ms. This is a correctness repair, not a speed
   repair.

## 3. Net result (`measure.py`, `drive_session.py`, `comparison.txt`)

The real service on the scratch store, the production model instance (resident, parallel
1, persona primed), and the resident voice worker ready. Three Voice sessions of three
turns each, per build, with the same phrases:

1. "Good evening, Val." — a normal turn with no previous answer;
2. the 23:03 request for "a detailed summary of what we accomplished with voice
   today…" — a substantive answer;
3. "What is the tuning on that? How fast are you supposed to respond…" — a subsequent
   turn in the ready state.

One discarded warm-up session preceded the runs; $0.

| median (range), n = 9 | before `0f44d20` | streamed | streamed + gate |
|---|---|---|---|
| speech end → first playback | 12.58 s (7.73–17.44) | 8.78 s (5.99–15.98) | 8.98 s (7.08–10.96) |
| his message committed → first playback | 10.48 s (5.62–15.31) | 6.77 s (3.88–13.87) | 6.87 s (5.05–8.83) |
| his message shown → first playback | 10.47 s (5.61–15.29) | 6.75 s (3.87–13.85) | 6.86 s (5.04–8.81) |
| first answer text → first playable audio | 2.10 s (1.21–5.03) | 0.96 s (0.51–1.02) | 0.82 s (0.50–1.13) |
| first segment ready → first playable audio | 2.02 s (1.14–4.52) | 0.76 s (0.51–0.77) | 0.76 s (0.50–0.77) |
| model time (first output + hidden reasoning) | 5.51 s (3.68–13.20) | 5.80 s (3.39–12.89) | 6.40 s (4.45–7.95) |
| **total less model time** | **4.24 s (3.28–7.14)** | **2.98 s (2.54–3.18)** | **2.98 s (2.58–3.26)** |
| joins with a gap over 50 ms | 4 of 49 (max 5.28 s) | 0 of 35 | 0 of 73 |
| underruns | — | 0 | 0 |

**What is claimed:**

- The part of the wait that is not model work fell by a median of 1.26 s, and the
  before and after ranges do not overlap.
- First answer text → first audio fell by about 1.1–1.3 s at the median. For long
  openings it fell from 3.5–5.0 s to under 1.1 s.
- The gate removed 0.6 s from request → first model output on turns that do not ask
  (turn 1: 2.26–2.31 s → 1.64–1.70 s). Turns that ask still carried the facts: logged
  "included" 6 times and "not_run" 3 times.

**What is not claimed:** the difference in total medians beyond this. Hidden reasoning
varied 1.1–10.8 s between answers and is unchanged work.

**Resume case** (pause 1.0 s, long enough that the recognizer splits the speech, short
enough that he is still speaking when the grace expires):

- **Before:** two owner messages, "Do you know of any way to increase the speed…" and
  "I would like it a little bit faster…", each answered separately.
- **After:** one message, answered once, with first playback 9.8–11.5 s after he
  stopped.

A 0.5 s pause was not split by the recognizer in either build, and is not counted.

**Machine:** lowest free memory 25–51% across runs, no swap growth, and the resident
voice worker at 3.19 GB was gone after each session.

## 4. Remaining, and why ordinary repair cannot remove it

- **Hidden reasoning at MEDIUM** (3.4–13.2 s of model time across these runs) is model
  work. It is kept, not truncated, and LOW is not reopened.
- **Request → first output, 1.6–3.1 s:** the conversation history is recomputed every
  turn, because only the persona prefix is reused (WP3 §21–§23). Removing it needs
  conversation-content priming, which is not authorised in this pass. The isolated
  experiment is specified in WP3 §23, and its 1.2–1.8 s is an estimate.
- **First sentence → first audio, 0.50–0.77 s:** the first second of audio and the
  poll. This is close to the floor for this voice model.
- **Speech end → his message, ~2.1 s:** confirmation and resume grace, unchanged by his
  order.
- **Barge-in while she is thinking** (23:03): her voice for the silenced answer stops,
  but its cognition runs on (~3.5 s there) before his new words are submitted. Removing
  that wait changes turn-taking or the record (see WP3 §24). It is not changed here.

Files:

- `onset_probe.py`, `tts_side.py`, `onset-probe.json` (§1);
- `measure.py`, `drive_session.py` and `serve_variant.py` (copied from the voice-repair
  run; the driver extended for pieces and `A || B`);
- `before-*.json`, `after-*.json`, `comparison.txt`, `summarise.py`;
- `service-timelines.txt` (content-free timeline, prime, warm, endpoint and gate lines
  only).
