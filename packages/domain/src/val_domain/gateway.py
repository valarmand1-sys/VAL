"""The Model Gateway's typed contracts (`01-architecture.md` §5.1).

These are the shapes every component speaks — provider-neutral by construction.
Nothing here knows how any provider spells its request; that knowledge lives in
`val_providers`, and only there.
"""

import math
from datetime import date
from enum import Enum, StrEnum
from typing import TYPE_CHECKING, Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from val_domain.project import ProjectAttribution


class Classification(StrEnum):
    """Data classification (`01-architecture.md` §5.4). Ambiguity resolves upward."""

    PUBLIC = "public"
    INTERNAL = "internal"
    PROTECTED = "protected"
    RESTRICTED = "restricted"


class TaskType(StrEnum):
    """The Layer 0 task types of `04-layer-0.md` §2.2, exactly."""

    CONVERSATION = "conversation"
    CLASSIFICATION = "classification"
    STRIP = "strip"
    BLIND_POSITION = "blind_position"
    TITLE = "title"


class CallStatus(StrEnum):
    """`model_calls.status`, exactly."""

    OK = "ok"
    ERROR = "error"
    REFUSED = "refused"


class CostCertainty(StrEnum):
    """Whether this row's cost is a fact or an absence (`04-layer-0.md` §2.2).

    A provider attempt has exactly three accounting outcomes, and only two of
    them are rows:

    - **NOT_SENT** — no provider request occurred. Cost is definitively zero and
      this was not a model call, so **no row is written at all**. That is why
      there is no enum member for it: a row asserting a call that never happened
      is the error this distinction exists to prevent.
    - **SENT_COST_KNOWN** — `KNOWN`. The request occurred and the response or
      error carried reliable usage, so `tokens_in`, `tokens_out`, and `cost`
      hold real figures.
    - **SENT_COST_UNKNOWN** — `UNKNOWN`. The request occurred — or may have —
      and usage cannot be established from what came back. `tokens_in`,
      `tokens_out`, and `cost` are **NULL**, never zero. Zero is a claim, and it
      is the wrong one: a call that reached the provider consumed input tokens
      whatever the transport did afterwards.

    A NULL `cost_certainty` on a row means only that the row predates this
    distinction (17 August 2026). It is not a third state.
    """

    KNOWN = "known"
    UNKNOWN = "unknown"


class TerminalState(StrEnum):
    """How a provider call actually ended — the provider-neutral terminal contract.

    Added in the current-version closure pass, 18 August 2026, because the
    previous contract collapsed materially different outcomes into a boolean:
    `ProviderResult.refused`. Under that shape an OpenAI `incomplete` (an output
    that hit its cap) was recorded as a *refusal*, and an Anthropic `max_tokens`
    truncation was recorded as an ordinary completed answer. A truncated reply
    that is persisted as Val's message is a fabrication — she did not finish
    saying it.

    Every adapter maps its provider's own stop semantics onto these four values
    explicitly. **Anything a provider returns that the adapter does not
    recognise maps to `UNKNOWN`, and `UNKNOWN` fails closed**: the gateway
    records the call honestly (it happened, it cost money) and then raises
    rather than handing the text onward as an answer.

    | State | Meaning | Becomes a Val message? |
    |---|---|---|
    | `COMPLETE` | the model finished naturally | yes |
    | `REFUSED` | the model declined; its refusal is deliberate and complete | yes |
    | `TRUNCATED` | the output cap cut it off; the text is a fragment | **no** — evidence only |
    | `FILTERED` | the content filter cut it off; a fragment | **no** — evidence only |
    | `UNKNOWN` | a stop state this adapter does not recognise | **no** — the call fails closed |

    Tool/action handoff states (`tool_use`, `pause_turn`) are not reachable at
    Layer 0 — no tool is ever sent — so an adapter receiving one maps it to
    `UNKNOWN`, which is exactly right: a state that cannot legitimately occur is
    a state we do not understand.
    """

    COMPLETE = "complete"
    REFUSED = "refused"
    TRUNCATED = "truncated"
    #: *Independent-review correction, 18 August 2026.* A content-filter stop is
    #: an INCOMPLETE result, not a refusal: a refusal is the model's deliberate,
    #: complete utterance, while a filter cut generation off mid-stream. The
    #: first closure pass mapped OpenAI's `incomplete`/`content_filter` to
    #: REFUSED, which `loop.send` persists as Val's finished message — partial
    #: filtered text entering history as though she finished speaking, the exact
    #: semantic class the terminal-state repair existed to close.
    FILTERED = "filtered"
    UNKNOWN = "unknown"


class CapabilityProfile(StrEnum):
    """What work a configuration is qualified for — ruling, 7 September 2026.

    The 2 September quality-priority ruling (`01-architecture.md` §5.5) orders
    routing as task → required quality floor → eligible routes meeting it →
    cost among those. Routing had no floor step: it went from eligibility to
    the cheapest candidate, so Val's own voice was served by the cheapest
    admitted route. A configuration now declares the profiles it satisfies,
    and a task names the profile it requires; cost ranks only routes that
    satisfy it and never lowers it.

    Three profiles, no broader than the rulings require. `STRUCTURED` is
    internal schema-constrained work — classification and titling. `STRIP`
    (9 September 2026) is the §4.1 preference strip, a floor of its own
    demonstrated on the frozen conformance suite. `PARTNER` is Val's partner
    cognition — every user-visible response and the blind position on a
    consequential exchange. None is a numeric ranking, and none names a model.
    """

    STRUCTURED = "structured"
    PARTNER = "partner"
    #: Ruling, 9 September 2026. The §4.1 strip is its own floor: a route
    #: serves it only after demonstrating the strip contract on the frozen
    #: conformance suite — zero leakage into an enforced blind input, zero
    #: neutral-content removal, no false contamination on clearly separable
    #: input. Structured-task competence elsewhere (classification, title)
    #: does not confer it, and holding it confers nothing else.
    STRIP = "strip"


