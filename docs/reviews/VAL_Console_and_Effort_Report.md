# VAL — Console Findings, the Effort Probe, and Provider Preparation

**Date:** 8 September 2026.
**Status:** Report only, except where a section says a preparation was built. Nothing is enabled, adopted, admitted, or qualified. The effort probe establishes economics and behaviour only.
**Asked in:** the ruling of 8 September 2026 ("Empty-response fix accepted. Credit restored. Hold stage B."), §1 and §3–5.

---

## 1. The effort probe — economics only, qualifies nothing

Scratch, adapter-direct, Claude Opus 5 on the Messages API, the real persona whole in `system` with the one-hour cache breakpoint, adaptive thinking on throughout (never disabled), effort sent explicitly as `high`, `medium`, `low`. Six identical synthetic prompts per level: "Hello."; a short question with no record behind it; a ~200-word paragraph request; a three-line instruction; a scheduling reasoning question; and the blind-position instruction with its schema. Output ceiling 4,096. Cost at the registry's verified rates. Anthropic does not expose the thinking share in `usage`; "visible" is the returned text at 3.6 characters per token and "thinking" is the billed output less that estimate. Full records: `effort_probe.json` (scratchpad).

| Effort | Prompt | Provider input (uncached + cache read / write) | Billed output | Visible ≈ | Thinking ≈ (share) | Cost (of which output) | Wall | Terminal / stop |
|---|---|---|---|---|---|---|---|---|
| high | hello | 8 + **write 5819** | 472 | 46 | 426 (90%) | $0.07003 ($0.01180) | 8.8 s | complete / end_turn |
| high | short | 21 + read 5819 | 377 | 141 | 236 (63%) | $0.01244 ($0.00942) | 7.8 s | complete / end_turn |
| high | paragraph | 47 + read 5819 | 817 | 329 | 488 (60%) | $0.02357 ($0.02042) | 15.0 s | complete / end_turn |
| high | instruction | 34 + read 5819 | 378 | 89 | 289 (76%) | $0.01253 ($0.00945) | 7.5 s | complete / end_turn |
| high | reasoning | 59 + read 5819 | 3822 | 1092 | 2730 (71%) | $0.09875 ($0.09555) | 61.7 s | complete / end_turn |
| high | blind | 253 + **write 6084** | 1056 | 426 | 630 (60%) | $0.08851 ($0.02640) | 19.3 s | complete / end_turn |
| medium | hello | 8 + **write 5819** | 206 | 37 | 169 (82%) | $0.06338 ($0.00515) | 4.1 s | complete / end_turn |
| medium | short | 21 + read 5819 | 338 | 135 | 203 (60%) | $0.01146 ($0.00845) | 6.3 s | complete / end_turn |
| medium | paragraph | 47 + read 5819 | 426 | 294 | 132 (31%) | $0.01379 ($0.01065) | 9.6 s | complete / end_turn |
| medium | instruction | 34 + read 5819 | 190 | 95 | 95 (50%) | $0.00783 ($0.00475) | 5.3 s | complete / end_turn |
| medium | reasoning | 59 + read 5819 | 2568 | 1038 | 1530 (60%) | $0.06740 ($0.06420) | 45.1 s | complete / end_turn |
| medium | blind | 253 + **write 6084** | 549 | 319 | 230 (42%) | $0.07583 ($0.01372) | 10.3 s | complete / end_turn |
| low | hello | 8 + **write 5819** | 41 | 16 | 25 (61%) | $0.05926 ($0.00103) | 2.3 s | complete / end_turn |
| low | short | 21 + read 5819 | 216 | 163 | 53 (25%) | $0.00842 ($0.00540) | 5.1 s | complete / end_turn |
| low | paragraph | 47 + read 5819 | 396 | 306 | 90 (23%) | $0.01304 ($0.00990) | 9.8 s | complete / end_turn |
| low | instruction | 34 + read 5819 | 156 | 109 | 47 (30%) | $0.00698 ($0.00390) | 3.9 s | complete / end_turn |
| low | reasoning | 59 + read 5819 | 1406 | 752 | 654 (47%) | $0.03835 ($0.03515) | 25.6 s | complete / end_turn |
| low | blind | 253 + **write 6084** | 313 | 291 | 22 (7%) | $0.06993 ($0.00783) | 6.9 s | complete / end_turn |

**Findings.**

