# Tier 1: the existing options compared, and one qualified — 26 September 2026

Owner order "VAL VOICE: COMPARE EXISTING TIER-1 OPTIONS, THEN QUALIFY THE BEST
CONFIGURATION". This record is the §10 return. Its predecessor, `RESULT.md`, stands as
the record of the earlier candidate; where this document corrects that one's reporting
it says so (§11). Nothing here is deployed; production is verified below.

Labels: OBSERVED (measured here), DERIVED (computed from observed marks), NOT RECORDED.
Every model call in this pass was local, at a known $0.

## 0. Deployment, verified once

When this work began, `master` stood at `964081b` (the dormant candidate, working tree
clean); production service process 50184, started 02:34 on `13b3cb8`'s code and not
restarted since (a restart would load `964081b`, which with every switch unset routes
nothing light); live store at `0031_prefix_prime`; the three candidate settings absent
from the launchd environment; desktop `13b3cb8` (no desktop change since); production
Voice last opened 00:59 and not opened during this pass (16 sessions before and after).
The earlier handoff's statement is correct.

## 1. The real opportunity (§1) — OBSERVED, read-only, model-free

`coverage_analysis.py` → `coverage-recent-spoken-use.json`. Every owner-spoken turn in
the live store (every message with voice provenance), 24–26 September 2026, the wording
in force, the frozen router run with only the context that preceded each turn (her
most recent answer, his earlier turn count). Nothing written; no words persisted.

| | turns | tier 1 | tier 2 (diagnostic only) | substantive / ineligible |
|---|---|---|---|---|
| all spoken turns (11 conversations) | 27 | 7 (25.9%) | 0 | 20 (74.1%) |
| ordinary use (4 conversations) | 7 | 4 (57.1%) | 0 | 3 (42.9%) |
| diagnostic / test conversations (7) | 20 | 3 (15.0%) | 0 | 17 (85.0%) |

Diagnostic conversations are those with an owner message about the voice system itself
(the rule is recorded in the file: hearing tests, voice-model checks, speed and tuning
questions). Unclassifiable: none. **The sample is three days of voice-mode building,
diagnostic-heavy, and says nothing about his long-term conversational habits.** In it,
a quarter of spoken turns are tier 1 — every one a greeting or a thanks that today
waits for MEDIUM.

Recorded waiting where the production log holds the turn's timeline (endpoint → first
audio at the sink; 11 of 27 turns have one): tier 1 n=3, median 10.4 s (6.3–16.2);
substantive n=8, median 11.7 s (6.7–54.0). The missing 16 predate the timeline log or
were interrupted. So the practical reach of the frozen router on this sample is: about
one spoken turn in four could be answered faster, and the other three keep MEDIUM's
7–12 s. **A faster greeting does not touch substantive latency.**

## 2. The Core-owned Tier-1 contract (§2)

`val_gateway/tier1.py`. Tier 1 is a standalone greeting, thanks or farewell. Core
decides eligibility **before projecting anything**, from the full working thread
(`deliberate.tier1_eligibility`): the frozen router's rules, plus — any question or
offer anywhere in her last answer (a pending matter), a corrected or withdrawn previous
message (correction-sensitive), or earlier turns with no readable answer of hers
(uncertain state) → ordinary MEDIUM. Nothing is hidden from eligibility; only the
request to the model is smaller.

**Retained:** the complete approved persona as the system prompt, byte for byte (so the
persona-prefix prime still lands on its boundary); the most recent exchange — his
previous message and her answer, wording in force; a reduced record state that states
what it left out; Core's contract for the turn; his words. **Omitted:** history counts
and retention figures (the block says "most_recent_exchange" and how many earlier
messages exist unseen); same-project recall and House recall (deliberately `not_run`,
stated as a positive state); `visual_input` / `audio_input` (a turn with media is not
Tier 1); `spoken_delivery` and the `spoken_path` facts; correction and withdrawal
facts (a turn after a correction is not Tier 1). The seal is kept and stated with the
standing note when the request is local-only.

**The contract**, identical for every candidate, framed as Core's instruction for the
turn (`authority: val_core`, a block distinct from the record state): answer the current
social utterance directly; one short, complete, natural response in Val's established
manner; the persona's example lines illustrate manner and are not facts or text to
recite; invent no project, completed work, weather, room, schedule or prior event; no
filler, no second answer, no restating the record state. Serialised by each runtime's
own template (GPT-OSS harmony; Qwen chat) — semantic equivalence, not identical bytes.

