# VAL — WP-0.4 Corrective Audit

**A controlled correction of the Model Gateway, ordered by Lord Armand on 17 August 2026** after an external review found that the budget guard did not enforce what it claimed to, that cost accounting recorded a figure it could not know, and that the gateway required every caller to make its own routing decision.

**One reading rule, carried from the handoff.** *Implemented*, *verified*, and *complete* are different states and are never used interchangeably here. Nothing in this document upgrades a work package's status on the strength of code existing.

---

## A. Pre-correction commit

| | |
|---|---|
| Branch | `master` |
| Commit | `f893fa0b98f1e71f4c0df3456388db1562b252a4` |
| Short | `f893fa0` |
| Working tree | Clean |
| Tests | 213 passing |
| Checks | ruff, ruff format, mypy (32 files), `check_boundaries`, `import-linter` (3 kept / 0 broken), `check_pins`, `check_secrets` — all passing |
| WP-0.4 | IN PROGRESS / BLOCKED |

**The eight statements in Part 1 of the order were each confirmed current at this commit before anything was edited**, and none has been weakened by this work:

| Statement | Where it lives at HEAD |
|---|---|
| PostgreSQL is authoritative | `00-charter.md` invariant 12 |
| All provider inference enters through one Model Gateway | `01-architecture.md` §5.1 |
| Provider substitution alters no identity or institutional state | `00-charter.md` §1.2; `01-architecture.md` §5.1 |
| Budget ceilings are enforced before a provider call | `00-charter.md` invariant 24 |
| Protected eligibility is never overridden by cost or availability | invariant 17; `01-architecture.md` §5.4 |
| Restricted content never goes to cloud inference | `01-architecture.md` §5.4; `04-layer-0.md` §1.1 |
| Layer 0 implements no later-layer governance machinery | `01-architecture.md` §1; `04-layer-0.md` §1 |
| WP-0.4 needs two providers through one normalized contract | `04-layer-0.md` WP-0.4 |

---

## B. Post-correction commits

Three, kept separate because the decisions in them are materially distinct.

| SHA | What |
|---|---|
| `65853a1` | The corrections: budget ledger, cost certainty, router, migration `0003`, tests, CI, and the `01-architecture.md` and `04-layer-0.md` amendments they required |
| `3e96e6e` | Document decisions independent of the code: persona v1.1 → **v1.2**, persona persistence and activation semantics, backup scope, `.env.example` |
| `6472911` | This bundle |
| *(this commit)* | A CI regression of my own, caught by the first push — see §P. It cannot name its own hash; `git log` places it at the tip. |

---

## C. Files changed

### New

| Path | What it is |
|---|---|
| `packages/gateway/src/val_gateway/ledger.py` | The budget reservation ledger — the authoritative pre-call spending control |
| `packages/policy/src/val_policy/routing.py` | Candidate filtering and attempt ordering, pure |
| `packages/domain/migrations/versions/0003_budget_reservations.py` | Alembic 0003 |
| `packages/gateway/tests/gateway_fakes.py` | Stub adapter and the in-memory ledger the gateway tests drive |
| `packages/gateway/tests/conftest.py` | The scratch-database fixture for the ledger's own tests |
| `packages/gateway/tests/test_budget_ledger.py` | 15 tests against real PostgreSQL, including the concurrency races |
| `packages/gateway/tests/test_router.py` | 22 router and fallback tests |
| `packages/policy/tests/test_budget.py` | 15 tests on the budget arithmetic |
| `infrastructure/ci/generate_manifest.py` | Regenerates the reviewer manifest, uniformly |

### Modified

| Path | Change |
|---|---|
| `docs/baselines/01-architecture.md` | §5.1 routing wording; §5.2 field list; §5.2.1 seven states and the admission amendment; §5.7 the corrected budget rule and Layer 0 routing; new §9.1.1 backup scope |
| `docs/baselines/03-persona.md` | v1.1 → **v1.2**: one sentence in §2, plus a §12 change log. Nothing else. |
| `docs/baselines/04-layer-0.md` | §2.1 persona persistence and activation semantics; §2.2 cost-certainty amendment; new **§2.5** budget reservations; WP-0.2 note on reversibility; WP-0.4 three new criteria |
| `docs/BACKUP.md` | New "What this covers, and what it does not"; history corrected — see §S |
| `.env.example` | Provider-key comments corrected — see §T |
| `.github/workflows/ci.yml` | Now runs the policy and gateway suites, which it never did |
| `packages/domain/src/val_domain/gateway.py` | `CostCertainty`, `Admission`, `AdapterStatus`, `PricingFeature`, `ReasoningEffort`, `NO_ELIGIBLE_ROUTE`; `ModelConfig` extended to the §5.2 contract |
| `packages/domain/src/val_domain/registry.py` | All three entries populated against the extended contract; `fallback_for` |
| `packages/domain/src/val_domain/schema.py` | `model_calls.cost_certainty` and nullable figures with two check constraints; `budget_reservations` |
| `packages/policy/src/val_policy/budget.py` | Rewritten: the ceiling is enforced against the proposed call |
| `packages/policy/src/val_policy/restricted.py` | Coverage stated exactly; five labelled-financial detectors added |
| `packages/gateway/src/val_gateway/gateway.py` | Routing entrance, deliberate explicit entrance, reservation lifecycle, unknown-cost accounting |
| `packages/gateway/src/val_gateway/persistence.py` | Returns the row id; writes certainty; the errored-calls claim corrected |
| `packages/gateway/src/val_gateway/startup.py` | Builds the ledger; sweeps stale reservations and reports overruns as warnings |
| `packages/domain/tests/test_schema.py` | §2 transcription extended — the hand-written second copy of the specification |
| `packages/domain/tests/test_registry.py` | 9 new tests on the §5.2 contract and the §5.2.1 states |
| `packages/gateway/tests/test_gateway.py` | Rewritten against the corrected contract — see §P for the one assertion that inverted |
| `packages/gateway/tests/test_persistence.py` | Cost-certainty cases, including the two the database itself refuses |
| `packages/policy/tests/test_restricted.py` | 12 new cases: 7 detections, 5 false-positive guards, 2 documentation guards |

