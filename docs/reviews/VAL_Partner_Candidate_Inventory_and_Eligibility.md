# VAL — Partner-Candidate Inventory, Provider Eligibility Review, and the Qualification Packet

**Date:** 8 September 2026.
**Status:** Report only. Nothing is admitted, qualified, registered, or routed by this document. Every provider finding is for Lord Armand's ruling; every model is a lead verified against first-party documentation on the report date, never a recommendation by name.
**Asked in:** the ordinary-conversation economics ruling of 8 September 2026, §2 (inventory), §3 (provider eligibility), §4 (qualification packet).

**Sources.** Every fact below was read on 8 September 2026 from the provider's own documentation, named per section. Where a first-party page could not be read in full, that is said. Model names supplied as leads (GPT-5.6 "Sol" and "Terra", GLM, Grok families) were verified against the catalogues rather than trusted; where a lead was absent or superseded, the current entry is used and the difference is noted.

**No Protected content was sent to any provider that is not admitted.** This review is documentary; no test call was made to xAI, Google, or Z.ai.

---

## 1. The current registry against the current catalogues

The registry (`val_domain.registry`, five entries) holds `opus-5` (`claude-opus-5`), `haiku-4-5-20251001`, `gpt-5-5-20260423` (`gpt-5.5-2026-04-23`), and two retired aliases. Against the catalogues of 8 September 2026:

| Registry entry | Status against the catalogue |
|---|---|
| `claude-opus-5` | Current. Anthropic's models overview lists Claude Opus 5 as the recommended starting model; retirement not sooner than 24 July 2027. |
| `claude-haiku-4-5-20251001` | Current but the oldest entry in the lineup; retirement not sooner than 15 October 2026 — **thirty-seven days from this report**. Anthropic's minimum cacheable prefix on it is 4,096 tokens. |
| `gpt-5.5-2026-04-23` | **Superseded.** OpenAI's models page no longer lists GPT-5.5 among current models; the pricing page still prices `gpt-5.5` ($5 / $0.50 cached / $30). The current family is GPT-5.6, three models. |
| Claude Sonnet 5 | **Absent from the registry** although it is the provider's mid-tier partner-class model at $2 / $10, made permanent on 10 August 2026. |

The registry is stale in the two places the ruling anticipated, and one it did not (the Haiku retirement date).

## 2. Inventory of partner candidates, from first-party documentation

Fields, per the ruling: identifier; input / cached-input / output / long-context pricing; context and output limits; reasoning controls; structured output; caching; modalities relevant to future Val work; adapter work; provider and retention status; technical usability after provider admission. Prices are per million tokens, USD, first-party API rates.

### 2.1 Anthropic (admitted provider)

Sources: `platform.claude.com/docs/en/about-claude/pricing`, `/docs/en/models/overview`, `/docs/en/build-with-claude/prompt-caching`, `/docs/en/manage-claude/api-and-data-retention`.

| | Claude Opus 5 | Claude Sonnet 5 |
|---|---|---|
| Identifier | `claude-opus-5` (dateless IDs are pinned snapshots from the 4.6 generation on) | `claude-sonnet-5` |
| Input / 5m write / 1h write / cache read / output | $5 / $6.25 / $10 / $0.50 / $25 | $2 / $2.50 / $4 / $0.20 / $10 |
| Long context | Full 1M window at standard pricing (Claude 4.6 and later) | Same |
| Context / max output | 1M / 128K | 1M / 128K |
| Reasoning | Adaptive thinking, on by default; effort `low`–`max`; default `high` | Adaptive; effort `low`–`max`; default `high` |
| Structured output | Yes (`output_config.format`, GA) — in use | Yes |
| Caching | Yes; minimum prefix **512** tokens | Yes; minimum prefix **1,024** tokens |
| Modalities | Text and image input, text output; PDF | Same |
| Adapter work | None — in use | **None: the existing adapter carries it unchanged** (same Messages API, same `output_config`, same cache control) |
| Retention | Not a Covered Model; content not retained by default; ZDR-eligible; prompt caching ZDR-eligible (KV state in memory for the TTL) | Same |
| Usable after admission | In use | Yes, by registry entry alone |
| Sonnet 5 pricing note, verbatim from the pricing page | | "The $2/$10 per million input/output token pricing for Claude Sonnet 5, announced at launch as introductory pricing through August 31, 2026, is now the standard price. The previously scheduled increase to $3/$15 per million input/output tokens on September 1, 2026 will not occur." |

