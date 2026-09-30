# Val in the room — live voice mode, work package 3 — 24 September 2026

Owner execution order of 24 September 2026. The controlled record of what was
built, what was proved, what was found, and what is **not yet** established
because it needs Lord Armand's own ears and his own screen.

**Status: awaiting owner acceptance.** Every automated proof below is green and the
application is built and installed. §20's physical sequence — the macOS orange
indicator, the sound from the speakers, the interruption in the room — has not been
run, because it cannot be run by me. **This package is not COMPLETED until he has
run it.**

---

## 1. The two invariants this package exists to make true

**Microphone activation belongs to the owner alone.** Val may never acquire it. No
model, persona instruction, Core decision, tool, API-side event, automation, timer,
wake word, idle behaviour, app launch, restart, machine wake, conversation restore,
error recovery, recognizer event, TTS event or future provider can. The only
activation events are explicit owner gestures in the desktop: the visible Voice
control starts a session, and the visible microphone control or the global shortcut
unmutes one that is already active. The shortcut **cannot start Voice**, and is
unregistered while Voice is off.

**Physical speech output belongs to the owner too.** Val is never audible merely
because Core produced text. With Voice off there is no sink at all — the player is
created when the owner starts a session and destroyed when he ends it — so no
generated speech can be played, no background process can re-enable playback, and no
recovery routine can restart it.

Both are enforced by structure, not by wording. The state machine's guards, the
single capture call site, the player's lifetime and the service's session-required
routes are each tested, and the tests sweep **every event** rather than the ones an
author thought of.

---

## 2. THE LIVE-VOICE SEAL — the new privacy ruling

> A live microphone transcript never leaves this Mac. Not on the turn it was
> spoken, not by a later typed turn in the same conversation, and not by being
> recalled into a different one.

### 2.1 How it is represented — and what it deliberately is not

`Egress.LOCAL_ONLY`, in `packages/domain/src/val_domain/egress.py`, carried on
`GatewayRequest` beside the classification and changing nothing else.

**It is not `Classification.RESTRICTED`, and that was a decision rather than an
omission.** Three reasons, each of which would have been enough:

- The local cognition configurations are registered **Restricted-ineligible**.
  Marking voice content Restricted would have left a spoken turn with no eligible
  route at all, or forced local eligibility to be widened to Restricted.
- **Whether local inference may carry Restricted content is a reserved owner ruling
  that has not been made.** It must not be made implicitly — not by this fact, and
  not by inventing a "successor" registry entry that quietly has it.
- Restricted carries recall and handling protections. Applying them to voice would
  change how spoken conversations are remembered, and a spoken turn is an ordinary
  turn (§1.6). Only its egress differs.

**Consequences, all verified:** a voice turn keeps its ordinary classification
(Protected); the existing local partner configuration remains eligible; **no registry
configuration was changed and none was added**; and the seal governs egress only —
not memory, not recall, not eligibility.
`packages/policy/tests/test_egress_policy.py` holds each of those as an assertion,
including a sweep over every cloud configuration in the registry rather than a
sample.

### 2.2 When it takes effect — two layers, and why

**Transient.** From the moment the owner turns Voice on until the session ends, the
conversation is local-only for **every** request it makes — typed or spoken, and
whether or not anything has been said yet. Read from live process state, never from
a table: a durable row saying "Voice is on" that survived a crash would be exactly
the stored preference §4.2 forbids, and it could not be true anyway, because a
session dies with the process holding its microphone
(`VoiceSessions.live_conversations`).

**Durable.** Applied only when live-microphone-derived text **first becomes a
canonical message**, and applied **in the same database transaction as that
message** — through `conversations.append`'s existing `also` hook, which runs on the
transaction that is writing the message. There is therefore no observable state in
which a spoken message exists and the seal does not, including the moment
immediately after Voice is turned off, when the transient layer has ended and an
ordinary typed turn would otherwise be free to route to a cloud provider.

`test_no_state_exists_with_the_spoken_message_present_and_the_seal_absent` asserts
that over the whole store rather than over one turn, so a future route to canonical
that forgot to seal fails there too.

**Turning Voice on does not durably seal anything.** A session that produces no
canonical spoken text leaves the conversation unsealed, and its ordinary egress rules
resume when the session ends — proved by
`test_a_voice_session_that_says_nothing_leaves_the_conversation_unsealed`, which
checks the seal's absence *and* the transient layer's presence while the session was
open.

**Every route to canonical applies it**, named rather than assumed
(`SealRoute`): `utterance_finalized`, `resume_merge`, and
`recovered_fragment_adopted`. The third needed a caller, so `POST /voice/adopt`
exists: the owner adopting a guess a restart found open, which is his act and never
the house's. All three are tested.

There is **no unseal control**, and `conversation_egress_seals` refuses UPDATE and
DELETE by trigger, so there is no quiet one either.

### 2.3 Where it is enforced

Three places, deliberately, with the same function deciding in all of them so they
cannot drift apart:

1. **The turn decides once** (`val_gateway.deliberate.send`) and carries the
   decision. Every call the turn makes is governed by one answer; recomputing it
   per call would let one of them disagree, which is the one failure a privacy rule
   cannot survive.
2. **Routing filters** (`val_policy.routing.candidates`), so a local-only request
   selects a local route and is *answered* rather than routed anywhere and then
   refused.
3. **The gateway refuses immediately before dispatch** (`Gateway._attempt`), which
   is the narrowest door every provider call passes through — including the pinned
   and candidate lanes. It runs before eligibility, before the adapter is looked up,
   before a runtime is asked to come up and before anything is reserved, so a
   refused call transmits nothing, charges nothing and writes no row.

The refusal is `LOCAL_ONLY_EGRESS_REFUSED` and is **not retryable**: retrying is the
thing forbidden, and no approval path exists, because the ruling is that the
transcript does not leave. The test asserts the refusal happened *before the adapter
was reached* and that `model_calls` stayed empty.

Checked against `Hosting` and never `Metering`: **a free cloud route would still be
egress.**

### 2.4 The seal travels with recall

Applied where recall is assembled into the request — `assemble_turn` now returns the
egress decision as it stands **once the request's content is known**, and the caller
routes on what came back rather than on what it passed in. A caller routing on the
decision it supplied would be routing on a request it had not finished building.

**Sealed conversations are not excluded from recall.** A spoken conversation is
remembered exactly as a typed one is; what changes is that remembering it makes the
remembering request local-only.
`test_a_sealed_conversation_is_still_recallable_locally` holds that directly.

### 2.5 The canary, and what the cloud actually saw

Every egress negative is proved with a distinctive phrase and a **cloud transport
spy** standing where every cloud provider stands, recording the complete request it
was handed. Nothing is ever sent to a real provider to prove a negative. The spy
**refuses** rather than answering, so a leak fails the turn as well as leaving
evidence.

| case | what the cloud saw | canary present? |
|---|---|---|
| the spoken turn itself | **nothing at all** | no |
| a later typed turn in the same sealed conversation | **nothing at all** | no |
| a different unsealed conversation recalling the sealed content | one call: its own classification of its own newly typed message | **no** |
| a fresh unsealed conversation drawing in nothing sealed | its ordinary classification, as before | no |

Each negative is paired with a positive that makes it mean something: the local
route **did** receive the phrase, so the tests prove the content was carried and
still did not leave, rather than proving that recall returned nothing.

### 2.6 A stated ordering fact, recorded rather than smoothed over

**The classifier runs before recall is assembled.** So an unsealed conversation that
is *about to* recall sealed content still makes its ordinary cloud classification
call first. What that call carries is the newly typed message alone — no history, no
recall, no envelope, no voice-derived context — so the sealed phrase cannot reach it,
and the test asserts that over the complete request body. The §2.6 escalation applies
to the call that actually carries the recalled content, which routes locally.

The alternative would have been to seal every conversation in a project as soon as
one of them was spoken in. §2.7 rules that out explicitly: a new conversation that
draws in no sealed content is the clean boundary back to ordinary egress. The
behaviour is therefore correct as specified, and the ordering is stated here so it is
a known property rather than a surprise.

---

## 3. The owner-accepted consequence, and what classification was found to gate

### 3.1 The finding, established from the code before the rule was written

**The consequentiality classification gates the reasoning path of the response, and
nothing else. It gates no action with effects outside the conversation, because
Layer 0 has no such action.**

The evidence is narrow and checkable: `TaskType` has exactly five members —
conversation, classification, strip, blind_position, title — and every one is a model
call. There is no tool contract, no MCP client, no web search, no filesystem writer
and no external side effect anywhere on the turn path. What the verdict decides today
is whether a blind position is formed before the final answer and whether a
deliberation is recorded: *how Val reasons*, not what she does to the world.

### 3.2 So the rule is a guard, and it is installed

`val_policy.consequence.execution_refusal` refuses on three states —
no record at all, **did not run**, and ran-but-established-nothing — and
`EXECUTION_GATED_ON_CLASSIFICATION` is the registry of executors that must consult
it. It is **empty, truthfully**, and a test asserts both that it is empty and that
`TaskType` still has exactly its five members, so the finding above stays true rather
than becoming stale. The first executor to arrive fails closed instead of inheriting
a default of yes.

**Owner confirmation is untouched.** NOT RUN never waives a confirmation the owner
would otherwise have been asked for.

### 3.3 NOT RUN is a positive state, never a fabricated negative

`classifications` gains `not_run_reason`, and the original `attempts >= 1` check —
true of every row that could then exist — is relaxed **only** where that reason is
present. A second constraint holds such a row to the truth: no attempts, no verdict,
`established = false`, no resolving call, no call ids. `record_classification` refuses
a not-run row that carries any of a run's traces.

The recorded reason names the seal and its grounds:

> local-only conversation (live-voice seal): voice_session_active. The
> consequentiality classifier and the preference strip route are cloud structured
> configurations, and live-voice content is not transmitted off this machine to be
> classified (owner ruling, 24 September 2026).

`test_the_spoken_turn_is_recorded_as_not_run_never_as_not_consequential` asserts the
verdict is null, the attempts zero, the calls zero and the resolution absent — and
explicitly that the verdict is not `not_consequential`.

### 3.4 Val is told, in one additive field

The record-state envelope gains `external_egress`, **present only when the
conversation is local-only**. An ordinary turn's envelope says nothing about egress,
because restating the ordinary case on every turn is context spent on nothing (the
per-turn necessity rule). The note tells her plainly that web search and remote tools
are unavailable here, and that the consequentiality classification did not run — so
she can answer him truthfully instead of attempting an operation that policy will
silently refuse, and so she does not describe a view as independently formed when it
was not. A test asserts the field is present in a sealed turn's request and **absent**
in an ordinary one.

---

## 4. Devices belong to the desktop

**One capture path.** `getUserMedia` plus an AudioWorklet in
`apps/desktop/src/microphone.ts`, and two tests — one in vitest over every desktop
module, one in pytest over the tree — assert **exactly one call site in the whole
application**. No MediaRecorder, no ScriptProcessorNode, no temporary file, no shell
capture, no API-side capture daemon. The service-side sweep covers `voice`,
`delivery`, `playback`, `speech`, the recognizer and the service app, with comments
and docstrings stripped first so a module's own prohibition is not mistaken for the
thing it prohibits.

**The recognizer still owns nothing.** It takes `feed(self, pcm: bytes)` from its
caller, and no device call appears in it.

**Format.** 16 kHz, mono, signed int16 little-endian — the recognizer's existing
contract — converted in the bounded worklet, which holds exactly one chunk
(320 samples, 20 ms) and no history. Each chunk is **transferred**, not copied, so
the audio thread keeps no second copy. No conversion intermediate touches disk.

### 4.1 Mute releases the device

On mute, in this order: stop accepting samples; detach the worklet's message handler;
disconnect the worklet; disconnect the source node; **stop every track**, not the
first; drop the stream; close the context; revoke the module URL.

Tested: every track stopped, the stream released, the nodes disconnected, the context
closed, the URL revoked, a chunk arriving through a retained reference **dropped**,
and the whole path idempotent — because a release that cannot be called twice is one
that will one day not be called at all. And explicitly: `track.enabled` is left
alone, because a disabled track is still a held device and the orange indicator stays
lit.

**The macOS indicator is the owner's ground truth and this application cannot
substitute its own icon for it.** §9.1 is his to accept.

### 4.2 Unmute reacquires

An explicit gesture, every time. The UI shows `Unmuting…`, `getUserMedia` is called
again, a new track is obtained, and only when it is genuinely live does the label
become `Mic Listening`. A failed reacquisition **stays muted, tells him, and does not
retry**. The test asserts two tracks were handed out and the first was stopped —
which is the whole of the rule: the device is not kept open across a mute to make
unmuting faster.

### 4.3 Lifecycle

Voice goes **off** — device released, playback stopped, shortcut unbound — when the
window goes away (`pagehide`, `beforeunload`), and when the **conversation changes**.
The conversation rule is keyed on the conversation the window is showing, with one
deliberate exception: a session started on a brand-new chat adopts the conversation
its first spoken turn creates, rather than treating that arrival as a switch.

A hidden or unfocused window is **not** a reason to mute (§16): he may be listening
while working in another application, which is exactly what the global shortcut is
for. So visibility is deliberately not listened to.

No error path calls `getUserMedia` again automatically, anywhere.

*Coverage note, stated rather than implied:* the controller's release-on-lifecycle
behaviour is tested directly for both `conversation_changed` and
`app_or_machine_suspending`. The one-line React effect that *invokes* it on a
conversation change is not covered by an automated test — the app-level wiring is
exercised by acceptance step I and by ordinary use.

### 4.4 Mute while Val is speaking

She keeps speaking. Mute controls his outgoing microphone only: it does not stop
playback, cancel her answer, clear her queue or leave Voice mode. Held in the state
machine (`activity` survives the mute) and in the player's independence from capture.

---

## 5. Physical playback, and the boundary it adds

WP2 proved delivery as far as an in-process sink. **Bytes handed to a desktop are not
sound in a room**, and that difference is what this package adds.

`DesktopSink` extends the ephemeral sink rather than replacing it, so everything WP2
proved about delivery truth — the delivered boundary, the exact prefix, the interrupt
semantics — holds unchanged. What is added is a bounded hand-off queue (depth 8) whose
segments are handed over **once** and released as they leave. A desktop that has
stopped collecting is one whose playback has ended, so a full queue drops the oldest
and counts it rather than growing.

**A defect found and fixed while testing this.** The delivery object was cleared the
instant the turn finished, so a segment synthesised in the last moment of an answer
was discarded before the desktop's next poll — losing the end of her sentence. The
hand-off now survives the turn (`VoiceSession.speech_handover`) until the next turn
replaces it, and Voice off discards it.

**One poll, two questions.** `GET /voice/sessions/{id}/speech/next` answers both *is
a segment waiting* and *should what is already playing stop*. A desktop that asked
only the first would keep a buffer sounding for a poll interval after Val had been
interrupted, which is precisely the failure barge-in must not have.

### 5.1 Delivery truth, physically

Migration `0030` adds `speech_playbacks`, append-only, one row per transition, with
five states kept apart: `available_to_desktop`, `playback_started`,
`playback_completed`, `playback_interrupted`, `playback_failed`.

- `available_to_desktop` is **the service's own fact about its own hand-off**, and a
  desktop claiming it is refused with 422. It is not a claim that anything was heard.
