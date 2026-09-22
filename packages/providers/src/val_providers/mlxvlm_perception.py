"""Qwen3.5 local visual perception, through MLX-VLM, without a terminal.

Owner ruling, 22 September 2026. Ordinary image use by Lord Armand requires no
Terminal, no manual Python command, no manual model load, no manual server
start, and no manual unload. This adapter is the whole of what makes that true.

**The smallest reliable mechanism, deliberately.** MLX-VLM is a library, not a
server: there is no daemon to supervise, no port to probe, no model to keep
warm. One perception run is one subprocess of the house's isolated visual
runtime, which loads the admitted artifact (0.99 s, measured), perceives, prints
its result, and exits. Exit is the release: every byte of Metal and MLX
allocation returns to the machine, which is how the visual model and the
cognition model take turns rather than competing. Qualification measured the
whole cycle — 13.10 GB wired during perception, 2.97 GB after, GPT-OSS reloaded
at its full 32,768-token window immediately afterwards.

**It is not a command path.** The same reasoning as `lmstudio_runtime`, and the
same discipline: the interpreter is a constant, the script is a constant, the
argument vector is exactly those two and nothing else, and there is no shell.
The request — prompts, file paths, digests — travels on **stdin as JSON**, so
nothing a model wrote, a document contained or a tool returned can become an
argument. A Role cannot call this, and calling it cannot run anything else.

**The media never leave the machine, and never outlive the run.** Bytes come
from the House's own blob store, are written into a private per-run directory
(0700) that is removed in a `finally`, and are checked against their recorded
digest before and after they reach the disk. Nothing is fetched, nothing is
uploaded, and no path outside that directory is ever named.

**One bounded recovery attempt, then an honest stop.** A run that fails is tried
once more, because a transient start failure is a real thing. A second failure
raises `PerceptionUnavailableError`, and the turn above fails closed. It does
not reach for a paid image-capable provider: that would be a decision nobody
made, and §19 of the order forbids it in the same words the 21 September
local-first ruling uses for Partner cognition.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from val_domain.perception import (
    Modality,
    PerceptionObservation,
    PerceptionRefusedError,
    PerceptionRequest,
    PerceptionResult,
    PerceptionUnavailableError,
    sources_are_coherent,
)

#: The house's isolated visual runtime. Separate from Val's production Python on
#: purpose: mlx, mlx-vlm and opencv are not production dependencies, and the
#: 22 September order forbids making them so.
VENV_PYTHON = Path.home() / ".val-runtimes" / "mlx-vlm-venv" / "bin" / "python"

#: The admitted artifact, at the qualified revision.
MODEL_PATH = Path.home() / ".val-models" / "Qwen3.5-9B-MLX-4bit"

#: The immutable revision the acceptance test ran against. Carried into every
#: provenance row: a perception record that cannot say which weights produced it
#: is not provenance.
MODEL_REVISION = "b455506b0f574c74616dbcd56879bde38fafcff3"

#: Quantization is identity here, as it is on the local text routes.
QUANTIZATION = "4-bit, group size 64, affine (MLX)"

#: The runner, resolved from this file rather than from a working directory, so
#: the adapter works the same whatever process started Val.
RUNNER = (
    Path(__file__).resolve().parents[4] / "infrastructure" / "perception" / "mlx_vlm_perceive.py"
)

#: A 9B model reading an image takes tens of seconds; the acceptance test
#: measured 28.1 s for the image case and 9.7 s for the video case, on a cold
#: load. This is the ceiling before a run is called failed, not an expectation.
RUN_TIMEOUT_SECONDS = 300.0

#: File extensions by media type, because MLX-VLM reads files and infers from
#: the name. Only the admitted modalities appear.
_SUFFIXES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "video/mp4": ".mp4",
}


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


class MLXVLMPerception:
    """Val's local visual-perception provider. Evidence in, nothing else out."""

    provider = "mlxvlm"
    model_identifier = "lmstudio-community/Qwen3.5-9B-MLX-4bit"

    def __init__(
        self,
        *,
        python: Path = VENV_PYTHON,
        model_path: Path = MODEL_PATH,
        runner: _Runner | None = None,
        timeout: float = RUN_TIMEOUT_SECONDS,
    ) -> None:
        self._python = python
        self._model_path = model_path
        self._runner = runner or _Runner()
        self._timeout = timeout

    # --- availability -------------------------------------------------------------

    def available(self) -> str | None:
        """Why local perception cannot run at all, or `None`.

        Checked before a run rather than discovered inside one, so an absent
        runtime is reported as an absent runtime instead of as a failed
        perception. It inspects the filesystem and starts nothing.
        """
        if not self._python.exists():
            return f"the isolated visual runtime is not installed at {self._python}"
        if not self._model_path.is_dir():
            return f"the admitted visual artifact is not present at {self._model_path}"
        if not RUNNER.is_file():
            return f"the perception runner is missing at {RUNNER}"
        return None

    # --- the one entry point ------------------------------------------------------

    def perceive(self, request: PerceptionRequest) -> PerceptionResult:
        """Perceive these sources once, with one bounded recovery attempt."""
        incoherent = sources_are_coherent(request.sources)
        if incoherent is not None:
            raise PerceptionRefusedError(incoherent)
        unavailable = self.available()
        if unavailable is not None:
            raise PerceptionUnavailableError(unavailable)

        started = time.monotonic()
        first: str
        try:
            report = self._attempt(request)
        except PerceptionUnavailableError as failure:
            # One bounded recovery attempt. A transient failure to start is a
            # real thing; a second one is a condition, not a hiccup.
            first = str(failure)
            try:
                report = self._attempt(request)
            except PerceptionUnavailableError as again:
                raise PerceptionUnavailableError(
                    f"local visual perception failed twice and is not available. "
                    f"First: {first}. After one bounded recovery attempt: {again}. "
                    "Nothing was sent to any paid provider and nothing was charged."
                ) from again

        reported = report.get("observations")
        if not isinstance(reported, list):
            raise PerceptionUnavailableError(
                "the perception run returned observations of the wrong shape"
            )
        observations = []
        for entry in reported:
            if not isinstance(entry, dict):
                raise PerceptionUnavailableError(
                    "the perception run returned an observation of the wrong shape"
                )
            reported_modality = str(entry.get("modality", ""))
            # Narrowed against the admitted set rather than cast to it: an
            # unadmitted modality coming back is a condition to report, not a
            # value to coerce into one of the two that are allowed.
            modality: Modality
            if reported_modality == "image":
                modality = "image"
            elif reported_modality == "video":
                modality = "video"
            else:
                raise PerceptionUnavailableError(
                    f"the perception run reported the unadmitted modality {reported_modality!r}"
                )
            observations.append(
                PerceptionObservation(
                    source_sha256=str(entry.get("sha256", "")),
                    modality=modality,
                    text=str(entry.get("text", "")),
                )
            )
        generation = report.get("generation")

        return PerceptionResult(
            observations=tuple(observations),
            provider=self.provider,
            model_identifier=self.model_identifier,
            model_revision=MODEL_REVISION,
            quantization=QUANTIZATION,
            runtime=str(report.get("runtime", "mlx-vlm")),
            runtime_version=str(report.get("runtime_version", "unknown")),
            generation=dict(generation) if isinstance(generation, dict) else {},
            duration_seconds=round(time.monotonic() - started, 3),
            # Local execution bills nothing. Recorded as an observed zero on a
            # route whose metering says so, never as an assumed one.
            cost_usd=0.0,
            local=True,
            # The artifact's chat template opens and immediately closes the
            # thinking block, so no reasoning content is produced to separate.
            # Observed in qualification, on both cases.
            reasoning_separated=True,
        )

    def release(self) -> None:
        """Nothing is held between runs, and that is the design.

        Present because the boundary declares it and because a future provider
        that *does* hold a model open must have somewhere to let it go. Here the
        release already happened: the subprocess exited when its run finished.
        """

    # --- one attempt --------------------------------------------------------------

    def _attempt(self, request: PerceptionRequest) -> dict[str, object]:
        workspace = Path(tempfile.mkdtemp(prefix="val-perception-"))
        os.chmod(workspace, 0o700)
        try:
            sources = []
            for index, source in enumerate(request.sources, start=1):
                suffix = _SUFFIXES.get(source.media_type)
                if suffix is None:
                    raise PerceptionRefusedError(
                        f"{source.media_type!r} is not a medium this perception route reads"
                    )
                path = workspace / f"{index:02d}-{source.sha256[:16]}{suffix}"
                path.write_bytes(source.content)
                sources.append(
                    {
                        "path": str(path),
                        "modality": source.modality,
                        "sha256": source.sha256,
                    }
                )
            payload = json.dumps(
                {
                    "model_path": str(self._model_path),
                    "prompt": request.prompt,
                    "sources": sources,
                    "max_tokens": request.max_output_tokens,
                }
            )
            try:
                code, out, err = self._runner.run(
                    [str(self._python), str(RUNNER)], payload, self._timeout
                )
            except subprocess.TimeoutExpired as expired:
                raise PerceptionUnavailableError(
                    f"the perception run did not finish within {self._timeout:.0f}s"
                ) from expired
            except OSError as failure:
                raise PerceptionUnavailableError(
                    f"the isolated visual runtime could not be started: {failure}"
                ) from failure

            report = self._parse(code, out, err)
            if not report.get("ok"):
                reason = str(report.get("reason", "no reason given"))
                if report.get("kind") == "refused":
                    raise PerceptionRefusedError(reason)
                raise PerceptionUnavailableError(reason)
            if not report.get("observations"):
                raise PerceptionUnavailableError(
                    "the perception run reported success and returned no observation"
                )
            return report
        finally:
            # The media are removed whatever happened. An attachment that
            # outlives the run it was written for is an attachment lying around.
            shutil.rmtree(workspace, ignore_errors=True)

    @staticmethod
    def _parse(code: int, out: str, err: str) -> dict[str, object]:
        """The runner's last stdout line, as JSON, or a failure worth reading."""
        line = next((text for text in reversed(out.splitlines()) if text.strip()), "")
        if not line:
            detail = err.strip().splitlines()[-1:] or ["no output"]
            raise PerceptionUnavailableError(
                f"the perception run produced no result (exit {code}): {detail[0]}"
            )
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as broken:
            raise PerceptionUnavailableError(
                f"the perception run produced output that is not a result (exit {code})"
            ) from broken
        if not isinstance(parsed, dict):
            raise PerceptionUnavailableError(
                "the perception run produced a result of the wrong shape"
            )
        return parsed
