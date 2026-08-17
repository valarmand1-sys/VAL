# VAL — Test and Evidence Index

Every claim of verification made anywhere in this project, with what it proves,
where the evidence is, and its result. **A claim not in this index has not been
verified.**

Generated at commit `ccc94e3`, 16 August 2026.
**Updated 17 August 2026** for the WP-0.4 corrective work. New and superseded
rows are dated; **nothing written on an earlier date has been rewritten to look
as though a later correction existed then.** Where a claim made at `ccc94e3` no
longer holds, the row that supersedes it says so and names both dates.

---

## 1. Continuous integration

Six jobs, on every push and pull request. Workflow: `.github/workflows/ci.yml`.
Every action pinned to a full commit SHA.

| Run | Commit | Title | Result |
|---|---|---|---|
| `31920323917` | `44674cf` | WP-0.4 live: model_calls write path | **PASS** (6/6) |
| `31919566935` | `3d970eb` | Five amendments from external review | **PASS** (6/6) |
| `31918578113` | `c5833de` | Gateway as a shared package, adapters | **PASS** (6/6) |
| `31914481307` | `df20574` | WP-0.4 foundation | **PASS** (6/6) |
| `31861362810` | `dcc4f49` | Spec amendments | **PASS** (6/6) |
| `31857078804` | `ec6d369` | WP-0.3 backup, watcher, runbook | **PASS** (6/6) |

Jobs: `No credentials in the tree`, `Versions are pinned`, `Dependency direction`,
`Python service`, `Database and migrations` (all ubuntu-24.04), `Desktop shell`
(macos-15).

---

## 2. Deliberate-failure evidence

The strongest class of evidence here: proving a control **rejects** what it
should, rather than proving it passes what it should.

| # | Claim proved | Evidence | Date | Commit | Result |
|---|---|---|---|---|---|
| 2.1 | CI rejects a dependency-direction violation | **PR #1**, run `31732534362`. `packages/policy` referencing `apps/desktop`. `Dependency direction` **failed** (`policy -> desktop  (path reference to 'apps/desktop')`), `Python service` **failed** (`test_repository_has_no_violation`), `Versions are pinned` and `Desktop shell` **passed** — so the failure was the boundary, not incidental lint. PR closed, branch deleted. | 14 Aug | `cd4cf5c` | **PASS** |
| 2.2 | `import-linter` catches a Python-visible violation | `policy` importing `val_providers` → contract `policy depends on domain only` **BROKEN** | 14 Aug | working tree | **PASS** |
| 2.3 | The two boundary checkers are genuinely complementary | On 2.1, `import-linter` reported **3 kept, 0 broken** — it cannot see TypeScript. `check_boundaries.py` caught it. Neither subsumes the other. | 14 Aug | — | **PASS** |
| 2.4 | Migration downgrade refuses to destroy capture records | Scratch database seeded with a reaction-only row; `downgrade` returned `NotNullViolation`; **record and revision both survived intact** | 15 Aug | `3d970eb` | **PASS** |
| 2.5 | Restore is impossible without the key | Complete repository, no key: `backup.info` unreadable, **0 files restored** | 13 Aug | `19d59a1` | **PASS** |
| 2.6 | Restore is impossible with a wrong key | Same repository, wrong passphrase: same refusal | 13 Aug | `19d59a1` | **PASS** |
| 2.7 | Startup refuses an ineligible provider | Zhipu configuration → `provider is excluded pending verification` | 15 Aug | `44674cf` | **PASS** |
| 2.8 | Startup refuses a configured route with no key | `VAL_OPENAI_API_KEY` unset → refusal naming the variable | 15 Aug | `44674cf` | **PASS** |
| 2.9 | The credential scanner catches its own false-negative regression | A first fix exempted any bare identifier, silently ceasing to catch an unquoted secret in a `.env`-style file. Its **own test** caught it before commit. | 15 Aug | `c5833de` | **PASS** |
| 2.10 | Migration `0003`'s downgrade refuses to destroy an unknown-cost record | Scratch database seeded with one `cost_certainty = 'unknown'` row; `alembic downgrade 0002` returned `NotNullViolation: column "cost" of relation "model_calls" contains null values`; **the row survived and the revision stayed at head** | 17 Aug | working tree | **PASS** |
| 2.11 | An expired reservation is recovered without freeing budget | `expire_stale(0)` moved a `reserved` row to `expired` and reported it by id; **committed spend was unchanged** | 17 Aug | working tree | **PASS** |
| 2.12 | CI was not running two whole test suites | The Python job ran `infrastructure/ci/tests` alone; `packages/policy/tests` and `packages/gateway/tests` were green locally and **never executed by CI**. Found by audit, not by a failure. | 17 Aug | working tree | **CORRECTED** |

