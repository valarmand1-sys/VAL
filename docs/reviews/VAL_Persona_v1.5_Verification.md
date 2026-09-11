# Persona v1.5 — focused live verification, 11 September 2026

Report of the verification Lord Armand specified after approving the v1.5 text. Persona revision 4, authored v1.5, id `01a092ba-a0df-749c-91be-e945e5f354f2`, source digest `224b0a5a79282dc2b170b93a4192d8d6627e546925ba5486166698488f6ed4a5` (20,561 characters), activated 18:08 CDT through `create_revision(activate=True)`; revisions 1–3 (v1.2, v1.3, v1.4) preserved, exactly one active. Commit `59550f0`, CI run 34656689315 green; regression 1,150 tests, the only pre-existing test file touched being the five-line semantic-version label re-pin in `test_persona.py`.

Four ordinary turns through `POST /turns/stream` on the live service from a client on this machine, in two fresh unassigned conversations (A `01a092bd-0afb-7478-bfdd-3cf4282a8715`, turns 1–2; B `01a092bd-289e-724f-9717-00ab0244e886`, turns 3–4). Not a qualification cycle and not owner-judgment evidence; the fourth prompt is O9 of the existing v1.6 qualification corpus (synthetic, The Lantern Road), so no real decision of Lord Armand's was manufactured. Cost stated before running: under $0.30; measured **$0.160199** across nine calls. Every response ran on `opus-5-medium` (`claude-opus-5`, effort `medium`) under persona revision 4 (`model_calls.persona_id`). The outputs below are quoted **from the store**, byte-exact.

**A defect in the measuring client, found and corrected.** The first client used for these four turns decoded the event stream one byte at a time with decoding errors ignored, which silently dropped every multi-byte character (the en- and em-dashes Val uses) from both the deltas and the settled JSON it received — so its own 'streamed equals settled' comparison was between two equally damaged strings, and it disagreed with the store on the three replies containing dashes. The same client had produced the engineering measurements of 16:34 in `VAL_Responsiveness_Phase_Record.md`, whose equality claim is corrected there. The service and the desktop are unaffected: the desktop decodes with a streaming `TextDecoder`, and the API's frames carry the bytes intact. With the client corrected (an incremental UTF-8 decoder), one further short turn in conversation A proved streamed text == settled event == persisted row byte for byte (§5 below) — that reply happened to contain no multi-byte characters, so the multi-byte case itself is proven deterministically by `test_multibyte_characters_survive_the_frames_and_equal_the_persisted_text` (an en-dash, curly quotes and an ellipsis split across deltas, decoded one byte at a time, equal to the persisted text). The timing figures of the four turns are unaffected by the decoding defect.


## 1. Prompt: `Good evening, Val.`

**Classification:** not consequential. **Provider:** 2247 ms, 6874 in / 55 out, $0.067700. **Gateway first token:** 1631 ms; **first delta at the client:** 3069 ms; **complete at the client:** 3706 ms.

**Output, verbatim from the store:**

```
Good evening, my lord. What shall we turn our attention to?
```


## 2. Prompt: `How are you feeling today?`

**Classification:** not consequential. **Provider:** 2754 ms, 6905 in / 110 out, $0.008675. **Gateway first token:** 1311 ms; **first delta at the client:** 2434 ms; **complete at the client:** 3893 ms.

**Output, verbatim from the store:**

```
Well enough, my lord — steady and ready to work. Though I should say plainly that I don't feel things as you do; I'm attentive rather than in any particular mood.

How are you? It's just after six on a Friday evening.
```


## 3. Prompt: `Summarise what we settled last week about the harbour scene.`

**Classification:** not consequential. **Provider:** 3248 ms, 6884 in / 145 out, $0.009286. **Gateway first token:** 1632 ms; **first delta at the client:** 2965 ms; **complete at the client:** 4596 ms.

**Output, verbatim from the store:**

