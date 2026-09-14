# Stage A1 — GPT-5.6 Sol adapter preflight — 14 September 2026

Owner-authorised 14 September 2026 (maximum $0.05). Run by `preflight_a1.py` at about 09:02 CDT on the scratch store `val_test` (dropped and re-migrated to `0020` first), through the service's own `OpenAIAdapter` and `Gateway.evaluate_with_configuration`, on `gpt-5-6-sol-medium` (`gpt-5.6-sol`, effort medium). No House material: the prompt was "Reply with the single word: ready." Raw output in `result.json`.

**Adapter and integration preflight only.** Not partner qualification, not admission, not closure of the Phase 1 two-provider gate.

## Result

**The configured account reaches `gpt-5.6-sol`.** All three calls returned `status: completed`.

| # | Path | Input | Output | Reasoning tokens | Reasoning item | Cached / written | Text | Latency | Cost |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `OpenAIAdapter.stream` | 14 | 5 | 0 | none | 0 / 0 | `ready` | 2,935 ms (first text 2,595 ms) | $0.000156 at registry rates (not persisted — adapter-level call) |
| 2 | evaluation door, `title` task, schema `{"word": string}`, ceiling 1,024 | 38 | 15 | 0 | none | 0 / 0 | `{"word":"ready"}` | 2,560 ms | **$0.000452** settled |
| 3 | the same, ceiling 16 | 38 | 15 | 0 | none | 0 / 0 | `{"word":"ready"}` | 2,265 ms | **$0.000452** settled |

- **Exact provider spend: $0.001060** (calls 2–3 settled at $0.000904 from the store; call 1 $0.000156 from the provider's usage at the same rates). Against $0.05 authorised.
- **Streaming:** one `TextDelta("ready")` then exactly one `ProviderResult`; no OpenAI type above the adapter.
- **Persistence:** two `model_calls` rows under `e9c6ec70-…` (Sol's own id), `task_type = title`, `status = ok`, `terminal_state = complete`, `cost_certainty = known`; two `model_call_measurements` rows (`streamed = false`, `text_output_chars = 16`, `reasoning_present = false`, `reasoning_output_tokens = 0`, cache reads and writes 0, no exchange — a harness call belongs to none); two reservations settled at known cost ($0.020648 → $0.000452 and $0.000488 → $0.000452).
- **Provider request ids:** `resp_0319a68b…`, `resp_08768267…`, `resp_0c5115c1…`.

## Discrepancies against the plan

1. **Call 3 did not truncate.** The 16-token ceiling was meant to exercise `incomplete` / `max_output_tokens`, but the reply was 15 output tokens and completed. Truncation handling on OpenAI is therefore **proved only by the deterministic adapter tests** (`test_openai_stream.py`, `test_adapters.py`), not by this live call. The call set was not expanded.
2. **Reasoning on a trivial prompt:** at effort `medium` the provider produced 0 reasoning tokens and no `reasoning` output item on all three calls. The adapter recorded `reasoning_present = false` (an output list with no reasoning item) and `reasoning_output_tokens = 0` as the provider reported them. Whether Sol reasons on a Val-shaped request is a measurement question, not settled here.
3. **Cost accounting was exact** for these calls: below the 1,024-token cache minimum, nothing was cached, so the accounting gap the protocol §3 described could not appear. It has since been closed (§2 of the ruling of 14 September; `test_automatic_cache_pricing.py`).
4. Call 1 was reserved and settled by nothing, by design: the evaluation door takes no stream sink, so the stream was exercised at the adapter boundary and its usage is recorded here rather than in the store.
