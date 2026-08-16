"""The normalized provider contract (`01-architecture.md` §5.1).

Every provider speaks a different dialect. Above this line nothing knows that:
one request shape in, one response shape out, and one error contract covering
timeouts, refusals, rate limits, authentication, outages, and data-policy
rejections alike.

`val_providers` is the only package permitted to import a provider SDK, and it
never depends on `val_policy` — routing asks policy, policy never asks a
provider (`01-architecture.md` §3).
"""

from dataclasses import dataclass
from typing import Protocol

from val_domain.gateway import GatewayError, GatewayErrorKind, Message, ModelConfig


@dataclass(frozen=True)
class ProviderResult:
    """What a provider returned, before cost is attributed to it."""

    text: str
    tokens_in: int
    tokens_out: int
    provider_request_id: str | None
    refused: bool


class ProviderAdapter(Protocol):
    """One provider, speaking the normalized contract."""

    name: str

    def complete(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
    ) -> ProviderResult:
        """Run one completion, or raise `GatewayError`."""
        ...


def normalize(error: Exception, provider: str) -> GatewayError:
    """Map any provider exception onto the one error contract.

    Matching is by exception class *name* rather than by importing every SDK's
    exception hierarchy, so this stays one function instead of one per provider
    and does not break when an SDK reorganises its modules. The names below are
    stable across the Anthropic and OpenAI Python SDKs.
    """
    name = type(error).__name__
    kinds = {
        "APITimeoutError": GatewayErrorKind.TIMEOUT,
        "APIConnectionError": GatewayErrorKind.PROVIDER_ERROR,
        "RateLimitError": GatewayErrorKind.RATE_LIMIT,
        "AuthenticationError": GatewayErrorKind.AUTHENTICATION,
        "PermissionDeniedError": GatewayErrorKind.AUTHENTICATION,
        "BadRequestError": GatewayErrorKind.INVALID_REQUEST,
        "UnprocessableEntityError": GatewayErrorKind.INVALID_REQUEST,
        "NotFoundError": GatewayErrorKind.INVALID_REQUEST,
        "InternalServerError": GatewayErrorKind.PROVIDER_ERROR,
        "APIStatusError": GatewayErrorKind.PROVIDER_ERROR,
    }
    kind = kinds.get(name, GatewayErrorKind.PROVIDER_ERROR)
    return GatewayError(kind, f"{provider}: {name}: {str(error)[:300]}")
