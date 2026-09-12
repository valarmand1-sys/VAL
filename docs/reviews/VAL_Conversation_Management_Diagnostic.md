# Conversation and message management — diagnostic, 12 September 2026

Diagnostic only, on Lord Armand's instruction of 12 September 2026. Read-only inspection of the live schema (`information_schema`, `pg_trigger`, `pg_proc`), migrations `0001`–`0015`, the gateway (`conversations.py`, `loop.py`, `memory.py`, `context.py`, `deliberation.py`, `execution.py`, `provenance.py`, `persistence.py`), the API (`app.py`, `contracts.py`) and the desktop (`App.tsx`, `scope.ts`, `api.ts`). No code, schema, test, API or runtime behaviour changed. No provider call.

The user-facing need: edit sent messages; remove sent messages from the working conversation; rename conversations; remove conversations from the sidebar; move conversations between projects and the unassigned pool. The binding principle (`04-layer-0.md` §2.1, requirement of 31 August 2026): **correction and retraction, never silent rewriting of history.**

---

## 1. The current schema and its immutability protections

### 1.1 `messages`

`id`, `conversation_id` (FK → conversations, NO ACTION), `role` (`user` | `val` | `system`), `content`, `created_at`, `sequence`. Unique `(conversation_id, sequence)`; `sequence` is assigned under the conversation row lock (`FOR UPDATE`) and is gapless by WP-0.7's criterion. GIN full-text index on `to_tsvector('english', content)`. **UPDATE refused** (`messages_rows_are_evidence`, migration `0009`); **DELETE refused** (`messages_forbid_hard_delete`, §2.3). `append` writes content exactly as given. There is no revision, retraction, supersession or state column, and no sidecar table that references a message other than the evidence tables below.

### 1.2 `conversations`

`id`, `project_id` (nullable; NULL is an explicit no-project state, since the only writer refuses an unresolved scope), `title`, `started_at`, `last_message_at`, `archived_at`. **`project_id` immutable** (`conversations_scope_is_immutable`, migration `0008`, BEFORE UPDATE: "moving it would rewrite what they mean. Switching project starts a new conversation (WP-0.6, forward-only)"). `title`, `last_message_at`, `archived_at` mutable by the `0009` matrix ("lifecycle"). DELETE refused. `archived_at` is ruled presentation scoping with no evidentiary meaning (31 August 2026, migration `0012`).

### 1.3 The evidence tables anchored on messages

Every foreign key is NO ACTION; every table below refuses UPDATE and DELETE.

| Table | Anchor | What it records against the anchor |
|---|---|---|
| `model_calls` | `message_id` (nullable), `conversation_id`, `project_id`, `project_attribution` | `provenance.py` refuses a conversation call whose `message_id` is not a `user` message of that conversation. The response call for a turn is anchored on **the user message that opened the turn**. Classification, strip and blind-position calls are anchored likewise (`deliberate.py`). Cost, tokens, terminal state, persona revision, cache split (`model_call_cache_usage`). |
| `classifications` | `message_id` (user), `conversation_id`, `project_id`, `model_call_ids`, `resolving_model_call_id` | The verdict formed on the text of that message; `classification_labels` and `classification_reviews` hang off it (the fifty hand labels). |
| `blind_positions` | `message_id` (user), `model_call_id`, `persona_id` | `position`, `reasoning`, **`stripped_content`** — the span removed from that message's text — `ordering`. |
| `deliberations` | `message_id` (user), `blind_position_id` | `position`, `stripped_content`, **`user_response`**, `outcome`, `what_changed_her_mind`, `both_positions`, `predictions`. |
| `execution_events` | `message_id` (any role; checked to belong to the conversation), `subject` (free text) | Acceptances, rejections, revision requests, corrections, reactions, reasons. |
| `budget_reservations` | `model_call_id` | Reserved before the call; settled from usage. |

Nothing stores the provider request body. "What did this call receive" is today a deterministic reconstruction from the rows plus the ruled assembly (the 11 September native-turn diagnostic reconstructed two requests byte-identically this way). That reconstruction assumes `messages.content` is what it was at assembly time — which is exactly the assumption revision breaks (§3.4).

### 1.4 What the interface reads

`GET /conversations/{id}` returns the messages in sequence and the four evidence lists; the desktop `MessageBlock` attaches blind positions, manual deliberations and execution events to a message **by `message_id`**. Recall excerpts carry `conversation_title` into the provider payload (`recall_block`), so the title is presentation that Val does see.

---

## 2. Existing rename and archive capability

