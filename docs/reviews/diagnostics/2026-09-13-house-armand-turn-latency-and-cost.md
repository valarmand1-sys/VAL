# Diagnostic — cost and latency of four genuine House Armand turns, 13 September 2026

Read-only, on Lord Armand's instruction of 13 September 2026. Sources: `model_calls`, `budget_reservations`, `model_call_cache_usage`, `classifications`, `blind_positions`, `deliberations`, `messages` on the live store; the service log since the deployment restart; the code at `70e367c`; a read-only reconstruction of each response request with `assemble_turn`. **No provider call, no synthetic turn, no replay, no write to the store.** Nothing was changed.

Conversation `01a09bab-0fc7-747f-9f2a-6c97510996c8` (unassigned). The four genuine turns are the user messages at sequences 1, 3, 5 and 7. Classification, strip and blind-position rows carry no `conversation_id` or `message_id` by design; they are assigned to turns by the classification record's `model_call_ids`, the blind position's `model_call_id`, and — for strip calls — the reservation window between the user message and Val's reply, in which no other call exists (every call since the deployment restart is listed below).

---

## 1. Cost, exactly

Rates implied by the settled components: Opus 5 input $5/M, 1-hour cache write $10/M, cache read $0.50/M, output $25/M; Sonnet 5 input $2/M, write $4/M, read $0.20/M, output $10/M.

### Final turn — sequence 7, user message `01a09bc5-bb8a-79dc-8d31-3c776a87490f`

| # | Task | Route (model, effort) | In | Out | Cache: uncached / write 1h / read | Reserved | Settled | Terminal | Provider latency |
|---|---|---|---|---|---|---|---|---|---|
| 1 | classification | `haiku-4-5-20251001` (effort not applicable) | 811 | 18 | not cached | $0.003329 | **$0.000901** | complete | 1,225 ms |
| 2 | strip | `sonnet-5-low` (claude-sonnet-5, low) | 2,061 | 291 | 140 / 0 / 1,921 — hit | $0.060160 | **$0.003574** = 0.000280 + 0.000384 + 0.002910 | complete | 3,469 ms |
| 3 | blind_position | `opus-5-medium` (claude-opus-5, medium) | 6,946 | 1,446 | 285 / **6,661** / 0 — created | $0.318170 | **$0.104185** = 0.001425 + 0.066610 + 0.036150 | complete | 43,925 ms |
| 4 | conversation | `opus-5-medium` | 10,994 | 2,410 | 2,375 / 771 / 7,848 — hit and created | $0.456100 | **$0.083759** = 0.011875 + 0.007710 + 0.003924 + 0.060250 | complete | 30,529 ms |

Call 4 names message `01a09bc5-…` and conversation `01a09bab-…`; calls 1–3 name neither. **Total: 0.000901 + 0.003574 + 0.104185 + 0.083759 = $0.192419.** The footer's $0.1925 agrees.

### The three preceding turns

| Turn | Calls and settled cost | Total |
|---|---|---|
| Sequence 5 (`01a09bc2-0a01-…`) | classification $0.000899 · strip $0.002382 (hit) · conversation $0.065957 (8,565 in: 717 / 834 / 7,014; 2,021 out) | **$0.069238** |
| Sequence 3 (`01a09bbc-44c3-…`) | classification $0.000868 · strip $0.009366 (first strip of the hour: 1,921-token write, $0.007684) · conversation $0.053248 (7,688 in: 674 / 618 / 6,396; 1,620 out) | **$0.063482** |
| Sequence 1 (`01a09bab-0fce-…`), House Recall | classification $0.000890 · conversation $0.192300 (27,519 in: **21,123 uncached** $0.105615 / 6,396 write $0.063960 / 0 read; 909 out $0.022725) | **$0.193190** |

Four turns: **$0.518329**. (The footer's absolute month-to-date figure differs from the ledger's $2.781998; the marginal differences agree with the ledger, which governs.)