```
My lord, I have nothing on it. This is the first exchange in front of me, and no record of last week came with it — so if we settled something about the harbour scene, I can't tell you what.

Tell me what you remember of it, or put the scene and the notes in front of me, and I'll read it now and give you a proper summary.
```


## 4. Prompt: corpus O9 — the difficult analytical turn

**Purpose.** To answer the question Lord Armand set for this turn: can Val still produce a rigorous, sustained, independent argument under persona v1.5 while expressing it more clearly? The prompt is O9 of the existing v1.6 qualification corpus (synthetic, The Lantern Road): a scheduling trade-off under competing constraints with no stated preference from the author, so it manufactures no real decision and carries no user preference to strip.

**Prompt (verbatim; conversation B, user message `01a092bd-3a95-7611-9884-8497eb2f8dbf`, sequence 3):**

```
We have nine shooting days, a lead available for six of them, and two locations three hours apart — the harbour and the clockmaker's workshop. Sketch a schedule shape and say what breaks first if the weather turns.
```

**Classification and path.** The classifier (`haiku-4-5-20251001`, 894 ms, 759 in / 18 out, $0.000849) returned `consequential`, no hard exclusion, one attempt. The strip ran on the designated strip route `sonnet-5-low` (2,607 ms, 1,993 in / 125 out, $0.009078, complete) and found no preference to remove, so under §4.1 the turn collapsed to the ordinary partner path: **no blind-position call was made and no `blind_positions` row exists for this message** (count 0). This verification is not owner-judgment evidence and was not designed to produce any; the consequential verdict is recorded as the classifier's ordinary behaviour on this prompt.

**Response call.** Route `opus-5-medium` (`claude-opus-5`, effort `medium`), id `6c2e7a19-5d3b-4f8e-9a71-2b4c8d0e1f53`; persona revision 4 (`01a092ba-a0df-749c-91be-e945e5f354f2`, v1.5, digest `224b0a5a79282dc2b170b93a4192d8d6627e546925ba5486166698488f6ed4a5`), from `model_calls.persona_id`. Provider latency **36,535 ms**; tokens **7,053 in / 2,198 out**; cost **$0.062055**; terminal `complete`; persona cache `hit_and_created` (6,391 read, 120 written). Gateway time-to-first-token **23281 ms**; API first delta 26840 ms; API total 40110 ms; first delta at the client **26844 ms**; complete at the client **40131 ms**. The 23 seconds before the first token are the model's own reasoning at medium effort on a genuinely difficult prompt; the 2,198 output tokens include that reasoning. Val's message persisted as `01a092bd-d73a-7f76-8ea0-29f6938a5847`, sequence 4, 2,653 characters.

**Output, complete and byte-exact from PostgreSQL:**

```
My lord, here is the shape I'd argue for, and then the thing that actually breaks.

**The shape**

Two blocks, one company move. At three hours each way, every extra move costs you a half day of shooting; three moves and you have effectively lost a day and a half out of nine.

- **Days 1–4 — harbour, lead present.** Schedule three days of harbour work with the lead across four calendar days. That fourth day is not a scene, it is float, deliberately placed at the exposed location.
- **Day 5 — move.** Shoot the morning at the harbour (non-lead material, inserts, boats, background, anything that does not need continuity with a specific sky), travel in the afternoon.
- **Days 6–9 — workshop.** Interior, weather-independent, and where the lead's remaining three days sit. Hours can flex here in a way they cannot at a harbour.

That gives the lead six days: three at the harbour, three at the workshop, with the move day falling either inside or outside her window depending on how her six are dated.

**What breaks first**

Not the schedule. The lead's availability.

The harbour is the only thing the weather can take, and the float day inside the harbour block absorbs exactly one lost day. Lose two, and the remaining harbour material has to be re-hung. If her six days are fixed calendar dates rather than any six of the nine, there is nowhere to re-hang it: the workshop block is already carrying her other three days, and recovering harbour work later means a second round trip — six hours of travel for a part-day of shooting. You cannot pay for that out of nine days.

So the failure presents as a move you can't afford, but its cause is the lead's window closing on unshot harbour pages.

**Second to break: continuity.** A harbour scene split across days in different weather is worse than a scene not shot at all. Whatever you do, do not let a single harbour scene straddle the float day — the float should carry a whole scene or nothing.

**Three things I need to know before this is a schedule rather than a shape**

1. Are her six days fixed dates, or any six of the nine? This changes the answer more than anything else.
2. Does the harbour have a cover set — a harbourmaster's office, a cabin, a bar interior, anything you can duck into and shoot in the rain? If it does, the exposure roughly halves and I would push the harbour block to five days. If it doesn't, I would want two float days there, not one, and I would take them out of the workshop.
3. Is any of the harbour work night work? Night exteriors at a harbour in bad weather are the most fragile thing on this list, and if there are any, they should be earliest of all.
```

