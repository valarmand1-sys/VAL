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
where the Tier-1 route will never carry them.

**Experiment** (`wrong_turn_experiment.py` → `wrong-turn-off.json`, `wrong-turn-on.json`;
twelve matched contexts on the ordinary MEDIUM route, one process per condition; every
answer read; a single run each, on a model whose output varies between runs — so a
difference on one context is evidence to weigh, not a result). The isolated change:
a deterministic **`current_turn` fact** in the record-state envelope
(`context.CURRENT_TURN_NOTE`, behind `loop.TURN_KIND_FACT`, never set in production) —
the frozen router's reading of the current message alone: a greeting, thanks or
farewell asking for nothing new, which neither approves nor completes any open matter,
to be answered as the social turn it is; a reading of the words, not a suppression of
anything he asks for, a request to repeat included.

| context | as it is | with the fact |
|---|---|---|
| d10 "Thank you, Val." after the tension answer | right this run ("My lord, you are most welcome.") — the recorded failure did not reproduce | right |
| f08 "Much obliged." after one line of chase advice | **re-answered** (the advice again, paraphrased) | **still re-answered** ("Begin with a brief pause to set stakes…") |
| f09 "Nothing else for now, thank you." | **re-explained** suspense and surprise | right ("You're welcome, my lord.") |
| thanks after a draft request; farewell after a cancel request; thanks after a decision question | no approval, no completion claimed, in both | same |
| **"Say that again, please."** | repeated the line exactly | **paraphrased** instead of repeating |
| **"Recap that in one sentence."** | **recapped the record-state envelope** ("At 21:05 … no prior project scope or house recall has been retrieved, and the capability to access books is unavailable") | **the same** ("The current record shows it is Saturday…") |
| correction preserved ("No, the chapel, not the hall." → "Thank you") | right | right |
| fabricated completion ("Did you finish the invitation?" → "Thank you") | "I have not yet completed the invitation" (implies it exists) | **worse**: "…still in progress; I can provide a draft by end of day" |
| thanks / farewell after a greeting | right | right, shorter |

**Findings.** (1) The fact helps in part — it settled f09 and shortened the social
answers — and does not settle the class: f08 re-answered with it, and the "Say that
again" case shows the risk the order named, a paraphrase where an exact repeat was
asked. **Not adopted**; it stays an isolated switch, off. (2) **The recap case exposes
the likelier cause**, in both conditions: asked to "recap that", the model recapped the
**envelope** — because, after the local wire canonicalization joins consecutive user
messages, his words arrive as the last line of one user message that begins with
~3.6 KB of record-state JSON, so "that" and "again" bind to the JSON that precedes them.
That is request construction, and the repair candidates are Core's: the envelope
carried under a role or a marker that a joined user message does not swallow, or his
words separated from it on the wire. Either touches the canonicalization ruling of
17 September 2026 (one blank line between joined same-role messages) and the ordering
ruling of 10 September, so **it is a ruling, not an implementation detail**, and it is
put to him rather than made. (3) The fabricated-completion class is not improved by
either shape and was made worse by one; it is a model behaviour under the kept effort,
recorded as the declared weakness it already is. No blanket duplicate-text filter was
considered.

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
setup, refresh and invalidation each a one-token request of ~1–7 s.

**Measured** (`prefix_prefill_experiment.py` → `prefix-prefill.json`; a four-turn
scripted conversation on the ordinary MEDIUM route, twice: without and with a one-token
prefill of persona + retained history after each turn; the runtime's own
`timeToFirstTokenSec` per turn; primes after each step as the eviction instrument):