- `playback_started` comes from the desktop's own report, made from the scheduling
  call itself — the moment the buffer is on the device.
- A report about a segment the house never handed over is refused with 409: a
  playback report about audio that was never sent is not evidence.
- The **text** on the row comes from the record of the hand-off, not from the report:
  the desktop says what its device did, and the house says what the words were.

The assistant message is never rewritten, and WP2's `speech_deliveries` is untouched.

---

## 6. Barge-in

When the microphone is live and he begins speaking while Val is speaking: the
recognizer's `speech_start` reaches the existing service-side interruption path,
which stops the sink and discards the queue; the desktop's next speech poll (80 ms)
returns `stop: true`; and the player **stops the sounding buffer first**, then
discards what was queued behind it. A queue emptied while a buffer plays on is not an
interruption, and the test asserts the source's `stop()` was called, the queue
emptied, the interruption recorded and — explicitly — that it was **not** recorded as
a completion.

Nothing already executed is undone, and the exact physically heard prefix stays on
the record.

**The real interval is his to measure.** The desktop records
`barge-in → buffer stopped` in the window and shows it. WP2's service-side 0.008 ms
figure is **not** reported as the WP3 boundary, and no physical figure is claimed
here at all: §20 G produces it.

---

## 7. The global mute shortcut

`⌘⇧M`, through the official Tauri 2 facility:
`@tauri-apps/plugin-global-shortcut@2.3.2` and `tauri-plugin-global-shortcut@=2.3.2`,
both pinned exactly. It is the **only** plugin registered, and the capability grants
exactly four permissions — register, unregister, unregister-all, is-registered.
Nothing else is exposed through the native bridge: no filesystem, no shell, no
process, no HTTP.

- **Registered only while a Voice session is active**, and unregistered when it ends.
- **It cannot start Voice.** Two guards: it is not bound at all while Voice is off,
  and the toggle it reaches is a hard no-op unless a session is already active.
- If the combination is already owned by macOS or another application, that is
  **said plainly and no substitute key is chosen silently.**

Tested: it toggles mute and unmute on an active session, does nothing from off (and
opens no session), and is unregistered when Voice goes off.

---

## 8. Honest indicators

The UI reports **actual** state. `Muted` appears after the release path has run and
no live track remains; `Mic Listening` only when a new capture track is live and
connected. Both dimensions are shown when they differ — `Voice On · Mic Muted · Val
Speaking` is a real label — and the states are **words**, so colour is never the only
signal. `aria-pressed`, `aria-label` and `aria-live` are set, and the guess in
progress is rendered deliberately unlike a message, because a provisional transcript
is not something he said.

A test asserts that an activity change cannot make a released microphone read as
live, over every activity value.

---

## 9. Audio and transcript lifecycle

**Raw audio exists only in:** the WKWebView MediaStream, the bounded AudioWorklet
buffer (one 20 ms chunk), the loopback request body, the service's request memory,
and the recognizer's stdin and volatile buffers. It is released progressively after
consumption, immediately on mute for anything unsent, on Voice off, on error, on
permission loss and on shutdown. **No audio file survives, and none is written.**

**Val's synthesised speech** exists in the service's hand-off queue until collected,
then in the desktop's decode buffer, which `decodeAudioData` detaches. Nothing is
retained at either end and there is no route to fetch a segment twice.

**Provisional transcripts** are not canonical, not Partner context and not recall
evidence; the existing recovery and interruption semantics are unchanged; and a
fragment the owner *adopts* applies the durable seal.

**Final transcripts** become ordinary canonical messages, stored **locally** in
PostgreSQL as conversation text, carrying voice provenance and applying the seal.
They may enter local Core, memory and recall as any message does, they carry the seal
wherever they or their derivatives go, and they may never egress.

Said plainly, because it is the distinction that matters: **"no recording" does not
mean "no local textual conversation history."** What he said is in the House record,
as his typed words are. What is never kept, anywhere, is the sound of him saying it.

---

## 10. What was found while building this

Four things, each recorded rather than quietly fixed:

1. **The hand-off died with the turn** (§5): the last segment of an answer could be
   synthesised and dropped. Fixed; the hand-off outlives the turn.
2. **A spoken turn can no longer anchor a blind position**, because a sealed
   conversation makes no classifier call. WP1's test R asserted that it could. The
   behaviour under test — a message anchoring a recorded decision is never rewritten
   to fake continuity — is unchanged and still tested, with the anchoring row now
   constructed by the test rather than arrived at. **The merge refusal remains as a
   guard whose production reachability from voice is currently nil**, and that is
   reported here rather than deleted with the test.
3. **The classifier precedes recall assembly** (§2.6): stated as a property, with the
   reason the alternative was rejected.
3b. **A latent hole in the non-deliberated send path.** `val_gateway.loop.send` — the
   plain WP-0.7 path, which no service route reaches but which harnesses and tests
   do — discarded the escalated egress decision that `assemble_turn` returns. A call
   on that path that recalled content from a sealed conversation would have routed
   without the seal. It now routes on what came back. Not reachable from the running
   application, and closed rather than left for someone to find.
4. **WP1 and WP2's voice test doubles now mirror the real door** (`spoken=True`), and
   their scripts no longer carry a classifier reply, because a spoken turn no longer
   makes that call. Where a test asserted the old two-call behaviour, it now asserts
   the new one-call behaviour **and** the NOT RUN record — a stronger assertion, since
   it fails both if Core is bypassed and if the transcript reaches the classifier.

---

## 11. Tests

**New:** `packages/policy/tests/test_egress_policy.py` (18) — what the seal is, what
it refuses, that routing is unchanged for ordinary requests, that voice content is
**not** Restricted and no eligibility moved, and §2.3.1's execution gate.
`packages/gateway/tests/test_voice_local_only.py` (16) — the canary suite, both
layers, atomicity, every route to canonical, the recall escalation, the envelope, and
the pre-dispatch backstop. `packages/gateway/tests/test_voice_device_authority.py` (6)
and `apps/api/tests/test_voice_device_authority.py` (3) — the structural proofs.
`apps/desktop/src/voiceState.test.ts` (18), `microphone.test.ts` (15),
`speaker.test.ts` (7), `voiceController.test.ts` (14).

**Extended:** `apps/api/tests/test_voice_service.py` — hand-off, the two playback
facts, the two refusals, and the adoption route. `packages/domain/tests/test_schema.py`
— the two new tables and the new column, hand-transcribed as everything there is.

**Full suites, all green:** domain **400**, gateway **852**, providers **254**, API
**105**, desktop **155**. Lint, format, mypy (104 files), secrets, pins, scope-ruling
and dependency-direction checks pass. Migration `0030` round-trips on an empty
database and refuses a downgrade that would require inventing a classifier attempt
that never happened.

**No existing test was weakened.** Three were amended to the new ruling, each with
the reason written in the test, and one strengthened. §0.1's vacuous assertion —
`assert ... or True` — is replaced with one that a mutation of `first` makes fail,
and that mutation was run to check.

---

## 12. What is NOT established

- **The macOS orange indicator.** Code cannot claim what his screen showed. §20's
  A, C, D, E, F and H are his.
- **Sound from the speakers.** Every figure here ends at the desktop's own
  scheduling call. Whether Val was audible, and in her established voice, is his to
  hear.
- **Physical barge-in latency in the room**, and **acoustic self-trigger**. The
  echo-cancellation constraint is requested; whether it is sufficient in his room is
  a physical fact, and it is not claimed from a synthetic test.
- **Unmute-ready latency** in real use. The window measures and displays it; no
  expected number was invented.
- **End of his speech → first audible speech**, for the same reason. The desktop's
  `transcript → audible` figure is labelled as a window observation, one poll
  interval at most after the service established the transcript, and not as the
  recognizer's own clock.

---

## 13. Deployment — done, with its results

**The live store was fingerprinted read-only before migrating and again after.**

| | before | after |
|---|---|---|
| messages | 158 | 158 |
| conversations | 38 | 38 |
| model calls | 185 | 185 |
| message digest | `77b71645d3c1f4788b5f243ec5d4332a` | `77b71645d3c1f4788b5f243ec5d4332a` |

**Identical.** Migration `0029_speech_delivery → 0030_voice_local_only` through the
governed `alembic -x deploy=live upgrade head` path; head now `0030_voice_local_only`.
The three new or changed structures are empty, as they must be before he has spoken:
`conversation_egress_seals` 0 rows, `speech_playbacks` 0 rows, and 0 classifications
carrying a not-run reason. Nothing existing was rewritten.

**The service** was restarted onto this build with `launchctl kickstart -k` and
reports `{"status":"running","warnings":[]}`.

**The desktop application** was built with `npm run tauri build` (release) and
installed at `/Applications/Val.app`; the installed binary's digest matches the
bundle it came from (`6b01d3ec86a8c909…`). Val was not running during the install.
The previous install is preserved at `~/Val builds/Val (built 2026-09-22).app`,
**outside `/Applications`**, because every Val build shares the bundle identifier
`house.armand.val` and a preserved copy inside `/Applications` makes macOS launch the
wrong one.

**One correction the install forced.** The first bundle carried no
`NSMicrophoneUsageDescription`, and macOS will not present the microphone prompt at
all without it — §20 A would have failed with nothing to diagnose but silence. It is
now declared in `src-tauri/Info.plist`, and the words are what he will read in the
system dialog: *"Val listens only while you turn Voice on. Your speech is transcribed
on this Mac and the audio is never recorded, stored or sent anywhere."* The bundle was
rebuilt and reinstalled with it present, and the string was verified in the installed
`Info.plist`.

---

## 14. Owner acceptance, first attempt: step A FAILED, and three defects behind it

He ran step A on the first installed build. Voice reached `Voice Starting…`, macOS
presented the microphone prompt with the expected text, and startup then failed with
the visible error **`Not allowed by CSP`**, returning to Voice Off.

**The violated directive was `default-src 'self'`**, as the fallback for the script
source, because the policy sets no `script-src`. **The blocked resource was the
AudioWorklet processor module**, which the desktop built as a string and loaded from a
`blob:` URL — and `blob:` is permitted in this policy for `img-src` and `media-src`
only. Reproduced under the policy read verbatim out of `tauri.conf.json`:

> Loading the script `blob:…` violates the following Content Security Policy
> directive: **"default-src 'self'"**. Note that `'script-src-elem'` was not
> explicitly set, so `'default-src'` is used as a fallback. The action has been
> blocked.

**The fix changed no policy at all.** The processor now lives in
`apps/desktop/public/pcm-worklet.js`, which the application serves at
`/pcm-worklet.js` — a same-origin script, which `default-src 'self'` already permits.
Adding `script-src 'self' blob:` would have permitted *any* blob-backed script this
window could construct; this needs no exception. The loopback boundary, the capability
file and the native bridge are untouched.

**Two further defects came out of testing that fix rather than reading it.** The
extracted file still carried `${TARGET_SAMPLE_RATE}` as literal text — a
`SyntaxError` at line 23 — so Voice would have failed again in the same place with a
different message. And, more seriously: **the microphone was not released
deterministically on the failure he hit.** The stream was acquired into a local
variable and assigned to the object only after the module load, so `release()` in the
`catch` found nothing to stop, and the granted track was left live, referenced only by
a variable that had gone out of scope. His screenshot showed no active microphone, and
that is consistent with the engine having collected it — but **§1.3 says a failure
moves toward released, and "eventually, probably" is not that.** Every resource is now
owned the instant it is created, and a regression test drives an `addModule` that
throws `Not allowed by CSP` *after* the device is granted and asserts every track
stopped, `released` reported before the failure, and never a live report. Reverting the
assignment order makes that test fail, which was run to check.

Full diagnosis, with the probe and both verifications:
`docs/reviews/qualification/runs/2026-09-24-wp3-csp/RESULT.md`.

---

## 15. Owner acceptance — the sequence, one step at a time

§20's sequence is his. It is not run here, not simulated, and not inferred. When he
is ready, it proceeds A through I, one step at a time, and any orange-dot failure is
a **defect** to be fixed and the step repeated — not reinterpreted.

---

## 16. Handoff — the owner diagnostic pass of 25 September 2026

**WP3 remains PARTIAL.** Full reconstruction and evidence:
`docs/reviews/qualification/runs/2026-09-25-wp3-onset/RESULT.md` (evidence index §103).
The previous passes' records are left as they were written.

**Starting state of this pass, as the owner set it down:**

- Step A remains banked.
- Step B remains unaccepted.
- the stale unlimited resume merge was repaired.
- self-trigger was not reproduced in the controlled run.
- historical "Hello." source remains unresolved.
- owner-message presentation entered this pass failed/open.
- the missing opening word entered this pass under pipeline-versus-recognizer isolation.
- Whisper Small had NOT been replaced.
- LOW remained NOT_ADMITTED.
- owner-facing latency entered this pass failed/open.
- warming entered this pass under scheduling review.
- Avatar remained blocked behind WP3.

**Historical owner evidence, as reconstructed.** Three sessions on the `91693d9` build,
each canonicalising "Good evening, Val." as `evening Val.`; run 3 reproduces his
`17612 ms`. His message was invisible because the desktop never read it before the
answer — the previous repair's trigger could not fire early — not because a read was
held. None of the three sessions was closed. Whether his own "Good" reached Whisper
and what made his wait feel like a minute are **UNRESOLVED** on retained evidence.

**Repaired and automatically verified (source, not yet physically accepted):**

- his committed message is exposed from inside the turn and read at once; the service
  returns it while cognition is held; the thread renders it while the session says
  `thinking`; stale reads cannot remove or duplicate it;
- the audio route no longer holds the event loop;
- opening speech preserved: the pad now precedes the first confident window, as the
  governed setting says — no configuration changed; the unchanged Whisper Small hears
  "Good" on complete input, so **no ASR decision is pending**;
- endpoint diagnostics correct and complete; every spoken turn logs a content-free
  timeline; warm-ups log when they ran;
- real speech preempts a running speech warm-up and waits for it to exit; cognition
  warming targets the turn's own first route;
- abandoned sessions are closed (desktop `keepalive` close first; service reaper at
  120 s);
- the desktop reads the service's `delivery` field.

**Pending physical owner acceptance:** Step B (his words visible while she thinks; one
utterance, one turn; "Good evening, Val." transcribed whole); the physical metric END OF
OWNER SPEECH → FIRST PHYSICAL AUDIBLE VAL SPEECH; everything after Step B in §15's
sequence. **Not done and not begun:** Avatar; any ASR change; LOW.

**Continuation point:** the single owner step named in this pass's return, on the
installed build that contains these repairs — never on an older bundle.

---

## 17. Handoff — Step B retest on `912b44f`, 25 September 2026

**WP3 remains PARTIAL.** Record: `docs/reviews/qualification/runs/2026-09-25-wp3-latency/RESULT.md`
(evidence index §104). §16 stands as written.

**Physical owner evidence, banked for this turn:** the exact transcript `Good evening,
Val.` (the opening word preserved); his message shown before her answer; no phantom
message of his; her short spoken reply arriving with her visible answer; her pace
acceptable. **To preserve:** in this short turn her text and voice arrived together and
did not feel like delayed read-aloud. No permanent text/voice synchronisation policy
has been set.

