# The Voice latency candidate — owner order of 27 September 2026 ("complete the remaining latency work")

Labels: OBSERVED (measured here), DERIVED (computed from observed marks), NOT MEASURED.
Every model call in this pass was local at a known $0. **Production unchanged**: service
on `13b3cb8`'s code, live store `0031`, no candidate setting in the launchd environment,
installed desktop `13b3cb8`, production Voice unused throughout (16 sessions before and
after). Nothing here is deployed.

## 1. Maintenance and the prompt cache (§2)

**The cause, established.** LM Studio's MLX engine (`mlx-llm…@1.11.0`, vendored
`app-mlx-generate…@34`) keeps prompt checkpoints in `LRUPromptCache(max_size=10)`, and
only an *insertion* moves an entry to the back of its queue — a hit renews nothing, so the
"LRU" is first-in-first-out per cache type (`ORDINARY_TURN.md` §12). Val's two persona
checkpoints are inserted once and used on every turn, so they are always the oldest
checkpoints; every turn adds a checkpoint and a snapshot of its own; after about four
turns the persona checkpoints are evicted and the next prime or turn pays a cold prefill
of ~5,000 tokens (~7 s), whatever the scheduling does. It is not capacity (the store holds
ten; the problem is which ten), and not memory (entries are the same size either way).

**The smallest effective change, shown on the engine's own code.** A faithful replay of
the engine's rules (`CacheWrapper.update_cache`, `_flush_live_cache`, `_restore_cache`'s
retry for an untrimmable exact hit, checkpoints at `prompt − 11`, snapshots at the next
request) driven through the vendored `mlx_lm.models.cache.LRUPromptCache` itself, with the
request pattern of a Voice conversation (a turn, then the refresh of both persona entries;
`cache_renewal_replay.py` → `cache-renewal-replay.txt`, rerun under the engine's own Python
3.11 against the committed hook):

| sixteen turns | as shipped | recency renewed on a hit |
|---|---|---|
| alternating LOW and MEDIUM | **8 cold primes** (both entries, every fourth turn) | **0** |
| MEDIUM only | **8** | **0** |

The change: after `fetch_nearest_cache` returns an entry, move that entry to the back of
its own queue — what `insert_cache` already does for a re-inserted key. Capacity, the
eviction order between cache types, exact-prefix matching, what is stored and when: all
unchanged; nothing is retained that the store would not retain, and nothing but the engine
reads it. It is written as `infrastructure/lmstudio/cache_renewal/val_cache_renewal.py`,
an import hook that wraps one model instance's history object, applied **only** to model
directories named in `~/.lmstudio/val-cache-renewal.json` (production's path deliberately
absent), switchable per call for A/B, failing to "engine unchanged" on any error; and
`install.py`, which refuses unless the engine's three relevant files match pinned SHA-256
digests, installs two files into that engine's site-packages, and `remove` restores the
engine byte-for-byte.

**Not installed.** Installing it — the two files into LM Studio's engine directory, an
APFS copy-on-write clone of the model directory for an isolated experiment instance, and
loading that instance beside production's — was **refused by this session's permission
classifier**, and was not pursued by any other route. The live effect of the fix is
therefore NOT MEASURED; the qualification below runs on the engine as shipped, and every
turn that paid a cold prefill is identified from the engine's own `Prompt cache: using N/M`
line so its share of the tail is known.

## 2. The confirmation delay (§3)

Design (results in §5–§7): the recognizer endpoints after **400 ms** of silence
instead of 650 ms, and the resume window is sized from the final transcript's shape by
`val_policy.turn_completion.endpoint_completion`, within the fixed path's own total silence
bound (~1.9 s):

- `complete` (window 0.12 s → ~0.65 s of silence before submission): a closed greeting,
  thanks or farewell; a closed question of three words or more; a closed sentence of four
  words or more — **never punctuation alone**, and never with a trailing conjunction,
  preposition, article, auxiliary-without-a-mark, "whether", or hesitation;
- `uncertain` (1.37 s → ~1.9 s, the same as today): everything else — a bare "Yes.",
  "Stop.", "The venue.", no terminal mark;
