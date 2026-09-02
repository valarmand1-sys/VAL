# 01 — Architecture

**Status:** Governing on how Val is built.
**Owns:** the capability layers, stack, machine topology, model routing, cost enforcement, data classification, tier handling, tool governance, presence.
**Does not own:** what Val is or may never do (`00-charter.md`), how she becomes expert or forms positions (`02-partner-systems.md`), how she speaks (`03-persona.md`).

Invariants referenced by number throughout are those in `00-charter.md` §6.

---

## 1. Build order

Val is built in **capability layers**, not governance phases. Every layer produces something used daily. Nothing is built speculatively.

| Layer | Delivers | Governance introduced |
|---|---|---|
| **0** | Core loop — she exists, remembers, is useful across projects | None. Nothing consequential can occur. |
| **1** | Presence — voice and face; local inference stands up | None. Presentation only. |
| **2** | Hands — MCP tools, read-only | Tool Registry. Discovery ≠ authorization. |
| **3** | Agents — Roles, supervision, review | Envelope rule. Temporal. Independent review. |
| **4** | Consequence — she changes real things | Full chain: tiers, approval, versioned writes, audit. |
| **5** | Learning — she gets better at this work specifically | Lesson promotion. Success models. |

Governance arrives exactly when there is something to govern. Building the approval chain at Layer 0 is constructing a vault around an empty room; the cost is not the vault but the twenty weeks before the first useful behavior exists.

**Later-layer behavior shall not be implemented early merely because its design exists.** Shared interfaces and placeholders needed by the current layer may be created, but the capability stays technically disabled until its layer.

There are three exceptions, and only three. Each is a **capture** obligation, not a capability, and each exists because the data is impossible to reconstruct later:

1. **Execution history** — every acceptance, rejection, revision, and correction, with its reason.
2. **Deliberation records** — Val's position, confidence, and what happened to it.
3. **Per-call cost attribution** — what each model call cost, and against which project and task type.

All three begin at Layer 0. The machinery that consumes them arrives at Layers 3 and 5. Recording is cheap; backfilling is impossible. See invariant 34.

A fourth Layer 0 obligation follows from the same argument and is easy to overlook: **backup of the authoritative store** (§9). The case for capturing this data from day one applies with equal force to not losing it afterward. Captured-then-lost and never-captured are the same outcome.

---

## 2. The layers

### 2.0 Layer 0 — The core loop

*Val exists, remembers, and is useful across projects.*

- PostgreSQL + pgvector as sole authoritative store for conversation, projects, and memory
- FastAPI service
- Multi-provider model routing behind one internal interface, from the first call
- Project awareness: every exchange attributable to a project, or explicitly to none
- Persona loaded whole into every context (`03-persona.md`)
- The three capture obligations of §1
- Text interface sufficient for daily use

No Temporal, no transactional outbox, no audit chain, no approval flow. Nothing consequential can happen here; these protect nothing yet.

Concrete work packages, schema, and acceptance criteria: `04-layer-0.md`.

### 2.1 Layer 1 — Presence

*Val has a voice and a face.*

- Speech-to-text running locally — Whisper via MLX or whisper.cpp. The M4 Pro handles this comfortably and audio stays on-device.
- Text-to-speech via ElevenLabs, using the established voice profile
- Avatar per §8
- Push-to-talk first. Wake word only once the loop is stable.
- **Local inference stands up here**, on the MacBook.

**Local inference is a Layer 1 deliverable, not a Layer 3 one.** It stands up on the existing 48GB MacBook and serves Layers 1–2 from there; it moves to the always-on box at Layer 3 (§4) as a relocation, not a first installation.

> **Amendment — 15 August 2026, Lord Armand.** The ~30B-class sizing in §3 belongs to the always-on box, which serves inference and nothing interactive. At Layer 1 the same 48GB also runs Premiere and After Effects. **The Layer 1 model is sized by measurement on the real machine, not by the spec's number**, and the local inference server must be stoppable on demand so it never competes with an active edit session.

The reason for standing it up this early is that the cost gradient (§5.3) is fiction until local exists. Every routing decision before that point is cloud-to-cloud, the ceiling does no real work, and the assumptions behind the budget go untested. Layer 1 is also when speech-to-text arrives, so on-device inference is being set up regardless. Exercising the gradient under Layer 1–2 volume — where the consequences of getting it wrong are a slow reply — is materially safer than first exercising it at Layer 3, when agents multiply call volume.

<!-- scope-ruling: 2026-08-31 -->
> **Sequencing ruling — 31 August 2026, Lord Armand. Presence may proceed in parallel with the Layer 0 gate, under one hard constraint.**
>
> Layer 0 gate evidence accumulates through real use — no manufactured judgments, no deadline; the gate closes when the evidence exists. Presence work (speech-to-text input, ElevenLabs output, avatar state loops, lip-sync) is **permitted before the gate on one condition, stated here as a constraint rather than a convention: it consumes the existing conversation contract and does not change it.** Concretely: **no new table, no new column, no migration, and no change to what the conversation endpoints return.** A presence feature that needs any of those **stops and waits for the gate** — it does not get a carve-out, and an implementation that finds a way to smuggle state into an existing column is violating the constraint, not satisfying it.
>
> Everything else stays behind the gate: message revision/retraction, attachment ingestion, documents, image vision, and anything touching persistence, recall, routing, evidence semantics, or egress.
>
> **Requirement, same date: invariant 29 applies to avatar state.** Every frame the avatar shows is a claim about what Val is doing. An idle or thinking loop displayed while something has actually failed is the same defect as an error banner asserting a cause it has not established — a confident assertion the system has not made true. Presence degrades honestly, and **the avatar must not depict a state the system cannot confirm**: a state loop is driven by confirmed backend state, never by optimism, and where the system cannot confirm what is happening, the avatar shows that — not a guess. This extends invariant 28 (animation is presentation only, §8) from "never implies success" to "never depicts the unestablished."

