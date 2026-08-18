# VAL — Open Decisions

Only questions that require Lord Armand's decision. Implementation problems
Claude can solve are not listed here; they are in §K of the handoff.

Generated at commit `ccc94e3`, 16 August 2026.
**Updated 17 August 2026** after the WP-0.4 corrective work: items 4, 5, and 6
added. **Updated again the same day**: items 4, 5, and 6 are **decided and
recorded below**, and item 7 — the WP-0.5 persona-adherence acceptance — is
recorded with them.

**Updated again 17 August 2026** after WP-0.6, and once more when its acceptance
was recorded: **item 8 is now decided.** Item 1 remains an action only Lord
Armand can take; items 2 and 3 stand as previously recommended; items 4–8 are
decided and recorded below.

**Nothing on this page currently awaits a decision.** Item 8 carries a *revisit
trigger* rather than an open question — see it for the two conditions that
require the decision to be made again.

---

## 1. The Anthropic account reports no credit

**Not a decision so much as an action only you can take**, listed here because it
is the single blocker on WP-0.4 and no engineering will clear it.

The key authenticates and lists models — `claude-opus-5`, `claude-sonnet-5`,
`claude-fable-5` — so it is valid and correctly scoped. Only inference is
refused:

```
400 invalid_request_error
"Your credit balance is too low to access the Anthropic API."
request_id: req_011Ce5aYFevxhMfvsywK1gem
```

You said credit was on both accounts, and OpenAI's is working. The likely causes
are credit purchased on a different organisation than the key belongs to, or a
workspace-scoped key without a spend allocation.

**No decision is needed on the code.** Once inference succeeds, the three
remaining WP-0.4 criteria are a single script run.

---

## 2. Should Gemini stay unusable, or should its verifier be built?

**Genuinely your call, and safe to leave as it is.**

Your 15 August ruling was that a Gemini configuration must verify at startup that
its key is attached to paid billing, and fail if it cannot confirm it. Google
exposes no API that reports billing status for a Generative Language API key, so
`verify_paid_billing` fails closed and **always** fails. Gemini therefore cannot
be configured at all. No Gemini entry is in the registry, so nothing is blocked
today.

Three options:

1. **Leave it.** Gemini stays unusable. Costs nothing; two providers is what the
   architecture requires.
2. **Build a real check** against the Cloud Billing API for the project behind the
   key. More moving parts, and needs a GCP project and service-account access.
3. **Rule differently** — e.g. accept a billing-account id recorded in the
   registry as sufficient evidence. **I would advise against this**: it is
   configuration claiming it, which your ruling explicitly rejected.

**Recommendation: option 1** until there is a reason to want Gemini. Nothing is
waiting on it.

---

## 3. Should the interrupt-level machinery arrive before WP-0.10?

**Low stakes; asking because the sequencing is yours.**

The four interrupt levels are specified in `02-partner-systems.md` §5.5 as of the
15 August amendment, with no machinery — as you directed. Level 3 (immediate:
integrity, data loss, security only) is the only one with a plausible Layer 0
consumer: the backup watcher currently alerts through macOS notifications on its
own rather than raising a signal for Val to level.

Doing nothing is defensible — the watcher works, and Val has no interface to
interrupt through until WP-0.10. **Recommendation: leave it.** The natural moment
is WP-0.10, when there is a conversation to interrupt.

---

## 4. Confirm the two governing-document amendments of 17 August

**Confirmation rather than a question.** Both were made under the explicit terms
of your corrective order, and both amend documents you own — so they are put in
front of you rather than left to stand by implication.

**`04-layer-0.md` §2.5 — a tenth table, `budget_reservations`.** §2 previously
said no table exists that §2 does not name. Your order required a database-backed
reservation with an explicit lifecycle — reserved, settled, released, expired —
and that cannot exist without a table. The alternative shape, holding the
reservation inside `model_calls` with a `pending` status, was considered and
rejected: it amends §2 anyway, since the `status` enum is specified there, and it
puts rows into the call record for calls that have not happened and may never
happen — precisely the confusion the cost-certainty work exists to remove.

