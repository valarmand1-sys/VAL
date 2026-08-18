# VAL — WP-0.6 Corrective Audit

**Two rounds of independent source review found six acceptance defects between them.** All six were confirmed against the source before anything was changed. This document records both rounds and preserves the lineage of the acceptance that preceded them.

| Round | Snapshot reviewed | Found | Recorded in |
|---|---|---|---|
| One | `VAL_Source_Snapshot_8cc0413.zip` | 4 defects | Sections A–J |
| Two | `VAL_Source_Snapshot_4ff6838.zip` | 4 fixes confirmed, **2 further defects** | Sections K–R |

**Round two is appended, not merged.** Sections A–J stand as written on 18 August and are not edited to read as though six findings were known at once. Round one's four corrections were reviewed and confirmed correct; nothing in it was withdrawn.

---

## A. Acceptance lineage — preserved, not rewritten

| Date | Event |
|---|---|
| 17 Aug 2026 | WP-0.6 implemented, source commit `8cc0413`, bundle `ef3e613` |
| 17 Aug 2026 | **Accepted COMPLETE** by Lord Armand, recorded at `6a89f7a` |
| 18 Aug 2026 | **Reopened** — independent source review of the accepted snapshot found four defects |
| 18 Aug 2026 | Corrected at source commit `4ff6838` |
| 18 Aug 2026 | **Reopened again** — second review of `4ff6838` confirmed all four fixes and found two more defects |
| 18 Aug 2026 | Corrected at source commit `699ed24` |

**The previous acceptance is historical evidence and stands as written.** `VAL_WP06_Project_Resolution_Audit.md` is not edited to pretend the defects were known then; it records what was believed and demonstrated on 17 August, which is what an evidence record is for. This document records what was found afterwards.

**Status during and after this correction:**

| | |
|---|---|
| WP-0.6 | **IMPLEMENTED / ACCEPTANCE BLOCKED** → returns to COMPLETE only on re-acceptance |
| WP-0.7 | **NOT STARTED** |

**Why the reopening was right.** The acceptance was recorded honestly on the evidence available, and the evidence was insufficient — not falsified. Three of the four defects were *documented in the source*: the resolver's own docstring described the model-authority rule as *"resolves only when nothing of higher authority disagrees"*, which is the defect stated plainly and then not recognised. A reviewer reading the code found in an afternoon what the author had written down and walked past. That is the case for independent review, and it is the reason WP-0.7 was worth stopping for.

---

## B. Findings — every one confirmed

### Finding 1 — model output could establish project scope · **CONFIRMED**

The governing rule (`04-layer-0.md` WP-0.6) is *"application code sets final scope; no model output determines it."*

`ProjectSignals.mentioned_reference` was documented as the field a model's suggestion enters through. Precedence 5 resolved it directly:

```python
# 5. An exact reference, with nothing established to weigh it against.
if signals.mentioned_reference is not None:
    resolved = _from_reference(...)
    if not isinstance(resolved, AmbiguousProject):
        return resolved  # <- a model just set scope
```

**The existing test only ever exercised the case where a session disagreed.** With no conversation and no session there is nothing of higher authority to disagree, so an exact match from any origin resolved outright.

Verified before changing anything:

```
untrusted exact "Project Beta", nothing else  ->  ResolvedProject(Beta)
```

### Finding 2 — established explicit-no-project conversation · **CONFIRMED, and worse**

`_established_scope` required `conversation_project_id is not None` to treat a conversation as established. `04-layer-0.md` §2.1 says a NULL conversation project means *deliberately outside every project* — a decision, not an absence.

Two consequences, verified live:

```
established + NULL project                    ->  AmbiguousProject   (should be ExplicitNoProject)
established + NULL + session Alpha            ->  ResolvedProject(Alpha) via session
```

**The second is the dangerous one and was not in the review's description.** A conversation the user had deliberately placed outside every project was **silently taken over by whatever the session held**. WP-0.7 persists and resumes conversation scope, so it would have become durable — a conversation permanently reattributed to a project nobody put it in.

### Finding 3 — clarification candidates indistinguishable · **CONFIRMED**

The human-facing question had been corrected to show slugs, but `ClarificationNeeded.candidates` remained `tuple[str, ...]` of names:

```
candidates payload: ('Winter Light', 'Winter Light')
distinguishable?    False
```

