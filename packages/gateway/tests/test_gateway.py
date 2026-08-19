"""Tests for the Model Gateway.

Every provider is a stub here: these test the gateway's own guarantees — one
normalized contract, a row per call and never a row without one, the budget
enforced against the call before it is made, Restricted refused without a row —
not whether Anthropic's SDK works.
"""

from datetime import date
from uuid import UUID, uuid4

import pytest
from gateway_fakes import FakeLedger, StubAdapter, build, config, request

from val_domain.gateway import (
    CallStatus,
    Classification,
    CostCertainty,
    GatewayError,
    GatewayErrorKind,
    GatewayRequest,
    Message,
    TaskType,
    TerminalState,
)
from val_domain.project import ProjectAttribution
from val_gateway.gateway import Gateway, check_startup, compute_cost
from val_policy.budget import CLOUD_CEILING_USD, maximum_cost
from val_providers.base import ProviderResult

# --- cost is computed at call time, from the configuration's rates ------------


def test_cost_is_computed_from_the_configuration_rates() -> None:
    """1M in and 1M out on Opus 5 is $5 + $25."""
    assert compute_cost(config(), 1_000_000, 1_000_000) == pytest.approx(30.00)


def test_cost_scales_linearly() -> None:
    """A thousandth of the tokens is a thousandth of the cost."""
    assert compute_cost(config(), 1_000, 1_000) == pytest.approx(0.030)


# --- every call writes a row -------------------------------------------------


def test_a_successful_call_writes_one_row_with_cost_project_and_task_type() -> None:
    """The WP-0.4 criterion: cost, project, and task type populated.

    *WP-0.7 corrective round:* the shared `request()` builder now defaults to
    `CLASSIFICATION`, because a conversation call must carry the conversation
    and the persisted user message that caused it, and these budget and
    recording tests have neither. What is under test — that the task type
    reaches the row — is unchanged.
    """
    adapter = StubAdapter(
        ProviderResult("Good evening, my lord.", TerminalState.COMPLETE, 1000, 500, "req_1")
    )
    gateway, rows, _, _ = build(adapter)
    response = gateway.complete_with_configuration(request(), config())

    assert len(rows) == 1
    row = rows[0]
    assert row.cost_usd == pytest.approx(compute_cost(config(), 1000, 500))
    assert row.cost_certainty is CostCertainty.KNOWN
    assert row.project_id is not None
    assert row.task_type == "classification"
    assert row.status is CallStatus.OK
    assert row.slug == "opus-5"
    assert response.cost_usd == row.cost_usd


def test_a_refusal_is_recorded_as_refused_not_as_an_error() -> None:
    """A refusal is a content outcome; the call happened and cost money."""
    adapter = StubAdapter(ProviderResult("", TerminalState.REFUSED, 800, 0, "req_2"))
    gateway, rows, _, _ = build(adapter)
    gateway.complete_with_configuration(request(), config())
    assert rows[0].status is CallStatus.REFUSED
    assert rows[0].cost_certainty is CostCertainty.KNOWN


# --- accounting: the three states, and never a factual zero ------------------


def test_a_provider_error_without_usage_records_unknown_not_zero() -> None:
    """The SENT_COST_UNKNOWN state. The old code wrote 0/0/$0.00 here."""
    adapter = StubAdapter(error=GatewayError(GatewayErrorKind.TIMEOUT, "timed out"))
    gateway, rows, _, _ = build(adapter)
    with pytest.raises(GatewayError) as caught:
        gateway.complete_with_configuration(request(), config())

    assert caught.value.kind is GatewayErrorKind.TIMEOUT
    assert len(rows) == 1, "zero calls without a row must still hold for failures"
    row = rows[0]
    assert row.status is CallStatus.ERROR
    assert row.cost_certainty is CostCertainty.UNKNOWN
    assert row.cost_usd is None, "an unestablished cost was recorded as a figure"
    assert row.tokens_in is None
    assert row.tokens_out is None


def test_an_unknown_cost_does_not_hand_the_reservation_back() -> None:
    """Conservative settlement: the provider was reached and would not say."""
    adapter = StubAdapter(error=GatewayError(GatewayErrorKind.PROVIDER_ERROR, "502"))
    gateway, _, ledger, _ = build(adapter)
    with pytest.raises(GatewayError):
        gateway.complete_with_configuration(request(), config())

    settled = ledger.settled()
    assert len(settled) == 1
    entry = settled[0]
    assert entry.certainty is CostCertainty.UNKNOWN
    assert entry.settled_cost_usd == entry.max_cost_usd, "budget was silently freed"
    assert ledger.committed_usd() == pytest.approx(entry.max_cost_usd)