---

## D. Schema and migration changes

**Migration `0003_budget_reservations`**, revises `0002_reaction_and_ideas`.

### Two new enumerated types

- `model_call_cost_certainty`: `known` | `unknown`
- `budget_reservation_state`: `reserved` | `settled` | `released` | `expired`

### `model_calls` — altered

| Change | Why |
|---|---|
| `+ cost_certainty` (nullable) | The three accounting states of §G |
| `tokens_in`, `tokens_out`, `cost` → **nullable** | NULL exactly when the certainty is `unknown` |
| `+ ck_model_calls_known_cost_is_recorded` | `known` must carry figures |
| `+ ck_model_calls_unknown_cost_is_not_a_zero` | `unknown` must carry none — the false zero is **unwritable**, not merely discouraged |

### `budget_reservations` — new table

`id`, `created_at`, `updated_at`, `state`, `model_config_id`, `slug`, `provider`, `model_identifier`, `task_type`, `project_id`, `max_cost`, `settled_cost`, `cost_certainty`, `model_call_id`, `resolution`.

Five check constraints, one index on `(state, created_at)`, foreign keys to `projects` and `model_calls` both `NO ACTION`, and the same no-hard-delete trigger every Layer 0 table carries.

### Why a new table was necessary, stated plainly

`04-layer-0.md` §2 says no table exists that §2 does not name, so this required **amending a governing document**, and that is worth being explicit about rather than burying.

The alternative was considered: hold the reservation inside `model_calls` with a `pending` status. It was rejected on two grounds. It amends §2 anyway — the `status` enum is specified there — and it puts rows into the call record for calls that have not happened and may never happen, which is exactly the confusion `cost_certainty` exists to remove. Keeping `model_calls` a record of calls that *occurred*, and putting in-flight claims in their own table, is the cleaner separation.

**§2.5 was therefore added to `04-layer-0.md` naming the table.** The order was explicit — *"Use a database-backed reservation, transaction/locking strategy, or equivalent authoritative mechanism"*, with an explicit lifecycle — and an explicit current decision by Lord Armand is first in the precedence order of `00-charter.md` §9. **This is flagged for confirmation in §U** rather than treated as settled by implication.

### Effect on existing rows: none

The authoritative store held six `model_calls` rows. After migration all six are byte-for-byte as they were, with `cost_certainty` NULL — *written before this distinction existed*. That includes five error rows carrying `cost = 0.000000`, which are precisely the false zeros this correction stops being written. **They were not rewritten.** Backfilling them to `unknown` would be a judgement about what an earlier implementation could see, and correcting history to match a better present is what invariant 14 forbids. NULL rather than a neutral value is the 0002 precedent, approved as standing.

### Reversibility

`downgrade base` → `upgrade head` from an empty database: **clean**, verified. Against real data the downgrade **deliberately fails** once an unknown-cost row exists, exactly as 0002 fails on reaction-only rows — restoring `NOT NULL` on `cost` cannot succeed while a row honestly records that its cost is unknown, and this migration will not delete the row or write a zero over it to make the rollback tidy. Proof in §Q.

---

## E. Budget-control design

### The defect

```
permit the call  ⟺  month_to_date_spend < CEILING
```

This runs before the call and enforces nothing about it. At $199.99 of a $200 ceiling it admits a call authorised to spend $40, and the ceiling is discovered breached by reading the record afterwards. Invariant 24 says the ceiling is enforced before a call and never reported after; the rule satisfied the letter and inverted the point.

### The rule

```
permit the call  ⟺  committed + maximum_cost(this call) ≤ CEILING
```

**`CEILING` is $200, unchanged.** Nothing here raises it. A control that was not enforcing it now does.

### `maximum_cost` is a bound, not an estimate

Input tokens are bounded by the **UTF-8 byte length** of everything being sent, plus fixed per-message framing, capped at the configuration's context window. A byte-level tokenizer cannot emit more tokens than there are bytes, so this cannot under-reserve however the content is encoded — a characters-per-token rule of thumb is an average, and an average is the wrong instrument for a ceiling: it is right about a corpus and wrong about the one message that breaches. Output is bounded by the request's own cap, itself capped by the model's.

The bound is loose for ordinary English, roughly four times the true figure. **That is the correct direction to be wrong in**, because the difference is released the instant the call settles. Reserving too much delays work at the margin; reserving too little breaches the ceiling.

### `committed` is authoritative and lives in PostgreSQL

Four components, because all four are money that may already be gone:

1. Reservations still `reserved`, at `max_cost`
2. Reservations `settled`, at `settled_cost`
3. Reservations `expired`, at `max_cost` — §F
4. `model_calls` rows with no reservation behind them, at their recorded cost — the six rows written before this ledger existed. Excluding them would quietly forgive real spending.

### Concurrency

Admission is one transaction holding `pg_advisory_xact_lock` on a fixed key: **sum, decide, and insert are one atomic step across every process on the machine**, and the lock releases with the transaction however it ends, including a dropped connection. Two simultaneous requests serialise — the first sees the true figure and reserves, the second sees the first's reservation already counted and is refused.

The lock is held for the arithmetic and the insert only, **never across the provider call**, which would serialise every call Val makes.

None of the forbidden mechanisms is relied on. There is no process-local counter, no optimistic UI state, no in-memory mutex, and no post-return check. The in-memory `FakeLedger` exists only so the gateway's own tests can be deterministic; **every concurrency claim is tested against real PostgreSQL**, because an in-process fake is precisely the thing this design forbids relying on.

---

## F. Reservation and reconciliation semantics