A question the caller can put and cannot interpret the answer to.

### Finding 4 — NULL still carried two meanings · **CONFIRMED, in two places**

The claim *"`project_id IS NULL` means exactly explicit no-project"* held for what the corrected `converse` wrote and failed for the table:

1. **Nine rows predate WP-0.6.** Six from WP-0.4's live verification before `projects` had a row; three from WP-0.5's persona work. None is a decision.
2. **`GatewayRequest.project_id: UUID | None = None`** — with a default, and `Gateway.complete()` persisted it directly. Any caller could write a fresh, semantically empty NULL without deciding anything.

---

## C. Corrections

### 1 — trust is a field, not a comment

`mentioned_reference` is **removed** and replaced by two fields:

| Field | May resolve? |
|---|---|
| `trusted_reference` | **Yes** — UI selection, exact command parsed by application code, trusted identifier |
| `untrusted_candidate` | **Never** — a model or heuristic, however exactly it matches |

Removing the old field rather than deprecating it meant **every stale call site failed to type-check**, which is how they were found rather than by searching.

An untrusted candidate that matches a real project produces `UNTRUSTED_SUGGESTION_ONLY` — a question **carrying the suggestion**, so confirming it is one answer rather than a fresh interrogation. One that matches nothing produces no candidate at all.

**Conflict detection still sees both** (`any_reference`): a model naming Beta while the session says Alpha remains worth asking about, even though it could never have resolved Beta.

### 2 — an established scope may be a decision to have none

`_established_scope` now returns `(project | None, source)`, distinguishing three states where it previously collapsed two:

| Signals | Before | After |
|---|---|---|
| established, NULL project | `AmbiguousProject` | **`ExplicitNoProject` via conversation** |
| established NULL + session Alpha | `ResolvedProject(Alpha)` | **`ExplicitNoProject` via conversation** |
| established NULL + unspecified | `AmbiguousProject` | **`ExplicitNoProject`** |
| established NULL + explicit selection Beta | Beta | Beta *(unchanged — precedence 2 > 3)* |
| established NULL + reference to Beta | — | **`CONFLICTING_SIGNALS`, asks** |

Forward-only switching is unchanged; no historical attribution is rewritten.

### 3 — candidates carry stable identity

`ProjectCandidate(project_id, name, slug)`. `status` is deliberately excluded: it has no settled semantics (executive decision, 17 August), and a field with no meaning does not belong in a payload whose whole job is to identify.

### 4 — the meaning is stored beside the value

`ProjectAttribution`: `resolved` | `explicit_none` | `legacy_unknown`.

`GatewayRequest` now requires **both** `project_id` and `project_attribution`, with **no defaults**, and a validator enforcing that they agree in both directions. `LEGACY_UNKNOWN` is **rejected** on any request — it is a read state describing history, never a way for new code to avoid deciding.

**`assemble` had the same defect in miniature** and was corrected the same way: it took `project_id` and `project_attribution` separately with a default on the second, so a caller could pass a real id alongside `EXPLICIT_NONE`. It now takes a `ProjectScope`, which cannot disagree with itself. **The new validator caught exactly this in my own test fixture while I was writing the fix** — which is the argument for the validator in one line.

### 5 — status non-authority, locked behaviourally

The same project identity resolves identically under seven arbitrary status strings — `active`, `archived`, `disabled`, `""`, `"on hold"`, `"DELETED"`, `"whatever"` — by slug, by name, and by id. Behavioural, not a source-text assertion: what matters is that no status changes the outcome. A future governing decision may change this test deliberately, together with the vocabulary it defines.

---

## D. Schema changes

**Migration `0006_project_attribution`**, revises `0005_persona_provenance`.

- New enum `model_call_project_attribution`.
- `model_calls.project_attribution`, **NOT NULL**.
- `ck_model_calls_resolved_attribution_has_a_project` — `resolved` ⟺ a real id.
- `ck_model_calls_legacy_attribution_is_reserved_to_history` — `legacy_unknown` refused on any row created from 18 August 2026.
- `model_calls_accounted` dropped and recreated so the view exposes the new column.

### Why a column and not a view

`0004` used a view for the fabricated zero costs, and that was right **there**: the rule identifying them was exact — the superseded code wrote `0/0/$0` on every error, unconditionally — so it was computable from data already present.