class GatewayErrorKind(StrEnum):
    """The one normalized error contract (`01-architecture.md` §5.1).

    Provider timeouts, refusals, rate limits, invalid output, outages, and
    data-policy rejections all arrive as one of these, never as a provider's own
    exception type.
    """

    TIMEOUT = "timeout"
    REFUSAL = "refusal"
    RATE_LIMIT = "rate_limit"
    INVALID_REQUEST = "invalid_request"
    AUTHENTICATION = "authentication"
    PROVIDER_ERROR = "provider_error"
    INVALID_OUTPUT = "invalid_output"
    BUDGET_EXCEEDED = "budget_exceeded"
    NOT_ELIGIBLE = "not_eligible"
    RESTRICTED_CONTENT = "restricted_content"
    #: The router found no configuration that is admitted, eligible, ready, and
    #: affordable. Truthful unavailability — never a reason to downgrade the
    #: content's classification or to reach for an unadmitted route.
    NO_ELIGIBLE_ROUTE = "no_eligible_route"
    #: Ruling, 13 September 2026: admitting the next call would take one user
    #: exchange past its configured spending envelope. Not retryable on another
    #: route — a cheaper configuration is never substituted to fit the envelope —
    #: and proceeding requires Lord Armand's authorisation.
    EXCHANGE_ENVELOPE_EXCEEDED = "exchange_envelope_exceeded"


class QualificationTarget(Enum):
    """A floor a NOT_ADMITTED candidate is being qualified for — ruling, 14 September 2026.

    **Not a capability profile, and never convertible into one.** A plain
    `Enum`, deliberately not a `StrEnum`: `CapabilityProfile.PARTNER` is the
    string "partner", and a string-valued twin would compare and hash equal to
    it, so a qualification target could satisfy `satisfies_profile` by
    accident. This type compares equal to nothing but itself. It is consulted
    by exactly one door, the candidate lane (`val_gateway.candidate`), and by
    nothing in routing, fallback, admission or the pinned production paths.
    Passing qualification confers nothing; admission is a separate ruling that
    edits the entry.
    """

    PARTNER = "partner"


class Admission(StrEnum):
    """How far a configuration has got through `01-architecture.md` §5.2.1.

    The vocabulary exists because the architecture's routing rule said *qualified*
    while §5.2.1 said qualification cannot exist before the Layers 2-3 exam suite.
    Both are now true of different states, and Layer 0 asserts only the weaker one.

    `QUALIFIED` is reserved. Nothing may carry it until an exam record exists,
    and no code path sets it — a configuration is promoted to it by a recorded
    decision, never by an implementation that finds the word convenient.
    """

    #: Present in the registry but not permitted to carry traffic.
    NOT_ADMITTED = "not_admitted"
    #: Admitted for Layer 0 use on the strength of the eligibility ruling and a
    #: working adapter. This is the strongest state any Layer 0 route may hold.
    PROVISIONALLY_ADMITTED = "provisionally_admitted"
    #: Passed the system-specific exam suite. No such record exists yet.
    QUALIFIED = "qualified"


class AdapterStatus(StrEnum):
    """Whether code exists that speaks this provider's dialect (§5.2.1).

    Separate from admission on purpose: an implemented adapter is not a live
    provider, and neither is evidence of eligibility.
    """

    IMPLEMENTED = "implemented"
    NOT_IMPLEMENTED = "not_implemented"


class CacheTtl(StrEnum):
    """A prompt-cache lifetime the provider documents (ruling, 8 September 2026).

    Anthropic offers two: five minutes at 1.25x the input rate to write, one
    hour at 2x. A read refreshes the entry at 0.1x. Which one Val uses is
    configuration (`VAL_CACHE_TTL`), never a buried literal, because the right
    answer depends on Lord Armand's cadence between messages.
    """

    FIVE_MINUTES = "5m"
    ONE_HOUR = "1h"


class Hosting(StrEnum):
    """Where a configuration's inference runs — ruling, 16 September 2026.

    `CLOUD`: an external model provider; content leaves the house and every
    egress rule applies. `LOCAL`: inference on this machine, reached only over
    the loopback interface; the request is not sent to an external provider.
    Local does not bypass policy — classification, eligibility, budget, persona
    and provenance run exactly as for a cloud route — and Restricted eligibility
    is a separate ruling that has not been made.
    """

    CLOUD = "cloud"
    LOCAL = "local"


class Metering(StrEnum):
    """How a configuration's provider/API inference is charged — ruling, 16 September 2026.

    `METERED`: the provider bills per token at the entry's verified rates, and
    a zero rate is a defect. `LOCAL_NO_METERED_COST`: no metered provider/API
    charge exists — local inference on the house's own hardware — so the rates
    are declared zero, the monetary reservation bound is zero, and every call
    settles at a *known* $0 whether or not the runtime reported token usage.
    Token telemetry and monetary certainty are separate facts. Indirect local
    costs (electricity, hardware) are not estimated here.
    """

    METERED = "metered"
    LOCAL_NO_METERED_COST = "local_no_metered_cost"


class PricingFeature(StrEnum):
    """Whether caching or batch pricing applies to a configuration (§5.2).

    `NOT_VERIFIED` is the honest default and is not a synonym for absent: it
    records that the provider's own pricing page has not been read for this, in
    the same spirit as `rates_verified_on`. Layer 0 uses neither caching nor
    batch pricing (`01-architecture.md` §5.3 makes them first-class from the
    layer that has repetitive context to cache), so nothing here is load-bearing
    yet — but a guessed value would become load-bearing the moment it is.
    """

    NOT_VERIFIED = "not_verified"
    AVAILABLE = "available"
    NOT_AVAILABLE = "not_available"
    NOT_APPLICABLE = "not_applicable"


