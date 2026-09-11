"""Val Core knows no provider — Phase 1, 11 September 2026.

Inside `val_gateway`, only the composition root (`startup.py`) may import
`val_providers`; every other module speaks the domain boundary
(`val_domain.provider`). Provider SDK modules are confined to `val_providers`
by the repository-wide boundary check; this test pins the narrower rule for
the core itself, so an SDK concept cannot arrive by way of the providers
package either.
"""

from __future__ import annotations

import ast
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "src" / "val_gateway"
COMPOSITION_ROOT = {"startup.py"}
UPPER_LAYERS = ("val_policy", "val_domain", "val_api")


def _imports(path: Path) -> list[str]:
    """Every module a file imports — parsed, so docstring prose cannot masquerade."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


def test_only_the_composition_root_imports_the_providers_package() -> None:
    offenders = {
        path.name
        for path in CORE.glob("*.py")
        if path.name not in COMPOSITION_ROOT
        and any(module.startswith("val_providers") for module in _imports(path))
    }
    assert offenders == set(), f"val_providers reached the core outside startup.py: {offenders}"


def test_no_sdk_module_is_imported_anywhere_in_the_core_or_above() -> None:
    sdks = ("anthropic", "openai", "google", "cohere", "mistralai", "groq", "ollama")
    roots = [CORE]
    for layer in UPPER_LAYERS:
        for base in (
            Path(__file__).resolve().parents[2],
            Path(__file__).resolve().parents[3] / "apps",
        ):
            roots.extend(base.glob(f"*/src/{layer}"))
    offenders = {
        str(path)
        for root in roots
        for path in root.rglob("*.py")
        if any(m.split(".")[0] in sdks for m in _imports(path))
    }
    assert offenders == set(), offenders
