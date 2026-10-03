# Typed prefix preparation for GPT-OSS — measured 2 October 2026

Owner authorisation (2 October 2026, evening): "isolated implementation and measurement of
prefix preparation for GPT-OSS typed work … Do not change Persona, reasoning effort,
sampling, model selection or instruction placement … must not load GPT-OSS alongside Gemma
during Voice, interfere with an active request, or turn background maintenance into
another delay … Measure a short sequence of differing typed turns, including a follow-up
and the transition from Voice to typing." Direction A of the same evening: "Establish why
subsequent replies also pay full prefill … Measure Send to first visible answer,
separating loading, preparation, prefill, reasoning and other waiting. Count delays
caused by background preparation … Six seconds is a reference point, not the completion
target."

**Status: measured; NOT RULED, NOT DEPLOYED.** Production runs r10 (`7921a00`) without the
typed prime. The candidate is in the proposed release r11 (§9).

---

## 1. What was found first

Every typed turn on production's GPT-OSS route prefilled its whole prompt from zero. The
runtime's own log says so (`Prompt cache: using 0/N tokens from cache`) on every typed
turn of the `off` baseline, at ~700 tokens/s — 8–10 s of prefill before any reasoning
begins, on a 6,600–7,500-token prompt. The persona checkpoint that Voice has had since
25 September (`prefix_prime`) existed only inside a Voice session; typing had none.

Why a previous turn's own computation cannot be reused (established 27 September,
`ORDINARY_TURN.md` §18, re-confirmed here): the runtime keeps one checkpoint near the end
of each prompt; the next turn's prompt diverges from it before that point (the generation
prompt differs from the continuation), so history is never reused. Only a checkpoint at
the persona boundary — a prime — is reusable, and only while the runtime's LRU prompt
cache (ten entries, two per distinct request) still holds it.

## 2. What was built

`Gateway.typed_prime` (`VAL_TYPED_PRIME`: unset/`off`, `transition`, `on`):

- `prime_typed_prefix` — the persona-boundary prime for the typed route, recorded as
  `prefix_prime` in `model_calls` like every prime, never while Voice holds the memory.
- At service start, and after Voice releases Gemma and reloads GPT-OSS
  (`rewarm_partner_after_voice`), in both modes.
- `on` only: a **refresh** after each typed answer (`typed_turn_finished`), waiting 1 s of
  idleness, coalesced, standing aside when a typed request is already waiting, never
  ahead of a request.
- `f7db6c8`: the prime at start and after Voice no longer stands aside for a waiting
  request (a refresh still does). Measured effect: none on the first typed turn after
  Voice (§5); it determines which of the first two post-Voice turns pays for the prime.

Nothing else changed: persona, MEDIUM, sampling, model, instruction placement, Voice's
own primes, the classification route.

## 3. Method

`run_typed_cache.sh MODE LABEL [TYPED_ONLY_TURNS]`, `typed_cache_bench.py`,
`summarise.py`, this directory. A scratch service (port 8766, scratch store `val_test`)
addresses a **second instance** of production's own model path (`val-exp-prod`,
`openai/gpt-oss-20b`, 32,768 context, `--parallel 1`, not on the cache-renewal allowlist,
so the runtime behaves exactly as production's instance does). A fresh instance per run,
so the cache starts empty. Gemma is started by the service's supervisor for the Voice
transition. Production, its store and its instance were not touched; the production
instance had expired by its 3,600 s idle TTL before every valid run, so the two never
coexisted (a T1 attempt where they did reached 3% free / 11 GB swap and was discarded).

Sequence: four differing typed turns in one conversation (a follow-up included), a real
Voice session opened and closed through the service's own Voice path (Gemma warm, prime,
one spoken-path prefill), then two typed turns in the same conversation. Typed-only
mode: ten differing turns in one conversation, no Voice.