| State | Means | Counts against the ceiling |
|---|---|---|
| `reserved` | Admitted; the provider is being contacted | Yes, at `max_cost` |
| `settled` | The attempt finished | Yes, at `settled_cost` |
| `released` | No provider request occurred | **No** |
| `expired` | The process died holding it | **Yes, at `max_cost`** |

**Settling below the reservation frees the difference immediately.** Nothing sweeps and nothing waits: the sum simply stops counting the maximum and starts counting the actual, at the moment the settlement commits.

**A release requires a stated reason.** `resolution` is `NOT NULL` for every state but `reserved`. A release with no reason is the shape a silent budget leak takes.

**Why `expired` still counts — the hardest call here.** A reservation whose process vanished may or may not have reached the provider, and nothing on this machine can establish which. `00-charter.md` §4 is explicit that an unknown consequential outcome is *unverified*, not *successful*. Freeing it would hand back money that may well have been spent.

Two requirements had to hold at once, and they pull opposite ways: a failed process must not permanently consume budget, and a stale reservation must not be recovered in a way that silently increases available spend. `expired` holds both. The row **leaves** `reserved`, so it stops looking like a call in flight and stops blocking reconciliation; its amount **stays committed**, so nothing is silently forgiven; it is **reported in words at startup**, so it surfaces rather than accumulating; and it falls out of the sum when the month's ceiling resets. A crash therefore costs at most the remainder of one month, and never widens what may be spent.

**Overruns.** `settled_cost > max_cost` should be impossible — the reserved figure is an arithmetic upper bound. If it happens the row is written **truthfully anyway**, both figures kept, and `ledger.overruns()` reports it at startup with the words `INVARIANT 24 VIOLATION` and the instruction *do not raise the ceiling; find why the bound failed*. Clamping the record to the reservation would hide a breached ceiling behind a tidy number, which is the one outcome worse than the breach.

---

## G. Unknown-cost semantics

A provider attempt has three accounting outcomes and **only two of them are rows**:

| Outcome | Provider reached | Recorded |
|---|---|---|
| **NOT_SENT** | No | **No row at all.** Cost is definitively zero, and this was not a model call. |
| **SENT_COST_KNOWN** | Yes | Real figures; `cost_certainty = 'known'` |
| **SENT_COST_UNKNOWN** | Yes, or possibly | `cost_certainty = 'unknown'`; `tokens_in`, `tokens_out`, `cost` all **NULL** |

There is no enum member for NOT_SENT on purpose: a row asserting a call that never happened is the error the distinction exists to prevent.

### What the old code did

Every provider failure wrote `tokens_in = 0, tokens_out = 0, cost = 0` — including failures after the request reached the provider. That is not an unknown recorded as unknown; **it is a figure known to be false recorded as a fact**, and it flowed straight into the month-to-date total the ceiling was enforced against. A call that reached the provider consumed its input tokens whatever happened to the response.

### The corrected rule, by failure class

| Failure | Provider reached | `model_calls` | Reservation |
|---|---|---|---|
| Restricted preflight (stated or detected) | No | **No row** | Never taken |
| Ineligible route, no eligible route | No | **No row** | Never taken |
| No adapter configured | No | **No row** | Never taken |
| Budget refusal | No | **No row** | Refused |
| Provider refused the content | Yes | Real usage, `known` | Settled at actual |
| Provider error carrying usage | Yes | Real usage, `known` | Settled at actual |
| Timeout, connection failure, error without usage | Yes, or possibly | **`unknown`, figures NULL** | **Settled at the full maximum** |

**The ledger and the call record disagree deliberately.** The ledger is conservative about what may be gone and charges the full reservation; the call record is honest about what is known and records NULL. Reading them as one number is the mistake; that is why `uncosted_calls_this_month()` exists alongside `month_to_date_spend()`, so no view can present the sum as complete when it is not (invariant 29).

**The false zero is unwritable.** Two check constraints in the database refuse it, independently of any code path. `test_the_database_refuses_an_unknown_cost_carrying_a_zero` proves it, as does its mirror for a `known` cost with no figure.

### The documentation claim that was wrong

`persistence.py` stated flatly that *refused and errored calls count toward spend*. True of refusals, false of errors as implemented. Corrected in place, with the by-class table above, and the module now says what `sum(cost)` does and does not include.

---

## H. Model Configuration state model

`ModelConfig` now carries the whole of `01-architecture.md` §5.2:

| Field | Kind |
|---|---|
| `provider`, `model_identifier`, `display_name` | Required |
| `context_window_tokens`, `max_output_tokens` | Required |
| `reasoning_effort` | `ReasoningEffort` — includes `NOT_APPLICABLE` |
| `temperature` | `float \| None`; None = the configuration sets none |
| `cost_per_mtok_in_usd`, `cost_per_mtok_out_usd` | Required |
| `caching`, `batch_pricing` | `PricingFeature` — `NOT_VERIFIED` \| `AVAILABLE` \| `NOT_AVAILABLE` \| `NOT_APPLICABLE` |
| `eligible_classifications` | Required |
| `known_weaknesses` | Tuple; empty means *none observed here* |
| `fallback_slug` | `str \| None`; None is an **explicit NONE** |
| `admission` | `Admission` — see §5.2.1 |
| `adapter_status` | `AdapterStatus` |
| `activated_on`, `retired_on`, `retired` | Lifecycle |
| `rates_verified_on` | Required |
| `last_live_call_on` | `date \| None` |

**Two fields are honestly empty rather than filled, and this is deliberate.**

`caching` and `batch_pricing` are `NOT_VERIFIED` on all three entries. Prompt-caching and batch availability are pricing facts, and this repository's standing rule is that pricing is read from the provider's own documentation and dated, never recalled. Layer 0 uses neither feature, so nothing depends on the value today — but a guessed value becomes load-bearing the moment something does. `NOT_VERIFIED` records that the page has not been read. **This is a small open item, listed in §U.**

