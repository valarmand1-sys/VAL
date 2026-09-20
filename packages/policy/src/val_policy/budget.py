"""The Layer 0 pre-call budget rule (`01-architecture.md` §5.7).

One hard stop, still: at the ceiling, cloud routing stops. The graduated
thresholds, the reserve, and the cost dashboard remain Layer 3.

**What changed on 17 August 2026, and why.** The rule was

    permit the call if month_to_date_spend < CEILING

which enforces nothing about the call being asked for. At $199.99 of a $200
ceiling it admits a $40 call, and the ceiling is breached by $39.99 *after the
money is spent* — precisely the "reported after" that invariant 24 forbids. A
ceiling enforced against history rather than against the proposed call is not a
pre-call control; it is a post-hoc observation wearing one's clothes.

The rule is now

    permit the call if committed + maximum_cost(this call) <= CEILING

where `committed` is the authoritative month-to-date figure — settled spend plus
every reservation still outstanding — and `maximum_cost` is the most this call
is permitted to consume.

**The estimate is an upper bound, deliberately, and it is arithmetic rather than
a guess.** Input tokens are bounded by the UTF-8 byte length of everything being
sent: a byte-level tokenizer never emits more tokens than there are bytes, so
this cannot under-reserve however the content is encoded. Output is bounded by
the cap the request itself carries. The bound is loose for ordinary English —
roughly four times the true figure — and that is the correct direction to be
wrong in, because the difference is released the moment the call settles
(`val_gateway.ledger`). Reserving too much delays work at the margin; reserving
too little breaches the ceiling.

Pure arithmetic. No clock, no database, no provider.
"""

import math
from collections.abc import Iterable, Sequence

from val_domain.gateway import CacheTtl, ImageInputSupport, ImagePart, ModelConfig

#: The routing ceiling: cloud model inference, per month (01-architecture.md §5.5).
CLOUD_CEILING_USD = 200.00

#: Per-message framing a provider adds around content — role markers and the
#: turn structure. Small, fixed, and counted so the bound stays a bound on short
#: messages, where framing is a larger share of the total than the text is.
#: Deliberately generous: chat framing is two or three tokens per turn in every
#: dialect this house speaks, and over-counting it costs a reservation that is
#: released seconds later.
FRAMING_TOKENS_PER_MESSAGE = 8


def upper_bound_input_tokens(parts: Iterable[str], config: ModelConfig) -> int:
    """The most input tokens this content can possibly be billed as.

    **Bound 1 of 2.** Two claims, and the bound is only sound if both hold:

    1. **A token is never fewer than one byte.** Every tokenizer in use here is
       byte-level BPE: its vocabulary is built over bytes, and the smallest
       token it can emit covers one byte. A string of *n* UTF-8 bytes therefore
       cannot become more than *n* tokens, whatever the script, whatever the
       encoding, however adversarial the input. This is why byte length is used
       and a characters-per-token rule of thumb is not — the rule of thumb is an
       average, and an average is the wrong instrument for a ceiling. It is
       right about a corpus and wrong about the one message that breaches.
    2. **Nothing is billed above the context window.** Content exceeding the
       window is refused by the provider before inference, so capping here
       remains an upper bound rather than becoming an assumption.

    `parts` must be *everything* that will be transmitted — every message body
    and the system prompt. The gateway assembles it with `content_parts`, the
    same function that feeds the Restricted preflight, so the two cannot drift
    apart and leave content that is scanned but not costed.
    """
    return min(raw_input_bound(parts), config.context_window_tokens)


def raw_input_bound(parts: Iterable[str]) -> int:
    """The byte-level input bound, uncapped by any model's window.

    Factored out in the closure pass so limit enforcement (`limit_overrun`) and
    budget pricing (`upper_bound_input_tokens`) compute from the same figure.
    Enforcement needs it *uncapped* — comparing a window-capped value against
    the window would pass by construction — while pricing caps it, because
    nothing above the window is ever billed.
    """
    materialised = list(parts)
    bytes_total = sum(len(part.encode("utf-8")) for part in materialised)
    return bytes_total + FRAMING_TOKENS_PER_MESSAGE * len(materialised)


