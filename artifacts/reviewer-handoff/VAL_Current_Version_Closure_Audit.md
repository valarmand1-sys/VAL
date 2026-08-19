# VAL — Current-Version Closure Audit

**The closure question: is any known defect in the implemented WP-0.1–WP-0.7 foundation being knowingly carried into WP-0.8?** After this pass, the answer this audit defends is **no**. Every finding supplied by review was confirmed against the source before repair; every additional finding discovered during the pass — including the ones this pass's own changes introduced — was fixed in the same package.

| | |
|---|---|
| Source commit | `05a51165ca64ea6a7775d92f78feb69fc9f66a93` |
| Branch | `closure/current-version-pass` (PR #2, **not merged**) |
| Baseline reviewed | `VAL_Source_Snapshot_e6fb16c.zip`, SHA-256 independently verified `c1139a69ff041cdaeee36de88ed067dee1bfe7fe79916c29204dd43ebd72dd1b` |
| Status | WP-0.7 **IMPLEMENTED / ACCEPTANCE BLOCKED**; WP-0.8 **NOT STARTED** |

---

## 1. Pre-work state

Recorded before anything was edited.

| | |
|---|---|
| HEAD | `6c2fdc3385b5aea8abd705931612c95fe06b67ef`, tree clean |
| Alembic (authoritative) | `0008_conversation_scope_recall` |
| `projects` / `conversations` / `messages` / `personas` | 6 / 16 / 37 / 1 |
| `model_calls` by attribution × status | resolved: 15 ok + 14 error · explicit_none: 1 ok + 1 error · legacy_unknown: 2 ok + 7 error (= 40) |
| `budget_reservations` | 34, all `settled` |
| Active persona | revision 1, semantic v1.2 |
| Registry | `opus-5`, `haiku-4-5`, `gpt-5-5` |
| CI | green at `6c2fdc3` (run 32184292822, six jobs) |

The baseline snapshot's hash matched the expected value exactly, and `git rev-parse e6fb16c` = `e6fb16c257b1b0ca2b9860c55614c6f6c87e5426`.

## 2. Governing authority

Read in order: `CLAUDE.md`, `00-charter.md`, `01-architecture.md`, `02-partner-systems.md`, `03-persona.md`, `04-layer-0.md`. Authority order applied as stated in the assignment; two explicit Lord Armand rulings (§11, §12 below) were recorded into `01-architecture.md`, which owns backup and eligibility.

---

## 3. Findings supplied by review — each confirmed, root cause, exact fix

### §2A — `Gateway.complete()` accepted hand-built conversation requests · **CONFIRMED**

A caller with a real conversation id, real user message id, matching project, and **any typed persona UUID** could invoke `complete()` directly. The provenance verifier checked message/conversation/project coherence but nothing established the persona was loaded through the WP-0.5 loader.

**Fix.** `complete()` refuses `TaskType.CONVERSATION` outright (`_refuse_masquerade`). `converse` is the only builder of conversation requests: it loads the persona itself and delegates to the private `_execute`, the single shared execution body — one copy of the guard order, because two copies is how one drifts. Additionally the verifier now checks `persona_id` **against the active `personas` row**, so even a caller reaching `_execute` directly cannot pass a typed UUID: proved by `test_a_typed_persona_uuid_is_not_enough`, which goes through the private door deliberately and is refused.

### §2B — `complete_with_configuration()` same, without the provenance guarantee · **CONFIRMED**

It never called `_refuse_incoherent_provenance` at all. **Fix:** it refuses `TaskType.CONVERSATION` before anything else. Naming a configuration is more deliberate, not more trusted.

### §3 — the conversation task type was caller-swappable · **CONFIRMED**

`converse` and `loop.send` both took `task_type: TaskType = CONVERSATION`, so a persisted Val turn could be filed as `classification` or `title`. **Fix:** the parameter is gone from both; `converse` states `CONVERSATION` itself. Old tests using the persisted loop for non-conversation shapes were moved to the generic entrance with `CLASSIFICATION` (§14 below). Proof: `test_converse_and_send_expose_no_task_type_parameter`, plus the recorded row asserting `task_type = 'conversation'`.

### §4 — provider outcomes collapsed into one boolean · **CONFIRMED, twice over**

`ProviderResult.refused: bool` could not say *truncated*, so:
- the OpenAI adapter mapped `status == "incomplete"` — which the provider's own vocabulary defines as *output stopped early* — to **refused**, while an actual refusal (a `refusal` content part inside a `completed` response) fell through as an ordinary, often empty, completed reply;
- the Anthropic adapter let `stop_reason == "max_tokens"` pass as an ordinary completed answer — **a truncated fragment persisted as Val's message, as though she finished saying it**.

**Fix.** `TerminalState` (`COMPLETE | REFUSED | TRUNCATED | UNKNOWN`) in the domain, mapped explicitly per provider from official stop semantics (§8 of this audit records sources):

| Provider signal | TerminalState |
|---|---|
| Anthropic `end_turn`, `stop_sequence` | COMPLETE |
| Anthropic `refusal` | REFUSED |
| Anthropic `max_tokens` | TRUNCATED |
| Anthropic `tool_use`, `pause_turn`, anything else | UNKNOWN — no tool is ever sent, so these cannot legitimately occur |
| OpenAI `completed` without refusal part | COMPLETE |
| OpenAI `completed` with refusal part | REFUSED (the refusal text is the text) |
| OpenAI `incomplete` / `max_output_tokens` | TRUNCATED |
| OpenAI `incomplete` / `content_filter` | REFUSED |
| OpenAI `failed` | raises the normalized provider error |
| anything else | UNKNOWN |

Consequences, proved in `test_closure_contracts.py`:
- **TRUNCATED** → the fragment is returned as evidence (`TruncatedTurn.partial_text`), the user's turn stays as asked-and-not-yet-answered, **no `val` message is written**, and the `model_calls` row records the call honestly (status ok, cost known).
- **REFUSED** → a deliberate refusal is Val's complete answer; it is persisted, the row records `refused`.
- **UNKNOWN fails closed** → the row records `error`, cost is settled honestly (known if usage was reported), and the gateway raises `INVALID_OUTPUT`. An unrecognised outcome is unverified, not successful.

### §5 — missing usage became a fabricated known $0 · **CONFIRMED**

`usage.input_tokens if usage else 0` in the OpenAI adapter; the gateway then priced 0 tokens and recorded **KNOWN $0** — the exact false factual zero the WP-0.4 doctrine exists to prevent, on exactly the calls whose cost was unknown.

**Fix.** `ProviderResult.tokens_* : int | None`; both adapters emit `None` when the provider reports no usage. The gateway records NULL figures with `UNKNOWN` certainty and settles the reservation **at its full maximum** (never released). `GatewayResponse.tokens_*`/`cost_usd` became honestly optional. Proved end-to-end: `test_missing_usage_is_recorded_unknown_not_zero`, `test_missing_usage_settles_the_reservation_at_its_maximum`. Historical rows untouched — lineage preserved.

### §6 — reservation transitions were atomic and *silent* · **CONFIRMED**

Every transition carried `where state = 'reserved'` — atomic, no race-dependent overspend — but a double settlement matched **zero rows and returned as though it had worked**. The caller believed a state the ledger did not hold (invariant 29 in accounting clothes). Two tests enshrined the silence as correct behaviour.

**Fix.** `settle` and `release` check `rowcount`; on zero they read the row's actual state and raise `InvalidReservationTransitionError` naming it (or "does not exist"). Proofs: double-settle refused with the first settlement standing to the cent; release-after-settle refused; settle-after-expire refused; unknown id refused by name; and **ten concurrent writers (half settling, half releasing, independent connections) admit exactly one winner and nine named refusals** — `test_concurrent_settle_and_release_admit_exactly_one_winner`. The two silence-enshrining tests were rewritten to assert the loud behaviour (§14).

### §7 — stale registry facts · **CONFIRMED, including the named item**

Verified against **official provider documentation only**, 18 August 2026:

| Fact | Registry before | Official | Registry after | Source |
|---|---|---|---|---|
| GPT-5.5 context window | **272,000** | **1,050,000** | 1,050,000 | `developers.openai.com/api/docs/models/gpt-5.5` |
| GPT-5.5 max output | 128,000 | 128,000 | ✓ | same |
| GPT-5.5 pricing | $5 / $30 per MTok | $5 / $30; **>272K input → 2× input, 1.5× output for the full session**; cached input $0.50 (unused) | $5 / $30 + threshold fields | same |
| Opus 5 identifier / window / output / pricing | `claude-opus-5` / 1M / 128K / $5–$25 | identical | ✓ | `platform.claude.com/docs/en/about-claude/models/overview` |
| Opus 5 reasoning | `NOT_APPLICABLE` | **`effort` supported, defaults `high` on the Claude API**; adaptive thinking bills as output within `max_tokens` | `ReasoningEffort.HIGH` | same |
| Haiku 4.5 identifier | `claude-haiku-4-5` (the **alias**) | API **ID** is `claude-haiku-4-5-20251001`; the alias is a convenience pointer | pinned dated snapshot | same |
| Haiku 4.5 window / output / pricing | 200K / 64K / $1–$5 | identical | ✓ | same |
| Haiku 4.5 thinking | — | extended thinking yes, adaptive no; not configured, not billed beyond output cap | unchanged | same |

The 272K error was exactly what the assignment suspected: **the pricing threshold mistaken for the context limit.** The threshold now lives on the registry entry (`long_context_threshold_tokens=272_000`, multipliers 2.0/1.5) — *a pricing fact in code is a pricing fact nobody re-verifies* — and one function, `effective_rates`, is read by **both** the pre-call bound and the settlement, so the estimator and the ledger cannot disagree about what a token costs. The pre-call bound uses the upper-bound input figure, which is conservative: crossing the threshold only raises the price. Proof: `test_long_context_pricing_reaches_the_bound_and_the_settlement`, `test_the_registry_context_window_is_the_window_not_the_threshold`. `rates_verified_on` advanced to 2026-08-18.

### §8 — limits enforced only by the provider, and an estimator/transmission mismatch · **CONFIRMED**

`upper_bound_output_tokens` **clamped** with `min()` for budgeting while its docstring claimed over-limit requests were "rejected outright" — a rejection that did not exist — and the adapter transmitted the **unclamped** request. Budgeting assumed a capped value; transmission requested a larger one. Nothing checked the context window locally.

**Fix.** `limit_overrun(config, parts, requested)` refuses (never clamps) when requested output exceeds the model's cap, or when the input bound plus requested output cannot fit the window — computed from `raw_input_bound`, the same uncapped byte-level figure the budget prices, factored out so enforcement and pricing share one estimate. Wired twice: as a **route-candidacy filter** (a route that cannot hold the request is not a candidate, so a bigger-windowed route can still serve it) and as the **backstop in `_attempt`** before any reservation. The false docstring is corrected. Proofs: over-cap refusal in the model's own words; an oversized payload refused with `NO_ELIGIBLE_ROUTE` and **zero adapter calls**; and `test_the_budget_and_the_adapter_agree_on_max_output` asserting the transmitted value equals the budgeted value.

### §9 — fallback NONE fell through · **CONFIRMED, with exact source cause**

`attempt_order` ended with `order.extend(config for config in ranked if config.slug not in seen)` — after the declared chain, **every remaining candidate was appended in cost order**. `fallback_slug=None` therefore meant "fall back to whatever else is ranked", observed live in the WP-0.7 acceptance logs (haiku, fallback NONE, "trying the next independently eligible route").

**Fix.** The tail extension is deleted: the order is the primary and its declared chain, full stop. Both halves proved: a declared fallback is followed; NONE does not fall through (`[entry.slug for entry in order] == ["other"]`).

**Consequent registry decision, documented rather than silent:** with NONE now honoured, haiku (the cheapest route, hence primary) having no fallback would make an Anthropic outage halt conversation entirely while an eligible OpenAI route sat unused — against *"Val degrades rather than halts"* (charter). Haiku now **declares** `gpt-5-5`, cross-provider, exactly as `gpt-5-5` already declared haiku for the mirror-image outage. Degradation survives through an authorized declaration instead of an accidental fall-through. The old "falling up costs more" comment was superseded and removed (red-team, §17).

### §10 — historical rows silently UPDATEable · **CONFIRMED** → migration `0009` (§12 below)

### §11 / §12 — rulings · **RECORDED** (§13 below)

### §13 — restore verifier insufficiency · **CONFIRMED** (§14 below)

### §14 / §15 — test quality and stale text · **CONFIRMED** (§15–16 below)

---

## 4. Additional findings discovered during the pass

| # | Finding | Where found | Fix |
|---|---|---|---|
| A1 | `test_persistence.py` "certainty required" test listed **eleven columns and supplied twelve values** — failing on argument count since `0006`, never reaching the constraint it names. The same defect class the WP-0.6 corrective round fixed in its neighbours. | §14 audit | Rewritten; asserts `ck_model_calls_certainty_required_after_the_amendment` via psycopg diagnostics |
| A2 | `test_a_hostile_persona_does_not_make_restricted_content_routable` was passing on a **TypeError** (bare `raises(Exception)` swallowed `converse`'s new required `turn`), proving nothing about Restricted | §14 audit | Supplies the turn; asserts `RESTRICTED_CONTENT` kind and zero adapter calls |
| A3 | `test_a_call_that_was_never_sent_records_no_persona` began passing on **this pass's own masquerade refusal** instead of the Restricted mechanism it names — a defect this pass introduced and caught in the same pass | §14 audit | Rerouted through `converse`; asserts the Restricted kind, zero calls, zero rows |
| A4 | Attribution-contradiction test would survive deletion of the validator it names (the provenance validator also fires on its CONVERSATION fixture) | §14 audit | Uses `CLASSIFICATION` + `match="attribution says"` — attribution is the only thing on trial |
| A5 | Registry `haiku-4-5` identifier was the movable **alias**, not the pinned snapshot | §7 verification | Pinned to `claude-haiku-4-5-20251001` |
| A6 | Opus 5 `reasoning_effort=NOT_APPLICABLE` stale — `effort` is supported and defaults high | §7 verification | Recorded `HIGH`, with the billing note |
| A7 | Haiku registry entry carried its **old "Explicit NONE" rationale above the new fallback value** — a comment contradicting the line beneath it | red-team | Comment superseded in place |
| A8 | Boundary test did not cover direct `_execute` calls or assert both public doors carry the masquerade guard | red-team | Two boundary tests added |
| A9 | Old ledger tests **enshrined the silent no-op** (§6) as correct | §14 audit | Rewritten to assert the loud refusal |

---

## 5. The final Gateway / conversation contract

```
Application conversation
    loop.send                    persists the user turn FIRST; assembles memory
      └─ Gateway.converse        loads the ACTIVE persona (WP-0.5 loader);
                                 task_type fixed = CONVERSATION;
                                 turn: TurnReference (required);
                                 builds ConversationProvenance internally
           └─ Gateway._execute   ONE body: Restricted preflight →
                                 provenance verify (message exists, is user's,
                                 belongs to conversation, scope agrees,
                                 persona = active row) →
                                 route candidacy (eligibility, readiness,
                                 limits, affordability) →
                                 reserve → adapter → record → settle
                └─ provider

Non-conversation work (classification, strip, blind_position, title)
    Gateway.complete             REFUSES TaskType.CONVERSATION → _execute
    Gateway.complete_with_configuration
                                 REFUSES TaskType.CONVERSATION; registry-identity
                                 checked; then _attempt
```

A `TaskType.CONVERSATION` provider call therefore cannot occur unless: the triggering user message is persisted; the conversation exists; the message belongs to it and is a `user` turn; project scope agrees with the conversation's stored scope; the persona named **is the active row** loaded by the canonical loader; and the context was assembled through the conversation path — because `converse` is the only code that builds such a request, both public generic doors refuse the shape, no module outside `gateway.py` names `_execute` (asserted at source level), and the verifier closes the typed-UUID case even past the private door. A gateway constructed without a verifier refuses conversation calls; the one production construction site (`startup.py`) supplies it, asserted by test.

## 6. Provider terminal-state contract

Recorded in §3/§4 above; the contract lives in `val_domain.gateway.TerminalState`, each adapter's mapping is a visible table in its module docstring with the official-doc citation, and unknown states fail closed after honest accounting. Tool/action handoff states are unreachable at Layer 0 (no tool is ever sent) and map to UNKNOWN by design.

## 7. Unknown-cost handling

`None` tokens → NULL row figures, `UNKNOWN` certainty, reservation settled at full maximum, `unaccounted_calls` still reporting the residue. Zero is written only when zero is known. The five historical superseded rows and nine legacy rows are untouched.

## 8. Budget reservation state machine — proof

States: `reserved → settled | released | expired`, one transition, guarded by `where state='reserved'` and now **loud** on the guarded path. Proofs (17 ledger tests): atomic reserve-under-advisory-lock; settle returns headroom at the real figure; unknown settles at maximum; double-settle/double-release/settle-after-expire/release-after-settle/unknown-id all refuse by name; concurrent race admits one winner; identity columns frozen by trigger (`0009`); hard delete refused (`0001`); no negative remaining budget (`remaining_usd` floor + `admits` against the proposed call).

## 9. Model-registry verification

The table in §3-§7 above, sources and date included. Caching and batch pricing remain `NOT_VERIFIED` and unused — never requested, so no billing path exists for them (unchanged 17 August decision).

## 10. Input/output limit enforcement

§3-§8 above. The mechanism: refuse-not-clamp, one shared input estimate for pricing and enforcement, per-route candidacy filtering with an in-`_attempt` backstop, and a test pinning transmitted == budgeted.

## 11. Fallback-NONE proof

§3-§9 above: the tail extension removed, both directions tested, the haiku declaration documented as a decision with its charter grounds.

## 12. Historical mutation-policy matrix — and migration `0009`

Audited first: **no application code UPDATEs any of the five frozen tables** (the only writers are INSERTs), so the freeze removed a capability nothing legitimate used.

| Table | Purpose | INSERT | UPDATE | Mutable fields | DELETE | Why |
|---|---|---|---|---|---|---|
| `projects` | current-state record | yes | yes | name, slug, description, status, updated_at | no (trigger, `0001`) | lifecycle record; identity referenced by FKs |
| `conversations` | conversation lifecycle | yes (scope required by type) | restricted | `title`, `last_message_at` only — `project_id` frozen (`0008`) | no | scope is history; labels are labels |
| `messages` | what was said | yes (one append path) | **refused (`0009`)** | none | no | a message is the record of what was said |
| `personas` | versioned identity | yes | restricted | `is_active`, `activated_at` only — authored columns frozen (`0005`) | no | editing creates a revision, never rewrites one |
| `model_calls` | call evidence | yes (`legacy_unknown` closed, `0007`) | **refused (`0009`)** | none | no | a completed call is evidence in all its columns; supersede visibly (`0004` pattern), never edit |
| `budget_reservations` | spend state machine | yes | transitions only | state, settled_cost, cost_certainty, model_call_id, resolution, updated_at — identity frozen (`0009`) | no | the machine transitions *around* the reserved facts |
| `execution_events` | append-only audit (WP-0.8) | yes (no writer yet) | **refused (`0009`)** | none | no | "audit is append-only" (charter) |
| `deliberations` | append-only capture (WP-0.9) | yes (no writer yet) | **refused (`0009`)** | none | no | same doctrine |
| `ideas` | current-state record | yes | yes | title, lifecycle_state, updated_at | no | lineage lives in `idea_state_changes` |
| `idea_state_changes` | append-only lineage | yes | **refused (`0009`)** | none | no | §2.4: history preserved, never overwritten |

**Migration `0009_evidence_is_immutable`:** one trigger function refusing UPDATE on the five frozen tables; one identity-column guard on `budget_reservations`. It **supersedes `0007`'s narrower stance** that historical `model_calls` rows stayed correctable in place — the closure ruling is that a completed call is evidence in all its columns, and the affected test was inverted with its reasoning in the docstring. Downgrade refuses whenever guarded rows exist (always, on the live store); clean from empty (CI). Applied to the authoritative store **after an encrypted backup**; row counts unchanged across it (16/37/40/34); live UPDATE attempts on `messages` and `model_calls` verified refused (rolled back). Full round trip from empty: 9 up / 9 down / 9 up; `alembic check` clean; no rewrite of `0001`–`0008`.

If WP-0.8/0.9's accepted designs need a field completed after insert (a rejection reason supplied on prompting, say), that is an explicit future migration — a visible decision, not a quiet UPDATE that was always possible. **Deferred to the owning layer.**

## 13. The two rulings, recorded

**Backup-transport eligibility (approved §11).** Recorded in `01-architecture.md` §9.2: the encrypted pgBackRest → B2 channel may carry every classification legitimately in authoritative PostgreSQL, conditional on pre-transmission encryption with verified configuration, a bucket-scoped credential, the designated repository as sole destination, and ciphertext only. Explicitly not an authorisation for arbitrary B2 uploads nor any widening of model/tool egress.

**Anthropic retention premise (approved §12).** The stale "7-day default retention" grounds in the §5.4 eligibility table are superseded. Verified 18 August 2026 against `platform.claude.com/docs/en/manage-claude/api-and-data-retention`: **conversation content is not retained by default** on the Claude API for non-Covered Models; the 30-day retention requirement attaches only to designated Covered Models (Claude Fable 5 / Claude Mythos 5), neither of which is in VAL's registry. The current verified terms are stronger than the premise they replace, so Protected eligibility stands; a Covered Model ever proposed for the registry is a **new** eligibility decision, not an inheritance. Restricted data remains prohibited regardless.

## 14. Restore-verifier hardening

`verify_restore.py` gains a fourth check: **per-table content digests** — every row rendered to text, hashed, aggregated in primary-key order (UUIDv7, deterministic on both sides) — plus the Alembic revision, compared exactly. Detects missing interior rows, substitutions, duplicates, changed identities, changed content, broken sequences, and missing migration state. No second source of truth: digests are computed from both instances at comparison time and stored nowhere.

**Proved adversarially:** a template copy of the live store with **one interior message's content substituted — counts identical, timestamp extents identical — fails verification** on the `messages` digest; the self-comparison passes on all eleven digests. The actual B2-origin restore remains the WP-0.3 blocker and is not claimed.

## 15. Test-quality audit — findings and fixes

Nine findings, all fixed, none by weakening: A1–A4 and A9 in §4 above, plus the two registry/router tests that asserted **current registry contents** rather than mechanism (rewritten to assert chain termination and both fallback directions), and the general sweep of bare `pytest.raises(Exception)` — each remaining instance now names its guard (`hard delete`, `uq_personas_single_active`, constraint names via diagnostics). The 40-writer concurrency test was re-inspected and is genuinely concurrent (barrier-released, independent engines). Coverage rose: 591 → **611** tests.

## 16. Stale comments and docstrings

Corrected: `loop.py`'s "memory as delimited data" (serialised envelope since the WP-0.7 corrective round) and its description of `exchange.py` as a boundary that "answers"; `upper_bound_output_tokens`' claim of a rejection that did not exist; the Anthropic adapter's stop-reason prose (now an explicit mapping table); the haiku fallback comment (A7); `provenance.py`'s "checking the loader against itself" waiver, superseded by the persona check it argued against. Baselines were amended only by the two approved rulings — implementation conforms to baseline, not the reverse.

## 17. Closure red-team pass — result

Performed after all repairs, structurally, against the final source: entry-point enumeration (one `converse` caller: `loop.py`; no `_execute` callers outside `gateway.py`; one production `Gateway(...)` site, with verifier), optional-guarantee sweep (missing verifier/loader ⇒ refusal, not skip), guard-order confirmation (Restricted → provenance → candidacy → reserve → transmit), provider-SDK import audit (only `val_providers`), process-local lock audit (none), deprecated-boundary audit (`exchange()` remains removed), evidence-mutation audit (no UPDATEs on frozen tables anywhere in source), model-fact audit (no pricing/limit constants outside the registry), credential sweep (clean).

**Findings: A7 and A8 (§4), both fixed and tested in this same package. No unresolved finding remains in the implemented WP-0.1–WP-0.7 surface.**

## 18. Regressions — WP-0.5 / WP-0.6 / WP-0.7

All prior suites pass unmodified in intent: persona provenance/immutability/single-active/DB-loaded/no-fallback-prompt (WP-0.5); scope parity, application-resolves, ambiguity-asks, duplicate identity, legacy_unknown closed, no project_id rewrites, status non-authority, migration guards (WP-0.6); the full WP-0.7 matrix — one durable path, forward-only switching, session/mention semantics, filter-before-rank with the adversarial stronger-match and starved-limit cases, no-project isolation both directions, persona exactly once, serialised envelope with the forged-delimiter suite, Restricted-memory preflight, budget on the final payload, 40-writer gapless concurrency, rollback no-gap, restart continuity, cross-conversation recall, provider substitution, deterministic trap-question layer.

**Prior live evidence remains valid, and no paid re-run was performed**, because the conversational outbound assembly is unchanged: same message/system construction, same envelope, same persona path, same adapter request shape. What changed is refusals of previously-permitted invalid shapes, terminal-state branching (COMPLETE flows identically), missing-usage accounting, and the haiku identifier moving from the alias to the **pinned snapshot of the same model** — none of which alters what a successful call sends or receives. The live trap questions, restart, and isolation evidence recorded in the WP-0.7 audits therefore stand.

## 19. Real-runtime smoke

Through the **production startup path** (`start(engine)` unmodified — real ledger, real persona loader, real verifier, adapters built from env keys), with stubs substituted at the provider boundary only:

```
1. production startup OK (1 warning: the known unaccounted legacy calls)
2. adapters stubbed at the provider boundary: anthropic, openai
3. persisted turn OK (disposable project 'closure-smoke')
4. active persona verified: system prompt byte-matches the active row
5. model_call provenance correct: conversation, message, persona, task type
6. both turns persisted, in order
7. adapter boundary inspected: the user turn is in the outbound payload
8. raw conversation entrance fails closed (invalid_request: goes through converse)
9. generic non-conversation gateway work still flows
```

## 20. Acceptance matrix

| | Question | Verdict | Evidence |
|---|---|---|---|
| A | Exactly one legitimate CONVERSATION provider path? | **PASS** | §5 contract; boundary tests; smoke 8–9 |
| B | Can raw Gateway API bypass active-persona loading for conversation? | **PASS** (it cannot) | masquerade refusals; verifier persona check; `test_a_typed_persona_uuid_is_not_enough` |
| C | Can incoherent conversation/message/project provenance reach a provider? | **PASS** (it cannot) | WP-0.7 corrective verifier + closure persona check, zero-adapter-call assertions |
| D | Can a caller mislabel a conversational turn? | **PASS** (no) | no `task_type` parameter; recorded row asserts `conversation` |
| E | Can incomplete/truncated/refused output become an ordinary Val reply? | **PASS** (no) | `TruncatedTurn`; UNKNOWN fails closed; refusal persisted as refusal |
| F | Can unknown usage/cost become zero? | **PASS** (no) | NULL/UNKNOWN path + maximum settlement, proved both ends |
| G | Can a reservation transition twice or after terminal state? | **PASS** (no) | loud state machine + concurrency race |
| H | Can an over-limit request be transmitted because only the provider enforces? | **PASS** (no) | `limit_overrun` filter + backstop; transmitted == budgeted |
| I | Does fallback NONE genuinely prevent automatic fallback? | **PASS** | tail extension removed; both direction tests |
| J | Can material historical evidence be silently UPDATEd contrary to doctrine? | **PASS** (no) | migration `0009`, live refusals verified |
| K | Can Project B enter Project A's retrieval or outbound context? | **PASS** (no) | WP-0.7 suite incl. adversarial cases, unchanged and green |
| L | Can no-project history cross into a Project or vice versa? | **PASS** (no) | both-direction isolation tests |
| M | Can stale session state override a resumed stored conversation? | **PASS** (no) | case D switch tests |
| N | Can historical recalled content forge current user authority? | **PASS** (no) | serialised envelope + forged-delimiter suite |
| O | Can the active Persona be bypassed or silently replaced? | **PASS** (no) | B above + WP-0.5 suite |
| P | Can a current registry fact be shown inconsistent with official docs? | **PASS** (no longer) | §9 verification table, sources dated 18 Aug 2026 |
| Q | Can the restore verifier miss an interior substitution/deletion? | **PASS** (no) | content digests; adversarial doctored-copy proof. The B2-origin restore itself stays BLOCKED (WP-0.3), as the assignment permits |
| R | Do any tests pass tautologically or on the wrong guard? | **PASS** (none known) | §15 — nine found, nine fixed; named-guard sweep |
| S | Does the production startup path pass a conversational smoke? | **PASS** | §19 |
| T | Does the final red-team review leave unresolved defects in WP-0.1–0.7? | **PASS** (none) | §17 |

## 21. Remaining known limitations

1. **WP-0.3:** the final restore has still never been pulled from B2. The verifier and architecture are ready; the act itself is the blocker.
2. **WP-0.4:** live substitution between two different providers remains unproved while the Anthropic account has no credit; the fallback now exercises the declared chain live on every real call, but only in one direction.
3. **Lexical retrieval:** a question sharing no vocabulary with the earlier conversation will not recall it (recorded WP-0.7 limit; embeddings deliberately deferred).
4. **Terminal-state mappings** are built from current official documentation; a provider adding a new stop reason lands in UNKNOWN and fails closed — safe, but it will need a mapping entry when observed.
5. **Non-conversation callers** of `complete()` receive `TerminalState` and must branch on TRUNCATED when such callers appear (WP-0.8+); the contract carries the information, the discipline is on future writers.

## 22. Legitimate future-layer deferrals

| Item | Owner |
|---|---|
| Controlled post-insert completion of `execution_events` (e.g. prompted rejection reason), if the accepted design needs it | WP-0.8, by explicit migration |
| Same for `deliberations` outcome fields | WP-0.9 |
| Semantic retrieval (four decisions recorded) | Layer 2+, `VAL_Open_Decisions.md` item 10 |
| Formal model qualification exams (`QUALIFIED` admission) | Layers 2–3 |
| Caching/batch pricing verification | when first requested (17 Aug decision unchanged) |

## 23. Test and gate results

**611 passed**, no warnings. Strict mypy over 48 source files; `ruff check` and `ruff format --check` clean (103 files); import-linter 3/3; dependency direction across 8 components; pins clean (142 files); secrets clean (147 files); `alembic check` clean; migration round trip from empty 9/9/9; authoritative store at `0009_evidence_is_immutable`, counts unchanged.

## 23b. Bundle

| | |
|---|---|
| Source commit | `05a51165ca64ea6a7775d92f78feb69fc9f66a93` |
| Snapshot | `VAL_Source_Snapshot_05a5116.zip`, **189 files** |
| SHA-256 | `cfac7c8ea74be13024adec48be1b04971f2919119902e281c6f1650cf4778156` |

Source only — `artifacts/` excluded and no prior snapshot embedded, verified
file-by-file against `git archive` of the commit: identical.

## 24. Executive decisions required

**NONE.** Both approved rulings are recorded; the haiku fallback declaration is documented as engineering-within-doctrine with its charter grounds (§3-§9) and is trivially reversible if you rule the other way.

## 25. Recommendation

**Every finding — supplied and discovered — is confirmed, fixed, and proved in this package.** The closure question ("any known defect knowingly carried into WP-0.8?") is answered **no** to the extent of this audit's evidence.

Recommended state: **WP-0.7 = IMPLEMENTED / READY FOR INDEPENDENT RE-ACCEPTANCE.** Not marked COMPLETE here — that determination is Lord Armand's, on independent review of `VAL_Source_Snapshot_05a5116.zip`. PR #2 remains open and unmerged.