`known_weaknesses` is empty on all three. Nothing has been observed in this house's own use, and the field is specified to be written from observation rather than from benchmarks or a provider's own copy. An empty tuple means *none observed here yet*, not *none exist*.

**No meaningless field was added to satisfy the checklist.** Where a provider has no such concept the record carries a typed `NOT_APPLICABLE`; where a fact has not been established it says `NOT_VERIFIED`; where a fallback does not exist it carries an explicit `None` that a test asserts is present.

---

## I. "Qualified" — the terminology fix

### The contradiction

`01-architecture.md` §5.1 said routing selects a **qualified** model configuration. §5.2.1 said qualification is the system-specific exam suite built at Layers 2–3, and that **no exam records exist**. Both were true, which left Layer 0 routing to configurations it was in no position to call qualified — and left an implementation free to use the word because the architecture did.

### The resolution

`Admission` is now a separate, explicit state on every configuration:

| State | Means |
|---|---|
| `NOT_ADMITTED` | Present in the registry; **not permitted to carry traffic** |
| `PROVISIONALLY_ADMITTED` | Permitted at Layer 0, on an eligibility ruling plus a working adapter. **The strongest standing any route holds today.** |
| `QUALIFIED` | Passed the exam suite. **Nothing holds this, and no code path sets it.** |

§5.1 now reads *select an **admitted** model configuration (§5.2.1)*. §5.2.1 lists seven states rather than six, with *provisionally admitted* between *currently enabled* and *qualified*, and a new rule beside the two that were already there: **enabled is not admitted**. Adding an entry to the registry is never, by itself, the act that opens a route.

### What this does not do

- **It does not weaken eligibility.** Admission is checked *in addition to* the classification eligibility of invariant 17, never instead of it. `test_a_cheaper_ineligible_route_is_never_a_candidate` and its companion — which proves the ineligible route was genuinely the cheapest — hold unchanged.
- **It does not change provider policy.** The 15 August rulings stand exactly as written. No provider gained or lost standing.
- **Later qualification supersedes provisional admission without changing identity.** `id` and `slug` are permanent, so a promoted route is the same route and every `model_calls` row pointing at it keeps resolving.
- **No status lets Val grant herself anything.** Admission lives in the committed registry, which she reads and does not write (invariant 2). `test_no_entry_claims_formal_qualification` fails the build if any entry ever claims the stronger word before the exam suite exists.

---

## J. Layer 0 routing algorithm

`Gateway.complete(request)` — the caller states **what the content is** and **what the work is**, and never a provider.

```
1  Restricted preflight        — content and stated classification, before anything else
2  candidates = active routes filtered by, in order:
       enabled            not retired
       admitted           PROVISIONALLY_ADMITTED or stronger
       eligible           the content's classification is in the route's set
       ready              an adapter exists and this process holds its credential
       affordable         maximum_cost fits in what is left
3  rank the survivors by cost, tie-broken on slug for stability
4  attempt order = primary, its declared fallback if it independently survives,
                   then the remainder in cost order
5  for each: reserve atomically → call → settle
       retryable failure  → next route
       non-retryable      → raise as it stands
6  nothing survived step 2 → NO_ELIGIBLE_ROUTE, saying which filter emptied the set
```

**The order of step 2 is the argument.** Cost ranks what eligibility has already admitted and never admits anything itself. Sorting before filtering would be the same code with the invariant inverted.

**Retryable** is timeout, rate limit, provider error, authentication, and budget refusal. **A content refusal is deliberately not retryable** — a provider declining to answer *is* an answer, and re-asking elsewhere until one complies is shopping for permission. `INVALID_REQUEST` is excluded for a duller reason: a malformed request is malformed everywhere.

**Budget refusal is retryable** because a cheaper eligible route may genuinely fit, and each candidate re-reserves atomically on its own account, so moving on cannot overspend — it can only find something affordable or run out.

### The explicit path is deliberate and is not a bypass

`complete_with_configuration(request, config)` exists for the strip step of `04-layer-0.md` §4, which must run on a *named* cheapest route, and for tests that pin one provider. It applies every check the routed path applies, **plus one the routed path does not need**: the configuration must be the registry's own entry for its id, identical field for field. A fabricated `ModelConfig`, or a real one with the model identifier or the eligibility set edited, is refused before any of the checks it was trying to walk around. Proof in §Q.7.

### What was not built

No prediction-ledger arbitration, no Role-specific routing, no local-inference tier, no graduated budget gradient, no dynamic provider installation. Layer 0 routing is 130 lines of pure filtering in `val_policy` plus an attempt loop in the gateway.

---

## K. Fallback behaviour

**A fallback is never inherited.** `fallback_slug` declares a *preferred successor*, and that is all it declares. When the successor is reached it must have passed **all five filters on its own account** — the implementation is literally a membership test against the already-filtered candidate set, so a fallback that is retired, unadmitted, ineligible for this content, unready, or unaffordable does not appear in the attempt order at all.

Registry declarations, each with its reasoning recorded in the entry:

| Route | Fallback | Why |
|---|---|---|
| `opus-5` | `haiku-4-5` | The cheaper Anthropic route. **Both are on the same account**, so this does not survive an account-level failure — which is exactly what the current WP-0.4 blocker is, and why it is written down. |
| `haiku-4-5` | **NONE**, explicitly | The cheapest route has nothing cheaper. Falling *up* to a frontier model on failure would spend more money in response to an outage, which is the wrong reflex. |
| `gpt-5-5` | `haiku-4-5` | A different provider, so this one does survive an Anthropic-account failure. |

Three tests guard the declarations themselves: every declared fallback resolves, no chain loops, and at least one entry records an explicit NONE so that "no fallback" is visible as a decision rather than as an omission.

---

## L. Persona revision clarification