### Where the final turn's extra $0.123181 over the seven-cent turn came from

0.192419 − 0.069238 = **0.123181**, decomposed exactly:

| Source | Δ |
|---|---|
| The blind-position call, entirely additional | **+0.104185** (of which the 6,661-token cache write is 0.066610) |
| Final response: reconciliation envelope in the uncached tail (+1,658 uncached tokens) | +0.008290 |
| Final response: 389 more output tokens | +0.009725 |
| Final response: cache write −0.000630, cache read +0.000417 | −0.000213 |
| Strip: 117 more output tokens and 11 more uncached | +0.001192 |
| Classification | +0.000002 |
| **Sum** | **0.123181** |

## 2. Which turns were consequential, and the path each took

| Turn | Verdict | Strip | Strip outcome | Blind call | Ordering | Deliberation | Final response |
|---|---|---|---|---|---|---|---|
| 1 | not_consequential (`retrieval_lookup_or_search`) | no | — | no | — | no | `opus-5-medium`, ordinary path |
| 3 | consequential | yes | `no_preference` (no warning logged, no blind row) | no | — | no row (resolves in a later turn by contract) | `opus-5-medium`, ordinary path |
| 5 | consequential | yes | `no_preference` | no | — | no row | `opus-5-medium`, ordinary path |
| 7 | consequential | yes | enforceable — withheld one `attributed_prior` span: "Hardmarch was your strongest recommendation, so follow the logic of your own choice." | yes | **enforced** | **agreed_from_start** | `opus-5-medium`, pinned to the blind configuration, reconciliation envelope attached |

The strip outcome of turns 3 and 5 is established by absence: the orchestrator logs a warning for every strip state other than `no_preference`, and none was logged.

## 3. The 48.73-second gap — hypothesis confirmed

**Clock origins, from the code:**

| Displayed metric | Clock starts | Clock stops |
|---|---|---|
| gateway first token | inside `Gateway._execute`, after the final response call's budget reservation is held, immediately before the provider is contacted (`gateway.py` `started = time.monotonic()`) | the first non-empty text delta from that provider stream |
| first delta at client | `performance.now()` immediately before the desktop's `fetch` of `/turns/stream` (`api.ts`) | the first `delta` event parsed |
| first words visible | `performance.now()` when `send` begins, before the fetch (`App.tsx`) | the `requestAnimationFrame` callback after the first render with non-empty streamed text |
| complete after | the same origin as first delta at client | the `settled` event parsed |

The gateway figure is therefore measured from the start of the **final response call only**; the client figures from the start of the **whole request**. On a consequential turn, classification, strip and the blind position all run before the final response call exists.

**Timeline of the final turn** (store timestamps; a reservation is written immediately before its provider call and settled immediately after):

| Event | Time (CDT) | From user message persisted |
|---|---|---|
| user message persisted | 12:17:02.217 | 0.000 s |
| classification reserved → settled | 02.224 → 03.454 | 1.230 s |
| orchestration | | 0.009 s |
| strip reserved → settled | 03.463 → 06.939 | 3.476 s |
| strip validation, persona load, assembly, route selection, blind payload logged | | 0.022 s |
| blind position reserved → settled | 06.961 → 50.893 | **43.932 s** |
| blind evidence row written | 50.895 | |
| response call reserved (gateway clock starts) | 50.917 | **48.700 s** |
| provider's first text token (+12.74 s) | ≈ 18:03.657 | 61.44 s |
| first delta at client | | 61.47 s (client origin, a few ms earlier than the persisted message) |
| first words visible | | 71.61 s |
| response settled; Val's message; deliberation row | 18:21.456; 21.458; 21.466 | 79.24 s |
| complete at client | | 79.28 s |