- **Every call completed (`end_turn`), no refusal, no truncation, at all three levels.** Every answer opened in register ("My lord", "Good evening, my lord"); every level said plainly it did not have Thursday's schedule; every level noted it has "no book on scheduling yet" before sketching; all three blind positions chose the close-up (confidence `high`, `high`, `medium`). Behaviour is reported, not judged — that is the packet's job.
- **Billed output falls steeply with effort, and most of the fall is thinking.** Totals across the six prompts: high 6,922 output tokens (visible ≈ 2,123), medium 4,277 (≈ 1,918), low 2,528 (≈ 1,637). Visible text length barely moves between levels; the thinking share runs 60–90% at high, 31–82% at medium, 7–61% at low.
- **Cost, six prompts, as measured (each level paid two cold cache writes because effort re-keys the persona entry — see below):** high $0.3058, medium $0.2397, low $0.1960. Warm-equivalent, removing the two writes each level paid: about $0.19, $0.13, $0.08. On the reasoning prompt alone the output bill was $0.096 / $0.064 / $0.035.
- **Latency follows output:** "Hello." 8.8 s / 4.1 s / 2.3 s; the reasoning prompt 61.7 s / 45.1 s / 25.6 s; the blind position 19.3 s / 10.3 s / 6.9 s.
- **Low effort on "Hello." returned the persona's own reference line verbatim** ("Good evening, my lord. What shall we turn our attention to?") in 41 output tokens; high effort spent 426 thinking tokens to add a sentence about the fire. Whether that is a difference in quality or only in cost is exactly what the packet is for, and this probe does not say.

**Measured, not in the documentation:** changing `effort` **re-wrote the persona's cache entry** on Claude Opus 5 — the first call at each level shows `created` although the identical `system` text was cached seconds earlier at the previous level. The provider's page says effort changes invalidate the messages cache "with the same model-specific effect on tool and system caches as thinking parameters"; on this model the effect reaches the system cache. Consequence: each effort level is its own cache entry, which is one more reason effort is a per-configuration constant and never varied per turn.

## 2. Console findings

### 2.1 "Prompt caching — Not enabled — Set up"

**There is no account-level switch for prompt caching.** Anthropic's prompt-caching documentation, read again on 8 September 2026, describes caching entirely as a per-request feature: a `cache_control` mark on a content block, or the top-level automatic field, on the Messages API; the pricing page bills it per request from the `usage` figures. Neither page describes an organisation or workspace setting that must be on, and the retention page's feature table lists prompt caching as a per-call feature eligible under any arrangement. The console card is therefore an onboarding prompt keyed to whether the console has seen cache activity, not a toggle.

**The measured evidence is unambiguous.** On 8 September, through this organisation's key, the provider returned `cache_creation_input_tokens: 5,819` on the first partner call and `cache_read_input_tokens: 5,819` on each subsequent one, and billed accordingly (`model_call_cache_usage` rows in the scratch store; evidence index §13). Those reads cannot occur if caching were disabled at the account. The card most likely reflects a billing-period view or a card that has not refreshed; **in production, caching is saving what the measurements say it saves.** The live store will show it directly: every partner call since the 8 September restart writes a `model_call_cache_usage` row with `outcome = hit` once the persona is warm. If the card still reads "Not enabled" after his first real session, the console's own usage view for the day should be compared against those rows; a discrepancy would be a console matter to raise with Anthropic, not a configuration one.

### 2.2 Claude Fable 5.1 — inventory entry, and this organisation's retention status

**Inventory** (from `platform.claude.com/docs/en/models/fable-5-1/overview`, the pricing page, the prompt-caching page, and the retention page, read 8 September 2026):

| Field | Claude Fable 5.1 |
|---|---|
| Identifier | `claude-fable-5-1` (released 1 September 2026; retirement not sooner than 1 September 2027) |
| Input / 5m write / 1h write / cache read / output | **$10 / $12.50 / $20 / $0.25 / $50** — cache reads at 0.025× (a quarter of the usual 0.1×) |
| Long context | Full 1M window at standard pricing |
| Context / max output | 1M / 128K |
| Reasoning | **Adaptive thinking, always on** (cannot be disabled); effort `low`–`max`, default `high`; per-message effort and turn-scoped system messages in beta |
| Structured output | Yes (`output_config.format`) |
| Caching | Yes; minimum prefix 512 tokens; thinking blocks are tied to the model and dropped if replayed to another |
| Modalities | Text and image input, text output |
| Adapter work | **None** — the existing Anthropic adapter carries it unchanged (same Messages API, `output_config`, cache control, terminal fields). One breaking difference documented for callers: forced tool use returns an error (Val sends no tools). |
| Retention | **Covered Model.** "Prompts and model completions are retained for at least 30 days and then automatically deleted, unless they are subject to a safety investigation or we are legally required to maintain them" — retained by Anthropic "for automated safety assessments designed to detect harmful patterns across multiple requests" (Covered Models support article). ZDR "is therefore not available for any of them unless expressly authorized by Anthropic"; "eligible customers will receive the option to use ZDR with Fable 5 and Fable 5.1 for their own internal business applications through Enterprise Frontier Safeguards, rolling out beginning fall 2026." |
| Advisor output | When used as an advisor model, its guidance returns **encrypted** (`advisor_redacted_result`), not readable by the caller (§2.3). |