**Recorded in `04-layer-0.md` §2.1, which owns WP-0.5 persistence. Nothing was implemented.**

`personas.version` is a **persistence revision**: monotonically increasing, immutable, counting rows — `1`, `2`, `3`, … The authored document keeps its own label — v1.1, v1.2, v2.0. Two different scales measuring two different things.

**The row seeded from the current persona therefore carries persistence revision `1`, whatever semantic label that document bears.** As of this commit the document is **v1.2** (§N), which makes the distinction concrete rather than theoretical: the first row will read `version = 1` and hold v1.2 content.

**The persistence revision must never be presented as the semantic version.** An interface showing "Persona v1" over a row seeded from v1.2 displays a state the record does not support (invariant 29), and the error is invisible until someone asks which persona was live during a given conversation.

**The semantic label is not currently storable, and this correction did not add it.** §2.1's column list has no field for it. **Proposed:** one nullable `semantic_version` text column on `personas`. Proposed, not made — it is a schema change belonging to whoever implements WP-0.5, and the order was to record the clarification rather than begin the package. Listed in §U.

---

## M. Persona activation clarification

Also recorded in `04-layer-0.md` §2.1, as a table because the previous wording admitted two readings:

| Property | Rule |
|---|---|
| Authored content | **Immutable once stored.** `content` is never updated on an existing row. |
| Record identity | **Immutable.** `id` and `version` never change. |
| Editing the persona | **Creates a new row** at the next revision; never rewrites the prior one. |
| Prior content | **Never overwritten**, never deleted (§2.3). |
| `is_active` | **Lifecycle state, and it may change.** Selection, not authorship. |
| Activating a revision | **One transaction** deactivating the former active row and activating the new one. |
| How many may be active | **Exactly one**, enforced by a unique partial index — already present in the schema, not convention. |
| Activation and history | Changing `is_active` **never touches authored content.** |

The distinction is the whole point: content is an authored artifact and is append-only; activation is operational state and moves. Collapsing them gives either a persona that cannot be switched or a history that gets edited to make the current state convenient — and the second is what invariant 14 exists to prevent.

---

## N. Books wording clarification

`03-persona.md` §2, one sentence. **The exact change:**

| | |
|---|---|
| **Was** | "When she takes on work in a domain, she reads the relevant volume in full — the accumulated reasoning in order, as it was learned." |
| **Now** | "Routine work draws on the summaries; when the work calls for that depth, she opens the relevant volume and reads it in full — the accumulated reasoning in order, as it was learned." |

**What is preserved, deliberately:** the volume is still read **in full**, still **in order**, still **as it was learned**. Assembling fragments and calling it having read the book remains the thing the design prevents — `02-partner-systems.md` §2.4 rule 4, untouched. What becomes unambiguous is *when*: deliberately, when the work calls for that depth, rather than automatically on every task that brushes the domain.

The surrounding sentences already said as much — "the full volumes she opens deliberately, when the work calls for depth" is the entry's own second clause. This makes the closing sentence agree with the opening one.

**Nothing else in the persona changed.** No reference line, no register, no boundary, no conduct rule, no voice. The document went **v1.1 → v1.2** with a §12 change log recording exactly the above, because a document loaded whole into every context is one where an ambiguity becomes an instruction.

---

## O. Backup scope clarification

**WP-0.3 is not marked complete.** See §S.

`01-architecture.md` §9.1 lists five things that must survive; only the first was covered by anything in `docs/BACKUP.md`. New **§9.1.1**, mirrored in `docs/BACKUP.md`:

| What | Protected by | Recovers to |
|---|---|---|
| PostgreSQL, in full | pgBackRest → **Backblaze B2**, encrypted, WAL-archived | Any moment inside retention |
| Governing baselines | **git → GitHub**, private remote | Any commit |
| Persona source | **git → GitHub** | Any commit |
| Migration history | **git → GitHub** | Any commit |
| Repository configuration and application source | **git → GitHub** | Any commit |
| Credentials and the repository passphrase | **Neither, deliberately** | 0600 config, and paper |

**GitHub is stated explicitly as the off-machine protection for repository-controlled material.** Private remote, off this machine, full history, every commit a restore point.

**It does not replace PostgreSQL point-in-time recovery**, and the documents now say so in as many words. The two protect disjoint things: git holds the text Val was built from, PostgreSQL holds what she has learned, decided, spent, and been told. A repository restored perfectly onto a machine with no database gives Val's character and none of her memory — every execution event, deliberation record, and cost attribution the layer exists to capture is in the other column and is reconstructible from nothing.

**Repository recovery is verified by performing it**: clone the remote onto a machine that has never held the project, build from `docs/BUILD.md` with no undocumented step, and confirm `docs/baselines/` and `03-persona.md` are byte-identical to the working copy. This is the clean-clone check WP-0.1 already requires; it is now *named* as the repository's restore verification so it is not left as a build test that happens to double as one.

**No secret is committed.** `.env` is git-ignored and `git add .env` is refused; B2 credentials and the passphrase live only in the 0600 config and on paper. A repository backup carrying them would put every credential wherever the repository goes.

---

## P. Tests run, and exact results

Run at the post-correction working tree, on the real toolchain, against PostgreSQL 18 on port 5433.

| Suite | Result |
|---|---|
| `infrastructure/ci/tests` | **69 passed** |
| `packages/domain/tests` | **120 passed** |
| `packages/policy/tests` | **49 passed** |
| `packages/gateway/tests` | **72 passed** |
| **Total** | **310 passed**, 0 failed, 1 pre-existing warning |

Was 213 at `f893fa0`. **+97 tests.**

