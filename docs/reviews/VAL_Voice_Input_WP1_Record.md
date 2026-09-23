# Live voice mode, work package 1 — service-side voice input and canonical turn integration — 23 September 2026

Val hears. The boundary this package built and shipped is:

    in-memory PCM → local whisper.cpp + Silero VAD → provisional transcript state
      → final transcript → canonical Val user turn → the existing Val Core

Nothing else. TTS delivery, speech segmentation, barge-in after Val begins
speaking, playback, the desktop Voice button, the AudioWorklet, desktop
microphone capture, echo-cancellation acceptance, the avatar, the camera, latency
optimisation, low-reasoning measurement and speculative decoding all belong to
later packages and none of them were built.

---

## 1. The one sentence this package exists to make true

**A spoken turn is an ordinary turn.**

There is no voice cognition route, no voice-specific classification, no voice
exemption from consequence handling, and no component here reaches a provider.
When an utterance settles, its text goes through `val_gateway.deliberate.send` —
the same door a typed turn uses — and therefore through project resolution,
classification, the strip and blind machinery, memory, recall, the record-state
envelope, the persona, routing, budget and persistence, unchanged. Production
GPT-OSS remains MEDIUM and was not touched.

Three distinctions the implementation refuses to blur, each held by tests:

**Provisional is not final.** A rolling guess is mutable session state. It is not
a message, not history, not recall evidence, not Partner context and not indexed.
`ProvisionalText` and `VoiceUtterance` are separate types, so handing the wrong
one onward is a type error rather than a silent promotion.

**Recovered is not canonical.** A guess a crash left open comes back labelled
`interrupted`, and nothing promotes it to something Lord Armand said.

**Consequential acts run on settled text only.** The classifier sees the final
transcription, because a guess never reaches `send` at all.

---

## 2. What was built

| Unit | Path |
|---|---|
| The input-half domain boundary | `packages/domain/src/val_domain/voice.py` |
| The recognizer helper, in the dedicated voice runtime | `infrastructure/voice/whisper_listen.py` |
| The production recognizer adapter | `packages/providers/src/val_providers/whisper_recognizer.py` |
| The voice-session state machine | `packages/gateway/src/val_gateway/voice.py` |
| Migration — session, provenance, recovery journal | `packages/domain/migrations/versions/0028_voice_input.py` |
| ORM models and the transcribed schema | `val_domain/schema.py`, `packages/domain/tests/test_schema.py` |
| The service contract for the later desktop package | `apps/api/src/val_api/app.py`, `contracts.py` |
| Composition — a recognizer factory, not a singleton | `val_gateway/startup.py`, `val_api/main.py` |
| The frozen fixture | `infrastructure/voice/fixtures/frozen-utterance.wav` |

**The recognizer helper** runs under `~/.val-runtimes/voice-venv/bin/python`, a
dedicated interpreter holding nothing but numpy, and reaches whisper.cpp through
`ctypes` against the shared library built from the pinned release — so **nothing
was added to Val's production Python dependency set** and no pinned dependency
was changed. It imports nothing from Val. Framed records arrive on stdin
(`[u32 kind][u32 length][payload]`; kind 0 is int16 PCM, kind 1 a JSON control
object) and JSON lines leave on stdout. Nothing reaches it through the command
line except one configuration object, so no value from a model, a document or a
tool result can become an argument. `verify_layout()` checks the library's own
`whisper_full_params` defaults at fields spread across the struct before anything
runs, because a wrong ctypes layout does not fail loudly on its own.

**The adapter owns no microphone.** Audio is handed to it. It holds a subprocess,
a reader thread and a queue, and no conversation, identity, policy or authority.
The two models are checked against their recorded digests before a session opens,
so a substituted model is refused rather than quietly listened with.

**The session** owns the guess in progress, the resume window and the journal. It
submits through the ordinary Core path on a worker, so audio keeps arriving while
Val thinks.

---

## 3. Two corrections made from measurement, not from taste

