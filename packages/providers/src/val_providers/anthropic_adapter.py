"""The Anthropic adapter.

Model identifiers and behaviour follow Anthropic's current documentation:
thinking is on by default on Claude Opus 5 and `max_tokens` bounds thinking plus
response text together, so callers give it headroom.

## Stop-reason mapping — explicit, and closed

Anthropic's documented `stop_reason` values map onto the provider-neutral
`TerminalState` one by one. The mapping is a dict rather than a chain of
conditionals so the whole contract is visible at once, and **anything not in
it maps to `UNKNOWN`**, which the gateway fails closed on. `tool_use` and
`pause_turn` are deliberately absent: Layer 0 never sends a tool, so receiving
either would mean the provider answered a request we did not make — a state we
do not understand, which is what `UNKNOWN` is for.

| `stop_reason` | `TerminalState` |
|---|---|
| `end_turn` | `COMPLETE` |
| `refusal` | `REFUSED` |
| `max_tokens` | `TRUNCATED` |
| anything else | `UNKNOWN` |

Missing usage becomes `None`, never zero: a zero that is not known to be zero
would be priced and recorded as a known $0 (closure pass, 18 August 2026).

The registry's `reasoning_effort` is carried on the request via the SDK's
`output_config={"effort": ...}` (anthropic 0.122.0 type surface, matching the
`effort` parameter in Anthropic's current docs). `NOT_APPLICABLE` sends nothing.
"""

import time
from collections.abc import Mapping
from typing import Literal

import anthropic
from anthropic.types import JSONOutputFormatParam, OutputConfigParam

from val_domain.gateway import (
    CacheTtl,
    GatewayError,
    GatewayErrorKind,
    Message,
    ModelConfig,
    ReasoningEffort,
    TerminalState,
)
from val_providers.base import ProviderResult, normalize

#: The provider-neutral levels this house configures, in the SDK's own literal
#: vocabulary. An explicit mapping rather than `.value` so a registry level the
#: SDK does not accept is a KeyError at call time, not a silent 400.
_EFFORT: dict[ReasoningEffort, Literal["low", "medium", "high"]] = {
    ReasoningEffort.LOW: "low",
    ReasoningEffort.MEDIUM: "medium",
    ReasoningEffort.HIGH: "high",
}

_STOP_REASONS: dict[str, TerminalState] = {
    "end_turn": TerminalState.COMPLETE,
    "refusal": TerminalState.REFUSED,
    "max_tokens": TerminalState.TRUNCATED,
    # `stop_sequence` is deliberately absent — closure red-team, 18 August
    # 2026. This adapter never sends `stop_sequences`, so the provider cannot
    # legitimately return that reason; receiving it means the provider answered
    # a request we did not make, which is the same cannot-occur rationale that
    # keeps `tool_use` and `pause_turn` out of this table. Absent maps to
    # UNKNOWN, which fails closed.
}


