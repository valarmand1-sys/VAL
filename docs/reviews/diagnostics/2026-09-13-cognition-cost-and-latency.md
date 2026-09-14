# Cognition cost and latency — first bounded diagnostic, 13 September 2026

Diagnostic and contract-defining only, on Lord Armand's instruction of 13 September 2026. **No provider call, no routing change, no classifier change, no persona change, no test traffic.** Every figure comes from the live store (read-only transactions), the service log, or the repository. Figures marked *derived* or *estimated* are arithmetic on recorded quantities and are labelled as such; nothing is presented as recorded that is not.

Rates used (registry, `opus-5-medium`): input $5/M, one-hour cache write $10/M, cache read $0.50/M, output $25/M. `sonnet-5-low`: input $2/M, one-hour write $4/M, read $0.20/M, output $10/M. Haiku 4.5: input $1/M, output $5/M.

---

## 1. The Hardmarch exchange, decomposed

Conversation `01a09bab-0fc7-747f-9f2a-6c97510996c8`, user message sequence 9 (`01a09d46-35e5-…`, 19:16:59 CDT), Val's answer sequence 10 (`01a09d47-44d3-…`). Persona v1.8, revision 7. **Exchange total $0.255322** (ledger month-to-date $2.781998 → $3.037320).

| Call | Route | In | Uncached | Cache read | Cache write (1h) | Out | Cost | Share | Latency |
|---|---|---|---|---|---|---|---|---|---|
| classification | `haiku-4-5-20251001` | 788 | 788 | — | — | 18 | $0.000878 | 0.34% | 1,699 ms |
| strip | `sonnet-5-low` | 2,031 | 110 | 0 | 1,921 | 643 | $0.014334 | 5.61% | 6,317 ms |
| blind_position | `opus-5-medium` | 7,471 | 7,471 | — (none requested) | — | 647 | $0.053530 | 20.97% | 11,303 ms |
| conversation | `opus-5-medium` | 12,134 | 1,762 | 0 | 10,372 | 2,962 | $0.186580 | **73.08%** | 49,903 ms |

**Visible versus hidden output cannot be established exactly from persisted data.** Anthropic's usage reports one output figure that includes thinking; the adapter persists that figure and the visible text, not a split. Estimates below use 3.6–4.2 characters per token for Val's prose.

### The final response, $0.186580

| Component | Tokens | Cost | Share of call | Basis |
|---|---|---|---|---|
| v1.8 persona, written to the one-hour cache | ≈6,995 | ≈$0.069950 | 37.5% | derived, §5 |
| retained history through sequence 8, written | ≈3,377 | ≈$0.033770 | 18.1% | 10,372 − persona |
| fresh turn material, uncached (record-state envelope, reconciliation envelope, the message) | 1,762 | $0.008810 | 4.7% | recorded |
| cache read | 0 | $0 | 0% | recorded |
| output: visible prose (4,002 characters) plus the reconciliation verdict block | ≈1,050–1,300 | ≈$0.026–0.033 | 14–18% | estimated |
| output: hidden reasoning | ≈1,660–1,910 | ≈$0.042–0.048 | 22–26% | estimated remainder |
| **total** | 12,134 in / 2,962 out | **$0.186580** | | 0.069950 + 0.033770 + 0.008810 + 0.074050 |

The owner's reconciliation check holds exactly: output $0.074050 (39.7%), input and cache $0.112530.

**Cold state.** No Claude Opus call had run since 12:18:21; every one-hour entry had expired. The same exchange with a warm prefix (persona and history read, strip instruction read) would have cost ≈$0.1495: the cold state added ≈$0.1058, 41% of the exchange.

### Persona across the exchange

v1.8 persona in the final call's cold write ≈$0.069950; in the uncached blind call ≈$0.034975. **Persona total ≈$0.104925, 41.1% of the exchange.** Warm, the final call's persona portion would have been ≈$0.003498.

## 2. Was the trigger correct?

**Correction to the premise, then confirmation.** "Hardmarch was your strongest recommendation, so follow the logic of your own choice" belongs to **sequence 7** (12:17), whose strip withheld it as an `attributed_prior`. The **sequence 9** exchange diagnosed here withheld, from the service log:

- `attributed_prior`: "Your criticism of the first founding was fair. I agree that the abandoned garrison and perfectly explanatory ledger make it too neat." — Val's own earlier judgment presented back to her, with the author's agreement;
- `preference`: "I want something less conventionally heroic and more historically messy, something that could plausibly have become nobler in the telling over generations."

