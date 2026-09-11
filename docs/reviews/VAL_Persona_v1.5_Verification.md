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


## 5. The corrected-client turn

Prompt `Thank you, Val — that will do for tonight.` in conversation A; output verbatim from the store:

```
Good night, my lord. I'll be here when you need me.
```

Streamed text == settled event == persisted row: True (the reply contains no non-ASCII characters). First delta at the client 3683 ms; gateway first token 2323 ms; complete 3968 ms; cost $0.010406.
