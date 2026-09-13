# House Recall budget — precision question and counting options, 13 September 2026

Analysis only, on Lord Armand's instruction of 13 September 2026. **No provider call; no runtime change; no migration; no House Recall traffic.**
- **Store reads:** the opening turn's ranked candidates were reconstructed from the live store, read-only.
- **Prose scenarios:** built locally from synthetic excerpts.
- **Provider documentation:** the token-counting page and the API-and-data-retention page on `platform.claude.com` were read as ordinary web documents. That sent no Val content.

Where a provider token figure is *inferred* or *modelled* rather than reported by the provider, it says so.

---

## 1. What the 16K House Recall budget was ruled to protect

**The ruling language, verbatim:**
- `04-layer-0.md`, amendment of 7 September 2026: *"a configurable **16,000-token soft budget** (`VAL_RECALL_TOKEN_BUDGET`, a recall-context target, never a capability or spending limit)"*.
  - Its motivation: *"A live turn's response input reached 34,365 tokens, of which about 28,000 were six recalled messages quoted whole — recall was bounded by count alone."*
  - Its method: *"Tokens are estimated locally from characters at a ratio calibrated on the measured turn; **no provider is asked to count**."*
  - The unit, confirmed 8 September: *"the estimate is in provider-context-token scale … so 16,000 admits **approximately** 16,000 provider-counted tokens — the magnitude ruled."*
- Same file, amendment of 10 September 2026, headed *"the aggregate recall budget is a ceiling"*: *"No candidate may exceed the aggregate budget; a top candidate that does admits nothing from that ranking."*
  - `val_policy/recall.py` rule 2 gives the sense of "ceiling": *"The budget is an aggregate ceiling across all admitted excerpts, **never a per-message allowance**."* "Ceiling" there removes the 7 September top-candidate exception and the per-message reading. It is measured in the estimator's scale.
- `val_policy/recall.py`: *"The 16,000-token value is a recall-context target in provider-context-token scale, not a capability or spending limit. Tokens are estimated locally … never by asking a provider to count."*
- `val_policy/tokens.py`: *"No provider is asked to count, because counting would be a network call per turn … dividing by 3.6 counts slightly high and the estimate **errs toward admitting less**."* It also says: *"The context-window preflight and the reservation keep the byte upper bound, because **a ceiling needs a bound and a target needs an estimate**."*
- `VAL_Test_and_Evidence_Index.md` §12b (8 September): *"admits approximately as many provider tokens as the setting names, erring toward fewer"*.
- House Recall ruling, 12 September: *"the same full-text ranking, limit and aggregate budget as automatic recall"*.

**Purpose, as the record establishes it:**

| Purpose | Status in the record |
|---|---|
| Preventing recall from crowding out the active conversation | **Primary.** The motivating finding: 28,000 of 34,365 input tokens were recall. |
| Limiting one large historical source's dominance | **Stated.** 10 September: no candidate over the aggregate; stop at the first misfit; never substitute shorter ones. |
| Cost control | **Consequential, not stated as the purpose.** Expressly *"never a … spending limit"*. Recall tokens are uncached input, so size is cost. Spending safety is the budget ceiling's job, and the reservation there already uses the byte bound. |
| Hard provider-context safety | **Not this budget's job.** The whole-payload context preflight (`limit_overrun`) uses the proof-grade byte bound regardless of recall. |
| Latency control | **Not stated.** |

**Does the contract require an inviolable 16,000-provider-token maximum? No.**
- **What it does require:** the materials consistently describe a *soft target* of *approximately* 16,000 provider tokens, reached by a *local estimate* that *errs toward admitting less*, with no provider counting.
- **What "ceiling" means there:** aggregate and exception-free, in the estimator's scale. It is not a proof-grade provider-token maximum.
- **Where the 13 September turn failed:** it breaks the contract's *"approximately"* and *"erring toward fewer"*, not a hard-ceiling clause.
- **The owner decision:** the materials do not resolve how much variance is acceptable, so the precision required is yours to set.
- **A second owner decision:** every provider-counting option below **reverses an explicit ruling**, *"no provider is asked to count"*.

**Practical harm of overshoot** (16,000 base; recall excerpts are uncached input at $5/M on `opus-5-medium`; they sit after the history cache breakpoint, and the envelope is not carried to the next turn):

