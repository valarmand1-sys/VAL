# OpenAI cache-boundary proof — STOPPED, 14 September 2026

Owner-authorised (ruling of 14 September 2026, §8): one three-turn scratch-store measurement, $0.20 maximum, to prove the explicit `prompt_cache_breakpoint` on the last retained history message is honoured by the provider. **Result: the provider rejected the request shape; no retained-history reuse was measured; admission and cutover are not enacted.** Raw output: `result-attempt1.json`, `result-attempt2.json`, `result.json` (attempt 3). Harness: `harness_cache_proof.py`.

## What was implemented (commit `3144160`, CI green)

`OpenAIAdapter._request` sends the message Val Core flags as the last retained history message (`Message.cache_breakpoint`, set by context assembly on `messages[-2]` — Val's reply preceding the current turn) as one `input_text` block carrying `prompt_cache_breakpoint: {"mode": "explicit"}`; the implicit breakpoint is kept; nothing else in the request changes. The pinned SDK (`openai==3.1.0`) types `EasyInputMessageParam` with `role: "assistant"` and a content list of `ResponseInputTextParam`, and `ResponseInputTextParam` carries `prompt_cache_breakpoint` — so the shape is representable in the client. Deterministic tests (`test_openai_history_breakpoint.py`, `test_history_breakpoint_metadata.py`, one Anthropic-unchanged test) pin that shape.

## The three attempts

| Attempt | What happened | Provider spend |
|---|---|---|
| 1 (16:59 CDT) | Turn 1 completed: 7,172 input (7,169 written cold, persona and the payload), 16 output, $0.036177, first text 1,933 ms. The harness then stopped itself before turn 2: its pre-call check used the ledger's byte-based reservation bound ($0.162 for a call whose measured cost is $0.036) against the $0.20 cap. Not a provider failure. | $0.039923 |
| 2 | Pre-call check corrected to the honest worst case (everything written at $5/M plus the 200-token ceiling), but on a fresh store the "largest input seen" was zero and it fell back to the bound; stopped before turn 1's Sol call. One classification call. | $0.002871 |
| 3 | Turn 1 completed: 7,172 input — **4,821 read** (the persona, still cached from attempt 1) and 2,348 written; 90 output (78 reasoning); $0.015480. **Turn 2 rejected by OpenAI with HTTP 400** before any token was billed: `Invalid value: 'input_text'. Supported values are: 'output_text' and 'refusal'.` at `input[1].content[0]` — the flagged assistant message. The call is on the record as `terminal_state = failed`, cost unknown (settled at its reservation maximum on the scratch ledger, as doctrine requires). | $0.019226 (classification $0.003746; Sol $0.015480; the rejected call billed nothing per the provider) |

**Total provider spend across the attempts: $0.062020** of $0.20. No House material; Sol medium; persona v1.8 (digest `1608715f…`) on every turn.

**Breakpoint location as transmitted (attempt 3, turn 2):** four input items — [user primer, **assistant reply (marked, 31 characters)**, state envelope, current question]; `prompt_cache_options` absent (implicit mode kept). The marker was where the ruling placed it; the provider refused the block type on an assistant item.

## The finding

- The API accepts `input_text` (the only text block type that carries `prompt_cache_breakpoint` in SDK 3.1.0) on **user and developer** items only. Assistant items must use `output_text` or `refusal`, and `output_text` has no `prompt_cache_breakpoint` field in the pinned client. The prompt-caching guide lists the messages eligible for a breakpoint as user messages, the last tool response in a group, and the last developer message in the initial group — assistant messages are not among them.
- Therefore **the ruled placement — the end of the last retained history message, which on Val's request shape is Val's own reply — cannot be represented cleanly in the pinned client**, and the SDK's static types did not reveal that. Per the ruling of 14 September 2026 §6 this is a stop, not a second request path.
- The code committed at `3144160` sends a shape OpenAI rejects on any OpenAI conversation call with retained history. **No production route reaches it** (Sol is `NOT_ADMITTED` and Anthropic's adapter is untouched), and the candidate lane is the only caller; it is left in place pending the ruling below rather than silently replaced by a different placement.

## The smallest options, for ruling

1. **Mark the last retained *user* history message instead** (an `input_text` block on a user item — supported). The reusable prefix would be persona + history through the last user turn; only Val's final reply, the envelope and the new message would be written each turn. Two ways to do it, either of which is a decision: (a) context assembly flags `messages[-3]` for every provider (the Anthropic path would then cache one message less of history — a behaviour change on the incumbent), or (b) the OpenAI adapter, on a flagged assistant message, marks the nearest preceding user message (provider-specific placement inside the adapter; the flag's meaning becomes "the boundary lies at or before here"). (b) is narrower and touches nothing Anthropic sends.
2. **Wait for a client/API that carries the field on `output_text`** — not in the pinned SDK; unverifiable here.

Not proposed: switching to `mode = explicit`, restructuring the envelope, or moving the envelope before the history (an ordering change the ruling forbids).

## What this leaves

- Cutover is not enacted; Sol remains `NOT_ADMITTED`, no profile, no fallback; the incumbent serves.
- Turn 1 of attempt 3 confirms again that the **persona prefix is reused** across conversations (4,821 read) — the history-loss finding of Stage B stands, and its correction awaits the ruling above.