---

## 3. Migration and schema verification

| # | Claim | Evidence | Result |
|---|---|---|---|
| 3.1 | `upgrade head` from empty produces the full schema | CI `Database and migrations`, every push | **PASS** |
| 3.2 | Migrations are reversible | CI: `downgrade base` → `upgrade head`; asserts no table, enum, or function outlives the downgrade | **PASS** |
| 3.3 | Schema matches §2 exactly | `test_schema.py` — §2 transcribed **by hand as a second copy**, so models cannot be compared against themselves | **PASS** |
| 3.4 | Models and migration agree | `compare_metadata` returns no differences | **PASS** |
| 3.5 | No hard delete on any table | 9 tables × DELETE and TRUNCATE | **PASS** |
| 3.6 | Nothing cascades | Every FK is `NO ACTION` | **PASS** |
| 3.7 | `reason`/`reason_source` cannot disagree | 3 coherent accepted, 3 incoherent refused | **PASS** |
| 3.8 | Reaction is representable without an event | `strongly_enthusiastic` + null `event_type` inserts; `event_type = 'accepted'` finds **0** | **PASS** |
| 3.9 | Idea lineage is preserved, not overwritten | Two transitions survive a state change | **PASS** |
| 3.10 | `0002` modifies no existing row | `event_type` retained; `reaction` NULL = *not recorded*, never `neutral` | **PASS** |
| 3.11 | `0003` modifies no existing row (17 Aug) | All six `model_calls` rows in the authoritative store unchanged after migration; `cost_certainty` NULL = *written before the distinction existed*. The five error rows carrying `$0.000000` — the false zeros this correction stops — were **left as they were**, because correcting history to match a better present is what invariant 14 forbids. | **PASS** |
| 3.12 | Reversibility holds from empty with `0003` in place (17 Aug) | `upgrade head` (3) → `downgrade base` (3) → `upgrade head` (3); 10 tables at head | **PASS** |

---

## 4. Backup and restore

| # | Claim | Evidence | Date | Result |
|---|---|---|---|---|
| 4.1 | Encrypted backup reaches B2 | `pgbackrest info`: cipher `aes-256-cbc`, 42.2 MB → 4.7 MB | 14 Aug | **PASS** |
| 4.2 | WAL archiving works end to end | `pgbackrest check` exit 0; archive `…0F` → `…24` | 14–16 Aug | **PASS** |
| 4.3 | Full restore to a scratch instance is verified | `verify_restore.py`: **7/7 tables**, **11/11 foreign keys**, all three capture tables continuous | 13 Aug | **PASS** |
| 4.4 | Point-in-time recovery works | Recovery stopped before the seeding transaction; restored instance held 0 rows while source held its own | 13 Aug | **PASS** |
| 4.5 | Restore fails without the separately-held key | §2.5 | 13 Aug | **PASS** |
| 4.6 | The B2 credential pre-flight distinguishes real causes | Master key → 403; capability-less key → 404 `NoSuchBucket`. Both diagnosed correctly. | 15 Aug | **PASS** |
| 4.7 | **Two consecutive unattended scheduled runs** | ~~Only one observed as of 16 Aug.~~ **Superseded 17 Aug 2026:** 16 Aug 03:15 (Sunday, correctly full) and 17 Aug 03:08 (Monday, correctly incremental). Two scheduled runs on consecutive days, no human step, type selection correct on both. Read from `pgbackrest info` against B2, not from the agent's log. | 17 Aug | **PASS** |
| 4.8 | **Restore pulled back from B2** | Still not attempted. 4.3–4.5 used a *local* repository, which proves the encryption, catalogue, and data but not that the bytes in Backblaze are retrievable. | — | **NOT RUN** |
| 4.9 | On-demand backup before a schema migration | `20260816-031538F_20260817-095800I`, taken before applying `0003`, per §9.2. B2 now holds four backups. | 17 Aug | **PASS** |

> 4.1–4.7 and 4.9 prove the mechanics and the schedule. **4.8 alone is why WP-0.3 remains BLOCKED** — and it is the criterion that matters most, because it is the only one that tests the off-machine copy rather than a local one.

---

## 5. Model Gateway and providers