| Overshoot | Extra tokens | Extra cost on that turn | Context crowding | Window safety | Recall quality |
|---|---|---|---|---|---|
| 1% | 160 | $0.0008 | negligible | unaffected; the byte preflight guards the window | negligible |
| 3% | 480 | $0.0024 | negligible | unaffected | negligible |
| 5% | 800 | $0.0040 | minor | unaffected | negligible |
| 13 Sep observed | ≈4,500 over 16K (envelope ≈20,500, estimated 12,204: ≈68% undercount) | ≈$0.0225 over budget; ≈$0.0415 over the estimate | material: recall was ≈75% of the 27,519-token input | unaffected | material: one screenplay was ≈97% of recall, the dominance the 10 September rule exists to stop |

## 2. The byte-bound-first hybrid

**Cleanly implementable, with five structural requirements and no change to ranking or whole-excerpt semantics:**
1. **Sizing hook:** `select_within_budget` must size the *cumulative serialised envelope* through a sizing function the gateway supplies (bytes, or bytes then count). Today it sums a content-only estimate that excludes the envelope's fixed overhead (1,595 bytes with one excerpt) and per-excerpt metadata.
2. **Counting capability:** the provider-neutral boundary needs a declared counting capability, like streaming. OpenAI routes have no equivalent Anthropic endpoint and would fall back.
3. **Restricted preflight first:** the preflight must run on the envelope **before** any counting egress. Today it runs on the assembled request.
4. **Record type:** a free counting call has no `model_calls` task type. Whether and how it is recorded is a decision.
5. **Failure rule:** counting unavailable must fail toward the byte bound, admitting less.

**Against the alternatives:** see the table in §9. Provider counting from rank 1 counts every prefix. Counting all candidates at once sends everything, and one total cannot decide prefix admission when the total exceeds the budget, so further counts would still be needed. The current estimator undercounts.

## 3. The 13 September opening turn, modelled