**Failed / open:** ~10–12 s from his speech to his message (his estimate); ~45–60 s
from his message to her reply (his estimate); speech end to first response overall;
exact physical first-audible latency; Step B performance acceptance.

**What the record shows for that run:** 3.1–4.1 s to his message (read returned) and
12.8–13.8 s from it to her playback start. The session, Voice On to Voice Off, lasted
32.9 s, so the record cannot hold a 45–60 s interval inside it; the difference is
UNRESOLVED and is not rewritten. The response path is dominated by provider workload:
~8 s of prompt processing on every turn with no prefix reuse, 1.6–5.3 s of reasoning,
and ~2.7 s of first-segment speech synthesis, of which ~1.3 s is per-process start-up
and model load. His commit took 1.2 s against 3–50 ms reproduced (UNRESOLVED, now
marked). Text and voice arrived together because both waited on the same boundary, all
segments synthesised; for longer answers that boundary puts her voice ahead of her text.

**Implementation state (source, automated only):** the panel shows the three
owner-facing intervals and posts them to the log; Voice Off follows a turn in flight so
her answer is not stranded; the commit's parts are marked. **No latency repair was
made**, because no software-removable delay larger than a few hundred milliseconds was
found on either critical path.

**Continuation point:** the owner's ruling on the decision boundary in the record
(prefix reuse on the admitted runtime; a resident speech process; model residency; the
text presentation boundary). Avatar remains blocked behind WP3; LOW and Whisper are not
reopened.

---

## 18. Handoff — prompt-prefix reuse pass, 25 September 2026

**WP3 remains PARTIAL.** Record: `docs/reviews/qualification/runs/2026-09-25-prefix-reuse/RESULT.md`
(evidence index §105). §16 and §17 stand as written; `60e4e81` made no latency
optimisation and none is claimed.

**Result: UNSUPPORTED — production unchanged.** On the installed stack (LM Studio
0.4.24+1, MLX engine 1.11.0), no serving setting gives cross-request reuse of VAL's
persona prefix for real turns. Measured with LM Studio's own engine in a separate,
isolated process: requests sharing ~97% of their tokens with an earlier one reused
**none**, in both the production batched mode and sequential mode. The reasons:
- GPT-OSS's sliding-window cache cannot be trimmed back to a shared prefix.
- The engine's checkpoints sit 11 tokens before a prompt's end, never at the persona
  boundary.

No cache control is exposed.

**The one demonstrated route, not taken:** a VAL-issued priming request that places a
checkpoint on the persona boundary, under sequential serving, cut first-token time
from ~6.5 s to ~0.41 s on changed-suffix requests in isolation. It is a new class of
model call and a concurrency change, not a serving setting, so it needs its own ruling.

**Held, unchanged:** resident speech process (~1.3 s per synthesis); longer model
residency; answer-text timing policy. **Open:** Step B performance acceptance; physical
latency under the three-interval panel; C / E / G; conversation switch. Avatar blocked.

---

## 19. Handoff — prefix priming qualified and deployed, 25 September 2026

**WP3 remains PARTIAL.** Record: `docs/reviews/qualification/runs/2026-09-25-priming/RESULT.md`
(evidence index §106). §16–§18 stand as written.

**What changed in production:**
- The local Partner model is loaded with `--parallel 1` (the engine's sequential kit).
- A Voice session sends a **`prefix_prime`** call: the persona plus a short filler,
  placed so the runtime's checkpoint lands exactly on the persona boundary (5,048
  tokens). It is sent when his first utterance settles and after every finished turn,
  and never while any part of his turn is under way.
- The call is recorded in `model_calls` (migration `0031`), attached to no
  conversation, and its one generated token is discarded.
- It is bound to the exact engine it was qualified on (`mlx-llm…@1.11.0`,
  `app-mlx-generate…@34`). Any other engine, or a batched instance, means no prime.

**Qualified through LM Studio on an isolated clone, against current production (12
governing trials each):**

| | production | primed |
|---|---|---|
| request-ready → first model output (median) | 8.02 s | **1.64 s** (ranges do not overlap) |
| speech end → playback (median) | 18.03 s | **13.18 s** |
| speech end → his message | 2.08 s | 2.08 s (unchanged) |

No first-turn regression: a cold cache matches production, and a cold model is
slightly faster. Reuse never crossed a divergence (a one-word persona change reused 0).
The cache stays in memory only.

**Preserved:** exact transcript, opening word, his message before her answer, no
phantom turn, the established voice and pace. The prime touches cognition serving and
nothing on the input or presentation path; those tests pass unchanged.

**Pending physical acceptance:** the smallest Voice retest, read from the three-interval
panel. **Held:** resident speech process (~1.3 s per synthesis); model residency; answer-
text timing. Avatar blocked; LOW NOT_ADMITTED; Whisper unchanged.

---

## 20. Handoff — voice-mode repair: his words, her response, text with speech, 25 September 2026

**WP3 remains PARTIAL.** Record: `docs/reviews/qualification/runs/2026-09-25-voice-repair/RESULT.md`
(evidence index §107). §16–§19 stand as written.

**His physical failure (OBSERVED):** his words took 2.1 s to appear, her voice began
9.0 s and 13.2 s after his words, and her text arrived after she had begun speaking —
2.7–2.9 s after she began (during her second segment) and 6.1–6.2 s after (during her
last), reconstructed from the desktop's own playback reports in `speech_playbacks`.
Cause of the last: the desktop read her answer only when the turn was appended, after
**every** segment had been synthesised — about when she started for a one-segment
reply (his earlier satisfactory run), mid-way or later for two or three segments.

**His presentation ruling, implemented:** her displayed answer progresses with her
speech — each segment's text appears when that segment starts playing, not by a timer
or a speaking rate; the answer is read the moment Core has written it
(`VoiceSessionView.answered`) so it is always ready before her voice; interruption,
failure, a 12 s stall or Voice ending show the rest at once, marked not spoken; text
mode unchanged.

**Also changed:** his settled words appear in the thread as provisional text ~1 s after
he stops, replaced by the canonical message (still 2.0–2.2 s, reported separately;
endpoint and resume grace unchanged). The speech model stays loaded in a resident
worker while Voice is on (same model, voice, pace and code; released when Voice
ends; falls back to one-shot on any failure). Speech offers name their answer so a
finished answer's state cannot land on the next. Desktop tests can no longer reach a
live service.

**Before → after (synthetic, same driver, production model, n=9 each):** first
sentence synthesis median 2.92 → 2.02 s; speech end → first playback median 10.29 →
9.13 s (first turn after Voice On 8.8–10.1 → 6.4–8.9 s); silent gaps 10.6 s → 0.6 s
in total; her text ready before her voice 0/9 → 9/9 turns; text offset up to +17 s →
0 for every segment. Priming retained unchanged. The persona entry is evicted about every five turns (from reading the engine's source: its prompt cache orders by insertion only); the refresh that follows costs ~6.6 s. In a one-token probe, a request arriving during it waited for its first streamed event no longer than with no refresh (6.2 s at 0.5 s in, 0.75 s at 6 s in, against 6.6 s), and closing the client did not shorten the next request's wait — neither establishes that maintenance never worsens a complete spoken turn, nor what the server computed after the client went (wording corrected under the targeted order, §5).

**Remaining dominant cost:** MEDIUM's hidden reasoning before visible text (1.1–6.3 s
in these runs, 9.1 s in his), then first-sentence synthesis under contention with
cognition (up to 4.2 s). **Unverified:** paint and sound in the room.

**Pending physical acceptance:** the smallest Voice retest (below). **Held:** C / E / G,
conversation-switch acceptance, Avatar; LOW NOT_ADMITTED; Whisper unchanged.

---

## 21. Handoff — targeted voice latency order, 25 September 2026

**WP3 remains PARTIAL.** Record: `docs/reviews/qualification/runs/2026-09-25-voice-repair/TARGETED.md`
(evidence index §108). §20's follow-up (physical reconstruction, maintenance probes)
was completion of the **earlier** order; this entry is the targeted order's.