The blind call received only "Keep Hardmarch as the working name, but take another pass at the founding."

**Two separate predicates produced the blind call, against the current code:**

1. **Consequential** — the §4.8 classifier (`val_policy.deliberation.CLASSIFIER_INSTRUCTION`): no hard exclusion, a choice among alternatives, binding later work ("creative direction, approach, priority, scope, or a standard for quality"). A revision of the House founding's direction meets that test. The classifier stores only the verdict, not its reasoning.
2. **Influence present** — the §4.1 strip: an `enforceable` result removing preference and attributed-prior spans. Only an enforceable strip produces a blind call (ruling of 10 September 2026).

So the conclusion is confirmed: this is the integrity machinery operating on the case it was designed for. The blind position ran because influence was present, not because the task was difficult. Consequential turns with no influence spans — sequences 3 and 5 of the same conversation — paid classification and strip and made no blind call.

## 3. Ordinary-turn shape from genuine use

**28 user turns since the partner route entered service (10 September 10:49). Every one was answered, and every one made exactly one conversation call.** Four also made a blind-position call; no other partner-quality call exists on the turn path.

*Genuine use* excludes, by record: the two conversations titled "Engineering verification…" (3 turns), the scripted persona-verification cluster of 11 September 18:10–18:14 (5 turns, seconds apart), and the House Recall verification cluster of 12 September 15:30–15:31 (3 turns). That leaves **17 genuine turns: 13 made one partner-quality call, and 4 made two.**

| Turn | Second partner call | Why |
|---|---|---|
| 10 Sep 18:25 | blind position, ordering `contaminated` | consequential; the strip did not establish separation. Before the strip correction of 10 September 21:36, a non-enforceable strip still produced a blind call. **Under the current rule this call would not run.** |
| 11 Sep 13:30 | blind position, enforced | consequential; enforceable strip |
| 13 Sep 12:17 | blind position, enforced | consequential; attributed prior "Hardmarch was your strongest recommendation…" withheld |
| 13 Sep 19:17 | blind position, enforced | consequential; attributed prior and preference withheld (§2) |

**Ordinary non-consequential turns already have the desired shape:** user → classification (structured route) → one partner call → Val Core settlement → user. There is no committee to remove. Remaining fan-out is confined to consequential turns with removable influence (4 of 17 genuine turns), plus the structured calls: classification on every turn, and strip on the 8 genuine consequential turns.

## 4. The blind-position contract

- **Instruction** (`BLIND_POSITION_INSTRUCTION`): "Commit: name the option you would choose and why, briefly", honest confidence, one JSON object.
- **Schema** (`BLIND_POSITION_OUTPUT_SCHEMA`): `position`, `confidence` (`high` | `medium` | `low`), `reasoning`; all required; no length constraint.
- **Ceiling:** `BLIND_MAX_OUTPUT_TOKENS = 4096`, which bounds thinking plus visible text together on Claude Opus 5. Two attempts; a truncated position is never used, and after the second failure the turn ends unanswered.
- **Consumed downstream:** all three fields. `reconciliation_envelope` carries position, confidence and reasoning into the final call; the `blind_positions` row stores all three; the deliberation row records confidence and outcome against them.

| Blind call | Route | Out (billed) | Visible JSON (position + reasoning chars) | Visible tokens (est.) | Hidden (est.) | Cost | Latency |
|---|---|---|---|---|---|---|---|
| 7 Sep 21:07 | Haiku 4.5 (before the partner route) | 150 | 225 + 365 | — | — | $0.005485 | 5,496 ms |
| 7 Sep 21:08 | Haiku 4.5 | 319 | 748 + 760 | — | — | $0.006385 | 9,447 ms |
| 10 Sep 18:27 | `opus-5-medium` | 1,364 | 431 + 2,063 | ≈650 | ≈710 | $0.096875 (6,011 written) | 23,594 ms |
| 11 Sep 13:30 | `opus-5-medium` | 512 | 395 + 1,225 | ≈420 | ≈90 | $0.074460 (6,011 written) | 10,392 ms |
| 13 Sep 12:17 | `opus-5-medium` | 1,446 | 1,192 + 1,910 | ≈800 | ≈650 | $0.104185 (6,661 written) | 43,925 ms |
| 13 Sep 19:17 | `opus-5-medium`, no cache | 647 | 306 + 616 | ≈240 | ≈400 | $0.053530 | 11,303 ms |

