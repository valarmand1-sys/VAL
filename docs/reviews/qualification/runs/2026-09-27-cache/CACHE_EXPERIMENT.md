# The live cache experiment and the integrated candidate — owner order of 27 September 2026 ("Continue the latency work")

Labels: OBSERVED (measured here), DERIVED (computed from observed marks), NOT MEASURED.
Every model call in this pass was local at a known $0. Nothing is deployed. The previous
pass's record is `../2026-09-26-redesign/LATENCY_CANDIDATE.md`.

## 1. The approval boundary (§1)

Each operation was submitted through the normal approval mechanism with his
authorisation, one at a time. **All four cache steps were approved and done**:

| step | command (from the repository root unless stated) | result |
|---|---|---|
| clone | `cp -c -R ~/.lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8 ~/.lmstudio/models/val-experiment/gpt-oss-20b-MXFP4-Q8-renewal` | approved; all ten files byte-identical (SHA-256 compared) |
| allowlist | `~/.lmstudio/val-cache-renewal.json` naming only the clone's path | approved |
| hook | `uv run --no-project python infrastructure/lmstudio/cache_renewal/install.py install` | approved; engine files matched the pinned digests; `val_cache_renewal.py` sha256 `665c06d1…af12` (= the repository file), `val_cache_renewal.pth` `1868b566…c0a` |
| instance | `lms load gpt-oss-20b-renewal --identifier val-exp-gpt-oss-20b -c 32768 --parallel 1 -y` | approved; the hook logged "renewal on hit installed" for the clone's path only |

