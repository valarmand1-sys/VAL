# VAL — Engineering State Handoff

**For an external reviewer.** Everything below is drawn from the repository at the
commit named in §A and from the running system, not from recollection of what was
intended. Where something is unproven, it says so.

**One reading rule.** *Implemented*, *verified*, and *complete* are different
states throughout this document, and they are never used interchangeably. Code
existing is not evidence that it works; a test passing is not evidence that the
acceptance criterion is met; an adapter compiling is not evidence that a provider
answers.

---

## A. Repository identity

| | |
|---|---|
| Repository | `valarmand1-sys/VAL` (private, GitHub) |
| Branch | `master` (the repository's default; there is no `main`) |
| Commit | `ccc94e301ca90737bb2e28425c0d906195f82361` |
| Short SHA | `ccc94e3` |
| Working tree | Clean at generation |
| Note on the commit | `ccc94e3` is the state **described** here: all implementation and all governing-document cleanup. This handoff bundle is documentation added on top of it, so the bundle's own commit is one later. Nothing in the code or the baselines differs between the two. |
| Generated | 16 August 2026; **revised 17 August 2026** for the WP-0.4 corrective work |
| Revision note | The corrective work of 17 August changed real facts in §C, §E, §F, §I, and §K. Those sections are updated. **Nothing dated earlier has been rewritten to look as though a later correction existed then** — where a claim made at `ccc94e3` no longer holds, the replacement says so and names both dates. Full account: `VAL_WP04_Corrective_Audit.md`. |
| Tags | None. History is linear on `master`; commits are the only markers. |

There is one closed pull request, [#1](https://github.com/valarmand1-sys/VAL/pull/1),
which exists solely as a deliberate CI-rejection proof (§I). It was never intended
to merge and its branch is deleted.

---

## B. Governing documents

These six are authoritative. Nothing else in the repository governs anything.

| Path | Status / version | SHA-256 | Authoritative on |
|---|---|---|---|
| `/CLAUDE.md` | Standing instructions | `114e31da…7c2f7e3c` | How the implementing engineer works: authority, invariant summary, when to stop and ask |
| `/docs/baselines/00-charter.md` | Governing | `5c49880f…9c7646e5` | Identity, mission, the four states, risk tiers, **35 invariants**, honest limits, what was rejected |
| `/docs/baselines/01-architecture.md` | Governing | `166f8df5…6ba18c58` | Layers, stack, topology, model routing, budget, data classification, MCP, avatar, backup |
| `/docs/baselines/02-partner-systems.md` | Governing | `0f629d7a…f90e5f56` | Roles, the books, self-evaluation, deliberation, prediction ledger, success models |
| `/docs/baselines/03-persona.md` | Governing, **v1.2** | `1d502685…7b8dddd04` | Voice, manner, bearing, conduct. Loaded whole, never summarised |
| `/docs/baselines/04-layer-0.md` | Governing | `0879eecc…8aa4b560` | Layer 0 scope, schema, work packages, acceptance criteria, the gate |

Full hashes are in `governing/README.md`. Byte-identical review copies are in
`governing/`; **the repository originals remain authoritative.**

**Precedence on conflict:** an explicit current decision by Lord Armand → the
charter → the baseline owning the topic → repository configuration and migrations
→ individual changes.

### Non-governing material

`docs/ARCHIVE-NOTE.md` marks a 379-page external draft package and several
superseded design documents as **superseded source material**. None of those
files is tracked in this repository; only the note itself is, and its first three
lines say plainly that the five baselines are the complete specification. No
superseded design document, old copy, or prior persona version exists in the tree
to be mistaken for current authority.

---

## C. Current architecture

### Capability layers

Built as capability layers, not governance phases. Governance arrives when there
is something to govern.

| Layer | Delivers | State |
|---|---|---|
| **0** | Core loop — exists, remembers, useful across projects | **IN PROGRESS** — 3 of 10 complete (WP-0.1, WP-0.2, WP-0.5); **WP-0.6 reopened after independent review** |
| 1 | Presence — voice, face, local inference | SPECIFIED FOR LATER |
| 2 | Hands — MCP tools, read-only | SPECIFIED FOR LATER |
| 3 | Agents — Roles, supervision, Temporal | SPECIFIED FOR LATER |
| 4 | Consequence — real changes, full approval chain | SPECIFIED FOR LATER |
| 5 | Learning — distillation, the books, success models | SPECIFIED FOR LATER |

### Stack — IMPLEMENTED NOW

| Concern | Selection | Pinned |
|---|---|---|
| Store | PostgreSQL 18.4 + pgvector 0.8.6 | major version asserted in tests; patch not pinned (Homebrew) |
| Service | Python 3.14.7, FastAPI 0.141.1, Pydantic 2.13.4 | exact |
| Migrations | SQLAlchemy 2.0.52 + Alembic 1.19.1 | exact |
| Desktop shell | Tauri 2.11.5 + React 19.2.8 + TypeScript 7.0.2 + Vite 8.2.1 | exact |
| Node / Rust | Node 24.19.0 (Krypton LTS), Rust 1.97.1 | exact |
| Providers | `anthropic` 0.122.0, `openai` 3.1.0 | exact |
| Package manager | `uv` 0.12.3 | exact, with `required-version` |

Every version was resolved against the publisher's own index and is recorded with
its source in `docs/TOOLCHAIN.md`. `infrastructure/ci/check_pins.py` fails CI on
any range, moving tag, or placeholder.

**DEFERRED:** Temporal (Layer 3), local inference (Layer 1), ElevenLabs (Layer 1).

### Package boundaries — IMPLEMENTED NOW

```
/apps/desktop        Tauri 2 + React/TypeScript shell (builds; no behaviour)
/apps/api            FastAPI service (package exists; no endpoints yet)
/apps/worker         Background workers (package exists; empty)
/packages/domain     Schemas, typed contracts, the Model Configuration Registry
/packages/gateway    The Model Gateway
/packages/policy     Deterministic classification, eligibility, budget, Restricted preflight
/packages/providers  Provider adapters — the only place an SDK may be imported
/packages/mcp        Structure only; capability arrives at Layer 2
/infrastructure/ci   Boundary, pin, and secret checkers
/infrastructure/backup  Backup runner, watcher, restore verifier, B2 pre-flight
```

Dependency direction is an **allowlist** in `infrastructure/ci/components.toml`,
narrower than the four rules in §3 of the architecture. Enforced by two
complementary checks that CI runs separately:

- `check_boundaries.py` — every language plus the manifests. Catches
  cross-language edges (`policy` → `desktop`) that no import statement can express.
- `import-linter` — transitive Python imports, layered and acyclic.

`gateway` is a shared package rather than a service, decided 15 Aug 2026: `api`
and `worker` share one implementation and one `model_calls` write path without
either process depending on the other being alive.

### Authoritative data store — IMPLEMENTED NOW

PostgreSQL is the sole authoritative store (invariant 12). **Ten** tables, all
created through Alembic; no manual DDL at any point. Details in §E.

### Model Gateway — IMPLEMENTED, PARTIALLY VERIFIED

All inference enters through `packages/gateway`. No component calls a provider
SDK directly, enforced in CI. Details in §F.

### Project scope — IMPLEMENTED NOW

Every exchange resolves to a specific project or deliberately to none before
anything is attributed. Unresolved is a third domain state that **cannot be
persisted**: `converse` takes a `ProjectScope`, a union of resolved-and-none
that excludes ambiguity, so an unsettled exchange is not the right type to pass.
That is what makes `project_id IS NULL` trustworthy as the explicit-none set —
the only value that writes a NULL is a decision. Details in §D.

### Data classifications — IMPLEMENTED NOW

`Public` / `Internal` / `Protected` / `Restricted`. At Layer 0 eligibility is
satisfied **structurally**: every configured route is Protected-eligible, so
there is no ineligible route to misdirect to. Restricted is refused two ways —
by stated classification, and by a deterministic local content preflight (§H).

### Budget — IMPLEMENTED NOW, CORRECTED 17 AUGUST

One hard stop: **$200/month cloud ceiling, enforced before each call against the
cost of that call.** The figure is unchanged; what changed is that it is now
actually enforced.

The 15 August implementation compared *historical* spend against the ceiling,
which at $199.99 admitted a call of any size — before the call, certainly, but
enforcing nothing about it. The rule is now `committed + maximum_cost(call) ≤
CEILING`, where `committed` is held in PostgreSQL as a reservation ledger with an
explicit lifecycle, and admission is atomic under an advisory lock so two
processes cannot each spend the same headroom. §F and
`VAL_WP04_Corrective_Audit.md` §E–F.

Graduated thresholds, the reserve, and the cost dashboard remain **DEFERRED to
Layer 3**.

### Backup — IMPLEMENTED, PARTIALLY VERIFIED

pgBackRest 2.59.0 → Backblaze B2, aes-256-cbc, WAL archiving at 300 s, GFS
retention 30/12/12, two launchd agents. Details in §D (WP-0.3) and §I.

### Machine topology — CURRENT

Single MacBook Pro (M4 Pro, 48 GB). PostgreSQL on **port 5433** — 5432 is an
unrelated instance this project never addresses. The always-on box and the
governed store migration are **SPECIFIED FOR LATER** (Layer 3).

### MCP, Roles, consequence, learning — SPECIFIED FOR LATER

MCP is Layer 2; Roles and agents Layer 3; the approval chain Layer 4; distillation
and the books Layer 5. `packages/mcp` exists as structure with no capability.

### REJECTED (recorded so it is not reintroduced)

The organizational metaphor as architecture; governance-first phase ordering;
uniform ceremony regardless of consequence; Temporal from the start; custom
connector strategy; autonomy levels 0–5 as a separate scale. GLM via Zhipu/Z.ai
is **excluded pending verification** — not rejected permanently.

---

## D. Layer 0 work package status

| WP | Title | Status |
|---|---|---|
| 0.1 | Repository and toolchain | **COMPLETE** |
| 0.2 | Database and migrations | **COMPLETE** |
| 0.3 | Backup and verified restore | **BLOCKED** |
| 0.4 | Model Gateway | **IN PROGRESS / BLOCKED** |
| 0.5 | Persona loading | **NOT STARTED** |
| 0.6 | Project resolution and attribution | **NOT STARTED** |
| 0.7 | Conversation loop and memory | **NOT STARTED** |
| 0.8 | Execution history capture | **NOT STARTED** |
| 0.9 | Deliberation capture | **NOT STARTED** |
| 0.10 | Text interface | **NOT STARTED** |

### WP-0.1 — Repository and toolchain · COMPLETE

**Exists:** full workspace of eight components; every toolchain version pinned
exactly and resolved against publisher indexes; three lock files committed; CI
with six jobs; two boundary checkers; a version-pin checker; a credential scanner.

**Paths:** `pyproject.toml`, `uv.lock`, `.python-version`, `.nvmrc`,
`rust-toolchain.toml`, `apps/desktop/package-lock.json`,
`apps/desktop/src-tauri/Cargo.lock`, `.github/workflows/ci.yml`,
`infrastructure/ci/`, `docs/TOOLCHAIN.md`, `docs/BUILD.md`.

**Verified:** clean-checkout build from the documented sequence with no
undocumented step (72 committable files, no build state carried over); every CI
job green on real runners including the macOS Tauri build; **PR #1 proved CI
rejects a dependency-direction violation** — `Dependency direction` and
`Python service` both failed, `Versions are pinned` and `Desktop shell` passed,
confirming the failure was the boundary and not incidental lint.

**Unresolved:** none.

### WP-0.2 — Database and migrations · COMPLETE

**Exists:** nine tables via two Alembic migrations; ten enumerated types;
no-hard-delete triggers on every table; check constraints enforcing the
load-bearing semantics.

**Paths:** `packages/domain/src/val_domain/schema.py`,
`packages/domain/migrations/versions/0001_layer_0_schema.py`,
`packages/domain/migrations/versions/0002_reaction_and_ideas.py`,
`packages/domain/tests/test_schema.py` (89 tests).

**Verified in CI on every push:** `upgrade head` from empty → `downgrade base` →
`upgrade head`. The schema test transcribes §2 **by hand as a second copy** so
models cannot be compared against themselves; `compare_metadata` additionally
proves models and migration agree.

**Unresolved:** none. Note that §2 now names nine tables (seven original plus
`ideas` and `idea_state_changes` from the 15 Aug amendment).

### WP-0.3 — Backup and verified restore · BLOCKED

**Exists:** pgBackRest → B2 with client-side encryption; WAL archiving; GFS
retention selector; daily launchd agent; hourly watcher with escalating alerts;
B2 credential pre-flight; restore verifier.

**Paths:** `infrastructure/backup/{run_backup,watch_backup,verify_restore,check_b2_credential}.py`,
`infrastructure/backup/launchd/`, `docs/BACKUP.md`.
Config at `/opt/homebrew/etc/pgbackrest/pgbackrest.conf` (mode 0600, **not** in the repo).

**Verified:** encrypted backup to B2 (42.2 MB → 4.7 MB); restore to a scratch
instance verified 7/7 tables, 11/11 foreign keys, capture tables continuous;
PITR to a timestamp stopping before the seeding transaction; **wrong-key and
no-key restores both refused with zero files restored.**

**Resolved since `ccc94e3` — the scheduled-run criterion is now met.** The
17 August firing succeeded: **16 Aug 03:15 (Sunday, correctly full) and 17 Aug
03:08 (Monday, correctly incremental)** are two unattended scheduled runs on
consecutive days, with the full/incremental selection correct on both. Read from
`pgbackrest info` against B2 rather than from the agent's own log. B2 now holds
four backups, the fourth taken on demand before migration `0003` per §9.2.

**Unresolved — one, and it is why this remains BLOCKED:**

1. **The verified restore was performed from a local repository, not from B2.**
   Every restore proved so far — the full restore, the PITR test, and both
   key-failure cases — used a local copy. That proves the encryption, the
   catalogue, and the data. **It does not prove that the bytes in Backblaze are
   retrievable and sound**, which is the one thing an off-machine backup exists
   to establish (invariant 35).

**Scope beyond PostgreSQL, clarified 17 August.** `01-architecture.md` §9.1 lists
five things that must survive; only the first is covered by pgBackRest. **GitHub
is now stated explicitly as the off-machine protection for everything the
repository controls** — baselines, persona source, migration history,
configuration, application source — and stated equally explicitly *not* to be a
substitute for point-in-time recovery. The two protect disjoint things: git holds
the text Val was built from, PostgreSQL holds what she has learned, decided,
spent, and been told. New `01-architecture.md` §9.1.1 and `docs/BACKUP.md`.

### WP-0.4 — Model Gateway · IN PROGRESS / BLOCKED

**Exists:** the gateway with a routing entrance and a deliberate explicit
entrance; the Model Configuration Registry with three routes carrying the full
§5.2 contract; the eligibility policy encoding the 15 Aug rulings; **the
pre-call budget reservation ledger**; **the Layer 0 router with independently
checked fallback**; adapters for Anthropic and OpenAI; the Google billing
verifier (fails closed); the `model_calls` write path with explicit cost
certainty; startup assembly; the Restricted preflight.

**Paths:** `packages/gateway/src/val_gateway/{gateway,ledger,persistence,startup}.py`,
`packages/domain/src/val_domain/{gateway,registry}.py`,
`packages/policy/src/val_policy/{eligibility,budget,routing,restricted}.py`,
`packages/providers/src/val_providers/`.

**Verified live (15 Aug):** OpenAI answered through the gateway — 37 tokens in,
24 out, **$0.000905**, exactly (37 × $5 + 24 × $30)/1M from the registry's rates;
Restricted refused with `model_calls` unchanged; the hard stop firing at a seeded
$250 against the $200 ceiling with no provider contacted and no row; error
normalisation across three real failure classes; startup refusing a Zhipu
configuration and refusing a configured route with no key; six `model_calls` rows
for six attempts including all four failures.

**Corrected 17 August**, after an external review found three real defects. Each
is proved in the negative — see `VAL_WP04_Corrective_Audit.md` §Q:

- **The budget guard did not enforce the ceiling.** It compared historical spend
  against $200, which at $199.99 admitted a call of any size. Now enforced
  against the proposed call, atomically, with a reservation ledger.
- **Cost accounting recorded a figure it could not know.** Every failure wrote
  `$0.00`, including failures after transmission. Now `unknown` with NULL
  figures, and the database refuses the zero.
- **The gateway did not route.** Every caller had to name its own configuration.
  Now it selects on admission, eligibility, readiness, and affordability, with
  cost ranking only what has already survived.

Two further gaps closed in passing: **CI was running neither the policy nor the
gateway test suite**, and the Restricted preflight's stated coverage was wider
than its detectors.

**Unresolved / blocked — one, and it is not a code defect:**

- **Anthropic returns 400 "credit balance is too low".** The key authenticates
  and lists models — only inference is refused. Request id
  `req_011Ce5aYFevxhMfvsywK1gem`. This blocks the two-provider criterion, the
  provider-substitution demonstration, and the day-of-real-use dashboard
  reconciliation. **No mock has been or will be used as proof of the live
  criterion**; `last_live_call_on` is null on both Anthropic routes and a test
  fails the build if that is quietly changed.

### WP-0.5 — Persona loading · COMPLETE

**Exists:** the canonical source-reading rule; a deterministic semantic-version
parser; an idempotent seeder keyed on the source digest; transactional
activation; a runtime loader that fails closed three ways; context assembly
placing the persona whole in `system`; `converse`, the persona-bearing gateway
entrance; per-call persona attribution on `model_calls`.

**Paths:** `packages/domain/src/val_domain/persona.py`,
`packages/gateway/src/val_gateway/{persona,context}.py`, migration
`0005_persona_provenance`.

**Seeded live (17 Aug):** persona `01a01169-c5c4-7576-9e87-6a82f26cd8b1`,
persistence revision **1**, authored version **1.2**, source SHA-256
`1d502685…7b8dddd04` — identical to the file's digest read before any work began.

**Verified:** both WP-0.5 acceptance checks, proved genuinely independent of each
other; immutability enforced by a database trigger; exactly one active revision;
a hostile persona moving no institutional state; five restart and
provider-independence proofs; every model call naming its persona revision,
including two transmitted failures. A real exchange ran through the normal path
and is recorded verbatim in `VAL_WP05_Persona_Loading_Audit.md` §Q.

**Accepted 17 August 2026.** The one criterion that could not be discharged by
engineering — *"Val's register in a real exchange is recognisably that of
`03-persona.md` §9, **assessed by reading, not asserted**"* — was left unsigned
until Lord Armand read the recorded exchange. He read it against the governing
persona and recorded that it **passes**, conditional on the technical evidence
remaining valid.

**That condition was re-verified rather than assumed**: the active persona,
revision, semantic version, stored digest, intactness, source check, and row
counts were all unchanged, `03-persona.md` on disk still hashed to the digest it
was seeded from, 373 tests passed, and CI was green on `73e9947`. **WP-0.5 is
COMPLETE.**

### WP-0.6 — Project resolution and attribution · IMPLEMENTED / ACCEPTANCE BLOCKED

**Exists:** three typed resolution states with `ProjectScope` — the union that
structurally excludes ambiguity; a pure deterministic resolver with a recorded
precedence order and exact-only matching; catalogue loading with existence
validation; an application-owned session; and the exchange boundary that orders
Restricted preflight → resolution → clarify-or-converse.

**Paths:** `packages/domain/src/val_domain/project.py`,
`packages/policy/src/val_policy/project_resolution.py`,
`packages/gateway/src/val_gateway/{projects,exchange}.py`.

**NO SCHEMA CHANGE.** The nullable `project_id` already spends its one meaning
on *explicitly no project*, so unresolved is eliminated before persistence
rather than stored. `converse` now takes a required `ProjectScope`, replacing
`project_id: UUID | None = None` — which let a caller who said nothing about
scope silently write NULL, and made `None` mean both a decision and the absence
of one.

> **Accepted 17 August 2026, then reopened 18 August.** Independent source
> review of the accepted snapshot `8cc0413` found **four acceptance defects**,
> all confirmed. The acceptance is preserved as historical evidence and is not
> rewritten — it records what was believed and demonstrated on the day. Three of
> the four defects were *documented in the source*: the resolver's own docstring
> described the model-authority rule as *"resolves only when nothing of higher
> authority disagrees"*, which is the defect written down and walked past.
>
> **Corrected at source commit `4ff6838`.** Full account:
> `VAL_WP06_Corrective_Audit.md`. WP-0.6 returns to COMPLETE only on
> re-acceptance.

**Originally accepted 17 August 2026.** Re-verified before that acceptance: 437
tests, `mypy` clean over 43 files, boundaries holding, Alembic unchanged at
`0005`, and the accepted snapshot still hashing to `cc580c1c…700221ec`.

**The WP-0.7 caveat is now closed by the schema rather than by a note.** The
nine legacy NULLs were flagged in the original audit as something retrieval must
not misread; the corrective round made that structural. `model_calls` carries
`project_attribution` — `resolved` | `explicit_none` | `legacy_unknown` — so a
reader gets the distinction from the row instead of from a warning. The nine
stay NULL and are labelled `legacy_unknown`; not one `project_id` was rewritten.

**Verified:** all eight real acceptance cases, including a live model call whose
`model_calls.project_id` equals the resolved project; ambiguity producing a
question with **zero** provider calls and **zero** rows; cross-project
attribution with deliberately confusable fixtures; and one persona revision
across Alpha, Beta, and explicit none.

### WP-0.7 to WP-0.10 · NOT STARTED

No implementation exists for the conversation loop, execution-history capture,
deliberation capture, or the text interface. **The schema for
`execution_events` and `deliberations` exists and is migrated, but nothing
writes to them** — those tables are empty and there is no write path.
`conversations` and `messages` likewise have no write path until WP-0.7.

---

## E. Current database

| | |
|---|---|
| PostgreSQL | 18.4 (Homebrew), port **5433** |
| pgvector | 0.8.6 (installed; no vector column exists yet — retrieval is WP-0.7) |
| Alembic revision | `0005_persona_provenance` (head) |
| Databases | `val` (authoritative), `val_test` (schema tests; refuses any name not ending `_test`) |

### Tables

| Table | Purpose | Rows in `val` |
|---|---|---|
| `projects` | Projects Val works across | 0 |
| `conversations` | `project_id` nullable — "no project" is explicit | 0 |
| `messages` | `role` ∈ user/val/system; `sequence` unique per conversation | 0 |
| `personas` | Versioned; at most one active (partial unique index) | **1** — revision 1, authored v1.2 |
| `model_calls` | Per-call cost attribution | **6** |
| `execution_events` | Acceptances, rejections, revisions, corrections, **reactions** | 0 |
| `deliberations` | Blind position, confidence, ordering, outcome | 0 |
| `ideas` | Idea lifecycle, manual marking only | 0 |
| `idea_state_changes` | Append-only lineage | 0 |
| `budget_reservations` | Pre-call budget claims, cradle to grave (§2.5, 17 Aug) | 0 |

**One view, and it is the only one §2 names.** `model_calls_accounted` projects
every `model_calls` column plus `effective_cost_certainty`, `accounted_cost`, and
`accounting_note`. It exists because five rows written on 15 August carry a
fabricated `cost = 0.000000` that the base table cannot distinguish from a real
one. **Every query that touches money reads the view, never the base table.**
§2.2 as amended, and migration `0004`.

### Constraints that carry meaning

- **No hard delete anywhere.** A trigger on all ten tables refuses `DELETE` and
  `TRUNCATE` (invariant 14, §2.3). Nothing cascades — every FK is `NO ACTION`, so
  capture records outlive the conversation that produced them.
- `ck_execution_events_reason_matches_source` — `reason` and `reason_source`
  cannot disagree.
- `ck_execution_events_event_or_reaction_present` — a row must carry an event, a
  reaction, or both. **Reaction is recorded independently of event type**:
  enthusiasm is never evidence of approval.
- `ck_deliberations_updated_requires_what_changed_her_mind`.
- `ck_idea_state_changes_state_change_changes_state` — a no-op transition is not lineage.
- `ck_model_calls_known_cost_is_recorded` and
  `ck_model_calls_unknown_cost_is_not_a_zero` (17 Aug) — a cost recorded as
  *known* must carry figures, and one recorded as *unknown* must carry none.
  Together they make **a false factual zero unwritable**, not merely discouraged.
- `ck_budget_reservations_settled_has_a_cost`, `…_settled_has_a_certainty`,
  `…_resolved_states_say_why` — a settled reservation carries both a figure and a
  certainty, and any state but `reserved` states in words why it left.
- `reason_source` and `ordering` carry **no default**: the writer must state them.
- Primary keys are `uuidv7()` — time-ordered, so the Layer 3 relocation is a merge
  of globally unique keys rather than a renumbering.

### Migration history

| Revision | Effect |
|---|---|
| `0001_layer_0_schema` | Seven tables, ten enums, pgvector, delete guards |
| `0002_reaction_and_ideas` | `reaction` added, `event_type` made nullable, idea tables |
| `0003_budget_reservations` | `model_calls.cost_certainty` with nullable figures and two check constraints; the `budget_reservations` table (17 Aug) |
| `0004_supersede_zero_costs` | A check constraint bounding the legacy set permanently, and the `model_calls_accounted` view (17 Aug) |
| `0005_persona_provenance` | WP-0.5: `semantic_version`, `source_sha256`, `source_path`, `created_at` on `personas`; `activated_at` nullable; an immutability trigger; `model_calls.persona_id` (17 Aug) |

`0002` modifies **no existing row**: `event_type` keeps its value and `reaction`
backfills as NULL meaning *not recorded*, never `neutral`. Its downgrade
**deliberately fails** if any reaction-only row exists rather than deleting or
fabricating capture records to satisfy a rollback — demonstrated on a scratch
database where the record and revision both survived the refused downgrade.

`0003` follows the same precedent exactly. It modifies **no existing row**: all
six `model_calls` rows in `val` are unchanged, with `cost_certainty` NULL meaning
*written before this distinction existed*. That includes five error rows carrying
`cost = 0.000000` — the very false zeros this migration stops being written. They
were **left as they are**: backfilling them would be a judgement about what an
earlier implementation could see, and correcting history to make the present tidy
is what invariant 14 forbids. Its downgrade likewise fails once any honestly
unknown-cost row exists, demonstrated the same way (`NotNullViolation`, row and
revision both intact).

`0004` supersedes the five fabricated zeroes **without touching them**. It
performs no `UPDATE` and no `DELETE`. The rule it publishes is exact rather than
heuristic — the superseded implementation wrote `0/0/$0` on every error and real
usage on everything else — and a check constraint bounds the legacy set
permanently, so a NULL `cost_certainty` can never come to mean anything but
*written before the distinction existed*. Its own downgrade is clean, unlike
`0002` and `0003`: it created no state, so removing it destroys none.

Reversibility from empty is verified: `upgrade head` (4) → `downgrade base` (4)
→ `upgrade head` (4), ten tables and one view at head.

### Backup/restore state

**Four** backups in B2: 14 Aug manual, 16 Aug scheduled (Sunday, full), **17 Aug
03:08 scheduled (Monday, incremental)**, and 17 Aug 09:58 on demand before
migration `0003`. WAL archived continuously from `00000001…0F` to `…32`.

The 16–17 August pair is **two consecutive unattended scheduled runs**, which
satisfies the WP-0.3 criterion that was outstanding at `ccc94e3`. Restore, PITR,
and both negative key cases remain proven against a **local** repository only; a
restore **from B2** has still not been performed, and that is now the single
criterion keeping WP-0.3 blocked.

---

## F. Model Gateway

### Routes, by the seven independent states of §5.2.1

| Provider | Config / slug | Adapter? | Admitted? | Qualified? | Protected-eligible? | Enabled? | Successfully called? | Last verified | Blocker |
|---|---|---|---|---|---|---|---|---|---|
| Anthropic | `claude-opus-5` / `opus-5` | **Yes** | Provisionally | No — exam suite is Layer 2–3 | **Yes** | Yes | **No** | — | Account credit |
| Anthropic | `claude-haiku-4-5` / `haiku-4-5` | **Yes** | Provisionally | No | **Yes** | Yes | **No** | — | Account credit |
| OpenAI | `gpt-5.5` / `gpt-5-5` | **Yes** | Provisionally | No | **Yes** | Yes | **Yes** | 15 Aug 2026 | — |
| Google Gemini | none configured | No | No | No | Paid billing only | No | No | — | No API reports billing status; verifier fails closed |
| GLM (Zhipu/Z.ai) | none configured | No | No | No | **Excluded pending verification** | No | No | — | Terms unreviewable as of July 2026 |

**A seventh state, *provisionally admitted*, was added on 17 August** to resolve a
contradiction rather than to add a capability: §5.1 said routing selects a
*qualified* configuration while §5.2.1 said qualification cannot exist before the
Layers 2–3 exam suite. `PROVISIONALLY_ADMITTED` is the strongest standing any
route holds today; **nothing carries `QUALIFIED`, and no code path sets it.** A
test fails the build if any entry ever claims it.

**Enabled is not admitted.** Adding an entry to the registry is never, by itself,
the act that opens a route.

`last_live_call_on` is carried in the registry, so *live* is controlled
configuration rather than prose. **An implemented adapter is not a live provider.**

### Pricing used by the registry (per million tokens, read 15 Aug 2026)

| Slug | In | Out | Context | Max output | Fallback |
|---|---|---|---|---|---|
| `opus-5` | $5.00 | $25.00 | 1,000,000 | 128,000 | `haiku-4-5` |
| `haiku-4-5` | $1.00 | $5.00 | 200,000 | 64,000 | **NONE**, explicitly |
| `gpt-5-5` | $5.00 | $30.00 | 272,000 | 128,000 | `haiku-4-5` |

Each entry now also carries reasoning settings, caching and batch applicability,
known weaknesses, admission and adapter state, and activation and retirement
dates — the full `01-architecture.md` §5.2 contract. Two fields are honestly
empty rather than filled: `caching` and `batch_pricing` read `NOT_VERIFIED`
because they are pricing facts and this repository reads pricing from the
provider's own page and dates it, never from recollection. `known_weaknesses` is
empty because nothing has been observed in this house's own use.

Each entry carries `rates_verified_on`. Startup **warns** (never fails) on rates
older than 90 days: a stale rate makes cost attribution quietly wrong, and quiet
wrongness is the failure mode a code-held registry creates.

### Contracts

- **Request:** `GatewayRequest` — task type, classification, messages, optional
  system, max output tokens, and the attribution triple (project, conversation,
  message). Provider-neutral by construction.
- **Response:** `GatewayResponse` — text, config id **and slug**, provider, model
  identifier, tokens in/out, cost, latency, provider request id.
- **Errors:** one `GatewayError` with a `GatewayErrorKind` — timeout, refusal,
  rate limit, invalid request, authentication, provider error, invalid output,
  budget exceeded, not eligible, restricted content. Mapped by exception **class
  name**, so it is one function rather than one per provider.

### Two entrances, deliberately not equivalent

- **`complete(request)`** — normal routing. The caller states what the content is
  and what the work is, and never names a provider. A component that must name
  its own provider is a component that can name the wrong one.
- **`complete_with_configuration(request, config)`** — the deliberate explicit
  path, for the strip step of `04-layer-0.md` §4 and for tests that pin one
  provider. **Not a bypass:** the configuration must be the registry's own entry
  for its id, identical field for field, so a fabricated `ModelConfig` — or a
  real one with its model identifier or eligibility set edited — is refused
  before any of the checks it was trying to walk around.

### Order of operations per call

1. **Restricted preflight** on the content itself, before a route is even
   selected → block, no row, **no budget reserved**.
2. **Route selection** — enabled, admitted, eligible, adapter present,
   affordable, in that order. Cost ranks only what has already survived.
3. **Budget reservation** taken atomically against the proposed call → refused
   means the provider is never contacted, and no row is written.
4. **The call** through the adapter.
5. **Settlement** — the reservation closes against what was actually consumed,
   and `model_calls` records the cost as known or as explicitly unknown.

### The five superseded rows — CORRECTED 17 AUGUST

Five `model_calls` rows written on 15 August carry `tokens_in = 0`,
`tokens_out = 0`, `cost = 0.000000`, `status = 'error'` and a NULL certainty.
They are **preserved unmodified** — history is not rewritten to make the present
tidy — and they are now **readable as what they are**. `accounted_cost` is NULL
on all five, `effective_cost_certainty` is `unknown`, and `accounting_note`
explains it in words to anyone querying by hand.

`month_to_date_spend` therefore reports what is *known*, `uncosted_calls_this_month`
counts these five so the total is never presented as complete, and startup warns
when any call is unaccounted for. The original evidence and the correction are
each reconstructable on their own: the base table holds the first, migration
`0004` is the second.

### Cost recording — CORRECTED 17 AUGUST

Computed at call time from the configuration's rates and stored. Never
recomputed: a historical record that silently re-prices itself is not a record.

**A provider attempt has three accounting outcomes and only two are rows.**
NOT_SENT writes nothing, because it was not a call. SENT_COST_KNOWN records real
figures. SENT_COST_UNKNOWN records `cost_certainty = 'unknown'` with NULL
figures — **never a zero.** The previous implementation wrote `0/0/$0.00` for
every failure including those after transmission, which is a figure known to be
false recorded as a fact, and it flowed into the total the ceiling was enforced
against. Two check constraints now make that zero unwritable.

### Hard stop — CORRECTED 17 AUGUST

`committed + maximum_cost(this call) ≤ $200`, decided atomically in PostgreSQL
under an advisory lock before the provider is contacted. `committed` sums settled
reservations, outstanding reservations, expired holds, and any `model_calls` row
predating the ledger **at its accounted cost** — read through
`model_calls_accounted`, so the five fabricated zeroes contribute nothing to a
figure that claims to be known, and `unaccounted_calls()` reports how many are
missing rather than letting the gap be silent. `maximum_cost` is an arithmetic upper bound from UTF-8 byte
length, not an estimate, so it cannot under-reserve; the unspent difference is
released the moment the call settles.

An **expired** reservation — one whose process died — stays charged rather than
being freed, because nothing on this machine can establish whether the provider
was reached, and an unknown consequential outcome is unverified rather than
successful. It is reported at startup and clears when the month resets.

### Fallback — IMPLEMENTED 17 AUGUST

A configuration declares a preferred successor or an explicit NONE. **A fallback
is never inherited**: when it is reached it must have passed every admission,
eligibility, readiness, and affordability check on its own account, and the
implementation is a membership test against the already-filtered candidate set —
so an ineligible successor never appears in the attempt order at all.

A content refusal is deliberately **not** retried elsewhere. A provider declining
to answer is an answer, and re-asking until one complies is shopping for
permission.

### Data-eligibility behaviour

Enforced at **startup**, not call time: a configuration that is not
Protected-eligible, a provider with no ruling, an excluded provider, a
Restricted-declaring route, or a Gemini route without verified billing all
prevent the service from starting. Re-checked per call as defence in depth.

---

## G. Capture systems

| Table | Schema | Write path | Populated |
|---|---|---|---|
| `model_calls` | **Implemented** | **Implemented** (`persistence.py`) | **Yes — 6 rows** |
| `execution_events` | **Implemented** (incl. `reaction`) | **None** | No |
| `deliberations` | **Implemented** | **None** | No |

`model_calls` is live and proven: every attempt writes a row, including failures.

`execution_events` and `deliberations` exist as migrated schema with their
load-bearing semantics enforced by constraints, and **nothing writes to them
yet** — those are WP-0.8 and WP-0.9. The distinction matters: the schema is ready
to receive the capture obligations, but no capture is occurring, so the
Layer 3/5 machinery would currently have nothing to consume beyond cost data.

---

## H. Security and trust boundaries

**Secrets storage.** `.env` at the repository root, git-ignored; `git add .env`
is refused. Backup credentials and the encryption passphrase live in
`/opt/homebrew/etc/pgbackrest/pgbackrest.conf` (mode 0600, outside the repo)
because `archive_command` runs unattended and cannot wait on an unlocked Keychain.
`infrastructure/ci/check_secrets.py` scans git's own view of the committable tree
on every CI run and fails on private keys, values against declared secret
variables, secret-shaped assignments, URLs with inline passwords, and
provider-issued key formats.

**Backup encryption.** aes-256-cbc client-side. The passphrase exists in exactly
two places: the 0600 config, and paper held by Lord Armand in two physical
locations. Not in iCloud, not in the Keychain, not in `.env`, not in B2.

**Protected / Restricted handling.** Protected is safe by construction — every
configured route is eligible. Restricted is refused twice: by stated
classification, and by `val_policy.restricted`, a deterministic local preflight
that reads the content before any transmission, blocks rather than downgrades,
fails closed if it errors, and never asks the receiving model to classify what it
is about to receive.

**Provider egress controls.** Provider SDKs may be imported **only** in
`packages/providers`, enforced in CI across all languages. All inference enters
through one gateway.

**Prohibited arbitrary-code paths.** The Tauri shell registers **no**
`invoke_handler` and **no** plugin; its capability file grants `core:default`
only. No filesystem, shell, or process permission exists to be widened later.

**Authentication.** **None.** There is no user-facing service yet — no API
endpoints, no interface. This is correct for the current state and becomes a real
requirement at WP-0.10.

### Accepted risks, current

1. **The operative backup key is readable by this operating account.** Anything
   running as this account can read `pgbackrest.conf` and decrypt every backup in
   B2. The paper copies do **not** mitigate this — paper protects against losing
   the key, not against someone obtaining it. Blast radius is limited by the
   bucket-scoped B2 key. Revisited at the Layer 3 migration. Recorded in
   `docs/BACKUP.md`.
2. **Gemini cannot be used at all.** The billing verifier fails closed because
   Google exposes no API reporting a key's billing status. Deliberate.
3. **`.env` is plaintext on disk**, protected only by file permissions.

---

## I. Tests and verification

Run everything with `uv run pytest -q` from the repository root. **437 tests, all
passing** — 213 at `ccc94e3`, plus 97 from the corrective work, 21 from the
reviewer-evidence issues, 42 from WP-0.5, and 64 from WP-0.6.

| Suite | Count | Command | Result |
|---|---|---|---|
| Schema and migrations | 101 | `uv run pytest packages/domain/tests/test_schema.py` | **PASS** |
| **Persona loading (WP-0.5)** | 39 | `uv run pytest packages/gateway/tests/test_persona.py` | **PASS** |
| **Project resolution (WP-0.6)** | 40 | `uv run pytest packages/policy/tests/test_project_resolution.py` | **PASS** |
| **Project attribution (WP-0.6)** | 24 | `uv run pytest packages/gateway/tests/test_project_attribution.py` | **PASS** |
| Restricted preflight | 34 | `uv run pytest packages/policy/tests/test_restricted.py` | **PASS** |
| Version pinning | 26 | `uv run pytest infrastructure/ci/tests/test_check_pins.py` | **PASS** |
| Gateway | 28 | `uv run pytest packages/gateway/tests/test_gateway.py` | **PASS** |
| Registry | 24 | `uv run pytest packages/domain/tests/test_registry.py` | **PASS** |
| **Router and fallback** | 25 | `uv run pytest packages/gateway/tests/test_router.py` | **PASS** |
| Dependency boundaries | 20 | `uv run pytest infrastructure/ci/tests/test_check_boundaries.py` | **PASS** |
| Credential scanner | 19 | `uv run pytest infrastructure/ci/tests/test_check_secrets.py` | **PASS** |
| **Budget arithmetic** | 21 | `uv run pytest packages/policy/tests/test_budget.py` | **PASS** |
| **Budget ledger (real PostgreSQL)** | 15 | `uv run pytest packages/gateway/tests/test_budget_ledger.py` | **PASS** |
| `model_calls` persistence | 17 | `uv run pytest packages/gateway/tests/test_persistence.py` | **PASS** |
| B2 credential parser | 4 | `uv run pytest infrastructure/ci/tests/test_check_b2_credential.py` | **PASS** |

**One assertion inverted in this work, named here rather than buried.**
`test_just_under_the_ceiling_still_calls` asserted that $199.99 against a $200
ceiling admits a call. **That assertion encoded the defect.** It was replaced by
two tests that state the real rule: one seeding spend so the specific call fits
exactly and asserting it proceeds, and one using the same $199.99 seed with a
larger call and asserting the provider is never contacted. Nothing else was
deleted, skipped, or relaxed; two tests were renamed to describe what they
actually assert. Full account in `VAL_WP04_Corrective_Audit.md` §P.

### Static and architectural checks

| Check | Command | Result |
|---|---|---|
| Version pins | `uv run --no-project python infrastructure/ci/check_pins.py` | **PASS** |
| Credential scan | `uv run --no-project python infrastructure/ci/check_secrets.py` | **PASS** |
| Boundaries (all languages) | `uv run python infrastructure/ci/check_boundaries.py` | **PASS** |
| Boundaries (transitive Python) | `uv run lint-imports` | **PASS** |
| Lint / format | `uv run ruff check . && uv run ruff format --check .` | **PASS** |
| Types (strict) | `uv run mypy` | **PASS** |

### CI — six jobs, green on every commit since `df20574`

`No credentials in the tree` · `Versions are pinned` · `Dependency direction` ·
`Python service` · `Database and migrations` (ubuntu-24.04) · `Desktop shell`
(macos-15). Every action pinned to a commit SHA.

> **Corrected 17 August.** The `Python service` job ran
> `pytest infrastructure/ci/tests` and nothing else, so **`packages/policy/tests`
> and `packages/gateway/tests` were green locally and were never executed by CI
> at all.** Found by audit rather than by a failure, which is the uncomfortable
> part: six green jobs were reported on every commit while two whole suites went
> unrun. The Python job now runs all three non-database suites, and the database
> job additionally runs `packages/gateway/tests` so the write path and the
> ledger's concurrency tests execute against a real PostgreSQL on every push.

### Live and manual verification

| Claim | Evidence | Date | Result |
|---|---|---|---|
| CI rejects a boundary violation | PR #1, run `31732534362` | 14 Aug | **PASS** — 2 jobs failed as predicted |
| Clean-checkout build | 72-file materialised checkout, full sequence | 13 Aug | **PASS** |
| Migration reversibility | CI `Database and migrations`, every push | ongoing | **PASS** |
| Encrypted backup to B2 | `pgbackrest info` — **4 backups** | 14–17 Aug | **PASS** |
| **Two consecutive unattended scheduled runs** | 16 Aug 03:15 full (Sun) + 17 Aug 03:08 incr (Mon) | 17 Aug | **PASS** |
| Verified restore (local repo) | `verify_restore.py` — 7/7 tables, 11/11 FKs | 13 Aug | **PASS** |
| PITR to a timestamp | recovery stopped before seeding txn | 13 Aug | **PASS** |
| Restore refused without key | 0 files restored, `backup.info` unreadable | 13 Aug | **PASS** |
| Restore refused with wrong key | same | 13 Aug | **PASS** |
| Live provider call | OpenAI, $0.000905, cost arithmetic confirmed | 15 Aug | **PASS** |
| Budget hard stop | seeded $250 vs $200 — no call, no row | 15 Aug | **PASS** |
| **Ceiling enforced against the proposed call** | $199.99 committed, $0.01 left, larger call — provider never contacted | 17 Aug | **PASS** |
| **Concurrent admission cannot exceed authority** | 2 threads / room for 1 → 1 admitted; 8 threads / room for 3 → 3 admitted, real PostgreSQL | 17 Aug | **PASS** |
| **`0003` downgrade refuses to destroy an unknown-cost row** | `NotNullViolation`; row and revision both intact | 17 Aug | **PASS** |
| **Expired reservation recovered without freeing budget** | state moved to `expired`, reported by id, committed spend unchanged | 17 Aug | **PASS** |
| **Fabricated configuration cannot create a route** | rogue provider with a matching adapter wired in — refused | 17 Aug | **PASS** |
| **A tiny prompt with a large output cap is refused before transmission** | 3 words, 128,000 authorised output tokens = $3.20 against $2.00 remaining — provider never contacted | 17 Aug | **PASS** |
| **The five fabricated zeroes are never read as confirmed free calls** | `accounted_cost` NULL, `effective_cost_certainty` `unknown`, counted as uncosted; originals byte-identical | 17 Aug | **PASS** |
| **Persona seeded from the governing document** | revision 1, authored v1.2, digest `1d502685…` identical to the file read before any work began | 17 Aug | **PASS** |
| **Real exchange with the persona loaded** | `converse` → gpt-5-5, 4056/161 tokens, $0.025110; `system` byte-equal to the active row, persona present exactly once | 17 Aug | **PASS** |
| **A live provider fallback, persona intact across it** | Anthropic unpayable → OpenAI; both attempts carried identical persona content and the same `persona_id` | 17 Aug | **PASS** |
| **Database restart leaves the persona authoritative** | `brew services restart postgresql@18`; same persona id, content intact, source check clean | 17 Aug | **PASS** |
| **A hostile persona moves no institutional state** | ceiling, eligibility, violations, admits, Restricted refusal — identical before and after activation | 17 Aug | **PASS** |
| **A real model call carries its resolved project** | `gpt-5-5`, 4050/83, $0.022740; `model_calls.project_id` equals the resolved Project Alpha | 17 Aug | **PASS** |
| **Ambiguity contacts no provider and writes no row** | "Winter Light" matching two projects: clarification returned, 0 calls, 0 rows | 17 Aug | **PASS** |
| **One persona revision across Alpha, Beta, and no-project** | a single distinct `persona_id`; active persona identical before and after a switch | 17 Aug | **PASS** |
| Restricted refused, no row | rows unchanged | 15 Aug | **PASS** |
| Error normalisation | 3 real failure classes | 15 Aug | **PASS** |
| Downgrade refuses to destroy records | scratch DB, `NotNullViolation`, record survived | 15 Aug | **PASS** |
| **Two consecutive scheduled backups** | only one observed (16 Aug) | — | **NOT MET** |
| **Restore from B2** | not attempted | — | **NOT RUN** |
| **Two providers, one contract** | Anthropic blocked | — | **NOT RUN** |

---

## J. Known deviations and amendments

Every one is recorded in the governing documents at the point it applies.

1. **Blind-position strip step runs on the cheapest cloud route, not local**
   (`04-layer-0.md` §4). Local inference does not exist until Layer 1. Recorded
   in the specification itself, not discovered later.
2. **ElevenLabs trains on submitted audio below Enterprise tier.** Training
   turned off on the account; Zero Retention Mode is out of budget. Accepted
   deviation, revisited at Layer 1 when local TTS can be compared by ear.
3. **The Model Configuration Registry is code, not a table.** §2 enumerates the
   tables and forbids others; §5.2 requires versioned records. Both hold with a
   typed committed artifact. Git supplies dated, attributable rate history and a
   deployed artifact cannot drift from what is running.
4. **The gateway is a shared package, not an HTTP service.** One implementation,
   one write path, no network hop, and either process works independently.
5. **Local model sizing is by measurement, not the spec's 32B figure** — that
   number belongs to the always-on box.
6. **Charter invariant 17 widened** from "every model configuration" to "every
   external egress path" — TTS, avatar, backup transport were mechanically
   uncovered.
7. **`event_type` is nullable** so a reaction with no event is representable.
8. **PostgreSQL patch version is not pinned** (Homebrew cannot); the major
   version is asserted in the test suite.
9. **Gemini fails closed and is therefore unusable.** Deliberate.
10. **Fallback routing is not implemented.** A gap, not a deviation.

---

## K. Open issues and blockers

| # | Blocker | Blocks | Owner |
|---|---|---|---|
| 1 | **Anthropic account credit.** Key authenticates and lists models; inference returns 400 "credit balance is too low". Likely credit on a different org, or a workspace key without spend allocation. | WP-0.4 completion — two providers, substitution, dashboard reconciliation | **Lord Armand** |
| 2 | ~~Second consecutive scheduled backup~~ | — | **CLEARED 17 Aug** — 16 Aug 03:15 and 17 Aug 03:08, both unattended, type selection correct on both |
| 3 | **Restore from B2 not performed.** Mechanics proven against a local repository only, which does not establish that the bytes in Backblaze are retrievable. | WP-0.3 — **now the only outstanding criterion** | Claude |
| 3a | ~~Reviewer-evidence issues: stale source snapshot, unmarked fabricated zeroes, unproven output bound~~ | — | **CLEARED 17 Aug** — all three were real; see `VAL_WP04_Corrective_Audit.md` §X |
| 4 | ~~No fallback routing~~ | — | **CLEARED 17 Aug** — implemented, with the fallback independently re-checked rather than inherited |
| 5 | Capture write paths absent for `execution_events` / `deliberations` | WP-0.8, WP-0.9 | Sequenced |

**All six decisions of 17 August are recorded and discharged**, including the
WP-0.6 acceptance and the `projects.status` ruling: status shall not disqualify a
project from resolution, because no governing vocabulary defines such behaviour
and a metadata field must not become an authority boundary by default. **Not a
permanent policy** — it carries a revisit trigger, recorded as item 8 in
`VAL_Open_Decisions.md`. **No decision is currently outstanding.**

---

## L. Next authorized work

**WP-0.5 — Persona loading.**

WP-0.4 is blocked on an account balance, which is not in the code. WP-0.3 is
blocked on a restore from B2 — a single verification run, not engineering. WP-0.5
is the next package with no dependency on either: it needs the `personas` table
(exists, migrated, empty) and `03-persona.md` (**v1.2**, stable), both ready.

Its persistence semantics were recorded on 17 August and should be read before it
starts: `personas.version` is a **persistence revision, not the semantic label**,
so the seeded row will read `version = 1` while holding v1.2 content; authored
content is immutable and editing creates a new row; `is_active` is lifecycle
state that may change, and activating a revision transactionally deactivates the
former one without touching any authored content. `04-layer-0.md` §2.1.

Its acceptance criteria require two separate checks — the assembled context
byte-matching the **active `personas` row**, and that row byte-matching
`03-persona.md` **at seed time** — precisely so that a divergence between file
and row cannot read as a pass.

WP-0.6 and WP-0.7 follow. WP-0.7 additionally carries the **trap-question suite**
from the 15 Aug amendment: seeded enthusiasm around a decision that was never
approved must produce a correct negative, never a confabulated date, run against
the real retrieval path and never against mocks.

**This handoff does not begin WP-0.5.**