**`01-architecture.md` §5.7 — the corrected budget rule and Layer 0 routing.**
§5.7 previously described "the crudest possible guard, and nothing else". The
guard as written was `month_to_date_spend < CEILING`, which enforces the ceiling
against history rather than against the call being asked for: at $199.99 of $200
it admitted a call of any size. The rule is now `committed + maximum_cost(call)
≤ CEILING`. The **$200 figure is unchanged** — a control that was not enforcing
it now does.

**Recommendation: confirm both as written.** Neither adds a capability. Both
narrow what the system may do rather than widening it, which is the direction an
implementation is permitted to move a boundary. The graduated thresholds, the
reserve, and the cost dashboard all remain deferred to Layer 3, untouched.

---

## 5. Should the persona's semantic version be stored?

**Low stakes. Worth deciding before WP-0.5 begins, not before you review this.**

`personas.version` is an integer persistence revision — 1, 2, 3 — counting rows.
The authored document carries its own label, now **v1.2**. §2.1 of
`04-layer-0.md` records the distinction, and the seeded row will therefore read
`version = 1` while holding v1.2 content.

The schema has no field for the authored label. **Proposed and deliberately not
implemented:** one nullable `semantic_version` text column on `personas`.

Without it, "which authored version of the persona was live on 3 September" is
answerable only by matching stored content against git history. That works, and
it is not a record.

**Recommendation: add it when WP-0.5 begins**, as part of that package rather
than ahead of it.

---

## 6. Should caching and batch pricing be verified now?

**Lowest stakes on this page. No deadline.**

The registry's `caching` and `batch_pricing` fields read `NOT_VERIFIED` on all
three entries. That is not a placeholder — it is the honest value. Prompt-caching
and batch availability are pricing facts, and this repository's standing rule is
that pricing is read from the provider's own documentation and dated, never
recalled.

Layer 0 uses neither feature, so nothing depends on the values today.

**Recommendation: leave them until Layer 3**, when `01-architecture.md` §5.3
makes caching structurally load-bearing and the values will be read from the
providers' own pages and dated, in the same discipline as `rates_verified_on`.
Filling them in now from recollection is exactly the failure that dating exists
to prevent.

---

## Decided — 17 August 2026

Recorded here so the decisions outlive the conversation that produced them.

### 4. The two governing-document amendments — **CONFIRMED**

`04-layer-0.md` §2.5 (`budget_reservations`, the tenth table) and
`01-architecture.md` §5.7 (the ceiling enforced against the proposed call, and
Layer 0 routing) stand as written. The $200 figure is unchanged; a control that
was not enforcing it now does.

### 5. The persona's semantic version — **DECIDED: store it, explicitly and separately**

*"WP-0.5 shall store the authored Persona semantic version explicitly and
separately from the integer persistence revision."*

Implemented in WP-0.5, migration `0005_persona_provenance`. `personas.version`
counts rows; `personas.semantic_version` counts authorship. The seeded record is
persistence revision **1** holding authored version **1.2**, and neither number
may stand in for the other. Stored **NOT NULL** rather than the nullable column
the earlier clarification proposed — a row that cannot say which authored
version it holds is the ambiguity the column exists to remove.

### 6. Caching and batch pricing — **DECIDED: deferred to Layer 3**

*"Full caching/batch-pricing qualification remains deferred to Layer 3. No
billing feature that invalidates the current maximum-cost bound may be enabled
before its cost semantics are qualified."*

The registry's `caching` and `batch_pricing` remain `NOT_VERIFIED` on every
entry, and `maximum_cost` records in its own docstring that a prompt-cache write
is billed **above** the base input rate and would therefore break the bound.
Whoever enables caching must widen the formula in the same change. WP-0.5's
context assembly puts the persona in `system` — the stable-prefix-first ordering
`01-architecture.md` §5.3 wants — **without requesting caching**, which is the
ordering benefit at none of the billing risk.

### 7. WP-0.5 persona adherence — **ACCEPTED**

The one WP-0.5 criterion that could not be discharged by engineering: *"Val's
register in a real exchange is recognisably that of `03-persona.md` §9. Assessed
by reading, not asserted."*

