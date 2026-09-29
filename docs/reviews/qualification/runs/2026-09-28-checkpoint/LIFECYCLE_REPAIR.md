# The interrupted-turn lifecycle repair — 28 September 2026 (evening)

Owner order of 28 September 2026 ("…one focused repair pass under the existing
isolated-development authorization"). **Nothing deployed. No physical test requested.**
Branch `latency-2026-09-28`, worktree `~/Projects/val-dev`; candidate code `af136fe`;
engine hook v2.3 (`3773168d…`, unchanged in this pass). All provider calls local, $0.

## 0. Production isolation

**Compatibility verified before anything is repointed:**

- **Database:** the release's newest migration is `0031_prefix_prime`, the same as the
  live store, so nothing is downgraded or applied. Master's head is `0032`, which is not
  applied; master runs only because nothing uses `0032` with the switches unset.
- **Configuration:** the launch file supplies five settings (three credentials, the
  database URL, the cache lifetime), which are the ones the release requires. The speech,
  voice and perception runtimes, models and voice files live outside any checkout
  (`~/.val-runtimes`, `~/.val-models`, `~/.val-voice`), so they are unaffected.
- **Desktop:** the installed app is the `13b3cb8` build (`val_desktop` sha256
  `21b8e948…`, the only bundle in /Applications). Since the reboot it has been served by
  master, whose three desktop changes were never installed; repointing restores a
  matched pair.
- **Backup jobs:** their scripts are identical in both revisions.
- **Release directory:** clean at `13b3cb8638714f42e3509f06ba4e8e3b485c5300`, with its
  own environment present.

**The procedure** is his to perform, one step at a time, each verified before the next
(steps and state in §8).

## 1. The ten driver waits over 240 s — reconstructed (`extreme-waits.json`)

Reconstructed from the existing evidence (driver files, service logs, the C2c store
dump); nothing re-run. Twelve cases in all: the nine in P1a, P1b, C2b and C2c, plus three
in C1a and R1, listed separately.

| class | cases | what it was |
|---|---|---|
| hand-off defect (the application; now repaired, §2) | 10: P1a S3 t5, P1a S5 t7, P1b S3 t5, P1b S5 t7, C2b S3 t5, C2b S5 t7, C2c S3 t5, C2c S5 t7; C1a S3 t5; R1 S5 t4 | Each followed a replacement or combined answer that **was produced on time, played in full and returned the page to idle within 7–21 s**. The playback worklet never reported the last segment `completed`, because the segment's closing marker was never collected, and the driver waits for that report. Not a long answer; she was not speaking. What was missing is below the table. |
| runaway speech (a real incomplete answer) + the same defect | 1: C2c S5 t4 | Segment 2 hit the speech-length bound (184 characters, 40.8 s of audio); only 2 of 9 segments were spoken. Its failure stop never reached the desktop, for the same hand-off reason. |
| the known C1a stall | 1: C1a S5 t1 | §3. |

- **The turn spoken after each timeout** was answered correctly, except after the C1a
  stall, which answered his earlier words.
- **Side effects the defect left in the records** (the C2c dump shows three): speech
  rows `playback_interrupted – voice mode ended` written minutes after the audio had
  ended, and `spoken_over_her_audio` flags that were false in fact. They stay in the
  record as written; the corrected explanation is here and in
  `CHECKPOINT_EXPERIMENT.md` §9.
- **What "the final piece" was.** The sink ends every segment with a **zero-length
  closing marker** (`DesktopSink.end_segment`: no audio, duration 0, `last=True`), and the
  player reports a segment `completed` only on it. Where the records allow a check, only
  that marker was lost:
  - **C2c** (the store was preserved): a streamed piece is exactly 12 codec tokens, 0.96 s.
    Each segment's synthesized duration (`speech_generations`) gives its piece count;
    comparing that with the pieces the desktop received gives the result below.

    | answer | final segment | audio pieces the desktop received | missing |
    |---|---|---|---|
    | S3 t5 | 2.80 s = 3 pieces | all 3 | the marker (piece 3) |
    | S5 t7 | 2.96 s = 4 pieces | all 4 | the marker (piece 4) |

    **In both, all of her audio was delivered and heard; the missing item was a
    completion marker, not audible content.**
  - **P1a, P1b, C2b, C1a, R1:** their stores were rebuilt, so this **cannot be
    determined**. The mechanism clears the hand-off 20–80 ms after synthesis finishes,
    and the last audio piece and the marker are offered milliseconds apart, so a lost
    final audio piece is possible there and is not excluded.
  - **Consequence either way:** the player never recorded the segment finishing, so
    "interrupted – voice mode ended" was written minutes after her audio had ended.

## 2. The hand-off defect — cause established, repaired

`VoiceSession._record` moved *whatever delivery was current* into the hand-off slot
(`_recent = _delivery; _delivery = None`) without checking that it was its own turn's. A
superseded turn's worker that ended after the newer turn had begun therefore took the
newer answer out of hand-off. Its closing piece was never collected, the page showed
her thinking while she spoke, and later playback rows said "interrupted" for audio that
had finished. **Repair:** `_record` moves only its own delivery.

- Test: `test_a_superseded_worker_ending_late_never_takes_the_newer_turns_delivery`
  (fails with the check removed).
- Real desktop: 0 driver timeouts in L2 and L3 (§5).

**The abandoned-worker limit was per Voice session, not per service — a defect,
repaired.** The count lived on the `VoiceSession` instance, and the API creates a new
instance each time Voice is switched on (`app.py:1101`). An abandoned worker is a daemon
thread that outlives its session, so switching Voice off and on again reset the count
while earlier stuck workers stayed alive: repeated reopening could accumulate them without
bound. The count is now **process-wide** (`abandoned_workers_alive()`), each worker is
removed only when its thread actually ends, and **Voice refuses to start** while the
service is over the limit, with the reason. Restarting the service ends the threads.
Test: `test_reopening_voice_does_not_reset_the_bound_on_workers_that_never_ended` (fails
with the start guard removed).

**A second hand-off defect, found through the desktop in this pass (L2) and repaired:**
an answer that had finished but not been heard, **kept** by his continuation to play
after him ("Azure."), was dropped unheard the moment his continuation's turn began: the
turn start clears the previous hand-off. Its delivery record read `completed`; no
playback row of any kind existed. **Repair:** an answer with audio still uncollected (the
sink's own `waiting` count) that did not end short is carried and offered before the new
answer, and Voice off releases it.

- Test: the continuation test now asserts it (fails with the carry removed).
- Real desktop: L3 (§5).
- An initial version read `waiting` as a method; the real sink exposes a count, so it
  would never have carried anything. The test's fake sink had hidden this, and now
  mirrors the real one.

## 3. The C1a stall — contained; the cause not established

**What the evidence shows:**

- At 13:51:59 his utterance was submitted early. At 13:52:01.556 speech resumed and the
  early turn was superseded. The engine logged the client's disconnect at 13:52:01, and
  the worker thread never returned: no superseded-call record, no timeline, no release,
  **no exception** (none in any run's log).
- The resume path joins his words only at the old worker's end (`_join_resumed`, called
  from `_run`), so they waited until his next utterance, 243 s later. The answer that
  then played was to the earlier words.
- Across the 87 superseded turns whose workers ended today (resumes, replacements and
  combinations; C1a's is the 88th), the worker ended 19 ms after the decision at the
  median (p90 53 ms). The slowest that ended took 2.8 s, queued in the
  exact preflight behind a busy runtime — and it **dispatched a request 2.7 s after being
  superseded**.

**What was tested, and what it does and does not exclude:**

- **The adapter layer is not excluded.** 30 of 30 forced cancellation races across the
  prefill's end ended in 1–48 ms (`supersede_race.py`), so the problem did not reproduce
  there under those conditions. That does not rule out a rarer interleaving at that layer.
- **The session lock is excluded:** later utterances were handled normally.
- **No nested lock acquisition in httpcore on that path** (read from the code). A lock
  inversion there is therefore unlikely, but that is not a demonstration.

**Not established:** where the thread was. The gateway logs its superseded record only
after two store writes (the call record, then the ledger settlement). A block there, a
row or advisory-lock wait with no lock timeout, fits every trace, but no stack exists to
show it.

**Status: contained; root cause unresolved.** Containment repairs the blocking, not the
unknown cause:

- **A finite recovery deadline.** A superseded worker still alive
  `SUPERSEDED_WORKER_DEADLINE_SECONDS = 1.0` s after its supersession is **abandoned**.
  - **Why 1.0 s:** it is about 20× the p90 end time. Past it, waiting gains nothing,
    because stale work can no longer act (below); it only delays his words.
  - **Diagnostic, not policy:** the 45-second stack watchdog in the harness stays
    diagnostic instrumentation, not the recovery.
- **The session takes over.** If his resumed words were waiting on that worker, the
  session joins them itself:
  - if the fragment was recorded, it is withdrawn (append-only) and his complete words,
    in the order he said them, become the turn;
  - if the fragment was never recorded, its words lead the joined turn, so nothing he
    said is lost.
- **The next occurrence names its cause.** The worker's stack and any store sessions
  waiting on a lock or idle in a transaction are captured once, in the log.
- **No silent accumulation.** Abandoned workers are counted across the whole service;
  above `MAX_ABANDONED_WORKERS = 3` alive, Voice ends with the reason and will not start
  again until they end (§2).
- **Stale work is refused at every action**, so a late return has no authority:
  - Core refuses to persist his message for a turn already superseded;
  - the answer's append is refused **under the conversation lock** once superseded, so
    it either precedes his newer words or does not exist. This matters because an answer
    appended after them would, by the live-answer rule, attach to them;
  - the LM Studio adapter sends no request for a call superseded before dispatch;
  - the late worker announces nothing, plays nothing, records no turn and does not join
    words.
- **Closed connection is not an available engine.** The session does not assume the
  engine is idle because the client disconnected: the recovery turn's request queues
  behind whatever the engine is still finishing (`--parallel 1`), and its own preflight
  and dispatch marks measure that wait.

**Measured recovery** (fault injection; `test_superseded_worker.py`, the old worker held
deaf to cancellation). **This is how long the session takes to stop waiting and get his
words going again after a stalled worker, measured with a test adapter that answers at
once. It is not an answer onset:** a real joined turn then takes an ordinary turn's
processing on top (§5a).

| case | recovery at the 1.0 s deadline |
|---|---|
| held after his fragment was recorded (five runs) | 1.20–1.23 s from supersession to his joined turn's answer (test adapter) |
| held before his fragment was recorded (five runs) | 1.21–1.24 s |

After release, every late return wrote nothing, sent nothing and played nothing, with no
duplicate submission. Each of the five lifecycle tests fails with its guard removed
(mutation checks).

**Exposure:**

| revision | stall / hand-off paths reachable? |
|---|---|
| running production, master `6bad617` | **No**: the code exists, but supersession and the cancel flag require `VAL_OWNER_PRECEDENCE` or `VAL_ADAPTIVE_ENDPOINT`, and the launch file sets neither. |
| pinned release `13b3cb8` | **No**: no supersession code at all, and a new turn always waits for the previous one. |
| candidate (switches on) | **Yes, before this repair**: any resumed speech after an early submission (stall), or a replacement / continuation while an answer was being made (hand-off). |

Since the cause is unknown, whatever blocked could in principle also affect an ordinary
turn's settlement. No production voice turn has shown such a stall, and the specific
trigger (cancelling a turn in flight) exists only in the candidate.

## 4. The latency conclusion, kept precise

- **The cache saving stands**, and it is not a conversational-speed solution: prefilled
  tokens −44%, and the ordinary-turn median did not improve (6.19 → 6.38 s).
- **Dispatch → first chunk** = the engine's own restore and prefill (mean 1.53 s prior,
  1.10 s candidate) + a constant ~0.42 s of HTTP, template and first-token overhead
  (unchanged).
- **Hidden reasoning** (first chunk → first visible text): mean 3.02 s prior, 3.36 s
  candidate, with a per-turn standard deviation of 1.6–1.9 s over 30 turns each. The
  +0.33 s difference is inside its own uncertainty (standard error about 0.46 s): **not
  established either way**, so reasoning effort is not declared the only lever.
- **The ~2.2 s audio-release floor overlaps processing; it is not added.** It is the
  endpoint plus the resume window and margin, during which cognition is already running.
  An ordinary answer's first audio is ready about 6 s after his speech ends, so the hold
  has closed long before. In the decomposition it never bound an ordinary turn (desktop
  collection + hold + playback start: 52 ms mean).
- **The numerical cache check, in its scope:** six stage-C requests, one model, one
  engine, logits at every position after the boundary. The divergence checkpoint's
  deviations were comparable to the no-cache chunking noise, and a wrong-prefix state was
  clearly distinguishable. That does not establish identical generated answers or
  equivalence in general.
- **Proposed controlled experiment (not run):** does the split layout lengthen MEDIUM's
  reasoning? Frozen histories (the `construction_frozen.py` pattern), the same 12
  ordinary turns rendered in both constructions (`envelope_in_system`, `split_state`),
  alternating, 5 samples each at the production sampling, on the experiment instance.
  Measured: hidden reasoning tokens (usage minus visible) and time from the first chunk
  to first visible text. About 120 local calls, $0, ~20 minutes. A difference larger
  than the sampling spread would settle it.

## 5. Verification through the real desktop and player

- **L1 was invalid and is kept only as such** (`*-INVALID-concurrent-tests.*`). My
  lifecycle tests were running against the same scratch database, whose fixture drops the
  schema, while L1's service used it. That is a process error of mine, and the one test
  failure during those runs was the same collision. No test runs alongside a bench run
  now.
- **L2** (`2de953a`, the lifecycle session twice, then S5):
  - **0 driver timeouts in the 26 turns with driver files;** the only "over her audio"
    turn was the deliberate barge-in;
  - every superseded worker ended 9–113 ms after the decision (13 measured), so none
    needed abandoning;
  - both boundary variants occurred: a continuation while the answer was being made
    (combined), and one after it had finished unheard (kept);
  - **the second hand-off defect was found here** (§2);
  - store preserved (`store-L2.dump`);
  - **missing evidence:** the first lifecycle pass's driver file was overwritten by the
    second pass (the runner's naming, since fixed); that pass survives only in the
    service log and the store.
- **L3** (`af136fe`, the lifecycle session twice, each pass kept separately): see §5a.

## 5a. L3 — the repaired code through the real desktop and player

- **20 turns, 0 driver timeouts.** The only "over her audio" turns were the two
  deliberate barge-ins.
- **Every superseded worker ended 3–45 ms after the decision (L2: 9–113 ms).** No
  abandonment was needed, so the containment path was exercised only by the fault-injection tests.
- **The kept answer is heard.** Pass 1's continuation arrived after "Cerulean" had
  finished but before it was heard; it was kept, handed over 1.2 s after the decision,
  started playing 6 ms later and completed, and the continuation's answer followed. In
  L2 the same boundary had no playback row at all.
- **Pass 2** had the continuation arrive while the colour answer was still being made: one
  answer ("indigo and an apple") covered both of his messages, and both messages stayed
  canonical.
- **Barge-in after synthesis:** 320 ms and 324 ms from his words to the worklet's
  `stopped`. Each record appends the segment the desktop reported cut.
- **The replacements' superseded answers** were never played; their records say so.
- Store preserved (`store-L3.dump`).

**Speech end → first real playback, identity-attributed** (L2's surviving pass and L3's
two; n is small and these are not latency qualification figures; one uncertain
attribution per path in L3 pass 2):

| path | measurements |
|---|---|
| resumed speech (0.8 s pause, joined) | 7.37, 7.09 s |
| explicit replacement | 7.90, 6.70 s |
| continuation while being made (combined) | 11.43, 7.44 s |
| continuation after the answer finished, unheard | continuation's answer 7.89, 5.32 s; the kept answer itself 9.50 s from his first request (it plays after his continuation) |
| his words over her audio (the answer to "Stop there.") | 6.98, 5.40 s |
| thanks | 6.66, 5.14 s |

L2's extraction counted its one surviving lifecycle file twice (its two passes had
shared a file name), so its summary duplicates; the values above count it once.

## 6. Identities; local and CI

- **Code:** `af136fe` on branch `latency-2026-09-28`. Earlier in this repair, `2de953a` (the
  lifecycle repair) and `7c7c2d5` (the checkpoint records).
- **Engine hook:** v2.3, sha256 `3773168dd12f62281e2eedfe7c29d198350c95d8274e2abf91f30356fe76cfae`,
  experiment instance only.
- **Local gate:** ruff, format and mypy clean; tests domain 406, policy 809, gateway
  1,012, providers 281, API 113, CI 102; the four CI checks pass.
- **CI:** not run. CI runs on master and pull requests only, and the branch is not
  merged.
- **Tested versus admitted:** everything here is tested in isolation, and none of it is
  admitted to production.

## 7. The next latency change

**Correctness first; it is done for the two hand-off defects and contained for the
stall.** For latency, from the per-turn evidence (§4, and CHECKPOINT_EXPERIMENT §10b):
hidden reasoning 3.0–3.4 s mean, prefill 1.1 s in the engine plus 0.42 s of fixed
dispatch overhead, first-piece synthesis 0.72 s, endpoint and confirmation 0.73 s.

1. **Run the proposed reasoning-under-layout experiment** (§4): about 120 local calls, $0,
   ~20 minutes, nothing to decide from you. It settles whether the split layout lengthens
   MEDIUM's reasoning. If it does, the candidate should keep the envelope-in-system layout
   with the divergence checkpoint: stage B reused 14,221 against split's 12,952 uncached
   tokens, i.e. slightly more prefill and less reasoning. If it does not, the split layout
   stands. Expected benefit: between 0 and the ~0.3 s the means differ by, **not
   established**.
2. **Then a shorter first streamed piece of her voice** (the first piece now carries
   ~1.0 s of audio). Same voice, same pace, same model; only when the first piece is
   handed over changes. Expected ~0.2–0.4 s off every answer's first audio. Tradeoff to
   measure: more pieces, so a higher risk of an underrun (a gap) on a busy machine. The
   player counts underruns, and the change is reversible. This is an implementation
   detail within my authority, not a ruling.

**What still needs your ruling, unchanged:** reasoning effort for ordinary turns (the
only lever of size on the 3 s; MEDIUM stays until you say otherwise) and conversation
priming (excluded in this pass). With neither, an ordinary reply will still begin about
5.5–6 s after he stops, even with (1) and (2).

## 8. Production isolation — complete (28 September 2026, 20:34)

Performed by him, one step at a time, each verified before the next:

1. **Backup:** the launch file was copied to `~/val-launch-backup/`, byte-identical, private
   (`drwx------`, `-rw-------`). It preserves the previous launch: `uv run --directory
   /Users/josepharmand/Projects/val val-api`.
2. **Repoint:** my Step 2 command was faulty. `plutil -replace ProgramArguments.3`
   **inserted** rather than replaced, leaving six arguments. That was caught before any
   reload and corrected (Step 2b) by setting the whole five-entry array. Verified: only
   `ProgramArguments` and `WorkingDirectory` differ from the backup; the environment is
   identical.
3. **Reload:** `bootout` and `bootstrap`; health `running`.

Verified afterwards:

| check | result |
|---|---|
| launch target | launchd runs `uv run --directory /Users/josepharmand/Projects/val-releases/13b3cb8 val-api` (pid 90532) |
| service process | pid 90534, the release's own interpreter |
| working directory | the release directory |
| code loaded | `val_api`, `val_gateway`, `val_domain` all import from the release; 28 files open under it, none under `~/Projects/val` |
| revision | `13b3cb8638714f42e3509f06ba4e8e3b485c5300`, clean |
| live migration | `0031_prefix_prime`, unchanged |
| desktop | the installed `13b3cb8` build (`21b8e948…`), a matched pair again |
| restarts | a crash restart or login reads the same launch file, so it loads the pinned release |

- **Tested versus admitted:** `13b3cb8` is the revision that was production before the
  reboot, not the candidate; master's unswitched repairs are no longer running.
- **Step 4 (backup jobs) deferred by his decision.** Their scripts are identical in both
  revisions and neither job uses the API or Val's packages. Condition: repoint them
  before anyone pulls, merges or edits `infrastructure/backup/` in `~/Projects/val`.
- **The faulty command in the 27 September procedure** is corrected there.

## 9. The request-layout comparison (bounded; `layout_compare.py`)

**Design, fixed before running.**

- **Held identical in both layouts:** fixed written histories inserted into a scratch
  store; the persona; his utterances; MEDIUM; Core's output allowance; production
  sampling; one model instance; renewal on and divergence checkpoint off (so neither
  layout gets reuse beyond the primed prefix); the route's own persona prime before
  every call.
- **Balanced:** order A B B A (B A A B on odd cases).
- **Separated:** reasoning is timed from the first streamed chunk to the first visible
  text, which prefill does not affect; engine prefill is taken on first samples only.
- **Decision rule:** the per-case paired difference in dispatch → first visible text,
  with a 90% bootstrap interval and a 0.4 s practical threshold. Expand once if
  undecided. Quality gates the choice.

**Batch 1: 8 cases × 2 layouts × 2 samples, 32 calls, all answered. Decisive; no
expansion.**

| split − envelope, per case | mean | 90% interval |
|---|---|---|
| dispatch → first visible text | **+1.90 s** | +1.02 to +3.06 s |
| hidden reasoning, seconds | +1.85 s | +0.98 to +3.01 s |
| hidden reasoning, tokens | +122 | +66 to +197 |
| dispatch → first speech-safe segment | +2.05 s | +1.09 to +3.31 s |

Engine prefill was equal (median 1.23 s envelope, 1.30 s split); the difference is
reasoning.

**Quality (every answer read, not only the automatic screen):**

- **Split, instruction boundary: a real failure.** The instruction planted in Core's
  record data was obeyed ("BONJOUR, dans une scène nocturne…"). In the split layout that
  data follows his words.
- **Split, the second act: a real honesty failure.** "I have examined the material you
  set before me…", then a critique of a second act that does not exist.
- **Envelope:** no failures. Its one flagged answer ("The Turn of the Screw.") is
  correct; the screen missed it, most likely because of non-breaking spaces.
- **Correction preservation:** correct in every sample of both layouts.

**Decision: the split record-state layout is rejected.** The candidate is
`envelope_in_system` with the divergence checkpoint and renewal (`run_bench.sh`
`candidate`; `split_candidate` keeps the rejected one). The switch value remains in code,
unused.

**Desktop check (E1, `a92bdbf`, S1–S4, one run): onset improvement not demonstrated.**

- Ordinary median **7.91 s** (17 turns), against 6.38 s for the split candidate (C2b/C2c,
  34 turns) and 6.19 s for the prior candidate (P1a/P1b, envelope without divergence,
  34 turns). Social median 4.53 s (4.45, 4.77).
- It is not a slower configuration. Reasoning tokens per MEDIUM call were the same as
  the split runs': mean 224, median 187 (C2c 211 / 204); mean call time 7.1 s (C2c
  7.4 s). E1's 15 decomposed turns caught more of MEDIUM's long reasoning tail: reasoning
  4.55 s mean, against a per-turn spread of 1–13 s today.
- One run cannot resolve this. Per the order, the desktop comparison is reported
  inconclusive and stopped. The revert rests on the controlled comparison, where the
  content was fixed and the result included quality.
- Reliability in E1: 0 driver timeouts, one runaway segment ended by the bound, every
  counted turn answered; store preserved (`store-E1.dump`).

## 10. Where the ordinary-turn wait is now, and the next option

**Largest remaining delay: MEDIUM's hidden reasoning.**

- **Share:** half or more of an ordinary turn: 3.0–4.5 s mean across today's runs,
  against prefill ~1.5 s, first-piece synthesis ~0.7 s, endpoint and confirmation
  ~0.7 s.
- **Variability:** very large from turn to turn (1–13 s; 146–731 tokens for the same
  factual question).
- **Sensitivity to the request:** the layout alone moved it by 1.9 s.

**Option A (within my authority, next): find what MEDIUM deliberates about.** Replay
fixed histories through the isolated experiment instance, where the hidden reasoning is
readable in the runtime's own log and never stored. Classify what the reasoning spends
itself on: the record-state notes, the local-only note, capability facts, the persona's
rules, the question itself. Then test only fact-preserving changes to how Core frames
those parts, with the same paired design and quality gate as §9.

- **Benefit:** unknown, between 0 and ~1.5 s. The layout result shows framing matters.
- **Risk:** honesty. The compact-notes attempt of 27 September degraded it, which is why
  the gate is required.
- **Bounds:** local, $0; one batch of 8 cases × 2 samples per variant.

**Option B (needs your ruling): LOW effort for a defined class of ordinary turns.** It
is the only measured lever that reliably shortens the reasoning itself.

- **Measured before (23 September):** first visible text 25% sooner, with the frozen
  checks at 40/44 against MEDIUM's 41/44. LOW lost a correction-preservation and an
  instruction-boundary check.
- **Bounded proposal:**
  - a paired, fixed-history comparison of MEDIUM and LOW on today's 8 cases plus the 44
    frozen checks, 2 samples each (about 200 local calls, $0);
  - adopt LOW for a class only if its onset gain is at least 1.0 s with zero additional
    correction, boundary or honesty failures;
  - otherwise MEDIUM stands.
- **Expected if it passes:** ordinary onset from ~6.4 s to ~4.5–5 s.
- **Tradeoff:** the quality risk already seen once, decided per class by the gate.

Neither is near-instant. The endpoint, the confirmation window, first-piece synthesis
and prefill remain (~3 s together) even with shorter reasoning.
