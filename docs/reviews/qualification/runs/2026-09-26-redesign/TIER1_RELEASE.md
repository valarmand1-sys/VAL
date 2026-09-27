# Milestone A — the narrow Tier-1 release, prepared: readiness, prime scheduling, the courtesy decision — 26 September 2026

Owner order "PREPARE THE LOW TIER-1 RELEASE, FIX FIRST-SESSION AND ROUTING DEFECTS,
THEN REDUCE ORDINARY-TURN WAITING", Milestone A. This is the §5 return. Milestone B is
reported separately (`ORDINARY_TURN.md`, when done); nothing of it is in this release.
**Nothing is deployed.** Production admission is his after reviewing this document.

Labels: OBSERVED (measured here), DERIVED (computed from observed marks), NOT RECORDED.
Every model call in this pass was local at a known $0.

## 0. Deployment, verified once

When this work began: `master` at `18aef94` (the second candidate, working tree
clean); production service process 50184, started 02:34 on `13b3cb8`'s code and not
restarted since; live store at `0031_prefix_prime`; no candidate setting in the launchd
environment; desktop `13b3cb8`; production Voice not opened since 00:59 (16 sessions
before and after this pass). The handoff's statement is correct; no authorised change
has touched production since.

## 1. The proven configuration and its limits (§1)

Unchanged from `TIER1_COMPARISON.md` and stated here without softening:

- GPT-OSS `openai/gpt-oss-20b` (MXFP4, MLX, LM Studio, `--parallel 1`, 32,768 context),
  the one instance; **LOW only for eligible standalone greetings, thanks and farewells**
  through the Core-owned Tier-1 request; **MEDIUM** for everything substantive,
  ambiguous, correction-sensitive or action-related; no Qwen resident; speculative
  answer generation off; adaptive completion off; the endpoint (0.5 / 220 / 650 /
  80 ms) and the fixed 1.1 s resume window unchanged.
