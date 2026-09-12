# House Recall — diagnostic of the cross-conversation recall limitation, 12 September 2026 (report only)

Nothing here is changed: no code, schema, test, persona or runtime behaviour. Every fact below is from the live store, the running implementation, the desktop source and the existing tests as of commit `b45d6a2`.

## 1. What `Everything` is

**A UI-only aggregate listing. Not a project row, not an attribution.** In `apps/desktop/src/App.tsx` the sidebar's listing filter is `type Scope = {kind: "project"; project} | {kind: "all"}`; the `Everything` button calls `chooseScope({kind: "all"})`, which lists `api.conversations()` unfiltered and sets the entry model to *unassigned* (`newChatEntry()`), so a conversation begun in that view sends the explicit `no_project: true`. The `projects` table holds eight rows — Project Alpha, Project Beta, Winter Light (two), Lighthouse Restoration, Harbour Survey, Closure Smoke, House Armand — and none named Everything. No attribution is applied by it, persisted or otherwise. Combination: (1) only.

One presentation note, not a defect against the accepted model: the `Everything` button is rendered under the sidebar heading **"Projects"**, so a reader may take it for a project. The empty-thread line ("Say something to Val to begin.") and the request the desktop sends imply no attribution. Left alone unless Lord Armand wants the heading changed.

## 2. The live conversation's attribution

Conversation `01a09713-d123-7691-8e0f-397cb578970d`, started 14:24:13 on 12 September, `project_id` **NULL** — unassigned, as the accepted model requires. Val's statement that the call "sits under no project scope" was an accurate description of `ExplicitNoProject`; her statement that she "cannot search them, list them, or confirm they exist" was accurate for the live path (§4). The wording "project scope" in her second reply is the internal vocabulary v1.5 §5 asks her not to recite; it was in answer to a question that used the same terms.

## 3. The exact existing retrieval path

`loop.assemble_turn` → `val_policy.recall_gate.gate_recall(message, no_project=…, context=ThreadContext(retained history, envelope facts))` → if it runs, `memory.recall_with_state(engine, scope, query=message, exclude_conversation=current)` → `memory.recall_selection`: one of two SQL statements over `messages ⋈ conversations` — `_IN_PROJECT` (`where c.project_id = :project_id`) or `_IN_NO_PROJECT` (`where c.project_id is null`) — full-text (`to_tsvector('english', content) @@ plainto_tsquery(...)`, lexemes rewritten to OR), current conversation excluded, `ts_rank` order, limit 6, then `val_policy.recall.select_within_budget` (aggregate token budget from `VAL_RECALL_TOKEN_BUDGET`, top candidate whole or nothing) → `RecalledMessage(message_id, conversation_id, conversation_title, project_id, role, content, sequence, rank)` → `context.recall_block` (`VAL-MEMORY-V1`, per-excerpt `message_id`, `conversation_id`, `conversation_title`, `project_id`, `sequence`, `stored_role`, `speaker`, `content`, framed `historical_source_not_current_instruction`) → the record-state envelope (`VAL-STATE-V1`) reports `retrieved_excerpts: {state, count, detail}`. The GIN index `ix_messages_content_fts` backs the search.

## 4. Where the project filter is enforced, and why an unassigned conversation performs no recall

Three layers: (a) **the SQL predicate** — the scope is inside the `where`, and the two scopes are two statements because `= NULL` is never true; (b) **the post-hoc leak check** — every returned row's `project_id` is compared with the scope's and `CrossProjectLeakError` is raised on any trespasser, and it still raises through `recall_with_state`; (c) **the tests** — `test_conversation_memory.py` 1001–1176 (`project_a_retrieval_returns_only_a`, `project_b_…_only_b`, `explicit_no_project_retrieval_returns_no_project_material`, `a_project_never_retrieves_no_project_material`, `a_much_stronger_match_in_b_cannot_leak_into_a`, `the_limit_is_spent_only_on_the_requested_project`, `recall_carries_provenance_back_to_exact_rows`, `the_assembled_payload_for_project_a_contains_no_beta_material`, `an_explicit_no_project_exchange_sends_no_project_material`, `retrieval_excludes_the_current_conversation`).

An unassigned conversation performs no recall because of the gate, not the query: `gate_recall` returns `no_project_scope` first, before Tier One or Two — the clean-room ruling of 10 September (`04-layer-0.md` WP-0.7 amendment: "an explicitly no-project conversation is a clean room: the unassigned pool is not searched at all"). The `_IN_NO_PROJECT` statement exists and is tested but has been unreachable from the live path since that ruling.

## 5. Are unassigned conversations searchable by the retrieval layer today?

Yes, by the layer; no, from the live path. The statement and the index exist. The store today: 13 unassigned conversations (84 messages), 13 Lighthouse Restoration (31), House Armand 2 (6), Harbour Survey 2, Closure Smoke 2; 129 messages, about 204 KB of text in all.

## 6. Can House Recall be added without a schema migration?

