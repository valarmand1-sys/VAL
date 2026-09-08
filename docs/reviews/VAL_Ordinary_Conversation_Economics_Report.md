# VAL — Ordinary-Conversation Economics: Prompt Caching, Measured

**Date:** 8 September 2026.
**Status:** Caching is implemented and deployed under the accounting rules of the ruling of this date. Measurements are from the real Anthropic provider through the real gateway into the scratch store. **Nothing here resumes substantive use**; that is Lord Armand's ruling on the figures below.
**Companion:** `VAL_Partner_Candidate_Inventory_and_Eligibility.md` (inventory, eligibility, qualification packet); evidence index §13.

---

## 1. Provider facts, from first-party documentation on 8 September 2026

| Fact | Source and wording |
|---|---|
| Lifetimes | 5 minutes (default) and 1 hour (`ttl: "1h"`); "the cache is refreshed for no additional cost each time the cached content is used"; "the lifetime is measured from the start of the request that writes or reads the cache entry, not from the end of its response." (prompt-caching page) |
| Multipliers | 5m write 1.25×, 1h write 2×, read 0.1× base input. Claude Opus 5: $5 base, $6.25 / $10 write, $0.50 read, $25 output. Claude Sonnet 5: $2 / $2.50 / $4 / $0.20 / $10 — and the page states its $2/$10 "is now the standard price. The previously scheduled increase to $3/$15 … on September 1, 2026 will not occur." (pricing page) |
| Minimum cacheable prefix | Claude Opus 5: **512 tokens**; Sonnet 5: 1,024; Haiku 4.5: **4,096**. "Shorter prompts cannot be cached, even if marked … processed without caching, and no error is returned." |
| What invalidates a hit | Exact prefix match; hierarchy tools → system → messages; a change at a level invalidates it and everything after. **Structured outputs and effort changes invalidate the messages cache but not the system cache.** Read literally that would let the blind call (schema-constrained) and the response call share the persona's entry; measured, they do not — the schema's rendered text is part of the blind call's prefix and it keeps its own entry (§4). |
| Growing conversations | Automatic top-level `cache_control` moves the breakpoint to the last block and reads the prior prefix incrementally; at most four breakpoints; a 20-position lookback. |
| Usage fields | `input_tokens` is only the uncached remainder after the last breakpoint; total input = `cache_read_input_tokens` + `cache_creation_input_tokens` + `input_tokens`; `cache_creation` breaks writes down by lifetime. |
| Retention | Retention page, feature table, prompt caching: ZDR-eligible **Yes** — "Your prompts and Claude's outputs are not stored. KV cache representations and cryptographic hashes are held in memory for the cache TTL and promptly deleted after expiry." Caches "are isolated between organizations … also isolated per workspace within an organization on the Claude API." Claude Opus 5 is not a Covered Model; content is "not retained by default". |

**Reading on the Protected-data premise.** The Anthropic eligibility ruling (15 August, re-verified 18 August) rested on no training and no default retention of content. Caching keeps both true: nothing is stored at rest, the in-memory representation is bounded by the TTL and isolated to this organisation. I read this as within the existing approval and enabled it; it is recorded so the reading can be overruled. The Covered-Model rule is unaffected (Opus 5 is not one).

## 2. What is byte-identical across turns, exactly

The rendered request on a partner call, in order:

| Part | Bytes across turns | Cacheable |
|---|---|---|
| `system` — the persona, whole (`03-persona.md` from the active row; measured **5,819 tokens** as written to cache) | Identical on every partner call: response calls, blind calls, every conversation, every project | **Yes — the breakpoint.** |
| `messages[0]` — the memory envelope (`VAL-MEMORY-V1` marker, fixed note, then the recalled excerpts as JSON) | The marker and note are fixed; the excerpts differ per turn, and the block is absent when nothing is recalled | No: the fixed part is a few hundred tokens and the varying part is inside the same block |
| Same-conversation history | Identical prefix turn to turn — **but it sits after the envelope**, so its prefix hash differs whenever the envelope does | Not under the present assembly order |
| The current user message; the reconciliation envelope on a consequential response call | Per turn | No |
| The blind call's message — fixed instruction plus the stripped question | Instruction fixed (~150 tokens), question per turn | Only the persona ahead of it; the instruction is too small to matter |
| Classifier and strip calls (Haiku) — system prompts of a few hundred tokens | Fixed | **No: below Haiku 4.5's 4,096-token minimum.** Nothing is requested, nothing is charged. |

