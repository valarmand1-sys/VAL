# Toolchain

Every version the build depends on, the exact value it is pinned to, and where
that value was resolved from. Resolved 12 August 2026 for WP-0.1.

Nothing here was recalled. Each version was read from the publisher's own index
or release channel on the date above. When a version is raised, it is re-resolved
the same way and this table is updated in the same commit as the manifest.

Pins are enforced by `infrastructure/ci/check_pins.py`, which runs in CI and
fails on any range, any moving tag, and any placeholder token.

---

## Runtimes

| Tool | Pinned | Pinned in | Resolved from |
|---|---|---|---|
| CPython | 3.14.7 | `.python-version` | `python.org` release index — current release of the current 3.14 line |
| Node.js | 24.19.0 | `.nvmrc`, `apps/desktop/package.json` `engines` | `nodejs.org/dist` — current release of the v24 "Krypton" line |
| Rust | 1.97.1 | `rust-toolchain.toml` | `static.rust-lang.org` stable channel, released 14 July 2026 |

**Node 24, not 26.** Node 26 is Current as of August 2026 and does not enter LTS
until November. Node 24 is Active LTS. `nodejs.org` release status was checked
rather than assumed.

**Rust 1.97.1 against Tauri's floor.** `tauri` 2.11.5 and `tauri-build` 2.6.3
declare `rust-version = 1.77.2`. The pinned toolchain clears it.

## Package managers

| Tool | Pinned | Pinned in | Resolved from |
|---|---|---|---|
| uv | 0.12.3 | `pyproject.toml` `[tool.uv] required-version`, CI, `docs/BUILD.md` | PyPI |
| npm | 11.17.0 | bundled with Node 24.19.0 | `nodejs.org/dist` index |
| cargo | 1.97.1 | bundled with the pinned Rust toolchain | `static.rust-lang.org` |

## Python packages

All resolved from PyPI. Every one declares support for Python 3.14.

| Package | Pinned | Used by |
|---|---|---|
| pydantic | 2.13.4 | `packages/domain` |
| fastapi | 0.141.1 | `apps/api` |
| uvicorn | 0.52.1 | `apps/api` |
| pydantic-settings | 2.15.0 | `apps/api` |
| hatchling | 1.32.0 | build backend, every workspace package |
| ruff | 0.16.2 | workspace dev group |
| mypy | 2.3.0 | workspace dev group |
| pytest | 9.1.1 | workspace dev group |
| import-linter | 2.13 | workspace dev group |

Resolution is locked in `uv.lock`, which covers the transitive set as well.

## Node packages

All resolved from the npm registry.

| Package | Pinned |
|---|---|
| react | 19.2.8 |
| react-dom | 19.2.8 |
| @tauri-apps/api | 2.11.1 |
| @tauri-apps/cli | 2.11.4 |
| @types/react | 19.2.18 |
| @types/react-dom | 19.2.4 |
| @vitejs/plugin-react | 6.0.5 |
| typescript | 7.0.2 |
| vite | 8.2.1 |

Locked in `apps/desktop/package-lock.json`.

**TypeScript 7.0.2.** TypeScript 7 is the native compiler, released 8 July 2026.
Microsoft states its type-checking is structurally identical to 6.0 and that code
compiling cleanly under 6.0 compiles identically under 7.0. It ships `tsc` under
the same `typescript` package name. `@vitejs/plugin-react` 6.0.5 declares a peer
range of `vite ^8.0.0`, satisfied by Vite 8.2.1; both require Node `>=22.12.0`,
satisfied by Node 24.19.0.

## Rust crates

All resolved from crates.io. Locked in `apps/desktop/src-tauri/Cargo.lock`.

| Crate | Pinned |
|---|---|
| tauri | 2.11.5 |
| tauri-build | 2.6.3 |
| serde | 1.0.229 |
| serde_json | 1.0.151 |

Cargo treats a bare version string as a caret range, so every crate is written
`"=x.y.z"`. `check_pins.py` rejects the bare form.

## GitHub Actions

Actions are pinned to a full commit SHA rather than a tag, because a tag can be
moved. The release each SHA corresponds to is recorded in a trailing comment in
the workflow and here.

| Action | Release | Commit |
|---|---|---|
| actions/checkout | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| actions/setup-node | v7.0.0 | `820762786026740c76f36085b0efc47a31fe5020` |
| astral-sh/setup-uv | v10.0.0 | `ae62891fec2bb8e7d6c99fc78c9fec3a63790f8d` |

Runner images are named explicitly rather than by a floating label: `ubuntu-24.04`
and `macos-15`, both generally available per GitHub's runner-image reference.
Neither is a preview image.

---

## Deliberately not pinned yet

`01-architecture.md` §3 names SQLAlchemy and Alembic in the stack. They are not
pinned here, because a version pinned and never built is an assertion rather than
a verified fact — the same objection the charter makes to an unrestored backup
(invariant 35). WP-0.2 introduces the schema and the migration set, and pins both
against the registry at that point, by the process above.

Provider SDKs are pinned at WP-0.4 for the same reason. Temporal is Layer 3 and
is not pinned at all yet.

## Dependencies pinned ahead of first use

Three dependencies are declared and locked before any code imports them, because
WP-0.1 owns toolchain pinning and `01-architecture.md` §3 names them as the
stack: `fastapi`, `uvicorn`, and `pydantic-settings` in `apps/api`;
`@tauri-apps/api` in the desktop shell; `serde` and `serde_json` in the Tauri
crate. Each is installed, locked, and compiled by CI, so the pin is exercised
rather than asserted.
