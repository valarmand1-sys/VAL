# VAL historical cleanup record — 18 September 2026

Owner instruction and approval, 18 September 2026. Phase One was a read-only audit of the whole project history; Phase Two executed only the audited manifest as amended by the owner. **No authoritative history was destroyed.**

## Phase One findings

- **No complete source file or architecture implementation met the proof standard for SAFE TO DELETE — OBSOLETE ARCHITECTURE.** The earlier architecture changes were replacements in place, not parallel abandoned implementations. Method: an import graph over all 64 source modules, a reference count for every top-level function and class, a TypeScript import check for the desktop, reference checks for every infrastructure script, environment variable and declared dependency, and a parse of the migration chain.
- One virtual environment, one Node tree, one Rust toolchain, one Python. Every declared dependency is imported; every variable in `.env.example` is read by code. No snapshot zip, copied repository or exported source tree survives anywhere.
- Models verified on disk: GPT-OSS (LM Studio, 11.25 GiB) and Gemma 4 31B Q6_K (23.47 GiB) only. Qwen and Mistral verified absent with no partials or cache remnants; no Hugging Face or llama.cpp download cache exists.
- Nine byte-identical duplicate groups among tracked files (76 KB): per-run frozen harness and corpus copies, kept as historical evidence, and `docs/reviews/governing/`.
- **Fourteen log files cited as evidence existed only in the working tree** because `*.log` is ignored.
- Kept by owner decision and untouched: GPT-OSS (the retained LM Studio regression fixture for exact local preflight and the wire seams); `google_billing.py`, `xai_adapter.py` and `test_xai_guard.py` (provider preparation still represented in the governing architecture; not activated); machine-wide caches; all user-owned Desktop and Downloads material. The Phase One security observation stands: files under `~/Desktop/Avatars/VAL/Documents/` whose names indicate credentials were listed by name only, never opened, and are left for a separate credential-migration task.
- Noted, not changed: `infrastructure/ci/generate_manifest.py` remains and can regenerate a manifest at any commit; the docstring of `registry.live_routes()` still describes the August credit state; `ARCHIVE-NOTE.md` still leaves the draft PDF's storage location unrecorded (it is on the owner's Desktop).

## Evidence-log preservation (commit `b45b5d3`)

Each file's SHA-256 was recorded before staging; the repository secret scanner run on exactly these fourteen files found nothing, as did an independent key-shape pass; the files were force-added at their existing paths; staged blobs and working files matched the recorded hashes; re-verified byte-identical and tracked after the cleanup. The `*.log` ignore rule is unchanged.

| File | SHA-256 |
|---|---|
| `docs/reviews/economics/history-cache-2026-09-10/history_cache.log` | `bb8c1ddc930bd6eb4184ebdd3a8064870a22e9d14a288f34264265a1250e0cf9` |
| `docs/reviews/qualification/runs/2026-09-09/opus-5-high/run.log` | `7416a8fc84bc5f1596c0a658663c63e6cd247c0eee84dfc38b15a89fdf21ec82` |
| `docs/reviews/qualification/runs/2026-09-09/opus-5-low/run.log` | `96ee8d5ccb1e7353d9ad0195972a135e558c852eb65381139b15ef0a3cbdd78b` |
| `docs/reviews/qualification/runs/2026-09-09/opus-5-medium/run.log` | `7fc421d8e1c24c1b44eed05c6a49c1ac30227200dbd24d4b7d4176b966653c3c` |
| `docs/reviews/qualification/runs/2026-09-09-v1.4/opus-5-high/run.log` | `977bc989af4c69681f33603993784fcc44ac51a11f191ddddac6e223c31790a9` |
| `docs/reviews/qualification/runs/2026-09-09-v1.4/opus-5-low/run.log` | `22edadb9c57a426e689fff3935ef9b466c6a18ef952a2000a008169beb94760d` |
| `docs/reviews/qualification/runs/2026-09-09-v1.4/opus-5-medium/run.log` | `7d13f30af60d85266580129360e37c816f5b48b0daf4c10d33b189bb4eae7059` |
| `docs/reviews/qualification/runs/2026-09-09-v1.5/opus-5-high/run.log` | `df3c6280e6043a5d849fbbfa7a33a7837108019da8642a2828197c71eeec65c5` |
| `docs/reviews/qualification/runs/2026-09-09-v1.5/opus-5-low/run.log` | `04d381b38be04c90b558524a0243bb5a7e071fedeb2836dd5dabfaa9948a8865` |
| `docs/reviews/qualification/runs/2026-09-09-v1.5/opus-5-medium/run.log` | `4f7f554d190969160cd842f5a449a84aad15a24d3710ae73573ca3424c5bccd7` |
| `docs/reviews/qualification/runs/2026-09-09-v1.5/record-state-regression/medium.log` | `129b38ad52f67219d15a1d8fe8c0e0d66401283c8acbed64e44bab68eba8a05b` |
| `docs/reviews/qualification/runs/2026-09-09-v1.6/opus-5-medium/run.log` | `0a6e5ad05c4da363e23dcc8babeb7e206b112d6a6a4038949fda262df5c3922d` |
| `docs/reviews/qualification/runs/2026-09-09-v1.6/specificity-probe/medium.log` | `235504da9d3e0f177bd7ec8c6740c5c46ca0a6db47d53b56b4e911d5a32785c1` |
| `docs/reviews/qualification/runs/2026-09-14-sol-stageb/run.log` | `79529a13a16fed710374e667fd2361e2f98df4fa98352ab39eb0a1107f1a961f` |

