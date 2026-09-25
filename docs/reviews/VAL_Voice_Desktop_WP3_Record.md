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
