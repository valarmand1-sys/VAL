# WP3 — owner silent-listen diagnostic: reconstruction, findings and repairs

Owner order "OWNER DIAGNOSTIC FAILED — STOP ACCEPTANCE AGAIN", 25 September 2026.
Installed build under test: `91693d9`. **WP3 remains PARTIAL.** Nothing here is owner
acceptance, and no owner voice turn was requested to produce it.

Evidence labels, as the order requires: **OBSERVED** (read directly from a retained
record), **DERIVED** (computed, with its basis stated), **NOT RECORDED** (no retained
record holds it; not reconstructed).

---

## 1. What the retained record holds

**OBSERVED — the store holds three spoken sessions on the installed build, not one.**
Between 22:10:55 and 22:14:14 CDT on 24 September (25 September UTC):

| Run | Voice On (`voice_sessions.started_at`) | Owner message (`messages.created_at`) | Canonical text | Val's answer (`created_at`) |
|---|---|---|---|---|
| 1 | 22:10:55.219 | 22:11:02.408 | `evening Val.` | 22:11:14.894 |
| 2 | 22:12:34.416 | 22:12:41.062 | `evening Val.` | 22:12:52.838 |
| 3 | 22:13:30.296 | 22:13:51.079 | `evening Val.` | 22:14:01.205 |

All three dropped "Good". Each recovery-journal row's provisional text is also
`evening Val.` (OBSERVED), so the provisional decode lacked it too. Which run the owner
means as "the diagnostic" is not recorded; **run 3 is the one whose playback timing
reproduces the `17612 ms` he read** (DERIVED, §4), so it is the run reconstructed below.

**OBSERVED — none of the three sessions was ever closed.** All three rows say
`listening` with no `closed_at`; the service log holds no close request for them; and
an hour later the service still held their three recognizer processes (PIDs 38018,
38129, 38194, ~600 MB resident each). See §6.

**What was never retained (NOT RECORDED):** the service log lines carry no
timestamps; the turn's in-process timing marks were discarded unrecorded (the recorder
was inert in production); the desktop console and its timings were not retained; the
delivery's in-memory marks (`first_tts_start_ms`, `cognition_complete_ms`) were never
persisted; no audio and no recognizer input was retained, by rule. The endpoint log
line that *was* retained reported `silence=0.000s` and `length=0.000s` for all three
runs — **those values are artefacts of two defects in my previous pass** (§3.3) and are
treated as NOT RECORDED, not as measurements.

## 2. Run 3 — the timeline, labelled

Clock sources: the store's `created_at` / `recorded_at` are PostgreSQL `now()` on this
Mac's wall clock (**`now()` is the transaction's start**, so a commit is slightly
later); `speech_deliveries.first_audio_ms` / `elapsed_ms` are the delivery's own
monotonic offsets from its creation; the desktop's figures are `performance.now()` in
the webview. The helper's clock is its own: on this machine two processes' monotonic
clocks were checked and **do not share an origin**, so helper marks cannot be placed on
the service clock except through a receipt time (instrumented now, §7).

