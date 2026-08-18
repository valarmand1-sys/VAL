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
| 2.12 | CI was not running two whole test suites | The Python job ran `infrastructure/ci/tests` alone; `packages/policy/tests` and `packages/gateway/tests` were green locally and **never executed by CI**. Found by audit, not by a failure. | 17 Aug | `65853a1` | **CORRECTED** |
| 2.13 | CI caught a regression in the fix for 2.12 | Adding the gateway suite to the database-less Python job broke `test_persistence.py`, which needs PostgreSQL: run `32043123796` on `6472911` — **7 failed, 168 passed, 15 skipped**. The `Database and migrations` job passed all 72. Fixed by the commit recording this row. | 17 Aug | `6472911` | **PASS** (the failure was correct) |

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
| 3.13 | `0004` modifies no existing row (17 Aug) | The migration performs no `UPDATE` and no `DELETE`. All six `model_calls` rows in `val` verified byte-identical after it: `cost` still `0.000000` on the five, `0.000905` on the one real call. | **PASS** |
| 3.14 | The five fabricated zeroes report as unknown, not as free (17 Aug) | `model_calls_accounted`: `accounted_cost` NULL and `effective_cost_certainty = 'unknown'` on all five; the one genuine call still `known` at `$0.000905` | **PASS** |
| 3.15 | The superseding rule is exact rather than a blanket (17 Aug) | `test_the_superseding_rule_is_exact_not_a_blanket` — legacy `ok` and `refused` rows stay `known`; only legacy `error` rows are reinterpreted, because only the error path fabricated figures | **PASS** |
| 3.16 | The legacy set is bounded permanently (17 Aug) | `test_a_new_row_may_not_omit_its_cost_certainty` — a check constraint refuses any post-17-August row with an unstated certainty, so NULL can never come to mean anything else | **PASS** |
| 3.17 | No view exists that §2 does not name (17 Aug) | `test_no_view_exists_that_the_specification_does_not_name` — the table checks filter on `BASE TABLE`, so without this a view would be invisible to them | **PASS** |
| 3.18 | Reversibility holds from empty with `0004` in place (17 Aug) | `upgrade head` (4) → `downgrade base` (4) → `upgrade head` (4); 10 tables and 1 view at head. `0004`'s downgrade is clean against real data — it created no state to destroy. | **PASS** |

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
| 5.5e | **A tiny prompt with a large output cap is refused before transmission** | `test_a_tiny_prompt_with_a_large_output_cap_is_refused_before_transmission` — 3 words of prompt, 128,000 authorised output tokens ($3.20 on Opus 5) against $2.00 remaining. Provider never contacted, no row, **no budget reserved**. The test asserts both premises first: that output alone exceeds the remainder, and that the prompt's own share is under a cent. | 17 Aug | **PASS** |
| 5.5f | The same prompt with a modest output cap still proceeds | `test_the_same_tiny_prompt_with_a_modest_output_cap_proceeds` — proves 5.5e is the output cap, not the prompt and not the ceiling | 17 Aug | **PASS** |
| 5.5g | The reservation covers the whole authorised output, and the surplus is freed | `test_the_reservation_covers_the_whole_authorised_output` — 64,000 authorised, 10 used, settled at under 1% of the hold | 17 Aug | **PASS** |
| 5.5d | An overrun is recorded truthfully rather than clamped | `test_an_overrun_is_reported_rather_than_clamped` — settled $5.00 against a $0.01 reservation: both figures kept, reported as `INVARIANT 24 VIOLATION` | 17 Aug | **PASS** |
| 5.6 | Errors normalise to one contract | Unroutable endpoint → `provider_error`; bad credential → `authentication`; unknown model → `invalid_request` | 15 Aug | **PASS** |
| 5.6d | **A billing failure is a route problem, not a request problem** | **Found by running the system, 17 Aug.** Anthropic returns "credit balance is too low" as an HTTP 400 → normalised to `INVALID_REQUEST`, which is deliberately non-retryable, so the router refused to fall back and a real exchange failed while a working route sat unused. Corrected to `PROVIDER_ERROR`; a genuinely malformed request is still not retried. `req_011Ce8xDp7bfjRu5BgXqNuXx`. | 17 Aug | **PASS** |
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