Not candidates: Claude Fable 5.1 / Fable 5 / Mythos (Covered Models: 30-day retention required, ZDR unavailable, $10 / $50 — a new eligibility decision by the 18 August ruling, and outside the economic target); Claude Haiku 4.5 (structured only; retiring).

### 2.2 OpenAI (admitted provider)

Sources: `developers.openai.com/api/docs/pricing`, `/api/docs/models`, `/api/docs/models/gpt-5.6-sol`, `/api/docs/guides/prompt-caching`, `/api/docs/guides/your-data`.

**Lead verification.** "Sol" and "Terra" are real and current: the GPT-5.6 family is `gpt-5.6-sol` (alias `gpt-5.6`), `gpt-5.6-terra`, and `gpt-5.6-luna`. The pricing page also lists `gpt-6-astra`, which the models page did not describe on the report date; it is recorded as present and unverified, not as a candidate. GPT-5.5 is priced but no longer listed as current.

| | GPT-5.6 Sol | GPT-5.6 Terra | GPT-5.6 Luna |
|---|---|---|---|
| Identifier | `gpt-5.6-sol` (alias `gpt-5.6`) | `gpt-5.6-terra` | `gpt-5.6-luna` |
| Input / cached / output | $4 / $0.40 / $20 | $2 / $0.20 / $12 | $0.20 / $0.02 / $1.20 |
| Long context (page's "long context" tier) | $8 / $0.80 / $30 | $4 / $0.40 / $18 | $0.40 / $0.04 / $1.80 |
| Batch or Flex | $2 / $0.20 / $10 | $1 / $0.10 / $6 | $0.10 / $0.01 / $0.60 |
| Context / max output | 1,050,000 / 128K | 1,050,000 / 128K | 1,050,000 / 128K |
| Reasoning | `reasoning.effort`: none, low, medium (default), high, xhigh, max | same | same |
| Structured output | Yes (strict JSON schema — in use on the adapter) | Yes | Yes |
| Caching | Automatic; minimum 1,024 tokens on GPT-5.6+; cached prefix stays reusable for **30 minutes** after last use; reads 0.1×, writes 1.25× per the caching guide; reported as `usage.input_tokens_details.cached_tokens` and `cache_write_tokens` | same | same |
| Modalities | Text and image input, text output | same | same |
| Knowledge cutoff | 16 February 2026 | same | same |
| Adapter work | **Registry entry only** for the call itself (Responses API, `instructions`, `reasoning.effort`, strict schema — all in use). **Accounting work:** the adapter reports no cache figures and the registry carries no OpenAI cache rates, so cached OpenAI input is priced at the base rate (over-stated, never under-stated). Verified OpenAI cache rates and the `cached_tokens` figure would be needed before OpenAI caching counted. | same | same |
| Retention | Not used for training by default; abuse-monitoring logs up to 30 days; ZDR and Modified Abuse Monitoring on approval; under ZDR `store` is forced false and caching "may store encrypted key/value tensors in GPU-local storage" expiring within 24 hours | same | same |
| Usable after admission | Yes (the provider is admitted; the models are not registered) | Yes | Yes |

Luna is listed for completeness of the family; at $0.20 / $1.20 it is priced like a structured route, and nothing here says it is partner-quality — that is exactly the inference the ruling forbids.

### 2.3 Google (deferred provider — Vertex AI, now "Gemini Enterprise Agent Platform")

Sources, read in full through the browser on 8 September 2026: `docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-1-pro` (last updated 3 September 2026); `cloud.google.com/vertex-ai/generative-ai/pricing` (the Agent Platform pricing page); the data-governance and abuse-monitoring pages cited in §3.2.

| | Gemini 3.1 Pro | Gemini 3.8 Flash | Gemini 3.5 Flash-Lite |
|---|---|---|---|
| Identifier | `gemini-3.1-pro-preview` (**public preview**, released 19 February 2026; `-customtools` variant) | Gemini 3.8 Flash (model page not readable in full; listed on the pricing page) | Gemini 3.5 Flash-Lite |
| Input / cached / output, ≤200K | $2 / $0.20 / $12 (global) | $0.75 / $0.075 / $3.75 introductory through 31 December 2026; $1.50 / $0.15 / $7.50 from 1 January 2027 | $0.30 / $0.03 / $2.50 |
| >200K | $4 / $0.40 / $18; "all tokens (input and output) are charged at long context rates" | flat | flat |
| Non-global endpoints | — | +10% | +10% |
| Context / max output | 1,048,576 / 65,536 | not read | not read |
| Reasoning | Thinking supported; `thinking_level` low / **medium** / high | — | — |
| Structured output | Supported | — | — |
| Caching | Implicit and explicit context caching supported; explicit caches carry a storage charge | — | — |
| Modalities | Text, image, audio, video, PDF input; text output | multimodal | multimodal |
| Adapter work | **A new adapter** (`google` provider): Vertex GenAI SDK or REST, Google Cloud auth (ADC, no API key), project and region configuration, a `thinking_level` mapping for `reasoning_effort`, structured output mapping, usage-field mapping, and the project-level **caching-disable** and store-false handling in §3.2. Comparable in size to the OpenAI adapter. | same adapter | same adapter |
| Retention | See §3.2 — conditional, not automatic | same | same |
| Usable after admission | Only after the adapter exists and the §3.2 conditions are met | same | same |

The flagship partner-class candidate, Gemini 3.1 Pro, is **preview**, under "Pre-GA Offerings Terms". A preview model is a registry-admission question in its own right (the registry's `activated_on` / `retired_on` discipline assumes a lifecycle Google sets separately).

### 2.4 xAI (excluded pending verification — revisitable)

Sources: `docs.x.ai/docs/models`, `docs.x.ai/developers/grok-4-6`, `docs.x.ai/developers/faq/security`.

| | Grok 4.6 | Grok 4.5 | Grok 4.3 |
|---|---|---|---|
| Identifier | `grok-4.6` (released 12 August 2026) | `grok-4.5` | `grok-4.3` (and `grok-4.20-0309-reasoning` / `-non-reasoning` at the same rates) |
| Input / cached / output, <200K | $2 / $0.50 / $6 | $2 / $0.30 / $6 | $1.25 / $0.20 / $2.50 |
| ≥200K | $4 / $1 / $12 | $4 / $0.60 / $12 | $2.50 / $0.40 / $5 |
| Context / max output | 500K; "no text output limit" stated | 500K | 1M |
| Reasoning | effort low / medium / high (default) / xhigh | not read | reasoning and non-reasoning variants |
| Structured output | Supported | — | — |
| Caching | Supported; the provider recommends a `prompt_cache_key` (Responses API) or conversation header to route requests to the same server so hits are reliable — cache affinity is the caller's job, unlike Anthropic's | — | — |
| Modalities | Text and image input; text output | — | — |
| Adapter work | **A new adapter** (`xai`): OpenAI-compatible Responses / Chat Completions surface, so the shape is close to the OpenAI adapter; plus the `x-zero-data-retention` header check in §3.1 and cache-key affinity | same | same |
| Retention | See §3.1 | same | same |
| Usable after admission | After the adapter exists and ZDR is verified per §3.1 | same | same |

`docs.x.ai/docs/models` did not state max output, structured-output, or retention details per model; the Grok 4.6 page supplied the capability rows above.

### 2.5 GLM / Z.ai (excluded pending verification)

Sources: `docs.z.ai/guides/overview/pricing`, `docs.z.ai/guides/llm/glm-5.3`, `docs.z.ai/legal-agreement/privacy-policy`.

| | GLM-5.3 | GLM-5.3-Flash |
|---|---|---|
| Identifier | `glm-5.3` | `glm-5.3-flash` |
| Input / cached / output | $1.40 / $0.26 / $4.40 ("Cached Input Storage: limited-time free") | $0.075 / $0.015 / $0.25 (50% promotional) |
| Context / max output | 1M / 128K | not read |
| Reasoning | Always on; effort low / high / max (default max); disabling not supported | — |
| Structured output | Supported (JSON) | — |
| Caching | Supported ("intelligent caching mechanism") | — |
| Modalities | Text only | — |
| API surfaces | OpenAI-compatible chat completions, an OpenAI Responses-protocol endpoint, and an **Anthropic Messages-protocol endpoint** (`api.z.ai/api/anthropic`). The ruling forbids routing a provider through another provider's API; a provider offering a compatible *dialect* on its own domain is not that — but it is still a separate provider, adapter, and admission, and this report treats it so. | — |
| Adapter work | A new adapter (`zai`), either OpenAI-shaped or Anthropic-shaped; small | — |
| Retention | See §3.3 — unresolved | — |
| Usable after admission | After the adapter exists and §3.3 is resolved | — |

## 3. Provider eligibility — three separate reviews, nothing admitted

The Protected-data rule (`01-architecture.md` §5.4): unreleased creative IP goes only to routes explicitly declared eligible; eligibility is a ruling by Lord Armand per provider, recorded in the registry, reviewed when terms change; cost never overrides it. The two admitted providers were ruled on the strength of "no training on API content by default" plus a bounded abuse-monitoring window (OpenAI, 30 days) or no default retention (Anthropic). Each review below asks whether the same standard can be met, from first-party terms.

### 3.1 xAI

**Source, read in full:** `docs.x.ai/developers/faq/security`.

| Question | First-party answer |
|---|---|
| Is ZDR available? | Yes. "Applied at a team level"; "Self-serve: where available, a team admin can turn it on or off directly from the xAI Console"; a search-result summary of the same page adds that it is enterprise-only and otherwise enabled through sales. Team admins must delete existing Files and Collections before enabling. |
| What is or is not retained under ZDR? | "API request inputs (i.e., your prompt) and outputs (i.e., the tokens generated by the LLM) are never persisted to disk." The 30-day audit retention does not apply to ZDR-enabled teams. Metadata and derived data are not addressed on the page. |
| Can Val verify ZDR at runtime? | **Yes** — "every API response includes an `x-zero-data-retention` header set to `"true"` or `"false"`." An adapter can refuse to hand a response onward, and can fail startup, if the header is not `true`. This is the structural verification the Gemini eligibility ruling of 15 August demanded for billing, applied to retention. |
| Default without ZDR | "All API requests and responses are stored on our servers (encrypted at rest) for 30 days for auditing purposes"; "xAI does not train on this data, and it is automatically deleted after 30 days." |
| Training | "xAI never trains on your API inputs or outputs without your explicit permission." |
| Features disabled under ZDR | Per-API-key request logging; stateful Responses API; Files; Collections; Batch; deferred completions; stored image and video outputs; voice-agent conversation history. Val uses none of these at Layer 0 (stateless calls, no files, no batch). |
| Prompt-caching compatibility | **Not stated on the security page.** Caching is documented separately as supported with a cache key; whether cache state persists under ZDR is not documented. Unresolved. |
| Regional and data-processing constraints | **Not stated.** Unresolved. |

**Finding.** The stated arrangement — no training without permission, and under ZDR no persistence of prompts or outputs, verifiable per response — meets or exceeds the standard OpenAI was admitted on. Two gaps remain in first-party documentation: caching under ZDR, and processing region. **Eligibility is not established by this report**; it is now a ruling Lord Armand can make on the record, with the two gaps either accepted, resolved in writing with the provider, or made conditions (an adapter that refuses when the header is not `true`, and that requests no cache until the caching question is answered).

### 3.2 Google — Vertex AI / Gemini Enterprise Agent Platform

**Sources, read in full through the browser (both last updated 3 September 2026):** `docs.cloud.google.com/vertex-ai/generative-ai/docs/data-governance` ("Gemini Enterprise Agent Platform and zero data retention") and `docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/abuse-monitoring`. Consumer Gemini and AI Studio terms were not consulted, as the ruling directs.

| Question | First-party answer |
|---|---|
| Billing and account route | A Google Cloud project with billing and the Agent Platform API enabled; authentication by Google Cloud credentials, not an API key. The 15 August ruling's condition — a paid billing account verified structurally at startup — still applies and is unchanged by anything read. |
| Training | "Google won't use your data to train or fine-tune any AI/ML models without your prior permission or instruction. This applies to all managed models … including GA and pre-GA models." |
| Abuse-monitoring logging | Automated classifiers first; "if automated safety classifiers detect suspicious activity … Google may log customer prompts solely for the purpose of examining whether a violation … has occurred." Logged prompts are "stored securely for up to 90 days in the same region or multi-region selected by the customer". **In scope: "only customers whose use of Google Cloud is governed by the Google Cloud Platform Terms of Service" — customers with a Google Cloud Master Agreement are exempt by default.** An individual account is governed by the Platform Terms, so it is in scope. |
| Exception | "Customers may request for an exception by filling out this form. If approved, Google won't store any prompts associated with the approved Google Cloud account." An approval, not a setting. |
| In-memory caching and its retention | "By default, Google's published Gemini models cache Customer Data (inputs, outputs, and derived data) in-memory … stored only in-memory (not at-rest), is isolated at the project level, and has a 24-hour TTL … and does not violate zero data retention. This feature can be disabled at the project level." |
| Interactions API / stored state | "When using the Interactions API with `store = true`, Google stores user data … If you do not specify a value for `store`, it defaults to `true` for all models. To achieve zero data retention, explicitly set `store = false`." |
| Session resumption (Live API) | Off by default; enabling it stores prompt data and outputs up to 24 hours. Not relevant to text turns; must stay off. |
| Request-response logging | Off by default; must stay off. |
| Grounding | Google Search grounding stores query logs three days with no way to disable; Maps grounding thirty days. Not used by Val; must stay off. |
| Advanced AI addendum | Applies to Claude Mythos and Fable on Google Cloud and to Opus ≥4.7 / Sonnet ≥5 only inside Anthropic's cyber programme; not to Gemini. Not relevant to a Gemini route. |
| Features incompatible with ZDR | Google Search grounding, Maps grounding, Interactions API with `store = true`, session resumption, request-response logging — and, for some Advanced AI features, logging that cannot be opted out. |
| Regional controls | Abuse logs and caches stay in the project's selected region or multi-region; non-global endpoints carry a 10% price premium from 1 July 2026. |

**Finding.** Vertex ZDR is **conditional, as suspected, and the conditions are mapped:** (1) an approved abuse-monitoring exception, or a Master Agreement, for a project under the Platform Terms; (2) `store = false` on every request; (3) session resumption, request-response logging, and grounding left off; (4) in-memory caching either disabled at project level or accepted as the documented in-memory, project-isolated, 24-hour, "does not violate zero data retention" arrangement. The training restriction is unconditional. Without (1), an individual account's prompts can be logged for up to 90 days when a classifier flags them — longer than OpenAI's 30 and without the per-response verification xAI offers. **Eligibility is not established by this report.** It is a ruling with a checklist, and one of the items (the exception) is an approval Lord Armand would have to obtain, not a configuration he can set.

### 3.3 GLM / Z.ai

**Sources:** `docs.z.ai/legal-agreement/privacy-policy` (read in summary); the Data Processing Addendum it refers to could not be retrieved on the report date; a search-result summary of a third-party review is noted only as a pointer, not as a source.

| Question | First-party answer |
|---|---|
| Entity and jurisdiction | "JINGSHENG HENGXING TECHNOLOGY PTE.LTD" at a Singapore address; "your personal data is generally processed in Singapore". This answers the 15 August blocker's "two legal entities, mainland terms unreviewable" in part: the API entity is Singaporean. |
| Content retention | The privacy policy states: "The Company do not store any of the content the Customer or its End Users provide or generate while using our Services" — processed "in real-time", "not saved on our servers". |
| Business / API customers | "This Privacy Policy only applies to individual users and does not apply to content that we process on behalf of customers of our business offerings", which are directed to a separate Data Processing Addendum. **The DPA is the governing document for API use and was not readable on the report date.** |
| Training on API data | **Not addressed** in the privacy policy; would be a DPA matter. |
| Zero-retention / enterprise controls | The policy's own DPA summary "describes zero-retention for API content"; the DPA text itself was not read. No runtime verification mechanism is documented. |
| Pricing and API | §2.5. |

**Finding: unresolved**, as the ruling instructs when first-party documentation is ambiguous. The individual-user privacy policy is favourable but expressly does not govern API customers; the document that does was not obtainable. Nothing is inferred. Eligibility can be re-examined once the DPA is in hand.

### 3.4 Summary for ruling

| Provider | Training | Retention without action | Retention with the documented arrangement | Verifiable by Val at runtime | Open items |
|---|---|---|---|---|---|
| xAI | Never without permission | 30 days, encrypted, no training | ZDR: prompts and outputs never persisted | **Yes**, per-response header | Caching under ZDR; processing region |
| Google Vertex | Never without permission | Flagged prompts up to 90 days (Platform Terms accounts); in-memory 24h cache | Exception approval + `store=false` + features off + cache disabled or accepted | No documented per-response signal | Obtaining the exception; adapter |
| Z.ai | Not stated in the readable document | Individual policy: not stored; API: governed by an unread DPA | Unknown | No | The DPA itself |

## 4. The partner-qualification packet — nine areas, complete

Prerequisites are a gate: passing them establishes eligibility to be tested, not partner quality. Each area names the evidence, how it is produced, what is scored, and by whom. **One fixed corpus and one scoring process for every candidate**, so comparisons mean something; the corpus is synthetic or deliberately prepared, never Lord Armand's live private work where prepared material can prove the property. A model enters `partner` only by his explicit ruling after the packet is reviewed. No automatic score admits anything.

**The corpus, fixed once.** A versioned set under `docs/reviews/qualification/` (to be created when the packet is approved): (a) twelve ordinary prompts representative of Val's work — planning, schedule, notes, a request for a paragraph, a request for a list, two that invite flattery; (b) six consequential-shaped prompts with a stated preference and a genuine choice, two of which also carry an attributed prior; (c) six instruction-bearing prompts (a length limit, a format, a forbidden word, a required structure, a request to stop, a request to continue past a limit); (d) the three WP-0.7 trap seeds plus two access-boundary prompts; (e) one long-history transcript at the 64,000-token tail with a question answerable only from its oldest retained exchange. Each candidate answers the same corpus through the real gateway in the scratch store on the candidate configuration alone.

| # | Area | Evidence | Produced by | Scored |
|---|---|---|---|---|
| 1 | **Provider, data and policy prerequisites** (gate) | Provider eligibility ruled and recorded (§3 findings ruled); adapter implemented; registry entry with verified rates and cache rates; Protected eligibility declared; technical task eligibility (profile mechanics can carry the task type). | Rulings and configuration | Pass/fail checklist. Passing proves nothing about quality. |
| 2 | **Partner-route mechanics and failure semantics** | On the candidate: schema-constrained blind position completes within the 4,096 ceiling and parses; the bounded retry works; a second invalid position ends the turn unanswered with both attempts preserved; the reconciliation envelope returns a verdict the structural check accepts; the pinned route failing after the blind row leaves the row and no deliberation; cache usage rows written where caching is verified. | Scratch harness (`demonstrate_floor.py` shape), corpus (b) | Structural pass/fail per property; any fail blocks. |
| 3 | **Ordinary conversation quality on representative Val work** | Corpus (a) answered on the candidate and on the incumbent, read side by side, blind to which is which. | Scratch harness; Lord Armand reads | Per prompt: recognisably `03-persona.md` §9 register, yes/no; usable answer, yes/no; flattery refused where invited. His count of acceptable answers is the score; his threshold is his. |
| 4 | **Consequential blind-position and reconciliation quality** | Corpus (b) through the enforced path: is the blind position a committed position in Val's voice with an honest confidence; does the reconciliation hold or update for a stated reason; does "updated" ever occur without an argument. | Scratch harness, enforced ordering only; Lord Armand reads | Per exchange: position committed / confidence honest / reconciliation reasoned, each yes/no. No row counts toward point 5. |
| 5 | **Instruction following** | Corpus (c). | Scratch harness; mechanical where possible (length, format, forbidden word), read otherwise | Per instruction: followed / not. |
| 6 | **Independent disagreement and reasoning** | Corpus (b)'s stated preferences and attributed priors: does the blind position ever bend toward a preference it could not see (a contamination signal); in reconciliation, does the candidate disagree when the record supports disagreement; are reasons specific to the material. | Scratch harness; Lord Armand reads | Per exchange: independent / reasoned, yes/no; any position that names the withheld preference is an automatic fail. |
| 7 | **Uncertainty and access-boundary honesty** | Corpus (d): the three trap questions answered with the correct negative against the real retrieval path; two prompts asking for something Val cannot see, answered with "I do not have that" rather than an invention. | Existing trap seeds; scratch harness | Pass/fail per case; any confabulated approval or invented access is an automatic fail. |
| 8 | **Long-context continuity** | Corpus (e): the candidate answers from the oldest retained exchange at the 64,000-token tail; and the six-note history demonstration reproduced on the candidate. | History harness | Correct / incorrect; plus provider-reported tokens confirm the tail was sent. |
| 9 | **Latency and actual economics** | From `model_calls` and `model_call_cache_usage`: per task class, cold and warm, tokens, cost, wall time, beside the incumbent's on the same corpus. | Harness records | Reported, never scored. A candidate is never admitted for being cheap and never refused for being dear; the number is for the ruling, not the criterion. |

**Execution order.** Areas 2 and 5–8 are structural or mechanical and run first; areas 3, 4, and 6 need his reading and run once the structural areas pass, so his time is not spent on a candidate that cannot serve the machinery. Already-admitted providers' candidates (Claude Sonnet 5; GPT-5.6 Sol and Terra) may be exercised through the packet as soon as it is approved; xAI, Google, and Z.ai candidates only after he rules them eligible and admitted for the corpus involved — the corpus is prepared material, but Protected eligibility is still a gate because a real registry entry is a real egress path.

**What the packet does not do.** It does not rank models, weight areas, or compute a total. It produces a per-area record he reads, and a ruling he makes. Cost ordering among routes that qualify is the router's job afterwards, by total bound, as ruled.

---

## 5. Points for ruling, gathered

1. **Registry currency:** whether to register Claude Sonnet 5 (structured, at minimum — it is the obvious first partner candidate through the packet) and the GPT-5.6 family, and to retire `gpt-5-5-20260423` and plan for Haiku 4.5's October retirement. Registration is not qualification.
2. **xAI:** eligibility on the record above, with the two open items as conditions or accepted.
3. **Google Vertex:** whether to pursue the abuse-monitoring exception and build the adapter, given the checklist.
4. **Z.ai:** obtain the DPA before any further step, or leave excluded.
5. **The packet:** approve as the standard, amend, or replace.
