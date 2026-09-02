# Attachment Substrate v1 — the shared contract

**Status: DRAFT, for Lord Armand's ruling. Not governing until accepted.**
**No migration and no application code exists for anything below**, per the
Track C ruling (`04-layer-0.md` §5, 2 September 2026): contract first, ruled,
then implemented. This document is written to be accepted as the shared
contract for both consumers — attachment-scoped image vision (first) and
document comprehension (waiting) — and to survive both without either
privately reshaping it.

Checkpoint review performed per the open-problems procedural rule: **OP-1**
and **OP-3** both name this work package; §8 records what this contract does
about each.

---

## 1. The one rule everything else serves

**One file, one attachment, one provenance tree.** A PDF with figures, a
slide with a frame: "what she saw" and "what the document says" are *derived
views of one attachment*, never two attachments. Page 17 and the figure on
page 17 are two **representations** under one identity, linked to their
parents, located within them. Nothing in this contract permits a derived view
to exist without a resolvable path back to the immutable original.

## 2. Tables (contract-level; exact DDL arrives with the ruled migration)

All four are **evidence-class**: no UPDATE, no hard delete, complete at
insert (`0009`/§2.3 footing). None adds a column to any existing table; every
reference to `messages` or `model_calls` is by foreign key from the sidecar
side, satisfying the Track C constraint structurally.

### 2.1 `attachments` — the immutable original

| Column | Meaning |
|---|---|
| `id`, `created_at` | uuidv7 identity of the *content instance*; when it entered the house |
| `sha256` | Hash of the original bytes. **Unique.** The bytes' identity. |
| `byte_size` | As stored |
| `media_type` | Probed from the bytes (magic numbers), never trusted from a filename. v1 admits image types only; the column is general. |
| `classification` | The data classification stated at ingestion (`public`/`internal`/`protected`; `restricted` refused — §6). Default `protected`, ambiguity resolves upward. |

**Identity is the content, not the act.** Attaching byte-identical files
twice yields one `attachments` row; the *acts* differ and live in
`message_attachments`, which carries the per-act facts (filename as given,
when, to which turn). This keeps "which image did she see" a single answer.

**Original bytes live in the authoritative store** (PostgreSQL is the sole
authoritative store; backup, PITR, and restore verification then cover them
with no second mechanism), in a companion `attachment_blobs(attachment_id,
bytes)` table so listings never drag megabytes. A file-system blob store
would be a second authoritative store and is rejected here so nobody has to
reject it later.

### 2.2 `message_attachments` — the association (the permitted additive path)

| Column | Meaning |
|---|---|
| `id`, `attached_at` | The act |
| `message_id` | FK → the existing **user** message this attachment accompanied. v1 restricts associations to `role = 'user'` — attaching is Lord Armand's deliberate act; Val producing attachments is not a v1 concept (extension rule §7). |
| `attachment_id` | FK → `attachments` |
| `position` | Order among one turn's attachments, unique per message |
| `given_filename` | The name as provided at this act — display and recall aid, never identity |

A text-only turn creates no row here and touches no code path that knows
this table exists — backward compatibility is structural, not filtered.

### 2.3 `attachment_representations` — typed derived views

| Column | Meaning |
|---|---|
| `id`, `created_at` | |
| `attachment_id` | FK → the one identity every view resolves to |
| `parent_representation_id` | FK → this table, nullable. NULL means derived directly from the original. A region crop of a page render points at the page render. **Parent/child provenance is a tree rooted at the original.** |
| `representation_type` | Typed, from the declared vocabulary (§7). v1 declares exactly one: `model_input_image` — the bytes actually transmitted to a provider when they differ from the original (resized/re-encoded for provider limits). When the original itself is sent, no representation row is needed or written. |
| `sha256`, `byte_size`, `media_type` | Of the derived bytes (blob in `attachment_blobs` keyed by representation where present) |
| `locator_ordinal` | Nullable int, 1-based: page or slide number within the parent. NULL = the whole parent. (Declared now for the documents sibling; v1 image derivations leave it NULL.) |
| `locator_region` | Nullable, `x0,y0,x1,y1` in pixel coordinates **of the parent representation's bytes**. NULL = the whole of what `locator_ordinal` selects. |
| `derived_by` | Processing provenance: tool and pinned version that produced these bytes (e.g. `pillow 11.1.0 resize 2048px`). Never blank. |
| `model_config_id`, `model_call_id` | Nullable FKs. Non-null exactly when a **model** produced the representation (e.g. future OCR); then the exact call is named, the same doctrine as `blind_positions.model_call_id`. v1 derivations are local and leave both NULL. |

**Complete at insert.** A representation row exists only for a derivation
that succeeded, and is immutable — the `0009` doctrine, not a status machine.

### 2.4 `attachment_processing_events` — status and errors, append-only

