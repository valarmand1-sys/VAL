"""Qwen3-Omni audio perception, through llama.cpp, without a terminal.

Owner execution order, 22 September 2026 §8. Val hears the owner's recordings on
the owner's own machine. The model is admitted for **audio and nothing else** —
its artifact carries a vision encoder too, and that is a fact about the file
rather than a permission — so `modalities` here names one modality and routing
reads that, not the model's name or its capabilities.

**The same shape as the visual adapter, deliberately.** One subprocess per run,
over fixed artifact paths, with no shell; the process exits and its memory
returns, which is how a 19 GB audio model and a 12 GB cognition model take turns
on a 48 GB machine instead of competing. There is nothing to start, nothing to
keep warm, and nothing for the owner to unload.

**Nothing the owner wrote reaches the argument vector.** `llama-mtmd-cli` takes
`-f FILE` for the prompt, so the question travels in a file in the run's own
private directory alongside the audio, and the argv is constants plus paths this
module generated. There is no shell, no interpolation and no model-supplied
value anywhere in the vector.

**Native multimodal, and nothing else.** The recording and the instruction go in
together through the model's own audio path — the path the frozen Case B pass of
21 September was measured on. **No Whisper. No separate transcription model. No
cloud service. No pre-transcribed text.** There is no code path here that could
reach one: the only subprocess this module can start is the one binary named
below.

**One bounded recovery attempt, then an honest stop.** A second failure raises
`PerceptionUnavailableError` and the turn above fails closed. Nothing falls
through to a paid audio API, because none is wired and none may be.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from val_domain.perception import (
    PerceptionObservation,
    PerceptionRefusedError,
    PerceptionRequest,
    PerceptionResult,
    PerceptionUnavailableError,
    sources_are_coherent,
)

#: The official llama.cpp multimodal CLI, at the fixed path Homebrew installs.
#: The exact binary the frozen Case B pass ran on: v0.4.1, build 10964, commit
#: `b29c606e2`, Metal.
LLAMA_MTMD_CLI = Path("/opt/homebrew/bin/llama-mtmd-cli")

#: The admitted artifacts, at the qualified revision
#: `6e35a28f4a19b18730f8949b0c579c6429649ab8`. The projector is one file carrying
#: both encoders; only the audio one is ever exercised from here.
MODEL_DIR = Path.home() / ".val-models" / "Qwen3-Omni-30B-A3B-Instruct-GGUF"
MODEL_FILE = MODEL_DIR / "Qwen3-Omni-30B-A3B-Instruct-Q4_K_M.gguf"
MMPROJ_FILE = MODEL_DIR / "mmproj-Qwen3-Omni-30B-A3B-Instruct-Q8_0.gguf"

MODEL_REVISION = "6e35a28f4a19b18730f8949b0c579c6429649ab8"
QUANTIZATION = "Q4_K_M (language model), Q8_0 (projector)"
RUNTIME_VERSION = "0.4.1 (build 10964, commit b29c606e2)"

#: Exactly what qualification passed: the context size and full Metal offload,
#: and nothing else. **No temperature, top-p, top-k or repeat penalty is
#: passed**, so the model's own defaults govern, as they did on 21 September.
CONTEXT_TOKENS = 16_384
GPU_LAYERS = 99

#: Loading 19 GB and perceiving takes time; Case B measured 3.5 s of inference
#: after the load. This is the ceiling before a run is called failed.
RUN_TIMEOUT_SECONDS = 900.0

#: What the CLI prints around the answer. Stripped so the stored observation is
#: the observation, not a transcript of a program starting up.
_NOISE_PREFIXES = (
    "build:",
    "main:",
    "llama_",
    "load_",
    "print_info:",
    "init_audio:",
    "clip_",
    "mtmd_",
    "encoding ",
    "decoding ",
    "ggml_",
    "Metal",
    "ggml_metal",
    "system_info:",
    "sampler ",
    "generate:",
    "llama perf",
    "encoding audio",
)


class _Runner:
    """The only place a subprocess is started, so there is one thing to read."""

    def run(self, argv: list[str], timeout: float) -> tuple[int, str, str]:
        completed = subprocess.run(  # noqa: S603 - fixed binary, fixed flags, no shell
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        return completed.returncode, completed.stdout, completed.stderr


class OmniAudioPerception:
    """Val's local audio-perception provider. Evidence in, nothing else out."""

    provider = "llamacpp-omni"
    model_identifier = "ggml-org/Qwen3-Omni-30B-A3B-Instruct-GGUF"
    #: **Audio alone.** Not a description of the artifact, which also contains a
    #: vision encoder — a declaration of what this route is admitted to receive.
    modalities = frozenset({"audio"})

    def __init__(
        self,
        *,
        binary: Path = LLAMA_MTMD_CLI,
        model: Path = MODEL_FILE,
        mmproj: Path = MMPROJ_FILE,
        runner: _Runner | None = None,
        timeout: float = RUN_TIMEOUT_SECONDS,
    ) -> None:
        self._binary = binary
        self._model = model
        self._mmproj = mmproj
        self._runner = runner or _Runner()
        self._timeout = timeout

    # --- availability -------------------------------------------------------------

    def available(self) -> str | None:
        """Why local audio perception cannot run at all, or `None`."""
        if not self._binary.exists():
            return f"the local audio runtime is not installed at {self._binary}"
        if not self._model.is_file():
            return f"the admitted audio artifact is not present at {self._model}"
        if not self._mmproj.is_file():
            return f"the admitted audio projector is not present at {self._mmproj}"
        return None

    # --- the one entry point ------------------------------------------------------

    def perceive(self, request: PerceptionRequest) -> PerceptionResult:
        """Perceive this recording once, with one bounded recovery attempt."""
        incoherent = sources_are_coherent(request.sources)
        if incoherent is not None:
            raise PerceptionRefusedError(incoherent)
        for source in request.sources:
            if source.modality != "audio":
                raise PerceptionRefusedError(
                    f"this route is admitted for audio alone and was handed "
                    f"{source.modality!r}; its artifact's other encoders are not a permission"
                )
        unavailable = self.available()
        if unavailable is not None:
            raise PerceptionUnavailableError(unavailable)

        started = time.monotonic()
        try:
            observations = self._attempt(request)
        except PerceptionUnavailableError as failure:
            first = str(failure)
            try:
                observations = self._attempt(request)
            except PerceptionUnavailableError as again:
                raise PerceptionUnavailableError(
                    f"local audio perception failed twice and is not available. "
                    f"First: {first}. After one bounded recovery attempt: {again}. "
                    "No transcription service and no paid audio API was contacted, and "
                    "nothing was charged."
                ) from again

        return PerceptionResult(
            observations=tuple(observations),
            provider=self.provider,
            model_identifier=self.model_identifier,
            model_revision=MODEL_REVISION,
            quantization=QUANTIZATION,
            runtime="llama.cpp",
            runtime_version=RUNTIME_VERSION,
            generation={
                "context_tokens": CONTEXT_TOKENS,
                "gpu_layers": GPU_LAYERS,
                # Untuned at qualification and untuned now. Named as absent
                # rather than left out, so the record says so.
                "temperature": None,
                "top_p": None,
                "top_k": None,
                "repeat_penalty": None,
                "sampling_arguments_passed": [],
            },
            duration_seconds=round(time.monotonic() - started, 3),
            cost_usd=0.0,
            local=True,
            # The Instruct build returned clean prose on all three frozen cases:
            # no thinking channel, no `<think>` block, no reasoning markup.
            reasoning_separated=True,
        )

    def release(self) -> None:
        """Nothing is held between runs: the subprocess exited when it finished."""

    # --- one attempt --------------------------------------------------------------

    def _attempt(self, request: PerceptionRequest) -> list[PerceptionObservation]:
        workspace = Path(tempfile.mkdtemp(prefix="val-audio-perception-"))
        os.chmod(workspace, 0o700)
        try:
            prompt_file = workspace / "prompt.txt"
            prompt_file.write_text(request.prompt, encoding="utf-8")
            observations = []
            for index, source in enumerate(request.sources, start=1):
                audio = workspace / f"{index:02d}-{source.sha256[:16]}.wav"
                audio.write_bytes(source.content)
                argv = [
                    str(self._binary),
                    "-m",
                    str(self._model),
                    "--mmproj",
                    str(self._mmproj),
                    "-c",
                    str(CONTEXT_TOKENS),
                    "-ngl",
                    str(GPU_LAYERS),
                    "--audio",
                    str(audio),
                    # The owner's words travel in a file, never in the vector.
                    "-f",
                    str(prompt_file),
                ]
                try:
                    code, out, err = self._runner.run(argv, self._timeout)
                except subprocess.TimeoutExpired as expired:
                    raise PerceptionUnavailableError(
                        f"the audio perception run did not finish within {self._timeout:.0f}s"
                    ) from expired
                except OSError as failure:
                    raise PerceptionUnavailableError(
                        f"the local audio runtime could not be started: {failure}"
                    ) from failure
                if code != 0:
                    detail = (err.strip().splitlines() or ["no output"])[-1]
                    raise PerceptionUnavailableError(
                        f"the audio perception run exited {code}: {detail}"
                    )
                text = self.observation_from(out)
                if not text:
                    raise PerceptionUnavailableError(
                        "the audio perception run succeeded and produced no observation"
                    )
                observations.append(
                    PerceptionObservation(source_sha256=source.sha256, modality="audio", text=text)
                )
            return observations
        finally:
            # The recording is removed whatever happened.
            shutil.rmtree(workspace, ignore_errors=True)

    @staticmethod
    def observation_from(out: str) -> str:
        """The answer, with the CLI's own startup chatter taken off.

        A `staticmethod` so the rule is testable on its own: what is stored as
        evidence must be the observation, not a program's log.
        """
        kept = [
            line
            for line in out.splitlines()
            if line.strip() and not line.lstrip().startswith(_NOISE_PREFIXES)
        ]
        return "\n".join(kept).strip()
