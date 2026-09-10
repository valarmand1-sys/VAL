# The strip route on a long correction — retry, route, and what is actually current, 10 September 2026 — report only

Nothing here is changed. No provider call was made for this report. The suite addition ruled "regardless of which route is used" is drafted as `strip-conformance/v3/` (v2 + S15, S16), not frozen and not run.

## What happened, from the store

Live turn 18:25:39, House Armand, a 1,269-character correction quoting Val's own sentence, classified consequential. The strip on `sonnet-5` (effort `high`, output ceiling `STRIP_MAX_OUTPUT_TOKENS = 4096`) returned 4,096 output tokens and terminal state `truncated` in 40.1 s; the ruled bounded retry, identical in configuration, schema, input and ceiling, returned 4,096 tokens `truncated` in 41.6 s. Both unparseable; the exchange was recorded `ordering = contaminated`; the blind position then ran on the whole message (23.6 s, $0.097) and the response followed (25.1 s, $0.076). Two strips: 81.7 s and $0.088 for nothing.

**What the 4,096 tokens were.** A conformant strip result for this message is a JSON object of a few hundred tokens (the spans are verbatim copies of short sentences). Sixty-four Sonnet strip calls in the exported qualification stores produced 79–1,774 output tokens, median 305, on inputs of 1,149–1,231 tokens, every one `complete`. Sonnet 5 runs adaptive thinking, thinking tokens are output tokens under `max_tokens`, and the effort parameter "affects all tokens in the response, including thinking"; at `high`, the default, the model "thinks on most requests and at greater length". On this message shape it thought past the whole ceiling before emitting the object. The 18:14 turn, 1,246 tokens of a different shape, took 293 output tokens and 3.7 s on the same route. The ceiling was consumed by thinking, not by output.

## 1. The retry as ruled, and what should follow a failed strip

**The retry.** The 9 September rule retries an *invalid* structured result once, identically, on the grounds that an unparseable reply may be a transient formatting failure. A reply that ended at the output ceiling is not that: the terminal state is `truncated`, the adapter already records it, and an identical request is overwhelmingly likely to truncate identically — which is what the store shows. Three options, with what each costs on the captured turn:

| Option | Behaviour on `truncated` | On the captured turn | Trade-off |
|---|---|---|---|
| **A. No retry on truncation** | `truncated` is treated as a determinate failure of the attempt, not a transient one: contaminated after one call; `invalid` for any other reason keeps its one identical retry | saves 41.6 s and $0.044 | Narrowest change; keeps the ruled retry where it can help (a malformed but complete reply). |
| B. Retry with a raised ceiling | second attempt at, say, 8,192 or 16,384 | unknown whether it completes; costs up to $0.088 or $0.17 more per attempt at Sonnet's $10/MTok output, and up to 80–160 s | Pays more to find out whether the model finishes; effort, not the ceiling, is the variable driving the overrun. |
| C. Fail fast to contaminated, no second call | as A, and also no retry for any invalid result | saves the same on this turn; loses the retry on the malformed-but-complete case, which the v2 conformance runs never needed (0 retries in 224 calls) | Simplest; the evidence says the retry has never yet paid for itself. |

The terminal state distinction is already in the record (`terminal_state = truncated` versus `complete`), so A is a one-condition change in `_strip`. B is the only option that could recover this shape on Sonnet at `high`, and it is the one the evidence argues against: the second attempt's cost is bounded only by the new ceiling.

**After a failed strip.** Today a contaminated exchange still runs the blind position on the whole message, with the preference in view, and then the response: two partner calls whose first cannot count as enforced ordering. On the captured turn that was $0.097 and 23.6 s for a position marked `contaminated`. The 7 September ruling permits the contaminated path only because the position "explicitly does not claim independence"; it does not require the call to be made. What the contaminated blind call buys: a recorded position and a reconciliation verdict (`held`, here) for the deliberation record — evidence for the prediction ledger, but not for point 5, and formed after exposure, which is the state §4.1 says a position rationalises toward. What collapsing would cost: that record, on the minority of consequential turns where separation fails. **My reading:** a contaminated exchange should collapse to the ordinary response path, recording the contamination reason and writing no blind row — the same shape as the `no_preference` collapse — because a position formed with the preference in view is the thing the machinery exists to avoid, and paying a partner call to record one is spending on the failure mode. Whether the ledger value of a contaminated position outweighs that is the ruling; nothing is changed.

