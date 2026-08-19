"""Which configurations may carry this request, and in what order.

The smallest router `01-architecture.md` §5.1 will admit: it selects among
*configurations*, never among raw models, and it decides on nothing Layer 0
cannot legitimately know. Pure functions over domain types — no adapters, no
clock, no database — because `policy` must stay callable and correct with no
application running (`01-architecture.md` §3).

**Five filters, in this order, and the order is the argument.**

1. **Enabled** — present and not retired in the registry (§5.2.1).
2. **Admitted for Layer 0** — `PROVISIONALLY_ADMITTED` or better. A
   configuration that exists is not a configuration that may carry traffic.
3. **Eligible for this content's classification** — invariant 17. Restricted
   never reaches this function at all; the gateway refuses it earlier, and
   there is no local route to send it to until Layer 1.
4. **Ready** — an adapter is implemented *and* the running process holds a
   credential for its provider. Readiness is supplied by the caller because it
   is a fact about the environment, not about policy.
5. **Affordable** — the reservation this call would need still fits under the
   ceiling. Supplied by the caller for the same reason.

**Cost orders what survives; it never admits anything.** Ranking happens only
inside the already-eligible set, which is what `04-layer-0.md` §1.1 permits and
is only safe because that set contains no ineligible option to be tempted by.
Sorting before filtering would be the same code with the invariant inverted.

**What this deliberately does not do.** No prediction-ledger arbitration, no
Role-specific routing, no local-inference tier, no graduated budget gradient,
no dynamic provider installation. Those are Layers 1, 3, and 5.
"""

from collections.abc import Callable, Iterable

from val_domain.gateway import Admission, Classification, ModelConfig

#: Admission states that may carry Layer 0 traffic. `QUALIFIED` is included
#: because it is strictly stronger, not because anything holds it — nothing
#: does, and nothing may until the §5.2.1 exam suite exists at Layers 2-3.
ROUTABLE_ADMISSION = frozenset({Admission.PROVISIONALLY_ADMITTED, Admission.QUALIFIED})


def is_admitted(config: ModelConfig) -> bool:
    """Whether this configuration is admitted for Layer 0 use."""
    return not config.retired and config.admission in ROUTABLE_ADMISSION


def is_eligible(config: ModelConfig, classification: Classification) -> bool:
    """Whether this configuration may receive content of this classification.

    Restricted is refused outright rather than looked up. A configuration
    declaring Restricted eligibility would already have stopped startup
    (`eligibility.startup_violations`); refusing here as well means a registry
    edited at runtime still cannot open the path.
    """
    if classification is Classification.RESTRICTED:
        return False
    return classification in config.eligible_classifications


def candidates(
    configs: Iterable[ModelConfig],
    classification: Classification,
    is_ready: Callable[[ModelConfig], bool],
    is_affordable: Callable[[ModelConfig], bool],
) -> list[ModelConfig]:
    """Every configuration that may carry this request, cheapest first.

    An empty list is a truthful answer — no eligible route — and the caller
    must report it as one. It is never a licence to downgrade the content or to
    reach for something unadmitted.
    """
    admitted = [
        config
        for config in configs
        if is_admitted(config)
        and is_eligible(config, classification)
        and is_ready(config)
        and is_affordable(config)
    ]
    # Cost ranks what eligibility has already admitted, and only that. The tie
    # break on slug keeps the order stable, so the same request routes the same
    # way twice — a router that reshuffles equal candidates makes every cost
    # comparison across days meaningless.
    return sorted(admitted, key=lambda config: (config.cost_per_mtok_in_usd, config.slug))


def attempt_order(
    configs: Iterable[ModelConfig],
    classification: Classification,
    is_ready: Callable[[ModelConfig], bool],
    is_affordable: Callable[[ModelConfig], bool],
    resolve_fallback: Callable[[ModelConfig], ModelConfig | None],
) -> list[ModelConfig]:
    """The order routes are tried: the primary, then its declared chain. Nothing else.

    The primary is the cheapest surviving candidate. If it declares a fallback
    and that fallback **independently** survives every filter above, it is tried
    next, and so on down the declared chain; otherwise the order ends there.

    **A route with no declared fallback has no fallback.** *Corrected in the
    current-version closure pass, 18 August 2026.* This function used to append
    every remaining candidate in cost order after the declared chain, so
    `fallback_slug=None` fell through to whatever else was ranked — which is
    exactly the behaviour a declared NONE exists to forbid. "Another provider is
    technically available" is not "this request is authorised to fall back to
    it": the registry declaration is the authorisation, and an undeclared
    fallback is an unauthorised one. Degrade-rather-than-halt still holds
    wherever a fallback is actually declared; where none is, the honest outcome
    is a truthful failure.

    Nothing is inherited. A declared fallback that is retired, unadmitted,
    ineligible for this content, unready, or unaffordable does not appear in
    this list at all, because it appears only if it passed the same five filters
    on its own account (`01-architecture.md` §5.4: "Fallback routes are checked
    for eligibility independently. A fallback is not inherited.").
    """
    ranked = candidates(configs, classification, is_ready, is_affordable)
    if not ranked:
        return []

    permitted = {config.slug: config for config in ranked}
    order: list[ModelConfig] = [ranked[0]]
    seen = {ranked[0].slug}

    # Follow the declared fallback chain as far as it independently holds.
    current: ModelConfig | None = ranked[0]
    while current is not None:
        declared = resolve_fallback(current)
        if declared is None or declared.slug in seen:
            break
        # `permitted` membership is the independent re-check: it contains only
        # configurations that passed all five filters on their own account.
        successor = permitted.get(declared.slug)
        if successor is None:
            break
        order.append(successor)
        seen.add(successor.slug)
        current = successor

    return order