## 5b. Persona loading — WP-0.5, 17 August 2026

| # | Claim | Evidence | Result |
|---|---|---|---|
| 5b.1 | The governing persona is seeded into PostgreSQL | revision 1, authored v1.2, id `01a01169-…d8b1`, 17,999 chars | **PASS** |
| 5b.2 | The stored content is the document byte-for-byte | `content.encode("utf-8")` equals the file's bytes; sections a summariser drops first are present | **PASS** |
| 5b.3 | The stored digest is the document's digest | `1d502685…7b8dddd04`, identical to the file read before any work began | **PASS** |
| 5b.4 | Reseeding is idempotent | Three runs: `created`, `unchanged`, `unchanged`; one row. Keyed on the source digest, so it holds across machines and a restored database. | **PASS** |
| 5b.5 | A changed document is not silently imported | `PersonaSourceChangedError`; nothing written. Git moving is not authorisation. | **PASS** |
| 5b.6 | **Check one** — assembled context matches the active row | `system` byte-equal to the active row's content, live and in tests | **PASS** |
| 5b.7 | **Check two** — the active row matches the governing source | `verify_against_source` reports no findings | **PASS** |
| 5b.8 | **The two checks are genuinely independent** | A record constructed to pass check one and fail check two: check two catches it. This is the failure comparing the context straight to the file would miss. | **PASS** |
| 5b.9 | Authored content cannot be updated | A `BEFORE UPDATE` trigger; 6 parametrised cases, each refused and each leaving the row unchanged | **PASS** |
| 5b.10 | Exactly one revision is active | Partial unique index, verified to exist by its own test | **PASS** |
| 5b.11 | Zero active personas fails loudly | `NONE_ACTIVE`; no generic Val, no embedded fallback | **PASS** |
| 5b.12 | Multiple active personas fail closed | The loader refuses rather than picking newest or first | **PASS** |
| 5b.13 | A failed activation leaves the previous revision active | Activating a missing id rolls the deactivation back with it | **PASS** |
| 5b.14 | A new revision leaves the old content untouched | Revision 1 byte-identical after revision 2 is created and activated | **PASS** |
| 5b.15 | Persona appears exactly once | Structural — `system` is a single field | **PASS** |
| 5b.16 | Provider substitution leaves the persona identical | Proved in tests and **live**, across a real fallback within one exchange | **PASS** |
| 5b.17 | Project switching leaves the persona identical | Same content, same `persona_id`; no project identifier in the persona | **PASS** |
| 5b.18 | **Persona cannot widen authority** | A hostile persona granting spend, tools, and Restricted eligibility activated: ceiling, eligibility sets, violations, `admits`, and the Restricted refusal all identical. Policy imports neither the gateway nor the persona. | **PASS** |
| 5b.19 | The active persona survives an application restart | New process, new engine: same id | **PASS** |
| 5b.20 | The active persona survives a database restart | `brew services restart postgresql@18`: same id, content intact | **PASS** |
| 5b.21 | Runtime works when the source document is unavailable | Full persona assembled from PostgreSQL against a root where the file does not exist | **PASS** |
| 5b.22 | An invalidated active persona refuses rather than falling back | `converse` raises; the provider is never contacted | **PASS** |
| 5b.23 | Model calls record the persona revision used | Live: all three rows name revision 1, authored v1.2 | **PASS** |
| 5b.24 | A transmitted call that errors keeps its attribution | Both Anthropic failures carry the persona | **PASS** |
| 5b.25 | Historical attribution survives a later activation | `persona_id` unchanged after a new revision is activated | **PASS** |
| 5b.26 | A request never sent records no persona | No row at all, so nothing to attribute | **PASS** |
| 5b.27 | **Real exchange through the normal path** | `converse` → gpt-5-5, 4056/161, $0.025110, `resp_02a5e187…`. Response recorded verbatim. | **PASS** |
| 5b.28 | **Persona register recognisable by human assessment** | Response recorded verbatim; **read against the governing persona and passed by Lord Armand, 17 August 2026.** The criterion is his reading, not a model's assertion, and it was not signed by one. | **PASS** |
| 5b.29 | The technical evidence still held when the acceptance was recorded | The acceptance was conditional, so it was checked: active persona, revision, semantic version, stored digest, intactness, check two, row counts, and the on-disk persona digest all unchanged; 373 tests passing; CI green on `73e9947` | **PASS** |

