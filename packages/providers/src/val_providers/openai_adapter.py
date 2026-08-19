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

Missing usage becomes `None`, never zero. The previous `usage.input_tokens if
usage else 0` fabricated a known $0 for exactly the calls whose cost was not
known, which is the defect the WP-0.4 cost doctrine exists to prevent.
"""

from typing import Literal

import openai
from openai.types.shared_params import Reasoning

from val_domain.gateway import (
    GatewayError,
    GatewayErrorKind,
    Message,
    ModelConfig,
    ReasoningEffort,
    TerminalState,
)
from val_providers.base import ProviderResult, normalize

#: Provider-neutral levels in the SDK's literal vocabulary; explicit so an
#: unaccepted registry level fails loudly at call time rather than as a 400.
_EFFORT: dict[ReasoningEffort, Literal["minimal", "low", "medium", "high"]] = {
    ReasoningEffort.MINIMAL: "minimal",
    ReasoningEffort.LOW: "low",
    ReasoningEffort.MEDIUM: "medium",
    ReasoningEffort.HIGH: "high",
}


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
                # Independent-review correction, 18 August 2026: the registry's
                # declared effort is SENT, not assumed. GPT-5.5 documents
                # reasoning.effort with medium as the default; the configured
                # MEDIUM is stated on every request so a provider-side default
                # change cannot silently alter a versioned configuration.
                reasoning=(
                    openai.omit
                    if config.reasoning_effort is ReasoningEffort.NOT_APPLICABLE
                    else Reasoning(effort=_EFFORT[config.reasoning_effort])
                ),
            )
        except Exception as error:
            raise normalize(error, self.name) from error

        if response.status == "failed":
            # The response object arrived but reports its own failure. This is a
            # provider failure wearing a 200, and it is raised as one.
            failure = getattr(response, "error", None)
            raise GatewayError(
                GatewayErrorKind.PROVIDER_ERROR,
                f"{self.name}: response {response.id} reports status 'failed': "
                f"{getattr(failure, 'message', failure)}",
            )

        refusal = _refusal_text(response)
        if response.status == "completed":
            terminal = TerminalState.REFUSED if refusal else TerminalState.COMPLETE
        elif response.status == "incomplete":
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

        usage = response.usage
        return ProviderResult(
            text=refusal if refusal is not None else (response.output_text or ""),
            terminal=terminal,
            tokens_in=usage.input_tokens if usage else None,
            tokens_out=usage.output_tokens if usage else None,
            provider_request_id=response.id,
        )
