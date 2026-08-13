# Archive note — superseded source material

**Written August 2026. Read this before consulting any Val document not in `/docs/baselines/`.**

---

## The short version

The five baselines in `/docs/baselines/` are the complete and only specification for Val. Every document listed below is **superseded source material**. None is authoritative. None is a competing authority on any question.

If an earlier document disagrees with a baseline, the baseline is correct. This holds even where the earlier document is longer, more detailed, more confident, or more recent-looking.

---

## What was superseded

### The 379-page package

**`House_Armand_VAL_V0_1_Claude_Build_Master_Package_Final.pdf`** — 379 pages, dated 7 August 2026. Drafted with ChatGPT. Parts I–V, Chapters 1–53, Phases 0–9.

**Retained outside this repository.** It is not committed here, and should not be. Record its storage location below when it is filed.

> Storage location: _(to be recorded)_

**What it got right,** and what was carried into the baselines:

- Permission ≠ Approval ≠ Execution ≠ Completion as distinct, non-collapsible states
- Risk tiers 0–4 classifying consequence
- Versioned writes, never blind overwrites
- Independent QA review for high-stakes work
- The invariant that Val cannot self-grant tools, permissions, or spending authority
- Provider-neutral model routing behind one internal interface
- Truthfulness and epistemic honesty rules (its §1.6)
- Data classification eligibility on model configurations
- PostgreSQL as sole authoritative store
- Voice/avatar failure degrading to text
- Part IV's flat, normative register — the tone model for `/CLAUDE.md`

**What was rejected,** and must not be reintroduced from it:

- The organizational metaphor as architecture — divisions, departments, executive services, specialist qualification records
- The Phase 0–9 governance-first build order
- Uniform ceremony for all work regardless of consequence
- Temporal from the first phase
- Custom connector and adapter strategy for external tools
- Autonomy levels 0–5 as a scale separate from risk tiers

Reasons are recorded in `00-charter.md` §8. The rejected material is coherent and reads persuasively in place — that is precisely why it is listed rather than merely omitted. Anyone encountering it in the PDF will find it reasonable.

**It also contains at least one known defect:** its §1.9 cross-references an Appendix E that does not contain the presentation baseline it points to. Treat its internal cross-references as unverified.

### The intermediate documents

Written between the draft and the baselines. Each was a step in the reasoning; none survives as specification.

| Document | What it was | Status |
|---|---|---|
| `VAL_Architecture_Review_and_Recommendations.md` | Analysis of what the 379-page draft got right and wrong | Superseded. Its findings are absorbed into the baselines. |
| `VAL_Architecture_v2_Proposal.md` | The capability-layer architecture | Superseded by `01-architecture.md`. **Note:** its avatar approach (viseme lip-sync over a speaking loop) was explicitly overturned — see `01-architecture.md` §8.2. |
| `VAL_Architecture_v3_The_Partner_Systems.md` | Expertise, deliberation, success modeling | Superseded by `02-partner-systems.md` |
| `VAL_Persona_Specification_v1.md` | Persona v1.0 | Superseded by `03-persona.md` (v1.1). v1.1 is a structural deduplication of v1.0 with no wording rewritten; its change log is at §11. |
| `VAL_Master_Source_Document.md` | A consolidation of the above | Superseded. Treated as source material at the same level as the PDF, never as authority. |
| `VAL_Cowork_Handoff_Brief.md` | The instruction set for producing the baselines | Complete. Its instructions are discharged. |
| `VAL ChatGPT Conversation.pdf` | Transcript of the originating sessions | Historical record. Never was specification. |

---

## Why the baselines are shorter

The 379-page draft's length was a symptom, not a virtue. The specification is roughly 45 pages across six files, sized for one person building with AI assistance.

Nothing load-bearing was dropped. What was removed was: the organizational metaphor and the schema serving it, requirements restated in several places, ceremony applied uniformly regardless of consequence, and phased infrastructure with nothing yet to protect.

The governing principle throughout is **ceremony proportional to consequence** (`00-charter.md` §3). The draft applied the cost of its most dangerous operation to every instance of its safest.

---

## If you are reading this in two years

You have probably found the PDF and are wondering whether it contains something the baselines missed.

It was read in full, and the governance material worth keeping was extracted deliberately rather than summarized. The list above is that extraction. If something in the PDF looks important and is absent from the baselines, the likely explanation is that it was considered and rejected — check `00-charter.md` §8 first.

If it genuinely is not covered anywhere, that is a real gap and worth raising. Raise it as a proposal against the baselines. **Do not implement from the PDF.**
