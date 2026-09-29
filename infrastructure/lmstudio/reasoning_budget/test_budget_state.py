# ruff: noqa: S101 - a test module outside the tests directories that carry this exemption
"""The reasoning-budget decision, on plain token lists (no engine, no mlx).

Run directly: `pytest infrastructure/lmstudio/reasoning_budget/test_budget_state.py`. Like
the cache hook, this module lives outside the service's packages and CI's test paths.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from val_reasoning_budget import CHANNEL, END, MESSAGE, START, BudgetState, sentence_end

ANALYSIS, FINAL, ASSISTANT = 35644, 17196, 173781
TRANSITION = [END, START, ASSISTANT, CHANNEL, FINAL, MESSAGE]
HEADER = [CHANNEL, ANALYSIS, MESSAGE]
WORD, STOP = 11, 13  # a word, and a token that ends a sentence


def run(state: BudgetState, stream: list[int], extra: int = 0) -> tuple[list[int], int]:
    """Feed the model's own tokens; a forced token replaces the model's choice."""
    generated: list[int] = []
    reads = 0

    def read() -> list[int]:
        nonlocal reads
        reads += 1
        return list(generated)

    source = iter(stream + [WORD] * extra)
    for _ in range(len(stream) + extra):
        forced = state.step(len(generated), read)
        generated.append(forced if forced is not None else next(source))
        if forced is not None:
            next(source, None)
    return generated, reads


def make(budget: int = 5, hard: int = 8) -> BudgetState:
    return BudgetState(
        budget=budget,
        hard=hard,
        transition=TRANSITION,
        analysis=[ANALYSIS],
        sentence_ends=frozenset({STOP}),
    )


def test_under_the_budget_nothing_is_read_or_changed() -> None:
    stream = [*HEADER, WORD, END, START, ASSISTANT, CHANNEL, FINAL, MESSAGE, WORD]
    state = make(budget=50, hard=60)
    generated, reads = run(state, stream)
    assert generated == stream
    assert reads == 0
    assert state.outcome == {"outcome": "under budget"}


def test_at_the_budget_it_waits_for_a_sentence_end_then_makes_the_transition() -> None:
    stream = [*HEADER, WORD, WORD, WORD, WORD, STOP, WORD, WORD, WORD, WORD, WORD, WORD]
    state = make(budget=5, hard=20)
    generated, _ = run(state, stream)
    assert generated[:8] == [*HEADER, WORD, WORD, WORD, WORD, STOP]
    at = generated.index(STOP) + 1
    assert generated[at : at + 6] == TRANSITION
    assert state.outcome["reason"] == "sentence end"
    assert state.state == "done"


def test_the_hard_limit_forces_the_transition_mid_sentence() -> None:
    stream = [*HEADER] + [WORD] * 20
    state = make(budget=5, hard=8)
    generated, _ = run(state, stream)
    assert generated[8:14] == TRANSITION
    assert state.outcome == {"outcome": "transition forced", "at": 8, "reason": "hard limit"}


def test_reasoning_the_model_ended_itself_is_left_alone() -> None:
    stream = [*HEADER, WORD, WORD, WORD, END, START, ASSISTANT, CHANNEL, FINAL, MESSAGE, WORD]
    state = make(budget=7, hard=9)
    generated, _ = run(state, stream)
    assert generated == stream
    assert "forced" not in state.outcome["outcome"]


def test_output_not_in_the_analysis_channel_is_left_alone() -> None:
    stream = [CHANNEL, FINAL, MESSAGE] + [WORD] * 10
    state = make(budget=4, hard=6)
    generated, _ = run(state, stream)
    assert generated == stream
    assert state.outcome["outcome"] == "not in reasoning at the budget"


def test_the_transition_is_made_once() -> None:
    stream = [*HEADER] + [STOP] * 30
    state = make(budget=4, hard=6)
    generated, _ = run(state, stream)
    assert generated.count(MESSAGE) == 2  # the analysis header's, and the final channel's
    assert generated.count(END) == 1


def test_sentence_end() -> None:
    assert sentence_end("done.")
    assert sentence_end("?")
    assert sentence_end(" line\n")
    assert not sentence_end(" word")
    assert not sentence_end("3.5x")
