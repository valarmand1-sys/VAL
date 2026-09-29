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
| hand-off defect (the application; now repaired, §2) | 10: P1a S3 t5, P1a S5 t7, P1b S3 t5, P1b S5 t7, C2b S3 t5, C2b S5 t7, C2c S3 t5, C2c S5 t7; C1a S3 t5; R1 S5 t4 | Each followed a replacement or combined answer that **was produced on time, played in full and returned the page to idle within 7–21 s**. The playback worklet never reported the last segment `completed`, because its empty closing piece was never collected, and the driver waits for that report. Not a long answer; she was not speaking. |
| runaway speech (a real incomplete answer) + the same defect | 1: C2c S5 t4 | Segment 2 hit the speech-length bound (184 characters, 40.8 s of audio); only 2 of 9 segments were spoken. Its failure stop never reached the desktop, for the same hand-off reason. |
| the known C1a stall | 1: C1a S5 t1 | §3. |

- **The turn spoken after each timeout** was answered correctly, except after the C1a
  stall, which answered his earlier words.
- **Side effects the defect left in the records** (the C2c dump shows three): speech
  rows `playback_interrupted – voice mode ended` written minutes after the audio had
  ended, and `spoken_over_her_audio` flags that were false in fact. They stay in the
  record as written; the corrected explanation is here and in
  `CHECKPOINT_EXPERIMENT.md` §9.
- **Missing evidence:** outside C2c, streamed piece durations are not recorded, so
  audio lengths there are estimates.

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

**Not the cause:**

- **The adapter:** 30 of 30 forced races across the prefill's end ended in 1–48 ms
  (`supersede_race.py`).
- **The session lock:** later utterances were handled normally.
- **An httpcore lock inversion:** no nested lock acquisition on that path.

**Not established:** where the thread was. The gateway logs its superseded record only
after two store writes (the call record, then the ledger settlement). A block there, a
row or advisory-lock wait with no lock timeout, fits every trace, but no stack exists to
show it.

**Containment (repair of the blocking, not of the unknown cause):**

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
- **No silent accumulation.** Abandoned workers are counted; above
  `MAX_ABANDONED_WORKERS = 3` alive, Voice ends with the reason.
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
deaf to cancellation):

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

- **Code:** `af136fe` on branch `latency-2026-09-28`. Earlier this pass: `2de953a` (the
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

## 8. The isolation walkthrough — state

The steps, each his to run and verify before the next:

1. **Preserve the launch file for rollback:** a byte-identical copy into a private
   folder outside `~/Library/LaunchAgents`. **Given; awaiting his confirmation.**
2. **Repoint** `ProgramArguments.3` and `WorkingDirectory` to the release directory (no
   effect on the running process).
3. **Reload** the job at a moment when no Voice session is open (about 10 s).
4. **Optionally, repoint the two backup jobs.**

After step 3 I verify:

- the running process's command, working directory and revision (`13b3cb8`);
- `/health`;
- the live store's migration (`0031_prefix_prime`);
- that the launch file names the release directory, not the development checkout.

**Blocker until then:** a routine restart still loads master from
`~/Projects/val`. No Voice session was open or restarted in this pass, and no credential
was read into any output.
