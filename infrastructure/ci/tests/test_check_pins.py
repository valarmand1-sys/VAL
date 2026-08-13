"""Tests for the version-pinning checker.

The forbidden words are assembled from fragments here for the same reason as in
`check_pins.py`: so that the test suite does not have to be excluded from the
scan it exercises.
"""

import json
from pathlib import Path

import pytest

import check_pins

INTERNAL = check_pins.internal_distributions()


# Taken from the checker rather than written out, so that `ruff format` cannot
# collapse a literal token into this file and trip the scan it is testing.
@pytest.mark.parametrize(
    "word",
    [*check_pins.FORBIDDEN_WORDS, check_pins.FORBIDDEN_MARKER],
)
def test_placeholder_words_are_found(
    tmp_path: Path, word: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each token WP-0.1 names is detected."""
    target = tmp_path / "example.toml"
    target.write_text(f'version = "{word}"\n', encoding="utf-8")
    monkeypatch.setattr(check_pins, "REPO_ROOT", tmp_path)
    assert len(check_pins.scan_tokens([target])) == 1


def test_ordinary_prose_is_not_flagged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The scan does not fire on a word that merely contains a token."""
    target = tmp_path / "example.md"
    target.write_text("Translated and collated.\n", encoding="utf-8")
    monkeypatch.setattr(check_pins, "REPO_ROOT", tmp_path)
    assert check_pins.scan_tokens([target]) == []


def test_unpinned_python_requirement_is_rejected(tmp_path: Path) -> None:
    """A range specifier is not a pin."""
    target = tmp_path / "pyproject.toml"
    target.write_text(
        '[project]\nname = "x"\nversion = "0"\ndependencies = ["fastapi>=0.141.1"]\n',
        encoding="utf-8",
    )
    problems = check_pins.check_pyproject(target, INTERNAL)
    assert any("is not pinned with ==" in problem for problem in problems)


def test_exact_python_requirement_is_accepted(tmp_path: Path) -> None:
    """An `==` requirement passes."""
    target = tmp_path / "pyproject.toml"
    target.write_text(
        '[project]\nname = "x"\nversion = "0"\n'
        'requires-python = ">=3.14,<3.15"\ndependencies = ["fastapi==0.141.1"]\n',
        encoding="utf-8",
    )
    assert check_pins.check_pyproject(target, INTERNAL) == []


def test_unbounded_requires_python_is_rejected(tmp_path: Path) -> None:
    """An open-ended Python range admits a runtime nobody tested."""
    target = tmp_path / "pyproject.toml"
    target.write_text(
        '[project]\nname = "x"\nversion = "0"\nrequires-python = ">=3.14"\n',
        encoding="utf-8",
    )
    problems = check_pins.check_pyproject(target, INTERNAL)
    assert any("not bounded" in problem for problem in problems)


@pytest.mark.parametrize("specifier", ["^19.2.8", "~19.2.8", ">=19.0.0", "*", "next"])
def test_unpinned_npm_specifier_is_rejected(tmp_path: Path, specifier: str) -> None:
    """Carets and ranges are how a build stops being reproducible."""
    target = tmp_path / "package.json"
    target.write_text(json.dumps({"dependencies": {"react": specifier}}), encoding="utf-8")
    problems = check_pins.check_package_json(target, INTERNAL)
    assert any("not an exact version" in problem for problem in problems)


def test_exact_npm_specifier_is_accepted(tmp_path: Path) -> None:
    """A bare `x.y.z` passes."""
    target = tmp_path / "package.json"
    target.write_text(json.dumps({"dependencies": {"react": "19.2.8"}}), encoding="utf-8")
    assert check_pins.check_package_json(target, INTERNAL) == []


def test_cargo_caret_default_is_rejected(tmp_path: Path) -> None:
    """A bare Cargo version string means a caret range, not a pin."""
    target = tmp_path / "Cargo.toml"
    target.write_text('[dependencies]\ntauri = "2.11.5"\n', encoding="utf-8")
    problems = check_pins.check_cargo_toml(target)
    assert any("not pinned with '='" in problem for problem in problems)


def test_cargo_exact_is_accepted(tmp_path: Path) -> None:
    """`=x.y.z` passes."""
    target = tmp_path / "Cargo.toml"
    target.write_text('[dependencies]\ntauri = "=2.11.5"\n', encoding="utf-8")
    assert check_pins.check_cargo_toml(target) == []


def test_runtime_pins_are_exact() -> None:
    """`.python-version`, `.nvmrc`, and `rust-toolchain.toml` name a patch version."""
    assert check_pins.check_runtime_pins() == []


def test_actions_are_pinned_to_a_commit_sha() -> None:
    """A moving tag is not a pin, and is the usual way a CI supply chain moves."""
    assert check_pins.check_workflows() == []


def test_lock_files_are_present() -> None:
    """All three language lock files are committed."""
    assert check_pins.check_lock_files() == []


def test_repository_is_clean() -> None:
    """The committed tree passes the check it ships with."""
    assert check_pins.main() == 0