**The VAD must run on the CPU — it is not a preference.** `use_gpu = True` on the
Silero context aborts the process in this build: the graph has a pre-allocated
tensor in an MTL buffer that cannot run the operation, and ggml calls `abort()`
rather than falling back. Measured on the CPU path it costs **0.028 s for 11 s of
audio — a real-time factor of 0.003** — so nothing is given up. (Batching was
measured too: 512, 1,536, 4,096 and 8,192-sample handovers all land at 0.002–0.003,
so the 512-sample window stays.) A first reading of whisper.cpp's own log took
`vad time = 27 ms` as a per-call cost; it is cumulative, and the direct
measurement is what is recorded here.

**Provisional decoding is gated on audio time, not wall-clock time.** In live use
the two are identical, because speech arrives as it is spoken. They diverge when
audio is fed faster than real time — a test, or the frozen fixture — and
wall-clock gating there produced *no provisional events at all*, which would have
made the rolling guess untestable and its interval unprovable. Audio-time gating
gives the same live behaviour and a deterministic one. A guess never runs more
often than twice its own last cost, so a long utterance on a slow machine spends
most of its time listening rather than re-guessing.

---

## 4. Endpointing, recorded rather than described

The configuration actually in force, carried on every session row as
`endpoint_configuration`:

```json
{"threshold": 0.5, "min_speech_ms": 220, "min_silence_ms": 650,
 "speech_pad_ms": 80, "max_utterance_s": 30.0}
```

One reasonable starting configuration, from the order's own figures. **No tuning
campaign was conducted.** `max_utterance_s` is the house's own addition: a stuck
VAD cannot hold a turn open forever.

---

## 5. The schema — migration `0028`, three append-only tables

What is *absent* from all three is as deliberate as what is present: **there is no
audio column anywhere, of any type.**

- **`voice_sessions`** — which conversation was heard, when listening began,
  exactly which recognizer and models heard it, and the endpointing in force. The
  one table here with a genuine lifecycle, so it takes the `budget_reservations`
  treatment of `0009` rather than the frozen one: a new trigger,
  `val_voice_session_identity_is_immutable`, pins everything that identifies the
  session — above all the recognizer and the two model digests — and only `state`,
  `closed_at` and `closed_reason` may move. A session re-labelled afterwards as
  having been heard by something else would prove nothing.
- **`voice_message_provenance`** — a sidecar on a finalized voice-origin message,
  rather than columns on `messages`, because a spoken turn is an ordinary turn and
  the core table should not learn about microphones to say so. One row per message
  (`unique(message_id)`), and `transcription_status = 'final'` is a check
  constraint: a guess is not a message and so can have no provenance row.
- **`voice_recovery_journal`** — text only. Append-only supersession: the next
  state of an entry is the next entry, numbered explicitly so ordering is a
  recorded fact rather than an inference from a timestamp. `state` may be
  `provisional`, `superseded`, `abandoned` or `interrupted` — **never `final`**,
  because this table holds no canonical statement by anybody — and
  `(state = 'superseded') = (superseded_by_message_id IS NOT NULL)` stops a guess
  being marked replaced without naming the turn that replaced it.

**No core table gained a column.** Migration `0027` was not rewritten. `0028` is
forward, deterministic, and reversible: proved down to `0027` and back up on the
scratch store, and by the domain suite which migrates from empty to head.

**The journal is structurally excluded from recall.** Recall reads the
`messages_current` view; a separate table is not reachable from it by any query
that exists, which is stronger than a flag a future change could forget to check.
`test_l_no_recall_query_can_reach_a_guess` asserts that `val_gateway.memory`'s
source names neither voice table and does name `messages_current`.

---

## 6. Resume before Val delivers

When Lord Armand pauses, the utterance endpoints, and he carries straight on
before Val has said anything aloud, that is **one** thing he meant to say. Two
visible owner messages for one human utterance is the failure to avoid.

**Before submission** — the ordinary case — the two halves are simply joined into
one utterance, with `merged_from` recording which breath was absorbed. Nothing has
been submitted, so nothing needs cancelling: this is the "where safely possible"
the order names, and it costs nothing.

**After submission, before delivery** — the canonical wording is corrected through
the existing append-only revision machinery (`val_gateway.revisions.revise`). The
`messages` row stays exactly what was first heard; the correction is a new
`message_revisions` row carrying the note *resumed before delivery*, and later
turns read the corrected wording. No UPDATE, no deletion, no second visible turn.

