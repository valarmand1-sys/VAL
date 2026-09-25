"""Val's ears, on Val's machine — whisper.cpp and Silero VAD, locally.

Owner execution order, Voice mode work package 1. The smallest proper production
boundary around the already-installed whisper.cpp runtime: Val's service supplies
in-memory PCM and receives structured recognition events.

**It owns no microphone.** Audio is handed to it by a caller. This adapter never
opens a capture device, never asks the operating system for one, and cannot: the
helper it starts is built without SDL and takes its audio from stdin.

**Nothing is written to disk and nothing is kept.** There is no temporary WAV, no
temporary MP3, no spool file and no cache of samples. PCM crosses a pipe into a
volatile buffer, is transcribed, and is released.

**No cloud, and no fallback.** There is no HTTP client here and no second
executable. Qwen3-Omni can transcribe audio and is **deliberately not reachable
from this path**: it is Val's admitted *perception* specialist for recordings the
owner attached, which is a different act from hearing him speak, and a fallback
nobody chose is a decision nobody made. When local recognition cannot run, this
raises and the caller fails closed.

**The recognizer is provably the admitted one.** The library, the ASR model and
the VAD model are all pinned, and the two models are checked against their
recorded digests before a session opens — so a substituted model is refused
rather than quietly listened with.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import struct
import subprocess
import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

from val_domain.voice import (
    SAMPLE_RATE,
    EndpointConfiguration,
    RecognizerEvent,
    RecognizerIdentity,
    VoiceUnavailableError,
    pcm_is_valid,
)

#: The pinned build. Settled evidence, not re-derived here.
WHISPER_VERSION = "v1.9.4"
WHISPER_COMMIT = "927cfce34f31707e17f2bff35c349632fb9e2c3a"
WHISPER_BUILD = Path.home() / ".val-runtimes" / "whisper.cpp" / "build"
LIBRARY = WHISPER_BUILD / "bin" / "libwhisper.dylib"

#: The house's dedicated voice runtime: its own interpreter holding numpy alone.
#: Separate from Val's production Python, from the visual runtime and from the
#: speech runtime, so no recognizer dependency can reach production.
VENV_PYTHON = Path.home() / ".val-runtimes" / "voice-venv" / "bin" / "python"

#: The admitted models, by path and by digest.
MODELS = Path.home() / ".val-models" / "whisper"
ASR_MODEL = MODELS / "ggml-small.en.bin"
ASR_MODEL_IDENTIFIER = "ggml-small.en"
ASR_MODEL_SHA256 = "c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d"
VAD_MODEL = MODELS / "ggml-silero-v6.2.0.bin"
VAD_MODEL_IDENTIFIER = "silero-vad-v6.2.0"
VAD_MODEL_SHA256 = "2aa269b785eeb53a82983a20501ddf7c1d9c48e33ab63a41391ac6c9f7fb6987"

#: The helper, resolved from this file rather than from a working directory.
HELPER = Path(__file__).resolve().parents[4] / "infrastructure" / "voice" / "whisper_listen.py"

#: The framed stdin protocol. Two kinds, because a live session needs exactly
#: two: audio, and a word about what to do with it.
FRAME_PCM = 0
FRAME_CONTROL = 1

#: How long the helper may take to announce itself before its absence is called
#: an absence. Model load is measured in tenths of a second; this is generous.
READY_TIMEOUT_SECONDS = 60.0

#: How long a stopped helper may take to leave before it is ended outright.
STOP_TIMEOUT_SECONDS = 10.0

#: A ceiling on one handed-over block, so a runaway caller cannot push an hour of
#: audio into a single frame. Thirty seconds is far beyond any sane block.
MAX_BLOCK_BYTES = SAMPLE_RATE * 2 * 30


def frame(kind: int, payload: bytes) -> bytes:
    """One record of the helper's stdin protocol: `[u32 kind][u32 length][payload]`.

    Length-prefixed rather than delimited, because PCM contains every byte value
    including whatever delimiter one might pick. A framing bug would desynchronize
    the stream silently, so the encoding lives in one function with one test.
    """
    return struct.pack("<II", kind, len(payload)) + payload


def digest_of_file(path: Path) -> str:
    """The file's SHA-256, read in chunks so a half-gigabyte model is cheap."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fingerprint(path: Path) -> tuple[int, int, int, int, int]:
    """The file's observed identity, as the operating system reports it.

    Five fields, each earning its place (owner execution order, work package 2 §4.1):

      * `st_dev` and `st_ino` — *which file this is*. A replacement written
        elsewhere and renamed over the path is a different inode, so
        rename-over substitution cannot inherit a cached result.
      * `st_size` — the obvious change.
      * `st_mtime_ns` — the obvious change to content.
      * `st_ctime_ns` — the one that closes the gap. An in-place edit whose size
        and modification time are then restored still moves the inode change
        time, and nothing in user space can put it back.

    Path alone is not identity, and size and mtime alone are forgeable by anyone
    with `touch`.
    """
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