- `continuing` (2.07 s → ~2.6 s, longer than today): a pause mark, an unfinished tail, a
  hesitation.

Speech that resumes inside the bound **after an early submission** is the rest of the same
utterance: the early turn is cancelled (its stream shut down, its hand-off never played),
withdrawn through the existing retraction machinery when its thread ends, and the halves
are submitted as one new turn — never a half-question answered, never a duplicate, never
an abandoned request (`test_adaptive_endpoint.py`, 4; `test_endpoint_completion.py`, 25).
Speech resuming after the bound is its own turn. `VAL_ADAPTIVE_ENDPOINT=on`; no model
dependency.

## 3. Interruption in the candidate (§4)

The corrected conservative owner precedence and the socket-shutdown cleanup of the
previous pass are in the candidate (`VAL_OWNER_PRECEDENCE=on`). **One defect found by the
first pilot and repaired:** "heard" was the desktop's playback report for *any* segment,
but the desktop holds its reports for segments voiced before her answer is written — so a
streamed answer could be audible for seconds with no report, and a late report for an
*earlier* answer's tail could mark a new, unplayed answer as heard (the pilot's resumption
was refused as "already heard" that way). "Heard" is now scoped to the answer in flight:
its own `playback_started` report, or its first handed-over piece having begun to play by
the playback-occupancy estimate (`test_owner_precedence.py`, 16, including the late-report
case). Barge-in once playback has begun is unchanged.

## 4. Method (§6)

`voice_bench_plan.py` renders a compact representative set — three short conversations,
eighteen turns: greetings, thanks and farewells; factual, conversational, substantive and
follow-up questions; a continuation after a pause, a hesitation, a correction after a
pause; immediate replies (0.3 s), replies landing just after maintenance begins (1.8 s),
and an explicit replacement spoken while the earlier answer is being made — in the macOS
voice the earlier harness used. `voice_bench.mjs` drives the **unmodified desktop
frontend** (its dev server, pointed at the isolated scratch service) in headless Brave and
replaces **only the microphone**: `getUserMedia` returns a stream the driver feeds, so each
utterance is spoken when the conversation calls for it; a listener beside the frontend's
own on the real playback worklet says when her audio actually starts, ends and whether it
ever underran. `voice_bench_extract.py` matches each turn to his persisted message **by
identity** and its answer's first playback from the frontend's own report; three measures
of speech end → first real playback are kept (the worklet's first audio after the driver's
exact speech end, the headline; the desktop's own report; the store's first playback row),
and the first two agree within ~0.1 s (§5 on the third). Readiness is
reported apart from the turn figures. `run_voice_bench.sh` runs one condition;
`voice_bench_summary.py` aggregates.

Conditions: **baseline** — master's code as of this order with production's settings
(every turn MEDIUM, the fixed endpoint and window, the request as it stands). That code
carries Milestone A's readiness and refresh maintenance, which production (`13b3cb8`)
does not run, so the baseline is the undeployed master, not the deployed service; **candidate** — the
corrected Tier-1 LOW route, the adaptive endpoint, the request-construction candidate with
per-route prime boundaries, owner precedence. Three runs each, alternating.

Every run: the isolated scratch service on port 8766 against the scratch store
(`val_test`), the desktop's dev server on 5173, the production LM Studio instance shared
read-only as before (the harness never ran while production Voice was in use — sixteen
production sessions before and after every run). Six runs, alternating B1 C1 B2 C2 B3
C3, 27 September 2026 03:05–04:43; then C4 (the speech bound added, 04:44–04:57), C5 (the
refresh repair of §7a, 05:00–05:13) and C6 (the guard of §7b, 05:14–05:27), each after the
repair it names. The model instance is production's LM Studio instance, used while
production was idle, as in every earlier pass; each run's requests leave their own
entries in its prompt store, which production's next turn meets as it would any turn's.

## 5. Results (§6) — speech end to her first real playback