| Check | Result |
|---|---|
| `ruff check .` | **All checks passed** |
| `ruff format --check .` | **72 files already formatted** |
| `mypy` (strict) | **Success — 35 source files** |
| `check_boundaries.py` | **Dependency direction holds across 8 components** |
| `lint-imports` | **3 kept, 0 broken** |
| `check_pins.py` | **No placeholder or unpinned specifier across 111 files** |
| `check_secrets.py` | **No credential-shaped literal across 113 committable files** |
| `alembic upgrade head` from empty | **3 migrations applied** |
| `alembic downgrade base` | **3 reversed, clean** |
| `alembic upgrade head` again | **3 applied; 10 tables at head** |
| `npm run build` (TypeScript) | **built in 51 ms** |
| `cargo build --locked` (Rust) | **Finished `dev` profile** |

### New tests, by area

| Area | Count | File |
|---|---|---|
| Budget arithmetic | 15 | `packages/policy/tests/test_budget.py` |
| Budget ledger against real PostgreSQL | 15 | `packages/gateway/tests/test_budget_ledger.py` |
| Router and fallback | 22 | `packages/gateway/tests/test_router.py` |
| Restricted preflight coverage | 12 | `packages/policy/tests/test_restricted.py` |
| Configuration registry contract | 9 | `packages/domain/tests/test_registry.py` |
| Cost certainty through persistence | 6 | `packages/gateway/tests/test_persistence.py` |
| Gateway accounting and the explicit path | 18 | `packages/gateway/tests/test_gateway.py` |

### CI was not running two of these suites at all

`.github/workflows/ci.yml`'s Python job ran `pytest infrastructure/ci/tests` and nothing else. **`packages/policy/tests` and `packages/gateway/tests` were green locally and were never executed by CI.** Corrected: the Python job now runs all three non-database suites, and the database job runs `packages/gateway/tests` as well, so the write path and the ledger's concurrency tests execute against a real PostgreSQL on every push.

### A regression I introduced, and CI caught

Worth recording because it is the second half of the same lesson.

Having found that CI ran neither the policy nor the gateway suite, I added both
to the **Python service** job — which has no PostgreSQL service container.
`test_persistence.py` tests the `model_calls` write path against a real database
and has always needed one, so **seven tests failed on the first push**
(`6472911`, run `32043123796`): `7 failed, 168 passed, 15 skipped`. The
`Database and migrations` job passed all 72 gateway tests, including every
concurrency test, so the failure was the job wiring and not the work.

Fixed by the commit that carries this paragraph — the fourth in §B — by ignoring that one file in the database-less job. It is
**ignored rather than made to skip itself**: a test about the database should
fail loudly when there is none, and the `database` job runs it for real. One
ignored file rather than two named files, so a new gateway test file is picked
up automatically instead of going silently unrun — which is exactly the failure
this correction was made to fix.

The ledger's 15 concurrency tests skip themselves in that job, visibly, and are
re-run against real PostgreSQL in the `database` job.

### Tests changed, and exactly why — nothing hidden

**One assertion inverted**, and it is named here because it is the load-bearing one:

| Was | `test_just_under_the_ceiling_still_calls` — asserted that with $199.99 spent against a $200 ceiling, a call proceeds |
|---|---|
| **Now** | `test_a_call_that_fits_in_the_remainder_is_still_admitted` — seeds spend so that the *specific* call fits exactly, and asserts it proceeds |

**That assertion encoded the defect.** It asserted that historical spend below the ceiling admits a call of any size, which is precisely what the review found wrong. The corrected behaviour is proved by `test_the_ceiling_is_enforced_against_the_proposed_call_not_history`, which uses the same $199.99 seed and asserts the provider is **not** contacted. The old test was not weakened to pass — it was replaced by the two tests that together state the real rule.

**Two tests renamed with their meaning intact:**

- `test_a_provider_error_still_writes_a_row` → `test_a_provider_error_without_usage_records_unknown_not_zero`. Same guarantee — zero calls without a row — with the additional assertions that the figures are NULL.
- `test_failed_and_refused_calls_count_toward_spend` → `test_calls_with_a_known_cost_count_toward_spend`. The old name asserted something the implementation could not deliver for every error; the assertion itself is unchanged.

**Nothing was deleted, skipped, or weakened.** No assertion was relaxed to match broken behaviour. The 15 ledger tests skip when `VAL_TEST_DATABASE_URL` is unset — visibly, as skips in the run, and CI's database job sets it, so they execute on every push.

---

## Q. Adversarial proof results

All seven ran. All seven pass.

### 1. Budget boundary — provider must not be contacted

`test_the_ceiling_is_enforced_against_the_proposed_call_not_history`, `test_a_call_larger_than_the_remainder_is_refused`

Spend seeded at **$199.99**, remaining **$0.01**, proposed maximum greater than $0.01. The test first asserts its own premise — that the authorised maximum genuinely exceeds the remainder — then asserts `adapter.calls == 0`, no `model_calls` row, and `GatewayErrorKind.BUDGET_EXCEEDED`. **PASS.** The ledger-level twin fills the month to exactly one cent of headroom against a real database and asserts a two-cent request is refused while a half-cent request is still admitted.

### 2. Concurrent budget race — combined admission must not exceed authority

`test_two_simultaneous_calls_cannot_both_take_insufficient_budget`, `test_many_simultaneous_calls_never_exceed_the_ceiling`

Two threads on **separate connections**, released simultaneously by a barrier, competing for headroom that fits exactly one: **exactly one admitted, one refused**, committed total ≤ ceiling. Then eight threads competing for room for three: **exactly three admitted**. Both against real PostgreSQL — a fake could not prove this, and using one would be proving the fake. **PASS.**

### 3. Unknown-cost provider failure — no factual zero, no full restoration

`test_a_provider_error_without_usage_records_unknown_not_zero`, `test_an_unknown_cost_does_not_hand_the_reservation_back`, `test_an_unknown_cost_settles_at_the_full_reservation`, `test_the_database_refuses_an_unknown_cost_carrying_a_zero`

