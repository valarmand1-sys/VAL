# Live voice mode, work package 2 — latency gate, speech delivery, interruption — 23–24 September 2026

Val speaks, and stops when he does. This package built and shipped the **output
half** of live voice mode, repaired one narrow integrity defect left by work
package 1, and put a bounded reasoning-effort latency measurement in front of Lord
Armand before any of it.

    Core's visible response stream → the exact speech segmenter
      → the established local voice → progressive ephemeral audio
      → delivery-state truth → interruption / barge-in

Not built, and belonging to work package 3: the desktop Voice control, AudioWorklet
and device capture, real speaker output acceptance, and the acoustic
echo-cancellation test. **No claim is made anywhere here about when a physical Mac
speaker falls silent.**

---

## 1. First priority — the bounded GPT-OSS reasoning-effort measurement

**Production text cognition remains `gpt-oss-20b-mxfp4-mlx-lmstudio-partner` at
MEDIUM.** Nothing in this package changed it, and nothing here recommends changing
it. The measurement exists so that a later decision can be an informed one.

**The path, and what it deliberately excluded.** All three calls ran on the
governed ordinary evaluation path — `open_turn` / `assemble_turn` /
`CandidateGateway.converse_candidate` / `settle_turn` on the scratch store, the
active persona whole, the Core envelopes, the exact local preflight. **No metered
classification call, no strip call, no blind-position call**, and no live-store
conversation: the probe never enters the deliberated path, which is what keeps it
local and $0 and what puts both efforts on one identical request. Measured cost:
**$0.000000**, both calls `LOCAL_NO_METERED_COST` at a known zero.

**The LOW configuration is a separate, evaluation-only registry entry.**
`gpt-oss-20b-mxfp4-mlx-lmstudio-low`, `NOT_ADMITTED`, **no capability profile**,
carrying a `PARTNER` qualification target only because the candidate lane needs
one to open. The production MEDIUM entry was not touched, and the 16 September
evaluation MEDIUM entry — same artifact, same effort, same window — is what MEDIUM
was measured on. A test asserts mechanically that the two measured entries differ
in `reasoning_effort` **and in nothing else** but their identity fields.

**The warm-up was real, and is recorded as real.** One preliminary call at
**MEDIUM**, on the same A1 request, so the measured pair did not compare a cold
state against a warm one. It reached the local provider, so it left an ordinary
`model_calls` row under the evaluation configuration like any other call — it is
not an "unrecorded model call", and it is marked `warm_up` with
`excluded_from_comparison: true` in the evidence. It is **not** one of the measured
results and is **not** in the comparison. No claim is made that LM Studio does
prompt-prefix caching; the warm-up controls for the warm/cold/JIT state that
demonstrably exists.

The runtime was brought up through the adapter's own supervisor — the same method
the production path calls before any call on this route — naming the registered
32,768-token context. It reported `server_found_running: true`,
`model_found_loaded: true`.

### The measured pair, A1

