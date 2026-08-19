# 04 — Layer 0

**Status:** Governing on the first work packages.
**Owns:** Layer 0 scope, schema, acceptance criteria, the gate.
**Does not own:** why any of it is shaped this way — see `01-architecture.md`.

**Estimate:** 2–3 weeks. **Machine:** the existing MacBook Pro. **Credentials:** model providers and backup storage only.

---

## 1. What Layer 0 is for

*Val exists, remembers, and is useful across projects.*

Layer 0 delivers a text conversation with a persistent, project-aware assistant who has her character from the first exchange. That is the visible part, and it is the smaller part.

**The value of Layer 0 is almost entirely in the capture obligations being correct from the first commit.** Execution history, deliberation records, and per-call cost attribution feed machinery that does not exist until Layers 3 and 5. If they are wrong or absent now, that machinery has nothing to consume and the gap cannot be filled later. Everything else in this layer can be rewritten in an afternoon; the captured record cannot be recreated at any price.

**Scope discipline is the second requirement.** Layer 0 staying small is deliberate. The following are explicitly out, and an implementation that adds them has failed the layer regardless of how well they work: Temporal, transactional outbox, audit chain, approval flow, tools of any kind, MCP, agents or Roles, voice, avatar, local inference, the graduated budget thresholds, the reserve, the cost dashboard, lesson distillation, success models.

### 1.1 Data classification at Layer 0

Every Layer 0 conversation carries real project content. For the first project that is unreleased creative IP — **Protected** classification — and it goes to cloud providers. Invariant 17 applies from the first exchange, before any tool exists.

The full per-content classification machinery is not built here. The obligation is met structurally instead:

**Only providers declared eligible for Protected content may be configured at Layer 0.**

With no ineligible route configured, eligibility is satisfied by construction rather than by a check on every call. There is no route to which Protected content could be misdirected, because no such route exists in the system. This is cheaper than per-call classification and stricter in effect.

Two consequences follow, and both are binding:

- **Cost never selects a route at Layer 0.** With every configured route Protected-eligible, choosing among them on cost is permissible; choosing a route *because* it is cheap, from a set that includes ineligible options, is not. The set contains no ineligible options.
- **Restricted content cannot be processed at Layer 0 at all.** Credentials, financial detail, and third-party personal data route to local inference only (`01-architecture.md` §5.4), and local inference does not exist until Layer 1. Val states plainly that she cannot handle it yet. She does not route it anywhere, and she does not reclassify it downward to make it routable.

**The structural guarantee covers routing, not content.** Every configured route being Protected-eligible means Protected content cannot be *misdirected*; it says nothing about a user message that happens to contain an API key. That gap is closed by a small deterministic local preflight in `packages/policy` — see WP-0.4's criteria. The preflight reads content and blocks; it never reclassifies downward, and it never asks the receiving model whether it should receive it.

Per-content classification arrives at Layer 2, when tools begin pulling in content of mixed classification and the structural guarantee no longer holds.

---

## 2. Schema

One migration set, Alembic, from the first commit. No manual DDL at any point.

### 2.1 Core

**`projects`** — `id`, `name`, `slug`, `description`, `status`, `created_at`, `updated_at`

**`conversations`** — `id`, `project_id` (nullable — "no project" is a real, explicit state, not a null accident), `title`, `started_at`, `last_message_at`

**`messages`** — `id`, `conversation_id`, `role` (`user` | `val` | `system`), `content`, `created_at`, `sequence`

**`personas`** — `id`, `version`, `semantic_version`, `content`, `source_sha256`, `source_path`, `created_at`, `is_active`, `activated_at`, `authored_by`. Versioned from the first load. Editing the persona creates a version; it never mutates a row.