Failure behavior: §8.3.

This layer lands early deliberately. It is the difference between a chat application and Val, and that difference determines whether the system is used at all. A correct system nobody opens has failed.

### 2.2 Layer 2 — Hands

*Val can reach the outside world.*

Val is a native MCP client (§7). Governance enters here because there is now something to govern:

- Every discovered tool enters the **Tool Registry**, is classified by action class and minimum risk tier, and is explicitly enabled. Discovery is never authorization (invariant 6).
- **Read-only tools first.** Write tools remain disabled until Layer 4.
- **Arbitrary-code tools are permanently excluded, not gated** (invariants 7, 8).

> **Requirement — 31 August 2026, Lord Armand. Val must be able to see images. Recorded against this layer; no work before it.**
>
> **The requirement is sight, not receipt.** The image reaches the model *as an image*, and Val can describe what is in it, reason about it, compare it against another image, and notice things Lord Armand did not point out. Anything less is not the requirement.
>
> **Why it is load-bearing:** most of the actual work is visual — setting masters, character sheets, storyboard frames. A partner who cannot see an image cannot help with the majority of what Lord Armand actually does.
>
> **The capability bar, concretely.** Val must be capable of: judging whether two setting images match on style, palette, and architecture; checking a character against a model sheet for continuity; reading a storyboard frame and saying what is wrong with the composition; comparing a generated image against the reference it was meant to follow.
>
> **Implications recorded now, built then:**
>
> - **Vision must reach the actual model call.** A filename or path in the prompt is not sight. An implementation that passes a path and lets the model narrate around it fails the requirement while appearing to meet it — that is the failure mode to test for.
> - **What she saw is recorded as part of the exchange**, so her judgment is attributable to the specific image — the same capture doctrine as everything else in the record: a visual judgment whose subject cannot be identified later is not evidence.
> - **Filesystem access via MCP is preferred over an upload control.** The files already live in structured folders on this machine, and this layer's read-only tool discipline is the natural fit. The Tool Registry rules above apply to it in full.
> - **An image is external egress, same as text.** It is classified before it leaves the house and respects data eligibility (§5.4, invariant 17); cost and availability never override eligibility. A vision-capable route must be eligible for the image's classification, not merely capable of receiving it.

<!-- scope-ruling: 2026-09-01 -->
> **Amendment — 1 September 2026, Lord Armand, after external review. Sight is re-scoped: it is not a Layer 2 capability and should not have been recorded against one. This is a plan change, not a defect.**
>
> **The reasoning: sight and filesystem access are different authority classes.** Sight is a property of the *model call* — image bytes reach a vision-capable route that is eligible for that content's classification, and what she saw is recorded against the exchange. Filesystem access is a property of *tool governance* — discovery, registry, read-only discipline, path confinement. Bundling them meant the first time Val could see anything was also the first time she could read the disk, which is both later and more dangerous than it needs to be.
>
> - **Sight may begin post-gate as attachment-scoped vision**: an image Lord Armand deliberately attached to a conversation. That satisfies "sight, not receipt" without Layer 2 Hands. Sequencing: `04-layer-0.md` §5.
> - **MCP filesystem access stays Layer 2.** The implication above that filesystem access is the preferred route to vision is **superseded**: it is the preferred route to *reading folders at scale*, which is a different requirement and stays where it is.
> - **Write and modify tools still wait for Layer 4.**
> - **Eligibility is unchanged and non-negotiable**: an image is external egress and the route must be eligible for its classification.
>
> **Why now rather than at Layer 2, stated in the accurate form:** the evidence record is append-only, so every visual judgment made before Val can see is *permanently* a worse class of evidence — her reasoning from Lord Armand's descriptions rather than from the thing itself. That is true now, not contingent on Layer 5 arriving.
>
> Everything else in the requirement above — the capability bar, sight-not-receipt, vision reaching the actual model call, what-she-saw recorded per exchange — stands unchanged.

### 2.3 Layer 3 — Agents

*Val builds and supervises her own working teams.*

- **Roles, not employees.** A Role is a durable, versioned object: instructions, permitted tools, model preference, output contract, evaluation criteria, and an accumulated knowledge base. Specified in `02-partner-systems.md` §1.
- Val composes Roles into working agents per task, in parallel where the work allows.
- **Val supervises rather than performs.** Agents produce structured output against a defined contract. Val evaluates, returns for revision, or accepts, then presents the result with her reasoning attached.
- **Independent review scales with stakes.** For consequential work, a reviewer Role that did not produce the work evaluates it. For routine work, structured self-critique suffices. A producing Role never approves its own material output (invariant 32).
- **The envelope rule.** Val creates Role *configurations* freely. Val never grants *capabilities* (invariant 3).

Temporal enters here, for long-running multi-agent work that must survive worker and application restart. Duplicate delivery and retries must not create duplicate effects.

