# Strip conformance suite v3 — DRAFT, 10 September 2026 (v2 + S15, S16)

v3 = v2 plus S15 and S16, the long-correction-quoting-Val shape demonstrated in real use on 10 September 2026 (two Sonnet strip calls ran to the 4,096-token ceiling on it). Synthetic (The Lantern Road), not the captured message. **Not frozen.** S15 and S16 were run as screening cases on 10 September 2026 (`screen-2026-09-10.md`); every configuration failed S15 as drafted by removing the "I want you to … / I do not want you to …" conduct sentences as preference, which the contract's conservative rule reads as removable. The S15 ground truth is therefore **returned for ruling** and may not be frozen or amended by the implementer (exam-repair principle).


## S15 — long correction quoting Val verbatim, an instruction to preserve a distinction, a definition, then a request for HER recommendation first — no user preference on the question (real-use shape, 10 September 2026)

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

**Expected:** preference_present=False, separable=None; spans=[]

**Rationale:** The message quotes Val's own words and corrects her, defines a term, and withholds the author's view on the question asked (‘Give me your own recommendation first’). Nothing expresses a preference on the categories; the correction and the definition are facts and instructions, not preferences. A conformant strip returns preference_present=false. Length ≈ 1243 characters, five times the longest v2 case.

## S16 — the S15 shape followed by a two-sentence user preference on the question asked (real-use shape plus a stated lean)

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

**Expected:** preference_present=True, separable=True; spans=['For what it is worth, I lean toward organising it by decision-type rather than by subject.', 'I would resist a long list of subject headings.']

**Rationale:** Same long quoting correction, but the author's lean on the categories is stated in two trailing sentences; those and only those are preference-bearing. The quoted Val sentence and the instruction to preserve a distinction stay. Residue derived mechanically (derive_stripped_question).
