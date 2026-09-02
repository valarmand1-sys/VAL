"""Deterministic eligibility evaluation (`01-architecture.md` §5.4).

Pure functions over domain types. No network, no database, no provider — this
package must stay callable and testable with no application running
(`01-architecture.md` §3). Startup runs `startup_violations` and refuses to
start on any finding; the gateway runs `refusal_for` before every call.

The provider rulings of 15 August 2026 are encoded here because they are policy,
and policy evaluation is this package's charter. Changing a ruling is a decision
by Lord Armand, applied to `01-architecture.md` §5.4 first and reflected here
second — never the other way around.
"""

from val_domain.gateway import Classification, GatewayErrorKind, ModelConfig
from val_domain.registry import declared_chain_violations

#: Providers ruled Protected-eligible on 15 August 2026, with the grounds
#: recorded in 01-architecture.md §5.4. Google's eligibility is conditional and
#: carries the structural billing check below.
#:
#: **Bound maintenance (ruled 1 September 2026):** admitting a new CLOUD
#: provider here also updates `CLOUD_PROVIDERS` in
#: `infrastructure/ci/check_scope_ruling.py` in the same commit — that roster
#: is how the strip-routing deviation's expiry (04-layer-0.md §4) tells a
#: local route from a new cloud one, and an unlisted cloud provider fires a
#: false red demanding the deviation move.
RULED_PROVIDERS = frozenset({"anthropic", "openai", "google"})

#: Excluded pending verification, not permanently: unverifiable terms as of
#: July 2026. A US-hosted SOC 2 / ZDR route or self-hosting can qualify later on
#: its own merits, by a new ruling.
EXCLUDED_PENDING_VERIFICATION = frozenset({"zhipu", "z-ai", "glm"})


def startup_violations(configs: list[ModelConfig]) -> list[str]:
    """Everything that must stop the service from starting.

    Eligibility is enforced at startup, not at call time (`04-layer-0.md`
    WP-0.4): a check that only fires when the call is made is not the structural
    guarantee §1.1 claims. An empty list means startup may proceed.
    """
    violations: list[str] = []

    active = [config for config in configs if not config.retired]
    if not active:
        violations.append("no active model configuration exists; the gateway has no route")

    # Independent-review correction, 18 August 2026: a declared fallback cycle
    # is registry data that contradicts the registry's own doctrine, and the
    # router's defensive seen-set must never be the only thing standing between
    # a mis-declaration and an infinite chain. Validated at boot, over the
    # active graph the router will actually walk.
    violations.extend(declared_chain_violations(tuple(active)))

    for config in active:
        name = f"{config.slug} ({config.provider}/{config.model_identifier})"

        if config.provider in EXCLUDED_PENDING_VERIFICATION:
            violations.append(
                f"{name}: provider is excluded pending verification "
                "(01-architecture.md §5.4 — unverifiable terms as of July 2026)"
            )
            continue

        if config.provider not in RULED_PROVIDERS:
            violations.append(
                f"{name}: provider has no eligibility ruling by Lord Armand; "
                "no ruling means not eligible (00-charter.md invariant 17)"
            )
            continue

        if Classification.PROTECTED not in config.eligible_classifications:
            violations.append(
                f"{name}: not declared Protected-eligible. At Layer 0 every "
                "configured route must be, so that eligibility holds by "
                "construction (04-layer-0.md §1.1)"
            )

        if Classification.RESTRICTED in config.eligible_classifications:
            violations.append(
                f"{name}: declares Restricted eligibility, but Restricted content "
                "routes to local inference only, which does not exist until "
                "Layer 1 (01-architecture.md §5.4)"
            )

        if config.provider == "google" and not config.billing_verified:
            violations.append(
                f"{name}: Gemini is Protected-eligible only with verified paid "
                "billing, and this key's billing is not verified. A billed and an "
                "unbilled key are indistinguishable in code, so startup fails "
                "rather than trusting configuration (§5.4 amendment, 15 Aug 2026)"
            )

    return violations


def refusal_for(
    classification: Classification, config: ModelConfig
) -> tuple[GatewayErrorKind, str] | None:
    """Why this content may not go to this route, or None if it may.

    At Layer 0 the startup check makes the eligibility branch unreachable in a
    correctly started service — every configured route is Protected-eligible by
    construction. It is checked anyway: defence in depth costs one set lookup,
    and the structural guarantee dissolves at Layer 2 when tools pull in mixed
    content.
    """
    if classification is Classification.RESTRICTED:
        return (
            GatewayErrorKind.RESTRICTED_CONTENT,
            "Restricted content routes to local inference only, which does not "
            "exist until Layer 1. It is refused, not reclassified (04-layer-0.md §1.1).",
        )
    if classification not in config.eligible_classifications:
        return (
            GatewayErrorKind.NOT_ELIGIBLE,
            f"route {config.slug} is not declared eligible for "
            f"{classification.value} content (00-charter.md invariant 17)",
        )
    return None