"Send → first visible" is the client's clock from `POST /turns/stream` to the first
`delta` event. The runtime's log gives the cache figure and the prefill span (1-s
stamps) for the turn's own request — the longest prompt in its window, so a prime
interleaved with it is not mistaken for it (a defect in the first reading, corrected in
`32322bd`; the T2 `on` after-Voice row's "43 s prefill" was that defect).

Valid runs: `T2-off`, `T2-transition`, `T2-on` (commit `3dae393`/`1787056`),
`T3-transition`, `T3-transition-2`, `T3-typed-only-transition`, `T3-typed-only-on`
(commit `f7db6c8`), all `dirty=0`. Discarded: the first `on` attempt (pytest rebuilt the
scratch store under the service; dirty tree), and the first `T3-typed-only-*` attempt
(bench defect, `run-T3b-failed.out`). `T3-transition-2` ran under the label
`T3-typed-only-transition` before the third argument was honoured and was renamed.

## 4. Results — send → first visible, seconds

| case | `off` (production today) | with the prime |
|---|---|---|
| typed, service freshly started, first turn | 17.3 | 9.9–12.2 (waited behind the start-up prime; bench artefact — the message was sent 12 s after start) |
| typed, no Voice, turns 2–5, one conversation | 10.4–14.9 (cache 0, prefill 8–9 s) | **2.5–7.7** across four runs (3.0, 2.5, 7.5; 7.7, 3.3, 6.4; 6.3, 2.7, 3.3; 2.8, 5.2, 5.0); 5.2–10.7 in the typed-only runs |
| first typed turn after Voice closed (sent 1–4 s after close) | 18.2 | **16.4–20.6 — no gain** (§5) |
| second typed turn after Voice | 19.2 | 8.7–18.2 (pays if it lands during the post-Voice prime) |
| typed-only, turns 6–10, `transition` | — | **18.8–21.9, cache 0** — the checkpoint is evicted after five distinct turns |
| typed-only, turns 6–10, `on` | — | 8.2–13.5 (one 37.4, §6), cache 5,790 on all ten |

Cache reuse when it holds: 5,790 of 6,621–7,520 prompt tokens; the remaining prefill is
the conversation's history and his message, 830–1,730 tokens, 1–6 s by the runtime's
stamps, growing with the conversation.

### 4.1 Stage breakdown of a steady-state typed turn (`on`, model resident, prime held)

| stage | measured | note |
|---|---|---|
| loading | 0 | model resident |
| preparation | 0 | the prime is a cache hit |
| receipt, classification, gates | ~10–50 ms | classification NOT RUN under the rule |
| prefill (history + message) | 1–6 s | 830–1,730 tokens at the runtime's rate |
| hidden reasoning (MEDIUM) | 2–5 s | not directly observable; the remainder of first-output time |
| first visible text | **2.5–8 s** after Send | 10–19 s today |

### 4.2 Delays caused by background preparation

- A warm refresh costs the runtime 0.23–0.49 s (`model_calls` latency), 1 s after the
  answer. A message arriving inside that window waits at most that long. None of the
  measured turns did (3 s spacing).
- A **cold** prime costs 8–10 s (9.96 s at service start; 20.9 s once, after the §6
  stall), and a message arriving during it waits for it: the first typed turn in each run
  (bench artefact) and the 37.4 s turn in §6 (real exposure: after any eviction or
  unload, the refresh runs cold and the next message may wait).
- The first typed turn after Voice: see §5.

## 5. The transition from Voice back to typing

Timeline (T3-transition, from the service and runtime logs): Voice closed → `lms load`
GPT-OSS 20:28:41 → loaded 20:28:48 (7 s) → the typed turn's request (sent 3.5 s after
close) and the post-Voice prime both released; the turn reached the runtime 0.14 s
earlier and prefilled cold (7,002 tokens, 20:28:48–20:29:04) → answer → the prime ran
cold behind it (5,801 tokens, 20:29:04–20:29:12) → the second typed turn (sent 20:29:08)
waited for it, then reused 5,790 (8.7 s). In T3-transition-2 the prime went first: turn
one 18.9 s, turn two waited 10 s behind the prime (18.2 s).