#: Ruling, 15 September 2026: the default output ceiling of the final PARTNER
#: conversation call. On a reasoning route the ceiling bounds reasoning and
#: visible output together — a 4,096 ceiling let a genuine House Armand turn
#: spend 2,521 tokens reasoning and cut the visible answer at about 1,575,
#: `incomplete_details.reason = max_output_tokens`, no persisted message. The
#: blind-position, strip and classifier ceilings are separate and unchanged; a
#: truncated final response is still never persisted as Val's message and is
#: never retried automatically.
CONVERSATION_MAX_OUTPUT_TOKENS = 6_144


def upper_bound_output_tokens(requested_max_output_tokens: int, config: ModelConfig) -> int:
    """The most output tokens this call can possibly be billed as.

    **Bound 2 of 2, and it is bounded separately for a reason.** Output is not a
    function of the prompt. A three-word question with `max_output_tokens =
    128_000` is authorised to spend $3.20 on Opus 5 — more than four hundred
    times what the input side of that call can cost. A guard that sized a
    reservation from the prompt would wave that through and discover the spend
    afterwards, which is the failure this whole control exists to prevent.

    Two limits apply and the lower one binds:

    - **The request's own cap**, which is what is actually sent to the provider.
      The provider stops generating there.
    - **The configuration's `max_output_tokens`.** `limit_overrun` refuses any
      request asking for more than the model permits *before* transmission, so
      by the time a call is priced the two figures agree — the value budgeted
      is the value sent. (*Corrected in the closure pass, 18 August 2026: this
      docstring used to claim the rejection existed while only the clamp did,
      so budgeting assumed a capped value transmission did not honour.*)

    Reasoning and thinking tokens need no separate term: every provider in this
    registry bills them as output and counts them inside the same cap, so they
    are already inside this number. That holds for the configured efforts too —
    Opus 5 runs at `HIGH` and GPT-5.5 at `MEDIUM` (independent-review
    correction, 18 August 2026), and both providers bill the resulting
    reasoning tokens as ordinary output inside `max_tokens` /
    `max_output_tokens`, which is exactly the cap this bound prices.
    """
    return min(requested_max_output_tokens, config.max_output_tokens)


def limit_overrun(
    config: ModelConfig, parts: Iterable[str], requested_max_output_tokens: int
) -> str | None:
    """Why this request cannot be served by this configuration, or `None`.

    *Closure pass, 18 August 2026.* VAL enforces the model's own limits before
    transmission; the provider's rejection is the backstop, never the mechanism.
    Two checks, and neither clamps:

    1. **Requested output beyond the model's cap is refused**, not silently
       served at the cap. A caller asking for 100k tokens from a 64k model has
       asked for something this route cannot do, and quietly doing less would
       make the authorised bound and the actual request disagree.
    2. **The input bound plus the requested output must fit the context
       window.** The input figure is the same byte-level upper bound the budget
       prices (`upper_bound_input_tokens`, uncapped), so enforcement and
       budgeting cannot drift apart: one function, one estimate.
    """
    if requested_max_output_tokens > config.max_output_tokens:
        return (
            f"{config.slug} supports at most {config.max_output_tokens:,} output tokens "
            f"and this request asks for {requested_max_output_tokens:,}. Refused rather "
            "than clamped: serving less than was asked would make the authorised bound "
            "and the transmitted request disagree."
        )

    input_bound = raw_input_bound(parts)
    if input_bound + requested_max_output_tokens > config.context_window_tokens:
        return (
            f"{config.slug}'s context window is {config.context_window_tokens:,} tokens; "
            f"this request's input bound ({input_bound:,}) plus its requested output "
            f"({requested_max_output_tokens:,}) cannot fit. Refused locally — nothing "
            "was routed, reserved, or transmitted."
        )
    return None


