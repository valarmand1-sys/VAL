# Owner acceptance repair pass — WP3 — 25 September 2026

Owner acceptance of 24 September 2026 banked ten passes and failed on five areas.
This is what the retained evidence established, what was wrong, and what changed.

**One cause produced three of the five failures.** It was not the recognizer.

---

## 1. What the retained evidence says about his acceptance turns

Read from the live store: `voice_sessions`, `voice_message_provenance`,
`message_revisions`, `messages`, `model_calls`, `classifications`,
`speech_deliveries`, `speech_playbacks`, `speech_voices`.

### 1.1 Endpoints per intended utterance

Three sessions, two conversations, eight canonical spoken messages — and **five of
the eight had a post-submission merge**, each joining two halves of one intended
sentence:

| what became canonical first | what the merge joined to it |
|---|---|
| `This is what masks they have.` | `alan can you hear me` |
| `Peace. Yes, exactly. Let's get political, all this is important.` | `Now can you hear me?` |
| `Now, can you hear me?` | `Can you hear me?` |
| `evening Val doing` | `Good evening, Val. How are you doing?` |
| `Thank you.` | `Very good. What is the council going to be covering?` |

`voice_message_provenance` records utterance indices 1–4 in the first session and
1–7 in the third for what he describes as roughly two and four intended utterances:
**about two endpoints per intended utterance.**

### 1.2 The pause durations that triggered those endpoints

**NOT RECONSTRUCTIBLE FROM RETAINED EVIDENCE.** No pause duration is recorded
anywhere, and the audio was correctly ephemeral. The intervals between
`finalized_at` timestamps are not pause durations — they contain a whole cognition
call. No value is inferred, and none is quoted.

### 1.3 Whether merged utterances overlapped in audio

**No overlap beyond the configured 80 ms of pre-speech padding**, established from
the code path rather than from the audio: `Listener.finalize` zeroes both the
utterance buffer and the padding ring, and the VAD is advanced window by window with
no rewind, so nothing but that padding can cross an utterance boundary.

**The buffer and the VAD state are reset between utterances** — `finalize` clears
`utterance`, `padding`, `in_speech`, `speech_run` and `silence_run` together.

So the duplicated wording he saw — `evening Val doing Good evening, Val. How are you
doing?` — is **not** re-recognised audio. It is his own repetition: the first
recognition was garbled, no answer was audible, he said it again, and the merge
joined the two. §1.2 F is satisfied by leaving genuine repetition alone, which is
what the repair does.

### 1.4 Merge-triggered recomputation, before the repair

**None.** Eight canonical messages, eight `conversation` calls in `model_calls`. The
old merge revised the message and kept the existing answer, so it caused no extra
cognition. That is exactly why the answer was obsolete.

---

## 2. Root cause of the obsolete answers

The chain, established from the records above:

1. an endpoint fires inside his sentence;
2. the resume grace (1.1 s) expires before he resumes, so the fragment is submitted
   and **answered**;
3. he carries on speaking;
4. the second half arrives after submission, and the old code **revised the owner's
   message in place** — leaving Val's answer attached to wording that had moved
   underneath it, which the interface then labelled "This reply answered the earlier
   wording of the message above";
5. because he was still speaking while the answer was being produced, the
   recognizer's `speech_start` interrupted delivery: **six of the deliveries in the
   record are `interrupted` at 0 characters** — his own continued speech barging in
   on the answer to the first half of it. That is where the silences came from, as
   well as from §4 below.

The Option-1 no-regeneration doctrine that revision path implements is correct for a
correction **Lord Armand chose to make**. Here he chose nothing: the house split one
sentence and answered half of it.

---

## 3. The revision-authority repair

`VoiceSession._merge_after_submission` no longer revises. When the owner resumes
before delivery has become audible, the exchange is **superseded**:

1. **the obsolete answer's speech is stopped** before a word of it can be spoken —
   available because `_mergeable` only ever returns a turn whose delivery is not yet
   audible, checked against that answer's own message id;
2. **the exchange is withdrawn** through the existing retraction machinery — his
   fragment and the answer to it both stay in the record, marked, with every
   classification, measurement and cost untouched, exactly as Remove does;