> **WP-0.5 is COMPLETE.** All 29 rows above pass. 5b.28 was the one criterion
> that could not be discharged by engineering, and it was left unsigned until
> Lord Armand read the exchange. Full account:
> `VAL_WP05_Persona_Loading_Audit.md`.

## 5c. Project resolution and attribution — WP-0.6, 17 August 2026

| # | Claim | Evidence | Result |
|---|---|---|---|
| 5c.1 | Exact id, slug, and canonical name each resolve | Three tests, one per key | **PASS** |
| 5c.2 | Normalisation is deterministic and idempotent | Case, outer and internal whitespace; `normalise(normalise(x)) == normalise(x)` | **PASS** |
| 5c.3 | **Near-misses do not resolve** | `Project Alpah`, `Alpha`, `Projekt Alpha`, `Project Alph` all fail. Similarity has no authority. | **PASS** |
| 5c.4 | A well-formed but unknown UUID is unresolved, not none | `UNKNOWN_IDENTIFIER`; the outcome carries no `project_id` attribute at all | **PASS** |
| 5c.5 | **A name matching two projects asks** | Two projects named `Winter Light`; `MULTIPLE_NAME_MATCHES` with both candidates | **PASS** |
| 5c.6 | The question names only the candidates | Unrelated projects asserted absent from the text | **PASS** |
| 5c.7 | **A clarification distinguishes candidates that share a name** | Found by running acceptance case E: the question said "Winter Light and Winter Light". Now falls back to the unique slug, and only where names collide. | **PASS** |
| 5c.8 | **A confident, wrong model cannot establish scope** | Session says Alpha, "model" insists on Beta → a question, not Beta | **PASS** |
| 5c.9 | A model naming a non-existent project creates no scope | No candidates, no attribution | **PASS** |
| 5c.10 | **The resolver cannot reach a model at all** | Import graph asserted: no provider, no gateway, no SDK | **PASS** |
| 5c.11 | Explicit no-project resolves to NULL | `ExplicitNoProject.project_id is None` | **PASS** |
| 5c.12 | **Silence is unresolved and never no-project** | The heart of the package: an unanswered question must not become an answer | **PASS** |
| 5c.13 | No ambiguous outcome can be read as no-project | Five ambiguous paths, none an `ExplicitNoProject` or `ResolvedProject` | **PASS** |
| 5c.14 | Precedence is as documented | *Superseded 18 Aug — see 5e.7.* The original guard was `PRECEDENCE == tuple(ResolutionSource)`, a flat order that could not express two sources of equal authority. | **PASS, superseded** |
| 5c.15 | **Conflicting signals ask rather than choose** | Session in Alpha, mention of Beta → `CONFLICTING_SIGNALS` with both candidates | **PASS** |
| 5c.16 | Restating the current project is not a conflict | Agreement resolves; it does not ask | **PASS** |
| 5c.17 | An inconsistent established scope asks | Conversation or session pointing at a deleted project | **PASS** |
| 5c.18 | Session lifetime is the process, and unset asks | A fresh session is unresolved, not none; `clear()` returns to unset | **PASS** |
| 5c.19 | An explicit-none session persists as a decision | Later unspecified exchanges stay at none rather than re-asking | **PASS** |
| 5c.20 | **Ambiguity contacts no provider and writes no row** | `adapter.calls == 0`, `model_calls` count unchanged. Invariant 16: scope-unknown content is not sent to a model to ask what it is. | **PASS** |
| 5c.21 | A resolved project reaches `model_calls.project_id` | Equal to the resolved id | **PASS** |
| 5c.22 | Explicit no-project reaches it as NULL | And by decision, because nothing else can write one | **PASS** |
| 5c.23 | **Switching A→B preserves A's history** | Alpha's row unchanged, still exactly one | **PASS** |
| 5c.24 | Switching to no-project preserves prior history | Alpha then NULL, in order | **PASS** |
| 5c.25 | **A and B attribution never cross** | Four alternating exchanges, exactly 2 each, with confusable fixtures | **PASS** |
| 5c.26 | Stale session state cannot leak in | Session in Alpha, explicit call about Beta → Beta | **PASS** |
| 5c.27 | **Scope does not come from provider conversation memory** | Messages naming Alpha repeatedly, exchange scoped to Beta → Beta | **PASS** |
| 5c.28 | One persona revision across projects | Alpha, Beta, and none produce a single distinct `persona_id` | **PASS** |
| 5c.29 | Provider substitution does not alter attribution | Same project across both configured providers | **PASS** |
| 5c.30 | **`converse` cannot be called without a scope** | `TypeError`. The signature is the guarantee; there is no default that writes NULL. | **PASS** |
| 5c.31 | **Every persisted NULL is a decision** | Resolved, explicit-none, and two unresolved exchanges: 2 rows, 1 NULL. The unresolved ones wrote nothing. | **PASS** |
| 5c.32 | Restricted is refused before scope is considered | §16's ordering, with an unresolved scope too | **PASS** |
| 5c.33 | **All eight real acceptance cases** | A–H against the authoritative store, incl. a live `gpt-5-5` call at $0.022740 whose `project_id` equals the resolved project | **PASS** |