Cumulative envelopes, reconstructed read-only (the same six candidates and order as the turn's logged selection):

| Prefix | New candidate | Envelope bytes | Envelope estimate | Today's content-only estimate | Provider count | Byte-only | Hybrid |
|---|---|---|---|---|---|---|---|
| 1 | rank 1: the 12 Sep verification question, 166 chars | 1,763 | 490 | 47 | not separable in the records | admit | admit, locally |
| 1–2 | rank 2: the 12 Sep diagnostic question, 166 chars | 2,420 | 672 | 94 | not separable | admit | admit, locally |
| 1–3 | rank 3: the 3 Sep *Phony Spumoni* draft, 38,987 chars | 43,939 | 12,204 | 10,924 (admitted on the day) | **≈20,500**, inferred: 27,519 input − 6,396 persona − ≈610 state envelope and message | reject, stop | **first counting request** → ≈20,500 > 16,000 → reject, stop |
| 1–4 | rank 4: a further 3 Sep draft, 20,923 chars | 65,563 | 18,202 | 16,736 | — | not considered | not considered |

**Confirmed:**
- Ranks 1–2 admit locally.
- Adding the screenplay crosses 16,000 bytes, so that cumulative envelope is the **only** counting request.
- That request would carry the envelope header and note, ranks 1 and 2 (both later admitted), and the whole 38,987-character screenplay (rejected).
- Admission stops at rank 3 under byte-only, the hybrid, and any exact count at 16,000.

**Recall-quality consequence to weigh:** under any correct 16K method this turn admits only the two earlier copies of the same question, none of the House material. The estimator's undercount is what let Val answer from the script.

## 4. Ordinary prose, modelled

Synthetic prose excerpts sized from the store's own distribution (Val messages: median 612, p90 3,429, maximum 11,666 characters). Provider tokens are **modelled**, not counted: prose at 3.2 characters per token, from the history cache increments of 13 September (3.08–3.33); envelope metadata at 2.0. A denser sensitivity case (3.0 and 1.6) gives the same admissions in every scenario.

| Scenario (six ranked excerpts) | Byte-only admits | Hybrid admits | Count requests | Rejected-content egress |
|---|---|---|---|---|
| median answers, 612 chars | 6 (≈1,150 tokens) | 6 | 0 | none |
| p90 answers, 3,429 chars | 3 (≈3,200 tokens) | 6 (≈8,300 modelled) | 3 | none |
| long notes, 5,000 chars | 2 (≈3,100 tokens) | 6 (≈11,200) | 4 | none |
| longest answer on record, 11,666 chars | 1 (≈3,650 tokens) | 3 (≈12,150) | 3 | one 11,668-byte candidate, egressed and not admitted |
| mixed 3,429 / 612 / 5,000 / 3,429 / 11,666 / 612 | 4 (≈3,900 tokens) | 6 (≈9,600) | 2 | none |

**What each count request sends.** Each request resends the whole cumulative envelope, not just the new candidate.
- **Long-notes case:** 17,426, 22,866, 28,307 and 33,748 bytes. Each is 5,002 bytes of first-time candidate content, and the rest is already-admitted content plus overhead sent again.
- **Across the four requests:** 102,347 bytes leave the machine for counting, 20,008 of them first-time candidate content.
- **Longest-answer case:** the third request sends 49,530 bytes, of which 11,668 are a rejected candidate.

**Capacity.** Byte-only holds ordinary prose to roughly 3,000–4,000 provider tokens under a 16,000 setting, a quarter of the magnitude ruled once fixed overhead is included. The hybrid reaches roughly 8,000–12,000 in these cases, stopping on the six-excerpt limit or the budget.

**Worst case:** six serial requests. That happens when rank 1 alone exceeds 16,000 bytes and every later prefix still fits under the count.

## 5. What `count_tokens` guarantees

The provider documentation says, verbatim:
- *"The token count is an **estimate**. In some cases, the actual number of input tokens used when creating a message might differ by a small amount."*
- *"Token counts may include tokens added automatically by Anthropic for system optimizations. You are not billed for system-added tokens."*
- *"No, token counting provides an estimate without using caching logic."*

Neither the bundled SDK documentation nor the SDK's docstring states a maximum discrepancy, an upper-bound guarantee, or tokenization identical to message creation. **`count_tokens` alone cannot prove an inviolable 16,000-actual-provider-token ceiling.** A safety margin reduces the risk of overshoot but does not create proof, because the discrepancy is unbounded in the documentation.

**Methods modelled, not chosen:**

| Method | Guarantee |
|---|---|
| Byte-only | Proof-grade ceiling: tokens never exceed UTF-8 bytes. |
| `count_tokens` against 16K | A documented estimate, "may differ by a small amount". |
| `count_tokens` with a margin | Lower overshoot risk, no proof. |
| Byte-first hybrid, count plus margin above the byte threshold | Proof-grade below 16,000 bytes; estimate-grade above. |

## 6. Latency

**No local measurement of the counting endpoint exists, and none was taken.**
- **On-record Anthropic round trips** are all generative: the fastest complete real call is 822 ms (Haiku, 13,612 tokens in, 12 out), and classification runs at median 1,441 ms.
- **The planning figure is an assumption:** counting is non-generative and should be materially faster, so 0.2–0.6 s per request is used below. It is not evidence.

| Option | 13 Sep turn | p90 / long-notes prose | Worst case | Added pre-response latency (assumed 0.2–0.6 s each) |
|---|---|---|---|---|
| Byte-only | 0 | 0 | 0 | none; local serialisation only |
| Count from rank 1 | 3 | 6 | 6 | 0.6–1.8 s on this turn; up to 1.2–3.6 s |
| Count all at once | 1 total, plus prefix counts when the total exceeds the budget | 1+ | 1 + up to 6 | ≥0.2–0.6 s |
| Byte-first hybrid | **1** | 3–4 | 6 | 0.2–0.6 s on this turn; 0.6–2.4 s; up to 1.2–3.6 s |

**Consolidating without changing admission.** Binary search over the prefixes above the byte bound needs at most 3 requests for 6 candidates, if successive counts are monotonic. It sends prefixes past the eventual stop point, which means more rejected-content egress. Concurrent counting of every prefix would cut latency to one round trip, but it sends content before it is known to be necessary. That is excluded by your instruction.

**Outside the critical path.** The only candidate is counting each message once when it is persisted, and summing stored counts at recall. That adds a counting call to every turn, against the per-turn necessity rule, and a new sidecar table. The summed counts would still differ from the serialised envelope's count, so it is not a proof and not recommended.

## 7. Billing, retention, organization status

- **Billing:** *"Token counting is **free to use** but subject to requests per minute rate limits based on your usage tier."*
- **Rate limits:** *"Token counting and message creation have separate and independent rate limits."*
- **ZDR:** the token-counting page lists *"ZDR: eligible (excludes Covered Models)"*. The retention page states *"Claude Messages and Token Counting APIs: ZDR applies to these endpoints for eligible features"*, and its feature table marks token counting "Yes". **No documented retention difference** exists between counting and eligible Messages traffic. Default retention outside ZDR: *"Conversation content (your prompts and Claude's outputs) is not retained by default; the exception is Covered Models."* Flagged content may be retained *"for up to 2 years"* under any arrangement.
- **Organization ZDR status:** *"To request ZDR for your organization, contact the Anthropic sales team. ZDR is enabled per organization."* Nothing in the repository, the service configuration or the records establishes a ZDR arrangement for this organization. **Organization-specific ZDR status unknown.** The Protected premise recorded on 18 August 2026 rests on "not retained by default", not on ZDR.

## 8. Egress and eligibility

| Method | What leaves the machine beyond today |
|---|---|
| Byte-only | Nothing. Only the final admitted envelope, inside the response call. |
| Count from rank 1 | Every cumulative prefix, from rank 1 up to and including the first rejection, before the response call. |
| Count all at once | Every candidate, including ones that would never be admitted (on 13 Sep: all three drafts, 87,207 bytes). |
| Byte-first hybrid | Nothing while the envelope is ≤16,000 bytes. Above that, each cumulative prefix up to and including the first rejection, resending already-admitted content each time. |

**Eligibility:** `01-architecture.md` §5.4 authorises Protected content to **routes explicitly declared eligible**, per configuration, for inference; the gateway enforces it per route. The counting endpoint is not a registered configuration and not a task type. Its purpose, sizing content that may never be sent for inference, is not covered by any ruling. The 7 September ruling forbids asking a provider to count.

**Sending otherwise-rejected material to a counting endpoint is a new egress purpose that needs explicit owner authorisation.** Eligibility has not been broadened.

## 9. Decision table

| | Current estimator | Byte-only | Count from rank 1 | Count all at once | Byte-first hybrid |
|---|---|---|---|---|---|
| Budget definition satisfiable | none; undercounts | A (inviolable) and B | B only | B only, and inefficiently | B; A only below 16,000 bytes |
| Hard-ceiling strength | none | proof | estimate | estimate | proof ≤16 KB, estimate above |
| Closeness to actual provider tokens | up to ≈70% under | 2–4× over for prose | "small" documented difference | same | proof below, small difference above |
| Usable capacity | over-admits | prose ≈3–4K tokens | ≈16K | ≈16K | ≈16K; small recall unchanged |
| Cost protection | failed on 13 Sep | strong, conservative | good | good | good |
| Context-crowding protection | failed | strong | good | good | good |
| Extra provider egress | none | none | every prefix | every candidate | only prefixes above 16 KB |
| Rejected-content egress | none extra | none | yes | yes, all | yes, one rejected candidate at most per turn |
| Repeated admitted-content egress | none | none | high | once per request | above 16 KB only |
| Monetary API cost | none | none | free (documented) | free | free |
| Added pre-response latency | none | none | per prefix | ≥1 round trip | 0 when small; per prefix above 16 KB |
| Round trips, 13 Sep | 0 | 0 | 3 | 1+ | 1 |
| Round trips, worst case | 0 | 0 | 6 | 1 + up to 6 | 6 |
| Retention / ZDR | as Messages | as Messages | counting endpoint; org ZDR unknown | same | same, only above 16 KB |
| Implementation complexity | existing | low | high | high | moderate-high |
| If counting is unavailable | n/a | n/a | fall back to byte-only, or zero | same | byte-only; fails toward less |

**Recommendation under A (16K is inviolable): byte-only.** It is the only method with a documented proof. Accept the capacity loss for prose, or re-rule the budget's number in a separate decision; bytes are not tokens.

**Recommendation under B (reliably close; small variance acceptable): byte-first hybrid.**
- **Cost:** no egress, latency or change for ordinary small recall, and one round trip on the 13 September turn.
- **Rejection:** it rejects the screenplay exactly as an exact count would.
- **Capacity:** it recovers roughly the ruled magnitude for prose.
- **Failure:** it falls back to byte-only.
- **Rulings it needs first:** reversing *"no provider is asked to count"*, authorising counting-purpose egress (including rejected content) under the Protected premise, and deciding how counting calls are recorded.
- **Your call:** whether to apply a margin under the count.