The deliberation machinery and prediction ledger become active at this layer (`02-partner-systems.md` §4).

### 2.4 Layer 4 — Consequence

*Val can change things in the real world.*

The full governance chain applies here, per §6 (tier handling):

- Risk-tier classification before execution
- The four states held distinct (`00-charter.md` §4)
- Approval required before anything irreversible or externally visible
- **Versioned writes, never blind overwrites** — especially Adobe project files (invariant 9)
- Append-only audit covering write actions and spending, not every conversational turn
- Independent verification of resulting state, not acceptance of an execution claim

The first consequential action class enabled is creation of a new versioned project file. Overwrite, send, upload, publication, and deletion remain disabled beyond it.

### 2.5 Layer 5 — Learning

*Val gets better at this user's work specifically.*

Every rejection, revision, and correction captured since Layer 0 becomes evidence. Each is distilled into a lesson record with its cause and scope and promoted as it proves transferable: repeated within one project → project knowledge; observed across projects → general knowledge about how this user works. Promoted lessons are injected into future Role context.

This is why the multi-project framing matters. A lesson confirmed in one project is a hunch; confirmed across three, it is knowledge.

Mechanism: `02-partner-systems.md` §2. Success models and standing evaluation also land here (`02-partner-systems.md` §5).

---

## 3. Stack

| Concern | Selection | Note |
|---|---|---|
| Authoritative store | PostgreSQL + pgvector | Sole source of truth (invariant 12) |
| Service | Python, FastAPI, Pydantic | Typed request and response contracts throughout |
| Migrations | SQLAlchemy + Alembic | Every schema change is a migration; no manual DDL |
| Desktop shell | Tauri 2 + React/TypeScript | Real native-bridge security boundary, small footprint |
| Durable workflow | Temporal | Layer 3 onward only |
| Local inference | ~30B-class quantized **on the always-on box** | Layer 1's MacBook model is sized by measurement, not by this figure — amendment at §2.1 |
| Speech-to-text | Whisper via MLX or whisper.cpp | On-device |
| Text-to-speech | ElevenLabs | Established voice profile |
| External tools | MCP | §6 |

**Repository shape: a modular monolith** with enforced dependency direction.

```
/apps/desktop      Tauri + React
/apps/api          FastAPI service
/apps/worker       Background and, from Layer 3, Temporal workers
/packages/domain   Schemas and typed contracts
/packages/providers  Model provider adapters
/packages/policy   Deterministic classification and permission evaluation
/packages/mcp      MCP client and Tool Registry
/infrastructure
/docs
```

Dependency rules, enforced in CI:

- `policy` depends on `domain` only. It never depends on `desktop`, `api`, `worker`, or `providers`.
- `worker` never depends on `desktop`.
- `providers` never depends on `policy` — routing asks policy, policy never asks a provider.
- No circular package dependencies.

The boundary that matters most is `policy`. It must remain callable, testable, and correct without any application running, because it is the component that decides whether a consequential action may occur.

---

## 4. Machine topology

**Layers 0–2 build on the existing MacBook Pro** (Apple M4 Pro, 48GB), including local inference from Layer 1 (§2.1).

**A dedicated always-on machine is purchased at Layer 3** — Mac Mini M4 Pro 48GB class, or a refurbished Apple Silicon machine with higher memory bandwidth. Memory capacity and bandwidth are the binding constraints for local inference, not core count.

From Layer 3 the topology is two machines on the local network:

| Machine | Runs |
|---|---|
| **Always-on box** | Postgres, FastAPI service, local inference, Temporal, standing loops |
| **MacBook** | Desktop client, Adobe MCP servers |

Local inference and the authoritative store both **relocate** here from the MacBook at Layer 3. Neither is a fresh installation, and the store's move is a governed data migration, not a copy (§9.4).

Adobe MCP servers live on the laptop because Adobe runs where the user edits. This is not a preference; it is where the applications are.

**Adobe-dependent tasks queue when the laptop is unavailable rather than failing.** A queued task is a distinct state — not an error, not a completion. Val continues to research, plan, write, evaluate, and prepare against everything else in the meantime, and reports what is waiting on the laptop when it returns.

---

## 5. Model routing and cost

### 5.1 The Model Gateway

All model inference enters through one internal gateway. No component calls a provider SDK directly.

Gateway responsibilities:

| Responsibility | Requirement |
|---|---|
| Provider neutrality | Normalized request and response contract, independent of any one provider |
| Routing | Select an **admitted** model configuration (§5.2.1) on capability, **data classification eligibility**, cost, latency, availability |
| Budget enforcement | Check the ceiling **before** the call is made, **against the cost of that call** (invariant 24; §5.7) |
| Usage recording | Tokens in and out, computed cost, latency, provider request reference, project, task type |
| Error normalization | Timeout, refusal, rate limit, invalid output, outage, and data-policy rejection normalized to one error contract |
| Fallback | Only to a prequalified route that is itself eligible for the content |
| Structured output | Output that fails schema validation is returned for repair, never accepted as prose |

Provider substitution changes none of Val's identity, memory, or governance state (`00-charter.md` §1.2).

### 5.2 Model Configuration Registry

A model configuration is a versioned record, not a model name in a settings file. Each declares:

- Provider and exact model identifier
- Context and output limits
- Reasoning or sampling settings
- **Data classifications it is eligible to receive** (§5.4)
- Cost per input and output unit, and whether caching or batch pricing applies
- Known weaknesses
- Fallback route **or an explicit NONE**, activation date, retirement state
- **Admission state and adapter state** (§5.2.1)
- **The date its rates were last read from the provider's own pricing**, and **the date it last answered a real call**, or none

Routing selects among configurations. It never selects a raw model.

> **Amendment — 17 August 2026, Lord Armand.** The last three lines were added after an audit found the implementation carrying only part of this list. Two rules govern how the fields are filled, and both exist because a confidently wrong value is worse than a visibly absent one:
>
> - **Where a provider has no such concept, the record carries a typed NOT_APPLICABLE rather than an invented value.** "No fallback" is `NONE` and is a decision; a blank field is not.
> - **Where the fact has not been established from the provider's own documentation, the record says so** — `NOT_VERIFIED` — rather than carrying a plausible guess. This is the same discipline as `rates_verified_on`, applied to the rest of the record.

#### 5.2.1 Seven distinct provider states

A provider is not one flag. These seven are independent, and conflating any two of them is how a system ends up sending Protected work to a route nobody qualified. **The registry is authoritative on every column; this table defines the vocabulary, not the roster.**

| State | Means | Where the answer lives |
|---|---|---|
| **Supported by the architecture** | The gateway's contract could carry it | This document (§5.1) |
| **Adapter implemented** | Code exists that speaks its dialect | `packages/providers` |
| **Eligible for Protected** | Ruled eligible by Lord Armand | §5.4 rulings, carried in the registry entry |
| **Currently enabled** | Present and not retired in the registry | `val_domain.registry.active()` |
| **Provisionally admitted** | Permitted to carry Layer 0 traffic | The registry entry's `admission` |
| **Qualified** | It passed the exam suite below | Exam records — none exist before Layers 2–3 |
| **Live** | It has actually answered a real call | `model_calls`, and the entry's own record |

Three rules follow, and each has already caught something:

- **An implemented adapter is not a live provider.** An adapter proves the code compiles against a dialect. Only a `model_calls` row with `status = ok` proves the route works.
- **Nothing here weakens Protected eligibility.** A provider may be enabled, adapted, and live and still be ineligible for Protected content; eligibility is a separate ruling and cost never overrides it (§5.4).
- **Enabled is not admitted.** A configuration may be present, un-retired, and eligible and still not be permitted to carry traffic. Admission is a separate field so that adding an entry to the registry is never, by itself, the act that opens a route.

> **Amendment — 17 August 2026, Lord Armand.** *Provisionally admitted* was added to resolve a contradiction, not to add a capability. §5.1 said routing selects a **qualified** configuration; this section said qualification cannot exist before the Layers 2–3 exam suite. Both were true, which left Layer 0 routing to configurations it was in no position to call qualified.
>
> The two states are now distinct and the weaker one is what Layer 0 asserts:
>
> - **`PROVISIONALLY_ADMITTED`** — permitted to carry Layer 0 traffic on the strength of an eligibility ruling by Lord Armand and a working adapter. It is the strongest standing any route may hold today, and every current route holds exactly it.
> - **`QUALIFIED`** — passed the system-specific exam suite. **No route may carry this until an exam record exists**, and no code path sets it: promotion is a recorded decision, never an implementation finding the word convenient.
>
> **Qualification supersedes provisional admission without changing configuration identity.** The `id` and `slug` are permanent, so a route promoted later is the same route, and every `model_calls` row already pointing at it keeps resolving. No admission state permits Val to add a provider, widen an eligibility class, or grant herself a capability — admission is set in the registry, which is committed, reviewed, and hers to read rather than to write (invariant 2).

> **Amendment — 15 August 2026, Lord Armand, from external architecture review.** Qualification for any new model configuration is a **system-specific exam suite run against this system's actual workload**, built at Layers 2–3: identity adherence under the persona, structured-output reliability, uncertainty handling — including the trap questions of `04-layer-0.md` WP-0.7 — cost per task class, and long-conversation behaviour. The standing rule: **a working model is never replaced because a benchmark sounds impressive.** Candidates run as experiments against the incumbent, and the prediction ledger (`02-partner-systems.md` §4.6) arbitrates.

### 5.3 The cost gradient

The right shape is a gradient, not a local/cloud binary:

| Work | Route |
|---|---|
| Classification, routing decisions, summarization, self-evaluation iteration, preference-stripping, first drafts, standing loops | **Local** (from Layer 1; §2.1) |
| Bulk work where quality tolerance is moderate | **Inexpensive cloud** (Gemini Flash class, on a paid-billing key) |
| Genuinely hard reasoning, adversarial review, final judgment | **Frontier** (Anthropic, OpenAI, Gemini Pro class) |

**The architecture requires a provider-neutral gateway and multi-provider routing. It does not name the roster.** Which providers are live at any moment is controlled configuration, not architectural law — it is the Model Configuration Registry's answer, and it changes without amending this document. See §5.2.1.

**Prompt caching and batch pricing are first-class, not optimizations.** Val's workload is unusually repetitive-context-heavy: persona, project canon, and Role knowledge are re-injected constantly. Caching is therefore a structural saving rather than a tuning exercise, and context assembly shall be ordered stable-prefix-first so cached segments actually hit. Non-urgent overnight work routes through batch APIs.

### 5.4 Data classification eligibility

Val's primary asset is unreleased creative IP. Provider retention and training policies differ, and eligibility is not a cost question.

