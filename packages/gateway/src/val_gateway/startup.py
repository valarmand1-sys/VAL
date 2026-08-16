"""Assembling the gateway at startup, and refusing to start when it must.

Two things happen here, in this order:

1. **Eligibility is enforced before anything else.** A configured route that is
   not Protected-eligible, a provider with no ruling, an unverified Gemini key —
   any of these stops the service. A check that only fires when the call is made
   is not the guarantee `04-layer-0.md` §1.1 claims, and by then Protected
   content has already left the house.
2. **Adapters are built from the environment.** Keys are read from
   `VAL_ANTHROPIC_API_KEY` and `VAL_OPENAI_API_KEY`, never from a literal and
   never from the registry — the registry is committed, and a committed key is a
   leaked key.

A provider that has a configured route but no key also stops startup. Silently
running with one provider when two are configured would make "swapping the
configured provider requires no change outside configuration" untrue in exactly
the way that is hardest to notice.
"""

import os
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine

from val_domain.registry import active
from val_gateway.gateway import Gateway, check_startup
from val_gateway.persistence import month_to_date_spend, record_call
from val_providers.anthropic_adapter import AnthropicAdapter
from val_providers.base import ProviderAdapter
from val_providers.openai_adapter import OpenAIAdapter

#: Where each provider's key is read from. A provider absent from this mapping
#: has no adapter and cannot be configured.
KEY_VARIABLES = {
    "anthropic": "VAL_ANTHROPIC_API_KEY",
    "openai": "VAL_OPENAI_API_KEY",
    "google": "VAL_GOOGLE_API_KEY",
}


class StartupRefusedError(Exception):
    """Startup may not proceed. Carries every reason, not just the first."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


@dataclass(frozen=True)
class Startup:
    """A started gateway, and the warnings that did not stop it."""

    gateway: Gateway
    warnings: list[str]


def build_adapters(providers: set[str]) -> tuple[dict[str, ProviderAdapter], list[str]]:
    """One adapter per configured provider, plus any reason startup must stop."""
    adapters: dict[str, ProviderAdapter] = {}
    problems: list[str] = []

    for provider in sorted(providers):
        variable = KEY_VARIABLES.get(provider)
        if variable is None:
            problems.append(f"{provider}: no adapter exists for this provider")
            continue
        key = os.environ.get(variable, "")
        if not key:
            problems.append(
                f"{provider}: a route is configured but {variable} is not set. "
                "Running with the route silently missing would make provider "
                "substitution untrue where it is hardest to notice."
            )
            continue
        if provider == "anthropic":
            adapters[provider] = AnthropicAdapter(key)
        elif provider == "openai":
            adapters[provider] = OpenAIAdapter(key)
        else:
            # Gemini is eligible only on verified paid billing, and the verifier
            # fails closed (01-architecture.md §5.4). Reached only if a Gemini
            # route is added to the registry, which startup would already refuse.
            problems.append(f"{provider}: no adapter is wired for this provider")

    return adapters, problems


def start(engine: Engine, today: datetime | None = None) -> Startup:
    """Build the gateway, or refuse to start and say why."""
    moment = today or datetime.now(UTC)
    violations, warnings = check_startup(moment.date())

    adapters, problems = build_adapters({config.provider for config in active()})
    violations.extend(problems)

    if violations:
        raise StartupRefusedError(violations)

    gateway = Gateway(
        adapters=adapters,
        recorder=lambda record: record_call(engine, record),
        month_to_date_spend=lambda: month_to_date_spend(engine),
    )
    return Startup(gateway=gateway, warnings=warnings)
