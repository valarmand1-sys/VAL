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

**`projects`** — `id`, `name`, `slug`, `description`, `status`, `created_at`, `updated_at`, `archived_at`

**`conversations`** — `id`, `project_id` (nullable — "no project" is a real, explicit state, not a null accident), `title`, `started_at`, `last_message_at`, `archived_at`

> **Amendment — 31 August 2026, Lord Armand. `archived_at` is presentation scoping and carries no evidentiary meaning.** Nullable, lifecycle-class (mutable, like `conversations.title`), on `projects` and `conversations` only. Set means exactly one thing: *hidden from the interface's default listings*. It means nothing else. **It must never be read as superseded, retracted, mistaken, or not real** — the first rows ever marked (migration `0012`: the seven demonstration projects and eighteen demonstration conversations of 15–19 August 2026) are all cited Layer 0 gate evidence, real conversations with real providers, preserved whole. Archiving changes no behavior outside listings: an archived conversation still resumes, an archived project still resolves and still scopes recall, and every capture and evidence table is untouched. Deletion remains impossible (§2.3) — archiving exists precisely because it is not deletion.
>
> **Standing rule, same date: demonstration fixtures never enter the live store again.** The August fixtures exist because the early acceptance runs deliberately ran live; that era is closed. Anything future that needs seeded data — with or without live providers — runs in a scratch database. The one exception is the Layer 0 gate's own single-session demonstration, which is real use through the interface and belongs in the live store by definition.

**`messages`** — `id`, `conversation_id`, `role` (`user` | `val` | `system`), `content`, `created_at`, `sequence`

> **Requirement — 31 August 2026, Lord Armand. Revision and retraction of his own messages. Recorded against the core loop; no work before Lord Armand authorizes it after the Layer 0 gate.**
>
> Lord Armand must be able to correct and retract messages he has sent — typos, a badly worded question, something sent to the wrong conversation. Today a mistake is permanent and visible forever, and that is a defect in daily use.
>
> **The bound he set with the requirement: the append-only record is not weakened.** The honest version is *correction and retraction, never erasure*: the original stands, the revision stands, and which came later is visible. A retracted message stops cluttering the live conversation and is not treated as live intent, but remains in the record. This is the shape the record already uses everywhere — the persona's edit-is-a-new-revision, `idea_state_changes`' append-only lineage, `model_calls_accounted`'s supersede-by-view — applied to `messages`.
>
> **Design constraints that bind any implementation:**
>
> - `messages` rows stay frozen (`0009`) and undeletable (§2.3). Revision and retraction are *new facts appended*, never edits to the original.
> - Retraction authority is per-author: this mechanism touches `role = 'user'` rows only. Nobody retracts another speaker's words — Val's answers are hers.
> - Evidence anchors never dangle: `model_calls`, `execution_events`, `deliberations`, and `blind_positions` reference specific message ids, and a retraction must leave every anchor resolving to exactly what was said when the anchored event happened.
> - Money already spent answering the original stays spent and stays attributed. A retraction rewrites no cost.
>
> **Open questions, his to decide when this is taken up** (options and recommendations were given at recording time): what recall does with a retracted message; what happens to an answer whose question is then revised; and how the sunk cost of a retracted exchange is shown.

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
| `persona_id` | **WP-0.5, 17 August 2026.** Which persona revision was assembled into this call's context. Nullable: rows written before a persona existed, and paths that legitimately assemble none, are not calls to attribute. **19 August 2026:** `blind_position` calls carry the persona and therefore attribute it — once a persona is assembled, a NULL here would mean "assembled and failed to attribute," which is a false record, not a missing feature. |
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

