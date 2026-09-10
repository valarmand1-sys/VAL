# WP-0.11 — live cost and runtime finding, 10 September 2026 — report only

The first two real-use turns after operational authorisation, decomposed from persisted evidence (`messages`, `model_calls`, `model_call_cache_usage`, `classifications`, and the gateway's per-call log lines in `/opt/homebrew/var/log/val/api.log`). Nothing was changed from this finding: routing, effort, recall behaviour, the history budget and the caching arrangement are as they were. The two ruled fixes of the same morning (unassigned new conversations; the clock in the envelope) are separate and are deployed.

## 1. The two turns, from the record

Conversation `01a08c02-1ada-…`, **no project** (created unassigned). Route `opus-5-medium`, persona v1.4, record-state contract present.

| | Turn 1 — "Hello, Val!" | Turn 2 — the correction |
|---|---|---|
| User message persisted | 10:49:03.327 | 11:03:32.458 |
| Val message persisted | 10:49:13.181 | 11:03:42.690 |
| **End-to-end (persisted)** | **9.85 s** | **10.23 s** |
| Classification call (Haiku) | 718 in / 25 out, US$0.000843, 1,626 ms, verdict not consequential | 748 in / 30 out, US$0.000898, 1,266 ms, not consequential |
| Partner call (opus-5-medium) | tokens_in 13,088 / out 429, **US$0.104895**, 8,094 ms | tokens_in 26,137 / out 462, **US$0.116378**, 8,859 ms |
| Cache usage on the partner call | uncached 7,342; **1h write 5,746** (the persona); read 0; outcome `created` | uncached 20,391; write 0; **read 5,746**; outcome `hit` |
| Same-conversation history sent | 0 prior messages (the current one only, 4 est. tokens) | 2 prior messages, 242 est. tokens, retained whole |
| Recalled excerpts admitted | **6** (4,466 est. tokens, 16,067 characters) | **1** (10,830 est. tokens, 38,987 characters) |
| Other calls | none | none |
| Unaccounted latency (UI, network, persistence) | 0.13 s | 0.10 s |

**Interval between the turns, from persisted timestamps: 14 minutes 29 seconds** (10:49:03 → 11:03:32), not five. The persona cache entry (1-hour lifetime) was **reused as expected**: turn 2 read 5,746 tokens at the read rate and wrote nothing.

**Cost decomposition of the partner calls** (registry rates: US$5 / MTok input, $25 output, $10 1h write, $0.50 read):

| Component | Turn 1 | Turn 2 |
|---|---|---|
| Persona cache write (one-off per hour) | 5,746 × $10 = **$0.0575** | — |
| Persona cache read | — | 5,746 × $0.50 = $0.0029 |
| Uncached input (envelope + excerpts + history + message) | 7,342 × $5 = $0.0367 | 20,391 × $5 = **$0.1020** |
| Output (visible + thinking) | 429 × $25 = $0.0107 | 462 × $25 = $0.0116 |
| **Partner total** | **$0.1049** | **$0.1164** |

So turn 1's five cents were mostly the hourly persona write; turn 2's twelve cents were mostly one recalled excerpt.

## 2. The recall — what was selected, and why

Both turns recalled from the **no-project pool**, because the conversation was created with no project: recall in that scope searches every other unassigned conversation. There are four such conversations holding 52 messages; 44 of them belong to one — `01a05b0a-3a4c-…`, "Hello Val! Welcome to House Armand!", 31 August to 3 September — which is where the *Phony Spumoni* pilot draft and its discussion were held, unassigned.

**Turn 1** ("Hello, Val!"): full-text ranking on the words *hello* and *val* put two greetings first (seq 13 "Hello Val. How are you today?", 30 characters; seq 1 "Hello Val! Welcome to House Armand!", 36 characters), then, at lower rank, four longer messages that merely contain "Val": seq 5 (9,581 chars — the canonical-foundation note), seq 25 (4,360 — corrections on the Tony reading), seq 19 (1,691), seq 11 (369). All six fit the 16,000-token recall budget and were admitted, per the ruled selection rule. Provider-attributable input for the excerpts: about 6,000 of the 7,342 uncached tokens (the 3.6-characters-per-token estimate runs about 1.34× low against provider counts on this material), i.e. **about $0.030 of the $0.105**.

**Turn 2** (the greeting correction): the words *morning*, *greeted*, *evening*, *correct* and *Val* ranked the **pilot draft itself** highest (seq 23, 38,987 characters, 10,830 est. tokens — a screenplay contains all of those words), and the rule *always admit the highest-ranked message whole* admitted it; the next candidate (20,923 chars) did not fit the remaining budget, so selection stopped there. Provider-attributable input for that one excerpt: roughly 14,500 of the 20,391 uncached tokens, i.e. **about $0.072 of the $0.116 — some two thirds of the turn**, on a message about the time of day.

**Answer to the question asked:** yes — project-scoped recall is injecting large, lexically-matched but irrelevant prior messages into trivial turns, and it is materially responsible for the cost (about a third of turn 1's partner cost, two thirds of turn 2's) though not for the latency, which is dominated by the partner call's own generation time (8.1 and 8.9 s) with the classifier adding 1.3–1.6 s in series. Two mechanisms produce it: ranking is lexical (PostgreSQL full-text rank on the current message's words, not meaning), and the ruled admission rule admits the top candidate whole regardless of size. **A related consequence of this morning's UI fix, for ruling:** with new conversations unassigned by default, every unassigned conversation is in every other unassigned conversation's recall scope — "no project" is a shared pool, not a clean room. The default is right for keeping stray thoughts out of project scopes; what the no-project pool should recall is a separate question and is not changed here.

