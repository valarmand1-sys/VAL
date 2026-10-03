# Local AI processing — the governing rule of 2 October 2026, implemented

Release r10 (service `7921a00`, tag `local-ai-rule-2026-10-02-r10`); NOT INSTALLED at the
time of writing. Governing text: `01-architecture.md` §5.4 (amendment of 2 October 2026)
and `CLAUDE.md`. This record is the implementation's account of itself.

## 1. What the installed service (r8, `7be9050`) can still do until r10 is installed

Read from r8's code and the live records of 2 October:

| Call | When | Where it goes | What is sent |
|---|---|---|---|
| Consequence classification | every typed turn in a conversation that is **not** sealed by live voice (a new typed chat, or one never spoken in) | Anthropic, `claude-haiku-4-5-20251001` | the classifier's fixed instructions and the newly typed message alone (727 input tokens on 2 October), before history or recall is assembled |
| Preference strip | only after a classification returns *consequential* | Anthropic, `sonnet-5-low`; registry fallback `gpt-5-5-20260423` (OpenAI) | the user message, for the deterministic strip of preferences before a blind position |
| Blind position, final answer | consequential turns, and every turn | **local** (GPT-OSS / Gemma) | — |
| Partner fallback to a paid route | never silently: the 21 September stop refuses before transmitting | — | — |

Spoken conversations, and any typed turn in them, are sealed local-only already and make
none of these calls. **The exposure is one call per typed turn in an unsealed
conversation**, and a second only if it is classified consequential.

**Immediate owner step, before r10 is installed:** either (a) send no typed message
except in a conversation that has been spoken in (the seal makes it local-only), or (b)
stop the service — `launchctl bootout gui/$(id -u)/house.armand.val.api` — which stops
every call at the cost of typed work until it is started again. Removing the hosted keys
from r8's configuration is **not** an option: r8 refuses to start when a key for an
active hosted route is missing.

## 2. Inventory of model-dispatch paths (r10)

Every call to a model passes through one of these; each is named with its provider,
when it runs, what it sends, and its state under the rule.

| Path | Task type | Runs when | Provider (hosting) | Sends | Under the rule |
|---|---|---|---|---|---|
| final answer | `conversation` | every turn | GPT-OSS via LM Studio on `127.0.0.1:1234` (typed); Gemma via llama.cpp on `127.0.0.1:8099` (Voice) | persona, guidance, envelope, history, his words | unchanged, local |
| light conversation, speculative light | `light_conversation`, `speculative_light` | only with switches set (unset in production) | local | — | unchanged, off |
| prefix prime | `prefix_prime` | Voice sessions | local | persona prefix | unchanged, local |
| blind position | `blind_position` | after a *consequential* classification | local partner | the stripped request | **not reached**: no classification runs |
| consequence classification | `classification` | every unsealed turn | Anthropic Haiku 4.5 (**hosted**) | the new message | **NOT RUN**, rule as reason |
| preference strip | `strip` | after a consequential classification | Anthropic Sonnet 5 low, fallback OpenAI (**hosted**) | the user message | **not reached** |
| title | `title` | **no dispatch exists** — titles are derived in the desktop/service without a model | — | — | n/a |
| perception (image, video, audio) | not a model call row | an attachment turn | local subprocesses (MLX-VLM, llama.cpp Omni) | the bytes | unchanged, local |
| speech (TTS) | not a model call row | Voice | local (mlx-audio) | her words | unchanged, local |
| recognition (STT) | — | Voice | local (whisper.cpp) | audio, never stored | unchanged, local |
| recall, house recall, summaries | — | per turn | **no model**: PostgreSQL | — | n/a |
| background jobs | — | prefix refresh, Partner re-warm after Voice | local | — | unchanged |
| retries and fallbacks | — | `_execute` walks the candidate order; registry `fallback_slug` chains | filtered to local by egress; refused at `_attempt` | — | **cannot reach a hosted route** |
| the candidate lane and the screening harness | any | isolated runs | whatever they pin | — | same door, same refusal |

