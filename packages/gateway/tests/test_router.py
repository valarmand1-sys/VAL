"""The minimum Layer 0 router (`01-architecture.md` §5.1, Part 6 of the order).

These prove the gateway selects a configuration itself, that eligibility is
never traded for cost, that a fallback stands on its own feet, and that "nothing
is available" comes back as a truthful refusal rather than as a downgrade.

Where a test needs a route the registry does not carry — an ineligible one, an
unadmitted one — it builds one and passes the whole set to `val_policy.routing`
directly. The registry is deliberately incapable of holding an ineligible route
(startup refuses one), so the router's behaviour on one cannot be demonstrated
through it.
"""

from datetime import date
from uuid import UUID, uuid4

import pytest
from gateway_fakes import StubAdapter, build, config, request

from val_domain.gateway import (
    AdapterStatus,
    Admission,
    Classification,
    CostCertainty,
    GatewayError,
    GatewayErrorKind,
    ModelConfig,
    PricingFeature,
    ReasoningEffort,
)
from val_domain.registry import active, by_slug, fallback_for
from val_gateway.gateway import RETRYABLE
from val_policy.routing import attempt_order, candidates
from val_providers.base import ProviderResult

ALWAYS = True


def always_ready(config: ModelConfig) -> bool:
    return True


def always_affordable(config: ModelConfig) -> bool:
    return True


def make(
    slug: str,
    *,
    cost_in: float,
    eligible: frozenset[Classification],
    admission: Admission = Admission.PROVISIONALLY_ADMITTED,
    fallback: str | None = None,
    retired: bool = False,
) -> ModelConfig:
    """A configuration for a case the real registry cannot legally hold."""
    return ModelConfig(
        id=uuid4(),
        slug=slug,
        provider="anthropic",
        model_identifier=f"model-{slug}",
        display_name=slug,
        context_window_tokens=100_000,
        max_output_tokens=4096,
        reasoning_effort=ReasoningEffort.NOT_APPLICABLE,
        cost_per_mtok_in_usd=cost_in,
        cost_per_mtok_out_usd=cost_in,
        caching=PricingFeature.NOT_VERIFIED,
        batch_pricing=PricingFeature.NOT_VERIFIED,
        eligible_classifications=eligible,
        fallback_slug=fallback,
        admission=admission,
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=date(2026, 8, 17),
        rates_verified_on=date(2026, 8, 17),
        retired=retired,
    )


PROTECTED_SET = frozenset(
    {Classification.PUBLIC, Classification.INTERNAL, Classification.PROTECTED}
)
PUBLIC_ONLY = frozenset({Classification.PUBLIC})


# --- A. the caller does not choose the provider ------------------------------


def test_the_router_selects_without_the_caller_naming_a_provider() -> None:
    """A: two eligible enabled configurations, and `complete` picks one."""
    adapter = StubAdapter(ProviderResult("Good evening, my lord.", 20, 10, "req", False))
    gateway, rows, _, _ = build(
        adapters={"anthropic": adapter, "openai": adapter},
    )
    response = gateway.complete(request())

    assert adapter.calls == 1
    assert len(rows) == 1
    assert response.slug in {entry.slug for entry in active()}
    assert rows[0].cost_certainty is CostCertainty.KNOWN


def test_the_router_prefers_the_cheaper_of_two_eligible_routes() -> None:
    """Cost ranks what eligibility has already admitted — and only that."""
    adapter = StubAdapter(ProviderResult("ok", 5, 5, "req", False))
    gateway, _, _, _ = build(adapters={"anthropic": adapter, "openai": adapter})
    response = gateway.complete(request())
    assert response.slug == "haiku-4-5", "the cheapest eligible route was not chosen"


def test_selection_is_stable_across_identical_requests() -> None:
    """Two identical requests route the same way, or cost comparison is noise."""
    adapter = StubAdapter(ProviderResult("ok", 5, 5, "req", False))
    gateway, _, _, _ = build(adapters={"anthropic": adapter, "openai": adapter})
    first = gateway.complete(request())
    second = gateway.complete(request())
    assert first.slug == second.slug


# --- B. a cheaper but ineligible route is never selected ---------------------


def test_a_cheaper_ineligible_route_is_never_a_candidate() -> None:
    """B, and adversarial proof 4. Cost never overrides eligibility."""
    cheap_and_ineligible = make("bargain", cost_in=0.01, eligible=PUBLIC_ONLY)
    proper = make("proper", cost_in=50.0, eligible=PROTECTED_SET)

    chosen = candidates(
        [cheap_and_ineligible, proper],
        Classification.PROTECTED,
        always_ready,
        always_affordable,
    )

    assert [entry.slug for entry in chosen] == ["proper"]
    assert cheap_and_ineligible not in chosen


