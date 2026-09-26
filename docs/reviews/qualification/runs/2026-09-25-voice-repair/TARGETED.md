# Targeted voice latency order — his successful session, 25 September 2026

Owner order "TARGETED VOICE LATENCY REPAIR" and its continuation of the same evening.
This record is separate from `RESULT.md`, which holds the earlier voice-mode repair
and its follow-up (physical reconstruction, maintenance probes). **That follow-up was
completed work on the earlier order; this record is the completion of the targeted
one.** WP3 remains PARTIAL.

## 1. The session and its build (OBSERVED)

Conversation `01a0db46-548d-7bf1-b80f-c2cde1770a4d`, Voice session `602a4297…`,
20:13–20:18 CDT: "Good evening, Val." → "I'm checking your voice model." → … → "Do you
know of any way to increase the speed of the conversation? Because that last one was
about 13 seconds before you were able to respond." → "I'd like it a little bit faster
if possible."

- **Desktop `b6c8937`:** every timing report the window sent carries the fields only
  `b6c8937` sends (`speech_end_to_owner_words_provisional_ms`, segment offsets and
  gaps).
- **Service `b6c8937`:** process 91899 started 19:22:49 CDT, after the install.
- **Runtime:** `openai/gpt-oss-20b`, parallel 1, 32,768 context. Every turn reused the
  5,048-token persona prefix (LM Studio's log). None of this pass's probes overlapped
  the session: they began at 20:32:36, and the session's last runtime request was at
  20:17:13.

## 2. Reconstruction (ms after the recognizer's endpoint unless stated)

The endpoint is about 0.65 s after speech end: the desktop's measured speech end →
playback exceeds endpoint → playback by that much. Reasoning and answer are separated
by the adapter's channel boundary: `provider_chunk` counts every streamed chunk,
`provider_visible_text` only the answer's. So the interval between the first chunk
and the first visible text is chunks of the hidden reasoning channel (turn 4: 374
chunks, 78 visible, the first 296 hidden).

| turn (answer) | request sent | first chunk (Δ) | first answer text (Δ hidden) | first segment ready (Δ, chars) | synthesis | audio → playback | speech end → playback (desktop) |
|---|---|---|---|---|---|---|---|
| 1 (msg 2) | 1,363 | 2,933 (1.57 s) | 4,926 (1.99 s) | 4,928 (0.00, 22) | 1.35 s | 0.11 s | **7,052** |
| 2 (msg 4) | 1,392 | 3,002 (1.61 s) | 8,088 (5.09 s) | 8,155 (0.07, 63) | 1.89 s | 0.08 s | **10,785** |
| 3 (msg 6) | 1,459 | 3,116 (1.66 s) | 5,420 (2.30 s) | 5,435 (0.02, 13) | 1.24 s | 0.02 s | **7,352** |
| **4 (msg 8)** | 1,374 | 3,112 (1.74 s) | 7,679 (4.57 s) | 8,020 (0.34, **121**) | **3.85 s** | 0.06 s | **12,596** |
| 5 (msg 10) | 1,400 | 3,449 (2.05 s) | 4,749 (1.30 s) | 5,056 (0.31, 112) | 4.81 s | NOT RECORDED¹ | NOT RECORDED² |
| 6 (msg 12) | 41,209³ | 43,505 (2.30 s) | 47,188 (3.68 s) | 47,650 (0.46, 157) | 6.38 s | behind msg 10⁴ | NOT RECORDED² |

In every turn, the endpoint → request-sent interval (1.36–1.46 s) was the confirming
silence plus the 1.1 s resume grace, persistence, assembly and readiness. There was no
maintenance wait: every refresh had finished before the next request, including the
full re-prime at 20:13:57 (0/5,059), which ended before turn 3's request at 20:14:12.
Segment ready → synthesis submission was 0–1 ms in every turn.

¹ Segment 1 was played, but its playback reports were refused (409): it was voiced
before the answer was written, so the service had no hand-off recorded against the
message. ² The panel paired these utterances with the wrong message and answer (§3).
³ His utterance settled at 20:15:37, while turn 5 was still being answered, and was
held until turn 5's delivery had synthesised all 16 segments. ⁴ Answer 12's audio
was ready at 20:16:31; answer 10 was still playing until 20:17:02.

**The 13-second answer (turn 4, OBSERVED 12,596 ms):** confirming silence and grace
~1.3 s → request overhead 0.1 s → first output 1.74 s (946 tokens after the cached
persona) → **hidden reasoning 4.57 s** → first sentence complete 0.34 s → **its
synthesis 3.85 s** → playback 0.06 s. The two largest parts are the model's reasoning
(model work at MEDIUM) and the synthesis of a 121-character first sentence, spoken
whole.

His later report of a longest wait of about 15 s does not match any single recorded
interval, and is not assigned to one.

## 3. What was avoidable, and what was defective

1. **First-segment length (avoidable).** The segmenter cut a sentence at a pause only
   past 220 characters, so a long opening sentence was synthesised whole before she
   could say a word. Synthesis of his session's openings (`first_segment_probe.py`,
   resident worker, nothing else running, three repeats): message 8, 121 characters
   3.04–3.46 s, cut at its dash (69) 2.07–2.28 s; message 12, 157 characters
   3.44–3.52 s, cut at its dash (79) 2.14–2.40 s. In the session, under contention with
   her reasoning, those syntheses took 3.85 s and 6.38 s.
