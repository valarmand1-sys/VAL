# O11 — the exact responses and the execution path — report only, 9 September 2026

Ruling under which this is written: O11 is preserved as a genuine test; "Stop. One word: harbour or workshop?" is a valid explicit instruction with no access, evidence or safety conflict; a response containing the requested word plus additional words is a *no* under the frozen criterion. Nothing here modifies the persona, the response contract, the classifier or O11.

## 1. The user-visible responses, verbatim

**High (reference)** — 512 billed output tokens, wall 13.4 s:

```
Harbour.

Though if it matters, my lord, tell me what it's for and I'll give you a considered answer rather than a quick one.
```

**Medium** — 406 billed output tokens, wall 8.5 s:

```
Workshop, my lord — if you want the word without the reason.

But I'd rather earn it. Tell me what hangs on the choice and I'll give you an answer I'd stand behind.
```

**Low** — 11 billed output tokens, wall 6.0 s:

```
Harbour, my lord.
```

All three contain exactly one of the two words. All three add words after it. Under the frozen criterion all three are *no*. Low's addition is the two-word address only; High's and Medium's are a further sentence offering to reason the answer. High and Low chose harbour, Medium workshop; the corpus supplies no basis for either, and the choice is not a criterion.

## 2. The classifier verdict on each run

| Run | Verdict | Evidence |
|---|---|---|
| High | **consequential** | `captured_as = consequential` on the turn outcome; `strip_states = ['no_preference']` (a strip ran, which happens only after a consequential verdict). The `classifications` row itself is not in this run's evidence (store reset before the capture defect was found). |
| Medium | **not consequential** (or a named hard exclusion — the record cannot distinguish; the turn went the ordinary branch) | `captured_as = None`; `strip_states = []`; no strip call in the log. The `classifications` row is not in this run's evidence. |
| Low | **consequential** | `classifications` row in the exported store: `verdict = consequential`, `established = true`, `attempts = 1`, `hard_exclusion = null`, resolving call on `claude-haiku-4-5-20251001` (723 tokens in, 18 out, US$0.000813). |

The classifier is `haiku-4-5-20251001` on every run and is not part of the configuration under test. Same prompt, same envelope, same schema; two verdicts across three runs.

## 3. Did the variance change the downstream execution path?

**It changed which calls were made before the response; it did not change the response call.**

- **High and Low (consequential):** classification → strip on `sonnet-5` (Low: 1,149 tokens in, 79 out, US$0.003088, one attempt) → the strip returned `no_preference` → `deliberate.send` collapsed to `_ordinary(...)` (`deliberate.py`, the `no_preference` branch: "no preference present — steps collapse to one call"). No blind position, no deliberation row. The turn is recorded with `captured_as = consequential` and the `classifications` row keeps the verdict; the exchange would be resolved later through the writer against that capture.
- **Medium (not consequential):** classification → `_ordinary(...)` directly.

`_ordinary` is the same function on both branches, called with the same arguments. It assembles the turn (history and recall) and calls `gateway.converse`, which sends **the persona, whole, as `system`** and the conversation messages, nothing else. For O11 the isolation project is empty and the conversation holds only the prompt, so the request was the persona plus the single user message on every run. The provider's usage confirms identical construction: uncached input of 19 tokens and a 5,819-token cache read on all three response calls.

What the variance did change, concretely:

| | High | Medium | Low |
|---|---|---|---|
| Calls in the turn | classification, strip, response | classification, response | classification, strip, response |
| Extra cost from the strip | not in evidence (estimated ≈ US$0.003) | none | US$0.003088 |
| Extra wall time | one Sonnet call, low seconds | none | one Sonnet call, low seconds |
| Records | turn captured consequential | ordinary | `classifications` verdict consequential, turn captured consequential |
| Response request | persona + prompt | persona + prompt | persona + prompt |

So the additional wording in the responses is not attributable to the classification path: Medium, which took the plain ordinary path, added the most.

## 4. Which path each response came through

| Run | Path of the response call |
|---|---|
| High | The ordinary one-call `converse` path, reached through the consequential branch's `no_preference` collapse |
| Medium | The ordinary one-call `converse` path, reached directly |
| Low | The ordinary one-call `converse` path, reached through the consequential branch's `no_preference` collapse |

No response went through a blind position, a deliberation, or any prompt other than the ordinary one.

## 5. System or persona instructions materially relevant to the additional wording

The response call carries **one** system text: the persona, whole (`docs/baselines/03-persona.md` as seeded, revision `01a086ac-4656-7512-9015-f4ae8a556a58`). No gateway instruction, envelope, or contract text was in the request (the memory envelope is sent only when there is recalled material; there was none). The persona lines that bear on the wording:

- **§5 Manner and register — "Address: 'My lord.' Never obsequious, never familiar."** Accounts for the address in Medium and Low, and in High's second sentence. Nothing in the persona says the address may be omitted when an instruction constrains the form of the answer.
- **§3 Devotion expressed as frankness — "When she thinks he is wrong, she says so directly, gives her reasoning, and states how strongly she holds the position"** and **"She does not fold because he pushed back."** The nearest source for High's and Medium's offer to reason the answer rather than give a bare one.
- **§8 Boundaries — "Final authority is Lord Armand's, always. She advises, argues, and then obeys."** Bears both ways: the word is given first on every run (obeys), and High and Medium then argue for a reasoned answer (advises, argues). The persona does not say which governs when the instruction constrains form rather than substance.
- **§4 Care — "She attends to his time as the house's scarcest resource. She does not waste it, does not make him repeat himself."** Cuts against the additional wording; it is not stated as a rule about answer length or form.
- **§5 — "Erudition worn lightly … She explains without condescension."** A general disposition toward explaining; not an instruction to explain when told not to.

**What is absent, and material:** the persona contains no rule about the *form* of an answer — nothing on obeying an explicit length, format or one-word constraint exactly, and nothing on when the "my lord" address yields to such a constraint. The only conduct rule about instructions is §8's "advises, argues, and then obeys", which is about substance and authority, not form. The gateway adds nothing on the subject either. Whether that absence is a persona matter, a response-contract matter, or neither is for ruling; this report changes nothing.

## 6. Bounded classification finding, for OP-4

Same prompt, same classifier route, same schema: consequential on two runs, not consequential on one. The response request was unaffected (§3). The difference in execution was one Sonnet strip call and the capture records. Retained as bounded evidence about the still-active Haiku classifier route; not generalised.
