"""Regenerate the reviewer's repository manifest.

Every git-tracked file, with its byte size and SHA-256, in one uniform table.

**Uniform is the point.** The manifest this replaces listed text files with a
hash and pushed the eighteen binary icons into a trailing section carrying size
alone. A reviewer cannot verify what has no hash, and a manifest with a section
that cannot be checked is a manifest that invites the reader to assume the rest
is fine. Binaries are exactly where a silent substitution would be hardest to
spot by eye, so they are the last thing that should be exempt.

The file list comes from `git ls-files` — a whitelist. `.env` cannot appear by
construction, and neither can build output, caches, or anything else git does
not track.

    uv run python infrastructure/ci/generate_manifest.py
"""

import hashlib
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

MANIFEST = Path("docs/reviews/VAL_Repo_Manifest.txt")

HEADER = """VAL repository manifest
Commit: {commit}
Generated: {generated}
Scope: every git-tracked project file, each with its size and SHA-256 — text and
       binary alike, in one table. Excludes .git internals, node_modules,
       virtualenvs, build output, caches, database data, backup repositories,
       and .env (which is git-ignored and never packaged).
Files: {count}

SIZE          SHA-256                                                           PATH
"""


def tracked_files() -> list[str]:
    """Every path git tracks, sorted. A whitelist, not a filter."""
    result = subprocess.run(
        ["git", "ls-files"],  # noqa: S607 - resolved from PATH deliberately
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(line for line in result.stdout.splitlines() if line)


def head_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def digest(path: Path) -> tuple[int, str]:
    """Size and SHA-256, read as bytes so text and binary are treated alike."""
    data = path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def main() -> int:
    paths = tracked_files()
    lines: list[str] = []
    missing: list[str] = []

    for name in paths:
        path = Path(name)
        if not path.is_file():
            # A tracked path that is not on disk is worth naming rather than
            # skipping quietly — it means the manifest and the tree disagree.
            missing.append(name)
            continue
        size, sha = digest(path)
        lines.append(f"{size:<13} {sha}  {name}")

    if missing:
        print("tracked but not present on disk:", file=sys.stderr)
        for name in missing:
            print(f"  {name}", file=sys.stderr)
        return 1

    header = HEADER.format(
        commit=head_commit(),
        generated=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        count=len(lines),
    )
    MANIFEST.write_text(header + "\n".join(lines) + "\n")
    print(f"{len(lines)} files written to {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
