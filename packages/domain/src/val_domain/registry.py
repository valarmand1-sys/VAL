"""The Model Configuration Registry (`01-architecture.md` §5.2).

A model configuration is a versioned record, not a model name in a settings
file. Each entry carries a stable `id` — the UUID `model_calls.model_config_id`
refers to — and a stable `slug`, the human-readable name every cost view
displays. Both are permanent: a retired configuration keeps its row in history,
so **an entry is never deleted, only marked retired.** Deleting one would orphan
every `model_calls` row that points at it.

**Why this is code and not a table.** `04-layer-0.md` §2 enumerates seven tables
and states that no table exists which §2 does not name, while `01-architecture.md`
§5.2 requires configurations to be versioned records. Both hold if the registry
is a typed, versioned artifact in the repository rather than an eighth table:
`model_calls` stores the UUID with no foreign key, and denormalises `provider`
and `model_identifier` alongside it — which §2.2 already required precisely so a
retired configuration still resolves historically. This reading is recorded here
rather than left to be rediscovered.

**Rates are per million tokens, as published by the provider**, and are the rates
`model_calls.cost` is computed from at call time. Stored, never recomputed:
provider pricing changes, and a historical record that silently re-prices itself
is not a record.

Every rate and model identifier below was read from the provider's own
documentation on 15 August 2026, not recalled. Raising a rate means re-reading
it the same way and adding a new entry — never editing one in place, because
calls already costed against the old rate must keep resolving to it.
"""

from datetime import date, timedelta
from uuid import UUID

from val_domain.gateway import (
    AdapterStatus,
    Admission,
    Classification,
    ModelConfig,
    PricingFeature,
    ReasoningEffort,
)

#: Every route is Protected-eligible, which is what makes Layer 0's structural
#: guarantee hold: there is no ineligible route to misdirect content to
#: (`04-layer-0.md` §1.1). Restricted is absent deliberately — it routes to local
#: inference only, which does not exist until Layer 1.
_PROTECTED = frozenset({Classification.PUBLIC, Classification.INTERNAL, Classification.PROTECTED})

#: The day every rate below was read from the provider's own documentation.
#: A new rate means a new entry stamped with a new date, never an edit in place —
#: calls already costed against the old rate must keep resolving to it.
_VERIFIED_ON = date(2026, 8, 15)

#: Past this, a rate is old enough that cost attribution may be quietly wrong.
#: A warning, deliberately, not a failure: stale rates degrade a record, they do
#: not make the system unsafe to run, and a startup that refuses to boot over a
#: 91-day-old price is a worse outcome than one that says so plainly.
RATE_STALENESS_WARNING = timedelta(days=90)

#: The day these three routes were admitted for Layer 0 use. Admission is
#: `PROVISIONALLY_ADMITTED`, never `QUALIFIED`: formal qualification is the exam
#: suite of `01-architecture.md` §5.2.1, which is built at Layers 2-3 and does
#: not exist. Claiming the stronger word here would assert a record nobody holds.
_ADMITTED_ON = date(2026, 8, 15)