OBSERVED. Each figure runs from the driver's exact last sample of his speech to the first
audio the frontend's real playback worklet started afterwards, both on the page's clock;
the desktop's own report agrees within ~0.1 s at every median. The store's first
`playback_started` row is **not** the headline: a pre-existing race (§10) can lose a
segment's start report, and on 15 of 146 counted turns the store's first row is a later
segment's, one segment late. A turn the plan speaks after her answer has played but which
was spoken while her audio was still sounding measures a barge-in, not the turn; seven are
excluded and named in the summaries (five baseline, spoken over the runaway segments of
§9; one in C1 and one in C5, spoken over a long answer). No counted turn in any condition
went without a played answer; the replaced turn never played, by design.

Four conditions. **Baseline** B1–B3. **Candidate as built** C1–C3 (§2–§4 with the
Tier-1 LOW route). **Bound, before the refresh repair** C4 (the speech bound added).
**Final** C5–C6 (the refresh repair of §7a; C6 also withholds the misrouted class of §7b).

| median / p90 / worst | turns | social | ordinary |
|---|---|---|---|
| baseline, 3 runs | 46 | 8.98 / 11.19 / 16.31 s | 9.66 / 14.75 / 17.11 s |
| candidate as built, 3 runs | 50 | **3.25 / 5.02 / 8.31 s** | **6.96** / 14.99 / 23.90 s |
| bound, before the refresh repair, 1 run | 17 | 4.04 / 5.55 / 8.23 s | 11.30 / 19.24 / 19.90 s |
| **final, 2 runs** | 33 | **3.17** / 9.52 / 15.91 s | **7.65** / 14.04 / 16.58 s |

**The tail is the engine's.** A turn that prefilled cold (the engine's own "Prompt cache:
using 0/N" line) or waited more than a second behind a cold prime is *affected*: baseline
11 of 46, candidate as built 5 of 50, C4 8 of 17, final 8 of 33. Split on that fact:

| median / p90 / worst | unaffected social | unaffected ordinary | affected turns |
|---|---|---|---|
| baseline | 7.50 / 8.82 / 8.98 s (9) | 9.33 / 12.27 / 14.75 s (26) | 11.19 / 16.31 / 17.11 s (11) |
| candidate as built | 3.18 / 4.76 / 5.77 s (17) | 6.67 / 9.63 / 13.86 s (28) | 16.87 / 23.90 / 23.90 s (5) |
| final | 3.09 / 4.23 / 7.16 s (9) | **6.10 / 8.78 / 10.12 s** (16) | 13.55 / 15.91 / 16.58 s (8) |

Social turns on the light route, final: 3.05 s median (7 turns, worst 3.27 s). No underrun
in any played answer in any condition.

Per turn class, baseline → candidate as built (medians): greeting 7.55 → 2.97; thanks after
an answer 8.82 → 2.97; farewell after an answer 10.71 → 4.63; factual 7.89 → 4.79;
conversational 12.27 → 6.36; substantive 11.48 → 6.76; follow-up 9.11 → 5.31;
continuation after a pause 8.99 → 10.02; hesitation 12.75 → 13.86; correction after a
pause 11.84 → 5.90; follow-up 0.3 s after her answer 8.74 → 8.48; question into
maintenance 7.78 → 7.45; thanks into maintenance 9.22 → 4.76; explicit replacement 15.11 →
16.87. The two classes slower in the candidate are C1's cold turns after the dropped
refresh (§7a) and the replacement's cold prefill (§7).

**What that is.** Where the engine's cache did not intervene, **social turns fall from
~7.5–9 s to ~3.1 s and ordinary turns from ~9.3 s to ~6.1–6.7 s**, the ordinary upper tail
from ~12.3 s to ~8.8–9.6 s. Where it did, a turn costs 11–24 s in every condition, on
10% to 47% of a run's turns with no consistent difference between conditions (§7). So the
median improvement is substantial and repeatable; **the upper tail is not improved, and
every turn in it traces to the engine's eviction or its unstoppable prefill** (§1, §11). The ~1 s target is not
met, and nothing here approaches it.

## 6. Where an ordinary turn's time goes now (§5)

DERIVED from each turn's own timeline (medians, conversation route):

