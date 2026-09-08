# VAL — Multi-Provider Partner-Route Report

**Date:** 7 September 2026, after the quality-floor repair (601ef5c) was deployed and demonstrated.
**Status:** Report only. Nothing is qualified, enabled, re-registered, or re-routed by this document. Every change it describes is a ruling for Lord Armand.
**Asked in:** the quality-floor ruling of 7 September 2026, §6, and the "BUILD IT" ruling of the same date.

---

## 1. Five facts about OpenAI that are not the same fact

The ruling asked for these to be kept apart. They are, and each is answered from the record rather than inferred from the others.

| Question | Answer | Where it lives |
|---|---|---|
| **Adapter support** | Implemented. `packages/providers/src/val_providers/openai_adapter.py` speaks the Responses API, sends the persona as `instructions`, sends `reasoning.effort` from the configuration, and carries strict `json_schema` structured output — the same contract the classifier, strip, and blind-position calls use. | `packages/providers` |
| **Present in the live registry** | Two entries: `gpt-5-5` (alias, retired) and `gpt-5-5-20260423` (active; `gpt-5.5-2026-04-23`; $5 in / $30 out per million; 1,050,000-token window; 128,000 max output; reasoning effort medium; long-context multipliers above 272K; explicit `fallback = NONE`; provisionally admitted since 18 August; rates verified 18 August). | `val_domain.registry` |
| **Eligible for Protected** | Yes, by the 15 August 2026 eligibility decision (no training on API content by default; 30-day abuse-monitoring window). | `01-architecture.md` §5.4 |
| **Technically eligible for the task types** | For **classification, strip, title**: yes — admitted, Protected-eligible, declares `structured`, adapter present. For **ordinary conversation and the blind position**: **no** — the router now requires `partner`, and `gpt-5-5-20260423` declares `structured` only. It is not "technically eligible but losing on cost"; it is filtered out before cost is consulted. | `val_policy.routing.candidates` |
| **Qualified for the partner profile** | **No.** Nothing has qualified it, and nothing in the record could. The ruling of 7 September declared `opus-5` partner-qualified as an implementation bridge; no other route holds the declaration. | registry entry, `capability_profiles` |

**What OpenAI has actually answered, from `model_calls` in the live store:** 21 calls in total, all between 15 and 18 August 2026 — 18 completed conversation calls on `gpt-5.5` on 18 August (the closure-pass demonstration; average latency 3,740 ms), two failed classification calls on 15 August, and one deliberate probe against a non-existent model. **No OpenAI call has been made in real use since 18 August**, none since the classifier contract was repaired on 3 September, and none under the 7 September floor. The only OpenAI call made after the repair was in the scratch demonstration: one structured classification on `gpt-5.5` (486 in / 71 out, 4,666 ms), which completed with a parseable verdict — evidence that strict-schema output works live on that adapter, and nothing more.

## 2. What qualification would require

A combination, in this order:

1. **Evidence** — see §3. This is the part that does not exist yet and cannot be produced by configuration.
2. **A ruling** recording the qualification, as the 7 September ruling did for `opus-5`.
3. **Configuration** — one change: add `CapabilityProfile.PARTNER` to `capability_profiles` on the `gpt-5-5-20260423` registry entry, with the ruling cited in the comment. No routing code changes. No policy change: `required_profile` already names `partner` for conversation and blind position, and the candidate filter already tests set membership.
4. **Adapter work** — none required by the mechanism. Two things are *unverified* rather than known-broken, because no OpenAI call has ever carried them live: a persona-bearing conversation under the current memory envelope and reconciliation envelope, and a schema-constrained blind position at the blind output cap. Both are structural properties the scratch harness can establish without manufacturing judgments.
5. **One registry value that is not about qualification but would decide every partner call the moment two routes qualify** — see §4, the tie.

## 3. The qualification standard: none exists, and what the smallest one would be

**Said plainly: there is no governing standard for admitting a configuration to the partner profile.** The baselines contain exactly one qualification concept, and it is a different one:

- `01-architecture.md` §5.2.1, amended 15 August 2026, defines **`QUALIFIED`** — the admission state above provisional admission — as passing "a system-specific exam suite run against this system's actual workload, built at Layers 2–3: identity adherence under the persona, structured-output reliability, uncertainty handling — including the trap questions of `04-layer-0.md` WP-0.7 — cost per task class, and long-conversation behaviour." **That suite does not exist**, no route holds `QUALIFIED`, and the amendment forbids any code path from setting it.
- The 7 September ruling created the `partner` profile and declared `opus-5` into it by ruling, explicitly as a bridge. It did not state a standard for the next route, and this report does not infer one from model name, price, benchmark reputation, provider, or Protected eligibility.

The two concepts must stay distinct: `QUALIFIED` is admission standing; `partner` is a capability floor. A route could in principle hold `partner` provisionally, as `opus-5` does now, long before the Layers 2–3 exam suite exists.

**Proposed minimum evidence standard, for a later ruling — not adopted here.** The smallest set that would let Lord Armand rule on a second partner route without inventing a benchmark, drawn from properties the architecture already names:

| # | Evidence | How produced | Why it is the minimum |
|---|---|---|---|
| E1 | **Register by reading.** A set of ordinary persona-bearing exchanges on the candidate route, read by Lord Armand and judged recognisably `03-persona.md` §9 — the WP-0.5 criterion, "assessed by reading, not asserted." The count is his to set; the exchanges must be real use or clearly labelled scratch, never counted as gate evidence. | Real use through the interface with the candidate temporarily the only partner route is *not* available without a ruling, so: the scratch harness, on the same prompts the current partner route has answered, read side by side. | The partner floor exists for Val's voice; nothing but reading tests that. |
| E2 | **Blind-position completeness.** On the candidate route, schema-constrained blind positions complete within the blind output cap and parse, on a small fixed set of consequential-shaped questions in the scratch store — the structural property that failed on `opus-5` today (§5). No judgments are recorded; this is machinery, not evidence of deliberation. | Scratch harness. | A partner route that cannot state a position within the cap cannot serve the consequential path at all. |
| E3 | **Reconciliation envelope discipline.** The `VAL-DELIBERATION-V1` envelope returns a checked verdict (`recorded_prior` echo, `final_position`, `changed_from_recorded_prior`) that parses under the 7 September structural check, on the same fixed set. | Scratch harness. | The deliberation row is written only from an explicit verdict. |
| E4 | **Trap questions.** The three WP-0.7 trap cases (never-approved, approved-then-superseded, mentioned-once-then-abandoned) answered with the correct negative on the candidate route, against the real retrieval path. | Existing test seeds, run against the candidate. | Already a baseline criterion; the one part of the Layers 2–3 exam that exists today. |
| E5 | **Measured cost and latency per task class** on the candidate, reported alongside the incumbent's. Reporting only; never a qualification criterion in itself (§5.5). | From `model_calls`. | So the ruling is made knowing the bill. |

Deliberately excluded: any numeric intelligence ranking, any external benchmark, any provider-published claim. The prediction ledger (`02-partner-systems.md` §4.6) is the eventual arbiter between an incumbent and a candidate; it does not exist at Layer 0, and this standard does not pretend to replace it.

## 4. The mechanism, under more than one qualified route

**Does the capability-profile mechanism support several qualified routes at once?** Yes, without change. `capability_profiles` is a set on each configuration; the filter is set membership; any number of configurations may declare `partner`. Nothing in `val_policy.routing` or `val_gateway.gateway` names a model. `test_router.py` §G asserts the current registry state (`opus-5` wins) in one line, labelled as registry state.

**Once the floor is satisfied, what orders the candidates?** In `candidates()`: admitted → eligible for the classification → satisfies the required profile → adapter present (ready) → affordable (the model-limits preflight for output cap and context window, then the budget admits the maximum cost) → then **sorted by `(cost_per_mtok_in_usd, slug)`**. So:

- Cost breaks ties among adequate routes, as the 2 September ruling intends.
- **Two factors sit before cost** and after the floor: readiness and affordability. Both remove routes; neither reorders them.
- **One factor sits after cost: the slug, alphabetically.** This is a tie-break, and it matters now. `opus-5` and `gpt-5-5-20260423` both carry **$5.00 per million input tokens**. The ordering key reads the input rate only; output rates ($25 versus $30) are not consulted. If `gpt-5-5-20260423` were declared `partner` with nothing else changed, **it would lead every partner task**, because "g" sorts before "o". That is a routing consequence the qualification ruling would have to face: either accept it, or rule that the ordering key should weigh output cost (a policy change, not a registry one), or express a preference some other declared way. This report recommends nothing; it records that the tie exists.
- After the primary is chosen, `attempt_order()` appends its **declared fallback chain**, each link re-checked against every filter including the profile. `opus-5` declares `haiku-4-5-20251001`, which now fails the profile check for partner tasks, so the partner attempt order is `[opus-5]` alone. `gpt-5-5-20260423` declares `NONE`.