**Does the contract encourage expansive prose?** "Briefly" is the only bound, and the reasoning field has run from 616 to 2,063 characters. The instruction permits long reasoning; it does not encourage it. The most recent call is already compact.

**What must survive:** a committed position naming the option; the material reason or reasons for it; confidence; and enough reasoning that the reconciliation can say what held or what moved her. Everything beyond the material reasons is not evidence.

### Proposed safe amendment (not implemented)

Replace "Commit: name the option you would choose and why, briefly." with:

> "Commit: name the option you would choose, in at most two sentences, and give only the material reasons for it — at most about 120 words of reasoning. Do not restate the question, draft the work itself, or add caveats that would not change the position."

**Unchanged:** the schema, the parser, the 4,096 ceiling (thinking shares it, so lowering it adds truncation, retries and unanswered consequential turns), the attempt count, the payload log and the reconciliation envelope. **No hard length rejection:** a parser-enforced maximum would turn an over-long but valid position into a retry, which costs more and risks an unanswered turn.

**Required tests:**
- the instruction carries the bound;
- the schema and parser are byte-identical, and a position with long reasoning still parses and is recorded;
- the ceiling is still 4,096;
- the reconciliation envelope still carries all three fields;
- the blind payload still contains no preference or attributed-prior span on the existing strip fixtures;
- the full deliberation regression suite.

The evidentiary property in real use — that positions still commit and still carry material reasons — can only be confirmed on subsequent genuine enforceable turns, by their recorded lengths and reconciliation outcomes. It cannot be manufactured.

**Expected benefit:** capping visible JSON near 800 characters would have removed ≈424, 205, 576 and 31 output tokens from the four partner blind calls: ≈$0.0106, $0.0051, $0.0144 and $0.0008, **mean ≈$0.0077 per blind call, ≈$0.0018 per genuine turn.** Latency saving is ≈0–15 s per blind call on the long cases and near zero on the most recent one. Hidden reasoning (≈400 tokens on the most recent call) is untouched by the instruction and is governed by effort, which this pass does not change. **Low value; safe.**

## 5. Persona size and cost

| Revision | Characters | Tokens | Chars/token | Basis |
|---|---|---|---|---|
| v1.2 (rev 1) | 17,999 | not measured | — | no partner call under it |
| v1.3 (rev 2) | 21,722 | not measured | — | active 9 Sep 15:01–18:19, no recorded partner call |
| v1.4 (rev 3) | 18,394 | **5,746** | 3.201 | recorded cache write on first turns |
| v1.5 (rev 4) | 20,561 | **6,391** | 3.217 | recorded |
| v1.6 (rev 5) | 20,663 | ≈6,423 | — | active 17 minutes, no partner call; estimated |
| v1.7 (rev 6) | 20,580 | **6,396** | 3.218 | recorded |
| v1.8 (rev 7) | 22,713 | **≈6,995 (±10)** | ≈3.247 | derived; see below |

**Derivation of v1.8.** The blind request is persona + the 265-token structured-output system text (constant: blind prefix − persona prefix = 265 under v1.4 and v1.7) + instruction + question. A linear fit of the three recorded blind uncached counts (533 at 1,269 question characters, 310 at 465, 285 at 361) gives instruction ≈186–198 tokens and ≈0.24–0.27 tokens per question character. With the 73-character question: 7,471 − 265 − (205…217) = **6,989–7,001**. It is not a recorded figure; no persona-only count exists for v1.8.

**Growth v1.4 → v1.8:** +4,319 characters (+23.5%), ≈+1,249 tokens (+21.7%). Incremental cost per partner call: +$0.012490 on a cold one-hour write, +$0.000625 on a warm read, +$0.006245 uncached in a blind call.

**v1.8 in the Hardmarch exchange:** cold write ≈$0.069950; warm it would have been ≈$0.003498; in the blind call, uncached, ≈$0.034975.

**Monthly estimate at observed genuine volume.** Assumptions, explicit:

- *Volume:* 17 genuine turns in 3.354 days (10 Sep 10:49 → 13 Sep 19:18) ≈ 5.1 turns/day ≈ **152 turns per 30 days**.
- *Mix, as observed:* 7 of 17 conversation calls wrote the persona cold and 10 read it; 4 of 17 turns made a blind call.
- *Spend basis:* current persona size and rates; the observed genuine spend rate holds.