## 2. The strip route — Sonnet-specific, or any structured route?

**What can be established without a provider call.** The failure is not in the schema, the parser, or the validator: 224 v2 conformance calls parsed and validated on both designated routes, and the live 18:14 strip parsed. It is not the input size: 1,490 tokens is within any route's context. It is output behaviour — reasoning consumed the ceiling — and that is a property of the model and its effort setting, which no deterministic test can decide for a route that has not been called on the shape. What the evidence does establish about each route:

- **Sonnet 5 at `high`** (the registered strip route): thinking is adaptive and effort-steered; the first-party guidance for Sonnet 5 places `medium` as "cost-saving step-down from the default, comparable to Claude Sonnet 4.6 at high effort" and `low` "for high-volume or latency-sensitive workloads". A strip is a mechanical separation task with a strict schema, the case the Opus 4.7 guidance names for overthinking at high settings. The registered effort is the default, never chosen for this task.
- **GPT-5.5 snapshot (`gpt-5.5-2026-04-23`)** at `medium`: reasoning tokens "are billed as output tokens" and count toward `max_output_tokens`; hitting the cap during reasoning returns `incomplete` / `max_output_tokens`, which the adapter maps to `TRUNCATED` — the same failure class is possible on any reasoning route. GPT-5.5 scored 112 of 112 on suite v2 with zero retries, but the suite's longest case is 289 characters and this shape is 1,269.

**So: the mechanism is generic to reasoning routes at an effort that thinks freely under a small ceiling; whether it fires on this shape is route- and effort-specific, and cannot be settled deterministically.** The suite v3 cases S15 and S16 are the instrument; running them is a provider activity.

**Cost figure, under the standing rule, if you authorise a run.** S15 and S16 (≈1,500 input tokens each), three samples each, per route:

| Route and effort | Per call, typical | Per call, worst (truncates at 4,096) | Six calls, worst |
|---|---|---|---|
| Sonnet 5, `high` (as registered) | $0.006 | $0.044 | $0.27 |
| Sonnet 5, `medium` or `low` | $0.006 | $0.044 | $0.27 each level |
| GPT-5.5 snapshot, `medium` (OpenAI balance) | $0.015 | $0.13 | $0.78 |
| GPT-5.6 Terra, `medium` (unregistered; needs registration first) | $0.006 | $0.05 | $0.31 |

A run covering Sonnet at three efforts and GPT-5.5 is at most about $1.60, typically under $0.30; each route's calls are Protected-eligible under the existing rulings. **Recommendation:** run S15 and S16 on Sonnet at `medium` and `low` and on the GPT-5.5 snapshot at `medium` before any route decision; do not switch on the strength of the v2 score alone, since v2 never contained this shape. Nothing is switched here.

## 3. What is actually current — first-party documentation read today

**OpenAI.** The model catalogue (`developers.openai.com/api/docs/models`, read today) lists **no GPT-5.5 model anywhere, including under legacy**; it lists **GPT-6 Astra** (`gpt-6-astra`, "our most capable model"), and the **GPT-5.6** family: **Sol** (`gpt-5.6-sol`, alias `gpt-5.6`, flagship), **Terra** (`gpt-5.6-terra`, "balances intelligence and cost"), **Luna** (`gpt-5.6-luna`, "optimized for cost-sensitive workloads"), and Cyber. The deprecations page carries **no entry for GPT-5.5 or `gpt-5.5-2026-04-23`** — no announced shutdown date — and lists GPT-5.6 models only as recommended replacements for older retirements. The pricing page still prices GPT-5.5 ($5 / $0.50 cached / $30 per MTok below 272K context; $10 / $1 / $45 above). **Reading: GPT-5.5 is superseded and off the catalogue but still served and priced, with no retirement schedule published.** The structured-outputs guide states strict JSON schema is available "on gpt-4o-mini, gpt-4o-mini-2024-07-18, and gpt-4o-2024-08-06 model snapshots and later" and recommends `gpt-6-astra` for new projects; it warns that reaching the max-tokens limit yields an incomplete, possibly non-conforming output. Reasoning: seven effort levels (`none` … `max`); reasoning tokens billed as output and counted against `max_output_tokens`.