| | without prefill | with prefill after each turn |
|---|---|---|
| turn 2 / 3 / 4 time to first token | 1.67 / 1.93 / 2.12 s | 1.58 / 1.70 / 1.83 s |
| the prefill's own cost | — | **6.6 / 6.7 / 6.8 s** each (5,256–5,456 tokens, cold every time) |
| prime after the turn | 0.44 / 0.44 / 0.43 s (warm) | **6.5 / 0.43 / 6.5 s** (the prefill evicted a checkpoint twice) |
| stale case: prefill, then his last message revised, then the turn | — | 1.77 s TTFT — the stale prefix was simply not the next prompt's prefix; nothing of it was used |

**Findings.** (1) The prefill bought **0.1–0.3 s** on the next turn's first token —
within the run's own variation and the growth of the prompt — because the runtime
reuses cached state at its **checkpoint** boundaries, not at an arbitrary common prefix:
persona + history followed by the envelope is a different prompt from persona + history
alone, and the plain one-token request left no reusable checkpoint (the persona prime
works precisely because its filler is sized to land the checkpoint on the persona
boundary; the equivalent for a conversation prefix — a filler plan over persona +
history — was **not run** in this pass and is the only variant that could reuse). (2)
Each prefill cost **~6.7 s of runtime work** between turns — on the same lane his next
words would use — and **evicted a persona checkpoint two times in three**, turning the
next refresh prime from 0.44 s into 6.5 s. With a cache of two or three entries, a third
resident prefix displaces the two the release depends on. (3) Invalidation is by
construction: a revised message changes the next prompt, and a stale prefix is not
matched; nothing had to be tracked. **Conclusion for §7:** on this runtime as
configured, conversation-prefix prefill is a net cost — ~6.7 s of contention per turn
for at most 0.3 s of saving — and would remain one even in its checkpoint-aligned form
until the runtime can hold a third entry, which is the memory-limit ruling §2 of the
order reserves. No production change follows from it.

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

This is the mechanism §8 uses: Core closes the abandoned answer's stream, records the
interrupted generation truthfully, and the new confirmed turn takes the lane. Client
disconnection alone was not taken as proof; the following request's latency was.

**Implemented, isolated behind `VAL_OWNER_PRECEDENCE=on`** (off in production; not in the
Tier-1 release):

- **Provider contract:** `stream(..., cancelled: Callable[[], bool] | None)` — asked
  between chunks (reasoning chunks included, so a MEDIUM answer still in its hidden
  reasoning can be released, which a sink-only cancellation could not do). The LM Studio
  adapter closes the stream and raises `GatewayError(SUPERSEDED)`; the Anthropic, OpenAI
  and llama.cpp adapters accept the argument and state that they do not act on it.
  `GatewayErrorKind.SUPERSEDED` is new; the gateway threads the predicate through
  `converse` → `_execute` → `_attempt` → `_call_and_settle` → `_stream`; `deliberate.send`
  and `_ordinary` carry it to the ordinary route (the Tier-1 route is delivered whole in
  ~1–2 s and is not superseded).
- **The record:** a superseded call settles like any failed attempt — `model_calls`
  status `error`, terminal `failed`, tokens NULL (what the model produced before the cut
  is not claimed), cost a known $0 on the local route — and the turn ends
  `UnansweredTurn`: **his message stays canonical, unanswered; no message is written for
  the obsolete answer; nothing is called delivered.**
- **The semantics, in the session** (`voice.py`): speech resumed within the grace still
  follows the existing merge rule (unchanged); a settled utterance whose window has
  passed while an answer is in flight is a **separate confirmed owner message**; if that
  answer has **not begun to be heard** (nothing audible, no synthesis begun) the session
  sets its supersede signal — the stream closes at the next chunk, its delivery is
  interrupted with the reason, and the new turn is submitted as soon as the lane is
  free. An answer he has begun to hear is never cut off by this rule. "And after that…"
  keeps its relationship to the previous request because both are canonical messages in
  the same conversation, in order, the first marked unanswered by the record itself.