| 5c.34 | The evidence still held when the acceptance was recorded | Re-verified at `ef3e613`: 437 tests, `mypy` over 43 files, boundaries across 8 components, `lint-imports` 3/0, Alembic unchanged at `0005`, snapshot still `cc580c1c…700221ec` | **PASS** |
| 5c.35 | **Every row written since WP-0.6 carries a resolved project** | The 2 rows from acceptance case G are `project-alpha`. The 9 NULLs all predate WP-0.6 — 6 from WP-0.4, 3 from WP-0.5 — and are **not** explicit no-project decisions. Recorded so WP-0.7 retrieval does not read them as decisions nobody made. | **PASS, with the caveat stated** |

### 5c-corrective — independent review findings, 18 August 2026

| # | Claim | Evidence | Result |
|---|---|---|---|
| 5d.1 | **An untrusted candidate cannot resolve, even with nothing to disagree** | The adversarial test the original suite lacked: no conversation, no session, no selection, an exact match to a real project → asks. Four normalisations, a model-produced UUID, and a hallucinated name all likewise. | **PASS** |
| 5d.2 | **The same bytes resolve from the trusted field and not the untrusted one** | The correction in one assertion: nothing about the string decides, only which field it arrived in | **PASS** |
| 5d.3 | An established conversation with a NULL project is explicitly none | Case A. Was `AmbiguousProject`. | **PASS** |
| 5d.4 | **A session cannot hijack an explicit-no-project conversation** | Case B, and the most dangerous of the four: it previously returned `ResolvedProject(Alpha)` **via session**, and WP-0.7 would have made it durable | **PASS** |
| 5d.5 | Explicit-none persists; explicit selection still switches; a mention asks | Cases C, D, E, plus a guard that established *project* conversations still resolve | **PASS** |
| 5d.6 | Duplicate-name candidates are structurally distinguishable | Two distinct ids, two distinct slugs, one shared name; question and payload describe the same projects | **PASS** |
| 5d.7 | **A legacy NULL is never read as explicit-none** | `project_attribution = 'legacy_unknown'` on the nine; `explicit_none` on new decisions | **PASS** |
| 5d.8 | The generic gateway path cannot omit attribution | `GatewayRequest` requires both fields with no defaults; contradictory pairs refused both ways | **PASS** |
| 5d.9 | **`LEGACY_UNKNOWN` is unreachable by new code** | *Partly superseded 18 Aug — see 5e.9.* The request validator holds. The check constraint keyed on `created_at` did **not**: backdating the row walked past it. | **PASS at the validator, FAILED at the database** |
| 5d.10 | Analytics separates a decision from a legacy NULL | Two NULL rows, one `explicit_none`, one `legacy_unknown` — indistinguishable before the correction | **PASS** |
| 5d.11 | No `project_id` was rewritten | 9 stay NULL, 2 stay `project-alpha`; backfill adds a statement about them and changes none of them | **PASS** |
| 5d.12 | `projects.status` has no resolution authority | Seven arbitrary status strings, three lookup paths, identical outcomes. Behavioural, not source-text. | **PASS** |
| 5d.13 | The accounting view still exposes every base column | `0006` recreated it; the new column is the one a future reader most needs | **PASS** |
| 5d.14 | All eight acceptance cases re-pass on corrected code | Including a live `gpt-5-5` call at $0.021615 recording `resolved` + Project Alpha | **PASS** |

