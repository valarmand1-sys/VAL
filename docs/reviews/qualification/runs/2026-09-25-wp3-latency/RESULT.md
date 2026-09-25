# WP3 Step B retest — where the time goes

Owner order "OWNER STEP B RETEST — CORRECTNESS / PRESENTATION PASS, LATENCY FAILS",
25 September 2026. Installed and source build `912b44f`. **WP3 remains PARTIAL.**
Labels: **OBSERVED**, **DERIVED** (basis stated), **NOT RECORDED**.

## 1. The run

**OBSERVED:** one Voice session on `912b44f` since the service restarted at 23:21 on
24 September: `voice_sessions` `01a0d8ee-e8ff…`, conversation `01a0d8ee-b9bf…`, owner
message `Good evening, Val.` (id `01a0d8ee-bc5b…`), answer `Good evening, my lord.`
(id `01a0d8ee-e8fc…`), one local model call (`openai/gpt-oss-20b`, 5,872 tokens in,
116 out, 9,651 ms, `complete`). Voice On 09:18:31.877; session **closed 09:19:04.801,
`closed by the caller`**; no recognizer process is running now. No other session was
opened in that service process (OBSERVED: the store and the log), and the previous
process's three orphaned helpers were gone after the 23:21 restart (OBSERVED in the
process list at the time), so **no other recognizer helper of this service was alive
during the run** (DERIVED from those two facts).

## 2. Timeline (ms from speech end; speech end = endpoint − 672 ms of confirming silence)

Clocks: the service's timeline line is anchored to the endpoint and to the wall clock
(`anchor_wall` 09:18:37.692); store rows are wall-clock; LM Studio's own log has
one-second resolution. Speech end itself is **DERIVED** — the VAD's endpoint less the
silence that confirmed it — not an acoustic observation.

| # | Boundary | Wall (CDT) | ms | Label |
|---|---|---|---|---|
| 1 | Voice On (session created) | 09:18:31.877 | −5,143 | OBSERVED |
| — | cognition warm: model **loaded from unloaded** (idle TTL) | 32.259–41.065 | −4,761…+4,045 | OBSERVED (8.806 s) |
| — | voice warm: load-only process | 41.065–44.756 | +4,045…+7,736 | OBSERVED (3.691 s, not preempted) |
| 2 | first PCM received | ≈ 35.29 | ≈ −1,730 | DERIVED: 38,400 samples (2.4 s) received at the endpoint, arriving in real time |
| 3 | VAD first confident speech | ≈ 36.28 | ≈ −736 | DERIVED: utterance's first sample + the 80 ms pad |
| 4 | speech admission | ≈ 36.51 | ≈ −512 | DERIVED: + 224 ms |
| 5 | speech end | 37.020 | 0 | DERIVED |
| 6 | endpoint (silence 0.672 s) | 37.692 | +672 | OBSERVED |
| 7–8 | final decode (helper-measured) | — | 106 ms | OBSERVED |
| 9 | final in VoiceSession | 37.805 | +785 | OBSERVED |
| 10–11 | resume grace | 37.805–38.909 | +785…+1,889 | OBSERVED (1.104 s) |
| 12 | owner message committed | 40.123 | +3,103 | OBSERVED mark; **the commit took 1,212 ms** (below) |
| 13 | `committed` in session state | 40.123 | +3,103 | OBSERVED (same instant) |
| 14–16 | desktop poll / read issued / **read returned** | 40.145–41.082 | +3,125…+4,062 | DERIVED: the one owner-message read is logged after assembly and before readiness ended |
| 17–18 | desktop state / DOM | — | — | NOT RECORDED (shown on the panel only) |
| 19 | readiness (turn waited on the warm's load of the same model) | 40.174–41.082 | 907 ms | OBSERVED |
| — | exact preflight | 41.082–41.334 | 252 ms | OBSERVED |
| 20 | dispatch | 41.339 | +4,319 | OBSERVED; LM Studio received it at 09:18:41 |
| 21 | provider queue | — | none | DERIVED: LM Studio started processing on receipt |
| 22 | first provider output | 49.402 | +12,382 | OBSERVED; **8,063 ms after dispatch**; LM Studio's log shows full prompt processing 41→49 |
| 23 | first visible answer text in Core | 50.985 | +13,965 | OBSERVED (1,583 ms of reasoning) |
| — | answer committed | 51.004 | +13,984 | OBSERVED |
| 24–26 | speech-safe segment → TTS start | 51.019 | +13,999 | OBSERVED (34 ms after first text) |
| 27 | TTS return / audio at sink | 53.848 | +16,828 | OBSERVED (2,829 ms) |
| 28 | audio offered to the desktop | 53.881 | +16,861 | OBSERVED |
| 29 | desktop receipt of audio | — | — | NOT RECORDED |
| 30 | playback start (software, desktop report) | 53.896 | +16,876 | OBSERVED |
| 31 | desktop receipt of answer text | 53.896–55.258 | +16,876…+18,238 | DERIVED: log order between its first two playback reports |
| 32 | render of answer text | — | — | NOT RECORDED |

## 3. The owner-facing intervals

| | Software (his run) | His estimate | |
|---|---|---|---|
| A speech end → his message (read returned; DOM not recorded) | **3.1–4.1 s** | ~10–12 s | differs by ~6–9 s |
| B his message → her playback start | **12.8–13.8 s** | ~45–60 s | differs by ~31–47 s |
| C speech end → her playback start | **16.9 s** | ~55–72 s | |
| D (internal) commit → playback start | 13.8 s | — | B starts later than D, at the read's return, 0.02–0.96 s after the commit |

**The record cannot hold interval B as estimated:** the whole session, Voice On to
Voice Off, lasted 32.9 s, and her audio played from 09:18:53.896 to 55.258. The
difference is **UNRESOLVED**: the desktop's own boundaries (poll receipt, DOM commit,
paint, sound leaving the speakers) were not retained in that run. What he was timing
is his, and is not rewritten here. From now on the desktop posts its three measured
intervals to the service log after every spoken turn, so the next run can be compared
directly.