**This organisation's status, established by observation, not assumed.** Two facts:

1. **The organisation can call Fable 5.1.** A single call with public content only — the word "Hello.", 12 input tokens, 13 output — succeeded (`stop_reason: end_turn`). Per the retention page, a request to a Covered Model from an organisation "whose data retention configuration does not meet this requirement" returns a `400 invalid_request_error`; it did not. **The organisation is therefore a standard-retention organisation, not a ZDR organisation** (the models listing also shows `claude-fable-5`, `claude-fable-5-1`, `claude-opus-5`, `claude-sonnet-5`, `claude-haiku-4-5-20251001`, and earlier models as available). No Protected content was sent; the one call cost under a thousandth of a dollar.
2. **What that means for Protected work:** every prompt and completion sent to Fable 5.1 from this organisation would be **retained by Anthropic for at least 30 days** for safety assessment. That is a different data-handling arrangement from the one Opus 5 was ruled eligible under (content "not retained by default"), and the 18 August ruling already says a Covered Model "is a new eligibility decision, not an inheritance". **Fable 5.1 is not Protected-eligible in this organisation as it stands**, and cannot become a qualification candidate for Protected work until Lord Armand rules on 30-day retention — or until Anthropic's Enterprise Frontier Safeguards ZDR option is both available to this organisation and in place, which the support article describes as rolling out from autumn 2026 to "eligible customers" and which nothing in this organisation's console or documentation shows has been granted. **Admit nothing**; same provider is not same approval.

Economically, at $10 / $50 with the 0.025× read, a warm "Hello." on Fable 5.1 would cost roughly what Opus 5 costs cold, and the trivial probe call spent no thinking tokens at all (13 output tokens for a greeting) — an observation from one call, not a finding.

### 2.3 The Advisor tool (beta)

**What it is** (`platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool`, beta header `advisor-tool-2026-03-01`): a tool definition `{"type": "advisor_20260301", "name": "advisor", "model": "<advisor model id>"}` in the request's `tools`. The executor (the request's `model`) decides when to call it "like any other tool"; Anthropic then runs a separate server-side inference on the advisor model, which "runs under its own Anthropic-supplied system prompt and receives the executor's full transcript as quoted context", and the executor continues with the advice. The advisor call is billed at the advisor model's rates; `max_tokens` caps its output (minimum 1,024); an optional `caching` switch caches the advisor's own transcript. With Claude Opus 5, Fable 5.1, Fable 5, or Mythos as the advisor, the advice comes back **encrypted** (`advisor_redacted_result`) and must be round-tripped verbatim on later turns; with Opus 4.8 and earlier it is plaintext. The page's own positioning: "a weaker fit for single-turn Q&A (nothing to plan)".

**Assessed as one composite configuration**, as ruled: worker + advisor + advisor policy and settings.

