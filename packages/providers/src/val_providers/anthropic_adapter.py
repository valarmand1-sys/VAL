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
| `stop_sequence` | `COMPLETE` |
| `refusal` | `REFUSED` |
| `max_tokens` | `TRUNCATED` |
| anything else | `UNKNOWN` |

Missing usage becomes `None`, never zero: a zero that is not known to be zero
would be priced and recorded as a known $0 (closure pass, 18 August 2026).
"""

import time

import anthropic

from val_domain.gateway import Message, ModelConfig, TerminalState
from val_providers.base import ProviderResult, normalize

_STOP_REASONS: dict[str, TerminalState] = {
    "end_turn": TerminalState.COMPLETE,
    "stop_sequence": TerminalState.COMPLETE,
    "refusal": TerminalState.REFUSED,
    "max_tokens": TerminalState.TRUNCATED,
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
        usage = getattr(response, "usage", None)
        return ProviderResult(
            text=text,
            terminal=_STOP_REASONS.get(response.stop_reason or "", TerminalState.UNKNOWN),
            tokens_in=getattr(usage, "input_tokens", None),
            tokens_out=getattr(usage, "output_tokens", None),
            provider_request_id=getattr(response, "_request_id", None),
        )


def measure(start: float) -> int:
    """Elapsed milliseconds, for `model_calls.latency_ms`."""
    return int((time.monotonic() - start) * 1000)
