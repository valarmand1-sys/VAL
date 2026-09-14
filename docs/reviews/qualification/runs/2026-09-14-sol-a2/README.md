# Stage A2 — one ordinary Val Core exchange on GPT-5.6 Sol through the candidate lane — 14 September 2026

Owner-authorised 14 September 2026 for one ordinary, non-consequential exchange (maximum $0.23; the consequential path not authorised). Run by `harness_a2.py` at about 09:50 CDT on the scratch store `val_test` (dropped and re-migrated to `0020`, persona seeded and asserted as v1.8), through `candidate_gateway_for_scratch_store` exactly as built and tested, with a harness-level guard that would have refused any candidate blind-position call. No House material. Raw output, including the provider request ids and the full messages, in `result.json`.

**Structural preflight only.** Sol remains `NOT_ADMITTED`, carries no capability profile and no fallback; nothing in production routing changed.

## The exchange

- **Prompt:** "Good morning, Val. What is the time by the house's clock, and how are you today?"
- **Classification** (Haiku 4.5, its normal structured route): `not_consequential`, hard exclusion `retrieval_lookup_or_search`, one attempt, $0.000875, 1,018 ms. No strip, no blind call; the guard was never reached.
- **Val's answer, streamed through Val Core** (30 deltas): "Good morning, my lord. It is 9:50 a.m. I don't experience feelings, but I'm here and ready to help." Persisted as sequence 2. The time came from the record-state envelope's `current_time`.

## The Sol partner call — measured

| Measure | Value |
|---|---|
| Configuration | `gpt-5-6-sol-medium` (`e9c6ec70-…`), `gpt-5.6-sol`, effort medium |
| Persona attributed | revision `01a0a066-5481-…`, v1.8, digest `1608715f…` — loaded whole per call |
| Total input tokens | **5,324** |
| Uncached input | **3** |
| Cache-write tokens (provider-reported) | **5,321** |
| Cached-read tokens | **0** |
| Output tokens | **34** |
| Reasoning tokens (provider-reported) | **0** |
| Reasoning item present | **no** |
| Generated visible text | 99 characters |
| Time to first generated text at the Val Core boundary | **2,903 ms** |
| Total provider latency | **4,915 ms** |
| Terminal state | `complete` (`status: completed`) |
| Settled cost | **$0.027297** = 3 × $4/M + 5,321 × $5/M + 0 × $0.40/M + 34 × $20/M = 0.000012 + 0.026605 + 0 + 0.000680 |
| Reservation maximum | $0.206450 (whole input by bytes at the $5 write rate plus 4,096 output at $20) |
| Recorded | `model_calls` under Sol's own id, `status ok`, `cost_certainty known`; `model_call_measurements` row (`streamed = true`); reservation settled; exchange identity on both calls |

**Full exchange cost: $0.028172** (classification $0.000875 + response $0.027297), against $0.23 authorised and ≈ $0.09 expected.

## Findings

1. **Reasoning tokens: zero.** On the real Val-shaped request — the whole persona, the record-state and capability-state envelopes and the turn — at effort `medium`, OpenAI reported `reasoning_tokens = 0` and no `reasoning` output item. This is the provider's figure, not an inference. Whether Sol reasons on a substantive turn is not established by a greeting; the incumbent's hidden-reasoning cost was observed on substantive and consequential turns.
2. **Caching: the whole prefix was written, cold.** OpenAI reported 5,321 of 5,324 input tokens written to its cache (the implicit breakpoint at the end of the user message) and 0 read. The persona, the state envelopes and the message all sit inside the written prefix; on a warm follow-up within 30 minutes the persona-plus-history part is the candidate for reads. **Written tokens were 99.9% of the input on this cold call, billed at $5/M.** Cost under the corrected accounting: $0.026605 of the $0.027297 was the cache write; had the same call been priced at base it would have been $0.021964 — the write premium on this call was $0.004641.
3. **Prefix size on OpenAI's tokenizer:** persona v1.8 plus the two envelopes and the message came to 5,324 tokens, against ≈ 6,995 tokens for the persona alone on the incumbent's tokenizer (derived, 13 September). OpenAI's count for the same persona text is materially smaller; the exact persona-only figure on OpenAI is not isolated by this call.
4. **Latency:** first generated text at 2,903 ms from the start of the provider call, 4,915 ms in total for 34 output tokens — the whole 5,324-token prefix processed cold. The incumbent's measured time-to-first-token on comparable warm ordinary turns was 12.7–23.9 s on the 13 September turns (those turns produced 1,620–2,410 output tokens with thinking; the comparison is not like for like and is recorded as such).
5. **Governance intact:** classification on its normal route; Sol used only for the partner response; persona whole and attributed; record state and capability state in the request (the answer used the clock); Core-owned streaming; normalized result; reservation and settlement ordinary; recorded under Sol's identity; no fallback; no admission or routing change.

## Not established here

- Warm reuse (no second call was authorised).
- Sol's reasoning behaviour on substantive or consequential turns.
- Quality: one greeting is not evidence for the partner floor; Stage B is the instrument.