**And it is refused where it must be.** When the message anchors an enforced blind
position or a deliberation, `revise` refuses, and this package does not work
around it: the resumed speech becomes its own turn and the refusal is kept on the
session's record as `merge_refused`. Continuity is not worth falsifying evidence
that was valid when it was produced.

**Worth Lord Armand's eye** (§8, OP-1): a merge of the second kind writes a
`message_revisions` row whose `authored_by` is "Lord Armand", because that writer
attributes every correction to the message's author. He did say both halves, and
the note records why the correction exists — but this is the first time the house
corrects his wording rather than him typing a correction, and the record does not
distinguish the two by author. Stated rather than smoothed over.

**The boundary.** Once the delivering layer marks a turn delivered, resumed speech
is a new turn: he has heard her, so what he says next is a reply, not the rest of
a sentence. Nothing speaks aloud in this package, so nothing calls that yet — the
delivering layer does, in work package 2. Post-audible barge-in is not built.

---

## 7. The service contract for the later desktop package

The smallest surface that package will need, on the existing transport:

| | |
|---|---|
| `POST /voice/sessions` | open a session (a conversation id, or none for a new chat) |
| `POST /voice/sessions/{id}/audio` | one block of 16 kHz mono int16 PCM, as the request body |
| `GET /voice/sessions/{id}` | poll: state, the guess, what is pending, the turns |
| `POST /voice/sessions/{id}/finalize` | end the utterance now rather than waiting for silence |
| `POST /voice/sessions/{id}/delivered/{message_id}` | the delivering layer says Val has spoken |
| `POST /voice/sessions/{id}/close` | stop listening and release the recognizer |
| `GET /voice/interrupted` | guesses a crash left open, labelled `interrupted` |

Ordinary POST and GET on the same loopback-only service, under the same CORS
grant and the same two shell origins. **No new origin, no new bind, no new header,
no upgrade, no token** — the existing stack carries these events perfectly well,
and a second realtime framework would be a second thing to secure. `provisional`
and `turns` are separate fields, so a caller that renders the rolling transcript
as conversation has to have chosen to.

With no recognizer wired the routes answer 503 with the negative stated, and reach
for nothing else.

**A stated limitation, not hidden.** A voice session's durable row is written on
first need rather than at open, because a session belongs to a conversation and a
new chat's conversation is created by its first spoken turn. Until a conversation
exists there is nothing to journal a guess against, so **the very first utterance
of a brand-new chat has no crash recovery**. Every later one does, and a session
opened on an existing conversation has it throughout. This is visible in the
integration proof below, where the journal holds one `superseded` entry and no
`provisional` ones.

---

## 8. Open problems reviewed at this checkpoint

**OP-1 — claims of work not performed have no structural counter.** Its
message-revision/retraction checkpoint is touched: this package gives
`message_revisions` a writer that is not Lord Armand typing. The merged wording is
exactly his two utterances joined, the note says *resumed before delivery*, and
the utterances absorbed are on the provenance row — so the fact is checkable
afterwards. It is not distinguishable *by author*, and that is recorded here
rather than solved. No change to OP-1's status.

OP-2, OP-4, OP-5 and OP-6 have no checkpoint naming voice input, this capability
or this layer, and none is advanced or affected by it. OP-3 is closed.

---

## 9. Tests

**No pre-existing test was weakened, and no pre-existing test file was modified
except `packages/domain/tests/test_schema.py`**, which is the hand-transcribed
schema and had to gain the three new tables, their columns and their nullable
columns — the transcription is the check.

New, 52 tests:

- `packages/gateway/tests/test_voice_input.py` (28) — the acceptance list A–V
  against real PostgreSQL and the real deliberated Core path, plus the session's
  own lifecycle and the domain's merge.
- `packages/providers/tests/test_whisper_recognizer.py` (13) — the framed
  protocol; audio on stdin and never as an argument; the argument vector is the
  interpreter, the helper and one configuration, with no shell; a substituted
  model refused before anything listens; each missing artifact reported as itself;
  the adapter satisfies the domain protocol; and the two structural negatives.
- `apps/api/tests/test_voice_service.py` (11) — the service contract end to end,
  the origin rules, recovery, and that the rest of the service is untouched.

Where each acceptance requirement is held:

