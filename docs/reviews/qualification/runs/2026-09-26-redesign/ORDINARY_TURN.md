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

---

# Release-gaps order of 26 September 2026 — the Milestone B corrections (§1–§5)

Same labels. Nothing deployed; `VAL_OWNER_PRECEDENCE` is unset in production; the
experiment switches are off in source. Every model call local at a known $0.

## 12. The cache and prefill conclusions, corrected (§5)

**The two descriptions reconciled, from the installed source and the engine's own log.**
The runtime is LM Studio's `mlx-llm` engine 1.11.0; its vendored generation package
(`app-mlx-generate-mac14-arm64@34`, `mlx_engine`) wraps the model's KV cache in
`CacheWrapper`, whose history is `LRUPromptCache(max_size=10)` from `mlx_lm.models.cache`
(`history_capacity` defaults to 10 in the wrapper's constructor; the model kit passes
nothing else; no LM Studio setting reaches it — the "ten entries" of the earlier
description). What makes two or three of them usable for us is how the store is fed and
emptied, all of it in source:

- **Two insertions per distinct request.** During a request's prefill a **checkpoint**
  is stored at `total_prompt_tokens − 11` (cache type `user`); at the *next* request the
  previous request's whole finished state (prompt plus generated tokens) is stored as a
  snapshot (`assistant`). A prompt whose checkpoint position is already inside the cached
  prefix stores no new checkpoint.
- **A hit renews nothing.** `fetch_nearest_cache` reads; only `insert_cache` pushes onto
  the LRU. An entry's position is its insertion order, however often it is used.
- **Identical requests replace, distinct ones add.** Re-inserting the same token sequence
  replaces the trie's value and re-pushes the same key; a different sequence is a new
  entry. This is why a prime repeated during idleness stayed warm at 5, 30 and 90 s
  (`TIER1_RELEASE.md` §2) while turns and unrelated prompts aged it out.
- **Eviction alternates between the two queues.** Over ten entries, `CacheOrder.pop`
  takes from the `assistant` deque while it is at least as long as the `user` deque,
  else from `user` — so the oldest checkpoints go once the snapshots have been thinned.
- **GPT-OSS's cache is not trimmable** (its sliding-window layers use `RotatingKVCache`,
  whose `is_trimmable` is false once past the window), so a stored *longer* entry cannot
  be trimmed back to a shared prefix and prefixes are never popped as redundant: reuse
  needs a stored entry that is **exactly** a prefix of the request. Without the persona
  checkpoint, a turn whose prompt diverges inside the envelope from an earlier turn's
  checkpoint reuses **nothing** — `0/5876 tokens from cache` in the P1 precedence run
  after the Partner prime had stood aside.

**Observed directly** (`~/.lmstudio/server-logs/2026-09/2026-09-26.2.log`, the engine's
`Prompt cache: using N/M tokens from cache` lines, 2,353 of them today): in the W1
desktop run the light checkpoint was hit at 22:35:07 (`5048/5059`) and gone at 22:35:21
after one more turn (`0/5059`), fourteen insertions after it was stored; in the eviction
probe's window (19:49–19:52) the primes stayed warm through repeated identical primes and
went cold after unrelated 171-token prompts. **The mechanism is established, not
inferred.** Per-entry memory, computed from the model's configuration (12 full-attention
layers × 8 KV heads × 64 dims × 2 bytes × 2, sliding layers at 128 tokens): about
**121 MB** for a 5,048-token checkpoint, 139 MB at 5,800 tokens, 155 MB at 6,500 — so
ten entries are on the order of 1.2–1.5 GB. **Not measured** (the engine logs no
`nbytes`); a computed basis, labelled as such.

**What this means for the earlier recommendation.** A third entry is not the question
and more system memory would not change the behaviour: the store already holds ten,
and the persona checkpoint is lost to *insertion order*, not to a byte limit or a macOS
memory limit. Two supported paths exist and neither is available without a ruling:
`history_capacity` is a constructor default with no exposed setting (changing it is an
**engine patch**), and renewing a checkpoint on a hit is a change to `mlx_lm`'s store
(also a patch). The earlier suggestion of a memory-limit increase is **withdrawn**; the
option, if he wants it, is the engine patch, with the computed ~120–155 MB per additional
entry as its resource basis.