**Rename.** `title` is mutable at the database level and the `0008` docstring anticipates it ("Retitling a conversation changes a label; rescoping it changes what the record means"). **No application writer exists**: no gateway function, no API route, no desktop control. The title is set once from the first line of the first message (`_title_from`, deterministic, no model call). No evidence table, foreign key, query or test depends on the title; provenance is by id everywhere. The only reader outside listings is the recall envelope, which shows the *current* title beside a recalled excerpt — so a rename changes what a later payload displays as the source, not what the record attributes.

**Archive.** `archived_at` exists on `projects` and `conversations`; the listing (`conversations.listing`, `GET /conversations?archived=`) and the desktop "Show archived" toggle honour it. **No application writer exists** either: the only rows ever archived are the eighteen fixtures marked by migration `0012`. `load`, `resume`, recall (both paths) and every capture path are archive-blind, by ruling and by test (`apps/api/tests/test_archive.py`).

So today Lord Armand can rename nothing and archive nothing from the product. Both operations have their semantics already ruled and their storage already present.

---

## 3. Message revision — the smallest append-only representation

### 3.1 What the record must be able to say

For a user message A later corrected to A2, and separately for a message later withdrawn, the record must answer: what was originally sent; what it was corrected to; which text is current; **which exact text a given model call, classification or deliberation received**; what ordinary assembly, automatic recall and House Recall use; and whether the original is recoverable on explicit request. And a revision must never change the input of a call made before it.

### 3.2 Shapes considered and rejected

