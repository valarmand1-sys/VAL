# The local conversational latency redesign: candidate and qualification — 26 September 2026

Owner order "VAL VOICE: IMPLEMENT AND QUALIFY THE LOCAL CONVERSATIONAL LATENCY
REDESIGN". This is the deliverable §11 asks for. **Nothing experimental is deployed:**
production runs `13b3cb8` (the audio repair, its own record in `AUDIO_REPAIR.md`) with
every candidate switch unset; the candidate exists in this commit, off unless three
environment settings turn it on, and it awaits his review.

Three things are kept apart throughout, as §11 requires: **implementation** (what was
built and how it is held off), **software qualification** (scripted sessions through
the real service and a desktop-equivalent player, on an isolated store), and
**physical acceptance** (his trial in the room, not held). Every figure is labelled
OBSERVED (measured here), DERIVED (computed from observed marks) or NOT RECORDED.
Everything ran locally at $0; production Voice was not opened during the runs (the
production service's session count was 16 before and after).

## 0. The finding that governs everything else

**The named fast candidate does not answer the light turn under the required prompt.**
`Qwen/Qwen3-4B-Instruct-2507` (`mlx-community/Qwen3-4B-Instruct-2507-4bit`), given
the persona whole and the authoritative record-state envelope exactly as Core assembles
every turn, answers a greeting or a thank-you by **copying example lines out of the
persona document** ("I have no book on distribution deals yet, and I won't pretend to
one…", "I do not have that in the record I can see. Put it in front of me and I'll
read it now.", "I remain unconvinced. But it is your house and your decision…"), by
**repeating her previous answer**, or by **inventing a scene** ("the window shows a
quiet snowfall", "a heavy wind with gusts from the east", "the volume on seasonal
staffing"). Established three ways:

- **On the real preparation path** (`light_quality_probe.py`, `light-quality-probe.json`):
  12 of 12 light turns, with and without history.
- **Replayed directly against the loaded instance** from the exact captured wire
  request (`light_prompt_diagnostic.py`, `light-prompt-diagnostic.json`), under every
  controlled variant: LM Studio's own sampling, the model card's recommended
  0.7 / 0.8 / 20, temperature 0.2, and his words as a separate final user message.
  No variant changes the behaviour. Only the **diagnostic control with the envelope
  removed** — not a deployable form, since the envelope is the authoritative context
  §2 requires — yields light answers some of the time, and those still invent details
  ("page 147", "the pacing review").
- **In the qualification run** (§3): of 49 light-route answers, **27 contain a persona
  example line verbatim**, 2 repeat her previous answer, 34 exceed 300 characters
  (median 594 characters against 207 for GPT-OSS on the substantive turns of the same
  run), and by reading, about **6 are acceptable answers to the words spoken** (five
  are the same sentence, "Good evening, my lord. What shall we turn our attention to?").

So under §5 ("enable each tier only if qualified") **neither tier is qualified and
neither is enabled.** The run is still reported in full: it measures what does not
depend on the model — the router's boundaries on real recognition, zero substantive
false positives, fallbacks, the mechanics of speculation and adaptive completion, the
latency of each stage, memory, contention, offline operation — and §11 asks for
quality failures and unmet targets with their causes. The directions that could change
this outcome are his to rule on (§12).

## 1. What was built (implementation)

All of it is in Core or policy; the fast provider owns nothing.

| piece | where | production state |
|---|---|---|
| Two-tier eligibility: deterministic, closed, fail-toward-MEDIUM | `val_policy/light_conversation.py`; fixture 34 / 34 / 38 cases; held-out 10 / 10 / 20 (two held-out false negatives recorded as strict xfails, not tuned) | inert: `FastRoute()` is empty |
| Light task types and capability floor | `TaskType.LIGHT_CONVERSATION`, `SPECULATIVE_LIGHT`, `CapabilityProfile.LIGHT`; routing requires the LIGHT floor | no production configuration carries LIGHT |
| Candidate registry entry | `qwen3-4b-instruct-2507-mlx-lmstudio-light`: NOT_ADMITTED, no profile, no target | unchanged on disk; promoted in-process only by `VAL_FAST_ROUTE_TIERS=1` or `1,2` |
| The light turn inside Core | `Gateway.converse_lightly` — its own function, because the closure contract (§3, 18 August 2026) forbids a task-type parameter on `converse`; `deliberate._ordinary` routes by tier, falls back to the partner route on a light failure before any word is delivered, never duplicates an answer | not reached |
| Speculative preparation | `deliberate.prepare_light_answer` + `speculation.py`: the conversation assembled prospectively with the settled words in the current message's place, under the seal the turn will carry; `Gateway.converse_prospectively` (task `speculative_light_conversation`, persona attributed, attached to no conversation, LOCAL_ONLY); binding by digest of persona + every assembled message + task, the envelope's minute clock excluded; every preparation recorded in `speculative_preparations` (migration `0032`, append-only) as accepted / discarded_mismatch / discarded_not_light / discarded_resumed / discarded_unused / failed | `VAL_SPECULATION` unset: no preparation ever runs |
| Adaptive turn completion | `val_policy/turn_completion.py`: a finished sentence 0.44 s, words that lead on 1.65 s, otherwise the fixed 1.1 s; the state recorded per utterance | `VAL_ADAPTIVE_GRACE` unset: fixed 1.1 s |
| Presentation | response-in-progress stages (thinking / writing / voicing / speaking; queued) — shipped in `13b3cb8` under the production-repair authorisation | live |
| Readiness | per-model readiness locks (the light model never waits behind GPT-OSS's load); the light route primed with the persona prefix on the partner route's terms | live, harmless without a light route |

Proved by test, all suites green, CI mirror green: production routes nothing light;
the closure contract holds (`converse` and `send` expose no task type); the
evaluation-door, execution-gate and device-authority tripwires were each checked and
amended with dated notes, not loosened; a persona-bearing call that belongs to no
conversation records its persona attribution (the speculative call joins the blind
position in that rule); a prepared answer binds only when the completed request is
the very request it was prepared for; changed words, a turn that is not light, and a
preparation that lands after the turn has gone on are each recorded as discarded.

Open problems reviewed at this checkpoint (`VAL_Open_Problems.md`): OP-1's voice note
(the resume merge as a second writer of `message_revisions`) is unchanged by this work —
a bound preparation becomes her answer through the same `settle_turn` as any turn, and a
preparation he did not confirm writes no message.

### Pins

| | |
|---|---|
| fast model | `mlx-community/Qwen3-4B-Instruct-2507-4bit` @ `50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b`; base `Qwen/Qwen3-4B-Instruct-2507` @ `cdbee75f17c01a7cc42f958dc650907174af0554` (Apache-2.0); the non-thinking Instruct variant; LM Studio key `qwen3-4b-instruct-2507`; loaded `--context-length 32768 --parallel 1 --ttl 3600`; 2.28 GB; no sampling override (LM Studio's defaults for the model); output ceiling 1,024 tokens |
| substantive model | `openai/gpt-oss-20b` MXFP4 at MEDIUM, unchanged; LOW unadmitted |
| runtime | LM Studio 0.4.24+1, engine `mlx-llm-mac-arm64-apple-metal-advsimd@1.11.0` (the light prime is bound to it as the partner prime is) |
| recognition | whisper.cpp v1.9.4 + Silero VAD v6.2.0, Whisper Small, endpointing 0.5 / 220 / 650 / 80 ms — unchanged |
| voice | `val-established-v1`, Qwen3-TTS-12Hz-1.7B-Base-8bit, mlx-audio 0.5.5, primed streaming decoder — unchanged |
| turn detector | not integrated (§7) |

## 2. Baseline (§3), once, from existing records

| | value | source | status |
|---|---|---|---|
| speech end → first playback, physical, his 23:03 turn | 18.0 s (~3.5 s queued behind a silenced answer; 5.30 s first synthesis whole; 4.05 s hidden reasoning; 2.67 s dispatch → first output) | WP3 Record §23 | OBSERVED (desktop) |
| speech end → first playback, scripted, before the onset pass (`0f44d20`) | 12.58 s median (7.73–17.44), n = 9 | `2026-09-26-onset/RESULT.md` | OBSERVED |
| after the onset pass (streamed first audio, resume held, facts gated) | 8.98 s median (7.08–10.96), n = 9 | same | OBSERVED |
| first answer text → first audio | 2.10 s → 0.82 s | same | OBSERVED |
| Voice On → speech readiness | 1.1 s → 2.3 s with decoder priming and warm-up | `AUDIO_REPAIR.md` | OBSERVED |
| "Good evening, Val" on MEDIUM, warm | 8.67 s speech end → playback | `fast-probe.json` | OBSERVED |
| cold first turn of a session (GPT-OSS not loaded) | 14.95 s | `fast-probe.json` | OBSERVED |
| his speaking pace | untouched throughout | — | — |

Already in place before this order and not presented as new: the persona-prefix prime
(25 September), the resident voice worker and incremental synthesis (26 September).

## 3. Qualification run (software; §10)

**Method.** `measure.py` starts the real service (`val_api.main.build`, the same
composition root launchd runs) on the scratch store `val_test` (rebuilt empty) and port
8766, addressing the production model instances; `drive_session.py` is the microphone
and the player — 16 kHz PCM in real time, the session polled as the desktop polls it,
each segment "played" on one serial output queue from its arrival, and the speech is
`say -v Daniel`, so speech end is exact on the driver's clock. The phrase set is
`qualification_phrases.json`: 34 tier-1, 35 tier-2, 45 ineligible utterances, written
after the router was frozen and disjoint from the fixture and held-out sets except the
five must-not examples the order names; 20 sessions of 4–6 turns mixing the groups
(§10: routing coverage on mixed conversations); six `A || B` phrases spoken as two
stretches 1.0 s apart (the resume case). Each turn is judged on the **transcript the
recognizer gave the router**, recorded beside the phrase.

Two conditions on the same 20 sessions:

- **E** — the full candidate: tiers 1+2, speculation, adaptive completion
  (`E-fast-spec-grace.json`, `-summary.json`, `service-E-fast-spec-grace.log`).
- **A** — production routing, no switches (`A-baseline.json`, `-summary.json`).

Preceded by a 2-session pilot (`pilot-E.json`; run before the two repairs in §3.5 and
kept as evidence of them).

### 3.1 Routing (E; 114 turns, 20 sessions, 0 failed sessions) — OBSERVED

| group | n | light route | substantive route | substantive false positives |
|---|---|---|---|---|
| tier 1 | 34 | 25 | 9 | — |
| tier 2 | 35 | 24 | 11 | — |
| ineligible | 45 | **0** | 45 | **0** |

**Zero substantive false positives**, including every phrase the order names
("Good evening, Val. Did you finish the invitation?", "Thanks, but change the venue.",
"Yes, do it.", "Rough week. Which reader should I believe?", "What do you think of the
second act?"), the corrections, negations, quoted instructions (recognised without
their quotes and still refused), capability questions, pending-action acknowledgements
and the three resumed ineligible pairs. **No fallbacks** (no light call failed). **No
unanswered turns.**

**Twenty false negatives (eligible turns on the substantive route), all safe:**

- **10 from recognition:** Whisper Small heard the synthetic voice's "Val" as "vowel",
  "Vowell" or "Vail" ("Hello there, vowel.", "Much obliged, Vowell.") and once "dark
  out" as "dog out"; the router does not know those words and fails toward MEDIUM as
  designed. A limit of the harness's voice, not evidence about his; **excluded from the
  router's count, reported here.**
- **10 from the frozen rules** (transcript correct): "Goodbye for now, Val." (the farewell
  list has "bye for now" but not "goodbye for now"); "A very good evening, Val."; "Are
  you well tonight, Val?"; "Farewell for now."; "How do you do, Val?" ("do" is a work
  word); "It's raining here tonight."; "Glad to hear you're there, Val." ("there" is
  stripped as a form of address before the pattern sees it); "Nothing much tonight,
  Val."; and the resumed "How are you, Val? || I'm well myself." **Recorded, not
  tuned** (§10: the qualification cases are not used to tune the router).

Coverage: 25/34 tier 1 and 24/35 tier 2 took the light route; on correctly recognised
transcripts, 25/28 and 24/31.

### 3.2 Latency (E) — OBSERVED at the driver, ms from speech end to first playback start

| | n | median | p90 | max |
|---|---|---|---|---|
| tier 1, light route | 25 | 6,129 | 8,944 | 11,717 |
| tier 2, light route | 24 | 6,020 | 7,377 | 12,228 |
| tier 1 + 2 on the substantive route (false negatives) | 20 | ~8,200 | ~9,600 | 11,083 |
| ineligible, substantive | 45 | 8,779 | 11,719 | 12,802 |

Targets (§10, engineering targets, not promised): tier 1 ~1 s median / p90 ≤ 2 s;
tier 2 ~2 s / ≤ 3 s. **Not met, by a factor of five to six.** Where the time goes,
from the service's own timelines (DERIVED, ms from the recognizer's endpoint):

| stage | speculative-bound light turns (n = 47) | own-call turns (n = 67, nearly all GPT-OSS) |
|---|---|---|
| speech end → endpoint (confirming silence) | ~650 (governed configuration) | ~650 |
| endpoint → submitted (transcript + adaptive window) | 593 | 597 |
| submitted → turn start: **waiting for the preparation to finish** | **4,117** (p90 5,750) | 2 |
| exact preflight | — | 39 |
| dispatch → first chunk | — | 2,068 |
| first chunk → first visible text (hidden reasoning) | — | 4,210 |
| first speech text → audio at sink | 473 | 802 |
| **endpoint → audio at sink** | **5,193** (p90 6,931) | **7,679** (p90 10,766) |

The light route's whole cost is the candidate generating its answer: a preparation
took **4.6 s median, 7.4 s p90, 10.1 s max** (`speculative_preparations.prepared_ms`,
n = 55) — with the persona prefix primed (114/114 refreshes `established`, 0.23–0.29 s)
and a first token in ~160 ms, the rest is 150–600 tokens of the text described in §0.
A model that answered a greeting in one sentence would finish in well under a second
on this path; the fast route's mechanics are not the bottleneck, the model's output is.

### 3.3 Answer quality (E) — read, not scored

49 light answers: 27 contain a persona example line verbatim; 2 repeat the previous
answer; 34 exceed 300 characters; roughly 6 are acceptable. Every one is in
`E-fast-spec-grace-summary.json` (`turns_detail`) beside its transcript. GPT-OSS's 65
substantive answers are of its ordinary quality, with its declared weakness visible in
the run ("I have completed the invitation as requested." on a store holding no
invitation — fabricated continuity, WP-0.9 Stage A finding 1).

### 3.4 Speculation (E; §6) — OBSERVED from `speculative_preparations`

55 preparations: **47 accepted** (bound to the turn, no second model call), **6
discarded_resumed** (he continued inside the window; the merged utterance was prepared
afresh or routed substantive), **2 discarded_unused** (the preparation was still
running past the 8 s bound; the turn went on alone), 0 mismatches, 0 failures. Every
accepted answer's speculative call is attached to no conversation and named by the
preparation row that binds it to his message and her answer. The binding is exact
(persona + every assembled message + task; the envelope's minute clock excluded, the
seal predicted as `conversation_sealed` exactly as the completed turn carries it);
the pilot proved the discard paths (mismatch, not light) in tests, not in the run,
because the resumed cases were caught earlier by the session's resume rule.

Cancellation: a preparation that misses its turn is not cancelled server-side — LM
Studio's OpenAI endpoint offers no cancel and the light instance serves one request at
a time — so a stale preparation completes and is recorded `discarded_unused`. **The
computation is not released on discard**; it is bounded by the output ceiling. That
is a limit of the runtime, reported.

Cost: $0 (LOCAL_NO_METERED_COST), 55 calls recorded in `model_calls`.

### 3.5 Adaptive completion and resumed speech (E; §7)

118 utterances judged `complete` (window 0.44 s), 2 `uncertain` (1.1 s), 0
`continuing`; recognition supplies terminal punctuation on nearly every utterance, so
the long window never fired. **All six resumed pairs were still joined into one
utterance** ("Good evening, Val. Thank you.", "Yes. Go ahead with the booking.")
because the second stretch began 1.0 s after the first ended, inside the endpoint's
0.65 s confirming silence plus the 0.44 s window plus transcript latency, and the
existing resume rule held the settled utterance — **no premature response, no
interrupted speech, no half-question answered** in this run. The margin is thin: a
pause of ~1.3 s would now split a sentence that the fixed 1.1 s window joined. That
trade is the whole content of adaptive completion and is his to weigh; it is
measured here, not recommended.

Two repairs made after the pilot, before the run: the router's address-only clause
("Good evening, Val, it's me." split on commas to a clause "Val" that classified as
nothing — fixed structurally, fixture cases added, no qualification phrase used to
tune); and the preparation wait (0.6 s, so every light turn queued a duplicate request
behind its own preparation on the one-request instance and the late result vanished —
now 8 s, with the late case recorded `discarded_unused`).

### 3.6 Against production routing (A) — the substantive comparison

A: the same 20 sessions and 114 phrases with no switch set (`A-baseline.json`,
`compare_conditions.py` → `comparison-A-vs-E.json`). Every turn substantive, 0 failed
sessions, 0 unanswered, 0 underruns; the light model was loaded but unused. OBSERVED,
speech end → first playback:

| group (paired phrases) | A, production routing | E, candidate | E − A per phrase, median |
|---|---|---|---|
| tier 1 (34) | 7.78 s median, p90 9.88, max 10.42 | 7.08 s, p90 8.94, max 11.72 | −0.76 s |
| tier 1, the 25 phrases E routed light | 7.41 s, p90 8.98 | 6.13 s, p90 8.94 | |
| tier 2 (35) | 8.71 s, p90 11.56, max 20.51 | 6.45 s, p90 9.54, max 12.23 | −2.18 s |
| tier 2, the 24 phrases E routed light | 9.21 s, p90 11.63 | 6.02 s, p90 7.38 | |
| ineligible (45) | 9.06 s, p90 12.08, max 14.77 | 8.78 s, p90 11.72, max 12.80 | −0.03 s |

So the candidate machinery took **0.8–2.2 s off a greeting or pleasantry at the median**
— a fraction of the 6–7 s the order set out to remove — while making her say three to
four times as much (median answer 70 → 193 characters on tier 1, 134 → 503 on tier 2),
and the text it made her say is §0's. **The substantive route did not regress from the
resident light model and the candidate machinery** (ineligible −0.03 s median; the
per-phrase spread of ±4 s is GPT-OSS's own hidden-reasoning variance, present in both
conditions).

Memory across the two runs: A's lowest free was 23%, E's 16%; **swap grew in both —
A 5.22 → 10.15 GB, E 4.70 → 5.70 GB** — with both models resident in both conditions, so
the growth is the cost of long sessions on the resident stack (the runtime's prompt
caches over 20 conversations), not of the candidate's calls; A is therefore not a
no-residency baseline for memory, and one was not run.

### 3.7 Audio in the run

0 underruns across every segment of 114 turns; no gaps counted. The player here is the
driver's serial queue, not a speaker: **software playback timestamps, not acoustic
onset** (§10 asks that the two be distinguished; the room adds the device's own
latency, NOT RECORDED here).

## 4. Readiness, resources, privacy, offline (§9) — OBSERVED

- **Voice On → ready** (cognition warm + voice worker primed, with the light route now
  readied in the same step): 5.89 s median (5.13–6.43), n = 20 sessions; of which the
  voice worker 5.4 s including a 3.7 s discarded warm-up generation under contention
  with the two model primes. Separately measured, as §9 asks; higher than the 2.3 s of
  `AUDIO_REPAIR.md` measured alone.
- **Residency:** GPT-OSS 12.10 GB + Qwen3-4B 2.28 GB loaded (32,768 context each,
  parallel 1, TTL 1 h), the voice worker 3.19 GB resident at peak, Whisper in the
  service. Idle with everything loaded: 92–93% free. **During the run: lowest free 16%
  (pilot 14%); swap grew 4.70 → 5.70 GB over the 20 sessions** (pilot: 1.30 → 5.00 GB
  over 2). Contention is real on a 48 GB machine with both models, the voice worker and
  the recognizer resident; it did not fail anything here, and it is not nothing.
- **Contention on the substantive route:** GPT-OSS's own-call turns in E measured
  7.68 s endpoint → audio against the onset pass's ~8.98 s speech end → playback — no
  regression from the resident light model is visible at this precision; a stricter
  answer is §3.6.
- **Offline:** during the run every process involved (LM Studio and its helpers, the
  scratch service, the voice worker, the recognizer) held only loopback listeners
  (127.0.0.1:1234, 127.0.0.1:8766, [::1]:8766) and **no non-loopback connection**
  (`lsof -i`, sampled during run E). No hosted fallback, telemetry or paid API exists on the
  path. The one download — the pinned public model snapshot via `huggingface_hub` —
  carries no conversation data.
- **Privacy:** no raw audio, no conversation text and no transcript is added to any
  store or log by this work; `speculative_preparations` holds a SHA-256 of the settled
  words, never the words; a preparation he did not confirm is not his message.
- **Not done:** speculative TTS (never attempted — the text was not worth voicing), any
  new persistent cache, conversation-content priming, silent truncation.

## 5. Audio (§8)

Repaired in production (`13b3cb8`; `AUDIO_REPAIR.md`, WP3 Record §25, index §112):
the cold streaming decoder and per-piece scheduling. Physical acceptance of clean
audio is pending his trial (§9). Fallback if the room disagrees: whole-segment
synthesis, 1.1–4.5 s to first audio. Truthful response-in-progress feedback is live.

## 6. The turn detector (§4, §7)

`livekit-plugins-turn-detector` 1.8.3 installs on arm64 (onnxruntime 1.30.0, isolated
in `~/.val-runtimes/turn-detector-venv`); the plugin code is Apache-2.0, but **the
end-of-turn model is under the LiveKit Model License**, whose §3 forbids use "on a
standalone basis or with any frameworks other than LiveKit Agents", and the plugin is
deprecated in favour of LiveKit's hosted inference. Val would use the model standalone,
offline, inside her own turn machinery — the excluded use. **Not integrated; blocker
reported.** Adaptive completion therefore uses the transcript's own cues.

## 7. Unmet targets and their causes (§11)

| target | result | cause |
|---|---|---|
| tier 1 ~1 s median, p90 ≤ 2 s | 6.1 s / 8.9 s | the candidate's answer: 4.6 s median to generate 150–600 tokens of persona echo; plus ~0.65 s confirming silence, 0.6 s transcript + window, 0.5 s to first audio |
| tier 2 ~2 s median, p90 ≤ 3 s | 6.0 s / 7.4 s | same |
| the fast model generates the actual answer | **fails** (§0) | the 4B model attends to the persona's examples and the envelope, not to his words; not a sampling or message-structure matter |
| substantive measured reduction | §3.6 | — |
| Voice On → ready | 5.9 s | the voice worker's warm-up under contention |
| resumed / corrected utterances | joined correctly, 6/6 | thin margin (§3.5) |

What *did* work: routing (0 false positives on 45 adversarial turns, 10 recorded misses),
speculation as a mechanism (47/55 bound, none mismatched), adaptive completion without a
premature answer, priming of the light route, per-model readiness, offline operation.

## 8. Release candidate, rollback, handoff (§11)

**Release candidate: none proposed for the routing.** The code is committed with every
switch off, so production behaviour is unchanged; a restart of the service on this
code with the live store at `0031` is safe because no code path reaches `0032`'s
objects while the switches are unset.

If he chooses to trial the candidate anyway (not recommended on this model): apply
`uv run alembic -x deploy=live upgrade head` (adds two enum values and one empty table,
additive), add `VAL_FAST_ROUTE_TIERS` (`1` or `1,2`), optionally `VAL_SPECULATION=light`
and `VAL_ADAPTIVE_GRACE=on` to the launchd environment, `launchctl kickstart -k`.
Rollback is removing the settings and kickstarting; the migration stays (forward-only
in intent, like `0031`), and its downgrade refuses while any light or speculative call
is on record.

## 9. Owner trial (§11) — what is there for him to hear now

Production `13b3cb8` only: clean audio (clicks and timbre — the audio repair), the
response-in-progress stages, natural pauses (the fixed window) and interruption. The
fast route, speculation and adaptive completion are **not** in this trial; nothing in
it depends on Qwen3-4B.

## 10. What needs his ruling (§12)

1. **The fast candidate.** Qwen3-4B-Instruct does not carry the light turn under the
   prompt §2 requires. The options are: (a) close the fast route on this model and keep
   MEDIUM for everything, accepting ~8–9 s for a greeting; (b) authorise **one** larger
   local candidate for the same narrow role (a broad search is excluded by the order —
   this would be a named pick, and the machine's headroom in §4 argues against a third
   resident model); (c) rule on how the authoritative envelope is presented to a small
   model — the diagnostic control shows the envelope is what the 4B model cannot look
   past, but removing or reshaping it is a Core assembly decision, not an
   implementation detail, and the control's answers still invented.
2. **Adaptive completion's trade** (§3.5): a shorter wait after a finished sentence
   against splitting a sentence resumed after ~1.3 s.
3. **Interruption policy** (WP3 Record §24, unchanged): the queue behind a silenced
   answer.
4. **Memory** (§4): whether a second resident model is acceptable at 16% lowest free
   and growing swap.