| Boundary | Value | Label and basis |
|---|---|---|
| Voice On (session object created) | 22:13:30.296 | OBSERVED `voice_sessions.started_at` |
| Warm-ups began / ended | — | NOT RECORDED (no log line existed) |
| Owner speech onset | — | NOT RECORDED |
| VAD speech_start | — | NOT RECORDED (helper event, not logged or stored) |
| Endpoint | — | NOT RECORDED as a time |
| Voiced duration | 0.704 s | OBSERVED log; **excludes the 224 ms admission run** by the code of that build (DERIVED), so VAD-confident speech was ≈ 0.928 s |
| Total utterance / endpoint silence / gap | — | NOT RECORDED (logged zeros are defect artefacts, §3.3) |
| PCM samples for the utterance; first-chunk handling | — | NOT RECORDED. 290 audio requests returned between session open and the endpoint line (OBSERVED count; sizes not logged) |
| Whisper final | `evening Val.` | OBSERVED (the message and the journal) |
| Desktop first saw the settled transcript | ≈ 22:13:50.0 | DERIVED: playback-start report 22:14:07.618 − 17.612 s; cross-clock, ± the report's transit (tens of ms) |
| Resume window | 1.1 s | the configured grace; submission follows it (code) |
| Delivery created (just before submit) | 22:13:51.072 | DERIVED: `completed` row 22:14:12.150 − `elapsed_ms` 21,078 (the `started` row gives the same to the millisecond) |
| **Canonical commit of "evening Val."** | **22:13:51.079** (transaction start) | OBSERVED `messages.created_at`; commit instant NOT RECORDED, and before dispatch |
| Runtime readiness | model already loaded | OBSERVED log line `model_found_loaded=True`, before the completion request |
| Cognition dispatch | ≈ 22:13:51.187 | DERIVED: `model_calls.created_at` 22:14:01.187 (written at completion) − `latency_ms` 10,000 (dispatch → completion) |
| First token / first visible text / first speech-safe segment / first TTS start | — | NOT RECORDED |
| Cognition complete | ≈ 22:14:01.187 | DERIVED as above |
| Val's answer committed | 22:14:01.205 (transaction start) | OBSERVED |
| First audio at the sink | 22:14:07.532 (t₀ + 16.460 s) | OBSERVED `started` row and `first_audio_ms` |
| Segment 1 offered to the desktop | 22:14:07.605 | OBSERVED `available_to_desktop` |
| Segment 1 playback started (software) | 22:14:07.618 | OBSERVED service receipt of the desktop's report |
| Segment 2 offered / started / done | 22:14:12.058 / 12.075 / 14.468 | OBSERVED |
| **The only conversation read** | returned between 22:14:12.075 and 22:14:14.468 | OBSERVED: one `GET /conversations/01a0d68e…` in the whole session, logged after segment 2's start report and before its completion report (uvicorn logs on completion) |
| Read issued / received / React state / DOM / paint | — | NOT RECORDED |
| First physical audible Val speech | — | NOT RECORDED (no acoustic measurement exists) |

## 3. Findings

### 3.1 Why his message stayed invisible — established, and it was my previous repair

**The desktop never issued a read while she was thinking; the service was not
holding one.** The previous pass's trigger keyed on the session's `turns`, and the
session appended a turn only in `_record` — **after `submit` returned, which is after
her answer was written *and* after `delivery.finish` had waited for her voice to
synthesise the whole answer.** An "asked" turn never existed on the real service, so
the trigger could not fire early. For a brand-new chat the session also reported
`conversation_id: null` until then, so the desktop had no conversation to read at all.
Retained evidence agrees exactly: one read, returned ~21 s after his commit, after she
had begun speaking. The previous regression passed because it asserted that a callback
fired over a scripted session in which an "asked" turn existed — a state production
never produced. **The previous pass's claim that the desktop "re-reads as soon as a
canonical owner turn exists" was false.**

**§2.1 candidate (read issued on time, returned late): not what happened in this run.**
No early read exists in the log, and the service kept answering throughout cognition —
81 session polls and 499 audio requests returned between the completion request's
headers and its settlement (OBSERVED ordering). **But the candidate boundary is real**
and was demonstrated by reproduction: the audio route was `async` and did its
recognizer hand-over synchronously on the event loop, so a slow hand-over held every
other request — a conversation read included — until it finished. Repaired (§5).

### 3.2 Why "Good" was lost — before Whisper, at VAD admission

**AUDIO PRESERVATION** (fixture, `onset_probe.py`, reports `onset-probe-*.json`).
Speech synthesised locally by macOS `say` (voices Daniel and Samantha; no owner
audio), placed after a **1.5 s room-noise lead-in (−60 dBFS RMS)**, with the first word's
**first 150 ms ramped from −24 dB to full level** — a low-energy onset. Carried through
the shipped AudioWorklet file run as-is (48 kHz → 16 kHz, 20 ms chunks, continuity
verified), three payload splittings (identical recognizer input in every case), the
helper's own conversion, and the **unmodified helper's own `Listener`**, observed from
outside so the exact array handed to `whisper_full` is compared sample for sample with
the stream.

