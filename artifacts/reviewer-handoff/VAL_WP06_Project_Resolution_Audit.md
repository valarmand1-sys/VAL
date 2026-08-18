# VAL — WP-0.6 Project Resolution and Attribution Audit

**Authorised by Lord Armand on 17 August 2026**, following the executive acceptance of WP-0.5 as COMPLETE.

**One reading rule, carried throughout.** *Implemented*, *verified*, and *complete* are different states and are never used interchangeably.

---

## A. Pre-work state

| | |
|---|---|
| Branch | `master` |
| Commit | `fe707a723ce2315036b971028c5884b32f03f17a` |
| Working tree | Clean |
| Alembic revision | `0005_persona_provenance` (head) |
| `projects` | **0** |
| `conversations` | **0** |
| `messages` | **0** |
| `model_calls` | **9** |
| `personas` | 1 — revision 1, authored v1.2, active |
| WP-0.5 | **COMPLETE**, accepted 17 August |
| WP-0.6 | **NOT STARTED** — no resolver module, and no `resolve_project`, `ProjectResolution`, `ExplicitNoProject`, or `AmbiguousProject` symbol anywhere in the tree |

**Existing project constraints:** foreign keys on `project_id` from `conversations`, `model_calls`, `execution_events`, `deliberations`, `ideas`, and `budget_reservations`, all `NO ACTION`; `uq_projects_slug` UNIQUE on `projects.slug`. **`projects.name` carries no uniqueness constraint** — which is what makes duplicate display names a real case rather than a hypothetical one.

**Indexes:** `pk_projects`, `uq_projects_slug`. Nothing else.

### The governing criterion, quoted

> **WP-0.6 — Project resolution and attribution**
>
> **Done when:** every exchange is attributable to a project or explicitly to none, and resolution is deterministic.
>
> **Verified by:**
> - Resolution uses explicit names, IDs, and session state. Application code sets final scope; no model output determines it.
> - Ambiguous project reference produces a question, never a guess. Test with a name matching two projects.
> - No message exists with an unresolved project state — nullable means "explicitly none," and the distinction is queryable.

No conflict between the repository and this assignment. The schema comment written at WP-0.2 had already deferred exactly this: *"The distinction between 'explicitly none' and 'not yet resolved' is not expressible in this schema; WP-0.6 requires it to be queryable, and the resolution is recorded there, not invented here."*

---

## B. Final source commit

**`8cc04134e4d38c2f2c19fdaf256d5dc83937d182`** — `8cc0413`.

The commit adding this bundle is one later and touches `artifacts/reviewer-handoff/` only, under the established convention. `git diff --name-only 8cc0413 HEAD` prints nothing outside that directory.

---

## C. Files changed

### New

| Path | What it is |
|---|---|
| `packages/domain/src/val_domain/project.py` | The three resolution states, and `ProjectScope` — the union that excludes ambiguity |
| `packages/policy/src/val_policy/project_resolution.py` | The pure deterministic resolver, precedence, and exact matching |
| `packages/gateway/src/val_gateway/projects.py` | Catalogue loading, existence validation, and the session |
| `packages/gateway/src/val_gateway/exchange.py` | The application boundary: preflight → resolve → clarify-or-converse |
| `packages/policy/tests/test_project_resolution.py` | 40 pure tests |
| `packages/gateway/tests/test_project_attribution.py` | 24 tests against real PostgreSQL |

### Modified

| Path | Change |
|---|---|
| `packages/gateway/src/val_gateway/gateway.py` | `converse` takes a required `ProjectScope` — see §K |
| `packages/gateway/tests/test_persona.py` | Four call sites pass an explicit scope. Assertions unchanged. |

---

## D. Schema changes

# **NONE.**

Deliberately, and the reasoning is the design.

`04-layer-0.md` §2.1 already spends the one meaning a nullable `project_id` has: NULL means *explicitly no project*. It therefore cannot also mean *nobody has worked out which project this is yet* — those two are opposite in consequence, and storing them in the same field is how an unanswered question eventually gets read as an answer.

