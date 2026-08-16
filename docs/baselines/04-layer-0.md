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

Per-content classification arrives at Layer 2, when tools begin pulling in content of mixed classification and the structural guarantee no longer holds.

---

## 2. Schema

One migration set, Alembic, from the first commit. No manual DDL at any point.

### 2.1 Core

**`projects`** — `id`, `name`, `slug`, `description`, `status`, `created_at`, `updated_at`

**`conversations`** — `id`, `project_id` (nullable — "no project" is a real, explicit state, not a null accident), `title`, `started_at`, `last_message_at`

**`messages`** — `id`, `conversation_id`, `role` (`user` | `val` | `system`), `content`, `created_at`, `sequence`

**`personas`** — `id`, `version`, `content`, `is_active`, `activated_at`, `authored_by`. Versioned from the first load. Editing the persona creates a version; it never mutates a row.

### 2.2 Capture

These three tables are the point of the layer.

**`model_calls`** — per-call cost attribution

| Column | Note |
|---|---|
| `id`, `created_at` | |
| `model_config_id` | The configuration, not a bare model string |
| `provider`, `model_identifier` | Denormalised deliberately — a retired config must still resolve historically |
| `tokens_in`, `tokens_out` | |
| `cost` | Computed at call time from the config's rates. Never recomputed later. |
| `project_id` | Nullable, matching `conversations` |
| `task_type` | Enumerated. Layer 0 values: `conversation`, `classification`, `strip`, `blind_position`, `title` |
| `conversation_id`, `message_id` | Nullable |
| `latency_ms`, `provider_request_id` | |
| `status` | `ok` \| `error` \| `refused` |

`cost` is stored, not derived. Provider pricing changes, and a historical record that silently re-prices itself is not a record.

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
- **Eligibility is enforced at startup, not at call time.** Configuring a provider not declared eligible for Protected content causes startup to fail with a clear error. Test by adding an ineligible configuration; the service must refuse to start. A check that only fires when the call is made is not the guarantee §1.1 claims.
- Restricted content is refused rather than routed. Test with content classified Restricted; Val declines and explains, and no `model_calls` row is written.

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
