# Val

A general-purpose personal AI and permanent working partner for House Armand.

**This repository contains no implementation yet.** It holds the governing specification and the directory structure the build will fill.

---

## Read this first

**[`/CLAUDE.md`](CLAUDE.md)** — standing operating instructions. Loaded every session by Claude Code. Read before touching anything.

---

## The baselines govern

The five documents in [`/docs/baselines/`](docs/baselines/) are the specification. **They are authoritative.** Code that contradicts them is wrong, not a new decision.

| Document | Authoritative on |
|---|---|
| [`00-charter.md`](docs/baselines/00-charter.md) | What Val is, the four states, risk tiers, non-negotiable invariants, honest limits, what was rejected and why |
| [`01-architecture.md`](docs/baselines/01-architecture.md) | Capability layers, stack, machine topology, model routing, budget, data classification, MCP and tool governance, avatar, backup |
| [`02-partner-systems.md`](docs/baselines/02-partner-systems.md) | Roles and their knowledge bases, the books, self-evaluation, deliberation and the prediction ledger, success models |
| [`03-persona.md`](docs/baselines/03-persona.md) | Voice, manner, bearing, conduct. Loaded whole into every context. |
| [`04-layer-0.md`](docs/baselines/04-layer-0.md) | Layer 0 scope, schema, work packages, acceptance criteria, the gate |

**Precedence on conflict:** an explicit current decision by Lord Armand → the charter → the baseline that owns the topic → repository configuration and migrations → individual changes.

When two requirements cannot both be satisfied, or when an observed fact contradicts the specification: **stop, state the conflict, recommend a resolution, and wait for the decision.** Do not implement around it. See `/CLAUDE.md`.

---

## Build order

Val is built in capability layers, each independently usable. Governance arrives when there is something to govern.

| Layer | Delivers | Status |
|---|---|---|
| **0** | Core loop — exists, remembers, useful across projects | **Authorized. Current work.** |
| 1 | Presence — voice, face, local inference | Not started |
| 2 | Hands — MCP tools, read-only | Not started |
| 3 | Agents — Roles, supervision, review | Not started |
| 4 | Consequence — real changes to real things | Not started |
| 5 | Learning — expertise accumulation | Not started |

**Only Layer 0 is authorized.** Later-layer capability is not implemented early merely because its design exists.

---

## Structure

```
/apps/desktop        Tauri 2 + React/TypeScript shell
/apps/api            FastAPI service
/apps/worker         Background workers; Temporal from Layer 3
/packages/domain     Schemas and typed contracts
/packages/providers  Model provider adapters
/packages/policy     Deterministic classification and permission evaluation
/packages/mcp        MCP client and Tool Registry
/infrastructure
/docs
```

Dependency direction is enforced in CI:

- `policy` depends on `domain` only — never on `desktop`, `api`, `worker`, or `providers`
- `worker` never depends on `desktop`
- `providers` never depends on `policy` — routing asks policy; policy never asks a provider
- No circular package dependencies

`policy` is the boundary that matters most. It decides whether a consequential action may occur, and must remain callable, testable, and correct with no application running.

---

## Getting started

There is nothing to run yet. The first work order is **WP-0.1** in [`04-layer-0.md`](docs/baselines/04-layer-0.md) §3 — repository and toolchain.

Toolchain versions are deliberately unpinned in this commit. WP-0.1 requires them resolved against current official documentation rather than guessed in advance.

---

## History

The specification supersedes a 379-page draft. See [`docs/ARCHIVE-NOTE.md`](docs/ARCHIVE-NOTE.md) before consulting any earlier document.