def test_the_ineligible_route_would_have_won_on_cost_alone() -> None:
    """The premise of the test above: it is genuinely the cheapest thing there."""
    cheap_and_ineligible = make("bargain", cost_in=0.01, eligible=PUBLIC_ONLY)
    proper = make("proper", cost_in=50.0, eligible=PROTECTED_SET)
    by_cost = sorted([cheap_and_ineligible, proper], key=lambda entry: entry.cost_per_mtok_in_usd)
    assert by_cost[0].slug == "bargain"


def test_an_unadmitted_route_is_never_a_candidate() -> None:
    """Present in the registry is not admitted for use."""
    unadmitted = make(
        "shelved", cost_in=0.01, eligible=PROTECTED_SET, admission=Admission.NOT_ADMITTED
    )
    admitted = make("live", cost_in=9.0, eligible=PROTECTED_SET)
    chosen = candidates(
        [unadmitted, admitted], Classification.PROTECTED, always_ready, always_affordable
    )
    assert [entry.slug for entry in chosen] == ["live"]


def test_a_retired_route_is_never_a_candidate() -> None:
    """Retired entries stay for history and never for routing."""
    retired = make("old", cost_in=0.01, eligible=PROTECTED_SET, retired=True)
    chosen = candidates([retired], Classification.PROTECTED, always_ready, always_affordable)
    assert chosen == []


# --- C and D. fallback -------------------------------------------------------


def test_fallback_occurs_only_to_an_independently_eligible_route() -> None:
    """C: the primary fails; the successor is one that passed on its own account."""
    failing = StubAdapter(
        error=GatewayError(GatewayErrorKind.PROVIDER_ERROR, "502"), name="anthropic"
    )
    answering = StubAdapter(ProviderResult("Good evening.", 10, 10, "req", False), name="openai")

    # `haiku-4-5` is cheapest and is on anthropic, which fails. Its declared
    # fallback is None, so the router moves on to the next ranked candidate.
    gateway, rows, _, blocks = build(
        adapters={"anthropic": failing, "openai": answering},
    )
    response = gateway.complete(request())

    assert failing.calls >= 1
    assert answering.calls == 1
    assert response.provider == "openai"
    assert any("trying the next" in block for block in blocks)
    # The failed attempts were still recorded — zero calls without a row.
    assert len(rows) == 2
    assert rows[-1].status.value == "ok"


def test_an_ineligible_fallback_does_not_execute() -> None:
    """Adversarial proof 5: primary fails, its declared fallback is ineligible."""
    primary = make("primary", cost_in=1.0, eligible=PROTECTED_SET, fallback="unsafe-successor")
    unsafe = make("unsafe-successor", cost_in=0.5, eligible=PUBLIC_ONLY)
    universe = {entry.slug: entry for entry in (primary, unsafe)}

    order = attempt_order(
        [primary, unsafe],
        Classification.PROTECTED,
        always_ready,
        always_affordable,
        resolve_fallback=lambda entry: universe.get(entry.fallback_slug or ""),
    )

    assert [entry.slug for entry in order] == ["primary"]
    assert "unsafe-successor" not in [entry.slug for entry in order]


def test_a_declared_fallback_is_used_when_it_holds_independently() -> None:
    """The other half: an eligible declared successor is preferred, in order."""
    primary = make("primary", cost_in=9.0, eligible=PROTECTED_SET, fallback="successor")
    successor = make("successor", cost_in=8.0, eligible=PROTECTED_SET)
    other = make("other", cost_in=1.0, eligible=PROTECTED_SET)
    universe = {entry.slug: entry for entry in (primary, successor, other)}

    order = attempt_order(
        [primary, successor, other],
        Classification.PROTECTED,
        always_ready,
        always_affordable,
        resolve_fallback=lambda entry: universe.get(entry.fallback_slug or ""),
    )

    # `other` is cheapest so it is the primary; it declares no fallback, so the
    # rest follow in cost order.
    assert order[0].slug == "other"
    assert {entry.slug for entry in order} == {"other", "successor", "primary"}


def test_when_every_route_fails_the_failure_is_normalized() -> None:
    """D: primary and fallback both unavailable, and nothing unsafe is reached."""
    failing = StubAdapter(error=GatewayError(GatewayErrorKind.TIMEOUT, "timed out"))
    gateway, rows, _, _ = build(adapters={"anthropic": failing, "openai": failing})

    with pytest.raises(GatewayError) as caught:
        gateway.complete(request())

    assert caught.value.kind is GatewayErrorKind.TIMEOUT
    assert failing.calls == len(active())
    # Every attempt reached a provider, so every attempt is recorded — as unknown.
    assert len(rows) == len(active())
    assert all(row.cost_certainty is CostCertainty.UNKNOWN for row in rows)