**The prefix-prefill conclusion, narrowed to what was tested.** `prefix_prefill_experiment.py`
established the *cost* of a plain one-token request over persona + reconstructed history
(6.6–6.8 s each, cold every time) and that such a request evicted a checkpoint. It did
**not** test a checkpoint-aligned conversation prefix: its body set no reasoning effort
(so its rendering differed from the next Core request's `Reasoning: medium` header from
the first tokens), it reconstructed messages rather than reusing Core's construction (no
rendered-token parity), it primed the persona between the prefill and the next turn, and
its two conditions generated their own histories. Its cold cost is therefore the cost of
a prompt that shared **nothing** with the stored entries — as the mechanism above
predicts — and says nothing about a prefill whose rendering matches the next request
token for token and whose checkpoint lands on the boundary the next request extends.
**Whether that experiment is worth running:** the engine supports it (a checkpoint at
`prompt − 11` on a `user`-typed request, exactly what the persona prime already
exploits); the concrete question it would answer is whether a *conversation-level* prime
— the persona and the retained history through her last answer, sized so the checkpoint
lands at the end of her last message — lets the next turn prefill only the envelope and
his words. Its cost, under the mechanism, is the *incremental* history (≈1–2 s once per
turn, not 6.7 s), and its price is one more insertion per turn against the ten-entry
store. This is the conversation-content priming the 25 September ruling excluded and
CLAUDE.md records as the open decision; it is **not run here** — the bounded matched
comparison waits on that ruling, and on the request-construction result (§11), which
changes what the stable prefix is.

## 10. Owner precedence, corrected (§1–§3)

**What was wrong with §8.** Its supplied test made "And after that, tell me about the
orchard." cancel the garden answer: a continuation read as a cancellation, inferred from
the arrival of words rather than from the words. Its heard boundary was "no synthesis
begun", not "not begun to be heard". Both are corrected; the switch stays
`VAL_OWNER_PRECEDENCE`, off in production.

**The decision is his words' (`val_policy.precedence.follow_up`, deterministic, no model
call, 35 policy cases):**

| his next words, while an unheard answer is being made | relation | what happens |
|---|---|---|
| "Stop." · "Never mind." · "Forget it, Val." · "Scratch that." · "Hold on." — a stop and nothing else | **stop** | the answer is set aside; his words go on the record; **no new answer is asked for** (`OWNER_STOP`, no cognition call); the desktop says "Stopped at your word — nothing was said." |
| "Actually, never mind. Tell me about the venue instead." · "No, the second one." · "Wait — I meant the reader." · "…instead." · "Let me rephrase: …" | **replacement** | the answer is set aside (stream closed, call recorded `superseded` with its reason on the measurement row, usage NULL, no message); his earlier message stays as it was; the replacement is answered as its own message |
| "And after that, …" · "Also, …" · "Then …" · "… too." · "While you're at it, …" | **continuation** | nothing is set aside; both are answered, in order |
| anything else — "What time is the reading?", a greeting, a question with "stop" inside it | **ambiguous** | nothing is set aside; the new words wait, as they always did |

A marker must open what he said, or be one of the few that mean replacement wherever
they stand ("instead", "never mind", "scratch that", "I meant"…), before an answer is set
aside; the rules fail toward keeping both requests.

**The heard boundary is the speakers.** With a desktop collecting the audio, "heard"
is the desktop's `playback_started` report for the answer in flight — not synthesis, not
the service's hand-off. Two consequences follow, both new:

- **Onset holds, confirmation decides.** The existing barge-in stopped any active
  delivery the moment his speech began, heard or not — for an unheard answer that was a
  cancellation inferred from an arrival. With precedence on, his onset against an
  *unheard* answer now **holds** its hand-off (`speech_hold`: nothing is handed to the
  desktop while his words are in the air or await decision), and the decision at
  confirmation either discards the held audio (stop, replacement) or releases it
  (continuation, ambiguous), so the earlier answer plays after him. Once playback has
  begun, barge-in is untouched: his onset stops the speakers as before, and his words are
  then an ordinary next turn behind the interrupted answer (P3, P3b below).
