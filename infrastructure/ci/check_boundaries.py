"""Enforce the dependency direction of 01-architecture.md §3 across every language.

`import-linter` (configured in the root pyproject.toml) is the deep, transitive
check over real Python imports. It cannot see `apps/desktop`, which is TypeScript
and Rust, and it cannot see a dependency declared in a manifest but not yet
imported. This checker covers both, in every language present, at the level of a
single edge between two components.

The two are complementary. CI runs both.

Rules come from `components.toml`, which is the machine-readable form of §3.
An edge that is not in a component's allowlist is a violation.

Exit code 0 means no violation was found. Exit code 1 means at least one was.
"""

import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPONENTS_FILE = Path(__file__).resolve().parent / "components.toml"

SOURCE_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".rs"})
MANIFEST_NAMES = frozenset({"pyproject.toml", "package.json", "Cargo.toml"})

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

PY_FROM = re.compile(r"^\s*from\s+([A-Za-z_][\w.]*)\s+import\b")
PY_IMPORT = re.compile(r"^\s*import\s+([A-Za-z_][\w.]*(?:\s*,\s*[A-Za-z_][\w.]*)*)")
PY_DYNAMIC = re.compile(r"""import_module\(\s*["']([^"']+)["']""")
JS_SPECIFIER = re.compile(
    r"""(?:\bfrom\s*|\brequire\s*\(\s*|\bimport\s*\(\s*|\bimport\s+)["']([^"']+)["']"""
)
RUST_USE = re.compile(r"^\s*(?:pub\s+)?use\s+(?:::)?([A-Za-z_]\w*)")
RUST_EXTERN = re.compile(r"^\s*extern\s+crate\s+([A-Za-z_]\w*)")
COMMENT_LINE = re.compile(r"^\s*(#|//|/\*|\*)")


@dataclass(frozen=True)
class Component:
    """One node of the §3 component graph."""

    name: str
    path: str
    languages: tuple[str, ...]
    allowed_dependencies: frozenset[str]
    python_module: str | None
    distribution: str | None
    npm_package: str | None
    cargo_crate: str | None


@dataclass(frozen=True)
class Violation:
    """A forbidden edge, located precisely enough to fix."""

    source: str
    target: str
    location: str
    detail: str

    def render(self) -> str:
        return f"  {self.location}: {self.source} -> {self.target}  ({self.detail})"


