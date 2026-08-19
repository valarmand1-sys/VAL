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
documentation, not recalled; each entry carries its own `rates_verified_on`.
Raising a rate means re-reading it the same way and adding a new entry — never
editing one in place, because calls already costed against the old rate must
keep resolving to it.

**The identifier rule — independent-review correction, 18 August 2026.** A
configuration's `model_identifier` is part of its identity, and it must be a
**pinned snapshot**, never a movable alias: an alias the provider can repoint
would let one configuration id serve different models over time, which is the
identifier-shaped version of a record that silently re-prices itself. Correcting
an identifier is therefore the same act as correcting a rate: **retire the old
entry in place and add a new entry with a new UUID.** The first closure pass
edited Haiku's identifier in place under its existing UUID, which broke this
rule; the retired entries below restore it, and the interim rows written during
that window are documented in the closure audit rather than rewritten.
(`claude-opus-5` is itself a pinned dateless snapshot per Anthropic's model-ID
documentation, so it needs no date suffix to satisfy the rule.)
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
_VERIFIED_ON = date(2026, 8, 18)

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
        # A pinned dateless snapshot, per Anthropic's model-ID documentation
        # ("Starting with the Claude 4.6 generation, model IDs use a dateless
        # format that is also a pinned snapshot, not an evergreen pointer") —
        # verified 18 August 2026. No date suffix is needed to satisfy the
        # identifier rule above.
        model_identifier="claude-opus-5",
        display_name="Claude Opus 5",
        context_window_tokens=1_000_000,
        max_output_tokens=128_000,
        # Closure pass, 18 August 2026: `NOT_APPLICABLE` was stale. Per the
        # models overview (platform.claude.com, verified 18 August 2026), Opus 5
        # supports the `effort` parameter, defaulting to `high` on the Claude
        # API. `HIGH` is the level these calls run at, and — independent-review
        # correction — the adapter now SENDS it explicitly rather than trusting
        # the provider default to stay put. Adaptive-thinking tokens bill as
        # output inside `max_tokens`, which the budget's output bound covers.
        reasoning_effort=ReasoningEffort.HIGH,
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
        fallback_slug="haiku-4-5-20251001",
        admission=Admission.PROVISIONALLY_ADMITTED,
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=_ADMITTED_ON,
        rates_verified_on=_VERIFIED_ON,
    ),
    # ------------------------------------------------------------------
    # RETIRED — independent-review correction, 18 August 2026.
    #
    # This is the configuration every pre-closure Haiku call was made under:
    # the movable alias identifier. The first closure pass edited the
    # identifier to the pinned snapshot IN PLACE under this same UUID, which
    # violated the registry's own rule that identity-bearing facts are never
    # edited — historical `model_calls` carrying this id must resolve to what
    # those calls actually used. The alias is restored here and the entry is
    # retired; the pinned successor below has its own UUID. A handful of rows
    # written during the in-place window (the closure smoke) carry this UUID
    # with the pinned identifier denormalised on the row — the row's own copy
    # is the truth of what was sent, and the audit documents the window rather
    # than rewriting it.
    # ------------------------------------------------------------------
    ModelConfig(
        id=UUID("b123b7f1-fc59-4de3-95c1-0a884cd43953"),
        slug="haiku-4-5",
        provider="anthropic",
        model_identifier="claude-haiku-4-5",
        display_name="Claude Haiku 4.5 (alias, retired)",
        context_window_tokens=200_000,
        max_output_tokens=64_000,
        reasoning_effort=ReasoningEffort.NOT_APPLICABLE,
        cost_per_mtok_in_usd=1.00,
        cost_per_mtok_out_usd=5.00,
        caching=PricingFeature.NOT_VERIFIED,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=_PROTECTED,
        known_weaknesses=(),
        # Retired entries take no part in routing; a declared fallback here
        # would be a pointer from history into the live graph.
        fallback_slug=None,
        admission=Admission.PROVISIONALLY_ADMITTED,
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=_ADMITTED_ON,
        rates_verified_on=_VERIFIED_ON,
        retired=True,
        retired_on=date(2026, 8, 18),
    ),
    # The pinned successor. Same model, same rates — a new entry because the
    # exact identifier is identity, and `claude-haiku-4-5` is an alias Anthropic
    # documents as a convenience pointer to this snapshot (verified 18 August
    # 2026, platform.claude.com models overview).
    ModelConfig(
        id=UUID("7c1c3c85-4c2b-49a2-9c46-1d1b41b0a5aa"),
        slug="haiku-4-5-20251001",
        provider="anthropic",
        model_identifier="claude-haiku-4-5-20251001",
        display_name="Claude Haiku 4.5",
        context_window_tokens=200_000,
        max_output_tokens=64_000,
        # Haiku 4.5 has no `effort` parameter (extended thinking exists but is
        # not configured here). NOT_APPLICABLE is the recorded absence, and the
        # adapter sends no effort field for it.
        reasoning_effort=ReasoningEffort.NOT_APPLICABLE,
        cost_per_mtok_in_usd=1.00,
        cost_per_mtok_out_usd=5.00,
        caching=PricingFeature.NOT_VERIFIED,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=_PROTECTED,
        known_weaknesses=(),
        # Cross-provider, so an Anthropic-account outage degrades to OpenAI
        # rather than halting ("Val degrades rather than halts", 00-charter.md).
        # The chain deliberately ENDS at the GPT entry — see its NONE — so the
        # declared graph terminates: opus → haiku → gpt → nothing.
        fallback_slug="gpt-5-5-20260423",
        admission=Admission.PROVISIONALLY_ADMITTED,
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=date(2026, 8, 18),
        rates_verified_on=_VERIFIED_ON,
    ),
    # ------------------------------------------------------------------
    # RETIRED — independent-review correction, 18 August 2026.
    #
    # The configuration every historical GPT-5.5 call was made under: the
    # `gpt-5.5` alias identifier. Retired for the same identifier rule as the
    # Haiku alias above — OpenAI's model page exposes a dated snapshot, and
    # one rule applies to both providers. Operational facts here carry the
    # closure pass's corrections (window, threshold), with the original error
    # recorded: until 18 August 2026 this entry miscoded the 272K pricing
    # threshold as the context window, and calls routed under that mistake
    # were bounded by 272K — a smaller, safe-direction error.
    # ------------------------------------------------------------------
    ModelConfig(
        id=UUID("3b9d25f4-e00c-448a-a4cd-ecdd79380008"),
        slug="gpt-5-5",
        provider="openai",
        model_identifier="gpt-5.5",
        display_name="GPT-5.5 (alias, retired)",
        context_window_tokens=1_050_000,
        max_output_tokens=128_000,
        reasoning_effort=ReasoningEffort.NOT_APPLICABLE,
        cost_per_mtok_in_usd=5.00,
        cost_per_mtok_out_usd=30.00,
        long_context_threshold_tokens=272_000,
        long_context_in_multiplier=2.0,
        long_context_out_multiplier=1.5,
        caching=PricingFeature.NOT_VERIFIED,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=_PROTECTED,
        known_weaknesses=(),
        fallback_slug=None,
        admission=Admission.PROVISIONALLY_ADMITTED,
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=_ADMITTED_ON,
        rates_verified_on=_VERIFIED_ON,
        # The recorded fact as it stood: this route first answered live on
        # 15 August 2026. It kept answering through the WP-0.7 acceptance; the
        # marker was never advanced, and retiring is not a licence to backfill.
        last_live_call_on=date(2026, 8, 15),
        retired=True,
        retired_on=date(2026, 8, 18),
    ),
    # The pinned successor: the dated snapshot the `gpt-5.5` alias currently
    # resolves to (developers.openai.com/api/docs/models/gpt-5.5, verified
    # 18 August 2026 — "Default snapshot: gpt-5.5-2026-04-23").
    ModelConfig(
        id=UUID("9f7de5b2-6f3a-4f6e-8f2a-2b7c9d4e1c55"),
        slug="gpt-5-5-20260423",
        provider="openai",
        model_identifier="gpt-5.5-2026-04-23",
        display_name="GPT-5.5",
        context_window_tokens=1_050_000,
        max_output_tokens=128_000,
        # Independent-review correction, 18 August 2026: GPT-5.5 supports
        # reasoning.effort — "none, low, medium (default), high and xhigh" —
        # so NOT_APPLICABLE was factually false (01-architecture.md §5.2: that
        # value means the provider has no such concept). MEDIUM is the level
        # these calls run at, and the adapter now sends it explicitly.
        reasoning_effort=ReasoningEffort.MEDIUM,
        cost_per_mtok_in_usd=5.00,
        cost_per_mtok_out_usd=30.00,
        # Above 272K input tokens the whole session bills at 2x input and
        # 1.5x output (same page, same date). Read by the budget bound and the
        # settlement through one `effective_rates` function.
        long_context_threshold_tokens=272_000,
        long_context_in_multiplier=2.0,
        long_context_out_multiplier=1.5,
        caching=PricingFeature.NOT_VERIFIED,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=_PROTECTED,
        known_weaknesses=(),
        # Explicit NONE, and the router honours it as none: this is the end of
        # the declared graph. A backward hop to Haiku could never run — Haiku
        # is cheaper, so whenever it is independently eligible, ready and
        # affordable it is already the primary; the only situations in which
        # GPT leads are ones where the Anthropic routes cannot serve at all,
        # and a fallback into them would fail the independent re-check anyway.
        # Declaring it would re-create the cycle the independent review found.
        fallback_slug=None,
        admission=Admission.PROVISIONALLY_ADMITTED,
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=date(2026, 8, 18),
        rates_verified_on=_VERIFIED_ON,
    ),
)


