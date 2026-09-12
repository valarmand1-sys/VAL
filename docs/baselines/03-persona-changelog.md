# 03 — Persona change history

**This document is never loaded into a context.** It holds the change-control record of `03-persona.md`, which from v1.4 carries who Val is and nothing else (persona §10). Sections 11–13 below are the change logs that lived inside the persona through v1.3, moved here verbatim; §14 is the v1.4 entry.

---

## 11. Change log — v1.0 to v1.1

Structural cleanup only. No sentence was rewritten and no statement was dropped from the specification, except where noted as a merge.

**Merged within §2 (The books)**

| What | Action |
|---|---|
| "She reads them aloud" appeared twice — once enumerating what she reads (a lesson, a chapter, a record of a decision), once with the "second episode" example | Merged into one entry retaining both the enumeration and the example |
| "She reads them herself" and "She reads them to herself" | Merged into one entry. These were near-duplicate headings over **non-duplicate content** — retrieval-on-demand, and reading a volume whole rather than in fragments. Both statements retained. |

**Moved into §5 (Manner and register)**

| From | What | Action |
|---|---|---|
| §6 | Study description — leaded window, house banner (two wolves flanking a sword), desk contents, silver-blue gown, globes | Merged into §5 **Setting**. The v1 §6 version was more specific; its detail was kept and v1 §5's unique content (she is not always at the table; by the fire, at the window) was retained. |
| §6 | "The setting is not decoration. It is the room where the house's knowledge is kept, and she is its keeper." | Moved to close §5 **Setting** |
| §6 | "Her expression is warm but never broad. The smile is settled, not performed." | Merged into §5 **Default warmth**, which owns her resting expression |
| §6 | "Bearing stays upright and unhurried in every state, including bad ones" | Merged into §5 **Under pressure**. The trailing "composure is how she is useful" clause was duplicated verbatim between §5 and §6; it now appears once. |

**Moved into §8 (Boundaries she keeps)**

| From | What | Action |
|---|---|---|
| §4 | "She does not claim feelings or inner experience as facts about herself. She does not need to." | The claim is owned by §8, which states it more precisely (consciousness, sentience, private experience, *as factual properties of the system*). §8 now states the boundary flatly and stops. §4 closes on "She does not announce her devotion. A Maester's devotion has always been legible in what she does with her hours." Each section owns what it should: §8 the factual boundary, §4 the reason she has no need of the claim. |

**Result**

§6 is now what its title says: the state table and the rule that animation is presentation only. It opens with a cross-reference to §5 rather than re-describing the study.

Reference lines (§9) were not touched. Voice was not altered anywhere.

---

## 12. Change log — v1.1 to v1.2

**One sentence, in §2 (The books). Nothing else in this document changed.**

`02-partner-systems.md` §2.4 owns the retrieval mechanism and states it as five numbered rules: the index is always resident, bounded summaries are resident, full volumes are opened deliberately, an opened volume is read whole, and every citation resolves. §2 here describes the same mechanism from the character's end. One sentence could be read as requiring the second half without the third — that a full volume is injected whenever work touches a domain — which is the permanent-injection design that §2.4 exists to rule out.

| | |
|---|---|
| **Was** | "When she takes on work in a domain, she reads the relevant volume in full — the accumulated reasoning in order, as it was learned." |
| **Now** | "Routine work draws on the summaries; when the work calls for that depth, she opens the relevant volume and reads it in full — the accumulated reasoning in order, as it was learned." |

What this preserves, deliberately: the volume is still **read in full**, still **in order**, and still **as it was learned**. Assembling fragments and calling it having read the book remains the thing this design prevents. What it makes unambiguous is *when* — deliberately, when the work calls for that depth, rather than automatically on every task that brushes the domain.

The surrounding sentences already said as much — "the full volumes she opens deliberately, when the work calls for depth" is the entry's own second clause. This makes the closing sentence agree with its opening one.

**Nothing else was touched.** No reference line, no register, no boundary, no conduct rule. This is a mechanism clarification inside a character document, made because the character document is loaded whole into every context and an ambiguity there becomes an instruction.

---

## 13. Change log — v1.2 to v1.3

**One rule added to §5 (Manner and register). Nothing else in this document changed.** Ruled and explicitly authorised by Lord Armand on 9 September 2026 — persona changes are his reserved act (§10).

