# GPT-5.6 Sol — measurement protocol, A1 preflight, and the A2 stop — 13 September 2026

Written before any OpenAI call, on Lord Armand's instruction of 13 September 2026. **No provider call has been made.** Nothing here admits, qualifies or routes to Sol. `gpt-5-6-sol-medium` is registered `NOT_ADMITTED` with no capability profile; Anthropic remains the partner route.

---

## 1. Verified first-party facts (read 13 September 2026)

| Fact | Value | Source |
|---|---|---|
| Model identifier | `gpt-5.6-sol`; the only snapshot; the `gpt-5.6` alias routes to it | developers.openai.com/api/docs/models/gpt-5.6-sol |
| Context and output | 1,050,000 context window (922,000 maximum input); 128,000 maximum output | same |
| Reasoning effort | `none`, `low`, `medium` (default), `high`, `xhigh`, `max` | same |
| Features | streaming, structured outputs, function calling, prompt caching | same |
| Standard price per 1M tokens | input $4.00; cached input $0.40; cache writes $5.00; output $20.00 | developers.openai.com/api/docs/pricing |
| Long context | above 272K input tokens: 2× input and 1.5× output | model page |
| Reasoning billing | "billed as output tokens"; the count is `usage.output_tokens_details.reasoning_tokens` | developers.openai.com/api/docs/guides/reasoning |
| Output ceiling | `max_output_tokens` includes reasoning; hitting it gives `status: incomplete`, reason `max_output_tokens` | same |
| Caching on | "enabled by default"; GPT-5.6 supports implicit and explicit breakpoints | developers.openai.com/api/docs/guides/prompt-caching |
| Cache minimum | 1,024 tokens for GPT-5.6 and later | same |
| Cache economics | writes 1.25× the uncached input rate; reads 0.1× | same |
| Cache lifetime | `prompt_cache_options.ttl` minimum lifetime `30m`, the only supported value and the default; a prefix stays reusable for 30 minutes after its most recent write or reuse | same; SDK 3.1.0 |
| Implicit breakpoint | at the end of the most recent eligible message | same |
| Cache usage fields | `usage.input_tokens_details.cached_tokens` and `cache_write_tokens` | same; SDK 3.1.0 |
| What breaks the prefix | `model`, `tools`, `parallel_tool_calls`, **`text.format` (Structured Outputs)**, `reasoning.effort`, `text.verbosity`, `context_management` | same |
| Top-level instructions | cannot carry an explicit breakpoint; reusable instructions must sit in a developer message | same |
| Protected eligibility | OpenAI is Protected-eligible under the 15 August decision (no training on API content by default; 30-day abuse monitoring) | `VAL_Multi_Provider_Partner_Report.md`; `01-architecture.md` |

**Consequence for the blind position.** `text.format` changes the prefix on OpenAI as the output format does on Anthropic, so the blind call is not expected to share a cached prefix with the response call. This is stated from documentation and is to be confirmed by measurement, not assumed.

## 2. What changed in the code before any call

- **OpenAI adapter:**
  - Streaming implemented against `StreamingProviderAdapter`. It uses the same request builder and result mapper as completion; only `response.output_text.delta` is text; completed, incomplete and failed terminal events are mapped identically; a stream with no terminal event, or with an error event, raises the normalized provider error.
  - Usage now maps cached input to the cache-read figure, cache writes to evidence, reasoning tokens to their figure, and the presence of a reasoning output item to the reasoning fact.
- **Registry:** `gpt-5-6-sol-medium` added — `gpt-5.6-sol`, effort medium, $4 / $20, long context above 272K at 2× / 1.5×, Protected-eligible, `NOT_ADMITTED`, no profile, no fallback, caching deliberately `NOT_VERIFIED`.
- **Instrumentation, provider-neutral:** exchange identity on every reservation, and `model_call_measurements` per call (evidence index §58).

## 3. An accounting gap — RULED AND CLOSED 14 September 2026

*Option 1 below was ruled and implemented on 14 September 2026 (`04-layer-0.md` WP-0.4 amendment of that date): `ModelConfig.cache_write_auto_per_mtok_in_usd`, disjoint uncached / read / written figures from the adapter, settlement at $4 / $0.40 / $5 per million, and the cold bound at the write rate. The paragraphs below are kept as the record of the gap.*

GPT-5.6 caching is automatic and bills writes at **1.25×** base, on a 30-minute minimum lifetime.
- **The registry cannot express it:** its cache fields are Anthropic's 5-minute and 1-hour write rates, and `maximum_cost` widens the bound only when this house requests a cache lifetime.
- **Pricing today:** cached reads are priced at base, which over-states them. Written tokens are priced at base inside the uncached figure, which **under-states by 0.25 × base per written token** — exactly quantifiable, because `provider_cache_write_tokens` is recorded on every call.
- **The bound:** the reservation bound can be exceeded by the same quarter on written tokens.

