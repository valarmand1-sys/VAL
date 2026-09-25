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

import json
import os
import shutil
import subprocess
import tempfile
import time
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

    def warm(self) -> dict[str, object]:
        """Load the voice model and generate nothing.

        Owner acceptance, 25 September 2026 (WP3 Step B §9). Each synthesis is its own
        subprocess, so the first one of a session pays for reading the weights off
        disk. Measured in his run: **6.708 s** for a 1.68 s phrase against **2.727 s**
        once the file was in the page cache — about four seconds, sitting directly in
        front of his first answer.

        This is the same shape as the cognition warming the latency pass established:
        done early, on the session's own thread, while he is still speaking, and
        **never a gate** — a failure is reported and the turn proceeds exactly as it
        would have. It produces no audio, writes no file and records no provenance,
        because Val has not spoken and there is nothing to attribute.
        """
        unavailable = self.available()
        if unavailable is not None:
            return {"warmed": False, "reason": unavailable}
        payload = json.dumps({"mode": "warm", "model_path": str(self._model_path), "out_path": ""})
        started = time.monotonic()
        try:
            code, out, err = self._runner.run(
                [str(self._python), str(RUNNER)], payload, self._timeout
            )
        except subprocess.TimeoutExpired:
            return {"warmed": False, "reason": "the voice runtime did not load in time"}
        elapsed = round(time.monotonic() - started, 3)
        if code != 0:
            return {"warmed": False, "reason": (err or out or "the voice runtime failed").strip()}
        try:
            report = json.loads(out.strip().splitlines()[-1])
        except ValueError, IndexError:
            return {"warmed": False, "reason": "the voice runtime reported nothing readable"}
        return {
            "warmed": bool(report.get("warmed")),
            "load_seconds": report.get("load_seconds"),
            "elapsed_seconds": elapsed,
            "spoke_nothing": True,
        }

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