| Case (unmodified helper at `91693d9`) | True onset → first confident window | → admission | Opening audio lost before Whisper | Whisper result |
|---|---|---|---|---|
| Daniel, listening, low-energy onset | 36 ms | 260 ms | **180 ms** | `evening, Val.` |
| Daniel, listening, natural onset | 4 ms | 228 ms | 148 ms | `Good evening, Val.` |
| Daniel, capture sample zero | 96 ms | 320 ms | 240 ms | `evening, Val.` |
| Samantha, listening, low-energy onset | 36 ms | 260 ms | **180 ms** | `evening, Val.` |
| Samantha, listening, natural onset | 36 ms | 260 ms | 180 ms | `evening, Val.` |
| Samantha, capture sample zero | 32 ms | 256 ms | 176 ms | `evening. Vowel.` |

**The defect:** while waiting for 220 ms of confident speech (seven 32 ms windows,
224 ms) before admitting an utterance, the helper kept only the last `speech_pad_ms`
(80 ms) of *everything* — the confident run included — so the utterance began 80 ms
before the **admitting** window, discarding 144 ms of speech the VAD was already sure
of, plus any low-energy onset before it. The governed setting and the code's own
comment say the pad precedes the **first confident** frame. Same file, same model, same
settings, after the repair:

| Case (repaired helper) | Pre-roll before true onset | Opening audio lost | Whisper result |
|---|---|---|---|
| Daniel, listening, low-energy onset | 44 ms | **0** | `Good evening, Val.` |
| Daniel, listening, natural onset | 76 ms | 0 | `Good evening, Val.` |
| Daniel, capture sample zero | — | 16 ms (see below) | `Good evening, Val.` |
| Samantha, listening, low-energy onset | 44 ms | **0** | `Good evening, Val.` |
| Samantha, listening, natural onset | 44 ms | 0 | `Good evening, Val.` |
| Samantha, capture sample zero | — | 0 | `Good evening, Val.` |

In every already-listening case the true-onset-to-first-confident offset (4–36 ms) is
inside the 80 ms pad. **One measured edge, kept rather than tuned away:** with speech
from the very first sample the helper receives, one voice's first confident window
came 96 ms after onset, exceeding the pad by 16 ms of the −24 dB ramp; Whisper still
heard "Good". The pad is governed configuration and was not changed.

**RECOGNITION, separately.** The complete valid input (from the pad before the true
onset to the end of the speech) given to the **unchanged Whisper Small** returned
`Good evening, Val.` in all six cases. **Whisper Small is not demonstrated to have
erred on complete valid input; the owner-authorisation stop of §6 is not reached.**

**Whether the acoustic "Good" of his run reached Whisper: UNRESOLVED / NOT RECORDED.**
His recognizer input was not retained, by rule, and was not reconstructed. The fixture
shows the mechanism reproduces his exact result; it does not prove what his audio was.

### 3.3 My previous pass's endpoint diagnostics were defective

The helper read the ending silence **after** clearing it (always 0.000 s), and the
length and gap were never on the `final` event that line logged. Both are repaired; the
line now also records which stretch of the stream went to Whisper, in samples.

### 3.4 Latency — what `transcript → audible 17612 ms` is

It started at the desktop's first poll response in which the service held a settled,
not-yet-submitted transcript for this utterance (`pending` non-empty), and ended when
the desktop called `start()` on the first segment's `AudioBufferSourceNode`. Both are
`performance.now()` in the webview. **It is not physical audibility**: output-device
latency is not in it, and it begins after the endpoint silence, the final decode and up
to one 120 ms poll. The panel now labels it `transcript → playback start`.

**Correlated critical path (DERIVED, run 3):** desktop sees transcript ≈ 50.0 →
**resume window 1.1 s** (deliberate, serial) → commit 51.08 → dispatch 51.19 (readiness
was an already-loaded check) → **cognition 10.0 s** (hidden reasoning, then visible
text; split NOT RECORDED) → answer 01.2 → **6.3 s more until the first segment's audio
existed** (07.53) → offered 07.605 → playback started 07.618. The first segment's
synthesis finished 16.46 s after submission and 6.3 s after the whole answer existed;
**when it started is NOT RECORDED**, so whether it overlapped cognition cannot be said.
Segment 2 took ≈ 4.5 s after segment 1. Nothing here is summed across overlapping spans;
the only overlaps retained are segment 2's synthesis under segment 1's playback.

