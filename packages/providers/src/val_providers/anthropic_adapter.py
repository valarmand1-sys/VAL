"""The Anthropic adapter.

Model identifiers and behaviour follow Anthropic's current documentation:
thinking is on by default on Claude Opus 5 and `max_tokens` bounds thinking plus
response text together, so callers give it headroom. A `stop_reason` of
`refusal` is a content outcome, not an error — it returns a refused result, and
the gateway records it as `status = refused` rather than raising.
"""

import time

import anthropic

from val_domain.gateway import Message, ModelConfig
from val_providers.base import ProviderResult, normalize


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
    ) -> ProviderResult:
        """Run one completion, or raise the normalized error."""
        turns: list[anthropic.types.MessageParam] = [
            {"role": "user" if m.role == "user" else "assistant", "content": m.content}
            for m in messages
        ]
        try:
            response = self._client.messages.create(
                model=config.model_identifier,
                max_tokens=max_output_tokens,
                messages=turns,
                system=system if system is not None else anthropic.omit,
            )
        except Exception as error:
            raise normalize(error, self.name) from error

        text = "".join(
            block.text for block in response.content if isinstance(block, anthropic.types.TextBlock)
        )
        return ProviderResult(
            text=text,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            provider_request_id=getattr(response, "_request_id", None),
            refused=response.stop_reason == "refusal",
        )


def measure(start: float) -> int:
    """Elapsed milliseconds, for `model_calls.latency_ms`."""
    return int((time.monotonic() - start) * 1000)