**48.700 s of machinery preceded the final response call**: classification 1.230 + strip 3.476 + blind position 43.932 + orchestration 0.062. Adding the gateway's 12.74 s gives 61.44 s against the client's 61.47 s. **Provider first token to the desktop's receipt of the first delta — Val Core, the reconciliation filter, SSE and the loopback — took about 30 ms at most. There is no demonstrated 48-second streaming buffer.**

The same arithmetic holds on the earlier turns: turn 5, pre-response 4.318 s (classification 1.663 + strip 2.611 + 0.044) + TTFT 23.91 = 28.23 vs client 28.24; turn 3, pre-response 4.716 s (1.195 + 3.475 + 0.046) + TTFT 14.71 = 19.43 vs client 19.45.

**One presentation gap is real and is not server-side.** On the final turn, *first words visible* came 10.14 s after *first delta at client* (71.61 vs 61.47); on turns 3 and 5 the same interval was 0.03–0.04 s. The text had reached the desktop's state at 61.47 s. The visible moment is taken on the next animation frame, and WebKit suspends `requestAnimationFrame` for a window that is not visible; a sixty-second wait is when a window is most likely to be behind another. That is the likely cause, but **no record establishes it** — the desktop's timings are not persisted and window visibility is not captured.

**So the two actual issues are:** (1) user-visible latency caused by serial work before the final response begins, dominated on this turn by the blind-position call; (2) a measurement and presentation defect — figures from two clock origins shown side by side without saying so, and a first-paint figure whose delay after receipt is unexplained by any record.

## 4. Consequential-turn latency, decomposed

| Stage | Final turn | Turn 5 | Turn 3 | Turn 1 |
|---|---|---|---|---|
| classification | 1.230 s | 1.663 s | 1.195 s | 1.593 s |
| strip | 3.476 s | 2.611 s | 3.475 s | — |
| blind position | **43.932 s** | — | — | — |
| orchestration and assembly | 0.062 s | 0.044 s | 0.046 s | 0.125 s (House Recall query included) |
| final response time to first token | 12.74 s | 23.91 s | 14.71 s | not reported to me |
| final response generation after first token | 17.79 s | 11.31 s | 14.40 s | — |
| provider first token → client first delta | ≤ 0.03 s | ≤ 0.01 s | ≤ 0.02 s | — |
| client first delta → first words visible | 10.14 s | 0.04 s | 0.03 s | — |

**The blind position against prior evidence.** Every blind-position call on record:

| Date | Route | In / out | Latency | Output rate | Cache |
|---|---|---|---|---|---|
| 7 Sep | haiku (pre-floor) | 4,735 / 150 | 5.5 s | — | — |
| 7 Sep | haiku | 4,790 / 319 | 9.4 s | — | — |
| 10 Sep | opus-5-medium | 6,544 / 1,364 | 23.6 s | ≈58 tok/s | created, 6,011 written |
| 11 Sep | opus-5-medium | 6,321 / 512 | 10.4 s | ≈49 tok/s | created, 6,011 written |
| **13 Sep** | **opus-5-medium** | **6,946 / 1,446** | **43.9 s** | **≈33 tok/s** | created, 6,661 written |

O9 (11 September) is not a valid blind-position comparison: its strip found no preference and no blind call ran. It is valid for the response stage — 23.3 s to first token on 2,198 output tokens — which bounds the final turn's 12.74 s TTFT as ordinary for this route.

**Verdict.** The final turn is the **existing consequential architecture on a hard prompt** — three serial calls before the answer, the third on the partner route at medium effort producing a position and reasoning of about 3,100 characters plus thinking — **combined with slower provider throughput on that call** (33 tokens/s against 49–58 on the same route and effort on 10–11 September). One sample per day establishes a variance, not a trend. **It is not a code regression**: `deliberate.py`, the Anthropic adapter, the strip and reconciliation policy and the registry are unchanged between `22c723e` (before conversation management) and `70e367c`; the only commit touching them since the Val Core base is Phase 1 itself. The responsiveness requirement is unchanged by this: the finding moves where a correction is sought, it does not make 71 seconds acceptable.

