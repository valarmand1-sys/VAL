# Corrective pass on the consequential-turn diagnostic — record, 13 September 2026

Implementation of Lord Armand's ruling of 13 September 2026 on `docs/reviews/diagnostics/2026-09-13-house-armand-turn-latency-and-cost.md`, recorded in `01-architecture.md` §5.1 and in `04-layer-0.md` (WP-0.4, WP-0.7 and WP-0.10 amendments of that date). **No provider call was made.** Every correction is verified deterministically; no House Recall, consequential or cache traffic was manufactured.

**Four of the five corrections are implemented and deployed. Correction 3, the House Recall budget, is not implemented:** it met the ruling's own stop condition, and its options are in §4.

---

## 1. Commits, CI and deployment

| Correction | Commit | CI run |
|---|---|---|
| 1 and 2 — streaming finding recorded; blind-position calls request no cache | `ab26786` | 34776208829, success |
| 4 and 5 — timing labelled by origin with instrumentation; stage progress | `b0a6d9a` | 34776782363, success |
| 6 — House Recall grounding continuity as provenance | `bc6e535` | 34777319138, success |

**Deployment.**
- **Store:** the live store was fingerprinted read-only, migrated `0018 → 0019` with `alembic -x deploy=live upgrade head`, and fingerprinted again. The immutable-record digests over messages, origin scopes and calls were identical.
- **Service:** restarted on `bc6e535` after the green run; health reported running with no warnings.
- **Desktop:** the native bundle was rebuilt from current source and installed at `/Applications/Val.app`. The morning's bundle is preserved as `Val (built 2026-09-13 morning).app`, and the app was not running.

**Tests.** There are now 1,261 Python tests: 1,219 on the configured paths plus 42 provider tests. There are 41 desktop tests. Before this pass the counts were 1,239 and 35. The only pre-existing test file touched is the schema transcription in `test_schema.py`, extended additively with the new table and its nullable columns. No existing expectation changed.

## 2. Correction 1 — streaming is not defective

Recorded as governing evidence in `01-architecture.md` §5.1. On the sequence-7 turn, about 48.700 s of serial machinery preceded the final response call. The provider took about 12.74 s to its first token, and that text reached the desktop within about 30 ms. Val Core streaming, SSE and the reconciliation filter are unchanged. The responsiveness requirement remains open.

## 3. Correction 2 — blind-position caching

**Current structure, and why it never read the persona cache.**
- **Breakpoint placement:** the adapter sends `system` as one text block, the persona whole, carrying the cache breakpoint, and the blind instruction and question as the only message. The request was therefore already persona → breakpoint → blind-specific text. The proposed reordering *is* the current shape.
- **Why the cache still missed:** the cached prefix recorded by the provider is persona plus a constant 265 tokens. This holds under both persona versions on record (response prefix 5,746 against blind prefix 6,011 under v1.4; 6,396 against 6,661 under v1.7).
- **Where the 265 tokens come from:** the one constant request-level difference is the structured-output format (`output_config.format`). The adapter's own documentation already recorded that the format adds its own system text. The provider renders that text inside the prefix ahead of the breakpoint. The application cannot place a breakpoint before provider-rendered content.
- **What reuse would require:** removing the output contract from the blind call, which the ruling forbids. Persona-cache reuse is therefore impossible without changing the blind request, and the ruling's fallback applies.

This cause is established by the constant difference in the records and by the documented behaviour of the format parameter. It is not confirmed by a provider call.

**Implementation.** `Gateway._cache_ttl_for` returns no cache lifetime for `blind_position` calls only. Deterministic proof:
- **Byte-equivalence:** `test_blind_request_cache_metadata.py` shows the uncached blind request equals the cached one with cache-control metadata removed. Model `claude-opus-5`, effort `medium`, the schema, the persona and the message are identical, and no `cache_control` is present.
- **Only this task type changed:** `test_blind_cache_ttl.py` shows every other task type decides caching as before, and the blind reservation is the base-rate bound.
- **End to end:** `test_blind_position_cache.py` runs the deliberated path with a one-hour cache configured. The blind call is sent with no lifetime, is reserved at exactly `maximum_cost(..., None)`, writes no cache-usage row, keeps the active persona attribution and stays on `opus-5-medium`. The response and strip calls still request the one-hour lifetime and write their usage rows, and the classifier still requests none.