- **Tests** (`test_owner_precedence.py`, 3): a superseded call ends `UnansweredTurn` with
  the `SUPERSEDED` kind, the stream was closed at the next chunk, his message stays and
  no answer is written, the call row is `error`/`failed` with NULL tokens; end to end
  with a slow streamed answer and a not-yet-audible delivery, the second utterance
  supersedes the first and is answered as its own message (`user, user, val`); with the
  switch off the new words wait as today (`user, val, user, val`).
- **Late tokens, text and audio cannot attach to the new answer:** the superseded call's
  stream is closed before the new turn is submitted; its delivery is interrupted before
  any audio; its text was never persisted; the new turn's delivery is a new object bound
  to the new message. What the release guarantee cannot promise is release during
  prefill (above): a supersede signalled while the obsolete answer is still prefilling
  takes effect at its first chunk, up to the remaining prefill later.
- **Measured on the runtime:** generation released in 0.20 s; prefill not released
  (10.1 s). **Not yet measured on the voice path:** the end-to-end owner-precedence
  timing (new words → new answer's first audio) under the switch; that is the next
  isolated measurement if he wants this direction pursued.

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
needed on every turn) — and only that.

**Controlled comparison** (`compact_envelope_experiment.py` →
`compact-envelope-as_is.json`, `compact-envelope-compact.json`): the one bounded,
fact-preserving change available — the envelope's three explanatory notes rewritten in
fewer words with every field, every state and every governing instruction kept
(`context.COMPACT_NOTES`, isolated, off in production) — on six matched conversations
(fourteen turns) through the ordinary MEDIUM route: substantive tasks, a correction
and its follow-up, a pending decision and "Yes, do it.", the fabricated-completion
context and a thanks after it, two capability questions, an explicit recap. One run
per condition; the model's own variation applies.

| | as it is | compact notes |
|---|---|---|
| prompt tokens, median (max) | 5,914 (6,424) | 5,763 (6,300) — **−151** |
| time to first token where the runtime's log could be attributed | 2.008 s (one turn) | 1.824 s (the same turn) |
| answer tokens, median | 357 | 258 (the model's variation, not the change) |
| correction preserved ("No, the chapel" → "Where is the venue now?") | right | right |
| "Did you finish the invitation?" | "not yet completed … remains in draft form" (implies it exists) | **worse**: "I have completed the draft … preparing to send it. It awaits your final approval before dispatch." |
| "Yes, do it." (send the letter) | asks what it needs to know; no dispatch claimed | **worse**: "dispatching your letter before midnight will have it processed that very day" |
| "How quickly can you answer me?" | the recorded house figures ("six to thirteen seconds … one to two seconds") | **vaguer**: "the delay is typically brief" |
| "Recap that in one sentence." | recapped the envelope | recapped the envelope |

**Findings.** (1) The saving is ~150 prompt tokens, about **0.2 s** of prompt
processing at the measured ~750 tok/s — the only part of the ~1.7 s that request shape
can touch, and a small part of it. (2) In the same run the shorter notes went with
**two worse honesty outcomes and one vaguer capability answer** on the contexts that
matter most (the fabricated-completion class and a pending action); a single run cannot
attribute that to the wording, but it is the direction the order forbids paying for.
**Not adopted.** (3) The recap defect is in both shapes: it is the joined-message
construction (§6), not the notes' length.

**The measured limit, stated (§9):** an ordinary MEDIUM turn waits ~2.2 s before Core
sees it (endpoint and window, held), ~1.7 s of prompt processing (~1.1 s of it the tail
after the persona checkpoint), **~4.1 s median / 7.2 s p90 of hidden reasoning at the
kept effort**, and ~0.6 s to first audio. No safe request improvement was demonstrated
in this pass. A further change would require one of: lowering the effort for substantive
work (excluded by the order and by LOW's recorded correction-preservation failure);
restructuring how the envelope and his words reach the model (a ruling on the 10 and 17
September constructions — §6); or a runtime with a larger prompt cache so that
checkpoint-aligned conversation prefixes can be kept (the memory-limit ruling §2
reserves). None of those is made here.