**Where the rule is enforced (all three hold at once):**

1. `val_policy.egress.decide_egress` adds `OWNER_RULE_LOCAL_AI` to every turn's decision,
   so routing offers local routes only and the classifier branch records NOT RUN.
2. `Gateway._attempt` — the narrowest door, reached by `complete`, `converse`,
   `complete_with_configuration`, the candidate lane and the primes — refuses a hosted
   configuration (`HOSTED_MODEL_NOT_AUTHORISED`) before eligibility, reservation or
   transmission, whatever the request says about its own egress; and then verifies the
   adapter's declared `destination` (a loopback URL, or `"subprocess"`) — a route
   labelled local with an adapter that would send elsewhere, or with no declaration, is
   refused the same way.
3. `startup.build_adapters` builds no adapter for `anthropic`, `openai` or `google`, so
   no object in the process can reach a hosted provider, and no hosted key is required.

The rule is `HOSTED_MODELS_FORBIDDEN = True` in `val_policy.egress`: a constant, not read
from the environment. No setting turns it off; the only way to permit a hosted model is
a code change under a further ruling.

## 3. Credentials: where hosted-model keys remain, and what else they serve

- `VAL_ANTHROPIC_API_KEY` and `VAL_OPENAI_API_KEY` are set in the live service plist and
  in the two rollback copies (`~/val-rollback-20260930/…13b3cb8`,
  `~/val-rollback-20261002/…r5-422ee71`). r10 neither reads nor requires them. They serve
  no other purpose in the service: nothing non-model uses them. They are not deleted and
  are never printed; removing them from the live plist is his decision and is recommended
  **after** r10 is installed (see §7), since r8 cannot start without them.
- `VAL_LMSTUDIO_API_TOKEN`, `VAL_LLAMACPP_API_KEY`: local model-server keys; fine.
- `VAL_DATABASE_URL`: the local store.
- Backups: `house.armand.val.backup` runs `infrastructure/backup/run_backup.py` from
  `~/Projects/val` with pgBackRest configured in `/opt/homebrew/etc/pgbackrest/pgbackrest.conf`
  (an S3-compatible repository); its credentials live there, outside the service, and
  nothing in this release touches that file (unchanged since 19 September). Backups and
  the restore check are authorised non-model connections and remain as they were.
- ElevenLabs: no code path in the service calls it; the §8 deviation is a reference-
  conditioning authorisation, not a route. The desktop makes no external request.

## 4. Verification (focused; nothing sent externally)

`packages/gateway/tests/test_local_ai_rule.py` (10) with scripted adapters: every turn's
decision carries the rule; a hosted configuration handed directly to the gateway is
refused before the adapter is reached, the spy sees nothing; an ordinary routed strip
request reaches no hosted route through any fallback; a route labelled local whose
adapter declares a non-loopback destination, or none, is refused and the turn ends
unanswered with nothing sent; a verified loopback destination is allowed; a typed turn
in a new conversation is answered locally and its classification row reads NOT RUN with
the rule as the reason and no verdict; startup builds no hosted adapter and needs no
hosted key; the registry still holds the hosted entries. `apps/api/tests/test_service.py`
holds the cost view's statement of the rule. The service was started in-process with
both hosted keys absent from the environment: it came up with adapters `llamacpp` and
`lmstudio` only and two warnings naming the unbuilt providers.

Suites: packages + infrastructure 3,064 (+2 expected failures), api 126, desktop 261;
ruff, format, mypy, boundaries, import contracts, pins, secrets, scope ruling clean.
**CI at `7921a00`: success** (run 37075227061).
The tests written before the rule drive scripted adapters under hosted provider names
and hold governance still true; they run with the rule stood down by a conftest fixture
that production code never reads, and one of them is annotated to say so.

**Reused, not repeated:** the Voice, resource, delivery and interruption evidence of the
r5–r9 records; the conversation models and their settings are untouched by this release.

## 5. Functions now unavailable, and what that means for Val's behaviour