> **Clarification — 17 August 2026, Lord Armand. Recorded before WP-0.5 begins, not implemented by it.**
>
> **`personas.version` is a persistence revision, not the persona's semantic version.** It is a monotonically increasing, immutable record number — `1`, `2`, `3`, … — and it counts rows, not authorship. The authored document keeps its own label: **v1.1, v1.2, v2.0**. The two are different scales measuring different things, and the row seeded from the current persona document therefore carries persistence revision **`1`** whatever semantic label that document bears.
>
> **The persistence revision must never be presented as the persona's semantic version.** An interface showing "Persona v1" over a row seeded from v1.2 is displaying a state the record does not support (invariant 29), and the mistake is invisible until someone asks which persona was live during a conversation.
>
> **The semantic label was not storable when this was written.** §2.1's column list had no field for it, and the clarification proposed one without adding it. **Implemented by WP-0.5 on 17 August 2026** — see the amendment below.
>
> **Immutability and activation, stated exactly**, because the current wording admits two readings and only one is intended:
>
> | Property | Rule |
> |---|---|
> | Authored content | **Immutable once stored.** `content` is never updated on an existing row. |
> | Record identity | **Immutable.** `id` and `version` never change. |
> | Editing the persona | **Creates a new row** at the next revision. It never rewrites the prior one. |
> | Prior content | **Never overwritten**, and never deleted (§2.3). |
> | `is_active` | **Lifecycle state, and it may change.** It is selection, not authorship. |
> | Activating a revision | **One transaction** that deactivates the former active row and activates the new one. |
> | How many may be active | **Exactly one**, enforced by a unique partial index rather than by convention. |
> | Activation and history | Changing `is_active` **never touches authored content.** Which persona is live is a different fact from what any persona says. |
>
> The distinction is the whole point: the persona's *content* is an authored artifact and is append-only; the persona's *activation* is operational state and moves. Collapsing them gives either a persona that cannot be switched or a history that gets edited to make the current state convenient — and the second is what invariant 14 exists to prevent.

> **Amendment — 17 August 2026, Lord Armand, authorising WP-0.5.** Four columns added to `personas`, and one nullability corrected. Executive decision 2 of that date: *WP-0.5 shall store the authored Persona semantic version explicitly and separately from the integer persistence revision.*
>
> | Column | Why |
> |---|---|
> | `semantic_version` | The authored label — `1.2`, canonical and without its `v`. **NOT NULL**, where the clarification above proposed nullable: a row that cannot say which authored version it holds is exactly the ambiguity the column exists to remove, and every row is written by a seeder that knows the answer. Narrowing a proposal is permitted; widening one is not. |
> | `source_sha256` | SHA-256 of the exact bytes of the document this row was seeded from. |
> | `source_path` | Which document, **repository-relative**. An absolute path is a fact about one machine, and a record that made one authoritative would be unverifiable anywhere else. |
> | `created_at` | When the row was written — a fact `activated_at` cannot carry once activation starts moving. |
> | `activated_at` → **nullable** | NULL means *this revision has never been active*. A revision created and not yet activated previously had to carry an activation instant for an event that had not happened. |
>
> **Immutability is enforced by the database.** A `BEFORE UPDATE` trigger refuses any change to `version`, `semantic_version`, `content`, `source_sha256`, `source_path`, `created_at`, or `authored_by`. `is_active` and `activated_at` sit deliberately outside it. Service code can be bypassed by the next caller; a trigger cannot, and `personas` is the one table whose historical content the whole of Layer 5 will later read back.
>
> **The canonical reading rule, stated once because WP-0.5's two checks are only independent if it is single.** The governing document is read as raw bytes; its digest is the digest of those bytes; its content is those bytes decoded as strict UTF-8 and stored verbatim. **No normalisation is applied** — none to newlines, trailing whitespace, or Unicode form. No normalisation *is* the normalisation, and it is the strongest available choice: every alternative requires trusting that the same transformation happened in both places, and this one has nothing to get wrong.
>
> **The authored label is parsed deterministically from the document's H1 and from nowhere else.** It is never inferred and never asked of a model, which would make the record depend on the thing it exists to govern. Migration: `0005_persona_provenance`.

### 2.2 Capture

These three tables are the point of the layer.

