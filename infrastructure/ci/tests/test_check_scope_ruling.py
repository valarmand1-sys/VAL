"""The scope-ruling tripwire fails when governance drifts — and only then.

Built against synthetic trees so every branch is exercised, including the
failure branches: a check that has never been seen red is an assertion, not a
control (the lesson of the tautological-test findings, 18 August 2026).
"""

from __future__ import annotations

from pathlib import Path

from check_scope_ruling import check

RULING = "<!-- scope-ruling: {date} -->\n> **Sequencing ruling.**\n"


def _tree(tmp_path: Path, baseline_dates: list[str], claude_date: str | None) -> tuple[Path, Path]:
    baselines = tmp_path / "baselines"
    baselines.mkdir()
    for index, date in enumerate(baseline_dates):
        (baselines / f"0{index}-doc.md").write_text(RULING.format(date=date), encoding="utf-8")
    if not baseline_dates:
        (baselines / "00-doc.md").write_text("no marker here\n", encoding="utf-8")
    claude = tmp_path / "CLAUDE.md"
    body = "## Current work\n"
    if claude_date is not None:
        body += RULING.format(date=claude_date)
    claude.write_text(body, encoding="utf-8")
    return baselines, claude


def test_in_step_is_green(tmp_path: Path) -> None:
    baselines, claude = _tree(tmp_path, ["2026-08-31"], "2026-08-31")
    assert check(baselines, claude) == []


def test_a_newer_baseline_ruling_turns_red(tmp_path: Path) -> None:
    """The drift the external reviewer found, as a failing check."""
    baselines, claude = _tree(tmp_path, ["2026-08-31", "2026-09-15"], "2026-08-31")
    problems = check(baselines, claude)
    assert len(problems) == 1
    assert "2026-09-15" in problems[0] and "2026-08-31" in problems[0]
    assert "governing document contradicting another" in problems[0]


def test_a_restatement_ahead_of_the_record_turns_red(tmp_path: Path) -> None:
    """CLAUDE.md cannot claim a ruling no baseline records."""
    baselines, claude = _tree(tmp_path, ["2026-08-31"], "2026-12-01")
    problems = check(baselines, claude)
    assert len(problems) == 1
    assert "cannot be ahead of the record" in problems[0]


def test_missing_markers_turn_red_rather_than_vacuously_green(tmp_path: Path) -> None:
    """Deleting the mechanism's inputs is not a way to retire the mechanism."""
    baselines, claude = _tree(tmp_path, [], None)
    problems = check(baselines, claude)
    assert len(problems) == 2
    assert any("no scope-ruling marker found anywhere" in p for p in problems)
    assert any("carries no scope-ruling marker" in p for p in problems)


def test_the_newest_marker_wins_across_documents(tmp_path: Path) -> None:
    baselines, claude = _tree(tmp_path, ["2026-08-31", "2026-09-15"], "2026-09-15")
    assert check(baselines, claude) == []


def test_the_real_tree_is_currently_in_step() -> None:
    """The repository itself, as CI sees it."""
    root = Path(__file__).resolve().parents[3]
    assert check(root / "docs" / "baselines", root / "CLAUDE.md") == []