### 5c-corrective, round two — second independent review, 18 August 2026

| # | Claim | Evidence | Result |
|---|---|---|---|
| 5e.1 | **An explicit "no project" beats a session project** | Case A. Was `ResolvedProject(Alpha)` via session — a session set an hour ago outranked a decision being made in that breath. | **PASS** |
| 5e.2 | An explicit "no project" beats an established conversation | Case B. Decides this exchange; nothing historical is touched. | **PASS** |
| 5e.3 | An explicit "no project" beats a trusted reference | Level 2 over level 5, as an explicit selection would | **PASS** |
| 5e.4 | **A trusted application id still outranks it** | Level 1 unchanged. The correction raised level 6 to 2, not to 0. | **PASS** |
| 5e.5 | **Two contradictory explicit choices fail closed** | Case F. Same authority class, disagreeing, so there is no principled pick. Was `ResolvedProject(Beta)`. | **PASS** |
| 5e.6 | An explicit-none session survives a competing reference | Cases D and E. Previously the session's decision vanished and Beta resolved outright — including from an **untrusted** candidate, which is finding 1 recurring through another door. | **PASS** |
| 5e.7 | **Precedence levels match the enum exactly** | The drift guard, rewritten over `tuple[frozenset[...], ...]`. Asserts level 2 holds exactly the two explicit-choice sources. | **PASS** |
| 5e.8 | An unset session is still distinct from an explicit-none session | The two must not collapse: one asks, the other is a decision | **PASS** |
| 5e.9 | **Backdating cannot reopen the legacy set** | Three dates — today, before `0006`'s cutoff, and 2001 — all refused by the `0007` trigger. Run against the **authoritative** store as well as the scratch one. | **PASS** |
| 5e.10 | An existing row cannot be turned into a legacy one | The half a check constraint cannot state: the guard is on the transition, so the obvious workaround is closed too | **PASS** |
| 5e.11 | A historical row stays an ordinary row | Closed to new members, not frozen — the nine remain correctable | **PASS** |
| 5e.12 | **The `0006` downgrade refuses once a decision is recorded** | One `explicit_none` row makes the rollback destructive; it refuses **and does not half-apply** | **PASS** |
| 5e.13 | The `0006` downgrade is still clean when nothing was decided | CI and any fresh checkout, and re-appliable afterwards | **PASS** |
| 5e.14 | The `0007` downgrade is clean both ways | It captured nothing, so it restores `0006`'s constraint rather than losing a record | **PASS** |
| 5e.15 | The nine historical rows are unchanged | Count and earliest date verified across the migration, after an on-demand encrypted backup | **PASS** |
| 5e.16 | **All eight original acceptance cases still pass** | Re-run unchanged against the corrected resolver | **PASS** |
| 5e.17 | **Two tests had been passing for the wrong reason** | Found while proving the above, not by the review. Both asserted only `pytest.raises(Exception)` and had been failing on argument count since `0006`, never reaching the constraint under test — and one named a constraint that does not exist. Now read from psycopg diagnostics. | **FOUND AND FIXED** |