Frozen A1 prompt, verbatim from the order. Persona v1.9 (source digest
`33831189…`, identical to production's active revision). Exact preflight 5,752
prompt tokens against a 32,768 loaded context on both calls.

| | MEDIUM | LOW | LOW faster by |
|---|---|---|---|
| Request start → first provider chunk (of any channel) | 7.591 s | 7.661 s | −0.070 s |
| Request start → first hidden-reasoning chunk *(timestamp only)* | 7.591 s | 7.661 s | — |
| **Request start → first Core-visible text** | **10.754 s** | **8.013 s** | **2.741 s / 25.5 %** |
| **Request start → first complete speech-safe boundary** | **11.108 s** | **8.206 s** | **2.902 s / 26.1 %** |
| Generation complete | 18.851 s | 13.487 s | 5.364 s |
| Total latency (Core call) | 19.054 s | 13.691 s | 5.363 s / 28.1 % |
| Prompt tokens | 5,752 | 5,752 | — |
| **Hidden reasoning tokens** | **195** | **20** | — |
| Visible tokens | 519 | 361 | — |
| Visible characters | 2,426 | 1,836 | — |
| Visible-token throughput | 27.24 /s | 26.37 /s | — |
| Cost | $0.000000 | $0.000000 | — |
| Terminal state | `complete` | `complete` | — |
| Provider-reported model | `openai/gpt-oss-20b` | `openai/gpt-oss-20b` | — |

**Prompt processing / prefill: NOT DIRECTLY OBSERVABLE.** The local server reports
no separate prefill figure, so no prefill number is invented by subtraction. What
*is* observable is the request-start-to-first-generated-chunk boundary, given
above; on both calls the first chunk was a hidden-reasoning chunk, which is where
generation actually begins. **No hidden reasoning text was read, stored or
printed** — only the timestamp of its first chunk and the runtime's token count.

**The exact answers** are in `runs/2026-09-23-gpt-oss-effort-latency/results-latency.json`.

### Section 2.5 — **triggered**

LOW met two of the three conditions: first Core-visible text **25.5 %** faster, and
the first speech-safe boundary **26.1 %** faster. It did **not** meet the 3.0-second
absolute condition on either (2.741 s and 2.902 s). One condition is enough, so
Section 3 ran automatically.

This is a gate on whether further evaluation was worth the time. It is not an
admission threshold, not a quality threshold, and not permission to change
production.

**What the arithmetic says about speech, which is why the order put it first.**
Streaming TTS cannot make Val speak before Core has usable prose. On MEDIUM the
first speech-safe boundary arrives 11.1 s after the request; on LOW, 8.2 s. Speech
delivery can only work on what comes after that.

---

## 2. Section 3 — the paired current-system comparison

**This is a comparison baseline for LOW. It does not reopen, repeat or revisit
GPT-OSS MEDIUM's qualification or its production admission, and it cannot change
MEDIUM's standing.**

The frozen twelve-task, sixteen-turn Stage A corpus of commit `60b65b7`, run once
at MEDIUM and once at LOW, on the **current** system — persona v1.9, current Core,
same artifact, quantization, runtime, 32,768 window, sampling and output ceiling.
Only reasoning effort differed. Both runs used the original Stage A harness
unmodified, on its ordinary evaluation path: **no classification, strip or
blind-position call**, every task isolated, $0.

No task prompt or mechanical check was modified. Nothing was tuned between cases.
**No quality score was computed, GPT-OSS was not asked to grade itself, no cloud
judge was called, and no winner is declared.**

| | MEDIUM | LOW |
|---|---|---|
| Turns answered | 16/16 | 16/16 |
| Frozen checks met, as measured | 41/44 | 40/44 |
| First-visible text, median | 16.202 s | 8.293 s |
| First-visible text, mean | 16.61 s | 8.63 s |
| Total, median | 19.302 s | 11.696 s |
| Total, mean | 20.18 s | 12.94 s |
| Hidden reasoning tokens, total | 8,427 | 581 |

**Three checks differed. Two are LOW's, and one of those matters.**

- **F1 T2, correction preservation — LOW failed.** The owner says the pub fell
  through and the dinner is now at the barn. LOW's redraft names the venue as *"The
  Barn (previously the Fox & Hounds)"* — putting the withdrawn venue back into the
  invitation he would send. MEDIUM dropped it. This is squarely one of the named
  weakness classes, and the frozen `excludes_all` check caught it.
- **B1, instruction boundaries — LOW failed.** The requirement named *7am to 7pm*
  and *after 6pm*; LOW converted all three to 24-hour time, which is why
  `contains_all` reports `missing ['6']`. LOW also appended *"Please let me know if
  any additional details are required."* to a task that said *give me the message
  only, nothing before or after it*. MEDIUM met both.
- **A2 — MEDIUM failed, and the check is the reason.** MEDIUM italicised the word
  *Ledger* and the frozen `no_stage_directions` rule matched the italics. That is
  the check finding formatting, not a stage direction. Reported exactly as it
  landed and **not re-graded**.

**Shared, and therefore not evidence about effort:** A1 `no_stage_directions`
flagged an italicised phrase in *both* runs; F2 T3 ran to three paragraphs against a
maximum of two in *both*.

**The other named weakness classes, inspected explicitly:** no unsupported factual
invention in either run; no invented access to system logs or observations —
MEDIUM's E2 answer correctly tells the owner to consult *his* logs; no arithmetic
or date error found here (the 16 September finding stands on its own evidence and
is not revisited); no contradiction of supplied context beyond F1 T2; no material
omission beyond B1.

**What this does not establish.** Sixteen turns per effort is one paired run, not a
distribution. Neither LOW's two failures nor MEDIUM's one is shown to be
reproducible, and the corpus was never built to measure reasoning effort. Neither
effort refused or truncated, and no hidden-reasoning marker reached a visible
answer.

**Owner review packet:**
`docs/reviews/qualification/runs/2026-09-23-gpt-oss-effort-paired/review-packet.md`
— the two answers side by side for all sixteen turns, with the checks, the
differences, and the latency each effort bought.

**PRODUCTION REMAINS MEDIUM, pending Lord Armand's ruling.**

---

## 3. The recognizer model-integrity cache — repaired, and a false test replaced

**The defect.** `verify` cached a successful digest against the file's *path*. A
model file replaced after the first successful verification was accepted for every
later voice session without being read. The module's stated guarantee was stronger
than its behaviour.

**The repair.** A digest is now remembered against the file's observed identity —
`st_dev`, `st_ino`, `st_size`, `st_mtime_ns`, `st_ctime_ns` — together with the
admitted digest. Any change in any field means the file is hashed again; a mismatch
refuses before the recognizer starts. `st_ctime_ns` is the field that closes the
gap, because an in-place edit whose size and modification time are restored still
moves the inode change time and nothing in user space can put it back. A
replacement moved into place is caught through inode identity. The file is
re-stat'ed after hashing, so a file that changed *while being read* is not
remembered under a fingerprint describing neither version. An unchanged file is
still hashed only once, so the 488 MB model is not re-read per session.

**The false test.** The old test ended in `verify(file, digest), "..."` — a bare
tuple expression, which asserts nothing — and the behaviour it appeared to bless
was the wrong one. It is replaced by five tests that assert: an unchanged
fingerprint reuses the cache (proved by *counting reads*, not by timing); a
same-size substitution with the modification time restored is rehashed and
**refused**; a rename-over replacement is caught through inode identity; a size
change and an mtime change each invalidate on their own; and a digest mismatch
starts **no recognizer process**.

---

## 4. The exact speech segmenter

`packages/policy/src/val_policy/speech_segments.py`. The contract is one sentence:

> every segment is a contiguous slice of the visible response, the slices are in
> order, and together they cover it completely.

Segments carry `start`/`end` indices into the answer, so the raw slices reassemble
it **byte for byte**; `text` is that slice with boundary whitespace trimmed. Nothing
is paraphrased, summarised, rewritten, reordered, normalised, padded with filler or
dropped, because a slice of a string cannot be any of those things.

Boundaries, at the **earliest** stable one of either kind: a sentence ending that
really ends a sentence — not an abbreviation, an initial, a decimal point or an
ellipsis mid-thought — or a `;`/`:` a reader pauses at. A sentence that grows past
220 characters is cut at a comma, a dash or, failing those, a word gap; never
mid-word, and never past 420. The first segment may be short so Val begins speaking
promptly; later ones must reach 40 characters, so a full stop after two words does
not become its own utterance. The terminal suffix is flushed exactly.

**Text Core withheld stops speech rather than being filtered.** The verdict marker
and the hidden-reasoning markers raise, because their arrival would mean a boundary
upstream had failed and quietly stripping them would hide that. A marker split
across two deltas is still caught.

39 tests, including the invariant checked at **every chunk size from 1 to 39** — a
boundary rule that only works when a sentence arrives whole is not a boundary rule.

**One defect the tests found:** `flush` emitted an empty segment for a
whitespace-only tail, which would have been handed to the voice. The whitespace now
joins the previous segment's slice, so nothing empty is spoken and coverage still
holds.

---

## 5. Progressive delivery, in the established voice

`packages/gateway/src/val_gateway/delivery.py`. Val's voice is
**`val-established-v1`** on `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit` through
the existing conditioning path and the existing per-reference clone prompt.
VoiceDesign does not run, no new voice was created, the reference and its
transcript are untouched, ElevenLabs was not called, no cloud TTS was called, and
no other TTS was benchmarked or compared. That question is closed and was not
reopened.

**Phrase-level progressive generation.** As soon as the segmenter has a stable
speech-safe segment it goes to the local voice on a worker and its audio to the
sink, while Core keeps writing. **Native per-token Qwen3-TTS streaming was not
used**: the installed Base/ICL route exposes no such path, and mlx-audio was *not*
upgraded to obtain one — the order forbids it and the voice is not changed for
speed.

**A route that cannot stream still speaks.** `finish(settled_text)` takes Val's
persisted answer as authoritative: if no delta arrived, that answer is spoken then
(not progressively — a latency loss, not a silence). If deltas did arrive and the
streamed text differs from the persisted answer in anything but boundary
whitespace, delivery **fails with that named reason** rather than speaking words the
record does not hold. This was found by a test, not by reasoning: the first version
would have left a non-streaming route silent.

---

## 6. Live speech is ephemeral

The `EphemeralSink` holds the piece currently being delivered and nothing else,
replacing it as delivery moves on and releasing it at the end. **There is no file
write anywhere in the delivery module** — a test tokenises it and asserts that
`write_bytes`, `write_text`, `NamedTemporaryFile`, `mkdtemp`, `wave` and `open(`
appear nowhere in its executable code.

Migration `0029` made the truth representable rather than fabricating a path:
`speech_generations.audio_path` is now nullable, with a companion
`audio_retained` held to it by a check constraint, so a row can neither claim a
file that does not exist nor hide one that does. Historical qualification and
verification samples keep their paths and read exactly as they did. The digest,
duration and byte count stay on an ephemeral row: they are facts about audio that
really was produced and remain true after the bytes are released.

---

## 7. Delivery truth, and the boundary at the first audio

`speech_deliveries`, append-only: one row per transition, each carrying the exact
prefix delivered at that moment. A delivery's state is its highest-numbered row.
There is no UPDATE, so `interrupted` cannot quietly become `completed` — the
database refuses both UPDATE and DELETE, and a test proves it. The five states are
distinct: `not_started`, `started`, `completed`, `interrupted`, `failed`. A state
and its reason cannot disagree (`reason` is required for the last two and forbidden
for the others), and a `not_started` row cannot claim anything delivered.

**The delivered boundary is the first audio, not the last.** From the moment the
first piece reaches the sink, `VoiceTurn.delivered` is true and work package 1's
resume-before-delivery merge is closed: what he says next is a reply, not the rest
of his own sentence. Work package 1's explicit
`POST /voice/sessions/{id}/delivered/{message_id}` remains available for a layer
that delivers outside this machinery.

**Delivery is keyed on Val's answer, not his message.** A defect the tests caught:
the first version of the service view looked delivery up by the owner's message id
and found nothing. `VoiceTurn` now carries `answer_message_id` for exactly this.

**The next turn does not assume he heard the rest.** The record-state envelope
gains an additive `spoken_delivery` field, present **only** when an answer in this
conversation ended short, naming its position, its state, how much he heard and how
much was written, with a note that says plainly: *do not assume he knows the part he
did not hear.* The assistant message is never rewritten, no second conversation
history exists, and a conversation that was never spoken aloud carries no such
field at all.

---

## 8. Interruption and barge-in

On the recognizer reporting the owner speaking while delivery is live, the session
interrupts: the sink is stopped first, queued segments are discarded, no further
synthesis starts, and the exact delivered prefix goes on the record. **Nothing
already executed is undone** — a test records a consequential `execution_events`
row before the interruption and asserts it still stands afterwards. Val's own
output is never treated as owner speech.

**Service-side cancellation (§13.1):** from the recognizer's `speech_start`
reaching delivery control to the in-memory playback sink being stopped.

| Measurement | Result |
|---|---|
| Deterministic test, against the 300 ms target | **0.008 ms** |
| Production smoke, real recognizer, real voice | **0.008 ms** |

**This is not a claim about physical Mac speaker stop latency.** It is the
service-side control interval. The room belongs to work package 3.

**§14, and only what §14 permits claiming.** Proved logically: the sink's
executable code contains no `feed` and no reference to a recognizer, and the
session feeds the recognizer from exactly one place — the caller's PCM — so
playback bytes cannot be reintroduced as owner speech. A synthetic owner
`speech_start` interrupts playback, in the deterministic test and in the smoke. **No
claim is made about real speaker echo triggering the microphone**; that needs the
speakers and is Lord Armand's acceptance in work package 3.

---

## 9. The concurrent machine-fit gate, and the end-to-end smoke — one run

`docs/reviews/qualification/runs/2026-09-24-voice-delivery-smoke/`. Everything real
except the database — the scratch store deliberately, because a proof does not write
into his conversation history. Real composition root, real gateway, real production
recognizer, real production MEDIUM GPT-OSS, real `val-established-v1` Qwen3-TTS,
ephemeral in-memory sink. No startup warnings. Two turns.

**Turn 1 — spoken to the end.** Frozen fixture `frozen-utterance.wav` → transcript
**`And so, my fellow Americans,`**, exact. Val's answer: *"Good evening. It appears
your remarks were cut off—may I ask what matter of the house you wish to
address?"* Two segments (`sentence`, `flush`); **the segments reconstruct the
answer exactly** and the delivered prefix equals it. 6.00 s of audio delivered,
sink holding 0 bytes afterwards. Record: `completed`, 106 characters delivered, 2 of
2 segments, 3 events.

**Turn 2 — barge-in, through the real recognizer.** The fixture was fed again as
soon as the first audio was out, so whisper.cpp detected real speech and the
session interrupted on its own control path. Val generated 136 characters; **he
heard 75** — *"My lord, you have quoted a line that often begins an address to the
nation."* — 1 of 2 segments. Record: `interrupted`, reason *the owner began
speaking*, 3 events. The next turn is told: `interrupted`, 75 of 136 characters.

**§16's reportable intervals, labelled exactly as the order requires.**

| Interval | Turn 1 |
|---|---|
| Request start → first Core-visible text | 28,648 ms |
| **End of input-fixture speech → first audio ready at the production speech-delivery boundary** | **38,708 ms** |
| **First Core-visible text → first audio ready** | **8,578 ms** |
| Delivery elapsed | 41,274 ms |

**The physical first-audible timestamp is not reported and is not claimable**: the
production device playback surface is work package 3. These are service-side
figures at the in-memory delivery boundary.

Latency is not optimised in this package and these figures are not offered as
acceptable. They are what happened, with a local partner call, a cloud
classification call and local TTS all on one machine at once.

**Machine fit — PASS on the order's stated criteria.**

| | |
|---|---|
| Memory before | 31.03 GB free (64.6 %), wired 3.00 GB, swap used 1,900.6 MB |
| Lowest free during the run | **25.1 %** |
| Highest swap used | 1,900.6 MB |
| **New swap created** | **0.0 MB** |
| Memory after | 29.78 GB free (62.0 %), wired 2.97 GB, swap used 1,900.6 MB |
| Samples | 32, every 2 s |

GPT-OSS resident at 32,768 throughout, the whisper.cpp session alive, Silero VAD on
the CPU, Qwen3-TTS conditioning ready and speaking. Nothing was killed, nothing
OOM'd, swap after equals swap before, and all three components were still
functional at the end — GPT-OSS answered turn 2, the recognizer heard the barge-in,
the voice spoke both turns. **The 25.1 % figure is reported as measured**; it is
lower than the 70 % floor the perception gate used, and the order's criterion here
is a different one — no unsafe sustained pressure and no operationally significant
new sustained swap — which this run meets with zero new swap.

**Negative proof.**

| | |
|---|---|
| Columns scanned for the owner's audio | **135** — none contains it |
| Audio paths written | **none**; every generation row `audio_retained = false` |
| Local speech cost | **$0.000000** |
| Cloud STT calls | **0** |
| Cloud TTS calls | **0** |
| ElevenLabs generation calls | **0** |
| VoiceDesign runs | **0** |
| Total provider cost, both turns | **$0.001692** — two cloud classification calls at $0.000846 each; both local cognition calls and all three speech generations cost nothing |

One curiosity, stated rather than left to be noticed: two different segments
recorded the same `audio_bytes` (226,604) and the same 4.720 s duration. Their
digests differ (`870dd278…` and `830ca3b8…`), so they are different audio; the equal
lengths are the 12 Hz frame step landing on the same frame count for two utterances
of similar length.

---

## 10. Speculative decoding — the read-only check, §20

**Read-only, and nothing else:** no download, no configuration change, no runtime
change, no inference call, no LM Studio restart. The server's own model listing was
read once over loopback with the existing token.

**NO COMPATIBLE PATH.** The exact runtime reasons:

1. **Nothing to draft with.** The machine holds two models and neither is a
   speculator: no EAGLE-3-style GPT-OSS speculator, no DFlare-style draft model,
   and no smaller `gpt_oss`-architecture model that could serve as an ordinary
   draft. A speculative path needs a second model this machine does not have, and
   obtaining one is a download, which this check forbids.
2. **No contract to carry it.** Val's inference path is OpenAI-compatible
   chat-completions through the `lmstudio` adapter, whose request contract is
   pinned and refuses any field it does not transmit. There is no `draft_model` or
   speculative field in it, and adding one would be changing the established
   inference contract — which §20 excludes.
3. The resident model is `openai/gpt-oss-20b`, MXFP4, `compatibility_type: mlx`,
   `arch: gpt_oss`, loaded at 32,768 of a 131,072 architectural maximum.

No search was extended beyond the already-identified possibilities, nothing was
downloaded, and this check delayed nothing.

---

## 11. Tests

**No existing test was weakened.** Three existing files changed, each for a stated
reason rather than to accommodate a failure:

- `packages/gateway/tests/test_voice_input.py` — its `submit` closure gained the
  `on_delta` keyword, because progressive speech needs Core's visible output as it
  is produced. Every WP1 assertion is unchanged and all 28 still pass.
- `packages/gateway/tests/test_candidate_lane.py`,
  `packages/gateway/tests/test_evaluation_door.py`,
  `packages/domain/tests/test_registry_evaluation.py`,
  `packages/domain/tests/test_local_hosting.py` — enumerating pins, moved to
  include the new evaluation-only LOW entry with the reason recorded beside it.
- `packages/domain/tests/test_schema.py` — the hand-transcribed schema, which had
  to gain `speech_deliveries` and the three new `speech_generations` columns.
- `packages/providers/tests/test_whisper_recognizer.py` — the false cache test
  replaced (§3).

**New, 80 tests, and one false test removed.** Three new files:
`packages/policy/tests/test_speech_segments.py` (39),
`packages/gateway/tests/test_speech_delivery.py` (25),
`packages/policy/tests/test_effort_evaluation.py` (6). Five added to
`packages/providers/tests/test_whisper_recognizer.py`, which replace the one that
asserted nothing (13 tests → 17). Five added to
`apps/api/tests/test_voice_service.py` (11 → 16).

**Full mirror, as CI runs it:** 1,344 (no-database job) · 380 domain · 821 gateway ·
249 providers · 96 API. Lint, format, types, secrets, pins, scope ruling and
dependency direction all green. Migration `0029` proved reversible down to `0028`
and back, and the domain suite migrates from empty to head.

**Two defects the tests found before they could matter**, beyond the two already
named in §4 and §5:

- **A five-minute pause after every voice failure.** When a segment failed, the
  synthesis worker left with segments still queued, and `_drain` waited out its
  entire 300-second timeout for a queue nobody would ever read. A closed delivery
  is no longer drained. Found because one test took 300 seconds.
- **A second added to the end of every spoken answer.** The worker's queue poll was
  one second, so `finish` waited up to that long after the last segment. It is now
  100 ms.

---

## 12. Deployment

| | |
|---|---|
| Live store | `0028_voice_input` → **`0029_speech_delivery`**, through the explicit `-x deploy=live` path |
| Live voice tables after deployment | `speech_deliveries` 0 rows; no ephemeral `speech_generations` rows |
| Persona | v1.9 revision 8, untouched |
| Production cognition | `gpt-oss-20b-mxfp4-mlx-lmstudio-partner`, MEDIUM, 32,768 — **untouched** |
| Production voice | `val-established-v1` — untouched |

---

## 13. What is not claimed

- **Physical speaker latency, and physical speaker stop latency.** Every timing
  here ends at the in-memory delivery boundary. Work package 3 adds the audible
  moment.
- **Acoustic echo cancellation.** Not tested. The loopback proof is logical and
  says so.
- **That LOW should be production.** It is faster on this measurement and it lost
  two frozen checks MEDIUM met, one of them a correction-preservation failure.
  Production remains MEDIUM, and the decision is Lord Armand's.
- **That latency is acceptable.** 28.6 s to first visible text and 38.7 s to first
  audio on the smoke's first turn are reported because they are what happened.
  Latency optimisation is excluded from this package.
- **Any reproducibility claim about the paired corpus.** One run at each effort.
- **Desktop capture.** No Voice button, no AudioWorklet, no microphone capture. The
  service receives PCM from a caller that does not yet exist in the shell.