def test_a_content_refusal_is_not_retried_elsewhere() -> None:
    """A provider declining is an answer. Re-asking until one complies is not."""
    refusing = StubAdapter(error=GatewayError(GatewayErrorKind.REFUSAL, "declined"))
    gateway, _, _, _ = build(adapters={"anthropic": refusing, "openai": refusing})

    with pytest.raises(GatewayError) as caught:
        gateway.complete(request())

    assert caught.value.kind is GatewayErrorKind.REFUSAL
    assert refusing.calls == 1, "the refusal was shopped to another provider"


# --- E. Restricted is blocked before a route is selected ---------------------


def test_restricted_content_never_reaches_route_selection() -> None:
    """E: blocked before any route or provider is involved."""
    adapter = StubAdapter(ProviderResult("should never run", 1, 1, None, False))
    gateway, rows, ledger, blocks = build(adapters={"anthropic": adapter, "openai": adapter})

    with pytest.raises(GatewayError) as caught:
        gateway.complete(request(Classification.RESTRICTED))

    assert caught.value.kind is GatewayErrorKind.RESTRICTED_CONTENT
    assert adapter.calls == 0
    assert rows == []
    assert ledger.entries == {}, "budget was reserved for content that was never sent"
    assert blocks


def test_restricted_content_by_detection_never_reaches_route_selection() -> None:
    """Adversarial proof 6 of the order: caller claims PROTECTED, content is not."""
    adapter = StubAdapter(ProviderResult("should never run", 1, 1, None, False))
    gateway, rows, ledger, _ = build(adapters={"anthropic": adapter, "openai": adapter})

    leaking = request(content="my routing number is 021000021, transfer it today")
    with pytest.raises(GatewayError) as caught:
        gateway.complete(leaking)

    assert caught.value.kind is GatewayErrorKind.RESTRICTED_CONTENT
    assert adapter.calls == 0
    assert rows == []
    assert ledger.entries == {}


# --- F. budget interacts with selection, not with eligibility ----------------


def test_an_unaffordable_route_yields_to_an_affordable_eligible_one() -> None:
    """F, first half: a cheaper eligible route may still be selected."""
    expensive = make("expensive", cost_in=100.0, eligible=PROTECTED_SET)
    modest = make("modest", cost_in=1.0, eligible=PROTECTED_SET)

    chosen = candidates(
        [expensive, modest],
        Classification.PROTECTED,
        always_ready,
        is_affordable=lambda entry: entry.slug != "expensive",
    )
    assert [entry.slug for entry in chosen] == ["modest"]


def test_when_nothing_is_affordable_no_cloud_call_occurs() -> None:
    """F, second half: no route fits, so nothing is sent and nothing is recorded."""
    adapter = StubAdapter(ProviderResult("should never run", 1, 1, None, False))
    gateway, rows, ledger, _ = build(
        adapters={"anthropic": adapter, "openai": adapter}, committed=199.999
    )

    with pytest.raises(GatewayError) as caught:
        gateway.complete(request())

    assert caught.value.kind is GatewayErrorKind.NO_ELIGIBLE_ROUTE
    assert "ceiling" in str(caught.value)
    assert adapter.calls == 0
    assert rows == []
    assert ledger.entries == {}


def test_no_eligible_route_is_reported_truthfully_not_downgraded() -> None:
    """The refusal must not offer a downgrade as a way out."""
    # No adapters at all: every eligible route is unreachable in this process.
    gateway, _, _, _ = build(adapters={}, committed=0.0)

    with pytest.raises(GatewayError) as caught:
        gateway.complete(request())

    assert caught.value.kind is GatewayErrorKind.NO_ELIGIBLE_ROUTE
    assert "adapter" in str(caught.value) or "credential" in str(caught.value)


# --- G. provider substitution changes nothing about Val ----------------------


