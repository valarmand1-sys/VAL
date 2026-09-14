"""The OpenAI adapter.

Uses the Responses API, which is OpenAI's primary surface: `responses.create`
takes `input` and `instructions`, and returns `output_text` with token counts on
`usage.input_tokens` / `usage.output_tokens`.

## Terminal-state mapping — explicit, and closed

*Corrected in the current-version closure pass, 18 August 2026.* The previous
adapter mapped `status == "incomplete"` to *refused*, which is wrong in the
provider's own vocabulary: `incomplete` means the output stopped early —
`incomplete_details.reason` says whether the output-token cap or the content
filter stopped it — while an actual refusal arrives as a `refusal` content part
inside an otherwise `completed` response. Under the old mapping a truncated
answer was recorded as Val declining, and a real refusal fell through as an
ordinary (often empty) completed reply.

| Responses API state | `TerminalState` |
|---|---|
| `completed`, no refusal part | `COMPLETE` |
| `completed`, refusal part present | `REFUSED` (the refusal text is the text) |
| `incomplete` / `max_output_tokens` | `TRUNCATED` |
| `incomplete` / `content_filter` | `FILTERED` — incomplete, never an utterance |
| `failed` | raises the normalized provider error |
| anything else | `UNKNOWN` — fails closed at the gateway |

## Two calling modes, one translation — ruling, 13 September 2026

`complete` and `stream` build the identical request (`_request`) and map the
identical final response (`_result`). `stream` sends it with `stream=True` and
reads the Responses API's server-sent events: each `response.output_text.delta`
becomes a provider-neutral `TextDelta` (refusal deltas and reasoning events are
never text), and the terminal `response.completed`, `response.incomplete` or
`response.failed` event carries the final response object, mapped by exactly
the function `complete` uses. A stream that ends without a terminal event, or
reports an `error` event, raises the normalized provider error; the gateway
settles such a call as unknown. No OpenAI type leaves this module.

## Usage, caching and reasoning, as reported — rulings, 13 and 14 September 2026

`usage.input_tokens` is the whole input. `input_tokens_details.cached_tokens`
is the cache-read figure and `cache_write_tokens` the automatic cache-write
figure (`cache_write_auto_tokens`); `tokens_in` is the remainder — input minus
reads minus writes — so the three are disjoint and the gateway prices each at
the route's verified rate (base, read, automatic write), never a token twice.
On a route whose caching is not verified the gateway prices reads and writes at
base, which over-states a read and under-states a GPT-5.6 write by a quarter.
`output_tokens_details.reasoning_tokens` is recorded as the reasoning figure,
and the presence of a `reasoning` output item as the reasoning fact.

Missing usage becomes `None`, never zero. The previous `usage.input_tokens if
usage else 0` fabricated a known $0 for exactly the calls whose cost was not
known, which is the defect the WP-0.4 cost doctrine exists to prevent.
"""

from collections.abc import Iterator, Mapping
from typing import Any, Literal

import openai
from openai.types.responses import (
    ResponseFormatTextJSONSchemaConfigParam,
    ResponseTextConfigParam,
)
from openai.types.shared_params import Reasoning

from val_domain.gateway import (
    CacheTtl,
    GatewayError,
    GatewayErrorKind,
    Message,
    ModelConfig,
    ReasoningEffort,
    TerminalState,
)
from val_domain.provider import ProviderEvent, TextDelta
from val_providers.base import ProviderResult, normalize

#: Provider-neutral levels in the SDK's literal vocabulary; explicit so an
#: unaccepted registry level fails loudly at call time rather than as a 400.
_EFFORT: dict[ReasoningEffort, Literal["none", "minimal", "low", "medium", "high"]] = {
    # `none` (10 September 2026): documented on the GPT-5.6 family as the
    # level for latency-critical tasks that do not benefit from reasoning;
    # GPT-6 Astra rejects it with a 400, which the adapter surfaces as-is.
    ReasoningEffort.NONE: "none",
    ReasoningEffort.MINIMAL: "minimal",
    ReasoningEffort.LOW: "low",
    ReasoningEffort.MEDIUM: "medium",
    ReasoningEffort.HIGH: "high",
}

#: The terminal events of a Responses API stream, each carrying the final response.
_TERMINAL_EVENTS = frozenset({"response.completed", "response.incomplete", "response.failed"})


def _refusal_text(response: object) -> str | None:
    """The refusal content, if any output item carries one."""
    for item in getattr(response, "output", None) or []:
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", "") == "refusal":
                return str(getattr(part, "refusal", "")) or "(refused without stated reason)"
    return None