**Every piece of content carries a classification before it may leave the house.** Every model configuration declares which classifications it is eligible to receive. Content is never routed to an ineligible configuration (invariant 17).

| Classification | Content | Routing |
|---|---|---|
| **Public** | Published material, general research, public reference | Any eligible route |
| **Internal** | Working notes, plans, non-sensitive drafts, system operation | Any route meeting standard retention terms |
| **Protected** | Unreleased creative IP — scripts, boards, designs, canon, production assets | Only routes explicitly declared eligible |
| **Restricted** | Credentials, financial detail, personal data of third parties | Local inference only. Never leaves the machine. |

Rules:

- Classification is deterministic and computed before routing, never inferred by the model that will receive the content.
- Where classification is ambiguous, the **higher** classification applies.
- Cost, latency, and availability never override eligibility. If no eligible route is available, the work waits or runs locally; it does not downgrade the content.
- Fallback routes are checked for eligibility independently. A fallback is not inherited.
- A retrieval that would mix classifications into one context assembles at the highest classification present.

Eligibility is set by Lord Armand per provider, recorded in the registry, and reviewed when a provider changes its terms. Val does not set her own eligibility (invariant 2).

**Amendment — 15 August 2026, decided by Lord Armand.** The mechanism above governs **every external egress path, not only model configurations.** Any component that sends content off the machine — model providers, TTS, avatar generation, backup transport, any future external API — declares which classifications it may receive and is checked identically. Same rule, wider scope. Invariant 17 already said content is classified before it leaves the house; this closes the gap where only model routes were mechanically covered.

#### Eligibility decisions — 15 August 2026, Lord Armand

| Provider | Ruling | Grounds |
|---|---|---|
| Anthropic API | **Protected-eligible** | Commercial Terms: no training on API content without express permission. **Retention premise re-verified 18 August 2026, decided by Lord Armand** against `platform.claude.com/docs/en/manage-claude/api-and-data-retention`: conversation content is **not retained by default** on the Claude API for the models VAL uses — the 30-day retention requirement applies only to designated Covered Models (Claude Fable 5, Claude Mythos 5), which are not in VAL's registry. The former "7-day default retention" premise was stale and is superseded; the current verified terms are stronger. If a Covered Model is ever proposed for the registry, its 30-day retention is a new eligibility decision, not an inheritance. Restricted data remains prohibited regardless. |
| OpenAI API | **Protected-eligible** | No training on API content by default; 30-day abuse-monitoring window |
| Google Gemini API, **paid billing only** | **Protected-eligible only with verified paid billing** | Google uses free-tier content to improve its products, with possible human review. A billed and an unbilled key are indistinguishable in code, so the distinction is enforced **structurally**: a Gemini configuration must verify at startup that its key is attached to a paid billing account, and startup fails if that cannot be confirmed. Configuration claiming it is not acceptance. |
| GLM via Zhipu/Z.ai direct | **Excluded — pending verification**, not permanently | Not for stated policy but for unverifiability: two legal entities, mainland terms unreviewable as of July 2026, and an individual-user carve-out differing from the API/DPA posture. GLM's weights are open, so a US-hosted route with SOC 2 and zero-data-retention terms, or self-hosting, can qualify later on its own merits. |

### 5.5 The budget envelope

**Total monthly envelope: $250.** The routing ceiling is a subset of it.

| Line | Amount | Enforced |
|---|---|---|
| Cloud model inference — **the routing ceiling** | $200 | Pre-call, by the gateway |
| ElevenLabs TTS subscription | ~$25 | Tracked, not gated |
| Other — avatar generation, storage, paid tool APIs | ~$25 | Tracked, not gated |

Fixed subscriptions are not routable and are therefore not gated. They are tracked against the envelope so total outlay is visible.

**Local inference never counts against the ceiling and is never throttled when the cloud budget is tight.** It is free at the margin, and absorbing volume is its entire purpose. Throttling local work to protect a cloud budget is backwards.

**Reserve.** 15% of the ceiling ($30) is held in reserve and unlocks only on explicit approval from Lord Armand. The routine allowance is therefore $170. This exists so that a genuinely urgent task late in the month is not blocked by routine spend earlier in it.

**Threshold behavior**, measured against the routine allowance:

| Point | Behavior |
|---|---|
| 70% | Notify. No change in routing. |
| 85% | Prefer cheaper routes. Route to local or low-cost cloud unless the work genuinely requires frontier reasoning. |
| 100% | Cloud routing stops. Reserve available on explicit approval only. |

The ceiling resets monthly. The cost view shows a rolling window, not only a month-to-date total, so a spending pattern is visible before the month ends.

**Attribution.** Every call records project and task type, so it is visible *where* money goes rather than only how much remains.

Two task types are broken out as their own categories in the cost view, because both scale with production volume rather than with conversation and are the first places to look when spend surprises:

- **Frontier vision passes** — the final gate on visual work (`02-partner-systems.md` §3.1)
- **Blind position calls** — the second call on consequential exchanges (`02-partner-systems.md` §4.1)

Neither is optional and neither should be silently absorbed into a general total.

### 5.6 Degradation

**Val degrades. She does not halt** (invariant 25).

At the ceiling she continues operating on local inference and states plainly what she can and cannot do until reset. She does not go quiet, and she does not fail requests without explanation.

