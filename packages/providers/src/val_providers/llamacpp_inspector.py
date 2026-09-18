"""The llama.cpp runtime/context inspector — read-only, over the server's own HTTP surface.

Owner ruling, 18 September 2026 (the second LOCAL provider). The standalone
`llama-server` counts and renders chat requests itself, so no SDK and no
template copy is needed:

- `GET  /props` — the authoritative runtime facts: the slot's context length
  (`n_ctx`), the active chat template, the model path, the build.
- `GET  /v1/models` — the identifier the server answers to.
- `POST /v1/chat/completions/input_tokens` — the token count of a chat
  completion body, parsed by the same function inference uses. **The body
  counted is the body sent:** the adapter hands this inspector the one
  canonical request body it will transmit.
- `POST /apply-template` — the exact rendered prompt of that same body (used by
  the proofs to show the declared thinking state in the rendering).

It never generates, completes, streams, loads, unloads or configures anything;
only these four endpoints are ever called. The credential is the provider's own
dedicated key, passed programmatically and rendered nowhere.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

import httpx

from val_domain.provider import ContextFeasibility, ContextInspectionUnavailableError

_LOGGER = logging.getLogger("val.providers.llamacpp.inspector")

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

#: The measurement's name on every evidence row.
SOURCE = "llamacpp-server"

INPUT_TOKENS_PATH = "/v1/chat/completions/input_tokens"
APPLY_TEMPLATE_PATH = "/apply-template"
PROPS_PATH = "/props"
MODELS_PATH = "/v1/models"


class _Reply(Protocol):
    def raise_for_status(self) -> object: ...
    def json(self) -> object: ...


class _Http(Protocol):
    def get(self, url: str, *, headers: Mapping[str, str], timeout: float) -> _Reply: ...
    def post(
        self, url: str, *, headers: Mapping[str, str], json: object, timeout: float
    ) -> _Reply: ...


@dataclass(frozen=True)
class TemplateIdentity:
    """The three hashes of a template pin and the verdict (owner ruling, 18 September 2026)."""

    raw_official_sha256: str
    canonical_official_sha256: str | None
    active_sha256: str
    raw_equal: bool
    canonical_equal: bool

    @property
    def accepted(self) -> bool:
        return self.raw_equal or self.canonical_equal


def compare_with_pinned_template(pinned: bytes, active: str) -> TemplateIdentity:
    """Byte identity of the server's active template with a pinned official template.

    llama.cpp b10360 drops exactly one terminal LF when it reads
    `--chat-template-file`. The owner accepted that one normalization and nothing
    else: **if and only if the pinned bytes end in exactly one LF, the active
    template may equal the pinned bytes with that one final LF removed.** No
    `rstrip`, no whitespace, CRLF or Unicode normalization, no second newline, no
    interior difference, no semantic equivalence. All three hashes are kept; the
    upstream hash is never rewritten.
    """
    active_bytes = active.encode("utf-8")
    exactly_one_terminal_lf = pinned.endswith(b"\n") and not pinned.endswith(b"\n\n")
    canonical = pinned[:-1] if exactly_one_terminal_lf else None
    return TemplateIdentity(
        raw_official_sha256=hashlib.sha256(pinned).hexdigest(),
        canonical_official_sha256=(
            None if canonical is None else hashlib.sha256(canonical).hexdigest()
        ),
        active_sha256=hashlib.sha256(active_bytes).hexdigest(),
        raw_equal=pinned == active_bytes,
        canonical_equal=canonical is not None and canonical == active_bytes,
    )


def server_root_of(base_url: str) -> str:
    """The server root (`scheme://host:port`) from the OpenAI-compatible base URL."""
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def is_loopback(base_url: str) -> bool:
    parsed = urlparse(base_url)
    return parsed.scheme in ("http", "https") and (parsed.hostname or "") in LOOPBACK_HOSTS


class LlamaCppContextInspector:
    """Read-only measurement of a running llama.cpp server."""

    def __init__(
        self,
        base_url: str,
        key: str | None,
        *,
        http: _Http | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        if not is_loopback(base_url):
            raise ValueError(
                "llamacpp inspector: the base URL must name this machine "
                f"(one of {sorted(LOOPBACK_HOSTS)}); a remote server is not inspected"
            )
        if not key:
            raise ValueError(
                "llamacpp inspector: the local server requires its API key "
                "(VAL_LLAMACPP_API_KEY); the inspector is not constructed without it"
            )
        self._root = server_root_of(base_url)
        self._headers = {"Authorization": f"Bearer {key}"}
        self._http: _Http = http if http is not None else httpx
        self._timeout = timeout_seconds

    # --- the four read-only calls ------------------------------------------------------

    def _get(self, path: str) -> object:
        return self._call(
            lambda: self._http.get(self._root + path, headers=self._headers, timeout=self._timeout),
            path,
        )

    def _post(self, path: str, body: Mapping[str, object]) -> object:
        return self._call(
            lambda: self._http.post(
                self._root + path, headers=self._headers, json=dict(body), timeout=self._timeout
            ),
            path,
        )

    def _call(self, send: Callable[[], _Reply], path: str) -> object:
        try:
            reply = send()
            reply.raise_for_status()
            return reply.json()
        except Exception as error:
            raise ContextInspectionUnavailableError(
                f"llamacpp inspector: {path} unavailable: {type(error).__name__}"
            ) from error

    def props(self) -> Mapping[str, object]:
        payload = self._get(PROPS_PATH)
        if not isinstance(payload, Mapping):
            raise ContextInspectionUnavailableError("llamacpp inspector: /props was not an object")
        return payload

    def model_ids(self) -> list[str]:
        payload = self._get(MODELS_PATH)
        data = payload.get("data", []) if isinstance(payload, Mapping) else []
        return [str(m["id"]) for m in data if isinstance(m, Mapping) and "id" in m]

    def count(self, body: Mapping[str, object]) -> int:
        payload = self._post(INPUT_TOKENS_PATH, body)
        value = payload.get("input_tokens") if isinstance(payload, Mapping) else None
        if not isinstance(value, int) or value <= 0:
            raise ContextInspectionUnavailableError(
                "llamacpp inspector: the server returned no usable input-token count"
            )
        return value

    def render(self, body: Mapping[str, object]) -> str:
        payload = self._post(APPLY_TEMPLATE_PATH, body)
        prompt = payload.get("prompt") if isinstance(payload, Mapping) else None
        if not isinstance(prompt, str) or not prompt:
            raise ContextInspectionUnavailableError(
                "llamacpp inspector: the server returned no rendered prompt"
            )
        return prompt

    # --- runtime facts ---------------------------------------------------------------------

    def runtime_facts(self) -> dict[str, object]:
        props = self.props()
        settings = props.get("default_generation_settings")
        n_ctx = settings.get("n_ctx") if isinstance(settings, Mapping) else None
        if not isinstance(n_ctx, int):
            n_ctx = props.get("n_ctx") if isinstance(props.get("n_ctx"), int) else None
        template = props.get("chat_template")
        return {
            "runtime": "llama.cpp server",
            "server_root": self._root,
            "n_ctx": n_ctx,
            "total_slots": props.get("total_slots"),
            "model_path": props.get("model_path"),
            "build_info": props.get("build_info"),
            "chat_template_sha256": (
                hashlib.sha256(template.encode("utf-8")).hexdigest()
                if isinstance(template, str)
                else None
            ),
        }

    # --- measurement ----------------------------------------------------------------------

    def measure(self, model_identifier: str, body: Mapping[str, object]) -> ContextFeasibility:
        """The server's own count of `body` against its own context length.

        `body` is the one canonical chat-completions request the adapter will
        transmit. The identifier must be one the server answers to; a missing
        or non-positive context length refuses. Nothing is estimated.
        """
        if model_identifier not in self.model_ids():
            raise ContextInspectionUnavailableError(
                f"llamacpp inspector: the server does not answer to {model_identifier!r}"
            )
        facts = self.runtime_facts()
        n_ctx = facts.get("n_ctx")
        if not isinstance(n_ctx, int) or n_ctx <= 0:
            raise ContextInspectionUnavailableError(
                "llamacpp inspector: the server reports no context length"
            )
        prompt_tokens = self.count(body)
        return ContextFeasibility(
            prompt_tokens=prompt_tokens,
            context_tokens=n_ctx,
            source=SOURCE,
            details={
                **facts,
                "model_identifier": model_identifier,
                "counted_body_keys": sorted(body),
                "turns": len(body.get("messages", [])),  # type: ignore[arg-type]
            },
        )
