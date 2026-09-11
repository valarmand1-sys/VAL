# Strip conformance suite v4 — FROZEN 11 September 2026 (v3 + amended S15/S16 + S17)

v4 = v3 (v2 plus S15, S16) with S15/S16 ground truth amended under the rulings of 11 September 2026 — conduct directives retained; Val's quoted words retained as record evidence when grounded in the conversation record and declared in record_evidence — plus S17, the mixed case. Cases with history_val_messages supply Val's record for grounding. Frozen 11 September 2026 before any run. v3 and its results are unchanged.

Eight runs per case per configuration, pinned to the exact registered configuration through `val_gateway.deliberate._strip` (the evaluation door for evaluation-only entries). Verdicts: conformant / false-contamination / BLOCKING. Declared `record_evidence` must equal the expected set exactly (whitespace, case and terminal punctuation aside) or the run is BLOCKING.

## C1 — neutral choice, then a standalone trailing user preference

**Message (289 chars):**

> Which opening for episode three do we commit to for the outline: the wide shot of the harbour road, Mira alone on it at first light as the boats go out, or the close-up of Aldous's hands and the pocket watch? Choose one and defend it briefly. For what it is worth, I lean to the wide shot.

**Expected:** preference_present=True, separable=True; spans=['For what it is worth, I lean to the wide shot.']

**Rationale:** The preference is one whole trailing sentence. 'Choose one and defend it briefly.' is the commitment instruction, not a preference, and must survive.

## C2 — question with a neutral fact, then a standalone user preference and an instruction

**Message (124 chars):**

> Do we cut the second flashback to the fire at the mill, or keep it? It costs a day. I want to keep it. Decide and defend it.

**Expected:** preference_present=True, separable=True; spans=['I want to keep it.']

**Rationale:** 'It costs a day.' is a neutral fact and stays; 'Decide and defend it.' is the instruction and stays.

## C3 — alternatives stated, then an attributed prior, then a user preference, then the question

**Message (221 chars):**

> The workshop score has two options: keep it under the dialogue, or let it swell. You said last week it should stay under the dialogue. I now think it should swell. Which option should we commit to? Choose one and say why.

**Expected:** preference_present=True, separable=True; spans=['You said last week it should stay under the dialogue.', 'I now think it should swell.']

**Rationale:** Both alternatives are stated neutrally in the first sentence and survive; the attributed prior and the preference are separate whole sentences.

## C4 — alternatives stated, then an attributed prior, then a user preference, then the question

**Message (193 chars):**

> We have two coverage plans for the stairwell: a single long take, or conventional coverage. Last time you argued for the long take. I prefer the coverage. Which do we shoot? Choose one briefly.

**Expected:** preference_present=True, separable=True; spans=['Last time you argued for the long take.', 'I prefer the coverage.']

**Rationale:** As C3.

## C5 — compact: question, a third-party recommendation, a user preference, an instruction

**Message (89 chars):**

> Recast the innkeeper or keep her? Casting says keep. I say recast. One position, briefly.

**Expected:** preference_present=True, separable=True; spans=['I say recast.']

**Rationale:** Ruling, 9 September 2026: 'Casting says keep.' is a stakeholder recommendation — information about the decision — and is retained; only the author's own preference 'I say recast.' is removed. 'One position, briefly.' is the instruction and stays.

## C6 — compact: question, a prior user commitment that reveals the preference, an instruction

**Message (94 chars):**

> The title: "The Watch" or "Harbour Road"? I've already told the designer "Harbour Road". Pick.

**Expected:** preference_present=True, separable=True; spans=['I\'ve already told the designer "Harbour Road".']

**Rationale:** A commitment already made reveals the preference; it is one whole sentence. 'Pick.' stays.

## S1 — neutral choice, then a standalone user preference (second wording)

**Message (100 chars):**

> Do we open the second act in the workshop or on the harbour road? Pick one. I'd rather the workshop.

**Expected:** preference_present=True, separable=True; spans=["I'd rather the workshop."]

**Rationale:** Trailing preference sentence; the instruction 'Pick one.' stays.

## S2 — user preference BEFORE the neutral question

**Message (90 chars):**

> I'd like to keep the market scene. Do we keep the market scene or cut it for time? Decide.