**His successful session** (conversation `01a0db46…`, desktop and service `b6c8937`)
**as measured:** speech end → playback 7.1, 10.8, 7.4 and **12.6 s** (the "about 13
seconds" answer).

The 12.6 s answer:

| part | time |
|---|---|
| confirmation and resume grace | ~1.3 s |
| request overhead | 0.1 s |
| first output | 1.74 s |
| hidden reasoning | 4.57 s |
| **synthesis of a 121-character first sentence spoken whole** | 3.85 s |
| playback | 0.06 s |

There was no maintenance wait in any turn.

**Changed:**

- **First segment:** the first segment alone is now cut at its first natural pause
  once past 60 characters. Probe: 0.9–1.3 s sooner on such openings; it engaged in
  none of the six measured answers, so no end-to-end gain is claimed.
- **Presentation defects fixed:** found when his next turn was committed while she
  was still speaking.
  - Her remaining text was marked "not spoken" while she spoke it.
  - Segments were routed to the wrong answer.
  - Timing figures were paired with the wrong turn.
- **Record gap closed:** a segment voiced before her answer was written now gets its
  hand-off and playback recorded.
- **Self-knowledge correction:** a record-state `spoken_path` block, present only in
  spoken conversations; the persona is unchanged. Three paraphrased checks: none of
  the invented one-second promise, network diagnosis or recording offer recurred. The
  residual is speculative hardware talk on hypothetical questions.

**Probe wording corrected** per the continuation.

**Remaining:**

- Hidden reasoning is model work.
- First output 1.6–2.3 s per turn because history is recomputed. Smallest decision:
  a conversation-level prime, which the priming ruling excluded.
- Turn-taking while she thinks.

**Pending physical acceptance.**

---

## 22. Handoff — final-segment playback excluded from stall detection, 25 September 2026

**WP3 remains PARTIAL.** A focused repair to §21's per-answer presentation. The
defect was reproduced by the owner in software, and again against the committed
implementation before the change.

**Defect.** `complete` means every segment of an answer has *started*. The stall
check skipped terminal answers, so it treated an answer whose final segment was still
sounding as silent. With a queued answer behind it, the queued answer was marked
stalled after `STALL_MS` and its full text shown while the earlier answer was still
playing.

**Repair** (`spokenPresentation.ts`, `voiceController.ts`, `speaker.ts`):

- Playback activity is judged from the segments of every answer, whatever its state,
  and never from reveal state.
- A segment stops counting as playing when:
  - the device reports its end;
  - it is cut off — the player's `onInterrupted`, the delivery's stop (now applied
    even to an answer already complete), a playback failure, or Voice ending;
  - its known audio length plus `END_GRACE_MS` (3 s) has passed without an end
    event, so a lost event cannot hold the fallback off indefinitely. This is
    bounded by the audio's own length, not a longer timeout.
- Cleanup never forgets an answer whose audio is still sounding.

**Tests** (7 new):

- the owner's sequence, then the fallback working once the final segment ends;
- the stop, cut-off, failure and release boundaries each clearing playback;
- a lost end event bounded by duration;
- cleanup retaining a playing answer.

The sequence was confirmed failing on the previous implementation.

**Status, as the owner worded it:**

- Overall response-latency improvement from the first-segment rule is **NOT YET
  DEMONSTRATED**. The isolated synthesis measurements show a potential benefit for
  qualifying openings.
- The self-knowledge correction is **PARTIAL**: the one-second guarantee and the false
  measurement offer did not recur in the reported checks, but unsupported hardware
  and stage claims remain. No further prompt-tuning in this repair.
- The **41-second wait** before his utterance spoken during her thinking was submitted
  is a remaining **turn-taking limitation**. It is separate from the repaired
  presentation bookkeeping, and not resolved because her previous answer was still
  audible.
- Conversation-content priming is **not authorised**; the restriction stands.
  Interruption policy is unchanged.

---

## 23. Handoff — his physical turn of 23:03, 25 September 2026: where the ~15 s went

**WP3 remains PARTIAL.** No code changed in this pass. Presentation and queued-answer
acceptance are **not** inferred from this timing report.

**Identity (OBSERVED):** Voice session `01a0dbe2-4826…`, conversation
`01a0dbe2-17fe…`, 23:03–23:04 CDT.

- **Service:** process 14780, started on `642cb35`'s code; `e866a09` changed only the
  desktop.
- **Desktop:** `e866a09` (DERIVED). The bundle was installed at 22:58:41 (its change
  time) while Val was not running, the deployment check found it the only launchable
  copy, and the session opened at 23:03:28. The report fields independently prove
  `b6c8937` or later. The desktop itself reports no build identity.
- **Runtime:** `openai/gpt-oss-20b`, parallel 1.

**What happened:**

1. He asked for "a detailed summary of what we accomplished with voice today…".
2. About 3.9 s after he finished (`gap_before_s`), while she was still reasoning
   (7.58 s of hidden reasoning), he began "And after that, tell me which remaining
   issue…".
3. His speaking was barge-in: answer 1's delivery was interrupted ("the owner began
   speaking"), and its 848 characters were written but never voiced.
4. His second utterance was queued until answer 1's cognition finished. It was
   submitted 29 ms after answer 1 was persisted.

**The turn he timed** (utterance 2; ms after the recognizer's endpoint unless stated):

| boundary | this turn | successful turn 4 (§21) |
|---|---|---|
| speech end → endpoint (confirming silence) | 0.67 s (DERIVED, `silence_s`) | ~0.66 s |
| endpoint → final transcript | 0.27 s | 0.16 s |
| **waiting behind answer 1's cognition** | **~3.5 s** (submitted 4.84 s after the endpoint against ~1.3 s normal; OBSERVED as submission 29 ms after answer 1 persisted) | none |
| speech end → his message in the DOM | **5,579 ms** (OBSERVED, desktop) | 2,024 ms |
| submitted → dispatch (readiness, preflight; no maintenance wait) | 0.10 s | 0.10 s |
| dispatch → first provider output | **2.67 s** (1,676 tokens beyond the 5,048 cached; the history now held answer 1) | 1.74 s (946) |
| first output → first answer text (hidden reasoning; all earlier chunks non-visible) | 4.05 s | 4.57 s |
| first answer text → first speech-safe segment | 0.34 s (107 characters: "My lord," + blank line + a 97-character sentence; no qualifying pause, so the first-pause rule correctly did not fire) | 0.34 s (121) |
| segment → playable audio (synthesis, while the rest of a 1,113-character answer was still being generated) | **5.30 s** | 3.85 s |
| audio → playback (service clock) | 0.09 s | 0.06 s |
| **speech end → playback** | **18,036 ms** (OBSERVED, desktop) | 12,596 ms |

His "about 15 seconds" is not assumed to share the software's starting point. From his
message appearing to her first sound was 12,457 ms (OBSERVED).

**Where the extra ~5.4 s over the successful turn went:**

- ~3.5 s queued behind a turn whose answer was never going to be spoken;
- ~0.9 s recomputing a longer history;
- ~1.45 s slower first synthesis under heavier contention.

Reasoning was 0.5 s shorter.

**Safe to remove now, within authorisation:** nothing demonstrated.

- The queue wait is turn-taking behaviour.
- The history recompute needs conversation-content priming, which is not authorised.
- The reasoning and the contended first synthesis are model and voice work under the
  kept settings.

**Measurement defect found, not fixed:** the panel's provisional-words figure for this
turn (−4,239 ms) paired utterance 2 with utterance 1's text. The session's `pending`
carries the in-flight turn's text while he is speaking again. The fix is to count
provisional words only when the session is not currently hearing. It is small, but it
was not made in this report-only pass.

**Turn-taking, separately.** When he speaks while she is still thinking, her voice for
that answer is already stopped, yet its cognition runs to completion before his new
words are submitted. Here that cost ~3.5 s, plus contention on what followed; in the
successful session it cost 41 s. Cancelling the unspoken answer's cognition — or
joining his follow-up to the question it continues — would remove that wait. It would
also change what reaches the record (an answer never written, or one merged turn).
That is interruption policy, and his to rule on.

**Conversation-level priming — proposed isolated experiment (not authorised, not
run):**

- **Content:** the persona plus the conversation's retained canonical messages, exactly
  as Core assembles them for the next turn. That is his words and her answers as
  stored, with none of her hidden reasoning, and not the per-turn record-state envelope
  or the new turn. A short filler places the engine's checkpoint exactly at the end of
  the history (the same token-identity plan as the persona prime).
- **Where the state lives:** the LM Studio engine's in-memory prompt cache (the MLX KV
  state in its 10-entry insertion-ordered `LRUPromptCache`), in RAM only. No disk cache
  appeared in the priming pass, and this is to be re-verified.
- **Lifetime and cleanup:** until later entries evict it, the model unloads (1 h idle),
  or LM Studio restarts. It is never written to the store.
- **Isolation:** the APFS clone `val-experiment/gpt-oss-20b` loaded as `val-exp`, a
  scratch service and store, and scripted synthetic conversations only. Production and
  his conversations are untouched, and the clone is removed afterwards.
- **Comparison:** the current persona prime against the conversation prime, on the same
  multi-turn conversations. Measured per turn:
  - request-ready → first output;
  - speech end → first playback;
  - each prime's establishment and refresh time, added into the totals;
  - complete spoken turns arriving during a refresh at 0.5 / 2 / 4 s;
  - Whisper decode time and first synthesis under contention;
  - free memory and swap.
- **Cost:** $0, local; about 45 minutes. Deployment would need its own ruling.
- **The 1.2–1.8 s per later turn is an estimate, not a measurement.**

---

## 24. Handoff — reducing the wait before Val speaks, 26 September 2026

**WP3 remains PARTIAL.** Record: `docs/reviews/qualification/runs/2026-09-26-onset/RESULT.md`
(evidence index §111). This was an execution pass under the owner's order of that
name.

**Cause of the remaining wait** (his 23:03 turn, §23):

- the first sentence voiced whole, under contention with her still-running answer
  (5.30 s);
- the history recomputed before her first output (2.67 s);
- hidden reasoning (4.05 s);
- a queue behind a silenced answer (~3.5 s).

**Contention demonstrated:** voicing a 107–121 character sentence whole took 2.6–3.2 s
alone and 4.3–5.4 s while GPT-OSS was generating, and her generation slowed from 55–61
to 41–44 chunks/s meanwhile.

**Repaired:**

1. **Streamed first audio.** The installed mlx-audio 0.5.5's own incremental path, from
   the resident worker to the desktop's gapless player. First playable audio is ~0.5 s
   after the first segment is ready for short openings and ~0.76 s for long ones, where
   it was 1.1–4.5 s. There were no seams, and no gaps or underruns in 73 joins. Voice,
   conditioning and pace are unchanged.
2. **Resume held while he is still speaking**, implementing the existing rule: his 20:15
   case now gives one message and one answer, not a half-question answered and the
   rest queued.
3. **`spoken_path` facts gated** to turns that ask: 470 tokens and 0.6 s off the first
   output of turns that do not.
4. **The provisional-timing mismatch** — a correctness repair only.

**Net result (n = 9 each):**

| median (range) | before | after |
|---|---|---|
| speech end → first playback | 12.58 s (7.73–17.44) | 8.98 s (7.08–10.96) |
| total less model time | 4.24 s (3.28–7.14) | 2.98 s (2.58–3.26), ranges not overlapping |
| first answer text → first audio | 2.10 s | 0.82 s |

The claimed improvement is the non-model part: 1.26 s at the median, plus 0.6 s before
first output on turns that do not ask. Hidden reasoning varies between answers and is
unchanged.

**Remaining:**

- MEDIUM's hidden reasoning (model work).
- History recompute, 1.6–3.1 s before first output. Removing it needs
  conversation-content priming, not authorised; the experiment is in §23 and its saving
  is an estimate.
- **The queue behind a silenced answer.** When he speaks after the resume grace while
  she is still thinking, her voice stops but that answer's cognition runs to completion
  before his new words go in. The choices, both his:
  - cancel the silenced answer's cognition, so no answer is written and the record
    shows his first question unanswered;
  - or join his new words to the question they follow, so one merged turn is answered
    and the first half's partial cognition is discarded.

  Either removes that wait (~3.5 s at 23:03). The current policy keeps both questions
  and both answers.

**Pending physical acceptance.**

---

## 25. Handoff — the audio regression's cause and repair, and response-in-progress feedback, 26 September 2026

**WP3 remains PARTIAL.** Record: `docs/reviews/qualification/runs/2026-09-26-redesign/AUDIO_REPAIR.md`
(evidence index §112). A production correctness repair under the redesign order's
standing authorisation; nothing of the redesign's experimental routing is in it.

**Cause 1, measured:** the library's streaming decoder began every sentence cold —
no reference context — where the whole decode had the voice already in its buffers.
Same codes by seeding: log-mel distance 0.11–0.50 against 0.0, and a 0.065 RMS burst
in the first 60 ms of a sentence against 0.0015. **Repair:** the streaming decoder is
primed with the reference codes once per reference, its primed state captured, and
restored per segment (sample-identical to fresh priming; ~0.1 ms). First piece stays
at 0.45–0.48 s. **Cause 2, structural:** each piece decoded and scheduled separately on
the desktop, a resampler restart and a scheduling edge per seam. **Repair:** one
playback worklet writes every piece as one continuous signal at the speech's own rate.

**Also:** the voice worker primes at Voice On when the governed voice is known and
spends MLX's one-time compilation on a discarded short generation (readiness 1.1 →
2.3 s, reported; the session's first sentence 1.07 → 0.47 s to first piece). The
session reports the accepted turn's stage — thinking, writing, voicing, speaking — and
whether his next words are queued behind it; the desktop shows it; it makes nothing
faster.

**Not established:** that it sounds clean in the room. Fallback if it does not:
whole-segment synthesis, 1.1–4.5 s to first audio.

## 26. Handoff — the local conversational latency redesign: candidate built, fast route not qualified, 26 September 2026

**WP3 remains PARTIAL. Nothing experimental is deployed.** Record:
`docs/reviews/qualification/runs/2026-09-26-redesign/RESULT.md` (evidence index §113).
Owner order "IMPLEMENT AND QUALIFY THE LOCAL CONVERSATIONAL LATENCY REDESIGN"; the
candidate awaits his review, off behind three unset switches.

**Built, inside Core:** a two-tier deterministic eligibility rule (greeting / thanks /
farewell; narrow pleasantry) that fails toward MEDIUM; `Gateway.converse_lightly` on a
`LIGHT` capability floor no production configuration carries; speculative preparation
of the light answer while the resume window runs, bound to the turn only when the
completed request is the very request prepared for, every outcome on the record
(`speculative_preparations`, migration `0032`); adaptive turn completion from the
transcript's own cues; per-model readiness; the light route primed like the partner
route. Guards: production routes nothing light; the closure contract holds; three
tripwires amended with dated notes.

**The finding:** `Qwen3-4B-Instruct-2507`, given the persona whole and the authoritative
envelope as Core assembles every turn, does not answer the light turn — it copies
persona example lines verbatim or repeats her previous answer (12/12 on the real path;
27 of 49 light answers in the run echo the persona; unchanged under every sampling and
message-structure variant; only the non-deployable envelope-free control answers, and
it invents). **Neither tier is qualified; neither is enabled.**

**Measured anyway (E: tiers 1+2 + speculation + adaptive completion; 20 sessions, 114
turns, real recognition, $0):** 0 substantive false positives on 45 adversarial turns
(every phrase the order names); 20 safe false negatives (10 Whisper hearing "Val" as
"vowel" on the synthetic voice, 10 frozen-rule misses, recorded not tuned); 47/55
preparations bound, 6 discarded on resume, 2 unused, 0 mismatched; all six resumed
pairs joined into one turn; light-route speech end → first playback 6.0–6.1 s median
against ~1–2 s targets, the whole excess being the candidate's 4.6 s median to generate
its answer; substantive 8.8 s median. Voice On → ready 5.9 s. Lowest free memory 16%,
swap +1.0 GB over the run. Offline: loopback only. **Against production routing on
the same 114 phrases (A):** the candidate took 0.76 s (tier 1) and 2.18 s (tier 2) off
the median while tripling the length of what she said; the substantive route did not
regress (ineligible −0.03 s median); swap grew in both conditions with both models
resident (A +4.9 GB, E +1.0 GB), so residency's memory cost has no clean baseline yet.

**Blocked:** the LiveKit turn detector — its Model License §3 excludes standalone use.
**Repaired on the way:** an address-only clause in the router; the preparation wait
(0.6 s → 8 s; a late preparation is now recorded `discarded_unused`).

**His rulings needed:** the fast candidate's future (close, one named larger local
candidate, or a ruling on how the envelope reaches a small model); adaptive
completion's trade; interruption policy (§24); a second resident model at that memory.

---

## 27. Handoff — Tier 1: the existing options compared, GPT-OSS at LOW with a Core-owned request qualified in isolation, 26 September 2026

**WP3 remains PARTIAL. Nothing deployed; production admission is his.** Record:
`docs/reviews/qualification/runs/2026-09-26-redesign/TIER1_COMPARISON.md` (evidence
index §114). Owner order "COMPARE EXISTING TIER-1 OPTIONS, THEN QUALIFY THE BEST
CONFIGURATION". Production verified: service still on `13b3cb8`'s code (process 50184),
live store `0031`, no switches, desktop `13b3cb8`, production Voice unused throughout.

**Coverage (read-only, model-free):** 27 owner-spoken turns, 24–26 September, 20 of
them in diagnostic conversations; tier 1 = 7 (26%), tier 2 = 0, substantive = 20; in
the 7 ordinary-use turns, 4 are tier 1. Three days of voice-mode building, not his
habits. Recorded waits: tier 1 ~10 s, substantive ~12 s median where a timeline exists.

**The Core-owned Tier-1 request** (`val_gateway/tier1.py`): persona whole; the last
exchange; a reduced state block that says what it omits (recall not run, history
beyond the last exchange unseen, no media); Core's contract for the turn (answer the
social utterance directly, one short answer in her manner, persona examples are not
facts or text, invent nothing, no filler); his words. Eligibility read from the full
state before projection: any question or offer in her last answer, any unresolved
action she named, a corrected previous message, or no readable answer → MEDIUM. A
Tier-1 answer is delivered whole after completion; a cap hit or empty answer falls
back to MEDIUM exactly once before a word is shown.

**Four-way comparison (30 cases, every answer read):** A ordinary MEDIUM re-spoke a
whole previous answer to "Thank you"; B MEDIUM + Tier-1 answers well but keeps ~150–400
tokens of hidden reasoning (9 s, no gain); **C LOW + Tier-1: no persona echo, no
repetition, no invention, one wrong-turn recap, ~32 tokens**; D Qwen3-4B + Tier-1 fast
but invents (6/23). **C selected.**

**LOW at the boundary:** the wire carries `reasoning_effort: low`; the runtime renders
`Reasoning: low` before the persona (first differing byte 148; persona bytes identical),
LOW's hidden reasoning is one line; LOW and MEDIUM prefixes **coexist** in the runtime's
cache (69 predictions attributed by `lms log stream`: MEDIUM after LOW = MEDIUM after
MEDIUM, 0.2–1.3 s to first token; the 7 s persona prefill never recurred after each
effort's first prime); every substantive request rendered MEDIUM. Prime plan now keyed
by effort (defect fixed).

**Qualification of C (29 sessions, 114 turns, real recognition, Qwen unloaded, fixed
window, no speculation):** 0 substantive false positives in 80 must-stay-MEDIUM turns;
21/34 tier-1 on the route, 13 safe false negatives (6 recognition, 7 rule/guard);
speech end → first audio **4.80 s median, p90 5.37, max 5.44** on the route (MEDIUM on the
same phrases 8.50 s); owner message visible → first audio 2.70 s (MEDIUM 6.53). 17/21
answers right and in her manner, 2 off-register, **2 wrong-turn answers in
pending-action contexts** ("Talk soon, Val." after "I will record the intent" →
"Understood. I will proceed accordingly.") → an unresolved-action guard added
afterwards, evaluated offline: both routed MEDIUM, coverage 15/34. **The ~1 s target is
not met**: 2.2 s of every turn is the endpoint and the fixed window (held steady), the
route itself ~2.7 s.

**Speculation:** ~0.9 s gain on greetings, but a discarded preparation cannot be
cancelled at the engine and delayed a corrected substantive request by ~1 s on the
shared lane → **left disabled**. **Resources:** no substantive regression (−0.23 s),
no swap growth, memory flat; the one cost is a second cold prime per session (6.5–7 s,
between turns, an arriving utterance waits behind it). Offline: loopback only, and the
service ran under a sandbox denying non-loopback network (record §9).

**Recommendation (his to take):** `VAL_FAST_ROUTE_TIERS=1`, `VAL_TIER1_ROUTE=low`,
speculation and adaptive completion off, migration `0032` applied live; rollback is
removing the two settings. Not an admission of LOW.

---

## 28. Handoff — Milestone A: the narrow Tier-1 release prepared (readiness, prime scheduling, the courtesy decision), 26 September 2026

**WP3 remains PARTIAL. Nothing deployed; production admission is his.** Record:
`docs/reviews/qualification/runs/2026-09-26-redesign/TIER1_RELEASE.md` (evidence index
§115). Milestone B is a separate record (`ORDINARY_TURN.md`, in progress) and is not in
this release.

**The configuration and its limits, unsoftened:** GPT-OSS, one instance; LOW only for
eligible standalone greetings, thanks and farewells through the Core-owned Tier-1
request; MEDIUM for everything else; no Qwen; speculation off; adaptive completion
off; endpoint and window unchanged. The earlier qualification: 21 LOW turns, two
wrong-turn answers in pending-action contexts, the guard added afterwards, ~15 of 34
eligible on replay; its 4.8 s median is not re-claimed for the revised decision. LOW's
scope is enforced by test: the `light` floor only; conversation, blind position and
structured routing unchanged; the registry on disk untouched.

**Readiness (§2):** "Ready" meant session + microphone. The session now reports
cognition, voice, Partner prefix and light prefix component by component; the prefixes
are primed at Voice On (standing aside, marked `skipped`, if he is already speaking);
the desktop says "Warming up…", "Val is warming up — your words are heard…", or
"Voice is degraded: …". Measured: Voice On → Ready **6.7 s warm**, **26.4 s cold**
(model load ≈ 10 s inside a 12.4 s warm-up, then 13.9 s of cold primes); first greeting
after Ready 4.4 s warm / 5.2 s cold; a greeting spoken 1 s after Voice On on a cold
start **15.2 s**. Prewarming moves the cold work before "Ready"; it does not remove it.
**Why checkpoints go cold:** not time (warm after 90 s idle), not session lifecycle;
distinct prompts entering a runtime cache that holds two or three entries — one
unrelated ~120-token prompt evicted a checkpoint.

**Prime scheduling (§3):** a refresh is owed by a turn and dispatched only after 1 s of
idleness (speech being heard now counts), rechecked at dispatch and before each call,
coalesced by a use generation, dropped after 60 s. **Selective refresh was measured and
rejected** — priming only the other effort left MEDIUM's next first token at 8 s (from
1.7 s); both entries are primed, light first and Partner last. Residual collision
under the final policy: his next words 0.3 s after her answer waited **≤ 0.8 s** on 2 of
12 turns, none with 2 s between turns; MEDIUM first token back at ~1.7 s; a cold prime
(~7 s) still runs after about every second turn — the recurring cost of two warm
prefixes on this runtime, stated.