class ReasoningEffort(StrEnum):
    """The configuration's reasoning setting, or a typed absence (§5.2).

    `NOT_APPLICABLE` means the provider has no such concept for this model. It
    is a recorded fact, not a missing value, and it is why this is an enum rather
    than an optional string that would leave "unset" and "unsupported"
    indistinguishable.

    `NONE` (ruling, 10 September 2026) is OpenAI's documented lowest level —
    `reasoning.effort = "none"`, "latency-critical tasks that do not benefit
    from any reasoning" — a level the provider offers and the configuration
    states. It is not an Anthropic level: the Anthropic adapter refuses a
    configuration declaring it rather than substituting a level nobody chose.
    """

    NOT_APPLICABLE = "not_applicable"
    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GatewayError(Exception):
    """A failed gateway call, in normalized form.

    `model_call_ids` names every `model_calls` row the failed call wrote on its
    way to failing — one per route attempted whose provider was contacted
    (3 September 2026). Empty when nothing was transmitted. A caller that
    records evidence about an attempt can then name the calls it paid for,
    without inferring them from timestamps.
    """

    def __init__(
        self, kind: GatewayErrorKind, detail: str, model_call_ids: tuple[UUID, ...] = ()
    ) -> None:
        super().__init__(f"{kind.value}: {detail}")
        self.kind = kind
        self.detail = detail
        self.model_call_ids = model_call_ids


class ProviderImageLimits(BaseModel):
    """What the **provider** documents about image input. Verified and dated.

    Owner ruling, 19 September 2026; corrected 20 September 2026. Every field
    here is a fact read from first-party documentation and re-read on
    `verified_on`. Nothing this house merely prefers belongs in this object —
    that lives in `HouseImagePolicy` beside it, so a later reader can tell a
    provider limit from a house choice without opening a document.
    """

    model_config = ConfigDict(frozen=True)

    #: Media types the provider accepts, as it documents them.
    media_types: frozenset[str]
    #: The detail level transmitted on every image of this route. Declared
    #: rather than defaulted: the provider's default resolves to no patch
    #: budget, and a cost with no ceiling cannot be reserved against a ceiling.
    detail: str = Field(min_length=1)
    #: The dimension bound of that detail level. An image inside it **and**
    #: inside the patch budget is transmitted as it is: the provider performs no
    #: resize, so the documented formula applies exactly.
    max_long_edge_pixels: int = Field(gt=0)
    #: The documented tokenisation: patches this many pixels square, at most
    #: `patch_budget` of them, each billed at `token_multiplier` input tokens.
    patch_pixels: int = Field(gt=0)
    patch_budget: int = Field(gt=0)
    token_multiplier: float = Field(gt=0)
    verified_on: date
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def _media_types_are_media_types(self) -> ProviderImageLimits:
        if not self.media_types:
            raise ValueError("a configuration declaring image input must name its media types")
        for media_type in self.media_types:
            if media_type != media_type.lower() or media_type.count("/") != 1:
                raise ValueError(f"{media_type!r} is not a media type")
        return self


class ProviderRequestImageLimits(BaseModel):
    """What the provider documents about a **whole request** carrying images.

    Owner correction, 20 September 2026. These are request-wide provider facts
    and belong to neither the per-image sizing rules above nor any house policy:
    a turn whose images are each individually valid can still be an invalid
    request, and the house must know that before any pixels leave the machine.

    **The measurement unit of the payload ceiling is NOT documented.** The page
    states the number and does not say what is counted against it — raw bytes,
    base64, the data URI, or the whole HTTP body. That gap is recorded here as a
    fact about the documentation (`payload_unit_is_documented`), so nobody later
    reads the house's conservative reading as something the provider said. How
    the house measures against it lives in `HouseImagePolicy`.
    """

    model_config = ConfigDict(frozen=True)

    #: "Up to 1,500 images per request."
    max_images_per_request: int = Field(gt=0)
    #: "Up to 512 MB total payload per request." Interpreted as 512 x 1,000,000
    #: rather than 512 MiB, because the smaller reading of an ambiguous ceiling
    #: is the conservative one.
    max_total_payload_bytes: int = Field(gt=0)
    #: False while the provider documents the number without defining the unit.
    #: A later documentation change that settles it flips this deliberately.
    payload_unit_is_documented: bool = False
    verified_on: date
    source: str = Field(min_length=1)


class HouseImagePolicy(BaseModel):
    """What **this house** chooses about image input, and why.

    Correction, 20 September 2026: a house limit recorded among provider facts
    is a house limit that a later reader will cite as the provider's. The
    provider documents no per-image size limit at all — only a per-request
    payload bound — so the ceiling below is the house's own, and says so.
    """

    model_config = ConfigDict(frozen=True)

    #: The largest ORIGINAL image this house admits. A house admission and
    #: safety policy, not a provider limit: the provider documents none.
    max_byte_size: int = Field(gt=0)
    #: Why this house set it where it did.
    reason: str = Field(min_length=1)
    #: **A house interpretation of an ambiguous provider fact, not a provider
    #: fact.** The provider caps a request's "total payload" and does not define
    #: what is measured; this names the quantity the house counts instead.
    request_payload_measure: str = Field(min_length=1)
    #: Why that quantity is the conservative choice, in words a later reader can
    #: check against the documentation themselves.
    request_payload_measure_reason: str = Field(min_length=1)


class ImageInputSupport(BaseModel):
    """One configuration's image-input capability: what the provider allows, and
    what this house permits itself.

    The two halves are separate objects on purpose (correction, 20 September
    2026). Routing, transmission planning and the reservation each read the half
    they are entitled to, and the registry entry reads as what it is.
    """

    model_config = ConfigDict(frozen=True)

    #: Per-image provider facts.
    provider: ProviderImageLimits
    #: Request-wide provider facts.
    provider_request: ProviderRequestImageLimits
    #: What this house chooses, including how it reads the ambiguous ceiling.
    house: HouseImagePolicy

    @property
    def max_tokens_per_image(self) -> int:
        """The most one transmitted image can bill, by the provider's own budget.

        The documented formula alone. The reservation adds a separate, declared
        margin for the provider's documented one-token rounding; that margin is
        not part of this figure and is never described as pricing.
        """
        return math.ceil(self.provider.patch_budget * self.provider.token_multiplier)