> **WP-0.6 was reopened a second time on 18 August**, after independent review
> of `VAL_Source_Snapshot_4ff6838.zip` confirmed the four round-one fixes and
> found two further defects. Both are corrected above. WP-0.6 returns to
> COMPLETE only on re-acceptance.

> **WP-0.6 was accepted on 17 August and reopened on 18 August** after
> independent source review found four defects, all confirmed. The rows above
> record the corrections. WP-0.6 returns to COMPLETE only on re-acceptance.
> Full account: `VAL_WP06_Corrective_Audit.md`.

> **The original WP-0.6 acceptance**, accepted by Lord Armand on 17 August 2026. No criterion
> here required a human reading — every one is a mechanical property of code and
> records — and all were re-verified before the acceptance was recorded. Full
> account: `VAL_WP06_Project_Resolution_Audit.md`.

## 5f. Conversation loop and memory — WP-0.7, 18 August 2026

| # | Claim | Evidence | Result |
|---|---|---|---|
| 5f.1 | A project conversation stores its project | | **PASS** |
| 5f.2 | An explicit-no-project conversation stores NULL | And by decision — nothing else can write one | **PASS** |
| 5f.3 | **Unresolved scope creates no conversation** | Clarification returned; conversation count unchanged | **PASS** |
| 5f.4 | **Ambiguous scope creates no conversation and no message** | Zero rows in both tables | **PASS** |
| 5f.5 | The type system refuses an ambiguous scope | `create` takes `ProjectScope`, no default — WP-0.6's mechanism one table further | **PASS** |
| 5f.6 | A user message persists with every required field | id, conversation, role, content, sequence, created_at | **PASS** |
| 5f.7 | A Val message persists as `val`, not `assistant` | The house's record says who spoke; `assistant` exists only on the wire | **PASS** |
| 5f.8 | **Content is preserved exactly** | Whitespace, tabs, unicode, and a 10,000-character body — byte-identical | **PASS** |
| 5f.9 | Sequence begins at 1 | | **PASS** |
| 5f.10 | Sequence is per-conversation, not a shared counter | Two conversations both start at 1 | **PASS** |
| 5f.11 | The database refuses a duplicate sequence | The backstop, asserted directly | **PASS** |
| 5f.12 | **Concurrent appends are gapless across independent connections** | 40 writers, 40 separate engines, barrier-released; assigned set is exactly 1..40 — not merely unique | **PASS** |
| 5f.13 | Content-to-sequence mapping is stable when reread | | **PASS** |
| 5f.14 | **A rolled-back append leaves no permanent gap** | The reason a PostgreSQL `SEQUENCE` was not used: it is non-transactional and would leave 1, 2, 4 | **PASS** |
| 5f.15 | `last_message_at` tracks the newest committed message | `greatest(...)`, same transaction | **PASS** |
| 5f.16 | A rolled-back append does not advance `last_message_at` | | **PASS** |
| 5f.17 | **A conversation's project cannot be changed** | Database trigger, migration `0008` | **PASS** |
| 5f.18 | Nor emptied to NULL | Alpha cannot quietly become explicit-no-project | **PASS** |
| 5f.19 | A title may still be changed | The guard is on scope, not on the row | **PASS** |
| 5f.20 | **Switching project starts a new conversation and preserves the old** | WP-0.6 forward-only, at conversation scale | **PASS** |
| 5f.21 | No-project → project preserves the old conversation | It is not adopted later | **PASS** |
| 5f.22 | Resume recovers scope and history from the record | `via=conversation`, sequence order | **PASS** |
| 5f.23 | An explicit-no-project conversation resumes as explicit-no-project | Not unresolved, and it does not ask | **PASS** |
| 5f.24 | **An unknown conversation id fails clearly** | It does not quietly start a different conversation under the same name | **PASS** |
| 5f.25 | Appending to an unknown conversation fails clearly | | **PASS** |
| 5f.26 | **A stale session cannot change a resumed conversation's scope** | Session in Beta, Alpha conversation resumed → Alpha, and no Beta material in the payload | **PASS** |
| 5f.27 | A conversation naming a missing project raises rather than degrading | A dangling reference is a broken row, not a decision | **PASS** |
| 5f.28 | **History reaches the provider in sequence order** | user/Val/user; asserted on what the adapter was handed | **PASS** |
| 5f.29 | The current message is not duplicated | Persisted first, so history already ends with it | **PASS** |
| 5f.30 | **The persona appears exactly once, and only in `system`** | WP-0.5's guarantee, holding with memory in the request | **PASS** |
| 5f.31 | History is bounded but the record is not | 57 messages stored, 40 sent, nothing edited | **PASS** |
| 5f.32 | A stored `system` message is never sent as a turn | Application bookkeeping is not a participant | **PASS** |
| 5f.33 | **The model call names the conversation and the triggering user message** | And explicitly not Val's reply — it did not exist when the call was made | **PASS** |
| 5f.34 | Model-call attribution agrees with the conversation | | **PASS** |
| 5f.35 | A no-project conversation records `explicit_none` | | **PASS** |
| 5f.36 | The model call names the active persona | | **PASS** |
| 5f.37 | **Old provenance survives a later switch** | A new conversation writes new rows; it does not re-attribute old ones | **PASS** |
| 5f.38 | Project A retrieval returns only A | Sentinel facts one word apart | **PASS** |
| 5f.39 | Project B retrieval returns only B | | **PASS** |
| 5f.40 | Explicit no-project retrieves no project material | | **PASS** |
| 5f.41 | A project never retrieves no-project material | The mirror; no shared pool | **PASS** |
| 5f.42 | **A much stronger match in B cannot leak into A** | Beta's message repeats the query terms five times; Alpha returns only Alpha | **PASS** |
| 5f.43 | **The limit is spent only on the requested project** | The quieter leak: 20 Beta matches, limit 3, Alpha still gets its own history | **PASS** |
| 5f.44 | Recall carries provenance back to exact rows | message id, conversation, sequence, role all match the stored row | **PASS** |
| 5f.45 | **A second conversation recalls the first within the project** | A2 has no history of its own, so anything it knows came from retrieval | **PASS** |
| 5f.46 | **The assembled payload for A contains no B material** | At the boundary the criterion actually names | **PASS** |
| 5f.47 | An explicit-no-project exchange sends no project material | | **PASS** |
| 5f.48 | Retrieval excludes the current conversation | Its history is assembled in full; recalling it would duplicate it | **PASS** |
| 5f.49 | A query with no searchable terms recalls nothing | Empty is ordinary, not an error and not everything | **PASS** |
| 5f.50 | **Provider substitution preserves the whole conversation** | Different adapter, different provider name, no shared state | **PASS** |
| 5f.51 | **A fresh runtime sees the whole conversation** | New engine, pool, gateway, loader — nothing but the URL and the id | **PASS** |
| 5f.52 | **Retrieved history is never injected as system governance** | It is a delimited `user` turn; `system` holds the persona alone | **PASS** |
| 5f.53 | **Restricted material in retrieved history blocks the call** | Seeded into a *stored* message; provider not contacted, source untouched | **PASS** |
| 5f.54 | The budget ceiling sees the assembled payload including memory | A large recalled message raises the reservation | **PASS** |
| 5f.55 | **A provider failure leaves the user turn as real history** | One row, `(1, user)`, no fabricated reply | **PASS** |
| 5f.56 | The next turn after a failure takes the next sequence | The abandoned turn is not tidied away | **PASS** |
| 5f.57 | A transmitted call that failed keeps its provenance | | **PASS** |
| 5f.58 | **A Restricted refusal is raised, not returned as unanswered** | Found while writing 5f.53 — refusing to send is not failing to send | **FOUND AND FIXED** |
| 5f.59 | `projects.status` still has no resolution authority | Seven values, one identical resolution and retrieval | **PASS** |
| 5f.60 | **Trap — never approved** | Enthusiasm retrieved and labelled discussion; nothing asserts approval | **PASS** |
| 5f.61 | **Trap — approved then superseded** | Both halves retrieved; order recoverable from `sequence` | **PASS** |
| 5f.62 | **Trap — mentioned once then abandoned** | | **PASS** |
| 5f.63 | Trap material does not cross projects | Beta's "approved on the fourth of March" never reaches an Alpha payload | **PASS** |
| 5f.64 | `0008` downgrade is clean when no conversation was held | And re-appliable | **PASS** |
| 5f.65 | **`0008` downgrade refuses once conversations exist** | It would leave their scope silently rewritable | **PASS** |
| 5f.66 | The message sequence guarantees predate WP-0.7 | Audited before `0008`; `0001` already had both, so nothing was added | **PASS** |

