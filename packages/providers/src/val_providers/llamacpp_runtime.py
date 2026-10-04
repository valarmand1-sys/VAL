"""Bringing the llama.cpp server up for a declared model, without a terminal.

Owner order, 29 September 2026 (a different conversational model for Voice). The same
rule as the LM Studio supervisor of 21 September: he opens Voice and Val answers; he does
not start a server or load a model.

**It is not a command path.** The executable is a constant. The arguments are constants
and values declared in `LAUNCH_SPECS`, keyed by the `model_identifier` the registry itself
declares. No value from a model, a document or a request is interpolated into any of
them, and there is no shell. Nothing a Role or a tool loop can reach calls this.

**What it starts.** One `llama-server` on the loopback interface, serving one model in one
slot, with the window the registry declares. The model file is checked against its pinned
SHA-256 before the first start, once per process. The server's key is this process's own
key, handed over in a file only this user can read and removed once the server is up.

**One bounded attempt.** The server is probed; if it is not serving this model, it is
started once and waited for. A failure is raised as a failure. The child is ended when
this process ends, or when `release` is called.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from val_domain.gateway import ModelConfig
from val_domain.provider import LocalRuntimeUnavailableError

#: The official llama.cpp server, at the path its installer creates.
SERVER = Path("/opt/homebrew/bin/llama-server")
#: Where the house keeps the model files this provider may serve.
MODELS_SETTING = "VAL_LLAMACPP_MODELS_DIR"
DEFAULT_MODELS = Path.home() / ".val-models" / "voice-candidates"
#: How long a load may take before it is called failed.
LOAD_TIMEOUT_SECONDS = 180.0


@dataclass(frozen=True)
class LaunchSpec:
    """What serving one declared model means: the file, its pin, and the fixed flags."""

    file: str
    sha256: str
    #: Flags beyond the common ones; constants, never interpolated.
    flags: tuple[str, ...] = ()


#: Keyed by the registry's `model_identifier`, which is also the server's alias.
LAUNCH_SPECS: Mapping[str, LaunchSpec] = {
    "gemma-4-26b-a4b-it": LaunchSpec(
        file="gemma-4-26B-A4B-it-Q4_K_M.gguf",
        sha256="e19514d9541344001cb7c8eaf88704b8bf2e5d8f4e9aac12402eed360cffdfc4",
        # Thinking off at the server as well as in each request (the request's template
        # argument is what the rendered prompt was verified against, 29 September 2026).
        flags=("--chat-template-kwargs", '{"enable_thinking":false}'),
    ),
    # Owner order, 2 October 2026: the typed candidate, served exactly as the Voice
    # model is (same flags, thinking off at the server and in each request).
    "gemma-4-26b-a4b-styletune-v2": LaunchSpec(
        file="Gemma-4-26B-A4B-StyleTune-V2.Q4_K_M.gguf",
        sha256="73742ed0dfd5f77db687964a3b7b178c424e1bd89f0a4d47e77b8ed87af2ec50",
        flags=("--chat-template-kwargs", '{"enable_thinking":false}'),
    ),
}


def models_directory() -> Path:
    raw = os.environ.get(MODELS_SETTING, "").strip()
    return Path(raw) if raw else DEFAULT_MODELS


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 24), b""):
            digest.update(chunk)
    return digest.hexdigest()


class LlamaCppRuntime:
    """The one llama.cpp server this process may start, and what it is serving."""

    def __init__(self, base_url: str, key: str) -> None:
        parsed = urlparse(base_url)
        self._host = parsed.hostname or "127.0.0.1"
        self._port = parsed.port or 8080
        self._root = f"{parsed.scheme}://{self._host}:{self._port}"
        self._key = key
        self._lock = threading.Lock()
        self._child: subprocess.Popen[bytes] | None = None
        self._verified: set[str] = set()
        atexit.register(self.release)

    # --- probing -----------------------------------------------------------------------

    def _get(self, path: str, timeout: float = 2.0) -> object:
        request = urllib.request.Request(  # noqa: S310 - the loopback server this adapter serves
            f"{self._root}{path}", headers={"Authorization": f"Bearer {self._key}"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))

    def serving(self, config: ModelConfig) -> Mapping[str, object] | None:
        """The server's own facts if it is serving this model now, else None."""
        try:
            self._get("/health")
            props = self._get("/props")
        except urllib.error.URLError, OSError, ValueError:
            return None
        if not isinstance(props, Mapping):
            return None
        try:
            listing = self._get("/v1/models")
        except urllib.error.URLError, OSError, ValueError:
            return None
        served = {
            entry.get("id")
            for entry in (listing.get("data") or [] if isinstance(listing, Mapping) else [])
            if isinstance(entry, Mapping)
        }
        if config.model_identifier not in served:
            return None
        settings = props.get("default_generation_settings")
        n_ctx = settings.get("n_ctx") if isinstance(settings, Mapping) else None
        return {"model": config.model_identifier, "n_ctx": n_ctx, "build": props.get("build_info")}

    # --- starting ----------------------------------------------------------------------

    def ensure_ready(self, config: ModelConfig) -> Mapping[str, object]:
        """Make this configuration servable now; one bounded attempt."""
        with self._lock:
            found = self.serving(config)
            if found is not None:
                return {"state": "already serving", **found}
            spec = LAUNCH_SPECS.get(config.model_identifier)
            if spec is None:
                raise LocalRuntimeUnavailableError(
                    f"llamacpp: no launch specification is declared for "
                    f"{config.model_identifier!r}; nothing is started for an undeclared model"
                )
            if not SERVER.exists():
                raise LocalRuntimeUnavailableError(f"llamacpp: {SERVER} is not installed")
            path = models_directory() / spec.file
            if not path.exists():
                raise LocalRuntimeUnavailableError(
                    f"llamacpp: the model file {spec.file} is absent"
                )
            if spec.file not in self._verified:
                if file_sha256(path) != spec.sha256:
                    raise LocalRuntimeUnavailableError(
                        f"llamacpp: {spec.file} does not match its pinned SHA-256; not served"
                    )
                self._verified.add(spec.file)
            self._stop_child()
            started = time.monotonic()
            handle, keyfile = tempfile.mkstemp(prefix="val-llamacpp-")
            try:
                with os.fdopen(handle, "w") as out:
                    out.write(self._key)
                os.chmod(keyfile, 0o600)
                arguments = [
                    str(SERVER),
                    "-m",
                    str(path),
                    "--alias",
                    config.model_identifier,
                    "--ctx-size",
                    str(config.context_window_tokens),
                    "--parallel",
                    "1",
                    "--jinja",
                    "-ngl",
                    "999",
                    "--host",
                    self._host,
                    "--port",
                    str(self._port),
                    "--api-key-file",
                    keyfile,
                    "--swa-full",
                    "-b",
                    "2048",
                    "-ub",
                    "2048",
                    "--no-webui",
                    *spec.flags,
                ]
                self._child = subprocess.Popen(  # noqa: S603 - constants and declared values only
                    arguments, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                deadline = time.monotonic() + LOAD_TIMEOUT_SECONDS
                while time.monotonic() < deadline:
                    if self._child.poll() is not None:
                        raise LocalRuntimeUnavailableError(
                            f"llamacpp: the server exited with {self._child.returncode} "
                            "while loading"
                        )
                    found = self.serving(config)
                    if found is not None:
                        return {
                            "state": "started",
                            "seconds": round(time.monotonic() - started, 1),
                            **found,
                        }
                    time.sleep(0.25)
                self._stop_child()
                raise LocalRuntimeUnavailableError(
                    f"llamacpp: the server was not ready within {LOAD_TIMEOUT_SECONDS:.0f} s"
                )
            finally:
                Path(keyfile).unlink(missing_ok=True)

    # --- stopping ----------------------------------------------------------------------

    def _stop_child(self) -> None:
        child, self._child = self._child, None
        if child is None or child.poll() is not None:
            return
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()

    def release(self) -> Mapping[str, object]:
        """End the server this process started, giving its memory back."""
        with self._lock:
            had = self._child is not None and self._child.poll() is None
            self._stop_child()
            return {"released": had}
