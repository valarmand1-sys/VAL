"""Prove that no version placeholder and no unpinned specifier remains.

WP-0.1 (`docs/baselines/04-layer-0.md` §3) requires every tool version to be
pinned to an explicit version, and requires a grep for placeholder tokens to come
back empty. This is that grep, plus the part a grep cannot do: checking that each
manifest's version specifiers are exact rather than ranges.

Two exclusions, both deliberate and both narrow:

  - `docs/baselines/` is governing specification text, not configuration. It is
    excluded from the token scan because the acceptance criterion itself quotes
    the forbidden tokens while stating the rule. Nothing in it pins a version.
  - Lock files are excluded from the token scan only. They exist to hold resolved
    exact versions, and a package whose name happens to contain a forbidden word
    is not a placeholder. Their presence is checked, and the manifests they lock
    are scanned in full.

Exit code 0 means clean. Exit code 1 means at least one placeholder or unpinned
specifier remains.
"""

import json
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPONENTS_FILE = Path(__file__).resolve().parent / "components.toml"

SKIP_DIRECTORIES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "target",
        "venv",
    }
)

TEXT_SUFFIXES = frozenset(
    {
        ".cjs",
        ".html",
        ".js",
        ".json",
        ".jsx",
        ".md",
        ".mjs",
        ".py",
        ".rs",
        ".sh",
        ".toml",
        ".ts",
        ".tsx",
        ".yaml",
        ".yml",
    }
)
TEXT_FILENAMES = frozenset({".nvmrc", ".python-version"})

TOKEN_SCAN_EXCLUDED = ("docs/baselines/",)
LOCK_FILES = (
    "uv.lock",
    "apps/desktop/package-lock.json",
    "apps/desktop/src-tauri/Cargo.lock",
)

# Every forbidden token is assembled from fragments at import time so that this
# file does not itself contain one. The alternative — excluding the checker from
# its own scan — would leave the one file most likely to drift unchecked.
#
# The fragments are joined rather than written as adjacent literals because
# `ruff format` collapses adjacent literals, which would put the tokens back.


def _token(*fragments: str) -> str:
    """Assemble a forbidden token out of pieces that are harmless apart."""
    return "".join(fragments)


FORBIDDEN_WORDS = (
    _token("TO", "DO"),
    _token("T", "BD"),
    _token("FIX", "ME"),
    _token("X", "XX"),
    _token("lat", "est"),
)
FORBIDDEN_WORD_RE = re.compile(
    r"(?<![\w-])(" + "|".join(FORBIDDEN_WORDS) + r")(?![\w-])", re.IGNORECASE
)
# Case-sensitive, unlike the words above: an upper-case marker is a stand-in
# value, while the ordinary lower-case word appears in prose describing this
# very check.
FORBIDDEN_MARKER = _token("PLACE", "HOLDER")
FORBIDDEN_MARKER_RE = re.compile(r"(?<![\w-])" + FORBIDDEN_MARKER + r"(?![\w-])")
# A GitHub Actions context expression is a filled value, not an unfilled
# template. Any other doubled brace is a template nobody substituted into.
_ACTIONS_CONTEXT = r"(?!\s*(?:github|matrix|runner|env|inputs|secrets|vars|needs|steps)\b)"
FORBIDDEN_TEMPLATE_RE = re.compile(
    _token("<", "version>") + "|" + _token("\\$", "\\{", "\\{") + _ACTIONS_CONTEXT + r"|(?<!\$)\{\{"
)

EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
EXACT_PYPI_REQUIREMENT = re.compile(r"^[A-Za-z0-9._-]+(\[[A-Za-z0-9,._-]+\])?==\d[\w.]*$")
EXACT_NPM_VERSION = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$")
EXACT_CARGO_VERSION = re.compile(r"^=\d+\.\d+\.\d+$")
BOUNDED_REQUIRES_PYTHON = re.compile(r"^>=\d+\.\d+(\.\d+)?,<\d+\.\d+$")
ACTION_PINNED_TO_SHA = re.compile(r"^[A-Za-z0-9._/-]+@[0-9a-f]{40}$")
USES_LINE = re.compile(r"^\s*-?\s*uses:\s*(\S+)")


