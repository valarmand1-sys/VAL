"""The LM Studio engine hooks run inside the engine's own Python 3.11, not the service's.

The repository formats for Python 3.14, whose formatter writes `except A, B:` (valid only
from 3.14) for `except (A, B):`. On 29 September 2026 that made the runtime observer's
import fail silently inside the engine, so it observed nothing until the engine's own
interpreter was used to find out why. Every hook module is parsed here with the 3.11
grammar, so the same mistake fails a test instead.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

HOOKS = sorted((Path(__file__).resolve().parents[2] / "lmstudio").glob("*/*.py"))


def test_there_are_hooks_to_check() -> None:
    assert any(path.name == "val_cache_renewal.py" for path in HOOKS)
    assert any(path.name == "val_runtime_observer.py" for path in HOOKS)


@pytest.mark.parametrize("path", HOOKS, ids=lambda path: f"{path.parent.name}/{path.name}")
def test_each_hook_module_parses_with_the_engine_grammar(path: Path) -> None:
    ast.parse(path.read_text(), filename=str(path), feature_version=(3, 11))