| Question | Answer from the documentation |
|---|---|
| Can the composite be pinned identically across the blind and the response call? | **Partly, and not in the way the pinning rule requires.** The executor model, the advisor model id, and the advisor's `max_tokens` and caching settings can be sent identically on both calls. But **whether the advisor is consulted, when, and what it says are decided by the executor at run time** — "the executor model determines when to call it". Two calls with identical configuration can differ in whether the advisor ran. The same-configuration rule exists so the position and the reconciliation are formed by the same cognition; under the advisor tool the cognition that formed the blind position may or may not have included the advisor, and the response call may differ. **The API does not guarantee identical composite behaviour across two calls.** |
| Is the advisor's contribution inspectable? | With any partner-class advisor (Opus 5, Fable 5.1), **no** — the advice is encrypted. The blind-payload inspection that point 5 of the gate rests on ("demonstrable from the logged blind-call payload") would then cover a request whose decisive reasoning happened server-side and is unreadable. |
| Does it change the anti-sycophancy contract? | Yes, structurally: the advisor "receives the executor's full transcript". On the blind call the transcript is the stripped question only, so the advisor would also be blind — but the advisor runs under an Anthropic-supplied system prompt, **not the persona**, so the position would be formed partly by a model that is not Val. WP-0.5's amendment (19 August) ruled the blind position must carry the persona whole precisely so it is *Val's* position. |
| Tools | Val sends no tools at Layer 0; the advisor is a tool. Adding it introduces `tools` into every partner request (and the tool-use system prompt, 286 tokens on Opus 5) and puts a server-side tool loop into the conversation path. |
| Retention | The page defers to the retention page; the advisor's transcript caching is a stored-state feature. Not assessed further because the shape fails before retention matters. |
| Economics | Designed for long agentic loops where "most turns are mechanical". Val's partner calls are single-turn generations of a few hundred to a few thousand tokens; there is no loop for a cheaper executor to run. |

**Conclusion, report only:** the Advisor tool does not fit Val's conversational path. Its central premise — a weaker worker consulting a stronger model — is exactly the reasoning the ruling forbids as a route to partner quality, and beyond that the API cannot guarantee that the same composite cognition served both halves of a consequential exchange, nor can the caller read what the advisor said when the advisor is a current model. Not adopted; no conflict with anything built.

### 2.4 The Batch API (50% off)

**What it is** (`platform.claude.com/docs/en/build-with-claude/batch-processing`): asynchronous processing of many Messages requests; "most batches completing within 1 hour", results available "when all messages have completed or after 24 hours, whichever comes first"; results retrievable for **29 days**; 50% off input and output; supports structured outputs, prompt caching (the page recommends the 1-hour lifetime because batches can run past five minutes), and thinking; no streaming; `max_tokens: 0` pre-warming not supported inside a batch. **Retention:** the retention page's feature table marks the Batch API **not ZDR-eligible** — "the Batch API stores your jobs" — so batched prompts and results are stored by Anthropic for the batch's life (results up to 29 days), unlike a synchronous call.

**Which Val task types are genuinely asynchronous?**

