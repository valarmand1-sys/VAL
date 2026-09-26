"""Val's voice, on Val's machine — Qwen3-TTS Base through MLX-Audio.

Owner execution order, 22 September 2026. Ordinary use requires no Terminal, no
manual Python, no manual server, no manual model load, no manual prompt creation
and no manual voice selection. This adapter is the whole of what makes that
true.

**The voice is designed, not borrowed.** The conditioning reference was
generated on this machine by the Qwen3-TTS **VoiceDesign** model from the
owner's frozen textual description of Val's voice. No ElevenLabs audio, no
Higgsfield audio, no third-party generated voice and no real person's voice is
conditioning input, and none can be: the reference is checked against its
recorded digest before every run, so a substituted file is refused rather than
spoken with.

**VoiceDesign never runs here.** Its role ended when the reference existed.
Ordinary speech is the Base model conditioned on that reference through
Qwen3-TTS's in-context-learning path — re-designing the voice per sentence is
precisely how a speaker identity drifts, and the reusable clone prompt on disk
is what keeps every utterance anchored to byte-identical material.

**It is not a command path.** The same discipline as the perception adapters:
the interpreter is a constant, the script is a constant, the argument vector is
exactly those two, and there is no shell. The request — Val's words, the
reference path, the digests — travels on **stdin as JSON**, so nothing a model
wrote, a document contained or a tool result returned can become an argument.

**No cloud, and no silent fallback.** There is no HTTP client here and no second
executable. When local speech cannot be produced, after one bounded recovery
attempt, this raises and the caller fails closed. **ElevenLabs is never invoked
automatically.** It may later be an explicit, owner-selected external voice
service; it is not a fallback for this route, and a fallback nobody chose is a
decision nobody made.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from collections.abc import Callable
from pathlib import Path

from val_domain.speech import (
    SpeechRefusedError,
    SpeechRequest,
    SpeechResult,
    SpeechUnavailableError,
    VoiceConditioning,
)

#: The house's dedicated speech runtime. Separate from Val's production Python
#: **and** from the isolated visual runtime: mlx-audio is not a production
#: dependency, and the admitted perception runtime stays exactly as qualified.
VENV_PYTHON = Path.home() / ".val-runtimes" / "mlx-audio-venv" / "bin" / "python"

#: The admitted artifact, at the qualified revision.
MODEL_PATH = Path.home() / ".val-models" / "Qwen3-TTS-12Hz-1.7B-Base-8bit"
MODEL_REVISION = "e7dd0585652209fa0d7783659aad4e8a324de11c"
QUANTIZATION = "8-bit MLX, group size 64, affine"

#: The VoiceDesign model that produced the canonical reference. Recorded here
#: because the voice's provenance belongs beside the voice, not in a comment.
VOICE_DESIGN_MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit"
VOICE_DESIGN_REVISION = "f90d617701d9f7f4ca499291e0b57f2b3c2fd2ee"

#: Where the governed voice lives: its reference recording and the reusable
#: clone prompt derived from it. Fixed paths, outside the repository, because
#: they are operating state rather than source.
VOICE_DIR = Path.home() / ".val-voice"


def clone_prompt_for(reference_sha256: str, directory: Path = VOICE_DIR) -> Path:
    """The reusable conditioning file belonging to **this** reference.

    Keyed on the reference digest rather than fixed, because the library's ICL
    cache is keyed on the reference text and waveform: a single shared path would
    let one voice's stored codes be loaded under another voice's key, and the
    result would be Val speaking in the wrong voice while every digest in the
    record still looked right. One file per voice makes that unrepresentable.
    """
    return directory / f"clone-prompt-{reference_sha256[:16]}.npz"


#: The runner, resolved from this file rather than from a working directory.
RUNNER = Path(__file__).resolve().parents[4] / "infrastructure" / "speech" / "qwen_tts_speak.py"

#: A sentence takes a few seconds once the model is warm and about fifteen when
#: it is not. This is the ceiling before a run is called failed.
RUN_TIMEOUT_SECONDS = 300.0

#: Val does not deliver a chapter in one breath. A ceiling on what may be handed
#: to the runtime at once, so a runaway upstream cannot ask for an hour of audio.
MAX_CHARACTERS = 4_000


def _as_int(value: object) -> int:
    return int(value) if isinstance(value, int | float | str) else 0


def _as_float(value: object) -> float:
    return float(value) if isinstance(value, int | float | str) else 0.0


def _as_mapping(value: object) -> dict[str, object]:
    return {str(key): item for key, item in value.items()} if isinstance(value, dict) else {}


class _Runner:
    """The only place a subprocess is started, so there is one thing to read."""

    def run(self, argv: list[str], payload: str, timeout: float) -> tuple[int, str, str]:
        completed = subprocess.run(  # noqa: S603 - fixed interpreter, fixed script, no shell
            argv,
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        return completed.returncode, completed.stdout, completed.stderr

    def start(self, argv: list[str]) -> subprocess.Popen[str]:
        """The same interpreter and runner, started without waiting — so it can be stopped."""
        return subprocess.Popen(  # noqa: S603 - fixed interpreter, fixed script, no shell
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            # A long-lived worker's unread stderr would fill its pipe and stall it;
            # its failures come back as JSON on stdout instead.
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            shell=False,
        )


#: Seconds of speech per streamed piece. Measured (26 September 2026): at 1.0 the
#: first piece of a sentence was ready in 0.74 s while her answer was still being
#: written, and every later piece arrived before the one ahead of it had finished
#: playing. Shorter pieces would mean more seams for little gain.
STREAM_INTERVAL_SECONDS = 1.0

#: How long a stopped resident worker is given to exit before it is killed outright.
STOP_GRACE_SECONDS = 2.0


class QwenTTSSpeech:
    """Val's local speech provider. Final text in, a waveform out."""

    provider = "mlxaudio"
    model_identifier = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit"

    def __init__(
        self,
        *,
        python: Path = VENV_PYTHON,
        model_path: Path = MODEL_PATH,
        voice_dir: Path = VOICE_DIR,
        runner: _Runner | None = None,
        timeout: float = RUN_TIMEOUT_SECONDS,
    ) -> None:
        self._python = python
        self._model_path = model_path
        self._voice_dir = voice_dir
        self._runner = runner or _Runner()
        self._timeout = timeout
        #: The resident worker (owner order, 25 September 2026, Voice-mode repair §5):
        #: the runner in `serve` mode, the model loaded once, requests one per line.
        #: Started by `warm` at Voice On, stopped by `release` when Voice ends.
        self._resident: subprocess.Popen[str] | None = None
        self._replies: queue.Queue[str | None] = queue.Queue()
        self._resident_lock = threading.Lock()
        self._resident_ready = threading.Event()

    # --- availability -------------------------------------------------------------

    def available(self) -> str | None:
        """Why local speech cannot run at all, or `None`.

        Checked before a run rather than discovered inside one, so an absent
        runtime is reported as an absent runtime instead of as a failed voice.
        """
        if not self._python.exists():
            return f"the dedicated speech runtime is not installed at {self._python}"
        if not self._model_path.is_dir():
            return f"the admitted speech artifact is not present at {self._model_path}"
        if not RUNNER.is_file():
            return f"the speech runner is missing at {RUNNER}"
        return None

    # --- the one entry point ------------------------------------------------------

    def synthesize(self, request: SpeechRequest) -> SpeechResult:
        """Speak this exact text in this voice, with one bounded recovery attempt."""
        text = self._checked(request)
        return self._synthesize(request, text)

    def synthesize_stream(
        self, request: SpeechRequest, on_chunk: Callable[[bytes, float], None]
    ) -> SpeechResult | None:
        """Speak this exact text in this voice, handing each piece over as it exists.

        Owner order, 26 September 2026 (reduce the wait before Val speaks). Measured on
        this Mac with the resident worker, the same texts and conditioning: voicing a
        107-121 character first sentence whole took 2.6-3.2 s alone and 4.3-5.4 s while
        her answer was still being written; its first second of audio, streamed through
        the installed library's own `stream=True` path, was ready in 0.48 s alone and
        0.74 s under the same load, and the rest kept ahead of playback.

        Only through the resident worker, which already holds the model: `None` when it
        is not serving, and the caller speaks the segment whole as before. Each piece is
        a complete little WAV (`on_chunk(bytes, seconds)`); nothing is written to a file.
        The whole waveform is rebuilt here, in memory, and must match the runner's own
        digest — the record's `audio_sha256` is of what was actually handed over.
        """
        text = self._checked(request)
        process = self._resident
        if process is None or process.poll() is not None or not self._resident_ready.is_set():
            return None
        started = time.monotonic()
        workspace = Path(tempfile.mkdtemp(prefix="val-speech-"))
        os.chmod(workspace, 0o700)
        try:
            reference = workspace / "reference.wav"
            reference.write_bytes(request.voice.reference_audio)
            payload = json.dumps(
                {
                    "mode": "speak_stream",
                    "model_path": str(self._model_path),
                    "text": text,
                    "ref_audio_path": str(reference),
                    "ref_audio_sha256": request.voice.reference_sha256,
                    "ref_text": request.voice.reference_text,
                    "clone_prompt_path": str(
                        clone_prompt_for(request.voice.reference_sha256, self._voice_dir)
                    ),
                    "streaming_interval": STREAM_INTERVAL_SECONDS,
                }
            )
            frames: list[bytes] = []
            rate = 0
            with self._resident_lock:
                if self._resident is not process or process.poll() is not None:
                    return None
                try:
                    if process.stdin is None:
                        raise OSError("the resident voice has no input pipe")
                    process.stdin.write(payload.replace("\n", " ") + "\n")
                    process.stdin.flush()
                    while True:
                        reply = self._reply(self._replies, self._timeout)
                        if "chunk" in reply:
                            piece = base64.b64decode(str(reply["wav_base64"]))
                            with wave.open(io.BytesIO(piece)) as reader:
                                rate = reader.getframerate()
                                frames.append(reader.readframes(reader.getnframes()))
                            on_chunk(piece, _as_float(reply.get("duration_seconds")))
                            continue
                        report = reply
                        break
                except (OSError, SpeechUnavailableError) as failure:
                    self._stop_resident_locked()
                    if not frames:
                        return None  # nothing went out: the whole-segment path speaks it
                    raise SpeechUnavailableError(
                        f"local speech stopped part-way through a streamed segment: {failure}"
                    ) from failure
        finally:
            shutil.rmtree(workspace, ignore_errors=True)
        if not report.get("ok"):
            reason = str(report.get("reason", "no reason given"))
            if report.get("kind") == "refused":
                raise SpeechRefusedError(reason)
            raise SpeechUnavailableError(reason)
        whole = io.BytesIO()
        with wave.open(whole, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(rate)
            writer.writeframes(b"".join(frames))
        audio = whole.getvalue()
        if hashlib.sha256(audio).hexdigest() != report.get("audio_sha256"):
            raise SpeechUnavailableError(
                "the streamed pieces do not reassemble into the waveform the runner reported"
            )
        return SpeechResult(
            audio=audio,
            sample_rate=_as_int(report.get("sample_rate")),
            duration_seconds=_as_float(report.get("duration_seconds")),
            provider=self.provider,
            model_identifier=self.model_identifier,
            model_revision=MODEL_REVISION,
            quantization=QUANTIZATION,
            runtime="mlx-audio",
            runtime_version=str(report.get("runtime_version", "0.5.5")),
            generation={
                **_as_mapping(report.get("generation")),
                "stream": True,
                "streaming_interval": STREAM_INTERVAL_SECONDS,
                "decoder_priming": report.get("decoder_priming"),
            },
            clone_prompt_sha256=str(report.get("clone_prompt_sha256", "")),
            elapsed_seconds=round(time.monotonic() - started, 3),
            cost_usd=0.0,
            local=True,
        )

    def _checked(self, request: SpeechRequest) -> str:
        """The text to speak, or the reason it may not be spoken at all."""
        text = request.text.strip()
        if not text:
            raise SpeechRefusedError("there is nothing to say: the text is empty")
        if len(text) > MAX_CHARACTERS:
            raise SpeechRefusedError(
                f"the text is {len(text):,} characters, over this house's "
                f"{MAX_CHARACTERS:,}-character ceiling for one utterance"
            )
        incoherent = request.voice.incoherent()
        if incoherent is not None:
            raise SpeechRefusedError(incoherent)
        unavailable = self.available()
        if unavailable is not None:
            raise SpeechUnavailableError(unavailable)
        return text

    def _synthesize(self, request: SpeechRequest, text: str) -> SpeechResult:
        started = time.monotonic()
        try:
            report, audio = self._attempt(request, text)
        except SpeechUnavailableError as failure:
            # One bounded recovery attempt. A transient failure to start is a
            # real thing; a second one is a condition, not a hiccup.
            first = str(failure)
            try:
                report, audio = self._attempt(request, text)
            except SpeechUnavailableError as again:
                raise SpeechUnavailableError(
                    f"local speech failed twice and is not available. First: {first}. "
                    f"After one bounded recovery attempt: {again}. No cloud text-to-speech "
                    "was called and nothing was charged."
                ) from again

        return SpeechResult(
            audio=audio,
            sample_rate=_as_int(report.get("sample_rate")),
            duration_seconds=_as_float(report.get("duration_seconds")),
            provider=self.provider,
            model_identifier=self.model_identifier,
            model_revision=MODEL_REVISION,
            quantization=QUANTIZATION,
            runtime="mlx-audio",
            runtime_version=str(report.get("runtime_version", "0.5.5")),
            generation=_as_mapping(report.get("generation")),
            clone_prompt_sha256=str(report.get("clone_prompt_sha256", "")),
            elapsed_seconds=round(time.monotonic() - started, 3),
            cost_usd=0.0,
            local=True,
        )

    # --- one attempt --------------------------------------------------------------

    def warm(self, voice: VoiceConditioning | None = None) -> dict[str, object]:
        """Start the resident speech worker: the model loaded once, nothing spoken.

        Owner order, 25 September 2026 (Voice-mode repair §5). The one-shot runner spent
        ~0.26 s starting an interpreter and ~1.0 s loading the model before every
        sentence — about half of each sentence's synthesis, measured on this Mac. The
        worker is the same runner in `serve` mode: the **same** model, settings and
        conditioning, run by the same code, with the load paid once at Voice On instead
        of once per sentence. It holds the model only while Voice is on: `release`
        stops it, and the speech, audio-perception and cognition models go back to
        taking turns in memory.

        Never a gate and never ahead of real speech: a real synthesis that arrives
        while the worker is still loading waits for that load — the one it would
        otherwise do itself — and any failure falls back to the one-shot runner.

        `voice` (26 September 2026): when the governed voice is known, its stored
        conditioning is loaded and the streaming decoder is primed at start, so the
        session's first sentence pays for neither (~0.6 s otherwise).
        """
        unavailable = self.available()
        if unavailable is not None:
            return {"warmed": False, "reason": unavailable}
        started = time.monotonic()
        with self._resident_lock:
            if self._resident is not None and self._resident.poll() is None:
                return {"warmed": True, "resident": True, "already_running": True}
            self._resident_ready.clear()
            try:
                process = self._runner.start([str(self._python), str(RUNNER), "serve"])
            except OSError as failure:
                return {"warmed": False, "reason": f"the voice runtime could not start: {failure}"}
            self._resident = process
            self._replies = queue.Queue()
            threading.Thread(
                target=self._read_replies, args=(process, self._replies), daemon=True
            ).start()
            workspace: Path | None = None
            try:
                if process.stdin is None:
                    raise OSError("the resident voice has no input pipe")
                opening: dict[str, object] = {"model_path": str(self._model_path)}
                if voice is not None:
                    workspace = Path(tempfile.mkdtemp(prefix="val-speech-"))
                    os.chmod(workspace, 0o700)
                    reference = workspace / "reference.wav"
                    reference.write_bytes(voice.reference_audio)
                    opening["prime"] = {
                        "ref_audio_path": str(reference),
                        "ref_audio_sha256": voice.reference_sha256,
                        "ref_text": voice.reference_text,
                        "clone_prompt_path": str(
                            clone_prompt_for(voice.reference_sha256, self._voice_dir)
                        ),
                    }
                process.stdin.write(json.dumps(opening) + "\n")
                process.stdin.flush()
                ready = self._reply(self._replies, self._timeout)
            except (OSError, SpeechUnavailableError) as failure:
                self._stop_resident_locked()
                return {"warmed": False, "reason": f"the resident voice did not start: {failure}"}
            finally:
                if workspace is not None:
                    shutil.rmtree(workspace, ignore_errors=True)
            if ready.get("mode") != "ready":
                self._stop_resident_locked()
                return {"warmed": False, "reason": "the resident voice did not report ready"}
            self._resident_ready.set()
        return {
            "warmed": True,
            "resident": True,
            "load_seconds": ready.get("load_seconds"),
            "primed": ready.get("primed"),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "spoke_nothing": True,
        }

    def release(self) -> dict[str, object]:
        """Stop the resident worker, and give its memory back to the machine."""
        with self._resident_lock:
            running = self._resident is not None
            self._stop_resident_locked()
        return {"released": running}

    @property
    def resident(self) -> bool:
        """Whether a loaded resident worker is serving."""
        process = self._resident
        return process is not None and process.poll() is None and self._resident_ready.is_set()

    def _stop_resident_locked(self) -> None:
        process, self._resident = self._resident, None
        self._resident_ready.clear()
        if process is None:
            return
        try:
            if process.stdin is not None and process.poll() is None:
                process.stdin.write(json.dumps({"mode": "stop"}) + "\n")
                process.stdin.flush()
                process.stdin.close()
            process.wait(timeout=STOP_GRACE_SECONDS)
        except OSError, subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=STOP_GRACE_SECONDS)

    @staticmethod
    def _read_replies(process: subprocess.Popen[str], replies: queue.Queue[str | None]) -> None:
        """Every stdout line of the worker, in order; `None` when it ends."""
        if process.stdout is None:
            replies.put(None)
            return
        for line in process.stdout:
            replies.put(line)
        replies.put(None)

    @staticmethod
    def _reply(replies: queue.Queue[str | None], timeout: float) -> dict[str, object]:
        """The worker's next JSON reply, skipping anything on stdout that is not one."""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SpeechUnavailableError(
                    f"the resident voice did not reply within {timeout:.0f}s"
                )
            try:
                line = replies.get(timeout=remaining)
            except queue.Empty as empty:
                raise SpeechUnavailableError(
                    f"the resident voice did not reply within {timeout:.0f}s"
                ) from empty
            if line is None:
                raise SpeechUnavailableError("the resident voice exited")
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

    def _run_resident(self, payload: str) -> dict[str, object] | None:
        """One request through the resident worker, or `None` to use the one-shot path.

        A request arriving while the worker loads waits for that load. Any failure
        stops the worker, so a broken one is never asked twice, and the caller runs
        the ordinary one-shot synthesis instead.
        """
        process = self._resident
        if process is None or process.poll() is not None:
            return None
        if not self._resident_ready.wait(timeout=self._timeout):
            return None
        with self._resident_lock:
            if self._resident is not process or process.poll() is not None:
                return None
            try:
                if process.stdin is None:
                    raise OSError("the resident voice has no input pipe")
                process.stdin.write(payload.replace("\n", " ") + "\n")
                process.stdin.flush()
                return self._reply(self._replies, self._timeout)
            except OSError, SpeechUnavailableError:
                self._stop_resident_locked()
                return None

    def _attempt(self, request: SpeechRequest, text: str) -> tuple[dict[str, object], bytes]:
        workspace = Path(tempfile.mkdtemp(prefix="val-speech-"))
        os.chmod(workspace, 0o700)
        try:
            reference = workspace / "reference.wav"
            reference.write_bytes(request.voice.reference_audio)
            out_path = workspace / "speech.wav"
            payload = json.dumps(
                {
                    "mode": "speak",
                    "model_path": str(self._model_path),
                    "text": text,
                    "ref_audio_path": str(reference),
                    "ref_audio_sha256": request.voice.reference_sha256,
                    "ref_text": request.voice.reference_text,
                    # Belonging to this reference, so a second voice can never
                    # be conditioned on the first one's codes.
                    "clone_prompt_path": str(
                        clone_prompt_for(request.voice.reference_sha256, self._voice_dir)
                    ),
                    "out_path": str(out_path),
                }
            )
            resident = self._run_resident(payload)
            if resident is not None:
                report = resident
            else:
                try:
                    code, out, err = self._runner.run(
                        [str(self._python), str(RUNNER)], payload, self._timeout
                    )
                except subprocess.TimeoutExpired as expired:
                    raise SpeechUnavailableError(
                        f"the speech run did not finish within {self._timeout:.0f}s"
                    ) from expired
                except OSError as failure:
                    raise SpeechUnavailableError(
                        f"the dedicated speech runtime could not be started: {failure}"
                    ) from failure
                report = self._parse(code, out, err)
            if not report.get("ok"):
                reason = str(report.get("reason", "no reason given"))
                if report.get("kind") == "refused":
                    raise SpeechRefusedError(reason)
                raise SpeechUnavailableError(reason)
            if not out_path.is_file():
                raise SpeechUnavailableError(
                    "the speech run reported success and produced no audio file"
                )
            audio = out_path.read_bytes()
            if not audio:
                raise SpeechUnavailableError("the speech run produced an empty audio file")
            return report, audio
        finally:
            # The reference copy and the waveform are removed whatever happened;
            # what survives is what the caller chose to keep.
            shutil.rmtree(workspace, ignore_errors=True)

    @staticmethod
    def _parse(code: int, out: str, err: str) -> dict[str, object]:
        """The runner's last stdout line, as JSON, or a failure worth reading."""
        line = next((text for text in reversed(out.splitlines()) if text.strip()), "")
        if not line:
            detail = (err.strip().splitlines() or ["no output"])[-1]
            raise SpeechUnavailableError(
                f"the speech run produced no result (exit {code}): {detail}"
            )
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as broken:
            raise SpeechUnavailableError(
                f"the speech run produced output that is not a result (exit {code})"
            ) from broken
        if not isinstance(parsed, dict):
            raise SpeechUnavailableError("the speech run produced a result of the wrong shape")
        return parsed


