"""The live-voice seal, as policy — owner ruling, 24 September 2026.

Voice work package 3 §2.2, §2.3.1 and §19. These are the pure decisions, held
without a database and without a provider: what the seal is, what it refuses, and
what it deliberately is **not**.

The one that matters most is the negative in §2.2: **voice content is not
Restricted.** Restricted would either strand a spoken turn with no eligible route,
because the local configurations are registered as Restricted-ineligible, or force
that eligibility to be widened — and whether local inference may carry Restricted
content is a reserved owner ruling nobody has made. A test is the only thing that
keeps a later convenience from making it implicitly.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from val_domain.deliberation import ClassificationRecord
from val_domain.egress import ORDINARY, Egress, LocalOnlyReason, sealed
from val_domain.gateway import (
    CapabilityProfile,
    Classification,
    GatewayErrorKind,
    Hosting,
    TaskType,
)
from val_domain.registry import active
from val_policy.consequence import EXECUTION_GATED_ON_CLASSIFICATION, execution_refusal
from val_policy.eligibility import egress_refusal_for
from val_policy.routing import candidates, is_admitted, required_profile, satisfies_profile

# --- what the seal is ---------------------------------------------------------------


def test_the_ordinary_decision_is_the_only_default() -> None:
    assert ORDINARY.egress is Egress.ORDINARY
    assert ORDINARY.local_only is False
    assert ORDINARY.reasons == ()


def test_a_sealed_decision_must_name_why() -> None:
    """A seal with no grounds would be a mood, not a fact."""
    with pytest.raises(ValueError):
        sealed()


def test_a_sealed_decision_keeps_every_ground_once() -> None:
    decision = sealed(
        LocalOnlyReason.VOICE_SESSION_ACTIVE,
        LocalOnlyReason.CONVERSATION_SEALED,
        LocalOnlyReason.VOICE_SESSION_ACTIVE,
    )
    assert decision.local_only
    assert decision.reasons == (
        LocalOnlyReason.VOICE_SESSION_ACTIVE,
        LocalOnlyReason.CONVERSATION_SEALED,
    )
    assert "voice_session_active" in decision.because()


# --- what it refuses ----------------------------------------------------------------


def _one(hosting: Hosting) -> object:
    for config in active():
        if config.hosting is hosting and is_admitted(config):
            return config
    raise AssertionError(f"the registry has no admitted {hosting.value} configuration to test with")


def test_an_ordinary_request_is_refused_to_nothing() -> None:
    for hosting in (Hosting.LOCAL, Hosting.CLOUD):
        assert egress_refusal_for(Egress.ORDINARY, _one(hosting)) is None  # type: ignore[arg-type]


def test_a_local_only_request_may_go_to_a_local_route() -> None:
    assert egress_refusal_for(Egress.LOCAL_ONLY, _one(Hosting.LOCAL)) is None  # type: ignore[arg-type]


def test_a_local_only_request_is_refused_to_every_cloud_route() -> None:
    """Every one, not the ones a test happened to think of."""
    cloud = [config for config in active() if config.hosting is Hosting.CLOUD]
    assert cloud, "the registry has cloud configurations; this test is about all of them"
    for config in cloud:
        refusal = egress_refusal_for(Egress.LOCAL_ONLY, config)
        assert refusal is not None, f"{config.slug} would have carried live-voice content"
        kind, detail = refusal
        assert kind is GatewayErrorKind.LOCAL_ONLY_EGRESS_REFUSED
        assert "local-only" in detail
        assert "24 September 2026" in detail


def test_the_refusal_is_about_where_inference_runs_not_about_who_pays() -> None:
    """A free cloud route would still be egress, so `Metering` is not the test."""
    import inspect

    source = inspect.getsource(egress_refusal_for)
    assert "hosting" in source
    assert "Metering" not in source.split('"""')[-1], "metering must not decide egress"


# --- routing ------------------------------------------------------------------------


def test_routing_offers_a_sealed_request_only_local_routes() -> None:
    ranked = candidates(
        active(),
        Classification.PROTECTED,
        is_ready=lambda config: True,
        is_affordable=lambda config: True,
        profile=CapabilityProfile.PARTNER,
        cost_bound=lambda config: config.cost_per_mtok_in_usd,
        egress=Egress.LOCAL_ONLY,
    )
    assert ranked, "a sealed partner turn still has somewhere to go: the local route"
    assert all(config.hosting is Hosting.LOCAL for config in ranked)


