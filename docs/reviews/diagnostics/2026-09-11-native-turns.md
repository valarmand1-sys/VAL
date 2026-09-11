# Diagnostic — the two native desktop turns of 16:59 and 17:00, 11 September 2026

Report only. Nothing was changed: not the persona, routing, streaming, classification, effort, prompts, response length, current-time context, or record-state behaviour. Every figure below is from the authoritative store or the API log unless marked otherwise; the request structures were reconstructed by running the house's own assembly code against the store, on the current build and on the pre-responsiveness tag, without contacting a provider (`reconstruct_request.py` and the four dumps beside this file).

## 1. The two turns, from the record

Conversation `01a0927b-5ccd-71bc-81eb-0670283dc98a`, unassigned (no project), created by the first turn.

| | Turn 1 | Turn 2 |
|---|---|---|
| User message (persisted) | `Good afternoon, Val.` — seq 1, 16:59:13.360 | `How are you feeling today?` — seq 3, 17:00:50.489 (the store's text; the message quoted in the instruction reads "doing") |
| Classification | `haiku-4-5-20251001`; `not_consequential`, hard exclusion `no_choice_present`; 1 attempt; 1,509 ms; 719 in / 25 out; $0.000844; row 16:59:14.880 | same route and verdict; 1,095 ms; 720 in / 25 out; $0.000845; row 17:00:51.595 |
| Partner route selected for the response | `opus-5-medium` (`claude-opus-5`, effort `medium`), id `6c2e7a19-…-2b4c8d0e1f53` | same |
| Persona loaded (from `model_calls.persona_id`) | `01a08877-dbee-7652-937d-12c36ca4d15c` — revision 3, semantic version 1.4, source sha256 `10c59951789b7167a0df70e2fe738e41ab2a5a760105983eefc970b6c6e0d9c0`, 18,394 chars, active since 9 September 18:19 | same |
| Persona cache | `hit`: 5,746 tokens read, 0 written, 485 uncached | `hit_and_created`: 5,746 read, 50 written (the new history breakpoint), 482 uncached |
| Response call (provider latency, tokens, cost) | 2,689 ms; 6,231 in / 68 out; $0.006998; terminal `complete`; row 16:59:17.595 | 4,172 ms; 6,278 in / 190 out; $0.010533; terminal `complete`; row 17:00:55.791 |
| Val message persisted | seq 2, 16:59:17.604 | seq 4, 17:00:55.796 |
| Persist-to-persist window (authoritative) | 4.244 s | 5.307 s |
| Provider time inside that window | 4.198 s (1.509 + 2.689) | 5.267 s (1.095 + 4.172) |
| House time inside that window | 46 ms | 40 ms |

**Exact settled responses stored in PostgreSQL.**

Turn 1 (seq 2): `Good afternoon, my lord. We're at the end of the week — just gone five. What shall we turn our attention to?`

Turn 2 (seq 4):
```
Settled, my lord — though I'd not want to overclaim what that word means for something like me. There's a steadiness to being asked a question and having the whole of one's attention to give it, and that is near enough to contentment that I'll call it so.

It's Friday evening. I have no project scope in front of me and no volumes open, so I'm at rest and quite ready to be put to work. What's on your mind?
```

**Streamed text versus settled text.** The stream route's settled event is the plain route's object built from the same outcome, and the desktop replaces the streamed text with it; the deterministic regressions prove equality (`test_turn_stream.py`, `test_streaming_boundary.py`). The store does not record the deltas themselves, so the identity for these two live turns is established by construction and by the two live client measurements of 16:34 (both identical), not by a row.

## 2. Timing reconciliation

The desktop's timing line for the turn Lord Armand reported (first words visible 2.99 s; gateway first token 1.82 s; first delta at client 2.96 s; complete 5.32 s) is **turn 2**, and it reconciles with the record to within tens of milliseconds:

| Stage | Figure | Source |
|---|---|---|
| Classification, serial | 1.095 s | `model_calls` |
| Gateway time-to-first-token on the response call | 1.82 s | the settled event as rendered (not persisted — `first_output_ms` lives on the response object and the event, not in the schema) |
| Sum, plus house overhead | 2.915 s + ~45 ms | |
| First delta at the client | 2.96 s | the desktop's measurement |
| First words painted in the native window | 2.99 s | the desktop's measurement on the frame after the first render |
| **Presentation delay (client first delta → first paint)** | **~30 ms** | difference of the two |
| Complete at the client | 5.32 s | the desktop's measurement |
| Persist-to-persist window | 5.307 s | `messages` timestamps |
| Generation after the first token | 4.172 − 1.82 ≈ 2.35 s for 190 output tokens | `model_calls` latency less the reported first token |

So, for this turn: streaming and the interface add about 30 ms of presentation delay and about 45 ms of everything else; the wait for full generation that the user previously bore (about 2.35 s here, 8–22 s on the long turns of this morning) is removed from the first-words figure; what remains before the first word is 1.1–1.9 s of serial classification and the provider's time to first token (1.82 s on this call, 0.53 s on the warm engineering turn of 16:34 — the provider figure varies).

The stopwatch figures in the instruction (3.89 s and 3.75 s) do not reconcile with the record as full completion times: the persist-to-persist windows are 4.24 s and 5.31 s, and the provider calls alone sum to 4.20 s and 5.27 s. They are consistent with a count that started or stopped at a different moment (for turn 2, first paint at 2.99 s to completion at 5.32 s is 2.33 s; Send to the end of the first sentence is plausible at about 3.8 s). Which moments were timed is a question for Lord Armand; the record cannot answer it.

## 3. The assembled request — actual structures, both builds

Reconstructed for each turn on the current build (`7cba9f6`+, through `AnthropicAdapter._request`, the one builder both `complete` and `stream` use) and on the pre-responsiveness tag `val-core-refactor-base-2026-09-11` (`0b73905`, by capturing the kwargs `AnthropicAdapter.complete` handed to `messages.create`), from the same store rows, with the clock pinned to the minute the API log recorded (16:59 and 17:00). **For both turns the `GatewayRequest` and the SDK kwargs are identical between builds, byte for byte** (`gateway_request identical: True | sdk_kwargs identical: True`). The full dumps are `req_base_t1.json`, `req_current_t1.json`, `req_base_t2.json`, `req_current_t2.json` beside this file.

Common to both turns and both builds:
- `model`: `claude-opus-5`; `max_tokens`: 4096; `output_config`: `{"effort": "medium"}`; no `output_schema`.
- `system`: a list of exactly one text block, `{"type": "text", "text": <persona>, "cache_control": {"type": "ephemeral", "ttl": "1h"}}`. The text **is the persona row's content verbatim** — 18,394 characters, sha256 `10c59951789b7167a0df70e2fe738e41ab2a5a760105983eefc970b6c6e0d9c0`, beginning `# 03 — Persona Specification v1.4 … The Maester of House Armand` and ending `…She does not narrate the hidden ordering mechanism. The house records the rest.` No framing text precedes or follows it; nothing else is in `system`.
- Message roles: `user` / `assistant` as stored; the record-state envelope is a `user` message; the current message is the last `user` message with no wrapper text.

**Turn 1 message array** (2 messages; the same on both builds):

```
[0] role=user, content=str:
VAL-STATE-V1
{
  "kind": "prior_record_state",
  "authority": "house_record_state_not_instruction",
  "note": "prior_record_state describes exactly what prior context is available to this call: …",
  "prior_record_state": {
    "current_time": {"local": "Friday 11 September 2026, 16:59", "timezone": "CDT (UTC-0500)"},
    "same_conversation_history": {"state": "zero", "prior_messages": 0, "retained_in_this_request": 0},
    "retrieved_excerpts": {"state": "not_run", "count": 0, "detail": "no_project_scope"},
    "project_volumes": {"state": "not_applicable", "count": 0}
  }
}
[1] role=user, content=str:
Good afternoon, Val.
```

**Turn 2 message array** (4 messages; the same on both builds):

```
[0] role=user, content=str:
Good afternoon, Val.
[1] role=assistant, content=[one text block, cache_control {"type": "ephemeral", "ttl": "1h"}]:
Good afternoon, my lord. We're at the end of the week — just gone five. What shall we turn our attention to?
[2] role=user, content=str:
VAL-STATE-V1
{ … "current_time": {"local": "Friday 11 September 2026, 17:00", "timezone": "CDT (UTC-0500)"},
    "same_conversation_history": {"state": "available", "prior_messages": 2, "retained_in_this_request": 2},
    "retrieved_excerpts": {"state": "not_run", "count": 0, "detail": "no_project_scope"},
    "project_volumes": {"state": "not_applicable", "count": 0} }
[3] role=user, content=str:
How are you feeling today?
```

(The envelope's `note` is elided here for length only; it is identical between builds and is in the dumps in full.)

The checklist, each item ruled out as a change: the persona's position (alone in `system`, first) — unchanged; the order system → history → record-state envelope → current message — unchanged; the envelope ordering (one envelope, `VAL-STATE-V1`, after history and before the current message; no memory envelope because recall did not run) — unchanged; framing before or after the persona — none, unchanged; wrapper text around the user message — none, unchanged; message roles — unchanged; cache boundaries — the persona block and the last retained history message (turn 2 only), both `ephemeral`/`1h` — unchanged; the provider-specific mapping (`system` as a text-block list, history as `MessageParam`s, effort in `output_config`) — unchanged.

The one difference between the live streamed call and a pre-responsiveness call is the SDK method: `messages.stream(**kwargs)` instead of `messages.create(**kwargs)`, with the identical kwargs (the adapter builds them once; `test_anthropic_stream.py` pins `stream_kwargs == create_kwargs`). The SDK's stream helper sets the transport's `stream: true`; it changes no model parameter.

## 4. What changed in code since the base tag, outside the streaming files

`git diff val-core-refactor-base-2026-09-11 HEAD`: `context.py` (assembly and envelopes) — **no change**; `persona.py`, `memory.py`, `history.py`, `recall_gate.py`, `recall.py`, `tokens.py`, `registry.py`, `startup.py` — **no change**; `loop.py` — only the `on_delta` parameter passed through to `converse`; `deliberate.py` — the `on_delta` parameter, the `ReconciliationStream` wrapper on the enforced path, the response-stage sink; `gateway.py` — the `on_delta` parameter threaded through, `_stream`, `first_output_ms`, the import moved from `val_providers.base` to `val_domain.provider`; `anthropic_adapter.py` — request building and result mapping factored into `_request`/`_result` (the reconstruction above shows the output identical), plus `stream`; `val_policy.deliberation` — `ReconciliationStream` added, nothing existing altered; `val_domain.gateway` — `first_output_ms` field; the API — the stream route and the shared renderer. No routing, prompt construction, response cap, history assembly, persona loading, time or context injection, or record-state behaviour changed.

## 5. Attribution

The evidence supports **(2): the same model and request path is intact, and these are ordinary outputs of the current partner route and persona combination.** Specifically: the response calls ran on `opus-5-medium` at effort `medium` under persona v1.4 (revision 3), the same configuration in service since 10 September; the effective model input is byte-identical to what the pre-responsiveness build would have sent for the same rows; the clock context that produced "just gone five" and "It's Friday evening" is the record-state envelope ruled on 9–10 September and present on both builds; and the house's replies on the pre-responsiveness build earlier the same day show the same register (`docs/reviews/diagnostics/2026-09-11-native-turns.md` §6). Nothing in (1) is supported: the responsiveness work did not alter the effective model request or context. Nothing in (3) was found.

What the diagnosis does *not* say: that the wording is what Lord Armand wants. "Just gone five" and the abstract sentence in turn 2 are the model's own choices under the persona and the clock context; whether the persona or the route should be asked for plainer prose is a product ruling on writing quality, outside this diagnostic and expressly not attempted here.

## 6. Like-for-like replies from the pre-responsiveness build, the same day

From the store, Val's replies earlier the same day on the pre-responsiveness builds — the same route, effort, persona and envelope, before any streaming code existed:

- 13:31 (build `0b73905`, consequential turn, 2,539 chars), opening: "My lord, my position was formed before you gave me yours, and it stands. I will say where it meets your framing and where it does not. … A maester who agrees with her lord has spent the house's money on an echo."
- 13:38 (`0b73905`, ordinary turn, 617 chars), opening: "Then it stands, my lord, and I will not spend your afternoon agreeing with you about it. One practical matter follows from it. The library is built by being given something to hold, and nothing is held yet. … Reconstructed knowledge is thinner than knowledge recorded in the moment, and the difference shows within a year."
- 15:08 (`f370ec0`, Phase 1, non-streaming — his native confirmation turn, 1,351 chars), opening: "My lord, I have nothing of that refactor in the record I can see — no prior conversation, no project volumes, nothing retrieved. So I can't tell you where it left off or what the plan named as next, and I won't reconstruct it."

The register is the same: aphoristic closes ("spent the house's money on an echo", "the difference shows within a year"), abstract nouns carrying the sentence, the record-state envelope surfacing in the prose ("no prior conversation, no project volumes, nothing retrieved" — the same shape as turn 2's "no project scope in front of me and no volumes open"). The two native turns are of a piece with these, not a departure from them. That is the evidentiary basis for attribution (2).