def test_a_known_cost_releases_the_unspent_difference() -> None:
    """Requirement E: actual below reservation, difference becomes available."""
    adapter = StubAdapter(ProviderResult("ok", TerminalState.COMPLETE, 10, 10, "req"))
    gateway, _, ledger, _ = build(adapter)
    gateway.complete_with_configuration(request(), config())

    entry = ledger.settled()[0]
    actual = compute_cost(config(), 10, 10)
    assert entry.settled_cost_usd == pytest.approx(actual)
    assert entry.settled_cost_usd < entry.max_cost_usd
    assert ledger.committed_usd() == pytest.approx(actual)


def test_a_pre_provider_rejection_creates_no_model_call() -> None:
    """The NOT_SENT state: no adapter, so no call, so no row and no reservation."""
    gateway, rows, ledger, _ = build(adapters={})
    with pytest.raises(GatewayError) as caught:
        gateway.complete_with_configuration(request(), config())
    assert caught.value.kind is GatewayErrorKind.INVALID_REQUEST
    assert rows == []
    assert ledger.entries == {}


# --- the budget guard, enforced against the call -----------------------------


def test_the_ceiling_is_enforced_against_the_proposed_call_not_history() -> None:
    """Adversarial proof 1, and the defect this correction exists for.

    $199.99 spent, $0.01 left, and a call authorised for more than $0.01. The
    old rule admitted it because `199.99 < 200`. The provider must not be
    contacted.
    """
    adapter = StubAdapter(ProviderResult("should never run", TerminalState.COMPLETE, 1, 1, None))
    gateway, rows, _, _ = build(adapter, committed=199.99)

    proposed = request()
    authorised = maximum_cost(config(), ("Good evening.",), proposed.max_output_tokens)
    assert authorised > 0.01, "the test's premise requires a call larger than the remainder"

    with pytest.raises(GatewayError) as caught:
        gateway.complete_with_configuration(proposed, config())

    assert caught.value.kind is GatewayErrorKind.BUDGET_EXCEEDED
    assert adapter.calls == 0, "the provider was contacted"
    assert rows == []


def test_a_call_that_fits_in_the_remainder_is_still_admitted() -> None:
    """The stop is arithmetic, not a mood. Room for the call means the call runs.

    Replaces `test_just_under_the_ceiling_still_calls`, which asserted that
    $199.99 of $200 admits any call at all. That assertion encoded the defect.
    """
    adapter = StubAdapter(ProviderResult("ok", TerminalState.COMPLETE, 10, 10, None))
    tiny = request(max_output_tokens=1)
    authorised = maximum_cost(config(), ("Good evening.",), 1)
    gateway, _, _, _ = build(adapter, committed=CLOUD_CEILING_USD - authorised)

    gateway.complete_with_configuration(tiny, config())
    assert adapter.calls == 1


def test_the_hard_stop_fires_above_the_ceiling() -> None:
    """Adversarial proof 6: seeded above the ceiling, nothing is contacted."""
    adapter = StubAdapter(ProviderResult("x", TerminalState.COMPLETE, 1, 1, None))
    gateway, rows, _, _ = build(adapter, committed=250.00)
    with pytest.raises(GatewayError) as caught:
        gateway.complete_with_configuration(request(), config())
    assert caught.value.kind is GatewayErrorKind.BUDGET_EXCEEDED
    assert "ceiling" in str(caught.value)
    assert adapter.calls == 0
    assert rows == []


def test_a_tiny_prompt_with_a_large_output_cap_is_refused_before_transmission() -> None:
    """The output exposure alone breaches the ceiling, and the prompt is three words.

    The case a prompt-sized reservation would wave through: two hundred bytes of
    input against 128,000 authorised output tokens — $3.20 on Opus 5, against
    $2.00 of remaining ceiling. **The provider must never be contacted.**
    """
    adapter = StubAdapter(ProviderResult("should never run", TerminalState.COMPLETE, 1, 1, None))
    gateway, rows, ledger, _ = build(adapter, committed=CLOUD_CEILING_USD - 2.00)

    spacious = GatewayRequest(
        task_type=TaskType.CLASSIFICATION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="Good evening."),),
        max_output_tokens=128_000,
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
    )
    authorised = maximum_cost(config(), ("Good evening.",), 128_000)
    assert authorised > 2.00, "the premise: output alone must exceed the remainder"
    assert maximum_cost(config(), ("Good evening.",), 1) < 0.01, (
        "the premise: the prompt's own share is negligible"
    )

    with pytest.raises(GatewayError) as caught:
        gateway.complete_with_configuration(spacious, config())

    assert caught.value.kind is GatewayErrorKind.BUDGET_EXCEEDED
    assert adapter.calls == 0, "the provider was contacted"
    assert rows == []
    assert ledger.entries == {}, "budget was reserved for a call that was refused"