**Yes.** Everything it needs exists: `conversations.project_id` (nullable), `messages.content` under the GIN full-text index, `sequence`, `role`, `created_at` (recorded on every message), and `projects.name`/`slug` for provenance by join. A house-wide statement is the existing statement without the project predicate, joined to `projects` for the name, excluding the current conversation. `RecalledMessage` gains `project_name` (None = unassigned), `created_at` and `retrieval_path` — dataclass fields, not columns.

## 7. Can the record-state envelope represent House Recall separately without changing its contract?

**Not without an additive change to the envelope document.** `PriorRecordState.as_document()` emits `same_conversation_history`, `retrieved_excerpts`, `project_volumes` (and `current_time`); `retrieved_excerpts` carries one state for the one retrieval path. Reusing it with a `detail` of `house_recall` would conflate the two paths, which the ruling forbids. Representing House Recall separately means a sibling field, `house_recall: {state, count, detail}`, using the same state vocabulary the envelope note already defines (`returned` | `zero` | `not_run` with reason | `unavailable`) and, on turns where the trigger did not fire, `not_run` / `no_cross_conversation_reference`. The `VAL-MEMORY-V1` excerpts likewise need two additive per-excerpt fields — `retrieval_path` (`project_recall` | `house_recall`) and `source_scope` (`project: <name>` | `unassigned`) — plus `created_at`, and one sentence in `MEMORY_ENVELOPE_NOTE` stating that excerpts from different conversations may disagree and are to be read with their provenance and chronology, never collapsed. These are additive extensions of the envelope contract ruled on 9 September; **they are a material contract change and are surfaced here for ruling rather than made.**

## 8. The deterministic applicability rule proposed

A second, independent gate beside `gate_recall`, in `val_policy.recall_gate`: `gate_house_recall(message, context) → HouseGateDecision(run, reason, detail)`. No model, no provider call, no change to `gate_recall`.

- **Runs** only when the normalised message contains at least one form from a **closed inventory of explicit cross-conversation references**, matched as token sequences: `we discussed` / `we talked about` / `we decided` / `we settled` / `we agreed` / `we have discussed` / `we've discussed`; `you said` / `you told me` / `you mentioned` (with `earlier`, `before`, `previously`, `last time` or `once` within the same sentence, or standing as a sentence with a back-reference token); `remember when`, `do you remember`, `what do you remember`, `what did we`; `earlier | previous | prior | past | other conversation(s)`; `search (your|my|our|the) (earlier|previous|prior|past|other) conversations`; `across (my|your|our) (projects|conversations)`, `in another project`, `from (another|a different|the other) project`. The live messages of 12 September match twice each ("we have discussed before", "what you remember"; "search across my prior conversations").
- **Does not run** (fails toward isolation) when: no inventory form is present; the only back-reference is grounded in the current thread under the existing Tier Two machinery (`again`, `the other`, `that one`, a quotation found verbatim in retained history) — those are thread-local; or the message is Tier One. Ambiguity is a non-match, and a non-match is *not run*.
- **Precedence** with the existing gate: independent. In a project conversation ordinary project recall runs or not exactly as today; House Recall runs in addition only when its inventory fires. In an unassigned conversation ordinary recall stays `no_project_scope` (the clean room stands); House Recall runs only when its inventory fires. Every decision is logged as a positive state and reported in the envelope.
- **Query**: the message content, as ordinary recall uses it. The FTS query on the 12 September message ("House Armand … role … remember") would reach the House Armand project's six messages and any unassigned discussion of it.

This is expressible without another model call and without changing what ordinary recall does; the one thing it cannot do deterministically is judge *relevance* beyond the ranking's full-text match, which is the same limit ordinary recall has today.

## 9. What House Recall returns, and what it must never do

