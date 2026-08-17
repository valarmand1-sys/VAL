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
| Generated | 16 August 2026 |
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
| `/docs/baselines/01-architecture.md` | Governing | `3db2aef7…65bbac5` | Layers, stack, topology, model routing, budget, data classification, MCP, avatar, backup |
| `/docs/baselines/02-partner-systems.md` | Governing | `0f629d7a…f90e5f56` | Roles, the books, self-evaluation, deliberation, prediction ledger, success models |
| `/docs/baselines/03-persona.md` | Governing, **v1.1** | `ee3a46e9…4551e149` | Voice, manner, bearing, conduct. Loaded whole, never summarised |
| `/docs/baselines/04-layer-0.md` | Governing | `b9d8fa99…4844a201` | Layer 0 scope, schema, work packages, acceptance criteria, the gate |

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
| **0** | Core loop — exists, remembers, useful across projects | **IN PROGRESS** — 2 of 10 work packages complete |
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

PostgreSQL is the sole authoritative store (invariant 12). Nine tables, all
created through Alembic; no manual DDL at any point. Details in §E.

### Model Gateway — IMPLEMENTED, PARTIALLY VERIFIED

All inference enters through `packages/gateway`. No component calls a provider
SDK directly, enforced in CI. Details in §F.

### Data classifications — IMPLEMENTED NOW

`Public` / `Internal` / `Protected` / `Restricted`. At Layer 0 eligibility is
satisfied **structurally**: every configured route is Protected-eligible, so
there is no ineligible route to misdirect to. Restricted is refused two ways —
by stated classification, and by a deterministic local content preflight (§H).

### Budget — IMPLEMENTED NOW

One crude hard stop: $200/month cloud ceiling, enforced **before** each call by
summing `model_calls`, never reported after (invariant 24). Graduated thresholds,
the reserve, and the cost dashboard are **DEFERRED to Layer 3**.

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

**Unresolved — two, and both are why this is BLOCKED:**

1. **Only one unattended scheduled run has been observed** — 16 Aug 2026 03:15,
   a Sunday, correctly a full backup. B2 holds exactly two backups: the 14 Aug
   manual one and this scheduled one. The criterion requires **two consecutive**
   scheduled runs. A run on 15 Aug either did not fire or was coalesced by
   launchd with the 16 Aug firing (documented behaviour when the machine sleeps).
   The next firing, 17 Aug 03:00, would satisfy it if it succeeds.
2. **The verified restore was performed from a local repository, not from B2.**
   The mechanics are proven; a restore pulled back out of B2 has not been done.

### WP-0.4 — Model Gateway · IN PROGRESS / BLOCKED

**Exists:** the gateway; the Model Configuration Registry with three routes; the
eligibility policy encoding the 15 Aug rulings; the budget hard stop; adapters for
Anthropic and OpenAI; the Google billing verifier (fails closed); the
`model_calls` write path; startup assembly; the Restricted preflight.

**Paths:** `packages/gateway/src/val_gateway/{gateway,persistence,startup}.py`,
`packages/domain/src/val_domain/{gateway,registry}.py`,
`packages/policy/src/val_policy/{eligibility,budget,restricted}.py`,
`packages/providers/src/val_providers/`.

**Verified live (15 Aug):** OpenAI answered through the gateway — 37 tokens in,
24 out, **$0.000905**, exactly (37 × $5 + 24 × $30)/1M from the registry's rates;
Restricted refused with `model_calls` unchanged; the hard stop firing at a seeded
$250 against the $200 ceiling with no provider contacted and no row; error
normalisation across three real failure classes; startup refusing a Zhipu
configuration and refusing a configured route with no key; six `model_calls` rows
for six attempts including all four failures.

**Unresolved / blocked:**

- **Anthropic returns 400 "credit balance is too low".** The key authenticates
  and lists models — only inference is refused. Request id
  `req_011Ce5aYFevxhMfvsywK1gem`. This blocks the two-provider criterion, the
  provider-substitution demonstration, and the day-of-real-use dashboard
  reconciliation.
- No fallback route logic is implemented (§F).

### WP-0.5 to WP-0.10 · NOT STARTED

No implementation exists for persona loading, project resolution, the
conversation loop, execution-history capture, deliberation capture, or the text
interface. **The schema for `execution_events` and `deliberations` exists and is
migrated, but nothing writes to them** — those tables are empty and there is no
write path. `personas` is empty; no seed exists.

---

## E. Current database

