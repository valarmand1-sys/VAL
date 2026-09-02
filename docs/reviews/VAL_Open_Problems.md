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
