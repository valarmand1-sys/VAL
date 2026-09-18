"""The LM Studio adapter — the first local cognition provider (ruling, 16 September 2026).

LM Studio serves a local model over an OpenAI-compatible HTTP surface on the
loopback interface. This adapter speaks that dialect — **chat completions**,
not the cloud Responses API — through the OpenAI client as transport only. It
shares nothing with the cloud OpenAI adapter beyond the domain contract, so a
cloud cache or request change cannot alter what is sent here, and vice versa.

## What this adapter guarantees

- **Loopback only.** The base URL's host must be a loopback address; anything
  else is refused at construction. A remote server cannot wear the local
  provider's name, and the eligibility ruling that admits `lmstudio` rests on
  the request never leaving the machine.
- **The token is required to construct, never shown.** It is handed to the
  client and appears in no log, error, result or record.
- **Conversation only.** No tools, no schema-constrained output (a request
  with `output_schema` is refused as `INVALID_REQUEST`), no cloud prompt-cache
  fields, no retries by the client (`max_retries=0`: a silent transport retry
  would be an uncounted second call).
- **Only generated content is text.** LM Studio returns the model's hidden
  reasoning as a separate `reasoning` (or `reasoning_content`) field, in the
  message and in stream deltas. That text is discarded at this boundary: it
  never becomes `ProviderResult.text` or a `TextDelta`, it is never logged,
  and only its *presence* and the runtime's reasoning-token count (when
  reported) travel onward as metadata.
- **The model that answered is the model that was asked.** The response names
  the model it came from; a mismatch is refused (`INVALID_OUTPUT`), never
  attributed to the requested configuration.
- **No silent context truncation.** The Core-assembled prompt is sent whole.
  If the server reports a prompt that fills its loaded context window, the
  reply is refused as `INVALID_OUTPUT` rather than settled — a local server
  may truncate an oversized prompt without saying so, and a reply built on a
  truncated prompt is not an answer to the question asked. Nothing here
  shortens, drops or retries.

## What only the live server can establish

The deterministic tests pin what this adapter *sends* and how it *maps* what
the installed client accepts. Whether LM Studio honours `reasoning_effort`,
returns usage on a stream, names the reasoning field `reasoning` or
`reasoning_content`, or reports prefill figures is the server's dialect, and
only a live loopback call proves it (`docs/reviews/qualification/runs/`).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
import openai

from val_domain.gateway import (
    CacheTtl,
    GatewayError,
    GatewayErrorKind,
    Message,
    ModelConfig,
    ReasoningEffort,
    TerminalState,
)
from val_domain.provider import (
    ContextFeasibility,
    ContextInspectionUnavailableError,
    ProviderEvent,
    TextDelta,
)
from val_providers.base import ProviderResult, normalize
from val_providers.lmstudio_inspector import LMStudioContextInspector

_LOGGER = logging.getLogger("val.providers.lmstudio")

#: The provider name every registry entry served here declares.
PROVIDER_NAME = "lmstudio"

#: The default local server: LM Studio's OpenAI-compatible base path.
DEFAULT_BASE_URL = "http://127.0.0.1:1234/v1"

#: Hosts that are this machine. Anything else is refused at construction.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

#: LM Studio's own model listing, beside the OpenAI-compatible surface: it
#: names the loaded model, its architecture, quantization and context length.
#: Read once at construction, recorded on every result; optional.
NATIVE_MODELS_PATH = "/api/v0/models"

#: The chat-completion reasoning fields the local dialect may use. Their text
#: is discarded; only presence is recorded.
_REASONING_FIELDS = ("reasoning", "reasoning_content")

#: gpt-oss reasoning levels the chat-completions surface accepts. Sent only for
#: a declared effort; `NOT_APPLICABLE` sends nothing.
_EFFORT: dict[ReasoningEffort, Literal["low", "medium", "high"]] = {
    ReasoningEffort.LOW: "low",
    ReasoningEffort.MEDIUM: "medium",
    ReasoningEffort.HIGH: "high",
}


#: The one deterministic separator the local wire canonicalization inserts between
#: the contents of consecutive same-role messages (owner ruling, 17 September 2026):
#: a blank line — the join LM Studio's chat-completions ingress was observed to
#: apply when it merged such a pair itself (the Qwen3.8-27B seam, evidence index §72).
WIRE_SEPARATOR = "\n\n"


def canonicalize_turns(turns: list[dict[str, str]]) -> list[dict[str, str]]:
    """One canonical local wire representation: consecutive same-role messages become
    one message of that role, contents joined by `WIRE_SEPARATOR`, in order.

    Why (owner ruling, 17 September 2026): Val Core structurally assembles the
    record-state envelope and the current user turn as two adjacent user
    messages. LM Studio's SDK `Chat` merges such a pair into one message with two
    content parts; its chat-completions ingress merges it into one string with a
    blank line; a Jinja template concatenates parts with nothing — so the exact
    preflight and the inference request rendered different prompts (5,560 vs
    5,561 on Qwen3.8-27B). Canonicalizing here, before BOTH branches, leaves the
    runtime nothing to merge on either path: divergence is removed by
    construction, not by calibration. Role-based, model-independent, never
    across roles, order and text otherwise unchanged; idempotent. Core's own
    message structure is untouched — this is the local adapter's wire form.
    """
    canonical: list[dict[str, str]] = []
    for turn in turns:
        if canonical and canonical[-1]["role"] == turn["role"]:
            canonical[-1] = {
                "role": turn["role"],
                "content": canonical[-1]["content"] + WIRE_SEPARATOR + turn["content"],
            }
        else:
            canonical.append({"role": turn["role"], "content": turn["content"]})
    return canonical


def _chat_turns(messages: tuple[Message, ...], system: str | None) -> list[dict[str, str]]:
    """The chat-completion items, in order — the one construction both the inference
    request and the context measurement use, already in the canonical local wire
    form (`canonicalize_turns`), so the two branches cannot diverge."""
    turns: list[dict[str, str]] = []
    if system is not None:
        turns.append({"role": "system", "content": system})
    for m in messages:
        turns.append({"role": "user" if m.role == "user" else "assistant", "content": m.content})
    return canonicalize_turns(turns)


def is_loopback(base_url: str) -> bool:
    """Whether the URL's host is this machine."""
    parsed = urlparse(base_url)
    return parsed.scheme in ("http", "https") and (parsed.hostname or "") in LOOPBACK_HOSTS