**Delivery:** a Tier-1 answer is delivered **whole, after completion**. It must end
`complete` and be non-empty or it is not delivered at all and the turn takes the
ordinary route once (`test_a_tier_1_answer_that_hits_its_cap_is_not_delivered_and_the_partner_answers`);
a cap hit therefore fails before a word reaches him. Output allowance 1,024 tokens on
the Tier-1 route (hidden reasoning counts against it on GPT-OSS; the largest observed
was 404 tokens); 4,096 on the ordinary route. **This difference is part of the changed
contract and is reported with it.**

The route that carries the request is a candidate-build setting, `VAL_TIER1_ROUTE`:
`medium` (the production Partner entry itself), `low` (the evaluation-only LOW entry —
the same loaded `openai/gpt-oss-20b` instance at LOW, promoted for the process; **not
an admission of LOW, never for substantive work**, whose route and floor are untouched)
or `qwen`. Off without `VAL_FAST_ROUTE_TIERS`. Tests: `test_tier1_request.py` (6),
`test_tier1_route_switch.py` (6).

## 3. The four-way quality comparison (§3) — OBSERVED

`tier1_compare.py`, `tier1_fixture.json`, `tier1-compare-{A,B,C,D}.json`,
`tier1-compare-reading.txt` (every answer, side by side). One process per condition on
the scratch store rebuilt empty, through the real Core, the production model instances,
**no speculation, no voice, no streaming, no priming** (the harness opens no Voice
session, so the persona-prefix prime never runs — the latencies below are therefore
cold-prefix figures and are **not** the answer-onset measurement; §5 is). 30 cases:
18 in hand while the request was designed, 12 written after it was frozen; 24 eligible
(9 standalone, 15 after a history exchange answered on the ordinary route in that
condition), 6 deliberately ineligible or pending. Every answer was read.

| condition | Tier-1 route taken | persona example copied | previous answer repeated | invented detail (read) | wrong-turn answer (read) | answer chars, median | Tier-1 call tokens out, median | Tier-1 call latency, median (cold prefix) |
|---|---|---|---|---|---|---|---|---|
| **A** ordinary MEDIUM | 0 / 30 | 2 (the greeting "What shall we turn our attention to?") | **2** (d10: the whole 629-token previous answer re-spoken to "Thank you, Val."; f08) | 0 on eligible turns | 2 | 70 | 190 (all reasoning + answer) | 9.8 s (all substantive-route) |
| **B** MEDIUM + Tier-1 request | 22 / 24 eligible | 1 (f08 "I have no book on…") | 0 | 0 | **2** (f08 re-advises on pacing; f09 re-explains suspense to "Nothing else for now, thank you") | 39 | 182 (≈150 hidden reasoning) | 9.0 s |
| **C** LOW + Tier-1 request | 23 / 24 eligible | **0** | **0** | 0 | **1** (d10: a three-point recap to "Thank you, Val.") | 47 | **32** | 7.8 s cold; **0.5–1.2 s** when its prefix was warm (d03–d09) |
| **D** Qwen3-4B + Tier-1 request | 23 / 24 eligible | 3 ("I do not have that in the record I can see", twice; the greeting line) | 0 | **6** ("the report on the grain supply chain", "the books closed and the fire low", "how are things on the schedule this afternoon", "the study warm", "the clock shows 16:27 — just after five", "a volume on social recognition") | 0 | 68 | 16 | 1.5 s (8.7 s cold, first call) |

Reading the answers (verdicts, not scores):

- **A** is what he gets today, and its worst failures are the ordinary route's: to
  "Thank you, Val." after a film-craft answer it **re-spoke the entire previous
  answer** (17.7 s); to "Much obliged." it repeated the advice; to "Nothing else for
  now, thank you" it said "I have taken note of the state, my lord."