3. **the joined wording is submitted as a new turn**, which gets its own answer and
   its own delivery.

The resulting invariant is the strongest form of what §1.1 asks: **a voice answer is
never bound to wording that changed afterwards, because a voice turn's message is
never revised after the fact at all.** An obsolete call that really ran stays on
`model_calls` as the historical fact it is, and no longer masquerades as the answer
to what he said.

**A rule that was thought to be in tension with this is not.** A message anchoring a
recorded decision refuses *revision* and permits *retraction*, precisely because a
retraction rewrites nothing and never invalidates evidence valid when produced. So
the words a decision was made about are still never rewritten, and the blind position
still stands exactly as it was — asserted directly in the amended test.

**The cost, stated plainly.** A merge now causes a second cognition cycle where it
previously caused none. A turn that is superseded therefore takes roughly twice as
long as an ordinary one. That is the right trade — an answer to half his sentence has
no value at any latency — but it is a real cost and it is reported rather than hidden.

---

## 4. The recognition pipeline: the dominant defect was ordering

Tested against the **production recognizer** — the pinned whisper.cpp v1.9.4
`927cfce3`, the admitted `ggml-small.en` and Silero v6.2.0, the same helper, the same
endpoint configuration — with the existing frozen fixture whose correct transcript is
`And so, my fellow Americans,`. No owner audio, nothing persisted, no model
downloaded or changed.

### 4.1 Chunk ordering — CONFIRMED, and it is the cause

The desktop forwarded every 20 ms chunk with `void this.forward(pcm)`: **fifty
concurrent, unawaited POSTs per second**, whose arrival order at the service nothing
guaranteed.

| stream | transcript |
|---|---|
| in order | `And so, my fellow Americans,` |
| one block arriving **1** late | `And so am I fellow Americans!` |
| one block arriving **2** late | `So much homework!` |
| one block arriving **4** late | `I'm so wanted to follow the winner!` |

That is precisely the character of what he saw: fluent, confident, and bearing no
relation to what he said — `This is what masks they have.` for "Val, can you hear
me", and `Peace. Yes, exactly. Let's get political, all this is important.` for
something else entirely.

**Repaired** by `OrderedPcmSender`: one sender, **one request in flight**, strict
order, and chunks coalesced into a larger payload while a request is outstanding, so
a slow request produces one bigger send rather than a backlog of racing small ones.
Bounded: a ceiling on the queue, and audio that could not be sent in time is dropped
**and counted** rather than pretended about. Closed on mute and on Voice off, because
audio from a microphone the owner has already closed is not audio to send.

### 4.2 Resampling — a real defect, honestly bounded

The worklet decimated by *picking* every Nth sample with no low-pass filter, while
its own comment claimed a decimating average. Picking folds everything above 8 kHz
straight back into the speech band.

Measured on a 10 kHz tone at 48 kHz, which can only reach 6 kHz by aliasing:
**picking put 3.9× more energy there than averaging does** (23,998,499 against
6,141,550).

On the fixture, **both methods transcribe correctly** — it is band-limited speech
upsampled from 16 kHz, so there is little above 8 kHz to alias. So: a real defect,
demonstrated on a tone, and **not demonstrated to change recognition on the material
available**. It is repaired because the code now does what it always said it did, not
because it was shown to be the bottleneck.

### 4.3 Everything else §2 asked about

| candidate | finding |
|---|---|
| duplicate PCM chunks | none: each chunk is offered once and consumed once |
| overlapping chunk transmission | none after the repair: one request in flight |
| lost chunks | possible only past the queue ceiling, and then **counted** |
| out-of-order chunks | **CONFIRMED as the dominant defect** — repaired |
| incorrect int16 conversion | none: clamped to ±1 then scaled, asserted in tests |
| clipping | none introduced by the conversion |
| sample-rate conversion error | **CONFIRMED** (aliasing) — repaired, effect on transcripts not demonstrated |
| wrong channel handling | none: channels are averaged to mono |
| resampler state reset | the bin accumulator resets per output sample; the worklet keeps one chunk and no history |
| endpoint/VAD timing | see §5 — **not** caused by reordering |
| resume-window concatenation | this was the authority defect, §2–§3 |
| replay of prior utterance PCM or text | none: `finalize` zeroes the buffer and the padding |
| desktop speaker / system-audio contamination | not established either way; `echoCancellation` is requested, and the physical question is his |
| inadequate echo cancellation | PENDING OWNER ACCEPTANCE — not claimable from a synthetic test |
| the helper receiving different bytes from the capture stream | no transformation between the worklet and the request body; the bytes are forwarded verbatim |

