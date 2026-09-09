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

from collections.abc import Callable, Iterable, Sequence
from itertools import pairwise

from val_domain.gateway import (
    Admission,
    CapabilityProfile,
    Classification,
    ModelConfig,
    TaskType,
)

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


#: Ruling, 7 September 2026: which capability profile each kind of work
#: requires. Ordinary conversation and the consequential blind position are
#: Val's partner cognition; classification, stripping, and titling are
#: structured internal work. Task policy names the floor; configurations
#: declare what they satisfy; nothing here names a model.
_REQUIRED_PROFILE: dict[TaskType, CapabilityProfile] = {
    TaskType.CONVERSATION: CapabilityProfile.PARTNER,
    TaskType.BLIND_POSITION: CapabilityProfile.PARTNER,
    TaskType.CLASSIFICATION: CapabilityProfile.STRUCTURED,
    TaskType.STRIP: CapabilityProfile.STRIP,
    TaskType.TITLE: CapabilityProfile.STRUCTURED,
}


def required_profile(task_type: TaskType) -> CapabilityProfile:
    """The capability floor this kind of work requires."""
    return _REQUIRED_PROFILE[task_type]


def satisfies_profile(config: ModelConfig, profile: CapabilityProfile) -> bool:
    """Whether the configuration declares the required profile. Declared, never inferred."""
    return profile in config.capability_profiles


def candidates(
    configs: Iterable[ModelConfig],
    classification: Classification,
    is_ready: Callable[[ModelConfig], bool],
    is_affordable: Callable[[ModelConfig], bool],
    *,
    profile: CapabilityProfile,
    cost_bound: Callable[[ModelConfig], float],
) -> list[ModelConfig]:
    """Every configuration that may carry this request, cheapest first.

    `cost_bound` is the candidate-specific **total** cost bound of the actual
    call — input bound plus output bound at that candidate's rates, the same
    figure reservation and admission use (ruling, 7 September 2026: an
    input-rate-only order is not a cost order). Nothing here invents an
    expected output length; the bound is the task's maximum-output allowance.

    The order of the filters is the ruling of 7 September 2026, restating
    `01-architecture.md` §5.5: eligibility → the task's required capability
    profile → the remaining readiness and budget constraints → cost ordering
    among the routes that satisfy the floor. Cost ranks only what the floor
    has already admitted; it can break ties, never lower the floor.

    An empty list is a truthful answer — no eligible route, or no route that
    satisfies the required profile — and the caller must report it as one. It
    is never a licence to downgrade the content, lower the floor, or reach for
    something unadmitted.
    """
    admitted = [
        config
        for config in configs
        if is_admitted(config)
        and is_eligible(config, classification)
        and satisfies_profile(config, profile)
        and is_ready(config)
        and is_affordable(config)
    ]
    # Cost ranks what eligibility has already admitted, and only that. The
    # slug is a stable last-resort tie-break, not a cost decision: it keeps
    # the same request routing the same way twice, and `true_ties` reports
    # every place it actually decided so the caller can log that it did.
    return sorted(admitted, key=lambda config: (cost_bound(config), config.slug))


def true_ties(
    ordered: Sequence[ModelConfig], cost_bound: Callable[[ModelConfig], float]
) -> list[tuple[str, str, float]]:
    """Adjacent candidates whose total cost bounds are exactly equal.

    Between such a pair the order was decided by the last-resort slug
    tie-break and by nothing else; the caller logs it as a tie, never as a
    cost preference (ruling, 7 September 2026).
    """
    return [
        (first.slug, second.slug, cost_bound(first))
        for first, second in pairwise(ordered)
        if cost_bound(first) == cost_bound(second)
    ]


def attempt_order(
    configs: Iterable[ModelConfig],
    classification: Classification,
    is_ready: Callable[[ModelConfig], bool],
    is_affordable: Callable[[ModelConfig], bool],
    resolve_fallback: Callable[[ModelConfig], ModelConfig | None],
    *,
    profile: CapabilityProfile,
    cost_bound: Callable[[ModelConfig], float],
    on_tie: Callable[[str, str, float], None] | None = None,
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
    ineligible for this content, **below the required capability profile**,
    unready, or unaffordable does not appear in this list at all, because it
    appears only if it passed the same six filters on its own account — which is
    what keeps a partner route's declared structured fallback from ever serving
    a partner task (ruling, 7 September 2026) (`01-architecture.md` §5.4:
    "Fallback routes are checked for eligibility independently. A fallback is
    not inherited.").
    """
    ranked = candidates(
        configs, classification, is_ready, is_affordable, profile=profile, cost_bound=cost_bound
    )
    # Ties are visible only here, among the ranked candidates: the attempt
    # order that follows is the primary plus its declared chain, so a caller
    # that wants to log a true tie is told of it from this list.
    if on_tie is not None:
        for first, second, bound in true_ties(ranked, cost_bound):
            on_tie(first, second, bound)
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