| Function | State under r10 | Effect |
|---|---|---|
| Consequence classification | NOT RUN, every turn, recorded with the rule as the reason | No turn is found consequential or ordinary by a model. Consequential execution is **blocked** for want of the gate (the existing `val_policy.consequence` fail-closed gate; nothing in Layer 0 executes outside the conversation anyway). Val answers every turn as an ordinary turn **without a safety verdict having been formed** — this is stated, not hidden. |
| Preference strip, blind position, deliberation record, prediction ledger | not reached | No independent blind position is taken on any turn. The consequential-turn machinery of WP-0.9 does not run. |
| Gate point 5 evidence (the fifty hand-labelled real classifications) | collection paused | No new classification rows carry a verdict, so the fifty cannot accumulate until a local classifier is qualified. The Layer 0 gate's point 5 is paused by this rule, not advanced. |
| The classification review path | still works on existing rows | Nothing new to review. |

**Not identical governance:** r10 keeps the conversation models and Voice exactly as r8,
and loses the two safeguards above until local replacements are qualified. A turn that
would have been classified consequential is now answered without that finding; the
record says NOT RUN, never "ordinary".

## 6. Local replacements — proposal, not adoption

| Function | Proposed local implementation | Qualification | Model and residency | Memory / latency | Until ready |
|---|---|---|---|---|---|
| Consequence classification | **First, the deterministic applicability gate** the 11 September ruling already prefers: a rule-based pre-check that settles the plainly ordinary turns (greetings, questions, creative requests) with no model, recorded as a positive gate decision; **then** the schema-constrained classifier contract on the **resident** conversation model for the rest (GPT-OSS when typed; Gemma when Voice — llama.cpp enforces a JSON grammar, LM Studio enforces a schema). | Against the existing hand-labelled real exchanges (20 labelled today of the fifty) plus the frozen classifier fixtures; the 3 September fallback — unknown is never ordinary — intact. The gate's rules constructed separately from the validation set, as that ruling requires. | No second model: the classifier call goes to whichever conversation model is resident, so the one-model-at-a-time policy holds and no memory is added. | Memory: none added (estimate). Latency: one serial local call before the answer on turns the gate does not settle — ~1.5–3 s on GPT-OSS at a 700-token prompt (estimate from the measured prefill rate), 0 on gated turns. | NOT RUN. |
| Preference strip | The same contract on the resident model, with the frozen v4 strip suite (136 cases) as its qualification. Only after a consequential classification, so its latency is paid on consequential turns only. | Frozen v4 suite, measured as it was for `sonnet-5-low` (134/136 recorded). | Resident model, no addition. | Memory: none (estimate). Latency: ~3–6 s on consequential turns (estimate). | not reached. |
| Blind position, judge | Already local (the partner model). | — | — | — | not reached only because classification is. |
| Titles, summaries, recall | No model is involved today; nothing to replace. | — | — | — | — |

No download, no new model and no qualification run is started by this record.

## 7. Release r10: contents, installation, rollback

- **Service:** `7921a00`, tag `local-ai-rule-2026-10-02-r10`; tree
  `~/Projects/val-releases/7921a00` (environment synced). Changes against the installed
  `7be9050`: the rule (domain reason, error kind, policy constants and refusals, the
  gateway door, startup, the classifier's NOT RUN reason), the cost view's two additive
  fields, and the desktop's cost line.
- **Desktop:** built from `7921a00`, staged as
  `~/Val previous builds.noindex/Val (local-ai rule 2026-10-02 r10 7921a00, staged, not installed).app`,
  binary SHA-256 `366cc97f3e83e4bc1960f47a5b648a03ebacff77e643c74ea960d51f8f32bb58`.
  Its cost line reads "AI processing runs on this Mac; no hosted model is used (owner
  rule, 2 October 2026). Earlier this month, before the rule: $0.0017 billed by outside
  providers." — stated only when the running service reports the rule; against r8 it
  shows the previous wording. The desktop holds no part of the enforcement.