---

## 5. The endpoint: NOT adjusted, and why

§2.1 authorised one evidence-based adjustment **if** the trace demonstrated endpoints
firing inside ordinary utterances. The merge records demonstrate exactly that. But
§2.1 also requires the magnitude to be justified from measured pause durations or,
where those are not reconstructible, **from a focused owner diagnostic** — and the
durations are not reconstructible (§1.2).

Two further reasons not to change it now, both evidential:

**Reordering was tested as a cause of premature endpoints and falsified.** The same
audio with an internal pause of 400 ms and of 500 ms — both comfortably under the
650 ms minimum — endpointed exactly once whether delivered in order or with blocks
two and four positions late. One utterance, one endpoint, every time. (The transcript
still collapsed to `Oh my god`, which is §4.1 again.)

**And his experience was measured through a broken pipeline.** He reported having to
speak slowly, loudly and repeatedly — behaviour that a garbled transcript provokes,
and behaviour that itself lengthens pauses. Tuning the endpoint against pauses
produced by working around a defect that no longer exists would be tuning against
the defect.

So: **no endpoint parameter changed.** `min_silence_ms` remains 650, and the
diagnostic that would justify changing it is added instead — the helper now reports
the silence run that ended each utterance, and the gap since the previous one, both
non-audio measurements §2 permits. The next acceptance measures what this one could
not.

---

## 6. The silent replies: a production registration that no test could miss

`speech_voices` in the live store held **0 rows**. Every delivery test had always
passed because **its fixtures registered the voice**; the running application never
did. So provenance could not be written for anything Val spoke, the session ended in
error, and `speech_generations` is empty for all eight turns.

Correlating the silences, as §3 requires: of the deliveries on record, **two reached
`started` and `completed`** with real audio (`first_audio_ms` 22,027 and 16,421) and
**six are `interrupted` at 0 characters** with reason "the owner began speaking".
So the silences have two causes, and the provenance failure is only one of them: the
session that failed on provenance is the third one, and within it the interruptions
came from his own continued speech (§2). Both are now repaired, by different fixes.

**The repair** is a governed idempotent provisioning step at startup: when the
admitted governed voice loads, it is registered, idempotently on the reference
digest, from **the same on-disk record the conditioning itself is read from**.
Nothing is fabricated, no identity is invented, `val-established-v1` is unchanged, no
conditioning was regenerated, VoiceDesign did not run and ElevenLabs was not called.
A record missing a field is refused rather than defaulted. A registration that fails
leaves the gateway with **no** voice and says so at startup — never unattributed
speech.

Proved on the live store after restart:

```
val-established-v1 | c5ebe0c7210bf332 | 900362 bytes | 24000 Hz | 18.756 s
identity_claim: This is VAL's established voice used as zero-shot …
```

### 6.1 The class, not the instance

Every row the Voice-path tests and fixtures provision, checked against the live store:

| row | required at runtime? | live store |
|---|---|---|
| `speech_voices` (the governed voice) | **yes** | **was MISSING → now PRESENT** |
| `personas` (one active) | yes | PRESENT (v1.9 revision 8) |
| `projects` | no — a voice session runs unassigned | PRESENT (8) |
| `conversations` | no — created by the first turn | PRESENT (40) |
| `budget_reservations` | no — written per call | PRESENT (187) |
| `voice_sessions` | no — written per session | PRESENT (3) |
| `speech_generations` | no — written per segment | PRESENT as a table, 0 rows, correctly |
| `conversation_egress_seals` | no — written by the first spoken turn | PRESENT (2) |
| `blind_positions`, `execution_events`, `voice_recovery_journal` | no — fixtures only, for scenarios | n/a |