**`model_calls`** — per-call cost attribution

| Column | Note |
|---|---|
| `id`, `created_at` | |
| `model_config_id` | The configuration, not a bare model string |
| `provider`, `model_identifier` | Denormalised deliberately — a retired config must still resolve historically |
| `tokens_in`, `tokens_out` | **Nullable since the 17 August 2026 amendment** — NULL exactly when `cost_certainty = 'unknown'` |
| `cost` | Computed at call time from the config's rates. Never recomputed later. **Nullable on the same terms.** |
| `cost_certainty` | `known` \| `unknown`. **Nullable** only on rows written before this amendment. |
| `project_id` | Nullable, matching `conversations` |
| `task_type` | Enumerated. Layer 0 values: `conversation`, `classification`, `strip`, `blind_position`, `title` |
| `conversation_id`, `message_id` | Nullable |
| `persona_id` | **WP-0.5, 17 August 2026.** Which persona revision was assembled into this call's context. Nullable: rows written before a persona existed, and paths that legitimately assemble none, are not Val utterances to attribute. |
| `latency_ms`, `provider_request_id` | |
| `status` | `ok` \| `error` \| `refused` |

`cost` is stored, not derived. Provider pricing changes, and a historical record that silently re-prices itself is not a record.

> **Amendment — 17 August 2026, Lord Armand, after external review.** A provider attempt has three accounting outcomes and only two of them are rows:
>
> | Outcome | Provider reached | Recorded |
> |---|---|---|
> | **NOT_SENT** | No | **No row at all.** Cost is definitively zero, and it was not a model call. |
> | **SENT_COST_KNOWN** | Yes | Real figures, `cost_certainty = 'known'` |
> | **SENT_COST_UNKNOWN** | Yes, or possibly | `cost_certainty = 'unknown'`, figures **NULL** |
>
> The implementation had been writing `tokens_in = 0, tokens_out = 0, cost = 0` for every failure, including failures that occurred after the request reached the provider. That is not an unknown recorded as unknown; it is a figure known to be false recorded as a fact, and it flowed into the month-to-date total the ceiling was enforced against. **A call that reached the provider consumed its input tokens whatever happened to the response.**
>
> Two check constraints make the false zero unwritable rather than merely discouraged: `known` must carry figures, and `unknown` must carry none. Rows written before this amendment keep every figure they hold and carry a NULL certainty, meaning *written before the distinction existed* — the 0002 precedent, NULL rather than a neutral value, because guessing which state an old row deserves would be inventing evidence.
>
> **The rule about errored calls and spend, stated truthfully.** A refusal and an error that reports usage count at their real cost. An error that reports no usage cannot count at its real cost because nobody knows it — so it counts against the ceiling at its **reserved maximum** (§2.5) while its `model_calls` row records the cost as unknown. The ledger is conservative about what may be gone; the call record is honest about what is known. They differ on purpose.

