# VAL — Open Decisions

Only questions that require Lord Armand's decision. Implementation problems
Claude can solve are not listed here; they are in §K of the handoff.

Generated at commit `ccc94e3`, 16 August 2026.
**Updated 17 August 2026** after the WP-0.4 corrective work: items 4, 5, and 6
added. Items 1–3 are unchanged and still stand.

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

## Nothing else

No other open question requires your decision. Everything else in §K of the
handoff is either sequenced work or waiting on time to pass.