Nothing else was missing, and no row was created that the production path does not
require.

---

## 7. The two latency figures he saw were not latencies

### 7.1 `barge-in → silence 49891 ms` — cause established

**The metric's start mark was stale.** `bargeInAt` was written as
`this.timings.bargeInAt ?? this.now()`, so it kept the **first** barge-in of the
whole session, while `silenceAt` was overwritten by the **latest** stop. The figure
was therefore the span from the session's first interruption to its last — across
several turns and minutes — and not an interruption latency at all.

Of §4.2's candidates: **(D), a stale prior event being paired**, with (B) as its
mechanism. Not (A): physical output did not continue for 49.9 seconds. Not (E):
cancellation reached the desktop, which is why `silenceAt` moved each time.

`transcript → audible 23210 ms` has the same defect: `speechEndAt` and
`firstAudibleAt` were each written once per **session**, so the pair spanned turns.
The figure happens to be near a plausible single-turn value, which is what made it
dangerous — it invited optimisation of an interval nobody had measured.

**Repaired.** Every interval is now a pair of marks from one event: the transcript
mark is keyed to the service's utterance index and resets `firstAudibleAt` with it,
and each interruption writes both of its own marks. Two regression tests hold it,
including one that fires a second barge-in forty seconds after the first and asserts
the pair is the second one.

### 7.2 Three post-fix turns, every boundary directly observed

Production-shaped, on the sealed voice path, **$0** — the same harness the latency
pass used, with the fixture as the input. Medians of three; each turn in
`postfix-latency.json`.

| boundary (exact name) | median |
|---|---|
| end of **fixture** speech → turn start (resume grace + finalisation) | 1.475 s |
| turn start → message persisted | 0.007 s |
| classification | **not run** — the conversation is sealed (§2.3) |
| context / recall / record-state assembly | 0.007 s |
| assembly end → runtime readiness start | 0.012 s |
| local runtime readiness | 0.018 s |
| exact context preflight | 0.044 s |
| preflight end → provider dispatch | 0.004 s |
| **provider dispatch → first provider chunk (pre-generation)** | **9.926 s** |
| **first chunk → first Core-visible text (hidden reasoning)** | **6.560 s** |
| first visible text → speech-safe segment queued | 0.317 s |
| segment queued → TTS start | 0.000 s |
| **TTS synthesis of the first segment** | **5.805 s** |
| TTS return → audio at the delivery hand-off | 0.000 s |
| **end of fixture speech → first audio at the delivery hand-off** | **23.211 s** |

Per turn: 23.211 / 24.964 / 22.446 s. **Merge-triggered recomputation in these
turns: none** — no endpoint fired inside the fixture, so no supersession occurred.
Where one does occur the turn costs a second cognition cycle, as §3 states.

Two things must be said exactly:

- **This is not physical audibility.** The last boundary is audio reaching the
  delivery hand-off inside the service. The desktop's playback-start command is not
  instrumented in this harness, and the physical metric stays PENDING OWNER
  ACCEPTANCE.
- **The input boundary is a fixture, not his voice.** It is labelled as such and is
  not relabelled as owner speech.

**And the uncomfortable part.** The median internal interval, 23.211 s, is within a
second of the 23,210 ms his window displayed. The metric that produced that number
was defective — it paired marks from different turns (§7.1) — and it nevertheless
landed on a value close to the truth. That is exactly what made it dangerous, and it
is why the repair was to the pairing rather than to the number.

**Nothing in this pass makes Val answer faster.** Of the 23.2 s, **22.3 s is the
provider and the voice**: pre-generation 9.9, hidden reasoning 6.6, synthesis 5.8.
Val's own code contributes about 0.09 s outside the 1.1 s resume window. His
observation that replies felt like minutes is correct, and the cause is the cognition
route's cost at MEDIUM, which the latency pass already established and whose only
remaining reductions are the two decisions already in front of him: cross-request
prefix reuse, and the parked LOW question. **That is an owner decision, not a defect
this pass can repair.**

### 7.3 What the internal figures actually are