**Initial selection versus mid-turn substitution — two different questions.**

- *Initial selection* happens once per consequential turn, in `select_configuration(..., task_type=CONVERSATION)`, before the blind call. With two qualified routes, they compete here and only here, on the order above.
- *Mid-turn substitution* is not a routing question and no qualification changes it. Both the blind call and the response call run through `complete_with_configuration` / `converse(configuration=...)` on the exact configuration selected, and **the pinned path has no fallback of any kind**: the code comment reads "No fallback — the turn is unanswered rather than deliberated on a silently different route." The §5.4 fallback doctrine (independent re-check of a declared successor) applies only to the unpinned `complete` path. **There is no already-ruled condition under which a second partner provider could be substituted for the response after the blind position exists.** Qualifying a second route would not create one; only a new ruling could, and this report does not propose it.

**If the selected partner route becomes unavailable after the blind position is recorded:** the response call raises, the orchestrator returns the turn **unanswered** (`unanswered_or_raise`), and the `blind_positions` row **stays** — the code's own words: "the position was formed and recorded, and the exchange going unanswered does not unhappen it." No `deliberations` row is written, because no reconciliation happened. The evidence is truthful about exactly what occurred. The user then sees the unanswered turn and can ask again; the next attempt is a new turn with its own classification and its own blind position.

## 5. What was found while demonstrating, and how it bears on this report

The demonstration of the floor (`VAL_Test_and_Evidence_Index.md` §12.14) found that on `opus-5` the schema-constrained blind position exceeded `BLIND_MAX_OUTPUT_TOKENS = 1024` and came back truncated; a fragment is not a position, so no `blind_positions` row was written and the orchestrator proceeded **as an ordinary turn**, answering without a recorded position and without a deliberation row. The cap was set when the cheapest route served the blind call. This is reported for ruling separately; it bears here in two ways: E2 above exists because of it, and any candidate route's blind-position behaviour must be measured against whatever cap is ruled, not the one that was calibrated on Haiku.

Also as asked in §4 of the finding ruling: the live deliberation rows created after the 7 September resume and before the repair are the enforced/held pair (`blind_positions` `01a07ec5-5649…`, `deliberations` `01a07ec5-7396…`) and the contaminated pair (`01a07ec5-e17c…`, `01a07ec6-1bf7…`). **Both blind calls and both response calls were served by `haiku-4-5-20251001`** (`model_calls`: two `blind_position` rows and the matching `conversation` rows on `claude-haiku-4-5-20251001`, 21:07–21:08 local). They are preserved unchanged and annotated in `04-layer-0.md` §5.

## 6. Is the partner profile a reusable class or a name for one model?

**A reusable class.** The profile is an enum value declared per configuration; the requirement is per task type; the router tests membership. The implementation does not map `partner` to `opus-5` anywhere: the registry declares it, and the one test that checks the current winner labels itself as an assertion about registry state. The smallest path by which another provider or model is admitted, **without any change to routing architecture**, is:

1. Produce the evidence in §3 (or whatever standard is ruled instead).
2. Lord Armand rules the qualification, recorded in `01-architecture.md` §5.2 alongside the 7 September ruling.
3. One registry line: add `CapabilityProfile.PARTNER` to that entry's `capability_profiles`, citing the ruling.
4. Rule the tie-break question in §4 in the same breath, because it decides which qualified route leads.
5. Update the one registry-state line in `test_router.py` §G, and record the change in the evidence index.

Nothing in `val_policy.routing`, `val_gateway.gateway`, `deliberate.py`, or the desktop changes.

---

**Recommendation:** none on qualification — the evidence does not exist and this report was asked not to create it. The two items that need a ruling before any second partner route could be safely considered are the blind output cap (§5) and the input-rate tie-break (§4).