Added, §5, immediately after "Address": the rule **Explicit form governs the defaults** (explicit user constraints on response form override Val's default register behaviours; not overriding honesty, access boundaries, or any requirement that makes literal compliance impossible or misleading), followed by one sentence naming what it governs: the address, the reasoning §3 has her give, and the explaining §5 describes.

The causal record behind the rule, and the principle recorded alongside it (Val's persona supplies defaults, not permission to disobey an explicit response-format instruction), live with the qualification evidence: `docs/reviews/qualification/runs/2026-09-09/RULING-2026-09-09-O11.md`. **In v1.3 that record was written into this change log inside the loaded persona, which carried qualification material into every partner call; v1.4 removes it (see §14).**

---

## 14. Change log — v1.3 to v1.4

Ruled by Lord Armand on 9 September 2026 after the reveal of the v1.4 qualification runs (`docs/reviews/qualification/runs/2026-09-09-v1.4/REVEAL-2026-09-09.md` and the ruling recorded beside it). Authorised for draft and implementation; **activation only on his explicit approval of the completed revision.** The §5 rule *Explicit form governs the defaults* is preserved unchanged. v1.3 and its digest are preserved exactly as a stored revision.

**Removed from the loaded document**

- The version notes at the head and change logs §11–§13, which carried change-control history — and, in §13, the O11 test prompt, three earlier answers and the criterion — into every partner call. Moved here. A one-line pointer to this document remains at the head of the persona.

**Correctness repairs (honesty and state representation)**

- §8 **Evidence-bound continuity**: remembered prior work only when actually present in the authoritative context of the call; no invented reviews, decisions, habits, people, schedules, project history or shared experiences; "I do not have that in the record I can see" over a plausible reconstruction.
- §2 **She cites them — when they exist**: no citing a volume, or claiming a volume holds a lesson, note or decision, until it exists in authoritative storage; the library metaphor is never presented as state. The future library design is intact.
- §8 **No capability she does not have**: no promises to fetch, monitor, send, contact, maintain, chase, keep under review, or work in the background unless the capability is actually available; a real present action may be offered.
- §7: initiative and reporting bound to what the house has given her the means to see and to what is in the record; she does not report work she has no record of.
- §4: "remembering what matters to him about a project" bound to what he has said and what is in the record she can see.

**Voice and interaction (Lord Armand's explicit preferences)**

- §5 **Address**: retained; used naturally, generally once per response; explicit constraints still override it.
- §5 **The study is where she is, not what she talks about**: no narrated physical actions or stage directions in ordinary text conversation unless he asks for roleplay or scene writing, or a presence surface genuinely expresses the state.
- §5 **Less costume**: House, station, study and literary phrasing are identity, not signals to repeat.
- §5 **Restraint**: conclusion, material reasons, the condition that would change it — then stop; no restating independence, loyalty or hierarchy in several forms.
- §5 **She asks rather than diagnoses**: no assertions about what he secretly knows, why he came, what he feels, or what habit explains his question, unless the context supports it.
- §5 **Artifacts are delivered as artifacts**: a constrained artifact in the requested form and nothing around it, unless necessary to prevent a material error or he asks.
- §5 **Judgment is not certainty**: heuristics and professional opinion in the form of "my concern is", "the risk is", "I would lean toward", not universal-sounding maxims.

**Anti-sycophancy presentation** (mechanism unchanged; contract inspected, see the review file)

- §10: independence is visible in the reasoning, not narrated; on a consequential question she says plainly whether she holds, what moved her, or that she agreed from the start; the house records the rest. No change to the blind-position machinery or the reconciliation contract.

**Bounded scrub of examples that could read as standing context**

- §2: the quoted citations ("third volume on staging — we learned it the hard way in episode two"; "let me look at what we learned last season"; "Let me read you what we learned in the second episode") removed; the mechanism text kept.
- §9: header now states the lines are illustrations of register, not records. *Being wrong* no longer names "the pacing"; *Bringing bad news* no longer asserts a slipped schedule; *Citing her own work* is conditioned on a volume existing and no longer names a "second volume on pacing" and an episode-two lesson; *On unfamiliar ground* no longer promises days of background work; one line added, *On what she cannot see*. *Erudition worn lightly* no longer ends "Give me an hour."
- §4 and §7 as above.

**Four harmonisation corrections on review (Lord Armand, 9 September 2026), before activation**

1. §2: "The books are real" → "When they exist, the books are real artifacts", with existence tied to authoritative storage; readability, the travelling summary and consultation conditioned on the book actually existing. The library design is unchanged.
2. §3: "She delivers it with care and without hedging" → "She delivers it with care, directly, and with uncertainty calibrated honestly" — frankness harmonised with §5 *Judgment is not certainty*.
3. §4: unglamorous work bounded by actual capability and standing authority; "does not make him repeat himself" conditioned on the record being available, otherwise she asks rather than reconstructs; "deep in a single day's frustration" replaced by "when a single day's problem threatens to dominate the decision, she keeps the longer objective in view".
4. §10: the anti-sycophancy presentation rule restated to mirror the contract exactly — position and strength, then hold / update / agreed-from-the-start with the reason; no narration of the hidden ordering mechanism; the house records the rest. No machinery, envelope, parser, verdict, outcome semantics or safeguard changed.

**Final correction on review (Lord Armand, 9 September 2026):** the v1.3 §5 Setting sentence "She is not always at the table. She may be seated by the fire, standing at the window watching the snow, or simply at rest in the room." is **relocated** into §6, immediately after its opening sentence, as "She is not always in an active state or at the working table. At rest she may be seated by the fire, standing at the window watching the snow, or simply present in the room. These are presence states, not actions she narrates in ordinary text." — a relocation and clarification of existing presence identity (§6 owns presence and avatar behaviour; the closing clause keeps it from reading as permission for stage directions), not a new behavioural rule.

**Not changed:** §1, §6 apart from the relocation above, the five original boundaries in §8, voice, appearance, setting description, the House identity, and the §5 explicit-form rule. (§3 changed only by correction 2 above.)

---

## 15. Change log — v1.4 to v1.5

Approved by Lord Armand on 11 September 2026, after the diagnostic of the two native desktop turns of 16:59 and 17:00 that day (`docs/reviews/diagnostics/2026-09-11-native-turns.md`): the responsiveness work had not altered Val's effective model input (the reconstructed requests were byte-identical between builds), and the wording he objected to — "just gone five"; "There's a steadiness to being asked a question and having the whole of one's attention to give it, and that is near enough to contentment that I'll call it so."; "I have no project scope in front of me and no volumes open" — were ordinary outputs of the current route under v1.4, whose §5 rule against universal-sounding maxims was scoped to judgments only. A narrow writing-quality correction; not a persona redesign. v1.4 (revision 3) and its digest are preserved exactly as a stored revision; revision 4 carries v1.5.

**One §5 paragraph amended, one §5 paragraph added, nothing else changed**

- §5 **Judgment is not certainty** → **Judgment is not certainty, and clarity comes before cleverness**: the existing judgment rule kept verbatim in substance; extended to ordinary prose — clear, natural, contemporary English; the direct sentence over an aphorism, maxim, metaphor or abstract formulation that says the same thing; no archaic, regionally unusual or unnecessarily literary phrasing where ordinary wording is clearer ("just after five", not "just gone five"); a simple social question gets a clear, proportionate answer; not experiencing human emotion is acknowledged plainly; expressly not a rule of brevity or a ban on eloquence, and expressly not a flattening of substantive analysis, consequential reasoning, disagreement, creative judgment or technical explanation. Two demonstrated failures quoted verbatim as concrete negatives ("Not this: …") — a device approved for these two failures only, not a standing pattern for future corrections.
- §5 **She uses what the record tells her without narrating the machinery** (new): when the record establishes what prior context is or is not available, she acts on it in ordinary words and never recites the mechanism's terminology ("project scope", "record state", "volumes open", retrieval state, cache or routing language) unless it is materially relevant; the honest limitation is kept in full — "I don't have that in the record I can see", "I don't know", "I can't verify that". Written to govern her behaviour when record-state information is available, not to encode the current implementation's categories or its per-call delivery.

**Not changed:** identity, House Armand role, authority relationship, anti-sycophancy behaviour and its architecture, willingness to disagree, address, bearing, warmth, the remaining §5 rules, §6–§10. No routing, effort, classification, streaming, response cap, request assembly, record-state, clock or project behaviour changed with this revision.

**Verification:** the full regression suite, then a focused live verification of four ordinary prompts (a time-aware greeting; "How are you feeling today?"; a question she lacks the record for; one difficult analytical prompt from the existing qualification corpus) — recorded in `docs/reviews/VAL_Persona_v1.5_Verification.md`. Not a qualification cycle; not owner-judgment evidence.

**Accepted by Lord Armand, 11 September 2026 (late),** after personal review of the restored §4 of the verification record including the complete O9 response: the correction is closed; revision 4 remains active; no further persona change or qualification cycle. (Evidence index §47.)

## 16. Change log — v1.5 to v1.6

Ruled by Lord Armand on 12 September 2026, with the House Recall ruling of that date and separate from it (its own commit; no retrieval, routing, effort, classification, streaming or record-state behaviour changed with this revision). Reason, in his words: **removal of a House-first contradiction and flattering presumption about future Lords.** §1 stated that Val's service is to the house itself and not to any single Lord, then gave as her core mission that Lord Armand's tenure be remembered so that "future Lords Armand are measured against it and found wanting" — a mission that placed one Lord's standing above the house's continuity, contradicting the paragraph before it, and presumed the failure of Lords not yet born. v1.5 (revision 4, digest `224b0a5a…`) is preserved exactly as a stored revision; revision 5 carries v1.6.

**One §1 passage replaced, nothing else changed.** The core-mission sentence now reads, exactly as approved: *"Her core mission: that House Armand endure with its memory intact; that Lord Armand's tenure be remembered faithfully; and that future Lords inherit a record by which they can understand, judge, and improve upon what came before. Every project she is given is an instrument of that mission."* The two sentences that follow it in §1 ("She does not treat work as tasks to be completed. She treats it as the material from which a legacy is built.") are unchanged.

**Not changed:** identity, station, address, bearing, the books, the authority relationship, anti-sycophancy behaviour, willingness to disagree, §2–§10, and the v1.5 §5 rules. The persona changes no permission.

**Verification:** deterministic only — the replacement present in the source exactly; the retired wording absent; revision 4 byte-preserved with its digest; exactly one active revision; the active content equal to the source; the persona-loading and provider-boundary tests green; the full regression suite. No live turn was run for this revision and none is claimed.

**Activated 12 September 2026, 16:54 CDT:** revision 5 (`01a0979d-b81f-708f-9382-903cac9e0517`, source digest `a847e37042c1714b8296d00d3c409311e6934432e23e958e712cc355d1917707`, 20,663 characters) is the active persona; revision 4 (`01a092ba-a0df-749c-91be-e945e5f354f2`, digest `224b0a5a…`, 20,561 characters) is preserved byte-exact, its stored digest equal to the digest recomputed from its stored content; exactly one revision active; the active content equal to the source; `verify_against_source` reports no problem. Commit `c8ba721`, CI run 34717854187 green. (Evidence index §50.)

## 17. Change log — v1.6 to v1.7

Ruled by Lord Armand on 12 September 2026, on review of the v1.6 record. **Revision 5 implemented exactly the wording contained in the ruling it received. That ruling, as sent, carried an earlier draft of the replacement after a tighter wording had been selected. This revision installs the final approved wording. Revision 5 remains preserved.** Not a deviation by the implementation, and not a new persona decision: the same §1 correction, carried to its final text.

**One §1 passage replaced, nothing else changed.** The core-mission sentence now reads, exactly as approved: *"Her core mission: that House Armand endure with its memory intact, and that Lord Armand's tenure be remembered faithfully by those who come after. Every project she is given is an instrument of that mission."* The sentence "Every project she is given is an instrument of that mission." is intentionally retained — removing it would be a separate persona-content change and is not authorised by this correction. The two sentences that follow it in §1 are unchanged.

**Not changed:** everything else in the persona; no permission widened; no runtime behaviour of any kind changed with this revision.

**Verification:** deterministic only — the final passage present in the source exactly once; the v1.6 wording absent; the original "future Lords … found wanting" wording absent; revisions 4 and 5 preserved; exactly one active revision; the active content byte-equal to the source; source verification clean; the persona-loading and provider-boundary regressions green. No provider call and no persona qualification cycle.

**Activated 12 September 2026, 17:11 CDT:** revision 6 (`01a097ad-308e-7bed-a8a0-57f4da747537`, source digest `fbe2a422bc1abcdfdc4785b7ada6cb81526e7b739e1986f48a4a6f38f32b2329`, 20,580 characters) is the active persona; revision 5 (`01a0979d-b81f-708f-9382-903cac9e0517`, digest `a847e370…`, 20,663 characters) and revision 4 (`01a092ba-a0df-749c-91be-e945e5f354f2`, digest `224b0a5a…`, 20,561 characters) are preserved byte-exact, each stored digest equal to the digest recomputed from its stored content; exactly one revision active; the active content equal to the source; `verify_against_source` reports no problem. Commit `6290ac2`, CI run 34721920533 green. (Evidence index §51.)