## 4. Reproduction through the real service — before this pass's changes

A second instance of the real application (`val_api.main.build`) on port 8766 over the
scratch store, driven exactly as the desktop drives it, with a locally synthesised
"Good evening, Val." (`serve_scratch.py`, `drive_turn.py`). $0; no cloud call (sealed turns).

| Trial | Condition | A (read returned) | B | C | TTFT | reasoning | TTS 1st | commit |
|---|---|---|---|---|---|---|---|---|
| before-1 | model unloaded (his condition) | 2.16 s | 16.76 s | 18.92 s | 8.08 s | 2.43 s | 2.56 s | 50 ms |
| before-2 | model resident | 2.11 s | 12.20 s | 14.31 s | 7.87 s | 1.58 s | 2.69 s | 11 ms |
| before-3 | model resident | 2.13 s | 15.90 s | 18.04 s | 7.96 s | 5.25 s | 2.61 s | 7 ms |
| after-1 | model unloaded | 2.12 s | 19.51 s | 21.63 s | 8.10 s | 4.69 s | 2.75 s | 44 ms |
| after-2 | model resident | 2.09 s | 13.04 s | 15.13 s | 7.99 s | 2.14 s | 2.80 s | 10 ms |

In the cold trials the turn also waited 3.70 s and 3.77 s for the rest of the load.
**No repair in this pass is on either critical path, and none produced a measured
improvement; the after-trials show no regression.**

## 5. Findings

**Owner message (A).** Critical path: 0.672 s confirming silence (governed) → 0.1 s
decode → 1.1 s resume grace (governed) → commit → ≤ 0.12 s poll → ~0.01 s read. That is
2.1 s every time it was reproduced. Recognition is not the problem: final decode is
106–115 ms on the actual input. His run's extra second was **the commit itself, 1,212
ms**: conversation created 38.911, append transaction began 39.229, message id
generated 39.579 (UUIDv7), committed 40.123 — uniformly slow database steps while LM
Studio was finishing its cold model load (09:18:32–41). Reproduced during an 8.2 s
model load from page cache the same step stayed ≤ 28 ms (`contention-baseline.json`),
and it is 3–18 ms uncontended; a load read cold from disk after an idle night could not
be reproduced without privileges. **UNRESOLVED**; `open_turn` now carries marks for
scope, conversation creation and append, so the next occurrence locates itself.

**Response (B).** Critical path, resident model: commit → 0.02 s readiness → 0.04 s
preflight → **~7.9–8.1 s to first model output, on every turn** → 1.6–5.3 s reasoning
(MEDIUM) → 0.03 s → **~2.5–2.8 s first-segment TTS** → 0.05 s to playback. First turn
after an idle hour adds whatever is left of the model load the warm-up started at Voice
On (0.9 s in his run, 3.7 s in the trials, where speech followed Voice On sooner).

- **The 8 s is prompt processing of 5,872 input tokens with no reuse between turns.**
  LM Studio's log shows a full pass on every request, including identical-prefix
  requests seconds apart; the model runs under its `BatchedModelKit` (parallel 4). The
  prefix is dominated by the persona, which is loaded whole by governance.
- **TTS, per synthesis:** ~0.26 s interpreter and imports, **1.0 s model load** (files
  already cached), ~1.2 s generation for 1.2–2.1 s of audio (`tts-split.json`).
- Warming did not delay real work: cognition warming performed exactly the load the
  turn needed (the turn waited 0.9 s instead of ~8.8 s); voice warming finished at
  44.756, six seconds before real speech began, and was not preempted.

**Why her text and voice arrived together.** A **shared completion boundary**,
demonstrated rather than designed: the desktop reads her answer when the session's
`turns` gains the exchange, which happens only after delivery has synthesised **every**
segment. For a one-segment answer that is the moment her first audio exists, so text
and voice land within about a second. For multi-segment answers the same boundary puts
her voice **before** her text — by 2.9–6.4 s in the reproductions. No text delay was
added in this pass, and the boundary was left as it is: moving the read to the answer's
commit would make the text lead her voice by the first segment's synthesis (≈ 2.8 s
measured), which is the owner's decision (§11.2), not an implementation choice.

## 6. What changed in this pass

- The session reports when the latest utterance's speech ended (endpoint less
  confirming silence) so the desktop's intervals start at speech end.
- The panel shows the three owner-facing intervals, each labelled for what it measures
  (VAD-estimated speech end; DOM commit; software playback start), or `unavailable`.
- The desktop posts those intervals, numbers only, to a new route that logs them.
- **Voice Off no longer strands an answer:** a turn committed before Voice went off is
  followed until her answer is in the conversation (bounded, and only while he stays).
- `open_turn` marks its parts.

## 7. Decision boundary

With the avoidable software delay on both paths at a few hundred milliseconds, the
remaining latency is provider/runtime workload, and each way to reduce it is a change
to an admitted component:

1. **Prompt-prefix reuse** on the admitted LM Studio runtime (for example a
   non-batched load, or its prompt-cache setting), which could remove most of the ~8 s
   on turns that share the persona prefix. Bounded plan, $0: the scratch harness above,
   three cold and three resident trials with the changed load, exact preflight and
   token parity checked, no model, route or reasoning change.
2. **A resident speech process** — ~1.3 s per segment, same model, voice and settings.
3. **Model residency** beyond the one-hour idle TTL while Voice is in use.

Not proposed: LOW, a different recognizer, any change to the persona or voice.