**No such rule exists here.** Distinguishing a deliberate no-project decision from a pre-WP-0.6 NULL requires knowing *when the concept existed*. A view could express that only as a date comparison — a rule nobody reading a single row could apply, and one that would misclassify any future backdated row. The fact is not derivable, so it is recorded.

### Downgrade

**Clean against real data**, unlike `0002`, `0003`, and `0005`. Those refuse because reversing them would destroy captured facts. This one adds a statement *about* facts and stores none of its own, so removing it loses an interpretation and no evidence. Verified: 6 up → 6 down → 6 up from empty.

---

## E. The nine historical rows

**Not one `project_id` was rewritten.**

| | Before | After |
|---|---|---|
| 9 rows | `project_id` NULL | `project_id` **NULL**, `project_attribution = 'legacy_unknown'` |
| 2 rows | `project-alpha` | `project-alpha`, `project_attribution = 'resolved'` |

The backfill rule is exact rather than a guess: every existing NULL predates project scope entirely, and every existing non-NULL was written by the corrected WP-0.6 path.

```
project_id IS NOT NULL  ->  'resolved'
project_id IS NULL      ->  'legacy_unknown'
```

Applied to the authoritative store after an on-demand backup per `01-architecture.md` §9.2. Lineage is untouched — what was added is a statement about what was already there, which is the difference between annotating history and editing it (invariant 14).

---

## F. Tests

| Suite | Result |
|---|---|
| `infrastructure/ci/tests` | **69 passed** |
| `packages/domain/tests` | **126 passed** |
| `packages/policy/tests` | **120 passed** |
| `packages/gateway/tests` | **158 passed** |
| **Total** | **473 passed**, 0 failed |

437 before this round. **+36 tests.**

**No test was weakened.** Several call sites changed because signatures changed — `converse`, `assemble`, and `GatewayRequest` all gained required arguments — and **every assertion in them is unchanged**. The four WP-0.5 persona tests, the router suite, and the budget suite all still assert exactly what they asserted before.

### The corrective cases

| Finding | Proof |
|---|---|
| 1 | Untrusted exact match with **nothing** of higher authority → asks, never resolves; four normalisations of a real name all ask; a model-produced UUID resolves nothing; hallucinated names produce no candidate; **the same bytes resolve from the trusted field and not the untrusted one**; a trusted reference beats an untrusted one |
| 2 | All five cases A–E, plus a guard that an established *project* conversation still resolves normally |
| 3 | Duplicate names give two distinct ids and two distinct slugs; the question and the payload describe the same projects |
| 4 | Legacy NULL never reads as explicit-none; new explicit-none records a decision; new resolved records a real id; a request omitting attribution is refused; a request claiming `LEGACY_UNKNOWN` is refused; contradictory pairs are refused in both directions; **the database refuses a new legacy row**; analytics separates the two kinds of NULL |
| 5 | Seven status strings, three lookup paths, identical outcomes |

### Static checks

| Check | Result |
|---|---|
| `ruff check` / `ruff format --check` | **All checks passed** / 89 files |
| `mypy` (strict) | **Success — 43 source files** |
| `check_boundaries.py` | **Holds across 8 components** |
| `lint-imports` | **3 kept, 0 broken** |
| `check_pins.py` | **No placeholder across 128 files** |
| `check_secrets.py` | **No credential-shaped literal across 130 files** |
| Alembic | **6 up / 6 down / 6 up**, clean from empty |

---

## G. WP-0.6 re-verification

The full original matrix, re-run against the corrected code.

| Requirement | Result |
|---|---|
| No model-origin candidate can establish final scope | ✅ |
| Established project conversation persists correctly | ✅ |
| Established explicit-no-project conversation persists correctly | ✅ |
| Session cannot hijack an explicit-no-project conversation | ✅ |
| Duplicate-name candidates structurally distinguishable | ✅ |
| Legacy NULL not treated as explicit none | ✅ |
| New NULL possible only through an explicit no-project decision | ✅ |
| Project status has no resolution authority | ✅ |
| Project A/B cross-attribution protections hold | ✅ |
| Persona attribution unchanged | ✅ |

### The eight acceptance cases, re-run live