class ModelConfig(BaseModel):
    """One entry of the Model Configuration Registry (`01-architecture.md` §5.2).

    A versioned record, not a model name in a settings file. `id` is the stable
    key `model_calls.model_config_id` refers to; `slug` is the stable
    human-readable name every cost view displays. Costs are per million tokens,
    as published by the provider, and are the rates `model_calls.cost` is
    computed from at call time — never recomputed later.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    provider: str
    model_identifier: str
    display_name: str
    context_window_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    #: Reasoning or sampling settings (§5.2). `temperature = None` means the
    #: configuration sets none and the provider's own default stands — recorded
    #: rather than filled in with an invented number.
    reasoning_effort: ReasoningEffort
    temperature: float | None = None
    #: Owner ruling, 18 September 2026 — orthogonal to the graded `reasoning_effort`,
    #: for models whose thinking is a binary switch the request itself declares.
    #: `True` = Core requires thinking ON; `False` = Core requires it OFF; `None` =
    #: the model/provider has no such contract. `None` never means "whatever the
    #: runtime's UI happens to be set to": a declared state is transmitted by the
    #: adapter and provable, or the adapter refuses the configuration.
    thinking_enabled: bool | None = None
    #: Whether prior-turn thinking may be replayed by the chat template. Val's
    #: contract is `False` wherever the switch exists: hidden reasoning is never
    #: persisted and never re-enters history.
    preserve_thinking: bool | None = None
    #: Sampling values an upstream publisher declares beside temperature, sent
    #: verbatim when set. `None` = not declared, nothing sent.
    top_p: float | None = Field(default=None, gt=0, le=1)
    top_k: int | None = Field(default=None, ge=1)
    #: Ruling, 16 September 2026: zero is legal only under
    #: `Metering.LOCAL_NO_METERED_COST` (validated below); a metered route with a
    #: zero rate is refused at construction.
    cost_per_mtok_in_usd: float = Field(ge=0)
    cost_per_mtok_out_usd: float = Field(ge=0)
    #: Ruling, 16 September 2026: the hosting axis and the metering basis.
    hosting: Hosting = Hosting.CLOUD
    metering: Metering = Metering.METERED
    #: Closure pass, 18 August 2026. Some providers re-price a call whose input
    #: crosses a threshold — GPT-5.5 bills 2x input and 1.5x output for the full
    #: session above 272K input tokens (developers.openai.com, verified 18
    #: August 2026). The threshold and multipliers live HERE, on the registry
    #: entry, because a pricing fact embedded in code is a pricing fact nobody
    #: re-verifies. `None` means the provider documents no such rule.
    #: Owner ruling, 19 September 2026 (Track C): declared image-input capability.
    #: `None` means this configuration is not image-capable, which is every
    #: configuration but the first slice's approved route. Declaring it does not
    #: admit a model or change a profile; it states what this route accepts.
    image_input: ImageInputSupport | None = None
    long_context_threshold_tokens: int | None = None
    long_context_in_multiplier: float = Field(default=1.0, ge=1.0)
    long_context_out_multiplier: float = Field(default=1.0, ge=1.0)
    #: Whether caching or batch pricing applies (§5.2). See `PricingFeature`:
    #: `NOT_VERIFIED` records that this has not been read from the provider.
    caching: PricingFeature = PricingFeature.NOT_VERIFIED
    #: Ruling, 8 September 2026. The provider's published cache rates, read
    #: from its pricing page on the date in `rates_verified_on`, and the
    #: shortest prefix it will cache. Present exactly when `caching` is
    #: `AVAILABLE`: a route may not be cached on rates nobody has read, and a
    #: verified route may not be missing the figures the bound and the
    #: settlement price with. `None` otherwise.
    cache_write_5m_per_mtok_in_usd: float | None = Field(default=None, gt=0)
    cache_write_1h_per_mtok_in_usd: float | None = Field(default=None, gt=0)
    cache_read_per_mtok_in_usd: float | None = Field(default=None, gt=0)
    cache_minimum_prefix_tokens: int | None = Field(default=None, gt=0)
    #: Ruling, 14 September 2026. A provider that caches **automatically** —
    #: no lifetime requested by this house, the provider deciding what it
    #: writes and reporting reads and writes in its usage — carries its one
    #: verified write rate here instead of the per-lifetime rates above. The
    #: two shapes are exclusive: an entry declares the requested-lifetime pair
    #: or the automatic rate, never both, and each with the read rate and the
    #: minimum prefix. Anthropic's semantics are untouched by this field.
    cache_write_auto_per_mtok_in_usd: float | None = Field(default=None, gt=0)
    batch_pricing: PricingFeature = PricingFeature.NOT_VERIFIED
    eligible_classifications: frozenset[Classification]
    #: Ruling, 7 September 2026. The capability profiles this configuration
    #: is qualified to serve; a task requiring a profile the configuration
    #: does not declare is never routed to it, whatever it costs. Required —
    #: an entry that declares nothing serves nothing. Qualification for
    #: `PARTNER` is a ruling, never inferred from eligibility, price, or name.
    capability_profiles: frozenset[CapabilityProfile]
    #: Weaknesses observed in this house's own use (§5.2). Written from
    #: observation, never from a provider's or a benchmark's claims, so an empty
    #: tuple means "none observed here yet" rather than "none exist".
    known_weaknesses: tuple[str, ...] = ()
    #: The preferred successor when this route cannot answer, or None for an
    #: explicit NONE. A fallback is re-checked against every admission and
    #: eligibility rule when it is reached; it never inherits the failed route's
    #: standing (`01-architecture.md` §5.4).
    fallback_slug: str | None
    #: How far this configuration has got through §5.2.1, and whether code exists
    #: that speaks its dialect. Independent: neither implies the other, and
    #: neither implies eligibility.
    admission: Admission
    #: Ruling, 14 September 2026: the floors this configuration is a candidate
    #: for. Only a `NOT_ADMITTED` entry declaring no capability profile may
    #: carry one (the validator below), and it is read by the candidate lane
    #: alone. Empty on every serving route.
    qualification_targets: frozenset[QualificationTarget] = frozenset()
    #: Ruling, 10 September 2026 (`01-architecture.md` §5.2): a configuration
    #: placed into operational service under the **owner-authorised operational
    #: exception** records that authorisation here — the residual it carries,
    #: the date, and the open-problem entry that holds the closure condition.
    #: This is an operational status, separate from `admission`: it never sets
    #: or implies `QUALIFIED`, and a configuration carrying it is formally
    #: *not met* on the frozen exam that produced it. `None` for every route
    #: that is not in service under an exception.
    owner_authorization: str | None = None
    adapter_status: AdapterStatus
    #: When this configuration became routable, and when it stopped being so.
    activated_on: date
    retired_on: date | None = None
    #: The day the rates above were read from the provider's own documentation.
    #: Rates go stale silently, and a stale rate makes cost attribution quietly
    #: wrong rather than visibly wrong — so the date is carried per entry and
    #: surfaced as a startup warning once it ages (`registry.stale_rates`).
    rates_verified_on: date
    #: The day this exact route last answered a real call successfully, or None
    #: if it never has. An implemented adapter is not a live provider
    #: (`01-architecture.md` §5.2.1): only a real answer proves the route works.
    #: Set from an observed `model_calls` row, never from the fact code exists.
    last_live_call_on: date | None = None
    #: Google-only structural requirement (`01-architecture.md` §5.4 amendment):
    #: True only when startup has verified the key is attached to paid billing.
    #: Configuration cannot claim it; the verifier sets it.
    billing_verified: bool = False
    retired: bool = False

    @model_validator(mode="after")
    def _qualification_targets_only_on_candidates(self) -> ModelConfig:
        """A qualification target rides only on an unadmitted, profile-less entry."""
        if self.qualification_targets and (
            self.admission is not Admission.NOT_ADMITTED or self.capability_profiles
        ):
            raise ValueError(
                f"{self.slug}: qualification targets belong to a NOT_ADMITTED candidate "
                "declaring no capability profile; a serving configuration is not a candidate "
                "and a candidate serves nothing (ruling, 14 September 2026)"
            )
        return self

    @model_validator(mode="after")
    def _cache_rates_iff_available(self) -> ModelConfig:
        """Cache rates travel with verified caching, and only with it."""
        requested = (self.cache_write_5m_per_mtok_in_usd, self.cache_write_1h_per_mtok_in_usd)
        automatic = self.cache_write_auto_per_mtok_in_usd
        common = (self.cache_read_per_mtok_in_usd, self.cache_minimum_prefix_tokens)
        rates = (*requested, automatic, *common)
        if self.caching is PricingFeature.AVAILABLE:
            requested_complete = all(rate is not None for rate in requested)
            requested_absent = all(rate is None for rate in requested)
            if any(rate is None for rate in common) or not (
                (requested_complete and automatic is None)
                or (requested_absent and automatic is not None)
            ):
                raise ValueError(
                    f"{self.slug}: caching is AVAILABLE but the cache rates or minimum prefix "
                    "are missing or mixed; a route is cached only on rates read from the "
                    "provider's pricing, as either the requested-lifetime pair or the one "
                    "automatic write rate, with the read rate and the minimum prefix"
                )
        if self.caching is not PricingFeature.AVAILABLE and any(rate is not None for rate in rates):
            raise ValueError(
                f"{self.slug}: cache rates are declared but caching is {self.caching.value}; "
                "rates on an unverified route are a guess wearing a number"
            )
        return self

    @model_validator(mode="after")
    def _thinking_declaration_is_coherent(self) -> ModelConfig:
        """`preserve_thinking` is a statement about a thinking switch that exists."""
        if self.preserve_thinking is not None and self.thinking_enabled is None:
            raise ValueError(
                f"{self.slug}: preserve_thinking is declared without thinking_enabled; the "
                "replay setting has no meaning for a model with no declared thinking switch"
            )
        if self.preserve_thinking is True:
            raise ValueError(
                f"{self.slug}: preserve_thinking = True would replay hidden reasoning into "
                "history, which Val never persists (ruling, 18 September 2026)"
            )
        return self

    @model_validator(mode="after")
    def _rates_match_metering(self) -> ModelConfig:
        """Zero rates only on a declared unmetered local route; never elsewhere."""
        zero = self.cost_per_mtok_in_usd == 0 or self.cost_per_mtok_out_usd == 0
        if self.metering is Metering.METERED and zero:
            raise ValueError(
                f"{self.slug}: a metered configuration declares a zero rate; a zero on a "
                "metered provider is a fabricated cost, not a price (ruling, 16 September 2026)"
            )
        if self.metering is Metering.LOCAL_NO_METERED_COST:
            if self.cost_per_mtok_in_usd != 0 or self.cost_per_mtok_out_usd != 0:
                raise ValueError(
                    f"{self.slug}: LOCAL_NO_METERED_COST declares no metered charge, so both "
                    "rates are exactly zero"
                )
            if self.hosting is not Hosting.LOCAL:
                raise ValueError(
                    f"{self.slug}: LOCAL_NO_METERED_COST is legal only on a LOCAL hosting entry; "
                    "an unmetered cloud route is not a thing this registry may describe"
                )
            if self.caching is PricingFeature.AVAILABLE:
                raise ValueError(f"{self.slug}: an unmetered route carries no cache pricing")
        return self

    @property
    def caches_automatically(self) -> bool:
        """Whether the provider caches this route on its own, at a verified write rate."""
        return (
            self.caching is PricingFeature.AVAILABLE
            and self.cache_write_auto_per_mtok_in_usd is not None
        )

    def cache_write_rate(self, ttl: CacheTtl) -> float:
        """The per-mtok cache-write rate for this TTL. Only on a verified route."""
        rate = (
            self.cache_write_5m_per_mtok_in_usd
            if ttl is CacheTtl.FIVE_MINUTES
            else self.cache_write_1h_per_mtok_in_usd
        )
        if rate is None:
            raise ValueError(f"{self.slug}: no verified cache-write rate for {ttl.value}")
        return rate


class TextPart(BaseModel):
    """Words. The part every turn has had since Layer 0 began."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["text"] = "text"
    text: str