REGISTRY: tuple[ModelConfig, ...] = (
    ModelConfig(
        id=UUID("4e38c060-3b9a-495d-bc54-73acd1530cd5"),
        slug="opus-5",
        provider="anthropic",
        model_identifier="claude-opus-5",
        display_name="Claude Opus 5",
        context_window_tokens=1_000_000,
        max_output_tokens=128_000,
        reasoning_effort=ReasoningEffort.NOT_APPLICABLE,
        cost_per_mtok_in_usd=5.00,
        cost_per_mtok_out_usd=25.00,
        caching=PricingFeature.NOT_VERIFIED,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=_PROTECTED,
        # Nothing observed in this house's own use. Left empty rather than filled
        # from a benchmark or a provider's own copy.
        known_weaknesses=(),
        # The cheaper Anthropic route. Both are on the same account, so this
        # fallback does not survive an account-level failure — which is exactly
        # what the credit blocker of WP-0.4 is, and why it is written down here.
        fallback_slug="haiku-4-5",
        admission=Admission.PROVISIONALLY_ADMITTED,
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=_ADMITTED_ON,
        rates_verified_on=_VERIFIED_ON,
    ),
    ModelConfig(
        id=UUID("b123b7f1-fc59-4de3-95c1-0a884cd43953"),
        slug="haiku-4-5",
        provider="anthropic",
        model_identifier="claude-haiku-4-5",
        display_name="Claude Haiku 4.5",
        context_window_tokens=200_000,
        max_output_tokens=64_000,
        reasoning_effort=ReasoningEffort.NOT_APPLICABLE,
        cost_per_mtok_in_usd=1.00,
        cost_per_mtok_out_usd=5.00,
        caching=PricingFeature.NOT_VERIFIED,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=_PROTECTED,
        known_weaknesses=(),
        # Explicit NONE. The cheapest route has nothing cheaper to fall back to,
        # and falling *up* to a frontier model on failure would spend more money
        # in response to an outage, which is the wrong reflex.
        fallback_slug=None,
        admission=Admission.PROVISIONALLY_ADMITTED,
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=_ADMITTED_ON,
        rates_verified_on=_VERIFIED_ON,
    ),
    ModelConfig(
        id=UUID("3b9d25f4-e00c-448a-a4cd-ecdd79380008"),
        slug="gpt-5-5",
        provider="openai",
        model_identifier="gpt-5.5",
        display_name="GPT-5.5",
        context_window_tokens=272_000,
        max_output_tokens=128_000,
        reasoning_effort=ReasoningEffort.NOT_APPLICABLE,
        cost_per_mtok_in_usd=5.00,
        cost_per_mtok_out_usd=30.00,
        caching=PricingFeature.NOT_VERIFIED,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=_PROTECTED,
        known_weaknesses=(),
        # A different provider, so this fallback survives an Anthropic-account
        # failure in a way `opus-5 → haiku-4-5` does not.
        fallback_slug="haiku-4-5",
        admission=Admission.PROVISIONALLY_ADMITTED,
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=_ADMITTED_ON,
        rates_verified_on=_VERIFIED_ON,
        # Answered a real call on 15 August 2026: 37 tokens in, 24 out, $0.000905.
        last_live_call_on=date(2026, 8, 15),
    ),
)


def active() -> tuple[ModelConfig, ...]:
    """Configurations available for routing."""
    return tuple(config for config in REGISTRY if not config.retired)


def by_id(config_id: UUID) -> ModelConfig | None:
    """Resolve a `model_calls.model_config_id`, retired entries included.

    History must resolve even when the configuration is no longer routable,
    which is the whole reason entries are retired rather than removed.
    """
    return next((config for config in REGISTRY if config.id == config_id), None)


def by_slug(slug: str) -> ModelConfig | None:
    """Resolve the human-readable name, retired entries included."""
    return next((config for config in REGISTRY if config.slug == slug), None)


def cheapest() -> ModelConfig:
    """The least expensive active route.

    `04-layer-0.md` §4 runs the preference-strip step here until local inference
    arrives at Layer 1. Choosing on cost is permissible only because every
    configured route is Protected-eligible by construction — the set contains no
    ineligible option to be tempted by (§1.1).
    """
    return min(active(), key=lambda config: config.cost_per_mtok_in_usd)


def fallback_for(config: ModelConfig) -> ModelConfig | None:
    """The successor this configuration declares, resolved, or None.

    Resolution only. **This says nothing about whether the fallback may be
    used** — admission, eligibility, readiness, and budget are all re-checked
    against it independently by the router, because a fallback is never
    inherited (`01-architecture.md` §5.4). A declared slug that resolves to
    nothing returns None rather than raising: the registry is a typed artifact
    and `test_registry.py` fails on a dangling reference long before startup.
    """
    if config.fallback_slug is None:
        return None
    return by_slug(config.fallback_slug)


def live_routes() -> tuple[ModelConfig, ...]:
    """Active routes that have actually answered a call.

    An adapter existing is not evidence (`01-architecture.md` §5.2.1). The two
    Anthropic routes are enabled, eligible, and adapted, and are **not** live:
    the account reports insufficient credit, so neither has ever answered.
    """
    return tuple(config for config in active() if config.last_live_call_on is not None)


def unproven_routes() -> tuple[ModelConfig, ...]:
    """Active routes that have never answered a call. Enabled is not proven."""
    return tuple(config for config in active() if config.last_live_call_on is None)


def stale_rates(today: date) -> list[str]:
    """Entries whose rates are older than the staleness window, as warnings.

    Returned rather than logged so the caller decides where they surface, and so
    this stays a pure function testable without a clock.
    """
    warnings: list[str] = []
    for config in active():
        age = today - config.rates_verified_on
        if age > RATE_STALENESS_WARNING:
            warnings.append(
                f"{config.slug}: rates last verified {config.rates_verified_on.isoformat()}, "
                f"{age.days} days ago. Re-read {config.provider}'s published pricing and add "
                "a new entry; cost attribution is only as good as this date."
            )
    return warnings
