# Packet v1.6 — the single Medium run under persona v1.4 and the record-state contract, 9 September 2026 (late)

**Configuration run (ruling of 9 September 2026 after the v1.5 reveal — Medium only):** `opus-5 / medium / adaptive`, persona v1.4 (`personas` revision 3, id `01a08877-dbee-7652-937d-12c36ca4d15c`, digest `10c59951789b…`, asserted by the harness on the scratch row before any call), with the prior-record-state contract in place on every response call (`04-layer-0.md` WP-0.7 amendment; the `prior record state` line is present in the log of every one of the 36 prompts). Packet `VAL_Partner_Qualification_Packet_v1.6.md` and corpus `corpus/v1.6/`, frozen as drafted; the harness's corpus verified equal to the frozen file. Code at commit `1050010`. Run 21:58–22:06 CDT; the store exported at the end.

**One configuration, one sheet.** There is no second configuration, so nothing is blinded and no comparison with High is manufactured. `reading-medium/reading.md` carries every read prompt with its answer (blind position, reasoning and recorded outcome on C prompts) and its criterion; `entries.md` is the blank sheet; `mechanical.md` the harness's checks and economics. The harness pre-filled only the mechanical results.

## Layout

| Path | Content |
|---|---|
| `opus-5-medium/` | `run.json`, `run.log`, `store/` (every row of the run's scratch store) |
| `reading-medium/` | `reading.md`, `entries.md`, `mechanical.md` |
| `harness/` | The harness exactly as used, the corpus modules, the single-sheet generator, and the specificity probe |
| `specificity-probe/` | The bounded non-drafting probe ruled alongside this run (its own README) |

## Structural (§4.6) — from the store

Row-level same-configuration pinning **six of six** (`blind_positions.model_call_id → model_calls.model_config_id` equals the response call's, from this run's exported store); blind rows `ordering = enforced` six of six; deliberation rows six of six; strip `enforceable` on every C prompt without retry; cache-usage rows on every partner call; 86 rows, cost certainty `known` on every one.

## Mechanical results

| Check | Result |
|---|---|
| I1 ≤ 20 words (ruled count) | yes (18) |
| I2 exactly four numbered lines | yes |
| I3 "warm" absent | yes |
| I4 two headings, Cast then Weather, content under each, nothing else | yes |
| I5 one sentence | yes |
| I6 ≥ 3 paragraphs | yes (4) |
| O11 exactly one of harbour / workshop | yes — "Harbour." |
| L1 (a) retained tail sent, exactly note 1 dropped | yes (11 retained, ~59.6K est. tokens, ~80.8K provider input) |
| L1 (b)(c) | target named; struck items marked as struck — whether presented as current is a reading judgment |

**Medium mechanically clears v1.6, pending human reading.** That is not partner qualification.

## Observed before the reading, stated without judgment

- **O6 (repaired):** three one-line risks, each drawn from the supplied facts (the principals' travel against the ten o'clock start; the Wednesday-night pages; an overrun at the harbour).
- **O9 (criterion repaired):** a nine-day table with day 5 as the company move, the lead's six days on 1–4 and 6–7, the three lead-free days at the workshop, the move explicitly accounted for; first failure named as the lead's sixth day, with the reason.
- **O2:** "Nothing in the record before me tonight … What would you have me look at?"
- **O4:** the note again opens "We've received the same list three times now" — the same count-in-a-drafted-artifact residual seen in v1.5 and in the record-state regression — and marks the date as a placeholder for him to fill, saying so.

## Economics (area 9) — reported, never scored

| | Medium |
|---|---|
| Whole run, 36 prompts, 86 calls, US$ (every call from the store) | 2.61 |
| Ordinary O1–O12, wall median / max | 5.8 s / 42.6 s |
| Consequential C1–C6, wall median / max | 26.1 s / 28.3 s |
| Long-context question L1, wall | 4.7 s |

## What is held

Substantive Val use, designation and WP-0.11 stay as they are until the reading and the pre-ruled outcome (`01-architecture.md` §5.2, ruling of 9 September 2026 after the v1.5 reveal).