def test_routing_is_unchanged_for_an_ordinary_request() -> None:
    """The seal narrows the sealed case and nothing else."""
    kwargs = dict(
        is_ready=lambda config: True,
        is_affordable=lambda config: True,
        profile=CapabilityProfile.PARTNER,
        cost_bound=lambda config: config.cost_per_mtok_in_usd,
    )
    default = candidates(active(), Classification.PROTECTED, **kwargs)  # type: ignore[arg-type]
    stated = candidates(
        active(),
        Classification.PROTECTED,
        egress=Egress.ORDINARY,
        **kwargs,  # type: ignore[arg-type]
    )
    assert [config.slug for config in default] == [config.slug for config in stated]
    assert any(config.hosting is Hosting.CLOUD for config in default), (
        "an ordinary partner request still sees the cloud routes it always saw"
    )


# --- the negative §2.2 exists to hold ------------------------------------------------


def test_the_seal_is_not_a_classification_and_changes_no_eligibility() -> None:
    """Voice content stays Protected, and no configuration's eligibility moves.

    If the seal had been implemented as `Classification.RESTRICTED`, the local
    partner route would have had to become Restricted-eligible to carry a spoken
    turn. It has not, and this is the test that notices if it ever does.
    """
    local_partner = [
        config
        for config in active()
        if config.hosting is Hosting.LOCAL
        and is_admitted(config)
        and satisfies_profile(config, CapabilityProfile.PARTNER)
    ]
    assert local_partner, "the local partner route is the one a sealed turn uses"
    for config in local_partner:
        assert Classification.RESTRICTED not in config.eligible_classifications, (
            "local Restricted eligibility is a reserved owner ruling and was not made here"
        )
        assert Classification.PROTECTED in config.eligible_classifications


def test_no_registry_configuration_was_added_for_the_seal() -> None:
    """The seal needed no new entry, and adding one would be a ruling by the back door."""
    slugs = {config.slug for config in active()}
    for slug in slugs:
        assert "local_only" not in slug and "sealed" not in slug and "voice" not in slug


def test_startup_is_still_clean() -> None:
    from val_policy.eligibility import startup_violations

    assert startup_violations(list(active())) == []
    assert date.today() is not None


# --- §2.3.1: execution fails closed -------------------------------------------------


def _record(**overrides: object) -> ClassificationRecord:
    base: dict[str, object] = dict(
        id=uuid4(),
        project_id=None,
        conversation_id=uuid4(),
        message_id=uuid4(),
        established=True,
        verdict=None,
        hard_exclusion=None,
        attempts=1,
        model_call_ids=(),
        resolving_model_call_id=None,
        resolution=None,
        created_at=None,
    )
    base.update(overrides)
    return ClassificationRecord(**base)  # type: ignore[arg-type]


def test_nothing_currently_executes_on_the_classification() -> None:
    """§2.3.1's finding, kept true by a test rather than by a comment.

    The classification gates the reasoning path and nothing else, because Layer 0
    has no action with effects outside the conversation. If an executor is ever
    added, this fails and its author has to consult the gate.
    """
    assert EXECUTION_GATED_ON_CLASSIFICATION == ()
    assert set(TaskType) == {
        TaskType.CONVERSATION,
        TaskType.CLASSIFICATION,
        TaskType.STRIP,
        TaskType.BLIND_POSITION,
        TaskType.TITLE,
    }, "a new task type may be an action; check it against the execution gate"


def test_execution_is_blocked_when_the_classification_did_not_run() -> None:
    refusal = execution_refusal(
        _record(established=False, attempts=0, not_run_reason="local-only conversation")
    )
    assert refusal is not None
    assert "BLOCKED" in refusal
    assert "local-only" in refusal


def test_not_run_is_never_equivalent_to_not_consequential() -> None:
    """The distinction the whole §2.3 record exists to keep."""
    did_not_run = _record(established=False, attempts=0, not_run_reason="local-only conversation")
    found_ordinary = _record(established=True, verdict=None, attempts=1)
    assert did_not_run.ran is False
    assert found_ordinary.ran is True
    assert execution_refusal(did_not_run) is not None
    assert execution_refusal(found_ordinary) is None


def test_execution_is_blocked_when_no_classification_exists_at_all() -> None:
    assert execution_refusal(None) is not None


def test_execution_is_blocked_when_the_classification_established_nothing() -> None:
    """The 3 September rule: an unknown classification is never treated as ordinary."""
    refusal = execution_refusal(_record(established=False, attempts=2, resolution="two failures"))
    assert refusal is not None and "no verdict" in refusal


def test_required_profile_is_unchanged_by_any_of_this() -> None:
    assert required_profile(TaskType.CONVERSATION) is CapabilityProfile.PARTNER
    assert required_profile(TaskType.CLASSIFICATION) is CapabilityProfile.STRUCTURED