**Courtesy against pending work (§4):** a Core-owned decision replaces the phrase
list — his previous message asked for an action or decision → MEDIUM whatever she said
about it (claims of completion are uncertain state); her answer asks or offers
something in particular → MEDIUM, generic courtesy closings excepted and never
overriding an open matter. Fresh set (20 courtesy / 22 pending), written before
implementation: first evaluation 1 inappropriate light (p14), tightened, then 0/22;
known failures 0/2; development 0/10. **Generated answers** in the newly permitted
contexts: LOW answered a bare thanks after a greeting-only exchange as a greeting
(3/7, then 1/6 after the request stopped carrying a light previous exchange) → **that
class is withheld**; farewells after a greeting and thanks after a settled substantive
answer are released. Final fresh coverage 7/20, 0 inappropriate. Historical coverage
recomputed read-only: unchanged, 7 of 27 turns.

**Release (§6):** `VAL_FAST_ROUTE_TIERS=1`, `VAL_TIER1_ROUTE=low`, nothing else;
migration **`0032_light_conversation` explicitly**, not `head`; rollback removes the
two settings and restores routing, not the recorded evidence nor the schema. Offline:
loopback-only by sampling; the runtime itself was not network-denied (he was active;
the two-minute step is his to authorise). Memory: free ≥ 40%, swap flat, the second
prefix's cost visible as cold primes. Physical acceptance test in §6.

---

## 29. Handoff — Milestone B: ordinary-turn waiting and wrong-turn responses, investigated; owner precedence implemented in isolation, 26 September 2026

**WP3 remains PARTIAL. Nothing deployed; nothing of this is in the Tier-1 release.**
Record: `docs/reviews/qualification/runs/2026-09-26-redesign/ORDINARY_TURN.md`
(evidence index §116). Every switch this milestone added is off in production:
`loop.TURN_KIND_FACT`, `context.COMPACT_NOTES` (module switches, never set by
configuration) and `VAL_OWNER_PRECEDENCE`.

**§6 wrong-turn repetition:** the recorded re-answers were **model-generated**, not a
delivery or association defect (own call rows; similarity 0.83/0.86 to the previous
answer, not copies). A deterministic `current_turn` fact in the envelope settled one of
two reproduced cases and paraphrased an exact "say that again" — **not adopted**. Both
conditions exposed the likelier cause: asked to "recap that", MEDIUM recapped the
**record-state envelope**, because his words are joined to it in one user message on the
wire. Repairing that touches the 10 and 17 September constructions — **a ruling, put to
him, not made**. The fabricated-completion class was not improved by any shape.

**§7 preparation during confirmation:** Core's own work between his settled words and
dispatch is ~80 ms; the 2.2 s is the endpoint (0.95 s) and the window (1.1 s), both held.
The runtime has **no generation-free prefill** (`max_tokens: 0` refused); a
conversation-prefix prefill is a one-token request, cost **6.6–6.8 s each**, bought
0.1–0.3 s on the next turn, and **evicted a persona checkpoint two times in three** —
a net cost until the runtime can hold a third cache entry (the reserved memory ruling).

**§8 owner precedence:** engine-level cancellation observed — closing the stream releases
**generation** (0.20 s to the next request) but **not prefill** (10.1 s). Implemented,
isolated, behind `VAL_OWNER_PRECEDENCE=on`: a `cancelled` predicate through the
provider contract (`GatewayErrorKind.SUPERSEDED`, LM Studio adapter closes the stream;
other adapters accept and state they do not act); a confirmed new turn supersedes an
answer he has not begun to hear, recorded as `error`/`failed` with NULL tokens, his
message kept unanswered, no message fabricated; speech resumed within the grace still
merges; an answer he has begun to hear is never cut off. Tests 3. End-to-end voice-path
timing under the switch not yet measured.

**§9 ordinary MEDIUM costs:** hidden reasoning **4.1 s median / 7.2 s p90 = 51% of the
wait**; prompt processing 1.7 s (1.1 s tail); TTS 0.6 s. The one fact-preserving request
change (compact notes) saved ~150 tokens ≈ 0.2 s and, in the same run, went with two
worse honesty outcomes — **not adopted**. The measured limit is stated with the three
trades a further change would require, none made.

---
## 30. Handoff — the Tier-1 release gaps closed (Milestone A return under the release-gaps order), 26 September 2026

**WP3 remains PARTIAL. Nothing deployed; production admission is his.** Record:
`docs/reviews/qualification/runs/2026-09-26-redesign/TIER1_RELEASE.md` §8 (evidence index
§117). **Release identity:** branch `release/tier1-low-2026-09-26`, tag
`tier1-low-release-2026-09-26` — cut from `3fbebf5` (Milestone A) and carrying only the
gap closures; **Milestone B (`d03dc74`) is not in it.** The tag's commit and CI result:
this section's closing line. Desktop: built from that tree, staged at
`~/Val previous builds.noindex/Val (release tier1-low 2026-09-26, staged, not installed).app`,
digest `fa994941…231d`, not installed; the installed desktop is still the `13b3cb8` build.

**What closed:** (§6A) the physical test now expects the routes the final decision
takes — a farewell after a greeting exchange on the light route, a bare thanks after one
withheld; (§6B) the desktop build is part of the release, with an exact identity; (§6C)
the release is the tag, not a master checkout; (§6D) the pending-work decision reads up
to three earlier exchanges, walking back until a message of his that is itself work,
because a social exchange settles nothing — a second fresh set (`courtesy_pending_window.json`,
12 + 10) evaluated once: 12/12 pending on MEDIUM, 9/10 courtesy on the route, r10 the
known "list" imprecision; historical coverage unchanged (7/27). **The real desktop was
driven** (unmodified frontend, dev server, headless Brave with a WAV microphone, DevTools
protocol): eight turns in two runs, every route as predicted, every hand-off reported
played by the frontend, light-route first audio **4.1 s** at the desktop boundary after
Ready (Voice On → Ready 7.9 s warm), and the speech-during-warming case observed at
that boundary (11.0 s, a request waiting behind a cold prime that began 1.0 s after his
undetected speech onset). **Two defects found and repaired:** (1) the recognizer's
"Vowel" for the driver's "Val" kept a greeting pair in the Tier-1 request and LOW
answered a farewell with a greeting — the omission now reads her answer's shape too
(`answer_is_courtesy`), verified 5/5 right on the real path; (2) the refresh's idle
clock ran from synthesis end while the player still spoke — handed-over audio now counts
as owner work for its duration (`speech_handed_over`, `test_prime_waits_for_playback`).
**§7 reconciled from timestamps:** no refresh ever started after speech began (dispatch
1.03–1.05 s after turn completion, 2.7–19.6 s before his onset); the report's sentence
was wrong, the idle definition was the defect. A turn reaching cognition before
readiness now shows "warming" whether or not its delivery exists. **Offline:** boundary
unchanged and stated; `offline_check.sh` prepared, not run. **Recommendation:** deploy on
his decision per §6; remaining: his physical test and the coordinated offline check.

**Closing line (the identities a record cannot carry for itself):** the tag
`tier1-low-release-2026-09-26` is commit `2dedda8` on `release/tier1-low-2026-09-26`; CI on that
push (run 36292787225) **success**; the merge into `master` is `e42f8e1`, CI run 36292828528
**success**. Nothing deployed.

## 31. Handoff — Milestone B corrected: owner precedence by his words, the request-construction experiment, the cache mechanism established, 27 September 2026

**WP3 remains PARTIAL. Nothing deployed; `VAL_OWNER_PRECEDENCE` unset in production; the
experiment switches (`context.ENVELOPE_IN_SYSTEM`, `loop.TURN_KIND_FACT`,
`context.COMPACT_NOTES`) are off in source.** Record: `ORDINARY_TURN.md` §10–§12
(evidence index §118). Production still runs `13b3cb8`'s code; the Tier-1 release of §30
is unchanged and separate.

