"""The local audio-perception adapter — owner execution order, 22 September 2026.

What is pinned here is the boundary, not the model: the exact argument vector,
that the owner's words travel in a file rather than in the vector, that the
recording is written privately and removed whatever happens, that a failure gets
one bounded recovery attempt and then stops honestly, and — the claim the order
asks for most explicitly — that **there is no code path here that could reach a
transcription service or a cloud API**, because the only binary this module can
start is the one named in it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from val_domain.perception import (
    PerceptionRefusedError,
    PerceptionRequest,
    PerceptionSource,
    PerceptionUnavailableError,
)
from val_providers.omni_audio_perception import (
    CONTEXT_TOKENS,
    GPU_LAYERS,
    MODEL_REVISION,
    OmniAudioPerception,
)

WAV = b"RIFF\x00\x00\x00\x08WAVE" + b"pretend frames"

#: What the CLI actually prints around an answer, in the shape the frozen Case B
#: run produced it.
NOISY = """build: 10964 (b29c606e2) with AppleClang for arm64
llama_model_loader: loaded meta data
init_audio: audio input is supported
encoding audio slice...
The lantern is beside the blue book. The number is forty-two.
llama perf context print: load time = 3512.00 ms
"""


def source(content: bytes = WAV, modality: str = "audio") -> PerceptionSource:
    return PerceptionSource(
        modality=modality,  # type: ignore[arg-type]
        act_id="0199a3f0-0000-7000-8000-000000000001",
        sha256=hashlib.sha256(content).hexdigest(),
        media_type="audio/wav",
        byte_size=len(content),
        content=content,
    )


def request(
    *sources: PerceptionSource, prompt: str = "Report what the recording says."
) -> PerceptionRequest:
    return PerceptionRequest(
        sources=sources or (source(),),
        question="What did she say about the envelope?",
        prompt=prompt,
        max_output_tokens=2048,
    )


class RecordingRunner:
    """Answers from a script, and records every invocation exactly as given."""

    def __init__(self, *replies: object) -> None:
        self.replies = list(replies)
        self.calls: list[list[str]] = []
        self.prompts_seen: list[str] = []
        self.audio_seen: list[Path] = []

    def run(self, argv: list[str], timeout: float) -> tuple[int, str, str]:
        self.calls.append(list(argv))
        self.prompts_seen.append(Path(argv[argv.index("-f") + 1]).read_text())
        self.audio_seen.append(Path(argv[argv.index("--audio") + 1]))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, tuple):
            code, err = reply
            return code, "", err
        return 0, str(reply), ""


def adapter(runner: RecordingRunner, tmp_path: Path) -> OmniAudioPerception:
    """An adapter whose runtime and artifacts exist, so `available()` passes."""
    for name in ("llama-mtmd-cli", "model.gguf", "mmproj.gguf"):
        (tmp_path / name).write_text("")
    return OmniAudioPerception(
        binary=tmp_path / "llama-mtmd-cli",
        model=tmp_path / "model.gguf",
        mmproj=tmp_path / "mmproj.gguf",
        runner=runner,  # type: ignore[arg-type]
    )


# --- the boundary, and what never enters it ----------------------------------------


def test_the_argument_vector_is_constants_and_paths_this_module_made(tmp_path: Path) -> None:
    """Nothing the owner wrote, and nothing a model produced, becomes an argument."""
    runner = RecordingRunner(NOISY)
    provider = adapter(runner, tmp_path)
    provider.perceive(request(prompt="Report what the recording says about Mara."))

    (argv,) = runner.calls
    assert argv[0] == str(tmp_path / "llama-mtmd-cli")
    assert argv[1:5] == [
        "-m",
        str(tmp_path / "model.gguf"),
        "--mmproj",
        str(tmp_path / "mmproj.gguf"),
    ]
    assert "-c" in argv and argv[argv.index("-c") + 1] == str(CONTEXT_TOKENS)
    assert "-ngl" in argv and argv[argv.index("-ngl") + 1] == str(GPU_LAYERS)
    # The one value carrying the owner's words is in a file, not the vector.
    assert not any("Mara" in argument for argument in argv)
    assert runner.prompts_seen == ["Report what the recording says about Mara."]


def test_nothing_here_can_reach_a_transcription_service_or_a_cloud_api(
    tmp_path: Path,
) -> None:
    """§8's explicit prohibition, proved structurally rather than promised.

    The only subprocess this module starts is the binary it names, and the whole
    module contains no URL, no HTTP client, and no second executable. A silent
    Whisper call would need code that does not exist here.
    """
    import inspect
    import io
    import tokenize

    from val_providers import omni_audio_perception

    # Comments and docstrings are stripped first, so the module's own
    # *prohibitions* are not mistaken for the thing they prohibit. What is left
    # is executable code.
    source_text = inspect.getsource(omni_audio_perception)
    code = "".join(
        token.string
        for token in tokenize.generate_tokens(io.StringIO(source_text).readline)
        if token.type not in (tokenize.COMMENT, tokenize.STRING)
    ).lower()
    for forbidden in ("whisper", "http://", "https://", "requests", "urllib", "openai"):
        assert forbidden not in code, f"{forbidden!r} must not appear in executable code"

    runner = RecordingRunner(NOISY)
    provider = adapter(runner, tmp_path)
    provider.perceive(request())
    (argv,) = runner.calls
    assert argv[0].endswith("llama-mtmd-cli"), "one binary, and it is the local one"


def test_the_recording_is_written_privately_and_removed_afterwards(tmp_path: Path) -> None:
    runner = RecordingRunner(NOISY)
    provider = adapter(runner, tmp_path)
    provider.perceive(request())
    (written,) = runner.audio_seen
    assert written.suffix == ".wav"
    assert not written.exists(), "the per-run directory is removed"
    assert not written.parent.exists()


def test_the_recording_is_removed_even_when_the_run_fails(tmp_path: Path) -> None:
    runner = RecordingRunner(OSError("no such binary"), OSError("still none"))
    provider = adapter(runner, tmp_path)
    with pytest.raises(PerceptionUnavailableError):
        provider.perceive(request())
    for written in runner.audio_seen:
        assert not written.parent.exists()


# --- audio alone ---------------------------------------------------------------------


def test_this_route_refuses_a_modality_it_is_not_admitted_for(tmp_path: Path) -> None:
    """The artifact carries a vision encoder. That is not a permission."""
    runner = RecordingRunner(NOISY)
    provider = adapter(runner, tmp_path)
    assert provider.modalities == frozenset({"audio"})
    with pytest.raises(PerceptionRefusedError, match="admitted for audio alone"):
        provider.perceive(request(source(modality="video")))
    assert runner.calls == [], "nothing was started"


def test_bytes_that_do_not_match_their_digest_are_refused_before_anything_runs(
    tmp_path: Path,
) -> None:
    runner = RecordingRunner(NOISY)
    provider = adapter(runner, tmp_path)
    wrong = PerceptionSource(
        modality="audio",
        act_id=None,
        sha256="0" * 64,
        media_type="audio/wav",
        byte_size=len(WAV),
        content=WAV,
    )
    with pytest.raises(PerceptionRefusedError, match="not the recorded attachment"):
        provider.perceive(request(wrong))
    assert runner.calls == []


# --- one bounded recovery, then an honest stop ---------------------------------------


def test_a_transient_failure_gets_exactly_one_more_attempt(tmp_path: Path) -> None:
    runner = RecordingRunner(OSError("the runtime did not start"), NOISY)
    provider = adapter(runner, tmp_path)
    result = provider.perceive(request())
    assert len(runner.calls) == 2
    assert "lantern" in result.observations[0].text


def test_two_failures_stop_honestly_and_say_what_did_not_happen(tmp_path: Path) -> None:
    runner = RecordingRunner((1, "first reason"), (1, "second reason"))
    provider = adapter(runner, tmp_path)
    with pytest.raises(PerceptionUnavailableError) as stopped:
        provider.perceive(request())
    assert len(runner.calls) == 2, "two attempts, not three"
    said = str(stopped.value)
    assert "first reason" in said and "second reason" in said
    assert "No transcription service and no paid audio API was contacted" in said


def test_an_absent_artifact_is_reported_as_an_absent_artifact(tmp_path: Path) -> None:
    runner = RecordingRunner()
    provider = OmniAudioPerception(
        binary=tmp_path / "missing",
        model=tmp_path / "model.gguf",
        mmproj=tmp_path / "mmproj.gguf",
        runner=runner,  # type: ignore[arg-type]
    )
    assert provider.available() is not None
    with pytest.raises(PerceptionUnavailableError, match="not installed"):
        provider.perceive(request())
    assert runner.calls == []


# --- what is stored is the observation, not the log ----------------------------------


def test_the_runtimes_startup_chatter_is_not_stored_as_evidence() -> None:
    observation = OmniAudioPerception.observation_from(NOISY)
    assert observation == "The lantern is beside the blue book. The number is forty-two."
    assert "llama_model_loader" not in observation
    assert "init_audio" not in observation
    assert "llama perf" not in observation


def test_the_result_carries_the_artifact_identity_and_a_known_zero_cost(
    tmp_path: Path,
) -> None:
    runner = RecordingRunner(NOISY)
    result = adapter(runner, tmp_path).perceive(request())
    assert result.provider == "llamacpp-omni"
    assert result.model_revision == MODEL_REVISION
    assert result.runtime == "llama.cpp"
    assert "10964" in result.runtime_version
    assert result.local is True and result.cost_usd == 0.0
    assert result.reasoning_separated is True
    # Untuned at qualification, untuned now — recorded as absent rather than
    # omitted, so the record says so.
    assert result.generation["sampling_arguments_passed"] == []
    assert result.generation["temperature"] is None
    assert result.observations[0].modality == "audio"