The assignment's §20 asks for the smaller resolution and it is also the better one: **add the third state to the domain, and eliminate it before persistence.** No column, no migration, no retrofit of old rows, and no new way for the schema to be wrong.

The distinction WP-0.6 requires to be **queryable** is therefore satisfied structurally: `project_id IS NULL` returns exactly the explicit-none set, because the only value that can write a NULL is an `ExplicitNoProject`, and an unresolved exchange never reaches the database at all. Proved by `test_every_persisted_null_project_id_is_a_decision`, which runs resolved, explicit-none, and unresolved exchanges together and asserts the unresolved ones produced no row.

---

## E. The resolution-state model

Three states in the domain, two of which can be persisted:

| State | Means | Persists as |
|---|---|---|
| `ResolvedProject` | A specific existing project, deterministically identified | its `id` |
| `ExplicitNoProject` | This exchange is deliberately outside any project | **NULL** |
| `AmbiguousProject` | Scope cannot be settled safely | **nothing — it must be asked about** |

`AmbiguousProject` carries a `reason`, the `question` to put, and the `candidates` it could not choose between. **It has no `project_id` attribute at all** — the absence is the point, and a test asserts it, because there is then nothing on it that could be persisted by accident.

Every resolution records the `ResolutionSource` that decided it, so *"why is this attributed to Alpha?"* is answerable from the result rather than by re-deriving the reasoning.

---

## F. Precedence

**No governing document defines an order.** WP-0.6 names the signals and requires determinism without ranking them, so the order recommended in the authorisation is adopted — and recorded in the module, because it is the kind of decision that becomes invisible once it works.

| | Signal | Source |
|---|---|---|
| 1 | Trusted application project id | `TRUSTED_APPLICATION_ID` |
| 2 | Explicit selection or switch in this interaction | `EXPLICIT_SELECTION` |
| 3 | The conversation's established project | `CONVERSATION` |
| 4 | The session's current project | `SESSION` |
| 5 | An unambiguous exact canonical name or slug | `EXACT_REFERENCE` |
| 6 | An explicit "this has no project" instruction | `EXPLICIT_NONE_INSTRUCTION` |
| 7 | Otherwise | **unresolved** |

**Higher authority wins outright; comparable authority in conflict asks.** A session in Alpha and a mention of Beta is not a case for preferring one — it is genuinely unclear whether the user means *switch to Beta* or *while working in Alpha, note that Beta did this*. Guessing is how an exchange about Beta gets filed under Alpha and stays there. So it asks, and switching is the explicit selection at level 2, which outranks everything below it and leaves nothing to interpret.

`PRECEDENCE` is declared as data and a test asserts it equals `tuple(ResolutionSource)` — a precedence documented in one place and implemented in another drifts.

**Matching is exact only.** Exact id, exact slug, exact canonical name. Normalisation is one rule — casefold, strip, collapse internal whitespace — applied to **both sides of every comparison**, tested idempotent, and tested *not* to resolve near-misses (`Project Alpah`, `Alpha`, `Projekt Alpha` all fail). No fuzzy matching has authority in WP-0.6.

---

## G. Explicit no-project

A genuine state, reached only by an explicit instruction or an explicit session selection, and the **only** thing in the system that writes a NULL `project_id`.

No fake "General" project was invented to avoid NULL. NULL is the right representation; what it needed was a guarantee about what could produce it, and that is what `ProjectScope` provides.

`ExplicitNoProject` selected into a session **persists as a decision**: later unspecified exchanges stay at no-project rather than going back to asking, because deciding to work outside every project is a decision and re-asking it every turn would make it useless.

---

## H. Ambiguity

Produces a `ClarificationNeeded` — **never a guess, never a NULL, never a row.**

Five cases produce it, each with its own reason and question: a name matching several projects, an identifier that resolves to nothing, conflicting signals of comparable authority, an established scope pointing at a project that no longer exists, and silence.

**Silence is the important one.** Nobody said anything about scope. That is not a decision to work outside every project; it is the absence of a decision, and the resolver says so:

> *"Which project is this for? I can also file it under no project, but I will not assume that — an exchange nobody scoped and an exchange deliberately outside every project are different things."*

**The question names only the candidates**, never the catalogue — asserted by a test that checks unrelated projects do not appear.

**A defect found by running the acceptance cases, not by reading the code.** Two projects both named `Winter Light` produced:

> *"I have 2 projects matching 'Winter Light': Winter Light and Winter Light. Which one do you mean?"*

A clarification that does not distinguish its candidates has not clarified anything. It now falls back to the slug, which is unique by database constraint, and only where the names actually collide:

> *"I have 2 projects matching 'Winter Light': Winter Light (winter-light-series) and Winter Light (winter-light-short). Which one do you mean?"*

---

## I. Session state

**Application-owned, in this process, keyed by nothing a provider can see.**

| State | Means |
|---|---|
| unset | Nothing selected. **Unresolved** — the next exchange asks. |
| a project | Selected; unspecified exchanges resolve to it |
| explicit none | The user chose to work outside every project |

`unset` and `explicit none` are both "no project id", and collapsing them would make a fresh process indistinguishable from a deliberate decision — the same confusion the whole work package exists to remove. `clear()` returns to **unset**, not to none.

### Lifetime, stated plainly

**The process, and no longer.** Session state is not written to the database and does not survive a restart, because persistent conversation state is WP-0.7's and pulling it forward would be building a later layer early.

After a restart, scope is **unset** — which is unresolved, not no-project — so the next exchange asks rather than assuming. That is the safe direction to fail.

`select()` takes a `ProjectScope`, so an ambiguous outcome cannot be selected: the session can only ever hold something that was settled.

---

## J. Project switching

**Forward only.** `select()` changes what future exchanges resolve to and touches no stored row — no conversation, no message, no model call, no execution history.

Switching is the **explicit selection at precedence 2**, which outranks the conversation and the session below it, so it needs no special case in the resolver: the same rule that resolves everything else resolves a switch.

Proved: an Alpha exchange, a switch to Beta, a Beta exchange — Alpha's row still says Alpha and there is still exactly one of them. And Alpha → explicit-none preserves Alpha's history while the new exchange records NULL.

---

## K. Application authority over model output

**Structural, in three layers.**

1. **The resolver is a pure function** over a catalogue snapshot. No database handle, no adapter, no network. There is no path by which a model's opinion could become scope because there is no path by which a model could be consulted at all. A test parses the module's import graph and asserts it imports no provider and no gateway.
2. **Model output can enter only as `mentioned_reference`** — a *candidate*. It is looked up exactly like any other reference, and it resolves only when the catalogue agrees and nothing of higher authority disagrees.
3. **`converse` requires a `ProjectScope`.** This replaced `project_id: UUID | None = None`, which was wrong twice over: the default let a caller who said nothing about scope silently write NULL, and `None` had to mean both a decision and the absence of one. A required union type is a guarantee the type checker enforces at every call site; a runtime check is one the next caller can forget.

Tested with a model that is confident and wrong: it names `Project Beta` while the session says Alpha. The result is a **question**, not Beta. And a model naming a project that does not exist creates no scope at all.

---

## L. Persistence attribution

Every Layer 0 path carrying `project_id` was audited: `conversations`, `model_calls`, `execution_events`, `deliberations`, `budget_reservations`, `ideas`.

**Only `model_calls` is written by a WP-0.6 exchange today.** `execution_events` and `deliberations` have no write path until WP-0.8 and WP-0.9, and `conversations` and `messages` until WP-0.7. Nothing was built to populate a table that is not yet active — but `attribution_of(scope)` is the single function that turns a resolution into a column value, so when those paths arrive there is one answer to how they attribute rather than one per table.

For a resolved exchange, `model_calls.project_id` is the resolved id. For explicit none it is NULL by decision. For an unresolved exchange there is no row.

---

## M. Cross-project safety

WP-0.7 owns retrieval isolation and none was built. What WP-0.6 owes is that bad attribution cannot create future leakage, and that is what is tested — with **deliberately confusable fixtures**, because a suite whose projects are named "A" and "B" proves nothing about the case that bites.

