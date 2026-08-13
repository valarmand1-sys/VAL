"""Tests for the dependency-direction checker.

The checker is the thing standing between the repository and a quietly inverted
dependency, so it is tested against the rules of 01-architecture.md §3 by name,
including the exact violation WP-0.1 requires CI to reject: `policy` reaching
`desktop`.
"""

import pytest

import check_boundaries
from check_boundaries import (
    Component,
    check_declared_graph,
    load_components,
    scan_source_file,
)

REPO_ROOT = check_boundaries.REPO_ROOT


@pytest.fixture
def components() -> list[Component]:
    """The real component graph, as CI loads it."""
    return load_components(check_boundaries.COMPONENTS_FILE)


def component(components: list[Component], name: str) -> Component:
    """Look one up by name."""
    return next(c for c in components if c.name == name)


def scan(source: str, filename: str, owner: Component, components: list[Component]) -> list[str]:
    """Write a file inside its component's real tree and scan it."""
    path = REPO_ROOT / owner.path / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    try:
        violations: list[check_boundaries.Violation] = []
        scan_source_file(path, owner, components, violations)
    finally:
        path.unlink()
    return [f"{v.source}->{v.target}" for v in violations]


# --- the four rules of 01-architecture.md §3 ---------------------------------


def test_policy_importing_desktop_is_rejected(components: list[Component]) -> None:
    """The violation WP-0.1 names explicitly.

    `packages/policy` is Python and `apps/desktop` is TypeScript and Rust, so no
    import statement can express this edge. A path reference is how it would
    actually be written, and that is what must be caught.
    """
    source = 'import sys\nsys.path.insert(0, "../../apps/desktop")\n'
    assert scan(source, "_probe.py", component(components, "policy"), components) == [
        "policy->desktop"
    ]


def test_policy_importing_providers_is_rejected(components: list[Component]) -> None:
    """Rule: policy depends on domain only."""
    source = "from val_providers import anything\n"
    assert scan(source, "_probe.py", component(components, "policy"), components) == [
        "policy->providers"
    ]


def test_policy_importing_domain_is_allowed(components: list[Component]) -> None:
    """The one edge policy is permitted."""
    source = "from val_domain import anything\n"
    assert scan(source, "_probe.py", component(components, "policy"), components) == []


def test_providers_importing_policy_is_rejected(components: list[Component]) -> None:
    """Rule: routing asks policy, policy never asks a provider."""
    source = "import val_policy\n"
    assert scan(source, "_probe.py", component(components, "providers"), components) == [
        "providers->policy"
    ]


def test_worker_importing_desktop_is_rejected(components: list[Component]) -> None:
    """Rule: worker never depends on desktop."""
    source = 'CONFIG = "apps/desktop/src/App.tsx"\n'
    assert scan(source, "_probe.py", component(components, "worker"), components) == [
        "worker->desktop"
    ]


def test_declared_graph_is_acyclic(components: list[Component]) -> None:
    """Rule: no circular package dependencies, checked on the allowlist itself."""
    assert check_declared_graph(components) == []


def test_cycle_in_the_allowlist_is_rejected() -> None:
    """A cycle introduced into components.toml fails the check rather than passing."""
    cyclic = [
        Component("a", "packages/a", ("python",), frozenset({"b"}), None, None, None, None),
        Component("b", "packages/b", ("python",), frozenset({"a"}), None, None, None, None),
    ]
    errors = check_declared_graph(cyclic)
    assert any("circular dependency" in error for error in errors)


# --- the other languages -----------------------------------------------------


def test_desktop_importing_policy_source_is_rejected(components: list[Component]) -> None:
    """A relative TypeScript specifier reaching into another component."""
    source = 'import { evaluate } from "../../../packages/policy/src/thing";\n'
    assert scan(source, "src/_probe.ts", component(components, "desktop"), components) == [
        "desktop->policy"
    ]


def test_desktop_internal_import_is_allowed(components: list[Component]) -> None:
    """A specifier that stays inside the component is not an edge."""
    source = 'import { App } from "./App";\n'
    assert scan(source, "src/_probe.ts", component(components, "desktop"), components) == []


def test_rust_use_of_a_workspace_crate_is_detected(components: list[Component]) -> None:
    """A Rust edge between components is detected like any other."""
    source = "use val_desktop::something;\n"
    assert scan(source, "_probe.rs", component(components, "api"), components) == ["api->desktop"]


def test_comment_lines_are_not_edges(components: list[Component]) -> None:
    """A reference in a comment is documentation, not a dependency."""
    source = "# see apps/desktop for the shell\n"
    assert scan(source, "_probe.py", component(components, "policy"), components) == []


# --- the repository as it stands ---------------------------------------------


def test_repository_has_no_violation(components: list[Component]) -> None:
    """The committed tree passes the check it ships with."""
    assert check_boundaries.walk(components) == []