**Cost arithmetic on the 13 September blind call** (6,946 input tokens, 1,446 output; Opus 5 at $5/M input, $10/M one-hour write, $0.50/M read, $25/M output):

| Behaviour | Input | Output | Total | Against the old write |
|---|---|---|---|---|
| Old: 285 uncached + 6,661 written for one hour | 0.001425 + 0.066610 | 0.036150 | **$0.104185** | — |
| **Now: all 6,946 uncached** | 0.034730 | 0.036150 | **$0.070880** | saves $0.033305 (32%) |
| Not achievable: 6,396 persona read + 550 uncached | 0.003198 + 0.002750 | 0.036150 | $0.042098 | would have saved $0.062087 |

The last row is shown only because the ruling asked for the comparison. It requires the reuse that §3 shows is impossible.

## 4. Correction 3 — House Recall budget: stopped, options returned

**No exact local count exists.** The repository has no Claude tokenizer, and the Anthropic SDK's token counting is the provider's `count_tokens` endpoint, a provider call. The house estimator is a documented characters-per-token heuristic, and the ruling forbids an empirical multiplier.

**The only deterministic provable bound available is destructive.** The budget code already proves that a byte-level tokenizer never emits more tokens than there are UTF-8 bytes. Governing the serialised `VAL-MEMORY-V1` block by its byte length therefore cannot undercount. Its cost in admission, measured on the opening turn's real candidates:

| Rank | Content | Serialised alone | Estimate |
|---|---|---|---|
| 1 | the 12 Sep question | 1,763 bytes | 47 |
| 2 | the 12 Sep diagnostic question | 1,763 bytes (envelope 2,420 cumulative) | 47 |
| 3 | the *Phony Spumoni* draft | 42,625 bytes (envelope 43,939) | 10,830 |
| 4 | a further draft | 22,730 bytes | 5,812 |

- **What the provider counted:** about 20,480 tokens for the three-excerpt envelope. That envelope was 43,939 bytes, estimated at 12,204.
- **Byte bound on this turn:** at a 16,000 budget it admits only ranks 1–2. An exact provider count at 16,000 tokens would also have excluded rank 3, so here the two agree.
- **Byte bound on prose:** bytes overstate provider tokens by about 3.2 times (the persona is 20,580 characters for 6,396 tokens). A 16,000-byte bound would admit roughly 5,000 provider tokens of prose, under a third of the ruled budget, on every recall turn.

**Options for ruling:**
1. **Byte bound over the serialised envelope.** Deterministic, provably never exceeds 16,000 provider tokens, no provider call. It admits roughly a third of the ruled budget for prose and about half for dense screenplay material. It is simple to test adversarially, because bytes are exact.
2. **Exact pre-transmission count with the provider's `count_tokens`, on House Recall turns only.** Exact for the active provider, and governs the actual serialised block. It is not a local method. It adds one network round trip before the response call on those turns, and it sends candidate excerpts, including ones then not admitted, to the provider's counting endpoint. That is egress of Protected content needing an eligibility ruling, and whether the endpoint is billed must be confirmed first.
3. **Both:** the exact count when the endpoint is available, and the byte bound when it is not, failing toward admitting less.

Recommendation: option 3 if counting egress is acceptable under the existing Protected-eligibility premise, otherwise option 1. The current estimator-based admission is unchanged until ruled, so the budget remains a target and not a ceiling.

*Ruled later the same day:* byte-only — a conservative 16,000-byte limit over the exact serialized recall envelope, shared by automatic recall and House Recall, with no provider counting. Implemented as recorded in `04-layer-0.md` (WP-0.7 amendment of 13 September 2026) and `VAL_Test_and_Evidence_Index.md` §55; the paragraphs above are kept as the record of what was returned.

## 5. Correction 4 — timing labelled by clock origin, with instrumentation

