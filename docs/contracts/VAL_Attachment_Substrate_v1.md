# Attachment Substrate v1.2 — the shared contract

**Status: DRAFT v1.2, for Lord Armand's ruling. Not governing until accepted.**
**No migration and no application code exists for anything below.**

v1.0 (2 September 2026) was not accepted; v1.1 (same date) applied the eleven
required amendments of the first ruling. v1.1 was not accepted; **v1.2 (same
date) applies the eight corrections of the second ruling** — the first seven
converged on independently by both external reviewers, the eighth found by
the third reviewer alone (reserve from the transmitted bytes, §8). The
eleven amendments are not reopened; neither are the tree, the sidecars,
Track C isolation, or per-act classification.

Checkpoint review per the open-problems procedural rule: **OP-1** and
**OP-3** name this work package; §10 records what this contract does about
each.

---

## 1. The one rule everything else serves

**One file, one attachment, one provenance tree.** A PDF with figures, a
slide with a frame: "what she saw" and "what the document says" are *derived
views of one attachment*, never two attachments. Page 17 and the figure on
page 17 are two **representations** under one identity, linked to their
parents, located within them. Nothing in this contract permits a derived view
to exist without a resolvable path back to the immutable original.

## 2. Storage: PostgreSQL as measured candidate, not assumption *(amendment 1)*

PostgreSQL remains the v1 candidate for original and derived bytes — the
sole-authoritative-store argument is real, and backup, PITR, and restore
verification then cover attachments with no second mechanism. But gate point
7 cuts the other way: if a year of masters and frames makes verified restore
too slow or B2 retention intolerable, Track C has compromised the gate it was
opened to serve.

**Required pre-implementation deliverable — the sizing exercise**, performed
against a representative sample of Lord Armand's actual files (setting
masters, character sheets, storyboard frames, generated images) and
reported before any migration is written:

- median and high-percentile original size;
- attachments per working day;
- expected annual raw and derived growth;
- WAL and backup growth under the actual pgBackRest policy;
- B2 storage impact under the actual retention policy;
- restore time at projected one-year volume;
- estimated ordinary and consequential visual-turn inference cost at
  representative median and high-percentile image dimensions on the approved
  routes *(correction 2 — the consequential figure includes the §8 double
  transmission)*.

No object store is designed now. Nothing here freezes storage architecture
past vision: **storage is explicitly reviewed again before audio or video.**

## 3. Tables