Lord Armand read the recorded exchange
(`VAL_WP05_Persona_Loading_Audit.md` §Q) against the governing persona and
recorded that it **passes**, conditional on the previously reported technical
evidence remaining valid. **The condition was re-verified rather than assumed**
— active persona, revision, semantic version, stored digest, intactness, source
check, row counts, the on-disk persona digest, 373 tests, and CI on `73e9947`
were all unchanged. **WP-0.5 is COMPLETE.**

This is the first acceptance in the project that a model was structurally
forbidden from signing, and the structure held: the criterion sat unsigned until
a human read the text.

---

## 8. `projects.status` shall not disqualify a project — **DECIDED 17 August 2026**

> For the current Layer 0 implementation, `projects.status` shall not disqualify
> a Project from resolution because no governing vocabulary or lifecycle policy
> currently defines such behavior. **This is not a permanent policy.** When an
> actual archived/inactive Project case exists or a lifecycle feature requires
> it, Project status vocabulary and resolution restrictions require an explicit
> decision. **Do not infer them now.**
>
> — Lord Armand, 17 August 2026

**Why, recorded because it is the reason and not merely the outcome.** Inventing
`active` / `archived` / `disabled` now would be speculative architecture, and —
the sharper objection — it could accidentally turn a metadata field into an
authority boundary without any settled semantics. A column nobody has defined
would start deciding what may be conversed about, and nothing would mark the
moment it began.

### The revisit trigger

Status semantics require an explicit decision when **either** becomes true:

1. **A real archived or inactive project exists** — an actual project someone
   has retired, not a fixture.
2. **A lifecycle feature requires it** — archival, retention, or any view that
   hides retired work.

Two things are then decided **together**: the vocabulary, and whether any value
restricts resolution. Deciding the vocabulary alone is precisely what would let
the field become an authority boundary by default.

### The original raising, kept for context

The column exists and is `NOT NULL`. **No baseline enumerates its values or
attaches meaning to any of them.** So WP-0.6 treats no status as disqualifying:
an archived project resolves by slug like any other, and a test asserts it.

Inventing a rule — that an archived project may be referenced but not made
current, say — would be writing policy this implementation is not entitled to
write, and §10 of the authorisation says as much: *"Do not invent status policy
if the current baseline does not define it."*

Two things would need deciding together:

1. **The vocabulary.** What values `status` may take.
2. **Whether any of them restricts conversation.** Read-only? Referenceable but
   not selectable? No restriction at all?

The behaviour in the meantime is the permissive one, which is visible, tested,
and easy to narrow — and narrowing later costs nothing, while having wrongly
forbidden something would have cost a conversation somebody wanted to have.

**One recommendation, not implemented.** When this is next touched, a guard test
asserting that the resolver branches on `status` nowhere would turn *"do not
infer them now"* from an instruction into something that fails the build if
someone later infers it silently. Deliberately not added after acceptance, so
the accepted source stays the source under review.

---

## 9. `conversations.project_id` before WP-0.7 — **NOT A DECISION, A CONSTRAINT ON WP-0.7**

Recorded 18 August 2026 during the second corrective round. **No decision is
required from you now.** It is here because it is the kind of thing that is
invisible until it has already happened.

`conversations.project_id` is nullable, and `val_policy.project_resolution`
reads an established conversation with a NULL there as an explicit no-project
decision. **That reading is correct today only because the table has zero rows.**

That is exactly the situation `model_calls` was in and did not survive.
`model_calls` had nine rows written before project scope existed, all carrying
NULL, none of them decisions — which is why `0006` had to add a
`project_attribution` column to say which NULLs meant what. `conversations` has
no such history yet, so there is no ambiguous set to disambiguate.

**WP-0.7 is the first thing that will write rows here.** Whatever creates a
conversation must resolve scope first, exactly as `converse` does. A conversation
created with a NULL because nobody asked would recreate the defect `0006` had to
correct — and this time there would be no date to separate the sets by, because
the clean and unclean rows would be interleaved from the start.

**No column was added.** Adding attribution to a table with no rows and no writer
would be building WP-0.7's machinery early, which is the first standing exclusion
in `CLAUDE.md`. The constraint is recorded here and in the `Conversation`
docstring in `val_domain/schema.py` instead, so it is in front of whoever opens
that file to add the writer.

---

## Nothing else

No other open question requires your decision. Everything else in §K of the
handoff is either sequenced work or waiting on time to pass.