**She never silently produces worse work to stay under budget** (invariant 26). If the budget is forcing a lesser model onto work that deserves better, she says so at the time — before the work, not in a footnote after it. A quietly degraded deliverable is worse than a refused one, because it enters the project as though it were sound.

### 5.7 What Layer 0 implements

Layer 0 takes the capture obligation and the crudest possible guard, and nothing else:

**In scope at Layer 0:**

- Per-call record: model configuration, provider, tokens in and out, computed cost **or an explicit unknown**, project, task type
- One hard stop: **a call is admitted only if what it is authorised to consume fits inside what is left of the ceiling**

The hard stop is not sophisticated and is not meant to be. It exists because a runaway loop is a real risk at this budget, and a crude backstop that exists beats a graduated one that does not.

**Not in scope at Layer 0:** the 70/85/100% thresholds, the reserve, the cost dashboard, the graduated cost gradient, or the rolling view.

> **Amendment — 17 August 2026, Lord Armand, after external review.** The hard stop as first written was `month_to_date_spend < CEILING`. That is enforced before the call and enforces nothing *about* the call: at $199.99 of $200 it admitted a call of any size, and the breach was discovered by reading the record afterwards. Invariant 24 says the ceiling is enforced before a call and never reported after; the old rule satisfied the letter and inverted the point.
>
> **The rule is now `committed + maximum_cost(this call) ≤ CEILING`**, where `maximum_cost` is an arithmetic upper bound on what the call may consume — not an estimate — and `committed` is the authoritative figure held in PostgreSQL: settled spend, plus every reservation still outstanding, plus reservations abandoned by a process that died.
>
> Three consequences, each deliberate:
>
> - **The ceiling figure is $200, unchanged.** Nothing here raises it. A control that was not enforcing it now does.
> - **Admission is a database reservation with a lifecycle** — reserved, settled, released, expired — taken under a lock, so two processes cannot each observe the same headroom and together spend it. Schema: `04-layer-0.md` §2.5.
> - **An unknown cost is never recorded as zero.** A call that reached the provider consumed input tokens whether or not the response survived; its reservation stays charged and its record says the cost is unknown. `04-layer-0.md` §2.2.
>
> **Route selection at Layer 0 is admitted-and-eligible first, cost second.** The gateway selects the configuration rather than requiring every caller to name one — a caller that must name its own provider is a caller that can name the wrong one. Cost ranks only what eligibility has already admitted, which is what `04-layer-0.md` §1.1 permits. This is not the graduated gradient of §5.5; that remains Layer 3.

**The graduated behavior of §5.5 arrives at Layer 3.** Layer 3 is when Roles spawn working agents and call volume genuinely multiplies — one request becoming a dozen calls across producer and reviewer Roles. That is the point at which the crude hard stop stops being adequate, because the gap between "fine" and "ceiling breached" can now be crossed inside a single task. Layers 1–2 add local inference and read-only tools; neither materially changes spend shape, so the hard stop carries them.

Cost is not a Layer 4 concern. Layer 4 governs consequence, and spending is only one narrow instance of it.

---

## 6. Governance by tier

Tier definitions and the escalation rules are in `00-charter.md` §5. This is how each tier is handled.

| Tier | Handling |
|---|---|
| **0** | Direct gateway call. No Assignment, no Role pipeline, no independent review, no workflow orchestration, no audit chain. Logged for observability and cost only. |
| **1** | Role pipeline. Independent review is policy-tunable — structured self-critique may suffice for low-stakes drafts. No approval required. Internal state only. |
| **2** | Full pipeline. Independent review by a Role that did not produce the work. Approval required. Versioned write. Verification of resulting state. Audit. |
| **3** | As tier 2, plus explicit approval naming the specific act, a recorded rollback plan, and independent verification before completion is claimed. |
| **4** | As tier 3. **No autonomous execution at any maturity.** Reserved to Lord Armand (`00-charter.md` §5.1). |

Classification is a deterministic step at the front of the pipeline, executed before any model is consulted, and recorded. It is not a subsystem — it is a function of action class, target, and context.

The overwhelming majority of daily interaction is tier 0. That is the point: the protective machinery sits entirely out of the path of ordinary conversation, so it can be as heavy as it needs to be where it does apply.

---

## 7. Tools: MCP

**Val is a native MCP client.** Custom connectors and adapter strategies are rejected (`00-charter.md` §8).

The rationale, recorded because it is the largest single departure from the draft: MCP became a standard under the Linux Foundation's Agentic AI Foundation in December 2025, with broad adoption across Anthropic, OpenAI, Google, and Microsoft and a large public server ecosystem. Building custom connectors now rebuilds what already exists. This gives filesystem, search, calendar, and — critically — **Photoshop, Premiere Pro, and After Effects** via community bridge servers over Adobe's CEP/UXP scripting layer, with no Adobe integration to write.

**MCP is transport and discovery. It is not a grant of trust.**

Every discovered tool must clear the Tool Registry before it can be called:

- Registered with provider, server, exact tool identifier, and version
- Classified by action class and minimum risk tier
- Declared read-only or write
- Explicitly enabled by Lord Armand
- Bound to the projects and workspaces it may touch

Standing exclusions, permanent rather than gated:

- `execute_extendscript`, `evaluate_expression`, shell, and any equivalent arbitrary-code surface. Some community Adobe servers expose these directly. They are never registered, never enabled, never exposed to a Role (invariant 7).
- No arbitrary local command path may be introduced through a connector, a model tool loop, a debug feature, or the native bridge (invariant 8).