Six, stated exactly *(amendment 9's count correction)*: one content-addressed
blob store plus five substantive tables. All are **append-only**: no UPDATE,
no hard delete, complete at insert (`0009`/§2.3 footing). No column is added
to any existing table; every reference to `messages` or `model_calls` is a
foreign key from the sidecar side.

### 3.1 `blobs` — one content-addressed byte store *(amendment 9, exact schema)*

| Column | Meaning |
|---|---|
| `sha256` | **Primary key.** Hex digest of `bytes`; verified equal to the computed digest at write. |
| `byte_size` | Length of `bytes` |
| `media_type` | Established by the **pre-commit admission preflight** (§3.3) from the bytes themselves (magic numbers), never trusted from filename or EXIF — a function of the bytes, so it lives with them |
| `bytes` | The content |
| `created_at` | First time these bytes entered the house |

Originals and derived bytes both live here, referenced by digest. Writing
bytes whose digest already exists is an idempotent no-op reuse (content
addressing), not an update and not an error. Byte identity is first-class
once, in one place.

### 3.2 `attachments` — the immutable original

| Column | Meaning |
|---|---|
| `id`, `created_at` | uuidv7 identity of the *content instance*; when it entered |
| `sha256` | FK → `blobs`. **Unique** — one content instance per distinct bytes. |

Identity is the content, not the act; the acts live in §3.3. *(Amendment 4:
no classification column here — bytes do not have a classification; the act
does.)*

**Why the table is this thin, and stays** *(correction 3)*: `blobs.sha256`
means *these exact bytes exist in the content-addressed store*.
`attachments.id` means *these bytes have been admitted as an original
conversational attachment and are the root of this provenance tree*. Those
are different concepts, and collapsing them would make five downstream
tables use a cryptographic storage key as their domain identity, muddle a
content store that originals and derived bytes deliberately share, and tie
attachment identity permanently to one hashing scheme.

### 3.3 `message_attachments` — the act *(amendments 4, 5, 10)*

| Column | Meaning |
|---|---|
| `id`, `attached_at` | The act |
| `message_id` | FK → the existing **user** message this act accompanied |
| `attachment_id` | FK → `attachments` |
| `position` | Order within the turn; **unique per message** |
| `given_filename` | The name as provided *at this act* — display, never identity |
| `stated_classification` | **Per act**: `public` \| `internal` \| `protected`, default `protected`, ambiguity resolves upward; `restricted` refused at the act. The `attachments` row is never mutated. |

**Re-use is a new act.** Explicitly re-associating a prior attachment with a
new turn creates a new row here with its **own classification statement,
defaulting `protected` again — never inheriting a weaker class from an
earlier act** — and its own egress decision, over the same content row. A UI
may pre-fill; the record is this act.

**Evidence begins at the successful send commit, after admission preflight
succeeds** *(amendment 10, boundary revised by correction 1)*: composer
selection is ephemeral client state and writes nothing. The sequence:

> send → **admission preflight** over the ephemeral candidate bytes — hash,
> byte size, actual media type, decodability, dimensions, format support →
> admission succeeds → **atomic evidence commit** (blob, attachment,
> association, and the user message together, in the same transactional
> motion that already persists the message before any provider is contacted)
> → later processing.

**The admission probe is pre-commit validation of ephemeral candidate bytes,
not an attachment-processing event** — the attachment identity does not
exist yet, and no temporary attachment row is invented so the probe can
record itself. **Failed admission writes nothing**: no blob, no attachment,
no association, no processing event, and no user message from that send.
Remove-before-send therefore never created an immutable row —
attach-preview-remove-choose-another accumulates no evidence of things never
sent.

### 3.4 `attachment_representations` — typed derived views

| Column | Meaning |
|---|---|
| `id`, `created_at` | |
| `attachment_id` | FK → the one identity every view resolves to |
| `parent_representation_id` | Nullable FK → this table. NULL = derived directly from the original. |
| `representation_type` | Typed, from the declared vocabulary (§9). v1 declares exactly one: `model_input_image` — bytes actually transmitted when they differ from the original (resized/re-encoded for provider limits). |
| `sha256` | FK → `blobs` — the derived bytes |
| `locator_ordinal` | Nullable int, 1-based page/slide within the parent; NULL = whole parent. (Declared for the documents sibling; v1 leaves NULL.) |
| `locator_region` | Nullable `x0,y0,x1,y1` in pixel coordinates of the parent's bytes; NULL = whole of what `locator_ordinal` selects |
| `derived_by` | Tool and pinned version (string is v1-sufficient — the derived sha256 carries identity; structured derivation parameters may be proposed when a representation type actually needs them, non-blocking) |
| `model_config_id`, `model_call_id` | Nullable FKs, non-null exactly when a model produced the representation; v1 derivations are local and leave both NULL |

**Complete at insert**: a row exists only for a derivation that succeeded,
and is immutable.

### 3.5 `attachment_processing_events` — attempts, honestly *(amendment 6)*

| Column | Meaning |
|---|---|
| `id`, `created_at` | |
| `attachment_id` | FK |
| `attempt_id` | **Durable attempt identity** (uuid). All events of one attempt share it; terminal events refer to the attempt they end. |
| `intent` | What is being attempted (`derive:model_input_image`, `verify`, …). **Not `probe`** *(correction 1)*: the admission probe is pre-commit and ephemeral (§3.3) — the identity this table requires does not exist yet. A later re-probe or verification of an *already-ingested* attachment may be an evidence-class attempt; the admission probe cannot be. |
| `event` | `started` \| `succeeded` \| `failed` |
| `representation_id` | Nullable FK — on `succeeded` derivations, what was produced |
| `error` | Verbatim, on `failed`; NULL otherwise |

Append-only; **current state is derived from the event sequence, never
mutated.** *(Correction 6)* — and a derivation therefore requires the
contract to say what a **valid sequence** is:

1. Exactly **one `started` per `attempt_id`**.
2. **At most one terminal event** (`succeeded` or `failed`) per `attempt_id`.
3. A terminal event **matches its `started`'s attachment and intent**.
4. `failed` **requires** `error`.
5. A `succeeded` derivation naming a representation requires that
   representation to **belong to the same attachment**.
6. A successful derive commits **the representation row and the `succeeded`
   event in ONE transaction.** This is the rule that matters most: without
   it, the representation row commits, the process crashes, the success
   event never lands — and the representation says *done* while the trail
   says only *started*: two evidence sources disagreeing about one fact.

The honesty rules, stated as contract:

- `started` with no terminal event means exactly **"started; no terminal
  outcome recorded"** — never, automatically, "currently processing." A
  crash after `started` leaves the same durable sequence as a live attempt,
  and the record does not pretend to know the difference.
- The interface may render *active* processing **only while the executing
  runtime can independently establish the attempt is still live** (its own
  in-process handle). After crash, restart, or lost liveness, the durable
  state renders as **incomplete or unknown** — one false spinner is not
  fixed by building a spinner that becomes false after a crash.

### 3.6 `model_call_image_inputs` — the image inputs bound to the call *(amendments 2, 3, 4, 11; corrections 4, 7)*

Name lineage, deliberate at every step: v1.0's `model_call_sight` overclaimed
sight; v1.1's `model_call_inputs` overclaimed being the authoritative record
of *all* inputs to a call, which it is not — it carries width, height,
transmitted image media type, and visual provider options. Documents, audio,
and video inherit this substrate later and must not inherit a name that
overclaims; renamed **before the table exists** *(correction 7)*. The row
proves **which image bytes were bound to a recorded call** — it cannot by
itself prove she saw them.

| Column | Meaning |
|---|---|
| `id`, `created_at` | |
| `model_call_id` | FK → the existing call row |
| `message_attachment_id` | FK → the exact **participating act** (§3.3), *(correction 4)* — structurally required to match this row's `attachment_id` (§5). Same attachment used `internal` on Monday and `protected` on Thursday: this names which act supplied the image to this call. |
| `attachment_id` | FK — the identity |
| `input_kind` | **`original` \| `representation`** — explicit discrimination, no semantic NULL |
| `representation_id` | FK, **required iff `input_kind = 'representation'`, NULL iff `'original'`** — check-constrained as a pair |
| `transmitted_sha256` | FK → `blobs`: the exact bytes bound to this call. One lookup, no reconstruction. Must equal the referenced original's or representation's digest (integrity rule, §5). |
| `width`, `height` | Read from the **decoded bytes**, never trusted from EXIF *(amendment 11)* — the dimensions of the transmitted bytes, which are what priced the call (§8) |
| `media_type` | As transmitted |
| `provider_options` | Any provider option that changes pricing or interpretation (e.g. a detail level); empty when none |
| `stated_classification` | Copied from the participating act at send *(amendment 4)* — kept even though the act is now named directly, so the egress record remains self-contained |
| `position` | Order within the call's payload; **unique per call** |

**The chain, complete** *(correction 4)*: call → image input → attachment
act → attachment → original blob.

These are the **facts that priced and transmitted the image**, preserved so
the reservation's factual basis survives — *not* so historical cost can be
recomputed; doctrine forbids that, and settlement stays as recorded at call
time.

## 4. When sight may be claimed *(amendment 3; correction 5)*

**The existing `model_calls` lifecycle already provides the distinction, and
this contract references it rather than adding machinery — stated
explicitly:** since migration `0010`, every call durably records
`terminal_state`. Evidence of sight is the conjunction:

> `model_call_image_inputs` rows **and** the call's `terminal_state` is
> **`complete`**.

**`refused` is not sight** *(correction 5)*: a provider refusal can be
produced by a safety layer that never ran vision, so claiming she saw the
image would go beyond what is known — exactly the invariant 29 failure.
`refused` establishes a provider-issued refusal and nothing more, **unless a
provider-specific contract demonstrably guarantees the visual input was
processed before that state is issued** — and no such guarantee is claimed
for any v1 route. Nothing is lost: a refused call produces no visual
judgment anyway.

`failed` (transit error; pixels may or may not have left the machine) is
**never** sight — the same crash-boundary honesty as cost, and no certainty
is manufactured about it. `unknown` fails closed here as it does everywhere.
`truncated`/`filtered` establish that the provider processed the input, but
no judgment is persisted from such calls anyway; nothing may cite them as
sight-behind-a-judgment because the judgment does not exist.

## 5. Structural integrity — contract, not the migration's good will *(amendment 8)*

Binding on the migration, enumerated:

1. A representation's parent belongs to the **same attachment** (composite
   FK `(parent_representation_id, attachment_id)` →
   `attachment_representations(id, attachment_id)`).