| stage | baseline | candidate |
|---|---|---|
| speech end → endpoint (configured silence + the measured ~0.13 s final decode) | ~0.78 s | ~0.53 s |
| endpoint → turn submitted (the resume window) | 1.24 s | **0.26 s** |
| exact preflight | 0.03 s | 0.03 s |
| dispatch → first streamed chunk (prefill of the uncached suffix) | 1.96 s | 1.96 s |
| dispatch → first visible word (prefill + hidden reasoning) | 5.83 s | **4.59 s** |
| visible word → first speech segment | 0.10 s | 0.18 s |
| segment → first audio at the sink | 0.62 s | 0.74 s |

In the candidate's median ordinary turn of ~6.7–7.0 s: **hidden MEDIUM reasoning ~2.6 s**
(dispatch→visible minus dispatch→first chunk), **prefill of the envelope, history and his
words ~2.0 s**, the confirmation delay ~0.8 s, speech ~0.9 s, the rest under 0.5 s. **MEDIUM
reasoning and prefill together are two-thirds of an ordinary turn's wait**, and nothing
in the pipeline around them is left that could buy back more than a few hundred
milliseconds. The first segment is cut at the first natural pause past 60 characters
(the targeted voice latency order of 25 September 2026, unchanged here); segment → first audio is the streamed first piece (~0.5 s on
the light route's short answers, ~0.7 s on MEDIUM's longer first segments). Nothing
unchecked, pre-scripted or filler is spoken: every word played is a slice of her
persisted answer.

The request-construction candidate (envelope in the developer block, per-route prime
boundaries) accounts for the ~1.2 s of dispatch→visible: a shorter hidden reasoning
before the first visible word, as the frozen-history comparison showed (4.96 → 3.98 s).
The adaptive endpoint accounts for ~1.2 s more (0.25 s of silence and ~1.0 s of window).

## 7. Collisions, interruption, resumption and corrections

