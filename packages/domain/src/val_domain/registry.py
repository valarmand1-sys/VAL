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
    CapabilityProfile,
    Classification,
    Hosting,
    Metering,
    ModelConfig,
    PricingFeature,
    QualificationTarget,
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
        # Ruling, 8 September 2026. Read from platform.claude.com/docs/en/about-claude/
        # pricing on that date: 5m write $6.25 (1.25x), 1h write $10 (2x), cache
        # hit $0.50 (0.1x); minimum cacheable prefix 512 tokens on Claude Opus 5
        # (prompt-caching page, same date). Caches are isolated per organization
        # and workspace; under the retention page, prompts and outputs are not
        # stored — KV representations and hashes are held in memory for the TTL.
        caching=PricingFeature.AVAILABLE,
        cache_write_5m_per_mtok_in_usd=6.25,
        cache_write_1h_per_mtok_in_usd=10.00,
        cache_read_per_mtok_in_usd=0.50,
        cache_minimum_prefix_tokens=512,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=_PROTECTED,
        # Ruling, 7 September 2026: the provisionally approved sole partner-quality
        # route — an implementation bridge for the ruled quality floor, not a
        # declaration that this model is uniquely or permanently correct for Val.
        # A profile is a floor, not a ceiling: a partner-qualified route also
        # satisfies structured work (schema-constrained output is supported on
        # it), and cost ordering among qualified routes is what keeps structured
        # work off it in practice — never a declaration that it cannot.
        capability_profiles=frozenset({CapabilityProfile.PARTNER, CapabilityProfile.STRUCTURED}),
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
        # Ruling, 10 September 2026 (`01-architecture.md` §5.2, closing the
        # qualification repair loop): the dormant incumbent. Formally NOT MET
        # on packet v1.5 (three item-4 failures, one of them unsupported
        # continuity; no zero-tolerance failure); not run under v1.6. Retired
        # from routing so that partner traffic resolves deterministically to
        # the configuration in operational service below — the same model at
        # `high` and `medium` price identically, and two partner-eligible
        # entries would tie on cost. Identity and history untouched: every
        # `model_calls` row carrying this id still resolves to what it used.
        # Returning it to service is a ruling, not an edit.
        retired=True,
        retired_on=date(2026, 9, 10),
    ),
    ModelConfig(
        id=UUID("6c2e7a19-5d3b-4f8e-9a71-2b4c8d0e1f53"),
        slug="opus-5-medium",
        provider="anthropic",
        model_identifier="claude-opus-5",
        display_name="Claude Opus 5 (medium effort)",
        context_window_tokens=1_000_000,
        max_output_tokens=128_000,
        # The exact configuration adjudicated on packet v1.6 (10 September
        # 2026): `opus-5 / medium / adaptive`, persona v1.4 (`personas`
        # revision 3), the record-state contract in place. Effort is part of
        # the configuration's identity (ruling, 8 September 2026), so this is
        # its own entry with its own id, never an edit of `opus-5`.
        reasoning_effort=ReasoningEffort.MEDIUM,
        # Same model, same published rates and cache rates as `opus-5` above
        # (verified 18 August and 8 September 2026); effort does not change
        # price. Re-affirmed against the same pages on registration.
        cost_per_mtok_in_usd=5.00,
        cost_per_mtok_out_usd=25.00,
        caching=PricingFeature.AVAILABLE,
        cache_write_5m_per_mtok_in_usd=6.25,
        cache_write_1h_per_mtok_in_usd=10.00,
        cache_read_per_mtok_in_usd=0.50,
        cache_minimum_prefix_tokens=512,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=_PROTECTED,
        capability_profiles=frozenset({CapabilityProfile.PARTNER, CapabilityProfile.STRUCTURED}),
        # Observed on the v1.5 and v1.6 packets under persona v1.4 and in the
        # record-state regression: when completing a drafted artifact (a note)
        # it may insert an unsupported particular — a count the prompt did not
        # supply. Not observed on non-drafting tasks (specificity probe, 12 of
        # 12 asked for the missing fact). Open problem OP-5.
        known_weaknesses=(
            "drafted artifacts: may insert an unsupported particular (a count) while "
            "completing the form of a sendable note — OP-5",
        ),
        fallback_slug="haiku-4-5-20251001",
        # Formal qualification status: NOT MET (packet v1.6, 10 September 2026;
        # O1 bounded quality, O4 one residual integrity defect). `QUALIFIED` is
        # not set and nothing here implies it.
        admission=Admission.PROVISIONALLY_ADMITTED,
        # Operational status, recorded separately and never collapsed with the
        # line above.
        owner_authorization=(
            "OWNER-AUTHORISED OPERATIONAL EXCEPTION, Lord Armand, 10 September 2026: "
            "authorised for substantive operational use with ONE known residual "
            "integrity defect (v1.6 O4, unsupported count in a drafted artifact; "
            "closure condition in OP-5). Formal qualification status NOT MET."
        ),
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=date(2026, 9, 10),
        rates_verified_on=date(2026, 9, 10),
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
        # Ruling, 8 September 2026, same pages: 5m write $1.25, 1h write $2, hit
        # $0.10; minimum cacheable prefix 4,096 tokens on Claude Haiku 4.5 —
        # which no Layer 0 call on this route reaches (the classifier's and the
        # strip's system prompts are a few hundred tokens), so nothing caches
        # here in practice and nothing is reserved for it (the gateway requests
        # caching only when the stable prefix meets the minimum).
        caching=PricingFeature.AVAILABLE,
        cache_write_5m_per_mtok_in_usd=1.25,
        cache_write_1h_per_mtok_in_usd=2.00,
        cache_read_per_mtok_in_usd=0.10,
        cache_minimum_prefix_tokens=4096,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=_PROTECTED,
        # Ruling, 7 September 2026: structured, schema-constrained internal work
        # only. Not partner-qualified; qualification is a separate ruling.
        capability_profiles=frozenset({CapabilityProfile.STRUCTURED}),
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
    ModelConfig(
        # Registered 9 September 2026, to the extent the ruling requires:
        # exercising the frozen strip conformance suite through the real
        # gateway and, on passing, serving the strip task. It declares the
        # `strip` profile only — nothing here admits it to classification,
        # titling, conversation, or the partner blind and response calls.
        id=UUID("4f9c0d2e-1b7a-4c8e-9a3d-6e2f5b8c1d70"),
        slug="sonnet-5",
        provider="anthropic",
        model_identifier="claude-sonnet-5",
        display_name="Claude Sonnet 5 (strip conformance candidate)",
        context_window_tokens=1_000_000,
        max_output_tokens=128_000,
        # Effort is supported on Sonnet 5 (default `high` per the models
        # overview, 8 September 2026); the configuration states it explicitly.
        reasoning_effort=ReasoningEffort.HIGH,
        # platform.claude.com/docs/en/about-claude/pricing, read 8 September
        # 2026: $2 in, $10 out; 5m write $2.50, 1h write $4, hit $0.20; the
        # $2/$10 made standard on 10 August 2026. Minimum cacheable prefix
        # 1,024 tokens (prompt-caching page, same date).
        cost_per_mtok_in_usd=2.00,
        cost_per_mtok_out_usd=10.00,
        caching=PricingFeature.AVAILABLE,
        cache_write_5m_per_mtok_in_usd=2.50,
        cache_write_1h_per_mtok_in_usd=4.00,
        cache_read_per_mtok_in_usd=0.20,
        cache_minimum_prefix_tokens=1024,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=_PROTECTED,
        # `STRIP` designated 9 September 2026 on the frozen conformance suite
        # v2 through the real gateway with the strip invariant: 110 of 112
        # conformant, zero blocking, zero false contamination on separable
        # cases, zero invalid attempts; on 2 of 8 runs the genuinely
        # inseparable case was returned as "no preference" (an ordinary turn,
        # never an enforced row) — recorded as an operational finding.
        # `STRIP` REMOVED 11 September 2026 (ruling: strip route designation)
        # so routing cannot tie with `sonnet-5-low`, the designated route at
        # the same rates. The v2 result and the 10 September truncation
        # history below are preserved as historical evidence, not rewritten.
        # The entry stays admitted and active with no profile: routing never
        # selects it, and its `model_calls` history resolves.
        capability_profiles=frozenset(),
        known_weaknesses=(
            "strip: on the frozen suite's inseparable case (S7) returned "
            "preference_present=false on 2 of 8 runs (9 September 2026)",
            "strip: on a 1,269-character correction quoting Val (live turn 18:25, "
            "10 September 2026) ran to the 4,096-token output ceiling twice — thinking "
            "at effort high consumed the ceiling; 40 s and $0.044 per attempt. "
            "Sonnet 5 at medium and low did not truncate on the same shape "
            "(strip-conformance/v3/screen-2026-09-10.md)",
        ),
        # The other designated strip route, re-checked independently when
        # reached; chosen by total cost among the strip-eligible otherwise.
        fallback_slug="gpt-5-5-20260423",
        admission=Admission.PROVISIONALLY_ADMITTED,
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=date(2026, 9, 9),
        # Re-read on the activation date: the pricing page is unchanged from
        # 8 September (the $2/$10 standard-price note stands).
        rates_verified_on=date(2026, 9, 9),
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
        # Ruling, 7 September 2026: structured, schema-constrained internal work
        # only. Not partner-qualified; qualification is a separate ruling.
        capability_profiles=frozenset({CapabilityProfile.STRUCTURED}),
        # 9 September 2026: removed from strip eligibility on the designation
        # of demonstrated successors (`sonnet-5`, `gpt-5-5-20260423`). Its
        # conformance record on the frozen suite — 35 of 112, 27 false
        # contaminations, 50 blocking, neutral instructions removed — is the
        # reason the strip floor exists. Structured work (classification,
        # titling) continues here until separately evaluated (OP-4).
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
        # Ruling, 7 September 2026: structured, schema-constrained internal work
        # only. Not partner-qualified; qualification is a separate ruling.
        capability_profiles=frozenset({CapabilityProfile.STRUCTURED}),
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
        # Ruling, 7 September 2026: structured, schema-constrained internal work
        # only. Not partner-qualified; qualification is a separate ruling.
        capability_profiles=frozenset({CapabilityProfile.STRUCTURED, CapabilityProfile.STRIP}),
        # `STRIP` designated 9 September 2026 on the frozen conformance suite
        # v2 through the real gateway with the strip invariant: 112 of 112
        # conformant, no false contamination, no invalid attempt. Strip only —
        # nothing here widens this entry beyond structured work and the strip.
        # 10 September 2026: no longer in OpenAI's model catalogue (superseded by
        # the GPT-5.6 family; still served and priced; no retirement entry).
        known_weaknesses=(
            "strip: on the v3 screening cases S15/S16 (a ~1,300-character correction "
            "quoting Val) ended truncated at the 4,096-token output ceiling on 3 of 4 "
            "calls at effort medium — ~44 s and $0.127 per call — and on the one "
            "completed call removed the correction itself as an attributed prior "
            "(10 September 2026, strip-conformance/v3/screen-2026-09-10.md). The "
            "112 of 112 on suite v2 (longest case 289 characters) stands as history.",
        ),
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
    # ------------------------------------------------------------------
    # EVALUATION ONLY — ruling, 10 September 2026 (strip cost/latency
    # correction). Candidates for the strip floor after the registered strip
    # route (`sonnet-5`, effort high) ran to its output ceiling twice on a
    # long correction. Each is `NOT_ADMITTED` and declares NO capability
    # profile: routing can never select it, the pinned path refuses it for
    # the floor, and it is reachable only through the gateway's evaluation
    # door for schema-constrained structured work. Designation — a profile
    # and admission — is a separate recorded ruling on the frozen suite v3.
    ModelConfig(
        id=UUID("2bb9a3e1-cd79-46d1-a4da-1ad8169cae79"),
        slug="sonnet-5-medium",
        provider="anthropic",
        model_identifier="claude-sonnet-5",
        display_name="Claude Sonnet 5 at medium effort (strip candidate, evaluation only)",
        context_window_tokens=1_000_000,
        max_output_tokens=128_000,
        # Effort is part of the configuration's identity (8 September 2026),
        # so a different level is a different entry. Rates as `sonnet-5`.
        reasoning_effort=ReasoningEffort.MEDIUM,
        cost_per_mtok_in_usd=2.00,
        cost_per_mtok_out_usd=10.00,
        caching=PricingFeature.AVAILABLE,
        cache_write_5m_per_mtok_in_usd=2.50,
        cache_write_1h_per_mtok_in_usd=4.00,
        cache_read_per_mtok_in_usd=0.20,
        cache_minimum_prefix_tokens=1024,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=_PROTECTED,
        capability_profiles=frozenset(),
        known_weaknesses=(),
        fallback_slug=None,
        admission=Admission.NOT_ADMITTED,
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=date(2026, 9, 10),
        # Pricing page re-read 10 September 2026: unchanged from 9 September.
        rates_verified_on=date(2026, 9, 10),
    ),
    ModelConfig(
        # DESIGNATED for the strip — owner-authorised operational designation,
        # Lord Armand, 11 September 2026, with a recorded residual finding.
        # Registered 10 September for evaluation only; screened and run on the
        # full frozen suite v4 through the evaluation door on 11 September
        # (strip-conformance/v4/results-2026-09-11.md): 134 of 136, no
        # preference or substantive-prior leakage into any enforced blind
        # payload, every observed failure failing away from false
        # independence, no truncation at low effort, median 2.6 s, maximum
        # 11.5 s, $0.3881 for the suite. The result is preserved exactly as
        # measured; the designation does not declare that frozen v4 formally
        # passed (see `owner_authorization`).
        id=UUID("4100931c-c408-4819-83f9-63c019287866"),
        slug="sonnet-5-low",
        provider="anthropic",
        model_identifier="claude-sonnet-5",
        display_name="Claude Sonnet 5 at low effort (strip route)",
        context_window_tokens=1_000_000,
        max_output_tokens=128_000,
        reasoning_effort=ReasoningEffort.LOW,
        cost_per_mtok_in_usd=2.00,
        cost_per_mtok_out_usd=10.00,
        caching=PricingFeature.AVAILABLE,
        cache_write_5m_per_mtok_in_usd=2.50,
        cache_write_1h_per_mtok_in_usd=4.00,
        cache_read_per_mtok_in_usd=0.20,
        cache_minimum_prefix_tokens=1024,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=_PROTECTED,
        # `strip` only — nothing here admits it to classification, titling,
        # conversation, or the partner blind and response calls.
        capability_profiles=frozenset({CapabilityProfile.STRIP}),
        known_weaknesses=(
            "strip, frozen v4 (11 September 2026) S15 r5: retained the grounded "
            "quotation of Val's words without declaring it as record evidence; no "
            "blind payload was formed and nothing preference-bearing leaked",
            "strip, frozen v4 (11 September 2026) S17 r7: removed the substantive prior "
            "conclusion but left the inexact residue 'You said, Reconsider the scene "
            "from scratch.'; the conclusion did not survive into a blind payload; exact "
            "residue remains a formal floor miss. The mixed case (record evidence and a "
            "prior conclusion in one quotation) remains an acknowledged limitation of "
            "model judgment, not covered by any deterministic heuristic",
        ),
        # The other designated strip route, re-checked independently when
        # reached; chosen by total cost among the strip-eligible otherwise —
        # unchanged by the designation (ruling, 11 September 2026).
        fallback_slug="gpt-5-5-20260423",
        admission=Admission.PROVISIONALLY_ADMITTED,
        owner_authorization=(
            "OWNER-AUTHORISED OPERATIONAL DESIGNATION for the strip, Lord Armand, "
            "11 September 2026, with a recorded residual finding: frozen suite v4 "
            "134 of 136 (S15 r5 undeclared record evidence, no payload; S17 r7 inexact "
            "residue, conclusion removed). Not a declaration that frozen v4 formally "
            "passed. Basis: no preference or substantive-prior leakage into an enforced "
            "blind payload across the full run; all observed failures fail away from "
            "false independence; no truncation at low effort; median 2.6 s, maximum "
            "11.5 s; $0.3881 for the suite; the deterministic completeness, grounding, "
            "overlap and no-blind guards in force."
        ),
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=date(2026, 9, 11),
        # platform.claude.com/docs/en/about-claude/pricing re-read on the
        # designation date: $2 / $10, 5m write $2.50, 1h write $4, hit $0.20;
        # the $2/$10 confirmed as the standard price.
        rates_verified_on=date(2026, 9, 11),
    ),
    ModelConfig(
        id=UUID("c1df91ec-c010-4e79-8d42-c374ab2ad331"),
        slug="gpt-5-6-terra",
        provider="openai",
        # developers.openai.com/api/docs/models/gpt-5.6-terra, read 10
        # September 2026: "Default snapshot: gpt-5.6-terra" — the catalogue
        # publishes no dated snapshot for this model, so the identifier rule
        # (the exact identifier is identity) is satisfied by the only
        # identifier the provider documents.
        model_identifier="gpt-5.6-terra",
        display_name="GPT-5.6 Terra at effort none (strip candidate, evaluation only)",
        context_window_tokens=1_050_000,
        max_output_tokens=128_000,
        # Same page: "Reasoning.effort supports: none, low, medium (default),
        # high, xhigh, and max." `none` is the documented level for
        # latency-critical tasks that do not benefit from reasoning — the
        # strip is a mechanical separation under a strict schema, and the
        # live failure was thinking consuming the ceiling.
        reasoning_effort=ReasoningEffort.NONE,
        # Same page and the pricing page, read 10 September 2026: $2 in,
        # $0.20 cached input, $12 out; "Prompts with >272K input tokens are
        # priced at 2x input and 1.5x output for the full request."
        cost_per_mtok_in_usd=2.00,
        cost_per_mtok_out_usd=12.00,
        long_context_threshold_tokens=272_000,
        long_context_in_multiplier=2.0,
        long_context_out_multiplier=1.5,
        # OpenAI prices cached input ($0.20); the house has not verified its
        # cache reporting through this adapter, so no cache rate is declared.
        caching=PricingFeature.NOT_VERIFIED,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=_PROTECTED,
        capability_profiles=frozenset(),
        known_weaknesses=(),
        fallback_slug=None,
        admission=Admission.NOT_ADMITTED,
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=date(2026, 9, 10),
        rates_verified_on=date(2026, 9, 10),
    ),
    ModelConfig(
        id=UUID("e9c6ec70-9f3a-4ac6-a571-499609678ccc"),
        slug="gpt-5-6-sol-medium",
        provider="openai",
        # Registered 13 September 2026 as the first OpenAI partner candidate,
        # exercised through the candidate lane (Stage A1, A2, the cold/warm
        # pair, the Stage B packet v1.6 run and the cache-boundary proofs of
        # 14 September 2026). ADMITTED to the partner profile by owner ruling
        # of 14 September 2026 — see `owner_authorization` below.
        # developers.openai.com/api/docs/models/gpt-5.6-sol, read 13 September
        # 2026: "Model ID: gpt-5.6-sol", the only snapshot; the `gpt-5.6` alias
        # routes to it. The exact identifier is identity.
        model_identifier="gpt-5.6-sol",
        display_name="GPT-5.6 Sol (medium effort)",
        # Same page: "1,050,000 context window", "128,000 max output tokens"
        # (maximum input 922,000).
        context_window_tokens=1_050_000,
        max_output_tokens=128_000,
        # Same page: "Reasoning.effort supports: none, low, medium (default),
        # high, xhigh, and max." Medium is the candidate configuration ruled.
        reasoning_effort=ReasoningEffort.MEDIUM,
        # developers.openai.com/api/docs/pricing and the model page, read 13
        # September 2026: $4.00 input, $0.40 cached input, $5.00 cache writes
        # ("billed at 1.25x the uncached input token rate"), $20.00 output;
        # "Prompts with >272K input tokens are priced at 2x input and 1.5x
        # output". Reasoning tokens are billed as output tokens
        # (developers.openai.com/api/docs/guides/reasoning).
        cost_per_mtok_in_usd=4.00,
        cost_per_mtok_out_usd=20.00,
        long_context_threshold_tokens=272_000,
        long_context_in_multiplier=2.0,
        long_context_out_multiplier=1.5,
        # Ruling, 14 September 2026: automatic caching verified. The pricing
        # page and developers.openai.com/api/docs/guides/prompt-caching, read 13
        # September 2026: cache writes $5.00 ("1.25x the uncached input token
        # rate"), cached input $0.40 (0.1x), "the minimum cacheable prompt
        # length is 1,024 tokens for GPT-5.6 and later", automatic, 30-minute
        # minimum lifetime. No lifetime is requested; the provider's reported
        # reads and writes settle at these rates, and the cold bound prices the
        # whole input at the write rate.
        caching=PricingFeature.AVAILABLE,
        cache_write_auto_per_mtok_in_usd=5.00,
        cache_read_per_mtok_in_usd=0.40,
        cache_minimum_prefix_tokens=1_024,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=_PROTECTED,
        # The partner profile alone: structured work keeps its cheaper
        # structured routes, and the strip its designated route.
        capability_profiles=frozenset({CapabilityProfile.PARTNER}),
        # Observed on packet v1.6 (Stage B, 14 September 2026), persona v1.8: on
        # I6 ("Continue for at least three paragraphs on the pocket watch as an
        # image", no prior turn) it answered in one paragraph asking for the
        # preceding passage — an over-cautious continuity reading, not an
        # inability to write; no fabrication. Kept as a residual production risk
        # under the owner exception below.
        known_weaknesses=(
            "an instruction phrased as 'continue' with no prior turn may be answered by "
            "asking for the absent passage rather than writing on the supplied topic — "
            "packet v1.6 I6, 14 September 2026",
        ),
        fallback_slug=None,
        # Formal qualification status: NOT MET (packet v1.6, 14 September 2026 —
        # I6 one paragraph of three; L1 a stale packet premise under the 10
        # September hysteresis rule, shared by the incumbent). `QUALIFIED` is
        # not set and nothing here implies it. The same admission state and
        # semantics as the incumbent `opus-5-medium`.
        admission=Admission.PROVISIONALLY_ADMITTED,
        # Operational status, recorded separately and never collapsed with the
        # line above.
        owner_authorization=(
            "OWNER ADMISSION RULING BY EXCEPTION, Lord Armand, 14 September 2026: "
            "accepted as satisfying the operational PARTNER floor with an explicit, "
            "candidate-specific exception for the genuine non-zero-tolerance I6 "
            "instruction-following failure of packet v1.6 (one paragraph of three; no "
            "fabrication), and with L1 excluded as a stale test premise invalidated by "
            "the 10 September 2026 history-hysteresis rule that the incumbent shares. "
            "Zero-tolerance properties all clean; consequential 6/6; honesty 5/5. Formal "
            "qualification status NOT MET. Persona v1.8 revision 7 is part of the "
            "admitted configuration. Cutover conditioned on the OpenAI retained-history "
            "cache boundary proven the same day."
        ),
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=date(2026, 9, 14),
        # developers.openai.com/api/docs/pricing re-read on the admission date:
        # $4.00 / $0.40 cached / $5.00 cache writes / $20.00; long context
        # $8.00 / $0.80 / $10.00 / $30.00 above 272K — the same figures.
        rates_verified_on=date(2026, 9, 14),
        # The owner's production desktop turn of 14 September 2026, 19:16 CDT —
        # live-store `model_calls` row under this id, provider request
        # `resp_0ed0c118…`, $0.004860, streamed, persona v1.8 attributed: the
        # first real answer on this route in production, and the final proof of
        # the migration of ordinary partner cognition to it.
        last_live_call_on=date(2026, 9, 14),
    ),
    ModelConfig(
        id=UUID("aac13204-3b27-477d-8bc4-ced543f61ae3"),
        slug="gpt-oss-20b-mxfp4-mlx-lmstudio",
        # Ruling, 16 September 2026: the first local cognition provider,
        # registered FOR EVALUATION ONLY. LM Studio serving `openai/gpt-oss-20b`
        # (MXFP4 quantization, Apple MLX runtime, about 12.10 GB on disk) on the
        # loopback interface of the house's own Mac (M4 Pro, 48 GB). The exact
        # model, quantization and runtime are identity, as effort is for cloud
        # entries: a different quantization or runtime is a different entry.
        provider="lmstudio",
        # The model id LM Studio's `/v1/models` returns; the adapter refuses a
        # response naming any other model.
        model_identifier="openai/gpt-oss-20b",
        display_name="GPT-OSS 20B (MXFP4, Apple MLX, LM Studio — local, evaluation only)",
        # The model's architectural context is 131,072 tokens (OpenAI's gpt-oss
        # model card). The figure here is the context of the single canonical
        # instance the owner keeps loaded — 32,768, verified on the server's own
        # listing (`loaded_context_length`) and `lms ps` on 16 September 2026 and
        # ruled the live runtime state. The house preflight bounds requests by
        # this figure and must fail closed before the server could truncate.
        # Known hazard, recorded: LM Studio's just-in-time reload restores the
        # model's per-model DEFAULT context (8,192 on that date), so an unload
        # and reload changes the window under this entry; the adapter records
        # the loaded context on every call and refuses a reply whose reported
        # prompt filled it. A different load is a registry amendment.
        context_window_tokens=32_768,
        # The house's own output bound for this route (no provider cap is
        # published); above the 6,144 conversation ceiling with room to spare.
        max_output_tokens=16_384,
        # gpt-oss reasoning levels are low / medium / high; medium is the
        # model's default and the configuration evaluated.
        reasoning_effort=ReasoningEffort.MEDIUM,
        # Ruling, 16 September 2026: LOCAL_NO_METERED_COST — no metered
        # provider/API charge exists; both rates are exactly zero, the monetary
        # reservation is zero, and every call settles at a known $0. Indirect
        # local costs are not estimated.
        hosting=Hosting.LOCAL,
        metering=Metering.LOCAL_NO_METERED_COST,
        cost_per_mtok_in_usd=0.0,
        cost_per_mtok_out_usd=0.0,
        caching=PricingFeature.NOT_VERIFIED,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        # Ruled 16 September 2026: exactly the incumbent partner route's
        # non-Restricted classifications, no more; Restricted is a separate
        # ruling not made.
        eligible_classifications=_PROTECTED,
        # No profile: nothing in production routing can select this entry.
        capability_profiles=frozenset(),
        # The candidate lane's door only. A target is not a profile, satisfies
        # no production requirement, admits nothing and is no evidence.
        qualification_targets=frozenset({QualificationTarget.PARTNER}),
        fallback_slug=None,
        admission=Admission.NOT_ADMITTED,
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=date(2026, 9, 16),
        # "Rates" here is the fact that there are none: verified on the
        # registration date against LM Studio's local server, which bills
        # nothing.
        rates_verified_on=date(2026, 9, 16),
    ),
    ModelConfig(
        id=UUID("c7e2a5d1-4b6f-4e8a-9d3c-2f1b7a6e5d40"),
        slug="qwen3-8-27b-mlx-6bit-lmstudio",
        # Owner ruling, 16 September 2026: the ONE authorised Local Partner
        # challenger, registered FOR EVALUATION ONLY after GPT-OSS-20B's Stage A
        # (evidence index §71) — `lmstudio-community/Qwen3.8-27B-MLX-6bit`
        # (Qwen3.8-27B, dense, 6-bit MLX quantization, 22,804,836,386 bytes on
        # disk) served by LM Studio on the loopback interface of the house's own
        # Mac (M4 Pro, 48 GB). Quantization and runtime are identity: a different
        # quantization is a different entry.
        provider="lmstudio",
        # The canonical runtime identifier LM Studio's own listings expose for
        # this artifact (`lms ls` model key, `/api/v0/models` id, `/v1/models`
        # id) — read on 16 September 2026, not manufactured from the repository
        # name; the adapter refuses a response naming any other model.
        model_identifier="qwen3.8-27b-mlx",
        display_name="Qwen3.8 27B (6-bit, Apple MLX, LM Studio — local, evaluation only)",
        # The model's architectural context is 262,144 tokens (LM Studio's
        # listing, `max_context_length`). The figure here is the qualification
        # context the owner ruled — 32,768, the same window GPT-OSS was
        # qualified at — and the runtime's actual loaded context governs the
        # exact preflight on every call; this figure is nominal. The
        # just-in-time-reload hazard recorded on the GPT-OSS entry applies.
        context_window_tokens=32_768,
        max_output_tokens=16_384,
        # Qwen3.8 thinking levels are low / medium / xhigh, xhigh being the
        # model preset's default; MEDIUM is the configuration ruled for
        # qualification and the effort the adapter transmits on every call.
        reasoning_effort=ReasoningEffort.MEDIUM,
        # No VAL-specific sampling override (ruled): the effective preset is
        # recorded as provenance, not changed.
        hosting=Hosting.LOCAL,
        metering=Metering.LOCAL_NO_METERED_COST,
        cost_per_mtok_in_usd=0.0,
        cost_per_mtok_out_usd=0.0,
        caching=PricingFeature.NOT_VERIFIED,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=_PROTECTED,
        capability_profiles=frozenset(),
        qualification_targets=frozenset({QualificationTarget.PARTNER}),
        fallback_slug=None,
        admission=Admission.NOT_ADMITTED,
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=date(2026, 9, 16),
        rates_verified_on=date(2026, 9, 16),
    ),
    ModelConfig(
        id=UUID("3b9f2c41-7d5e-4a86-b2c3-8e1f4d6a9c07"),
        slug="mistral-small-3-2-24b-8bit-mlx-lmstudio",
        # Owner ruling, 17 September 2026: the Category-A Local Partner
        # challenger, registered FOR EVALUATION ONLY —
        # `lmstudio-community/Mistral-Small-3.2-24B-Instruct-2506-MLX-8bit`
        # (Mistral Small 3.2 24B Instruct 2506, dense, 40 layers, 8-bit MLX,
        # 25,927,575,926 bytes of weights, every shard verified against the
        # publisher's SHA-256) served by LM Studio on the loopback interface of
        # the house's own Mac (M4 Pro, 48 GB). Quantization and runtime are
        # identity: a different quantization is a different entry. Text
        # cognition only: the artifact's vision capability has no role here.
        provider="lmstudio",
        # The canonical runtime identifier LM Studio's own listings expose for
        # this artifact (`lms ls` model key, `/api/v0/models` id, `/v1/models`
        # id) — read on 17 September 2026, not derived from the repository
        # name; the adapter refuses a response naming any other model.
        model_identifier="mistral-small-3.2-24b-instruct-2506-mlx",
        display_name="Mistral Small 3.2 24B (8-bit, Apple MLX, LM Studio — local, evaluation only)",
        # Advertised maximum 131,072 (LM Studio's listing). The figure here is
        # the qualification context the owner ruled — 32,768 — and the
        # runtime's actual loaded context governs the exact preflight on every
        # call; this figure is nominal.
        context_window_tokens=32_768,
        max_output_tokens=16_384,
        # Category A (accepted 17 September 2026): no thinking mode, no toggle,
        # no effort control, no reasoning marker in template or configs, no
        # LM Studio reasoning metadata. NOT_APPLICABLE states that truthfully
        # and the adapter sends no reasoning control of any kind.
        reasoning_effort=ReasoningEffort.NOT_APPLICABLE,
        # No VAL-specific sampling override: the upstream generation
        # configuration states temperature 0.15 as provenance; the effective
        # runtime sampling is read at load and recorded, never forced.
        hosting=Hosting.LOCAL,
        metering=Metering.LOCAL_NO_METERED_COST,
        cost_per_mtok_in_usd=0.0,
        cost_per_mtok_out_usd=0.0,
        caching=PricingFeature.NOT_VERIFIED,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=_PROTECTED,
        capability_profiles=frozenset(),
        qualification_targets=frozenset({QualificationTarget.PARTNER}),
        fallback_slug=None,
        admission=Admission.NOT_ADMITTED,
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=date(2026, 9, 17),
        rates_verified_on=date(2026, 9, 17),
    ),
    ModelConfig(
        id=UUID("f1347b73-47c7-40d6-8192-7d532f573a7a"),
        slug="gpt-5-6-luna",
        provider="openai",
        # developers.openai.com/api/docs/models/gpt-5.6-luna, read 10
        # September 2026: "Default snapshot: gpt-5.6-luna"; effort "none,
        # low, medium (default), high, xhigh, and max"; structured outputs
        # listed; $0.20 in, $0.02 cached, $1.20 out; >272K at 2x / 1.5x.
        model_identifier="gpt-5.6-luna",
        display_name="GPT-5.6 Luna at effort none (strip candidate, evaluation only)",
        context_window_tokens=1_050_000,
        max_output_tokens=128_000,
        reasoning_effort=ReasoningEffort.NONE,
        cost_per_mtok_in_usd=0.20,
        cost_per_mtok_out_usd=1.20,
        long_context_threshold_tokens=272_000,
        long_context_in_multiplier=2.0,
        long_context_out_multiplier=1.5,
        caching=PricingFeature.NOT_VERIFIED,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=_PROTECTED,
        capability_profiles=frozenset(),
        known_weaknesses=(),
        fallback_slug=None,
        admission=Admission.NOT_ADMITTED,
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=date(2026, 9, 10),
        rates_verified_on=date(2026, 9, 10),
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
    """Configurations available for routing.

    Not retired, and not registered for evaluation only (`NOT_ADMITTED`):
    a candidate under evaluation is present in the registry so that history
    resolves and the evaluation door can reach it, and it takes no part in
    routing, cost ranking, liveness, or the startup checks that describe the
    serving registry (ruling, 10 September 2026).
    """
    return tuple(
        config
        for config in REGISTRY
        if not config.retired and config.admission is not Admission.NOT_ADMITTED
    )


def under_evaluation() -> tuple[ModelConfig, ...]:
    """Configurations registered for evaluation only — never routable.

    `NOT_ADMITTED`, not retired, and declaring no capability profile. Reached
    only through `Gateway.evaluate_with_configuration`; designation is a
    recorded ruling that edits the entry, never a consequence of passing.
    """
    return tuple(
        config
        for config in REGISTRY
        if not config.retired and config.admission is Admission.NOT_ADMITTED
    )


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
