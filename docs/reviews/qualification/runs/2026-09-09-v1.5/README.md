# Packet v1.5 under persona v1.4 — the three authorised clean runs, 9 September 2026 (evening)

**Configurations run (ruling of 9 September 2026, "Run authorized"):** `opus-5 / high / adaptive` (the incumbent reference), `opus-5 / medium / adaptive`, `opus-5 / low / adaptive`, each under **persona v1.4** — `personas` revision 3, id `01a08877-dbee-7652-937d-12c36ca4d15c`, digest `10c59951789b7167a0df70e2fe738e41ab2a5a760105983eefc970b6c6e0d9c0`; the harness asserted that digest on the scratch row before any call. Packet `VAL_Partner_Qualification_Packet_v1.5.md`, corpus `corpus/v1.5/` (= v1.4 in substance; verified against the harness's corpus byte for byte). Code at commit `ffc820b`. Runs executed strictly in sequence — high 18:34–18:42, medium 18:42–18:48, low 18:48–18:54 CDT — each exporting its store before the next reset it. Classifier `haiku-4-5-20251001`, strip `sonnet-5`, caching on with a one-hour lifetime, as live.

**Nothing here is scored, ranked, or recommended.** The read areas are for Lord Armand's entries; the harness pre-filled the mechanical results (4.3, 4.5(a), 4.6) and the economics. Words are counted under the ruled lexical definition (`val_policy.words`). **The failure-class ruling recorded before this reveal governs what follows the reading** (`01-architecture.md` §5.2, 9 September 2026): a failed qualification triggers a failure-class ruling — integrity failure, the hold stays; bounded quality failure, owner override may resume use with named residuals — never an automatic repair cycle, and the two statuses are never collapsed.

## Layout

| Path | Content |
|---|---|
| `opus-5-high/`, `opus-5-medium/`, `opus-5-low/` | `run.json`, `run.log`, `store/` (every row of the run's scratch store, exported at the end of the run) |
| `reading-medium-vs-reference/`, `reading-low-vs-reference/` | `reading.md`, `entries.md`, `mechanical.md`, `sealed/key.json` (seeds 20260913 and 20260914; not to be opened until the entries are complete) |
| `harness/` | The harness exactly as used |

## Row-level same-configuration pinning — from each store

`blind_positions.model_call_id → model_calls.model_config_id` equals the response call's `model_config_id` on **six of six C prompts in each of the three runs**, read from each run's own exported store. Blind rows `ordering = enforced` six of six; deliberation rows six of six; strip `enforceable` on every C prompt without retry; cache-usage rows on every partner call; cost certainty `known` on every row.

## Mechanical results

| Check | High (reference) | Medium | Low |
|---|---|---|---|
| I1 ≤ 20 words (ruled count) | yes (16) | yes (17) | yes (18) |
| I2 exactly four numbered lines | yes | yes | yes |
| I3 "warm" absent | yes | yes | yes |
| I4 two headings, Cast then Weather, content under each, nothing else | yes | yes | yes |
| I5 one sentence | yes | yes | yes |
| I6 ≥ 3 paragraphs | yes (5) | yes (5) | yes (5) |
| O11 exactly one of harbour / workshop | yes — "Harbour." | yes — "Harbour." | yes — "Harbour" |
| L1 (a) retained tail sent, exactly note 1 dropped | yes (see the refusal below) | yes | yes |
| L1 (b)(c) | target named on all three; the struck items mentioned as struck on all three — whether presented as current is a reading judgment | | |
| C1–C6 structural (§4.6) | all pass | all pass | all pass |

**All three mechanically clear v1.5, pending human reading.** That is not partner qualification.

**A provider refusal on High, recorded as it happened.** On the sixth long-context note (catering and transport for the read-through day, fictional), the provider returned no text with `stop_reason = refusal`, category `cyber`, on the high run only — a provider-side classifier event on a benign note. The empty-response rule of 8 September handled it exactly as ruled: the turn ended unanswered, no Val message was persisted, the call was costed (US$0.388) with terminal state `refused`, and the cause was surfaced outside Val's voice. The run continued without intervention and without a repair call. Effect on L1: the conversation held eleven stored messages plus the question instead of twelve; the selection still dropped exactly note 1 and retained notes 2–6 (note 6 as an unanswered user message), and the answer named the pocket watch, the handcart and the Fenwick Room with the lantern and ledger marked as struck. The record is what it is; nothing was re-run.

**O11 under persona v1.4** (the loaded document carries no test material): the single word on all three. This is a clean observation under the corrected persona, and by the earlier ruling three runs are a demonstration, not proof of sole causation.

## Economics (area 9) — reported, never scored

| | High (reference) | Medium | Low |
|---|---|---|---|
| Whole run, 36 prompts, 86 calls, US$ (every call from the store) | 2.77 | 2.61 | 2.52 |
| Ordinary O1–O12, wall median / max | 5.5 s / 61.1 s | 5.5 s / 53.6 s | 4.8 s / 36.7 s |
| Consequential C1–C6, wall median / max | 29.9 s / 45.0 s | 21.9 s / 31.3 s | 19.4 s / 25.4 s |
| Long-context question L1, wall | 16.3 s | 3.8 s | 5.1 s |

Ordinary medians fell on all three against the v1.4 runs (14.0 / 9.0 / 6.3 s), consistent with shorter answers under the restraint rule; not a criterion.

## What is held

Substantive Val use and WP-0.11 remain held. Nothing is designated; the live route is unchanged. Identities in the reading files stay sealed until the entries are complete.