> **Second amendment — 17 August 2026, Lord Armand. The five superseded rows, and `model_calls_accounted`.**
>
> The amendment above stopped the false zero being *written*. It did nothing about the five already in the store: rows from 15 August 2026 carrying `tokens_in = 0, tokens_out = 0, cost = 0.000000, status = 'error'` and a NULL certainty. **They are preserved exactly as written** — invariant 14 forbids editing history to make the present tidy — but preserving them is not the same as leaving them readable. As they stand, `sum(cost)` counts them as five confirmed free calls and nothing marks them as anything else.
>
> **The rule that identifies them is exact, not heuristic.** The superseded implementation wrote `0, 0, 0` on *every* `GatewayError`, unconditionally, and real usage on every success and refusal:
>
> | Row | Means |
> |---|---|
> | `cost_certainty IS NULL` and `status = 'error'` | Cost **unknown**. The zero was fabricated. |
> | `cost_certainty IS NULL` and `status <> 'error'` | Cost **known**. Real usage was recorded. |
> | `cost_certainty IS NOT NULL` | Says what it is. |
>
> Two mechanisms apply it, and **neither adds a table or a row**:
>
> - **A check constraint bounds the legacy set permanently.** No row created from 17 August 2026 onward may leave `cost_certainty` unstated. A NULL therefore means *written before the distinction existed* and can never come to mean anything else, so the rule cannot silently widen to rows it was not written for.
> - **The view `model_calls_accounted`** projects every column of `model_calls` plus `effective_cost_certainty` (never null), `accounted_cost` (NULL when the cost is not known), and `accounting_note` (the explanation, in words, on superseded rows only). **Every query that touches money reads the view.** SQL, Python, and Layer 5 distillation therefore share one interpretation, because there is only one.
>
> **This is the one view §2 names**, and it is named for the same reason §2 names tables: so that nothing arrives unnamed. It holds no state of its own and cannot drift from the base table, because it *is* the base table read through a rule.
>
> **Both halves stay reconstructable, which is the requirement this satisfies.** `SELECT * FROM model_calls` returns the original evidence, `0.000000` still there. `SELECT * FROM model_calls_accounted` returns what it means. The correction itself is the migration — dated, attributable, in git, append-only in the way migrations are. Neither half is derived from the other's absence, and no row was mutated or deleted to produce either.

**`execution_events`** — every acceptance, rejection, revision, and correction

| Column | Note |
|---|---|
| `id`, `created_at` | |
| `project_id`, `conversation_id`, `message_id` | |
| `event_type` | `accepted` \| `rejected` \| `revision_requested` \| `corrected`. **Nullable since the 15 August 2026 amendment** — a reaction with no event is a real record. At least one of `event_type` and `reaction` must be present. |
| `subject` | What was accepted or rejected — free text at Layer 0 |
| `reason` | **The reason, in Lord Armand's words where he gave one.** Nullable, but a null reason is a defect to be surfaced, not a normal state. |
| `reason_source` | `stated` \| `inferred` \| `absent` |
| `reaction` | `negative` \| `neutral` \| `interested` \| `enthusiastic` \| `strongly_enthusiastic`. Nullable. |

> **Amendment — 15 August 2026, Lord Armand, from external architecture review.** Reaction is not intent. "He loved the idea" and "he approved the work" are different facts, and a schema that conflates them poisons Layer 5 distillation with false approvals. `reaction` is therefore recorded independently of `event_type`: a record like *reaction: strongly_enthusiastic, no acceptance event* is representable (`event_type` null) and queryable. A reaction is **never inferred from wording alone**, and **enthusiasm is never evidence of approval** — the same rule appears where distillation reads this table (`02-partner-systems.md` §2.1).

`reason_source` matters more than it looks. A reason Val inferred and a reason Lord Armand stated are different evidence, and Layer 5 distillation must be able to weight them differently. Collapsing them now makes every later lesson slightly untrustworthy.

**`deliberations`** — per `02-partner-systems.md` §4.7

| Column | Note |
|---|---|
| `id`, `created_at`, `project_id`, `conversation_id`, `message_id` | |
| `position` | Val's position, formed blind |
| `confidence` | `high` \| `medium` \| `low` |
| `reasoning` | Brief |
| `stripped_content` | What the strip step removed (§3.9) |
| `ordering` | `enforced` \| `contaminated` — whether the blind position was genuinely blind |
| `user_response` | |
| `outcome` | `updated` \| `held` \| `overridden` \| `agreed_from_start` |
| `what_changed_her_mind` | Nullable; required when `outcome = updated` |
| `both_positions`, `predictions` | Nullable. Populated on compromise. **This is the seed of the prediction ledger.** |
| `classification` | `consequential` \| `uncertain` |
| `classified_by` | `automatic` \| `user` \| `val` |

### 2.3 Constraints

- Every `message` resolves to a `conversation`. Every `conversation` resolves to a `project` or explicitly to none.
- `execution_events` and `deliberations` cascade on nothing. They outlive the conversation that produced them. So do `ideas` and `idea_state_changes` (§2.4).
- No table permits hard delete at Layer 0. Corrections preserve lineage (`00-charter.md` invariant 14).