#: The governed voice record, written when the voice was designed and read by
#: the composition root. The voice is a self-describing object: the reference,
#: its transcript, the frozen description it was designed from, and the model
#: that designed it, all in one place, so nothing has to be remembered.
VOICE_RECORD = VOICE_DIR / "val-voice.json"


def canonical_voice_description(record: Path = VOICE_RECORD) -> dict[str, object]:
    """The governed voice record's own descriptive metadata, as written when it was designed.

    Owner acceptance repair, 25 September 2026 (WP3 §3). The composition root needs
    these fields to register the voice in the store, and **they are read from the
    record rather than restated anywhere**: the reference's sample rate and duration,
    what designed it and how, its origin, and the identity claim in its own words.
    Nothing here is invented, defaulted or inferred — a record missing a field is a
    record that cannot be registered, and it says so.
    """
    if not record.is_file():
        raise SpeechUnavailableError(f"Val has no governed local voice: {record} does not exist")
    try:
        described = json.loads(record.read_text())
        return {
            "reference_sample_rate": int(described["reference_sample_rate"]),
            "reference_duration_seconds": float(described["reference_duration_seconds"]),
            "designed_by_quantization": str(described["designed_by_quantization"]),
            "designed_by_runtime": str(described["designed_by_runtime"]),
            "designed_generation": described["designed_generation"],
            "origin": str(described["origin"]),
            "identity_claim": str(described["identity_claim"]),
        }
    except (OSError, ValueError, KeyError, TypeError) as broken:
        raise SpeechUnavailableError(
            f"the governed voice record at {record} is incomplete: {broken}"
        ) from broken


def load_canonical_voice(record: Path = VOICE_RECORD) -> VoiceConditioning:
    """Val's governed local voice, read from disk.

    Raises `SpeechUnavailableError` when the voice has not been designed yet or
    its reference is missing — a house with no voice says so rather than
    substituting one.
    """
    if not record.is_file():
        raise SpeechUnavailableError(f"Val has no governed local voice: {record} does not exist")
    try:
        described = json.loads(record.read_text())
        reference = Path(described["reference_path"])
        audio = reference.read_bytes()
    except (OSError, ValueError, KeyError) as broken:
        raise SpeechUnavailableError(
            f"the governed voice record at {record} could not be read: {broken}"
        ) from broken
    return VoiceConditioning(
        name=str(described["name"]),
        reference_audio=audio,
        reference_sha256=str(described["reference_sha256"]),
        reference_text=str(described["reference_text"]),
        voice_description=str(described["voice_description"]),
        designed_by_model=str(described["designed_by_model"]),
        designed_by_revision=str(described["designed_by_revision"]),
    )