## 5. Did conversation management contribute? No, on every measure available

**Input.** No revision, removal or transition fact exists anywhere in the store, so no revision key entered any request; the logged state envelopes carry exactly the pre-existing keys. Provider input is fully accounted for by the persona, the incremental history and the per-turn tail:

| | Turn 1 | Turn 3 | Turn 5 | Turn 7 |
|---|---|---|---|---|
| Final-response input (provider) | 27,519 | 7,688 | 8,565 | 10,994 |
| Persona prefix (provider, from the first write) | 6,396 written | 6,396 read | 6,396 read | 6,396 read |
| Retained history (provider, cache increments) | — | 618 written | 618 read + 834 written | 1,452 read + 771 written |
| Uncached tail (provider) | 21,123 | 674 | 717 | 2,375 |
| — House Recall envelope (reconstructed, estimator) | 43,931 chars ≈12,204 | — | — | — |
| — record-state envelope (estimator) | ≈457 | ≈472 | ≈472 | ≈472 |
| — current message (estimator) | ≈47 | ≈84 | ≈113 | ≈124 |
| — reconciliation envelope (estimator) | — | — | — | 5,262 chars ≈1,462 |
| Classification input (provider) | 750 | 778 | 809 | 811 |
| Strip input (provider) | — | 2,007 | 2,050 | 2,061 |
| Blind-position input (provider) | — | — | — | 6,946 |

**Cache.** The response-call cache behaved as designed: turn 1 wrote the persona, each later turn read everything before its breakpoint and wrote only the newest exchange. The strip wrote once and read thereafter.

**Synchronous time.** Previous call settled → final response reserved: 22.7–23.7 ms on these turns without House Recall, 105 ms with it; on 12 September, before conversation management, 26 ms without and 99–104 ms with. On the live store now, the working-thread reads take 0.2 ms each, a conversation read with the new derivations 0.5 ms, and the House Recall statement over `messages_current` 22 ms.

**Nothing else on the critical path changed.** The whole latency and cost difference is attributable to the existing consequential machinery and provider timing.

## 6. House Recall participation and grounding continuity

| Turn | House Recall | Gate reason | Excerpts | Admitted (estimator) | Sources |
|---|---|---|---|---|---|
| 1 | **returned** | explicit reference: "we have discussed" | 3 | 10,924 | all `unassigned`: the 12 September verification turn, the 12 September diagnostic question, the 3 September *Phony Spumoni* draft; a fourth candidate (5,812) did not fit |
| 3 | not run | `no_cross_conversation_reference` | 0 | — | — |
| 5 | not run | `no_cross_conversation_reference` | 0 | — | — |
| 7 | not run | `no_cross_conversation_reference` | 0 | — | — |

No later turn incurred House Recall. Automatic recall was `not_run / no_project_scope` on all four (unassigned conversation).

**A finding on turn 1's size.** The recall budget is measured by the house estimator on excerpt content. The admitted 10,924 estimated tokens became a 43,931-character envelope estimated at 12,204 — and the provider counted about 20,600 tokens for it (21,123 uncached less the state envelope and message). The estimator undercounts this serialised, escaped screenplay material by roughly 1.7×, against about 1.1× on ordinary prose (persona 5,717 estimated vs 6,396). That undercount, not House Recall's design, is why turn 1 cost $0.193.

**Grounding continuity — the drop is structural and intended by the current contract.** The recall envelope is assembled per call from that call's recall outcome and is never persisted into the thread (`assemble_turn`; `recall_block`). On turn 3, Val received: the persona; her own previous answer, verbatim, as retained history; Lord Armand's messages; and a record-state envelope saying `house_recall: not_run`. She did **not** receive the excerpts, their provenance, or any statement that her previous answer had drawn on them. Her reply then said: "I do not have that record available on this turn, and I should not have stated it with that confidence. Treat it as unverified until one of us puts the material back in front of me." Given what she was sent, that is the persona's honesty rule applied to an absence the envelope made indistinguishable from never having had the record — a grounding-continuity gap, not a House Recall defect.

