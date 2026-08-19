# VAL — Cross-Reference and Source-of-Truth Audit

Part A of the 16 August 2026 cleanup. Every item is PASS (already correct),
CORRECTED (changed by this cleanup), or BLOCKED (needs a decision).

Commit after cleanup: `ccc94e3`.

---

## Result

| Item | Subject | Result |
|---|---|---|
| A1 | Charter invariant / version consistency | **PASS** |
| A2 | Persona version consistency | **PASS** |
| A3 | Provider architecture vs provider registry | **CORRECTED** |
| A4 | Layer 0 Restricted-content preflight | **CORRECTED** |
| A5 | Books / volume retrieval semantics | **CORRECTED** |
| A6 | Historical-document isolation | **PASS** |
| A7 | Backup-key threat-model note | **CORRECTED** |
| A8 | Cross-reference audit | **PASS** |

**Nothing is BLOCKED.** No settled decision had to change to make the audit green.

---

## A1 — Charter invariants · PASS

The suspected drift is **not present at repository HEAD**. Measured, not assumed:

- `00-charter.md` §6 defines **exactly 35** invariants, numbered `1..35` with no
  gaps and no repeats. (The file has 40 numbered lines: 35 invariants plus the
  5-entry precedence list in §9.)
- **Every** invariant citation across all six governing documents, the
  implementation, and the tests resolves within `1..35`. Highest cited: 35.
  Out-of-range citations: **zero**.
- Most-cited: 17 (classification before egress) and 24 (budget before the call),
  five times each; then 35 (a backup never restored is not a backup), four times.

The "fewer invariants" version described externally is superseded source material
and is not tracked in this repository. **No canonicalisation was required and
none was performed** — inventing a fix here would have been the error.

---

## A2 — Persona version · PASS

- `docs/baselines/03-persona.md` is **v1.1** at HEAD, titled as such in line 1.
- Its §11 retains the complete v1.0 → v1.1 change log **inside** the current
  document — history preserved without a second file that could be mistaken for
  authority.
- **No separate v1.0 file exists** in the repository.
- The `personas` table exists, is migrated, and is **empty**: WP-0.5 has not
  started, so there is no seed that could disagree with the file. WP-0.5's
  acceptance criteria already require the two-way check (context ↔ active row,
  active row ↔ document at seed time) that keeps them from diverging.

No voice or character text was touched.

---

## A3 — Provider architecture vs registry · CORRECTED

**Was:** §5.3 named the roster inline — "Anthropic, OpenAI, Gemini, plus local" —
which read as architectural law, and nothing distinguished *an adapter exists*
from *this route works*.

**Now:**

- §5.3 states the architectural requirement only, and defers the roster to the
  registry as controlled configuration.
- New **§5.2.1** defines six independent states and names where each is answered:
  supported by architecture · adapter implemented · qualified · eligible for
  Protected · currently enabled · live.
- The registry carries `last_live_call_on`, so *live* is recorded configuration
  rather than prose: `gpt-5-5` = 15 Aug 2026; both Anthropic routes = **null**.
- Two rules stated explicitly: an implemented adapter is not a live provider; and
  nothing in this model weakens Protected eligibility, which remains a separate
  ruling that cost never overrides.

Three tests enforce the distinction (`test_registry.py`).

---

## A4 — Restricted preflight · CORRECTED (a real gap)

**The one substantive implementation finding of this audit.**

**Was:** the gateway refused `Classification.RESTRICTED` — but the classification
is supplied by the *caller*. A caller asserting `PROTECTED` over a message
containing an API key transmitted the key. The structural guarantee of §1.1
covers **routing**, not **content**, and nothing closed that gap.

**Now:** `packages/policy/src/val_policy/restricted.py` reads the content before
any provider is contacted. Every requirement met and tested:

| Requirement | How |
|---|---|
| Executes before cloud transmission | First step of `Gateway.complete`, ahead of eligibility and budget |
| Never uses the receiving model | Pure local regex + Luhn; no network |
| Blocks rather than downgrades | Raises `RESTRICTED_CONTENT`; no reclassification path exists |
| Records the block without a phantom call | Reported to an observer; **no `model_calls` row** — none occurred |
| Clear explanation | Val states what was found, why, and that she will not reclassify it |
| Automated tests | **19** in `test_restricted.py` + 4 at the gateway boundary |
| Never sends silently on failure | Scan errors → block, `"could not complete"` |

Detects: private-key blocks, Anthropic / OpenAI / AWS / GitHub key shapes,
labelled credentials, URLs with inline passwords, SSN-shaped numbers, and
Luhn-valid payment cards. Deliberately small; explicitly **not** the Layer 2
classification system arriving early. Recorded in `04-layer-0.md` §1.1 and as a
WP-0.4 acceptance criterion.

Ordinary creative and project language is tested to pass, because a preflight
that fires on real work gets disabled, and a disabled preflight protects nothing.

---

## A5 — Book retrieval semantics · CORRECTED

Persona §2 and Partner Systems §2.4 described the same mechanism from opposite
ends and could be read as two policies. `02-partner-systems.md` §2.4 now states
one interpretation as five numbered rules: index always fully resident · bounded
summaries to the token budget · full volumes opened deliberately · an opened
volume read as an authored document in order · every citation resolving to a real
record. Technical clarification only; no persona text was altered.

---

## A6 — Historical-document isolation · PASS

No superseded design document, review, proposal, master-source file, old copy, or
prior persona/charter version is tracked in this repository. The only historical
artifact is `docs/ARCHIVE-NOTE.md`, which is itself the isolation mechanism: its
first three lines state that the five baselines are the complete specification
and that everything it lists is superseded and non-authoritative. Nothing was
deleted; nothing needed moving.

---

## A7 — Backup-key threat model · CORRECTED

`docs/BACKUP.md` now records the tradeoff explicitly rather than leaving it
implied: **anything able to read as this operating account can read
`pgbackrest.conf` and decrypt every backup in B2.** The note states plainly that
the paper copies do *not* mitigate this — paper protects against losing the key,
not against someone obtaining it — lists what does limit blast radius (the
bucket-scoped B2 key, 0600 permissions, encryption at rest), names what would
actually reduce it (a low-privilege archiver account, or an HSM-backed key
service), and marks the risk **accepted, current, revisited at the Layer 3
migration**. The original decision stands unchanged.

---

## A8 — Cross-reference audit · PASS

Automated over all six governing documents:

| Checked | Result |
|---|---|
| Referenced document filenames | All resolve |
| Invariant citations | All within 1..35 |
| Layer references | All within 0..5 |
| Work-package references | All within WP-0.1..WP-0.10 |
| Section references | Spot-checked; no dangling |
| Provider statuses | Consistent between §5.2.1, §5.4, and the registry |
| Risk-tier terminology | Consistent (0–4, defined once in the charter) |
| Permission / Approval / Execution / Completion | Used as four distinct states throughout |
| Deferred-capability statements | Consistent across all documents |

**Issues found: none.**
