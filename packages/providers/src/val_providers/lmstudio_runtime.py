"""Bringing LM Studio up, and GPT-OSS into it, without the owner touching a terminal.

Owner ruling, 21 September 2026. Local cognition has to behave like cognition:
Lord Armand opens Val and Val thinks. He does not start a server, load a model,
remember which backend a question needs, or find out that he should have when an
answer fails to arrive.

**This uses the runtime's own supported mechanisms and invents none.** LM Studio
ships a command-line tool at a fixed path with documented verbs — `server start`,
`ps`, `load` — and the house already talks to the same runtime through its HTTP
server and its read-only SDK inspector. Three fixed argument vectors are all this
module runs.

**It is not a command path.** The invariant that forbids arbitrary local command
execution (`00-charter.md` §6) forbids a *path* — something a Role, a model, a
tool loop, a connector or a fetched document could reach and steer. Nothing here
is reachable from any of those. The executable is a constant, the arguments are
constants and registry-declared integers, no value from a model or a document is
interpolated into any of them, there is no shell, and the only identifier passed
is the `model_identifier` the registry itself declares. A Role cannot call this,
and calling it cannot run anything else.

**The context length is named, never inherited.** The hazard recorded on the
evaluation registry entry is that a just-in-time reload restores the model's own
smaller default window; an ordinary turn would then fail the exact preflight,
correctly but uselessly. So the load states the registry's context explicitly,
and the result is reported back for the record. Runtime remains authoritative at
call time: this module makes the window right, it does not get to assert it.

**One bounded attempt.** The runtime is probed; if it is not serving, it is
started once; if the model is not loaded with a large enough window, it is loaded
once. Nothing here loops, and a failure is raised as a failure rather than
retried into a timeout.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from val_domain.gateway import ModelConfig
from val_domain.provider import LocalRuntimeUnavailableError

#: LM Studio's command-line tool, at the fixed path its installer creates.
LMS = Path.home() / ".lmstudio" / "bin" / "lms"

#: How long to wait for a server that has just been asked to start.
SERVER_WAIT_SECONDS = 20.0

#: How long a load of a twelve-gigabyte model may take before it is called failed.
LOAD_TIMEOUT_SECONDS = 300.0

#: LM Studio's own model listing, beside the OpenAI-compatible surface. It reports
#: each model's `state` and `loaded_context_length`, which is everything the
#: residency question needs — over HTTP, without spawning the CLI.
NATIVE_MODELS_PATH = "/api/v0/models"

#: How long the loaded instance stays resident with no traffic. Unloading is
#: welcome — it returns memory to the owner's machine — precisely because this
#: module loads it again, named window and all, the next time Val thinks.
IDLE_TTL_SECONDS = 3600

#: How many predictions the admitted instance serves at once. Owner order, 25
#: September 2026 (priming-cache pass): **one**. At LM Studio's default of four the MLX
#: engine serves the model with its batched kit, whose cache is keyed on prompt *and*
#: generated tokens and can never hand a later turn the computation of the persona
#: they share; at one it uses its sequential kit, which can, once a prefix prime has
#: placed a checkpoint at the persona boundary. Measured through LM Studio on an
#: isolated instance: first output 0.70-0.80 s against ~7 s on changed-suffix turns.
SERVING_PARALLEL = 1

#: The LM Studio file that names the engine selected for each model format.
BACKEND_PREFERENCES = Path.home() / ".lmstudio" / ".internal" / "backend-preferences-v1.json"
BACKENDS = Path.home() / ".lmstudio" / "extensions" / "backends"


class _Runner:
    """The only place a subprocess is started, so there is one thing to read."""

    def run(self, argv: Sequence[str], timeout: float) -> tuple[int, str]:
        completed = subprocess.run(  # noqa: S603 - fixed executable, fixed verbs, no shell
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        return completed.returncode, (completed.stdout + completed.stderr).strip()


class LMStudioRuntime:
    """Makes one LM Studio configuration servable, and says what it had to do."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        runner: _Runner | None = None,
        lms_path: Path = LMS,
        probe_timeout: float = 3.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        # The native listing sits beside `/v1`, not under it.
        self._native_base = self._base[: -len("/v1")] if self._base.endswith("/v1") else self._base
        # The server requires a bearer token on every request (LM Studio 0.4.24
        # answers 401 to an unauthenticated probe, including on loopback). It is
        # carried, never logged, and never part of the provenance this returns.
        self._token = token
        self._runner = runner or _Runner()
        # One load at a time, per runtime object. See `ensure_ready`.
        self._loading = threading.Lock()
        self._models_lock = threading.Lock()
        self._per_model: dict[str, threading.Lock] = {}
        self._lms = lms_path
        self._probe_timeout = probe_timeout

    # --- observation -------------------------------------------------------------

    def serving(self) -> bool:
        """Whether the local server answers on the loopback address at all."""
        request = urllib.request.Request(  # noqa: S310 - http on loopback, fixed by the adapter
            f"{self._base}/models", headers={"Authorization": f"Bearer {self._token}"}
        )
        # No proxy: this is the loopback interface of this machine, and a proxy
        # standing in front of it would make the probe answer for something else.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=self._probe_timeout) as response:
                return bool(200 <= response.status < 300)
        except urllib.error.URLError, OSError, ValueError:
            return False

    def loaded(self) -> list[Mapping[str, object]]:
        """Every loaded instance, as the runtime itself reports it.

        The server's own listing first, the command-line tool second. Both ask the
        same runtime the same question; the difference is that one is an HTTP
        request on the loopback interface and the other spawns LM Studio's
        Node-based CLI. Measured on this machine (latency pass §12): **4 ms
        against 138 ms**, and this runs on the critical path of every turn.

        The CLI remains the fallback, so nothing is weakened: if the HTTP listing
        cannot answer — an older server, a changed surface, a malformed reply —
        the subprocess is still there and the answer is the same.
        """
        served = self._loaded_over_http()
        return served if served is not None else self._loaded_over_cli()

    def _loaded_over_http(self) -> list[Mapping[str, object]] | None:
        """The server's native listing, filtered to what is actually resident.

        `None` means the listing could not be used, which is a reason to ask the
        CLI — never a reason to report that nothing is loaded.
        """
        request = urllib.request.Request(  # noqa: S310 - http on loopback, fixed by the adapter
            f"{self._native_base}{NATIVE_MODELS_PATH}",
            headers={"Authorization": f"Bearer {self._token}"},
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=self._probe_timeout) as response:
                parsed = json.load(response)
        except urllib.error.URLError, OSError, ValueError:
            return None
        rows = parsed.get("data") if isinstance(parsed, Mapping) else None
        if not isinstance(rows, list):
            return None
        return [
            row
            for row in rows
            if isinstance(row, Mapping) and str(row.get("state", "")) == "loaded"
        ]

    def _loaded_over_cli(self) -> list[Mapping[str, object]]:
        code, output = self._runner.run([str(self._lms), "ps", "--json"], timeout=20.0)
        if code != 0 or not output:
            return []
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            return []
        return [row for row in parsed if isinstance(row, dict)] if isinstance(parsed, list) else []

    def _instance(self, model_identifier: str) -> Mapping[str, object] | None:
        for row in self.loaded():
            # `id` is the server listing's name for the model; the other three are
            # the CLI's. Both sources are read the same way.
            identity = {str(row.get(key, "")) for key in ("modelKey", "path", "identifier", "id")}
            if model_identifier in identity:
                return row
        return None

    def serving_parallel(self, model_identifier: str) -> int | None:
        """How many predictions the loaded instance serves at once, or `None`.

        Only the command-line listing reports it (the server's HTTP listing does not),
        so this spawns `lms ps` — which is why it is read on the prime's path and never
        on a turn's.
        """
        for row in self._loaded_over_cli():
            identity = {str(row.get(key, "")) for key in ("modelKey", "path", "identifier", "id")}
            if model_identifier in identity:
                value = row.get("parallel")
                return value if isinstance(value, int) else None
        return None

    @staticmethod
    def engine_identity(
        preferences: Path = BACKEND_PREFERENCES, backends: Path = BACKENDS
    ) -> dict[str, Any] | None:
        """The engine LM Studio has selected for safetensors models, as it records it.

        Name, version and the vendored generation package it runs — the package whose
        cache behaviour a prefix prime depends on. `None` when it cannot be read.
        """
        try:
            selected = next(
                row
                for row in json.loads(preferences.read_text())
                if isinstance(row, Mapping) and row.get("model_format") == "safetensors"
            )
            name, version = str(selected["name"]), str(selected["version"])
            manifest = json.loads(
                (backends / f"{name}-{version}" / "backend-manifest.json").read_text()
            )
        except OSError, ValueError, KeyError, StopIteration:
            return None
        packages = manifest.get("vendor_lib_package_names", [])
        return {
            "name": name,
            "version": version,
            "vendor_packages": sorted(str(item) for item in packages)
            if isinstance(packages, list)
            else [],
        }

    @staticmethod
    def _context_of(instance: Mapping[str, object]) -> int:
        for key in ("contextLength", "loadedContextLength", "loaded_context_length"):
            value = instance.get(key)
            if isinstance(value, int):
                return value
        return 0

    # --- action ------------------------------------------------------------------

    def _start_server(self) -> None:
        code, output = self._runner.run([str(self._lms), "server", "start"], timeout=60.0)
        if code != 0:
            raise LocalRuntimeUnavailableError(
                f"the local inference server did not start: {output or 'no output'}"
            )
        deadline = time.monotonic() + SERVER_WAIT_SECONDS
        while time.monotonic() < deadline:
            if self.serving():
                return
            time.sleep(0.5)
        raise LocalRuntimeUnavailableError(
            f"the local inference server was started but is not answering on {self._base}"
        )

    def _load(self, model_identifier: str, context_tokens: int) -> None:
        code, output = self._runner.run(
            [
                str(self._lms),
                "load",
                model_identifier,
                "--context-length",
                str(context_tokens),
                "--ttl",
                str(IDLE_TTL_SECONDS),
                "--parallel",
                str(SERVING_PARALLEL),
                "--yes",
            ],
            timeout=LOAD_TIMEOUT_SECONDS,
        )
        if code != 0:
            raise LocalRuntimeUnavailableError(
                f"{model_identifier} could not be loaded at {context_tokens:,} tokens of "
                f"context: {output or 'no output'}"
            )

    # --- the one entry point ------------------------------------------------------

    def ensure_ready(self, config: ModelConfig) -> Mapping[str, object]:
        """Make this configuration servable now. One bounded attempt at each step.

        **Serialised.** Two callers asking at once used to issue two loads, and LM
        Studio obliged: the exact preflight then found *two* loaded instances
        answering to one model identifier and refused to guess between them,
        failing closed onto the conservative byte bound and losing the exact
        measurement the 16 September ruling makes a hard gate. Found by this
        latency pass, when warming a session raced the turn that followed it — but
        the defect was already reachable by two turns in flight together.

        The second caller waits, then observes again and finds the model loaded.
        The lock covers observation and action together, because a decision to load
        taken before another caller's load finishes is the whole of the bug.
        """
        # One lock per model (26 September 2026): the light route's small model must
        # not wait behind the Partner model's load — a first greeting sat 9.8 s behind
        # GPT-OSS loading. Observation and action for one model are still one step.
        with self._models_lock:
            lock = self._per_model.setdefault(config.model_identifier, threading.Lock())
        with lock:
            return self._ensure_ready_locked(config)

    def _ensure_ready_locked(self, config: ModelConfig) -> Mapping[str, object]:
        # The server itself is one thing for every model: observed and started under
        # one lock, so two models arriving together cannot both start it.
        with self._loading:
            found_serving = self.serving()
            started = False
            if not found_serving:
                self._start_server()
                started = True

        instance = self._instance(config.model_identifier)
        wanted = config.context_window_tokens
        held = self._context_of(instance) if instance is not None else 0
        loaded = False
        # A window smaller than the registry's is reloaded rather than accepted:
        # the preflight would fail closed on it, which is correct and useless.
        if instance is None or held < wanted:
            self._load(config.model_identifier, wanted)
            loaded = True
            instance = self._instance(config.model_identifier)
            held = self._context_of(instance) if instance is not None else 0
            if instance is None:
                raise LocalRuntimeUnavailableError(
                    f"{config.model_identifier} reports no loaded instance after loading it"
                )
            if held < wanted:
                raise LocalRuntimeUnavailableError(
                    f"{config.model_identifier} loaded with {held:,} tokens of context, "
                    f"short of the {wanted:,} this route is registered for"
                )

        return {
            "server_found_running": found_serving,
            "server_started": started,
            "model_found_loaded": not loaded,
            "model_loaded": loaded,
            "requested_context_tokens": wanted,
            "loaded_context_tokens": held,
            "base_url": self._base,
        }