## 7. Behavioural observations recorded for separate ruling (no change made)

From Lord Armand's genuine use, and visible in the stored replies:

- A House or medieval register in ordinary conversation ("sworn to the house rather than to any one Lord"; "a Maester who only raises objections when they will be welcome is decorative").
- Unnecessary precision at a socially fuzzy greeting boundary: "Good morning, my lord — it is a few minutes short of noon here" at 11:48, then "Good afternoon, my lord — just past noon" at 12:07.
- Repeated promises to start a book although the books are not implemented: "I will start the book on it" (sequence 2); "begin the book on the house's history properly" (sequence 6); "That ledger is the first volume of this library" (sequence 8).
- Invention presented with factual confidence: "Armand comes from the old roots for *hard* and *man*" (sequence 6). By contrast, sequence 8 labelled its founding story "invention offered as a starting point, not record".

## 8. Candidate corrections, for ruling — none implemented

Ranked by expected user-visible impact. None removes or weakens the consequential machinery.

1. **Show honest stage state while the machinery runs.** Emit stream events for the stages already confirmed by the backend — classifying, forming her own position, answering — and display them. First visible *feedback* would arrive in about 1 s on every turn; first generated *text* is unchanged. Low risk, no cost. It is presentation of confirmed state under invariant 29 and changes nothing Val receives. It does not satisfy the 1–2 s generated-text requirement and should not be represented as doing so.
2. **Bound the blind position's output.** The blind call wrote about 3,100 characters of position and reasoning; generation time scales with it. Tightening the contract, for example to a short reasoning field, would cut most of the 43.9 s on a turn like this one. Moderate risk: this is a WP-0.9 contract change touching evidence quality, and needs a ruling and a frozen-suite check before any provider traffic.
3. **Fix the timing display.** Label each figure by its origin, and add "work before Val began answering" plus the stage breakdown. Record the receipt → render → paint moments and the window's visibility so the 10-second first-paint gap is diagnosable. No risk, no cost.
4. **Stop paying the blind call's 1-hour cache write.** Every blind call on record wrote a fresh prefix and none has ever read one: the calls are days apart, and the prefix is always 265 tokens longer than the persona prefix on response calls (5,746 → 6,011 under v1.4; 6,396 → 6,661 under v1.7). That constant difference is consistent with the provider-enforced output schema sitting inside the cached prefix — an inference, not verified without a provider call. Sending the blind call uncached would save about $0.033 per blind call; a 5-minute lifetime about $0.025. Latency effect negligible. Low risk; a caching-doctrine ruling, since caching was enabled on the partner route's stable prefix on 8 September.
5. **Carry House Recall provenance, not content, into later turns.** Add a record-state fact that Val's answer at a given position drew on House Recall excerpts from named conversations and dates, not re-supplied. This closes the self-disavowal without making recall universal or adding excerpt tokens. Low cost; changes what Val is told, so it needs a ruling. The persona side of how she treats her own prior statements is part of the separate behavioural ruling.
6. **Calibrate the recall budget to serialised size.** Measure excerpts as they are serialised, or calibrate the estimator for escaped content, so a 16,000-token budget cannot become about 20,600 provider tokens. This reduces cost on material-heavy recall turns. It changes how much is admitted, so it needs a ruling.
7. **Run strip concurrently with classification, speculatively.** This saves about 3.5 s on consequential turns. It costs about $0.002–0.009 on every turn and conflicts with the per-turn necessity rule, so it is not recommended without a ruling.

Not candidates: removing or skipping the blind position, lowering the partner route's effort for it, or streaming anything before the blind position is durable. Each weakens the evidence the machinery exists to produce.