### 5f-live — the real acceptance, against the authoritative store

| # | Claim | Evidence | Result |
|---|---|---|---|
| 5f.67 | A real conversation, a real reply | A1, `gpt-5.5`, $0.024430 | **PASS** |
| 5f.68 | **An actual PostgreSQL restart** | `pg_postmaster_start_time` moved from 2026-08-17 15:32:05 to 2026-08-18 10:32:03 | **PASS** |
| 5f.69 | **Resume by id in a new process recovers scope and history** | The creating process had already exited | **PASS** |
| 5f.70 | **Continuity across the restart** | "catalogued as **CN-4417** […] **cobalt blue**", from PostgreSQL alone | **PASS** |
| 5f.71 | Cross-conversation recall, live | A2 retrieved 4 A1 messages, ids recorded | **PASS** |
| 5f.72 | **Conflicting Beta detail never reaches Alpha** | CN-9902/amber absent from retrieval and from the answer | **PASS** |
| 5f.73 | No-project receives neither project, live | Retrieval returned 0 | **PASS** |
| 5f.74 | **The three trap questions, real retrieval and real provider** | Correct negatives, no confabulated dates | **PASS** |
| 5f.75 | Provider independence, live | A1 continued through an OpenAI-only gateway; everything preserved | **PASS** |
| 5f.76 | Every WP-0.7 model call carries full provenance | 16/16 conversation, message, persona; 0 attributed to a non-user message; 0 disagreeing with their conversation's project | **PASS** |
| 5f.77 | Gapless across the whole store | 0 conversations with a gap or duplicate | **PASS** |