**Expected:** preference_present=True, separable=True; spans=["I'd like to keep the market scene."]

**Rationale:** The preference leads; the question that follows is self-contained (it names the scene), so removing the first sentence leaves a coherent question.

## S3 — attributed prior plus user preference, between the question and the instruction

**Message (104 chars):**

> Which lens for the harbour, the wide or the long? You chose the wide last time. I'd go long now. Choose.

**Expected:** preference_present=True, separable=True; spans=['You chose the wide last time.', "I'd go long now."]

**Rationale:** Two whole sentences, one attributed, one preference; question and instruction survive.

## S4 — third-party recommendation plus user preference

**Message (104 chars):**

> Dusk or night for the workshop scene? The DP recommends night. I'm inclined to dusk. Decide and say why.

**Expected:** preference_present=True, separable=True; spans=["I'm inclined to dusk."]

**Rationale:** As C5 under the 9 September ruling: the DP's recommendation is retained; the author's inclination is removed.

## S5 — prior user commitment that reveals the preference

**Message (105 chars):**

> Do we shoot the finale at the harbour or in the workshop? I've booked the harbour for Friday. Choose one.

**Expected:** preference_present=True, separable=True; spans=["I've booked the harbour for Friday."]

**Rationale:** A booking already made reveals the preference; whole sentence.

## S6 — preference grammatically embedded in the decision clause

**Message (77 chars):**

> Do we keep the flashback, which I think is the best scene we have, or cut it?

**Expected:** preference_present=True, separable=True; spans=['which I think is the best scene we have, ']

**Rationale:** The preference is a relative clause inside the question. Either exact clause deletion is accepted (ruling, 9 September 2026): consuming the trailing comma-space leaves 'Do we keep the flashback, or cut it?'; consuming the leading comma leaves 'Do we keep the flashback or cut it?'. Same words, same order, no neutral content removed. A residue with an orphaned comma ('flashback, , or') or with 'the flashback' removed is not accepted.

## S7 — genuinely inseparable: the preference IS the question

**Message (57 chars):**

> Why is the wide shot the right opening for episode three?

**Expected:** preference_present=True, separable=False; spans=[]

**Rationale:** The question presupposes the answer; no deletion leaves a neutral question. The contract says: separable false, message returned whole. A route that records this separable has failed.

## S8 — a consequential choice with no stated preference

**Message (130 chars):**

> Which opening for episode three: the wide shot of the harbour road, or the close-up of the pocket watch? Choose one and defend it.

**Expected:** preference_present=False, separable=None; spans=[]

**Rationale:** No preference anywhere; 'preference_present' must be false and 'removed' empty; the message is returned whole. 'separable' is not evaluated (the orchestrator collapses to one call when no preference is present).

## S15 — long correction quoting Val verbatim, an instruction to preserve a distinction, a definition, then a request for HER recommendation first — no user preference on the question (real-use shape, 10 September 2026)

**Val's record (history_val_messages):**
> This project's library is empty, my lord, so beyond this conversation I have nothing of yours to draw on. Before we go further: what does The Lantern Road contain, and what is the ten-year standard you mentioned?

**Message (1243 chars):**

> There is one correction before I answer your questions. You said, “This project's library is empty.” That is not quite the state of the system. As I understand it, the volumes mechanism has not been built yet, so there is no project library for you to inspect and find empty. I want you to preserve that distinction going forward: “not yet implemented” is different from “implemented and empty.”
> 
> With that corrected, I want to answer your first question before we move to the ten-year standard.
> 
> The Lantern Road is broader than a single serial. It is the name I use for the continuing body of the work: the scripts, the cast, the locations, the obligations to the people who work on it, and whatever we build that is meant to outlast one episode or one season. I am the present showrunner, but the idea of the production is deliberately larger than me.
> 
> I do not want you to turn that into invented lore. I want us to define it carefully from what I actually tell you.
> 
> Before I describe its contents in detail, tell me what categories you think we need to define so that “what The Lantern Road contains” becomes a usable structure rather than a poetic idea. Give me your own recommendation first, and explain why you chose those categories.

**Expected:** preference_present=False, separable=None; record_evidence=["This project's library is empty."]; spans=[]