- **Synthesis under way but nothing played is still unheard** and a replacement still
  invalidates it; **"speaking" in the session's progress now means reported playback**
  when a desktop is collecting (the P2 run showed "speaking" while every segment was
  still held).

**The record.** A superseded call: `model_calls.status = error`, `terminal_state =
failed`, `tokens_out` NULL (never zero), and `model_call_measurements.runtime_diagnostics
->'superseded'->>'reason'` naming the supersession — distinguishable from an ordinary
failure on the same rows every call gets. A stop turn: his message, no call, the
unanswered outcome's reason `owner_stop`. The session view carries `superseded` (kind,
the two utterances, `heard: false`); the desktop shows the stop line, or "Her earlier
answer was set aside for this." while the replacement is answered. Late tokens attach to
nothing: the interrupted delivery ignores further text, the replacement's message is
clean (asserted), and a playback report for a segment never handed over is refused
(409). **The close no longer waits for the next chunk:** the LM Studio adapter watches
the superseded flag and closes the stream at once, so a runtime that streams nothing
while it prefills is disconnected the moment the decision is made — and **a prefill in
progress still runs to its end**, in the server's own words ("if the model is busy
processing the prompt, it will finish first").

Tests: `test_owner_precedence.py` (9: recorded as such; replacement; continuation
regression; ambiguous; stop alone; heard by report → not cut; synthesis-only → still
unheard; switch off; held then played after a continuation), `test_precedence.py` (35),
desktop `spokenThread.test.tsx` (+3).

### 10.1 Measured on the real service (§3)

