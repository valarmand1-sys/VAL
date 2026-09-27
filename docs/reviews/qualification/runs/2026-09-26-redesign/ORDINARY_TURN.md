# Milestone B — ordinary-turn waiting and wrong-turn responses: investigation record — 26 September 2026

Owner order "PREPARE THE LOW TIER-1 RELEASE, FIX FIRST-SESSION AND ROUTING DEFECTS,
THEN REDUCE ORDINARY-TURN WAITING", Milestone B. **Isolated from Milestone A's release
(`TIER1_RELEASE.md`); nothing here is in that release, and nothing here is deployed.**
Labels as in the other records: OBSERVED, DERIVED, NOT RECORDED. Every model call local,
$0.

## 6. Wrong-turn repetition (§6)

**The recorded cases** (`tier1-compare-A.json`, ordinary MEDIUM with the ordinary
request, 26 September 2026): d10 — after "Val, explain three ways to make a film scene
feel tense without using dialogue." and her 1,329-character answer, his "Thank you,
Val." drew a 1,293-character answer beginning with the same words; f08 — after "Give me
one line of advice on pacing a chase sequence." and her one-line answer, "Much
obliged." drew the advice again in slightly different words; f09 — after the
suspense/surprise explanation, "Nothing else for now, thank you." drew "I have taken
note of the state, my lord. No further action is required at this time."

**Which layer** (from the recorded calls and texts, before assuming):

