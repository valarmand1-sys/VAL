"""Val's local speech adapter — owner execution order, 22 September 2026.

What is pinned here is the boundary, not the voice: the exact argument vector,
that Val's words travel on stdin and never as an argument, that the reference is
checked against its digest before anything runs, that a failure gets one bounded
recovery attempt and then stops honestly — and the claim the order asks for most
explicitly, that **no code path here can reach ElevenLabs or any cloud voice
service**, because the only executable this module can start is the one it names.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from val_domain.speech import (
    SpeechRefusedError,
    SpeechRequest,
    SpeechUnavailableError,
    VoiceConditioning,
    digest_of,
)
from val_providers.qwen_tts_speech import (
    MAX_CHARACTERS,
    MODEL_REVISION,
    RUNNER,
    VOICE_DESIGN_MODEL,
    VOICE_DESIGN_REVISION,
    QwenTTSSpeech,
    clone_prompt_for,
)

WAV = b"RIFF\x00\x00\x00\x08WAVE" + b"pretend frames"


def voice(audio: bytes = WAV) -> VoiceConditioning:
    return VoiceConditioning(
        name="val-local-v1",
        reference_audio=audio,
        reference_sha256=digest_of(audio),
        reference_text="Good evening, my lord.",
        voice_description="Adult British woman. Kind, intelligent, warm.",
        designed_by_model=VOICE_DESIGN_MODEL,
        designed_by_revision=VOICE_DESIGN_REVISION,
    )


class RecordingRunner:
    """Answers from a script, and records every invocation exactly as given."""

    def __init__(self, *replies: object) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[list[str], str]] = []

    def run(self, argv: list[str], payload: str, timeout: float) -> tuple[int, str, str]:
        self.calls.append((list(argv), payload))
        request = json.loads(payload)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, str):
            return 1, reply, ""
        # A successful run writes the audio where it was told to.
        Path(request["out_path"]).write_bytes(b"RIFF" + b"\x00" * 60 + b"generated")
        report = {
            "ok": True,
            "sample_rate": 24000,
            "duration_seconds": 2.88,
            "clone_prompt_sha256": "c" * 64,
            "generation": {"temperature": 0.9, "kwargs_passed_to_generate": []},
            **reply,
        }
        return 0, json.dumps(report) + "\n", ""


def adapter(runner: RecordingRunner, tmp_path: Path) -> QwenTTSSpeech:
    """An adapter whose runtime and artifact exist, so `available()` passes."""
    python = tmp_path / "python"
    python.write_text("")
    model = tmp_path / "model"
    model.mkdir()
    return QwenTTSSpeech(
        python=python,
        model_path=model,
        voice_dir=tmp_path,
        runner=runner,  # type: ignore[arg-type]
    )


# --- the boundary, and what never enters it ----------------------------------------


def test_the_argument_vector_is_exactly_the_interpreter_and_the_runner(tmp_path: Path) -> None:
    """Val's words never become an argument; they travel on stdin."""
    runner = RecordingRunner({})
    provider = adapter(runner, tmp_path)
    provider.synthesize(SpeechRequest(text="The work is finished, my lord.", voice=voice()))

    ((argv, payload),) = runner.calls
    assert len(argv) == 2, "the interpreter and the runner, and nothing else"
    assert argv[0] == str(tmp_path / "python")
    assert argv[1] == str(RUNNER)
    sent = json.loads(payload)
    assert sent["text"] == "The work is finished, my lord."
    assert sent["mode"] == "speak", "ordinary speech never re-designs the voice"
    assert not any("my lord" in argument for argument in argv)


def test_nothing_here_can_reach_elevenlabs_or_any_cloud_voice_service() -> None:
    """The order's explicit prohibition, proved structurally rather than promised.

    Comments and docstrings are stripped first, so the module's own
    *prohibitions* are not mistaken for the thing they prohibit.
    """
    import inspect
    import io
    import tokenize

    from val_providers import qwen_tts_speech

    source_text = inspect.getsource(qwen_tts_speech)
    code = "".join(
        token.string
        for token in tokenize.generate_tokens(io.StringIO(source_text).readline)
        if token.type not in (tokenize.COMMENT, tokenize.STRING)
    ).lower()
    for forbidden in ("eleven", "http://", "https://", "requests", "urllib", "azure", "polly"):
        assert forbidden not in code, f"{forbidden!r} must not appear in executable code"


def test_voice_design_is_not_reachable_from_ordinary_speech(tmp_path: Path) -> None:
    """Re-designing the voice per sentence is how a speaker identity drifts."""
    runner = RecordingRunner({})
    provider = adapter(runner, tmp_path)
    provider.synthesize(SpeechRequest(text="Ready when you are.", voice=voice()))
    ((_, payload),) = runner.calls
    sent = json.loads(payload)
    assert sent["mode"] == "speak"
    assert "instruct" not in sent, "no voice description is sent on an ordinary utterance"
    assert sent["model_path"].endswith("model"), "the Base artifact, not the VoiceDesign one"


def test_every_utterance_names_the_same_reusable_clone_prompt(tmp_path: Path) -> None:
    """The identity anchor, not re-derived per sentence."""
    runner = RecordingRunner({}, {})
    provider = adapter(runner, tmp_path)
    provider.synthesize(SpeechRequest(text="One.", voice=voice()))
    provider.synthesize(SpeechRequest(text="Two.", voice=voice()))
    prompts = {json.loads(payload)["clone_prompt_path"] for _, payload in runner.calls}
    assert prompts == {str(clone_prompt_for(digest_of(WAV), tmp_path))}