2. **A new turn committed while she was still speaking (defect in `b6c8937`).** With a
   single "current answer", committing turn 6 at 20:16:18 ended answer 10. Its
   remaining text was shown marked "Not spoken — Voice ended" while she spoke it for
   44 s more, and its later segments were absorbed into the new turn's record and then
   relabelled with answer 12's id (the −63,932 ms "gap"). The stall rule would also
   have dumped answer 12's text as "delayed" while it waited behind answer 10.
3. **Timing pairing (defect).** The panel paired utterance 6 with message 9's display
   and answer 10's playback, producing the negative figures.
4. **Unbound playback unrecorded (pre-existing record gap).** A segment handed over
   before its answer is written had no hand-off record, so both of its playback
   reports were refused.
5. **Not avoidable here:** the hidden reasoning (model work at MEDIUM, unchanged), and
   the ~1.3 s of confirmation and resume grace (unchanged, by his standing order).

## 4. Repairs

- **First segment's own pause rule** (`val_policy.speech_segments`). Once the first
  segment passes 60 characters without a sentence end, it is cut at its earliest
  comma, semicolon or dash (the unspaced em dash included) that leaves at least 24
  characters. It applies only to the first segment and only at a pause a reader would
  make. "My lord," is never spoken alone, and the exactness invariant holds (asserted
  under streaming).
- **Per-answer presentation** (`spokenPresentation.ts`, `voiceController.ts`, `App.tsx`):
  - Each answer has its own record, and a new turn ends nothing.
  - Segments carry the key of the answer that took them.
  - Stalls are judged on the silence of the whole output.
  - Timings pair only an utterance's own message and answer.
- **Unbound hand-offs recorded:**
  - **Service:** remembers the hand-off and writes it, at the time it happened, once
    the answer is named (`record_playback(observed_at=…)`).
  - **Desktop:** holds such playback reports until it knows the answer, then sends
    them with `observed_ms_ago`.

**Net effect, measured honestly.** `serve_variant.py` switched the rule off and on in
otherwise identical code: three sessions × three turns each, production instance, $0
(`measure-pause-off.json`, `measure-pause-on.json`). **The rule engaged in none of the
six measured answers:** with the spoken-path facts (§5) her answers opened with short
sentences (44–93 characters), each ending at a full stop or semicolon before any
qualifying pause. The medians of later turns (12.0 s off, 10.5 s on) are therefore
answer-to-answer variation, not the rule's effect, and are not claimed. The rule's
effect is DERIVED from the synthesis probe: on openings like messages 8 and 12 (two of
his six answers), about 0.9–1.3 s sooner to first audio with nothing else running.
Under contention it is likely larger, but that is not measured.

Tests: segmenter streaming cases (4 new; one earlier assertion kept word for word
with the rule off, reason written in); presentation rewritten per answer, including
his session's queued-turn sequence; a rendered thread test of it through the real
controller; held reports; the service recording an unbound hand-off with its real
time (streaming adapter paused after the first sentence).

## 5. Self-knowledge correction

In messages 8, 10 and 12 she invented:

- "a reply within about one second";
- a delay "usually due to network or local processing load rather than the model
  itself";
- advice: a wired connection, a GPU, a lower sample rate;
- an offer to "record a brief demonstration".

**The persona is unchanged.** The correction is a record-state block, `spoken_path`,
present only in a conversation he has spoken in or has Voice on in now
(`voice_session_active`, `conversation_sealed`; never typed-only, never merely
recalled). It sits after the cached persona prefix, so priming is unaffected, and
the ruled `capability_state` (books alone) is untouched.

It states:

- the path is local only, with no network;
- no response time is promised;
- the house's dated test figures, as a range and per stage, which are "not this
  conversation";
- whether it can be made faster is unknown to her — neither promise it nor rule it
  out;
- `timing_measurement: unavailable` — if asked, say plainly she cannot.

**Paraphrased checks** (local model, scratch store, spoken through the full voice
path, $0), each with differently worded questions:

| check | usual delay | "time yourself / is it my connection" | "what would it take for one second" |
|---|---|---|---|
| 1 (first wording) | 3/3 no promise, no network blame | no false offer; one placed the dated figure "in this session" | not asked |
| 2 (not this conversation; say you cannot) | 2/2 (one misheard "wait" as "weight" and asked) | 1/1 correct | 2/2 invented limits: "fixed… cannot be shortened by software", or 200 ms and "1–2 s of computation" |
| 3 (measured stages; the only figures you have) | 2/2 correct | 2/2 correct: cannot measure; connection not a factor | 1/2 used the measured stages; **1/2 invented hardware** ("single-core CPU", "Whisper… 1–2 s") |

None of the three errors of his session recurred in any check: no one-second promise,
no network diagnosis, no offer to record or measure. **Residual:** on hypothetical
"what would it take" questions, the model still sometimes speculates about hardware
and stage times it was not given. This matches GPT-OSS's declared production weakness
(fabrication), and is reported rather than tuned further.

## 6. Maintenance-probe wording (continuation §5)

`RESULT.md` §4a, WP3 §20 and evidence index §107 were corrected without rerunning the
probes:

- Both probes measure **time to the first streamed SSE event**; the payload was never
  inspected.
- The abort probe shows only that **closing the client did not shorten** the next
  request's wait.
- The collision results are **one-token requests** over an uncached prefix, and do not
  establish complete Voice latency or recognition under contention.
- The eviction explanation is from the **engine's source**.

The pushed commit message of `b8ce924` carries the earlier overstated wording; history
is not rewritten, and this record supersedes it.

## 7. Remaining, and the smallest decision

- **Hidden reasoning** (1.3–5.1 s in his session) is model work at MEDIUM. It is not
  changed and LOW is not reopened.
- **First output 1.6–2.3 s every turn:** only the persona prefix is reused. The
  conversation history (811–1,371 tokens) is recomputed each turn, because the per-turn
  envelope follows it and this engine keeps checkpoints only 11 tokens before each
  prompt's end. Reusing the history would need a checkpoint at its end: a
  conversation-level prime containing his conversation's content, which the priming
  ruling excluded. **Smallest decision:** authorise a conversation-level prime (local
  only, recorded like `prefix_prime`, qualified first on an isolated instance). DERIVED
  saving: about 1.2–1.8 s per later turn. Not measured.
- **A turn he speaks while she is thinking** waits for her previous answer's entire
  synthesis before its own cognition begins. In his session this cost nothing audible,
  because answer 10 was still playing when answer 12 was ready. Whether speaking during
  her thinking should interrupt her is turn-taking policy, and is his to decide.
- **Unverified:** paint and sound in the room.

Files:
- `first_segment_probe.py` and `first-segment-probe.json` (§3);
- `serve_variant.py`, `measure-pause-off.json` and `measure-pause-on.json` (§4);
- `measure-selfknowledge.json`, `measure-selfknowledge-2.json` and
  `measure-selfknowledge-3.json` (§5: synthetic scratch conversations; their
  multi-line answers are read whole from the scratch store in this record);
- `service-timelines-targeted.txt`: the scratch services' content-free timeline, prime,
  warm and endpoint lines; the full logs were not kept. The earlier runs' equivalents
  were renamed from `.log`, which the repository ignores, to `.txt`, so the files these
  records cite are in the tree.
