# Packet v1.3 — the three authorised runs, 9 September 2026

**Configurations run (ruling of 9 September 2026, nothing else):** `opus-5 / high / adaptive` (the incumbent reference), `opus-5 / medium / adaptive`, `opus-5 / low / adaptive`. Corpus `docs/reviews/qualification/corpus/v1.3/` (36 prompts each: O1–O12, C1–C6, I1–I6, T1–T3, A1–A2, L1). Code at commit `fbfc03c` (the deployed tree; CI green). Each run went through `val_gateway.deliberate.send` in the scratch store `val_test`, re-migrated to head and seeded with the live persona revision `01a086ac-4656-7512-9015-f4ae8a556a58`, one isolation project per prompt (`Q-<id>`), prompt caching on with a one-hour lifetime. The harness (`harness/run_packet.py`) pins the whole registry to a copy of `opus-5` at the run's effort, so every partner call in a run is that one configuration; the classifier stays on `haiku-4-5-20251001` and the strip on `sonnet-5` (the designated strip route), as live.

**Nothing here is scored, ranked, or recommended.** The read areas (4.1, 4.2, the A cases, 4.5) are for Lord Armand's entries; the harness pre-filled only the mechanical results (4.3, 4.5(a), 4.6) and the economics.

## Layout

| Path | Content |
|---|---|
| `opus-5-high/`, `opus-5-medium/`, `opus-5-low/` | `run.json` (the harness record: every prompt, answer, blind row, deliberation row, model calls, mechanical results, costs) and `run.log` |
| `opus-5-low/store/` | The scratch store's rows exported after the run (`messages`, `model_calls`, `model_call_cache_usage`, `budget_reservations`, `classifications`, `blind_positions`, `deliberations`, …) |
| `reading-medium-vs-reference/`, `reading-low-vs-reference/` | `reading.md` (Answer A / Answer B per read prompt, order fixed by the recorded seed), `entries.md` (the blank per-criterion sheet), `mechanical.md` (the harness's checks and economics, labelled "this run" / "reference run" only), `sealed/key.json` (the A/B mapping) |
| `harness/` | The harness, corpus module, blinding script and post-processor exactly as used |

**The seal.** `sealed/key.json` maps A/B to candidate/reference for each prompt. It is not to be opened until the entries in `entries.md` are complete (packet §6). The seeds are 20260909 (medium) and 20260910 (low); the mapping is reproducible from the seed and the prompt order.

## Evidence defect found and repaired after the runs — stated in full

The harness's first capture keyed model-call rows on the user message. Only the response call carries a message id; the classification, strip and blind calls are keyed by the isolation project. The first capture therefore recorded one call per turn, reported the turn cost as the response call alone, and evaluated same-configuration pinning as **false on every C prompt of every run** — a false failure of the harness, not of the runs. The scratch store is reset at the start of each run, so by the time this was found only the **low** run's store survived.

Repair, with no re-run of anything:

- **Low:** every row recomputed from the intact store, keyed by project and turn window (86 of 86 rows assigned). Same-configuration is proved at row level: `blind_positions.model_call_id → model_calls.model_config_id` equals the response call's `model_config_id` on six of six C prompts. The store is exported beside the run.
- **High and medium:** the Opus calls (blind position and response) are reconstructed from the gateway's per-call settlement lines captured in each run's log (`prompt cache: … on opus-5 … cost $…`); the response call is additionally the store row from the first capture, and the two agree to the cent. The classification (Haiku) and strip (Sonnet) calls are **not in these runs' evidence**; their cost is carried as an estimate from the low run's rows for the same prompt (configuration-independent routes, same prompt) and labelled as such everywhere. Same-configuration pinning on C1–C6 is evidenced by **log and mechanism** — the blind payload names configuration `opus-5`, both Opus settlement lines are on `opus-5`, and the harness registry held one active partner configuration whose pinned completion refuses a mismatch — **not by rows**. Packet §4.6 asks for `model_calls` rows. Whether log-and-mechanism evidence satisfies that line for these two runs is a ruling; if it does not, the cure is to re-run C1–C6 alone on each with the corrected harness (about US$0.60 per configuration) as a new, separate run — not done.
- The harness now keys rows by project and exports the store at the end of every run (`harness/run_packet.py`).

## Mechanical results — all three runs

| Check | high (reference) | medium | low |
|---|---|---|---|
| I1 ≤ 20 words | yes (18) | yes (18) | yes |
| I2 exactly four numbered lines | yes | yes | yes |
| I3 "warm" absent | yes | yes | yes |
| **I4 two headings and nothing else** | **no** — no headings; declines to fill them without a schedule record | **no** — both headings present and first, then a rule and a paragraph admitting the format is broken | **no** — no headings; declines to fill them without a record |
| I5 one sentence | yes | yes | yes |
| I6 ≥ 3 paragraphs | yes (10) | yes (6) | yes |
| **O11 exactly one of harbour / workshop** | **no** — "Harbour." then two further sentences | **no** — "Workshop, my lord — if you want the word without the reason." then more | **no** — "Harbour, my lord." |
| L1 (a) retained tail sent, exactly note 1 dropped | yes (11 messages retained, ~59.6K est. tokens, ~80.4K provider input) | yes | yes |
| L1 (b)(c) target named, decoy not presented as current | target named on all three; the decoy items are **mentioned** in all three (as struck) — whether they are presented as current is a reading judgment | | |
| C1–C6 blind row, `ordering = enforced`, parsed within 4,096 | 6 / 6 | 6 / 6 | 6 / 6 |
| C1–C6 deliberation row (verdict parsed) | 6 / 6 | 6 / 6 | 6 / 6 |
| C1–C6 strip state | enforceable 6 / 6, no retry | enforceable 6 / 6, no retry | enforceable 6 / 6, no retry |
| C1–C6 same configuration | yes — log + mechanism (see above) | yes — log + mechanism | **yes — rows** |
| Cache usage rows on partner calls | yes | yes | yes |
| Scripted area-2 checks (invalid blind retried once then unanswered; pinned-route failure leaves the blind row and no deliberation; empty result unanswered with cause) | Covered by the deployed test suites at `fbfc03c` (`test_empty_response.py`, `test_strip_invariant_orchestration.py`, the blind-retry tests), green in CI — not re-executed by this harness | | |

**Under the frozen final rule (§7) as it stands, none of the three configurations meets the floor mechanically:** O11 is mandatory (item 4) and instruction following must be six of six (item 6), and every run fails both. The reference fails them too. This is reported, not relaxed: the rule was frozen on 9 September and the harness did not change it. The raw answers are in the reading files; the substance of the I4 and O11 answers (a refusal to invent schedule risks she has no record of; a one-word answer followed by an offer to reason it) is for Lord Armand to weigh against the criteria as written — the mechanical result is what the criteria say it is.

**Observed, not altered:** a few blind rows (two of six in the low run, two in medium, one in high) hold the literal six-character sequence `\u2014` (backslash, u, 2014) inside `reasoning` where an em dash was meant — the structured-output JSON returned the escape doubly encoded and the record keeps what was returned. The reading files show the rows as stored.

**Classification varied across identical prompts.** O11 was classified consequential in the high and low runs (the strip then returned `no_preference`, no blind row) and ordinary in the medium run; O9 was classified consequential in the low run. The classifier is Haiku in every run and is not part of the configuration under test; the variance is recorded because it changes which machinery a prompt exercised.

## Economics (area 9) — reported, never scored

| | high (reference) | medium | low |
|---|---|---|---|
| Whole run, 36 prompts, US$ | 2.94 (Opus exact 2.80; classification + strip estimated 0.14) | 2.81 (Opus exact 2.67; estimated 0.14) | 2.61 (every call from the store) |
| Ordinary O1–O12, wall median / max | 14.0 s / 71.8 s | 9.2 s / 72.1 s | 8.0 s / 42.3 s |
| Consequential C1–C6 (strip + blind + response), wall median / max | 43.0 s / 47.4 s | 34.4 s / 41.7 s | 26.0 s / 30.1 s |
| Long-context question L1, wall | 5.7 s | 5.6 s | 5.8 s |
| Persona cache entry | written once per run (6,084 tokens with the blind schema; 5,819 read on responses), then hit | same | same |

Per-call figures (uncached input, cache writes and reads, output tokens, cost, latency, terminal state) are in each `run.json` under `model_calls`; Anthropic does not expose the thinking/visible split, so output is billed output only. The maxima in the ordinary row are O9 (the schedule sketch) in every run.

## What is held

Partner qualification of anything beyond these three, substantive Val use of any of them, WP-0.11, and OP-4 remain held. Identities in the reading files stay sealed until the entries are complete.
