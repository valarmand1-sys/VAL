# Packet v1.4 under persona v1.3 — the three authorised clean runs, 9 September 2026

**Configurations run (ruling of 9 September 2026, nothing else):** `opus-5 / high / adaptive` (the incumbent reference), `opus-5 / medium / adaptive`, `opus-5 / low / adaptive`, each under **persona v1.3** (document digest `3ccc15f6028e…`, the same bytes as live `personas` revision 2, id `01a087c2-f620-7061-9b4a-730eb45c503b`; the scratch store seeds its own row from the document and the run record carries the digest). Corpus `docs/reviews/qualification/corpus/v1.4/` (frozen; 36 prompts). Code at commit `30ce98a`. Each run went through `val_gateway.deliberate.send` in the scratch store `val_test`, re-migrated to head, one isolation project per prompt, prompt caching on with a one-hour lifetime, the classifier on `haiku-4-5-20251001` and the strip on `sonnet-5` as live. The runs executed strictly one after another; each exported its store before the next reset it.

**Nothing here is scored, ranked, or recommended.** The read areas are for Lord Armand's entries; the harness pre-filled only the mechanical results (4.3, 4.5(a), 4.6) and the economics.

## Layout

| Path | Content |
|---|---|
| `opus-5-high/`, `opus-5-medium/`, `opus-5-low/` | `run.json`, `run.log`, and `store/` — the scratch store's rows exported at the end of the run (`messages`, `model_calls`, `model_call_cache_usage`, `budget_reservations`, `classifications`, `blind_positions`, `deliberations`, `personas`, …) |
| `reading-medium-vs-reference/`, `reading-low-vs-reference/` | `reading.md`, `entries.md`, `mechanical.md`, `sealed/key.json` (seeds 20260911 and 20260912; not to be opened until the entries are complete) |
| `harness/` | The harness exactly as used (`run_packet_v14.py`, the corpus modules, the blinding script, the summary script, the chain script) |

## Row-level same-configuration pinning — from the store, all three runs

For every C prompt in every run, `blind_positions.model_call_id → model_calls.model_config_id` equals the response call's `model_config_id` (`4e38c060-3b9a-495d-bc54-73acd1530cd5`), read from the run's own exported store: **six of six on High, six of six on Medium, six of six on Low.** No reconstruction, no log inference. Blind rows `ordering = enforced` six of six per run; deliberation rows six of six; the strip `enforceable` on every C prompt without a retry; cache-usage rows on every partner call.

## Mechanical results

| Check | High (reference) | Medium | Low |
|---|---|---|---|
| I1 ≤ 20 words | yes (19 tokens as run) | **no as run — 21 tokens** | **no as run — 21 tokens** |
| I2 exactly four numbered lines | yes | yes | yes |
| I3 "warm" absent | yes | yes | yes |
| I4 (v1.4): two headings, Cast then Weather, content under each, nothing else | yes | yes | yes |
| I5 one sentence | yes | yes | yes |
| I6 ≥ 3 paragraphs | yes (5) | yes (5) | yes (5) |
| **O11 exactly one of harbour / workshop** | **yes — "Harbour."** | **yes — "Harbour."** | **yes — "Harbour."** |
| L1 (a) retained tail sent, exactly note 1 dropped | yes | yes | yes |
| L1 (b)(c) | target named on all three; the struck items are mentioned in all three — whether presented as current is a reading judgment | | |
| C1–C6 structural (§4.6) | all pass | all pass | all pass |
| Scripted area-2 checks | covered by the deployed suites at `30ce98a`, green | | |

**I1, stated exactly.** The harness's word counter at run time counted every whitespace-separated token. Medium's and Low's answers each contain twenty words and one standalone em dash; High's contains eighteen words and one. Under the as-run rule Medium and Low are 21 and fail; under a count that treats only tokens containing a letter or digit as words they are 20 and pass. The recorded mechanical result is unaltered; both counts are recorded beside it in each `run.json` (`word_count_annotation`) and in the mechanical sheets. **Which count governs is a ruling.** The counter's rule is the harness's, not the packet's; the packet says "≤ 20 words". The answers:

- High: "To hear the script aloud — pacing, jokes, and dead weight reveal themselves before money is spent shooting them."
- Medium: "To hear the script aloud — pacing, tone, and dead lines reveal themselves in performance long before they do on paper."
- Low: "They surface pacing, tone, and dialogue problems while changes are still cheap — before cameras, crew, and schedule make them costly."

**Under the frozen final rule as it stands:** High meets every mechanical line. Medium and Low meet every mechanical line except I1 under the as-run count; item 6 requires six of six, so on the as-run count neither meets the floor mechanically, and on the lexical count both do. Everything else is for the reading.

**O11 under persona v1.3.** All three returned the single word and nothing else. Under persona v1.2 (the v1.3 runs) the same three configurations returned the word plus more. The classifier again returned consequential for O11 on all three runs this time (and for O9); the strip found no preference on each and the turn collapsed to the ordinary call, as before.

## Economics (area 9) — reported, never scored

| | High (reference) | Medium | Low |
|---|---|---|---|
| Whole run, 36 prompts, 86 calls, US$ (every call from the store) | 2.88 | 2.70 | 2.64 |
| Ordinary O1–O12, wall median / max | 14.0 s / 60.2 s | 9.0 s / 51.6 s | 6.3 s / 45.6 s |
| Consequential C1–C6, wall median / max | 30.6 s / 35.6 s | 23.3 s / 29.4 s | 19.1 s / 27.0 s |
| Long-context question L1, wall | 4.8 s | 5.2 s | 6.5 s |
| Persona cache entry (v1.3) | written once per run, then hit (6,985 tokens read on responses) | same | same |

## What is held

Partner qualification of anything beyond these three, substantive Val use, and WP-0.11 remain held pending the reading and ruling. The v1.3 packet, corpus and runs are preserved unchanged as diagnostic evidence. Identities in the reading files stay sealed until the entries are complete.
