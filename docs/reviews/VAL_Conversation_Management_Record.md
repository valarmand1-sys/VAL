# Conversation and message management — implementation record, 12–13 September 2026

Implementation of Lord Armand's ruling of 12 September 2026 on `VAL_Conversation_Management_Diagnostic.md`, recorded as the `04-layer-0.md` §2.1 and §5 amendments of that date (scope-ruling marker `2026-09-12`; `01-architecture.md` §2.1 pointer; `CLAUDE.md` in step). The diagnostic stands unchanged as the pre-implementation record. Four stages, each its own commit with CI green before the next. **No provider call was made at any point**: every guarantee below is demonstrated deterministically, and live verification traffic was not manufactured — Lord Armand exercises the interface through normal use, and edits, removals, archives and moves made that way are product evidence, never Layer 0 judgment evidence by the fact of having occurred.

---

## 1. Commits and CI

| Stage | Commit | CI run |
|---|---|---|
| 1 — rename and archive; the owner amendment recorded | `8156d4a` | 34735562112, success |
| 2 — message revision and retraction | `5b659bf` | 34738500716, success |
| 3 — conversation Remove and Reinstate | `fa6beb6` | 34739014253, success |
| 4 — explicit scope transitions | `57f50f1` | 34767937614, success |

## 2. Migrations and schema objects

| Migration | Objects |
|---|---|
| `0016_message_revisions` | table `message_revisions`; enum `message_revision_kind` (`revision`, `retraction`); unique `(message_id, revision_number)`; index `(conversation_id, after_sequence)`; checks `revision_number_positive`, `after_sequence_positive`, `content_iff_revision`, `revision_says_something`, `authored_by_named`; trigger function `val_message_revision_is_coherent` with trigger `message_revisions_is_coherent`; guards `message_revisions_forbid_hard_delete`, `message_revisions_rows_are_evidence`; view `messages_current` |
| `0017_conversation_removals` | table `conversation_removals`; enum `conversation_removal_kind` (`removed`, `reinstated`); unique `(conversation_id, event_number)`; checks `event_number_positive`, `authored_by_named`; trigger function `val_conversation_removal_is_coherent` with trigger `conversation_removals_is_coherent`; guards `conversation_removals_forbid_hard_delete`, `conversation_removals_rows_are_evidence`; function `val_conversation_removed_at(uuid)` |
| `0018_scope_transitions` | table `conversation_scope_transitions`; unique `uq_scope_transitions_conversation_number`; index `ix_scope_transitions_conversation_after`; foreign keys to `conversations` and, for both ends, `projects`; checks `transition_number_positive`, `after_sequence_not_negative`, `a_move_changes_scope`, `authored_by_named`; trigger function `val_scope_transition_is_coherent` with trigger `conversation_scope_transitions_is_coherent`; guards `conversation_scope_transitions_forbid_hard_delete`, `conversation_scope_transitions_rows_are_evidence`; functions `val_effective_project_id(uuid, bigint)` and `val_scope_transitions(uuid)` |

No column was added to any existing table, no existing trigger or guard changed, and every downgrade refuses once a fact exists. The revision id of the third migration is `0018_scope_transitions` because alembic's version column holds 32 characters; the table keeps its full name. A text index on revision wording, sketched while designing, was not created: the recall predicate is over the current wording through `messages_current`, which that index could not serve, and at the House's volume the scan is negligible.

## 3. API routes added

- `POST /conversations/{id}/title` — rename (422 on an empty or over-long title)
- `POST /conversations/{id}/archive`, `POST /conversations/{id}/unarchive`
- `POST /messages/{id}/revisions` — `{content, note?}`; 409 `deliberated` / `unchanged` / `removed` / `not_authored_by_lord_armand`, 403 Restricted, 422 empty, 404 unknown
- `POST /messages/{id}/retraction` — `{note?}`; 409 `already_withdrawn` / `removed` / `not_authored_by_lord_armand`
- `POST /conversations/{id}/remove`, `POST /conversations/{id}/reinstate` — `{note?}`
- `POST /conversations/{id}/scope` — exactly one of `{project_id}` or `{no_project: true}`, optional note; 422 when both or neither, 404 unknown project, 409 `unchanged` / `removed`
- `GET /conversations?removed=true` — includes removed conversations

