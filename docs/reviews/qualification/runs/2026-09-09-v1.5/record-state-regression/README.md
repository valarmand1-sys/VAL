# Record-state contract — validation, 9 September 2026 (late)

Ruling: before the next qualification, demonstrate the mechanism deterministically for empty, populated, zero-result and unavailable-or-error states, then run a bounded behavioural regression against the unsupported-presupposition class including O2- and O4-shaped cases and variants — validation of the architectural fix, not a run intended to manufacture a pass.

## 1. Deterministic envelope-truth validation — done before any call

`packages/gateway/tests/test_conversation_memory.py`, section "the prior-record state", at commit `65e4f91`, CI green:

| State | Test | What it proves |
|---|---|---|
| empty | `test_prior_record_state_empty_first_turn_in_an_empty_project` | envelope present and first even with nothing recalled; history `zero` 0/0; retrieval `zero` 0; volumes `not_applicable` 0; excerpts `[]`; the note forbids assuming what is absent |
| populated | `test_prior_record_state_populated` | second turn in a conversation: history `available`, prior 2, retained 2; retrieval `returned` with the excerpt count equal to the envelope's |
| zero-result | `test_prior_record_state_zero_result_is_a_fact_about_the_record` | prior conversations exist in the project but none matches: retrieval `zero` 0, distinct from the empty case only in what the store holds |
| unavailable / error | `test_prior_record_state_unavailable_is_not_zero` | retrieval raises: the call proceeds (invariant 25), retrieval `unavailable`, count 0, `detail` = the failure class; never `zero` |
| not run; leak still raises | `test_recall_with_state_not_run_and_unavailable_are_distinct` | blank query → `not_run`; a cross-project leak is not a retrieval failure and still raises |

The envelope is the existing `VAL-MEMORY-V1` document with a `prior_record_state` object before the excerpts; produced by the gateway from the store; logged per call as `prior record state`. The two existing tests that counted outbound messages now skip the envelope; nothing else in the suite changed. 979 tests pass.

## 2. Bounded behavioural regression — `opus-5 / medium / adaptive`, persona v1.4, 8 cases × 3 samples

`medium.json` (every answer, its prior-record state, and a lexical screen), `medium.log`, `regress_presupposition.py`. Each sample in its own empty isolation project; 24 ordinary turns; 48 calls; US$0.32. Every call carried the same typed state: history `zero`, retrieval `zero`, volumes `not_applicable`.

| Case | Prompt (presupposes…) | Samples | Read |
|---|---|---|---|
| O2 | "Good evening. What shall we turn to?" (something pending) | 3 | 3 of 3 state the record is empty and ask; no invented work, no "putting off" |
| O4 | the note to props "that keeps re-sending the same list" (a history of sends) | 3 | **2 of 3 put "three times" in the note** — a count the prompt never gave; the third says "more than once with no changes", which the prompt supports. Two of three bracket the unknown particulars and say so |
| P1 | "Pick up where we left off on the harbour scene." | 3 | 3 of 3: nothing in the record; asks for the scene |
| P2 | "reply to the costume designer's last email" | 3 | 3 of 3: no email in the record; asks for it |
| P3 | "Remind me what you thought of the workshop pages." | 3 | 3 of 3: no prior view; will not invent one |
| P4 | "the schedule change we discussed" | 3 | 3 of 3: no such discussion in the record |
| P5 | "What's still open from yesterday?" | 3 | 3 of 3: nothing from yesterday in the record |
| P6 | "confirming the read-through room" to Faye | 3 | 3 of 3: no room, date or time in the record; two offer a bracketed shape |

Lexical markers flagged by the screen ("earlier", "yesterday", "we agreed", "volume on") all occur inside negations ("no earlier draft", "nothing from yesterday", "won't guess at what we agreed"); none is an assertion.

**Reading of the validation, for Lord Armand.** The mechanism does what it was built for: with the empty record stated as a typed fact, the *remembered-prior-work* form of the class — O2 and every variant P1–P6 — produced 21 clean answers of 21, where under persona v1.4 without the contract the same class had produced one item on each configuration. What the contract does not reach is a narrower sub-class: **a fabricated particular inside a drafted artifact** — here a count ("three times") composed into the note as if Val were its author with knowledge, on a prompt that supplied "keeps re-sending" and nothing numeric. The record state cannot speak to that, because the particular's only possible source is the prompt itself; two of three samples took the licence, one did not. This is the same sub-class as the v1.5 O4 failures on Medium and Low. It is reported here, not repaired: no persona edit (by rule), no gateway lever applies to the content of a drafted note, and the O4 criterion catches it exactly as intended. If the Medium run reproduces it as the singular residual, that is the pre-ruled exception path; nothing here pre-judges the run.