**Precedence, corrected (§1–§3).** The decision is his words' (`val_policy.precedence`,
deterministic): a stop or a clear replacement supersedes an answer he has not begun to
hear; a continuation or anything ambiguous leaves it in force and both are answered in
order — "And after that, tell me about the orchard." is the continuation regression case.
"Heard" is the desktop's playback report, not synthesis and not the hand-off; his onset
against an unheard answer **holds** its hand-off instead of stopping it (barge-in
unchanged once playback has begun), and the decision at confirmation discards or releases
it. A stop asks for nothing (`OWNER_STOP`, no cognition call; the desktop says "Stopped at
your word — nothing was said."). The superseded call's reason is on its measurement row,
usage NULL; late tokens attach to nothing; late playback reports are refused. The LM
Studio adapter closes a superseded stream from a watcher at once; the session no longer
waits for that thread (a runtime that stops on disconnect but keeps the socket open left
it blocked — P4c). **Measured on the real service** (software player) and **through the
real desktop**: where the runtime is generating, decision → stream closed **15–21 ms**,
replacement dispatched within **50 ms**; the wait to the replacement's first audio is its
own MEDIUM turn (10–14 s here). Where the runtime is **prefilling**, nothing the client
does stops it (the engine's own words); the remaining delay is the prefill, measured in
§10.1 (P4d). The text-begun-but-unplayed window (0.3–0.9 s) is shorter than onset
detection and is proved by unit test, not reproduced live. Tests: `test_owner_precedence`
(10), `test_precedence` (35), desktop +3.

**Request construction (§4).** The wire, inspected: the envelope and his words render as
one last user block that begins with ~3.6 KB of JSON and ends with his words, and two
application-level user messages are joined again by the ingress. Behind
`context.ENVELOPE_IN_SYSTEM` the envelope follows the persona inside the developer block
(recall excerpts stay in the user role) and the last user block is his words alone. On
nineteen matched contexts, both constructions primed and read: **8/19 wrong-turn or false
answers as the request stands (the envelope recapped as his, closings re-answered,
"the state you supplied", a claimed draft, "no audio input"), 0/19 with the envelope in
the developer block** (one off-register opener; "say that again" paraphrased in both; one
run of the candidate made an unsupported speed claim). **Timing:** the first two
forms of the candidate lost the persona checkpoint (first visible text 10.3–10.6 s against
5.4 s) because the engine's checkpoint is sized to land after the user-message header,
which a turn whose developer block continues never renders; with the prime's target moved
to the end of the developer content (`boundary="developer_end"`, under the switch) every
turn reused **5,089** tokens and first visible text fell to **4.0 s** against 5.4 s, with
half the reasoning tokens. **A
ruling, not an implementation:** it touches the 10 and 17 September rulings and the
prime's boundary.

**Cache and prefill (§5).** The mechanism is established from the installed source and
the engine's own log: `LRUPromptCache(max_size=10)`, two insertions per distinct request,
no renewal on a hit, identical requests replace, eviction alternating between the two
queues; GPT-OSS's cache is not trimmable, so reuse needs an entry that is exactly a
prefix. A persona checkpoint lives about four or five distinct requests however often it
is used. **The memory-limit suggestion is withdrawn**; the option is an engine patch
(`history_capacity`, or renewal on hit), ~120–155 MB per additional entry (computed, not
measured). The prefix-prefill conclusion is narrowed to the method tested; the
checkpoint-aligned conversation prime is the open ruling and was not run.

## 32. Handoff — the corrections of 27 September 2026: Milestone A's guard and classes; Milestone B's classifier, cleanup and controlled construction comparison

**WP3 remains PARTIAL. Nothing deployed.** Two independent decisions are returned.

**Milestone A — the corrected release.** Branch `release/tier1-low-2026-09-26`, tag
**`tier1-low-release-2026-09-27`** = commit `e5963d4` (CI run 36301002855 success),
merged into master as `beee2cb` (CI 36301090519 success). Desktop: the staged build
`fa994941…231d` (desktop source unchanged on the branch since it was built). Record:
`TIER1_RELEASE.md` §8.9. The pending-work decision walks back over social exchanges
**without a bound**; withdrawal is the authoritative settlement and nothing else is
(not her claim, not elapsed conversation, not social exchanges); a work message of his
ends the walk because his courtesy answers that exchange, and the reason names the older
requests that remain on the record. A farewell after a greeting-only exchange is
withheld from LOW alongside a bare thanks (the final-build check drew a greeting for it,
8 right in 9 since the repair); released to LOW: a greeting into an empty or settled
context, thanks or a farewell after a settled substantive exchange. Maintenance
occupancy is an estimate with actual playback state preferred within a 3 s bound; the
final-build check shows the refresh dispatched 23 s after a MEDIUM turn, once her answer
had been played. Final-build figures: a correctly recognised greeting **4.47 s** to
desktop playback; a correctly answered farewell after a substantive exchange 7.89 s, 3.1 s
of it behind a cold refresh prime; "Good evening, Val." heard as "Vowel" once (the
driver's voice). Migration `alembic -x deploy=live upgrade 0032_light_conversation`;
settings `VAL_FAST_ROUTE_TIERS=1`, `VAL_TIER1_ROUTE=low`; then the paired desktop; rollback
removes the settings only. `offline_check.sh` rewritten for every network service; not
run.

**Milestone B — two recommendations, separately.** Record: `ORDINARY_TURN.md` §13–§18
(evidence index §119). (1) The **supersession classifier** is clause-based and
conservative (`val_policy/precedence.py`, 60 cases; the five reproduced false
cancellations and fifteen neighbours keep the request; a leading "and" never overrides
an explicit stop). (2) The **cancellation lifecycle**: the adapter shuts the superseded
stream's socket down before closing it — reader released in 10 ms against the 600 s the
close alone left it blocked (`socket-shutdown-probe.json`); each superseded call gets one
prompt record; repeated replacements accumulate nothing; the runtime's slot is released
only when its prefill ends (5.6 s in the probe). (3) The **construction comparison on
frozen histories** (`construction-frozen.json`, 19 paired calls, alternating, primed):
9/19 wrong-turn answers as the request stands, 0/19 with the envelope in the developer
block; first visible text 4.96 → 3.98 s; the planted "SYSTEM OVERRIDE" inside the envelope
ignored by both; the prime verified to carry only persona and separator; the light route's
prime kept at the persona boundary after a 7.9 s cold-prefill regression on LOW was found
and repaired. (4) Through the desktop, one run each: light turns equal (4.2–4.5 s to
playback); MEDIUM turns dominated by reasoning variance, the candidate's single run
slower; **no audible-response improvement is claimed**. Recommendations: the request
construction as a candidate for his ruling; owner precedence as ready to enable behind its
switch. One does not admit the other. Engine-cache patch and conversation-content priming
deferred, as ordered.

## 33. Handoff — the remaining latency work (owner order of 27 September 2026, "complete the remaining latency work")

**WP3 remains PARTIAL. Nothing deployed; production unchanged; every candidate switch
unset in production; no physical test requested.** Record:
`qualification/runs/2026-09-26-redesign/LATENCY_CANDIDATE.md` (evidence index §120).
Outcome **B**: a substantial median improvement demonstrated through the real desktop
frontend and player against the isolated service; the upper tail unchanged and owned by
the engine's cache; one authorisation needed before the cache work can be measured.

**Measured (speech end → first audio the real playback worklet started; baseline three
runs, candidate as built three, final configuration two; eighteen turns each):** social
turns **8.98 → 3.25 s** median (3.17 s final; greetings and thanks on LOW ~3.0 s);
ordinary turns **9.66 → 6.96 s** (7.65 s final). On the turns the engine's cache did not
intervene in: social ~7.5 → ~3.1 s, ordinary ~9.3 → ~6.1–6.7 s, ordinary p90 ~12.3 →
~8.8–9.6 s. A turn that prefilled cold or waited behind a cold prime cost 11–24 s in every
condition (baseline 11 of 46 turns, final 8 of 33), so **the upper tail is not improved**.
Corrections preserved every time; a request with a pause inside it answered whole;
replacements superseded unheard; no underrun; no substantive turn on LOW.

**Done in this order:** the adaptive endpoint (400 ms silence; the resume window sized from
the words, never punctuation alone, ambiguous waits as long as today, unfinished waits
longer; resumption after an early submission cancels and withdraws the early turn and
joins the halves); "heard" scoped to the answer in flight; a speech-length bound through a
wrapper around the unchanged runner (a segment played 327.7 s — 4,096 codec tokens at 12.5
per second, the library's default — and production has the same exposure); **an owed
refresh prime is no longer dropped after 60 s** (an answer of two minutes left the persona
prefix evicted and his next turn cold, 12.3 s; repaired, 4.58 s; ungated, master only);
**courtesy after a self-corrected request stays on MEDIUM** ("Thanks." after "…No, a famous
ghost story." re-answered on LOW in 2 of 5 runs and drew a greeting in 1; the guard could
not see "No," and its "wait," never matched). The last two are findings against the
released tag `tier1-low-release-2026-09-27` as well. Switches: `VAL_FAST_ROUTE_TIERS=1
VAL_TIER1_ROUTE=low VAL_ADAPTIVE_ENDPOINT=on VAL_REQUEST_CONSTRUCTION=envelope_in_system
VAL_OWNER_PRECEDENCE=on VAL_TTS_LENGTH_BOUND=on`, migration `0032` for the light route;
rollback removes them.

**Blocked on his authorisation — the cache correction.** The engine's prompt store renews
nothing on a hit, so Val's persona checkpoints are evicted every few turns (a replay on
the engine's own cache class: 8 cold primes in sixteen turns as shipped, 0 with recency
renewed on a hit). The fix is written (`infrastructure/lmstudio/cache_renewal/`),
digest-pinned, allowlisted to an experiment copy of the model and reversible. Installing
it puts a hook into LM Studio's shared engine directory, imported by every instance
including production's (inert there); cloning the model and loading a ~12 GB experiment
instance beside production's is also needed. These were refused by the session's
permission classifier and not attempted otherwise. Its effect is NOT MEASURED.

**The architectural finding.** In an ordinary turn now, MEDIUM's hidden reasoning (~2.6 s)
and the prefill of envelope, history and his words (~2.0 s) are two-thirds of the wait;
nothing authorised reduces them further. The ~1 s target is not reachable while an answer
is generated after he stops speaking (the fastest class, a greeting on LOW, is ~3.0 s).
Alternatives, each his decision: LOW for ordinary turns (≈25% sooner, one
correction-preservation loss on the frozen checks), a different model (none qualified),
or no change.

**Found and not repaired (outside the order):** two held playback reports for one segment
can compute the same event number and one is refused with HTTP 500, losing a record of
what the speakers did (both conditions; 15 of 146 turns' first-audio rows one segment late;
a retry of the refused insert would fix it).

**Open problems reviewed (procedural rule):** OP-1 names message retraction as a
checkpoint, and the adaptive endpoint withdraws an early fragment through that machinery.
The withdrawal makes no claim: the early turn's answer is cancelled before it is handed
over, so no answer of hers to a fragment is persisted or played (`test_adaptive_endpoint.py`;
in the last run's scratch store, rebuilt per run, no withdrawn message of his is followed by
an answer of hers). The durable live-voice seal is applied when the fragment first becomes
canonical, as before, so the joined message is written into a conversation already sealed. OP-6 (greeting
length) is not touched: the envelope's note text is unchanged. No other checkpoint names
this work.

## 34. Handoff — the live cache experiment and the integrated candidate (owner order of 27 September 2026, "Continue the latency work")

**WP3 remains PARTIAL. Nothing deployed; production unchanged; no physical test
requested.** Record: `qualification/runs/2026-09-27-cache/CACHE_EXPERIMENT.md` (evidence
index §121). Candidate code frozen at `175c380`.

**The cache correction, live.** All four authorised steps were submitted and approved
(clone, allowlist, digest-pinned hook, experiment instance `val-exp-gpt-oss-20b`); a
separate experimental engine is not supported by LM Studio (one engine per model format).
With renewal on a hit, across two alternating runs each: **none of the 62 counted turns
prefilled cold or waited behind maintenance** (78 of 80 including S5 carried an
identity-attributed engine line, none cold; *corrected 28 September 2026 — this said "no
turn of 124", the same 62 counted twice*) (off: 17 of 47 MEDIUM turns cold, 16 waits over 1 s, 32
cold primes); the only cold primes are the two after each reload (initial loading).
Every reused prefix was exactly its route's persona boundary; every call named the
experiment instance; effort on the wire as intended; production's instance declined by
the hook. **Integrated candidate against the same afternoon's baseline** (same frozen
code, switches off, engine as shipped): social **4.77 s** median (p90 6.68, worst 8.15)
against 7.29 (11.04, 15.31); ordinary **6.64 s** (9.27, 12.21) against 9.57 (13.96, 19.84).
Time of day matters: LOW's hidden reasoning ran 73–259 tokens this afternoon against ~32
at night.

**Also done:** the merge window holds an early answer's audio until it closes (28 paused
utterances, no sound of hers during any; corrections kept; the edge at a measured 1.37 s
gap splits a 1.6 s pause either way); playback reports serialised and idempotent (tests
fail on the old writer); the speech bound's failure path (a runaway ends as a named
failure, "segment N began and did not complete"; forced at 2 s on the real voice; one
live runaway in the runs stopped at its bound); identity attribution in the harness.

**Blocked on him — production across restarts.** A pinned release directory
`~/Projects/val-releases/13b3cb8` is built and verified, but repointing the launchd job
was refused by the automatic review ("[Production Deploy]"); the step-by-step procedure
with verification and rollback is in the record, §2. Until then a restart of production
loads the working tree (master).

**The remaining decision.** In a warm ordinary turn now: MEDIUM's hidden reasoning
~2.2 s, prefill ~2.0 s (Core's state block ~1.1 s every turn; history ~1.33 ms per token,
seconds for a quarter of his real turns), confirmation ~0.8 s, speech ~1.0 s. On this
runtime no request ordering can reuse history (one checkpoint per request, 11 tokens from
its end; untrimmable caches; the template hoists every system message to the top), so
the §8 variant was stopped. **Recommended experiment (needs his authorisation):** a hook
checkpoint at the point where a request diverges from what the store holds, with the
stable state kept in the developer block and only the per-turn counts and minute after
his words — expected to remove the state block's ~1.1 s and most history prefill.

**Found and recorded (not repaired):** barge-in does not stop an answer whose synthesis
has finished (production and both releases); the spoken-path gate fires on "pacing".
Post-tag defects of `tier1-low-release-2026-09-27` are recorded in `TIER1_RELEASE.md`
§8.10. **Open problems reviewed:** OP-1 (retraction) — the merge window's withdrawals
make no claim (no answer to a withdrawn fragment was played in 28 cases); no other
checkpoint names this work.

## 35. Handoff — the checkpoint and layout experiment and the Voice repairs (owner order of 28 September 2026, "Retain the demonstrated cache-renewal improvement…")

**WP3 remains PARTIAL. Nothing deployed; production unchanged by this work; no physical
test requested.** Record: `qualification/runs/2026-09-28-checkpoint/CHECKPOINT_EXPERIMENT.md`
(evidence index §122). Branch `latency-2026-09-28` (candidate `a5d9680` + hook v2.3 in the
records commit); not merged into master (below).

**First: production runs master since the 00:10 reboot** (`6bad617`, pid 958 from 00:21;
live store `0031`): no candidate switch is set, but master's ungated repairs are live
without a deployment decision. Isolation remains his (step 1 re-verified; steps 2–4 his).

**Correction:** "no turn of 124" (27 September) was the same 62 counted turns twice; 78 of
80 turns including S5 carried an engine line, none cold. Corrected in place, marked.

**The checkpoint (authorised, isolated).** Hook v2.3 on the experiment instance only: the
engine's own one checkpoint per request is placed where the request diverges from what the
store holds (engine-captured, complete, never truncated, re-keyed or associated with a
shorter prefix), only with ≥ 128 tokens gained and ≥ 64 before the end; a renewed
exact-hit key queued as a copy (an aliasing defect since v1, reproduced, closed); every
stored prefix of the entry used renewed with it, shortest last (the persona checkpoints
had aged out — found in the integrated run). **Correctness gate passed:** 0 invalid hits
in 117 staged requests; logits over every post-boundary position within the no-cache
noise floor (mean KL 0.023–0.067 against 0.025–0.080) with a wrong-prefix control plainly
visible (0.18–1.18); greedy text is not a valid test here and was not used as one.
**Net benefit:** 25% fewer uncached tokens staged; 44% fewer in the integrated runs.
**Split record-state layout** (`VAL_REQUEST_CONSTRUCTION=split_state`): per-turn fields
after his words, steady fields after the persona, every value current.

**Also:** the Voice-facts gate no longer fires on pacing a scene (follow-ups kept); the
time-of-day hypothesis is not supported (142 vs 154 reasoning tokens; the clock is used,
not stumbled over) and the clock was kept; **barge-in after synthesis repaired** — the
desktop stops at once and the record follows the desktop's own report of the segment it
cut (a first version recorded from the estimate and, with reports delayed, marked an
answer heard whole as cut; repaired), 323–425 ms to silence; **combined continuations**
behind `VAL_COMBINE_CONTINUATIONS` — the window-end continuation 67.6 / 129.7 s → 4.2 / 7.0 s.

**Integrated (real desktop and player; prior P1a/P1b against final C2b/C2c):** social
4.77 → **4.45 s** median (p90 6.27 → 5.92); **ordinary 6.19 → 6.38 s median — not
improved** (p90 9.76 → 8.53, worst 10.14 → 11.19); replacement 8.85 → 5.79 s median.
Critical path of an ordinary turn now (mean): endpoint 0.47 s, confirmation 0.26, Core
0.06, prefill 1.52 (was 1.94), **hidden reasoning 3.36 (51%)**, first segment 0.20,
synthesis 0.72, playback 0.05; no maintenance queue; the merge hold never bound.

**OPEN — the stalled turn:** in C1a one superseded early turn's thread never returned;
his joined words waited 243 s. 1 of 63 resumes; not reproduced; stack instrumentation in
place. The adaptive endpoint's resume path is not fit for admission until it is found.

**Not merged, deliberately:** the barge-in repair and the gate are not behind switches,
and production launches from the main checkout's master, so a merge would reach
production at its next restart. **Next:** correctness first — find and bound the stall;
then two rulings of his: a conversation-level prime after each answer (≈ −0.7 to −0.9 s,
conversation content in an idle prime) and reasoning effort for ordinary turns (the only
lever on the 3 s). **Open problems reviewed:** OP-1 — combined continuations keep both
messages canonical and write no revision; nothing else names this work.


## 36. Handoff — the interrupted-turn lifecycle repair (owner order of 28 September 2026, "…one focused repair pass")

**WP3 remains PARTIAL. Nothing deployed; no physical test requested.** Record:
`qualification/runs/2026-09-28-checkpoint/LIFECYCLE_REPAIR.md` (evidence index §123).
Code `af136fe` on branch `latency-2026-09-28` (not merged); hook v2.3 unchanged.

**Production isolation:** compatibility with the live store (`0031`), the configuration
and the installed desktop (`13b3cb8` build) verified. The owner's walkthrough has begun;
step 1 is awaiting his confirmation. **Not in force.**

**The ten driver waits over 240 s were not long answers.** Eight of the nine counted,
plus C1a S3 and R1 S5, followed a replacement or combined answer whose hand-off a late
superseded worker had taken (`_record` moved another turn's delivery); the ninth (C2c
S5) followed a runaway segment whose stop never reached the player for the same reason.
Cause established; **repaired**.

**A second hand-off defect, found through the desktop in L2 and repaired:** a finished,
unheard answer kept by his continuation was dropped when the next turn began; it is now
carried and played before the new answer.

**The C1a stall: contained, cause not established.**

- **Containment:** a 1.0 s recovery deadline, after which the session joins his words
  itself.
- **Stale work refused at every action:** no persisting, no answer after the lock, no
  dispatch, no playback, no join.
- **Accounting:** abandoned workers counted, with fail-closed at three.
- **Evidence for next time:** the stack and lock waits are captured at abandonment.
- **Recovery 1.20–1.24 s** in fault injection; each guard's test fails without it.
- **Exposure:** not reachable in the running master (switches unset) or the release
  (`13b3cb8` has no supersession).

**Through the real desktop (L3):** 20 turns, 0 timeouts; the kept answer heard;
barge-in 320 and 324 ms. L1 was invalidated by my own tests sharing its database
(recorded); L2's first pass was lost to a file-name collision (recorded, fixed).

**Latency, precise:** the cache saving stands and is not a conversational-speed solution;
the reasoning difference between layouts is not established (proposed experiment,
$0); the ~2.2 s audio-release floor overlaps processing and never bound an ordinary turn.
**Next:** the reasoning-under-layout experiment, then a shorter first voice piece (within
authority); effort and priming remain his rulings.

**Open problems reviewed:** OP-1 — combined continuations and the abandoned-worker join
keep his messages canonical; a recorded fragment is withdrawn by the existing append-only
retraction, never revised.

## 37. Handoff — production isolation completed; the lifecycle questions closed; the layout question settled (owner order of 28 September 2026, "Continue with production isolation and one bounded request-layout comparison")

**WP3 remains PARTIAL. Nothing experimental deployed; no physical test requested.**
Record: `LIFECYCLE_REPAIR.md` §0, §8–§10 (evidence index §124). Code `a92bdbf` on branch
`latency-2026-09-28` (lifecycle code `f882653`); hook v2.3 unchanged.

**Production isolation: complete (20:34).**