A1 is below the 1,024-token minimum and cannot cache, so A1 is exact. **COLD and WARM measurement on Val's real request shape will write.**

Options, for ruling before those stages:
1. **(Recommended)** Rule OpenAI automatic-cache pricing into the registry and the bound. The smallest form is a verified automatic-cache write rate and a read rate on the entry, with `maximum_cost` bounding every input token at the write rate on configurations whose provider caches automatically. Settlement then prices reported writes and reads at verified rates.
2. Disable caching on measured OpenAI calls (`prompt_cache_options.mode = "explicit"` with no breakpoints, supported for GPT-5.6). This keeps the current doctrine exact, but the WARM stage then measures nothing.

## 4. Stage A1 — adapter preflight — RUN 14 September 2026

*Authorised and run on 14 September 2026: all three calls completed on `gpt-5.6-sol` for $0.001060 against $0.05 authorised; call 3 did not truncate (15 output tokens under a 16-token ceiling). Record: `qualification/runs/2026-09-14-sol-a1/README.md`. The plan below is kept as written.*

**Purpose:** prove account and model access, request construction, streaming, the normalized result, terminal-state handling, usage mapping, accounting and persistence. **Not** partner qualification, and **not** closure of the Phase 1 two-provider gate.

**Store:** the scratch `val_test` database, as the packet and strip-conformance harnesses used — never the live store.

**Content:** no House material. Prompt: "Reply with the single word: ready."

**Calls, all to `gpt-5-6-sol-medium`:**

| # | Path | Request | Proves |
|---|---|---|---|
| 1 | `OpenAIAdapter.stream` directly | the prompt, `max_output_tokens` 1,024, no schema | streaming: text deltas only, one terminal result, usage and reasoning mapping |
| 2 | `Gateway.evaluate_with_configuration` (existing lawful door: `NOT_ADMITTED`, no profile, structured task, schema required) | the same prompt as a `title` task with the schema `{"word": string}`, `max_output_tokens` 1,024 | request construction, normalized result, reservation with exchange identity absent, `model_calls` row, `model_call_measurements` row, settlement |
| 3 | the same door | the same, `max_output_tokens` 16 | terminal-state handling: `incomplete` / `max_output_tokens` recorded as truncated, settled at known cost |

**Why call 1 is adapter-level.** The evaluation door takes no delta sink, so streaming cannot be exercised through it. Streaming through the gateway on an unadmitted configuration would need the door changed, which this pass does not do. Call 1's usage is recorded in the run record from the provider's own figures.

**Cost:**

| | Figure | Basis |
|---|---|---|
| Expected | **≈ $0.007** | input ≈ 60–120 tokens per call at $4/M, negligible; output including reasoning ≈ 100–200 tokens on calls 1–2 at $20/M ≈ $0.002–0.004 each; call 3 ≤ 16 output tokens |
| Conservative maximum | **$0.05** | 1,024 × $20/M on two calls = $0.041; 16 × $20/M = $0.0003; input bounded by bytes ≈ $0.00003; rounded up |

**Pass criteria:**
- every call returns a normalized result;
- call 1 yields at least one `TextDelta` and exactly one terminal result, with no OpenAI type above the adapter;
- calls 2–3 each write exactly one `model_calls` row, one measurement row and one settled reservation;
- call 3 is `truncated`;
- `reasoning_output_tokens` and `reasoning_present` are populated as reported;
- recorded cost equals the provider's usage at registry rates.

## 5. The measurement protocol (after A1, and after §3 and §6 are ruled)

Every stage runs on Val's real request shape through Val Core, on the scratch store, with the new instrumentation.

**Recorded per call:**
- total, uncached, cached-read and cache-write input;
- output and reasoning tokens;
- reasoning presence;
- generated-text characters;
- cost as settled;
- time to first text;
- total latency.

**Recorded per exchange:** the reservation and measurement sums joined by exchange identity.

| Stage | Request | What it establishes |
|---|---|---|
| COLD | an ordinary turn whose persona-and-history prefix has not been seen within 30 minutes | cache writes actually billed; write premium; time to first text; total latency |
| WARM | the next turn of the same conversation within 30 minutes | cached-input tokens actually reused, at the rate actually applied; cost; time to first text; latency |
| ORDINARY | one normal non-consequential response (persona, record state, capability state, bounded memory where applicable) | the one-partner-call cost and latency on OpenAI |
| CONSEQUENTIAL | one exchange through the unchanged strip → blind → reconciled response doctrine | the integrity machinery's added cost; whether the blind call and the response share any prefix; reasoning share in each |

