"""Val's ears at the boundary — Voice mode work package 1, 23 September 2026.

What is pinned here is the boundary, not whisper's accuracy: the recognizer's own
behaviour was settled by its proof against real PCM. What has to hold is that the
argument vector is exactly the interpreter and the helper, that audio travels as
framed bytes on stdin and never as an argument or a file, that a model which is
not the admitted one is refused before anything listens, and the claim the order
asks for most explicitly — **no cloud speech recognition and no Qwen3-Omni
fallback is reachable from this path**, because the only executable this module
can start is the one it names.

These tests do not require whisper.cpp to be installed. They are the contract, and
the contract is what CI can hold on a machine with no Metal and no models.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from val_domain.voice import EndpointConfiguration, LiveRecognizer, VoiceUnavailableError
from val_providers.whisper_recognizer import (
    ASR_MODEL_SHA256,
    FRAME_CONTROL,
    FRAME_PCM,
    MAX_BLOCK_BYTES,
    VAD_MODEL_SHA256,
    WHISPER_COMMIT,
    WHISPER_VERSION,
    WhisperRecognizer,
    digest_of_file,
    frame,
    verify,
)

PCM = b"\x11\x22" * 160


class FakeProcess:
    """A started helper, standing still. Records every byte written to it."""

    def __init__(self, *, running: bool = True) -> None:
        self.written = bytearray()
        self.stdin = self
        self.stdout = iter(())
        self.killed = False
        self.waited = False
        #: A helper that has already left. `start` notices and stops waiting,
        #: rather than sitting out the whole ready timeout.
        self.running = running

    # stdin
    def write(self, data: bytes) -> int:
        self.written.extend(data)
        return len(data)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None

    # process
    def poll(self) -> int | None:
        return None if self.running else 0

    def wait(self, timeout: float | None = None) -> int:
        self.waited = True
        return 0

    def kill(self) -> None:
        self.killed = True


def installed(tmp_path: Path) -> WhisperRecognizer:
    """A recognizer whose every artifact exists, so `available()` passes.

    The two model files carry content whose digests are then registered as the
    admitted ones, so the verification path can be exercised without half a
    gigabyte of real model.
    """
    python = tmp_path / "python"
    python.write_text("")
    helper = tmp_path / "whisper_listen.py"
    helper.write_text("")
    library = tmp_path / "libwhisper.dylib"
    library.write_text("")
    asr = tmp_path / "ggml-small.en.bin"
    asr.write_bytes(b"the admitted recognition model")
    vad = tmp_path / "ggml-silero.bin"
    vad.write_bytes(b"the admitted activity model")
    return WhisperRecognizer(
        python=python, helper=helper, library=library, asr_model=asr, vad_model=vad
    )


# --- the framed protocol -------------------------------------------------------------


def test_the_frame_is_a_length_prefixed_record_of_the_declared_kind() -> None:
    """Length-prefixed, because PCM contains every byte a delimiter could use."""
    record = frame(FRAME_PCM, PCM)
    kind, length = struct.unpack("<II", record[:8])
    assert (kind, length) == (FRAME_PCM, len(PCM))
    assert record[8:] == PCM, "the samples are carried verbatim"
    assert frame(FRAME_CONTROL, b"{}") == struct.pack("<II", 1, 2) + b"{}"


def test_audio_travels_on_stdin_and_never_as_an_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The argument vector is the interpreter, the helper, and one configuration."""
    started: list[list[str]] = []
    process = FakeProcess()

    def fake_popen(argv: list[str], **kwargs: object) -> FakeProcess:
        started.append(argv)
        assert kwargs["shell"] is False, "there is no shell anywhere on this path"
        return process

    monkeypatch.setattr("val_providers.whisper_recognizer.subprocess.Popen", fake_popen)
    recognizer = installed(tmp_path)
    monkeypatch.setattr("val_providers.whisper_recognizer.verify", lambda path, expected: None)
    # `start` waits for the helper's `ready`; the fake never speaks, so the
    # protocol is exercised by placing the process directly.
    recognizer._process = process

    recognizer.feed(PCM)
    recognizer.flush()

    assert bytes(process.written) == frame(FRAME_PCM, PCM) + frame(
        FRAME_CONTROL, json.dumps({"action": "flush"}).encode()
    )
    assert started == [], "no second executable was involved"


def test_the_configuration_is_one_argument_and_names_the_pinned_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[list[str]] = []

    def fake_popen(argv: list[str], **kwargs: object) -> FakeProcess:
        started.append(argv)
        return FakeProcess(running=False)

    monkeypatch.setattr("val_providers.whisper_recognizer.subprocess.Popen", fake_popen)
    monkeypatch.setattr("val_providers.whisper_recognizer.verify", lambda path, expected: None)
    recognizer = installed(tmp_path)
    with pytest.raises(VoiceUnavailableError, match="did not report 'ready'"):
        recognizer.start()

    ((argv),) = started
    assert len(argv) == 3, "the interpreter, the helper, and the configuration"
    assert argv[0] == str(tmp_path / "python")
    assert argv[1] == str(tmp_path / "whisper_listen.py")
    configuration = json.loads(argv[2])
    assert configuration["model"].endswith("ggml-small.en.bin")
    assert configuration["vad_model"].endswith("ggml-silero.bin")
    assert configuration["endpoint"] == EndpointConfiguration().as_record()


# --- the models must be the admitted ones ---------------------------------------------