The one metric that matters —
**END OF OWNER SPEECH → FIRST PHYSICAL AUDIBLE VAL SPEECH** — is
**PENDING OWNER ACCEPTANCE**, and so is
**OWNER BARGE-IN → PHYSICAL MAC SPEAKER SILENCE**. Neither is claimed here.

The dominant internal contributor is already established and unchanged by this pass:
his eight acceptance turns each spent **12.0–16.6 s inside the single local cognition
call** (`model_calls.latency_ms`: 16557, 12191, 12791, 13961, 12150, 13873, 13689,
12042). That is GPT-OSS at MEDIUM, which the latency pass measured and whose only
remaining reductions are the two decisions already in front of him.

---

## 8. The conversation switch

The release is the ruling and is unchanged: Voice never carries its microphone or its
session silently into another conversation. What changed is that he is **asked
first**. Every navigation that changes the active conversation — opening one, New
chat, entering a project, leaving to Everything — now goes through one guard:

> Switching conversations will end Voice and release the microphone. Continue?

**Cancel** leaves the conversation, the Voice session and the microphone exactly as
they were. **Confirm** ends Voice through the ordinary governed path — device
released, playback stopped, shortcut unbound — and only then navigates. No automatic
activation anywhere, and no "keep Voice across conversations" path was added.

The effect-level release stays as the safety net for a change arriving by another
route, and a structural test asserts every navigation call site sits behind the
guard, because a handler that forgot it would not show up in a rendered test nobody
clicked.


---

# Owner acceptance Step B — 25 September 2026

Step A passed. Step B failed, and the retained evidence from this run reconstructs it
completely. **The endpoint diagnostics the repair pass added did not survive their own
run** — see §B.7 — but the recovery journal, which does survive, turned out to carry
the decisive facts.

## B.1 The run, from the store

Session `01a0d631-3190…`, conversation `01a0d630-f496…`, opened 20:31:50.45.

| moment | event |
|---|---|
| 20:32:07.71 | **owner msg 1 committed** — "I'm testing your system." (utterance 1) |
| 20:32:23.31 | answer msg 2 — **15.6 s of cognition** |
| 20:32:29.78 | Val's first audio; `first_audio_ms` **22,016**; segment 1 = "Good evening, my lord." |
| 20:32:31.06 | delivery **interrupted** at 22 characters, "the owner began speaking" |
| 20:32:31.23 | **owner msg 3** — "Now please tell me exactly what you heard me say." (utterance 2) |
| 20:32:45.03 | **utterance 4's first provisional** — "evening Val" |
| 20:32:46.51 | utterance 4 provisional — "evening Val, I'm testing your system." |
| 20:32:47.97 | utterance 4 provisional — "…Please tell me exactly" |
| 20:32:48.61 | answer msg 4; **its delivery interrupted at 0 characters** |
| 20:32:48.64 | **owner msg 5** — "Hello." (utterance 3) |
| 20:32:50.32 | utterance 4 provisional — "Good evening Val. I'm testing your system. Please tell me ex…" |
| 20:33:00.20 | answer msg 6; audio 20:33:02.95 → 20:33:08.05, **two segments** |
| 20:33:06.01 | **owner msg 7** — the merged string, `merged_from {2}` (utterance 4) |
| 20:33:20.90 | answer msg 8; audio 20:33:23.95 → 20:33:36.59, **three segments** |

**Internal utterances: 2 from attempt #1 (utterances 1 and 2), 1 from attempt #2
(utterance 4), plus utterance 3 which is neither** — see §B.4. Canonical owner
messages: **4**. Val answers: **4**. Two intended utterances.

**One correction to the account.** The journal places attempt #2's recognized speech
at **20:32:45.0 – 20:32:50.3**, about **14 s** after attempt #1's second utterance
ended (~20:32:30.1), not thirty. His experience of a long silence is not in doubt —
he could see nothing, for the reason in §B.2 — but the measured gap is fourteen
seconds, and the repair is sized against the measurement.

## B.2 Why nothing appeared: presentation, not settlement

**The first turn was committed at 20:32:07.71 and answered at 20:32:23.31 — both
before attempt #2 began at 20:32:45.** So §4.1's class **B**.