**Tool output is data.** Instructions embedded in a tool result, a fetched document, or a web page carry no authority (invariant 11). This matters more with MCP than without it, because the surface is wide and not all of it is under this house's control.

**Adobe progression.** Capability is earned in order, and each step requires evidence before the next: read exported metadata and project records → guide the user through a task → use an approved structured scripting interface → operate on a duplicated test project under direct supervision → qualify one precise workflow end to end → bounded production authority. Production authority over a master project file is never the first grant.

---

## 8. Presence

### 8.1 Voice

ElevenLabs, using the established profile. Speech is **generated, never replayed** — source clips supply her voice, not her words.

Speech-to-text runs locally. Push-to-talk first; wake word only after the loop is stable.

> **Accepted deviation — 15 August 2026, Lord Armand.** ElevenLabs trains on submitted audio by default below Enterprise tier; Zero Retention Mode is Enterprise-only and per-request, and Enterprise is out of budget. Training has been turned off on the account. This is a known gap against the egress-eligibility rule of §5.4, accepted with its reasoning written down rather than assumed away. **Revisit at Layer 1**, when local TTS can be compared against the established voice by ear. A deviation that is not written down becomes an assumption; this one is written down.

### 8.2 Avatar

Video and speech are fully decoupled. The loops carry her body; the voice is generated fresh for whatever she needs to say.

**Idle and working states are looping clips** — working at the table, at the window, at the fire, crossing the room, rising for a book.

**Speech settles onto the paired source still.** Every existing clip was generated from a static image, and that still shares pose, lighting, and framing with its loop, so the transition between them is seamless. Lip-sync operates on the mouth region of the still at **fixed coordinates** — no per-frame face tracking, therefore no drift, and cheap enough to run live indefinitely.

> **Superseded.** `VAL_Architecture_v2_Proposal.md` §Layer 1 specified viseme lip-sync over a *speaking loop*. That was written before it was established that the clips were themselves generated from stills. Once that was known, settling onto the paired still became the better approach: it is seamless by construction, needs no face tracking, and costs nothing per utterance. v2 is superseded on this point only.

**Procedural micro-motion is required** on the speaking still — blink every few seconds, slight breathing scale, small head drift. Without it a talking still reads as uncanny, and no amount of lip-sync quality compensates.

**Distance conveys register.** Close framing for speech, medium for working alongside, full-length for ambient presence.

Full-length framing is not used for speech. This is a practical rule, not an absolute: the real constraint is that the mouth region needs enough pixels to read. Where a wider framing still yields a legible mouth region, it is usable; where it does not, it is not.

**Books signal working state.** A volume in her hands or open before her means she is working. Away from them she is at rest, listening, or thinking. This is legible at a glance and removes the need for an interface element to convey her state. State definitions: `03-persona.md` §6.

**Val curates her own visual library.** She works from existing loops, identifies states she lacks, and proposes generating them. Lord Armand approves them into the library, including the generation cost. New footage is generated from the same source stills so she remains visually consistent.

**Format.**

- Existing footage is **1248×1664 at 24fps** — tall portrait. *Verified from the video files.*
- A full-height column in the interface is **recommended**, not required. *Recommendation, not a measured constraint.*
- Existing stills are **not** a single aspect ratio; they range from roughly 2:3 to 4:5. **Open action item:** standardize future stills on one ratio. Until that is settled, the interface must tolerate variable source ratios without cropping her out of frame.

### 8.3 Failure

Voice or avatar failure degrades to text and never breaks core operation (invariant 27).

Animation is presentation only. It never implies that an action succeeded, an approval was given, or work completed (invariant 28). If the avatar shows *presenting* and the record shows *pending*, the record is correct and the interface is wrong.

---

## 9. Durability and recovery

The authoritative store holds the books, execution history, deliberation records, the prediction ledger, project canon, and the asset registry. §1 argues that this data is impossible to reconstruct and must therefore be captured from Layer 0. **That argument applies with identical force to losing it after capture.** Captured-then-lost and never-captured are the same outcome, and the second is easier to bring about.

Backup begins at Layer 0, alongside the three capture obligations, and for the same reason: cheap to establish now, impossible to establish retroactively over data that is already gone.

### 9.1 What is backed up

- **PostgreSQL in full** — every table, not a curated subset. Curation is how the important table gets missed.
- **Baseline documents and the persona specification**, versioned. These are governing text; losing an edited persona is losing an authored artifact.
- **Configuration**: model configuration registry, Tool Registry state, project workspace registrations, classification eligibility settings.
- **Encryption keys, stored separately from the backups themselves.** A backup that cannot be decrypted is not a backup.

Model provider caches, embeddings, and derived indexes are excluded. They are reconstructible from the store, which is what makes them derived.

#### 9.1.1 Two recovery domains, not one — clarification, 17 August 2026

§9.1 lists five things to protect and one mechanism was implemented for them all. It is worth being exact about which mechanism covers what, because "it's backed up" covering two different things by two different means is how one of them turns out not to be.

