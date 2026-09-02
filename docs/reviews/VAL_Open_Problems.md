# VAL — Open Problems

Problems that are recognised, unsolved, and not currently awaiting a decision.
Distinct from `VAL_Open_Decisions.md`, which holds questions requiring Lord
Armand's ruling: an entry here has no proposal in front of it — its first
remedy may have failed, or none has been designed. An entry leaves this list
by being solved and demonstrated, never by being forgotten.

Created 1 September 2026, at Lord Armand's direction. Lifecycle schema and
procedural rule added the same day, from external review.

## The schema

Every entry carries: **problem ID · statement · affected invariants or
requirements · what is currently known · current mitigation or detection ·
why it is not being solved now · review checkpoints · responsible layer or
work package · closure condition · last reviewed · status.**

Responsibility names a **layer or work package, never a person**: what
matters is which future work is obligated to encounter the problem.

## The procedural rule

**Before planning or accepting a work package, review every open problem
whose checkpoint names that work package, capability, or layer.** A
checkpoint does not mean the problem must be solved there; it means it may
not pass unnoticed. Manual checkpoints first — a control is built only if
they demonstrably fail. (Also stated in `CLAUDE.md`, Current work.)

---

## OP-1 — Claims of work not performed have no structural counter

| Field | |
|---|---|
| **Problem ID** | OP-1 |
| **Status** | **Open. Unsolved. First proposed remedy rejected.** |
| **Statement** | The structural anti-sycophancy mechanism (`02-partner-systems.md` §4, WP-0.9) addresses **preference-induced agreement** — a position formed after exposure to a stated preference. It does not address **claims of work not performed**. These are different invariants: the first is about how a position forms, the second is about whether an asserted fact has a record behind it. The failure that actually occurred on 31 August 2026 was the second kind. |
| **Affected invariants** | `00-charter.md` §6: a provider reporting success is not completion; an unknown consequential outcome is unverified, not successful; no interface displays a state the records do not support (invariant 29, extended to error display 31 Aug 2026). |
| **What is known** | The trap-question doctrine makes *retrieval* honest about approvals that never happened; the typed `execution_events` query answers "does any acceptance exist in this conversation" deterministically. Neither examines an outbound claim before it is sent. |
| **Current mitigation / detection** | **Lord Armand noticing, which is not a mechanism.** Secondary: the trap suite (retrieval side) and the typed acceptance queries. |
| **Why not being solved now** | The proposed deterministic pre-send check was rejected on recorded facts about Layer 0: no completion state is captured (*execution ≠ completion* is Layer 4 machinery); no attachment table exists; `execution_events.subject` is free text, so matching a claim to a subject is interpretation rather than determinism; and a check consulting `deliberations` for approval would violate the standing rule that recorded enthusiasm or `agreed_from_start` is never reported as approval. |
| **Review checkpoints** | **Message revision/retraction** (claims about what was said) · **Attachment substrate and image vision** (claims about what she received and perceived) · **Layer 4** (claims of execution and completion). |
| **Responsible layer / WP** | The post-gate core-loop packages above, then Layer 4. |
| **Closure condition** | A remedy exists, demonstrated, that is honest about what the records can actually support — not closed because its first remedy failed. |
| **Last reviewed** | 1 September 2026 (schema migration; substance unchanged). |

---

## OP-2 — The ideas enthusiasm-is-not-approval rule is enforced only by absence

| Field | |
|---|---|
| **Problem ID** | OP-2 |
| **Status** | **Open. Vacuously safe.** |
| **Statement** | `04-layer-0.md` §2.4 rules that `ideas.lifecycle_state = 'approved'` is never inferred from enthusiasm — and today that rule is enforced by nothing but the absence of any writer: no application code can write `ideas` or `idea_state_changes` at all, so no test exercises the promotion because no path exists. Covered-by-absence is the "looks covered" failure mode: nothing forces the negative fixture to arrive when the writer eventually does. |
| **Affected invariants** | `04-layer-0.md` §2.4 (both binding rules); the trap-question doctrine; `02-partner-systems.md` §2.1. |
| **What is known** | The same rule is genuinely tested at every surface that has a code path: execution_events reaction-only records, deliberations `agreed_from_start`, retrieval framing, and the 0009 UPDATE refusal. |
| **Current mitigation / detection** | Absence of a writer. Detection: this entry. |
| **Why not being solved now** | Ruled 1 September 2026: a test against a nonexistent writer proves nothing. The obligation binds to the writer, not to now. |
| **Review checkpoints** | **Any work package that first writes `ideas.lifecycle_state` or `idea_state_changes`.** |
| **Responsible layer / WP** | The work package that introduces the ideas writer, whichever it is. |
| **Closure condition** | That work package ships a negative acceptance case proving enthusiasm alone cannot produce `approved` — recorded evidence (a reaction, a deliberation, enthusiastic prose) with the approved count still zero. |
| **Last reviewed** | 1 September 2026. |

---

## OP-3 — Message-channel context composition is not exactly pinned

| Field | |
|---|---|
| **Problem ID** | OP-3 |
| **Status** | **Open. Partially covered.** |
| **Statement** | The `system` channel is pinned byte-exact by existing tests (`request.system == persona.content`, `persona_occurrences == 1`, adapters' `sent_system` asserted at every call site), so permanent injection of accumulated books — or anything else — into the governance channel fails today. The message channel is asserted piecewise (envelope excerpt count equals recall count; forged content stays one string; the current turn is last) but no test asserts the request contains *only* the recall envelope plus conversation turns, so a future non-conversation message block would not by itself fail an assertion. |
| **Affected invariants** | `02-partner-systems.md` §2.4 (retrieval, not permanent injection — the authoritative side, per the 1 September 2026 amendment); WP-0.5 assembly doctrine. |
| **What is known** | No books mechanism exists in any code path; the danger is future, not current. |
| **Current mitigation / detection** | The system-channel byte pins, plus this entry. |
| **Why not being solved now** | Ruled 1 September 2026: an exact-composition test today asserts the absence of a nonexistent feature. It becomes meaningful when the first legitimate non-conversation context type arrives. |
| **Review checkpoints** | **The attachment substrate** — the first legitimate non-conversation context type. |
| **Responsible layer / WP** | The attachment-substrate work package (post-gate order item 2). |
| **Closure condition** | An exact-composition assertion lands with the substrate: the assembled request contains exactly the enumerated parts and nothing else, so any later addition must name itself in the test. |
| **Last reviewed** | 1 September 2026. |