- **A new `messages` row that "revises" an earlier one.** Rejected: it would take the next `sequence`, placing the corrected text at the *end* of the conversation rather than at the position of the message it corrects; every reader of the thread would have to reorder; and it would need a link column on the frozen `messages` table.
- **A mutable "current content" column beside the original.** Rejected: `messages` is frozen by `0009`, and rightly — a message is what was said.
- **Timestamp-based "as of" reconstruction** (a revision is in force for a call if `revision.created_at < model_calls.created_at`). Rejected as inexact: `model_calls.created_at` is settlement time, not assembly time; a revision landing during a call's flight would appear to have been received; and PostgreSQL `now()` is transaction start, so two writes serialised by a lock can still carry out-of-order timestamps. The repository already learned this lesson for message order ("sequence, and why it is not a PostgreSQL sequence").
- **A per-call manifest of every history message received** (the shape of the attachment contract's `model_call_image_inputs`). Exact, but universal on every turn — dozens of rows per call — to answer a question the ruled deterministic assembly can answer without them once the revision's position in the conversation's order is a lock-assigned integer. Kept as the stronger alternative if Lord Armand wants per-call exactness stored rather than derived.

### 3.3 Recommended: one append-only sidecar, ordered by the conversation's own counter

**`message_revisions`** — new table, frozen and undeletable like the evidence tables, no column added to `messages` or `conversations`:

| Column | Meaning |
|---|---|
| `id`, `created_at` | uuidv7; when the fact was recorded |
| `conversation_id` | FK; denormalised for the query paths, checked equal to the message's |
| `message_id` | FK → `messages`. **Must be `role = 'user'`** (retraction authority is per-author, `04-layer-0.md` §2.1) — enforced by the one writer and by a trigger the way `provenance.py` and `0008` enforce their rules |
| `revision_number` | 1, 2, 3 … per message, assigned under the conversation row lock |
| `after_sequence` | **The conversation's highest `messages.sequence` at the moment this fact was recorded**, read under the same lock. This is the fact that makes every historical question exact (§3.4) |
| `kind` | `revision` \| `retraction` — explicit discrimination, no semantic NULL (the attachment contract's rule) |
| `content` | The corrected text; **required iff `kind = 'revision'`, NULL iff `retraction`** (check-constrained as a pair) |
| `authored_by` | `'Lord Armand'` — the only author who may write here |
| `note` | Optional short reason ("typo", "wrong conversation"). Nullable in v1 unless ruled otherwise; a typo needs no reason and `execution_events` doctrine on fabricated reasons argues against demanding one |

Rules, stated as contract:

1. The original `messages` row is never touched. A revision or retraction is a new row here.
2. **Current text** of a user message = the `content` of its highest-numbered `revision` row, unless a higher-numbered `retraction` row exists, in which case the message is **retracted**; with no rows, the original. A revision after a retraction reinstates the message with the new text — so "undo" is one more appended fact, never a delete.
3. `messages.sequence` stays gapless: a revision consumes no message sequence number. `after_sequence` places the fact in the conversation's order without a shared counter.
4. **A turn's view of history is defined by its own sequence.** The turn whose user message has `sequence = s` sees, for every earlier user message, the current text **as of `after_sequence < s`** — revisions and retractions recorded after that turn's message was appended are invisible to it, by construction and regardless of concurrency. Assembly reads "as of s", not "most recent".
5. A Val message is never revised or retracted; nothing here references a `val` row.

### 3.4 The eight questions, answered on this model

| Question | Answer |
|---|---|
| What did Lord Armand originally send? | `messages.content` for that id — unchanged, forever. |
| What did he later correct it to? | The `revision` rows for that id, in `revision_number` order; the most recent is the current wording. |
| Which is current for ordinary conversational use? | The most recent fact (rule 2). |
| Which exact text did a particular call, classification or deliberation receive? | The call is anchored on the user message that opened its turn, sequence `s`. For every history message it received the text as of `after_sequence < s` (rule 4); for its own anchoring message it received the original — a turn's own message cannot have been revised before the turn existed. Deterministic from the rows, no timestamps. |
| Which version should current-thread assembly use after the correction? | The current text (rule 2), read as of the new turn's own sequence (rule 4) — which is the most recent, since the new turn is newest. |
| Which should automatic recall retrieve? | The current text, marked corrected (§6). |
| Which should House Recall retrieve? | The current text, marked corrected, with the original date of the utterance **and** the correction date, never presenting the corrected text as what was originally said (§6). |
| Can Val recover the original if explicitly asked? | The original is on the record and in the interface's history view. Whether it enters Val's *context* on request is a separate small behaviour (a gated history-inspection path, §6.4) and is not implied by this model. |

**A current revision never changes the input of an earlier call**: rule 4 makes the earlier call's input a function of rows that were fixed when the call's turn was opened.

---

## 4. The downstream-answer problem — an owner ruling

User message A → Val answer B. A is edited to A2. B was generated from A. Later turns C, D … may have been written after B.

### Option 1 — B stays visible, belonging to the historical A; A2 becomes current

The thread shows A2 in A's position, marked corrected, with the original one click away; B follows it, marked "answered the earlier wording"; C, D … unchanged. For the provider: the next turn's retained history carries A2 then B. **The honest hazard**: Val then reads an answer that may not fit the question in front of it. Mitigation without editing the pair: the record-state envelope (already the place where the house tells Val what the record is) states the positions corrected after being answered — "the message at position 7 was corrected after Val answered it; her answer at 8 addressed the earlier wording" — so she reads B for what it was. Downstream turns: nothing pretends they answered A2; the envelope fact covers them by implication (they came after 8). **Smallest, and truthful in both the record and the payload.** Cost: one deterministic envelope addition; a ruling, because it changes what Val is told.

### Option 2 — B hidden from the working branch, kept in history and evidence

The thread shows A2 with no answer beneath it. Clean for the last exchange; wrong mid-conversation: C and D may refer to B, and hiding B alone leaves them answering nothing visible. It also removes Val's own words from ordinary sight on Lord Armand's edit, which sits awkwardly with "Val's answers are hers". Workable only as a special case of the last exchange, and Option 1 already handles that case acceptably.

### Option 3 — a branch from A2, preserving A → B separately

The chat-product model. Truthful, and the only model in which "downstream turns responded to A2" can ever become true (because they would be new turns on the new branch). Cost: `messages` is linear by `sequence`; branching needs a parent pointer or a branch identity, assembly must pick a branch, the sidebar and detail must show and switch branches, recall must decide which branches are searchable, and every evidence reader must learn which branch a row sits on. A large change to the conversation model, not a sidecar. Not recommended before the gate; recorded as the honest large option.

### Option 4 — appended correction rather than replacement (mid-thread)

When A already has downstream turns, "edit" appends a new user turn "correction of A: A2" (a `revision` fact with `after_sequence` at the end, *plus* an ordinary new message is not needed — the fact alone, surfaced in the envelope, tells Val the correction). In effect Option 1's data with Option 1's envelope, minus the in-place display. It reads chronologically and never re-poses history; but it does not give him what he asked for — the message corrected where it sits.

**Recommendation: Option 1**, with the envelope statement, and with **no regeneration implied by an edit** — Val's new answer is a new turn only if he sends one. Ruling required on: (a) Option 1 as the semantics; (b) whether the envelope carries the "corrected after being answered" facts (recommended yes; without it the payload is truthful but the pair is silently incoherent); (c) whether the last-exchange case (A is the newest user message and B the newest answer) should offer "correct and re-ask" as one gesture — which would be an edit *and* a new turn, two events, the second a provider call he initiates explicitly.

---

## 5. Retraction semantics — the smallest honest rule

The requirement: a retracted message stops cluttering the live conversation and stops functioning as live intent while remaining in the authoritative record. The distinction that settles most of the questions: **ordinary recall of current conversational truth** versus **explicit historical inspection**.

| Surface | Recommended rule |
|---|---|
| Current-thread assembly | The retracted user message is omitted from the retained thread (as of the new turn's sequence). **Its Val answer B is omitted with it** — B without A is noise that reads as Val volunteering something; omitting it from *assembly* is context policy, not a retraction of her words, which stay on the record. The envelope states "n exchanges withdrawn at positions …" so she can acknowledge a withdrawal if asked and never treats it as live. Downstream turns C, D … stay: they happened. |
| Automatic project recall | Retracted user messages and their immediate Val answers are excluded from the ranked set — a `WHERE` predicate inside the query, the same shape as project isolation, never a post-filter. A retracted message must not return as active intent because full-text search matched it. |
| House Recall | Same exclusion by default. House Recall is access to relevant prior *conversation*, and a withdrawn statement is not conversation Val may treat as said. |
| Transcript / history inspection | The interface's detail view shows the retracted message in place, collapsed, marked "withdrawn on <date>", expandable to the original, with B beneath it marked "answered a withdrawn message". The record does not pretend it never existed. |
| Val's answer B | On the record, unchanged, hers. Excluded from ordinary assembly and recall as above; visible in inspection. |
| Downstream messages | Unchanged everywhere. |
| Judgment and deliberation evidence | Unchanged rows, still anchored on the original message, still shown against it in inspection; still evidence of the mechanism having run on real use (§8). |
| Cost | Unchanged; the retracted exchange's calls and costs stay attributed and stay in every total. The detail shows them on the withdrawn exchange exactly as on any other, which answers the requirement's open question "how the sunk cost of a retracted exchange is shown": the same way, with the exchange marked withdrawn. |

**Ruling required** on: whether explicit House Recall may ever surface retracted content when Lord Armand asks about the history of a retraction (recommended: not through recall; through the interface, and later through a deliberately gated history-inspection path that presents it as withdrawn); and whether B leaves ordinary assembly with A (recommended yes).

---

## 6. Ordinary recall and House Recall for current, revised and retracted messages

| Message state | Automatic recall | House Recall |
|---|---|---|
| Current (no facts) | As today | As today |
| Revised | Ranked and returned on the **current** text; excerpt marked `corrected: true`, carrying `revised_at` and the original message id (the original text recoverable by id, not injected) | Same, plus the existing `created_at` (when it was originally said) **and** the correction date; the envelope note extended: "an excerpt marked corrected shows the current wording; the wording at the recorded time differed and is on record" |
| Retracted | Excluded from the ranked set, in the query | Excluded, in the query |
| Val's answer to a revised message | Returned as today, marked "answered an earlier wording of the preceding message" | Same |
| Val's answer to a retracted message | Excluded with it | Excluded with it |

**Mechanics.** Both recall statements are written out in full for auditability; they would gain a lateral join to the most recent `message_revisions` fact per message (or a `messages_current` view stating the rule once, in the `model_calls_accounted` manner), rank on the current text, and exclude retracted rows in the `WHERE`. The full-text index exists on `messages.content`; a matching GIN index on `message_revisions.content` keeps a revised message findable by its corrected words. The `CrossProjectLeakError` second check and every isolation test stay as they are: revision changes *which text* a row contributes, never *which scope* it is in.

**Val's own history inspection (6.4).** "What did I originally say before I corrected it?" is an explicit historical question, not recall. It could be served by a small deterministic gate in the House Recall family that admits the original wording as an excerpt marked "superseded on <date>". Not designed here; noted so the ruling can say whether Val may ever see a retracted or superseded wording in context.

---

## 7. Conversation-level management, each operation separately

### 7.1 Rename

Supported safely by the existing mutable `title` once a writer exists: one gateway function, `PATCH /conversations/{id}` with `title`, one desktop control. No provenance or evidence depends on the title. One known imprecision, stated rather than solved: a historical payload reconstructed after a rename would show the current title beside a recalled excerpt where the call actually saw the old one. If Lord Armand wants exact title history, the smallest cure is an append-only `conversation_titles` log; recommended **not** in v1 — the title is ruled lifecycle-class presentation, and the cost of exactness here is out of proportion.

### 7.2 Archive — remove from the sidebar

`archived_at` **fully satisfies** "I don't want to see this in the sidebar" once a writer exists: `POST /conversations/{id}/archive` and `/unarchive`, a desktop control, the existing "Show archived" toggle for recovery. It **does not satisfy** any expectation beyond the listing, by ruling: an archived conversation still resumes; its messages are still ranked by automatic recall in its scope and by House Recall; its evidence and costs are untouched. If "remove" is meant to stop a conversation influencing Val, archiving alone is insufficient under the current contract.

### 7.3 Delete conversation

Not hard deletion (§2.3; every table refuses it). The candidates:

- **Archive only.** Sidebar clean; everything else unchanged. Sufficient for clutter, insufficient for "stop remembering this".
- **Conversation-level retraction (a withdrawal state), distinct from archive.** An append-only `conversation_retractions` row (conversation, created_at, note; a later `reinstated` row reverses it). Effects: the conversation's messages leave ordinary recall on both paths (query predicate); **resume for new turns is refused** while withdrawn (a withdrawn conversation is closed; reinstating reopens it); history, evidence, judgments and costs unchanged and inspectable; the sidebar shows it under "withdrawn" beside "archived" when the toggle is on. Never a per-message retraction of Val's words — it withdraws the *conversation* from live use, not her authorship.
- **Both**, as two verbs: "Archive" (hide) and "Remove" (withdraw). **Recommended.** They answer different intents and neither alone covers the other.

**True erasure** — bytes gone for privacy or legal reasons — is a separate governed operation: it would need the no-delete and frozen-row triggers relaxed under a specific migration, a redaction design that preserves digests, sequence positions, costs and evidence anchors while removing content, and backup and PITR implications (a restore would resurrect erased bytes unless the backups are also handled). None of that is designed or implied here, and the ordinary interface must not use "Delete" to mean it.

### 7.4 "Delete" as a label

The ordinary UI **may** present the action as Delete only if it cannot be read as erasure: the confirmation says what happens ("Removed from this conversation and from what Val ordinarily remembers. It stays in the House record with its evidence and cost, marked withdrawn."), the history view shows the withdrawn item collapsed and marked rather than absent, and no wording anywhere says permanent, erased or destroyed. **Recommended label: "Remove"** for messages and conversations, with "Archive" as the separate hide verb, and the word "Delete" kept out of the product until a true-erasure operation exists to own it. This is a labelling recommendation, not a ruling on semantics.

---

## 8. Moving conversations between projects — the architectural conflict

`conversations.project_id` is immutable (`0008`), because every message and every attributed `model_calls` row in the conversation says it was held in that scope, and WP-0.6 ruled scope switching **forward-only** — a switch starts a new conversation. "Move to project" as an UPDATE of `project_id` is refused by the database and would falsify provenance if it were not.

### Option A — filing separate from origin attribution

A mutable, nullable organisational field — `filed_project_id` on `conversations`, or a sidecar `conversation_filings` (recommended over a second project column on the row: two project columns with different meanings on one row is the exact ambiguity the attribution work removed). Origin `project_id` stays immutable.

| | |
|---|---|
| Sidebar | Lists by filing (falls back to origin) |
| Resumed scope | **Origin.** New messages and calls are attributed to the origin scope |
| Automatic recall | Origin scope, unchanged; every isolation test stands |
| House Recall | Unchanged; excerpts could additionally show "filed under" |
| Old model calls | Untouched |
| Old vs new messages in different scopes | No — all in origin |
| `project_id` immutable | Yes |
| Schema | One sidecar table or one mutable column; no migration on frozen tables |
| Failure modes | The gap: a conversation begun unassigned and filed under Project B continues as an unassigned clean room — Val does not get B's material automatically, and the sidebar says B. Honest but surprising; the interface must show "created unassigned · filed under B" |

### Option B — scope transitions with immutable history

Append-only `conversation_scope_transitions` (conversation, from, to, `after_sequence`, created_at). Effective scope of a message = the last transition with `after_sequence` below its sequence, else origin; `conversations.project_id` remains the origin.

| | |
|---|---|
| Sidebar | By current effective scope |
| Resumed scope | Current effective scope; new messages and calls attributed to it |
| Automatic recall | Per-message effective scope — the in-project statements join a `message_scopes` derivation; isolation must hold per message |
| House Recall | Unchanged mechanically; `source_scope` becomes per message |
| Old model calls | Untouched, still attributed to the scope in force when made |
| Old vs new messages in different scopes | **Yes, truthfully** — the only option where this is so |
| `project_id` immutable | Yes (it becomes "origin") |
| Schema | One table plus a derivation the recall queries and the loop must use; `ProjectScope` on resume becomes sequence-dependent |
| Failure modes | Reverses the forward-only doctrine: a conversation spans scopes, the retained thread of a Project B turn carries Project A material as same-conversation history (cross-scope by construction, though explicitly authorised by the move), and every place that reads `conversation.project_id` as *the* scope must be found and changed. The most truthful model and the largest |

### Option C — fork or continue, never move

The original stays where it was created, optionally archived; "Continue in Project B" creates a new conversation in B with `continued_from_conversation_id` recorded (an append-only sidecar, or a nullable FK on the new row set at creation and never changed).

| | |
|---|---|
| Sidebar | Two conversations, the link shown on both |
| Resumed scope | The new one is B; the old one is what it was |
| Automatic recall | Unchanged; the continuation does not see its parent automatically (that would be cross-scope) |
| House Recall | The explicit path already reaches the parent; a deterministic "continuation reads its parent" rule could be ruled as an explicit owner act, in House Recall's family |
| Old model calls | Untouched |
| Different scopes | Different conversations |
| `project_id` immutable | Yes |
| Schema | One nullable link or one sidecar |
| Failure modes | Not what "move" means to the user: the thread does not travel; he must re-establish context or rely on House Recall |

### Option D — the cleanest model already in the architecture

Filing as **presentation scoping with no evidentiary meaning** — exactly the `archived_at` doctrine of 31 August 2026 extended to organisation: Option A, ruled explicitly as a label that recall never follows. It is the smallest thing that satisfies "organise under" without touching attribution, recall or a single isolation test, and it composes with Option C for the case where he genuinely wants to *continue* work in another scope.

### Recommendation and the ruling required

**Recommend D (filing as presentation) plus C (linked continuation)**: a sidecar `conversation_filings` (append-only, most recent wins, so re-filing is a new fact) and `continued_from` on continuation. Do not implement B unless Lord Armand rules that a conversation may span scopes, which reverses forward-only.

**The ruling this needs, stated plainly:** does recall follow origin, current filing, or both? The recommendation is *origin*, keeping every isolation guarantee as tested and leaving House Recall as the explicit cross-scope path. If he rules that filing a conversation under B should make it *B work for Val* — automatic recall of B material, attribution of new calls to B — then only Option B delivers that truthfully, and it must be ruled as the reversal it is.

---

## 9. Evidence lineage under revision and retraction

Trace, for an already-completed **consequential** exchange (user message A at sequence `s`, classified consequential, strip enforceable, blind position formed, deliberation recorded, judgment captured), what each row does when A is revised to A2 or retracted:

| Row | Anchored on | After revision / retraction |
|---|---|---|
| `classifications` | A's id | Unchanged. It classified A's text; its `model_call_ids` point at calls that received A. A2 has no classification — it was never sent. |
| Conversation `model_calls` row for the turn | A's id | Unchanged; cost and attribution stand. Its input is reconstructable as of `s` (rule 4): A itself, and history as of `after_sequence < s`. |
| Strip attempts (`model_calls` rows, task `strip`) | A's id | Unchanged; the removed span is recorded in `blind_positions.stripped_content` against A's text. |
| `blind_positions` | A's id, its blind call | Unchanged: `stripped_content` is a span of **A**, `ordering = enforced` is a fact about a call that received A minus that span. |
| `deliberations` | A's id, the blind position | Unchanged; `user_response` is what he then said. |
| Judgment (`execution_events`) | A's id or B's id | Unchanged. |
| Execution events generally | any message id | Unchanged. |
| Cost attribution | the calls | Unchanged; nothing moves to A2, nothing is uncounted. |
| Message provenance | A's row | Unchanged; the `message_revisions` rows say what happened afterwards, and when, in the conversation's own order. |
| Later House Recall | A (current text A2) | Returns A2 marked corrected with both dates; the deliberation evidence is not injected and is not attributed to A2. |

Every row above can still be pointed at and its conversational state reconstructed: the rows it references, the text as of its turn's sequence, the retained thread as of that sequence. **Nothing migrates from A to A2.**

### 9.1 The case that needs naming — an enforced blind position on a message later revised

The rows stay correct. The *presentation* is where the danger lives: if the ordinary thread shows A2 as the message in that position with the deliberation block beneath it, the record appears to assert that the blind position was independent of a preference that A2 no longer contains, or contains differently. That is a false display by juxtaposition, not a broken key — invariant 29 in a new shape.

The options, for ruling:

1. **An exchange that produced an enforced blind position (or any deliberation) may not be revised through the ordinary mechanism.** Deterministic: the writer refuses a `revision` row for a message that anchors a `blind_positions` or `deliberations` row. He may still *retract* it (§9.2) or correct it by an ordinary new turn.
2. **Revision allowed, the consequential branch preserved visibly.** The deliberation block stays attached to the *original* wording and the thread shows "corrected after a deliberated answer; the evidence below concerns the earlier wording", original one click away. Truthful if the display rule is enforced everywhere the evidence is shown — including any future Layer 5 distillation that reads the thread.
3. **Appended correction, not replacement.** A correction to a deliberated message is recorded as a fact but does not replace the message as the current conversational text; the thread shows the original with "correction recorded: …" beneath it. Val's next turn sees the original plus the correction in the envelope.
4. Another rule — none found better than 1 for v1: "materially changes the preference" cannot be decided mechanically, and a rule that needs judgment to apply is a rule that will be applied inconsistently.

**Recommendation: option 1 for revision**, because it keeps the deliberation record's meaning and the thread's appearance in agreement without a display rule that every future reader must honour; typo-class corrections to a deliberated message are rare and are served by a new turn.

### 9.2 Revision versus retraction here

Retraction of a deliberated message is different and should be **allowed**: withdrawing a consequential statement later is legitimate, and the retraction leaves the exchange intact — A, the strip, the blind position, the deliberation, B — as the evidence it is, marked withdrawn in inspection and removed from live intent and from ordinary recall. The evidence still demonstrates the mechanism ran on real use; whether a withdrawn exchange still **counts** toward gate point 5 and toward the fifty hand labels is a ruling (recommended: it counts — the mechanism's execution is what the gate measures, and the label was formed on the text as sent).

---

## 10. Reusable provenance principles, and what not to couple

From the attachment contract (v1.2) and the existing record: the immutable original (`attachments`, the persona row) → `messages`; typed derived views with an explicit discriminator and no semantic NULL (`representation_type`, `input_kind`/`representation_id` as a check-constrained pair) → `kind`/`content`; the act as its own row ("re-use is a new act") → each revision or retraction a row; append-only events with current state *derived* from the sequence (`attachment_processing_events`) → current text derived from `message_revisions`; complete-at-insert immutability and NO ACTION keys everywhere; supersede-by-view (`model_calls_accounted`) → a `messages_current` view stating the current-text rule once. Not reused: nothing in this design references, joins or depends on the attachment tables, and the attachment substrate's own rule that automatic recall stays out of v1 for attachments is unaffected.

---

## 11. Gate status — what could proceed now, and what needs an amendment

The governing documents (`04-layer-0.md` §5 rulings of 31 August, 1 and 2 September 2026; `01-architecture.md` §2.1) place **message revision and retraction** first in the post-gate order and hold "anything touching persistence, recall, routing, evidence semantics, or egress" behind the gate. Prioritising this problem does not repeal that.

**Implementable under current scope without a baseline amendment** — because their semantics are already ruled and they touch no persistence, recall or evidence meaning:

- **Rename**: a title writer, `PATCH /conversations/{id}`, a desktop control. Title is ruled lifecycle-class and mutable (`0008`, `0009` matrix).
- **Archive / unarchive**: a writer for `archived_at`, two routes, a desktop control. Meaning ruled 31 August 2026 (presentation only).

Both are conversation-management interface work, which Lord Armand's standing instruction reserves; they need his go-ahead, not an amendment, and each is additive on the API (existing responses unchanged).

**Requires an explicit owner amendment before implementation**: message revision (§3), message retraction (§5), the recall behaviours (§6), conversation retraction (§7.3), filing and continuation (§8), the deliberated-message rule (§9.1). Each is behind the gate as written, and §6 and §8 change what recall does.

---

## 12. Schema, migration, API, interface and test impact of the recommended models

**Schema and migrations** (one migration each, additive, no column on the seven core tables, every new table frozen and undeletable by the standing functions):

- `message_revisions` (§3.3) with a GIN index on `content`, a role trigger, the `kind`/`content` check, unique `(message_id, revision_number)`; a `messages_current` view.
- `conversation_retractions` (§7.3).
- `conversation_filings` and a `continued_from` link (§8) — only after the ruling.

**API.** `PATCH /conversations/{id}` (title); `POST /conversations/{id}/archive|unarchive`; `POST /messages/{id}/revisions` and `/retractions` (author-only; 409 on a deliberated message under §9.1 option 1); `POST /conversations/{id}/retract|reinstate`; `PUT /conversations/{id}/filing`; `POST /conversations/{id}/continue` (target scope). `MessageView` gains `state` (`current` | `corrected` | `withdrawn`), `content` remains **the current text**, plus `original_content` and `revisions[]` on the detail; `ConversationView` gains `filed_project_id`, `withdrawn`, `continued_from`. Listing and turn routes unchanged in meaning; the settled turn event unchanged.

**Interface states needed to expose the semantics honestly**: a corrected message shows its current text with a "corrected · view original" affordance and the correction date; a withdrawn message is collapsed in place, marked, expandable; a Val answer beneath either is marked "answered the earlier wording" / "answered a withdrawn message"; the deliberation block on a withdrawn exchange stays attached and visible; a withdrawn conversation is listed under its own tag, cannot be continued, can be reinstated; a filed conversation shows "created in X · filed under Y" when they differ; a continuation shows its parent link; the confirmation dialogs state the record semantics (§7.4).

**Deterministic tests required** (new files; none of the existing ones edited):

- `message_revisions` rows are immutable and undeletable; the writer refuses a `val` message, a message from another conversation, and (under §9.1) a deliberated message.
- Current text follows the most recent fact; retract then revise reinstates; `messages.sequence` stays gapless across revisions (the existing concurrency test's property, asserted again with revisions interleaved).
- **As-of exactness**: a call at turn `s` receives the text as of `after_sequence < s`; a revision recorded after the turn is invisible to it; reconstructing the request for an earlier turn after a revision yields the original bytes (the 11 September reconstruction technique, made a test).
- Assembly omits a retracted message and its immediate answer, keeps downstream turns, and the envelope states the withdrawn positions and the corrected-after-answer positions.
- Both recall paths rank the current text, mark corrected excerpts with both dates, and exclude retracted messages in the query — with the exclusion asserted on the returned rows, not only on the SQL (the `CrossProjectLeakError` habit).
- Every evidence row anchored on a revised or retracted message resolves unchanged; counts of classifications, blind positions, deliberations, events and costs are identical before and after.
- Conversation retraction: excluded from both recall paths; resume refused; reinstate reopens; evidence and costs untouched.
- Filing: never changes `project_id` (the trigger fires and the writer never tries); recall follows origin; the listing follows filing.
- API: the routes above, and that a text-only turn's request is byte-identical to today's when no facts exist (backward compatibility as an acceptance requirement, the Track C standard).

**Existing tests that must remain unchanged**: `test_schema.py` (no hard delete; the delete guard on every table; frozen historical rows), `test_conversation_memory.py` (gapless concurrent sequence; project isolation `test_project_b_retrieval_returns_only_b`; the clean-room test as amended for House Recall; `test_a_title_may_still_be_changed`), `test_house_recall.py`, `test_house_recall_gate.py`, `test_project_attribution.py`, `test_deliberation_machinery.py` (evidence rows refuse update and delete; durable before transmission), `test_budget_ledger.py`, `apps/api/tests/test_archive.py` (archive leaves only the listing), `test_turn_stream.py`, and the desktop `scope`, `sse`, `presentation` and `api` tests. Adding a recall predicate for retracted rows must leave every one of these green without edits.

**Conflicts with Layer 0 evidence criteria or append-only invariants**: none in the recommended models — every new fact is an insert, every existing row is untouched, every anchor resolves, every cost stays attributed. The one *tension* is §9.1, which is a presentation-truth problem the ruling resolves. Option B for moving (§8) conflicts with the forward-only doctrine and would need it reversed explicitly.

---

## 13. The owner rulings needed before implementation

1. **Revision model**: `message_revisions` as in §3.3, with `after_sequence` and as-of assembly (rule 4); `note` optional or required.
2. **Downstream answers** (§4): Option 1; the envelope carries "corrected after being answered" facts; no regeneration implied by an edit; whether "correct and re-ask" exists as an explicit two-event gesture on the last exchange.
3. **Retraction** (§5): B leaves ordinary assembly with A; both recall paths exclude retracted exchanges in the query; historical inspection through the interface; whether Val may ever see withdrawn or superseded wording in context (§6.4).
4. **Deliberated messages** (§9): revision refused (option 1) or allowed with visible preservation (option 2) or appended correction (option 3); retraction allowed; whether a withdrawn consequential exchange still counts as gate and label evidence.
5. **Conversation removal** (§7.3): archive plus conversation retraction, with resume refused while withdrawn; the "Remove" / "Archive" labels (§7.4); true erasure stays out of scope.
6. **Moving** (§8): filing as presentation with recall following origin (D + C), or scope transitions (B) reversing forward-only.
7. **Rename and archive now**: go-ahead for the two operations that need no amendment (§11), or hold them with the rest.
8. **Gate**: an amendment to `04-layer-0.md` §5 if any of items 1–6 is to be built before the gate; otherwise this diagnostic is the design on file for post-gate item 1.

---

## 14. The smallest staged plan after the rulings

- **Stage 1 — rename and archive** (no amendment): title writer and archive writer in `conversations.py`; three routes; two desktop controls; tests on the API and the listing; the existing archive tests untouched.
- **Stage 2 — message revision and retraction**: migration `0016` (`message_revisions`, view, index, triggers); the one writer; `conversations.history` gains an as-of reader; `assemble_turn` uses it and the envelope gains the corrected/withdrawn facts; both recall statements gain the current-text join and the retracted predicate; `MessageView` and the detail extended; the desktop states; the test set of §12. Live verification: one corrected and one withdrawn exchange in a scratch-then-live sequence, cost stated first, with the request reconstruction proving the earlier call's input unchanged.
- **Stage 3 — conversation retraction**: migration `0017`; writer; recall predicates; resume refusal; routes; sidebar tag; tests.
- **Stage 4 — filing and continuation**: migration `0018`; writers; listing by filing; `continued_from`; tests proving `project_id` never changes and recall follows origin.

Each stage is its own commit and CI run, deployed only on green, with existing tests as immutable regression evidence throughout. No stage begins without the ruling it depends on.