### 2.4 Ideas — amendment, 15 August 2026, Lord Armand

An idea's history cannot be reconstructed later, which is the same capture argument as §2.2. Layer 0 records it with **manual marking only** — no automatic idea detection, no classification calls. Machinery arrives with later layers.

**`ideas`** — `id`, `project_id` (nullable — same rule as everywhere), `title`, `lifecycle_state`, `created_at`, `updated_at`

**`idea_state_changes`** — `id`, `idea_id`, `from_state` (nullable — null marks creation), `to_state`, `changed_at`. Lineage is append-only: state history is preserved, never overwritten. `ideas.lifecycle_state` duplicates the latest `to_state` for query convenience; the application keeps them consistent, and the lineage rows are the record.

`lifecycle_state` values: `mentioned` | `discussed` | `researching` | `prototyped` | `approved` | `implemented` | `superseded` | `rejected` | `abandoned`.

Two rules, binding on every writer and on Layer 5 distillation:

- **`implemented` is never inferred from discussion of how something might be built.**
- **`approved` is never inferred from enthusiasm.**

### 2.5 Budget reservations — amendment, 17 August 2026, Lord Armand

Enforcing the ceiling against the call being proposed rather than against history (`01-architecture.md` §5.7 as amended) requires knowing what is already claimed but not yet settled. That is a fact about the house rather than about a process: `api` and `worker` share one gateway implementation and not one address space, and two counters would each observe the same headroom and together spend it. **PostgreSQL is the only place that can answer for both**, so this is a table.

**`budget_reservations`** — `id`, `created_at`, `updated_at`, `state`, `model_config_id`, `slug`, `provider`, `model_identifier`, `task_type`, `project_id` (nullable — same rule as everywhere), `max_cost`, `settled_cost` (nullable), `cost_certainty` (nullable), `model_call_id` (nullable), `resolution` (nullable)

`state` values: `reserved` | `settled` | `released` | `expired`.

| State | Means | Counts against the ceiling |
|---|---|---|
| `reserved` | Admitted; the provider is being contacted | Yes, at `max_cost` |
| `settled` | The attempt finished | Yes, at `settled_cost` |
| `released` | No provider request occurred | No |
| `expired` | The process died holding it | **Yes, at `max_cost`** |

Four rules, binding:

- **Admission is atomic.** The sum, the decision, and the insert happen in one transaction under a lock, so no second caller can slip between the sum and the insert. A check-then-act guard leaves exactly that window open, and two calls through it breach the ceiling by the size of one call.
- **`expired` still counts.** A reservation whose process vanished may or may not have reached the provider, and nothing on this machine can establish which. Freeing it would treat an unknown consequential outcome as a successful non-event, which `00-charter.md` §4 forbids in as many words. It stays committed, it is reported in words at startup, and it falls out of the sum when the month resets — so a crash costs at most the remainder of one month and never silently widens what may be spent.
- **An unknown cost settles at the full reserved maximum.** The provider was reached and would not say what it charged; releasing the difference would treat "we cannot tell" as "nothing was spent."
- **`settled_cost` may exceed `max_cost`, and if it does the record says so.** It should never happen — the reserved figure is an arithmetic upper bound, not an estimate — but the row is written truthfully rather than clamped. A tidy number concealing a breached ceiling is worse than the breach.

No hard delete, like every other table (§2.3). A spending record that can be deleted is a spending record that will be.

**Why this is a table when the Model Configuration Registry is not.** The registry is a versioned artifact whose history belongs in git — dated, diffable, attributable, and unable to drift once deployed. A reservation is the opposite: it is mutable state that two processes must agree on *right now*, and the whole mechanism is that agreement. Neither shape fits both.

---

## 3. Work packages

Each states what exists when it is done and how that is verified.

### WP-0.1 — Repository and toolchain