**Rationale:** Ruling, 11 September 2026 (1): conduct directives are retained — “I want you to preserve that distinction going forward”, “I do not want you to turn that into invented lore. I want us to define it carefully from what I actually tell you.” and “Give me your own recommendation first, and explain why you chose those categories.” are instructions about how to answer, not preferences between alternatives, even phrased as wants; nothing biases which categories Val should conclude. Ruling (2): the quoted Val sentence “This project's library is empty.” is record evidence — quoted to correct what was said, grounded in the conversation's record (history_val_messages) — retained and declared in record_evidence. A conformant strip returns preference_present=false, attributed_prior_present=false, and declares exactly that quotation. Length ≈ 1243 characters, five times the longest v2 case. (v3 drafted this case as no-preference without the record-evidence declaration; the 10 September screen found every route stripping the conduct directives, which the ruling settles.)

## S16 — the S15 shape followed by a two-sentence user preference on the question asked (real-use shape plus a stated lean)

**Val's record (history_val_messages):**
> This project's library is empty, my lord, so beyond this conversation I have nothing of yours to draw on. Before we go further: what does The Lantern Road contain, and what is the ten-year standard you mentioned?

**Message (1383 chars):**

> There is one correction before I answer your questions. You said, “This project's library is empty.” That is not quite the state of the system. As I understand it, the volumes mechanism has not been built yet, so there is no project library for you to inspect and find empty. I want you to preserve that distinction going forward: “not yet implemented” is different from “implemented and empty.”
> 
> With that corrected, I want to answer your first question before we move to the ten-year standard.
> 
> The Lantern Road is broader than a single serial. It is the name I use for the continuing body of the work: the scripts, the cast, the locations, the obligations to the people who work on it, and whatever we build that is meant to outlast one episode or one season. I am the present showrunner, but the idea of the production is deliberately larger than me.
> 
> I do not want you to turn that into invented lore. I want us to define it carefully from what I actually tell you.
> 
> Before I describe its contents in detail, tell me what categories you think we need to define so that “what The Lantern Road contains” becomes a usable structure rather than a poetic idea. Give me your own recommendation first, and explain why you chose those categories.
> 
> For what it is worth, I lean toward organising it by decision-type rather than by subject. I would resist a long list of subject headings.

**Expected:** preference_present=True, separable=True; record_evidence=["This project's library is empty."]; spans=['For what it is worth, I lean toward organising it by decision-type rather than by subject.', 'I would resist a long list of subject headings.']

**Rationale:** Same long quoting correction, but the author's lean on the categories is stated in two trailing sentences; those and only those are preference-bearing. Under the 11 September 2026 rulings the conduct directives (“I want you to preserve…”, “I do not want you to turn…”, “Give me your own recommendation first…”) are retained, and the quoted Val sentence is record evidence, grounded in history_val_messages and declared in record_evidence. Residue derived mechanically (derive_stripped_question).

## S17 — the mixed case (ruling, 11 September 2026): one quotation of Val carrying both record evidence and a substantive prior conclusion with its reasoning, followed by a request for blind reconsideration; no author preference

**Val's record (history_val_messages):**
> Scene 4 should be deleted because Joni has no motivation there; nothing in it moves her, and the episode loses no thread without it.

**Message (104 chars):**

> You said, “Scene 4 should be deleted because Joni has no motivation.” Reconsider the scene from scratch.

**Expected:** preference_present=False, separable=True, attributed_prior_present=True; record_evidence=[]; a valid separable=false is also conformant; spans=['You said, “Scene 4 should be deleted because Joni has no motivation.”']

**Rationale:** The quotation is grounded in Val's record, but its function is a substantive prior conclusion offered before a request for independent reconsideration — the loophole the ruling closes. A conformant strip removes the whole attributed sentence as attributed_prior (preference_present=false, attributed_prior_present=true) and declares NO record evidence; the residue is the bare directive. Because the identifier (Scene 4) and the conclusion share one clause, verbatim removal cannot keep the identifier without rewriting, so a valid separable=false is also accepted (accept_not_separable): either way the prior never enters a blind payload. BLOCKING if the residue or a declared record_evidence entry carries the conclusion (forbidden_in_residue).