A failure after transmission records `cost_certainty = 'unknown'` with `cost`, `tokens_in`, `tokens_out` all NULL; the reservation settles at its **full maximum**, so committed spend is unchanged by the failure rather than reduced by it; and the database itself rejects an insert pairing `unknown` with a zero. **PASS on all four.**

### 4. Ineligible cheap route — never selected

`test_a_cheaper_ineligible_route_is_never_a_candidate`, `test_the_ineligible_route_would_have_won_on_cost_alone`

A route priced at **$0.01/Mtok** and eligible for Public only, against one at **$50.00/Mtok** eligible for Protected. Protected content selects the $50 route. The companion test proves the premise — that the ineligible route is genuinely the cheapest thing present — so the first test cannot pass by accident. **PASS.**

### 5. Unsafe fallback — must not execute

`test_an_ineligible_fallback_does_not_execute`

Primary declares `unsafe-successor` as its fallback; the successor is cheaper and is Public-only. Against Protected content the attempt order is `["primary"]` — the declared fallback **does not appear in it at all**, because it never passed the filters on its own account. **PASS.**

### 6. Restricted mislabelling — blocked before routing

`test_restricted_content_by_detection_never_reaches_route_selection`, `test_a_credential_in_protected_content_is_blocked_before_transmission`

Caller states `PROTECTED`; content carries a valid ABA routing number, and in the companion test an Anthropic-shaped key. Both blocked. `adapter.calls == 0`, no `model_calls` row, **no budget reserved**, and the block recorded through the observer. **PASS.**

### 7. Raw-model bypass — must not create a route

`test_a_fabricated_configuration_is_refused`, `test_a_widened_eligibility_set_is_refused`

A `ModelConfig` with provider `rogue` and model `anything-1` — with a matching adapter deliberately wired in, so the only thing standing between it and a call is the check itself — is refused with `NO_ELIGIBLE_ROUTE`. The subtler attempt, taking the *real* registry entry and adding Restricted to its eligibility set, is refused the same way. **PASS.**

### Two further deliberate-failure proofs from this work

| Claim | Evidence | Result |
|---|---|---|
| The downgrade refuses to destroy an unknown-cost record | Scratch database seeded with one `cost_certainty = 'unknown'` row; `alembic downgrade 0002` returned `NotNullViolation: column "cost" of relation "model_calls" contains null values`; **the row survived and the revision stayed at head** | **PASS** |
| An expired reservation is recovered without freeing budget | `expire_stale(0)` moved a `reserved` row to `expired`, reported it in words naming its id, and **committed spend was unchanged** | **PASS** |

---

## R. Remaining WP-0.4 blockers

**One, and it is not a code defect.**

> **Two providers must answer the same request through one normalized contract.** OpenAI `gpt-5.5` has: a real call on 15 August 2026, 37 tokens in / 24 out, $0.000905, `req` recorded. **Anthropic has never answered.** The key authenticates and `models.list` succeeds; completion requests return HTTP 400 *"Your credit balance is too low to access the Anthropic API"* (`req_011Ce5aYFevxhMfvsywK1gem`).

This is an account balance, not an implementation fault, and **only Lord Armand can clear it.**

**No mock was used as proof of the live criterion, and none will be.** The Anthropic adapter is exercised by unit and contract tests that do not bill; those tests prove the adapter speaks the dialect and normalizes its errors. They prove nothing about the route working, and the registry says so structurally: `last_live_call_on` is **null** on both Anthropic routes, `live_routes()` returns `{gpt-5-5}` alone, and `test_only_a_real_answer_marks_a_route_live` fails the build if that is ever quietly changed.

Downstream and equally blocked: **provider substitution by configuration alone** (needs both routes live) and **zero uncosted calls over a day of real use** (needs both, plus a day).

**WP-0.4 status: IN PROGRESS / BLOCKED.** Every code correction in this document is complete and proved; the package is not, and does not become so by their completion.

---

## S. WP-0.3 status

**BLOCKED.** One criterion outstanding — down from two.

**Newly satisfied — the scheduled-run criterion.** WP-0.3 requires *"a backup runs unattended on schedule with no human step. Confirmed by observing two consecutive days."* Verified from `pgbackrest info` against B2, not from the agent's own log:

| Run | Type | Correct? |
|---|---|---|
| **16 Aug 2026, 03:15** | full | Yes — Sunday |
| **17 Aug 2026, 03:08** | incremental | Yes — Monday |

Two scheduled runs on consecutive days, both unattended, full/incremental selection correct on both. **This criterion is now met.** The previous handoff reported only one run because only one had occurred at the time it was written.

**Still outstanding — a restore pulled back from B2.** Every restore proved so far used a **local** repository: 13 August's full restore (7/7 tables, 11/11 foreign keys, capture tables continuous), the PITR test, and both key-failure cases. Restoring from a local copy proves the encryption, the catalogue, and the data. **It does not prove that the bytes in Backblaze are retrievable and sound**, which is the one thing an off-machine backup exists to establish. Until that is done the package does not pass (`00-charter.md` invariant 35 — *a backup that has never been restored is not a backup*).

**A fourth backup was taken during this work**, on demand before applying migration `0003`, per §9.2's *"plus on demand before any schema migration"*: `20260816-031538F_20260817-095800I`, incremental, chained onto 16 August's full — a complete restore point for the pre-migration schema. B2 now holds four backups.

---

## T. Minor documentation and handoff fixes

### `.env.example` — the comment was actively wrong

It said: *"Leave a key blank to leave that provider unconfigured. A blank key is not an error."*

**That is not what happens.** `build_adapters` refuses startup for any provider the registry has an active route for and whose key is unset. The registry carries active routes on `anthropic` and `openai`, so **both keys are required and a blank one stops the service**, with a message naming the variable.