- **Pauses inside a request** (continuation, correction): in every candidate run the
  first half was submitted early (a closed sentence), speech resumed inside the bound,
  the early turn was cancelled before anything played and withdrawn, and the halves were
  answered as one — twelve resumptions in six candidate runs, each fragment withdrawn,
  **no half-answer played, no duplicate, the correction preserved every time** (every
  answer, in every condition, named a ghost story, never a mystery novel). The hesitation ("I was
  wondering, um, whether…") was held on the long window each time and never split.
- **Explicit replacement**: every candidate run superseded the earlier answer before
  it was heard (precedence outcome `superseded`, `answer_heard: false`), none of it
  played, and the replacement was answered. It is the one class slower in the candidate
  (15.11 → 16.87 s median; worst 23.90 s), and it is the engine: the superseded request's
  prefill cannot be stopped ("If the model is busy processing the prompt, it will finish
  first"), so the replacement waited 4.7 s in its preflight, and then prefilled **cold**
  because the persona checkpoint had been evicted (C1, C3, C4, C5: 14.8–23.9 s; warm in
  C2 and C6: 7.4 s and 5.4 s).
- **Utterances into maintenance**: a reply 1.8 s after her answer lands on a refresh
  prime. When the prime is warm it costs nothing measurable; when it is cold it cannot be
  preempted — the light route's one slow turn (8.3 s, C2 "Thanks.") waited 4.9 s behind
  one.
- **Cold prefills**: baseline 4 of 46 counted turns; candidate as built 4 of 50 (two
  replacements, and C1's two turns after the dropped refresh of §7a); final 5 of 33 (two
  substantive questions, a correction, a replacement, and the thanks §7b moved to MEDIUM).
  Cold primes 12 of 48 (baseline, ~7 s, one entry), 17 of 53 (candidate as built) and 14
  of 38 (final) — ~7 s for one entry and **~13 s when both route prefixes are cold**.
  Two prefixes put twice the pressure on the same ten-entry first-in-first-out store —
  the eviction §1 identifies, measured on the live engine.

**Every upper-tail turn in the candidate traces to the engine's eviction order or its
unstoppable prefill.** None traces to the endpoint, the route, the request or speech.

## 7a. A maintenance delay found in the runs, and removed (§2)

An owed refresh prime waits for a second of idleness, and was **dropped after 60 s
without it** ("refresh dropped (the session never fell idle)"). A substantive answer of
hers is often longer than that — C1's answer to "How long should a first chapter be?"
and C4's to the suspense question each ran about two minutes of speech — so the refresh
was dropped while she was still speaking, nothing restored the evicted persona prefix,
and his next turn prefilled cold: C4's follow-up 12.3 s (8.4 s of it the cold prefill),
C1's continuation 17.1 s and hesitation 15.0 s. The desktop meanwhile kept "Warming up…"
on screen — truthfully, since the prefix was not warm — which is also what held the
driver past its 150 s wait (§9). **Repaired:** an owed refresh now waits for as long as
the session is open and runs at the first idle second after she stops
(`VoiceSession._schedule_refresh`; `test_prime_waits_for_playback.py`, the long-answer
case). In C5, with the repair, the same follow-up after a two-minute answer was warm:
**4.58 s**; no refresh was dropped in C5 or C6. Dropped refreshes per run before the repair: B1 2,
B2 4, B3 1, C1 3, C2 0, C3 1, C4 3 — the baseline paid it too. This is not gated: it
changes when maintenance runs, never what is said. Production (`13b3cb8`) has no refresh
at all; the rule was master's and the released tag's (Milestone A), so this finding is
against `tier1-low-release-2026-09-27` as well.

## 7b. A misroute found in the runs, and withheld (§6)

The light route's released classes are those that answered right in every run. One did
not here: a bare "Thanks." after "Name a famous mystery novel. No, a famous ghost story."
drew the corrected answer again from LOW in C1 ("The Turn of the Screw.") and C5
("My lord, *The Haunting of Hill House* by Shirley Jackson is a celebrated ghost
story."), and a greeting in C3 ("Good day, my lord."); right in C2 and C4. "Thank you."
after a factual answer was right in all five. The pending-work guard names correction
words ("actually", "instead", "never mind") but could not see a sentence that opens
with "No," at all, and its "wait," never matched before a space (a word boundary after a
comma needs a word next). **Withheld:** a previous message of his that corrects itself
— a sentence or clause opening with no, nope, wait, sorry, "I mean", "scratch that",
"correction" — keeps courtesy after it on MEDIUM, and counts as a request in the walk
over earlier exchanges (`val_policy.light_conversation._SELF_CORRECTION`;
`test_courtesy_pending.py`, five cases; the fresh-set counts unchanged). It errs toward
MEDIUM ("Snow, no wind." is caught too). **The released tag `tier1-low-release-2026-09-27`
carries the same guard and therefore the same misroute**; this finding is against it too.
In C6, with the guard, "Thanks." after the correction went to MEDIUM and was answered
"You're most welcome, my lord." — at 15.9 s, a cold prefill and a wait behind a cold prime
(§5): withholding costs this class the light route's speed until the cache is repaired.

## 8. Readiness, kept apart

Voice On to "Ready" as the desktop displays it (OBSERVED, nine sessions per condition):
baseline 3.2–11.7 s (median 6.1; the first session of each run 9.9–11.7), candidate
3.8–17.5 s (median 5.0; the first session of each run 17.0–17.5 — both prefixes primed
cold, which is what "Ready means ready" requires). C4–C6, each started straight after
another run: 3.6–9.6 s. Readiness is not in any turn figure.

## 9. Speech that did not stop (a pre-existing defect, found here)

Two baseline runs stalled on one answer each: in B2 one segment played for **327.7 s —
7,864,320 samples at 24 kHz, exactly 4,096 codec tokens at 12.5 per second**, Qwen3-TTS
`generate`'s default `max_tokens`, reached because the model never emitted its end of
speech; in B1 one segment played for 128 s until his next utterance stopped it. The turns
the driver spoke over that audio are the five baseline exclusions of §5. (C1 and C4 also
tripped the driver's 150 s wait, but not on a stall: each followed an answer of about two
minutes of speech, and the desktop kept its "Warming up…" line up afterwards because the
refresh had been dropped — §7a. Those turns are kept where her audio had ended.)
Nothing bounds it. **Production has the same exposure.**
The candidate carries a bound **without touching the runner production spawns**:
`infrastructure/speech/qwen_tts_speak_bounded.py` wraps the unchanged
`qwen_tts_speak.py`, bounding each segment's codec tokens in proportion to its text
(at least 4 s; 5 characters per second as the slowest plausible reading, about a third
of her ordinary pace; 12.5 tokens per second) and saying so on stderr when the bound is
reached. `VAL_TTS_LENGTH_BOUND=on` selects it (`QwenTTSSpeech(runner_path=…)`); unset, the
original runner runs.

**Through the real path (C4–C6, bound on):** the wrapper was the resident speech worker
(`qwen_tts_speak_bounded.py serve`); no answer stalled; the longest segment played 17.8 s;
in C4's store every one of the 90 segments with both reports ended well inside its bound
(the closest at about a third of it; her median pace 16 characters per second); segment → first
audio unchanged (0.47 s light, 0.74 s MEDIUM). No runaway occurred in C4–C6, so the bound
was never reached live; that it stops one rests on the library honouring `max_tokens` on
the streaming Base path (read in `qwen3_tts.py`) and on the unit test. C4 ran with the
constant at 12 tokens per second before the codec rate was measured at 12.5, a bound 4%
tighter than stated; C5 and C6 ran with 12.5.

## 10. Defects found on the way, and what was done

- **"Heard" credited the wrong answer** (§3): repaired in the candidate, tested.
- **Runaway speech** (§9): pre-existing, production exposed; bounded in the candidate
  through a wrapper, production's runner untouched.
- **A playback report can be lost** (pre-existing, not repaired here): when the desktop
  releases a segment's held `playback_started` and `playback_completed` together, both
  inserts compute the same next event number, the unique constraint refuses one, and the
  endpoint answers 500 — the frontend ignores it, so nothing breaks audibly, but one
  record of what the speakers did is missing (seen in every run, baseline and
  candidate). The refusal is by design (`record_playback`'s docstring); the loss is not. The fix is a retry of the refused
  insert, in ungated service code outside this order's scope — recorded, not done.
- **A startup warning named the wrong light route**: with `VAL_TIER1_ROUTE=low` it still
  named the Qwen candidate; it now names the configuration actually promoted.
- **An owed refresh was dropped after 60 s** (§7a): repaired on master, ungated; a finding
  against the released tag.
- **Courtesy after a self-corrected request went to LOW and was answered wrongly** (§7b):
  withheld; a finding against the released tag.
- **The engine hook would not have loaded**: the repository's formatter targets Python
  3.14 and rewrote the hook's `except (OSError, ValueError)` into the 3.14-only form,
  which the engine's Python 3.11 refuses; written as two clauses, and both cache files
  compile under the engine's own interpreter. The speech wrapper compiles under its 3.12
  runtime. Found before anything was installed.

## 11. The decision returned — outcome B

**Completed and qualified in isolation:** the adaptive endpoint (§2), the corrected
precedence and resumption (§3, §7), the request construction with per-route prime
boundaries (§6), the corrected Tier-1 LOW route, the speech bound (§9), the refresh that
is no longer dropped (§7a) and the self-correction guard (§7b). Through the real desktop
frontend and player, speech end to her first audio: **social 8.98 → 3.25 s median (three
runs; 3.17 s in the final two), ordinary 9.66 → 6.96 s (7.65 s final)**; on the turns the
engine's cache did not intervene in, **social ~7.5 → ~3.1 s and ordinary ~9.3 → ~6.1–6.7
s, with the ordinary 90th percentile ~12.3 → ~8.8–9.6 s**. Corrections preserved, no
half-answer, no unheard answer credited as heard, no underrun, no substantive turn on
LOW. **The upper tail is not improved**: cold prefills and waits behind cold primes put
11–24 s on a turn in every condition.

**Not finished, and why — one authorisation.** The cache correction (§1) is written,
digest-pinned against the engine files it depends on, reversible byte-for-byte, and
shown on the engine's own cache class to remove every cold prime of a sixteen-turn
conversation. Measuring it needs four things this session's permission classifier
refused and which were not attempted any other way:

1. `python infrastructure/lmstudio/cache_renewal/install.py install` — adds
   `val_cache_renewal.py` and `val_cache_renewal.pth` to the site-packages of LM
   Studio's vendored engine `app-mlx-generate-mac14-arm64@34` (inert for any model not
   listed; `install.py remove` restores the engine);
2. `~/.lmstudio/val-cache-renewal.json` naming **only** an experiment copy of the model;
3. an APFS copy-on-write clone of `~/.lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8`
   under a separate directory, so production's model path is never in the allowlist;
4. `lms load` of that clone as a separate identifier, 32,768-token context,
   `--parallel 1`, beside production's instance, for the qualification only.

It touches the software production runs on. The engine directory is shared, so the
`.pth` line imports the hook into **every** model instance that engine loads, production's
included; there it reads the allowlist, finds production's path absent, and changes
nothing — but it is code of ours running in production's inference process, and a second
~12 GB GPT-OSS instance must fit beside production's for the measurement. That is why it
is his to authorise, and why it was not done. Every upper-tail turn in the candidate (§7) — the cold
replacement, the waits behind cold primes, the doubled cold primes of two route
prefixes, the 17 s first-session readiness — is what it would remove; **its effect is
NOT MEASURED** and no figure is claimed for it.

**The architectural decision, stated precisely.** With the pipeline around it reduced,
an ordinary turn's remaining wait is MEDIUM's hidden reasoning (~2.6 s median) and the
prefill of the envelope, history and his words (~2.0 s), both inside the model call. No
work authorised in this order reduces either further: MEDIUM is kept, the persona and
the honesty rules are unchanged, conversation-content priming was excluded, speculative
decoding has no compatible path on this engine, and closing a stream cannot stop a
prefill. The measured alternatives on the table, each his decision:

- **LOW for ordinary turns** — first visible text ~25% sooner (10.75 → 8.01 s on the
  22 September measurement), but 40/44 against MEDIUM's 41/44 on the frozen checks, one
  of the losses a correction-preservation failure;
- **a smaller or different local model** — Qwen3-4B failed its qualification on the
  persona whole; no other candidate is qualified;
- **no change** — the candidate as it stands, ordinary turns ~7 s at the median.

The **~1 s target** cannot be met by an arrangement in which an answer is generated
after he stops speaking: the candidate's fastest class (a greeting on LOW) is 2.98 s,
of which confirmation is ~0.8 s, the LOW call to its first words ~1.7 s and the first
streamed audio ~0.5 s. Reaching it would need her first words to be generated before
the turn is confirmed (speculation, measured earlier at −0.9 s on greetings and +1 s on a
corrected substantive request) or a model call that is itself far faster than any
admitted today.

## 12. Identity and rollback

Candidate code: this commit on master. With every switch unset, master behaves as the
baseline did (every turn MEDIUM, the fixed endpoint and window, the request as it stands),
except that an owed refresh is no longer dropped (§7a), which applies either way; the gate
mirror runs with every switch unset. Settings, all six for the full candidate:
`VAL_FAST_ROUTE_TIERS=1`, `VAL_TIER1_ROUTE=low`, `VAL_ADAPTIVE_ENDPOINT=on`,
`VAL_REQUEST_CONSTRUCTION=envelope_in_system`, `VAL_OWNER_PRECEDENCE=on`,
`VAL_TTS_LENGTH_BOUND=on`; the light route needs migration `0032_light_conversation` on
the store. Rollback: remove the settings and restart; the migration is additive and
stays. Evidence: `cache_renewal_replay.py` → `cache-renewal-replay.txt`;
`voice-bench-B{1,2,3}.json`, `voice-bench-C{1,…,6}.json` with their `-session-N.json`
driver files (the service logs `service-bench-*.log`, 69 MB, stay on this Mac — `*.log`
is git-ignored, as for every earlier run); the rendered utterances `voice-bench-plan.json`,
so every condition heard identical audio; the two development pilots
`voice-bench-pilot-candidate*.json` (the "heard" defect of §3) and
`voice-bench-pilot2-candidate*.json` (driver development; its extract is not evidence);
summaries `voice-bench-summary-B-C.json`,
`voice-bench-summary-C4.json`, `voice-bench-summary-C5.json`, `voice-bench-summary-C6.json`,
`voice-bench-summary-C5-C6.json`; driver `voice_bench_plan.py`, `voice_bench.mjs`,
`voice_bench_extract.py`, `voice_bench_summary.py`, `run_voice_bench.sh`. **Not deployed;
not ruled.**
