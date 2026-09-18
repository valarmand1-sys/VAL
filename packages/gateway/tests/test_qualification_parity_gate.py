"""The qualification harness's exact-parity hard stop — owner ruling, 18 September 2026.

The Mistral Stage A run continued past four calls whose exact preflight did not
match the server's count, because the harness recorded parity warnings rather
than enforcing the ruled STOP. The gate is now a shared function the harness and
the proof scripts call after every call; this pin loads it from the run directory
so CI holds the behaviour: any nonzero difference, or a missing parity record,
halts.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_DIR = REPO_ROOT / "docs/reviews/qualification/runs/2026-09-16-gpt-oss-stage-a"
GATES = RUN_DIR / "qualification_gates.py"


def _parity_halt() -> Callable[..., str | None]:
    spec = importlib.util.spec_from_file_location("qualification_gates", GATES)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parity_halt


def test_exact_parity_lets_the_call_stand() -> None:
    halt = _parity_halt()
    exact = {
        "exact": True,
        "difference": 0,
        "preflight_prompt_tokens": 5,
        "server_prompt_tokens": 5,
    }
    assert halt(exact, label="T1") is None


def test_any_nonzero_difference_halts_immediately() -> None:
    halt = _parity_halt()
    for difference in (1, -1, -2, 40):
        parity = {
            "exact": False,
            "difference": difference,
            "preflight_prompt_tokens": 5,
            "server_prompt_tokens": 5 - difference,
        }
        message = halt(parity, label="F1 T2")
        assert message is not None
        assert message.startswith("PARITY NOT EXACT on F1 T2") and message.endswith("STOP.")


def test_a_missing_parity_record_halts_rather_than_passing_silently() -> None:
    halt = _parity_halt()
    assert halt(None, label="T1") is not None
    assert halt({}, label="T1") is not None


def test_the_harness_calls_the_gate_after_every_call() -> None:
    harness = (GATES.parent / "harness_stage_a.py").read_text(encoding="utf-8")
    assert "from qualification_gates import parity_halt" in harness
    assert "sys.exit(4)" in harness, "a halt ends the run, it does not merely warn"