So the one lever available without changing what Val sees is the persona, and it is the largest single component of every partner call. The history lever is real and is recorded, not taken: moving the memory envelope after the history would let the conversation prefix cache incrementally (automatic caching would then read the whole prior conversation each turn and write only the new turn), but it changes the order in which Val encounters recalled material versus the live conversation, which is a ruling.

## 3. The arithmetic, at the measured persona size

Persona as cached: 5,819 tokens on Claude Opus 5 (the blind call's entry is 6,084 — see §4). Per partner call:

| Cost of the persona alone | Amount |
|---|---|
| Uncached (before this change) | $0.02910 |
| Written, 5m lifetime | $0.03637 |
| Written, 1h lifetime | $0.05819 |
| Read (either lifetime) | $0.00291 |

**Break-even, per lifetime, for n partner calls that share the entry:**

| Pattern | Uncached | 5-minute | 1-hour |
|---|---|---|---|
| 1 call, no reuse | $0.0291 | $0.0364 (worse) | $0.0582 (worse) |
| 2 calls, both within the window | $0.0582 | $0.0393 | $0.0611 (still worse) |
| 3 calls | $0.0873 | $0.0422 | $0.0640 |
| 10 calls | $0.2910 | $0.0626 | $0.0844 |
| n calls | 0.0291 n | 0.0364 + 0.0029 (n−1) | 0.0582 + 0.0029 (n−1) |

The reviewers' arithmetic holds: **a 5-minute entry must be reused once to beat uncached; a 1-hour entry needs two reads to clearly win.** Between the two lifetimes: 5-minute is $0.0218 cheaper per warm session **if no start-to-start gap between partner calls exceeds five minutes**; every gap longer than that costs a fresh 5-minute write ($0.0364) where the 1-hour entry would have cost a read ($0.0029) — so **one pause longer than five minutes within an hour pays for the dearer write with $0.0117 to spare, and every further pause saves $0.0335.** Lord Armand's stated cadence — pauses to think and read, often longer than five minutes — is the 1-hour case. A consequential turn is two partner calls (blind, then response) seconds apart, so it always reads twice on one write.

**Can breakpoints keep the persona warm while history grows?** Yes, trivially: the persona's entry is independent of anything after it, and a read refreshes it; every partner call in a session refreshes the same entry whatever the history does. What history does not get is its own entry (§2).

## 4. Measured — cold and warm, real provider

Scratch store `val_test`, real Claude Opus 5 and Haiku 4.5, real waits (`demonstrate_cache.py`, `cache_run2.json`; the follow-up in `cache_run2b.json`). Each turn is one classification on Haiku (uncacheable, ~$0.0009) plus the partner call(s) on Opus 5. "Cold" = the persona written this call; "warm" = read.

| Scenario (each a new conversation in the scratch project) | Lifetime | Persona entry | Uncached input | Output tokens | Partner call(s) | **Turn cost** | Wall |
|---|---|---|---|---|---|---|---|
| "Hello." — first call of the session | 5m | **created** (5,819 written at $6.25/M) | 8 | 303 | $0.0440 | **$0.0448** | 6.9 s |
| "Hello." — after a **5.5-minute wait** | 5m | **created again** — the entry had expired | 421 | 171 | $0.0428 | **$0.0436** | 5.6 s |
| "Hello." — one reuse, seconds later | 5m | **hit** (5,819 read at $0.50/M) | 598 | 262 | $0.0125 | **$0.0133** | 6.9 s |
| Short ordinary question | 5m | hit | 529 | 315 | $0.0134 | **$0.0143** | 7.3 s |
| Paragraph (~200 words asked) | 5m | hit | 1,520 | 619 | $0.0260 | **$0.0269** | 14.2 s |
| Consequential (classify, strip, blind, reconcile) | 5m | blind: **created its own entry** (6,084); response: hit | 241 + 2,531 | 885 + 1,428 | $0.0614 + $0.0513 | **$0.1150** | 40.7 s |
| "Hello." — first call after the 5m block expired | **1h** | **created** (5,819 written at $10/M) | 769 | 197 | $0.0670 | **$0.0678** | 5.9 s |
| "Hello." — after a **6-minute gap** | 1h | **hit** — the entry survived | 942 | 227 | $0.0133 | **$0.0141** | 6.6 s |
| Short ordinary question | 1h | hit | 2,134 | 412 | $0.0239 | **$0.0248** | 9.4 s |
| Paragraph | 1h | hit | 2,886 | 580 | $0.0318 | **$0.0327** | 11.1 s |
| Consequential | 1h | blind: **created its own entry** (6,084 at $10/M); response: hit | 241 + 4,145 | 888 + 1,602 | $0.0843 + $0.0637 | **$0.1503** | 42.7 s |
| Consequential, again, one minute later (follow-up run) | 1h | blind: **hit** (6,084 read); response: **refused by the provider, 0 output tokens** (§7b) | 241 + 4,563 | 1,001 + 0 | $0.0293 + $0.0270 | $0.0587 (no answer) | 21.1 s |
| Consequential, again, immediately | 1h | blind: hit; response: refused, 0 output | 241 + 4,254 | 1,046 + 0 | $0.0304 + $0.0254 | $0.0582 (no answer) | 23.6 s |

Every turn also carries one classification on Haiku (about $0.0009, 1.1–1.8 s) and, when consequential, one strip (about $0.0015, 2.2–2.4 s); those are inside the turn cost. Comparators without caching: the 7 September ordinary turn cost **$0.0375** (5,840 in / 298 out, 7.5 s wall); the 7 September consequential turn cost **$0.1595** (62 s).

**Two measured facts the documentation did not state.** (1) **The blind call keeps its own cache entry.** Its prefix is the persona plus the structured-output grammar text the provider renders for the schema — 6,084 tokens against the plain call's 5,819 — so the first blind call of a session writes a second entry and later blind calls read it (confirmed: the follow-up's blind calls read 6,084 tokens, $0.0030 each, where the first had cost $0.0608 to write under 1h). A session therefore pays two cold writes, not one. **Ruled expected behaviour (8 September 2026):** the two entries stay separate because the two contracts differ; the anti-sycophancy wire contract is not reshaped to share a cache. (2) **The uncached remainder grew across the run**, from 8 to 4,563 tokens, because recall in the scratch project kept admitting the earlier turns' text as the same questions were re-asked; that is a property of re-asking in one project, not of caching, and it is why the later warm turns cost more than the first.