def local_context_overrun(
    config: ModelConfig,
    prompt_tokens: int,
    context_tokens: int,
    requested_max_output_tokens: int,
) -> str | None:
    """Why an exactly measured local request cannot fit its loaded window, or `None`.

    Ruling, 16 September 2026 — the local context preflight, for
    `Metering.LOCAL_NO_METERED_COST` routes only. The byte bound in
    `limit_overrun` is a monetary upper bound and stays the cloud rule and the
    local fail-closed fallback; this is context feasibility on exact figures:

        prompt_tokens + requested_max_output_tokens <= context_tokens

    `prompt_tokens` is the runtime's own count of the serialised prompt and
    `context_tokens` the context of the instance actually loaded — never the
    registry's nominal window. The output reserve is the whole requested
    ceiling: on a reasoning model it covers hidden reasoning and visible text
    together, because the server counts and caps them together. Nothing is
    clamped or trimmed to fit; a request that does not fit is refused in words.
    """
    if requested_max_output_tokens > config.max_output_tokens:
        return (
            f"{config.slug} supports at most {config.max_output_tokens:,} output tokens "
            f"and this request asks for {requested_max_output_tokens:,}. Refused rather "
            "than clamped: serving less than was asked would make the authorised bound "
            "and the transmitted request disagree."
        )
    if prompt_tokens + requested_max_output_tokens > context_tokens:
        return (
            f"{config.slug}: the loaded context is {context_tokens:,} tokens; this request's "
            f"exact serialised prompt ({prompt_tokens:,}) plus its requested output reserve "
            f"({requested_max_output_tokens:,}, reasoning and visible text together) cannot "
            "fit. Refused locally — nothing was routed, reserved, or transmitted; nothing "
            "was shortened to make it fit."
        )
    return None


def image_input_tokens(width: int, height: int, support: ImageInputSupport) -> int:
    """Billable input tokens for one transmitted image, by the provider's formula.

    Owner ruling, 19 September 2026 (Track C). The provider tokenises an image
    as square patches and bills a multiple of the patch count, capping the count
    at the detail level's budget and resizing to fit. Transcribed from
    `support`, which carries the numbers as dated, sourced registry facts:

        patches  = ceil(width / patch_pixels) x ceil(height / patch_pixels)
        billable = ceil(min(patches, patch_budget) x token_multiplier)

    The cap is what makes this **bounded**: whatever arrives, one image cannot
    bill more than `support.max_tokens_per_image`. That is the property a
    reservation needs, and it is why the detail level is declared rather than
    left to the provider's default, which resolves to no budget at all.

    The value is exact for an image inside the budget, and conservative for one
    above it — the provider shrinks such an image before counting, so it bills
    at most the capped figure and usually slightly less.
    """
    patches = math.ceil(width / support.patch_pixels) * math.ceil(height / support.patch_pixels)
    return math.ceil(min(patches, support.patch_budget) * support.token_multiplier)


def upper_bound_image_tokens(images: Sequence[ImagePart], config: ModelConfig) -> int:
    """The bound on every transmitted image of one call. Fails closed.

    A configuration that declares no image input cannot price an image, so a
    call carrying one is refused here rather than reserved at a figure that
    omits it. Under-reserving is how a ceiling stops being a ceiling.
    """
    if not images:
        return 0
    support = config.image_input
    if support is None:
        raise ValueError(
            f"{config.slug} declares no image input, so an image bound cannot be computed; "
            "routing must not have selected it for a turn carrying images"
        )
    return sum(image_input_tokens(image.width, image.height, support) for image in images)