The desktop re-read the conversation only when a turn had an **answer**
(`settled.answer !== null`). His own words therefore stayed invisible for the whole of
cognition — 15.6 s on this turn — and he reasonably concluded nothing had happened.

**§4.0 is eliminated.** The trailing silence did reach the service: the turn settled
1.1 s after the endpoint, which is exactly the resume grace and nothing more. The
ordered sender did not hold it. Progression is driven by the desktop's 120 ms poll
(`snapshot` → `advance`) and by incoming audio; neither needs further owner speech.

**Repaired.** The conversation is re-read as soon as a canonical turn exists, and again
when its answer arrives — keyed on the turn's identity so it happens twice per turn and
not on every poll.

## B.3 The cross-attempt merge, and its exact cause

`_mergeable` had **no time bound of any kind**. It asked only whether the turn had been
*delivered* — and msg 3's answer was interrupted at **0 characters**, so `delivered`
stayed false and that turn remained eligible for ever.

Fourteen seconds later, utterance 4 merged into it. The lineage of the string he
flagged is exactly:

| component | utterance | recognised | source |
|---|---|---|---|
| `Now please tell me exactly what you heard me say.` | **2** (attempt #1, second half) | settled ~20:32:30.1, committed 20:32:31.23 as msg 3 | the stale fragment |
| `Good evening Val. I'm testing your system. Please tell me exactly what you heard me say.` | **4** (attempt #2, complete) | 20:32:45.0 – 20:32:50.3 | his deliberate retry |

joined in that order — the old tail **in front of** the new complete attempt, which is
precisely what §6 forbids.

**Repaired.** A resumed utterance may join a submitted turn only if the pause between
them is within **the configured resume window** — measured from the previous
utterance's endpoint to the next one's first voiced frame, both the recognizer's own
monotonic marks. The pause here was ~14 s against a 1.1 s window. A session-clock
fallback bounds the case where a recognizer reports no marks, so a markless recognizer
cannot unlock what was previously unbounded. Four regression tests; the two that matter
fail against the old code, which was checked by mutation.

## B.4 "Hello." — what can and cannot be established

**Not a hallucination on silence or noise.** Driven through the production recognizer:

| material | RMS | VAD speech starts | utterances | text |
|---|---|---|---|---|
| digital silence, 3 s | 0.0 | **0** | 0 | — |
| noise, 3 s | 0.002 | **0** | 0 | — |
| noise, 3 s | 0.010 | **0** | 0 | — |
| noise, 3 s | 0.050 | **0** | 0 | — |
| noise with gaps | 0.027 | **0** | 0 | — |
| real speech, 0.4 s | 0.033 | 0 | 0 | — |
| real speech, 0.8 s | 0.095 | 1 | 0 | — |
| the whole fixture | 0.194 | 1 | 1 | `And so, my fellow Americans,` (voiced 1.664 s) |

**The Silero VAD never triggered on any synthetic non-speech**, so whisper.cpp is never
invoked on it. The admission rule §7 contemplates would therefore have prevented
nothing here, and adding it would be theatre: it is **not** implemented.

**Not stale state either.** The journal holds "Hello." as utterance 3's own provisional,
not a replay of another utterance's text.

So the microphone captured something the VAD classified as **speech**. Its window is
bounded by the utterance ordering — after utterance 2's endpoint (~20:32:30.1) and
before utterance 4 began (~20:32:44) — and **Val was audible for the first ~0.96 s of
that window** (20:32:29.78 → 20:32:31.06).

> **Which acoustic source it was: NOT RECONSTRUCTIBLE FROM RETAINED EVIDENCE.** The
> audio was correctly ephemeral. That it overlapped her playback is not evidence that
> it was her, and his statement that he did not speak does not distinguish her voice
> from other room or system audio. The `gap_before` measurement that would have pinned
> the window existed in this build's helper and was **discarded by the event type**
> before anything could record it (§B.7).

## B.5 Physical speech: already progressive, and the cost is elsewhere

Per-segment synthesis, from `speech_generations`:

| answer | segment | text | synthesis | audio |
|---|---|---|---|---|
| msg 2 | 1 | "Good evening, my lord." | **6,708 ms** | 1.68 s |
| msg 6 | 1 | "Good evening, my lord." | 2,727 ms | 1.28 s |
| msg 6 | 2 | "How may I assist you today?" | 2,942 ms | 2.16 s |
| msg 8 | 1 | "I have no record of hearing your words…" | 3,305 ms | 2.80 s |
| msg 8 | 2 | "The house's logs show that no spoken input…" | 4,865 ms | 4.80 s |
| msg 8 | 3 | "If you wish, please repeat what you said…" | 3,223 ms | 2.96 s |

**Segment-1 synthesis already begins before cognition completes** — by 0.3 s on msg 2
and 0.05 s on msg 6 — so the pipeline is progressive. The margin is negligible because
~6.6 s of hidden reasoning precedes any visible text and the answers are short, so the
whole answer lands within a fraction of a second of its first sentence. That is why it
reads as delayed read-aloud: **the visible text is complete before the first audio
because synthesis of the first segment takes 2.7–6.7 s after it.**

**Inter-segment gaps were 0.007 s, 1.66 s and 2.07 s — not 45–90 s.** The minute-scale
waits he experienced were **new answer cycles** to the extra turns: Val's audible
moments were 20:32:29.8 (interrupted), 20:33:02.9 and 20:33:23.9, which is 33 s and
21 s apart, each gap being cognition for a new message.

**Repaired, and measured.** The first synthesis of a session cost **6,708 ms against
2,727 ms** warm — about four seconds of weights coming off disk, since each synthesis
is its own subprocess. The runner gains a **load-only warm mode** that generates no
audio, writes no file and records no provenance, and a Voice session warms the voice
alongside the cognition runtime while he is still speaking. Neither warming is a gate.
And the progressive boundary is now **recorded** rather than argued: delivery keeps the
first segment's synthesis start and the cognition-complete moment, and a test asserts
segment 1 begins before the answer is finished — with the honest counter-case that a
route which cannot stream records `False` rather than looking identical.

## B.6 False barge-in: not demonstrated

Both interruptions are explained without it:

- **20:32:31.06**, while Val was audible: caused by utterance 2 — **his own words**,
  the second half of his own sentence. Genuine barge-in.
- **20:32:48.62**: caused by utterance 3 being submitted. Val had **no audio playing**
  — that delivery was interrupted at 0 characters, and her previous playback had ended
  17 s earlier. So this was not her voice being heard.

**No canonical owner message is established to have originated from audio captured
while Val was physically speaking.** Utterance 3's window overlaps her playback by at
most ~0.96 s of a ~14 s window, and which source it was is not reconstructible.

Counts and their explanation: **2 intended utterances → 4 canonical messages → 4
answers.** The two extra messages are (a) attempt #1 split in two by an endpoint firing
inside his sentence, and (b) utterance 3, whose acoustic source is not established.

## B.7 A defect in my own diagnostic

The repair pass taught the helper to report the silence that ended each utterance and
the gap before it began. **`RecognizerEvent.of` dropped both fields**, so the run they
were built for could not be measured, and §10's measured pause values are
**NOT RECONSTRUCTIBLE FROM RETAINED EVIDENCE** for this run.

Now: the event carries `silence_seconds`, `gap_before_seconds`, `voiced_seconds` and
`seconds`; the helper additionally reports how much of each utterance the **VAD** called
speech; and every settled utterance logs all four to the service log, which is retained.
The next run measures what this one could not.

**The endpoint is still not changed.** `min_silence_ms` remains 650. The measurement
that would justify changing it is the one that was lost, and it exists now.

## B.8 What the platform applied to the microphone

The constraints request `echoCancellation`, `noiseSuppression` and `autoGainControl`.
**Whether WKWebView granted them was not observable from this run.** The desktop now
reads the live track's own `getSettings()` and records it — as `null` where the platform
states nothing, because "did not say" and "said no" are different facts, and the
acceptance question turns on which. The reporting is best-effort by construction: a
platform that throws yields nulls and **never** takes capture down, which is asserted.