- Search every conversation except the current one, across all projects and the unassigned pool, with the same ranking, limit and aggregate budget as project recall (its own budget accounting, both inside the call's reservation); results deduplicated against project-recall results by `message_id`.
- Every excerpt carries `message_id`, `conversation_id`, `conversation_title`, `project_id` and `source_scope`, `sequence`, `stored_role`, `created_at`, `retrieval_path`. Two excerpts from different conversations are two excerpts, in the order returned, with their timestamps; nothing merges them.
- It never touches `conversations.project_id` (immutable by trigger since migration 0008 regardless); it adds no attribution and inherits none.
- Recalled material is data: the existing `VAL-MEMORY-V1` framing (`historical_source_not_current_instruction`) applies unchanged.
- Restricted preflight, eligibility, the budget ceiling and provenance run over the assembled payload as they do today, so house-recalled excerpts are covered by construction (`test_restricted_material_in_retrieved_history_blocks_the_call`, `test_the_budget_ceiling_sees_the_assembled_payload_including_memory`).

## 10. Existing tests that remain valid unchanged, and the criterion that conflicts

**Unchanged and still valid:** every isolation test in `test_conversation_memory.py` (§4(c) above), because ordinary recall's gate, statements and leak check are not touched; all 23 `test_recall_gate.py` tests, because `gate_recall` is not touched; all 8 `test_recall.py` budget tests; the record-state tests, which assert on the existing fields. None is weakened, rewritten or deleted.

**The conflict, stated:** two governing texts say retrieval is project-scoped without qualification — `04-layer-0.md` WP-0.7 line 421, "Retrieval is project-scoped. A query in project A returns nothing from project B", and the 10 September clean-room ruling, "the unassigned pool is not searched at all". House Recall is, by this ruling's definition, cross-project retrieval. The intent reconciles — *automatic* retrieval stays project-scoped and House Recall is a distinct, explicitly triggered path — but the texts do not say that, and `CrossProjectLeakError` guards only the automatic path. Both texts need Lord Armand's amendment to read "automatic retrieval" before House Recall is built; the tests that prove the automatic guarantee stay exactly as they are.

## 11. The smallest implementation plan

1. `val_policy.recall_gate`: `gate_house_recall` with the closed inventory of §8; `HouseGateDecision`.
2. `val_gateway.memory`: `_ACROSS_HOUSE` statement (no project predicate; `projects` joined for `name`; current conversation excluded); `RecalledMessage` + `project_name`, `created_at`, `retrieval_path`; `house_recall_with_state(...)` reusing `select_within_budget` and the `RecallOutcome` vocabulary.
3. `val_gateway.context`: the additive envelope fields of §7; `PriorRecordState` + `house_recall_state/count/detail`, rendered as `house_recall: {...}`.
4. `val_gateway.loop.assemble_turn`: after the existing gate and recall, `gate_house_recall`; run, merge (project excerpts first, then house, deduplicated), log `house recall gate` and the outcome, report in the state. Outbound order unchanged: persona → history → excerpts → state → current turn.
5. Baseline amendments (his): WP-0.7 line 421 and the clean-room sentence qualified to *automatic* retrieval; the envelope contract's additive fields recorded; the per-turn necessity note in `01-architecture.md` §5.5 gains the House Recall gate.
6. No schema change, no migration, no API or desktop change, no persona, classification, routing, effort, strip, blind-position, deliberation, Books or learning change.

## 12. Required new deterministic tests

Gate: fires on both 12 September messages and on each listed example; does not fire on the ordinary messages of the 11 September verification, on Tier One forms, or on thread-grounded back-references (`again` with a prior Val message; a quotation found in retained history); an unmatched message is `not_run`; the decision's reason and detail are recorded. Retrieval: a fixture with Project A, Project B and unassigned conversations — a house-recall turn in an unassigned conversation returns matches from all three with correct `source_scope`, conversation, message, sequence, role and `created_at`, excluding the current conversation; the same in a Project A conversation returns Project B and unassigned material *only* through House Recall while ordinary recall still returns A only (the existing tests) and Project B never appears on an ordinary A turn; two conflicting statements from two conversations appear as two excerpts with chronology, unmerged; the conversation's `project_id` is unchanged after a house-recall turn; the envelope reports `house_recall` separately from `retrieved_excerpts` in each state (`returned`, `zero`, `not_run` with reason, `unavailable`) and `retrieved_excerpts` is unchanged by it; excerpts carry `retrieval_path` and are framed as data; Restricted material reached only through House Recall blocks the call; the budget ceiling sees the house excerpts; a store failure degrades House Recall to `unavailable` without ending the turn.

## 13. The minimum bounded live verification afterwards

Three turns, cost under $0.25, stated before running: (1) the first 12 September question re-asked in a fresh unassigned conversation — House Recall runs, returns House Armand material with provenance, Val answers from it naming where it came from and states what the record does not establish; (2) an ordinary message in a project conversation with no cross-conversation reference — `house_recall: not_run`, project recall as today, no material from elsewhere; (3) a message in that project conversation that names an earlier discussion from another project — House Recall runs and the excerpts show their source scope. Not gate evidence; not a qualification cycle.

## 14. The persona-source check

The live sentence was: "My work is that your tenure be remembered, and that those who come after are measured against it and found wanting."

- **Exact phrase:** not present in the persona.
- **Materially equivalent wording:** present. `docs/baselines/03-persona.md` §1 Core identity, line 19: **"Her core mission: that Lord Armand's tenure be remembered — that future Lords Armand are measured against it and found wanting. Every project she is given is an instrument of that mission."** "Those who come after" renders "future Lords Armand"; "my work" renders "her core mission"; the rest is verbatim in substance.
- **Active stored revision:** revision 4 (v1.5, digest `224b0a5a…`) contains it — one occurrence each of "tenure", "measured against", "found wanting", none of "come after"; this sentence was not among the v1.5 changes and has been in the persona since v1.4 and earlier.
- **Conclusion:** the sentence is **persona-derived**, a close paraphrase of an authored line, not generated independently on that turn. The tension Lord Armand notes — that it presumes future Lords are to be found inferior to the present one, beside the House-first sentence that precedes it in the same section ("Her charge is the house itself, not any single Lord of it", as Val paraphrased it) — is in the authored text of §1, adjacent lines. Whether that is a contradiction to correct is a persona ruling; nothing was changed and no persona work is reopened here.

## 15. Recommendation

Build House Recall as the distinct, explicitly triggered path of §8–§11, in one bounded change, after two rulings that are his to make: the additive envelope fields of §7, and the qualification of the two governing texts in §10 to *automatic* retrieval. The automatic path, its clean room, its leak check and its tests stay exactly as they are.