def load_components(path: Path) -> list[Component]:
    """Read the component graph."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    components: list[Component] = []
    for entry in raw["component"]:
        components.append(
            Component(
                name=entry["name"],
                path=entry["path"],
                languages=tuple(entry["languages"]),
                allowed_dependencies=frozenset(entry["allowed_dependencies"]),
                python_module=entry.get("python_module"),
                distribution=entry.get("distribution"),
                npm_package=entry.get("npm_package"),
                cargo_crate=entry.get("cargo_crate"),
            )
        )
    return components


def check_declared_graph(components: list[Component]) -> list[str]:
    """Reject unknown names and cycles in the allowlist itself."""
    errors: list[str] = []
    known = {c.name for c in components}
    for component in components:
        for dependency in sorted(component.allowed_dependencies):
            if dependency not in known:
                errors.append(
                    f"{component.name} allows a dependency on unknown component {dependency!r}"
                )
            if dependency == component.name:
                errors.append(f"{component.name} allows a dependency on itself")

    edges = {c.name: c.allowed_dependencies & known for c in components}
    state: dict[str, int] = dict.fromkeys(edges, 0)

    def visit(node: str, trail: list[str]) -> None:
        if state[node] == 1:
            cycle = " -> ".join([*trail[trail.index(node) :], node])
            errors.append(f"circular dependency in the allowlist: {cycle}")
            return
        if state[node] == 2:
            return
        state[node] = 1
        for nxt in sorted(edges[node]):
            visit(nxt, [*trail, node])
        state[node] = 2

    for name in sorted(edges):
        visit(name, [])
    return errors


def owning_component(relative_path: Path, components: list[Component]) -> Component | None:
    """Return the component a repository-relative path belongs to, if any."""
    text = relative_path.as_posix()
    best: Component | None = None
    for component in components:
        if text == component.path or text.startswith(component.path + "/"):
            if best is None or len(component.path) > len(best.path):
                best = component
    return best


def _record(
    violations: list[Violation],
    source: Component,
    target: Component | None,
    location: str,
    detail: str,
) -> None:
    if target is None or target.name == source.name:
        return
    if target.name in source.allowed_dependencies:
        return
    # One line can trip two detectors — a resolvable module specifier and the
    # path-reference catch-all both fire on `from "../../packages/policy/x"`.
    # It is one edge in one place, so it is reported once.
    if any(
        existing.source == source.name
        and existing.target == target.name
        and existing.location == location
        for existing in violations
    ):
        return
    violations.append(Violation(source.name, target.name, location, detail))


def _by_python_module(module: str, components: list[Component]) -> Component | None:
    root = module.split(".", 1)[0]
    for component in components:
        if component.python_module == root:
            return component
    return None


def _by_npm_package(specifier: str, components: list[Component]) -> Component | None:
    for component in components:
        if component.npm_package is not None and (
            specifier == component.npm_package or specifier.startswith(component.npm_package + "/")
        ):
            return component
    return None


def _by_cargo_crate(crate: str, components: list[Component]) -> Component | None:
    for component in components:
        if component.cargo_crate == crate:
            return component
    return None


def _resolve_relative(
    source_file: Path, specifier: str, components: list[Component]
) -> Component | None:
    target = (source_file.parent / specifier).resolve()
    try:
        relative = target.relative_to(REPO_ROOT)
    except ValueError:
        return None
    return owning_component(relative, components)


def scan_source_file(
    file_path: Path,
    component: Component,
    components: list[Component],
    violations: list[Violation],
) -> None:
    """Scan one source file for edges leaving its component."""
    relative = file_path.relative_to(REPO_ROOT).as_posix()
    suffix = file_path.suffix
    others = [c for c in components if c.name != component.name]

    for number, line in enumerate(
        file_path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
    ):
        location = f"{relative}:{number}"
        if COMMENT_LINE.match(line):
            continue

        if suffix == ".py":
            modules: list[str] = []
            match = PY_FROM.match(line)
            if match is not None:
                modules.append(match.group(1))
            match = PY_IMPORT.match(line)
            if match is not None:
                modules.extend(part.strip() for part in match.group(1).split(","))
            modules.extend(PY_DYNAMIC.findall(line))
            for module in modules:
                _record(
                    violations,
                    component,
                    _by_python_module(module, components),
                    location,
                    f"python import {module!r}",
                )

        elif suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
            for specifier in JS_SPECIFIER.findall(line):
                target = (
                    _resolve_relative(file_path, specifier, components)
                    if specifier.startswith(".")
                    else _by_npm_package(specifier, components)
                )
                _record(
                    violations,
                    component,
                    target,
                    location,
                    f"module specifier {specifier!r}",
                )

        elif suffix == ".rs":
            for pattern in (RUST_USE, RUST_EXTERN):
                match = pattern.match(line)
                if match is not None:
                    _record(
                        violations,
                        component,
                        _by_cargo_crate(match.group(1), components),
                        location,
                        f"rust crate {match.group(1)!r}",
                    )

        # Catch-all: a reference to another component's directory, in any form —
        # a relative path, a sys.path insertion, a build-config path. This is what
        # makes a cross-language edge detectable at all, since `packages/policy`
        # cannot reach `apps/desktop` through any language's import statement.
        for other in others:
            if re.search(rf"(?<![\w-]){re.escape(other.path)}(?![\w-])", line):
                _record(
                    violations,
                    component,
                    other,
                    location,
                    f"path reference to {other.path!r}",
                )


def scan_manifest(
    file_path: Path,
    component: Component,
    components: list[Component],
    violations: list[Violation],
) -> None:
    """Scan one manifest for declared dependencies leaving its component."""
    relative = file_path.relative_to(REPO_ROOT).as_posix()
    text = file_path.read_text(encoding="utf-8")

    if file_path.name == "pyproject.toml":
        data = tomllib.loads(text)
        declared: list[str] = list(data.get("project", {}).get("dependencies", []))
        for group in data.get("dependency-groups", {}).values():
            declared.extend(item for item in group if isinstance(item, str))
        for requirement in declared:
            name = re.split(r"[\s\[=<>!~;]", requirement, maxsplit=1)[0]
            for other in components:
                if other.distribution == name:
                    _record(
                        violations,
                        component,
                        other,
                        relative,
                        f"declared dependency {name!r}",
                    )

    elif file_path.name == "package.json":
        data = json.loads(text)
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            for name in data.get(section, {}):
                _record(
                    violations,
                    component,
                    _by_npm_package(name, components),
                    relative,
                    f"declared {section} {name!r}",
                )

    elif file_path.name == "Cargo.toml":
        data = tomllib.loads(text)
        for section in ("dependencies", "dev-dependencies", "build-dependencies"):
            for name, spec in data.get(section, {}).items():
                _record(
                    violations,
                    component,
                    _by_cargo_crate(name.replace("-", "_"), components),
                    relative,
                    f"declared {section} {name!r}",
                )
                if isinstance(spec, dict) and isinstance(spec.get("path"), str):
                    _record(
                        violations,
                        component,
                        _resolve_relative(file_path, spec["path"], components),
                        relative,
                        f"path dependency {spec['path']!r}",
                    )


def walk(components: list[Component]) -> list[Violation]:
    """Scan every component's tree."""
    violations: list[Violation] = []
    for component in components:
        root = REPO_ROOT / component.path
        if not root.is_dir():
            continue
        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file():
                continue
            if any(part in SKIP_DIRECTORIES for part in file_path.parts):
                continue
            if file_path.suffix in SOURCE_SUFFIXES:
                scan_source_file(file_path, component, components, violations)
            elif file_path.name in MANIFEST_NAMES:
                scan_manifest(file_path, component, components, violations)
    return violations


def main() -> int:
    """Run every check and report."""
    components = load_components(COMPONENTS_FILE)

    graph_errors = check_declared_graph(components)
    if graph_errors:
        print("The declared component graph is invalid:", file=sys.stderr)
        for error in graph_errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    violations = walk(components)
    if violations:
        print(
            f"Dependency direction violated in {len(violations)} place(s) (01-architecture.md §3):",
            file=sys.stderr,
        )
        for violation in violations:
            print(violation.render(), file=sys.stderr)
        print(
            "\nAllowed edges are declared in infrastructure/ci/components.toml. "
            "Widening them is an architecture decision, not an implementation one.",
            file=sys.stderr,
        )
        return 1

    names = ", ".join(sorted(c.name for c in components))
    print(f"Dependency direction holds across {len(components)} components: {names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