> **Clarification — 19 August 2026, Lord Armand. SENT_COST_UNKNOWN versus process-death indeterminacy.**
>
> SENT_COST_UNKNOWN applies when Val remains alive and can durably record an
> attempted provider operation whose outcome or cost is unknown — a timeout or
> provider error. Process-death indeterminacy before durable `model_calls`
> evidence exists is governed instead by §2.5: the surviving
> `budget_reservations` row becomes `expired`, represents that transmission may
> or may not have occurred, remains charged at its authorized maximum, and does
> not cause Val to fabricate a `model_calls` row on restart. If independent
> provider-side evidence later establishes that a call occurred, that evidence
> may be appended truthfully; it is never inferred from the expired reservation
> alone.
>
> *Recorded because the two sections overlapped: both describe an attempt whose
> outcome is unknown, and without this line the SENT_COST_UNKNOWN row could be
> misread as required in the crash case, where no process survives to write it.*

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
| `blind_position_id` | **19 August 2026.** The exact `blind_positions` evidence this record resolves. Nullable: a deliberation recorded manually, or one whose exchange carried no preference to strip, has no blind call behind it. |

**`blind_positions`** — amendment, 19 August 2026, Lord Armand

The blind position is the primary evidence that Val formed a genuinely independent judgment — Layer 5 exists partly to determine exactly that — and it exists *before* the exchange resolves, while the `deliberations` row cannot be written until the outcome is known. Keeping the most load-bearing record in the least durable place would be backwards, so the position is captured as an **append-only evidence row, persisted before step 3 of §4 begins**, on the same footing as every other Layer 0 capture table. It is not mutable interim state: no UPDATE, no hard delete, complete when written.