## Gemma 4 31B disposition (commit `18c69c5`)

NOT_ADMITTED AS LOCAL PARTNER, PARTNER QUALIFICATION CLOSED (owner/VAL): a model-quality and operational-suitability decision, not a failure of llama.cpp, the `LlamaCppAdapter`, provenance, exact preflight, thinking control, reasoning separation, parity or local-provider infrastructure (evidence index §77–§78). After that commit the candidate `llama-server` (pid 30712) was sent SIGTERM and verified gone, with no listener on port 8766 and no open handle on the file; then only `/Users/josepharmand/Models/val-llamacpp/gemma-4-31B-it-Q6_K.gguf` (25,201,483,424 bytes) was deleted and verified absent. The directory `~/Models/val-llamacpp/` is kept, empty, for llama.cpp. Kept: llama.cpp itself, the adapter and inspector, the qualification scripts, the pinned official template, the provenance record, both proof files, the raw Stage A responses, the review packet and the evaluation-only registry entry.

## Deleted — generated, untracked

`apps/desktop/src-tauri/target/` (2.1 GiB); `.mypy_cache/` (67 MB); `packages/gateway/.mypy_cache/` (62 MB); `packages/domain/.mypy_cache/` (26 MB); `packages/policy/.mypy_cache/` (11 MB); `.ruff_cache/`; `.pytest_cache/`; `.import_linter_cache/`; 20 `__pycache__/` directories outside `.venv` and `node_modules`; `apps/desktop/dist/`; `apps/desktop/src-tauri/gen/`; 31 `.DS_Store` files; `artifacts/` (it held only a `.DS_Store`). The `val_test` scratch database (432 MB, almost all catalogue bloat from repeated schema drops) was dropped and recreated empty with the same owner, encoding and collation. Output regenerated by the validation below (`target/`, `dist/`, `gen/`, tool caches, bytecode) was removed again afterwards; these are the same audited generated paths.

## Removed — tracked

- `docs/reviews/governing/` (seven files, 168 KB): review copies refreshed 17 August 2026, declared non-authoritative by their own README, five of six stale. Each is reproducible from Git: `00-charter.md` equals `docs/baselines/00-charter.md` (`5c49880ffd089a13…`); `01-architecture.md` `166f8df53d6b…` at `65853a1`; `02-partner-systems.md` `0f629d7a8938…` at `ccc94e3`; `03-persona.md` `1d502685773b…` at `3e96e6e` (persona v1.2, the digest the WP-0.5 seed recorded as `source_sha256`); `04-layer-0.md` `0879eecc6868…` at `f791268`; `CLAUDE.md` `114e31dafc53…` at `a5ac688`. Historical audits that mention `governing/` are left as written; this record is where those pointers now resolve.
- `docs/reviews/VAL_Repo_Manifest.txt`: generated 19 August 2026 at `a791465` for 172 files; stale against a tree of over 600. No new manifest was created.
- `infrastructure/ci/check_pins.py`: the token-scan exclusion and docstring sentence that existed solely for `docs/reviews/governing/` were removed. Nothing else referenced the directory in tests, CI or runtime.

## ReferenceTrust

Removed from `val_domain/project.py`. Reconfirmed immediately before the edit: its only occurrence in the working tree was its own definition — zero imports, callers, tests, serialization or schema use, migration use, documentation contract or public re-export. The trusted/untrusted distinction it described is enforced by the separate `trusted_reference` and `untrusted_candidate` fields of `ProjectSignals`, unchanged.

## Disk

| | |
|---|---|
| Free before cleanup | 86.2 GiB |
| Free immediately before / after the Gemma deletion | 86.18 GiB / 86.19 GiB |
| Free at the end of the cleanup | 93.4 GiB |
| Logical space released | about 26.2 GiB (Gemma 23.47, desktop build output 2.1, scratch database 0.42, caches 0.17) |
| Repository working tree | 2.6 GiB before, 382 MB after |

Free space has not yet risen by the full amount because fourteen Time Machine local snapshots taken on 17–18 September still reference the deleted blocks. macOS releases them as the snapshots expire or when space is needed. Snapshots were not touched.

## Validation

Migration chain: 23 revisions, one root (`0001_layer_0_schema`), one head (`0023_second_local_provider`), unbroken. Focused tests: CI checker tests 82 passed; domain and policy 563 passed; gateway project, resolution and scope tests 95 passed against the recreated scratch database. Full mirror green: secrets, pins, scope ruling, boundaries, import linter, ruff, mypy, migrations empty to head, down to base and up again, domain, gateway, providers, API, desktop tests and typecheck. Desktop rebuilt from the cleaned tree with `tauri build` (release): one bundle, `val_desktop` 9,700,080 bytes, the same size as the installed binary. Installed `/Applications/Val.app` unchanged (combined file hash `4faac47aa04e694a` before and after). Authoritative store untouched: 152 messages, 179 model calls, 36 conversations before and after; no migration was run on it. GPT-OSS present, three weight shards, not loaded. No registry entry added, removed or changed by the cleanup; no route changed; Sol remains the production Partner.
