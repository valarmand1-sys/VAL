# VAL — Open Problems

Problems that are recognised, unsolved, and not currently awaiting a decision.
Distinct from `VAL_Open_Decisions.md`, which holds questions requiring Lord
Armand's ruling: an entry here has no proposal in front of it — its first
remedy may have failed, or none has been designed. An entry leaves this list
by being solved and demonstrated, never by being forgotten.

Created 1 September 2026, at Lord Armand's direction.

---

## 1. Claims of work not performed have no structural counter

**Open. Unsolved. First proposed remedy rejected. Detected by Lord Armand
noticing, which is not a mechanism.**

The structural anti-sycophancy mechanism (`02-partner-systems.md` §4, WP-0.9)
addresses **preference-induced agreement**: a position formed after exposure
to a stated preference. It does not address **claims of work not performed**.
These are different invariants — the first is about how a position forms, the
second is about whether an asserted fact has a record behind it — and the
failure that actually occurred on 31 August 2026 was the second kind.

A deterministic pre-send check was proposed and **rejected**, for reasons that
are themselves recorded facts about Layer 0:

- Layer 0 captures **no completion state** — there is no record a claim of
  "work done" could be verified against, and the charter's own chain
  (*execution ≠ completion*) is Layer 4 machinery.
- There is **no attachment table**; a check "against attachments" checks
  against nothing.
- `execution_events.subject` is **free text**, so matching a claim to a
  subject is interpretation rather than determinism — the check would be a
  model call wearing a checker's name.
- A check consulting `deliberations` for approval would **violate the
  standing rule** that an `agreed_from_start` outcome or recorded enthusiasm
  is never reported as an approval.

What exists today is narrower than the problem: the trap-question doctrine
makes *retrieval* honest about approvals that never happened, and the typed
`execution_events` query answers "does any acceptance exist in this
conversation" deterministically. Neither examines an outbound claim before it
is sent.

The problem is not closed because its first remedy failed. It stays here
until a remedy exists that is honest about what the records can actually
support.