| # | Claim | Evidence | Date | Result |
|---|---|---|---|---|
| 5.1 | A real call succeeds through the gateway | OpenAI `gpt-5.5`: `'Good evening, my lord.'`, 37 in / 24 out, 3378 ms | 15 Aug | **PASS** |
| 5.2 | Cost is computed correctly from registry rates | **$0.000905** = (37 × $5 + 24 × $30) / 1M | 15 Aug | **PASS** |
| 5.3 | Every call writes a `model_calls` row | 6 rows for 6 attempts — including all 4 failures | 15 Aug | **PASS** |
| 5.4 | Restricted content is refused and writes no row | Rows unchanged at 3; provider never contacted | 15 Aug | **PASS** |
| 5.5 | The budget hard stop fires **before** the call | Seeded $250 vs $200 ceiling: no provider contacted, no row, plain explanation | 15 Aug | **PASS** |
| 5.5a | **The ceiling is enforced against the proposed call, not against history** | **Superseding 5.5, 17 Aug.** The 15 Aug guard was `spend < ceiling`, which at $199.99 admitted a call of any size. `test_the_ceiling_is_enforced_against_the_proposed_call_not_history`: $199.99 committed, $0.01 left, a call authorised for more — provider never contacted, no row. The test asserts its own premise first. | 17 Aug | **PASS** |
| 5.5b | **Two concurrent calls cannot together exceed the ceiling** | `test_two_simultaneous_calls_cannot_both_take_insufficient_budget` — two threads, separate connections, barrier-released, headroom for one: exactly one admitted. Then eight threads, room for three: exactly three. **Against real PostgreSQL**, not a fake. | 17 Aug | **PASS** |
| 5.5c | A reservation released, settled below its maximum, or expired resolves correctly | `test_budget_ledger.py` — release returns all of it; settling at $0.25 of a $4.00 reservation returns $3.75; **expiry returns nothing** and is reported in words | 17 Aug | **PASS** |
| 5.5d | An overrun is recorded truthfully rather than clamped | `test_an_overrun_is_reported_rather_than_clamped` — settled $5.00 against a $0.01 reservation: both figures kept, reported as `INVARIANT 24 VIOLATION` | 17 Aug | **PASS** |
| 5.6 | Errors normalise to one contract | Unroutable endpoint → `provider_error`; bad credential → `authentication`; unknown model → `invalid_request` | 15 Aug | **PASS** |
| 5.6a | **A provider failure with no usage is recorded as unknown, never as zero** | **Correcting 5.3, 17 Aug.** The 15 Aug write path recorded `0/0/$0.00` for every error, including errors after transmission — a figure known to be false. Now `cost_certainty = 'unknown'` with NULL figures, and two check constraints make the zero **unwritable**. `test_the_database_refuses_an_unknown_cost_carrying_a_zero`. | 17 Aug | **PASS** |
| 5.6b | An unknown-cost failure does not restore its reserved budget | `test_an_unknown_cost_does_not_hand_the_reservation_back` — settles at the full maximum; committed spend unchanged by the failure | 17 Aug | **PASS** |
| 5.6c | A rejection before the provider creates no `model_calls` row | `test_a_pre_provider_rejection_creates_no_model_call` — no row, and no reservation taken | 17 Aug | **PASS** |
| 5.7 | No provider SDK outside `packages/providers` | `check_boundaries.py`, every CI run | ongoing | **PASS** |
| 5.8 | An adapter existing is not evidence a route works | Registry `last_live_call_on`: `gpt-5-5` set, both Anthropic routes null | 15 Aug | **PASS** |
| 5.8a | **The gateway routes; the caller does not name a provider** | `test_the_router_selects_without_the_caller_naming_a_provider`, and selection is stable across identical requests | 17 Aug | **PASS** |
| 5.8b | **A cheaper ineligible route is never selected** | $0.01/Mtok Public-only against $50.00/Mtok Protected: the $50 route wins. A companion test proves the cheap one really is cheapest, so this cannot pass by accident. | 17 Aug | **PASS** |
| 5.8c | **A fallback is never inherited** | `test_an_ineligible_fallback_does_not_execute` — the declared successor is Public-only and does not appear in the attempt order at all | 17 Aug | **PASS** |
| 5.8d | **An arbitrary provider and model cannot create a route** | `test_a_fabricated_configuration_is_refused` (with a matching adapter deliberately wired in), and `test_a_widened_eligibility_set_is_refused` | 17 Aug | **PASS** |
| 5.8e | Nothing claims formal qualification before the exam suite exists | `test_no_entry_claims_formal_qualification` — every entry is `PROVISIONALLY_ADMITTED` | 17 Aug | **PASS** |
| 5.9 | **Two providers answer through one contract** | Anthropic returns 400 "credit balance is too low" (key authenticates and lists models; `req_011Ce5aYFevxhMfvsywK1gem`) | — | **BLOCKED** |
| 5.10 | **Provider substitution by configuration alone** | Requires 5.9 | — | **NOT RUN** |
| 5.11 | **Zero uncosted calls over a day of real use** | Requires 5.9 and a day of use | — | **NOT RUN** |

---

## 6. Data-eligibility and Restricted handling