| | |
|---|---|
| PostgreSQL | 18.4 (Homebrew), port **5433** |
| pgvector | 0.8.6 (installed; no vector column exists yet — retrieval is WP-0.7) |
| Alembic revision | `0002_reaction_and_ideas` (head) |
| Databases | `val` (authoritative), `val_test` (schema tests; refuses any name not ending `_test`) |

### Tables

| Table | Purpose | Rows in `val` |
|---|---|---|
| `projects` | Projects Val works across | 0 |
| `conversations` | `project_id` nullable — "no project" is explicit | 0 |
| `messages` | `role` ∈ user/val/system; `sequence` unique per conversation | 0 |
| `personas` | Versioned; at most one active (partial unique index) | 0 |
| `model_calls` | Per-call cost attribution | **6** |
| `execution_events` | Acceptances, rejections, revisions, corrections, **reactions** | 0 |
| `deliberations` | Blind position, confidence, ordering, outcome | 0 |
| `ideas` | Idea lifecycle, manual marking only | 0 |
| `idea_state_changes` | Append-only lineage | 0 |

### Constraints that carry meaning

- **No hard delete anywhere.** A trigger on all nine tables refuses `DELETE` and
  `TRUNCATE` (invariant 14, §2.3). Nothing cascades — every FK is `NO ACTION`, so
  capture records outlive the conversation that produced them.
- `ck_execution_events_reason_matches_source` — `reason` and `reason_source`
  cannot disagree.
- `ck_execution_events_event_or_reaction_present` — a row must carry an event, a
  reaction, or both. **Reaction is recorded independently of event type**:
  enthusiasm is never evidence of approval.
- `ck_deliberations_updated_requires_what_changed_her_mind`.
- `ck_idea_state_changes_state_change_changes_state` — a no-op transition is not lineage.
- `reason_source` and `ordering` carry **no default**: the writer must state them.
- Primary keys are `uuidv7()` — time-ordered, so the Layer 3 relocation is a merge
  of globally unique keys rather than a renumbering.

### Migration history

| Revision | Effect |
|---|---|
| `0001_layer_0_schema` | Seven tables, ten enums, pgvector, delete guards |
| `0002_reaction_and_ideas` | `reaction` added, `event_type` made nullable, idea tables |

`0002` modifies **no existing row**: `event_type` keeps its value and `reaction`
backfills as NULL meaning *not recorded*, never `neutral`. Its downgrade
**deliberately fails** if any reaction-only row exists rather than deleting or
fabricating capture records to satisfy a rollback — demonstrated on a scratch
database where the record and revision both survived the refused downgrade.

### Backup/restore state

Two backups in B2 (14 Aug manual, 16 Aug scheduled). WAL archived continuously
from `00000001…0F` to `…24`. Restore, PITR, and both negative key cases proven
against a local repository; a restore **from B2** has not yet been performed.

---

## F. Model Gateway

### Routes, by the six independent states of §5.2.1

| Provider | Config / slug | Adapter? | Qualified? | Protected-eligible? | Enabled? | Successfully called? | Last verified | Blocker |
|---|---|---|---|---|---|---|---|---|
| Anthropic | `claude-opus-5` / `opus-5` | **Yes** | No — exam suite is Layer 2–3 | **Yes** | Yes | **No** | — | Account credit |
| Anthropic | `claude-haiku-4-5` / `haiku-4-5` | **Yes** | No | **Yes** | Yes | **No** | — | Account credit |
| OpenAI | `gpt-5.5` / `gpt-5-5` | **Yes** | No | **Yes** | Yes | **Yes** | 15 Aug 2026 | — |
| Google Gemini | none configured | No | No | Paid billing only | No | No | — | No API reports billing status; verifier fails closed |
| GLM (Zhipu/Z.ai) | none configured | No | No | **Excluded pending verification** | No | No | — | Terms unreviewable as of July 2026 |

`last_live_call_on` is carried in the registry, so *live* is controlled
configuration rather than prose. **An implemented adapter is not a live provider.**

### Pricing used by the registry (per million tokens, read 15 Aug 2026)

| Slug | In | Out | Context | Max output |
|---|---|---|---|---|
| `opus-5` | $5.00 | $25.00 | 1,000,000 | 128,000 |
| `haiku-4-5` | $1.00 | $5.00 | 200,000 | 64,000 |
| `gpt-5-5` | $5.00 | $30.00 | 272,000 | 128,000 |

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

### Order of operations per call

1. **Restricted preflight** on the content itself → block, no row.
2. **Eligibility** for the stated classification → refuse.
3. **Budget** before contacting the provider → refuse, no row.
4. **The call** through the adapter.
5. **Cost and attribution** written to `model_calls` — on success, refusal, **and
   error**.