- **Performed by him, verified step by step:** backup, repoint, reload.
- **Running now:** launchd runs `13b3cb8` from `~/Projects/val-releases/13b3cb8`; code,
  working directory and open files are all in the release; live store `0031`; desktop
  `13b3cb8`, matched. A restart loads the release.
- **Corrected:** my Step 2 command, and the 27 September procedure's, inserted rather
  than replaced (caught before reload).
- **Backup jobs deferred** on the stated condition.

**Lifecycle questions:**

- **The "final piece" was the zero-length completion marker**, with every audio piece
  delivered in the two checkable C2c answers; elsewhere it cannot be determined.
- **The stall** is contained, with its root cause unresolved; the adapter layer is not
  excluded.
- **The abandoned-worker limit was per session:** a defect, repaired (service-wide, and
  Voice refuses to start while over it; test).
- **Fault-injection recovery is kept apart from answer onset.**

**Layout:** split record state rejected on a controlled, paired comparison (+1.9 s to
first text; an instruction-boundary and an honesty failure); the candidate is
`envelope_in_system` + divergence. The desktop run (E1) did **not** demonstrate faster
onset (7.91 s median, one run; reasoning tokens equal to the split runs'): inconclusive,
stopped.

**No measured improvement in actual ordinary onset this pass.**

**Next:** Option A (what MEDIUM deliberates about; within authority, $0) or Option B
(LOW for a defined class; his ruling, bounded proposal in the record).

## 38. Handoff — the bounded LOW-effort experiment (owner order of 28 September 2026, "Authorize a bounded reasoning-effort experiment")

**WP3 remains PARTIAL. Nothing deployed; production unchanged; no physical test
requested.** Record: `qualification/runs/2026-09-28-checkpoint/EFFORT_EXPERIMENT.md`,
pre-registered in `602aaea` before any code or call (evidence index §125). Machinery
`330d55f`: `val_policy.ordinary_effort`, `registry.PIN_ONLY`, `VAL_ORDINARY_LOW` (unset in
production), Core's per-turn pin with a counted fallback, 49 tests.

**Outcome: failed at screening under its registered terms.**

- **Reasoning:** LOW cut hidden reasoning from ~3.5 s to ~0.3 s (13.5 against 222.5
  tokens, median).
- **Onset:** with only the existing primes, LOW's prompt prefix (it begins "Reasoning:
  low") was cold every time: ~7.7 s to the first chunk against MEDIUM's ~1.6 s. Onset was
  slower by +1.70 s (F) and +1.44 s (C), against the required −1.5 s.
- **Quality:** class F also failed. LOW refused "What is the capital of Portugal?" once,
  and misstated sonnet rhyme schemes. Class C held up in 6 answers.
- **Regression:** LOW invented a review of a nonexistent second act, confirming the
  exclusion of missing-information contexts.
- **Routing:** 0 of 23 traps routed LOW.

**Found on the way, affecting earlier records:** the renewal clone has no LM Studio hub
definition, so it ignored `reasoning_effort` (rendering "Reasoning: medium") and used
generic sampling. The Tier-1 "LOW" route on the clone (27–28 September runs) actually ran
at MEDIUM. Corrections are appended to the cache, checkpoint and lifecycle records. The
26 September Tier-1 LOW qualification (real instance) stands.

**Next option (his authorization):** LOW for class C with its own primed prefix. Estimated,
not measured: class-C audible onset ~3.5–4 s against ~6.4 s. It needs a LOW ordinary prefix
prime, plus a hub definition for the clone or a real-key instance. If that fails, the next
step is a different local inference path, which needs new qualification.
## 39. Handoff — the corrected LOW configuration experiment (owner order of 28 September 2026, late night, "Resolve those directly before concluding that LOW cannot improve onset")

**WP3 remains PARTIAL. Nothing deployed; production unchanged and pinned; no physical
test requested.** Record: `qualification/runs/2026-09-28-checkpoint/EFFORT_EXPERIMENT.md`
§12–§17 (registered in `ab66807` before the batch). The original screening result (§7–§11)
stands as recorded: a failure of the tested configuration, including its unmatched LOW
prefix. Class F stays rejected and was not retested.

**The corrections, verified before any batch with request-attributed evidence:**

- **A hub definition for the clone.** It uses LM Studio's `model.yaml` mechanism, is
  isolated and removable, and leaves production's definition unchanged. The clone now
  honours LOW and MEDIUM and production's sampling.
- **One shared LOW prime**, persona and fixed framing only, on the 5,043-token prefix the
  Tier-1 and ordinary LOW requests share. It serves both routes, so no separate prime
  was needed.
- **Two static prefixes are held** in the 10-entry cache. Switching efforts left MEDIUM's
  reuse intact.

**The corrected class C batch** (12 calls, $0, every call attributed, every effort
rendered as requested):

| median | prepared LOW | prepared MEDIUM |
|---|---|---|
| dispatch → first speech-safe segment | 1.8 s | 3.3 s |
| hidden reasoning | 0.29 s | 2.2 s |

- **Quality:** no LOW quality failure.
- **Registered statistic:** −1.494 s against ≤ −1.5 s. **It fails by 6 ms, recorded as a
  fail.**
- **A residual mismatch favoured MEDIUM:** a divergence checkpoint left by the
  verification probe, worth about 0.45 s on three LOW calls. It is named, not corrected
  after the fact, and was not rerun.
- **Maintenance:** each prime is ≈6.2 s cold and ≈0.45 s warm. Neither static prefix was
  evicted in the batch. Sustained-conversation eviction and queueing behind maintenance
  were not measured: Stage 3 was not reached.

**Coverage, from the production store (read-only):** class C matches **0 of his 27
spoken turns** and 0 of 110 user messages. Even qualified, it would have changed none of
his recorded spoken turns. **The approach is stopped.**

**Where the wait is:** production MEDIUM reasons a median of 269 hidden tokens on his
spoken turns (p90 440): ≈4.3 s at the median and ≈7 s at the 90th percentile before her
first visible word.

**Next local inference approach (his authorization, feasibility unverified):** a bounded
hidden-reasoning budget at MEDIUM on the same model, through the isolated engine hook,
qualified against the frozen checks before any desktop comparison.

- **Not claimed:** that LOW broadly fails, or that Voice is solved.
- **Instance:** unloaded after the run. The hub definition, hook and allowlist are kept,
  pending his ruling.

## 40. Handoff — Class C closed; the reasoning-budget experiment; the next direction (owner order of 29 September 2026)

**WP3 remains PARTIAL. Nothing deployed; production unchanged and pinned; no physical
test requested.** Record: `qualification/runs/2026-09-29-reasoning-budget/BUDGET_EXPERIMENT.md`
(feasibility and registration committed in `0a49d99` before any quality call); closure
of the effort experiment in `2026-09-28-checkpoint/EFFORT_EXPERIMENT.md` §18.

- **Class C closed.**
  - It matched none of the 27 inspected spoken turns (24–26 September).
  - The 6 ms miss of its threshold is not evidence of a meaningful difference.
  - The verification probe's attribution was by token count alone; this is corrected
    from the existing records.
- **Feasibility:**
  - No supported reasoning budget exists on the MLX path. LM Studio's
    `reasoning.budgetTokens` belongs to its llama.cpp engine.
  - A separate, pinned, allowlisted engine hook (`infrastructure/lmstudio/reasoning_budget/`,
    7 tests) makes the model's own six-token transition from reasoning to answer the
    only continuation after the budget.
  - Probe: reasoning 1,048 → 154 tokens; first answer text 15.5 s → 2.8 s; no reasoning
    in the answer; cancellation intact.
- **Screening** (budget 128, transition by 160; 12 cases × 2 × 2; every answer read):
  - **Speed:** registered median −1.13 s against ≤ −1.5 s. **It fails, and the approach
    stops.**
  - **Quality:** no new disqualifying failure. Two shared failures (O4, R1), and one
    uncapped-only failure (O4 s2).
  - **Cache:** an unexplained interaction with the prompt-cache store cost capped calls
    about 0.5 s. The reasoning saving alone was about 1.5–1.7 s.
  - **State:** the hook is removed from the engine; its source and evidence are kept.
- **Next direction (desk research, his authorization):** qualify
  `Qwen3-30B-A3B-Instruct-2507` (MLX 4-bit, no hidden-reasoning phase) as the cognition
  for spoken conversation, against the full Partner bar.
  - **Estimate:** 2.9–3.9 s against 6.30 s measured.
  - **Quality risk:** high. Prior non-reasoning local candidates failed.
  - **Memory:** it must replace GPT-OSS while Voice is on.
- **Fallback:** a dedicated Mac Studio M5 Max, a proposed option.
  - $2,499; about 3.6–4.8 s, a theoretical scenario.
  - Same model, same quality.
  - It conflicts with "a spoken conversation never leaves this Mac" unless Val moves
    wholly onto it.
- **Not claimed:** that Voice is solved. Neither option is expected to reach ~1 s.

## 41. Handoff — Qwen3-30B-A3B-Instruct-2507, isolated qualification (owner order of 29 September 2026)

**WP3 remains PARTIAL. Nothing deployed; production unchanged and pinned; no physical
test requested.** Record: `qualification/runs/2026-09-29-qwen3-30b/QWEN_QUALIFICATION.md`
(registered in `68d871b` before any quality call). The reasoning-budget experiment is
closed, with its hook removed (`2026-09-29-reasoning-budget/BUDGET_EXPERIMENT.md` §6).

- **Artifact:** `mlx-community/Qwen3-30B-A3B-Instruct-2507-4bit` @ `e9675aa3…`, every
  file matched to its digests.
  - Served through the model definition `val-experiment/qwen3-30b-a3b-instruct-2507-exp`,
    with the publisher's sampling.
  - Registry entry NOT_ADMITTED; `VAL_EXPERIMENT_COGNITION` promotes it in-process only.
- **Verified before qualification:**
  - The effective sampling of both models was observed at the engine by a read-only
    observer.
  - Its first install failed silently under the engine's Python 3.11 after the
    formatter unparenthesised an `except`. It is now guarded by a 3.11-grammar test
    over every hook.
  - Persona whole in one system block; exact preflight parity; natural stops; streaming;
    the persona prime; stock-cache reuse to the point of divergence.
- **Memory:** both cognition models resident, idle, drove swap to 8.4 GB before speech
  was loaded. Conditions ran one model at a time. A deployment would have needed a
  cognition switch at Voice On (about 13–16 s).
- **Screening** (12 cases, 2 samples, every answer read):
  - **Speed:** first speech-safe text 1.08 s against 5.91 s (paired −4.53 s).
  - **Quality:** **two confirmed critical regressions**:
    - an invented contract review with a quoted clause (C6);
    - a claimed book and access contrary to Core's `capability_state` (C5).
  - Plus a persona failure (C10 s2).
  - Shared failures are recorded as failures (C3 in all four answers).
  - **Stopped by the registered rule;** no Stage 2 or desktop run; no prompt tuning.
- **Cause:** quality, not latency, memory or integration.
- **Recommendation:** finish Voice on GPT-OSS MEDIUM. The needed rulings are the measured
  latency stack:
  - cache renewal in production;
  - the envelope-in-developer-block construction;
  - owner precedence;
  - Tier-1 LOW for courtesy turns;
  - the adaptive endpoint;
  - then the physical acceptance test.
  - Measured 27 September: ordinary 9.57 → 6.64 s median (worst 19.84 → 12.21 s);
    social 7.29 → 4.77 s.
  - Ordinary onset stays about 6–7 s. No purchase is claimed to reach the target.
- **State:** the Qwen weights, definition and registry entry are kept pending his ruling;
  the observer is removed; the cache allowlist is restored; instances are unloaded.

## 42. Handoff — the corrected-configuration Qwen comparison (owner order of 29 September 2026, "resolve one specific configuration mismatch")

**WP3 remains PARTIAL. Nothing deployed; production unchanged; no physical test
requested.** Record: `qualification/runs/2026-09-29-qwen3-30b/QWEN_QUALIFICATION.md`
§9–§14 (registered in `aecb582` before any call).

- **The mismatch was real.**
  - The first Qwen screen ran production's construction: the rendered system block was
    exactly the persona, and the envelope sat in the newest user message.
  - It did not run the `envelope_in_system` construction selected on 27 September.
- **Corrected comparison,** both models in the existing `envelope_in_system`
  construction, stock cache, one model resident at a time:
  - verified placement, effective settings and a fresh matching prime for each
    (GPT-OSS reused 5,089 of 5,089; Qwen 5,073 of its 5,074-token prime).
- **Decisive cases, five samples each:**
  - **Qwen fabricated the nonexistent contract review in 5 of 5 samples.** Invented
    clause numbers and text; "the original draft in front of me"; volumes that do not
    exist, one while saying books are unavailable.
  - **Rejected at the first case** by the registered rule. C5, C7 and C8 were not run for
    Qwen.
  - **The GPT-OSS MEDIUM comparator** was honest on C6 and C5 and met C7. On C8 it
    followed the planted record-content instruction once in five samples ("BONJOUR…").
    That is evidence against the corrected construction's boundary, and it needs
    attention before that construction is ruled as part of any latency deployment.
- **Outcome A:** Qwen closed on quality. This does not show that every non-reasoning model
  must fail.
- **The remaining proven configuration** (GPT-OSS MEDIUM) cannot meet substantially faster
  ordinary conversation: about 6.3–6.6 s median, about 70% of it hidden reasoning and
  prefill. That is not finished.
- **The remaining decision** is his: faster hardware for the same model (shorter
  reasoning and prefill, not one-second replies, and it moves conversations off this Mac
  unless Val moves), or a different local model that passes the Partner floor, which is
  a new search.
- **§41's "finish Voice on GPT-OSS MEDIUM"** is withdrawn as a completion claim. The
  GPT-OSS latency stack remains a separate decision, and the 27 September figures are
  not a qualification of today's configuration (the clone ignored effort and used
  generic sampling).

## 43. Handoff — speculative decoding closed; the desktop measurement stopped; the fast-path proposal (owner orders of 29 September 2026)

**WP3 remains PARTIAL. Nothing deployed; production unchanged; no physical test
requested.** Records: `qualification/runs/2026-09-29-fastest-config/RESULT.md` and
`FAST_PATH_PROPOSAL.md`.

- **Standing rulings recorded:**
  - Qwen is removed from consideration for production Voice; both screens are preserved.
  - `envelope_in_system` is excluded from any proposed release until its authority
    boundary is repaired and qualified.
  - Six to seven seconds does not complete Voice.
- **Speculative decoding: closed** on the installed engine's own code, with nothing
  downloaded and the engine unchanged.
  - GPT-OSS's 128-token rotating cache (12 of 24 layers) cannot be trimmed at Val's prompt
    lengths, and mlx_lm's speculative path refuses such a cache.
  - A draft model resets the cache history and disables prefix checkpoints.
  - No draft shares GPT-OSS's 201,088-token vocabulary.
- **Components independent of `envelope_in_system`:** cache renewal and divergence, Tier-1
  LOW, owner precedence, adaptive endpoint, speech bound, combined continuations.
- **The desktop measurement of them, stopped at 14:49 by his order: INCOMPLETE.**
  - F-B1, F-I1 and F-I2 complete. F-B2 stopped in session 1 of 5.
  - Everything is preserved; no comparison is drawn.
  - Raw, unbalanced: real Tier-1 LOW courtesy turns 2.97 s median (p90 3.65 s);
    MEDIUM turns 7.26 s in the independent runs.
