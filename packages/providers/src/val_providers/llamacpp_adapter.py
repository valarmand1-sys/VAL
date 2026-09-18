"""The llama.cpp adapter — the second local cognition provider (owner ruling, 18 September 2026).

A standalone `llama-server` on the loopback interface, speaking the
OpenAI-compatible chat-completions dialect. It stands beside `LMStudioAdapter`
and replaces nothing. It exists because this runtime lets Val Core *declare* a
model's cognitive mode on every request and *prove* what was executed — which a
runtime whose thinking switch lives in a per-model UI preset cannot.

## What this adapter guarantees

- **Loopback only, keyed.** A non-loopback base URL is refused at construction;
  the provider's own dedicated key is required and appears in no log, error,
  result or record.
- **One canonical request body.** `wire_body` builds the single dictionary that
  is both counted by the exact preflight (`/v1/chat/completions/input_tokens`)
  and transmitted for inference. Messages take the accepted local wire form
  (`canonicalize_turns`). The body counted is the body sent.
- **Declared is transmitted.** `thinking_enabled` and `preserve_thinking` travel
  as `chat_template_kwargs` (`enable_thinking`, `preserve_thinking`);
  `temperature`, `top_p`, `top_k` travel verbatim. A `None` sends nothing and
  means the model has no such contract — never "whatever the runtime prefers".
  A graded reasoning effort is refused here: this runtime does not honour one.
- **Conversation only.** No tools, no schema-constrained output, no client
  retries (`max_retries=0`), no fallback.
- **Only generated content is text.** The server's Gemma-aware parser returns
  hidden thought as `reasoning_content`; that text is discarded at this
  boundary — never a delta, never the result text, never logged. Only its
  presence (and a token count, when reported) travels onward.
- **No silent truncation.** A reply whose reported prompt filled the server's
  context is refused rather than settled.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from typing import Any

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
from val_providers.llamacpp_inspector import LOOPBACK_HOSTS, LlamaCppContextInspector, is_loopback
from val_providers.lmstudio_adapter import _chat_turns, _extra, _plain, _reasoning_present

_LOGGER = logging.getLogger("val.providers.llamacpp")

#: The provider name every registry entry served here declares.
PROVIDER_NAME = "llamacpp"

#: The default local server: `llama-server`'s OpenAI-compatible base path.
DEFAULT_BASE_URL = "http://127.0.0.1:8766/v1"

#: Request fields the installed OpenAI client models itself; everything else in
#: the canonical body rides in `extra_body` and is merged back by the client.
_CLIENT_FIELDS = frozenset({"model", "messages", "max_tokens", "temperature", "top_p"})


def wire_body(
    config: ModelConfig,
    messages: tuple[Message, ...],
    system: str | None,
    max_output_tokens: int,
) -> dict[str, Any]:
    """The one canonical chat-completions body: counted by the preflight, sent for inference."""
    body: dict[str, Any] = {
        "model": config.model_identifier,
        "messages": _chat_turns(messages, system),
        "max_tokens": max_output_tokens,
    }
    if config.temperature is not None:
        body["temperature"] = config.temperature
    if config.top_p is not None:
        body["top_p"] = config.top_p
    if config.top_k is not None:
        body["top_k"] = config.top_k
    template_kwargs: dict[str, bool] = {}
    if config.thinking_enabled is not None:
        template_kwargs["enable_thinking"] = config.thinking_enabled
    if config.preserve_thinking is not None:
        template_kwargs["preserve_thinking"] = config.preserve_thinking
    if template_kwargs:
        body["chat_template_kwargs"] = template_kwargs
    return body


def split_for_client(body: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """`(client keyword arguments, extra_body)` — merged back, they are exactly `body`."""
    kwargs = {key: value for key, value in body.items() if key in _CLIENT_FIELDS}
    extra = {key: value for key, value in body.items() if key not in _CLIENT_FIELDS}
    return kwargs, extra


class LlamaCppAdapter:
    """A llama.cpp server on the loopback interface, speaking the normalized contract."""

    name = PROVIDER_NAME

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        key: str | None = None,
        *,
        timeout_seconds: float = 900.0,
        inspector: LlamaCppContextInspector | None = None,
    ) -> None:
        if not is_loopback(base_url):
            raise ValueError(
                f"{self.name}: the base URL must name this machine (one of "
                f"{sorted(LOOPBACK_HOSTS)}); a remote server cannot be a local provider"
            )
        if not key:
            raise ValueError(
                f"{self.name}: the local server requires its API key "
                "(VAL_LLAMACPP_API_KEY); the adapter is not constructed without it"
            )
        self._base_url = base_url.rstrip("/")
        self._client = openai.OpenAI(
            base_url=self._base_url, api_key=key, timeout=timeout_seconds, max_retries=0
        )
        #: The read-only HTTP inspector, built by startup with the same key; None
        #: means measurement is unavailable and the gateway fails closed.
        self._inspector = inspector
        self._runtime: dict[str, object] | None = None

    # --- exact context measurement ---------------------------------------------------

    def measure_context(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int | None = None,
    ) -> ContextFeasibility:
        """The server's own count of the exact body `complete`/`stream` would send."""
        if self._inspector is None:
            raise ContextInspectionUnavailableError(
                f"{self.name}: no runtime inspector was built for this adapter; the exact "
                "context preflight is unavailable and the conservative bound applies"
            )
        if config.provider != self.name:
            raise ContextInspectionUnavailableError(
                f"{self.name}: configuration {config.slug!r} belongs to {config.provider!r}"
            )
        if max_output_tokens is None:
            raise ContextInspectionUnavailableError(
                f"{self.name}: the output allowance was not supplied, so the exact request "
                "body cannot be built; the body counted must be the body sent"
            )
        body = wire_body(config, messages, system, max_output_tokens)
        feasibility = self._inspector.measure(config.model_identifier, body)
        self._runtime = {k: v for k, v in feasibility.details.items() if k != "counted_body_keys"}
        return feasibility

    def runtime_facts(self, model_identifier: str) -> dict[str, object]:
        facts: dict[str, object] = {
            "runtime": "llama.cpp server",
            "base_url": self._base_url,
            "requested_model": model_identifier,
        }
        if self._runtime is None and self._inspector is not None:
            try:
                self._runtime = self._inspector.runtime_facts()
            except ContextInspectionUnavailableError:
                self._runtime = {}
        facts.update(self._runtime or {})
        return facts

    def loaded_context_length(self) -> int | None:
        value = (self._runtime or {}).get("n_ctx")
        return value if isinstance(value, int) and value > 0 else None

    # --- the two calling modes ---------------------------------------------------------

    def complete(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> ProviderResult:
        kwargs, extra = self._request(config, messages, system, max_output_tokens, output_schema)
        del cache_ttl
        try:
            completion = self._client.chat.completions.create(**kwargs, extra_body=extra)
        except Exception as error:
            raise self._normalized(error) from error
        choices = getattr(completion, "choices", None) or []
        message = getattr(choices[0], "message", None) if choices else None
        content = getattr(message, "content", None) if message is not None else None
        refused = getattr(message, "refusal", None) if message is not None else None
        return self._assemble(
            config,
            text=content if isinstance(content, str) else "",
            refusal=refused if isinstance(refused, str) and refused else None,
            finish_reason=getattr(choices[0], "finish_reason", None) if choices else None,
            usage=getattr(completion, "usage", None),
            reported_model=getattr(completion, "model", None),
            reasoning_present=message is not None and _reasoning_present(message),
            extras=self._extras(completion),
        )

    def stream(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> Iterator[ProviderEvent]:
        """The same body, answered as content deltas then the final result.

        Reasoning deltas are never yielded; their presence is recorded.
        """
        kwargs, extra = self._request(config, messages, system, max_output_tokens, output_schema)
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
                stream=True, stream_options={"include_usage": True}, **kwargs, extra_body=extra
            )
            for chunk in chunks:
                model = getattr(chunk, "model", None)
                if isinstance(model, str) and model:
                    reported_model = model
                if getattr(chunk, "usage", None) is not None:
                    usage = chunk.usage
                extras.update(self._extras(chunk))
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

    # --- request and response mapping -------------------------------------------------

    def _request(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
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
        if config.reasoning_effort is not ReasoningEffort.NOT_APPLICABLE:
            raise GatewayError(
                GatewayErrorKind.INVALID_REQUEST,
                f"{self.name}: {config.slug!r} declares a graded reasoning effort, which this "
                "runtime does not honour; a declared setting is transmitted or refused, never "
                "dropped (binary thinking is declared with thinking_enabled)",
            )
        return split_for_client(wire_body(config, messages, system, max_output_tokens))

    @staticmethod
    def _extras(obj: object) -> dict[str, object]:
        timings = _extra(obj, "timings")
        return {} if timings is None else {"timings": _plain(timings)}

    def _normalized(self, error: Exception) -> GatewayError:
        if type(error).__name__ == "APIConnectionError":
            return GatewayError(
                GatewayErrorKind.PROVIDER_ERROR,
                f"{self.name}: cannot reach the local inference server at {self._base_url}; "
                "llama-server is not running or not listening there",
            )
        return normalize(error, self.name)

    def _assemble(
        self,
        config: ModelConfig,
        *,
        text: str,
        refusal: str | None,
        finish_reason: object,
        usage: object,
        reported_model: object,
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
        loaded = self.loaded_context_length()
        if loaded is not None and isinstance(tokens_in, int) and tokens_in >= loaded:
            raise GatewayError(
                GatewayErrorKind.INVALID_OUTPUT,
                f"{self.name}: the server reports a prompt of {tokens_in} tokens against a "
                f"context of {loaded}; the prompt filled the window and silent truncation "
                "cannot be excluded, so the reply is refused rather than settled",
            )
        model = reported_model if isinstance(reported_model, str) and reported_model else None
        runtime: dict[str, object] = {
            **self.runtime_facts(config.model_identifier),
            "reported_model": model,
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
            provider_reported_model=model,
            runtime_diagnostics=runtime,
        )
