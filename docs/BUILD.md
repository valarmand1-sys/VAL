# Build

The complete sequence for a machine that has never seen this project. There is no
step that is not written here, and no step that depends on anything already
installed beyond `git`, `curl`, and — on macOS — the Xcode Command Line Tools.

Every version installed below is read from a file in the repository rather than
passed on a command line, so there is nothing to keep in sync by hand. What each
version is and where it was resolved from: [`TOOLCHAIN.md`](TOOLCHAIN.md).

---

## Prerequisites

macOS (the Layer 0 machine, per `baselines/04-layer-0.md`):

```bash
xcode-select --install
```

Linux, for the desktop shell only, needs WebKitGTK and its build dependencies;
see Tauri's prerequisites. The Python service and every check below run on Linux
with no additional system package.

## 1. Clone

```bash
git clone <repository-url> val
cd val
```

## 2. Python

`uv` installs the interpreter as well as the packages. It reads `3.14.7` from
`.python-version` and the dependency set from `uv.lock`.

```bash
curl -LsSf https://astral.sh/uv/0.12.3/install.sh | sh
```

```bash
uv python install
```

```bash
uv sync --all-packages --locked
```

`--locked` fails rather than silently re-resolving if `uv.lock` does not match the
manifests.

## 3. Node

Install Node 24.19.0. With `nvm`, the version is read from `.nvmrc`:

```bash
nvm install
```

Then install the locked dependency set:

```bash
npm ci --prefix apps/desktop
```

`npm ci` installs `package-lock.json` exactly and fails if it disagrees with
`package.json`.

## 4. Rust

`rustup` reads `rust-toolchain.toml` and installs 1.97.1 on first use, so no
toolchain is named on the command line:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain none --profile minimal
```

---

## Verify

The same commands CI runs, in the same order. All of them must pass.

```bash
uv run --no-project python infrastructure/ci/check_pins.py
```

```bash
uv run python infrastructure/ci/check_boundaries.py
```

```bash
uv run lint-imports
```

```bash
uv run ruff check .
```

```bash
uv run ruff format --check .
```

```bash
uv run mypy
```

```bash
uv run pytest
```

```bash
npm run build --prefix apps/desktop
```

```bash
cargo build --locked --manifest-path apps/desktop/src-tauri/Cargo.toml
```

## Run the desktop shell

```bash
npm run tauri --prefix apps/desktop dev
```

At Layer 0 this opens a window and nothing more. The text interface is WP-0.10.

---

## What the checks enforce

| Command | Enforces |
|---|---|
| `check_pins.py` | No placeholder token, no version range, no moving action tag, all three lock files present |
| `check_boundaries.py` | Dependency direction across Python, TypeScript, and Rust, plus manifests |
| `lint-imports` | Dependency direction through transitive Python imports |
| `ruff`, `mypy`, `pytest` | Lint, format, types, and the checkers' own tests |

`check_boundaries.py` and `lint-imports` overlap deliberately. `lint-imports`
follows real Python imports transitively but cannot see `apps/desktop`, which is
TypeScript and Rust, and cannot see a dependency declared in a manifest but not
yet imported. `check_boundaries.py` covers both and every language. Neither
subsumes the other.

The allowed dependency edges live in `infrastructure/ci/components.toml`.
Widening them is an architecture decision (`01-architecture.md` §3), not an
implementation one.

## Regenerating the desktop icons

Only needed if the mark changes:

```bash
npm run tauri --prefix apps/desktop icon src-tauri/icons/source-1024.png
```

Delete the generated `android/` and `ios/` directories afterwards; Tauri mobile is
not in scope.