class AnthropicAdapter:
    """Anthropic, speaking the normalized contract."""

    name = "anthropic"

    def __init__(self, api_key: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> ProviderResult:
        """Run one completion, or raise the normalized error."""
        # Ruled 10 September 2026: a message flagged as the cache breakpoint —
        # the last retained history message — is sent as a text block carrying
        # `cache_control`, so the persona-plus-history prefix is cached and an
        # append-only thread reads it on the next turn. Only when a lifetime was
        # requested; otherwise the flag is inert and the plain form is sent.
        message_cache_control: anthropic.types.CacheControlEphemeralParam | None = None
        if cache_ttl is not None:
            message_cache_control = {"type": "ephemeral"}
            if cache_ttl is CacheTtl.ONE_HOUR:
                message_cache_control["ttl"] = "1h"
        turns: list[anthropic.types.MessageParam] = [
            {
                "role": "user" if m.role == "user" else "assistant",
                "content": (
                    [{"type": "text", "text": m.content, "cache_control": message_cache_control}]
                    if m.cache_breakpoint and message_cache_control is not None
                    else m.content
                ),
            }
            for m in messages
        ]
        # Independent-review correction, 18 August 2026: the registry's
        # declared effort is SENT, not assumed. The provider's default happens
        # to match today (Opus 5 defaults to high on the Claude API), but a
        # versioned configuration must not depend on a provider default
        # silently staying put. NOT_APPLICABLE sends nothing — the model has no
        # such parameter, and inventing one would be configuring a concept the
        # provider does not offer.
        #
        # 3 September 2026: the same `output_config` carries the schema
        # constraint (Anthropic's structured outputs, GA, `format` of type
        # `json_schema`). The provider then guarantees the text block is valid
        # JSON conforming to the schema; the grammar is compiled once per
        # schema and cached provider-side, and no extra tokens are billed
        # beyond the format's own system text, which the usage block reports
        # like any other input. An empty config is omitted, as before.
        output_config: OutputConfigParam = {}
        if config.reasoning_effort is not ReasoningEffort.NOT_APPLICABLE:
            level = _EFFORT.get(config.reasoning_effort)
            if level is None:
                # A registry level Anthropic does not offer (`none`, `minimal`)
                # is refused before any provider contact — never mapped to the
                # nearest level, which would run a configuration nobody stated.
                raise GatewayError(
                    GatewayErrorKind.INVALID_REQUEST,
                    f"{self.name}: {config.slug} declares reasoning effort "
                    f"{config.reasoning_effort.value!r}, which is not an Anthropic effort "
                    f"level ({', '.join(sorted(v for v in _EFFORT.values()))}); the "
                    "configuration is refused rather than run at a substituted level",
                )
            output_config["effort"] = level
        if output_schema is not None:
            output_config["format"] = JSONOutputFormatParam(
                type="json_schema", schema=dict(output_schema)
            )
        # Ruling, 8 September 2026: prompt caching on the stable prefix. The
        # persona is the whole of `system` and the only byte-identical prefix
        # every partner call shares, so the one breakpoint goes on it — as a
        # single text block carrying `cache_control`. Since 10 September 2026 the
        # last retained history message carries a second breakpoint (above); the
        # envelopes and the current turn follow it and are never marked. The TTL
        # is the caller's (configuration), and the provider's own minimum
        # prefix decides whether anything is actually cached; the usage block
        # is the ground truth either way.
        system_param: str | list[anthropic.types.TextBlockParam] | anthropic.Omit
        if system is None:
            system_param = anthropic.omit
        elif cache_ttl is None:
            system_param = system
        else:
            cache_control: anthropic.types.CacheControlEphemeralParam = {"type": "ephemeral"}
            if cache_ttl is CacheTtl.ONE_HOUR:
                cache_control["ttl"] = "1h"
            system_param = [{"type": "text", "text": system, "cache_control": cache_control}]
        try:
            response = self._client.messages.create(
                model=config.model_identifier,
                max_tokens=max_output_tokens,
                messages=turns,
                system=system_param,
                output_config=output_config if output_config else anthropic.omit,
            )
        except Exception as error:
            raise normalize(error, self.name) from error

        text = "".join(
            block.text for block in response.content if isinstance(block, anthropic.types.TextBlock)
        )
        usage = getattr(response, "usage", None)
        # The four usage figures, as documented: `input_tokens` is the uncached
        # remainder after the last breakpoint; `cache_read_input_tokens` and
        # `cache_creation_input_tokens` are the cached parts, the latter broken
        # down by lifetime in `cache_creation`. Where the breakdown is absent
        # the whole creation figure is attributed to the lifetime requested,
        # because that is the rate the provider bills it at; where no caching
        # was requested, absent figures are None and price as zero activity.
        creation = getattr(usage, "cache_creation", None)
        write_5m = getattr(creation, "ephemeral_5m_input_tokens", None)
        write_1h = getattr(creation, "ephemeral_1h_input_tokens", None)
        creation_total = getattr(usage, "cache_creation_input_tokens", None)
        if creation_total is not None and write_5m is None and write_1h is None:
            if cache_ttl is CacheTtl.ONE_HOUR:
                write_1h = creation_total
            else:
                write_5m = creation_total
        # Ruling, 8 September 2026: the provider's terminal fields travel with
        # the result. `stop_details` carries a refusal's category and
        # explanation when the provider gives them; it is rendered as text and
        # never interpreted here.
        details = getattr(response, "stop_details", None)
        rendered_details: str | None = None
        if details is not None:
            dump = getattr(details, "model_dump", None)
            rendered_details = str(dump(exclude_none=True)) if callable(dump) else str(details)
        return ProviderResult(
            text=text,
            terminal=_STOP_REASONS.get(response.stop_reason or "", TerminalState.UNKNOWN),
            tokens_in=getattr(usage, "input_tokens", None),
            tokens_out=getattr(usage, "output_tokens", None),
            provider_request_id=getattr(response, "_request_id", None),
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", None),
            cache_write_5m_tokens=write_5m,
            cache_write_1h_tokens=write_1h,
            stop_reason=response.stop_reason,
            stop_details=rendered_details,
        )


def measure(start: float) -> int:
    """Elapsed milliseconds, for `model_calls.latency_ms`."""
    return int((time.monotonic() - start) * 1000)
