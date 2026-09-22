"""The local visual-perception adapter — owner ruling, 22 September 2026.

What is pinned here is the boundary, not the model: the exact argument vector,
that the request travels on stdin and never as an argument, that the media are
written into a private directory and removed whatever happens, that a failure
gets one bounded recovery attempt and then stops honestly, and that a source
whose bytes do not match its digest is refused before anything runs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from val_domain.perception import (
    PerceptionRefusedError,
    PerceptionRequest,
    PerceptionSource,
    PerceptionUnavailableError,
)
from val_providers.mlxvlm_perception import (
    MODEL_REVISION,
    RUNNER,
    MLXVLMPerception,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"pretend bytes"


def source(content: bytes = PNG, media_type: str = "image/png") -> PerceptionSource:
    return PerceptionSource(
        modality="image",
        act_id="0199a3f0-0000-7000-8000-000000000001",
        sha256=hashlib.sha256(content).hexdigest(),
        media_type=media_type,
        byte_size=len(content),
        content=content,
    )


def request(
    *sources: PerceptionSource, prompt: str = "Report what you can see."
) -> PerceptionRequest:
    return PerceptionRequest(
        sources=sources or (source(),),
        question="What is in this?",
        prompt=prompt,
        max_output_tokens=2048,
    )


class RecordingRunner:
    """Answers from a script, and records every invocation exactly as given."""

    def __init__(self, *replies: object) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[list[str], str]] = []
        self.paths_seen: list[list[str]] = []

    def run(self, argv: list[str], payload: str, timeout: float) -> tuple[int, str, str]:
        self.calls.append((list(argv), payload))
        parsed = json.loads(payload)
        self.paths_seen.append([source["path"] for source in parsed["sources"]])
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, str):
            return 1, reply, ""
        observations = [
            {"sha256": source["sha256"], "modality": source["modality"], "text": "A navy field."}
            for source in parsed["sources"]
        ]
        return 0, json.dumps({"ok": True, "observations": observations, **reply}) + "\n", ""


def adapter(runner: RecordingRunner, tmp_path: Path) -> MLXVLMPerception:
    """An adapter whose runtime and artifact exist, so `available()` passes."""
    python = tmp_path / "python"
    python.write_text("")
    model = tmp_path / "model"
    model.mkdir()
    return MLXVLMPerception(python=python, model_path=model, runner=runner)  # type: ignore[arg-type]


# --- the boundary is a process, and the request travels on stdin -------------------


def test_the_argument_vector_is_exactly_the_interpreter_and_the_runner(tmp_path: Path) -> None:
    """Nothing from a model, a document or a tool result can become an argument.

    The invariant against an arbitrary local command path is kept by there being
    no path to steer: two constants, and everything else on stdin.
    """
    runner = RecordingRunner({"runtime_version": "0.7.2"})
    provider = adapter(runner, tmp_path)
    provider.perceive(request())

    ((argv, payload),) = runner.calls
    assert len(argv) == 2, "the interpreter and the runner, and nothing else"
    assert argv[0] == str(tmp_path / "python")
    assert argv[1] == str(RUNNER)

    # The prompt — the one value that carries the owner's words — is in the
    # payload, never in the vector.
    sent = json.loads(payload)
    assert sent["prompt"] == "Report what you can see."
    assert not any("Report what you can see" in argument for argument in argv)


def test_the_media_are_written_privately_and_removed_afterwards(tmp_path: Path) -> None:
    runner = RecordingRunner({"runtime_version": "0.7.2"})
    provider = adapter(runner, tmp_path)
    provider.perceive(request())

    (written,) = runner.paths_seen
    path = Path(written[0])
    assert path.suffix == ".png"
    assert not path.exists(), "the per-run directory is removed"
    assert not path.parent.exists()


def test_the_media_are_removed_even_when_the_run_fails(tmp_path: Path) -> None:
    runner = RecordingRunner(OSError("no such interpreter"), OSError("still none"))
    provider = adapter(runner, tmp_path)
    with pytest.raises(PerceptionUnavailableError):
        provider.perceive(request())
    for written in runner.paths_seen:
        assert not Path(written[0]).parent.exists()


# --- one bounded recovery attempt, then an honest stop -----------------------------


def test_a_transient_failure_gets_exactly_one_more_attempt(tmp_path: Path) -> None:
    runner = RecordingRunner(OSError("the runtime did not start"), {"runtime_version": "0.7.2"})
    provider = adapter(runner, tmp_path)
    result = provider.perceive(request())
    assert len(runner.calls) == 2, "one bounded recovery attempt, and it worked"
    assert result.observations[0].text == "A navy field."


def test_two_failures_stop_honestly_and_name_both(tmp_path: Path) -> None:
    runner = RecordingRunner(OSError("first reason"), OSError("second reason"))
    provider = adapter(runner, tmp_path)
    with pytest.raises(PerceptionUnavailableError) as stopped:
        provider.perceive(request())
    assert len(runner.calls) == 2, "two attempts, not three"
    said = str(stopped.value)
    assert "first reason" in said and "second reason" in said
    # The sentence that matters for §19: the failure is honest about what did
    # *not* happen instead.
    assert "Nothing was sent to any paid provider and nothing was charged." in said


def test_output_that_is_not_a_result_is_unavailability_not_a_guess(tmp_path: Path) -> None:
    runner = RecordingRunner("a traceback, not JSON", "a traceback, not JSON")
    provider = adapter(runner, tmp_path)
    with pytest.raises(PerceptionUnavailableError, match="not a result"):
        provider.perceive(request())


# --- refusals are not retried ------------------------------------------------------


def test_bytes_that_do_not_match_their_digest_are_refused_before_anything_runs(
    tmp_path: Path,
) -> None:
    """Evidence recorded against the wrong bytes is worse than no evidence."""
    runner = RecordingRunner({"runtime_version": "0.7.2"})
    provider = adapter(runner, tmp_path)
    wrong = PerceptionSource(
        modality="image",
        act_id=None,
        sha256="0" * 64,
        media_type="image/png",
        byte_size=len(PNG),
        content=PNG,
    )
    with pytest.raises(PerceptionRefusedError, match="not the recorded attachment"):
        provider.perceive(request(wrong))
    assert runner.calls == [], "nothing was started"


def test_a_medium_this_route_does_not_read_is_refused(tmp_path: Path) -> None:
    runner = RecordingRunner({"runtime_version": "0.7.2"})
    provider = adapter(runner, tmp_path)
    with pytest.raises(PerceptionRefusedError, match="not a medium"):
        provider.perceive(request(source(media_type="audio/wav")))


def test_an_absent_runtime_is_reported_as_an_absent_runtime(tmp_path: Path) -> None:
    runner = RecordingRunner()
    provider = MLXVLMPerception(
        python=tmp_path / "missing",
        model_path=tmp_path,
        runner=runner,  # type: ignore[arg-type]
    )
    assert provider.available() is not None
    with pytest.raises(PerceptionUnavailableError, match="not installed"):
        provider.perceive(request())
    assert runner.calls == []


# --- what the result carries -------------------------------------------------------


def test_the_result_carries_the_artifact_identity_and_a_known_zero_cost(
    tmp_path: Path,
) -> None:
    runner = RecordingRunner({"runtime_version": "0.7.2", "runtime": "mlx-vlm"})
    provider = adapter(runner, tmp_path)
    result = provider.perceive(request())
    assert result.provider == "mlxvlm"
    assert result.model_revision == MODEL_REVISION
    assert result.quantization.startswith("4-bit")
    assert result.runtime == "mlx-vlm" and result.runtime_version == "0.7.2"
    assert result.local is True and result.cost_usd == 0.0
    assert result.reasoning_separated is True


def test_release_holds_nothing_because_the_run_already_exited(tmp_path: Path) -> None:
    """Sequential residency: the subprocess exiting is the release."""
    runner = RecordingRunner({"runtime_version": "0.7.2"})
    provider = adapter(runner, tmp_path)
    provider.perceive(request())
    provider.release()
    provider.release()
    assert len(runner.calls) == 1, "releasing starts nothing and stops nothing"
