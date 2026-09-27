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

**Release candidate (corrected by the release-gaps order of 26 September 2026, §6C):**
the head of the branch **`release/tier1-low-2026-09-26`**, tagged
**`tier1-low-release-2026-09-26`** — cut from the Milestone A commit `3fbebf5` and
carrying only the gap closures of §8 below; **it does not contain Milestone B**
(`d03dc74`, the owner-precedence switch and the provider-stream contract change), which
is on `master` only. The tag's commit hash and its CI result are stated in the handoff
(a record cannot carry its own hash). Service and desktop are one pair: the service is
that commit's Python, and the desktop is the bundle built from that same commit, whose
identity (bundle version, binary digest, build time) §8.6 records. With these settings
in the service's launchd environment and nothing else changed:

```
VAL_FAST_ROUTE_TIERS=1
VAL_TIER1_ROUTE=low
```

`VAL_SPECULATION`, `VAL_ADAPTIVE_GRACE` and `VAL_OWNER_PRECEDENCE` **unset**. **The
desktop build is part of the release, not optional** (§6B): the readiness display is what
makes "Ready" truthful, and a service reporting readiness to a desktop that cannot show it
would be a release claiming what the owner cannot see. Install order: service, then
desktop (`ditto` the staged bundle into `/Applications`, move the previous bundle to
`~/Val previous builds.noindex`, run `check_desktop_deployment.py`).

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

**Physical acceptance test (corrected, release-gaps order §6A — the expected routes now
match the final implementation, in which a bare thanks after a greeting-only exchange
is withheld from LOW):** with the release deployed and Voice on, wait for the status to
stop reading "Warming up…" (warm: about 8 s after Voice On; cold, with the model not
loaded: about 26 s), then —