| | Case | Result |
|---|---|---|
| A | "Work on Project Alpha" | Resolved, via `explicit_selection` |
| B | Follow-up unspecified | Resolved Alpha, via `session` |
| C | Switch to Beta | Future scope Beta; Alpha history untouched |
| D | "This isn't for a project." | `ExplicitNoProject`, `project_id = None` |
| E | Ambiguous "Winter Light" | Clarification; candidates **distinguishable** — `winter-light-series` / `winter-light-short`; 0 rows |
| F | Invalid Project ID | Clarification, `unknown_identifier`; 0 rows |
| G | Real model call | `gpt-5-5`, **$0.021615**; `project_id` = Project Alpha; `project_attribution = 'resolved'` |
| H | Persona across the switch | Revision 1, v1.2 — unchanged; the call carries it |

**Case G's response**, verbatim:

> Good evening, my lord. What shall we turn our attention to?

Attribution in the authoritative store: `resolved` / `project-alpha` — 4; `legacy_unknown` / NULL — 9.

---

## H. CI and commits

| | |
|---|---|
| Pre-correction HEAD | `6a89f7acfb7b3490d3af0805aa6d7baf6b47e76b` |
| **Final source commit** | **`4ff6838237f3d6168714ada88d9f7d7f877fadda`** |
| Final HEAD | recorded on the bundle commit; see the handoff §A |

**`VAL_Source_Snapshot_4ff6838.zip`** — 134 entries, 400,102 bytes, SHA-256
`0972f207886aafacb6cc263291f747b07dcb8171cc83d4299191f17db135df42`.

Built from the final source commit, excluding `artifacts/reviewer-handoff/`, under
the established convention. **No governing document changed this round** — the
corrections were entirely to code and its tests — so the `governing/` copies and
their hashes are carried forward unrefreshed.

**No known secret.** Built from `git ls-files`; `.env` cannot appear by
construction and its absence was verified. Migration `0006` verified present.
The same three scan hits as every previous round, each already inspected by hand.

CI result recorded on push; see `VAL_Engineering_State_Handoff.md` §I.

---

## I. WP-0.6 recommendation

**Ready to return to COMPLETE, subject to your acceptance.**

Every defect the review found is corrected, each with tests that fail against the old behaviour. Three of the four were closed **structurally** rather than by adding a check: a removed field, a required argument, and a rejected enum value, so the old mistakes are no longer expressible rather than merely no longer made.

I do not mark it COMPLETE myself. It was accepted once and the acceptance did not hold, and the appropriate response to that is not to re-award the status unilaterally.

---

## J. Executive decisions required

**NONE.**

The `projects.status` ruling of 17 August is unchanged and now has a behavioural regression test locking it. Its revisit trigger — a real archived project, or a lifecycle feature that needs to know whether a project is live — is unchanged and remains recorded as item 8 in `VAL_Open_Decisions.md`.

---
---

# Round two — review of `VAL_Source_Snapshot_4ff6838.zip`

The second review confirmed all four round-one corrections and found two further defects. Both were confirmed against the source before anything was changed.

**Both are the same shape as round one:** a guarantee that held on the path the tests walked and failed elsewhere. Round one's recurring form was *model output resolves when nothing disagrees*. Round two's is *the decision survives when nothing else is said*.

---

## K. Findings — both confirmed

### Finding 5 — an explicit "no project" was ranked below stale session state · **CONFIRMED**

Precedence placed `EXPLICIT_NONE_INSTRUCTION` at level 6, beneath conversation (3) and session (4). The consequence, reproduced against the source before any change:

```
session = Project Alpha, user says "this isn't for a project"
  ->  ResolvedProject(Alpha) via session
```

A session set an hour ago outranked a decision being made in that breath. The user said the work has no project and the exchange was attributed to Alpha.

**The ranking was the error, not the ordering within it.** *"Select Project Beta"* and *"this is not for a project"* are the same act — a person stating scope for this exchange. Level 2 was already *"the explicit current-interaction scope choice"*; declining a project is one of those choices, and it had been filed as a weak fallback because it produces a NULL rather than an id. The storage shape had leaked into the authority model.

**The session's own explicit-none had the same defect underneath it.** `resolve_scope` carried a `_nothing_else_said` special case, so a session holding a deliberate no-project decision was consulted only when no other signal existed. Four sub-cases were checked and three were wrong:

| Signals | Was | Now |
|---|---|---|
| explicit-none session, nothing else | `ExplicitNoProject` via session | unchanged — the one that worked |
| explicit-none session + trusted "Project Beta" | `ResolvedProject(Beta)`, no question | **`AmbiguousProject`, conflicting signals** |
| explicit-none session + untrusted "Project Beta" | `ResolvedProject(Beta)` | **`AmbiguousProject`, conflicting signals** |
| explicit selection Beta + explicit no-project | `ResolvedProject(Beta)` | **`AmbiguousProject`, conflicting signals** |

The third row is the serious one: an untrusted model suggestion resolved scope outright, which is the round-one finding recurring through a different door. Round one closed it by making trust a field; the session's decision disappearing meant there was nothing left of higher authority for the check to weigh against.

### Finding 6 — the `legacy_unknown` reservation was bypassable · **CONFIRMED, and demonstrated**

`0006` reserved the value with a check constraint:

```sql
project_attribution <> 'legacy_unknown' OR created_at < TIMESTAMPTZ '2026-08-18'
```

**`created_at` is data, and whoever writes the row supplies it.** The review demonstrated the bypass, and it reproduces exactly:

```sql
INSERT ... created_at = '2026-08-15', project_attribution = 'legacy_unknown'
-> INSERT 0 1
```

Round one's audit called this *"reserved by constraint, not by convention"*. It was a convention wearing a constraint's clothing, which is worse than an honest convention because it reads as enforcement — and because the round-one document asserted the guarantee in those words, a later reader would have had no reason to check.

**A second defect was found alongside it, in `0006`'s downgrade.** It claimed to be unconditionally clean on the reasoning that `project_attribution` *"adds interpretation but stores no fact of its own"*. True until the first `explicit_none` row exists; false forever after. `project_id` NULL + `explicit_none` and `project_id` NULL + `legacy_unknown` become the **same row** once the column is dropped, and nothing left in the table distinguishes them. That is a captured decision destroyed by a rollback — the thing `0002`, `0003`, and `0005` all refuse to do.

---

## L. Corrections

### 5 — precedence became levels, because two sources share a class

`PRECEDENCE` was `tuple[ResolutionSource, ...]`: a flat order, which cannot express two sources of equal authority. It is now `tuple[frozenset[ResolutionSource], ...]`.

```python
PRECEDENCE: tuple[frozenset[ResolutionSource], ...] = (
    frozenset({ResolutionSource.TRUSTED_APPLICATION_ID}),
    frozenset({ResolutionSource.EXPLICIT_SELECTION, ResolutionSource.EXPLICIT_NONE_INSTRUCTION}),
    frozenset({ResolutionSource.CONVERSATION}),
    frozenset({ResolutionSource.SESSION}),
    frozenset({ResolutionSource.EXACT_REFERENCE}),
)
```

The type change is the point. A flat list forced every source to outrank every other, so *"these two are equal"* was not a statement the structure could hold — and the only way to write it down was to pick one, which is what had happened. Both forms are now handled at level 2 and both fail closed:

```python
if signals.explicit_selection is not None and signals.explicit_no_project:
    return AmbiguousProject(reason=AmbiguityReason.CONFLICTING_SIGNALS, question=...)
```

Supplying both is a contradiction between instructions of equal authority. There is no principled way to pick, so it asks.

### 5b — the session's explicit-none is structural, not a special case

`_nothing_else_said` is gone. Session scope is now the `(is_set, project_id)` pair that conversation scope already used, read by the same code:

```python
if signals.session_is_set:
    if signals.session_project_id is None:
        return None, ResolutionSource.SESSION
    ...
```

`resolve_scope` fills the pair from the live session with `dataclasses.replace` rather than reconstructing the signals, so the two fields cannot drift apart at the call site.

**Why symmetry rather than a fix to the special case.** The conversation path had been corrected in round one to read an established NULL as a decision. The session path was left with a bespoke branch, and a bespoke branch is where the next inconsistency goes. Making them the same shape means a future correction to one is a correction to both.

### 6 — the reservation moved from a timestamp to the operation

Migration `0007` drops the check constraint and installs a `BEFORE INSERT OR UPDATE` trigger.

| Operation | Result |
|---|---|
| INSERT with `legacy_unknown` | **refused, whatever `created_at` claims** |
| UPDATE turning a non-legacy row into `legacy_unknown` | **refused** |
| UPDATE of a row already `legacy_unknown`, staying so | permitted |

