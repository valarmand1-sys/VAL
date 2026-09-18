## How to read this packet

Every answer marked **ORIGINAL — EXACT PARITY** or **CORRECTED RERUN — EXACT PARITY** is an answer for the owner's final review, and every one of them has exact preflight/server prompt-token parity. Four multi-turn answers of the first run (F1 T2, F1 T3, F2 T2, F2 T3) are marked **QUARANTINED** and shown in a quoted block as historical evidence only; the corrected rerun beside each is the answer for review. Engineer text appears only under the label **PROVISIONAL ENGINEER NOTES**, separated from the raw answers; it is a reading, not a score, and no PASS, FAIL, comparison or admission verdict is made anywhere in this packet.

**Primary qualitative review points:** A1, A2, D1, D2, E1, E2, F1, F2 — evidence-bound continuity, persona conduct, instruction following, supplied-context fidelity, arithmetic and date discipline, capability and system-state honesty, correction preservation, authorship and identity discipline, planning quality, and whether narrated stage directions (A2, E2) and the D1/E2/F2 constraint errors read as isolated slips or as a broader pattern. B1, B2, C1, C2 follow in order.

**Record-state material on every call.** Each conversation was opened unassigned on the scratch store, so every call carried the Core record-state envelope as a user message immediately before the user's turn: no prior record, no project volumes, `capability_state: {books: unavailable}`, plus the current local time; the persona v1.8 travelled whole as the system message. The envelope and the user's turn were joined into one wire message by the accepted local canonicalization. F2's supplied memo is the first user turn of F2, shown in full.

## Qualification provenance

| | |
|---|---|
| Artifact | `lmstudio-community/Mistral-Small-3.2-24B-Instruct-2506-MLX-8bit` (every shard SHA-256-verified against the publisher) |
| Canonical identity | `mistral-small-3.2-24b-instruct-2506-mlx` (LM Studio's own listings) |
| Architecture | `mistral3`, 24B dense, MLX 8-bit |
| Configured context | 32,768 |
| Actual runtime context | 36,352 — a Mistral-specific accepted MLX substitution, not owner-selected |
| Sampling | temperature 0.15, the upstream publisher value, explicitly transmitted on every call; no other Mistral-specific sampling override |
| Reasoning | `ReasoningEffort.NOT_APPLICABLE`; no reasoning parameter sent; no reasoning tokens observed on any call |
| Benchmark | frozen commit `60b65b7`, twelve tasks, sixteen calls, unmodified |
| Persona | v1.8, whole, as the system message |
| Runtime | LM Studio 0.4.24+1, MLX engine 1.11.0; SDK 1.6.0b1 for inspection only |
| Local provider/API spend | $0 (every call $0 KNOWN); cloud $0 |
| Production route | unchanged; Sol remains the production Partner |
| Admission state | NOT_ADMITTED, pending owner/VAL qualitative review |

## Serving-contract status for the evidence reviewed here

- **A.** Adjacent same-role (envelope + user turn) ingress seam: fixed by the shared local canonicalization (17 September 2026).
- **B.** Historical-assistant end-of-sequence seam: fixed using the SDK's documented `omitEosToken` rendering behaviour (18 September 2026).
- **C.** GPT-OSS Harmony regression under both fixes: exact.
- **D.** The four affected Mistral reruns: exact.
- **E.** The qualification harness now hard-stops on any nonzero or missing parity.

## Comparison context with GPT-OSS Stage A (accepted evidence only)

From the accepted first-run notes, Mistral appears to have avoided three GPT-OSS failures on the same frozen tasks: A1 (no invented House history), E1 (clean boundary handling), and D2 (arithmetic and date handling). No new comparison score is made and no winner is chosen. **COMPARABILITY NOTE:** GPT-OSS Stage A ran with no pinned sampling configuration; Mistral Stage A ran with the upstream temperature explicitly pinned to 0.15. Same frozen tasks and qualification structure, not an identical sampling state.