def test_the_same_tiny_prompt_with_a_modest_output_cap_proceeds() -> None:
    """The refusal above is the output cap, not the prompt and not the ceiling."""
    adapter = StubAdapter(
        ProviderResult("Good evening, my lord.", TerminalState.COMPLETE, 10, 10, "req")
    )
    gateway, rows, _, _ = build(adapter, committed=CLOUD_CEILING_USD - 2.00)

    modest = GatewayRequest(
        task_type=TaskType.CLASSIFICATION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="Good evening."),),
        max_output_tokens=1000,
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
    )
    gateway.complete_with_configuration(modest, config())
    assert adapter.calls == 1
    assert len(rows) == 1


def test_the_reservation_covers_the_whole_authorised_output() -> None:
    """What is held is the bound, not what the call turned out to use."""
    adapter = StubAdapter(ProviderResult("brief", TerminalState.COMPLETE, 10, 10, "req"))
    gateway, _, ledger, _ = build(adapter)

    spacious = GatewayRequest(
        task_type=TaskType.CLASSIFICATION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="Good evening."),),
        max_output_tokens=64_000,
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
    )
    gateway.complete_with_configuration(spacious, config())

    entry = ledger.settled()[0]
    assert entry.max_cost_usd == pytest.approx(maximum_cost(config(), ("Good evening.",), 64_000))
    # The call used 10 output tokens of 64,000 authorised; the difference is freed.
    assert entry.settled_cost_usd is not None
    assert entry.settled_cost_usd < entry.max_cost_usd / 100


def test_the_refusal_states_the_arithmetic() -> None:
    """What Val says has to be actionable, not just a policy announcement."""
    adapter = StubAdapter(ProviderResult("x", TerminalState.COMPLETE, 1, 1, None))
    gateway, _, _, _ = build(adapter, committed=199.99)
    with pytest.raises(GatewayError) as caught:
        gateway.complete_with_configuration(request(), config())
    message = str(caught.value)
    assert "$0.01" in message, "the remaining budget was not stated"
    assert "199.99" in message, "what is already committed was not stated"


# --- Restricted ---------------------------------------------------------------


def test_restricted_content_is_refused_and_writes_no_row() -> None:
    """It was never a call: no provider contacted, nothing to cost (WP-0.4)."""
    adapter = StubAdapter(ProviderResult("x", TerminalState.COMPLETE, 1, 1, None))
    gateway, rows, ledger, _ = build(adapter)
    with pytest.raises(GatewayError) as caught:
        gateway.complete_with_configuration(request(Classification.RESTRICTED), config())
    assert caught.value.kind is GatewayErrorKind.RESTRICTED_CONTENT
    assert rows == []
    assert adapter.calls == 0
    assert ledger.entries == {}, "a refused request must not hold budget"


def fake(*fragments: str) -> str:
    """Build a credential-shaped string without writing one down."""
    return "".join(fragments)


def test_a_credential_in_protected_content_is_blocked_before_transmission() -> None:
    """The gap this closes: the caller says PROTECTED, the message holds a key."""
    adapter = StubAdapter(ProviderResult("should never run", TerminalState.COMPLETE, 1, 1, None))
    gateway, _, _, blocks = build(adapter)

    leaking = GatewayRequest(
        task_type=TaskType.CLASSIFICATION,
        classification=Classification.PROTECTED,
        messages=(
            Message(
                role="user", content="deploy with " + fake("sk-", "ant-", "a1b2c3d4e5f6g7h8i9j0k1")
            ),
        ),
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
    )
    with pytest.raises(GatewayError) as caught:
        gateway.complete_with_configuration(leaking, config())

    assert caught.value.kind is GatewayErrorKind.RESTRICTED_CONTENT
    assert adapter.calls == 0, "the provider was contacted"
    assert blocks, "the block was not recorded anywhere"


def test_a_blocked_request_writes_no_model_calls_row() -> None:
    """No provider was contacted, so a row would assert a call that never happened."""
    adapter = StubAdapter(ProviderResult("x", TerminalState.COMPLETE, 1, 1, None))
    gateway, rows, ledger, _ = build(adapter)

    leaking = GatewayRequest(
        task_type=TaskType.CLASSIFICATION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="ssn 123-45-6789"),),
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
    )
    with pytest.raises(GatewayError):
        gateway.complete_with_configuration(leaking, config())
    assert rows == []
    assert ledger.entries == {}