2. **No self-parent** (`parent_representation_id <> id`); **no cycles** —
   structurally impossible given insert-only rows and a parent that must
   already exist, and the self-parent check closes the one degenerate case.
3. An input row's `representation_id` belongs to its stated `attachment_id`
   (same composite-FK device).
3a. An input row's `message_attachment_id` names an act whose
   `attachment_id` **equals the input row's own** *(correction 4)* — the
   same composite-FK device, so the act linkage cannot quietly point at a
   different file's act.
4. `transmitted_sha256` equals the digest of the named original or
   representation (enforced mechanism chosen at migration time; the rule is
   contract).
5. `position` unique per message (§3.3) and per call (§3.6).
6. Associations and input rows **outlive the message and call they
   reference** the way `execution_events` outlive conversations: NO ACTION
   everywhere, no cascade delete, hard delete refused.

## 6. Egress, eligibility, and the honest v1 limit

An image is external egress, same as text. The effective classification of a
call is the **strictest** of its text parts and every *participating act's*
stated classification; routing and eligibility refusals run on that through
the **existing gateway** — no new entrance, no side door.

Stated plainly: the Restricted content preflight reads text and cannot read
pixels. v1 images are classified by Lord Armand's statement per act, default
`protected`, upward resolution. There is no pretend image scanner; the
absence is a recorded v1 limit.