| Quantity | Observed (3.354 days) | Per 30 days |
|---|---|---|
| Persona portion of genuine conversation calls | $0.4641 | ≈$4.15 |
| Persona portion of blind calls | $0.2139 | ≈$1.91 |
| **Persona-related total** | **$0.6780** | **≈$6.06** (≈$0.040 per turn) |
| Increment from growth v1.4 → v1.8 | ≈$0.0070 per turn | ≈$1.06 |
| All genuine turn spend (partner + structured, approx.) | ≈$1.82 | ≈$16.3 |

The persona is ≈37% of genuine spend.

## 6. Prompt-cache economics at observed use

A simulation of every recorded conversation call under three cache policies reproduces the recorded one-hour cost to the cent ($1.913194 simulated against $1.913193 recorded), so the model is sound:

| Policy | All 28 calls | 17 genuine calls |
|---|---|---|
| no caching | $2.010780 | $1.356715 |
| 5-minute cache | $1.870098 | $1.383756 |
| **1-hour cache (current)** | **$1.913193** | **$1.334347** |

On genuine use, one-hour caching saves **1.6%** against no caching, and a 5-minute cache would cost more. Genuine use is bursty sessions separated by hours: the first turn of each session pays the 2× write, and only sessions with several turns recover it. **The cache lifetime is not a lever. The write premium on cold starts is structural on this provider.** Whether another provider's caching carries a write premium is migration evidence (§10).

## 7. Cost levers, ranked by likely impact (genuine evidence)

1. **Final-response output, especially hidden reasoning.** Genuine conversation output 18,510 tokens = $0.463 (35% of genuine conversation spend). Visible prose ≈31,258 characters ≈7,400–8,700 tokens, so hidden reasoning is ≈9,800–11,100 tokens, ≈$0.25–0.28. It is governed by effort and model; not changed here.
2. **Cold prefix writes of persona and history.** 7 persona writes in 17 genuine calls, ≈$0.064–0.070 each, plus history on resumption ($0.034 on Hardmarch). Structural at current use (§6); the provider comparison decides it.
3. **The blind stage on enforceable turns.** $0.054–0.104 each: persona duplicated uncached (≈$0.035 now), output $0.013–0.036.
4. **Persona size.** ≈$0.040 per turn, of which the growth since v1.4 is ≈$0.007.
5. **Strip on consequential turns.** $0.0036 warm to $0.0143 cold (a 1,921-token instruction write each cold hour).
6. **Fixed envelope notes in the uncached tail.** The state note is 1,247 characters and the reconciliation note and contract 1,908, after the breakpoint: ≈$0.002–0.004 per turn.
7. **Classification.** ≈$0.0009 per turn.

## 8. Latency levers, ranked

1. **Final response time to first visible token.** Recorded on 13 September turns 3, 5 and 7 at 14.71, 23.91 and 12.74 s — hidden reasoning before the first text. Not recorded for Hardmarch, whose final call took 49.9 s in total with 2,962 output tokens.
2. **The serial blind position** on enforceable turns: 10.4–43.9 s, output length including thinking.
3. **Final response generation** once the first token has arrived, 11.3–17.8 s on recorded turns. Visible length is not being changed.
4. **Strip** on every consequential turn: 2.6–6.3 s.
5. **Classification** on every turn: 1.2–1.7 s. Governed by the fifty-label ruling; `classification_labels` holds 0 rows today.
6. Orchestration: 0.03–0.12 s. Negligible.

Hardmarch: 19.445 s before the final call (28%), 49.911 s final call (72%), 69.366 s server total. Client receipt, render and paint are not persisted.

## 9. Premium-context duplication between blind and final stages

| Material | Blind call | Final call | Duplicated? |
|---|---|---|---|
| persona | ≈6,995 tokens, uncached | ≈6,995, cached (written cold) | **yes: the whole persona, ≈$0.035 per blind call** |
| structured-output system text | 265 | — | no; this is what prevents a shared prefix |
| retained history | none | ≈3,377 | no |
| turn material | the stripped remainder (73 characters) | the full message (364), plus the blind position inside the reconciliation envelope | the remainder is a subset; the position is carried once, as evidence |
| instructions | blind instruction ≈190 | record-state and reconciliation notes | no |