**Cold versus warm, per message type (partner call only, persona 5,819):**

| Type | Uncached (before) | Cold, 5m write | Cold, 1h write | Warm (read) |
|---|---|---|---|---|
| "Hello." (≈250 output tokens) | ≈$0.035 | $0.0440 | $0.0670 | **$0.0125–0.0133** |
| Short question (≈350 output) | ≈$0.038 | ≈$0.046 | ≈$0.069 | **$0.0134–0.0239** |
| Paragraph (≈600 output) | ≈$0.045 | ≈$0.053 | ≈$0.075 | **$0.0260–0.0318** |
| Consequential (blind + response) | $0.157 (7 Sep) | $0.113 (one write, one read) | $0.148 | ≈$0.09 with both entries warm (blind read $0.030 + response read ≈$0.06) |

**Provider-reported figures behind the table:** on the cold "Hello." the provider reported `input_tokens` 40 (the uncached remainder), `cache_creation_input_tokens` 5,787, `cache_read_input_tokens` 0; on the warm calls `cache_read_input_tokens` 5,787 with the same uncached remainder. The cache lifetime measurement is real: the 5-minute entry was gone after a 5.5-minute wait; the 1-hour entry survived a 6-minute gap.

## 5. Against the two targets

**Target 1 — materially reduce the ~$0.04 ordinary turn without reducing quality: met.** A warm ordinary turn measures **$0.013–$0.025** including classification — a 35–65% reduction depending on how much recall the turn carries — with the persona whole, the same route, the same effort, the same output. The cold turn is dearer than before ($0.045 at 5m, $0.068 at 1h) and is paid once per lifetime window; under the deployed 1-hour lifetime and Lord Armand's cadence, that is about once an hour of use, twice if a consequential turn occurs (the blind entry).