- **Not a delivery or answer-association defect.** Each answer is its own `model_calls`
  row on his thanks message (`tokens_out` 629 / 319 / 150; `latency_ms` 17,721 /
  12,406 / 10,351) and the texts are **not** byte-identical to the previous answers
  (difflib similarity 0.83 and 0.86; f09's 0.05). The persisted answer is what the
  model generated for this call; nothing re-attached an earlier message.
- **Not request ordering.** The request is assembled as always: persona (system) →
  retained history (his question, her answer) → the record-state envelope → his
  current message, joined by the local wire canonicalization into one user message
  after her answer (envelope, blank line, "Thank you, Val."). The current turn is last,
  as the envelope's own note says it is.
- **A model-generated response to the wrong conversational turn.** For d10 and f08 the
  model **re-answered the previous question**, paraphrased (0.83/0.86 similarity, not a
  copy); for f09 it answered the envelope ("taken note of the state"). MEDIUM's hidden
  reasoning on d10 shows the mechanism: the model deliberates over the whole request
  and treats a bare thanks as continuation of the previous exchange rather than as a
  turn of its own.

**Repair — to be established in this milestone**, not assumed: the candidate causes
are (a) the joined user message (envelope + his words as one message, so his words sit
after ~3.6 KB of JSON), and (b) the absence, in the ordinary request, of any framing
that the current message is a new turn to be answered on its own terms. Both are
request construction, which is Core's. The Tier-1 route already avoids the failure for
eligible thanks by construction (a smaller request that says what the turn is); §6
asks that ordinary MEDIUM not mishandle thanks in **pending-work** contexts either,
where the Tier-1 route will never carry them. _Investigation and tests: below, when done._

## 7. Overlap safe preparation with turn confirmation (§7)

**Generation-free prefill: the runtime does not offer it** (OBSERVED,
`runtime_capabilities_probe.py` → `runtime-capabilities-probe.json`). A chat completion
with `max_tokens: 0` is refused by LM Studio's schema ("maxPredictedTokens … must be
greater than or equal to 1"); the smallest request that processes a prompt is a
**one-token generation** (`max_tokens: 1`; an 8,065-token cold prompt took 10.5 s and
reported `completion_tokens: 0`). So any "conversation-prefix prefill" on this runtime
is what the persona prime already is — a one-token generation request whose token is
discarded — and it is described as that, never as prefill without generation. The
experiment the order authorises therefore stands on the same footing as the persona
prime: a distinct cache entry per (persona + exact conversation prefix + effort),
competing for the two or three slots the runtime keeps (`TIER1_RELEASE.md` §2), with
setup, refresh and invalidation each a one-token request of ~1–7 s. _Its measurement:
pending._

**The ~2.2 s before dispatch, decomposed per turn** (OBSERVED, 228 turns of `Q-low` and
`B-medium-noqwen`, the service's own marks, ms; medians with p90 and max — consecutive
marks of the same turns, not unrelated medians summed):

| from → to | median | p90 | max |
|---|---|---|---|
| speech end → endpoint (the recognizer's confirming silence and final decode; driver clock) | ~950 | ~1,050 | ~1,400 |
| endpoint → final transcript received | 126 | 159 | 410 |
| final transcript received → processed | 9 | 18 | 28 |
| transcript processed → owner turn submitted (**the fixed 1.1 s resume window**) | 1,107 | 1,122 | 1,130 |
| submitted → his message persisted (open, scope, append) | ~7 | ~10 | 80 |
| persisted → egress decided → assembled (history, recall gate, envelope) | ~10 | ~14 | 32 |
| assembled → runtime ready → exact preflight → dispatch | 35 typical; **645 p90, 1,279 max** | | |

**Core's own work between his settled words and the request leaving is ~80 ms.** The
2.2 s is the endpoint (0.95 s) and the window (1.1 s), both held by §7 of the order, and
the only elastic part is the exact preflight when it waits behind a prime prefilling on
the runtime (p90 645 ms — `TIER1_RELEASE.md` §3). So there is nothing material of
Core's to overlap with confirmation: reading the thread, resolving scope and building
the envelope are ~20 ms together. **What could overlap is model work** — the ~1.1 s of
prompt processing after the persona checkpoint that begins at dispatch — and on this
runtime that is a one-token generation request (above) whose cache entry competes with
the two the primes keep. That experiment is the remaining §7 item.

## 8. Owner precedence over an obsolete unspoken answer (§8)

**Engine-level cancellation, observed rather than assumed** (`runtime_capabilities_probe.py`,
`prefill_abandon_probe.py`):

- **Token generation stops when the client closes the stream.** A 900-token essay was
  requested as a stream and the connection closed after 1.5 s (44 chunks received); a
  tiny request sent at once completed in **0.20 s** (control, nothing abandoned:
  0.26 s). On a `--parallel 1` instance a generation still running would have queued
  that request for ~10 s; it did not, so the engine released the slot on disconnect.
- **Prefill does not stop.** A cold ~8k-token prompt was requested as a stream and the
  connection closed 0.5 s in, before any token; the tiny request that followed waited
  **10.1 s** — the whole prefill ran to its end with no client attached. So
  cancellation releases the engine only once generation has begun; an abandoned request
  still in prefill occupies the lane for the remainder of its prefill (~7–10 s on a
  cold 5–8k prompt, ~1 s on the ~800-token tail after a warm checkpoint). That bounds
  what owner precedence can promise: immediate release when the obsolete answer is
  already generating, a wait of up to the remaining prefill when it is not.

This is the mechanism §8 would use: Core closes the abandoned answer's stream, records
the interrupted generation truthfully (a call row with its terminal state, no message
fabricated, nothing claimed delivered), and the new confirmed turn takes the lane.
Client disconnection alone was not taken as proof; the following request's latency
was. _Implementation of the precedence semantics: pending._

## 9. Ordinary MEDIUM request costs (§9)

**Decomposition from the existing runs first** (OBSERVED; the 207 ordinary MEDIUM turns
of `Q-low` and `B-medium-noqwen`, service timelines, ms from the recognizer's
endpoint; the driver's speech end lies ~0.95 s before the endpoint):

| stage | median | p90 | max |
|---|---|---|---|
| dispatch → first provider event (prompt processing of the ~800 tokens after the persona checkpoint, plus the first token) | 1,720 | 2,320 | 3,864 |
| first provider event → first user-facing answer token (**hidden reasoning**) | **4,066** | **7,224** | 18,252 |
| first answer text → first speech-safe segment | 0 | 0 | 0 |
| TTS start → first audio at the sink | 614 | 767 | 870 |
| endpoint → first audio at the sink | 8,008 | 11,524 | 21,966 |

Hidden reasoning is **51% of the wait** at the median turn and the whole of its
variance; prompt processing is a steady ~1.7 s (of which ~1.1 s is the tail after the
persona checkpoint, at ~750 tok/s — `TIER1_COMPARISON.md` §4/§5); first audio a steady
~0.6 s. The calls: 5,970 tokens in at the median (6,400 p90, 7,550 max, as history
grows), 288–300 tokens out at the median (520–530 p90, up to 1,206 — reasoning and
answer together).

So the remaining delay on an ordinary turn is not one thing: ~2.2 s before Core sees
the turn (endpoint and window, held), ~1.7 s of prompt processing that is request
shape, ~4 s of MEDIUM's reasoning that is model work at the kept effort, ~0.6 s of
voice. What a bounded request improvement could touch is the 1.7 s (the ~800-token
tail: envelope ~3.6 KB of JSON, the Tier-1-style question of whether every field is
needed on every turn) — and only that. _Controlled comparison: pending._