- **Settings:** the eleven of r8, unchanged. No migration. No backup requirement.
- **Installation (his hands, one step at a time):** stop the service; point the plist at
  `~/Projects/val-releases/7921a00`; start it and read its startup warnings — the two
  "hosted provider … no adapter built" lines are the proof the rule is in force; verify
  `GET /costs` reports `hosted_models_permitted: false`; install the desktop bundle.
  **Then, recommended:** remove `VAL_ANTHROPIC_API_KEY` and `VAL_OPENAI_API_KEY` from the
  live plist (the rollback copies keep them; nothing is printed), so that no hosted key
  is in the running service's environment at all.
- **Rollback and how the restriction survives it:** the rule is in the service code, so
  it cannot be turned off by a setting and is unaffected by rolling back the desktop
  (desktop r9's cost line simply reads the old way). Rolling the **service** back to r8
  **would** restore the hosted classification route — that is what r8 does — and if the
  hosted keys have been removed from the plist, r8 refuses to start, which makes a
  silent restoration impossible: a rollback to r8 would need the keys put back
  deliberately, from the rollback copy, by his hand. The only rollback that keeps the
  rule is to a service revision at or after `7921a00`.

## 8. Historical costs and the display

Every `model_calls` row and cost stays as recorded. The service's `/costs` now carries
`hosted_models_permitted` and `hosted_models_rule`; the desktop distinguishes the
month's historical charges from current local processing only when the running service
reports the rule — it never claims the rule ahead of installation.

## 9. INSTALLED — 2 October 2026, 18:50–19:20 CDT (his approval, his hands, each step verified read-only)

- Service `7921a00` (tag `local-ai-rule-2026-10-02-r10`) from `~/Projects/val-releases/7921a00`,
  started twice: first with r8's configuration (verified), then — after the typed
  request-path check — with `VAL_ANTHROPIC_API_KEY` and `VAL_OPENAI_API_KEY` **removed from
  the active plist** (his authorisation). The running process's environment holds the
  fourteen expected variables and no hosted key. Store `0032`, no migration. Desktop
  `366cc97f…bb58` installed; r9's (`b9800ac0…`) set aside.
- **Request-path check (19:03 CDT):** his typed "What is the capital of Australia?" in a
  new conversation — answered "Canberra, my lord." by one call to `openai/gpt-oss-20b` at
  `http://127.0.0.1:1234/v1`, $0 (first text 12.9 s); the classification row: no verdict,
  not established, 0 attempts, 0 calls, reason naming the rule; the service's outbound
  requests since startup: `127.0.0.1:1234` only; the process's connections: the local
  store, LM Studio and its own listener.
- **The classification gate, confirmed before installation** (his point 1):
  `val_policy.consequence.execution_refusal` refuses on no record, not-run, or nothing
  established, and permits only an established verdict; `EXECUTION_GATED_ON_CLASSIFICATION`
  is empty because nothing in Layer 0 acts outside the conversation; the local-only branch
  never enters the blind-position path; `execution_events` executes nothing; the review
  path calls no model. Tests: `test_egress_policy.py` (not-run ≠ not-consequential; blocked
  on not-run, on no record, on nothing established), `test_local_ai_rule.py`.
- **Safe recovery under the rule:** no older service satisfies it. If r10 misbehaves, stop
  the service (`launchctl bootout gui/$(id -u)/house.armand.val.api`) and leave it stopped
  while r10 is repaired. The plist copies `~/val-rollback-20260930/…13b3cb8`,
  `~/val-rollback-20261002/…r5-422ee71` and `…r8-7be9050` contain hosted keys and are
  **historical records, unsuitable for restoration**. Desktop rollback (to the r9 bundle)
  changes nothing about the rule.
- **Temporary governance limitations in force:** consequence classification NOT RUN on
  every turn; preference strip, blind position and deliberation not reached; consequential
  execution blocked for want of the gate; gate point-5 evidence paused. Local replacements
  (§6) proposed, **not approved**.
- Backups, external tools, Voice settings and the models: unchanged.