Additive fields: `ConversationView.removed`, `ConversationView.origin_project_id` (with `project_id` now the current effective scope — identical for every conversation never moved); `MessageView.state`, `original_content`, `answered_state`, `revisions`, `revision_refusal` (defaults on a turn's own messages); `ConversationDetail.scope_transitions`. `POST /turns` returns 409 for a removed conversation, and the stream emits a `refused` event. All routes are POST, so the desktop's CORS grant is unchanged.

## 4. Desktop controls added

Conversation header: **Rename** (inline), **Archive / Unarchive**, **Remove / Reinstate** (with a confirmation stating that nothing is deleted), **Move to…** (every other project, and No project, with a confirmation that earlier messages keep their scope). Messages: **Edit** on Lord Armand's messages, **Remove** with a confirmation, **View original** on a corrected message, a line on Val's reply saying it answered the earlier wording or a withdrawn message, a withdrawn exchange collapsed with **Show**, and on a deliberated message **Why can't this be edited?** with the explanation in place of Edit. The thread shows a marker where a move took effect. Sidebar: `(removed)` tags; the toggle reads "Show archived and removed"; the composer is closed on a removed conversation. The words are pure functions in `apps/desktop/src/messageState.ts`, tested directly.

## 5. What is demonstrated, against the acceptance list

| Requirement | Evidence |
|---|---|
| Original message bytes unchanged after revision | `test_the_original_message_row_is_byte_identical_after_a_revision`; UPDATE and DELETE refused on messages and facts |
| Historical calls reconstruct with the wording they received | `test_an_earlier_call_reconstructs_exactly_after_a_revision` — the second turn's request, reconstructed after a revision and a later turn, equals what the adapter was handed |
| Current turns use the corrected wording | same test and `test_a_later_turn_is_told_the_earlier_message_was_corrected_after_its_answer` |
| Revisions consume no sequence | `test_a_revision_consumes_no_message_sequence` |
| Concurrent ordering exact through the lock and `after_sequence` | `test_a_revision_recorded_while_a_turn_is_open_is_invisible_to_it`; `test_the_conversation_lock_orders_a_revision_against_a_concurrent_append` (the revision waits for the lock; a message appended under it precedes the fact); the pure as-of rule with deliberately misleading timestamps in `test_working_thread.py` |
| Corrected and original distinguishable in the UI; answers attached to what they answered | detail fields in `test_a_correction_is_shown_in_place_with_the_original_and_the_answer_marked`; words in `messageState.test.ts` |
| Retracted exchanges leave assembly and both recall paths; evidence and costs remain | `test_a_retracted_exchange_leaves_assembly_and_keeps_everything_else`, `test_a_retracted_exchange_leaves_both_recall_paths`, `test_a_retraction_is_marked_and_destroys_nothing` |
| Deliberated messages refuse revision and permit retraction | `test_a_deliberated_message_refuses_revision_and_permits_retraction` (writer and trigger), `test_an_enforced_blind_position_refuses_revision_and_permits_retraction` (through the orchestrator's enforced blind position) |
| Rename changes no evidence identity; archive changes listings only | `test_conversation_rename_archive.py`; `test_archive.py` unchanged |
| Remove changes recall and resume but destroys nothing | `test_conversation_removal.py`, `test_conversation_removal_api.py` (no message appended and no provider contacted by a refused turn) |
| Scope movement never changes `project_id`; history keeps its scope; new turns take the new scope | `test_a_move_keeps_the_origin_and_the_past_and_attributes_the_future`; `test_after_a_move_the_next_turns_evidence_belongs_to_the_destination` (classification, blind position and all four calls of a deliberated turn) |
| Retained thread survives a move | `test_the_moved_conversation_keeps_its_own_thread` |
| Automatic recall isolated by effective message scope; unassigned activates no recall | `test_recall_follows_the_scope_each_message_was_written_in`, `test_moving_out_of_every_project_stops_automatic_recall_and_keeps_the_thread` |
| House Recall provenance accurate across transitions | `test_house_recall_reports_each_excerpts_scope_as_written` |
| Existing Project A / Project B isolation holds | `test_project_a_retrieval_returns_only_a`, `test_project_b_retrieval_returns_only_b` and the House Recall isolation test pass unedited |
| No hard delete possible | the parametrised schema tests now cover the three new tables; delete refusals asserted in each stage's tests |
| A request with no facts is byte-identical to before | the whole pre-existing suite passes unedited against the new assembly and recall; `test_no_facts_means_no_revision_keys_in_the_envelope`, `test_an_unrevised_excerpt_carries_no_revision_keys` |

**Final counts:** 1,239 Python tests (1,198 on the configured paths plus 41 providers), all passing; 35 desktop tests (28 before this work). Before this work: 1,171 and 28.

## 6. Pre-existing tests amended

One file, additively: `packages/domain/tests/test_schema.py`, whose hand transcription of §2 must name every table, nullable column, enum and view or the schema tests fail by design. The three tables, their nullable columns, the two enums and the `messages_current` view were added to the transcription. No existing expectation was changed or weakened, and no other pre-existing test file was edited in any stage. The desktop's new message fields were made optional in `api.ts` precisely so the existing `presentation.test.ts` literals stand unchanged.

## 7. Deployment

The live store was fingerprinted read-only before migrating (counts; an md5 over every message's id, role, content, sequence and timestamp; over every conversation's origin `project_id`; over every call's id, project, cost and message). Migrated `0015 → 0018` with `alembic -x deploy=live upgrade head`; the service restarted on `57f50f1`, health running with no warnings. **The fingerprint after migration is identical**: 135 messages, 34 conversations, 150 calls, and all three digests unchanged. Read-only checks on the live store: `messages_current` has one row per message, every one `current` and `live` with wording equal to the original; `val_effective_project_id` equals the origin for every conversation and every message; no conversation is removed; zero revision, removal and transition facts; every new guard present. The running service's listing and detail carry the new fields. The native bundle was rebuilt (`npm run tauri build`, the interface compiled from the current source at 11:17 on 13 September) and installed at `/Applications/Val.app`; the 11 September bundle is preserved beside it as `Val (built 2026-09-11).app`. The app was not running.

## 8. Conflicts, limits and checkpoint review

- **No conflict with the ruling was encountered.** The one place an existing contract meaning moved is `ConversationView.project_id`, which is now the current effective scope rather than the origin; for every conversation never moved the two are the same value, and the origin is carried beside it. This follows ruling item 8 (the sidebar and resume use the current scope).
- **Which Val reply answered which message** is inferred by adjacency: the Val message immediately after a user message answered it. The record has always relied on this (no stored reply-to link), and the interface sends one turn at a time. Two turns racing in one conversation could misattach an `answered_state`; no evidence row depends on it.
- **OP-1 checkpoint** (`VAL_Open_Problems.md`, message revision/retraction — claims about what was said): narrowed, not solved. What was said, what it was corrected to and when, and what any past call received are now checkable deterministically from `messages`, `message_revisions` and the as-of rule, and Val is told structurally when an earlier message was corrected after she answered it. Nothing examines an outbound claim before it is sent, so OP-1 stays open with its remaining checkpoints.