| Proof | Result |
|---|---|
| Four alternating Alpha/Beta exchanges | Exactly 2 each; no crossing |
| Switching A → B | Alpha's row unchanged, still exactly one |
| Ambiguous reference | Neither A nor B attribution — no row at all |
| Stale session in Alpha, explicit call about Beta | Recorded as Beta |
| Messages naming Alpha repeatedly, exchange scoped to Beta | **Recorded as Beta** — the provider's view of the conversation contributes nothing |

---

## N. Persona stability

A project changes context scope. It does not change who Val is.

Three exchanges — Alpha, Beta, explicit none — produce **exactly one distinct `persona_id`** across all their `model_calls` rows, and the active persona's id, persistence revision, and authored semantic version are identical before and after. Confirmed live in acceptance case H.

---

## O. Real acceptance cases

Run against the authoritative store with real fixture projects, through `start()` and the normal exchange path.

| | Case | Result |
|---|---|---|
| **A** | "Work on Project Alpha" | **Resolved** — Project Alpha, via `explicit_selection` |
| **B** | Follow-up without restating | **Resolved** — Project Alpha, via `session` |
| **C** | Explicit switch to Project Beta | Future scope Beta; **Alpha's history unchanged** |
| **D** | "This isn't for a project." | **ExplicitNoProject**, `project_id = None` |
| **E** | Ambiguous "Winter Light" | **Clarification**, `multiple_name_matches`, **0 model calls written** |
| **F** | Invalid Project ID | **Clarification**, `unknown_identifier`, no attribution, **0 model calls written** |
| **G** | A real model call after resolution | `gpt-5-5`, 4,050/83 tokens, **$0.022740**. `model_calls.project_id` = `01a0122f-fbc6-7601-94ed-9f2980298808` = Project Alpha |
| **H** | Persona across the switch | `01a01169-…d8b1`, revision 1, v1.2 — **unchanged**, and the call carries it |

**Case G's response**, verbatim:

> Good evening, my lord. Begin with the decision that becomes more expensive by tomorrow.

The Anthropic route failed on its billing blocker and the router fell back to OpenAI, as it has since that correction. The failed attempt was recorded with unknown cost **and Alpha's project id**, which is correct: it was transmitted.

Attribution in the authoritative store afterwards: `project-alpha` 2, `(none)` 9 — the nine being the pre-existing rows written before projects existed.

---

## P. Tests

| Suite | Result |
|---|---|
| `infrastructure/ci/tests` | **69 passed** |
| `packages/domain/tests` | **125 passed** |
| `packages/policy/tests` | **95 passed** |
| `packages/gateway/tests` | **148 passed** |
| **Total** | **437 passed**, 0 failed |

373 before WP-0.6. **+64 tests** — 40 pure resolution, 24 attribution against real PostgreSQL.

All 24 cases of the assignment's §18 matrix are covered; each test's docstring names the case it discharges.

| Check | Result |
|---|---|
| `ruff check` / `ruff format --check` | **All checks passed** |
| `mypy` (strict) | **Success — 43 source files** |
| `check_boundaries.py` | **Holds across 8 components** |
| `lint-imports` | **3 kept, 0 broken** |
| `check_pins.py` | **No placeholder across 126 files** |
| `check_secrets.py` | **No credential-shaped literal across 128 files** |
| Alembic | **Unchanged at `0005`** — no migration was added |

**No test was weakened.** Four WP-0.5 tests were updated because `converse`'s signature changed; each now passes an explicit `ExplicitNoProject()` — which is the honest scope for an exchange about the persona — and **every assertion in them is unchanged**.

---

## Q. CI and the source snapshot

**`VAL_Source_Snapshot_8cc0413.zip`** — 133 entries, 387,318 bytes, SHA-256
`cc580c1c05ec4c49f3f52d77ac74626fe89ecf4817ae7c21bfbfea32700221ec`.

