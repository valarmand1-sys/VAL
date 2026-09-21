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
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path

from val_domain.gateway import ModelConfig
from val_domain.provider import LocalRuntimeUnavailableError

#: LM Studio's command-line tool, at the fixed path its installer creates.
LMS = Path.home() / ".lmstudio" / "bin" / "lms"

#: How long to wait for a server that has just been asked to start.
SERVER_WAIT_SECONDS = 20.0

#: How long a load of a twelve-gigabyte model may take before it is called failed.
LOAD_TIMEOUT_SECONDS = 300.0

#: How long the loaded instance stays resident with no traffic. Unloading is
#: welcome — it returns memory to the owner's machine — precisely because this
#: module loads it again, named window and all, the next time Val thinks.
IDLE_TTL_SECONDS = 3600


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
        # The server requires a bearer token on every request (LM Studio 0.4.24
        # answers 401 to an unauthenticated probe, including on loopback). It is
        # carried, never logged, and never part of the provenance this returns.
        self._token = token
        self._runner = runner or _Runner()
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
        """Every loaded instance, as the runtime itself reports it."""
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
            identity = {str(row.get(key, "")) for key in ("modelKey", "path", "identifier")}
            if model_identifier in identity:
                return row
        return None

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
        """Make this configuration servable now. One bounded attempt at each step."""
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