class OpenAIAdapter:
    """OpenAI, speaking the normalized contract."""

    name = "openai"

    def __init__(self, api_key: str) -> None:
        self._client = openai.OpenAI(api_key=api_key)

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
        kwargs = self._request(
            config, messages, system, max_output_tokens, output_schema, cache_ttl
        )
        try:
            response = self._client.responses.create(**kwargs)
        except Exception as error:
            raise normalize(error, self.name) from error
        return self._result(response)

    def stream(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> Iterator[ProviderEvent]:
        """The same call as `complete`, answered as text deltas then the final result."""
        kwargs = self._request(
            config, messages, system, max_output_tokens, output_schema, cache_ttl
        )
        final: object | None = None
        try:
            events = self._client.responses.create(stream=True, **kwargs)
            for event in events:
                kind = getattr(event, "type", "")
                if kind == "response.output_text.delta":
                    delta = getattr(event, "delta", "")
                    if delta:
                        yield TextDelta(delta)
                elif kind in _TERMINAL_EVENTS:
                    final = getattr(event, "response", None)
                elif kind == "error":
                    raise GatewayError(
                        GatewayErrorKind.PROVIDER_ERROR,
                        f"{self.name}: the stream reported an error event: "
                        f"{getattr(event, 'code', None)} {getattr(event, 'message', '')}",
                    )
        except GatewayError:
            raise
        except Exception as error:
            raise normalize(error, self.name) from error
        if final is None:
            raise GatewayError(
                GatewayErrorKind.PROVIDER_ERROR,
                f"{self.name}: the stream ended without a terminal response event, so the "
                "call's outcome, usage and cost are unknown",
            )
        yield self._result(final)

    def _request(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None,
        cache_ttl: CacheTtl | None,
    ) -> dict[str, Any]:
        """The SDK request both calling modes send — built once, identically."""
        # `cache_ttl` is accepted and not sent (8 September 2026): OpenAI's
        # caching is automatic, this registry has not verified its cache rates,
        # and nothing is requested here; what the provider reports is recorded
        # as it arrives (module docstring).
        del cache_ttl
        turns: list[openai.types.responses.EasyInputMessageParam] = [
            {"role": "user" if m.role == "user" else "assistant", "content": m.content}
            for m in messages
        ]
        # 3 September 2026: a schema constraint rides on the Responses API's
        # `text.format` as a strict `json_schema`, the provider's structured
        # output mechanism — the reply is then guaranteed to conform. Strict
        # mode requires `additionalProperties: false` and every property
        # required, which the house's schemas state explicitly.
        text_config: ResponseTextConfigParam | openai.Omit = openai.omit
        if output_schema is not None:
            text_config = ResponseTextConfigParam(
                format=ResponseFormatTextJSONSchemaConfigParam(
                    type="json_schema",
                    name="val_structured_reply",
                    schema=dict(output_schema),
                    strict=True,
                )
            )
        return {
            "model": config.model_identifier,
            "input": list(turns),
            "max_output_tokens": max_output_tokens,
            "instructions": system,
            "text": text_config,
            # Independent-review correction, 18 August 2026: the registry's
            # declared effort is SENT, not assumed. GPT-5.5 documents
            # reasoning.effort with medium as the default; the configured
            # MEDIUM is stated on every request so a provider-side default
            # change cannot silently alter a versioned configuration.
            "reasoning": (
                openai.omit
                if config.reasoning_effort is ReasoningEffort.NOT_APPLICABLE
                else Reasoning(effort=_EFFORT[config.reasoning_effort])
            ),
        }

    def _result(self, response: object) -> ProviderResult:
        """The provider-neutral result from a final response — both modes, one mapping."""
        status = getattr(response, "status", None)
        response_id = getattr(response, "id", None)
        if status == "failed":
            # The response object arrived but reports its own failure. This is a
            # provider failure wearing a 200, and it is raised as one.
            failure = getattr(response, "error", None)
            raise GatewayError(
                GatewayErrorKind.PROVIDER_ERROR,
                f"{self.name}: response {response_id} reports status 'failed': "
                f"{getattr(failure, 'message', failure)}",
            )

        refusal = _refusal_text(response)
        if status == "completed":
            terminal = TerminalState.REFUSED if refusal else TerminalState.COMPLETE
        elif status == "incomplete":
            reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
            if reason == "max_output_tokens":
                terminal = TerminalState.TRUNCATED
            elif reason == "content_filter":
                # Independent-review correction, 18 August 2026: an incomplete
                # response is incomplete, whatever stopped it. A refusal is the
                # model's deliberate, complete utterance; a filter cut this one
                # off mid-stream, and mapping it to REFUSED let the fragment be
                # persisted as Val's finished message. FILTERED is evidence,
                # never an utterance.
                terminal = TerminalState.FILTERED
            else:
                terminal = TerminalState.UNKNOWN
        else:
            terminal = TerminalState.UNKNOWN

        usage = getattr(response, "usage", None)
        input_details = getattr(usage, "input_tokens_details", None)
        output_details = getattr(usage, "output_tokens_details", None)
        cached = getattr(input_details, "cached_tokens", None)
        written = getattr(input_details, "cache_write_tokens", None)
        tokens_in = getattr(usage, "input_tokens", None) if usage else None
        if tokens_in is not None:
            tokens_in = max(tokens_in - (cached or 0) - (written or 0), 0)
        incomplete_reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
        output_items = getattr(response, "output", None)
        return ProviderResult(
            text=refusal if refusal is not None else (getattr(response, "output_text", None) or ""),
            terminal=terminal,
            tokens_in=tokens_in,
            tokens_out=getattr(usage, "output_tokens", None) if usage else None,
            provider_request_id=response_id,
            cache_read_tokens=cached,
            # Ruling, 8 September 2026: the provider's own terminal fields.
            stop_reason=status,
            stop_details=(
                f"incomplete_details.reason={incomplete_reason}"
                if incomplete_reason
                else ("refusal item present" if refusal is not None else None)
            ),
            reasoning_present=(
                None
                if output_items is None
                else any(getattr(item, "type", "") == "reasoning" for item in output_items)
            ),
            reasoning_tokens=getattr(output_details, "reasoning_tokens", None),
            cache_write_auto_tokens=written,
        )
