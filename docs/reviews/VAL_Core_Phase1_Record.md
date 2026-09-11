# Val Core Phase 1 — the provider-neutral boundary, streaming-capable — 11 September 2026

Ruling: "Begin Phase 1: Val Core Provider-Neutral Refactor." Objective: make the existing system structurally provider-neutral without changing Val's visible behaviour or weakening any accepted capability; streaming supported by the architecture from the beginning; conversational responsiveness a formal product requirement carried forward. Baseline tag before any change: `val-core-refactor-base-2026-09-11` on `0b73905` (`strip-closed-2026-09-11` preserved on `6216756`).

## 1. What was found before changing anything

The boundary already existed in shape and was already SDK-clean: `ProviderAdapter` was a protocol, every adapter mapped its SDK's dialect to `ProviderResult` and `TerminalState`, and CI confined SDK imports to `val_providers`. What was not provider-neutral *structurally*: the boundary types lived in the providers package, so the core (`val_gateway.gateway`) imported its own contract from the package it was meant to be independent of; and there was no streaming contract at all, so streaming would have had to be retrofitted through every layer.

## 2. What Phase 1 built

- **`val_domain.provider`** — the boundary, in the domain: `ProviderResult` (moved, unchanged), `ProviderAdapter`, and the streaming contract — `TextDelta`, `ProviderEvent`, `StreamingProviderAdapter`, `DeltaSink`, `supports_streaming`. Streaming is a declared per-adapter capability, never inferred. `val_providers.base` re-exports every name unchanged, so no existing import moved; the error normalizer stays in the providers package because it is the one piece that knows SDK exceptions.
- **The core depends on the domain, not the providers.** `val_gateway.gateway` imports the boundary from `val_domain.provider`; inside `val_gateway` only the composition root (`startup.py`) imports `val_providers`, and a test pins that (`test_core_boundary.py`). Repository-wide dependency direction unchanged (`check_boundaries.py` green).
- **Streaming through Val Core.** `Gateway.converse`, `complete` and `complete_with_configuration` accept an optional `on_delta` sink owned by the caller inside the core. When given and the adapter declares streaming, `_call_and_settle` consumes the adapter's events: each `TextDelta` is forwarded to the sink, the first is timed (`GatewayResponse.first_output_ms`), and the terminal `ProviderResult` is settled by the identical code that settles a completed call — reservation before, `model_calls` row, cache-usage row, ledger settlement, terminal doctrine. A stream that ends without a result is a provider failure settled as unknown. The loop (`loop.send`) and the deliberation orchestrator (`deliberate.send`) accept and pass the sink to the **response** stage only; classification, strip and blind position never stream. On the enforced path the sink is wrapped in `ReconciliationStream` (policy): her prose streams, the typed verdict block never does, even when the marker arrives split across deltas.
- **Anthropic behind the adapter, in both modes.** `AnthropicAdapter.stream` uses the SDK's `messages.stream`, yields `TextDelta` for each text delta, then the final message mapped by the same function `complete` uses; both modes build the identical request. The OpenAI adapter conforms to the boundary as before and declares no streaming — the second-provider step, not Phase 1.
- **No schema change, no migration, no persona change, no strip change, no API or desktop change.** The desktop path is exactly as before: `POST /turns` returns the settled turn; nothing streams to the UI yet. The `first_output_ms` figure is on the response object and in the log, not in the schema.

## 3. Evidence

**Deterministic (1,140 tests; 1,116 pre-existing, none modified; 24 new):** `test_provider_boundary.py` (streaming declared, never inferred; the boundary module imports only the domain), `test_boundary_reexport.py` (the providers package re-exports the domain's objects; Anthropic declares streaming, OpenAI does not), `test_reconciliation_stream.py` (prose forwarded in order; marker withheld whole at every split size; nothing after it; a marker-less reply released on close), `test_anthropic_stream.py` (identical request in both modes; identical mapped result; truncation and mid-stream failure mapped as in completion; effort `none` refused before contact), `test_core_boundary.py`, and `test_streaming_boundary.py` through the orchestrator on real PostgreSQL: an ordinary turn streams every delta in order and persists the settled text; a truncated stream is presented but never spoken; a stream without a terminal result is a provider failure with the cost recorded unknown; an adapter without `stream` is served by `complete` when a sink is offered; on a consequential turn only the response stage streams and the verdict block never reaches the sink, with the streamed prose equal to the persisted message; the reservation is durable before the first delta and `first_output_ms` is measured; a completed call reports none.

**Pre-existing test files touched by the refactor: none.** Every one of the 1,116 pre-existing tests passes unchanged; `git status` on the test directories shows only the six new files.

## 4. The real streamed call

One TITLE-class structured request through `Gateway.complete(request, on_delta=…)` in the scratch store, routed by the gateway to the cheapest structured route (`haiku-4-5-20251001`), against the real Anthropic API — no persona, no conversation, nothing of Val's. Cost stated before running: under $0.001.

| Figure | Value |
|---|---|
| Route | `haiku-4-5-20251001`, terminal `complete` |
| Gateway `first_output_ms` (time to first generated-text delta) | 673 ms |
| Gateway `latency_ms` (call complete) | 763 ms |
| Wall clock at the caller | 772 ms |
| Deltas forwarded to the sink | 4 (first at 677 ms, last at 762 ms) |
| Streamed text equals settled text | yes |
| Tokens / cost | 46 in, 14 out, $0.000116 |
| `model_calls` row | one, `title`, `complete`, 763 ms, $0.000116; reservation `settled` |

Time-to-first-token as observed at the gateway; nothing was rendered, so no user-visible figure exists yet — that measurement belongs to the phase that carries the stream to the interface.

## 5. The real end-to-end turn

Recorded below on completion.

## 6. Requirements carried forward (not implemented in Phase 1)

Recorded in `01-architecture.md` §5.1 (amendment of this date): ordinary text turns begin visibly responding — Val's own generated text on screen, not a progress affordance — in approximately 1–2 seconds; continuous streaming to presentation; time-to-first-token, time-to-first-generated-text-visible-in-the-UI, and total completion time reported separately, the user-visible figure governing; faster routes preferred only at the required quality bar; consequential turns may carry serial reasoning stages but the final response stage streams once it begins; providers qualified by latency, cost, quality and task class without changing the upper-layer contracts; a real desktop demonstration is the final acceptance. What Phase 1 makes possible: the response stage can now stream through the core, and the gateway measures its first output. What remains for the next phase: the API and desktop presentation of the stream, the user-visible measurement, and the serial classification call that stands between the user's message and the partner call on every ordinary turn (1.4–1.9 s on the two live turns of 11 September).

## 7. Open acceptance gate

The two-live-provider proof remains open until the OpenAI API is configured and funded; the boundary is built so that the second adapter is a registry entry and a `stream` implementation, not a change to any upper-layer contract.