**Done when:** the repository structure of `01-architecture.md` §3 exists, every tool version is pinned to an explicit version resolved against current official documentation, and a clean checkout builds on a machine that has never seen the project.

**Verified by:**
- CI enforces dependency direction and fails on violation. Prove it: open a PR that references `desktop` from `policy`; CI must reject it.
  - *Amended from "imports" after PR #1: the rule governs dependency direction, not import syntax, and `policy` is Python while `desktop` is TypeScript and Rust, so no import statement in any language can express this edge.*
- No version placeholder remains anywhere. Grep for `TODO`, `TBD`, `latest`, and unpinned specifiers; result is empty.
- Clean-clone build succeeds from a documented command sequence with no undocumented step.

### WP-0.2 — Database and migrations

**Done when:** PostgreSQL with pgvector is running, §2's schema exists entirely through Alembic migrations, and the migration set applies cleanly from empty.

**Verified by:**
- `alembic upgrade head` against an empty database produces the full schema.
- `alembic downgrade base` then `upgrade head` succeeds — migrations are reversible.
- Schema matches §2 exactly. No table exists that §2 does not name.

> **Note on reversibility, 17 August 2026.** "Reversible" means the migration set has a defined and tested downgrade from an empty-database run, which CI exercises on every push. It has never meant that a downgrade may destroy capture records to succeed. Two migrations deliberately fail against real data — `0002` on reaction-only rows, `0003` on rows honestly recording an unknown cost — and that refusal is the correct behaviour, not a gap in reversibility. A rollback that erases what was captured is not a rollback.

### WP-0.3 — Backup and verified restore

**Done when:** automated encrypted off-machine backup runs daily, WAL archiving is enabled, and a restore has actually been performed and verified.

**Verified by:**
- A backup runs unattended on schedule with no human step. Confirmed by observing two consecutive days.
- Backups are encrypted, and the key is stored somewhere other than the backup location. Demonstrate by restoring on a machine holding only the backup — it must fail without the separately-held key.
- **A full restore to a scratch instance is performed and checked:** row counts match source per table, referential integrity holds, and conversation, execution history, and deliberation records are continuous with no gaps.
- Point-in-time recovery to an arbitrary timestamp within retention succeeds.

**This package does not pass on a backup that has been configured but never restored** (`00-charter.md` invariant 35).

### WP-0.4 — Model Gateway

**Done when:** all inference routes through one internal gateway, at least two providers are wired, every call is costed and attributed, and the hard stop works.

**Verified by:**
- No provider SDK is imported anywhere outside `packages/providers`. Enforced by CI.
- Two providers answer the same request through one normalized contract. Swapping the configured provider requires no change outside configuration.
- Every call writes a `model_calls` row with cost, project, and task type populated. Zero calls without a row — verified by comparing provider dashboards against the table for a day of real use.
- Provider errors, timeouts, and refusals normalize to one error contract. Test by pointing a configuration at an invalid endpoint and at a request that will be refused.
- **Hard stop:** with month-to-date cloud spend seeded above the ceiling, cloud routing stops and Val says plainly that it has. Test with a seeded value; do not wait for it to occur naturally.
- **The ceiling is enforced against the proposed call — amendment, 17 August 2026.** With spend seeded at $199.99 and a call authorised to consume more than the remaining $0.01, the provider is **not contacted**. Two simultaneous calls competing for insufficient headroom admit at most the authorised amount between them, proved against a real PostgreSQL rather than a fake. A reservation released, expired, or settled below its maximum returns exactly what it should, and an expired one returns nothing. Mechanism: `01-architecture.md` §5.7 and §2.5 above.
- **Cost accounting is truthful — amendment, 17 August 2026.** A rejection before the provider is contacted writes **no** `model_calls` row. A provider failure carrying no usage is recorded as `cost_certainty = 'unknown'` with NULL figures, never as a zero, and its reservation stays charged. §2.2 above.
- **The gateway routes — amendment, 17 August 2026.** A caller states what the content is and what the work is; the gateway selects the configuration. It selects only among configurations admitted for Layer 0 and eligible for the classification; a cheaper ineligible configuration is never selected; a fallback is used only if it independently satisfies every rule; and where no route qualifies the result is a normalized, truthful unavailability, never a downgrade. Passing an arbitrary provider and model identifier through an application path does not create a route.
- **Eligibility is enforced at startup, not at call time.** Configuring a provider not declared eligible for Protected content causes startup to fail with a clear error. Test by adding an ineligible configuration; the service must refuse to start. A check that only fires when the call is made is not the guarantee §1.1 claims.
- Restricted content is refused rather than routed. Test with content classified Restricted; Val declines and explains, and no `model_calls` row is written.
- **Restricted preflight — amendment, 15 August 2026, Lord Armand.** A deterministic local check reads the *content* before any cloud transmission, because the stated classification is only as good as the caller's knowledge. It runs before the provider is contacted, never uses the receiving model to classify, **blocks rather than downgrades**, fails closed if the check itself errors, writes no `model_calls` row (no call occurred), records the block, and explains plainly. Deliberately small: obvious credentials, keys, connection strings, government identification, and Luhn-valid payment cards. It is **not** the Layer 2 per-content classification system arriving early.