**Why a trigger and not a stricter constraint.** A check constraint sees one row's values. It cannot see whether it is looking at an INSERT or an UPDATE, nor what the row held before. The rule being enforced — *this value may persist but may not be acquired* — is about the transition. The same reasoning as the persona immutability guard in `0005`.

The third row matters as much as the first two: the nine historical rows stay **ordinary rows**. A wrong latency or a missing provider request id is still correctable. The set is closed to new members, not frozen.

### 6b — `0006`'s downgrade now refuses once a decision exists

```python
if decisions:
    raise RuntimeError(
        f"Refusing to downgrade: {decisions} model_calls row(s) record a "
        "deliberate no-project decision ..."
    )
```

Clean on a database with no `explicit_none` row — CI and any fresh checkout — and refusing after that. Nothing is deleted, rewritten, or coerced to make the downgrade succeed.

`0006`'s constraint drop was also made `IF EXISTS`, since `0007` may legitimately have removed it already. A downgrade must not fail on the absence of something a later migration was right to take away.

---

## M. Two test defects found while proving this

Neither was in the review. Both were found by making the round-two tests assert specifically, and both are recorded because a test that cannot fail for the right reason is not evidence.

**`test_the_database_refuses_an_unknown_cost_carrying_a_zero` and `test_the_database_refuses_a_known_cost_with_no_figure` had stopped testing anything.** They asserted only `pytest.raises(Exception)`. When `0006` added `project_attribution`, the value was appended to the `VALUES` list without adding the column name — so the statement failed on argument count and never reached the constraint it exists to prove. Both had been passing for the wrong reason since the previous round.

They now name the constraint they expect, read from psycopg's diagnostics rather than matched against the message text. That immediately caught a second error: the constraint asserted was `ck_model_calls_known_cost_carries_a_figure`, which **does not exist** — the real name is `ck_model_calls_known_cost_is_recorded`. A substring match against a message SQLAlchemy truncates mid-name would have gone on hiding it.

---

## N. Fabricating history is now confined to one place

`0007` closes `legacy_unknown` to new rows, which means several existing tests could no longer insert the rows they need — the accounting-view tests genuinely exercise pre-amendment rows, and those are the rows that carry `legacy_unknown`.

Rather than weaken the guard, the tests admit what they are doing. `conftest.fabricate_a_legacy_row` suspends the trigger for one transaction and restores it in the same one, and it is the only place in the suite that does so. Its docstring states plainly that nothing in `val_gateway` may do this: a writer that disables the guard has simply decided not to decide scope, which is what `0007` exists to stop.

---

## O. Schema change — migration `0007`

| | |
|---|---|
| Adds | trigger `model_calls_legacy_attribution_is_closed`, function `val_legacy_attribution_is_closed()` |
| Drops | `ck_model_calls_legacy_attribution_is_reserved_to_history` |
| Columns changed | **none** |
| Rows rewritten | **none** |
| Downgrade | **clean, both ways** — it captured nothing, so reversing it restores `0006`'s weaker constraint |

The weaker guard is dropped rather than kept alongside the stronger one. Leaving both invites a reader to find the weak one and believe it — which is how round one's audit came to assert a guarantee that did not hold.

`§20` of the WP-0.6 authorisation asks that schema change be avoided unless actually required. This one is required and is the minimum: the rule cannot be expressed as a check constraint, and no column, type, or row is touched.

---

## P. The nine historical rows — verified again

```
 project_attribution | count |  earliest
---------------------+-------+------------
 resolved            |     4 | 2026-08-17
 legacy_unknown      |     9 | 2026-08-15
```

Unchanged in count and earliest date across the `0007` migration. An on-demand encrypted backup was taken before it ran. The adversarial insert was then run against the **authoritative** store, not only the scratch one, and refused.

---

## Q. Round-two verification

### The six round-two cases, run live

| | Signals | Result |
|---|---|---|
| A | session Alpha + explicit no-project | `ExplicitNoProject` via `explicit_none_instruction` |
| B | conversation Alpha + explicit no-project | `ExplicitNoProject` via `explicit_none_instruction` |
| C | explicit-none session, nothing else | `ExplicitNoProject` via `session` |
| D | explicit-none session + trusted "Project Beta" | `AmbiguousProject`, `conflicting_signals` |
| E | explicit-none session + untrusted "Project Beta" | `AmbiguousProject`, `conflicting_signals` |
| F | explicit selection Beta + explicit no-project | `AmbiguousProject`, `conflicting_signals` |