- **Service:** the settled timing gains `api_response_started_ms`, measured from the service's receipt of the request to the start of the final response call.
- **Desktop, from Send:** every client figure is measured from Send in the window — work before Val began answering (when the `preparing_response` stage arrives), first text received, first render, confirmed first paint, and complete. First paint is taken on the second animation frame after the render that showed her text.
- **Response call, separately:** the response call's time to first token is shown on its own line as "Response call alone, from its own start", never beside the figures from Send.
- **Visibility:** the desktop records whether the window was visible at the first delta, render and paint, and every visibility change during the turn. It shows a visibility line only when the window was hidden, and writes the whole record to the developer console as `val.turn.timing`. Nothing is persisted.
- **Undiagnosed gap:** the 10.14-second delta-to-paint gap of 13 September remains undiagnosed until this instrumentation observes one.
- **Where it lives:** the pure wording functions are in `apps/desktop/src/timing.ts`, tested against the 13 September figures in `timing.test.ts`.

## 6. Correction 5 — stage progress

**Semantics:** `understanding` when the message is persisted and the turn begins; `forming_view` immediately before the enforced blind-position call, and never on a turn that forms none; `preparing_response` immediately before the final response call.
- **Delivery:** stage events go only to a streamed request that asks for them (`progress: true`, which the desktop sends). Every existing stream contract, including the exact event sequences pinned by the existing stream tests, is unchanged.
- **Payload:** events carry only the stage and the service's elapsed milliseconds, never a label, preference, position or text. They are never stored and never spoken.
- **Display:** the desktop shows "Considering your message…", "Forming an independent view before answering…" and "Preparing a response…" only until Val's first words arrive. It adds no artificial delay.
- **The requirement:** progress does not count toward the 1–2 second generated-text requirement. That is stated in the interface's tooltip, in `04-layer-0.md` WP-0.10 and here.
- **Tests:** `test_turn_progress.py` covers the ordinary order, the enforced order and forbidden vocabulary, no false `forming_view`, the unchanged stream without the flag, nothing stored, and no stage on a clarification.

## 7. Correction 6 — grounding continuity as provenance

**Why a sidecar was needed.** No existing durable record established the mapping: the recall envelope is per call and not persisted, and House Recall's selection was only logged. Migration `0019` adds **`answer_recall_sources`**, one append-only row per House Recall source admitted to the response call that produced a persisted Val answer:
- **Linkage:** answer message, response call, retrieval path, rank.
- **Source:** message, conversation and sequence; **`source_revision_number`**, the exact wording seen, NULL for the original; the scope it was written in; when it was said; and a title snapshot for presentation.

A coherence trigger guards it, and it is frozen and undeletable. Rows are written right after Val's message, failing toward no provenance. Nothing is backfilled.

**Derivation.** On a later turn, `grounded_answers` in the record-state envelope names each retained Val answer that House Recall supported, by position. Each source carries its id, conversation id and title, sequence, speaker, when said, scope, wording (`original` or `correction n`), `retrieval_path`, and `status_now` (unchanged, corrected since, withdrawn since, conversation removed since). The key is absent when there is no such answer, so every other request is byte-identical.

**No excerpt content is carried forward merely for provenance.** The tests assert the source text appears in no message of the later request.

`test_answer_grounding.py` proves the linkage, provenance without content, no linkage without House Recall, and that a later revision cannot change the recorded wording. It also covers a source retrieved after a correction, a retracted source and a removed source keeping their historical role, House Recall not running because of the fact, one provider call per turn, and the trigger's refusals.

## 8. Confirmations

- **Other caching unchanged:** conversation responses, strip, classification and every task type except `blind_position` decide caching exactly as before (the tests in §3).
- **Nothing ruled out was changed:** the partner route, `opus-5-medium`, medium effort, the strip order, enforced ordering, the blind-position output contract, deliberation semantics, Val Core streaming semantics and the persona.
- **The rejected parallelism was not implemented:** strip still runs after classification.
- **Persona observations untouched:** they stay recorded in the diagnostic §7 for their separate ruling.
- **No provider call** was made at any point in this pass.
- **Conflicts:**
  - Correction 3 is blocked by the ruling's own stop condition (§4).
  - Stage events were made opt-in because the existing stream tests pin exact event sequences. This preserves that contract without amending a test; it is a design choice within the ruling, not a conflict with it.