1. "Good evening, Val." → the light route; her reply should begin about **4–5 s** after
   your words end (the desktop's own measurement in §8.3 was 4.1 s), one short sentence
   in her voice.
2. "Good night, Val." straight after → **still the light route** (a farewell after a
   greeting exchange is a released class), about 4–5 s, a farewell back — never a
   greeting. Then keep going; the test is not over.
3. "What do you think of the second act?" → an ordinary **MEDIUM** answer, about 6–11 s
   to her first words depending on how long she reasons.
4. "Thank you, Val." straight after → **MEDIUM** if her answer asked you anything (it
   usually does on that question) — the courtesy decision holding — and no
   acknowledgement of work she did not do; if her answer ended in only a generic
   closing, the light route in about 4–5 s with a plain "you're welcome" in her manner.
   Either is correct; what would be wrong is a fast answer that ignores an open question.
5. In a fresh chat: "Good evening, Val.", then "Thank you, Val." → the second stays on
   **MEDIUM** (about 6–10 s): this class is withheld, on the generated-answer evidence of
   §4, and the release does not claim it.

Listen for clicks or a changed timbre (the audio repair's physical acceptance is still
pending) and for whether the pauses feel natural. What this does not test: acoustic onset
in the room (every figure here is the software's), or Milestone B.

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

## 8. The release gaps, closed — owner order "CORRECT THE RELEASE GAPS…", 26 September 2026 (§6–§8)

Same labels as above. Every model call in this section was local at a known $0; production
was not touched (service pid 50184 on `13b3cb8`'s code, live store `0031`, no setting in
the launchd environment, production Voice not opened: 16 sessions before and after).

### 8.1 Release identity (§6C)

`master` at the time of this order carried Milestone B (`d03dc74`). The release is
therefore **not** a master checkout: it is the branch `release/tier1-low-2026-09-26`, cut
from the Milestone A commit `3fbebf5`, plus the closures below, tagged
`tier1-low-release-2026-09-26` at its head. It contains none of Milestone B — no
owner-precedence switch, no `cancelled` in the provider stream contract, no
experiment switches — so what it contains is exactly what §1–§7 and this section
qualify. Master receives the same closures by merge; the tag, not master, is the release.

### 8.2 The courtesy decision beyond the previous exchange (§6D)

**History, preserved and named.** The fresh set of §4 was evaluated twice; after the
p14 tightening its pending half is **no longer unseen evidence for the action and offer
patterns** and this document does not call it that. The evidence for the widened rule is
a **second fresh set** (`courtesy_pending_window.json`, 12 pending + 10 courtesy
contexts of one to three exchanges), written before the rule was widened, focused on an
unmet request followed by a social exchange and then courtesy, on the tightened
action/offer boundaries ("read", "show", "find", "look up", "check", "I'll", "put it in
front of me"), and on informational earlier exchanges that a social turn must not turn
into pending work. It was evaluated **once** (`WINDOW_FIRST_EVALUATION` in
`test_courtesy_window.py`): **12/12 pending on MEDIUM, 9/10 courtesy on the route**, the
one miss (r10, "the guest **list**") the known imprecision of the action list matching an
informational question — safe, left as it is.

**The rule (`pending_matter`, `PENDING_WINDOW_EXCHANGES = 3`):** rules 1 and 2 are now
applied to the three exchanges before the previous one as well, walking back from the
most recent **until a message of his that is itself work** — he moved on, and his
courtesy attaches to that — because a message the frozen router reads as social (a
greeting, thanks, a farewell, a pleasantry, a bare acknowledgement) settles nothing.
"Send the invitation tonight." → "I will see to it." → "Lovely evening." → "It is." →
"Thank you, Val." stays on MEDIUM; the same request followed by "Explain what a caesura
is." and its answer, then "Thank you, Val.", takes the route. The window is bounded so a
conversation that has moved on does not lose courtesy for ever over a request an hour
old; the bound is a house choice, recorded, not evidence. `tier1_eligibility` pairs the
thread's messages exactly as the read-only coverage script does.

**Historical coverage, recomputed read-only with the window
(`coverage-recent-spoken-use-window-guard.json`): unchanged** — 7 of 27 spoken turns tier 1,
0 tier 2, 20 substantive; the seven were first turns or greetings into settled contexts.

**A defect the desktop run found, and its repair.** In run W2 (§8.3) the recognizer heard
the synthetic driver's "Good evening, Val." as "Good evening, Vowel." — not a greeting to
the router, so the exchange stayed in the Tier-1 request; her answer to it was a greeting
back; and LOW answered "Good night, Val." with **"Good evening, my lord."** — the same
copying that withheld bare thanks after a greeting exchange in §4, reached through a
misheard name. The omission of a courtesy-only previous exchange (`tier1.last_exchange`)
now reads **her answer's shape as well as his words** (`answer_is_courtesy`: every
sentence a greeting, thanks, farewell, pleasantry, acknowledgement or generic closing of
service once "my lord" is removed), so a misheard greeting no longer carries a greeting
pair into the request. Verified on the real path (`courtesy_answers_3.py` →
`courtesy-answers-3.json`, six two-turn conversations, openers the router does not call
light): **5 farewells on LOW, 5 right** ("Good night, my lord." ×4, "Until tomorrow, my
lord."); the sixth stayed on MEDIUM (her answer "How may I serve you this night?" is
not in the closing list — a safe miss) and **MEDIUM answered it with "Good evening, my
lord. I shall retire now; please summon me if any matter requires attention."** — the
wrong-turn class of `ORDINARY_TURN.md` §6, on the ordinary route, recorded for Milestone
B §4. The same mishearing occurred in the 26 September qualification run (`Q-low.json`:
five utterances ending "Vowel", every one routed MEDIUM as out of scope), so part of that
run's "safe misses" were the driver's voice, not the router; a property of the synthetic
driver, and one reason the physical test is his.

### 8.3 Through the real desktop (§6, the required integration evidence)

**Method.** The unmodified `apps/desktop` frontend, served by its own dev server and
pointed at the scratch service on port 8766 (the one build-time override `VITE_VAL_API_BASE`,
inert in the packaged application, whose content-security policy admits no origin but
production's), in headless Brave whose microphone is a prepared WAV of the driver's
voice (`desktop_owner_audio.py`; Chromium's fake capture device; the browser's same-origin
enforcement disabled for the scratch origin, nothing in Val changed for it). The driver
(`desktop_integration.mjs`) clicks the visible "Voice on" control once, watches the DOM
on the page's clock, and clicks "Voice off" at the end. The desktop's **own timing
report** (`speech_end_to_playback_start_ms`, posted to the service as in production) and
its playback reports are the desktop-output figures. **Three boundaries, kept apart:**
the *harness* figures of §5 (a software player in the driver); the *desktop-output*
figures here (the real frontend's worklet clock, headless — no speaker); *acoustic* onset
in the room, which only he measures. Records: `desktop-integration-W1-speech-before-ready.json`,
`desktop-integration-W2-warm-after-ready.json`, and their service logs.

| run | Voice On → Ready (service / displayed) | turn | route taken | speech end → her words on screen | speech end → playback start (desktop) |
|---|---|---|---|---|---|
| **W1** — warm runtime, speech **12 s** after Voice On (turned out to be *before* Ready: warm-up 12.6 s, then the initial prime) | 35.5 s / 46.0 s (the display was occupied by turns until then) | "Good evening, Val." | light | 2.05 s | **11.0 s** — the request waited ~7.6 s behind the cold light prime that had begun 1.0 s after his (not yet detected) speech onset |
| | | "What do you think of the second act?" | MEDIUM | 2.56 s | 11.1 s (Partner prefix cold: its prime had stood aside) |
| | | "Thank you, Val." | MEDIUM (her answer asked) | 2.01 s | 6.4 s |
| | | "Good night, Val." | MEDIUM (her answer asked) | 1.94 s | 6.0 s |
| **W2** — warm, speech **45 s** after Voice On (after Ready) | **7.9 s / 8.0 s** | "Good evening, Vowel." (misheard) | MEDIUM (out of scope) | 2.06 s | 11.1 s |
| | | "Good night, Val." | **light** | 2.02 s | **4.1 s** (answer wrong before the §8.2 repair) |
| | | "Explain what a caesarean is." (misheard "caesura") | MEDIUM | 2.02 s | 6.1 s |
| | | "Thank you, Vowel." | MEDIUM (her answer asked) | 2.05 s | 6.5 s |

What the runs show, and only that: the readiness display appears within 0.4 s of the
click and clears when the service reports ready (W2: 7.9 s service, 8.0 s displayed; W1:
the service was ready at 35.5 s and the display could show it only once the turns'
stage lines cleared, at 46.0 s); a turn spoken before readiness shows "Val is warming up —
your words are heard and will be answered." (W2, turn 3, when the Partner prefix had
been skipped); the routing decision reached the desktop as the rule predicts in all
eight turns; every segment handed over was reported played by the real frontend
(W1: 10 segments, W2: 9 — `available_to_desktop` → `playback_started` →
`playback_completed` each); and **the desktop-output first-audio figure for a light turn
after Ready was 4.1 s**, against the harness's 4.4–4.8 s. The W1 first turn is the
harness's "speech during warming" case seen through the desktop: **the initial prime
began 1.0 s after his speech onset and 0.4 s before the recognizer detected it**, and a
prime in progress cannot be stopped, so his request waited behind it. Nothing
deterministic knows he is about to speak; this is the structural residual of §3, now
observed at the desktop boundary rather than inferred.

**Not done at the desktop boundary:** the cold case (the model not loaded) — it requires
unloading the shared runtime while he is at the machine; the harness's 26.4 s / 15.2 s
figures stand for it — and the physical speaker, which the headless browser has not.

### 8.4 Readiness and maintenance, without overclaiming (§7)

**The trade, stated plainly:** about **26 s** to full readiness in the measured cold
case, **8 s** warm; about **4–5 s** to the first reply after readiness on the light
route (4.1 s at the desktop boundary, 4.4–4.8 s in the harness); **6–11 s** for an
ordinary MEDIUM reply; and **longer waiting** — 11–15 s — when speech arrives during cold
startup or while a cold prime is running. This is not near-instant conversation, and this
document does not call it that.

**The apparent contradiction, reconciled from the recorded timestamps.** §3 said "the
refresh has just started when the request arrives" for his words 0.3 s after her answer.
The service logs of both collision runs (`service-A3b-collision-pause-*.log`) say
otherwise: **every** refresh was dispatched 1.03–1.05 s after the turn's own completion
line and **2.7–19.6 s before his next speech onset**; on the 0.3 s runs the cold primes
had been running for 2.7–6.7 s of their 7–8 s when he spoke. No refresh started after
speech began — the sentence was an explanation error. What the timestamps also show is
**where the idle second came from**: the service's turn completed (synthesis done) while
the harness's player was still speaking the tail of her answer for several seconds; the
scheduler counted "no answer being voiced" from synthesis end, not from the end of
playback, so a refresh could begin while she was still audibly speaking and be mid-prefill
when he answered her. **That is a defect of the idle definition, and it is repaired:**
audio handed to the desktop is now counted as heard for its own duration, serially
(`speech_handed_over` on each hand-off; a barge-in or a reported stop ends it), and the
refresh's idle clock starts when that ends (`test_prime_waits_for_playback.py`, 2). The
desktop runs above ran with the repair; under it the refresh after a turn began after
the last segment's duration had elapsed, and no request waited behind a refresh in either
run. **The sub-second collision figures of §3 remain observations for those trials, not a
bound**: a prime in progress is not cancellable, and a request arriving during a cold one
waits for its remainder, up to ~7 s.

**One more display truth, from W1:** a turn that reached cognition before readiness
showed "Val is thinking…" once its delivery object existed, though nothing had been
written and the warming it waited on had not ended. `_progress_locked` now applies the
same rule whether or not a delivery exists ("warming" until ready), and W2's turn 3 shows
the line.

### 8.5 Offline (§8)

The boundary is unchanged and stated as it is: the service, driver and voice worker ran
under the loopback-only sandbox; **LM Studio itself was observed by sampling with the
network up, not constrained.** The shortest coordinated check is prepared as
`offline_check.sh`: Wi-Fi off, two spoken turns on the deployed release (or two minutes),
the runtime's connections sampled every second, Wi-Fi back on, always, on any exit; what
it can establish and what it cannot are in its header. **It has not been run** — it needs
his machine's network and his two minutes — and whole-stack network denial is **not**
described here as verified.

### 8.6 The desktop build (§6B)

Built from the release tree (`npm run tauri build`), staged **outside** the launchable
locations as `~/Val previous builds.noindex/Val (release tier1-low 2026-09-26, staged, not
installed).app`, **not installed**: identity below. Installing it is the second half of the
deployment step in §6, on his approval, followed by `check_desktop_deployment.py`.

| | |
|---|---|
| bundle | `Val.app`, `CFBundleIdentifier` `house.armand.val`, `CFBundleShortVersionString` `0.0.0` (the bundle version is not bumped per build; the digest and build time identify it) |
| binary digest (SHA-256 of `Contents/MacOS/val_desktop`) | `fa994941cb0791ff60dea8d520ba872be24cbba9ee7b0faf55f47cc93b50231d` |
| built | 2026-09-26 22:46:33 CDT, from the release tree (desktop source identical to the tagged commit) |
| the installed production desktop, for contrast | `21b8e948023713798ef74bbf9fa77eb3d5528ce9a925d2a58cd06d992a9b3895` (the `13b3cb8` build), untouched |

### 8.7 Gates on the release branch

Full CI mirror, green before the tag: secrets, pins, scope, boundaries, ruff, format,
mypy; store-free suite with its two recorded xfails; domain; gateway (with
`test_prime_waits_for_playback` 2 and the misheard-greeting Tier-1 request test); policy
(with `test_courtesy_window`: 12 pending, coverage recorded, the answer-shape cases);
providers; api; desktop tests (240) and build; cargo. CI on the pushed tag and on the
merge to `master`: stated in the handoff.

### 8.8 Deployment recommendation

**Recommended for his decision, with the remaining checks named:** the release is fit to
deploy as specified in §6 — migration `0032_light_conversation` explicitly, the two
settings, kickstart, then the staged desktop build and the deployment check — and its
routing rollback is the removal of the two settings. What remains after deployment and
before the package is called complete is his: the physical acceptance test of §6 in the
room (acoustic onset and the sound of the voice), and the two-minute coordinated offline
check of §8.5. Neither can be done for him.
