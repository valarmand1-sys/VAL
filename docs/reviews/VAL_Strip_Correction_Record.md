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

Recorded in the evidence index §41 and below on push.