### Cost recording

Computed at call time from the configuration's rates and stored. Never
recomputed: a historical record that silently re-prices itself is not a record.

### Hard stop

`month_to_date_spend()` sums `model_calls` for the calendar month and compares
against $200 **before** the call. Refused and errored calls count toward spend —
a refusal still consumed input tokens, and excluding them would let a failing
loop overspend while the guard reported room.

### Fallback

**NOT IMPLEMENTED.** The architecture requires fallback only to a prequalified,
independently eligible route. No fallback logic exists today; a failed call
raises. This is a known gap against §5.1, not a deviation — it was never claimed.

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

Run everything with `uv run pytest -q` from the repository root. **213 tests, all
passing at this commit.**

| Suite | Count | Command | Result |
|---|---|---|---|
| Schema and migrations | 89 | `uv run pytest packages/domain/tests/test_schema.py` | **PASS** |
| Version pinning | 26 | `uv run pytest infrastructure/ci/tests/test_check_pins.py` | **PASS** |
| Dependency boundaries | 20 | `uv run pytest infrastructure/ci/tests/test_check_boundaries.py` | **PASS** |
| Restricted preflight | 19 | `uv run pytest packages/policy/tests` | **PASS** |
| Credential scanner | 19 | `uv run pytest infrastructure/ci/tests/test_check_secrets.py` | **PASS** |
| Gateway | 16 | `uv run pytest packages/gateway/tests/test_gateway.py` | **PASS** |
| Registry | 15 | `uv run pytest packages/domain/tests/test_registry.py` | **PASS** |
| `model_calls` persistence | 5 | `uv run pytest packages/gateway/tests/test_persistence.py` | **PASS** |
| B2 credential parser | 4 | `uv run pytest infrastructure/ci/tests/test_check_b2_credential.py` | **PASS** |

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

### Live and manual verification

| Claim | Evidence | Date | Result |
|---|---|---|---|
| CI rejects a boundary violation | PR #1, run `31732534362` | 14 Aug | **PASS** — 2 jobs failed as predicted |
| Clean-checkout build | 72-file materialised checkout, full sequence | 13 Aug | **PASS** |
| Migration reversibility | CI `Database and migrations`, every push | ongoing | **PASS** |
| Encrypted backup to B2 | `pgbackrest info` — 2 backups | 14, 16 Aug | **PASS** |
| Verified restore (local repo) | `verify_restore.py` — 7/7 tables, 11/11 FKs | 13 Aug | **PASS** |
| PITR to a timestamp | recovery stopped before seeding txn | 13 Aug | **PASS** |
| Restore refused without key | 0 files restored, `backup.info` unreadable | 13 Aug | **PASS** |
| Restore refused with wrong key | same | 13 Aug | **PASS** |
| Live provider call | OpenAI, $0.000905, cost arithmetic confirmed | 15 Aug | **PASS** |
| Budget hard stop | seeded $250 vs $200 — no call, no row | 15 Aug | **PASS** |
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
| 2 | **Second consecutive scheduled backup not yet observed.** One occurred 16 Aug 03:15. Next firing 17 Aug 03:00. | WP-0.3 | Time |
| 3 | **Restore from B2 not performed.** Mechanics proven locally only. | WP-0.3 | Claude, once #2 clears |
| 4 | No fallback routing | Nothing at Layer 0 | Deferred |
| 5 | Capture write paths absent for `execution_events` / `deliberations` | WP-0.8, WP-0.9 | Sequenced |

---

## L. Next authorized work

**WP-0.5 — Persona loading.**

WP-0.3 and WP-0.4 are both blocked on things Claude cannot resolve — an account
balance and the passage of a night. Neither blocker is in the code, and both will
clear without further engineering. WP-0.5 is the next package with no dependency
on either: it needs the `personas` table (exists, migrated, empty) and
`03-persona.md` (v1.1, stable), both of which are ready.

Its acceptance criteria require two separate checks — the assembled context
byte-matching the **active `personas` row**, and that row byte-matching
`03-persona.md` **at seed time** — precisely so that a divergence between file
and row cannot read as a pass.

WP-0.6 and WP-0.7 follow. WP-0.7 additionally carries the **trap-question suite**
from the 15 Aug amendment: seeded enthusiasm around a decision that was never
approved must produce a correct negative, never a confabulated date, run against
the real retrieval path and never against mocks.

**This handoff does not begin WP-0.5.**