| # | Claim | Evidence | Result |
|---|---|---|---|
| 6.1 | Eligibility is enforced at **startup**, not call time | `check_startup` refuses before any adapter is built | **PASS** |
| 6.2 | An excluded provider prevents startup | §2.7 | **PASS** |
| 6.3 | Restricted content is refused by stated classification | §5.4 | **PASS** |
| 6.4 | **Obvious Restricted content is caught regardless of the stated classification** | `test_restricted.py` — 9 representative cases: private key, Anthropic key, OpenAI key, AWS key, GitHub token, labelled credential, connection string with password, SSN, Luhn-valid card | **PASS** |
| 6.5 | The preflight blocks before transmission and writes no row | `test_a_credential_in_protected_content_is_blocked_before_transmission`, `test_a_blocked_request_writes_no_model_calls_row` — adapter call count 0 | **PASS** |
| 6.6 | It fails closed | A scanner raising → request refused, `could not complete` | **PASS** |
| 6.7 | It does not block ordinary creative work | 6 project-language cases pass; a bare 16-digit number is not a card unless it checksums | **PASS** |
| 6.8 | It runs before the budget check | The reason given is the real one | **PASS** |
| 6.9 | Gemini cannot start without verified paid billing | `google_billing.verify_paid_billing` fails closed | **PASS** (by construction) |
| 6.10 | **Labelled financial credentials are caught** (17 Aug) | 7 cases: ABA routing number with check digit, labelled bank account, sort code, BIC/SWIFT, IBAN by mod-97 | **PASS** |
| 6.11 | **The financial detectors do not fire on ordinary work** (17 Aug) | 5 guards: a nine-digit number failing the ABA check, an IBAN-shaped string failing mod-97, an unlabelled invoice number, and two sentences using "account" and "sort" in production senses | **PASS** |
| 6.12 | **The documented coverage claim matches the implementation** (17 Aug) | `test_the_coverage_claim_matches_what_is_implemented` and `test_the_docstring_does_not_claim_comprehensive_detection` — the module states what it does **not** cover and defers mixed-content classification to Layer 2 | **PASS** |

---

## 7. Security

| # | Claim | Evidence | Result |
|---|---|---|---|
| 7.1 | `.env` cannot be committed | `git check-ignore -v .env` → `.gitignore:3:.env`; `git add .env` refused | **PASS** |
| 7.2 | No credential-shaped literal in the committable tree | `check_secrets.py`, every CI run | **PASS** |
| 7.3 | The scanner found a real leak on its first run | CI Postgres service carried a throwaway password; now `POSTGRES_HOST_AUTH_METHOD: trust` | **PASS** |
| 7.4 | No version placeholder or unpinned specifier | `check_pins.py`; literal grep returns empty | **PASS** |
| 7.5 | Every GitHub Action is pinned to a commit SHA | `check_workflows()` | **PASS** |
| 7.6 | The Tauri shell exposes no native bridge | No `invoke_handler`, no plugin, `core:default` only | **PASS** (by inspection) |

---

## 8. Build and toolchain

| # | Claim | Evidence | Result |
|---|---|---|---|
| 8.1 | A clean checkout builds from the documented sequence | 72-file materialised checkout; `uv sync --locked`, `npm ci`, `cargo build --locked` — all succeeded, no undocumented step | **PASS** |
| 8.2 | Every toolchain version resolved against the publisher's index | `docs/TOOLCHAIN.md` records each with its source | **PASS** |
| 8.3 | The desktop shell builds on a machine that never saw it | CI `Desktop shell`, macos-15, every push | **PASS** |
| 8.4 | PostgreSQL major version matches everywhere | `test_postgres_major_version_is_18` | **PASS** |

---

## 9. Summary

| Category | Verified | Blocked / not run |
|---|---|---|
| CI | 6 jobs | — |
| Deliberate-failure | 12 | — |
| Migration / schema | 12 | — |
| Backup / restore | 8 | **1** (4.8) |
| Gateway / providers | 20 | 3 (5.9, 5.10, 5.11) |
| Eligibility / Restricted | 12 | — |
| Security | 6 | — |
| Build | 4 | — |
| **Automated tests** | **310 passing** | — |

**Four outstanding items, none a code defect** — down from five. Three need the
Anthropic account balance; one needs a restore pulled back from B2.

The 17 August corrective work added 97 tests and, more usefully, closed two gaps
that no test had been asserting at all: the ceiling was being enforced against
historical spend rather than against the call being proposed, and a provider
failure after transmission was being recorded as a $0.00 call. Both are now
proved in the negative — the provider is not contacted, and the false zero is
refused by the database itself. Full account: `VAL_WP04_Corrective_Audit.md`.