| What | Protected by | Recovers to |
|---|---|---|
| PostgreSQL, in full | **pgBackRest → Backblaze B2**, encrypted, WAL-archived | Any moment inside retention |
| Governing baselines (`docs/baselines/`) | **Git → GitHub**, private remote | Any commit |
| Persona source (`03-persona.md`) | **Git → GitHub** | Any commit |
| Migration history (`packages/domain/migrations/`) | **Git → GitHub** | Any commit |
| Repository configuration needed to rebuild Val | **Git → GitHub** | Any commit |
| Application source and non-secret configuration | **Git → GitHub** | Any commit |
| Credentials and the backup passphrase | **Neither.** Held outside both, deliberately | §9.2, and paper |

**GitHub is the stated off-machine protection for everything the repository controls.** That is a decision, recorded here rather than left implicit: the remote is private, it is off this machine, it holds full history, and every commit is a restore point.

**It does not replace PostgreSQL point-in-time recovery, and nothing may imply that it does.** The two protect disjoint things. Git holds the text Val was built from; PostgreSQL holds what she has learned, decided, spent, and been told. A repository restored perfectly onto a machine with no database gives a Val with her character and none of her memory. The three capture obligations of §1 live entirely in the second column.

**Repository recovery is verified the same way any backup is** — by doing it, not by assuming it: clone the remote to a machine that has never held the project, build from the documented sequence with no undocumented step, and confirm the baselines and the persona are byte-identical to the working copy. This is the clean-clone check WP-0.1 already requires; it is named here as the repository's restore verification so that it is not left as a build test that happens to double as one.

**No secret is ever committed.** `.env` is ignored and cannot be added; the backup passphrase and B2 credentials live in a 0600 file outside the repository and on paper. A repository backup that carried them would put every credential wherever the repository goes, which is the opposite of protection.

### 9.2 How

| Requirement | Specification |
|---|---|
| Schedule | Automated daily, plus on demand before any schema migration |
| Encryption | Encrypted at rest and in transit; key held separately from backup storage |
| Location | **Off-machine.** A backup on the same physical machine protects against nothing that is likely to happen. |
| Point-in-time recovery | WAL archiving enabled, so recovery targets a moment rather than the last snapshot |
| Automation | No step depends on a human remembering. An unautomated backup is an intention. |

#### Backup-transport eligibility — 18 August 2026, decided by Lord Armand

The 15 August egress amendment (§5.4) requires every external egress path to
declare which classifications it may receive. The backup channel's declaration
is recorded here:

**VAL's encrypted pgBackRest → Backblaze B2 channel may carry every
classification legitimately present in authoritative PostgreSQL, including
sensitive material**, provided all of the following hold:

- encryption occurs **before** transmission, and the encryption configuration
  is verified;
- the credential remains **bucket-scoped**;
- the destination is the designated VAL backup repository and nothing else;
- the permission covers **backup ciphertext only**.

This does not authorise arbitrary B2 uploads, and it does not broaden any
cloud-model or tool egress. It is transport eligibility for one channel whose
payload is ciphertext of the store the channel exists to protect.

### 9.3 Retention and verified restore

**Retention: 30 daily, 12 weekly, 12 monthly** — roughly a year of coverage. The requirement driving this is not disaster but *late discovery*: a corrupted lesson record, a bad distillation, or a silently failing capture may not be noticed for weeks. Retention must outlive the discovery lag, not just the incident.

**Restores are verified on a cadence — quarterly at minimum.** A verified restore means restoring to a scratch instance and checking that the data is actually there and coherent: row counts against expectation, the books readable, execution history and deliberation records continuous with no unexplained gaps, referential integrity intact.

**A backup that has never been restored is not a backup.** It is an assumption with a filename, and it fails at the only moment it is needed (invariant 35).

Backup capability being unavailable is a degraded state Val reports plainly. It does not block ordinary Layer 0 work. It does block schema migrations and the §9.4 migration.

### 9.4 The Layer 3 migration

Moving the authoritative store from the MacBook to the always-on box is the single highest-risk data moment in the build, and it is the one moment when the store exists in two places and neither is obviously canonical.

It is a **governed, verified migration**, never an implicit copy:

1. Stand up the target: Postgres, extensions, schema at the identical migration revision.
2. Take a fresh full backup of the source and verify it restores — before touching anything.
3. Replicate to the target.
4. **Verify against the source**: row counts per table, checksums, referential integrity, and a manual spot check that the books, execution history, and deliberation records are complete and continuous.
5. Run the target read-only in parallel briefly. Confirm the application reads correctly from it.
6. Cut over. The target becomes authoritative at one recorded moment, not gradually.
7. **Leave the source machine's data intact and untouched for a defined period** — thirty days minimum — before the MacBook is reused for anything. Do not delete the old store on the day the new one appears to work.

Step 7 is the one that gets skipped, and it is the one that saves the migration when a problem surfaces a week later.

---

## 10. Timeline

Roughly 14–19 weeks to the complete system.

The material property is not the total but the shape: **useful from week three, conversational from week six.** Every subsequent layer is built on something already in daily use, so design decisions are made against real experience rather than speculation — which is the actual argument for this ordering, more than time to completion.

| Layer | Estimate |
|---|---|
| 0 — Core loop | 2–3 weeks |
| 1 — Presence | 2–3 weeks |
| 2 — Hands | 2 weeks |
| 3 — Agents | 4–5 weeks |
| 4 — Consequence | 2–3 weeks |
| 5 — Learning | 2–3 weeks |

Estimates assume one person with AI assistance and no parallel work. The 14–19 range is the sum of this table and supersedes the 14–18 figure carried from `VAL_Architecture_v2_Proposal.md`.
