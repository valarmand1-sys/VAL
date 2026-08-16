"""The OpenAI adapter.

Uses the Responses API, which is OpenAI's primary surface: `responses.create`
takes `input` and `instructions`, and returns `output_text` with token counts on
`usage.input_tokens` / `usage.output_tokens` — the same two numbers Anthropic
reports, which is why the normalized contract can carry both without a per-
provider shape.
"""

import openai

from val_domain.gateway import Message, ModelConfig
from val_providers.base import ProviderResult, normalize


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
    ) -> ProviderResult:
        """Run one completion, or raise the normalized error."""
        turns: list[openai.types.responses.EasyInputMessageParam] = [
            {"role": "user" if m.role == "user" else "assistant", "content": m.content}
            for m in messages
        ]
        try:
            response = self._client.responses.create(
                model=config.model_identifier,
                input=list(turns),
                max_output_tokens=max_output_tokens,
                instructions=system,
            )
        except Exception as error:
            raise normalize(error, self.name) from error

        usage = response.usage
        return ProviderResult(
            text=response.output_text or "",
            tokens_in=usage.input_tokens if usage else 0,
            tokens_out=usage.output_tokens if usage else 0,
            provider_request_id=response.id,
            refused=response.status == "incomplete",
        )