def _extra(obj: object, name: str) -> object:
    """A field the installed client does not model but the server may send."""
    value = getattr(obj, name, None)
    if value is None:
        extra = getattr(obj, "model_extra", None)
        if isinstance(extra, Mapping):
            value = extra.get(name)
    return value


def _reasoning_present(obj: object) -> bool:
    """Whether a message or delta carries reasoning text — the text itself is not read."""
    for name in _REASONING_FIELDS:
        value = _extra(obj, name)
        if isinstance(value, str) and value:
            return True
    return False


def _plain(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump()
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    if hasattr(value, "__dict__"):
        return {key: _plain(item) for key, item in vars(value).items()}
    return str(value)


class LMStudioAdapter:
    """LM Studio on the loopback interface, speaking the normalized contract."""

    name = PROVIDER_NAME

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        token: str | None = None,
        *,
        timeout_seconds: float = 600.0,
        read_native_models: bool = True,
        inspector: LMStudioContextInspector | None = None,
    ) -> None:
        if not is_loopback(base_url):
            raise ValueError(
                f"{self.name}: the base URL must name this machine (one of "
                f"{sorted(LOOPBACK_HOSTS)}); a remote server cannot be a local provider"
            )
        if not token:
            raise ValueError(
                f"{self.name}: the local server requires its API token "
                "(VAL_LMSTUDIO_API_TOKEN); the adapter is not constructed without it"
            )
        self._base_url = base_url.rstrip("/")
        self._client = openai.OpenAI(
            base_url=self._base_url, api_key=token, timeout=timeout_seconds, max_retries=0
        )
        # The native listing lives beside the OpenAI-compatible surface, not
        # under it, so it is fetched with the transport library directly; the
        # header is built once and never rendered anywhere.
        self._native_headers = {"Authorization": f"Bearer {token}"}
        self._native_models: dict[str, Mapping[str, object]] = {}
        if read_native_models:
            self._native_models = self._read_native_models()
        #: Ruling, 16 September 2026: the read-only runtime/context inspector,
        #: built by startup with the same credential; None means measurement is
        #: unavailable and the gateway fails closed on its byte bound.
        self._inspector = inspector

    # --- exact context measurement (ruling, 16 September 2026) ----------------

    def measure_context(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int | None = None,
    ) -> ContextFeasibility:
        """Measure exactly what `complete`/`stream` would send, against the loaded window.

        `max_output_tokens` is accepted for the shared contract and unused here: this
        runtime measures the message structure through its template RPC, which the
        output allowance does not enter.

        The turns are built by the same function the request uses, so the
        inspector renders the same message structure the OpenAI-compatible
        call transmits. Nothing is sent; nothing is generated; nothing is
        loaded. Without an inspector the measurement is unavailable and the
        caller fails closed.
        """
        if self._inspector is None:
            raise ContextInspectionUnavailableError(
                f"{self.name}: no runtime inspector was built for this adapter; the exact "
                "context preflight is unavailable and the conservative bound applies"
            )
        if config.provider != self.name:
            raise ContextInspectionUnavailableError(
                f"{self.name}: configuration {config.slug!r} belongs to {config.provider!r}"
            )
        del max_output_tokens
        return self._inspector.measure(config.model_identifier, _chat_turns(messages, system))

    # --- construction-time runtime facts ---------------------------------------

    def _read_native_models(self) -> dict[str, Mapping[str, object]]:
        """LM Studio's own listing, keyed by model id; empty if the server has none."""
        root = self._base_url[: -len("/v1")] if self._base_url.endswith("/v1") else self._base_url
        try:
            reply = httpx.get(root + NATIVE_MODELS_PATH, headers=self._native_headers, timeout=5.0)
            reply.raise_for_status()
            response = reply.json()
        except Exception as error:
            _LOGGER.info(
                "%s: native model listing unavailable: %s", self.name, type(error).__name__
            )
            return {}
        listing: dict[str, Mapping[str, object]] = {}
        for entry in response.get("data", []) if isinstance(response, dict) else []:
            if isinstance(entry, Mapping) and isinstance(entry.get("id"), str):
                listing[entry["id"]] = entry
        return listing

    def runtime_facts(self, model_identifier: str) -> dict[str, object]:
        """What the server says about this model — loaded state, context length, quantization."""
        entry = self._native_models.get(model_identifier)
        facts: dict[str, object] = {
            "runtime": "LM Studio",
            "base_url": self._base_url,
            "requested_model": model_identifier,
        }
        if entry is not None:
            for key in (
                "state",
                "arch",
                "quantization",
                "compatibility_type",
                "max_context_length",
                "loaded_context_length",
                "publisher",
            ):
                if key in entry:
                    facts[key] = _plain(entry[key])
        return facts

    def loaded_context_length(self, model_identifier: str) -> int | None:
        entry = self._native_models.get(model_identifier)
        value = None if entry is None else entry.get("loaded_context_length")
        return value if isinstance(value, int) and value > 0 else None

    # --- the two calling modes ---------------------------------------------------

    def complete(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> ProviderResult:
        kwargs = self._request(config, messages, system, max_output_tokens, output_schema)
        del cache_ttl  # no prompt-cache mechanism is requested of a local server
        try:
            completion = self._client.chat.completions.create(**kwargs)
        except Exception as error:
            raise self._normalized(error) from error
        return self._result(config, completion)

    def stream(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> Iterator[ProviderEvent]:
        """The same request, answered as content deltas then the final result.

        Reasoning deltas — before, between or after content — are never
        yielded; their presence is recorded. Usage arrives on the final chunk
        when the server honours `stream_options.include_usage`; otherwise the
        usage figures are `None`, never guessed.
        """
        kwargs = self._request(config, messages, system, max_output_tokens, output_schema)
        del cache_ttl
        text_parts: list[str] = []
        reasoning_present = False
        refusal: str | None = None
        finish_reason: str | None = None
        usage: object | None = None
        reported_model: str | None = None
        extras: dict[str, object] = {}
        try:
            chunks = self._client.chat.completions.create(
                stream=True, stream_options={"include_usage": True}, **kwargs
            )
            for chunk in chunks:
                model = getattr(chunk, "model", None)
                if isinstance(model, str) and model:
                    reported_model = model
                    self._refuse_mismatch(config, model)
                if getattr(chunk, "usage", None) is not None:
                    usage = chunk.usage
                stats = _extra(chunk, "stats")
                if stats is not None:
                    extras["stats"] = _plain(stats)
                for choice in getattr(chunk, "choices", None) or []:
                    delta = getattr(choice, "delta", None)
                    if delta is not None:
                        if _reasoning_present(delta):
                            reasoning_present = True
                        piece = getattr(delta, "content", None)
                        if piece:
                            text_parts.append(piece)
                            yield TextDelta(piece)
                        refused = getattr(delta, "refusal", None)
                        if refused:
                            refusal = (refusal or "") + refused
                    reason = getattr(choice, "finish_reason", None)
                    if reason:
                        finish_reason = reason
        except GatewayError:
            raise
        except Exception as error:
            raise self._normalized(error) from error
        yield self._assemble(
            config,
            text="".join(text_parts),
            refusal=refusal,
            finish_reason=finish_reason,
            usage=usage,
            reported_model=reported_model,
            reasoning_present=reasoning_present,
            extras=extras,
        )

    # --- request and response mapping -------------------------------------------

    def _request(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None,
    ) -> dict[str, Any]:
        """The chat-completion request: the Core-assembled prompt, whole and in order."""
        if config.provider != self.name:
            raise GatewayError(
                GatewayErrorKind.INVALID_REQUEST,
                f"{self.name}: configuration {config.slug!r} belongs to provider "
                f"{config.provider!r}; this adapter serves only {self.name!r} entries",
            )
        if output_schema is not None:
            raise GatewayError(
                GatewayErrorKind.INVALID_REQUEST,
                f"{self.name}: this route is conversation-only and enforces no output "
                "schema; a schema-constrained task is refused rather than sent unconstrained",
            )
        undeliverable = [
            name
            for name in ("thinking_enabled", "preserve_thinking", "top_p", "top_k")
            if getattr(config, name) is not None
        ]
        if undeliverable:
            # Owner ruling, 18 September 2026: a declared state is transmitted and
            # provable, or refused. This runtime's chat-completions request cannot
            # carry a thinking switch, and no entry served here declares these.
            raise GatewayError(
                GatewayErrorKind.INVALID_REQUEST,
                f"{self.name}: {config.slug!r} declares {', '.join(undeliverable)}, which this "
                "adapter does not transmit; refused rather than silently dropped",
            )
        kwargs: dict[str, Any] = {
            "model": config.model_identifier,
            "messages": _chat_turns(messages, system),
            "max_tokens": max_output_tokens,
        }
        effort = _EFFORT.get(config.reasoning_effort)
        if effort is not None:
            kwargs["reasoning_effort"] = effort
        if config.temperature is not None:
            kwargs["temperature"] = config.temperature
        return kwargs

    def _refuse_mismatch(self, config: ModelConfig, reported: str) -> None:
        if reported != config.model_identifier:
            raise GatewayError(
                GatewayErrorKind.INVALID_OUTPUT,
                f"{self.name}: the server answered with model {reported!r}, not the "
                f"requested {config.model_identifier!r}; the reply is refused rather than "
                "attributed to the requested configuration",
            )

    def _normalized(self, error: Exception) -> GatewayError:
        name = type(error).__name__
        if name == "APIConnectionError":
            return GatewayError(
                GatewayErrorKind.PROVIDER_ERROR,
                f"{self.name}: cannot reach the local inference server at {self._base_url}; "
                "LM Studio's server is not running or not listening there",
            )
        if name == "NotFoundError":
            return GatewayError(
                GatewayErrorKind.INVALID_REQUEST,
                f"{self.name}: the server has no such model available to load or serve: "
                f"{str(error)[:200]}",
            )
        return normalize(error, self.name)

    def _result(self, config: ModelConfig, completion: object) -> ProviderResult:
        reported = getattr(completion, "model", None)
        reported_model = reported if isinstance(reported, str) and reported else None
        if reported_model is not None:
            self._refuse_mismatch(config, reported_model)
        choices = getattr(completion, "choices", None) or []
        message = getattr(choices[0], "message", None) if choices else None
        text = ""
        refusal: str | None = None
        reasoning_present = False
        if message is not None:
            content = getattr(message, "content", None)
            text = content if isinstance(content, str) else ""
            refused = getattr(message, "refusal", None)
            refusal = refused if isinstance(refused, str) and refused else None
            reasoning_present = _reasoning_present(message)
        finish_reason = getattr(choices[0], "finish_reason", None) if choices else None
        extras: dict[str, object] = {}
        stats = _extra(completion, "stats")
        if stats is not None:
            extras["stats"] = _plain(stats)
        return self._assemble(
            config,
            text=text,
            refusal=refusal,
            finish_reason=finish_reason,
            usage=getattr(completion, "usage", None),
            reported_model=reported_model,
            reasoning_present=reasoning_present,
            extras=extras,
        )

    def _assemble(
        self,
        config: ModelConfig,
        *,
        text: str,
        refusal: str | None,
        finish_reason: object,
        usage: object,
        reported_model: str | None,
        reasoning_present: bool,
        extras: Mapping[str, object],
    ) -> ProviderResult:
        if finish_reason == "stop" or (finish_reason is None and (text or refusal)):
            terminal = TerminalState.REFUSED if refusal else TerminalState.COMPLETE
        elif finish_reason == "length":
            terminal = TerminalState.TRUNCATED
        elif finish_reason == "content_filter":
            terminal = TerminalState.FILTERED
        else:
            terminal = TerminalState.UNKNOWN
        tokens_in = getattr(usage, "prompt_tokens", None) if usage is not None else None
        tokens_out = getattr(usage, "completion_tokens", None) if usage is not None else None
        details = getattr(usage, "completion_tokens_details", None) if usage is not None else None
        reasoning_tokens = getattr(details, "reasoning_tokens", None) if details else None
        loaded = self.loaded_context_length(config.model_identifier)
        if loaded is not None and isinstance(tokens_in, int) and tokens_in >= loaded:
            raise GatewayError(
                GatewayErrorKind.INVALID_OUTPUT,
                f"{self.name}: the server reports a prompt of {tokens_in} tokens against a "
                f"loaded context of {loaded}; the prompt filled the window and silent "
                "truncation cannot be excluded, so the reply is refused rather than settled",
            )
        runtime: dict[str, object] = {
            **self.runtime_facts(config.model_identifier),
            "reported_model": reported_model,
            "finish_reason": _plain(finish_reason),
            **dict(extras),
        }
        return ProviderResult(
            text=refusal if refusal is not None else text,
            terminal=terminal,
            tokens_in=tokens_in if isinstance(tokens_in, int) else None,
            tokens_out=tokens_out if isinstance(tokens_out, int) else None,
            provider_request_id=None,
            stop_reason=None if finish_reason is None else str(finish_reason),
            stop_details=None,
            reasoning_present=reasoning_present or (reasoning_tokens or 0) > 0,
            reasoning_tokens=reasoning_tokens if isinstance(reasoning_tokens, int) else None,
            provider_reported_model=reported_model,
            runtime_diagnostics=runtime,
        )