**A separate experimental engine location is not supported.** LM Studio selects an
engine per *model format* for the whole application
(`~/.lmstudio/.internal/backend-preferences-v1.json`: one `mlx-llm…@1.11.0` for
`safetensors`), and `lms load` has no per-instance engine option; a copied engine would
have had to be selected globally, production included. The shared engine directory was
therefore used as authorised: the hook is imported by every instance that engine loads,
and declines every path not on the allowlist (§3 confirms production's).

**One operation was refused** — not a cache step. Repointing production's launchd job
at a pinned release directory (§2):

```
plutil -replace ProgramArguments.3 -string /Users/josepharmand/Projects/val-releases/13b3cb8 ~/Library/LaunchAgents/house.armand.val.api.plist
plutil -replace WorkingDirectory -string /Users/josepharmand/Projects/val-releases/13b3cb8 ~/Library/LaunchAgents/house.armand.val.api.plist
```

**Corrected 28 September 2026 — the first command above is faulty; do not use it.** On
this Mac `plutil -replace` with an array index **inserts** the new value and shifts the old
one along, leaving six arguments (`… --directory <release> /Users/josepharmand/Projects/val
val-api`), with which the service would not start. It was caught before any reload. The
command used, and verified, sets the whole array:

```
plutil -replace ProgramArguments -json '["/Users/josepharmand/.local/bin/uv","run","--directory","/Users/josepharmand/Projects/val-releases/13b3cb8","val-api"]' ~/Library/LaunchAgents/house.armand.val.api.plist
```

Isolation was completed that way on 28 September at 20:34
(`2026-09-28-checkpoint/LIFECYCLE_REPAIR.md` §8).

Stated reason: **"[Production Deploy]"**, from the session's automatic permission
classifier. That is a policy decision of the automatic review about who performs a
production change, not a technical restriction and not a missing authorisation of his
(his order authorised it); the classifier's own guidance is that the owner decides. It
was not retried, relocated or attempted by another route. The operation is acceptable
for him to perform; §2 is the verified procedure.

## 2. Production across restarts (§2)

**The hazard, confirmed.** launchd runs `uv run --directory /Users/josepharmand/Projects/val
val-api` with `KeepAlive`, so any restart — a crash, a `kickstart`, a login — loads
whatever the working tree holds (today, master with every candidate switch unset). The
running process has been up since 26 September 02:34, when HEAD was `13b3cb8`
(committed 02:25; the next commit 05:34), so `13b3cb8` is the production revision. The
two backup jobs run their scripts from the same working tree (unchanged since `13b3cb8`,
but any later edit would reach production backups silently).

**Built and verified, not yet in force.** A detached worktree at the production revision,
`/Users/josepharmand/Projects/val-releases/13b3cb8` (`git rev-parse HEAD` =
`13b3cb8638714f42e3509f06ba4e8e3b485c5300`, `git status --porcelain` empty), with its own
environment from the frozen lock (`uv sync --frozen`): the same 55 pinned third-party
packages as production's `.venv` (compared), Val's packages installed from the release
directory. Booted exactly as launchd would boot it — production's own environment,
overriding only the database (a scratch `val_release_test` at `0031_prefix_prime`, the
live store's revision) and the port (8799): it served `/health` from the release
directory; its one warning was the scratch store's missing persona. The runners the
service spawns (`infrastructure/speech/`, `voice/`, `perception/`) resolve inside the
release directory at `13b3cb8`. No production setting, schema or process was touched,
and the live store stays at `0031`.

**The procedure for him** — one step at a time, each verified before the next, in a
Terminal on this Mac, at a moment when no Voice session is open (production's log shows
no request since 26 September 05:35). The launchd file holds credentials; nothing below
prints it.

1. *Confirm the release.* `git -C ~/Projects/val-releases/13b3cb8 rev-parse HEAD` →
   `13b3cb8638714f42e3509f06ba4e8e3b485c5300`; `git -C ~/Projects/val-releases/13b3cb8 status --porcelain`
   → nothing.
2. *Repoint the API job* (no effect on the running process). The two `plutil -replace`
   commands in §1. Verify: `plutil -extract WorkingDirectory raw ~/Library/LaunchAgents/house.armand.val.api.plist`
   → `/Users/josepharmand/Projects/val-releases/13b3cb8`, and the same for
   `ProgramArguments.3`.
3. *Reload it* (a restart of about ten seconds): `launchctl bootout gui/$(id -u)/house.armand.val.api`,
   then `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/house.armand.val.api.plist`.
   Verify: `curl -s http://127.0.0.1:8756/health` → `"status":"running"`;
   `launchctl print gui/$(id -u)/house.armand.val.api | grep -A6 arguments` names the
   release directory; `lsof -a -d cwd -p $(pgrep -f 'val-releases/13b3cb8/.venv/bin/val-api')`
   → the release directory.
4. *The backup jobs* (optional; **deferred by his decision of 28 September**, on the condition
   that they are repointed before anyone pulls, merges or edits `infrastructure/backup/` in the
   main checkout; use the whole-array form above, adjusted to each job's own arguments):
   `ProgramArguments.4`, `WorkingDirectory` and, for `house.armand.val.backup` only,
   `EnvironmentVariables.PYTHONPATH` → the release directory (plus `/infrastructure/backup`
   for the last), then `bootout`/`bootstrap` each.

**Rollback:** the same `plutil -replace` commands with `/Users/josepharmand/Projects/val`,
then step 3. **After it is in force**, a routine restart cannot activate candidate code:
the job names a directory checked out at `13b3cb8`, and a new release is a new worktree
and a deliberate repoint. Until then, the hazard stands and this pass restarted nothing.

## 3. The live cache correction (§3)

**Design.** One frozen candidate (`175c380`, every candidate switch on:
`VAL_FAST_ROUTE_TIERS=1 VAL_TIER1_ROUTE=low VAL_ADAPTIVE_ENDPOINT=on
VAL_REQUEST_CONSTRUCTION=envelope_in_system VAL_OWNER_PRECEDENCE=on VAL_TTS_LENGTH_BOUND=on`),
the real desktop frontend and player, the scratch service addressing **only** the
experiment instance; the one variable is renewal on a hit, set per run by the
allowlist's flag; the instance reloaded before every run so each starts from the same
empty cache; capacity unchanged (the engine's ten entries). Four runs, alternating —
off, on, off, on — 27 September 13:13–15:10, each of five sessions: the earlier compact
set (S1–S3), fourteen alternating social (LOW) and ordinary (MEDIUM) turns, past the
known eviction cycle (S4), and the merge-window session (S5, reported in §4a, kept out
of the latency figures). Harness: `run_cache_bench.sh`, `voice_bench.mjs` (idle rule
corrected: the truthful "Warming up…" line no longer counts as her speaking),
`voice_bench_extract.py`, `cache_bench_summary.py` → `cache-bench-summary.json`.

**Speech end → her first real playback, identity-attributed** (OBSERVED, two runs each,
S1–S4; no attribution was uncertain; one turn per run spoken over her audio excluded):

| median / p90 / worst | renewal off | renewal on |
|---|---|---|
| social (28 turns each) | 8.32 / 12.87 / 15.63 s | **4.77 / 6.68 / 8.15 s** |
| ordinary (34 each) | 8.89 / 16.71 / 19.56 s | **6.64 / 9.27 / 12.21 s** |
| per run, social median | 8.07, 8.37 s | 4.96, 4.73 s |
| per run, ordinary median | 8.94, 8.84 s | 6.66, 6.62 s |
| explicit replacement | 9.76, 12.54 s | 6.63, 5.91 s |

**Cache reuse, by identity** (every engine line matched exactly one call):

| | renewal off | renewal on |
|---|---|---|
| MEDIUM turns that prefilled the persona cold | **17 of 47** | **0 of 45** |
| LOW turns cold | 0 of 15 | 0 of 17 |
| cold primes | 32 of 106 (~6.8 s each) | **4 of 112 — the two after each reload** |
| requests waiting > 1 s behind maintenance | 16 | **0** |
| turns touched by either | 27 of 62 | **0 of 62** |

**The replay's benefit reproduced live.** With renewal off, cold primes recur through
every run (positions 5, 8, 12, 16, 23, … of ~55) exactly as the first-in-first-out
replay predicts; with it on, the only cold primes are the first two after each reload.
Distinguishing the causes the order names: *initial loading* — the two primes after
each reload (and Voice On's first readiness, ~20 s) — remains and is not avoidable
eviction; *avoidable eviction* — every other cold prime and every cold turn — is gone;
*a prefill already in progress* — the explicit replacement still runs behind the
superseded request's prefill, which the engine cannot stop, but that prefill is now a
warm one (~1.5 s) instead of a cold one, and no preflight waited over a second; *an
incompatible prefix* — none arose: LOW and MEDIUM keep separate persona entries (their
headers differ by the effort line) and both stayed warm. Renewal does not prevent a cold
prefill in general: a new model load, a persona or configuration change, or more than
ten distinct live prefixes would still start cold.

**Correctness of what is reused** (OBSERVED): every attributed line reused exactly the
persona boundary of its own route — 5,048 tokens for LOW, 5,089 for MEDIUM — never more,
never less; the prompt count on every line equalled the call's own `tokens_in`; every
call named `val-exp-gpt-oss-20b` and nothing else; the requests on the wire carried
`reasoning_effort` low for the light route and its prime, medium for everything else
(`effort_on_the_wire` in the summary). Renewal only reorders the store's queue: what is
stored, when, and how it is matched are the engine's own. Production's instance: loaded
once as production's supervisor loads it, the hook logged "declined (not allowlisted):
…/mlx-community/gpt-oss-20b-MXFP4-Q8", and it was unloaded again — production runs the
engine as shipped.

**Memory.** Lowest free memory 23% (renewal off) and 36% (on), system-wide; swap grew
0 and 32 MB in the off runs and 454 and 646 MB in the on runs. Renewal changes neither
the number of entries (ten) nor their size, so the swap figures are not attributed to
it; this Mac was in use by its owner through the afternoon (other applications'
memory is in the same figures). Not measured: the engine process's own footprint per
condition.

**Readiness, apart.** Voice On → Ready: ~20 s for the first session after a reload
(both route prefixes cold: initial loading), 6.4–7.7 s for later sessions, in both
conditions.

**Time of day, stated.** These runs were made 13:00–15:10; the earlier comparison ran at
03:00–05:30. The light route's hidden reasoning is markedly longer this afternoon —
73–259 tokens for a greeting or thanks, against about 32 at night — because "Good
evening" and "Good night" at two in the afternoon draw deliberation (the answers stayed
right: "Good day, my lord" to "Hello" at 14:00). The social figures here are therefore
not comparable with the night's 3.0 s; §3a gives a same-afternoon baseline.

## 3a. The integrated candidate against the same afternoon's baseline (§9)

The baseline is **the tested, undeployed code configuration with every candidate switch
off** — the same frozen commit `175c380`, production's settings, the engine as shipped
(renewal off), the same experiment instance, S1–S4, two runs (B0a 15:08, B0b 15:24). It
is not production's installed build (`13b3cb8`, which has no refresh maintenance).

| speech end → first real playback, median / p90 / worst | baseline | integrated candidate (renewal on) |
|---|---|---|
| social (28 turns each) | 7.29 / 11.04 / 15.31 s | **4.77 / 6.68 / 8.15 s** |
| ordinary (34 each) | 9.57 / 13.96 / 19.84 s | **6.64 / 9.27 / 12.21 s** |
| turns touched by a cold prefill or a > 1 s wait | 8 of 62 | **0 of 62** |
| cold primes | 14 of 66 | 4 of 112 (initial loading) |

Social turns are 35% faster at the median and 40% at the 90th percentile; ordinary
turns 31% and 34%; the worst case falls by 47% and 38%. Every counted turn in both
conditions was answered and played; no attribution was uncertain; no underrun.

**Fallbacks, failures and missing measurements, apart from the figures.** One runaway
segment (R1a, 229 characters) reached its bound and the delivery ended *failed*, the
segment recorded as begun and not completed, the rest of that answer not claimed; its
playback lasted ~12 s before the stop because generation outran playback (§6). One turn
per candidate run was spoken over her audio after the driver's 240 s wait in S5 (a kept
continuation queued behind a long answer, by policy) and is excluded. Not measured: a
physical room, the macOS output device, and the engine process's own memory by
condition.

## 4. The merge window under the faster path (§4)

**The policy, stated.** Under the adaptive endpoint a turn can be submitted about 0.65 s
after he stops, and speech resuming within the fixed path's silence bound (~1.9 s of
silence) is the rest of the same utterance. **An early-submitted answer's audio is now
held until that window has closed** (plus 0.3 s for the recognizer to report an onset),
whether the answer is still being written or already finished and waiting
(`VoiceSession._merge_hold`, keyed to that turn's own delivery). So:

- **resumption inside the window** always finds private work: the in-flight turn is
  cancelled, or a finished one's exchange is withdrawn through the retraction machinery,
  and the joined words are answered once — nothing of the early answer has sounded;
- **after the window** his words are an independent turn: an unheard answer in flight
  is decided by owner precedence (a correction or stop sets it aside; a continuation or
  anything ambiguous leaves it), and an answer that has begun to play is barge-in's
  ground — nothing audible is withdrawn or relabelled unheard.

The trade: an answer ready before the window closes waits for it — at most ~2.2 s after
his speech ends, when her first audio has so far arrived at ~3 s or later (§4a: in the
live runs it never did). No half-answer can play inside the window **by construction**,
not by luck. Tests: `test_adaptive_endpoint.py` (7: held until the window closes and
released the moment it does; a correction 1.3 s after the endpoint withdraws a finished
unheard answer and the joined request keeps the correction's meaning; audio begun after
the window stays on the record with both requests). Live resumption at 0.8, 1.2, 1.6 and
2.3 s of silence: §3, session S5.

**Found, and not repaired here (§7c below):** once an answer's synthesis has finished, the
session holds no active delivery, so his onset does not stop what the desktop is still
playing, and the delivery record — which later context reads — still says completed.

## 4a. The merge window, live (§4, session S5)

Four runs × seven paused requests (the renewal-on and -off runs; OBSERVED):

| rendered pause | measured gap after the endpoint | outcome in the four runs |
|---|---|---|
| 0.8 s (continuation) | 0.54–0.58 s | joined 4/4, the fragment withdrawn, one answer to the whole |
| 1.2 s (correction; greeting then request) | 0.85–1.00 s | joined 8/8, the correction's meaning kept every time |
| 1.6 s (window end: continuation, correction, greeting then request) | 1.25–1.40 s | joined 5 of 12, separate 7 of 12 — a measured gap ≤ 1.37 s joins, and the recognizer puts a 1.6 s pause either side of it |
| 2.3 s (correction, past the window) | ~2.08 s | separate 4/4 — his correction answered as its own turn ("Hamlet"), both requests on the record |

**No sound of hers began during any of the 28 paused utterances**, in either condition.
**The hold cost nothing measured:** in the renewal-on runs none of the 70 turns with a
spoken answer had its first segment ready before its merge window closed (DERIVED from
each turn's timeline: the first segment queued later than the settle time plus 1.37 s plus
the 0.3 s margin), so no answer waited for the window.
Where a pause near the edge was *not* joined, the second half was an independent turn
exactly as §4 states: a continuation was kept and answered after the first answer (so
its first audio waited for the whole earlier answer: 35–62 s — a policy outcome, excluded
from latency), a greeting was answered and then the question, and a correction past the
window was answered on its own with its meaning intact. The window's edge is where the
recognizer measures it (0.4 s endpoint + 1.37 s), not a promise about a spoken pause:
a pause the owner means as a pause should stay under about 1.5 s to be joined.

## 5. Playback reports (§5)

Writers for one (answer, segment) are serialised by a transaction-scoped PostgreSQL
advisory lock, and a transition already on record is not written again
(`val_gateway.playback.record_playback`). Nothing is retried, overwritten or deleted;
event numbers are the order of recording and `recorded_at` carries when each happened.
Tests (`apps/api/tests/test_playback_reports.py`): the held start and completion
released together, each delivered three times, through the API — every request 200,
each transition once, both on the right answer and segment, the start before the
completion by time; eight writers released at once — one event per transition. **Both
fail on the previous writer** (lost requests; `IntegrityError`). The worklet's own
timing stays the independent cross-check (§3).

## 6. The speech-length bound, reached (§6)

`VAL_TTS_LENGTH_BOUND` stays in the candidate. Reaching the bound now ends the segment as
a named failure (`SpeechLengthBoundReached`) instead of a completion; the unchanged
runner reports it, the provider raises, and the delivery ends **FAILED** with
"segment N began and did not complete — the local voice stopped part-way through it:
speech length bound reached …". Under the ruled delivered-boundary contract the
segment's first sound had reached him, so it is **not relabelled unheard**; it is not
recorded as completed; nothing after it is claimed; the desktop stops what is playing and
shows the rest of her answer, whose full text stays in the record, as not spoken.

Forced on the real voice (`speech_bound_probe.py` → `speech-bound-probe.json`, bound
forced to 2 s through the test-only `VAL_TTS_BOUND_FORCE_SECONDS`): a 168-character
segment stopped at **exactly 2.0 s** of audio after 0.9 s and failed with the named
reason; the worker stayed alive and idle (CPU 2%) and voiced the next segment normally
(1.36 s); on release the worker exited. Tests: `test_speech_bound.py` (4 — a runaway stops
at its bound, ordinary speech unchanged, the forced bound is only what the test sets,
the delivery records a truncated segment as begun and not completed). The ordinary
speech path is unchanged (the wrapper only adds `max_tokens`), so no new
normal-duration benchmark was needed. The wrapper's eager `len(audio)` fallback — a
latent crash for arrays without a length — was corrected on the way.

## 7. Benchmark attribution (§7)

The run directory's extractor (`voice_bench_extract.py`) now attributes by identity:

- **first real playback** is the first worklet sound of *the intended answer*: the
  worklet names each sound by the desktop's answer key and segment, the desktop's report
  names it by message and segment, and a key maps to a message when a report for the
  same segment was recorded within 0.5 s of the sound. Without a mapping the figure is
  kept but marked `uncertain` and left out of the distributions;
- **each engine cache line** ("Prompt cache: using N/M") is read with the instance named
  on the line after it and attributed to a call when the instance is the call's model,
  M equals the call's `tokens_in`, and the line falls inside the call's span — exactly
  one match, or `uncertain`; primes are attributed the same way;
- turns spoken over her still-sounding audio are excluded as barge-ins and listed; bound-
  reached speech, turns without a played answer, driver timeouts and deliveries that did
  not complete are counted as reliability results;
- the baseline of the previous pass is **the tested, undeployed master configuration
  with every switch off** — not production's installed build (`13b3cb8`), which has no
  refresh maintenance at all.

The launcher (`serve_experiment.py`) is corrected too: the earlier one repointed only
the MEDIUM partner at an isolated instance, so the LOW route addressed production's
identifier; here every GPT-OSS entry addresses the experiment instance, and the process
cannot address production's model.

### 7c. A barge-in gap found (pre-existing; production and both releases)

When an answer's synthesis has finished — every short answer within a second or two,
and the tail of any long one, since streamed synthesis runs faster than playback — the
session moves its delivery to "recent" and `_began` no longer interrupts it: his onset
does not stop what the desktop is still playing, and the desktop's own `interruptSpeech`
is never called. Stopping it properly also needs the delivery record (which is what
later context reads to know what he heard) to say that a completed hand-off was cut —
a change to the ruled delivery-truth records, so it is recorded here for its own
decision rather than folded into this pass.

## 8. Request ordering and conversation-prefix reuse (§8)

`prefix_reuse_analysis.py` → `prefix-reuse.json`: six ordinary MEDIUM turns per
construction, sent live through the real Core path (sealed, local, $0) to the experiment
instance with renewal on, each request's **rendered model input** taken from the runtime
itself (`lms log stream`, `llm.prediction.input`) and tokenized by the instance's own
tokenizer; the engine's own cache line for each request read beside it.

**What the engine can reuse, from its code.** One checkpoint per request, at the prompt
length less 11 tokens (`mlx_engine.cache_wrapper`, `checkpoint_tail_tokens = 11`), and
the previous answer's live cache snapshotted at the next request; an entry is used only
when its whole key is a prefix of the new prompt, because a GPT-OSS cache cannot be
trimmed back to a shorter one. So history is reusable only if everything after it in the
previous request fits in its last 11 tokens.

**What the requests look like** (OBSERVED; every pair; the engine's reuse agreed with the
computed reuse on every request):

| | as the request stands | candidate (state in the developer block) |
|---|---|---|
| order after the persona | history, then **one user message: Core's state block, then his words** | **Core's state block**, then history, then his words |
| where consecutive requests first differ | the start of the previous request's final user message — everything before it (persona and all older history) is common | ~340 tokens into the state block, at the history counts |
| the previous request's checkpoint a prefix of the next? | no — it contains the previous state block | no — it contains the previous counts, and history follows the state |
| reused (engine line) | 5,048 (persona) | 5,089 (persona and separator) |
| recomputed every turn | history 178–548 + state + words ~825 | state ~820 + history 121–491 + words ~15 |

**What changes between turns** (not assumed — read from the rendered state block):
every turn, `same_conversation_history.prior_messages` and `retained_in_this_request`;
the clock only when the minute turns (one pair in five); the `spoken_path` block (~490
tokens) when its gate fires — and it fired on "Give me one line of advice on **pacing** a
chase sequence", a false positive of the speed-and-timing gate that costs ~0.65 s where
it fires (recorded, not changed here).

**Where the ~2 s of prefill goes** (DERIVED; fit over the twelve requests: time to first
token = 0.19 s + 1.33 ms per uncached token, ~750 tokens/s): the state block ~820
tokens ≈ **1.1 s every turn**; history ≈ 1.33 s per 1,000 tokens, growing — 0.2–0.7 s in
these short conversations, and in his real conversations (read from the live store, sizes
only: prior conversation at his turns, median ~1,500 characters, 75th percentile ~16,600,
90th ~108,000) several seconds for a quarter of turns; his words ~0.02 s.

**Why the variant stops here.** A variant placing the changing state after reusable
history would, on this runtime, still recompute the history: the checkpoint of each
request lies 11 tokens from its end, inside whatever per-turn content follows the
history, and none of it survives into the next request. The template also forbids the
cleanest form: LM Studio's GPT-OSS template hoists **every** system-role message into
the single developer block at the top (rendered through the SDK: a system message placed
after history appeared inside the opening developer block), so after the history Core's
state could only sit inside his final user message — the joined block that produced the
earlier wrong-turn answers (9/19 against 0/19). The installed runtime cannot reuse the
desired boundary; per the order the variant is stopped, no priming was added, and no
invalidation test was needed because nothing beyond the persona is ever reused (the
engine's exact-prefix match is what keeps a corrected, withdrawn or switched history
from being served: in every run no request reused more than its route's persona boundary, the turns
after a withdrawal included).

## 9. The remaining decision (§9)

**Retained.** Live cache renewal removes the recurring long waits: with it, none of the
62 counted turns (S1–S4 of the two renewal-on runs, R1a and R1b: 28 social, 34 ordinary)
prefilled cold or waited behind maintenance; including S5, 78 of the runs' 80 turns
carried an identity-attributed engine line and none was cold (the other two are the
superseded "to be replaced" turns, whose calls ended before any cache line). *Corrected
28 September 2026 (reporting only, no rerun): this sentence said "no turn of 124" — the
same 62 turns counted twice, once in §3's table and once in §3a's, which report one
population.* The integrated candidate is
**social 4.77 s, ordinary 6.64 s median; 6.68 s and 9.27 s at the 90th percentile; worst
8.15 s and 12.21 s** (§3a), against 7.29 / 9.57 s, 11.04 / 13.96 s and 15.31 / 19.84 s for the
baseline the same afternoon.

**The next dominant measured costs** of a warm ordinary turn (renewal on, medians):
MEDIUM's hidden reasoning ~2.2 s (visible text 4.40 s after dispatch, first chunk 2.15 s);
prefill ~2.0 s, of which Core's state block ~1.1 s and history 0.2–0.9 s (growing with
the conversation); confirmation ~0.8 s; speech to first audio ~1.0 s. On the light route
this afternoon, LOW's hidden reasoning (73–259 tokens, 2.5–5.4 s) dominates. The
historical LOW comparison of 22 September is not used as an estimate, and its
correction-preservation loss stands; no reasoning level, persona or model was changed.

**Recommended experiment — one: reuse the unchanged prefix of consecutive requests,
at the point where they diverge.**

- *What.* Extend the digest-pinned hook, for allowlisted instances only, so that a normal
  request stores its checkpoint at the point where it diverges from what the store
  already holds — the longest common prefix the engine's own trie reports against the
  stored entries (so the refresh primes between turns do not hide the previous turn) —
  when that lies beyond what is already cached, instead of at the prompt less 11 tokens,
  which for Val is never reusable. No extra call, no priming of
  conversation content, no disk, no new store: the same ten in-memory entries, renewed on
  use. Pair it with one request layout, qualified in isolation: the stable part of Core's
  state (everything but the per-turn counts and the minute) stays in the developer block
  after the persona; the per-turn counts and the minute move to a short, labelled line
  after his words in the final message (his words stay first and identifiable).
- *Expected source of savings.* With that layout consecutive requests share the persona,
  the whole state block and all history up to his words of the exchange before last;
  only the last exchange or two, his new words and the short line are prefilled (a
  checkpoint is made one request after the divergence it marks) — the state block's ~1.1 s every turn,
  plus the history's 1.33 ms per token, which is seconds for a quarter of his real turns.
  Without the layout change the hook alone saves the stable ~340 tokens of the state block
  (~0.45 s) in the candidate construction.
- *Privacy.* Only what Core already sent, in the engine's existing in-memory store, on the
  experiment instance; nothing leaves the process, nothing is written to disk, and a
  sealed conversation's content is cached exactly as its persona is today — in memory,
  on this Mac.
- *Correctness.* Reuse stays exact-prefix: a correction, withdrawal, removal, recall change,
  conversation switch, persona or effort change alters the rendered tokens before the
  reuse point and the stored entry no longer matches — to be demonstrated case by case,
  with the recap, repetition, correction and fabricated-completion cases of the frozen
  set, because the layout change alters what Val reads.
- *Memory.* Each checkpoint of a long prompt costs ~25 KB per token of full-attention KV
  (~150 MB at 6k tokens); ten entries can reach several GB — measured, with capacity
  unchanged.
- *Authorisation required.* (1) The hook's divergence checkpoint for the allowlisted
  experiment instance — a change to the engine's behaviour beyond recency renewal;
  (2) the request layout above, for isolated qualification only — a change to what Val
  reads, to be ruled as the 10 and 17 September constructions and the 25 September prime
  boundary were; (3) measurement on the experiment instance. Nothing reaches production
  without a further ruling.

**Not recommended now**: more reasoning effort changes (a separate ruling), a smaller
model (none qualified), speculative decoding (this LM Studio now offers load-time draft
options — `--speculative-draft-*` — which the pinned inference contract does not carry;
examining them would be its own authorised experiment).

## 10. Identities, what is installed, and rollback

- **Candidate code**: `175c380` on master (frozen for every run here); this record's
  commit adds only records and harness. Settings for the integrated candidate:
  `VAL_FAST_ROUTE_TIERS=1 VAL_TIER1_ROUTE=low VAL_ADAPTIVE_ENDPOINT=on
  VAL_REQUEST_CONSTRUCTION=envelope_in_system VAL_OWNER_PRECEDENCE=on
  VAL_TTS_LENGTH_BOUND=on`; migration `0032_light_conversation` for the light route.
  Rollback: remove the settings.
- **Runtime**: LM Studio engine `mlx-llm-mac-arm64-apple-metal-advsimd@1.11.0`
  (`app-mlx-generate-mac14-arm64@34`), pinned files matching; hook
  `val_cache_renewal.py` sha256 `665c06d1…af12` + `.pth` `1868b566…c0a`, **installed and
  inert for production** (its path is not on the allowlist); allowlist
  `~/.lmstudio/val-cache-renewal.json` = the clone only, `"renewal": true`; clone
  `~/.lmstudio/models/val-experiment/gpt-oss-20b-MXFP4-Q8-renewal` (byte-identical to
  production's model); experiment instance `val-exp-gpt-oss-20b` **unloaded** at the
  end. They are kept pending his ruling on §9, which would use them. Removal:
  `uv run --no-project python infrastructure/lmstudio/cache_renewal/install.py remove`
  (the engine is then byte-for-byte as shipped), `rm ~/.lmstudio/val-cache-renewal.json`,
  `rm -r ~/.lmstudio/models/val-experiment` (a copy-on-write clone; production's model is
  untouched).
- **Production**: unchanged — the running service (`13b3cb8`, up since 26 September
  02:34), the live store at `0031`, the launchd environment without a candidate setting,
  production Voice unused throughout (16 sessions before and after). The pinned release
  directory `~/Projects/val-releases/13b3cb8` is built and verified; putting it in force
  is §2's procedure, his to run.

Evidence: `cache-bench-summary.json`; `voice-bench-{R0a,R0b,R1a,R1b,B0a,B0b}.json` with
their `-session-N.json`; `memory-*.tsv`; `prefix-reuse.json`; `voice-bench-smoke*.json`
(pipeline check, not evidence); `../2026-09-26-redesign/speech-bound-probe.json`. Service
logs (`service-*.log`) stay on this Mac, git-ignored.

**Correction, 28 September 2026 (night; `2026-09-28-checkpoint/EFFORT_EXPERIMENT.md` §8).** The renewal clone (`val-exp-gpt-oss-20b`) has no LM Studio hub definition, so it ignored `reasoning_effort` and rendered "Reasoning: medium" for every request, and used LM Studio's generic sampling defaults rather than production's. **The Tier-1 route's "LOW" requests in these runs ran at MEDIUM**, so the social figures here are Tier-1 requests at MEDIUM effort. The MEDIUM-against-MEDIUM comparisons (renewal, divergence, layout) stay internally valid. The 26 September Tier-1 LOW qualification, on the real `openai/gpt-oss-20b` instance, is unaffected.