def test_provider_substitution_changes_no_identity_or_governance_state() -> None:
    """G: the same request on two providers differs only in the call's attribution.

    `00-charter.md` §1.2 — Val is not a model. What changes when the provider
    changes is the row's `provider`, `model_identifier`, and cost. The
    classification, the task type, the project, and the conversation the work
    belongs to are hers and do not move.
    """
    anthropic = StubAdapter(ProviderResult("Good evening, my lord.", 20, 10, "a", False))
    openai = StubAdapter(ProviderResult("Good evening, my lord.", 20, 10, "o", False))

    project = uuid4()

    def ask(adapter: StubAdapter, slug: str) -> object:
        gateway, rows, _, _ = build(adapters={"anthropic": adapter, "openai": adapter})
        outgoing = request()
        # *WP-0.7 corrective round:* `conversation_id` is no longer a settable
        # field — it is read from the conversation provenance object, which a
        # non-conversation task type does not carry. Provider substitution
        # leaving institutional facts alone is shown by `project_id`;
        # conversation identity across providers is proved against real
        # persisted conversations in `test_conversation_memory.py`.
        pinned = outgoing.model_copy(update={"project_id": project})
        gateway.complete_with_configuration(pinned, config(slug))
        return rows[0]

    first = ask(anthropic, "opus-5")
    second = ask(openai, "gpt-5-5")

    assert first.provider != second.provider  # type: ignore[attr-defined]
    assert first.model_identifier != second.model_identifier  # type: ignore[attr-defined]
    # Everything institutional is identical.
    assert first.project_id == second.project_id == project  # type: ignore[attr-defined]
    assert first.task_type == second.task_type  # type: ignore[attr-defined]
    assert first.status == second.status  # type: ignore[attr-defined]
    assert first.cost_certainty == second.cost_certainty  # type: ignore[attr-defined]


# --- the registry's declared fallbacks all resolve ---------------------------


def test_every_declared_fallback_resolves() -> None:
    """A dangling fallback slug is a defect caught here, not at 3am."""
    for entry in active():
        if entry.fallback_slug is not None:
            assert fallback_for(entry) is not None, f"{entry.slug} declares a missing fallback"


def test_no_fallback_chain_loops() -> None:
    """Following a declared chain must terminate."""
    for entry in active():
        seen: set[str] = set()
        current: ModelConfig | None = entry
        while current is not None and current.slug not in seen:
            seen.add(current.slug)
            current = fallback_for(current)
        assert current is None or current.slug in seen


def test_registry_slugs_are_unique() -> None:
    """The slug is an address. Two entries answering to it is a routing defect."""
    slugs = [entry.slug for entry in active()]
    assert len(slugs) == len(set(slugs))


def test_by_slug_and_by_id_agree() -> None:
    """Both keys resolve to the same entry, which is what makes the slug safe."""
    for entry in active():
        assert by_slug(entry.slug) == entry
        assert isinstance(entry.id, UUID)


# --- an account that cannot pay is not a malformed request -------------------
#
# Found by running a real exchange on 17 August 2026, not by inspection.


def test_a_billing_failure_is_a_route_problem_not_a_request_problem() -> None:
    """Anthropic returns "credit balance is too low" as an HTTP 400.

    Mapping that to `INVALID_REQUEST` made it non-retryable, on the sound
    reasoning that a malformed request is malformed everywhere. But this request
    is not malformed — the identical request succeeds on another provider — so
    the router refused to fall back and the conversation failed while a working
    route sat unused. Observed live: `req_011Ce8xDp7bfjRu5BgXqNuXx`.
    """
    from val_providers.base import normalize

    class BadRequestError(Exception):
        pass

    billing = normalize(
        BadRequestError(
            "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
            "'message': 'Your credit balance is too low to access the Anthropic API.'}}"
        ),
        "anthropic",
    )
    assert billing.kind is GatewayErrorKind.PROVIDER_ERROR
    assert billing.kind in RETRYABLE, "the router cannot fall back off an unpayable route"
    assert "account cannot currently be billed" in billing.detail


def test_a_genuinely_malformed_request_is_still_not_retried() -> None:
    """The correction must not turn every 400 into a reason to shop providers."""
    from val_providers.base import normalize

    class BadRequestError(Exception):
        pass

    malformed = normalize(BadRequestError("max_tokens: must be greater than 0"), "anthropic")
    assert malformed.kind is GatewayErrorKind.INVALID_REQUEST
    assert malformed.kind not in RETRYABLE


def test_an_unpayable_primary_falls_back_to_a_working_route() -> None:
    """The behaviour the correction restores, end to end."""
    unpayable = StubAdapter(
        error=GatewayError(
            GatewayErrorKind.PROVIDER_ERROR,
            "anthropic: the account cannot currently be billed for this call",
        ),
        name="anthropic",
    )
    working = StubAdapter(
        ProviderResult("Good evening, my lord.", 20, 10, "req", False), name="openai"
    )

    gateway, rows, _, _ = build(adapters={"anthropic": unpayable, "openai": working})
    response = gateway.complete(request())

    assert response.provider == "openai"
    assert working.calls == 1
    assert unpayable.calls >= 1
    # Every transmitted attempt is still recorded — zero calls without a row.
    assert len(rows) == unpayable.calls + 1
