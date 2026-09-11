# The strip cost/latency correction — record, 10 September 2026

The record the ruling asked for: the ruling, the implementation, the route evidence, exact costs, the final configuration, CI and commit. Ruling recorded in `docs/baselines/04-layer-0.md` (WP-0.9 amendment, 10 September 2026); evidence indexed at `VAL_Test_and_Evidence_Index.md` §41; the finding it answers is `VAL_Strip_Route_Finding.md`.

## 1. The ruling, as applied

| Part | Ruled | Done |
|---|---|---|
| 1 | Option A: a `truncated` strip attempt gets no identical retry; the bounded retry stays only for a completed invalid/unparseable result; the ceiling is not raised; deterministic regression that a truncated strip causes exactly one strip provider call | Yes |
| 2 | No enforceable blind payload (truncated, invalid exhausted, failed, or valid `separable = false`) → record the strip/capture failure honestly, collapse to the ordinary partner path, **no blind-position call, no `blind_positions` row**, existing classification and strip evidence preserved, no fabricated deliberation | Yes |
| 3 | No route switch yet; S15/S16 approved as screening cases; the $1.60 matrix not spent; stage: Sonnet `medium`, Sonnet `low`, `gpt-5.6-terra` registered for evaluation only at `none` (documented exactly), `gpt-5.6-luna` at `none` in the same bounded work; GPT-5.5 only if every candidate fails; figures stated before running; a failing candidate is eliminated | Yes — every candidate failed S15 as drafted; GPT-5.5 then run and also failed |
| 4 | Designation on the full frozen v3 only; select by exact correctness, then latency, then cost; run the full suite only on the leader; stop if the estimate exceeds $1 | **Not reached** — no survivor; nothing frozen, nothing designated |
| 5 | GPT-5.5's 112/112 on v2 preserved as history; not a target; Astra not a candidate | Yes — history untouched; Astra not registered |
| 6 | Partner untouched: `opus-5-medium`, persona v1.4, response reasoning, recall, history, cache, attribution, anti-sycophancy objective | Yes — no file on the partner path changed |
| 7 | Acceptance: the deterministic tests listed; CI green; provider calls only for the bounded sequence with costs stated; record; restart only after green; stop | Tests and CI green; the "production strip configuration has passed the entire frozen v3 suite" criterion is **unmet** and cannot be met without the ruling in §4 |

## 2. The implementation