def maximum_cost(
    config: ModelConfig,
    parts: Iterable[str],
    max_output_tokens: int,
    cache_ttl: CacheTtl | None = None,
    *,
    images: Sequence[ImagePart] = (),
) -> float:
    """The most this proposed call is permitted to consume, in USD.

    **Ruling, 8 September 2026 — the formula is widened for caching, as the
    warning below required.** When the call requests a prompt cache for
    `cache_ttl`, every input token is bounded at the **greater** of the base
    input rate and that lifetime's cache-write rate: the maximum legitimate
    cost state is a miss that writes the whole prefix at the write premium.
    Nothing assumes a hit. The reservation is therefore never smaller than
    the bill, and the difference is returned at settlement like any other
    unspent reservation.

    This is the figure the ceiling is enforced against and the amount reserved
    before the provider is contacted. **It is a bound, not an estimate** — the
    difference matters, because an estimate that is usually right is exactly
    wrong at a ceiling.

        maximum_cost = (upper_bound_input_tokens  x cost_per_mtok_in
                      + upper_bound_output_tokens x cost_per_mtok_out) / 1e6

    The two terms are bounded independently — see each function — because they
    are independent exposures. Neither constrains the other.

    **Every provider-billable component at Layer 0 is in that sum, and this list
    is the proof rather than an assurance:**

    | Component | Billable now? | Where it is bounded |
    |---|---|---|
    | Input tokens | **Yes** | Term 1 |
    | Output tokens | **Yes** | Term 2 |
    | Reasoning / thinking tokens | Yes, as output | Inside term 2's cap |
    | Prompt-cache **writes** | **No** — never requested | See the warning below |
    | Prompt-cache reads | No — never requested, and cheaper than base input |  |
    | Batch submissions | No — never requested, and cheaper |  |
    | **Image input** | **Yes**, since 19 September 2026 | Term 1, via
      `upper_bound_image_tokens`: capped per image by the route's declared
      patch budget, and refused on a route that declares none |
    | Audio, video, documents | No — no part type carries them yet |  |
    | Tool or web-search calls | No — no tool exists until Layer 2 |  |
    | Per-request or storage fees | No — none in these providers' pricing |  |

    > **The one way this bound can be broken, written down before it can happen.**
    > A prompt-cache *write* is billed **above** the base input rate — a quarter
    > again, on the dialects this house speaks. Every other unbilled row above is
    > either free or cheaper than what is already counted, so enabling it can only
    > make the bound looser. Caching is the exception, and it is the one
    > `01-architecture.md` §5.3 says becomes first-class later. **Whoever enables
    > caching must widen this formula in the same change**, and the registry's
    > `caching` field is `NOT_VERIFIED` on every entry precisely so that nobody
    > can switch it on believing it was already accounted for.
    """
    # Widened for image input exactly as the caching warning below required of
    # caching: the component is counted in the same change that enables it.
    tokens_in = upper_bound_input_tokens(parts, config) + upper_bound_image_tokens(images, config)
    tokens_out = upper_bound_output_tokens(max_output_tokens, config)
    rate_in, rate_out = effective_rates(config, tokens_in)
    # The long-context multiplier stacks on cache rates as it does on the base
    # rate (the provider's pricing page: multipliers stack). Ruling, 16
    # September 2026: an unmetered local route has a zero base rate and, by
    # its validator, no cache pricing, so there is no multiplier to derive and
    # the bound is exactly zero — the ledger still reserves it, at $0.
    multiplier = 1.0 if config.cost_per_mtok_in_usd == 0 else rate_in / config.cost_per_mtok_in_usd
    if config.caches_automatically and config.cache_write_auto_per_mtok_in_usd is not None:
        # Ruling, 14 September 2026: a provider that caches on its own may
        # write every cache-eligible input token on a cold call, and this house
        # cannot ask it not to. The legitimate expensive state is therefore the
        # whole input written at the automatic write rate; nothing assumes a hit.
        rate_in = max(rate_in, config.cache_write_auto_per_mtok_in_usd * multiplier)
    elif cache_ttl is not None:
        rate_in = max(rate_in, config.cache_write_rate(cache_ttl) * multiplier)
    return (tokens_in * rate_in + tokens_out * rate_out) / 1_000_000