class ImagePart(BaseModel):
    """The exact image bytes selected for transmission, with what describes them.

    Owner ruling, 19 September 2026 (Track C). These are **already-selected**
    bytes: the admission preflight established the media type from them, and
    transmission planning decided whether the original or a derived
    `model_input_image` is what leaves the house. An adapter base64-encodes what
    it is given and transmits it unchanged — no adapter resizes, re-encodes or
    chooses, because two adapters choosing independently is how a blind call and
    a final call come to see different pixels (Attachment Substrate v1.2 §7).

    `width` and `height` are the decoded dimensions of *these* bytes, so the
    figures that priced the call, the figures on the wire and the figures on the
    `model_call_image_inputs` row are one set of facts (§8).
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["image"] = "image"
    #: The digest of `content`, and the key of the blob holding it.
    sha256: str = Field(min_length=64, max_length=64)
    media_type: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    #: Never in a repr: an image in a log line is an image outside the record.
    content: bytes = Field(repr=False)


#: One ordered sequence, discriminated on `kind`. **Audio and video become
#: additional members here** — a new part type and the adapters that can carry
#: it — rather than a second boundary beside this one. Nothing else about a
#: message changes when they arrive, which is the whole point of doing this once.
ContentPart = Annotated[TextPart | ImagePart, Field(discriminator="kind")]


class Message(BaseModel):
    """One conversational turn, provider-neutral: an ordered sequence of parts.

    Owner ruling, 19 September 2026. Val Core used to assume a turn *was* a
    string. It is now an ordered list of content parts, of which text is one —
    the same lesson as the provider-neutral cognition boundary: build the
    abstraction once, then populate it as capabilities arrive.

    A text-only turn is unchanged in every way that matters. `Message(role=...,
    content="...")` still constructs one, `message.content` still reads the
    words back, and every existing caller, adapter and test keeps working: the
    string is simply the one text part, and `content` is the text of the parts
    rather than a second field beside them. There is one source of truth.
    """

    model_config = ConfigDict(frozen=True)

    role: str = Field(pattern=r"^(user|assistant)$")
    parts: tuple[ContentPart, ...] = Field(min_length=1)

    if TYPE_CHECKING:
        # Pydantic builds `__init__` at run time and the validator below accepts
        # `content=` as shorthand for one text part. Declaring the signature here
        # lets the type checker see both spellings; it exists only for analysis.
        def __init__(
            self,
            *,
            role: str,
            content: str = ...,
            parts: tuple[ContentPart, ...] = ...,
            cache_breakpoint: bool = ...,
        ) -> None: ...

    #: Ruled 10 September 2026: the last retained same-conversation history
    #: message carries the prompt-cache breakpoint, so the append-only history
    #: prefix (persona + history) is cached and later turns read it. An adapter
    #: that caches honours it when a lifetime was requested; one that does not
    #: cache ignores it. Never set on the envelopes or the current turn.
    cache_breakpoint: bool = False

    @model_validator(mode="before")
    @classmethod
    def _text_is_one_part(cls, data: object) -> object:
        """`content="..."` is the ordinary way to say *one text part*."""
        if isinstance(data, dict) and "content" in data and "parts" not in data:
            supplied = dict(data)
            text = supplied.pop("content")
            if not isinstance(text, str):
                raise ValueError("Message content is text; other media are parts")
            supplied["parts"] = (TextPart(text=text),)
            return supplied
        return data

    @property
    def content(self) -> str:
        """The words of this turn, in order — the text parts and nothing else.

        A text-only message returns exactly what it was constructed with. A
        message carrying images returns the words around them, which is what a
        byte bound, a lexical screen or a log line should see: the pixels are
        accounted for by their own dimensions, never by pretending they are
        characters.
        """
        return "".join(part.text for part in self.parts if isinstance(part, TextPart))

    @property
    def images(self) -> tuple[ImagePart, ...]:
        """The image parts of this turn, in the order they were attached."""
        return tuple(part for part in self.parts if isinstance(part, ImagePart))


class TurnReference(BaseModel):
    """The turn a conversation call answers: a conversation and its user message.

    What a caller holds *before* the persona is loaded. `converse` takes this;
    context assembly adds the persona revision it just read and produces the
    complete `ConversationProvenance`. Two objects rather than one optional
    field, so no code path can construct provenance with the persona missing and
    no code path has to pass `None` for a value it is about to supply.

    Both ids are required. They are the pair `val_gateway.loop.send` already
    holds by the time it calls the gateway, because it persisted the message.
    """

    model_config = ConfigDict(frozen=True)

    conversation_id: UUID
    message_id: UUID


class PersonaAttribution(BaseModel):
    """Which persona revision is assembled into a `blind_position` call.

    *WP-0.9 ruling, 19 August 2026.* The blind position must be **Val's**
    position, so the blind call carries the active persona whole (`04-layer-0.md`
    WP-0.5, as amended) — and once a persona is assembled, the call must
    attribute it: a NULL `model_calls.persona_id` on a persona-bearing call
    would mean "assembled and failed to attribute," a false record.

    Deliberately **not** `ConversationProvenance`. Conversation provenance is
    conversation-only — a blind call is machinery, not Val answering a turn —
    and reusing the conversation shape here would hand machinery the ids that
    attribute utterances. This is the smallest separate contract that carries
    the one fact the record needs.

    The id must name the **active** persona; the gateway verifies that against
    the WP-0.5 loader before transmission rather than trusting the caller.
    """

    model_config = ConfigDict(frozen=True)

    persona_id: UUID


class ConversationProvenance(BaseModel):
    """What caused a conversation call, as one indivisible fact — WP-0.7 corrective.

    Independent review of `VAL_Source_Snapshot_d137925.zip` found that a
    `TaskType.CONVERSATION` request could still be built with
    `conversation_id`, `message_id` and `persona_id` all `None` — a Val
    utterance with nothing tying it to a conversation, a question, or an
    identity. WP-0.7's persistence guarantee held for `loop.send` and for
    nothing else.

    **Three optional fields were the defect, not three missing checks.** They
    were independently defaultable, so "all three or none" was a convention any
    caller could break one field at a time. Here they are one object with no
    defaults: a caller either has the provenance or cannot construct it, which
    is the same device that kept `AmbiguousProject` out of persistence in
    WP-0.6.

    | Field | Means |
    |---|---|
    | `conversation_id` | the conversation this turn belongs to |
    | `message_id` | the **persisted user message** that caused the call |
    | `persona_id` | the persona revision assembled into it (WP-0.5) |

    `message_id` is the *triggering* turn — the question — not Val's reply,
    which does not exist when the call is made.

    **This object asserts the three ids exist together. It does not assert they
    agree.** Coherence — that the message really belongs to the conversation and
    that the conversation's scope matches the call's — is a fact about the
    database, and is checked in `val_gateway.provenance` before transmission.
    """

    model_config = ConfigDict(frozen=True)

    conversation_id: UUID
    message_id: UUID
    persona_id: UUID


class GatewayRequest(BaseModel):
    """What a caller asks of the gateway.

    The caller states the classification; the gateway never infers it
    (`01-architecture.md` §5.4 — classification is computed before routing,
    never by the model that will receive the content). Attribution fields
    mirror `model_calls` and are recorded on every call.
    """

    model_config = ConfigDict(frozen=True)

    task_type: TaskType
    classification: Classification
    messages: tuple[Message, ...]
    system: str | None = None
    max_output_tokens: int = Field(default=4096, gt=0)
    #: WP-0.6 corrective round, 18 August 2026. **Both are required and neither
    #: has a default.** `project_id` alone cannot say whether a NULL is a
    #: decision, and the default it used to carry let any caller write a
    #: semantically empty NULL without deciding anything — which is precisely how
    #: the claim "NULL means exactly explicit no-project" stopped being true.
    #:
    #: `LEGACY_UNKNOWN` is rejected here (see the validator). It describes rows
    #: written before this distinction existed and is never a way to avoid
    #: deciding now.
    project_id: UUID | None
    project_attribution: ProjectAttribution
    #: WP-0.7 corrective round, 18 August 2026. **One object, not three
    #: independently optional ids.** Required for `TaskType.CONVERSATION` and
    #: absent on the task types that legitimately have no conversation behind
    #: them — classification, strip, blind_position, title. Those are machinery
    #: the house runs on its own behalf; a conversation is Val speaking to Lord
    #: Armand, and it must be possible to say which turn it answered.
    conversation: ConversationProvenance | None = None
    #: WP-0.9 ruling, 19 August 2026. Present iff `task_type` is BLIND_POSITION:
    #: the blind call carries the active persona and must attribute it, and no
    #: other non-conversation task assembles one (WP-0.5's deliberate narrowing —
    #: classification and strip are the house reading content, not Val speaking).
    #: A conversation's persona rides in `ConversationProvenance`, never here.
    persona: PersonaAttribution | None = None
    #: 3 September 2026. A JSON Schema the provider must constrain its reply
    #: to, for callers whose contract is a machine-readable document — the §4.8
    #: classifier first. Added after the classifier's instruction-only JSON
    #: contract was observed failing on real replies (a correct verdict followed
    #: by prose answering the exchange; prose followed by a fenced verdict):
    #: an output contract enforced by instruction alone is asserted, not
    #: structural. An adapter that cannot enforce the schema refuses the call
    #: rather than dropping it — a constraint silently not applied would be the
    #: same defect through a different door.
    output_schema: dict[str, object] | None = None
    #: Ruling, 13 September 2026: the user exchange this call belongs to — the
    #: conversation and the persisted user message that caused the work — on
    #: every task type an exchange runs (classification, strip, blind position,
    #: the response). Unlike `conversation`, it attributes nothing on
    #: `model_calls`: it is carried to the reservation and the measurement
    #: sidecar only, so machinery keeps its no-provenance record while the
    #: exchange's total cost becomes reconstructable. A conversation call's
    #: exchange is its provenance; an explicit one must agree with it.
    exchange: TurnReference | None = None

    @property
    def exchange_reference(self) -> TurnReference | None:
        """The exchange this call belongs to: explicit, or a conversation's own turn."""
        if self.exchange is not None:
            return self.exchange
        if self.conversation is not None:
            return TurnReference(
                conversation_id=self.conversation.conversation_id,
                message_id=self.conversation.message_id,
            )
        return None

    @property
    def conversation_id(self) -> UUID | None:
        """The conversation, if this call has one. Read by the recorder."""
        return None if self.conversation is None else self.conversation.conversation_id

    @property
    def message_id(self) -> UUID | None:
        """The persisted user message that caused this call, if there is one."""
        return None if self.conversation is None else self.conversation.message_id

    @property
    def persona_id(self) -> UUID | None:
        """The persona revision assembled into this request, if any.

        From conversation provenance on a conversation call, from the separate
        persona attribution on a blind-position call, and None on the paths
        that legitimately assemble none.
        """
        if self.conversation is not None:
            return self.conversation.persona_id
        if self.persona is not None:
            return self.persona.persona_id
        return None

    @model_validator(mode="after")
    def _provenance_iff_conversation(self) -> GatewayRequest:
        """Conversation provenance is present iff the task is conversation.

        *Independent-review correction, 18 August 2026.* The first closure pass
        enforced only the forward direction — a conversation must carry
        provenance — and left the inverse open: a CLASSIFICATION request could
        carry real conversation, message, and persona ids and, through a
        generic entrance that never runs the conversation verifier, write
        coherent-looking `model_calls` attribution for machinery that was never
        part of any conversation. The contract was always meant as an iff, and
        now it is one.

        Forward: a Val utterance must say which turn it answered
        (`04-layer-0.md` WP-0.7) — use `val_gateway.loop.send`, which persists
        the message first and supplies all three ids.

        Inverse: classification and strip are the house reasoning about content
        before it is routed, `blind_position` is a deliberation step, and
        `title` names something. None of them is Val answering Lord Armand, and
        provenance on one would be attribution to a conversation that did not
        cause it.
        """
        if self.task_type is TaskType.CONVERSATION and self.conversation is None:
            raise ValueError(
                "a conversation call must carry its provenance: the conversation it "
                "belongs to, the persisted user message that caused it, and the "
                "persona revision assembled into it. Without them a Val utterance is "
                "recorded with nothing tying it to what was said or who said it "
                "(04-layer-0.md WP-0.7). Use `val_gateway.loop.send`, which persists "
                "the message first and supplies all three."
            )
        if self.task_type is not TaskType.CONVERSATION and self.conversation is not None:
            raise ValueError(
                f"a {self.task_type.value!r} request may not carry conversation "
                "provenance. Only a conversation is caused by a conversation turn; "
                "attaching real conversation, message, and persona ids to machinery "
                "would record model_calls attribution for a conversation that never "
                "made the call (current-version closure, independent-review "
                "correction, 18 August 2026)."
            )
        return self

    @model_validator(mode="after")
    def _exchange_agrees_with_provenance(self) -> GatewayRequest:
        """A conversation call's exchange is the turn its provenance names."""
        if (
            self.exchange is not None
            and self.conversation is not None
            and (
                self.exchange.conversation_id != self.conversation.conversation_id
                or self.exchange.message_id != self.conversation.message_id
            )
        ):
            raise ValueError(
                "the exchange named on a conversation call must be the turn its provenance "
                "names; one call cannot belong to two exchanges"
            )
        return self

    @model_validator(mode="after")
    def _persona_iff_blind_position(self) -> GatewayRequest:
        """Separate persona attribution is present iff the task is blind_position.

        *WP-0.9 ruling, 19 August 2026.* Forward: a blind-position call carries
        the active persona (WP-0.5 as amended), and a persona assembled without
        attribution writes a false NULL. Inverse: classification, strip, and
        title assemble no persona — attributing one would record an identity
        that was never in the call — and a conversation's persona rides in
        `ConversationProvenance`, so a second copy here could only disagree
        with it. Guarded at the entrances too, because `model_copy` skips
        validators.
        """
        if self.task_type is TaskType.BLIND_POSITION and self.persona is None:
            raise ValueError(
                "a blind_position call must carry its persona attribution: the blind "
                "position is Val's position, so the call assembles the active persona "
                "(04-layer-0.md WP-0.5, amended 19 August 2026) and must say which "
                "revision it assembled — a persona-bearing call recording NULL would "
                "be a false record, not a missing feature."
            )
        if self.task_type is not TaskType.BLIND_POSITION and self.persona is not None:
            raise ValueError(
                f"a {self.task_type.value!r} request may not carry persona "
                "attribution. Classification, strip, and title assemble no persona "
                "(WP-0.5's deliberate narrowing), and a conversation's persona rides "
                "in its ConversationProvenance (WP-0.9 ruling, 19 August 2026)."
            )
        return self

    @model_validator(mode="after")
    def _attribution_agrees_with_the_id(self) -> GatewayRequest:
        """The two fields must say the same thing, or the record would lie."""
        if self.project_attribution is ProjectAttribution.LEGACY_UNKNOWN:
            raise ValueError(
                "LEGACY_UNKNOWN describes rows written before project attribution "
                "existed. It is not a way for new code to avoid deciding scope: "
                "resolve the exchange, or state that it is explicitly outside every "
                "project (04-layer-0.md WP-0.6, corrective round)."
            )
        resolved = self.project_attribution is ProjectAttribution.RESOLVED
        if resolved and self.project_id is None:
            raise ValueError("attribution says RESOLVED but carries no project id")
        if not resolved and self.project_id is not None:
            raise ValueError("attribution says EXPLICIT_NONE but carries a project id")
        return self


