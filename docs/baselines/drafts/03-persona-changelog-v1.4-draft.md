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

**Not changed:** §1, §3, §6, the five original boundaries in §8, voice, appearance, setting description, the House identity, and the §5 explicit-form rule.