def declared_chain_violations(configs: tuple[ModelConfig, ...]) -> list[str]:
    """Every declared fallback chain must terminate at an explicit NONE.

    *Independent-review correction, 18 August 2026.* The registry carried a real
    declared cycle — haiku ↔ gpt — hidden by two tests whose assertions restated
    their own loop's exit conditions and therefore could not fail. The router's
    seen-set kept the runtime finite, but defensive cycle handling is not
    permission for the registry to declare one: a cycle is a chain that never
    terminates, and "every declared chain terminates" is this registry's own
    stated doctrine.

    Checked here as data validation — called from `startup_violations`, so a
    declared cycle stops the service at boot — and exercised by tests against
    synthetic cyclic and dangling registries, which is what makes the tests
    themselves falsifiable.
    """
    problems: list[str] = []
    by_slug_map = {config.slug: config for config in configs}

    for start_config in configs:
        walked: list[str] = [start_config.slug]
        current = start_config
        while current.fallback_slug is not None:
            successor = by_slug_map.get(current.fallback_slug)
            if successor is None:
                problems.append(
                    f"{current.slug} declares fallback {current.fallback_slug!r}, "
                    "which names no entry"
                )
                break
            if successor.slug in walked:
                cycle = " -> ".join([*walked, successor.slug])
                problems.append(
                    f"declared fallback cycle: {cycle}. A chain that revisits an "
                    "entry never terminates; declare NONE where the chain ends."
                )
                break
            walked.append(successor.slug)
            current = successor
    return problems


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