| Column | Meaning |
|---|---|
| `id`, `created_at` | |
| `attachment_id` | FK |
| `intent` | What was being attempted (`probe`, `derive:model_input_image`, …) |
| `outcome` | `succeeded` \| `failed` |
| `error` | The actual error, verbatim, when failed; NULL otherwise |

"Pending" is the honest absence of an outcome, not a stored claim; a failure
is a permanent record, not an overwritten retry; and the interface renders
processing state only from rows that exist (invariant 29 — no spinner may
assert progress this table does not support).

### 2.5 `model_call_sight` — what she saw, attributable

The vision requirement's capture half ("what she saw is recorded as part of
the exchange") without touching `model_calls`:

| Column | Meaning |
|---|---|
| `id`, `created_at` | |
| `model_call_id` | FK → the existing call row |
| `attachment_id` | FK — the identity seen |
| `representation_id` | Nullable FK — the exact derived bytes sent; NULL means the original bytes were sent |
| `position` | Order of images within the call's payload |

One row per image per call, written by the gateway path in the same motion
as the call record. A visual judgment is then permanently attributable to
the exact bytes behind it: call → sight rows → representation → original.
This is the substrate's contribution to the sight-not-receipt requirement's
evidence half, and it is deliberately a sidecar, not a `model_calls` column.

## 3. Egress, eligibility, and the honest v1 limit

An image is external egress, same as text. The effective classification of a
call is the **strictest** of its text parts and every attached image's
stated classification; routing and the eligibility refusals run on that
through the **existing gateway** — no new entrance, no side door.
`restricted` images are refused at ingestion exactly as restricted text is
refused at transmission.

**Stated plainly rather than papered over:** the Restricted *content*
preflight (credentials, card numbers) reads text and cannot read pixels.
v1 images are classified by Lord Armand's statement with a `protected`
default and upward resolution — there is no pretend image scanner, and the
absence is recorded here as a v1 limit, not discovered later.

## 4. Cost, within existing doctrine

Providers bill image inputs as input tokens computed from dimensions, and
report actual usage in the same fields the accounting already reads. So:
`maximum_cost` gains an image term per attached image using each provider's
published dimensional formula (a registry-adjacent fact, verified and dated
like every rate); settlement continues from returned usage, unchanged;
reservations, expiry, and `cost_certainty` doctrine untouched. **This feeds
new measured usage through the existing doctrine.** If any target provider's
image pricing turns out not to be expressible this way, that is the ruled
STOP condition — halt and present, not adapt.

## 5. Backward compatibility (acceptance requirement)

- A text-only turn executes the identical existing path: no attachment
  concept, state, lookup, or processing step enters it.
- Existing conversation and message representations remain valid with
  attachment associations absent; API changes are additive only (new
  endpoints; new optional response fields such as a per-message attachments
  list). No existing field changes meaning.
- No new column on `conversations`, `messages`, `execution_events`,
  `deliberations`, `model_calls`, `personas`, `budget_reservations` — and
  the migration's tests assert those tables' column sets are byte-identical
  before and after.

## 6. What v1 explicitly does not include

Document parsing, text extraction, OCR, page rendering (the documents
sibling — its needs are *representable* above, deliberately, but no such
representation type is declared yet); audio and video; any filesystem
access; Val-produced attachments; attachment editing or deletion (immutable,
like everything evidentiary); any recall/retrieval of attachments into later
context (an attachment is seen in the turns it accompanies; retrieval
doctrine for attachments is its own future decision, not a default).

## 7. Extension rules — contract-stable, not frozen

1. **Additive representation types are permitted** without re-ruling: a new
   `representation_type` value with its own `derived_by` semantics, using
   the existing columns.
2. **New locator kinds are additive**: a representation kind needing a
   locator beyond ordinal/region adds a nullable typed column by amendment
   to this contract's table list — never by overloading an existing one.
3. **Core provenance semantics may not be privately changed by either
   sibling**: content-hash identity, one-file-one-tree, parent/child links,
   complete-at-insert immutability, and the `model_call_sight` linkage are
   the core. A sibling finding a core assumption wrong stops and the
   contract is amended deliberately.
4. Every amendment to this document is dated and attributed, and notes which
   consumer forced it.

## 8. Open-problem checkpoints (procedural rule, fired)

- **OP-3** closes with this substrate's implementation: the exact-composition
  assertion lands — the assembled request contains exactly the enumerated
  parts (persona system, recall envelope, conversation turns, and now
  explicitly-declared attachment parts) and nothing else.
- **OP-1** is *narrowed, not solved*: claims about "what she received and
  perceived" become checkable against `model_call_sight` rows — a
  deterministic record where none existed. Claims of approval and completion
  remain uncovered; OP-1 stays open with its remaining checkpoints.
