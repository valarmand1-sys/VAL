# COLD → WARM measurement pair on GPT-5.6 Sol — 14 September 2026

Owner-authorised 14 September 2026: two ordinary exchanges in one fresh scratch conversation, $0.45 maximum for the pair, cumulative spend checked before the second partner call, the consequential path refused by a harness guard on the lane's blind method (never reached), no retry. Run by `harness_pair.py` at 15:27 CDT on `val_test` (dropped and re-migrated to `0020` once, before turn 1; not touched between the turns), through `candidate_gateway_for_scratch_store` exactly as built, `gpt-5-6-sol-medium`, persona v1.8 asserted (digest `1608715f…`). No House material. Raw output in `result.json`.

**Pair total: $0.038028** of $0.45 authorised (≈ $0.06–0.08 expected). Ordinary-use measurement only: not qualification, not admission; Sol remains `NOT_ADMITTED`, no profile, no fallback.

## The two exchanges

| | COLD (turn 1) | WARM (turn 2, 5.7 s later, same conversation) |
|---|---|---|
| Prompt | "Good morning, Val. Please tell me the current time by the house's clock in one brief sentence." | the five-job ordering problem, verbatim as authorised |
| Classification (Haiku, normal route) | `not_consequential`, `retrieval_lookup_or_search`; $0.000875; 1,890 ms | `not_consequential`, `execution_of_decided_task`; $0.000911; 926 ms |
| Val's answer | "Good afternoon, my lord. The house's clock reads 3:27 p.m. CDT." | below, verbatim |

## The two Sol calls, measured

| Measure | COLD | WARM |
|---|---|---|
| Total input tokens | **5,324** | **5,365** |
| Uncached input | 3 | 3 |
| Cache-write tokens | **5,321** | **541** |
| Cached-read tokens | **0** | **4,821** |
| Output tokens | 24 | **225** |
| Reasoning tokens (provider-reported) | 0 | **115** |
| Reasoning item present | no | **yes** |
| Visible output | 63 characters | 332 characters (≈ 110 visible tokens) |
| First generated text at the Core boundary | **3,228 ms** | **3,525 ms** |
| Total provider latency | 3,701 ms | 4,749 ms |
| Settled response cost | **$0.027097** = 3×$4 + 5,321×$5 + 24×$20 per M | **$0.009145** = 3×$4 + 541×$5 + 4,821×$0.40 + 225×$20 per M |
| Classification cost | $0.000875 | $0.000911 |
| Full exchange cost | **$0.027972** | **$0.010056** |
| Reservation maximum | $0.206520 | $0.207255 |
| Terminal state | `complete` | `complete` |

Cumulative-spend check before turn 2: $0.027972 settled + $0.214589 conservative remaining bound = $0.242561 ≤ $0.45, admitted.

## Cache analysis (provider usage, not timing)

- **Reads: 4,821 tokens.** Of the 5,321 tokens the cold call wrote, **4,821 (90.6%) were reused** on the warm turn.
- **Where the match ends.** The cold request was persona (instructions) → state envelope → primer; the warm request was persona → primer → Val's answer → new state envelope → problem. The first input item differs, so the matching prefix is the instructions block. The persona v1.8 text is therefore **≈ 4,821 tokens on OpenAI's tokenizer** (against ≈ 6,995 derived on the incumbent's). The instrumentation establishes this by arithmetic on the reported figures, not by a provider-stated boundary.
- **Newly written: 541 tokens** — the two history messages, the new state envelope and the problem (the implicit breakpoint at the end of the latest user message).
- **Ordinary uncached input: 3 tokens** on both calls (below OpenAI's rounding of the breakpoint).
- **Dollar value:** reads $0.001928; new writes $0.002705; uncached $0.000012 — warm input $0.004645. Priced as a fresh cold write the same 5,365 tokens would have been $0.026825: **saving $0.022180 (83%)** on the input side.
- **What survives:** the stable persona prefix survives the change of conversation shape; nothing after it does, because nothing after it is byte-identical. On an append-only thread, later turns would also read the history prefix written by the previous turn.

## Reasoning analysis

- COLD (greeting): 0 reasoning tokens of 24 output.
- WARM (five-job ordering): **115 reasoning tokens of 225 output — 51% of billed output**; ≈ 110 visible tokens (332 characters). Medium-effort Sol does reason on a multi-step task, briefly. Reasoning cost on this turn: $0.0023. Observed on one task; not generalised.

## Visible answer, verbatim

> Valid execution orders:
>
> 1. **E → A → B → C → D**
> 2. **E → A → C → B → D**
> 3. **E → C → A → B → D**
>
> **Why no others are possible:**
> E must precede both A and C, so E is first. D must follow both B and C, so D is last. Among A, B, and C, the only remaining constraint is that A precedes B, yielding exactly the three orders above.

**Mechanical comparison** against the expected set {E A B C D, E A C B D, E C A B D} (never sent to the provider): all three present; none omitted; none extra. **The explanation is correct and complete:** E precedes A (stated) and C (stated), so E is first; D follows B and C, so D is last; A before B is the only remaining constraint among A, B, C, which admits exactly ABC, ACB, CAB. The constraints are all accounted for and the exclusion argument is sound.

## Latency

Time to first generated text was 3.2 s cold and 3.5 s warm: the warm figure is not lower because the 115 reasoning tokens precede the first text. Total 3.7 s cold (24 output tokens) and 4.7 s warm (225). The incumbent's measured time to first token on ordinary warm turns of 13 September was 12.7–23.9 s, on turns producing 1,600–2,400 output tokens with thinking; not like for like, recorded for orientation only.

## Governance

Classification on its normal route both turns; Sol used only for the two partner responses; persona whole and attributed on each; record and capability state in each request (the clock answer used it); Core-owned streaming (`streamed = true`, first-text measured at the Core); normalized results; ordinary reservations settled at known cost; both calls under Sol's own id with exchange identity; no fallback; no admission or routing change; the blind guard never reached.