def test_a_substituted_model_is_refused_before_anything_listens(tmp_path: Path) -> None:
    """A different model is a different pair of ears wearing this one's name."""
    file = tmp_path / "model.bin"
    file.write_bytes(b"not the admitted model")
    with pytest.raises(VoiceUnavailableError, match="is not the admitted model"):
        verify(file, "0" * 64)


def test_the_admitted_digest_is_accepted_and_remembered(tmp_path: Path) -> None:
    """Half a gigabyte of hashing once per process, not once per session."""
    file = tmp_path / "model.bin"
    file.write_bytes(b"the admitted model")
    digest = digest_of_file(file)
    verify(file, digest)
    file.write_bytes(b"changed underneath")
    verify(file, digest), "remembered for this process; a model file does not change under us"


def test_starting_refuses_when_a_model_is_not_the_admitted_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal happens at `start`, before a subprocess exists."""
    started: list[object] = []
    monkeypatch.setattr(
        "val_providers.whisper_recognizer.subprocess.Popen",
        lambda *a, **k: started.append(a) or FakeProcess(),
    )
    recognizer = installed(tmp_path)
    with pytest.raises(VoiceUnavailableError) as refused:
        recognizer.start()
    assert "is not the admitted model" in str(refused.value)
    assert "no cloud recognizer was called" in str(refused.value)
    assert started == [], "nothing was started"


# --- availability, stated plainly ------------------------------------------------------


def test_each_missing_piece_is_reported_as_itself(tmp_path: Path) -> None:
    """An absent runtime is an absent runtime, not a failure to hear."""
    recognizer = installed(tmp_path)
    assert recognizer.available() is None

    for path, expected in (
        (tmp_path / "python", "voice runtime is not installed"),
        (tmp_path / "whisper_listen.py", "recognizer helper is missing"),
        (tmp_path / "libwhisper.dylib", "shared library is missing"),
        (tmp_path / "ggml-small.en.bin", "speech-recognition model is missing"),
        (tmp_path / "ggml-silero.bin", "voice-activity model is missing"),
    ):
        kept = path.read_bytes()
        path.unlink()
        reported = recognizer.available()
        assert reported is not None and expected in reported
        path.write_bytes(kept)
    assert recognizer.available() is None


def test_feeding_a_recognizer_that_is_not_running_says_so(tmp_path: Path) -> None:
    recognizer = installed(tmp_path)
    with pytest.raises(VoiceUnavailableError, match="not running"):
        recognizer.feed(PCM)


def test_audio_that_is_not_the_contract_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recognizer = installed(tmp_path)
    recognizer._process = FakeProcess()
    with pytest.raises(VoiceUnavailableError, match="empty block"):
        recognizer.feed(b"")
    with pytest.raises(VoiceUnavailableError, match="whole number of"):
        recognizer.feed(b"\x00\x00\x00")
    with pytest.raises(VoiceUnavailableError, match="ceiling"):
        recognizer.feed(b"\x00\x00" * (MAX_BLOCK_BYTES // 2 + 1))


# --- identity, and the two negatives --------------------------------------------------


def test_the_recognizer_names_exactly_what_heard_the_words(tmp_path: Path) -> None:
    identity = installed(tmp_path).identity.as_record()
    assert identity["recognizer"] == "whisper.cpp"
    assert identity["recognizer_version"] == WHISPER_VERSION == "v1.9.4"
    assert identity["recognizer_commit"] == WHISPER_COMMIT
    assert identity["asr_model"] == "ggml-small.en"
    assert identity["asr_model_sha256"] == ASR_MODEL_SHA256
    assert identity["vad_model"] == "silero-vad-v6.2.0"
    assert identity["vad_model_sha256"] == VAD_MODEL_SHA256
    assert len(ASR_MODEL_SHA256) == len(VAD_MODEL_SHA256) == 64


def test_the_adapter_satisfies_the_domain_boundary(tmp_path: Path) -> None:
    """The core depends on the protocol; this is the thing that has to fit it."""
    assert isinstance(installed(tmp_path), LiveRecognizer)


def test_no_cloud_recognizer_and_no_omni_fallback_is_reachable_from_this_module() -> None:
    """The order's explicit prohibition, proved structurally rather than promised.

    Comments and docstrings are stripped first, so the module's own *prohibitions*
    are not mistaken for the thing they prohibit.
    """
    import inspect
    import io
    import tokenize

    from val_providers import whisper_recognizer

    code = "".join(
        token.string
        for token in tokenize.generate_tokens(
            io.StringIO(inspect.getsource(whisper_recognizer)).readline
        )
        if token.type not in (tokenize.COMMENT, tokenize.STRING)
    ).lower()
    for forbidden in (
        "http://",
        "https://",
        "requests",
        "urllib",
        "httpx",
        "openai",
        "deepgram",
        "assemblyai",
        "azure",
        "omni",
        "whisper_api",
    ):
        assert forbidden not in code, f"{forbidden!r} must not appear in executable code"


def test_nothing_here_writes_a_file() -> None:
    """No temporary WAV, no spool, no cache of samples — in the executable code."""
    import inspect
    import io
    import tokenize

    from val_providers import whisper_recognizer

    code = "".join(
        token.string
        for token in tokenize.generate_tokens(
            io.StringIO(inspect.getsource(whisper_recognizer)).readline
        )
        if token.type not in (tokenize.COMMENT, tokenize.STRING)
    )
    for forbidden in ("write_bytes", "write_text", "NamedTemporaryFile", "mkdtemp", "wave"):
        assert forbidden not in code, f"{forbidden} must not appear: audio is never written down"