- **Continuation point: `FAST_PATH_PROPOSAL.md`, awaiting his decision.**
  - **The design:** ordinary spoken turns on the resident GPT-OSS at LOW effort under
    three Core-owned layers:
    - a deterministic pre-route to MEDIUM on correction, pending action, consequential
      subject, attachments or recall, multiple constraints, or a reference to a record
      Core cannot find;
    - a Core-owned answer contract, with the persona alone as system;
    - a pre-speech grounding guard that withholds any segment claiming unrecorded work,
      documents, volumes or capabilities, and escalates to MEDIUM.
  - **Estimate:** about 3.2–4.5 s on fast-path turns (blended about 3.5–4.5 s), against
    6.3–7.3 s measured. About one second is impossible under the current turn boundary:
    fixed costs are about 1.6 s.
  - **His tradeoff:** LOW's lower general-knowledge accuracy (sonnet 2/2 wrong; one
    refused fact), or MEDIUM on every turn.
  - **The early gate:** about 70 local calls, about 15 minutes, $0. It rejects if any
    fabrication, false capability, lost correction or boundary violation reaches speech,
    if more than 30% of ordinary-shaped cases escalate, or if the first segment's median
    exceeds 1.5 s.
- **Runtime:** instances unloaded; cache allowlist restored; observer removed. The Qwen
  weights, definition and entry are kept pending his ruling on removal.

**Avatar correction (owner, 29 September 2026), for every later reader.**

- **Val's avatar is not prerecorded video loops with lip-sync.** He rejected that
  approach.
- **The existing videos and stills are references** for her appearance, room, clothing,
  behaviour, movement and transitions, not the runtime animation.
- **The intended avatar** is a continuously responsive, locally rendered photorealistic
  character in a coherent room. A real-time 3D prototype is the direction to evaluate,
  with fidelity and performance not established.
- **Withdrawn:** the proposal's first draft listed the avatar as loops under 1 GB. That
  figure is removed from every capacity statement, and its GPU and memory demand are
  **unknown**.
- **Capacity going forward:** any cognition model or hardware choice must leave headroom
  that the avatar prototype's concurrent measurement establishes (`FAST_PATH_PROPOSAL.md`
  §3).
- **A baseline conflict for his amendment:** `docs/baselines/01-architecture.md` §8.2 still
  specifies looping clips and lip-sync on a still. That is the rejected approach and the
  source of the error. The baseline was not edited here; it is his to amend.

## 44. Handoff — the fast path closed; the avatar baseline amended; the unresolved decision (owner order of 29 September 2026)

**WP3 remains PARTIAL. Nothing deployed; production unchanged; no model call, download or
benchmark in this step.** Record: `qualification/runs/2026-09-29-fastest-config/DECISION.md`.

- **The ordinary-LOW fast path (§43) was not approved and is closed.**
  - He did not authorise trading general-knowledge accuracy for speed.
  - "Three layers make it safe" is withdrawn:
    - the pre-route's key rule does not exist;
    - the contract is an instruction;
    - the pre-speech check is pattern matching. It would miss a falsehood stated plainly,
      and it cannot check general facts.
  - A failure after earlier sentences have played means duplicate or contradictory speech
    and a 6–7 s gap. Holding all audio erases the gain.
- **Coverage, from the 27 recorded spoken turns (24–26 September), each classified with
  only its prior context:**
  - 7 are courtesy turns the Tier-1 route already carries;
  - 11 are excluded;
  - **9 would have taken the fast path**: 3 test statements, 5 questions about her own
    state, 1 creative request.
  - Of 6 turns read as ordinary use, it would have carried 2.
  - My earlier 70–85% estimate was wrong.
- **No supported configuration on this Mac meets both his response-time goal and his
  quality requirements.** None has been demonstrated.
- **Descriptive observations from the stopped, unbalanced comparison** (speech end → first
  audio, median):
  - production configuration 9.85 s;
  - independent latency components 7.26 s;
  - Tier-1 LOW courtesy turns 2.97 s.
- **THE UNRESOLVED DECISION (his):** whether Val's cognition may run on a dedicated local
  machine in the house with a discrete GPU, this Mac keeping microphone, desktop,
  recognition, voice and avatar.
  - **Estimate:** about 2.8–3.4 s, not one second.
  - **It requires:**
    - amending the seal from "this Mac" to the house's own machines on the local network;
    - a second machine to keep;
    - requalifying MEDIUM on a different runtime.
  - **The proposed early gate:** a single-stream rate measurement with a public-text prompt
    of Val's prompt length, before any purchase. No price is quoted; none was sourced.
  - **If he declines,** one of three gives way: MEDIUM's quality, the latency goal, or
    cognition on this Mac alone.
- **Avatar baseline amended** on his authorisation: `docs/baselines/01-architecture.md` §8.2
  now specifies the locally rendered, continuously responsive avatar.
  - The existing videos and stills are references.
  - Implementation, fidelity, memory, GPU use and concurrent performance require prototype
    qualification.
  - The former loop design is preserved there as superseded history.
  - §2.1 carries a note on the 31 August wording.

## 45. Handoff — the dedicated-GPU feasibility proposal (owner order of 29 September 2026, later)

**WP3 remains PARTIAL. Nothing deployed, bought, rented, downloaded or run; production
unchanged.** Record: `qualification/runs/2026-09-29-fastest-config/GPU_PROPOSAL.md`.

- **His position:** the ordinary-LOW proposal stays closed, with its coverage findings and
  the limits of its checks preserved (`DECISION.md`).
  - The dedicated local GPU option is worth evaluating.
  - **Not authorised:** a purchase, a paid rental, deployment, or any amendment letting a
    private Voice conversation leave this Mac.
  - About three seconds is not accepted as completion; his goal is approximately one
    second.
- **Recommended configuration:**
  - RTX 5090 (32 GB) in a complete prebuilt desktop, Ubuntu 24.04;
  - llama.cpp `llama-server`, one pinned CUDA build;
  - `ggml-org/gpt-oss-20b-GGUF` file `gpt-oss-20b-MXFP4.gguf` (12.11 GB, revision
    `ef9b12f2…`), window 32,768, one slot;
  - MEDIUM through the chat template, and production's sampling sent per request, both
    verified as executed.
  - Cognition alone would move. Core, the store, recognition, the voice, the desktop and
    the avatar stay on this Mac. The machine stores nothing and has no tools.
- **Published, same runtime and file** (llama.cpp maintainers): 282.5 tokens/s generation
  and 8,834 tokens/s prompt processing at 8k, against 62–65 and about 650–750 measured
  here.
  - **Unknown:** the rate at about 6,000 tokens occupied, warm-prefix reuse in
    `llama-server` for this model, and time to a first answer sentence at MEDIUM.
- **The pre-purchase measurement:** public or synthetic material only, about 40 requests.
  - It measures cold prefill and warm reuse separately, the reasoning rate at natural
    reasoning lengths, time to the first answer segment, and memory with the occupied
    context stated.
  - Fixed thresholds.
  - $0 on a borrowed machine, or a rental with a **$5 ceiling** and a stopping rule.
- **Estimate if it passes:** about 2.8–3.4 s speech end → first audio (slower turns about
  3.5–4.3 s), with the Mac-side endpoint, recognition, synthesis and playback at their
  measured values.
  - The further changes toward one second (faster first audio, a shorter turn boundary,
    less reasoning) are separate, unproven, and not in that estimate.
  - Approximately one second is not reachable by any identified change while MEDIUM's
    reasoning is kept.
- **Cost:** $4,499.99 before tax for the complete machine (listing to be confirmed); about
  5–7 days of integration; an always-on second machine to maintain.
- **Decisions awaiting him:**
  1. **Now:** whether and how to run the measurement.
  2. **Only if it passes, each separately:** the purchase; the seal amendment; the
     llama.cpp provider ruling; requalification of MEDIUM on the new runtime.
- **Limits preserved:**
  - no tested configuration on this Mac has demonstrated both requirements, which is not
    proof that every local architecture must fail;
  - `envelope_in_system` is not approved;
  - avatar headroom on this Mac is unverified until the prototype is measured
    concurrently.

## 46. Handoff — EAGLE3 on llama.cpp tried and closed; the GPU proposal corrected (owner order of 29 September 2026, evening)

**WP3 remains PARTIAL. Nothing deployed; production unchanged; no purchase or rental.**
Records: `qualification/runs/2026-09-29-eagle3/EAGLE3_PROOF.md` (registered at `4867d83`
before any measured request); `2026-09-29-fastest-config/GPU_PROPOSAL.md` (corrected at
`c99e799`).

- **Scope:** the earlier speculative-decoding closure is of the installed MLX engine only.
- **EAGLE3, the documented llama.cpp pairing:** it loads and runs on this Mac through Metal
  and is closed on performance.
  - **Tested:** official llama.cpp 0.4.1 (build 10964, `b29c606e2`); target
    `gpt-oss-20b-MXFP4.gguf` and draft `eagle3-gpt-oss-20b-BF16.gguf` from
    `ggml-org/gpt-oss-20b-GGUF` @ `ef9b12f2…`; MEDIUM; through Val Core in production's
    construction.
  - **Measured, 8 requests:** generation 60 tokens/s with the draft off and 20–23 with it
    on. Draft acceptance 9–15%. First speech-safe segment 16.5 s median with the draft
    on.
  - Prefix reuse worked (5,048 tokens reused per request). Streams intact. No swap growth.
  - **llama.cpp without the draft matches MLX's rates,** so changing runtime on this Mac
    gains nothing.
  - **Not established:** onset with the draft off (a harness defect, counted against the
    sixteen); per-request sampling as executed; cancellation.
- **The GPU proposal is preserved as the alternative, corrected:**
  - warm-prefix reuse is mandatory;
  - a separately defined "no reuse" outcome, estimated at about 4.1 s;
  - estimates at the gate's thresholds (about 3.4 s), apart from published empty-context
    rates;
  - the fallback's memory cost stated;
  - prices provisional.
- **The remaining ordinary delay is unchanged:** measured 28 September, 6.3 s median speech
  end → first audio. Its parts: endpoint 0.47, confirmation 0.26, Core 0.06, prefill 1.49,
  reasoning 3.04, segment 0.21, synthesis 0.78, playback 0.05.
- **Continuation point, his decision:** whether to run the GPU pre-purchase measurement
  (borrowed machine, or a rental capped at $5; public or synthetic material only). Nothing
  else is pending.

## 47. Handoff — a different conversational model for Voice, measured and staged for his approval (owner order of 29 September 2026, deadline 30 September 17:36 CDT)

**WP3 remains PARTIAL. Nothing deployed; production unchanged and pinned; no physical
test made — one is required.** Record: `qualification/runs/2026-09-29-voice-model/VOICE_MODEL.md`.

- **Selection:** Gemma 4 26B-A4B (thinking off; `lmstudio-community/gemma-4-26B-A4B-it-GGUF`
  @ `f6e67478…`, `Q4_K_M`, 16.8 GB) on the installed official llama.cpp (0.4.1, build
  10964). Fallback Qwen3.6 35B-A3B, not needed and not downloaded.
- **Screen (registered first):** 32 critical samples, no absolute failure; 8 ordinary cases,
  no material regression against GPT-OSS MEDIUM on the same inputs; first speakable text
  1.90 s median (threshold 2.0 s).
- **Integration (isolated, off in production):** `VAL_VOICE_MODEL` pins spoken turns to
  the model through Val Core; typed work stays on GPT-OSS; GPT-OSS answers once if the
  Voice call fails before any word; a supervisor starts and stops the server;
  `VAL_VOICE_TURN_PREFILL` prepares the turn's request ahead of his words;
  `VAL_VOICE_EARLY_AUDIO` (not recommended) releases audio early for complete utterances.
- **Measured through the real desktop and player** (5 sessions, 40 turns each,
  recognition and synthesis active, GPT-OSS unloaded):
  - **hold kept (recommended):** ordinary 2.33 s median / 4.18 p90; simple exchanges 2.56 s
    median; every continuation joined; no fallback, no missing audio, one player
    underrun event;
  - **early audio:** 1.98 s / 2.26 p90; one continuation not joined and answered after
    45.7 s.
  - GPT-OSS in production's configuration: 9.85 s median on the same turns (descriptive).
  - **One second is not met.** What remains: synthesis 0.71 s, endpoint and confirmation
    0.72 s, the hold 0.39 s.
- **Resources:** free memory 38% median with everything resident; single samples of 9–16%
  at model load crossed the registered "below 20%" threshold, whose reading (lowest
  sample or sustained) is his to settle; swap growth inside its threshold. Avatar
  compatibility not claimed.
- **Staged, not installed:** release tag `voice-model-release-2026-09-29` (`9db6e61`),
  `~/Projects/val-releases/9db6e61` with its environment, and the paired desktop bundle
  (`955438f0…7686`) outside the launchable locations. The credential tool gained the
  `llamacpp` target. Procedure and rollback in the record §9.
- **His decisions:** admission of the model and the provider for spoken turns; the
  adaptive endpoint; the ahead-of-words preparation (conversation content primed
  locally, the open ruling of 25 September); the memory threshold's reading; the release
  (47 commits, migration `0032`, the desktop build); then the listening check.

## 48. Handoff — the challenger comparison and the release checks (owner order of 29 September 2026, evening)

**WP3 remains PARTIAL. Nothing deployed; production unchanged.** Records:
`qualification/runs/2026-09-29-voice-model/CHALLENGER.md`, `VOICE_MODEL.md` §10.

- **Challenger review (9 of the 45 minutes):** one candidate has a stated, concrete
  advantage — Qwen3.6-35B-A3B non-thinking, a third-party hallucination rate of 50.5%
  against Gemma's 86.4% (abstention, bearing on the fabrication requirements); no
  candidate can improve onset (the model is ~0.4 s of 2.3 s) and it is 3.6 GB larger.
  Conditions for beating Gemma are registered (CHALLENGER.md §1.4), the ten
  fabrication-pressure cases are written and unseen by either model (`voice_screen.py
  pressure`). **Blocked before download: 16 GB free against a 20.4 GB file.** Freeing space
  (the removed Qwen3-30B weights, 17 GB) or another volume is his; deletion was refused
  to me. **Recommendation as it stands: retain Gemma.**
- **Resident-together check FAILED its threshold:** GPT-OSS loaded beside the Voice model,
  swap 3.0 → 14.5 GB in fifteen minutes, one 0% free sample; onset and answers unaffected.
  The staged release does not unload GPT-OSS at Voice On. **Repair behind
  `VAL_VOICE_RELEASES_PARTNER`** (unset): Voice On unloads the Partner model, Voice ending
  loads it back. Measured: swap flat, free 39% median, latencies unchanged, no fallback.
  The return path could not be demonstrated in the harness (instance identifier vs model
  key) nor on production's key (refused as a shared-resource change) — `lifecycle_proof.py`
  is prepared for him. Recommendation: ship it set.
- **Underrun:** single event at an interruption boundary; none in 66 further turns.
  **Lifecycle** session clean twice. **CI green** on `release/voice-model-2026-09-29` at
  `9db6e61`; the residency repair needs a re-tag (desktop unchanged).