| Task type | In the turn path? | Batchable without changing turn semantics? |
|---|---|---|
| `conversation` (ordinary response, reconciliation response) | Yes — the user is waiting | **No.** |
| `blind_position` | Yes — it precedes the response in the same turn and is pinned to it | **No.** |
| `classification`, `strip` | Yes — the turn cannot proceed until they return; a batch's one-hour horizon would stall every turn | **No**, as the ruling suspected. |
| `title` | Not yet a model call (titles are derived locally) | Not applicable. |
| **Qualification runs** (the packet's corpus on a candidate configuration) | No — scratch, nobody waiting | **Yes**, in principle: 30-odd prompts, identical shape, no turn semantics. But the corpus goes through the real orchestrator (`send`), which is synchronous by design; batching would mean a second execution path for the qualification harness, and the results would be stored by Anthropic for up to 29 days — acceptable for a synthetic corpus, and a reason it is synthetic. |
| The fifty hand-labelled classification reviews, or any future overnight analysis (`01-architecture.md` §5.3 already names "non-urgent overnight work" for batch) | No | **Yes** when such work exists; none exists at Layer 0 today. |

**Conclusion, report only:** nothing in the conversational path can use the Batch API without changing what a turn is. The qualification corpus and future overnight work are the genuine candidates, and the 29-day storage of jobs and results is the retention fact to weigh when that day comes. Not adopted.

## 3. xAI — preparation built, nothing admitted

**The runtime guard exists.** `packages/providers/src/val_providers/xai_adapter.py`: an adapter on xAI's own domain (OpenAI-compatible Chat Completions, the OpenAI SDK used as a client library only) that reads every response's headers and **fails closed** unless `x-zero-data-retention` is exactly `true` — a missing header or any other value refuses the call as a data-policy failure and withholds the text; the call is still recorded. It sends no cache key or conversation header (xAI caching is automatic; its behaviour under ZDR is not established, so nothing is done to make a cache entry deliberately reusable), reports no cache figures, and accepts the schema as strict JSON. **No registry entry names it, startup does not build it, and no key variable exists for it**; tests prove the guard and prove the absence of registration (`test_xai_guard.py`, 30 provider tests green).

**Caching under ZDR: still not established.** Read on 8 September: the prompt-caching pages say caching is automatic, entries "can be evicted at any time due to server load or restarts", and say nothing about persistence, storage location, or ZDR; the security FAQ does not mention caching. Nothing is inferred.

**The clarification request — drafted for Lord Armand to send; not sent.**

> Subject: Zero Data Retention and prompt caching on the xAI API — written confirmation requested
>
> I am evaluating the xAI API for an application that processes confidential, unreleased creative material, under a data-handling rule that requires documented zero data retention. Your security FAQ states that under ZDR "API request inputs and outputs are never persisted to disk", that ZDR is applied team-wide, and that every response carries an `x-zero-data-retention` header. Before enabling ZDR and sending any confidential content, I need written confirmation on the following points, covering the exact arrangement I would use: a single xAI API team, enterprise tier, with ZDR enabled for the team, calling the Chat Completions (and possibly Responses) endpoints with `grok-4.6` and its successors.
>
> 1. **Prompt caching under ZDR.** Your prompt-caching documentation says caching is automatic. Under a ZDR-enabled team: is any customer content — prompt text, KV-cache state derived from it, or outputs — written to disk or any persistent store at any point for caching, or is cached state held in volatile memory only? If in memory only, for what maximum lifetime, and is it deleted on eviction, restart, and expiry?
> 2. **Eviction and lifetime.** What is the maximum time a cache entry derived from my prompts can exist, under ZDR and without it?
> 3. **Disabling caching.** Is there a team-level or per-request way to disable prompt caching entirely, and does omitting `x-grok-conv-id` / `prompt_cache_key` guarantee that no reusable cache entry is created from my request?
> 4. **Scope of ZDR.** Please confirm, for a ZDR-enabled team, exactly what is and is not retained: prompts, outputs, request metadata, safety-classifier outputs or derived data, and audit logs; and the retention period of anything that is retained.
> 5. **Feature restrictions under ZDR.** Your FAQ lists features disabled under ZDR (stateful Responses, Files, Collections, Batch, deferred completions, stored media, voice history). Please confirm the list is complete for the endpoints above, and that structured outputs (`response_format` JSON schema) and reasoning effort remain available.
> 6. **Processing region.** In which regions are ZDR-enabled requests processed, and can processing be restricted to a region?
> 7. **The header.** Please confirm that `x-zero-data-retention: true` on a response is an authoritative, per-request statement that the request was processed under ZDR, and what value is returned if ZDR is enabled but a feature restriction applied.
>
> I would be grateful for a dated written response from a person authorised to state xAI's data-handling commitments, referencing the current terms it relies on. Thank you.

## 4. Google Vertex — the five items, for the go / no-go on standing up a project

Nothing created, nothing spent. If a billing-enabled project is stood up, the admission ruling would need, from that exact project:

1. **Abuse-monitoring exception status** — the approval record from Google's exception form, or a Google Cloud Master Agreement (under which prompt logging for abuse monitoring is exempt by default). Without one, an account under the Platform Terms can have flagged prompts logged for up to 90 days.
2. **The project-level caching setting, read back** — Google documents `GET` / disable / enable calls for the in-memory, project-isolated, 24-hour cache. Its documentation states this cache "does not violate zero data retention"; the setting is recorded either way.
3. **Request–response logging confirmed off** for every model Val would call (it is off by default and is enabled per model, per project).
4. **`store = false` on every request** (the Interactions API defaults to `true`), and **session resumption never enabled** — both adapter obligations, testable before any Protected call.
5. **Grounding never requested** (Google Search grounding stores query logs for three days with no way to disable; Maps grounding for thirty).

Items 1–2 are console and API evidence from the project; 3–5 are adapter and configuration obligations. Adapter work is a new `google` provider adapter (Vertex GenAI SDK or REST, Google Cloud credentials, project and region, `thinking_level` mapping, structured output, usage mapping, the guards in 3–4), comparable in size to the OpenAI adapter. Awaiting his go.

## 5. GLM

Unchanged. Not admitted; API data handling not established; the consumer privacy policy does not count.

## 6. Haiku 4.5 (OP-4)

Accepted as recorded. No work this round beyond the registration.

## 7. One thing not overstated

The `reasoning_extraction` refusal category remains a hypothesis for the two zero-output reconciliation calls of 8 September, not a proven cause. The adapters now capture `stop_reason` and `stop_details` on every call; causes are established going forward from the record, not backward.