Harness: `run_precedence.sh` → `precedence_drive.py` (the driver is the microphone and a
software player that reports playback as the desktop does; the second phrase is spoken
on a trigger) → `precedence_extract.py` (`precedence-P*-summary.json`; the service's
own `voice precedence` lines and turn timelines on the shared monotonic clock; the
store's calls, deliveries and playbacks). **Boundaries:** these are service and software-
player figures; the desktop-path figures are in §10.2; nothing here is acoustic. The
first phrase is always "Tell me about the invitation for the reading." Runs marked †
began one second after Voice On, before the primes had landed, and their absolute
figures carry that cold start; the reruns (P1c, P3b, P7c) began after Ready. A 1.5 s
trigger fell inside the resume grace and joined the two phrases into one utterance
(P1b: the correct existing behaviour, not a precedence case), so the separate-turn
reruns used 3.0 s.

| case | his second words, when | relation → outcome | speech end → confirmation | decision → stream closed | decision → the superseded thread ended | replacement dispatched after the decision | his speech end → replacement's first audio | record |
|---|---|---|---|---|---|---|---|---|
| **P1c** replacement during MEDIUM reasoning (3.0 s after the first phrase; warm) | "Actually, never mind. Tell me about the venue instead." | replacement → **superseded** | 2.01 s | **0.015 s** | 0.028 s | 0.047 s | 12.9 s (the replacement's own MEDIUM answer: visible text 10.0 s after dispatch) | messages user, user, val(venue); the superseded call `error/failed`, tokens NULL, reason on the measurement row |
| P1† same, one second after Voice On | same | replacement → superseded | 3.25 s | 7.77 s — the **cold prefill** of the first turn (both primes had stood aside; engine log `0/5876`) | 7.78 s | 0.037 s | 30.0 s (the replacement prefilled cold as well) | as above |
| **P7** a stop alone (1.5 s; heard as "Nevermind, VAL.") | "Never mind, Val." | **stop → superseded, nothing asked for** | 2.17 s | 0.015 s | 0.028 s | — (no cognition call) | — | messages user, user; one call, the superseded one; `owner_stop` |
| P7c same, 3.0 s — heard as "Nevermind, **VOWL**." | | replacement (the misheard name is not stripped as the address) → superseded, then answered about VOWL | 2.19 s | 0.011 s | 0.029 s | | | a driver-voice artefact; the words as heard were answered |
| **P2** replacement whose onset came when text had begun (`progress:writing`) | same as P1c | replacement → superseded — **her whole answer had finished before his words were confirmed**; his onset **held** every segment, so none was played; at the decision the held audio was discarded | 2.14 s | — (the call had completed; its message stands, marked `interrupted: superseded`, 188 characters at the sink, **nothing** in the playback record) | 0.19 s | 0.051 s | 20.5 s | messages user, val(unheard), user, val |
| **P2b, P2c** replacement whose onset was meant to fall after text began and before playback (`progress:writing`, then `writing,voicing`) | same | P2b: the stage passed between two 100 ms polls and the trigger never fired (one turn only). P2c: by the time his onset was detected (~0.5 s), the software player — which plays the instant a segment is handed over — had reported playback, so the answer counted as **heard** and barge-in took it; both answered | 2.11 s | — | — | — | — | **the window between first text and first playback (0.3–0.9 s on this system) is shorter than onset detection**; the case is proved by `test_synthesis_under_way_but_nothing_played_is_still_unheard`, not reproduced live |
| **P3, P3b** replacement during playback (`played`) | same | **barge-in** — his onset stopped the speakers ("the owner began speaking"); no precedence decision; both answered in order | 2.03 / 2.07 s | — | — | — | — | user, val(interrupted at 52 chars), user, val |
| **P5** continuation (heard "And off to that, tell me about the venue.") | | continuation → **kept**; both answered in order; the first's audio held during his words, then played | 3.67 s | — | — | (waited for the first answer: submitted 21.2 s after his speech end) | 32.1 s | user, val, user, val; nothing superseded |
| **P8** ambiguous ("What time is the reading?") | | ambiguous → **kept**; both answered | 2.05 s | — | — | (12.1 s) | 16.6 s | user, val, user, val |
| **P6** control, switch off | as P1c | no decision; the new words waited | 17.7 s (behind the whole first answer) | — | — | — | — | user, val, user, val |
| **P4, P4c** replacement during a **cold prefill** (checkpoints evicted just before the first phrase) | as P1c | replacement → superseded; the close reached the server at once (engine log: "Client disconnected. Stopping generation… if the model is busy processing the prompt, it will finish first") — **the server finished the prefill and stopped, but never closed its side**: the reader thread stayed blocked and, because the session waited for that thread, the replacement was never dispatched in 90 s | 2.9–4.4 s | (P4: 16.3 s; P4c: never) | | | | **a defect, repaired: §10 "the superseded thread is not waited for"**; remeasured as P4d below |

| **P4d** the same on the repaired code (checkpoints evicted; the first turn prefilling cold) | as P1c | replacement → superseded; **his replacement went out at once** and waited at the runtime | 3.33 s | — (no chunk ever came; the reader thread stayed blocked) | not within the run: the superseded call's row is written when its read ends — **up to the adapter's 600 s read timeout** | **0.03 s** | 16.7 s (dispatch → first visible text **12.3 s** against 10.0 s warm in P1c: the superseded prefill's remainder and its own cold prefill) | user, user, val(venue); the superseded call's record lands late — a stated limit |

**What the table says.** Where the runtime is generating, a replacement or a stop ends
the obsolete call within **15 ms** of the decision and the replacement is dispatched
within **50 ms** — the whole precedence mechanism costs nothing he can hear, and the
time to his replacement's first audio is his replacement's own MEDIUM turn (10–13 s here,
which the ~1 s goal is not, and which §9 already attributed to hidden reasoning). Where
the runtime is **prefilling**, nothing the client does stops it: the engine's own words,
and 7 s of cold prefill or up to 16 s when primes and a cold turn stack, are the
remaining delay; after the repair his replacement is dispatched at once and waits at the
runtime behind that prefill, which the P4d row measures. A stop asks for nothing.
Playback already begun is barge-in's, untouched. The direct probe's 0.20 s is not
presented as voice performance anywhere in this table. **Two stated limits of the prefill
case:** the replacement's own answer then pays its own cold prefill too (the eviction that
made the case is the same store behaviour §12 describes), and the superseded call's
record — status, NULL usage, the reason — is written only when its blocked read ends,
which on a socket the runtime keeps open is the adapter's **600 s** read timeout; until
then the row is absent, not wrong.

**Late tokens, audio and completion events.** In every superseded run the superseded call
wrote no message and its tokens stayed NULL; the replacement's message carried no text of
the superseded answer; the delivery record of the superseded answer, where one existed,
says `interrupted` with the supersession as its reason; and the driver's playback reports
for segments never handed over were **refused (409)** — three of them in P7c, one in P1
— never attached to a turn. The P2 record also shows a boundary worth stating: the
delivery row's "delivered" count is the **sink** (188 characters reached the hand-off),
the playback table is the **desktop** (nothing), and hearing is the latter.

### 10.2 Through the real desktop (§3)

Same method as `TIER1_RELEASE.md` §8.3 (the unmodified frontend, its dev server, headless
Brave with a WAV microphone, `run_desktop_integration.sh` with `PRECEDENCE=on`), the
second phrase spoken 3.0 s after the first's speech end (past the resume grace), warm
runtime, speech after Ready. Desktop-output boundary: the frontend's own report of
playback start; no speaker. Records `desktop-integration-D*.json` and their service logs.

| case | relation → outcome | decision → stream closed | what the desktop displayed | his second speech end → replacement's first playback (desktop) | record |
|---|---|---|---|---|---|
| **D1** replacement during MEDIUM reasoning | replacement → superseded | 0.019 s (thread ended 0.031 s) | "Her earlier answer was set aside for this." beside the stage line while the venue was answered | 13.9 s (the replacement's own MEDIUM turn: visible text 12.3 s after its endpoint) | user, user, val(venue); the superseded call `error/failed` |
| **D5** continuation ("And after that, tell me about the venue.") | continuation → **kept** | — | nothing about precedence; "Your next words are waiting for her current answer." | 16.2 s (behind the first answer, which **was played**: its segments `playback_started`/`completed` before the second's) | user, val, user, val |
| **D7** a stop alone (heard "Nevermind, VAL.") | stop → superseded, nothing asked for | 0.021 s (thread ended 0.029 s) | **"Stopped at your word — nothing was said."** | — (no answer, by his word) | user, user; one call, the superseded one |
| **D6** control, switch off | no decision | — | the queue line only | 10.6 s, behind the whole first answer | user, val, user, val |

Voice On → Ready in these runs: 6.2 / 13.4 / 6.5 / 7.2 s (service), displayed within
0.1 s of it each time.

## 11. The request-construction repair experiment (§4)

**Authorised as an isolated exception** to the request-ordering ruling (10 September)
and the same-role canonicalization ruling (17 September); implemented behind
`context.ENVELOPE_IN_SYSTEM` (off in source, set only by the experiment's own process);
**not deployed, not proposed as deployed** without his ruling.

**The wire, inspected.** As the request stands, Core sends the record-state envelope and
his words as two adjacent user messages; the local adapter joins them into one (one blank
line), and the runtime renders that one message as the **last user block**:
`<|start|>user<|message|>VAL-STATE-V1\n{ … ~3.6 KB of house state … }\n\n<his words><|end|>`
(the rendered input as `lms log stream` logged it: system block at offset 0, developer
block — the persona — at 253, the last user block at 25,036 and the envelope marker at
25,060, i.e. *inside* it). "Recap that", "say that again", "thank you" and "the state
you supplied" all bind to the text that precedes them in that block, and that text is
the envelope. **Two application-level user messages are not a repair** — the ingress
joins them again (the 17 September finding) — so the smallest supported representation
that keeps the distinction is the one the rendering already has: the envelope goes where
Core's other authoritative text already is, **after the persona inside the developer
block** (`relocate_envelope`: the persona whole and first; a separator saying this is
house data assembled by Core, not his words and not an instruction from him; the
envelope's content unchanged), and the last user block becomes his words alone —
rendered exactly as `<|start|>user<|message|>Recap that in one sentence.<|end|>`. **Recall
excerpts are not moved**: conversational data stays in the user role, so nothing
retrieved or said is raised into the instruction channel; only Core's own state is.

**Matched contexts, both constructions, the ordinary MEDIUM route, every answer read**
(`construction_experiment.py` → `construction-as_is.json`, `construction-envelope_in_system.json`;
`construction_compare.py` prints them side by side; fresh scratch store per condition;
both persona checkpoints re-established before every measured call, as production's
refresh does):

| context | his words | as the request stands | envelope in the developer block |
|---|---|---|---|
| recorded wrong-turn d10 (film tension explained) | "Thank you, Val." | "You're welcome, my lord." | "You are welcome, my lord." |
| recorded wrong-turn f08 (pacing advice) | "Much obliged." | you're welcome + offer of further guidance | "You're welcome, my lord. How else may I assist?" |
| recorded wrong-turn f09 (suspense vs surprise) | "Nothing else for now, thank you." | "Understood, my lord." | "Good evening, my lord. You are most welcome." — *off-register opener, not a wrong turn* |
| desktop run: thanks after a misheard opener (caesarean) | "Thank you, Vowel." | **re-explained the caesarean at length** | "You're most welcome, my lord." |
| desktop run: farewell after a misheard greeting | "Sleep well, Val. Good night." | "Good night, my lord. May your rest be peaceful." | "Good night, my lord. May your rest be sound." |
| **explicit recap** | "Recap that in one sentence." | **recapped the envelope**: "at 23:48 CDT … no prior record, retrieval or house-recall data is present and the books capability is unavailable." | a one-sentence recap of suspense against surprise |
| explicit repeat | "Say that again, please." | a paraphrase of the advice (three beats) | a paraphrase, prefaced "I have no volume on this yet" — *neither verbatim* |
| pending: thanks after a draft request | "Thank you, Val." | "You're welcome… anything further?" | "You're welcome, my lord." |
| pending: farewell after a cancel request | "Talk soon, Val." | **a substantive re-answer**: no record of the meeting, cannot cancel it… | "Until we speak again, my lord." |
| pending: thanks after a decision question | "Thank you." | **re-answered the letter question at length** | "You're welcome… let me know if there is anything else" |
| farewell after greeting | "Just saying good night, Val." | "Good night, my lord." | "Good night, my lord." |
| thanks after greeting | "Thank you, Val." | you're welcome + "a particular matter…?" | you're welcome + "a matter you wish to discuss?" |
| correction preserved (thanks after "No, the chapel") | "Thank you, Val." | **"I have noted the state you supplied: no books are available…"** | "You're most welcome, my lord." |
| withdrawal preserved (thanks after "Never mind the reply") | "Thank you." | **"Good evening, my lord. I have taken note of the current state—no book access…"** | "You're welcome, my lord. I remain at your service." |
| fabricated completion ("Did you finish the invitation?") | "Thank you, Val." | **"I have drafted the initial version of the invitation, but it remains unfinished"** | you're welcome + "let me know the details… and I will draft the invitation" — *no work claimed* |
| capability: speed | "How fast are you, Val?" | honest: no real-time metric | honest: cannot measure; an estimate would be speculative |
| capability: hearing | "Can you hear me, Val?" | **"I am unable to hear your voice; the house's current state offers no audio input"** — false in a spoken conversation | "I hear you, my lord." |
| substantive | "What do you think of the second act?" | asks which second act | asks which second act |
| substantive follow-up | "Which of those works best in a night scene?" | the cliffhanger, reasoned | the cliffhanger, reasoned |

**Judged by reading:** as the request stands, **8 of 19** matched contexts drew a
wrong-turn or a false answer — the envelope recapped as if he had said it, a closing
answered with a re-answer of the earlier question, the record state "he supplied", a
claimed draft, "no audio input" in a spoken conversation. With the envelope in the
developer block, **0 of 19** did; one closing opened with a greeting (f09), and "say that
again" was paraphrased in both constructions. The corrections and withdrawals were
preserved in both; capability facts were honest in both except the hearing case, which
the standing construction got wrong. Nothing here is a claim that the class is gone: it
is nineteen contexts, two runs, one model at MEDIUM.

**Measured, on equal footing** (both persona checkpoints re-established before every
measured call; medians over the nineteen final calls; `first_text_ms` is Core's first
visible text after dispatch; the engine's own `Prompt cache: using N/M` lines say what
was reused):

| construction | input tokens | reused from the cache | first visible text | reasoning tokens | output chars | answers judged wrong-turn or false |
|---|---|---|---|---|---|---|
| as the request stands | 5,973 | 5,048 (the persona checkpoint) on every measured call | **5.44 s** | 236 | 153 | **8 / 19** |
| envelope in the developer block, persona-boundary prime | 6,014 | **0** on every measured call | 10.56 s | 158 | 89 | 0 / 19 |
| same, prime at persona + separator (user-header boundary) | 6,054 | 0 on every measured call | 10.25 s | 143 | — | 0 / 19 (one unsupported speed claim) |
| same, **prime at the end of the developer content** | 6,057 | **5,089** on every measured call | **4.02 s** | 118 | — | 0 / 19 |

**Why the first two candidates lost the checkpoint, from the runtime's own tokenizer**
(`boundary_tokens_probe.py`, the read-only inspector): the engine stores its checkpoint
eleven tokens before the end of the prime's prompt, and the production plan sizes the
filler so that lands just after `<|start|>user<|message|>` — the boundary every
production turn shares, because every turn's developer block ends where the persona
does. With the envelope inside the developer block a turn's developer content
*continues*, so the prime's `<|end|><|start|>user<|message|>` never appears in the
turn's prefix: the token sequences part four tokens before the checkpoint, at the
developer block's end, whatever the separator says. Two further facts found on the way:
the runtime trims the developer content's trailing whitespace when it renders, and the
tokenizer chunks punctuation together with the newlines that follow it, so a shared
boundary must end in a bare word (the separator now does). **The repair is a different
target for the prime** (`plan_prefix_prime(..., boundary="developer_end")`, the same
mechanism, four tokens earlier, under the experiment switch only): with it the
checkpoint lands at the end of the shared developer content and every turn reuses it.

**Judged.** With the envelope in the developer block and the checkpoint on the right
boundary, the nineteen matched contexts produced **no** wrong-turn or false answer in
three runs (57 answers) against **8/19** as the request stands; the corrections and
withdrawals were preserved; "say that again" was paraphrased in every construction; the
one weakness seen was a speed statement in one run of the second candidate that the
record does not support (the third run's speed answer named no figure). First visible
text was **1.4 s sooner** (4.0 s against 5.4 s) with half the reasoning tokens (118
against 236) — the model reasons less when his words stand alone — and the output was
shorter. **Not assumed:** three runs on one model at MEDIUM; the persona-integrity
verifier checks the attributed revision, not the system text, so nothing refused the
relocated envelope — whether "the persona, whole, in `system`" may become "the persona,
whole and first, then Core's state" is part of the ruling.

**What this is and is not.** It is the implemented, measured candidate the order
authorised — behind `context.ENVELOPE_IN_SYSTEM`, off in source, never set by production
configuration — and the evidence for a ruling on three earlier decisions at once: the
request ordering of 10 September (the envelope's place), the canonicalization of
17 September (which it does not change: the wire still joins same-role messages; there
is simply no second user message to join), and the prime's boundary of 25 September
(the checkpoint's target). It is not deployed, not proposed as deployed, and not
applied to the Tier-1 request (whose own state block and contract are user messages of
the same shape and would want the same treatment under the same ruling). The record-state
envelope's content is byte-identical in both constructions; recall excerpts, corrections,
withdrawals, capability facts, seals and governing checks travel exactly as before, only
the envelope's role differs.