### The eight original acceptance cases, re-run unchanged

| | Signals | Result |
|---|---|---|
| A | exact trusted name | `ResolvedProject` → Alpha via `exact_reference` |
| B | trusted application id against everything else | `ResolvedProject` → Beta via `trusted_application_id` |
| C | conversation Alpha over session Beta | `ResolvedProject` → Alpha via `conversation` |
| D | untrusted model suggestion alone | `AmbiguousProject`, `untrusted_suggestion_only` |
| E | no signal at all | `AmbiguousProject`, `unknown_identifier` |
| F | unknown trusted name | `AmbiguousProject`, `unknown_identifier` |
| G | explicit no-project alone | `ExplicitNoProject` via `explicit_none_instruction` |
| H | slug reference, trusted | `ResolvedProject` → Beta via `exact_reference` |

**Level 1 is unchanged.** A trusted application id still outranks an explicit no-project instruction. The correction raised the instruction to level 2, not to level 0.

### Database proofs

| Proof | Result |
|---|---|
| Backdated `legacy_unknown` INSERT (three dates: today, before the old cutoff, 2001) | **refused** on all three |
| UPDATE turning an existing row into `legacy_unknown` | **refused** |
| UPDATE of a row already `legacy_unknown` | permitted, and the row stays legacy |
| `0006` downgrade with no `explicit_none` row | clean, and re-appliable |
| `0006` downgrade with one `explicit_none` row | **refuses, and does not half-apply** |
| `0007` downgrade | clean, restores `0006`'s constraint, re-appliable |
| Nine historical rows after all of the above | unchanged |

### Static and full-suite

| Gate | Result |
|---|---|
| `pytest` (whole repository) | **489 passed**, no warnings |
| `mypy` strict, 43 source files | **clean** |
| `ruff check .` | clean |
| `ruff format --check .` | 91 files formatted |
| `lint-imports` | 3 contracts kept, 0 broken |
| `check_boundaries.py` | 8 components, direction holds |
| `check_pins.py` | no unpinned specifier across 130 files |
| `check_secrets.py` | no credential-shaped literal |
| `alembic upgrade head → downgrade base → upgrade head` | clean from empty |
| `alembic check` | no pending autogenerate |

**One test fewer than the previous round's arithmetic suggests.** `test_database_url` was an imported helper pytest was collecting as a test; it is now aliased on import. The count went 480 → 490 → 489.

---

## R. Recommendation and status

**WP-0.6 remains IMPLEMENTED / ACCEPTANCE BLOCKED until you re-accept it. WP-0.7 remains NOT STARTED.**

Both findings are corrected with tests that fail against the old behaviour, and both were closed structurally rather than by adding a check:

- **Finding 5** by a type change — precedence levels, so *"equal authority"* is expressible and the old flat order cannot be written down again.
- **Finding 6** by moving enforcement from a column the writer controls to the operation itself.

**I am not marking it COMPLETE.** It has now been accepted once on evidence that did not hold, and reopened twice. Re-awarding the status unilaterally is not mine to do, and the reason for that is stronger after a second round than it was after the first.

### One observation for WP-0.7, not acted on

`conversations.project_id` is nullable, and `val_policy` reads an established conversation with a NULL there as an explicit no-project decision. **That is true today only because the table has zero rows** — there is no legacy set to disambiguate, which is precisely what `model_calls` did have.

WP-0.7 is the first thing that will write conversation rows. Whatever creates one must resolve scope first, exactly as `converse` does; a conversation created with a NULL because nobody asked would recreate the defect `0006` had to correct, and there would be no date to separate the sets by.

**No column was added.** Adding attribution to a table with no rows and no writer would be building WP-0.7's machinery early — the first standing exclusion in `CLAUDE.md`. It is recorded in `VAL_Open_Decisions.md` and in the `Conversation` docstring instead.

## S. Executive decisions required

**NONE.**

The `projects.status` ruling of 17 August is unchanged and still locked by a behavioural regression test. Its revisit trigger is unchanged.
