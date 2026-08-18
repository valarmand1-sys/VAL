# VAL — WP-0.6 Corrective Audit

**Independent source review of `VAL_Source_Snapshot_8cc0413.zip` found four acceptance defects.** All four were confirmed against the source before anything was changed. This document records the corrections and preserves the lineage of the acceptance that preceded them.

---

## A. Acceptance lineage — preserved, not rewritten

| Date | Event |
|---|---|
| 17 Aug 2026 | WP-0.6 implemented, source commit `8cc0413`, bundle `ef3e613` |
| 17 Aug 2026 | **Accepted COMPLETE** by Lord Armand, recorded at `6a89f7a` |
| 18 Aug 2026 | **Reopened** — independent source review of the accepted snapshot found four defects |
| 18 Aug 2026 | Corrected at source commit `4ff6838` |

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