| | Requirement | Test |
|---|---|---|
| A | PCM enters the recognizer in memory | `test_a_pcm_enters_the_recognizer_in_memory_and_the_session_keeps_none` |
| B | silence creates no user message | `test_b_silence_creates_no_user_message` |
| C–G | speech_start, provisional, revision, speech_end, final | `test_c_to_g_the_five_event_concepts_are_distinct` |
| H | one utterance, one canonical message | `test_h_one_finalized_utterance_creates_exactly_one_canonical_message` |
| I | through normal Val Core | `test_i_the_spoken_turn_goes_through_normal_val_core` |
| J | provenance: `input_mode=voice` and exact recognizer facts | `test_j_provenance_records_input_mode_voice_and_the_exact_recognizer`, `test_j_the_visible_message_text_carries_none_of_that` |
| K | the guess is absent from message history | `test_k_the_provisional_transcript_is_absent_from_message_history` |
| L | the guess cannot enter recall | `test_l_no_recall_query_can_reach_a_guess` |
| M | the guess cannot enter cognition context | `test_m_a_guess_never_reaches_the_cognition_context` |
| N | the journal holds text only | `test_n_the_recovery_journal_holds_text_and_nothing_else`, `test_n_a_guess_is_journalled_as_text_while_it_is_being_spoken` |
| O | the journal cannot enter recall | `test_o_the_journal_is_not_reachable_from_conversation_history` |
| P | finalization supersedes append-only | `test_p_successful_finalization_supersedes_the_guess_append_only`, `test_p_the_journal_refuses_to_be_rewritten` |
| Q | interrupted recovery is labelled, never canonical | `test_q_an_interrupted_guess_comes_back_labelled_and_never_canonical` |
| R | resume before delivery is one owner turn | four tests: pre-submission merge, post-submission revision, the delivered boundary, and the deliberation refusal |
| S | consequential behaviour never from provisional text | `test_s_the_classifier_sees_settled_text_and_never_a_guess` |
| T | typed behaviour unchanged | `test_t_typed_turns_are_completely_unchanged`, `test_the_rest_of_the_service_is_untouched_by_this_package` |
| U | no cloud STT reachable | `test_u_no_cloud_speech_recognition_is_reachable_from_this_path`, `test_no_cloud_recognizer_and_no_omni_fallback_is_reachable_from_this_module` |
| V | no raw-audio persistence | `test_v_no_raw_audio_is_persisted_anywhere` |

Test PCM is synthetic or the frozen fixture. **No owner microphone audio was
recorded, used or retained.**

### Two defects found before they could matter, and how each was found

**One spoken conversation would have become many.** The service's first submission
closure restated the session's project signals on **every** utterance. House
doctrine reads a project stated on a resumed conversation as a switch, and a
switch starts a new conversation — so a voice session would have scattered one
spoken conversation across a new conversation per utterance. The signals are now
offered only while there is no conversation yet; once there is one, its own stored
scope is the authority (WP-0.7 §18). Found by `test_h`, which asked for one
message in one conversation and got none.

**A failed provenance write was silently swallowed.** Found by restarting the real
service onto this build before the live store had taken migration `0028`: the
provenance insert runs on a worker thread, and its exception died with the thread
— so the turn was answered and in the conversation while the session went on
looking healthy and the record was incomplete. The write now reports the failure
onto the session's own state, which is a thing a caller can see and say.
`test_a_failure_writing_provenance_is_reported_not_swallowed` holds it by renaming
the table out from under a live session, and asserts the turn itself is not
pretended away.

---

## 10. The real Core integration proof

One deterministic run, everything real except the database — the scratch store
deliberately, because a proof should not write into Lord Armand's conversation
history. The real composition root (`val_gateway.startup.start`), the real
gateway, the real registry and routing, the real production recognizer adapter,
the real local partner route. Nothing injected.

**Fixture:** `infrastructure/voice/fixtures/frozen-utterance.wav` — 2.600 s,
16 kHz mono 16-bit, 83,244 bytes, SHA-256
`376dc5b345f450c74f54444a8dfb3749e718398eb7c5fd75ee3c3b67740eeb4f`. Cut
deterministically from whisper.cpp's own public-domain sample. Fed in 20 ms
blocks, then a tail of silence so endpointing fires the way it does when he stops
talking.