**Essential to the independence property:** the persona in the blind call (Val's own position must be formed by Val, whole-persona rule); the stripped question and the absence of history and influence; the recorded position in the final call.

**Possibly compactable without weakening it:** the persona is billed twice only because the provider renders the output-format text inside the cached prefix. A prefix shared by both calls — only possible through a different enforcement of the blind output contract, which the 13 September ruling forbids removing — would save ≈$0.0315 per blind call, warm or cold. Nothing else is duplicated at material size.

## 10. Where each optimization belongs

**Val Core, whatever the provider:**
- exchange identity on every reservation and call;
- persisted time to first visible token and visible-output size per call, so hidden reasoning is measured rather than inferred;
- the blind instruction bound (§4);
- keeping fixed notes out of the uncached tail, if an ordering ruling ever permits;
- the exchange envelope (§11).

**OpenAI migration and qualification evidence:**
- partner-quality reasoning economics at the needed effort (lever 1);
- whether prefix caching carries a write premium and how it behaves on Val's persona-plus-history shape, cold and warm (lever 2);
- real time to first token (latency lever 1);
- whether a blind-position output contract can share a cached prefix with the response;
- Sol's partner qualification, and whether escalation to Astra is ever selected before the main response rather than after it.

None of these may be assumed from the Anthropic figures.

## 11. The exchange-wide envelope

**Supportable, with one gap.** `DatabaseLedger.reserve` already sums commitments, decides and inserts under one advisory lock, before the provider is contacted; reservations settle at actual cost; retries and escalations already reserve separately. Cold cost is already included: `maximum_cost` assumes a miss at the write rate.

**The gap: no durable exchange identity.**
- Classification, strip and blind-position `model_calls` rows carry no `conversation_id` or `message_id`. Hardmarch was reassembled through `classifications.model_call_ids`, `blind_positions.model_call_id` and reservation timing.
- The strip has no durable link at all apart from timing.
- `budget_reservations` carries none.

**Smallest seam:**
1. Carry the existing `TurnReference` (conversation, user message) on every `GatewayRequest` made for an exchange.
2. Have `BudgetLedger.reserve` accept it.
3. Store it on `budget_reservations`: an additive, nullable column, not a core table.
4. Inside the existing locked transaction, also sum that exchange's settled and outstanding reservations plus the new maximum against an exchange envelope, returning a distinct refusal that requires owner authorisation rather than a silent reroute.

**Threshold arithmetic (no threshold chosen):** because calls are serial, earlier calls are settled at actual cost when the next reserves. At the Hardmarch final reservation the exchange held $0.068742 settled plus a $0.495650 maximum = **$0.564392 at admission** against **$0.255322 actual**. An envelope must be set against bounds, not against typical actuals.

## 12. Recommendation — the next implementation pass, ranked

No Val Core change available today yields a large, safe cost reduction without touching effort, model, persona or consequential doctrine. The two largest levers — hidden reasoning and cold-start write premiums — are provider-shaped and belong to the OpenAI measurement. The next pass should therefore make those levers measurable and bounded, and take the small safe saving:

1. **Exchange identity and per-call timing capture.**
   - `TurnReference` on every exchange request and reservation; an additive reservation column.
   - Persist time to first visible token, visible output characters and thinking presence per call.
   - No behaviour change. This is prerequisite evidence for every later decision, and the instrument the OpenAI comparison will need.
2. **The exchange envelope, disabled by default.** The seam in §11 with no threshold configured: sums recorded, refusal path tested, and owner authorisation wired but unreachable until a threshold is ruled.
3. **The blind instruction bound (§4).** ≈$0.008 per blind call and up to ≈15 s on long positions. Safe, small, confirmed only by subsequent genuine turns.
4. **Measurement protocol for the OpenAI partner candidate, written before any call.** Cold and warm cost on Val's real request shape; hidden-reasoning share; time to first token; the blind contract's cache interaction; with a cost figure put before Lord Armand first.

Not recommended: changing the cache lifetime (§6); lowering the blind ceiling; any narrowing of consequentialness; any classifier replacement before fifty labels; any persona trimming.

**Current evidence on what is achievable.**
- An ordinary warm turn on the current route already costs $0.007–0.084; one warm turn carrying 20,000 tokens of recalled material reached $0.116.
- A cold first turn costs $0.06–0.19, depending on history and recall.
- An enforceable consequential turn costs ≈$0.16 warm (the 13 September 12:17 exchange re-priced under the current uncached blind rule: $0.159114) to $0.26 cold.
- "Cents rather than tens of cents" is already true of warm ordinary turns. It is not true of cold starts or enforceable consequential turns on this provider, and Val Core alone cannot make it so without lowering the floor.