#: A digest is remembered only against the exact file it was computed from, so a
#: half-gigabyte model is hashed once while it stays that same unchanged file —
#: and is rehashed the moment it does not.
_verified: dict[Path, tuple[tuple[int, int, int, int, int], str]] = {}


def verify(path: Path, expected: str) -> None:
    """Refuse a model that is not the admitted one.

    The cache is keyed on the file's stat fingerprint as well as its path and the
    admitted digest. **A file replaced after a successful verification is hashed
    again**, which is what the module's stated guarantee has always claimed and
    what it did not previously do: the earlier cache was keyed on the path alone,
    so a substitution after the first session was accepted without being read.
    """
    observed = fingerprint(path)
    remembered = _verified.get(path)
    if remembered is not None and remembered == (observed, expected):
        return
    actual = digest_of_file(path)
    if actual != expected:
        # Forget the path entirely rather than remembering a refusal: the next
        # attempt should read the file, not trust a recorded verdict about it.
        _verified.pop(path, None)
        raise VoiceUnavailableError(
            f"{path.name} is not the admitted model: expected {expected}, found {actual}. "
            "Nothing was transcribed and no cloud recognizer was called."
        )
    # Re-stat after hashing: if the file changed while it was being read, the
    # fingerprint recorded would describe neither version, and remembering it
    # would cache a digest for a file that no longer exists in that state.
    settled = fingerprint(path)
    if settled == observed:
        _verified[path] = (observed, actual)