| Column | Note |
|---|---|
| `id`, `created_at` | |
| `project_id`, `conversation_id`, `message_id` | The exchange it belongs to. Project derived from the conversation's stored scope. |
| `model_call_id` | The blind call itself — the `model_calls` row that produced this position |
| `persona_id` | The persona revision assembled into the blind call (see WP-0.5's 19 August 2026 amendment) |
| `position`, `confidence`, `reasoning` | The position as formed, blind |
| `stripped_content` | What the strip step removed |
| `ordering` | `enforced` \| `contaminated` |
| `classification`, `classified_by` | The §4.8 provenance that triggered the capture |

The exact blind-call payload is additionally logged for WP-0.9's inspection criterion; the log is for inspection, this table is the evidence.

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

> **Amendment — 19 August 2026, Lord Armand. "Every context" is deliberately narrowed to every context in which Val speaks.** WP-0.9 is the first place non-conversation model calls exist, and the rule is resolved rather than left to be read two ways: the **blind-position call carries the active persona whole** — the position must be *Val's* position, and a persona-less blind position compared against her persona-bearing response is two different speakers, which she would update away from nearly every time. That is the same failure `02-partner-systems.md` §4.1 names for a weaker model forming the blind position — theatre generating a paper trail of false independence — arriving through a different door. **Classification and strip calls carry no persona**: they are the house reading content, not Val speaking. This is a narrowing recorded as a decision, not an omission. Every call that carries the persona attributes it: `model_calls.persona_id` names the revision, verified against the active row before transmission.

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

> **Amendment — 3 September 2026, Lord Armand. The classifier contract failed in real use, and unknown classification is not ordinary classification.**
>
> **What was found.** Through 3 September, `blind_positions` and `deliberations` held zero rows and no strip or blind-position call had ever been made: the §4.8 classifier had never delivered a parseable verdict on a real exchange that warranted one. Of 27 classification calls on the record, six ended at the 256-token output cap and at least ten more completed unparseably. Controlled reproduction on the live route showed the shape: the exchange was sent as a bare `user` turn under an instruction-only JSON contract, and the model treated it as a message *to* it — a correct verdict followed by prose answering the exchange until the cap, or prose followed by a fenced verdict. The output cap was a symptom, not the cause; raising it was ruled out. The verdicts, where present, agreed with §4.8's test.
>
> **The repair, smallest correct surface.** Two halves. The reply is **schema-constrained** through the providers' structured-output mechanisms (Anthropic `output_config.format`, GA on the classifier's route, no extra billing beyond the format's own system text, grammar compiled once and cached provider-side; OpenAI strict `json_schema` on the fallback route) — the schema is the parser's exact vocabulary, so the parser stays strict. And the exchange is **framed as data** in a serialised envelope (`VAL-CLASSIFY-V1`), the same device as the memory envelope, so it cannot read as addressed to the classifier. The strip and blind-position contracts are unchanged; they were exercised for the first time in the demonstration below and behaved. A `GatewayRequest` may now carry `output_schema`; an adapter that cannot enforce one refuses rather than drops it.
>
> **The ruling.** Until now a classifier failure was a logged capture miss and the turn proceeded as an ordinary turn — the mechanism deciding whether the safeguard applies switched the safeguard off when it failed. **Unknown classification may not be treated as ordinary classification.** The recovery is bounded: one retry of the identical request; if the classification is still unestablished, the turn ends unanswered — the message stays in the record, no `val` message is written, every classification call is on `model_calls`, and the interface says no provider was asked for a response. It does not proceed as ordinary. Retroactive marking remains. This is not a conflict with invariant 25 (degrade rather than halt): a turn ending unanswered with a plain statement is the existing `UnansweredTurn` shape a provider outage already produces, and Val continues; what is refused is the silent substitution of a lesser path.
>
> **The record, corrected without erasure.** The 19 August report to Lord Armand described the WP-0.9 implementation as *demonstrated* on the strength of the orchestration tests, which run against a scripted provider. That was accurate about the orchestration and inaccurate as a claim about the mechanism: nothing had run against a real provider, and the first real exchanges found the contract failing. The 19 August report stands as written; this amendment records that its "demonstrated" did not cover the provider contract, and that the first real-provider demonstration of the full path is the one of 3 September 2026. The gate consequence is recorded in §5.

### WP-0.10 — Text interface

**Done when:** the interface supports daily use without developer tooling.

**Verified by:**
- A full day of real work conducted entirely through it, with no terminal, no database client, no log tailing.
- Project switching, conversation history, and marking an exchange consequential are all reachable from the interface.
- Nothing in the interface displays a state the database does not support (`00-charter.md` invariant 29).

<!-- scope-ruling: 2026-09-02 -->
### WP-0.11 — Budget-control hardening (warn-and-raise) — recorded 2 September 2026, not yet begun

**Ruled by Lord Armand after both external reviewers converged. Its own work package, not Track C**: Track C's isolation rule is attachments and derived views only, and budget policy colliding with vision in practice does not pull it into the substrate. Layer 0, because the ceiling it hardens is Layer 0's (`01-architecture.md` §5.5 as ruled 2 September 2026).

**What it blocks and what it does not.** It does **not** block the attachment migration or the internal vision implementation after the storage ruling; those proceed on their existing path. It **does** block Track C becoming an operational working-day capability, and it blocks visual conversations contributing evidence to the Layer 0 gate — otherwise "she cannot see" is traded for "she stops mid-session and the raise is a code edit," the same stall through a different door. **Not a development blocker. A live-use blocker.**

**Minimum shape when this work begins:**
- Operating target and runaway safety ceiling are separate concepts with separate values. Neither is a source-code literal.
- The operating target never admits, refuses, or reroutes. It is planning and reporting information only. **Only the runaway ceiling can refuse a call.**
- A clear, non-blocking warning before the ceiling is reached; the first indication of approaching the limit may not be a hard refusal. The initial threshold is proposed with the work-package design, not ruled now.
- Lord Armand can raise the safety ceiling at runtime without editing code, changing schema, restarting the service, or rebuilding Val. The raise is durably attributable: amount, scope, time, actor.
- A runtime raise changes the safety ceiling, not the operating target, and never retroactively alters historical reporting; the concepts stay separate through the records and the interface.
- Reservation, accounting, cost capture, and hard-refusal behavior remain authoritative against the effective ceiling.
- **The degrade behavior is fixed here.** Today a routed call's `BUDGET_EXCEEDED` is retryable, so a turn steps down to a cheaper eligible route and refuses only when nothing affordable remains — Val silently doing worse work to stay under the only number she has, contradicting the quality priority and reading as resilience, which is why it went unnoticed. Under this package: a ceiling hit refuses, or resolves to `UnansweredTurn`. It does not pick a lesser model. An operating-target hit does nothing to the call at all.
- **The number is Lord Armand's.** The refusal must not remain at $200 under a new name — that is still a planning figure stopping a heavy day. The safety ceiling is accident-scale: a figure that trips only when something is genuinely wrong, never because he is working hard. The design proposes the shape; the value is his.

**Not authorized:** automatic increases, forecasting, dashboards, provider-specific budget management, spend optimization, or a policy engine. Premature.

> **Amendment — 31 August 2026, Lord Armand. Invariant 29 applies to error display.** An error message that names a cause it has not established is a false claim. Recorded from real use: the interface asserted the service was "not reachable" while the service was demonstrably healthy — the actual failure was browser policy — and the asserted cause sent diagnosis down a network path that did not exist. Binding on the interface: a failure is reported as what was actually observed ("no response", "the service refused with this status", "the reply could not be read"), never as a diagnosis the observing code cannot make; where script cannot distinguish two causes, the message names both rather than picking one; and a multi-step operation reports each step's failure individually rather than collapsing them into one claim.

---

## 4. The blind position call at Layer 0 — a deviation

<!-- deviation: strip-routing-cloud-until-local -->

`02-partner-systems.md` §4.1 routes the strip step to local inference. **Local inference does not exist until Layer 1.**

> *Tripwired, 1 September 2026: this deviation carries its own expiry — when a local inference route exists in the Model Configuration Registry, `infrastructure/ci/check_scope_ruling.py` fails until this section moves. Temporary deviations with built-in invalidation conditions are exactly the rules that become permanent by accident.*

Layer 0 therefore runs the strip step on **the cheapest configured route** — which, under §1.1, is Protected-eligible by construction — and moves it to local at Layer 1. This is a routing deviation, recorded here rather than left to be discovered.

The alternative — recording positions at Layer 0 without enforcing ordering, and adding the structure at Layer 3 — was rejected. Positions recorded without the ordering guarantee are contaminated by construction, and they would seed the prediction ledger with exactly the data the mechanism exists to exclude. Months of records that cannot be trusted are worse than no records, because they look like evidence.

Cost: two extra calls on consequential exchanges only, one of them on the cheapest configured route. At Layer 0 conversation volumes this is small, and it is measurable from day one via `model_calls.task_type`.

> **Amendment — 19 August 2026, Lord Armand. The true cost, stated.** The paragraph above prices only the deliberation structure. The §4.8 classification is itself a model call, and it runs on **every** exchange, before any position is formed, because it decides whether the structure runs at all. The true recurring cost is therefore: **one classification call per exchange on the cheapest eligible route, plus the two calls above on consequential exchanges only.** This cost is approved. Classification spend is reported **separately** in the cost view from day one — if it comes to dominate, that is read from the record, never inferred.
>
> **Resolved reading — 19 August 2026, Lord Armand.** `02-partner-systems.md` §4.8 says that at Layer 0 the classification "gates recording only," while this section runs the blind-position structure at Layer 0. This document owns Layer 0 scope and records the deviation deliberately, so the resolved reading is: *"recording only" means recording, and the calls recording requires.* The contrast §4.8 draws is with Layer 3, where the classification additionally gates machinery beyond capture.

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

<!-- scope-ruling: 2026-09-03 -->
> **Gate-state ruling — 3 September 2026, Lord Armand. Point 5 restarts from zero; evidence depending on consequential deliberation is paused until the repair is demonstrated.**
>
> Point 5 had not lacked samples; the machinery it names had never executed successfully in real use (WP-0.9 amendment of this date). An unparseable classification attempt is not a classification and counts for nothing. Accordingly: **point 5 stands at zero deliberations**, and WP-0.9's fifty hand-labelled exchanges start from zero — no prior classification is on the record to label against. Points 4, 6 and 7, and the real conversations behind points 1–3, are unaffected and keep their evidence; point 6 continues to count the failed classification calls, which are costed honestly. Accumulation of point-5 evidence and of the fifty resumes only once the repaired path has been demonstrated end to end against real providers, and then through Lord Armand's real use — no manufactured exchanges.

<!-- scope-ruling: 2026-08-31 -->
> **Sequencing ruling — 31 August 2026, Lord Armand. Two tracks.**
>
> **Track A, mandatory:** gate evidence accumulates through real use. No manufactured judgments, no deadline. The gate closes when the evidence exists.
>
> **Track B, permitted in parallel:** Layer 1 presence only, under the hard constraint stated in `01-architecture.md` §2.1 — it consumes the existing conversation contract and changes nothing about it (no new table, no new column, no migration, no change to what the conversation endpoints return); a presence feature needing any of those stops and waits for the gate.
>
> **Everything else stays behind the gate**, and the post-gate order is decided now so it is not re-litigated then:
>
> 1. Message revision and retraction (§2.1 requirement, 31 August 2026)
> 2. Attachment substrate, **with provenance designed once for all four modalities** — not per-modality as each arrives
> 3. Documents
> 4. Image vision (`01-architecture.md` §2.2 requirement, 31 August 2026)
> 5. Audio and video afterward, **each designed against specific real tasks, with a cost model established before implementation**

<!-- scope-ruling: 2026-09-01 -->
> **Amendment — 1 September 2026, Lord Armand. Sight re-scoped out of Layer 2 (`01-architecture.md` §2.2, as amended); the post-gate order changes with it.**
>
> Image vision depends only on the attachment substrate, not on documents, so items 3 and 4 above become **siblings rather than sequential**. The amended order:
>
> 1. Message revision and retraction
> 2. Attachment substrate, provenance designed once for all four modalities before either sibling begins
> 3. **Image vision and documents, as siblings** — image vision is attachment-scoped (an image deliberately attached to a conversation), which satisfies "sight, not receipt" without Layer 2 Hands; MCP filesystem access — reading folders at scale — stays Layer 2
> 4. Audio and video afterward, each designed against specific real tasks, with a cost model established before implementation

<!-- scope-ruling: 2026-09-01 -->
> **Amendment — 1 September 2026, Lord Armand, from external review. The attachment-substrate acceptance boundary.** Both reviewers found a hole in the sibling ruling that neither Lord Armand nor the implementation caught: the design-once rule did not cover **mixed-modality files**. A PDF with figures, a slide with a frame — "what she saw" and "what the document says" are *derived views of one attachment*, not two attachments, and without a rule, page 17 and the figure on page 17 become two provenances for one file.
>
> **Attachment Substrate v1 must be accepted as a shared contract for both image vision and document comprehension before implementation of either consumer begins.** The contract establishes at minimum: the immutable original; attachment identity and hash; typed derived representations; parent/child provenance; processing and model provenance; structural locators such as page/slide/region; processing status and errors; and rules for extending the representation model later.
>
> **The standard is contract-stable, not frozen.** Core provenance semantics may not be privately changed by either sibling. Additive typed representations are permitted. If a sibling finds a core assumption wrong, the contract is amended deliberately rather than quietly becoming the vision version of the attachment model.
>
> **Siblings describes dependency, not mandatory concurrency:** after the substrate is accepted, either may be implemented first, or both in parallel.

<!-- scope-ruling: 2026-09-02 -->
> **Track C — gate-enabling capability. Ruling, 2 September 2026, Lord Armand, after external review; both reviewers independently reached the same conclusion and the same narrow scope. A new track, opened against his own gate-first constraint.**
>
> **Why.** The gate-first ruling was made before Lord Armand had tried to have a working day with Val. Having tried, the finding is that the gate has a **collection-pathway failure nobody modelled**: it assumed the pre-gate product would be useful enough to generate evidence organically. His organic use is visual production work; a text-only Val cannot examine that work, so the evidence either does not accumulate or accumulates thin — her reasoning from his descriptions rather than from the thing itself, the exact inferior evidence class the sight amendment exists to prevent. **That is a defect in how evidence is collected, not evidence that the Layer 0 criteria are wrong.** Night one stands. The bar is not lowered. The sentence that decided it: **a gate that cannot be reached does not keep its authority. It gets abandoned later, messily.** Changing the sequencing assumption while preserving the evidence bar is what stops the gate becoming ceremonial.
>
> **Scope: Attachment Substrate v1 and attachment-scoped image vision. Nothing else.** Explicitly held, not opened: message revision/retraction (a real pain and a different pain — not what stalled the working day), document comprehension (the sibling that waits), audio, video, MCP filesystem, and every later-layer capability. The substrate acceptance boundary above stands in full: Substrate v1 is accepted as a shared contract for both siblings before either consumer begins, contract-stable not frozen, mixed-modality provenance intact. Vision is its first consumer; documents still do not start. **Track B is unaffected**: Layer 1 presence remains permitted in parallel under its existing constraint. Track C supplements Track B; it does not replace, widen, or reinterpret it.
>
> **The constraint.** New tables and migrations for attachments and derived views **only**. **No new column** on `conversations`, `messages`, `execution_events`, `deliberations`, `model_calls`, `personas`, or `budget_reservations` — a feature needing to touch those stops and waits for a ruling. The boundary is **semantic, not syntactic**: existing text-only turns behave exactly as they do now; existing Layer 0 tables do not acquire changed meanings; attachments live in their own substrate and reference existing message and model-call ids through sidecar or join structures. An additive, backward-compatible API surface for associating an attachment with a turn is permitted; changed meaning on an existing surface is not. **Backward compatibility is an acceptance requirement, not a preference**: existing conversation and message representations remain valid when attachment fields or associations are absent, and a text-only turn continues to execute through the existing conversation path without acquiring any new required attachment concept, state, or processing step. Track C may add an association path; it may not make attachments part of the mandatory core-loop contract. **Eligibility is unchanged and uses the existing gateway**: an image is external egress and is classified before it leaves; no provider gets a side door because vision needs one. **If multimodal pricing requires changing the budget or accounting doctrine** rather than feeding new measured usage through it, **STOP and rule before proceeding** — that is the strongest argument the gate has, and it is not being suspended.
>
> **What Track C does not do.** The seven closing points of §5 stay exactly as written. The counts stay at twenty and fifty. Layer 0 does not close until that single session is demonstrated as specified. **Vision behavior is not a gate criterion and does not reduce any count.** Both halves of the evidence distinction, recorded so this is not goalpost movement: **(1)** a conversation *made possible* by an attachment generates ordinary Layer 0 evidence when it genuinely exercises the unchanged Layer 0 mechanisms — a storyboard shown, two alternatives discussed, a consequential blind position formed through the existing machinery, judged with a substantive reason, is a real judgment and a real classification and it counts; the attachment made the conversation possible, it did not make the mechanism less real. **(2)** "Val described an image" never satisfies a gate criterion.
>
> **First deliverable: Substrate v1 as a contract, for Lord Armand's review before implementation.** Immutable original, attachment identity and hash, typed derived representations, parent/child provenance, processing and model provenance, structural locators, processing status and errors, and the rules for extending the representation model later. Contract only — no migrations, no application code — until he has seen it and ruled.

---

## 6. Explicitly deferred

Recorded so it is not added under pressure of seeming incomplete:

| Deferred | Arrives |
|---|---|
| Voice, avatar, local inference | Layer 1 |
| **Processing Restricted content** — requires local inference (§1.1) | Layer 1 |
| **Per-content data classification and per-call eligibility checks** — Layer 0 satisfies invariant 17 structurally (§1.1); tools break that guarantee | Layer 2 |
| MCP, Tool Registry, any tool at all | Layer 2 |
| **Vision** — images reaching the model *as images*, with sight recorded per exchange (`01-architecture.md` §2.2). Re-scoped 1 September 2026: attachment-scoped sight arrives **post-gate** (§5 amended order); folder-scale filesystem reading stays Layer 2 | Post-gate / Layer 2 |
| Roles, agents, self-evaluation, standing adversary, prediction ledger scoring | Layer 3 |
| Temporal, graduated budget thresholds, reserve, cost dashboard | Layer 3 |
| Outbox, audit chain, approval flow, versioned writes, risk-tier machinery | Layer 4 |
| Lesson distillation, promotion, the books as readable artifacts, success models | Layer 5 |

Layer 0 has no actions, so it needs no protection against them. Building that protection now is the failure the whole layering exists to avoid.
