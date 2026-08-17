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

from collections.abc import Iterable

from val_domain.gateway import ModelConfig

#: The routing ceiling: cloud model inference, per month (01-architecture.md §5.5).
CLOUD_CEILING_USD = 200.00

#: Per-message framing a provider adds around content — role markers and the
#: turn structure. Small, fixed, and counted so the bound stays a bound on short
#: messages, where framing is a larger share of the total than the text is.
FRAMING_TOKENS_PER_MESSAGE = 8


def upper_bound_input_tokens(parts: Iterable[str], config: ModelConfig) -> int:
    """The most input tokens this content can possibly become.

    UTF-8 byte length, not a characters-per-token rule of thumb. The rule of
    thumb is an average, and an average is the wrong instrument for a ceiling:
    it is right about a corpus and wrong about the one message that breaches.

    Capped at the configuration's context window, which is still an upper bound
    — content exceeding the window is rejected by the provider, so no call can
    charge for more input than the window holds.
    """
    materialised = list(parts)
    bytes_total = sum(len(part.encode("utf-8")) for part in materialised)
    framing = FRAMING_TOKENS_PER_MESSAGE * len(materialised)
    return min(bytes_total + framing, config.context_window_tokens)


def maximum_cost(config: ModelConfig, parts: Iterable[str], max_output_tokens: int) -> float:
    """The most this proposed call is permitted to consume, in USD.

    This is the figure the ceiling is enforced against and the amount reserved
    before the provider is contacted — not an estimate of what the call will
    probably cost.
    """
    tokens_in = upper_bound_input_tokens(parts, config)
    tokens_out = min(max_output_tokens, config.max_output_tokens)
    return (
        tokens_in * config.cost_per_mtok_in_usd + tokens_out * config.cost_per_mtok_out_usd
    ) / 1_000_000


def remaining_usd(committed_usd: float) -> float:
    """Authorised spend still available this month. Never negative."""
    return max(CLOUD_CEILING_USD - committed_usd, 0.0)


def admits(committed_usd: float, maximum_cost_usd: float) -> bool:
    """Whether a call permitted to consume this much may be admitted.

    The comparison is against the *proposed* call, which is the whole point:
    `committed < CEILING` was true in every case this rule now refuses.
    """
    return committed_usd + maximum_cost_usd <= CLOUD_CEILING_USD


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