**The same exchanges on the incumbent** (`opus-5-medium`) are the comparison. Their figures come from the same instrumentation on genuine use, never manufactured.

**Must be established from usage, not documentation:**
- whether caching is automatic for this request shape;
- the minimum prefix as observed;
- the write premium as billed;
- the cached-input price as billed;
- reuse within and beyond 30 minutes;
- reasoning tokens as a share of output;
- whether the structured blind request shares any prefix with the response.

## 6. Stage A2 — the candidate lane, RULED AND BUILT 14 September 2026; the call NOT yet authorised

*The stop below was ruled on 14 September 2026 and the mechanism authorised, with structural requirements: a distinct qualification type (not a capability profile), a structurally separate gateway construction, every ordinary Val check in force, scratch-store enforcement, and truthful recording. Built as `val_gateway.candidate` (`QualificationTarget`, `CandidateGateway`, `candidate_gateway_for_scratch_store`) with `deliberate.send(candidate=...)`; the design differs from the proposal below in that the harness-only construction is a **separate type built by a refusing factory**, not a boolean on `Gateway`, and the marker is a **distinct `Enum`**, never string-equal to a profile. **A2 was authorised for the ordinary path and run later on 14 September 2026:** `not_consequential`; Sol's response call 5,324 input (3 uncached, 5,321 written, 0 read), 34 output, 0 reasoning tokens, first text 2,903 ms, 4,915 ms total, $0.027297; exchange $0.028172 against $0.23. Record: `qualification/runs/2026-09-14-sol-a2/README.md`. The original stop-and-report package follows as the record.*

**A2 cost under the built mechanism (14 September 2026), one exchange on a fresh scratch store.** The reservation bounds now price Sol's whole input at the $5 automatic write rate, so the bounds are higher than the 13 September figures; expected actuals are little changed:

| Path | Expected | Conservative maximum (sum of reservation bounds) |
|---|---|---|
| ordinary (classification → response) | ≈ $0.09 — persona and envelopes ≈ 8,500 tokens written cold at $5/M ≈ $0.043; output including reasoning ≈ 1,500 at $20/M ≈ $0.03; classification ≈ $0.001 | ≈ $0.23 — response bound $0.2235 (input by bytes at $5/M plus 4,096 output at $20/M) plus classification $0.003 |
| consequential (classification → strip → blind → response) | ≈ $0.15 — as above plus the blind call's separate cold prefix ≈ 7,300 written ≈ $0.037 and ≈ 600 output ≈ $0.012, plus strip ≈ $0.01 | ≈ $0.49 — response $0.2235, blind $0.1999, strip ≈ $0.06, classification $0.003 |

The harness prompt asks for two or three sentences on beginning a fictional founding account; the classifier may find creative direction in it, so the consequential column is the honest maximum.


**The contracts that prevent it:**
- **Pinned conversation path.** `Gateway.converse(configuration=...)` and `complete_with_configuration` both pass through `_verify_named_configuration` (`gateway.py`). It refuses a configuration that is not admitted, or does not satisfy the profile the task requires. `CONVERSATION` and `BLIND_POSITION` require `PARTNER` (`val_policy.routing`).
- **Routing.** `active()` excludes `NOT_ADMITTED` entries, so routing cannot select Sol.
- **Evaluation door.** `Gateway.evaluate_with_configuration` refuses `CONVERSATION` and `BLIND_POSITION` outright: "a task in which Val speaks; a configuration under evaluation never serves it" (ruling, 10 September 2026). It also requires an output schema.

**Why the evaluation door cannot lawfully be reused.** That refusal is the door's safety property — it was built so a candidate could be exercised without ever speaking as Val. Admitting partner-class requests would widen it, which the ruling forbids.

**How the Opus partner qualification was exercised.**
- The packet harnesses (`docs/reviews/qualification/runs/2026-09-09-v1.6/harness/run_packet_v16.py` and predecessors) replaced `val_gateway.gateway.active`, `by_id` and `fallback_for` in-process.
- They substituted an effort-variant copy of the already `PROVISIONALLY_ADMITTED`, partner-profiled `opus-5` entry, under the same id and slug.
- They ran `deliberate.send` against the scratch store, so every call passed the ordinary checks because the substituted entry was already admitted with the partner profile.
- Consequence in the evidence: the v1.6 medium run's 42 Opus calls are recorded under `opus-5`'s id, not the later `opus-5-medium`.

**Is that mechanism still available, and appropriate?**
- **Technically still available:** the module-level lookups remain patchable.
- **Not appropriate for Sol:** it would require an in-memory copy of Sol carrying `PROVISIONALLY_ADMITTED` and the `PARTNER` profile — exactly "temporarily label Sol as partner", which is forbidden. It also records calls under a configuration whose stated standing is false.