### WP-0.5 — Persona loading

**Done when:** `03-persona.md` loads whole into every context from the active `personas` row.

**Verified by two separate checks.** The persona loads from the active `personas` row, so comparing the assembled context against the source document would let a divergence between file and row read as a pass.

- **Check one:** the assembled context byte-matches the **active `personas` row**. No truncation, no summarisation.
- **Check two:** the active row byte-matches `03-persona.md` **at seed time**, verified when the row is seeded and whenever the document changes.
- Editing the persona creates a new version row and leaves the prior row intact.
- Val's register in a real exchange is recognisably that of `03-persona.md` §9. Assessed by reading, not asserted.

### WP-0.6 — Project resolution and attribution

**Done when:** every exchange is attributable to a project or explicitly to none, and resolution is deterministic.

**Verified by:**
- Resolution uses explicit names, IDs, and session state. Application code sets final scope; no model output determines it.
- Ambiguous project reference produces a question, never a guess. Test with a name matching two projects.
- No message exists with an unresolved project state — nullable means "explicitly none," and the distinction is queryable.

### WP-0.7 — Conversation loop and memory

**Done when:** a real conversation persists across a full application restart and Val recalls prior context within a project.

**Verified by:**
- Full restart of application and database mid-conversation; conversation resumes with history intact.
- Retrieval is project-scoped. A query in project A returns nothing from project B. Test with deliberately similar content in both.
- Message ordering is stable and gapless under concurrent writes.
- **Trap questions — amendment, 15 August 2026, Lord Armand.** With the database seeded with discussion and enthusiasm around a fictional decision that was never approved, "when did I approve X?" is answered with a correct negative — *"I find discussion and enthusiasm, but no approval record"* — never a confabulated date. At least three cases, each run against the real retrieval path and never against mocks: **never-approved**, **approved-then-superseded**, and **mentioned-once-then-abandoned**.

### WP-0.8 — Execution history capture

**Done when:** every acceptance, rejection, revision, and correction writes an `execution_events` row with its reason.

**Verified by:**
- Accept, reject, request revision, and correct — one of each in real use — and confirm four rows with correct types.
- A rejection without a stated reason prompts for one. Declining to give a reason records `reason_source = absent` rather than fabricating one.
- `reason_source` correctly distinguishes stated from inferred across a sample of twenty real events, checked by hand.

### WP-0.9 — Deliberation capture

**Done when:** consequential exchanges are classified per `02-partner-systems.md` §4.8, a blind position is formed before exposure to preference, and the record populates.