class WhisperRecognizer:
    """One live recognizer: PCM in, recognition events out.

    Satisfies `val_domain.voice.LiveRecognizer`. It holds a subprocess, a reader
    thread and a queue, and no conversation, identity, policy or authority.
    """

    def __init__(
        self,
        *,
        endpoint: EndpointConfiguration | None = None,
        python: Path = VENV_PYTHON,
        helper: Path = HELPER,
        asr_model: Path = ASR_MODEL,
        vad_model: Path = VAD_MODEL,
        library: Path = LIBRARY,
    ) -> None:
        self.endpoint = endpoint or EndpointConfiguration()
        self._python = python
        self._helper = helper
        self._asr_model = asr_model
        self._vad_model = vad_model
        self._library = library
        self._process: subprocess.Popen[bytes] | None = None
        self._events: queue.Queue[RecognizerEvent] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._lock = threading.Lock()

    # --- identity -------------------------------------------------------------------

    @property
    def identity(self) -> RecognizerIdentity:
        """Exactly what heard this, for the record."""
        return RecognizerIdentity(
            name="whisper.cpp",
            version=WHISPER_VERSION,
            commit=WHISPER_COMMIT,
            model_identifier=ASR_MODEL_IDENTIFIER,
            model_sha256=ASR_MODEL_SHA256,
            vad_model_identifier=VAD_MODEL_IDENTIFIER,
            vad_model_sha256=VAD_MODEL_SHA256,
        )

    # --- availability ---------------------------------------------------------------

    def available(self) -> str | None:
        """Why live voice cannot run at all, or `None`.

        Checked before a session opens rather than discovered inside one, so an
        absent runtime is reported as an absent runtime instead of as a failure
        to hear.
        """
        if not self._python.exists():
            return f"the dedicated voice runtime is not installed at {self._python}"
        if not self._helper.is_file():
            return f"the recognizer helper is missing at {self._helper}"
        if not self._library.is_file():
            return f"the whisper.cpp shared library is missing at {self._library}"
        if not self._asr_model.is_file():
            return f"the admitted speech-recognition model is missing at {self._asr_model}"
        if not self._vad_model.is_file():
            return f"the admitted voice-activity model is missing at {self._vad_model}"
        return None

    # --- lifecycle ------------------------------------------------------------------

    def start(self) -> None:
        """Bring the recognizer up, with its models proved before it listens."""
        if self._process is not None:
            return
        unavailable = self.available()
        if unavailable is not None:
            raise VoiceUnavailableError(unavailable)
        verify(self._asr_model, ASR_MODEL_SHA256)
        verify(self._vad_model, VAD_MODEL_SHA256)

        configuration = json.dumps(
            {
                "model": str(self._asr_model),
                "vad_model": str(self._vad_model),
                "endpoint": self.endpoint.as_record(),
            }
        )
        try:
            process = subprocess.Popen(  # noqa: S603 - fixed interpreter, fixed helper, no shell
                [str(self._python), str(self._helper), configuration],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                # The helper's diagnostics are whisper.cpp's own chatter. They are
                # not evidence and are not worth a pipe nobody drains.
                stderr=subprocess.DEVNULL,
                shell=False,
                # The library is named rather than searched for. The rest of the
                # environment is inherited, because the shared library resolves
                # its own ggml dependencies through the loader's paths.
                env={**os.environ, "VAL_WHISPER_LIB": str(self._library)},
            )
        except OSError as failure:
            raise VoiceUnavailableError(
                f"the dedicated voice runtime could not be started: {failure}"
            ) from failure

        self._process = process
        self._reader = threading.Thread(target=self._read, args=(process,), daemon=True)
        self._reader.start()

        ready = self._await("ready", READY_TIMEOUT_SECONDS)
        if ready.kind == "error":
            self.stop()
            raise VoiceUnavailableError(f"the recognizer could not start: {ready.detail}")

    def _read(self, process: subprocess.Popen[bytes]) -> None:
        """One JSON line at a time, off the helper's stdout, onto the queue."""
        if process.stdout is None:
            return
        for line in process.stdout:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except ValueError:
                continue
            if isinstance(payload, dict):
                # Stamped on arrival, on this process's clock — the only way a
                # helper boundary can be placed on the service's timeline.
                received = time.monotonic()
                self._events.put(replace(RecognizerEvent.of(payload), received_at=received))

    def _await(self, kind: str, timeout: float) -> RecognizerEvent:
        """Wait for one particular event, keeping anything that arrives first."""
        held: list[RecognizerEvent] = []
        remaining = timeout
        while remaining > 0:
            step = min(0.25, remaining)
            try:
                event = self._events.get(timeout=step)
            except queue.Empty:
                remaining -= step
                if self._process is not None and self._process.poll() is not None:
                    break
                continue
            if event.kind in (kind, "error"):
                for kept in held:
                    self._events.put(kept)
                return event
            held.append(event)
        for kept in held:
            self._events.put(kept)
        raise VoiceUnavailableError(
            f"the recognizer did not report {kind!r} within {timeout:.0f}s. "
            "No cloud speech recognition was called."
        )

    def stop(self) -> None:
        """Release the recognizer and everything it holds."""
        process, self._process = self._process, None
        if process is None:
            return
        try:
            self._send(process, FRAME_CONTROL, json.dumps({"action": "stop"}).encode())
        except VoiceUnavailableError:
            pass
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            process.wait(timeout=STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=STOP_TIMEOUT_SECONDS)
        if self._reader is not None:
            self._reader.join(timeout=STOP_TIMEOUT_SECONDS)
            self._reader = None

    # --- the live path --------------------------------------------------------------

    def feed(self, pcm: bytes) -> None:
        """One block of 16 kHz mono little-endian int16 PCM.

        Validated and handed straight over. It is not copied anywhere else, not
        accumulated here, and not written down.
        """
        invalid = pcm_is_valid(pcm)
        if invalid is not None:
            raise VoiceUnavailableError(f"this audio block cannot be recognized: {invalid}")
        if len(pcm) > MAX_BLOCK_BYTES:
            raise VoiceUnavailableError(
                f"a single audio block of {len(pcm):,} bytes is over this house's "
                f"{MAX_BLOCK_BYTES:,}-byte ceiling"
            )
        self._send(self._running(), FRAME_PCM, pcm)

    def flush(self) -> None:
        """End the utterance in progress, if any, and finalize it."""
        self._send(self._running(), FRAME_CONTROL, json.dumps({"action": "flush"}).encode())

    def reset(self) -> None:
        """Forget the utterance in progress without finalizing it.

        For abandoning a breath, not for ending one: nothing is transcribed and
        no `final` follows.
        """
        self._send(self._running(), FRAME_CONTROL, json.dumps({"action": "reset"}).encode())

    def drain(self) -> Iterator[RecognizerEvent]:
        """Every event observed since the last drain, in order."""
        while True:
            try:
                yield self._events.get_nowait()
            except queue.Empty:
                return

    def await_final(self, timeout: float) -> RecognizerEvent:
        """Block until this utterance is settled. Used by the acceptance path."""
        return self._await("final", timeout)

    # --- the pipe -------------------------------------------------------------------

    def _running(self) -> subprocess.Popen[bytes]:
        if self._process is None or self._process.poll() is not None:
            raise VoiceUnavailableError(
                "the recognizer is not running. No cloud speech recognition was called."
            )
        return self._process

    def _send(self, process: subprocess.Popen[bytes], kind: int, payload: bytes) -> None:
        if process.stdin is None:
            raise VoiceUnavailableError("the recognizer has no input channel")
        record = frame(kind, payload)
        # One writer at a time: a half-written frame would desynchronize the
        # protocol, and two threads feeding one session is an ordinary shape.
        with self._lock:
            try:
                process.stdin.write(record)
                process.stdin.flush()
            except (BrokenPipeError, OSError) as failure:
                raise VoiceUnavailableError(
                    f"the recognizer stopped accepting audio: {failure}. "
                    "No cloud speech recognition was called."
                ) from failure

    # --- a session, bounded ---------------------------------------------------------

    def __enter__(self) -> WhisperRecognizer:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()