def effective_rates(config: ModelConfig, tokens_in: int) -> tuple[float, float]:
    """The per-mtok rates that actually apply at this input size.

    *Closure pass, 18 August 2026.* Some providers re-price the whole call above
    an input threshold — GPT-5.5 bills 2x input and 1.5x output for the full
    session once input exceeds 272K tokens. A ceiling computed at base rates
    would under-reserve exactly the largest calls, which is the ceiling failing
    where it matters most. The threshold and multipliers come from the registry
    entry, never from code, and both the pre-call bound (which feeds this an
    *upper-bound* input figure — conservative, since crossing the threshold only
    raises the price) and the post-call settlement (which feeds it the real
    figure) use this one function, so the two cannot disagree about what a
    token costs.
    """
    threshold = config.long_context_threshold_tokens
    if threshold is not None and tokens_in > threshold:
        return (
            config.cost_per_mtok_in_usd * config.long_context_in_multiplier,
            config.cost_per_mtok_out_usd * config.long_context_out_multiplier,
        )
    return config.cost_per_mtok_in_usd, config.cost_per_mtok_out_usd


def remaining_usd(committed_usd: float) -> float:
    """Authorised spend still available this month. Never negative."""
    return max(CLOUD_CEILING_USD - committed_usd, 0.0)


def admits(committed_usd: float, maximum_cost_usd: float) -> bool:
    """Whether a call permitted to consume this much may be admitted.

    The comparison is against the *proposed* call, which is the whole point:
    `committed < CEILING` was true in every case this rule now refuses.
    """
    return committed_usd + maximum_cost_usd <= CLOUD_CEILING_USD


def admits_exchange(
    exchange_committed_usd: float, maximum_cost_usd: float, envelope_usd: float | None
) -> bool:
    """Whether one more call fits inside its user exchange's spending envelope.

    Ruling, 13 September 2026. `exchange_committed_usd` is what the exchange has
    already claimed — settled calls at their settled cost, outstanding or expired
    reservations at their maximum — and `maximum_cost_usd` is the proposed
    call's bound, never an expected actual. `None` is the disabled envelope,
    the default: nothing is refused on the exchange's account.
    """
    if envelope_usd is None:
        return True
    return exchange_committed_usd + maximum_cost_usd <= envelope_usd


def exchange_envelope_message(
    exchange_committed_usd: float, maximum_cost_usd: float, envelope_usd: float
) -> str:
    """What Val says when the exchange envelope has stopped the next call."""
    return (
        f"I have not made that call, my lord. This exchange has already committed "
        f"${exchange_committed_usd:.4f}, the next call is authorised to consume up to "
        f"${maximum_cost_usd:.4f}, and together they exceed the ${envelope_usd:.4f} "
        "envelope set for a single exchange. I will not substitute a cheaper "
        "configuration to fit it; going on needs your authorisation."
    )


def ceiling_message(committed_usd: float, maximum_cost_usd: float) -> str:
    """What Val says, plainly, when the ceiling has stopped this call.

    It states the arithmetic rather than announcing a policy, because the
    difference between "you are out of money" and "this particular call does not
    fit in what is left" is one Lord Armand can act on.
    """
    remaining = remaining_usd(committed_usd)
    return (
        f"I have not made that call, my lord. It is authorised to consume up to "
        f"${maximum_cost_usd:.2f}, and only ${remaining:.2f} of the "
        f"${CLOUD_CEILING_USD:.2f} monthly cloud ceiling is left — "
        f"${committed_usd:.2f} is already committed this month. The ceiling is "
        "enforced before a call, never reported after it (00-charter.md "
        "invariant 24). It resets at the start of next month, and I cannot "
        "degrade to local inference until Layer 1, so cloud-model work waits "
        "(01-architecture.md §5.6, §5.7)."
    )


def no_affordable_route_message(committed_usd: float) -> str:
    """What Val says when nothing eligible fits in what is left."""
    return (
        f"No configured route fits within what is left of the monthly cloud "
        f"ceiling: ${remaining_usd(committed_usd):.2f} remains of "
        f"${CLOUD_CEILING_USD:.2f}. I will not reclassify the work or reach for "
        "an unadmitted provider to get around it."
    )
