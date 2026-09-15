# OpenAI cache-boundary proof, second authorisation — PASSED, 14 September 2026

Owner-authorised (ruling of 14 September 2026, §10; a new $0.20 authorisation after the stopped proof). Run at 18:31 CDT by the self-contained `harness_cache_proof.py` on `val_test`, through `candidate_gateway_for_scratch_store`, `gpt-5-6-sol-medium`, persona v1.8 (digest `1608715f…`), no House material, no candidate blind call (guarded, never reached), three ordinary turns 0.0 s, 4.7 s and 10.2 s apart. Code at `f196b6b` (CI green). Raw output: `result.json`.

**Spend: $0.062433** of $0.20 (Sol $0.057817; classification $0.004616).

## Cap behaviour

No command-line figure. The harness computes one internal Sol-call maximum from the fixed proof shape — the measured largest cold primer input of 7,172 tokens plus a 1,500-token margin, all priced as written at $5/M, plus the 200-token output ceiling at $20/M = **$0.04736** — and checks, before every paid call, cumulative actual spend plus that maximum (or the ledger's own bound for a classification call) ≤ $0.20. Every check passed; the ledger's byte-based production bound ($0.16 per Sol call) was reserved as usual but not used as the cap predicate.

## The three turns

| | T1 primer | T2 short | T3 short |
|---|---|---|---|
| Classification (Haiku, normal route) | `not_consequential`, $0.002871 | `not_consequential`, $0.000875 | `not_consequential`, $0.000870 |
| Total input | 7,172 | 7,211 | 7,248 |
| Ordinary uncached | 3 | 3 | 3 |
| Cache-read | **0** | **4,821** | **6,694** |
| Cache-write | 7,169 | 2,387 | 551 |
| Output / reasoning | 58 / 42 | 60 / 42 | 14 / 0 |
| First generated text | 2,709 ms | 4,211 ms | 1,762 ms |
| Total latency | 3,223 ms | 4,649 ms | 2,229 ms |
| Terminal | complete | complete | complete |
| Sol cost | $0.037017 | $0.015075 | $0.005725 |
| Exchange cost | $0.039888 | $0.015950 | $0.006595 |
| Answer | "I've noted this reference for the present conversation." | "Crate 3 is used to count spare lantern glass." | "The handcart is checked at the harbour gate." |

## Logical versus physical boundary, as transmitted (non-mutating observers)

| Turn | Core logical boundary | Adapter physical boundary | Transmitted items (role / block / marked / chars) | Implicit mode |
|---|---|---|---|---|
| T1 | none (first turn) | none | user string 2,014 (envelope); user string 6,659 (primer) | kept |
| T2 | index 1, Val's reply (assistant) | **index 0, the primer (user)** | **user `input_text` marked 6,659**; assistant string 55; user string 2,019 (envelope); user string 68 | kept |
| T3 | index 3, Val's reply (assistant) | **index 2, the T2 question (user)** | user string 6,659; assistant string 55; **user `input_text` marked 68**; assistant string 45; user string 2,019 (envelope); user string 65 | kept |

Assistant items were transmitted as plain strings on every turn; no assistant block carried a marker; the previously observed HTTP 400 did not recur.

## Success criteria (§13)

- **T1:** the cold primer succeeded — 7,169 written. ✓
- **T2:** accepted; the 400 is gone; the assistant reply is a valid assistant item; the explicit marker sits on the nearest preceding user message (the primer). ✓ Cached reads were the persona only (4,821): T1's user prefix was **not** reusable on T2, because a first turn's request is [envelope, primer] while T2's is [primer, …] — the first item differs, so no cached breakpoint from T1 lies on T2's prefix. The criterion was conditional on that prefix being reused; it was not, and the reason is structural and recorded.
- **T3:** the logical boundary advanced (1 → 3) and the physical marker advanced with it (0 → 2); accepted; **cached reads 6,694 = the persona (4,821) + the primer up to T2's explicit marker (1,873)** — retained-history reuse beyond the persona baseline, from provider usage. ✓
- **Growth:** the reusable prefix grew from 4,821 (T2) to 6,694 (T3), and T3's marker on the T2 question means a fourth turn could read persona + primer + reply + question. ✓

## Measures the ruling asked for

- Persona-only baseline: **4,821** tokens.
- T2 reusable-history increment above the baseline: **0** (structural, above).
- T3 reusable-history increment above the baseline: **+1,873** tokens (39 % more than the persona alone).
- Reusable prefix grew: **yes**.
- T3 input cost $0.005445 (3 uncached, 551 written, 6,694 read). Under the Stage B pattern — persona read, everything else written — the same input would have cost ≈ $0.014 (2,424 written); as a fresh cold write ≈ $0.036. **Savings ≈ 61 % against the Stage B pattern and ≈ 85 % against a cold write, on this small thread.** On a long thread the saving scales with the history, which is what the Stage B L1 loss was.

## What this does not claim

Val's most recent reply is still written each turn (it cannot carry a marker), and the first turn's request shape means the primer is written twice (T1 cold, then again at T2 as the marked item's prefix). Neither affects the correction's purpose: from the second turn on, the growing history is read, not re-written.