**The owner's ≈ 1 minute: UNRESOLVED.** Retained evidence bounds: Voice On →
first playback start 37.3 s; Voice On → last segment finished 44.2 s (both DERIVED from
service wall-clock rows). Voice On → the desktop seeing his transcript was ≈ 19.7 s, of
which his own pre-speech time is NOT RECORDED, so how much was his waiting and how much
was the system's cannot be said. One retained oddity is recorded, not interpreted: only
50 session polls returned in those ≈ 19.7 s against a 120 ms poll interval.

### 3.5 Warming (§7.2, §8, §9)

**Cognition warm-up — what it does:** the runtime's readiness call — list loaded models
over HTTP, and load the model only if absent. **It sends no inference.** Its only
shared resource with a turn is the runtime's load lock. In run 3 the turn's own
readiness found the model loaded (OBSERVED) and dispatch followed the commit by ≈ 0.1 s
(DERIVED): **no queue wait behind cognition warming is visible**, and when warming ran
is NOT RECORDED. **Voice warm-up — what it does:** a separate process that loads the
speech model and **exits**; nothing stays resident, each synthesis still loads its own
copy, and what it leaves behind is the model files in the operating system's cache
(6.708 s cold vs 2.727 s cached for one phrase — not a room claim). Whether it ran,
finished, or overlapped the first synthesis in run 3: NOT RECORDED. Its ≥ 6 s first
synthesis is consistent with a cold load, but that is not evidence it was one.

## 4. Why run 3 is the one he read

Run 2's rows give (22:12:55.796 − (22:12:41.055 − 1.1)) ≈ 15.8 s for the same figure and
run 1 has no playback rows at all (no read of its conversation either), so only run 3
reproduces 17,612 ms within the reports' transit time. DERIVED.

## 5. Repairs, and the tests that hold them

| Defect | Repair | Regression (and mutation that it catches) |
|---|---|---|
| His message invisible until her answer | `deliberated_send(on_persisted=…)` fires on the commit; the session exposes `committed` (and the conversation id) at once; the desktop reads on it | API test with cognition **held**: poll shows `committed`, `GET /conversations` **returns** his message and no answer while the provider has not returned (fails with the commit notification removed: the view stays `conversation_id: null`, `committed: null`). jsdom test: real controller polling, real read rule, real `Thread`; his words in the document while the session says `thinking` (fails with the trigger removed) |
| Stale reads | newest-issued-wins read rule; `invalidate()` on New chat / scope change | answer's read first, older read later: answer stays, no duplicate (fails without the rule) |
| Event loop held by audio hand-over | recognizer hand-over moved off the loop | API test: a held hand-over; a conversation read must return meanwhile (failed before: "the audio route is holding the event loop") |
| Opening speech discarded | pad precedes the first confident window; the confident run is kept | voice-runtime tests with scripted VAD, sample-exact (4 fail with the old behaviour restored) — **skipped in CI**, which has no voice runtime; numpy is not added to production |
| Diagnostics zero / missing | silence read before clearing; extent and sample positions on every event; receipt time stamped by the adapter | same file |
| No timeline | every spoken turn records its marks and writes one content-free `voice turn timeline` line anchored to the endpoint and the wall clock; warm-ups log begin/end | gateway test: one line, commit mark present, no transcript text |
| Warm-up could delay real speech | real synthesis stops a running speech warm-up and **waits for its process to exit**; no warm-up starts while speech runs | real child processes: at the instant synthesis begins the warm-up has exited and its PID no longer exists (fails with preemption removed) |
| Cognition warm matched the turn only by coincidence | chosen by the turn's own `attempt_order` under local-only egress | warm and a spoken turn ask the runtime for the identical configuration |
| Orphaned sessions | desktop sends close first with `keepalive`; service reaps a session unasked-about for 120 s | close sent before the first await (fails with the old order); keepalive/no-headers; reaping |
| Desktop read `speaking`, service sends `delivery` | field renamed to the contract | fixture corrected |

## 6. What is still open

Owner acceptance of Step B; physical first-audible latency; the owner's ≈ 1 minute
(UNRESOLVED); whether his actual "Good" reached Whisper (UNRESOLVED); when the first
segment's synthesis started (instrumented now, NOT RECORDED then); the 16 ms
capture-start edge (measured, governed pad unchanged).
