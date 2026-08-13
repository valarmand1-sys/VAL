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

**Local inference is a Layer 1 deliverable, not a Layer 3 one.** A ~30B-class model at 4-bit runs on the existing 48GB MacBook and serves Layers 1–2 from there; it moves to the always-on box at Layer 3 (§4) as a relocation, not a first installation.

The reason for standing it up this early is that the cost gradient (§5.3) is fiction until local exists. Every routing decision before that point is cloud-to-cloud, the ceiling does no real work, and the assumptions behind the budget go untested. Layer 1 is also when speech-to-text arrives, so on-device inference is being set up regardless. Exercising the gradient under Layer 1–2 volume — where the consequences of getting it wrong are a slow reply — is materially safer than first exercising it at Layer 3, when agents multiply call volume.

Failure behavior: §8.3.

This layer lands early deliberately. It is the difference between a chat application and Val, and that difference determines whether the system is used at all. A correct system nobody opens has failed.

### 2.2 Layer 2 — Hands

*Val can reach the outside world.*

Val is a native MCP client (§7). Governance enters here because there is now something to govern:

- Every discovered tool enters the **Tool Registry**, is classified by action class and minimum risk tier, and is explicitly enabled. Discovery is never authorization (invariant 6).
- **Read-only tools first.** Write tools remain disabled until Layer 4.
- **Arbitrary-code tools are permanently excluded, not gated** (invariants 7, 8).

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
| Local inference | ~30B-class quantized | A 32B model at 4-bit sits comfortably in 48GB |
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
| Routing | Select a qualified model configuration on capability, **data classification eligibility**, cost, latency, availability |
| Budget enforcement | Check the ceiling **before** the call is made (invariant 24) |
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
- Fallback route, activation date, retirement state

Routing selects among configurations. It never selects a raw model.

### 5.3 The cost gradient

The right shape is a gradient, not a local/cloud binary:

| Work | Route |
|---|---|
| Classification, routing decisions, summarization, self-evaluation iteration, preference-stripping, first drafts, standing loops | **Local** (from Layer 1; §2.1) |
| Bulk work where quality tolerance is moderate | **Inexpensive cloud** (GLM, Gemini Flash class) |
| Genuinely hard reasoning, adversarial review, final judgment | **Frontier** (Anthropic, OpenAI, Gemini Pro class) |

Multi-provider from day one: Anthropic, OpenAI, Gemini, GLM, plus local — all behind §5.1.

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

- Per-call record: model configuration, provider, tokens in and out, computed cost, project, task type
- One hard stop: if month-to-date cloud spend exceeds the ceiling, cloud routing stops

The hard stop is not sophisticated and is not meant to be. It exists because a runaway loop is a real risk at this budget, and a crude backstop that exists beats a graduated one that does not.

**Not in scope at Layer 0:** the 70/85/100% thresholds, the reserve, the cost dashboard, per-route preference logic, or the rolling view.

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

### 9.2 How

| Requirement | Specification |
|---|---|
| Schedule | Automated daily, plus on demand before any schema migration |
| Encryption | Encrypted at rest and in transit; key held separately from backup storage |
| Location | **Off-machine.** A backup on the same physical machine protects against nothing that is likely to happen. |
| Point-in-time recovery | WAL archiving enabled, so recovery targets a moment rather than the last snapshot |
| Automation | No step depends on a human remembering. An unautomated backup is an intention. |

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
