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


#: An account that cannot pay is not a malformed request — corrected 17 August 2026.
#:
#: **Observed, not assumed.** Anthropic returns *"Your credit balance is too low
#: to access the Anthropic API"* as an HTTP **400**, which the SDK raises as
#: `BadRequestError` (request `req_011Ce8xDp7bfjRu5BgXqNuXx`, 17 August 2026).
#: Mapping that to `INVALID_REQUEST` was wrong in a way that only showed up under
#: a real call: `INVALID_REQUEST` is deliberately **not** retryable, on the sound
#: reasoning that a malformed request is malformed everywhere. But a billing
#: failure is a property of the *route*, not of the request — the identical
#: request succeeds on another provider — so the router refused to fall back and
#: the whole conversation failed while a working route sat unused.
#:
#: It normalises to `PROVIDER_ERROR`: from the caller's side this route cannot
#: serve, which is what an outage is, and `PROVIDER_ERROR` is retryable so the
#: fallback does its job. Matched on the message because the provider offers no
#: other signal — a narrow, documented sniff, applied only to the status classes
#: that could plausibly carry it.
_ACCOUNT_CANNOT_PAY = ("credit balance is too low", "billing", "quota", "insufficient_quota")

_UNPAYABLE_CLASSES = frozenset(
    {"BadRequestError", "PermissionDeniedError", "APIStatusError", "RateLimitError"}
)


def _is_account_problem(name: str, message: str) -> bool:
    """Whether this failure is the account's, rather than the request's."""
    if name not in _UNPAYABLE_CLASSES:
        return False
    lowered = message.lower()
    return any(signal in lowered for signal in _ACCOUNT_CANNOT_PAY)


def normalize(error: Exception, provider: str) -> GatewayError:
    """Map any provider exception onto the one error contract.

    Matching is by exception class *name* rather than by importing every SDK's
    exception hierarchy, so this stays one function instead of one per provider
    and does not break when an SDK reorganises its modules. The names below are
    stable across the Anthropic and OpenAI Python SDKs.

    One message-level exception is layered over that, for the case where the
    status code lies about what went wrong — see `_ACCOUNT_CANNOT_PAY`.
    """
    name = type(error).__name__
    message = str(error)

    if _is_account_problem(name, message):
        return GatewayError(
            GatewayErrorKind.PROVIDER_ERROR,
            f"{provider}: the account cannot currently be billed for this call, so this "
            f"route is unusable — not the request. {name}: {message[:250]}",
        )

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
    return GatewayError(kind, f"{provider}: {name}: {message[:300]}")