- **The qualification of 26 September was not flawless:** 21 of 34 nominal tier-1 turns
  took LOW; **two produced wrong-turn answers in pending-action contexts** ("Many
  thanks, Val." → a restated offer; "Talk soon, Val." → "Understood. I will proceed
  accordingly."); the guard that catches them was added **afterwards**; on offline
  replay of the run's own contexts with that guard, **about 15 of the original 34**
  remained eligible. Its **4.8 s median / 5.4 s p90** speech end → first audio was
  measured on those 21 turns under the *earlier* guard and is **not** re-claimed for
  the revised decision; §5 below gives what was measured for the changed flow.
- **Narrow admission, enforced** (`test_low_scope.py`): the promotion gives the LOW entry
  the `light` floor and nothing else (`capability_profiles == {LIGHT}`); routing for
  `conversation`, `blind_position`, `classification` and `strip` selects exactly what
  the production registry selects without the promotion; only `light_conversation`
  reaches LOW; the registry on disk keeps LOW `NOT_ADMITTED` with no profile. The
  recorded correction-preservation failure of LOW stands, and the courtesy decision
  (§4) exists because of it. The eventual production ruling would be a narrow Tier-1
  admission of this request shape, not an admission of LOW.

## 2. First-session readiness (§2) — OBSERVED

**What "Ready" meant.** The desktop moved to "Voice On · Mic Listening" on two facts —
the service session existed and the microphone was capturing — and nothing about the
cognition runtime, the voice worker or the persona prefixes entered it. The session's
warm-up (cognition readiness and the voice worker's prime) ran on its own thread with
no gate; **the first persona prime ran only when his first utterance settled** (a
25 September decision, taken so the prime would not slow the recognizer's final decode
while he spoke), and stood aside if his request was already waiting — so his first
turn routinely ran on a cold prefix.

**Now.** The session reports readiness **component by component** (`VoiceReadiness` in
`voice.py`, `readiness` on the view and the API contract): `cognition`, `voice`,
`prefix_partner`, `prefix_light`, each `warming` / `ready` or `primed` / `skipped` /
`failed` (with the reason) / `not_applicable`; `ready` only when every applicable one
is. The persona prefixes are primed **at Voice On**, after the warm-up, unless he is
already speaking — then the prime stands aside (marked `skipped`, not hidden) and runs
when his utterance settles, as before. The desktop shows "Warming up… you can speak;
the first answer may take longer." until ready, "Val is warming up — your words are
heard and will be answered." for a turn that reached cognition before readiness (in
place of "thinking"), and "Voice is degraded: … unavailable (reason)" for a failed
component. Speech during warming is transcribed and displayed as before; nothing is
discarded (tests: `test_voice_readiness.py` 7, desktop `spokenThread.test.tsx` +3).
**Reuse of warm state:** the prime is the runtime's only supported way to establish or
confirm a checkpoint; when the checkpoint is resident it costs 0.25–0.33 s per entry
and prefills nothing — a warm prime is not a cold prime, and the log records which.

**Measured** (`A2-*.json` and their service logs; `measure.py` with `DRIVE_LEAD_S`
setting when the driver begins speaking after Voice On; the runtime unloaded before
each cold case):

| case | Voice On → ready | Voice On → first response | speech end → first audio (first turn) | later turns |
|---|---|---|---|---|
| **cold start** (model not loaded), speech 1 s after Voice On | never "ready" during the turn: warm-up 15.4 s (model load ≈ 10 s + voice worker 5 s); primes skipped for his request | ~35 s | **15.2 s** (LOW prefix cold: 10.5 s to first token) | MEDIUM 11.3 s; then a light turn **4.3 s** once both refreshed |
| **cold start**, speech after Ready | **26.4 s** (warm-up 12.4 s, then both cold primes 13.9 s) | ~58 s (he waited for Ready) | **5.2 s** (light, warm) | MEDIUM 8.5 s; greeting after a pending answer → MEDIUM 10.8 s |
| **warm reopen**, speech 1 s after Voice On | 6.4 s to the Partner prime; light prime skipped for his request | ~13 s | **5.4 s** (light; its preflight waited 0.94 s behind the prime) | MEDIUM 7.9 s; light 6.1 s (its prefix cold) |
| **warm reopen**, speech after Ready | **6.7 s** (warm-up 4.25 s + both primes 2.5 s) | ~23 s | **4.4 s** (light, warm) | MEDIUM 9.7 s; greeting after a pending answer → MEDIUM 16.2 s |
| **eviction case** (four substantive turns, then a new session) | 20.0 s (initial primes both cold, 7.8 s) | — | light after Ready **4.6 s** | MEDIUM 10.9 s |

Model loading and prefix recomputation are distinct in every row: the load is inside
the warm-up (≈10 s, once per model TTL), the prefixes are the primes (6.5–7 s each when
cold, 0.25–0.5 s warm). **Prewarming does not remove the cold-start work; it moves it
before "Ready" and says so.** A cold start still costs ~26 s before the house is fully
ready, and a turn spoken into it still pays.

**Why the checkpoints go cold** (`cache_eviction_probe.py` → `cache-eviction-probe.json`,
the prime's own duration as the instrument, warm ≈ 0.85 s for both, cold ≈ 7 s each):

- **Not time**: primes after 5 s, 30 s and 90 s of idleness were all warm.
- **Not Voice session lifecycle**: opening and closing a session issues no model call
  (the probe's session step failed on a harness argument, but the code path makes no
  runtime request, and warm reopens confirm it: the initial prime after a reopen was
  2.1–2.5 s, i.e. one entry warm).
- **Distinct prompts entering a small bounded cache**: after **one** unrelated ~120-token
  prompt the Partner checkpoint was cold (7.1 s); after two, the light checkpoint;
  after three, neither; after five, the Partner. After one ordinary MEDIUM turn the
  light checkpoint was cold once in four. The runtime keeps very few entries (the
  behaviour fits two or three) and evicts by age; two checkpoints plus each turn's own
  prompt already exceed it. Within the supported behaviour nothing here changes that:
  the engine is not patched, no memory limit is raised, no persistent cache is added.

## 3. Owner work before prime maintenance (§3) — OBSERVED

**Scheduling now** (`voice.py`): a turn's completion **owes** a refresh; the refresh is
dispatched only after **1.0 s of idleness** — no speech being heard, no settled
utterance, no turn in flight, no answer being voiced — rechecked every 100 ms, again at
dispatch, and again inside the prime before each entry's call (`still_wanted`); two
turns finishing close together owe one refresh (coalesced by a use generation, so a
prime that finishes cannot clear a refresh owed after it began); a refresh that finds
no idleness within 60 s is dropped. Speech being heard now counts as owner work for
every maintenance decision (it did not before: a refresh could start while he was
mid-sentence).

**Selective refresh tried and rejected.** Priming only the effort the turn did *not*
use (one entry per turn instead of two) was implemented and measured first: in both
collision runs (`A3-collision-pause-*.json`) the next MEDIUM turn's first token went
from ~1.7 s to **8.0–8.6 s** on four of six MEDIUM turns per session, because a turn's
own prompt is not a prefix the runtime reuses for the next turn and the light prime
evicted it. That is faster greetings purchased with slower substantive replies, which
§3 forbids; the refresh returned to **both entries, light first and Partner last** (so
the Partner checkpoint is the most recent entry when his next, most likely
substantive, turn arrives). _Collision figures under the final policy: §5._

**What a collision is, honestly.** A prime under way cannot be interrupted: LM Studio's
endpoint offers no cancel, and a prefill in progress runs to its end whatever the
client does — so "owner turns never wait" is not claimed. An utterance that arrives
while a **cold** refresh is prefilling waits behind it at the runtime (the exact
preflight and then the dispatch queue); measured in the readiness runs as 0.69–0.94 s
of preflight on the turn that followed a prime, and in `Q-low` as the 877 ms p90 of
submitted → dispatch on the Tier-1 route. What the scheduling removes is the *queued*
refresh starting while he speaks or while his words are in their window; what it
cannot remove is a prefill that began in a genuine idle gap and is still running when
he speaks ~1–7 s later. The residual is measured in §5.

**Under the final policy** (`service-A3b-collision-pause-*.log`; the same twelve turns
per run as the first collision runs, greeting and substantive alternating; the harness's
result files for these two runs were lost to a post-processing fault on the new log
line, so the figures are the service's own timelines — endpoint-based, ms; the driver's
speech end lies ~0.95 s earlier):

| | his next words 0.3 s after her answer | 2.0 s after |
|---|---|---|
| MEDIUM turns, dispatch → first token | 1,668–1,922 on 11 of 12 (**8,103 on the first turn of a cold service**) | 1,572–1,980 on 12 of 12 |
| waits before dispatch (exact preflight) on turns that followed a refresh | **335 ms and 766 ms** (2 of 12; the other 10: 33–37 ms) | 28–39 ms on 12 of 12 |
| primes | 14: 7 cold (7.1–8.0 s), 7 warm (0.87–0.91 s) | 14: 7 cold, 7 warm |
| refresh dropped for lack of idleness | 0 | 0 |

So: the substantive route is back where it was (MEDIUM first token ~1.7 s, against the
8 s the selective policy produced); when his next words come 0.3 s after her answer —
inside the 1 s idle threshold plus the 2.2 s of endpoint and window, so the refresh has
just started when the request arrives — the request waited **≤ 0.8 s** behind it on 2
of 12 turns and not at all on the others; with 2 s between turns there was no wait at
all. **The residual collision is bounded below one second on the turns measured, not
zero**, and a cold prime (~7 s of runtime work) still runs after about every second
turn in a conversation that alternates greetings and substantive turns, because the
runtime's cache cannot hold both checkpoints beside the turns' own prompts (§2). That
is the recurring cost of two warm prefixes on this runtime, stated as measured.

## 4. Courtesy against genuine pending work (§4)

**The decision** (`val_policy.light_conversation.pending_matter`, called from
`deliberate.tier1_eligibility` with the full working thread): a social utterance may
take the Tier-1 route only when the context holds no open matter, read in this order —

1. **His previous message asked for an action or a decision** (or was itself a
   correction or withdrawal: "not the…", "I meant", "never mind", "wait,"). Nothing she
   said about it settles it here — that she did it, will do it, noted it, recorded the
   intent, or cannot do it. A claim of action or completion is **uncertain state, not
   proof**; a refusal leaves the matter with him. → MEDIUM.
2. **Her previous answer asks or offers something in particular**: any sentence with a
   question mark or an offer, *except* the generic closings of courtesy — "How may I
   assist you?", "What shall we turn our attention to?", "Is there anything else you
   require?", "How may I be of service?" and their variants — which are courtesy when
   nothing else is open and **never override an open matter found by rule 1**. An offer
   in a contraction ("I'll read it now") or an instruction to him ("Put it in front of
   me") counts. → MEDIUM.
3. A corrected or withdrawn previous message, or earlier turns with no readable answer
   of hers (uncertain) → MEDIUM (unchanged, in `tier1_eligibility`).
4. The utterance itself must be a standalone greeting, thanks or farewell under the
   frozen router (a mixed utterance with an instruction is work).

This replaces the blanket phrase guard ("I will", "I can"…) added after the run.

**Evidence sets, kept apart** (`packages/policy/tests/fixtures/courtesy_pending_*.json`,
`test_courtesy_pending.py`, 675 policy tests + 2 recorded xfails):

| set | n | inappropriate light routes | light | safe misses (MEDIUM) |
|---|---|---|---|---|
| the two wrong-turn contexts from the run (regression) | 2 | **0** | 0 | — |
| development cases (generic offer; specific proposal; refusal; claimed intention; earlier work then courtesy; correction; withdrawal; thanks/farewell authorising nothing; "And you?"; mixed) | 10 | **0** | 2 (the generic offer, the settled question) | — |
| **fresh courtesy contexts**, written before implementation | 20 | — | **9** | 11 |
| **fresh pending / ambiguous / correction-sensitive**, written before implementation | 22 | **first evaluation: 1** (p14) → **after tightening: 0** | 0 | — |

**The fresh set was evaluated twice, and that is recorded.** As written, the decision let
one pending context through: "Read me the note." → "I do not have that in the record I
can see. Put it in front of me and I'll read it now." → "Thank you." ("read" was not in
the action list; "I'll" was not in the offer pattern). The two patterns were tightened
for exactly that, and the fresh pending set then routes 22/22 to MEDIUM — so for those
two patterns the fresh set is no longer unseen evidence, and the coverage figure on
the courtesy half (9/20) was not changed by the tightening. **Zero inappropriate light
routes on every set** after the correction.

The 11 courtesy misses are all safe (MEDIUM) and each has its reason: three are tier-2
pleasantries ("Glad to hear it", "Good.", "No, thank you" — tier 2 is outside this
pass); three are wordings the frozen router does not admit ("Until this evening",
"Nothing for now", "Just saying good night"); one is her answer's specific offer ("I
will keep it in mind"); one is the utterance's own work word ("Good advice"); and
**three are the action list matching informational questions** ("How long should a cold
**open** run", "to **open** a chapter", "**make** a scene tense") — a known imprecision of
rule 1, left as it is rather than loosened against the evaluation set; it costs
coverage, never safety.

**Generated answers for newly permitted contexts** (`courtesy_answers.py`; twelve
conversations on the real path: a greeting or an answered informational question on
MEDIUM, then his thanks or farewell, which the decision may now route to LOW; every
answer read):

- **First shape** (`courtesy-answers.json`): of 7 closings routed to LOW, **3 were
  wrong** — after a greeting exchange, "Thank you, Val." drew "Good evening, my lord.",
  "Good night, Val." drew "Good evening, my lord.", "Thank you kindly." drew her own
  previous line back ("Good evening, my lord. How may I attend to you?"). Thanks after a
  substantive answered question were right ("My lord, you're most welcome.", "All
  right, my lord."). Cause: the Tier-1 request carried the previous exchange, and when
  that exchange was itself a greeting pair, LOW copied its own line from it.
- **Request corrected** — a previous exchange that was itself light is left out of the
  Tier-1 request (`tier1.last_exchange`; a substantive exchange stays, because "thank
  you" answers *that*) — and **re-run** (`courtesy-answers-2.json`): of 6 closings on
  LOW, **5 right** ("Good night, my lord." ×3, "You're most welcome, my lord.", "My
  lord, I stand ready to attend to whatever you require."), **1 wrong**: "Thank you,
  Val." after "Good evening, Val." → "Good evening, my lord." again.
- **Class decision (§4: release only what qualifies):** a **bare thanks after a
  greeting-only exchange is withheld** from LOW and stays on MEDIUM (routing reason
  recorded: "thanks after a greeting exchange: LOW answered it as a greeting in
  verification"). Farewells after a greeting exchange (3/3 right) and thanks or
  farewells after a settled substantive answer with a courtesy closing (right in every
  run) are released. The two fresh courtesy cases of that class (c01, c10) become safe
  misses, and the development case d01 is re-expected MEDIUM with the reason on the
  fixture — **the final fresh-set figures are 7/20 courtesy on the route, 13 safe
  misses, 0/22 inappropriate** (`FRESH_FINAL_EVALUATION` in the test module).
- **Also seen, for Milestone B:** ordinary MEDIUM mishandled two closings in these
  probes — "Just saying good night, Val." drew "Good evening, my lord.", and "That's
  all for tonight. Thank you." drew a four-sentence leave-taking about "the opening of
  a volume in our house's library" — the wrong-turn class of `ORDINARY_TURN.md` §6.

**Historical coverage, recomputed read-only with the final decision**
(`coverage-recent-spoken-use-final-guard.json`): unchanged — 7 of 27 spoken turns
(25.9%) tier 1, 0 tier 2, 20 substantive; 4 of the 7 ordinary-use turns. The seven were
first turns or greetings into settled contexts, so the pending decision removes none;
the sample remains three days of diagnostic-heavy voice-mode building.

## 5. Release evidence (§5)

Targeted verification of the changed behaviour only — readiness (§2), scheduling
(§3), the courtesy decision (§4) — reusing the settled 114-turn qualification of
`TIER1_COMPARISON.md` for what did not change. **Player boundary:** every latency below
is the harness's — the driver posts audio to the service as the desktop does and
"plays" each segment on a serial software queue from its arrival; it is the software
output boundary, not the desktop's own audio worklet and not acoustic onset in the
room. The desktop's changed flow (the readiness display) is covered by its component
tests; its physical acceptance is the test in §6.

**First-turn against later-turn distributions** (speech end → first audio at the
player, ms; OBSERVED):

| | first turn of a session | later turns |
|---|---|---|
| light route, warm reopen, spoken after Ready (A2/A2b, n = 2) | 4,394 / 3,426+~950 ≈ 4,400 | light 4,289–6,059 (n = 3); MEDIUM 7,858–16,190 |
| light route, cold start, spoken after Ready (n = 1) | 5,187 | MEDIUM 8,475; a greeting held on MEDIUM by the courtesy decision 10,838 |
| light route, spoken 1 s after Voice On, warm (n = 1) | 5,353 | — |
| light route, spoken 1 s after Voice On, **cold** (n = 1) | **15,215** | — |
| the settled qualification (earlier guard, 21 light turns, `Q-low`) | — | 4,796 median, p90 5,370, max 5,443 |
| MEDIUM turns across all Milestone A runs (n = 36, **endpoint** → first audio) | — | median 7,753, p90 10,833, max 16,323 (+~950 from speech end) |
| light-route turns across all Milestone A runs (n = 9, **endpoint** → first audio) | — | median 3,795, p90 4,533, max 14,401 (the cold-start turn) |

**Route coverage and fallbacks in these runs:** every tier-1 phrase spoken into a
settled context took the Tier-1 route; every one spoken after an answer of hers that
asked or offered something, or after a substantive request, stayed on MEDIUM (the
courtesy decision working as specified — e.g. "Good morning to you, Val." after her
"second act" answer that asked which act he meant); no fallbacks (no light call failed
before delivery); no false positives on the 24 must-stay-MEDIUM turns in these runs.
**Substantive-turn effects:** under the final refresh policy MEDIUM's first token stays
at ~1.7 s (§3); the one 8.1 s MEDIUM first token was the first turn of a freshly
started service before its initial primes had landed.

**Generated answers in the newly permitted courtesy contexts:** _§4, filled below from
`courtesy-answers.json` (first request shape) and `courtesy-answers-2.json` (after the
light-previous-exchange rule)._

**Offline.** The sampled connections of every process during the runs were loopback
only, as before, and the service, driver and voice worker ran under the loopback-only
sandbox in `TIER1_COMPARISON.md` §9. **The runtime itself (LM Studio and its helpers)
was not constrained in this pass**: the two reversible methods available — cutting the
machine's network for the duration of a two-turn probe, or relaunching LM Studio inside
the sandbox profile — both interrupt him (the first his whole machine, the second Val's
runtime while it is his), and his idle time during this pass was under two minutes, so
neither was done unannounced. **The remaining verification boundary is exactly that:**
the runtime's loopback-only behaviour is established by sampling, not by denial. The
two-minute step he can authorise: Wi-Fi off, two spoken turns, Wi-Fi on.

**Memory, not "zero":** the runs of this pass (readiness, eviction, collision) sampled
free memory no lower than 40% (`memory_pressure`), swap unchanged within a run at
1.4–1.7 GB used, the voice worker 2.5–3.2 GB resident; the second prefix's cost in the
runtime's own cache is real and shows as the cold-prime rate (§2, §3), not as process
memory.

## 6. Release identity, deployment, rollback, physical test (§5)

**Release candidate:** the commit that carries this document — the Milestone A commit on `master` following `18aef94`, whose hash and CI result are stated in the handoff (a record cannot carry its own hash) — with these settings in the service's launchd environment and nothing else
changed:

```
VAL_FAST_ROUTE_TIERS=1
VAL_TIER1_ROUTE=low
```

`VAL_SPECULATION` and `VAL_ADAPTIVE_GRACE` **unset**. The desktop needs no new build for
routing; the readiness display (§2) is in this commit's desktop source and needs a
desktop build and install (`npm run tauri build`, preserve the previous bundle, `ditto`,
`check_desktop_deployment.py`) — it is presentation only and the service works without
it.

**Migration.** The live store is at `0031_prefix_prime`; this release needs
**`0032_light_conversation`** and no other: two values added to `model_call_task_type`
(`light_conversation`, `speculative_light_conversation`) and the empty, append-only
`speculative_preparations` table. Apply that revision explicitly —

```
uv run alembic -x deploy=live upgrade 0032_light_conversation
```

— not `upgrade head`, so that a later revision the repository may have gained is never
applied by accident to the live store. The service refuses to start against a store
behind the revisions its code writes to only on the paths that reach them; with the
switches set, the first light turn would write `model_calls.task_type =
'light_conversation'`, which `0031` cannot hold — so the migration comes first.

**Deployment, on his approval:** apply the migration; add the two settings to
`~/Library/LaunchAgents/house.armand.val.api.plist`; `launchctl kickstart -k
gui/$(id -u)/house.armand.val.api`; confirm the startup line "CANDIDATE fast route
enabled … effort low" and `/health`; optionally install the desktop build for the
readiness display.

**Rollback:** remove the two settings and kickstart. **This restores today's routing
exactly, and no more:** the light calls already recorded stay in `model_calls` as the
evidence they are; `speculative_preparations` stays (empty unless speculation was ever
enabled); the schema stays at `0032` — its downgrade is forward-only in intent, like
`0031`'s, and **refuses** while any light or speculative call is on record. Rollback of
routing is a setting; rollback of the schema is a separate act with its own conditions.

**Physical acceptance test (concise):** with the release deployed and Voice on, wait
for the status to read ready (not "Warming up…"), then — (1) "Good evening, Val."
→ expect her reply to begin in about 4–5 s from the end of your words, one short
sentence in her voice; (2) "What do you think of the second act?" → an ordinary
MEDIUM answer, ~8–10 s; (3) "Thank you, Val." straight after → **MEDIUM again** (her
answer asked you something), no acknowledgement of work she did not do; (4) "Good
evening, Val." into a fresh chat, then "Thank you, Val." → the second in ~4–5 s, a
plain "you're welcome" in her manner. Listen for clicks or a changed timbre (the audio
repair's physical acceptance is still pending) and for whether the pauses feel natural.
What this does not test: acoustic onset in the room (the figures here are the
software's), or Milestone B.

## 7. Release identity and gates

Code: the Milestone A commit (the one carrying this document; the handoff names its
hash), following `18aef94`. Model: `openai/gpt-oss-20b` MXFP4 MLX, LM Studio 0.4.24+1,
engine `mlx-llm-mac-arm64-apple-metal-advsimd@1.11.0`, `--parallel 1`, 32,768 context;
LOW entry `gpt-oss-20b-mxfp4-mlx-lmstudio-low` promoted in-process by `VAL_TIER1_ROUTE=low`,
`NOT_ADMITTED` on disk. Recognition, voice and desktop unchanged from `13b3cb8` except
the readiness display. Gates (full CI mirror, green before the commit): secrets, pins,
scope, boundaries, ruff, format, mypy; store-free 1,034 passed + 2 recorded xfails;
domain 406; gateway 941; providers 278; api 111; desktop tests and build; cargo. CI on
the pushed commit: stated in the handoff.