**Smallest proposed mechanism (not built).** A partner-candidate door, confined by construction:
1. **Registry:** a `candidate_profiles` field on `ModelConfig`, settable only on `NOT_ADMITTED` entries, disjoint from `capability_profiles`, and set by ruling (Sol: `{PARTNER}`). It confers no routing and no admission.
2. **Gateway:** `Gateway(..., candidate_evaluation: bool = False)` and a method `converse_candidate(messages, *, scope, turn, configuration, on_delta)`. It refuses unless:
   - the gateway was built with `candidate_evaluation=True`;
   - the entry is the registry's own, not retired, `NOT_ADMITTED`, with the task's profile in `candidate_profiles`.

   Otherwise it runs exactly `converse`'s checks: persona loaded whole and verified, Restricted preflight, provenance verifier, eligibility by classification, an ordinary reservation carrying exchange identity, `model_calls` recorded under the candidate's own id, measurement, and no fallback.
3. **Deliberation:** `deliberate.send(..., candidate=config)` pins only the partner calls (blind and response) to the candidate through that door. Classification and strip route as always.
4. **Startup:** the service gateway is always built with `candidate_evaluation=False`. No HTTP contract gains a candidate parameter.
5. **Harness:** a script under `docs/reviews/qualification/runs/`, scratch store only, refusing a database whose name does not end in `_test`.

**Files and contracts it would touch:**
- `packages/domain/src/val_domain/gateway.py` (field and validator)
- `packages/domain/src/val_domain/registry.py`
- `packages/gateway/src/val_gateway/gateway.py`
- `packages/gateway/src/val_gateway/deliberate.py` and `loop.py`
- `packages/gateway/src/val_gateway/startup.py`
- tests
- the harness
- `01-architecture.md` §5.2 (ruling)
- `04-layer-0.md` WP-0.4 and WP-0.9 amendments

**Safety properties and required tests:**
- **The service stays closed:** the production gateway refuses the door; the API exposes no candidate parameter; startup always builds the flag off.
- **The door is narrow:** it refuses admitted, retired, unmarked and caller-copied configurations; routing, the pinned path and the evaluation door are unchanged and still refuse the candidate.
- **Only the partner calls are pinned:** classification and strip never go to the candidate.
- **Every check still runs:** the persona is whole and verified; Restricted and eligibility checks are unchanged; reservations and settlement are ordinary; calls are recorded under the candidate's id; there is no fallback.
- **Harness guard:** the harness refuses a non-`_test` store.

**Owner-level ruling required: yes.** It creates the first path by which an unqualified configuration speaks as Val, even confined to a harness. That extends the 10 September evaluation-door ruling, and the `01-architecture.md` §5.2 routing and admission doctrine.

**A2 cost, if the mechanism is ruled and built.** One ordinary exchange on the scratch store carrying persona, record state, capability state, bounded memory and streaming:

| Call | Figure | Basis |
|---|---|---|
| Sol, expected | **≈ $0.08** | input ≈ 8,000–9,000 tokens at $4/M (≈ $0.035, or ≈ $0.045 if written at 1.25×); output including reasoning ≈ 1,500 at $20/M ≈ $0.03 |
| Classification (Haiku) | ≈ $0.001 | |
| Conservative maximum | **≈ $0.22** | Sol reservation bound: input by bytes ≈ 30,000 at $4/M plus 4,096 output at $20/M ≈ $0.20, plus up to 25% on written input until §3 is ruled; plus classification |

## 7. Stage B — the frozen corpus for later qualification

- **Packet and corpus:** `docs/reviews/qualification/VAL_Partner_Qualification_Packet_v1.6.md` (frozen 9 September 2026; errata `…_v1.6_ERRATA.md`) and `docs/reviews/qualification/corpus/v1.6/corpus.json` (`"version": "v1.6"`).
- **Scale:** 36 prompts per run.
- **Scoring:** packet §§4–7, unchanged.
- **Reference run:** the v1.6 medium run on Opus made 86 calls for US$2.61.
- **Candidate configuration:** persona v1.8 (revision 7) is part of the exact configuration.
- **Not yet estimable:** the Sol call count and spend depend on its measured reasoning and caching economics (§5). They will be stated before Stage B is authorised.

## 8. External blockers

- **None known for A1:** the service's OpenAI key is configured and the provider is Protected-eligible.
- **Unconfirmed until A1 runs:** whether the account can reach `gpt-5.6-sol`.
- **A2 is blocked** on the §6 ruling.
- **COLD and WARM measurement is blocked** on the §3 ruling.