**Verified by:**
- **Classifier accuracy:** across fifty real exchanges hand-labelled by Lord Armand, hard exclusions are never classified consequential (zero tolerance — these are unambiguous), and disagreements on the inclusion test are reviewed and used to tune.
- **Ordering is structural, not asserted.** Log the exact payload of the blind position call and confirm by inspection that no preference-bearing content is present. A test case where preference and question are in one message must show the preference absent from the blind call and present in `stripped_content`.
- Where preference cannot be separated, `ordering = contaminated` and the record is not treated as independent.
- `outcome` populates correctly across all four values in real use.
- **The disagreement signal:** time since Val last disagreed is queryable and correct.
- **Trap questions — amendment, 15 August 2026.** The WP-0.7 trap-question suite runs against deliberation records too: enthusiasm recorded in a deliberation — or an `agreed_from_start` outcome — is never reported as an approval.

### WP-0.10 — Text interface

**Done when:** the interface supports daily use without developer tooling.

**Verified by:**
- A full day of real work conducted entirely through it, with no terminal, no database client, no log tailing.
- Project switching, conversation history, and marking an exchange consequential are all reachable from the interface.
- Nothing in the interface displays a state the database does not support (`00-charter.md` invariant 29).

---

## 4. The blind position call at Layer 0 — a deviation

`02-partner-systems.md` §4.1 routes the strip step to local inference. **Local inference does not exist until Layer 1.**

Layer 0 therefore runs the strip step on **the cheapest configured route** — which, under §1.1, is Protected-eligible by construction — and moves it to local at Layer 1. This is a routing deviation, recorded here rather than left to be discovered.

The alternative — recording positions at Layer 0 without enforcing ordering, and adding the structure at Layer 3 — was rejected. Positions recorded without the ordering guarantee are contaminated by construction, and they would seed the prediction ledger with exactly the data the mechanism exists to exclude. Months of records that cannot be trusted are worse than no records, because they look like evidence.

Cost: two extra calls on consequential exchanges only, one of them on the cheapest configured route. At Layer 0 conversation volumes this is small, and it is measurable from day one via `model_calls.task_type`.

---

## 5. The Layer 0 gate

Layer 0 is complete when all of the following hold simultaneously, demonstrated in one session:

1. A real conversation, conducted through the interface, with no developer tooling.
2. Attributed to a project, with resolution deterministic and ambiguity surfaced rather than guessed.
3. Persisted across a full restart of application and database, resuming with history intact.
4. With `execution_events` populating — acceptances, rejections, revisions, corrections, each with its reason and `reason_source`.
5. With `deliberations` populating on consequential exchanges, ordering enforced and demonstrable from the logged blind-call payload.
6. With `model_calls` populating on every call, cost and project and task type present, and zero uncosted calls.
7. **And a verified restore from backup** — restored to a scratch instance, row counts and referential integrity checked, capture tables continuous.

Points 4 through 7 are the gate. Points 1 through 3 are what makes the layer pleasant to use; 4 through 7 are what makes the next five layers possible.

**Definition of done:** every work package's acceptance criteria met and demonstrated, not asserted. Compiling is not completion. Passing unit tests alone is not completion (`00-charter.md` §4).

---

## 6. Explicitly deferred

Recorded so it is not added under pressure of seeming incomplete:

| Deferred | Arrives |
|---|---|
| Voice, avatar, local inference | Layer 1 |
| **Processing Restricted content** — requires local inference (§1.1) | Layer 1 |
| **Per-content data classification and per-call eligibility checks** — Layer 0 satisfies invariant 17 structurally (§1.1); tools break that guarantee | Layer 2 |
| MCP, Tool Registry, any tool at all | Layer 2 |
| Roles, agents, self-evaluation, standing adversary, prediction ledger scoring | Layer 3 |
| Temporal, graduated budget thresholds, reserve, cost dashboard | Layer 3 |
| Outbox, audit chain, approval flow, versioned writes, risk-tier machinery | Layer 4 |
| Lesson distillation, promotion, the books as readable artifacts, success models | Layer 5 |

Layer 0 has no actions, so it needs no protection against them. Building that protection now is the failure the whole layering exists to avoid.