Built from the final source commit `8cc0413` and excluding
`artifacts/reviewer-handoff/`, under the established convention. The commit
adding it touches only that directory, so the source inside is byte-identical to
the source at HEAD — checkable with `git diff --name-only 8cc0413 HEAD`.

**No governing document changed in WP-0.6**, so the `governing/` copies and
their hashes are carried forward unrefreshed. That is worth stating rather than
leaving to be inferred: WP-0.6 needed no amendment to any baseline, which is the
first work package since WP-0.2 that did not.

**No known secret.** Built from `git ls-files`, so `.env` cannot appear by
construction and its absence was verified. Positively verified present:
`project.py`, `project_resolution.py`, `exchange.py`. The same three scan hits as
every previous round, each already inspected by hand and re-confirmed.

CI result recorded on push; see `VAL_Engineering_State_Handoff.md` §I.

---

## R. Defects and limitations

### One defect, found by running rather than by reading

The clarification for two projects sharing a display name named them both identically and was unanswerable. Corrected to fall back to the slug where names collide, and only there. Two tests lock both halves.

### Limitations, stated

- **Session lifetime is the process.** Restarting loses the selection and returns to unset, which asks. Persistence across restart is WP-0.7's and was not pulled forward.
- **Signals, not prose.** The resolver takes a record of signals; turning "work on the animation project" into one is the interface's job (WP-0.10). This is deliberate — it is what keeps a parser's guess from acquiring authority it was never granted — but it does mean WP-0.6 delivers no natural-language command parsing, and the acceptance cases drive the boundary explicitly.
- **`conversations` and `messages` have no write path yet**, so the conversation-established signal is currently supplied by the caller rather than read from a stored conversation. The resolver handles it identically either way; WP-0.7 will supply it from the store.
- **Ambiguity has no persistent pending state.** A clarification is returned to the caller, who holds it for the length of the interaction. Nothing is written, which is the requirement; a pending question surviving a restart would be WP-0.7 memory.

---

## S. WP-0.6 recommendation

**COMPLETE.**

Every condition in §22 of the assignment is met and evidenced:

| Condition | Status |
|---|---|
| Every normal exchange deterministically resolved before attributed persistence | ✅ |
| Unresolved distinct from explicit none | ✅ three states, and only two persist |
| Ambiguity asks rather than guesses | ✅ five reasons, each with its own question |
| Application code owns final scope | ✅ pure resolver, no path to a model |
| Model output cannot assign project authority | ✅ candidate only; import graph asserted |
| Supplied IDs existence-validated | ✅ a well-formed UUID is not evidence |
| Session and current-conversation resolution work | ✅ |
| Switching preserves history | ✅ forward-only, nothing rewritten |
| Persistence records agree on attribution | ✅ one `attribution_of` |
| Explicit no-project is queryable | ✅ `project_id IS NULL` is exactly that set |
| No unresolved state persisted as explicit none | ✅ structurally — wrong type to pass |
| Cross-project attribution tests pass | ✅ with confusable fixtures |
| Persona identity unchanged across projects | ✅ one persona id across all three |
| Real acceptance cases pass | ✅ all eight |
| All tests and CI pass | ✅ 437, six jobs |
| Evidence package complete | ✅ this document |

Unlike WP-0.5, **no acceptance condition here requires a human reading**: every criterion is a mechanical property of code and records, and all of them are discharged. The recommendation is therefore mine to make, and I make it — subject, as always, to your review.

---

## T. Executive decisions required

**One, narrow, and not blocking.**

### `projects.status` has no defined vocabulary

The column exists and is `NOT NULL`, and no baseline enumerates its values or attaches meaning to any of them. WP-0.6 therefore **treats no status as disqualifying**: an archived project resolves by slug like any other, and a test asserts it.

Inventing a rule — that archived projects may be referenced but not made current, say — would be writing policy this implementation is not entitled to write, so it is surfaced rather than guessed at, per §10 of the assignment.

**Nothing is blocked.** Today there are four fixture projects and no archived one in real use. **Recommendation: leave it until there is a real archived project**, then decide two things together — the status vocabulary, and whether any value restricts conversation. Deciding it now would be deciding it without the case that would inform it.