class GatewayResponse(BaseModel):
    """What the gateway returns, with the cost already attributed and recorded.

    `terminal` says how the call actually ended; callers that persist the text
    as a Val message must branch on it (`val_gateway.loop` does). `tokens_*` and
    `cost_usd` are `None` exactly when the provider did not report usage — the
    closure pass removed the path where missing usage became a fabricated zero.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    terminal: TerminalState
    model_config_id: UUID
    slug: str
    provider: str
    model_identifier: str
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float | None
    latency_ms: int
    provider_request_id: str | None
    #: Ruling, 8 September 2026: the provider's own terminal fields, verbatim,
    #: for reporting a call that ended with no text by its observed cause.
    stop_reason: str | None = None
    stop_details: str | None = None
    #: WP-0.9, 19 August 2026. The `model_calls` row this call wrote, so
    #: evidence that must name its call — a `blind_positions` row — can name
    #: it without a second query that might not find the same row. None only
    #: when the recorder declined to return an id (test fakes).
    model_call_id: UUID | None = None
    #: Val Core Phase 1 (11 September 2026): milliseconds from the call's start
    #: to the first generated-text delta, when the call was streamed and the
    #: provider produced any text. None for a completed (non-streamed) call and
    #: for a stream that produced no text. Time-to-first-token as observed at
    #: the gateway — not yet what a user sees; that figure is measured at the
    #: interface, separately, once streaming reaches it.
    first_output_ms: int | None = None