> **WP-0.7 is submitted as IMPLEMENTED, ready for acceptance.** The governing
> criterion — including the trap-question amendment of 15 August 2026 — is
> satisfied. Full account: `VAL_WP07_Conversation_Memory_Audit.md`.

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
| Migration / schema | 18 | — |
| Backup / restore | 8 | **1** (4.8) |
| Gateway / providers | 24 | 3 (5.9, 5.10, 5.11) |
| Persona loading | 29 | — |
| Project resolution | 35 | — |
| Project resolution — corrective, round one | 14 | — |
| Project resolution — corrective, round two | 17 | — |
| Eligibility / Restricted | 12 | — |
| Security | 6 | — |
| Build | 4 | — |
| Conversation loop and memory | 66 | — |
| Conversation memory — live acceptance | 11 | — |
| **Automated tests** | **555 passing** | — |

**Four outstanding items, none a code defect** — down from five. Three need the
Anthropic account balance; one needs a restore pulled back from B2.

The 17 August corrective work added 97 tests and, more usefully, closed two gaps
that no test had been asserting at all: the ceiling was being enforced against
historical spend rather than against the call being proposed, and a provider
failure after transmission was being recorded as a $0.00 call. Both are now
proved in the negative — the provider is not contacted, and the false zero is
refused by the database itself. Full account: `VAL_WP04_Corrective_Audit.md`.