The first typed turn after Voice costs **the GPT-OSS reload plus one cold prefill**
whichever order the two take — prefill is linear in tokens, and the prime is 5,801 of the
turn's ~7,000. The order only decides whether the second turn pays as well. The reload is
there because Voice releases GPT-OSS for Gemma (`VAL_VOICE_RELEASES_PARTNER=on`; the two
do not fit: the T3-transition memory log touched 10% free for one 5-s sample during the
Gemma load even with GPT-OSS already released). The transition therefore costs ~15 s of
preparation after Voice ends, hidden only when he waits that long before typing. The
desktop does not currently show it; a readiness indication after Voice ("preparing typed
cognition … ready") is the honest presentation and is proposed, not built.

The same shape applies after an idle hour: the runtime unloads the instance at
`IDLE_TTL_SECONDS = 3600` and the cache with it; the next typed turn reloads (~7 s) and
prefills cold (~10 s) — his "Canberra, about 13 seconds" and the 16.5 s draft reply of
the r9 check are this case. `on` re-primes after that turn. Keeping GPT-OSS resident
(a longer TTL, ~12 GB held) would remove it; that is a memory decision and his.

## 6. An anomaly, recorded as observed

T3-typed-only-on, turn 4 ("Give me a title for a film about an orchard."): the runtime
finished prefill at 20:39:29 and logged nothing until "Finished streaming response" at
20:45:54 — 385 s for a 271-token answer that reads normally (398 characters). The three
instruments disagree on this turn: the bench's stream closed at 91.2 s, `model_calls`
latency 89.4 s, the service's completion log and the runtime's at 20:45:54–55. During the
window swap grew 4.37 → 8.21 GB and returned to 4.25 GB afterwards (free never below
59%). The LM Studio log carries 27 `UnboundLocalError: cannot access local variable
'token'` entries today, all after 20:00, none on 30 September or 1 October; the first
follows an `applyPromptTemplate` (the exact preflight's inspector), not a prime, so it is
not shown to belong to the prime. The turn's own request hit the cache normally
(5,790/7,136). **Not explained; not attributed to the prime; production runs the same
runtime and carries the same exposure.** The next refresh ran cold (20.9 s) and the
following turn waited behind it (37.4 s).

## 7. Memory

| run | min free | swap |
|---|---|---|
| T2-off / T2-transition / T2-on | 29–34% | 4.1 → 5.3 GB |
| T3-transition | **10%** (one sample, 20:28:29, during the Gemma load) | 4.53 → 4.75 GB |
| T3-transition-2 | 28% | ≤ 4.67 GB |
| T3-typed-only-transition | 63% | 4.38 GB, flat |
| T3-typed-only-on | 59% | 4.37 → **8.21** (§6) → 4.25 GB |

Only the models each run needed were resident (production's instance expired by TTL
before each run; `lms ps` empty before and after). After the runs: no model resident,
82% free, swap 4.3 GB. Production's GPT-OSS reloads on demand — the production log shows
`model_found_loaded=False, model_loaded=True` on today's reloads — but the next reload
after this measurement has not happened yet, because he has not typed since; his first
typed message will show it in `/opt/homebrew/var/log/val/api.log`.

## 8. Conclusions

1. **The cause of the typed delay is one fact: no reusable checkpoint outside Voice.**
   With the prime held, an ordinary typed turn's first visible text moves from 10–19 s to
   **2.5–8 s**; the remainder is history prefill (1–6 s, growing) and MEDIUM's hidden
   reasoning (2–5 s), neither of which this work may change.
2. **`transition` is not sufficient**: the checkpoint is evicted after about five
   distinct typed turns and every later turn is cold again. **`on` holds it** across ten
   turns at 0.2–0.5 s of background work per turn.
3. **The first typed turn after Voice, and after an idle hour, is not improved** —
   reload plus one cold prefill, 16–21 s — and cannot be by a prime. Honest presentation
   (readiness after Voice) and the resident-memory question are his decisions.
4. `f7db6c8` (prime first after Voice) gained nothing measurable and is kept only because
   it makes the second post-Voice turn's outcome deterministic (it pays once, then every
   turn is warm).
5. Six seconds is met by the median steady-state turn and not by every turn; the ~1 s
   target remains unmet and is not claimed.
6. One runtime stall of 385 s with 3.8 GB of swap growth is on record (§6), unexplained,
   and not caused by this work.

## 9. Proposed release r11

`tag typed-prime-versions-2026-10-02-r11` on branch `latency-2026-09-28`, CI on
`release/voice-model-2026-09-29`, containing since r10 (`7921a00`): the typed prime
(§2); message editing, versions and reinstatement (`VAL_Message_Versions_Record.md`,
migration `0033_message_version_selections`); the bench and these records. Installation
is by his hands, one step at a time, with the usual confirmation per step; the exact
commands are given in the handoff message when he approves. Outline:

1. Back up the live store (`pg_dump`) — the release carries a migration.
2. Stop the service: `launchctl bootout gui/$(id -u)/house.armand.val.api`; verify the
   process is gone.
3. Check out the tagged commit at `~/Projects/val-releases/<sha>`; `uv sync --frozen`.
4. `alembic upgrade head` against the live store (adds `message_version_selections`,
   additive, append-only).
5. Edit the plist: `ProgramArguments` → the new directory; add `VAL_TYPED_PRIME=on`.
   No hosted key is added; the plist keeps the local-AI rule's state.
6. `launchctl bootstrap`; `/health`; the log shows `typed prime: {"primed": true …}`
   within ~15 s of start.
7. Desktop: move `/Applications/Val.app` (r10, `366cc97f…`) to
   `~/Val previous builds.noindex/`, install the staged r11 bundle, run the deployment
   check (one bundle, the right digest).

Rollback: bootout; `ProgramArguments` back to `~/Projects/val-releases/7921a00`; remove
`VAL_TYPED_PRIME`; bootstrap; restore the r10 desktop bundle. The migration stays —
`0033` is additive and r10 ignores the table (its downgrade refuses while rows exist).
Rollback never restores a hosted route: r10's plist has no hosted key and none is kept
anywhere the rollback reads.

Not in the release and still open: the readiness indication after Voice, the TTL/resident
memory question, the §6 stall, classification's local replacement (not approved), the
~1 s target.