- `packages/gateway/src/val_gateway/deliberate.py` — `_strip`: a response whose `terminal` is `TRUNCATED` records state `truncated`, logs, and returns without retry; the completed-invalid retry is unchanged; `evaluation=` selects the evaluation door for the harness only. The post-strip branch: `not validation.enforceable` → log the capture failure (unless `no_preference`, which is §4.1's own collapse) → `_ordinary` → `DeliberatedTurn` with `blind=None`, `deliberation=None`, `strip_states` set. The enforced path is unchanged from the derivation onward; `Ordering.CONTAMINATED` is no longer written by the live path and stays in the domain for history.
- `packages/gateway/src/val_gateway/gateway.py` — `Gateway.evaluate_with_configuration`: refuses conversation and blind-position tasks, requests without a schema, a non-registry configuration, a retired one, any configuration not `NOT_ADMITTED`-with-no-profile, and ineligible classifications; otherwise the ordinary `_attempt` (reservation, row, settlement).
- `packages/domain/src/val_domain/registry.py` — `active()` excludes `NOT_ADMITTED`; `under_evaluation()` added; four evaluation-only entries; observed truncation recorded on `sonnet-5` and `gpt-5-5-20260423` (and GPT-5.5's catalogue status).
- `packages/domain/src/val_domain/gateway.py` — `ReasoningEffort.NONE`.
- `packages/providers/src/val_providers/openai_adapter.py` — `NONE → "none"`; `anthropic_adapter.py` and `xai_adapter.py` refuse an unmapped level before provider contact.
- Tests: `test_deliberation_machinery.py` (truncated → one call; failed → no blind; inseparable → no blind; exhausted invalid → no blind; enforceable → blind durable before response; historical contaminated rows readable), `test_strip_invariant_orchestration.py` (the same through the orchestrator, plus truncation), `test_evaluation_door.py` (new), `test_registry_evaluation.py` (new), `test_adapters.py` (effort `none` both ways). 988 tests pass locally.

## 3. Route evidence and exact costs

Full detail: `docs/reviews/qualification/strip-conformance/v3/screen-2026-09-10.md`, with per-call rows in the two JSON files and the harness beside them. Figures stated before each stage (screen: expected ≈ $0.10, maximum ≈ $0.58, hard stop $1.00; GPT-5.5: expected ≈ $0.06, maximum ≈ $0.52).

| Stage | Calls (strip rows) | Measured cost |
|---|---|---|
| Four candidates, S15/S16 × 2 | 20 | $0.1378 |
| GPT-5.5, S15/S16 × 2 | 4 | $0.4773 |
| **Total** | **24** | **$0.6150** |

Outcome: no candidate passed S15 as drafted; the failure is the ground-truth/contract conflict on "I want you to …" conduct directives (four of five identically), plus a second reading question on the quoted-Val sentence as `attributed_prior`. Terra (three `invalid`), Luna (decision-content removal) and GPT-5.5 (truncated 3 of 4, ~44 s, $0.127 a call) are eliminated on grounds independent of that conflict; Sonnet `medium` and `low` (no truncation, S16 exact 4 of 4, 6–10 s) are the only configurations whose result turns on the ruling.

## 4. Final configuration

Unchanged for the strip: `sonnet-5` (effort `high`) with `gpt-5-5-20260423` as declared fallback — both now carrying the observed truncation in `known_weaknesses`. Four candidates registered for evaluation only. Partner route unchanged (`opus-5-medium`, persona v1.4). The strip machinery now costs one call on truncation and makes no blind call without an enforceable payload.

**Returned for ruling** (nothing further spent until then): (a) are conduct directives phrased as wants preference-bearing under §4.1 and the contract's conservative rule? (b) is a verbatim quotation of Val's earlier words, offered to correct a fact, an `attributed_prior`? (c) if S15/S16 are amended under (a) and (b), does the staged screen resume on the two Sonnet candidates only?

## 5. CI and commit

- `e2fa535` — the implementation, tests, registry, evidence and documents above. CI run 34549263390 was **red on one job**: `apps/api/tests/test_service.py::test_a_contaminated_position_is_never_presented_as_independent`, which pinned the pre-ruling presentation of a contaminated blind row; the API suite had not been in the local run. No service restart on the red run.
- `01957b8` — corrects that test to the ruling (an inseparable strip → answered turn, no blind position, no deliberation, no `blind_positions` row in the conversation detail; 34 API tests, 80 infrastructure tests). **CI run 34549611128: green** (https://github.com/valarmand1-sys/VAL/actions/runs/34549611128). The service was restarted on this commit after the green run and answered its health check.

## 6. The three strip questions ruled — 11 September 2026

What the ruling asked the report to contain, in its order.

**S15 and S16 on Sonnet medium and Sonnet low (screen, two samples each).** Both 4 of 4: S15 `no_preference` with the quoted Val sentence declared as record evidence on every run; S16 exactly the two trailing preference sentences, exact residue, quotation declared. Medium 8.7–13.9 s ($0.0551); low 6.6–7.4 s ($0.0407). No truncation, no retry. Leader by exact correctness (tie), then latency: `sonnet-5-low`.

**The full frozen v4 on the winning configuration, complete suite.** `sonnet-5-low`: **134 of 136** — C1–C6, S1–S8 and S16 all 8 of 8; S15 7 of 8 (r5 retained the quotation without declaring it; no blind payload, nothing leaked or removed); S17 7 of 8 (r7 removed `“Scene 4 should be deleted because Joni has no motivation.”` alone, leaving `You said, Reconsider the scene from scratch.` — the conclusion never survived, the residue is not the exact expected one). Under the 10 September sequence the next survivor then ran: `sonnet-5-medium` **133 of 136** — C5 r4 removed `Casting says keep. I say recast.` (a third party's recommendation is retained decision content), S7 r2 the known inseparable-returned-as-no-preference finding, S17 r5 the same residue shape. Per-case tables: `strip-conformance/v4/results-2026-09-11.md`.

**The winner's latency and cost.** `sonnet-5-low` on the full suite: median 2.6 s, maximum 11.5 s (S15/S16 6–9 s; short cases 2–3 s); $0.3881 for 136 calls, mean $0.00285 a call; no truncation, no retry. For comparison `sonnet-5-medium`: median 3.1 s, maximum 14.5 s, $0.5019.

**Cost stated before running, against what was spent.**

| Stage | Stated before | Measured |
|---|---|---|
| Screen, S15/S16 × 2, medium + low (8 calls) | expected ≈ $0.10, maximum ≈ $0.35 | $0.0958 |
| Full v4, `sonnet-5-low` (136 calls) | expected ≈ $0.82 | $0.3881 |
| Full v4, `sonnet-5-medium` (136 calls) | expected ≈ $0.70 | $0.5019 |
| **Total, 11 September** | | **$0.9858** |

The full-suite estimates were high because the short v2-shape cases cost about $0.002 a call at these efforts, not the $0.0055 carried over from the `high` runs.

**The truncation guard fails closed.** `validate_strip(..., complete=False, terminal="truncated")` returns `truncated` with no residue and no spans even for a perfectly formed outcome; `_strip` records the state, makes no retry, and the orchestrator makes no blind call and writes no row (`test_the_completeness_guard_fails_closed_before_any_parse_is_trusted`, `test_a_truncated_strip_makes_exactly_one_strip_call_and_no_blind_call`, `test_a_truncated_strip_is_not_retried_and_collapses`). No live reply on 11 September was incomplete, so the guard was exercised deterministically only.

**Frozen v3 and its results are untouched.** `git status` on `strip-conformance/v3/` is clean; no file there was modified. v4 is a new directory.

**The mixed-case implementation result, and the limitation.** Implemented as a contract rule in three parts: the instruction (a quotation carrying a substantive prior conclusion is removed as an attributed prior and never reported as record evidence; where the task identifier cannot be kept without rewriting, `separable = false`); the deterministic check that a declared quotation may not overlap a removed span (`invalid` — evidence or prior, never both); and grounding, so an alleged quotation not in Val's record is `ungrounded` and never reaches a blind call. The representation gap that made this impossible — an attributed prior with no author preference was unexpressible under the 7 September shape — is closed. **The limitation, stated plainly:** whether a *grounded* quotation is record evidence or a prior conclusion is the model's judgment; no deterministic rule distinguishes "you greeted me with 'good evening'" from "you said 'delete scene 4'" by text alone. And where the identifier and the conclusion share one clause, the verbatim mechanism cannot preserve the identifier without rewriting: the frozen S17 accepts either whole-sentence removal or a valid inseparable, and on one run in eight each Sonnet effort removed the quoted clause alone and left "You said," dangling — the conclusion gone, the residue inexact. That is the limitation showing in behaviour, not a heuristic covering it.

**Designation.** Not made. The 10 September ruling designates only a configuration that passes the entire frozen suite, and the 9 September floor names exact residue on separable cases and no neutral-content removal; `sonnet-5-low` misses the first once in 136 (S17 r7) and `sonnet-5-medium` misses both. Whether the S17 residue miss is disqualifying, or is recorded as an operational finding as `sonnet-5`'s S7 finding was on 9 September, is his ruling. Recommendation: designate `sonnet-5-low` for the strip with the S17 finding on its entry — every miss is non-leaking, it is the fastest and cheapest configuration measured, and it never truncated — and remove `strip` from `sonnet-5` at `high` so routing cannot tie. Until then the strip routes are unchanged and the amended contract runs on them.

**Sequence.** The strip work is not closed and the state is not tagged; the full regression suite ran green locally (1,115) and in CI. The Vale Core refactor is not begun; no avatar or voice work.

**CI and commit.** `bf3f487` — CI run 34626010882 green (https://github.com/valarmand1-sys/VAL/actions/runs/34626010882); the service was restarted on it after the green run (12:10, 11 September 2026) and answered its health check with no warnings. The amended contract is therefore live on the unchanged strip routes.