def _relative(path: Path) -> str:
    """Repository-relative path, falling back to the full path when outside it."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def internal_distributions() -> frozenset[str]:
    """Names of workspace packages, which are sourced by path and carry no version."""
    raw = tomllib.loads(COMPONENTS_FILE.read_text(encoding="utf-8"))
    names: set[str] = set()
    for entry in raw["component"]:
        for key in ("distribution", "npm_package", "cargo_crate"):
            value = entry.get(key)
            if isinstance(value, str):
                names.add(value)
    return frozenset(names)


def iter_files() -> list[Path]:
    """Every text file in the repository worth scanning."""
    found: list[Path] = []
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRECTORIES for part in path.parts):
            continue
        if path.suffix in TEXT_SUFFIXES or path.name in TEXT_FILENAMES:
            found.append(path)
    return found


def scan_tokens(files: list[Path]) -> list[str]:
    """Find placeholder tokens."""
    problems: list[str] = []
    for path in files:
        relative = _relative(path)
        if relative.startswith(TOKEN_SCAN_EXCLUDED) or relative in LOCK_FILES:
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            for pattern in (
                FORBIDDEN_WORD_RE,
                FORBIDDEN_MARKER_RE,
                FORBIDDEN_TEMPLATE_RE,
            ):
                match = pattern.search(line)
                if match is not None:
                    problems.append(f"{relative}:{number}: placeholder {match.group(0)!r}")
    return problems


def check_pyproject(path: Path, internal: frozenset[str]) -> list[str]:
    """Every PyPI requirement is exact; every workspace requirement is bare."""
    relative = _relative(path)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []

    requirements: list[str] = list(data.get("project", {}).get("dependencies", []))
    requirements.extend(data.get("build-system", {}).get("requires", []))
    for group in data.get("dependency-groups", {}).values():
        requirements.extend(item for item in group if isinstance(item, str))

    for requirement in requirements:
        name = re.split(r"[\s\[=<>!~;]", requirement, maxsplit=1)[0]
        if name in internal:
            if requirement.strip() != name:
                problems.append(
                    f"{relative}: workspace requirement {requirement!r} should be "
                    f"the bare name {name!r}"
                )
        elif EXACT_PYPI_REQUIREMENT.match(requirement) is None:
            problems.append(f"{relative}: requirement {requirement!r} is not pinned with ==")

    requires_python = data.get("project", {}).get("requires-python")
    if requires_python is not None and BOUNDED_REQUIRES_PYTHON.match(requires_python) is None:
        problems.append(
            f"{relative}: requires-python {requires_python!r} is not bounded above and below"
        )

    required_uv = data.get("tool", {}).get("uv", {}).get("required-version")
    if required_uv is not None and re.match(r"^==\d+\.\d+\.\d+$", required_uv) is None:
        problems.append(f"{relative}: uv required-version {required_uv!r} is not exact")

    return problems


def check_package_json(path: Path, internal: frozenset[str]) -> list[str]:
    """Every npm dependency and engine constraint is an exact version."""
    relative = _relative(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []

    for section in ("dependencies", "devDependencies", "peerDependencies"):
        for name, specifier in data.get(section, {}).items():
            if name in internal:
                continue
            if not isinstance(specifier, str) or EXACT_NPM_VERSION.match(specifier) is None:
                problems.append(
                    f"{relative}: {section}.{name} = {specifier!r} is not an exact version"
                )

    for engine, specifier in data.get("engines", {}).items():
        if EXACT_VERSION.match(str(specifier)) is None:
            problems.append(f"{relative}: engines.{engine} = {specifier!r} is not an exact version")

    return problems


def check_cargo_toml(path: Path) -> list[str]:
    """Every crate dependency is pinned with `=`, not a caret range."""
    relative = _relative(path)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []

    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        for name, spec in data.get(section, {}).items():
            version = spec if isinstance(spec, str) else spec.get("version")
            if not isinstance(version, str) or EXACT_CARGO_VERSION.match(version) is None:
                problems.append(
                    f"{relative}: {section}.{name} = {version!r} is not pinned with '='"
                )

    rust_version = data.get("package", {}).get("rust-version")
    if rust_version is not None and EXACT_VERSION.match(rust_version) is None:
        problems.append(f"{relative}: package.rust-version {rust_version!r} is not exact")

    return problems


def check_runtime_pins() -> list[str]:
    """The three language runtimes are pinned to an exact patch version."""
    problems: list[str] = []

    for name in (".python-version", ".nvmrc"):
        path = REPO_ROOT / name
        if not path.is_file():
            problems.append(f"{name}: missing")
            continue
        value = path.read_text(encoding="utf-8").strip()
        if EXACT_VERSION.match(value) is None:
            problems.append(f"{name}: {value!r} is not an exact version")

    toolchain = REPO_ROOT / "rust-toolchain.toml"
    if not toolchain.is_file():
        problems.append("rust-toolchain.toml: missing")
    else:
        channel = (
            tomllib.loads(toolchain.read_text(encoding="utf-8")).get("toolchain", {}).get("channel")
        )
        if not isinstance(channel, str) or EXACT_VERSION.match(channel) is None:
            problems.append(f"rust-toolchain.toml: channel {channel!r} is not an exact version")

    return problems


def check_workflows() -> list[str]:
    """Every GitHub Action is pinned to a full commit SHA."""
    problems: list[str] = []
    workflows = REPO_ROOT / ".github" / "workflows"
    if not workflows.is_dir():
        return ["`.github/workflows`: missing"]
    for path in sorted(workflows.glob("*.yml")):
        relative = _relative(path)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = USES_LINE.match(line)
            if match is not None and ACTION_PINNED_TO_SHA.match(match.group(1)) is None:
                problems.append(
                    f"{relative}:{number}: action {match.group(1)!r} is not pinned to a commit SHA"
                )
    return problems


def check_lock_files() -> list[str]:
    """A pinned manifest without its lock file is only half a pin."""
    return [f"{name}: missing" for name in LOCK_FILES if not (REPO_ROOT / name).is_file()]


def main() -> int:
    """Run every check and report."""
    internal = internal_distributions()
    files = iter_files()

    problems: list[str] = []
    problems.extend(scan_tokens(files))
    for path in files:
        if path.name == "pyproject.toml":
            problems.extend(check_pyproject(path, internal))
        elif path.name == "package.json":
            problems.extend(check_package_json(path, internal))
        elif path.name == "Cargo.toml":
            problems.extend(check_cargo_toml(path))
    problems.extend(check_runtime_pins())
    problems.extend(check_workflows())
    problems.extend(check_lock_files())

    if problems:
        print(
            f"{len(problems)} placeholder(s) or unpinned specifier(s) remain "
            "(04-layer-0.md §3, WP-0.1):",
            file=sys.stderr,
        )
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print(f"No placeholder and no unpinned specifier across {len(files)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
