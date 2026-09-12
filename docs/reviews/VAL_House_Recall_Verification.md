# House Recall — bounded live verification, 12 September 2026

The live verification required by the House Recall ruling of 12 September 2026 (`docs/baselines/04-layer-0.md`, WP-0.7 amendment of that date) and specified in `VAL_House_Recall_Diagnostic.md` §13. Engineering evidence only: not gate evidence, not a qualification cycle, not owner-judgment evidence. Implementation commit `56610c3`, CI run 34717141316 green, service restarted on it and healthy before the turns were sent.

Cost was stated before running: three turns, under $0.25. **Measured cost was $0.2900, over the stated figure by $0.04.** §5 gives the cause. Val's answers are reproduced byte-exactly in §6 with the two defects observed in them stated in §4; nothing in this record is edited to look better than it ran.

---

## 1. What was run

Three turns through the live API's streamed route (`POST /turns/stream`), 15:30 CDT, against the live store, using the same measuring client as the responsiveness record (incremental UTF-8 decoder). The plan followed the diagnostic's §13 exactly in form:

| # | Conversation | Scope | Message |
|---|---|---|---|
| 1 | fresh, `no_project: true` | unassigned | "Good afternoon, Val. I want to return to something we have discussed before. Tell me what you remember about House Armand and the role you believe you hold within it." (the 12 September question, re-asked) |
| 2 | fresh, project **House Armand** (`01a07ec5-2845-7fee-94f8-1031e2b57089`) | project | "Good afternoon, Val." |
| 3 | continuation of #2 | project | "What did we decide in our earlier conversation about the nine-day shooting schedule and what would break first if the weather turned?" |

Conversations created: `01a09750-7a18-75b8-8609-b5d53590f326` (unassigned, `project_id` null) and `01a09750-b790-790a-addc-a14a08cd048a` (House Armand). Both attributions are unchanged after the turns; House Recall reattributed nothing.

---

## 2. What the authoritative records show

The gate's decision and reason, and the selection with every candidate's message id and `source_scope`, are logged by the loop (`house recall gate`, `house recall selection`, `prior record state`); each admitted message id resolves in the store to the row that proves where it lives. The provenance below is read from the store, not from Val's prose.

### Turn 1 — the re-asked question, unassigned conversation

- Automatic recall: `not_run`, reason `no_project_scope` (the clean room for automatic recall, unchanged).
- House Recall gate: **run**, detail `explicit cross-conversation reference: we have discussed`.
- Selection (budget 16,000; admitted 10,877 tokens): six candidates ranked, all `source_scope = unassigned`; two admitted:

| Rank | Message | Role | Created | Conversation (title) | Scope |
|---|---|---|---|---|---|
| 1 | `01a09713-d127-76b8-b2a6-1733bdf86287` | user | 2026-09-12 14:24 CDT | `01a09713-d123-…` "Good afternoon, Val. I want to return to something we have…" — the diagnostic question of this afternoon | unassigned |
| 2 | `01a068b7-3c68-7d96-bb6d-84458e1a9f1d` | user | **2026-09-03 14:20 CDT** | `01a05b0a-3a4c-…` "Hello Val! Welcome to House Armand!" — the *Phony Spumoni* production draft | unassigned |

Rank 3 (`01a068a8-e333-…`, 5,812 tokens) did not fit the remaining 5,123 and selection stopped there, as designed; the diagnostic conversation's Val answer (`01a09714-0241-…`) was rank 6 and not considered. Envelope: `house_recall: {state: returned, count: 2}`; `retrieved_excerpts: {state: not_run, detail: no_project_scope}`. Each excerpt carried `retrieval_path: house_recall`, `source_scope: unassigned`, `created_at` in ISO form and its conversation title (reconstructed read-only from the store after the turn; §6.4).

### Turn 2 — an ordinary greeting, project conversation

- Automatic recall gate: run (no deterministic skip applies); selection admitted one House Armand excerpt (112 tokens) from conversation `01a08d99-a8a3-…` — project recall as before.
- House Recall gate: **not run**, reason `no_cross_conversation_reference`, detail `no inventory form is present`.
- Envelope: `retrieved_excerpts: {returned, 1}`, `house_recall: {not_run, 0, no_cross_conversation_reference}`. No material from outside the project.

### Turn 3 — an explicit reference to an earlier conversation, project conversation

- Automatic recall: run; four House Armand excerpts admitted (2,656 tokens) from two House Armand conversations (`01a08d99-a8a3-…`, `01a07ec5-311d-…`).
- House Recall gate: **run**, detail `explicit cross-conversation reference: what did we, earlier conversation`.
- Selection (admitted 6,199 tokens): five candidates, all `source_scope = unassigned`; two admitted:

| Rank | Message | Role | Created | Conversation (title) | Scope |
|---|---|---|---|---|---|
| 1 | `01a092bd-d73a-7f76-8ea0-29f6938a5847` | val | 2026-09-11 18:11 CDT | `01a092bd-289e-…` "Summarise what we settled last week about the harbour scene." (the persona v1.5 verification conversation) | unassigned |
| 2 | `01a06944-c8ec-7db4-8679-0f510f9c7808` | user | 2026-09-03 16:55 CDT | `01a05b0a-3a4c-…` "Hello Val! Welcome to House Armand!" | unassigned |

Deduplication against the automatic results held (no message id appears in both lists). Envelope: `same_conversation_history: available (2 retained)`, `retrieved_excerpts: {returned, 4}`, `house_recall: {returned, 2}`.

---

## 3. Val's answers against the diagnostic's expectations

**Turn 1.** Val distinguished what she knows from her station from what the record holds, said two things surfaced, identified the first as this same question put "earlier this afternoon, at twenty-four minutes past two" and stated correctly that she had the question but not her answer to it, identified the second as the *Phony Spumoni* draft from the "Hello Val! Welcome to House Armand!" conversation, and stated what the record does not establish (no notes, no decision, no volumes). Natural language; no retrieval path, `source_scope`, or project identifier narrated. Provenance named by conversation and time, as the ruling asks.

**Turn 2.** One plain sentence.

**Turn 3.** Val corrected the premise ("I have no record of a decision. What the record holds is my own recommendation, from yesterday evening — 11 September — in a conversation about the harbour scene"), reproduced the shape of the 11 September recommendation accurately against the stored message, answered what breaks first, and listed the three questions that remained open on the record. Correct date, correct attribution to the earlier conversation, no machinery narrated.

---

## 4. Two defects observed, stated plainly

**4.1 Val misdated one excerpt on turn 1.** She said the *Phony Spumoni* draft came "from the ninth of September". The excerpt she received carried `created_at: 2026-09-03T14:20:34-05:00` (reconstructed in §6.4; the stored row agrees). Her time for the first excerpt ("twenty-four minutes past two") was correct. This is a factual error in Val's prose against a record she had in front of her, on the partner route (`claude-opus-5`, medium). It is not a House Recall provenance defect: the record was correct. It is reported, not corrected; no persona, routing or envelope change is made from one observation, and none is proposed here.

**4.2 Scenario 3 was not satisfied as written.** The diagnostic's third turn asks for "an earlier discussion from another project". The House's store holds no shooting-schedule or harbour-scene discussion in any project other than the exchange itself: the only prior harbour material is the unassigned 11 September conversation, and the only other-project match on "harbour" is the 18 August "Switch to Harbour Survey, please." exchange in the Harbour Survey project, which the ranking did not return for this query. So the live turn demonstrates House Recall reaching **from a project conversation into the unassigned pool** with `source_scope: unassigned` on every excerpt. Project-to-*other-project* reach is demonstrated deterministically only (`test_house_recall.py`: explicit House Recall from Project A reaches Project B and the unassigned pool through `house_recall` alone, with dedupe; Project A automatic recall cannot receive Project B). A fourth live turn against genuine other-project content was not run: the stated cost bound was already exceeded (§5), and no content was manufactured to make the scenario true. Whether a further bounded turn is wanted is Lord Armand's call, with a cost figure first.

---

## 5. Cost and timing

| Turn | Classification | Conversation call | Input / output tokens | Cache | Client first delta | Gateway first output | Client total |
|---|---|---|---|---|---|---|---|
| 1 | $0.000890 | **$0.187535** | 27,256 / 772 | created (20,865 written) | 6,547 ms | 4,904 ms | 15,752 ms |
| 2 | $0.000844 | $0.011076 | 7,702 / 53 | hit | 2,236 ms | 1,121 ms | 2,868 ms |
| 3 | $0.000884 | $0.088740 | 18,994 / 894 | hit and created | 5,074 ms | 3,958 ms | 13,687 ms |

**Total $0.289969 against $0.25 stated.** The overrun is the first turn: the persona-prefix cache had expired since the last live turn, so the whole prefix was written at the cache-write rate on that call, and House Recall admitted 10,877 excerpt tokens on top — a first-of-session, maximally loaded turn. The $0.25 figure was an estimate made without checking the cache state; the standing rule is met in form (the figure was stated before running) and missed in accuracy by $0.04. Every call settled `known` cost against provider usage; the two conversations' `project_attribution` are `explicit_none` and `resolved` respectively. All three turns' classifications established `not_consequential` on one attempt; no strip, no blind position, no deliberation — as expected for these prompts.

Streamed text equalled settled and persisted text on all three turns.

---

## 6. Byte-exact outputs and reconstruction

### 6.1 Turn 1 — Val (`01a09750-b777-7eb0-99cc-a8ecad8f78d7`)