def test_two_voices_never_share_a_clone_prompt(tmp_path: Path) -> None:
    """One file per reference, so one voice cannot borrow another's codes.

    The library keys its ICL cache on the reference text and waveform, so a
    shared path would let stored codes be loaded under the wrong key — Val
    speaking in the wrong voice while every digest in the record still looked
    right. Unrepresentable rather than guarded against.
    """
    other = b"RIFF" + b"\x00" * 40 + b"a different recording entirely"
    runner = RecordingRunner({}, {})
    provider = adapter(runner, tmp_path)
    provider.synthesize(SpeechRequest(text="One.", voice=voice()))
    provider.synthesize(SpeechRequest(text="One.", voice=voice(other)))
    prompts = [json.loads(payload)["clone_prompt_path"] for _, payload in runner.calls]
    assert len(set(prompts)) == 2, "each reference has its own conditioning file"


# --- the voice must be the governed one --------------------------------------------


def test_a_reference_that_is_not_the_governed_one_is_refused(tmp_path: Path) -> None:
    """A substituted reference is a different voice wearing this voice's name."""
    runner = RecordingRunner({})
    provider = adapter(runner, tmp_path)
    substituted = VoiceConditioning(
        name="val-local-v1",
        reference_audio=b"RIFF someone else entirely",
        reference_sha256=digest_of(WAV),
        reference_text="Good evening, my lord.",
        voice_description="Adult British woman.",
        designed_by_model=VOICE_DESIGN_MODEL,
        designed_by_revision=VOICE_DESIGN_REVISION,
    )
    with pytest.raises(SpeechRefusedError, match="not the governed voice reference"):
        provider.synthesize(SpeechRequest(text="Anything.", voice=substituted))
    assert runner.calls == [], "nothing was started"


def test_a_voice_with_no_transcript_is_refused(tmp_path: Path) -> None:
    """The clone path takes an explicit transcript; there is no automatic one."""
    runner = RecordingRunner({})
    provider = adapter(runner, tmp_path)
    silent = VoiceConditioning(
        name="val-local-v1",
        reference_audio=WAV,
        reference_sha256=digest_of(WAV),
        reference_text="   ",
        voice_description="Adult British woman.",
        designed_by_model=VOICE_DESIGN_MODEL,
        designed_by_revision=VOICE_DESIGN_REVISION,
    )
    with pytest.raises(SpeechRefusedError, match="transcript is empty"):
        provider.synthesize(SpeechRequest(text="Anything.", voice=silent))
    assert runner.calls == []


def test_nothing_to_say_and_too_much_to_say_are_both_refused(tmp_path: Path) -> None:
    runner = RecordingRunner({})
    provider = adapter(runner, tmp_path)
    with pytest.raises(SpeechRefusedError, match="nothing to say"):
        provider.synthesize(SpeechRequest(text="   ", voice=voice()))
    with pytest.raises(SpeechRefusedError, match="ceiling for one utterance"):
        provider.synthesize(SpeechRequest(text="a" * (MAX_CHARACTERS + 1), voice=voice()))
    assert runner.calls == []


# --- one bounded recovery, then an honest stop ---------------------------------------


def test_a_transient_failure_gets_exactly_one_more_attempt(tmp_path: Path) -> None:
    runner = RecordingRunner(OSError("the runtime did not start"), {})
    provider = adapter(runner, tmp_path)
    result = provider.synthesize(SpeechRequest(text="Ready.", voice=voice()))
    assert len(runner.calls) == 2, "one bounded recovery attempt, and it worked"
    assert result.audio.startswith(b"RIFF")


def test_two_failures_stop_honestly_and_say_what_did_not_happen(tmp_path: Path) -> None:
    runner = RecordingRunner(OSError("first reason"), OSError("second reason"))
    provider = adapter(runner, tmp_path)
    with pytest.raises(SpeechUnavailableError) as stopped:
        provider.synthesize(SpeechRequest(text="Ready.", voice=voice()))
    assert len(runner.calls) == 2, "two attempts, not three"
    said = str(stopped.value)
    assert "first reason" in said and "second reason" in said
    assert "No cloud text-to-speech was called" in said


def test_an_absent_runtime_is_reported_as_an_absent_runtime(tmp_path: Path) -> None:
    runner = RecordingRunner()
    provider = QwenTTSSpeech(
        python=tmp_path / "missing",
        model_path=tmp_path,
        voice_dir=tmp_path,
        runner=runner,  # type: ignore[arg-type]
    )
    assert provider.available() is not None
    with pytest.raises(SpeechUnavailableError, match="not installed"):
        provider.synthesize(SpeechRequest(text="Ready.", voice=voice()))
    assert runner.calls == []


# --- what the result carries ---------------------------------------------------------


def test_the_result_carries_the_artifact_identity_and_a_known_zero_cost(
    tmp_path: Path,
) -> None:
    runner = RecordingRunner({})
    result = adapter(runner, tmp_path).synthesize(
        SpeechRequest(text="The work is finished.", voice=voice())
    )
    assert result.provider == "mlxaudio"
    assert result.model_revision == MODEL_REVISION
    assert result.quantization.startswith("8-bit MLX")
    assert result.runtime == "mlx-audio"
    assert result.sample_rate == 24000
    assert result.local is True and result.cost_usd == 0.0
    assert result.clone_prompt_sha256 == "c" * 64
    assert result.generation["kwargs_passed_to_generate"] == []


def test_the_staged_workspace_does_not_outlive_the_run(tmp_path: Path) -> None:
    """The reference copy and the waveform are removed whatever happened."""
    runner = RecordingRunner({})
    provider = adapter(runner, tmp_path)
    provider.synthesize(SpeechRequest(text="Ready.", voice=voice()))
    ((_, payload),) = runner.calls
    written = Path(json.loads(payload)["ref_audio_path"])
    assert not written.exists() and not written.parent.exists()
