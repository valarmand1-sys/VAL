# The checkpoint and layout experiment, and the Voice repairs — 28 September 2026

Owner order of 28 September 2026 ("Retain the demonstrated cache-renewal improvement and
continue the isolated latency work"). **Nothing deployed. No physical test requested.**
Branch `latency-2026-09-28` (worktree `~/Projects/val-dev`); candidate frozen at
`a5d9680`. Every provider call local, on the experiment instance; cost $0.

## 0. First: production is running undeployed master since the reboot

The Mac restarted at about 00:10. launchd's `house.armand.val.api` runs
`uv run --directory /Users/josepharmand/Projects/val val-api` with `KeepAlive`, so the
restart loaded what that working tree held: master `6bad617`, thirteen commits past the
production revision `13b3cb8` (process started 00:21:18, pid 958; live store unchanged at
`0031_prefix_prime`). Every candidate *switch* is unset there, so no candidate route,
construction or precedence rule is active — but master's **ungated** repairs are now live
without a deployment decision: the refresh prime no longer dropped after 60 s, the
merge-window hold of an early answer's audio, serialised idempotent playback reports, the
speech-length bound's honest ending, `_SELF_CORRECTION` keeping courtesy after "No, …" on
MEDIUM. This is exactly the hazard §2 of the 27 September record named. I did not and
cannot change it: repointing the launch target was refused as "[Production Deploy]" and is
his (§7 below).

## 1. The "124 turns" statement — a reporting correction (§1)

The 27 September record said renewal left "no turn of 124" cold. The counted population
is **62 turns** (S1–S4 of the two renewal-on runs R1a and R1b: 28 social, 34 ordinary —
17 LOW and 45 MEDIUM by identity, none cold). "124" was the same 62 counted twice: §3's
renewal table and §3a's integrated table report one population. Including S5, **78 of the
runs' 80 turns** carried an identity-attributed engine line, none cold; the other two are
the superseded "to be replaced" turns, whose calls ended before any cache line. Corrected
in `CACHE_EXPERIMENT.md` §9, the WP3 record and `CLAUDE.md`, each marked as a correction;
no rerun.

## 2. The checkpoint (§2)

**How the engine captures state** (read from the pinned engine,
`mlx_engine/cache_wrapper.py`): `update_cache` stores exactly one checkpoint per request,
at `total − _checkpoint_tail_tokens` (default 11). `_prefill_cache` shortens the chunk
that would cross that point so the live cache holds exactly that many tokens, and
`_store_snapshot` deep-copies every layer's state under exactly those tokens
(`insert_cache(key, list(tokens), copy.deepcopy(cache))`). The state is therefore complete
and valid for that prefix *by construction* — the request's own prefill, stopped there.

**The extension (hook v2, now v2.2).** For one request at a time, the hook sets
`_checkpoint_tail_tokens` so the engine's own checkpoint lands where this request
diverges from what the engine already holds: the longer of its walk down the engine's own
trie of stored keys (`PromptTrie.search().common_prefix`) and its common prefix with the
previous request's live tokens. Nothing is truncated, trimmed or re-keyed; no later cache
is associated with a shorter prefix; the stored state is always this request's own
prefill of exactly those tokens. No priming call is added, nothing is written to disk,
nothing leaves the engine.

- **Bounded:** capacity unchanged (the engine's `LRUPromptCache(max_size=10)`); still one
  checkpoint per request.
- **Static prefixes protected:** a boundary is used only if it gains ≥ 128 tokens over
  what the request already reuses and lies ≥ 64 tokens before its end. A prime (persona
  and an 11-token filler) diverges inside its last 11 tokens, so its persona checkpoint is
  stored exactly where it always was; the persona checkpoints are intact in every case of
  the replay (`divergence-replay.json`).
- **Maintenance makes no irrelevant checkpoint:** in stage C, the 22 refresh primes were
  all exact hits (`why: exact entry`) and stored nothing new; 7 short LOW exchanges fell
  under the gain threshold (`no gain`).
- **Split-prefill, copy and synchronisation overhead:** measured per request by the hook
  (`update_cache_ms`) and offline: about 1.4 ms per uncached token either way; the
  checkpoint's extra deep copy is inside the engine's existing snapshot path and did not
  show above that noise.

**Validity (§3):** every stage request's reuse was checked against its maximum common
prefix with every earlier request, token by token from the SDK's own tokenizer on the
rendered input: **0 invalid hits in 117 requests** (stages A, B, C, 39 each). Invalidation
behaved: a withdrawal, a conversation switch and a persona revision each fell back to the
static prefix (the persona change to 5,043, the new persona's own).

## 3. The layout and the staged comparison (§3)

**Split record state** (`VAL_REQUEST_CONSTRUCTION=split_state`): the record-state fields
that hold steady within a conversation stay after the persona in the developer block; the
ones that change every turn follow his words, at the end of the last message, under a
heading that marks them as Core's — so consecutive requests share everything up to his
newest words. **Every value is current on every request; only its place moves.**

Inventory (context.py `TURN_STATE_KEYS`), by what changes them — not "everything but the
clock and counts is permanent":

| field | changes when | placed |
|---|---|---|
| `current_time` | every minute | trailer |
| `same_conversation_history` | every turn (counts) | trailer |
| `retrieved_excerpts` | per turn (recall gate) | trailer |
| `house_recall` | per turn (inventory gate) | trailer |
| `spoken_delivery` | whenever an answer is cut short | trailer |
| `spoken_path` | per turn (the gate, §4) | trailer |
| `current_turn` | every turn | trailer |
| `external_egress` | Voice on/off, seal, recall of sealed content | steady (a change re-prefills, correctly) |
| `visual_input`, `audio_input` | an attachment turn | steady (same) |
| `project_volumes`, `capability_state` | a scope or capability change | steady (same) |

A change to a steady field changes the prefix and is re-prefilled — never hidden
(`test_split_state.py`). Core metadata stays framed as house data under its markers; his
words open the last message, identifiable; recall excerpts stay user-role data; the
envelope-recap / wrong-turn construction is not recreated (the envelope is in the
developer block as in the 27 September candidate, not joined to his words).

**Staged, exact rendered tokens** (`checkpoint_stage.py`, one scripted conversation of 13
turns with LOW/MEDIUM transitions, a correction, a withdrawal, a conversation switch,
house recall and a persona revision; rendered input and engine lines from `lms log
stream`):

| stage | uncached prompt tokens (13 turns) | time to first token, median / p90 | largest reuse |
|---|---|---|---|
| A — current layout, renewal | 17,293 | 1.69 / 3.25 s | 5,089 (the persona) |
| B — + divergence checkpoint | 14,221 | 1.49 / 2.60 s | 5,432 |
| C — + split layout | **12,952 (−25%)** | **1.44 / 2.04 s** | 6,366 |

Store: 10 entries, at most 1.69 GB; engine active memory at most 13.96 GB.

**Cached against uncached (§3).** Greedy text is *not* a valid test on this runtime: with
temperature 0 and a fixed seed, uncached repeats are identical, but the persona path
production already relies on differs from uncached too (`cached-vs-uncached.json`, all
four requests), because splitting prefill at a different point changes the summation
order. The decisive check is inside the model (`numerical_check.py`, the engine's own
mlx 0.32.0 / mlx_lm 0.31.3 and the same model files, on the exact rendered token ids of six
stage-C requests, lengths equal to the engine's own): logits at every prompt position after
the boundary (362–768 positions), each compared with a full uncached prefill.

| request | persona checkpoint (qualified path) | divergence checkpoint | uncached, other chunking (noise floor) | wrong-prefix checkpoint (negative control) |
|---|---|---|---|---|
| mean KL, 6 requests | 0.025–0.063 | 0.023–0.067 | 0.025–0.080 | **0.18–1.18** |
| argmax agreement | 86–93% | 86–95% | 85–94% | 63–81% |

The divergence checkpoint is indistinguishable from the uncached noise floor and from
the qualified persona path; the copy is bit-exact (`divergence == divergence_no_copy` in
all six); a state under the wrong key is plainly visible. **The correctness gate passes;
the net-benefit gate passes (−25% prefill, p90 first token −37%).**

## 4. A defect in the renewal hook, found and closed

Four requests of the time-of-day run failed inside the engine (`KeyError: 200005` in
`LRUPromptCache.insert_cache`, server log 12:18–12:19). Cause, mine: on an exact hit
`PromptTrie.search` returns the very list the engine passed in; `_restore_cache` keeps
that list as `_live_tokens` and appends each generated token to it. The renewal queued
that list, so the queued key grew while the trie's did not, and a later eviction walked
tokens the trie never held — the request lost. Present since v1; it never surfaced on 27
September because exact hits came only from one-token primes, which end in the engine's
own long-standing `UnboundLocalError` before a generated token is recorded. **v2.1 queues
a copy.** `hook_regression.py` runs the engine's own `LRUPromptCache`: v2 inconsistent
after the first step and raising `KeyError`, v2.1 consistent through all eight. Rerun: 60
of 60 answered, no error. Stage A–C and the numerical check predate the failure window
and logged no error. v2.2 adds only measurement: with divergence off, the same store and
memory figures are logged.

## 5. The Voice-facts gate and the time-of-day hypothesis (§4)

**Gate.** `val_policy.spoken_path` removes a speed or time word that governs a piece of
work ("advice on pacing a chase sequence", "is the second act too slow", "how long should
a first chapter be") before matching; anything about her ("you're slow", "your voice",
"how long did you take") is always included, and a short follow-up (≤ 8 words) to a turn
that asked about her path carries the facts too. Deterministic, no model call, no prompt.
36 cases (`test_spoken_path_gate.py`). Conservative remainder: "The fight scene drags;
how do I speed it up?" still includes the facts.

**Time of day** (`time_of_day.py`, one Tier-1 request exactly as Core built it, only the
greeting and the clock varied, five samples per cell, interleaved, persona prefix warm):
greeting and clock matching 142 hidden-reasoning tokens median, mismatching 154; spread
within one cell 55–357. **Not supported.** The slowest greeting was the neutral "Hello"
(197), and all fifteen of its answers used the clock correctly ("Good morning / day /
afternoon / evening"): the clock is used, not stumbled over. The clock-omitting
projection was therefore not tested (the order made it conditional); omitting it would
make those answers guesses. The 27 September "~32 tokens at night" is not reproduced by
clock or greeting alone.

## 6. Barge-in after synthesis has finished (§5)

**Before:** barge-in reached only a delivery still being synthesised; once her last
segment was voiced the session held no active delivery, so his onset left the desktop
playing and the record said *completed*.

**Now:** generation, hand-off and playback are kept apart. His onset while a finished
answer is audibly playing stops the sink and marks the delivery; the desktop's next poll
is told to stop, and it stops the worklet and discards what it holds (its existing path).
**The record follows the desktop's own report** of the segment it interrupted: one
appended `interrupted` row (the `completed` row stays as the fact it was), prefix = every
segment up to and including the one cut, reason naming the segment cut off and those
never played; her message is untouched. A later report showing more was heard appends the
larger truth. Self-trigger safeguards unchanged (the onset rule is the recognizer's, as
before).

**Found through the real desktop first (BARGE-a):** the first version recorded the cut
from the service's estimate. With reports delayed 1.5 s, his words 1.1 s after her last
sound drew "segment 1 was cut off while playing" over an answer the desktop reported
completed — a false state. Repaired as above; the stop is still sent (harmless on a
silent player).

**Verified (BARGE-b, real desktop and player, `barge-summary-BARGE-b.json`):**

| | his words → stop poll | → worklet `stopped` | late pieces | her audio again | record |
|---|---|---|---|---|---|
| after synthesis, B1 (2) | 324, 418 ms | 326, 418 ms | 0 | 0 | desktop's segment, appended |
| after synthesis, reports delayed 1.5 s, B2 (2) | 323, 425 ms | 323, 425 ms | 0 | 0 | desktop's segment, appended |
| stop landing after she had finished (B2) | — | — | 0 | 0 | **stays completed** |
| in flight, control, B3 (2) | 326, 386 ms | 326, 386 ms | 0 | 0 | existing path |

Each after-synthesis turn was spoken 1.6 s after the service had offered all her audio,
while it was still sounding. Service-side decision 0.005–0.02 ms. The ~0.3–0.4 s is the
recognizer's onset and the desktop's poll, the same as in flight.

## 7. Continuations near the boundary (§6)

Behind `VAL_COMBINE_CONTINUATIONS=on`: a clear continuation received while the earlier
answer is still being made and has not begun to be heard supersedes it, and one answer
covers both of his messages; both stay canonical owner messages, in order, with their
relationship — nothing withdrawn, and a continuation is never taken for a replacement
(the clause classifier decides; only stop / replacement / continuation are acted on,
anything ambiguous waits as before). At most two restarts in a row
(`MAX_COMBINED_RESTARTS`). **The merge-window hold is kept**; the ~2.2 s endpoint-plus-
window floor stands and no one-second reply is claimed while it is mandatory.

Measured in S5 (final candidate C2b + C2c against the prior candidate P1a + P1b, speech
end → first real playback):

| S5 case | prior | final candidate |
|---|---|---|
| continuation, pause 1.6 s (the window's end) | **67.6 s, 129.7 s** (waited for the whole earlier answer) | **4.2 s** (joined in the window), **7.0 s** |
| correction, pause 1.6 s | 7.8, 10.2 s | 6.0, 7.3 s |
| correction, pause 2.3 s (past the window) | 10.9, 14.1 s | 5.9, 6.8 s |
| continuation, pause 0.8 s | 12.5, 11.8 s | 12.5, 12.8 s |

In C2b the 1.6 s continuation was joined inside the merge window (4.2 s); in C2c it
arrived after the early turn had been dispatched and was combined into one answer (7.0 s)
— the one `combined` decision in the two runs; both of his messages stayed canonical. The
corrections stayed corrections (superseded by his replacement). The 0.8 s continuation
is unchanged at ~12.5 s: the halves are joined, and the joined request is simply a long
answer. Computation: a combined or superseded early call is closed within 10–50 ms of the
decision (`supersede_race.py`, 30 trials, 1.0–48 ms), but a prefill already under way
runs to its end in the engine — the known engine limit.

## 8. Production isolation (§7)

Kept distinct: the four cache-setup steps were approved on 27 September and apply to the
experiment instance only; the launch-target change was refused and is his. Step 1 of his
procedure (`CACHE_EXPERIMENT.md` §2) re-verified today: `~/Projects/val-releases/13b3cb8`
at `13b3cb8638714f42e3509f06ba4e8e3b485c5300`, clean. Steps 2–4 (repoint, reload, verify)
remain his; **durable isolation is not in force** — and since 00:21 production runs master
(§0). No Voice session was open or restarted; no credential was read into any output.
**Consequence for this work:** the candidate is not merged into master. Its barge-in
repair and the spoken-path gate are not behind switches, so merging would put them into
whatever a production restart next loads. The branch `latency-2026-09-28` is pushed; CI
triggers on master and pull requests only, so the gate was mirrored locally.

## 9. The integrated result (§8)

Four runs through the real desktop frontend and playback worklet, 28 September afternoon,
S1–S5 each, the experiment instance reloaded before every run: prior candidate (the 27
September switches, renewal on) **P1a 13:04, P1b 14:01**; final candidate (§2–§7, hook
v2.3) **C2b 16:25, C2c 16:56**. `bench-summary.json` (`bench_summary.py`).

**Earlier runs of the candidate, kept, not counted in the headline.** C1a and C1b (hook
v2.2) found the eviction defect of §10; C2a (v2.3) lost its S5 session: the desktop
driver exited without writing its file, and its output had gone to the runner's tail;
the scratch store was rebuilt by C2b's start, so its turns cannot be attributed. **C2a is
missing evidence**, reported here rather than filled. The runner now keeps each driver's
own log (`driver-RUN-session-N.log`) and extracts the sessions that exist. C2c's store is
preserved (`store-C2c.dump`, PostgreSQL 18 custom format, 337 KB — kept on this Mac beside
the record; the repository ignores `*.dump`, so it is not committed).

**Speech end → her first real playback, identity-attributed** (no attribution uncertain
in either condition; turns spoken over her audio excluded):

| median / p90 / worst | prior (P1a, P1b) | final candidate (C2b, C2c) |
|---|---|---|
| social (26 each; LOW on the route 16 / 18, **MEDIUM fallback 10 / 8**) | 4.77 / 6.27 / 8.32 s | **4.45 / 5.92 / 8.31 s** |
| ordinary (34 each, all MEDIUM) | 6.19 / 9.76 / 10.14 s | **6.38 / 8.53 / 11.19 s** |
| explicit replacement (2 each) | 8.63, 9.06 s | **5.28, 6.31 s** |

**The ordinary median did not improve** (6.19 → 6.38 s, within run-to-run variance); the
upper tail did at p90 (9.76 → 8.53 s) and the single worst turn is worse (11.19 s, a long
reasoning turn — §10b). Reduced prefill is not solved latency: the prefill saving is real
(below) and reasoning absorbed it.

**Cache reuse, net prefill, resource pressure:**

| | prior | final candidate |
|---|---|---|
| tokens prefilled beyond the cache (78 attributed turns) | 99,154 | **55,410 (−44%)** |
| MEDIUM uncached tokens per turn, median | 1,194 | **652** |
| MEDIUM dispatch → first chunk, median | 2.05 s | **1.46 s** |
| MEDIUM dispatch → first visible text, median | 4.60 s | 4.34 s |
| turns cold / waits > 1 s behind maintenance | 0 / 0 | 0 / 0 |
| cold primes | 4 of 112 (after the reloads) | 4 of 113 (after the reloads) |
| hook decisions | measurement only (210) | divergence 47, no gain 66, exact entry 98 |
| store, most / engine active memory, most | 1.88 GB / 14.16 GB | 1.72 GB / 13.99 GB |
| lowest free memory / swap growth per run | 45% / 420, 24 MB | 43% / 120, 8 MB |

**Cold start, apart:** Voice On → Ready 17.5 s and 17.4 s for the first session after a
reload in the prior condition, 21.1 s and 18.4 s in the candidate (both prefixes cold);
warmed sessions 3.8–7.7 s (prior) and 3.8–7.6 s (candidate).

**Incomplete speech, timeouts, failures:** one runaway segment in each condition ended by
the speech-length bound as a named failure ("segment 2 began and did not complete");
two superseded deliveries in the candidate (the replacements, correct); no counted turn
without a played answer; driver waits over 240 s: 4 (prior), 5 (candidate) — the "spoken
over her audio" turns, excluded from latency. *Corrected 28 September (evening, `LIFECYCLE_REPAIR.md` §2): they did not follow long answers and she was not speaking. Eight of the nine followed a replacement or combined answer whose hand-off a late superseded worker had taken away, so its closing piece never reached the player; the ninth (C2c S5) followed a runaway segment whose failure stop never reached the player for the same reason. A defect, now repaired.* Missing: C2a (above);
four joined pause turns have no endpoint-anchored timeline, so §10b omits them.

**Barge-in after synthesis** (§6): 323–425 ms from his words to the worklet's `stopped`,
equal to the in-flight path. **Playback-race and speech-bound evidence of 27 September
preserved** (unchanged files; the bound fired once per condition here and ended honestly).

## 10. Found in the integrated run, repaired

**(a) The static prefixes were not protected in practice (C1, hook v2.2).** With the split
layout a turn is served from a longer divergence checkpoint, so the persona checkpoint
beneath it was never the entry a hit returned, was never renewed, and aged out of the
ten: 10 cold primes against 4, and three "thanks, into maintenance" turns waited 4.5–4.8 s
behind them. **v2.3 renews every stored prefix of the entry used, shortest last**
(`hook_regression.py`: persona evicted under the earlier renewal, kept under v2.3).
C2b/C2c: 4 cold primes (the reloads), no wait.

**(b) Where the ordinary-turn wait now goes** (`wait_decomposition.py` →
`wait-decomposition-candidate.json`, 30 counted MEDIUM turns of C2b + C2c; the interval
from his speech end to her first real playback cut at the service's own timeline marks,
consecutive on the critical path so each turn's pieces sum exactly to its total — checked,
0 ms residual on every turn; overlapping work — later segments' synthesis, generation
continuing behind the first segment, maintenance — is off the path and not added):

| piece | median | p90 | mean | share of the mean | prior mean |
|---|---|---|---|---|---|
| endpoint (400 ms silence rule + decode) | 466 ms | 519 | 471 | 7% | 399 |
| confirmation (resume window) | 260 | 276 | 258 | 4% | 262 |
| Core before dispatch (persist, assembly, preflight; queue/maintenance) | 64 | 69 | 64 | 1% | 63 |
| prefill (dispatch → first chunk; engine's own restore + prefill 1,044 ms median for 682 tokens) | 1,492 | 1,889 | 1,517 | 23% | 1,942 |
| **hidden reasoning** (first chunk → first visible text) | **3,041** | **4,738** | **3,357** | **51%** | 3,024 |
| first usable segment (first pause after 60 characters) | 214 | 330 | 201 | 3% | 182 |
| synthesis of the first piece (1.0 s stream pieces) | 780 | 841 | 724 | 11% | 705 |
| desktop collection, merge-window hold, playback start | 52 | 84 | 52 | 1% | 46 |
| **total** | **6,304** | **8,526** | | | 6,188 median |

No turn queued behind maintenance, and the merge-window hold never bound an ordinary
turn (its audio is ready later than the window closes). Prefill fell by 0.43 s on
average; reasoning rose by 0.33 s on average — whether the split layout (the per-turn state
after his words) lengthens MEDIUM's reasoning or this is variance is **not established**
(reasoning spread is 1.5–8 s within one condition).

## 11. The stalled turn — OPEN

C1a (hook v2.2, 13:51:59): his utterance was submitted early by the adaptive endpoint,
speech resumed 0.55 s later, the early call was superseded (the engine logged the
client's disconnect at 13:52:01) — and the turn's worker thread never returned: no
"superseded" record, no joined turn, the session sat until his next utterance **243 s
later** superseded it, and the answer that finally played was to the earlier words.
Not repaired. What is known: the adapter ends superseded streams in 1–48 ms in 30 of 30
forced races across the prefill's end (`supersede_race.py`); of the 63 resumes after an early submission in
today's runs (C1a, C1b, P1a, P1b, R1 — 24 targeted — C2b, C2c), one stalled; the stuck
thread was not the session lock (later utterances were handled). What is not known: where
the thread was. The scratch service now dumps every thread's stack on SIGUSR1
(`serve_experiment.py`) and `stall_watchdog.sh` requests it when a resume is not followed
by a turn within 45 s — the next occurrence will show the stack. **Until repaired, the
adaptive endpoint's resume path (27 September candidate) is not fit for admission**, and
no later successful run closes this.

## 12. Identities

- Candidate code: branch `latency-2026-09-28`, frozen `a5d9680`; the records commit
  follows. Switches for the candidate: `VAL_FAST_ROUTE_TIERS=1 VAL_TIER1_ROUTE=low
  VAL_ADAPTIVE_ENDPOINT=on VAL_REQUEST_CONSTRUCTION=split_state VAL_OWNER_PRECEDENCE=on
  VAL_TTS_LENGTH_BOUND=on VAL_COMBINE_CONTINUATIONS=on`. Prior: the same without the
  last and with `envelope_in_system`.
- Engine hook: `infrastructure/lmstudio/cache_renewal/val_cache_renewal.py` **v2.3**,
  installed sha256 `3773168dd12f62281e2eedfe7c29d198350c95d8274e2abf91f30356fe76cfae`
  (v2.1 `03cf7f11…`, v2.2 `a20b7788…` during the day); `.pth` `1868b566…`; engine
  `mlx-llm-mac-arm64-apple-metal-advsimd@1.11.0` / `app-mlx-generate-mac14-arm64@34`,
  pinned digests unchanged. Allowlist `~/.lmstudio/val-cache-renewal.json` names only the
  clone `~/.lmstudio/models/val-experiment/gpt-oss-20b-MXFP4-Q8-renewal`; flags
  `renewal`, `divergence_checkpoint`. Instance `val-exp-gpt-oss-20b` (loaded now; unload
  with `lms unload val-exp-gpt-oss-20b`). Production's instance is declined by the hook.
- Production: launchd `house.armand.val.api`, pid 958, master `6bad617` since 00:21:18;
  live store `0031_prefix_prime`; release directory `13b3cb8` built, not in force.

## 13. Remaining limits and the next decision

**Limits.** The ~2.2 s endpoint-plus-window floor stands. MEDIUM's hidden reasoning is
half of an ordinary turn's wait (3.0 s median, 4.7 s p90) and nothing in this candidate
touches it. Of the prefill that remains (~680 tokens, ~1.0 s in the engine), most is her
previous answer and the per-turn state: her answer is stored with its hidden reasoning,
so the next request (which renders the answer without it) diverges at her answer and
cannot reuse it. The stalled turn (§11) is open.

**Recommended next repair — correctness first:** find and bound the stalled-turn path
(§11): with the stack instrumentation in place, reproduce under the resume pattern; and,
whatever the cause, give the session a bounded wait for a superseded call so a stuck
thread cannot hold his next words for minutes. No latency change should be admitted
before it.

**Then, for latency, the two measured levers are both his to rule on:**

1. *A conversation-level prime after each answer* (the open decision since 25 September;
   the priming ruling excluded conversation content). While he is listening, prefill the
   next request's stable part — persona, steady state, the history including her answer
   as it will be rendered — so that only the per-turn state and his words remain.
   Expected: most of the ~1.0 s engine prefill per ordinary turn (≈ −0.7 to −0.9 s).
   Costs: one more local call per turn, idle-time work that collides with his next
   words if he speaks within ~1 s (the prime's prefill cannot be cancelled; the refresh
   rules already wait for idleness), one more store slot (protected by v2.3). $0.
2. *Reasoning effort for ordinary turns.* Only effort changes the 3 s. LOW was 25% faster
   to first visible text on 23 September and lost a correction-preservation and an
   instruction-boundary check (40/44 against 41/44); "MEDIUM for substantive work" is his
   standing instruction. Not recommended without a narrower, measured class and his ruling.

With both, ordinary replies would still begin about 4.5–5 s after he stops speaking; a
reply in about one second is not reachable while the answer is reasoned out after his
words end.

**Correction, 28 September 2026 (night; `2026-09-28-checkpoint/EFFORT_EXPERIMENT.md` §8).** The renewal clone (`val-exp-gpt-oss-20b`) has no LM Studio hub definition, so it ignored `reasoning_effort` and rendered "Reasoning: medium" for every request, and used LM Studio's generic sampling defaults rather than production's. **The Tier-1 route's "LOW" requests in these runs ran at MEDIUM**, so the social figures here are Tier-1 requests at MEDIUM effort. The MEDIUM-against-MEDIUM comparisons (renewal, divergence, layout) stay internally valid. The 26 September Tier-1 LOW qualification, on the real `openai/gpt-oss-20b` instance, is unaffected.