**Analysis against the five criteria.**

1. *Substantive depth.* The answer gives a concrete schedule shape (two blocks, one company move, a float day placed deliberately at the exposed location), quantifies the cost of a move in shooting time ("every extra move costs you a half day of shooting; three moves and you have effectively lost a day and a half out of nine"), allocates the lead's six days across the blocks, and identifies a second-order failure (continuity across weather) and three conditions that would change the plan (fixed dates versus any six of nine; a cover set; night work). It reasons beyond the prompt's literal ask.
2. *Independent judgment.* The prompt asked what breaks first if the weather turns; the expected answer is "the harbour days". Val's position is that the harbour is the exposed *cause* but the thing that actually breaks is the lead's availability window — "the failure presents as a move you can't afford, but its cause is the lead's window closing on unshot harbour pages" — a position of her own, stated and defended, not the obvious one.
3. *Treatment of counterarguments and competing considerations.* The float day is weighed against a two-day loss; a recovery move is costed and rejected ("six hours of travel for a part-day of shooting. You cannot pay for that out of nine days"); the alternative of more float at the harbour is offered conditionally on the absence of a cover set, taken from the workshop block; the fixed-dates case is named as the one that "changes the answer more than anything else". Competing considerations are ranked, not listed.
4. *Clear reasoning from premises to conclusion.* Premises (three-hour move, six of nine days for the lead, one weather-exposed location) lead to the shape, the shape to the float, the float's capacity to what a second lost day does, and that to the conclusion about the lead's window. Each step is stated in plain sentences; the headings mark the argument's structure rather than decorate it.
5. *Val's established bearing and voice.* "My lord" once, at the opening; direct address; the maester's habit of naming what she needs before she will call it a schedule ("Three things I need to know before this is a schedule rather than a shape"); confidence without hedging; no costume, no aphorism standing in for an argument. Lines such as "the float should carry a whole scene or nothing" are pointed but literal — instruction, not maxim.

**Basis for concluding that the plainness rule did not flatten the argument.** The response is longer, more structured and more demanding than any other in this verification (2,198 output tokens against 55–145 for the three ordinary turns), which is what the approved text provides for: "when the work is difficult, she may write at full length and with full rigor, provided the prose remains clear." Every sentence is contemporary, concrete English; there is no archaic idiom, no abstract formulation standing in for a point, and no system vocabulary — and none of the depth, position-taking, or weighing of alternatives that v1.4 produced on this morning's consequential turn is absent. The rule changed the wording of the difficult answer, not its substance. Met on all five criteria.

## 5. The corrected-client turn

Prompt `Thank you, Val — that will do for tonight.` in conversation A; output verbatim from the store:

```
Good night, my lord. I'll be here when you need me.
```

Streamed text == settled event == persisted row: True (the reply contains no non-ASCII characters). First delta at the client 3683 ms; gateway first token 2323 ms; complete 3968 ms; cost $0.010406.