**Target 2 — ordinary useful conversation at a fraction of a cent: not met by Opus caching, and it cannot be.** The floor of a warm minimal turn on Claude Opus 5 is the persona read ($0.0029) plus the classifier ($0.0009) plus the output — and the output for "Hello." was 303 billed tokens ($0.0076) for an 84-character visible answer. **Output, not input, is now the dominant term, and most of it is thinking** (§7). Opus caching brings the ordinary turn to about a cent and a half; it does not bring it to a fraction of a cent. The levers that can, in the order of the ruling: an evidence-qualified partner route at lower rates (on Claude Sonnet 5's published rates the same warm "Hello." would be roughly $0.004: persona read $0.0012, output $0.003, classification $0.0009 — a projection from rates, not a measurement, and not a qualification); and the thinking share of output, which is a registry `reasoning_effort` value and a quality question for ruling, never a silent change.

**Lifetime, as deployed: 1 hour.** The measurement bears out the arithmetic in §3: the 5-minute entry was gone after a 5.5-minute pause and cost a full re-write ($0.036); the 1-hour entry read for $0.003 after a 6-minute pause. With pauses longer than five minutes the rule of his working pattern, the 1-hour lifetime is the cheaper one from the first such pause each hour; in a session with no such pause it costs $0.022 more per cold write than 5 minutes would. The setting is `VAL_CACHE_TTL` in the installed service environment and changes without code. Not chosen: a keep-alive (the documented `max_tokens: 0` re-warm) — it is a recurring background call and a design change, and is reported here as a lever, not taken.

## 6. Accounting, as ruled — what the implementation does

- **Reservation never assumes a hit.** `maximum_cost` prices every input token at the greater of the base rate and the requested lifetime's write rate, so the reservation covers a full miss plus creation; the unspent difference returns at settlement.
- **Settlement from the provider's usage.** The adapter reports the four figures (uncached, 5m writes, 1h writes, reads); the gateway prices them at the registry's verified rates, stores the total in `model_calls.cost` at call time, and writes the split — with the outcome `hit` / `created` / `hit_and_created` / `not_cached` — to `model_call_cache_usage` in the same transaction. Never recomputed.
- **Caching is requested only when it can count:** the gateway is configured with a lifetime (`VAL_CACHE_TTL`), the route's caching is verified with rates (`caching = AVAILABLE`), and the system text meets the model's minimum. Haiku's classifier calls never qualify and never reserve for it.
- **The persona is untouched.** Whole, exactly once, in `system`, as before; the only change on the wire is the `cache_control` mark on that block.
- **OpenAI** reports no cache figures through the adapter and has no verified cache rates in the registry, so any OpenAI caching is priced at the base rate — over-stated, never under.

## 7. Output length — report only, nothing changed

**Does the persona or the scaffolding encourage long answers?** The persona does not. `03-persona.md` §5 asks for a bearing that is "composed, precise, unhurried", "never gush", reports "briefly and concretely", and its §9 reference lines are one to three sentences each. The measured visible answers match it: 84 characters for "Hello.", 291–709 for a short question, 1,169–1,181 for a requested paragraph, 1,849–2,167 for a consequential reconciliation. The scaffolding leans the other way in two places, both deliberate and both ruled: the reconciliation note asks her to reconcile "explicitly" — hold and say why, or update and say what moved her — and the output contract appends a JSON verdict; the blind instruction asks for a position "briefly" with "brief reasoning", and the recorded blind reasoning ran 1,214–1,351 characters. Neither is a length instruction; both invite explanation.

**Where the billed output actually goes.** Claude Opus 5 runs adaptive thinking by default, the registry sends `effort = high` explicitly, and the provider bills thinking as output tokens. Comparing billed output tokens with the visible text (estimated at 3.6 characters per token):

| Turn | Billed output | Visible text | Visible share | Thinking share (by difference) |
|---|---|---|---|---|
| "Hello." cold | 303 | 84 chars ≈ 23 tokens | 8% | **≈92%** |
| "Hello." warm | 262 | 291 chars ≈ 81 | 31% | ≈69% |
| Short question | 315 / 412 | 537 / 709 chars ≈ 149 / 197 | 47% | ≈53% |
| Paragraph | 619 / 580 | 1,169 / 1,181 chars ≈ 325 / 328 | 53–57% | ≈45% |
| Consequential response | 1,428 / 1,602 | 1,849 / 2,167 chars ≈ 514 / 602 | 36–38% | **≈63%** |
| Blind position | 885 / 888 | position + reasoning ≈ 1,500 chars ≈ 415, plus JSON | ≈50% | ≈50% |

So the 3,216-token, 50-second consequential response of 7 September was, on this evidence, roughly a third visible prose and two thirds thinking. **Cost and latency contribution of output length:** on the warm consequential turn of this run, output was $0.062 of the $0.150 turn (41%) and all but a few seconds of the 42.7-second wall (the two partner calls generated for 15 and 24 seconds; the cached input was read in well under a second each); on the warm ordinary turns output was 50–60% of cost and nearly all of the wall time. Every second of perceived latency after the classifier is generation.

**Nothing was changed.** The persona's voice, the reconciliation contract, the blind instruction, and the registry's effort level are as they were. The one lever with a large effect — effort, which is a quality setting — is for ruling.

### 7b. Finding for ruling: a provider refusal with no text became an empty Val message

In the follow-up run, two consequential response calls were **refused by the provider** (`stop_reason: refusal`, 0 output tokens, under a second, request ids `req_011CerPt5ukFdXGinnvxemEh` and `req_011CerPuqBXKM9FUSCgAuZz9`) — the fourth and fifth time the same consequential question was sent in one scratch project within fifteen minutes, with the earlier answers recalled into the prompt. Why the provider declined is not known: the adapter does not capture `stop_details`, which carries the category and explanation. The blind positions were formed and recorded (`enforced`); no deliberation was written, correctly, because there was no verdict.

What went wrong is what happened next. `settle_turn` treats `REFUSED` as "a deliberate refusal is Val's answer" (closure pass, 18 August 2026) and persists the text — which was empty. **Two `messages` rows with `role = val` and zero-length content were written** in the scratch store. An empty utterance is not an answer; it is a false record, and through the interface it would appear as Val saying nothing. The 18 August doctrine assumed a refusal carries words. **Recommendation, not applied:** a response whose text is empty — whatever its terminal state — ends the turn unanswered with the truthful cause (the provider refused, with its stated category), writes no Val message, and keeps the blind row; and the Anthropic adapter captures `stop_details` into the call's failure detail so the reason is on the record. **Ruled and fixed the same day (820d2f1, deployed):** an empty result ends the turn unanswered with the provider's observed terminal fields as the cause, no assistant message is written, and the adapters now capture `stop_reason` and `stop_details`. The SDK's refusal categories include `reasoning_extraction` — "the request asks the model to reproduce its internal reasoning in the response text" — which is a plausible cause for a reconciliation call that asks Val to say what moved her; it was not captured on the two refused calls and is not asserted. Future refusals will carry the category on the record.

## 8. What this round did not do, by ruling

No trivial-turn carve-out; no classifier deciding when a response may fall below the partner floor; no return of Haiku to Val's voice; no trimming of the persona; no latency work; no qualification of any route. The next economic levers, in the order the ruling set: evidence-qualified partner routes competing on total cost (the packet is in the companion report), and — only by ruling — the assembly-order change that would let history cache.