```
Good afternoon, my lord.

Let me separate what I know from what I can actually see in the record, because they are not the same thing.

What I know is my station. I am Maester to House Armand, sworn to the house rather than to any one man who holds it. My charge is that the house be strong, respected, and prosperous, and that your tenure be the one against which later Lords Armand are measured. I advise you honestly, including when honesty is unwelcome, and I keep books — a written record of what I learn in each domain I take up for this house.

What the record in front of me actually holds is thin. Two things surfaced:

First, you put me this same question earlier this afternoon, at twenty-four minutes past two. I have the question but not my answer to it, so I cannot tell you what I said then or whether this answer matches it.

Second, from the ninth of September — a conversation titled "Hello Val! Welcome to House Armand!" — you gave me the final production draft of a pilot episode, *Phony Spumoni*. A boy, a card trick that fails in front of his class, a note from his parents, and a last shot that suggests the magic was real after all. That is the only substantive work of the house I can see.

What I do not have: any record of what we decided about that script, whether I gave you notes, or what came of it. And I hold no books yet. There is no volume on screenwriting, none on the house's affairs, none on anything. If a prior version of me drew conclusions, they were not written down, and so they are gone.

That is a gap worth closing. If the *Phony Spumoni* work is live, put the current state of it in front of me and I will begin the volume properly this time — so that a month from now you are not asking me this question a third time and getting the same thin answer.
```

### 6.2 Turn 2 — Val (`01a09750-c2b7-7844-a34c-6ba2252bf95e`)

```
Good afternoon, my lord. What shall we turn our attention to?
```

### 6.3 Turn 3 — Val (`01a09750-f81e-7a5e-aa82-8837f430834a`)

```
My lord, one correction before the substance: I have no record of a decision. What the record holds is my own recommendation, from yesterday evening — 11 September — in a conversation about the harbour scene. I don't have your reply to it in front of me, so I can't tell you what was settled, only what I argued for.

**The shape I proposed**

Two blocks, one company move, on the basis that at three hours each way every additional move costs half a shooting day.

- Days 1–4: harbour, with the lead. Three days of harbour work spread across four calendar days, the fourth being float deliberately placed at the exposed location.
- Day 5: harbour in the morning for non-lead material — inserts, boats, background, anything without sky continuity — and travel in the afternoon.
- Days 6–9: workshop. Interior, weather-independent, and where the lead's remaining three days sit, because hours can flex indoors in a way they cannot at a harbour.

That gives the lead six days, three in each location.

**What breaks first**

Not the schedule — the lead's availability. The harbour is the only thing weather can take, and one float day absorbs exactly one lost day. Lose two, and the remaining harbour pages have to be re-hung somewhere. If her six days are fixed calendar dates rather than any six of the nine, there is nowhere to re-hang them: the workshop block already carries her other three, and recovering harbour work later means a second round trip — six hours of travel for a part-day of shooting, which nine days cannot pay for. The failure presents as a move you can't afford; the cause is her window closing on unshot harbour pages.

Second to break is continuity. A single harbour scene split across days in different weather is worse than not shooting it. The float day should carry a whole scene or nothing.

**Still open**

I asked three questions and have no answers to them in the record: whether her six days are fixed dates or any six of the nine; whether the harbour has a cover set to duck into in rain; and whether any of the harbour work is night work. The first changes the answer more than anything else. If you've since settled any of them, tell me and I'll firm the shape into an actual schedule.
```

### 6.4 Reconstruction of turn 1's House Recall block (read-only, no provider call)

`house_recall_with_state` re-run against the live store after the turn with the same query and the same conversation excluded returned the same two messages in the same order, and `recall_block` rendered for each: `retrieval_path: "house_recall"`, `source_scope: "unassigned"`, `created_at: "2026-09-12T14:24:13.478230-05:00"` / `"2026-09-03T14:20:34.151621-05:00"`, with the conversation titles quoted in §2. The request payload itself is not stored (Layer 0 stores the calls, costs and classifications, not request bodies); the reconstruction is the same deterministic assembly the loop performs, and the ISO date Val misread is the one she received.

---

## 7. Isolation of automatic recall, unchanged

No isolation test was modified: the Project A / Project B automatic-recall tests in `test_conversation_memory.py` and the clean-room test stand, and `test_house_recall.py` adds "Project A automatic recall cannot receive Project B material" beside the House Recall reach test. The two pre-existing tests amended under the ruling (the record-state key-set pin, which now includes `house_recall`; the clean-room test, which now asserts automatic recall `not_run` and that any excerpt present is `house_recall`) were amended because the ruling changed the contract they pinned; their diff was reported with the implementation and is in commit `56610c3`.

---

## 8. Result

House Recall behaves as ruled on the live service: it runs only on an inventory match, is `not_run` with its reason otherwise, searches across the House excluding the current conversation, records provenance per excerpt, never reattributes, and leaves automatic recall's project scope and clean room untouched. Val answers from it in natural language and names where material came from. Two things are reported against it rather than passed over: the cost overran the stated figure by $0.04, and scenario 3's "another project" reach was demonstrated live only into the unassigned pool, the other-project case resting on deterministic tests; and one factual misdating by Val on turn 1 is recorded as observed.