- **B** answers the social turn correctly and briefly in 22 of 24 eligible cases, in
  her manner ("Good night, my lord. May the house rest well.", "Until tomorrow, my
  lord."); it fails twice by answering the previous question again. **Its latency does
  not move:** MEDIUM's hidden reasoning (≈150–400 tokens) runs on a greeting exactly as
  on a question, so the Tier-1 request buys ~1 s of shorter output and nothing else.
- **C** is the cleanest text of the four: every eligible answer short, complete and in
  her voice, no persona echo, no repetition, no invention; one wrong-turn recap. With
  ~30 output tokens and no hidden reasoning its generation is ~0.4 s; **whether it is
  fast depends entirely on whether its prompt prefix is warm** — §4 measures that.
- **D** is fast and short but **invents** — six times in 23 answers, in the register
  of a manor drama — and still copies a persona line. The Tier-1 request removed the
  rambling (median 594 → 68 characters against the earlier run) and not the
  fabrication. Not admissible for Val's words.

The ineligible and pending cases stayed on MEDIUM in every condition where the state
showed the matter open; **d15 exposed a guard defect**: in C and D the history answer
listed the questions it needed answered, numbered, without a terminal "?", and the
guard read only the last sentence, so "Thank you." went light. The guard now reads the
whole of her last answer (one correction, recorded here; the run's results are
preserved unchanged). The must-not phrases the order names went MEDIUM in all four.

**One correction to the shared request design:** none was needed. The one change made
after reading is the routing guard above, not the request.

**Selection under §3:** B passes quality and fails to improve latency; D fails quality;
**C passes quality** on this fixture and is the only one whose answer could arrive in
about a second — if LOW's prompt prefix can be kept warm without disturbing MEDIUM's.
That is §4.

## 4. LOW at the execution boundary (§4) — OBSERVED

`low_boundary.py` (wire request, rendered input, first trials) and `low_boundary2.py`
(cache interference by the runtime's own per-prediction statistics); files
`low-boundary.json`, `low-boundary-rendered.json`, `low-boundary-2.json`. Production's
model, quantization, context (32,768), serving configuration (`--parallel 1`) and
default MEDIUM are untouched; the LOW entry names the same loaded instance and no second
GPT-OSS instance was loaded.

**1. The runtime receives LOW and honours it.** The adapter's request for the LOW entry
carries `reasoning_effort: "low"` (`"medium"` for the Partner entry). LM Studio's own
model-input log shows the rendered prompt: `Reasoning: low` in the harmony system header
against `Reasoning: medium` — the **first differing byte is at offset 148, before the
persona**, and the persona (developer message) is byte-identical thereafter. The
runtime's own output log shows LOW's hidden reasoning as one short line ("We need short
response. Use 'my lord'.") and 26 output tokens, against MEDIUM's paragraph of
deliberation on the same greeting. LOW is executed, not labelled.

**2. Effort changes the rendered prefix, therefore the cache identity.** Because the
effort line precedes the persona, a LOW prompt and a MEDIUM prompt share no prefix
tokens beyond the header; a prime sent at one effort warms only that effort's prefix. A
cold LOW prompt paid **7.28 s** of prefill on 5,743 tokens (runtime `timeToFirstTokenSec`);
after the existing prime machinery ran for the LOW entry (the light route is primed
beside the Partner route, at the entry's own effort) LOW's first token came in
**0.20–1.14 s**. Defect found and fixed: the prime plan was keyed by persona and engine
only, so LOW reused MEDIUM's plan and reported MEDIUM's rendering digest; the key now
carries the effort (the inspector renders at the runtime's default effort, so the
digest remains that rendering's — the token *count*, which places the checkpoint, is
the same at every effort, each being one token; verified against the runtime's input).

**3. No cross-effort interference, measured.** 69 predictions attributed to their
steps; `timeToFirstTokenSec` on a ~5.8k-token prompt is the prefill:

| step under test (3 repeats each) | time to first token, s | reading |
|---|---|---|
| MEDIUM fresh after prime (S1) | 0.184 / 0.201 / 1.305 | warm baseline |
| MEDIUM fresh **after a LOW call**, no re-prime (S2) | 0.187 / 0.204 / 1.302 | **same as baseline** |
| MEDIUM fresh after a MEDIUM greeting, no re-prime (S3) | 0.198 / 0.202 / 0.214 | control |
| MEDIUM fresh after LOW then re-prime (S4, the production pattern) | 0.197 / 1.300 / 1.313 | same |
| LOW Tier-1 after prime (S2, S4) | 0.199 / 1.128 / 1.136 / 1.132 / 0.199 / 1.137 | LOW's prefix warm |
| LOW after LOW (S5) | 0.199 / 0.203 / 0.204 / 0.213 / 0.199 / 0.204 | full reuse |
| LOW after a MEDIUM turn, **no prime at all** (S6) | 0.202 / 1.141 / 0.195 | LOW's prefix survived MEDIUM |

Two states appear and nothing else: **~0.20 s** when an identical prompt shape was
already resident (the runtime's LRU holds whole prompts; repeats of the same fresh
conversation hit it), and **~1.13–1.33 s** when only the persona checkpoint is reused
and the ~700–830 tokens after it (exchange, envelope, Tier-1 blocks, his words) are
prefilled. **The 7 s persona prefill never recurred** after each effort's first prime,
in any order — LOW and MEDIUM prefixes coexist in the runtime's cache; a single serving
slot did not mean a single-entry cache, as §4 warned it might not. The historical
eight-second cost did not recur and was not assumed to.

**Substantive requests still use MEDIUM:** every ordinary-route prediction in every
sequence rendered `Reasoning: medium` (69/69 attributed; the LOW renderings are exactly
the Tier-1 calls). **Re-prime cost:** the production pattern primes both entries after
each turn, sequentially; in run E the refresh of both together measured 0.84–0.89 s, of
which the light entry's prime was 0.23–0.29 s — it runs between turns, never ahead of
an owner request, and is the recurring cost of keeping two prefixes warm. **Working memory:** two 5k-token prefix entries instead of one in the
runtime's cache; the cache is bounded by the runtime (10 entries) and no unload or
reload occurred.

## 5. The answer-onset path (§5) — OBSERVED, DERIVED where marked

Configuration C on the voice path: `measure.py` + `drive_session.py` (the real service on
the scratch store, the driver as microphone and player), `VAL_FAST_ROUTE_TIERS=1
VAL_TIER1_ROUTE=low`, no speculation, the fixed 1.1 s window, Qwen unloaded. Pilot
`pilot-low.json` (3 sessions), then the qualification run `Q-low.json` (29 sessions,
114 turns; `Q-low-onset.json`, `onset_decomposition.py`). Milliseconds; the driver's
clock for speech end and the player's first write, the service's per-turn timeline
(from the recognizer's endpoint) for everything between.

| stage | Tier-1 route (LOW), n = 21 | ordinary MEDIUM, n = 93 |
|---|---|---|
| speech end → endpoint (confirming silence + recognizer) | 962 median, p90 1,047 | 963, p90 1,047 |
| endpoint → owner turn submitted (final transcript + the fixed 1.1 s resume window) | 1,240, p90 1,292 | 1,250, p90 1,286 |
| submitted → provider dispatch (open, seal, Tier-1 projection or full assembly, readiness, exact preflight) | 454, p90 877, max 1,150 | 82, p90 532 |
| dispatch → first provider event | 1,662, p90 2,089 (**the whole generation**: ~1.1 s tail prefill + ~30 tokens; not streamed) | 1,717, p90 2,285 |
| first provider event → first user-facing answer token (hidden reasoning) | — (none: the answer *is* the first event) | 3,826, p90 7,151, max 18,252 |
| first answer text → first speech-safe segment | — (whole answer) | 0 |
| generation complete → Core confirmation (persisted, checks) | ≤ 70 (persisted before the marks that follow) | ≤ 75 |
| first speech-safe segment → TTS start | 6 | 109, p90 247 |
| TTS start → first audio ready at the sink | 589, p90 617 | 608, p90 762 |
| **endpoint → first audio ready** | **3,987, p90 4,518, max 4,670** | 7,819, p90 11,698 |
| **speech end → first audio written by the player** (driver) | **4,796 median, p90 5,370, max 5,443** | 8,674, p90 12,508, max 22,843 |

Reading: **~2.2 s of every turn passes before Core sees it** (0.96 s confirming silence
and recognition, 1.24 s transcript and the fixed window) — held steady by §7 and not
touched. The Tier-1 route's own cost is **~2.7 s**: 0.45 s to dispatch (of which the
first turn of a session waits on readiness and a prime; median otherwise ~0.1 s),
1.66 s of generation on the LOW route (the ~830 tokens after the persona checkpoint
prefilled at ~750 tok/s, then ~30 output tokens), 0.6 s to first audio. Against MEDIUM
on the same greetings the saving is **~3.9 s at the median** (8.7 → 4.8 s) and ~7 s at
p90 (12.5 → 5.4 s): MEDIUM's hidden reasoning (3.8 s median, up to 18 s) is what a
greeting no longer pays.

**Which boundary requires completion, and why.** A Tier-1 answer is delivered whole
after completion by design (§2): the cap-hit and empty-answer checks must fail before a
word reaches him, and the fallback must be exactly once. With ~30 output tokens that
completion costs ~0.4 s after the first token — **generating a correct short answer
removes the earlier candidate's wait naturally** (the old Qwen path waited 4.6 s for
150–600 tokens of the wrong text). No delivery-boundary repair was needed; none was
made. The earlier 8 s preparation bound is now irrelevant to the delivered path (no
speculation is enabled — §6).

**The re-prime cost, observed.** The production pattern primes both entries after each
turn. In this run 143 primes were made, **58 of them over 3 s (6.4–7.5 s)**: the first
prime of each effort in a session is a full persona prefill because the runtime's
prompt LRU evicts the checkpoints between sessions (each turn adds prompts; the same
eviction hit MEDIUM alone in run E at 4.6–6.9 s). Warm refreshes are 0.25–0.33 s per
entry. A prime runs between turns and never starts ahead of an owner request, but an
utterance that arrives *while a cold prime is prefilling* waits behind it at the
runtime: the submitted → dispatch p90 of 877 ms on the Tier-1 route (max 1,150) is
that wait. Two warm prefixes double the exposure to it. Reported, not hidden; a design
that primes only on idle or drops the light prime when a turn is pending is his to ask
for.

## 6. Speculation (§6) — OBSERVED on a subset, and left disabled

Evaluated only after C's text passed (§3, §8). `S-low-spec.json` /
`S-low-spec-summary.json` (`speculation_ab.py`): six sessions of the qualification plan
— the first five and the one holding the two resumed tier-1 pairs — with
`VAL_SPECULATION=light` beside the same LOW route, against the same six sessions of the
no-speculation run (`Q-low`). 24 turns, 8 on the Tier-1 route in both. Binding as
before (§2 of `RESULT.md`): the digest over persona + every message + task, with the
Tier-1 state block's minute clock excluded as the envelope's is — the only normalised
field, because a preparation is bound within seconds of being made and the clock is
presentation of the moment, not context (every other field, including the seal, the
exchange and the contract, is in the digest). A preparation is invalidated when he
resumes (`discarded_resumed`), when the completed request differs (`discarded_mismatch`),
when the turn is not light (`discarded_not_light`) or when it lands too late
(`discarded_unused`); nothing speculative is delivered or persisted before Core binds it.

| | speculation on | speculation off (same phrases, same route) |
|---|---|---|
| Tier-1 route, speech end → first audio written | n = 8: **3,873** median, p90 4,141, max 4,374 | n = 7: 4,796, p90 5,198, max 5,328 |
| MEDIUM turns | n = 16: 9,745 median, p90 12,762, max 20,218 | n = 16: 10,345, p90 14,230, max 22,843 |
| preparations | 11: **8 accepted**, 3 discarded on resume, 0 mismatched, 0 unused; 2,168 ms median to prepare (1,631–3,648) | — |
| false positives / fallbacks | 0 / 0 | 0 / 0 |

**Net benefit on the Tier-1 route: ~0.9 s at the median** (the LOW generation runs
inside the fixed 1.1 s window instead of after it). **Cost to corrected requests:** the
three resumed pairs each had a preparation for their first half in flight when the
second half arrived; the preparations were discarded on resume and completed anyway
(1.7–3.6 s — LM Studio's endpoint offers no cancel, so client cancellation stops
nothing at the engine, as §6 warned). The merged turns then went: "Good evening, Val.
|| Thank you." light 3,734 ms (off: 4,301); "Thank you. || Now change the venue to the
hall." MEDIUM 9,527 (off: 8,494 — **+1.0 s**, the corrected substantive request queued
behind the stale LOW generation on the shared lane); "Good night. || Vowel" MEDIUM
20,218 (off: 12,400 — MEDIUM's own reasoning variance dominates; not attributable). So a
discarded preparation **can delay the corrected request by up to its remaining
generation time (~1–2 s) on the shared execution lane**, exactly the case §6 flags for
LOW and MEDIUM sharing an instance, and it could not be cancelled.

**Decision: speculation stays disabled in the recommended configuration.** A ~0.9 s
gain on an eligible greeting against a ~1 s penalty on a corrected substantive request
is not a net benefit he should pay for by default, and the penalty lands on the turn
that matters more. It remains available behind `VAL_SPECULATION=light` if he judges the
trade differently; speculative TTS was not attempted (the text was not worth voicing
early: LOW's first audio follows completion by ~0.6 s).

## 7. Turn completion and audio (§7)

Held steady: the fixed 1.1 s resume window and the 0.5 / 220 / 650 / 80 ms endpoint
configuration; `VAL_ADAPTIVE_GRACE` unset throughout this pass; the licence-blocked
detector not integrated; no hosted detection. The audio repair (`13b3cb8`), voice
identity and pace unchanged. Physical acceptance of clicks, timbre, continuity and the
progress feedback remains pending; no new audio evidence arose.

## 8. Qualification of the selected configuration (§8) — OBSERVED

**Selected: C — GPT-OSS at LOW with the Core-owned Tier-1 request.** B passes quality
and does not move latency; D fails quality; C passes quality on the fixture, its warm
prefix coexists with MEDIUM's (§4), and it changes the fewest things: no second model
resident, no new artifact, the same instance. Ordinary MEDIUM (A) is the baseline.

**Run:** `Q-low.json` / `Q-low-summary.json` (`SUMMARY_TIER1_ONLY=1`), 29 sessions,
114 turns, real recognition, the desktop-equivalent player, Qwen unloaded, no
speculation, the fixed window. Phrase set `tier1_qualification_plan.json`: the 34
tier-1 phrases (two of them resumed `A || B` pairs) and **80 must-stay-MEDIUM phrases**
— the 45 ineligible/mixed/adversarial (pending actions, corrections, negation, quoted
instructions, capability questions, the five the order names) and the 35 tier-2
pleasantries, which are outside this pass and must route MEDIUM; every session
alternates a tier-1 phrase with a must-stay-MEDIUM one, so the Tier-1 route and MEDIUM
hand over inside one conversation on every session. Every turn is judged on the
transcript the recognizer gave the router. $0.

| | n | Tier-1 route | MEDIUM | substantive false positives |
|---|---|---|---|---|
| tier-1 phrases | 34 | 21 | 13 | — |
| must-stay-MEDIUM (45 ineligible + 35 tier-2) | 80 | **0** | 80 | **0** |

**Zero substantive false positives in 80.** No fallbacks, no unanswered turns, no
underruns (0 of 114). Transitions Tier-1 → MEDIUM → Tier-1 inside a session: 29
sessions, all clean.

**Safe false negatives, 13 of 34, reported separately:** 6 from recognition (the
synthetic voice's "Val" heard as "vowel"/"Vail", one "hall" as "hole" elsewhere; 16
misrecognised turns in all, none routed light); 7 with a correct transcript — 4 are the
frozen rules' known misses ("A very good evening", "Goodbye for now", "Farewell for
now", "Thanks very much indeed" split by the recognizer into two sentences the rule
does not join), and **3 are the pending-matter guard** ("Good afternoon, Val." and two
others spoken after an answer of hers that ended "How may I assist you?" — the guard
reads any question or offer as an open matter, which is conservative and costs
coverage; whether a courtesy offer should count is his call). Refusals by reason across
all 114: 42 work/judgment/memory/capability words, 19 open question or offer, 13 tier 2
not enabled, 11 unknown words from recognition, 2 over twelve words, 7 rule misses.

**Latency (speech end → first audio written by the player; driver clock):**

| | n | median | p90 | max |
|---|---|---|---|---|
| tier-1 phrases on the Tier-1 route | 21 | **4,796 ms** | **5,370** | 5,443 |
| tier-1 phrases that fell to MEDIUM (safe false negatives) | 13 | 7,801 | 11,472 | 12,400 |
| tier-1 phrases, all — what he would experience | 34 | 5,345 | 9,165 | 12,400 |
| must-stay-MEDIUM turns | 80 | 8,894 | 12,744 | 22,843 |

**Owner message visible → first audio** (the driver's `committed_seen`, the moment the
desktop learns his canonical message, 2.1 s after speech end on both routes): Tier-1
route **2,698 ms median, p90 3,256, max 3,406** (n = 21); MEDIUM 6,530 median, p90 10,410,
max 20,679 (n = 93). OBSERVED at the driver. **The ~1 s median / 2 s p90 targets are not met and
are not claimed**: 2.2 s of the 4.8 s is the endpoint and the fixed window §7 holds
steady, and the route's own 2.7 s is prefill, generation and first audio. Quality
passing and latency passing are separate findings: **quality passes on the run with the
two exceptions below; latency improves by ~3.9 s at the median and does not reach the
target.**

**Answer quality on the 21 Tier-1 answers (read):** 17 are right and in her manner
("Good night, my lord.", "My lord, you are most welcome.", "Until the morning, my lord.
I will remain at your service."); 2 are off-register but harmless ("A toast is most
fitting." to "Cheers."; "Good morning, my lord." to "See you in the morning"); **2 are
wrong-turn answers in pending-action contexts** — "Many thanks, Val." after "I am unable
to book the venue… I can draft a booking request" drew a restatement of that offer, and
"Talk soon, Val." after "I have noted your request to cancel the meeting… I will record
the intent" drew **"Understood. I will proceed accordingly."** The second is exactly the
class the order's routing guard exists for: a farewell spoken into an unresolved action
must not be answered as if the action were agreed. The router let both through because
her answers held no question and no offer word. **Guard added after the run:** her last
answer saying what she will, can or cannot do ("I will", "I can", "I cannot", "I am
unable", "I have noted"…) is an unresolved action, and the turn stays on MEDIUM.
Evaluated offline on the run's own recorded contexts (`decide` over each light turn's
transcript and her previous answer): **both wrong-turn cases now route MEDIUM, and so do
4 others** ("evening to you", "Hi there", "See you in the morning", "Nothing more
tonight" after answers containing "I can…"), leaving **15 of 34** on the Tier-1 route.
The run's figures above are preserved as measured; the guard is in the candidate code
and is the coverage cost of the correction-preservation requirement.

**Pending-action, correction and resumed cases:** every "Yes, do it." / "Yes. || Go
ahead with the booking." / "Thanks, but change the venue." / "Wait, I meant…" / "No, not
that one" went MEDIUM; the two resumed tier-1 pairs were joined into one utterance by
the existing resume rule ("Good evening, Val. Thank you." → light, 4.3 s; "Good night.
Vowel" → MEDIUM on recognition); no premature response, no interrupted speech.
Cancellation and late events: not exercised in this run (no speculation, so nothing to
cancel); §6 covers them.

## 9. Resources and offline (§9) — OBSERVED

LOW was selected, so the comparison §9 prescribes: **ordinary MEDIUM routing against
mixed Tier-1 LOW / substantive MEDIUM routing, without Qwen loaded**, the same 29
sessions and 114 phrases (`B-medium-noqwen.json` against `Q-low.json`;
`comparison-A-vs-E.json` from `compare_conditions.py`). Both runs started from the same
resident stack (GPT-OSS alone, the voice worker, the recognizer), each on a fresh
scratch store and a fresh service process, so accumulated cache growth is the same in
both. Metrics: `memory_pressure -Q` "free percentage" of the 48 GB machine sampled once
a second; `sysctl vm.swapusage` used swap in MB; the voice worker's resident set (RSS,
MB) from `ps`; Voice On → cognition and voice ready from the service's own `voice warm`
line.

| | ordinary MEDIUM routing | mixed LOW Tier-1 / MEDIUM |
|---|---|---|
| must-stay-MEDIUM turns, speech end → first audio (80 paired) | 8.99 s median, p90 12.21, max 17.28 | 8.89 s, p90 12.74, max 22.84 (−0.23 s per phrase, median) |
| tier-1 phrases (34 paired) | 8.77 s, p90 11.56 | 5.34 s, p90 9.16 (route mix); 4.80 s on the 21 light-routed |
| lowest free memory | 37% | 34% |
| swap used, first → last sample | 1,651 → 1,619 MB (none new) | 1,659 → 1,651 MB (none new) |
| voice worker RSS, peak | 3,190 MB | 3,190 MB |
| Voice On → ready (`voice warm`) | 4.24 s median (3.49–4.95), n = 29 | 4.25 s (2.90–4.94), n = 29 |
| primes over 3 s (cold prefills) of 143 | 22 (MEDIUM's own evictions) | **58** (MEDIUM's plus LOW's, once each per session) |
| recognition, TTS | unchanged: the same recognizer and voice worker, no underruns in either run (0 of 114) | same |

**Reading:** no substantive-route regression (−0.23 s median per phrase; the p90/max
spread is MEDIUM's own reasoning variance, present in both runs); no measurable memory
cost — the same model instance carries both efforts, and the second warm prefix is one
more entry in the runtime's cache (not separately observable from outside the
runtime; the process-level figures did not move); no swap growth in either run once
Qwen was gone (contrast `RESULT.md` §3.6, where both runs with Qwen resident grew swap
by 1–5 GB). The one resource cost that did move is the number of cold primes (§5):
LOW's checkpoint is evicted between sessions like MEDIUM's, so each session pays one
more 6.5–7 s prefill between turns, with the waiting-behind-it exposure that implies.

**Offline.** Two probes. (1) During the runs, every process involved — the service, the
driver, the voice worker, LM Studio and its helpers — held loopback listeners only
(127.0.0.1:1234, :41343, :8766, [::1]:8766) and **no non-loopback connection** (`lsof -i`,
sampled during run E and again during the baseline). Sampled connections alone do not
establish offline operation, so: (2) the service, the driver and the voice worker it
spawns were run **inside a macOS sandbox profile that denies every non-loopback network
operation** (`loopback-only.sb`; verified beforehand: an external HTTPS request fails
with no connection, LM Studio and the scratch store on loopback answer) for two LOW
sessions — `offline-low.json`: **2 sessions, 8 turns, every turn answered, 0 false
positives, 0 denials in the service log**; 2 tier-1 turns on the Tier-1 route (11.2 s
for the first turn of a freshly started service, which paid the cold primes; 4.75 s for
the next), 2 tier-1 turns held on MEDIUM by the unresolved-action guard (her previous
answer had said "I'm unable to place the booking"), 4 must-stay-MEDIUM turns on MEDIUM.
The harness's machine sampler could not run inside the sandbox (0 samples), which is
why the memory figures come from the unsandboxed runs above. The runtime (LM Studio) itself runs
outside that sandbox as the always-on local server; its connections were loopback-only
in every sample, and no hosted fallback, telemetry or paid API exists on this path (the
seal makes every spoken turn local-only by construction, and the fast route has no
egress, tools or writes).

## 10. Deployment recommendation and rollback (§10)

**Recommendation — for his decision, not made here:** deploy **C** as the Tier-1 route:
`VAL_FAST_ROUTE_TIERS=1` and `VAL_TIER1_ROUTE=low`, with speculation **off**
(`VAL_SPECULATION` unset, §6) and adaptive completion **off** (`VAL_ADAPTIVE_GRACE`
unset, §7), and with the unresolved-action guard of §8 in the router. What he would get:
a standalone greeting, thanks or farewell in a settled context answered in **~4.8 s**
from the end of his speech (~2.7 s from his message appearing) instead of ~8.7 s, in a
short answer in her voice, with zero substantive false positives in 80 adversarial
turns; **about 15 of every 34 such utterances** would take the route under the guard,
the rest falling safely to MEDIUM. What he would not get: any change to substantive
turns (8.7 s median, p90 12.5 s, dominated by MEDIUM's hidden reasoning), the ~1 s
target (2.2 s of every turn is the endpoint and the fixed window), or an answer while a
matter is open. Recurring costs: a second warm prefix (a 0.25 s refresh per turn; a
6.5–7 s cold prime once per effort per session, during which an arriving utterance
waits — §5); no memory change beyond one more cache entry (§9).

**What it is not:** an admission of LOW. LOW carries the Tier-1 request only; the
registry entry stays `NOT_ADMITTED` on disk and is promoted in-process by the setting;
every substantive request renders `Reasoning: medium` (§4, 69/69); the recorded
correction-preservation failure stands, and the router's guards exist because of it.

**Deployment (on his approval):**

1. `uv run alembic -x deploy=live upgrade head` — migration `0032` (two enum values and
   the empty `speculative_preparations`; additive, forward-only in intent).
2. Add `VAL_FAST_ROUTE_TIERS=1` and `VAL_TIER1_ROUTE=low` to the launchd environment
   (`~/Library/LaunchAgents/house.armand.val.api.plist`). Leave `VAL_SPECULATION` and
   `VAL_ADAPTIVE_GRACE` unset.
3. `launchctl kickstart -k gui/$(id -u)/house.armand.val.api`; confirm the startup log
   line "CANDIDATE fast route enabled … effort low" and `/health`.
4. No desktop change is required (the desktop is on `13b3cb8`; nothing in this pass
   touched it).

**Rollback:** remove the two settings and kickstart. Production routing is then exactly
today's; the migration stays (its downgrade refuses while any light call is on record,
as `0031`'s does).

**Physical test (§7, §10):** there is nothing new to hear on production until the
switches are set; the one concise listening test after deployment is: say "Good
evening, Val." and time to her first word (expect ~4–5 s; the audio repair, voice and
pace unchanged); then say something with a pending matter open — "Draft a note to the
reader." then "Thank you, Val." — and confirm the thanks waits for MEDIUM and does not
treat the draft as done.

## 11. Corrections to the earlier record's reporting (§10)

- **"Qualification completed" is not "candidate qualified."** `RESULT.md`'s run E
  completed; its candidate did not qualify. Every use of the word in this document
  means the run; the verdict is stated separately each time.
- **Answer-length statistics and their denominators.** `RESULT.md` §0 gave "median 594
  characters" over the 49 light-route answers of run E, and §3.6 gave "70 → 193 (tier 1),
  134 → 503 (tier 2)" over all 34 tier-1 and 35 tier-2 phrases per condition including
  the ones E routed substantive; both are correct for their denominators and the
  denominators were not stated beside the figures. Here every length figure names its
  set.
- **Two different waits.** The **~41-second within-grace defect** (his resumed speech
  answered as a half-question and the rest queued) was **repaired** on 26 September
  (the resume hold; `2026-09-26-onset/RESULT.md`). The **~3.5-second wait behind
  silenced cognition** (he speaks after the grace while she is still thinking; her
  voice stops but that answer's cognition runs to completion before his new words go
  in) is **unresolved** and is interruption policy, his to rule on (WP3 Record §24).
  `RESULT.md` §10 listed the second correctly; this note keeps the two apart.