## 3. The three questions ruled for measurement (history cost and caching)

Measured on 10 September 2026 with the SDK the adapter uses, `claude-opus-5` at `medium`, persona v1.4 whole in `system` with a 1h breakpoint, an append-only fictional history built from the frozen long-context notes; two consecutive turns per arm at each checkpoint so the second turn could hit the first's prefix. Script and raw usage: `docs/reviews/economics/history-cache-2026-09-10/`. **The measurement itself cost US$7.28** on the Anthropic balance (48 calls, most of them 27K–88K tokens of input).

**Q1 — Is the history prefix cacheable, what invalidates it, can both persona and history hold breakpoints, what does it save?**

Anthropic caches any exact prefix ending at a breakpoint (up to four breakpoints; the system looks back through earlier breakpoints for a hit), so an append-only history is exactly the shape caching is for, and the persona (`system`) and a history breakpoint coexist — arm C proves both being read on one call. Three things invalidate it, and one of them is ours:

1. **Anything that changes before the breakpoint.** Today the record-state envelope is the *first* message and its counts change every turn, so a history breakpoint placed after it never hits: arm B rewrote the whole prefix on every turn at the 2× write rate and cost **twice** the current arrangement ($0.82 versus $0.41 at 64K). Caching history requires the envelope to sit *after* the history (arm C), which is a change to message order, not to content, and is not made here.
2. **The contiguous-tail drop at the 64K budget.** Once a conversation is at the cap, each new turn drops the oldest exchange, the prefix changes at its start, and the entire cached prefix is rewritten at 2×. So history caching pays up to the cap and costs double at it — the cap and the cache work against each other as ruled today.
3. **The one-hour lifetime.** A gap longer than an hour rewrites the prefix at 2× on the next turn (at 64K, about $0.82 for that one turn).

What it saves, measured (arm C, second turn, versus the current arrangement):

| Retained history (est. / provider tokens) | Current arrangement, per turn | With the history prefix cached, per turn | Saving |
|---|---|---|---|
| 16K / 27K | $0.110 | $0.017 | 85% |
| 32K / 48K | $0.216 | $0.028 | 87% |
| 48K / 66K | $0.307 | $0.036 | 88% |
| 64K / 88K | $0.413 | $0.047 | 89% |

The first turn after a cold start or an hour's gap pays the write instead (about 2× the uncached price of the prefix); every turn within the hour after that pays a tenth.

**Q2 — What a turn costs at 16K, 32K, 48K and 64K of retained history, all else equal** (current arrangement, persona cached, short reply): **$0.11, $0.22, $0.31, $0.41.** The estimator runs about 1.34× low, so "64K" is about 88K provider tokens on this material — consistent with the qualification long-context turns (≈80K provider input for ≈60K estimated).

**Q3 — One long thread at the cap versus a fresh conversation with recall.** A turn at the 64K cap costs about $0.41. A fresh-conversation turn carries at most the 16K-token recall budget plus its own short history; today's turn 2, with a 20K-token excerpt, cost $0.116, and a turn with a typical smaller recall costs $0.05–0.10. **Per turn, a fresh thread is roughly a third to a quarter of the cost of a thread at the cap.** What is available to her differs in kind: the long thread gives her the last ~60K tokens of *that conversation*, verbatim and in order; the fresh thread gives her up to six *lexically matched* messages from other conversations in the same scope, up to 16K tokens, chosen by the words in her current message — which is what put a screenplay into a reply about the time of day. Whether that is continuity depends on the question being asked in words the earlier material used. The practice choice is Lord Armand's; the engineering fact is that recall is keyword-ranked and admits whole messages, and that the cap and history caching are currently in tension.

## 4. Recorded alongside, as ruled

When the greeting contradiction was pointed out (turn 2), Val corrected it and then volunteered, unprompted, that she had listed rulings on *Tony Spumoni* as though she held them firmly when what she actually had was the pilot draft and little else, and offered to strike anything that was not his rather than build on it. Recorded as evidence that the record-state contract and persona v1.4 are holding in real use.