## 7. Vision and the deliberation machinery *(amendment 7)*

**The blind call and the response bind the same ordered image-input set**:
same attachment identities, same `transmitted_sha256` per position, same
provider options that change interpretation or price. **Derive once, reuse**
— the two calls must not independently resize or re-encode. If the blind
call does not get the images, she forms a position on a description rather
than the work — the exact inferior evidence class Track C exists to
eliminate. If the two calls see different bytes, the deliberation ledger is
theatre. Both calls' `model_call_image_inputs` rows make the binding checkable
after the fact.

**The claim boundary, stated because pixels can carry preference** (an
annotated sheet reading "MY FAVORITE" over option A defeats the blind
position while textual stripping reports success): **`ordering = enforced`
on a visual turn means the *text* was stripped. It does not mean the pixels
were preference-free.** No image redaction and no preference detector is
built. When preference in an image is noticed, the existing `contaminated`
marking and manual-override path apply. Successful text-stripping is never
described — in records or interface — as a blinded *visual* deliberation.

## 8. Cost, within existing doctrine *(amendment 11; corrections 2, 8)*

**Reserve from the transmitted bytes, not the original** *(correction 8)*.
Amendment 11's probe-before-reserve was written against the original, but
transmission may use a `model_input_image` derived after admission — and
reserving from the original's dimensions while sending a resize is another
invented number, the exact class of defect this review exists to catch. The
order, binding:

> **admit → derive if needed → reserve from the dimensions of the bytes that
> will actually be sent → call.**

`maximum_cost`'s image term is computed from the transmitted bytes'
dimensions via each provider's published dimensional formula (a
registry-adjacent fact, verified and dated like every rate); those same
dimensions land on the `model_call_image_inputs` row, so the reservation's
basis and the transmission record are one set of facts. Dimensions are
always read from decoded bytes, never EXIF. Settlement continues from
returned usage, unchanged; reservations, expiry, and `cost_certainty`
doctrine untouched. **The STOP condition stands**: if any provider's image
pricing cannot be expressed through the existing doctrine, halt and present
— do not adapt.

**Double transmission is structural** *(correction 2)*: a consequential
visual turn transmits the ruled image-input set to **both** the
blind-position call and the final-response call, so image-input cost is
incurred on both. This is a structural consequence of genuine visual
anti-sycophancy, **not duplicate work to be optimized away** — cost pressure
must not cause either call to omit, alter, or independently re-derive the
visual input. Provider caching or discounted repeated input may reduce
*settlement* if the provider reports it; **never reserve as though it
will.** Estimated ordinary and consequential visual-turn costs are part of
the §2 pre-implementation measurement report; operating targets live outside
this contract, and eligibility and existing budget doctrine remain
authoritative.

**Preview**: no `ui_preview` in v1. The composer renders the selected
original from ephemeral local bytes; after send, the client may downsample
from the original blob. If that becomes intolerable, `ui_preview` is
declared as a representation type **before those bytes exist** — no unnamed
thumbnail ever sits on disk.

## 9. Scope boundaries and extension rules

**Automatic recall stays out of v1** — Val does not pull Monday's sheet on
Thursday because the conversation mentioned it; retrieval doctrine for
attachments is its own future decision. **Explicit re-association is
permitted and is not retrieval** *(amendment 5)*: selecting a prior
attachment for a new turn is a new act under §3.3 — new association row, new
classification statement, new egress decision, one content row. The picker
UI is not required in the first slice, but nothing in this contract may be
read as forbidding re-attachment.

Also not in v1: document parsing, text extraction, OCR, page rendering (the
waiting sibling — representable above, deliberately, but no type declared);
audio and video; filesystem access; Val-produced attachments; attachment
editing or deletion.

**Contract-stable, not frozen:**

1. Additive `representation_type` values are permitted without re-ruling.
2. New locator kinds are additive nullable typed columns, by amendment here
   — never by overloading an existing column.
3. **Core provenance semantics may not be privately changed by either
   sibling**: content-hash identity, one-file-one-tree, parent/child links,
   complete-at-insert immutability, per-act classification, the
   `model_call_image_inputs` binding, and the §4 sight-claim rule are the core.
   A sibling finding a core assumption wrong stops; the contract is amended
   deliberately.
4. Every amendment is dated, attributed, and notes which consumer forced it.

## 10. Open-problem checkpoints (procedural rule, fired)

- **OP-3** closes with this substrate's implementation: the
  exact-composition assertion lands — the assembled request contains exactly
  the enumerated parts, now including explicitly declared attachment parts,
  and nothing else.
- **OP-1** is *narrowed, not solved*: claims about what she received become
  checkable against `model_call_image_inputs` plus the §4 sight rule — a
  deterministic record where none existed. Claims of approval and completion
  remain uncovered; OP-1 stays open with its remaining checkpoints.