| OpenAI candidate for the structured profile | Context / max output | Price per MTok (in / cached / out) | Structured outputs | Effort | Adapter work |
|---|---|---|---|---|---|
| `gpt-5.5-2026-04-23` (registered) | 1.05M / 128K | 5 / 0.50 / 30 (2× / 1.5× above 272K) | yes | default `medium` | none; **not in the catalogue** |
| **`gpt-5.6-terra`** | 1.05M / 128K | **2 / 0.20 / 12** | yes ("structured_outputs") | `none`…`max`, default `medium` | registry entry only: same Responses API and `reasoning.effort`; cached-input rate to add to the entry; verify `none` behaviour for a strip |
| `gpt-5.6-luna` | 1.05M / 128K | 0.20 / 0.02 / 1.20 | yes | as Terra (verify) | as Terra; capability for a verbatim-span strip unproven |
| `gpt-5.6-sol` | 1.05M / 128K | 4 / 0.40 / 20 | yes | as Terra | as Terra; dearer than Sonnet for a structured task |
| `gpt-6-astra` | 1.05M / 128K | 10 / 1 / 50 | yes | `low`…`max`, no `none` | as Terra; a partner-class price, not a structured-route price |

**Anthropic.** The models overview and deprecations page (read today): **Claude Sonnet 5 is Active**, `claude-sonnet-5`, $2 / $10, 1M context, 128K output, adaptive thinking, default effort `high`, retirement "not sooner than June 30, 2027"; structured outputs supported. **Claude Haiku 4.5** (`claude-haiku-4-5-20251001`) is **Active**, $1 / $5, 200K / 64K, extended thinking only, **effort not supported**, retirement "not sooner than October 15, 2026" — unchanged since OP-4 was recorded, and no deprecation notice has been posted; Anthropic gives at least 60 days' notice, so the earliest possible notice-to-retirement window has not yet opened. No newer Haiku is listed. Claude Opus 5 is Active (retirement not sooner than July 24, 2027). Sonnet 4.6 and 4.5 remain Active legacy models with structured-output support; nothing on Anthropic's side is newer than what the registry holds.

| Anthropic candidate for the structured profile | Context / max output | Price per MTok (in / out; cache write 1h / read) | Structured outputs | Effort | Adapter work |
|---|---|---|---|---|---|
| `claude-sonnet-5` at `high` (registered) | 1M / 128K | 2 / 10; 4 / 0.20 | yes | `low`…`max`, default `high` | none; the effort is a registry field |
| `claude-sonnet-5` at `medium` or `low` | same | same | yes | as above | **a new registry entry** (effort is part of the configuration identity, ruled 8 September) |
| `claude-haiku-4-5-20251001` (classifier) | 200K / 64K | 1 / 5; 2 / 0.10 | yes | not supported | none; retirement not sooner than 15 October 2026 |

**What the registry got wrong and right.** The `gpt-5-5-20260423` entry names a model that is served and priced but no longer catalogued, so the 112 of 112 was scored against a superseded model, as you said; the entry's rates and limits still match the pricing page. Nothing is registered for GPT-5.6 or GPT-6; the earlier inventory named Sol and Terra and did not verify Luna, Cyber or GPT-6 Astra, which exist. Sonnet 5 is current and its registered rates match. Haiku 4.5's OP-4 date stands.