| | |
|---|---|
| Expected transcript | `And so, my fellow Americans,` |
| **Recognized final transcript** | `And so, my fellow Americans,` — **exact** |
| Provisional events | **3** |
| Canonical user messages created | **1** |
| Voice provenance | `input_mode=voice`, `transcription_status=final`, utterance 1, `endpoint_reason=silence`, `provisional_events=3`, `merged_from={}`, recognizer `whisper.cpp` `v1.9.4` `927cfce3…`, ASR `ggml-small.en` `c6138d6d…f9c41e5d`, VAD `silero-vad-v6.2.0` `2aa269b7…f7fb6987`, endpointing as §4 |
| Classification | `not_consequential`, established, 1 attempt — `claude-haiku-4-5-20251001`, 721 in / 25 out, 1,461 ms, **$0.000846** |
| **Production cognition route** | `openai/gpt-oss-20b` on `lmstudio` — the ordinary production partner route, 5,681 in / 559 out, 17,902 ms, **$0.000000** |
| **Final persisted Val text** | "My lord, if you wish to continue your address or require assistance in shaping its content, I am at your service." |
| **Provider cost** | **$0.000846** total |
| Recovery journal | one entry: utterance 1, entry 1, `superseded`, naming the message — the first-utterance-of-a-new-chat limitation of §7, working as stated |
| Voice sessions | 1, closed, reason recorded |

**Zero raw-audio persistence, checked rather than asserted.** Every `bytea`,
`text`, `character varying` and `jsonb` column in the store — **131 columns** —
was searched for a 32-byte slice of the fixture's samples. **None contains it.**
The only `bytea` column in the whole schema is `blobs.bytes`, and `blobs` and
`attachments` are both empty: speaking created no attachment. **Zero cloud speech
recognition**: the two provider calls above are the whole of what was transmitted,
one classification and one local response, and neither is speech recognition. **No
audio file was written**: a search of `/tmp`, the system temporary directory,
`~/.val-voice`, `~/.val-models` and `~/.val-runtimes` for `.wav`, `.mp3`, `.pcm`
or `.raw` files created during the run returns nothing.

Provider credentials were read from the installed launch agent by `plistlib`
straight into the child environment; no secret value was printed, logged or
returned.

---

## 11. Deployment

**The live store took migration `0028` through the explicit deployment path**
(`alembic -x deploy=live upgrade head`), moving `0027_local_speech` →
`0028_voice_input`. The three tables are present and empty, with their guards in
place; no existing table was altered. This is the deliberate act the migration
doctrine requires, not something an environment variable did.

**The service was restarted onto this build and is healthy** — `/health` reports
`{"status":"running","warnings":[]}` with no voice warning, because the runtime,
the library and both models are present. A live voice session opened successfully
against the real recognizer through the production service (`201`), and the
recognizer subprocess was released when the service was restarted, leaving nothing
behind. **No turn was taken through the live store**: a proof does not write into
his conversation history, and the live voice tables are empty.

Baseline before this package: `master` `9537499a13d264464869896abc279c790f088ca1`,
live store `0027_local_speech`, persona v1.9 revision 8, cognition
`gpt-oss-20b-mxfp4-mlx-lmstudio-partner` at MEDIUM with a 32,768-token context,
production voice `val-established-v1`. **Persona, cognition, reasoning effort,
context and voice are all untouched by this package.**

---

## 12. What is not claimed

- **Recognition accuracy is not characterised.** One fixture transcribed exactly
  is one fixture transcribed exactly. No word-error rate was measured, and none
  is claimed.
- **Latency is not optimised, and the local partner call took 17.9 s** on this
  turn. Latency optimisation is excluded from this package by the order; the
  figure is recorded because it is what happened, not because it is acceptable.
- **Nothing speaks.** There is no TTS delivery, no playback, no segmentation and
  no barge-in after Val begins speaking.
- **Nothing captures.** There is no desktop Voice button, no AudioWorklet and no
  microphone capture; the service receives PCM from a caller that does not yet
  exist in the shell.
- **Echo cancellation is untested.** It is work package 2's acceptance.
- **WP-0.11 is unchanged and still open.** This package changes nothing about it.