def test_the_preflight_runs_before_the_budget_check() -> None:
    """Restricted material is refused even when the ceiling would have stopped it.

    Order matters: the reason Lord Armand is given must be the real one.
    """
    adapter = StubAdapter(ProviderResult("x", TerminalState.COMPLETE, 1, 1, None))
    gateway, _, _, _ = build(adapter, committed=999.0)
    leaking = GatewayRequest(
        task_type=TaskType.CLASSIFICATION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="password = " + fake("hunter", "2hunter2")),),
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
    )
    with pytest.raises(GatewayError) as caught:
        gateway.complete_with_configuration(leaking, config())
    assert caught.value.kind is GatewayErrorKind.RESTRICTED_CONTENT


def test_ordinary_work_still_passes_the_preflight() -> None:
    """The guard must not block the work it exists to protect."""
    adapter = StubAdapter(ProviderResult("Noted, my lord.", TerminalState.COMPLETE, 20, 10, "req"))
    gateway, rows, _, _ = build(adapter)
    gateway.complete_with_configuration(request(), config())
    assert adapter.calls == 1
    assert len(rows) == 1


# --- startup -----------------------------------------------------------------


def test_startup_passes_on_the_committed_registry() -> None:
    """Every configured route is Protected-eligible by construction."""
    violations, _ = check_startup(date(2026, 8, 15))
    assert violations == []


def test_startup_warns_but_does_not_fail_on_stale_rates() -> None:
    """Stale rates degrade a record; they do not make the system unsafe to run."""
    violations, warnings = check_startup(date(2026, 12, 1))
    assert violations == []
    assert warnings
    assert all("rates last verified" in w for w in warnings)


def test_slug_appears_in_every_recorded_row() -> None:
    """Any cost view Lord Armand reads displays the slug, not the UUID."""
    adapter = StubAdapter(ProviderResult("x", TerminalState.COMPLETE, 1, 1, None))
    gateway, rows, _, _ = build(adapter)
    gateway.complete_with_configuration(request(), config())
    assert rows[0].slug == "opus-5"
    assert isinstance(rows[0].model_config_id, UUID)


# --- the explicit path is deliberate, not a bypass ---------------------------


def test_a_fabricated_configuration_is_refused() -> None:
    """Adversarial proof 7: an arbitrary provider and model through a normal path.

    A caller that assembles its own `ModelConfig` — or copies a real one and
    edits the model identifier — must not thereby create a route.
    """
    adapter = StubAdapter(ProviderResult("should never run", TerminalState.COMPLETE, 1, 1, None))
    gateway, rows, ledger, _ = build(adapter, adapters={"anthropic": adapter, "rogue": adapter})

    forged = config().model_copy(update={"provider": "rogue", "model_identifier": "anything-1"})
    with pytest.raises(GatewayError) as caught:
        gateway.complete_with_configuration(request(), forged)

    assert caught.value.kind is GatewayErrorKind.NO_ELIGIBLE_ROUTE
    assert adapter.calls == 0
    assert rows == []
    assert ledger.entries == {}


def test_a_widened_eligibility_set_is_refused() -> None:
    """The subtler bypass: the real route, with Restricted quietly added."""
    adapter = StubAdapter(ProviderResult("should never run", TerminalState.COMPLETE, 1, 1, None))
    gateway, rows, _, _ = build(adapter)

    widened = config().model_copy(update={"eligible_classifications": frozenset(Classification)})
    with pytest.raises(GatewayError) as caught:
        gateway.complete_with_configuration(request(Classification.INTERNAL), widened)

    assert caught.value.kind is GatewayErrorKind.NO_ELIGIBLE_ROUTE
    assert adapter.calls == 0
    assert rows == []


def test_the_registry_entry_itself_is_accepted() -> None:
    """The explicit path still works for what it exists for — the strip step."""
    adapter = StubAdapter(
        ProviderResult("ok", TerminalState.COMPLETE, 5, 5, "req"), name="anthropic"
    )
    gateway, rows, _, _ = build(adapter)
    gateway.complete_with_configuration(request(), config("haiku-4-5"))
    assert adapter.calls == 1
    assert rows[0].slug == "haiku-4-5"


def test_the_fake_ledger_matches_the_real_accounting_rule() -> None:
    """Guard on the guard: if the fake drifts, every test above proves nothing."""
    ledger = FakeLedger(opening_committed_usd=10.0)
    claim = ledger.reserve(config(), 5.0, TaskType.CONVERSATION, uuid4())
    assert not isinstance(claim, type(None))
    assert ledger.committed_usd() == pytest.approx(15.0)
    ledger.settle(claim.id, 1.0, CostCertainty.KNOWN, None)  # type: ignore[union-attr]
    assert ledger.committed_usd() == pytest.approx(11.0)


def test_gateway_requires_a_ledger() -> None:
    """There is no constructor that omits budget control."""
    with pytest.raises(TypeError):
        Gateway(adapters={}, recorder=lambda record: None)  # type: ignore[call-arg]