Corrected to say so, with the reason the refusal exists — running with a configured route silently missing would make *"swapping the configured provider requires no change outside configuration"* untrue in the way hardest to notice, because the fallback would quietly never be reachable. `VAL_GOOGLE_API_KEY` genuinely is optional, because no active Google route exists; the corrected text says that too, and notes that adding one would make the key required *and* subject to the paid-billing verification.

### Reviewer manifest — regenerated uniformly

The manifest listed text files with size and SHA-256 and pushed the **eighteen binary icons into a trailing section carrying size alone**. A reviewer cannot verify what has no hash, and a manifest with an unverifiable section invites the reader to assume the rest is fine — binaries being exactly where a substitution is hardest to spot by eye.

Regenerated by `infrastructure/ci/generate_manifest.py` (committed, so it is reproducible): **every git-tracked file, text and binary alike, in one table with size and SHA-256.** The file list comes from `git ls-files`, a whitelist, so `.env` cannot appear by construction.

### Handoff documents

`VAL_Engineering_State_Handoff.md`, `VAL_Test_and_Evidence_Index.md`, and `VAL_Open_Decisions.md` are updated **only where this work established new facts**, and every new row is dated 17 August 2026.

**No past evidence was rewritten as though these fixes existed earlier.** The 15 August entries still describe what was true on 15 August, including the budget guard as it then was. Where a claim made at `ccc94e3` is now superseded, the superseding row says so and names both dates rather than editing the original away.

---

## U. Executive decisions required

**Three. None blocks further work; the first is the only one with a cost attached.**

### 1. Confirm the two governing-document amendments — *confirmation, not a question*

Both were made under the explicit terms of the 17 August order, and both amend documents Lord Armand owns:

- **`04-layer-0.md` §2.5** names `budget_reservations`, a tenth table. §2 previously said no table exists that §2 does not name. The order required a database-backed reservation with an explicit lifecycle; that cannot exist without a table, and the alternative shape was rejected on the reasoning in §D.
- **`01-architecture.md` §5.7** now describes a pre-call rule enforced against the proposed call, and a router that selects on eligibility then cost. §5.7 previously described "the crudest possible guard, and nothing else."

**Recommendation: confirm both as written.** Neither adds a capability, both narrow what the system may do rather than widening it, and the graduated thresholds, the reserve, and the cost dashboard all remain deferred to Layer 3.

### 2. Whether to store the persona's semantic version — *low stakes, decide before WP-0.5*

`personas` has no field for the authored label (§L). Proposed and **not implemented**: one nullable `semantic_version` text column.

**Recommendation: add it when WP-0.5 begins.** Without it, "which authored version was active on 3 September" is answerable only by matching stored content against git history — which works, and is not a record.

### 3. Whether to verify caching and batch pricing — *low stakes, no deadline*

`caching` and `batch_pricing` are `NOT_VERIFIED` on all three registry entries (§H). Layer 0 uses neither.

**Recommendation: leave them until Layer 3**, when prompt caching becomes structurally load-bearing and the values will be read from the providers' own pricing pages and dated, in the same discipline as `rates_verified_on`. Filling them now from recollection is precisely the failure `rates_verified_on` exists to prevent.

### Carried forward, unchanged

**The Anthropic account credit** (§R) remains the only thing standing between WP-0.4 and its live acceptance criterion, and it is an action only Lord Armand can take.

---

## V. Source snapshot, and confirmation it holds no secret

**`VAL_Source_Snapshot_3e96e6e.zip`** — 131 entries, 418,919 bytes,
SHA-256 `9759187f4ee8397c5367623ddbc1ec36facb30aab5d44897309476a4770a598c`.

The `ccc94e3` snapshot was **replaced rather than kept alongside it**: a bundle
containing a snapshot that no longer matches the documents describing it is a
bundle that invites the reader to check the wrong thing. Its content is
recoverable from git at that commit if it is ever wanted.

**Confirmed: no known secret.** Built from `git ls-files` — a whitelist, so
`.env` cannot appear by construction, and its absence was verified rather than
assumed. No `node_modules`, `.venv`, `target`, `dist`, `__pycache__`, database
data, or backup material.

Scanned with a deliberately blunter matcher than the project's own. **Three
hits, each inspected by hand:**

| Hit | What it actually is |
|---|---|
| `.env.example:59` | The match runs off the end of a **blank** Anthropic key declaration and onto the name of the next variable below it. Both declarations are valueless. |
| `check_secrets.py:68` | A comment inside the scanner explaining its own rule — `password = read_password()` is given as an example of an expression it must *not* flag |
| `test_check_secrets.py:86` | A test fixture asserting the scanner does **not** fire on `api_key = read_key_from_keychain()` |

None is a literal secret.

---

## W. Status after this work

| WP | Status | Change |
|---|---|---|
| **0.1** Repository and toolchain | **COMPLETE** | Unchanged — no evidence changed |
| **0.2** Database and migrations | **COMPLETE** | Unchanged. Migration `0003` applies, reverses from empty, and refuses to destroy records; the schema test's hand-transcribed copy of §2 was extended to match the amended specification |
| **0.3** Backup and verified restore | **BLOCKED** | One criterion **newly met** (two consecutive scheduled runs); one outstanding (restore from B2) |
| **0.4** Model Gateway | **IN PROGRESS / BLOCKED** | Code corrections complete and proved. **Not COMPLETE** — the live two-provider criterion is unmet |
| **0.5** Persona loading | **NOT STARTED** | Semantics recorded (§L, §M). Nothing implemented. |
| **0.6–0.10** | **NOT STARTED** | Unchanged |

**No Layer Gate is tagged.** `04-layer-0.md` §5 requires all seven gate conditions demonstrated in one session; four of them depend on packages not started.

**Is WP-0.5 technically ready to begin?** Yes. It needs the `personas` table (migrated, empty), `03-persona.md` (stable at v1.2), and the revision and activation semantics now recorded in §2.1. It depends on neither outstanding blocker — one is an account balance, the other a restore. **It has not been begun**, as instructed.
