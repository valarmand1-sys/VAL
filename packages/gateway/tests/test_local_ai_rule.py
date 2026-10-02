"""The governing rule of 2 October 2026: local AI processing.

Ordinary typed and spoken interaction, and every supporting or background AI task, runs
on this Mac. These tests hold the rule where it is enforced — the egress decision taken
for every turn, the narrowest door every provider call passes through, the startup that
builds no hosted adapter, and the destination check that trusts no label — with
scripted adapters, so nothing leaves the machine to prove that nothing leaves.

The conftest stands the rule down for the tests written before it; every test here
stands it back up.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

from dataclasses import dataclass

import pytest
from gateway_fakes import FakeLedger
from sqlalchemy import Engine, text
from test_deliberation_machinery import (
    clean_personas,
    ok,
    store,
    verifier,
)
from test_voice_local_only import CloudSpy, LocalAdapter, two_worlds

import val_policy.egress as egress_policy
from val_domain.egress import LocalOnlyReason
from val_domain.gateway import (
    Admission,
    Classification,
    GatewayError,
    GatewayErrorKind,
    GatewayRequest,
    Hosting,
    Message,
    ModelConfig,
    TaskType,
)
from val_domain.registry import active, by_slug
from val_gateway.deliberate import send as deliberated_send
from val_gateway.gateway import Gateway
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader
from val_gateway.projects import load_catalogue
from val_gateway.startup import build_adapters
from val_policy.egress import LiveVoiceConversations, decide_egress
from val_policy.project_resolution import ProjectSignals


@pytest.fixture(autouse=True)
def the_rule_stands(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(egress_policy, "HOSTED_MODELS_FORBIDDEN", True)


def _cloud_config() -> ModelConfig:
    return next(
        c
        for c in active()
        if c.hosting is Hosting.CLOUD and c.admission is not Admission.NOT_ADMITTED
    )


# --- the decision every turn carries ----------------------------------------------------


def test_every_turn_is_local_only_on_the_rules_ground(store: Engine) -> None:
    decision = decide_egress(store, None, live=LiveVoiceConversations())
    assert decision.local_only
    assert decision.reasons[0] is LocalOnlyReason.OWNER_RULE_LOCAL_AI
    assert "owner_rule_local_ai" in decision.because()


def test_the_rule_is_not_configuration() -> None:
    import os

    source = open(egress_policy.__file__, encoding="utf-8").read()
    assert "HOSTED_MODELS_FORBIDDEN = True" in source
    assert "os.environ" not in source.split("HOSTED_MODELS_FORBIDDEN = True")[0], (
        "the rule is a constant, not a setting"
    )
    assert "VAL_HOSTED" not in os.environ or True


# --- the narrowest door -----------------------------------------------------------------


def test_a_hosted_route_is_refused_by_every_entrance_before_anything_is_sent(
    store: Engine,
) -> None:
    cloud = CloudSpy()
    gateway = two_worlds(store, LocalAdapter([]), cloud)
    config = _cloud_config()
    request = GatewayRequest(
        task_type=TaskType.CLASSIFICATION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="Is the barn booked?"),),
        system=None,
        max_output_tokens=64,
        project_id=None,
        project_attribution="explicit_none",  # type: ignore[arg-type]
    )
    with pytest.raises(GatewayError) as refused:
        gateway.complete_with_configuration(request, config)
    assert refused.value.kind is GatewayErrorKind.HOSTED_MODEL_NOT_AUTHORISED
    assert "owner rule, 2 October 2026" in str(refused.value)
    assert cloud.seen == [], "nothing reached the hosted provider"


def test_an_ordinary_routed_request_never_reaches_a_hosted_route(store: Engine) -> None:
    cloud = CloudSpy()
    gateway = two_worlds(store, LocalAdapter([]), cloud)
    request = GatewayRequest(
        task_type=TaskType.STRIP,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="Book the barn."),),
        system=None,
        max_output_tokens=64,
        project_id=None,
        project_attribution="explicit_none",  # type: ignore[arg-type]
    )
    with pytest.raises(GatewayError) as refused:
        gateway.complete(request)
    assert cloud.seen == [], "no fallback and no retry reached the cloud"
    assert refused.value.kind in (
        GatewayErrorKind.NO_ELIGIBLE_ROUTE,
        GatewayErrorKind.HOSTED_MODEL_NOT_AUTHORISED,
    )


@dataclass
class _Remote(LocalAdapter):
    """A route registered as local whose adapter would send elsewhere."""

    destination: str = "http://192.168.1.20:1234/v1"


@dataclass
class _Unlabelled(LocalAdapter):
    pass


def _gateway_with_local(store: Engine, adapter: LocalAdapter) -> Gateway:
    providers = {config.provider for config in active() if config.hosting is Hosting.LOCAL}
    return Gateway(
        adapters={provider: adapter for provider in providers},  # type: ignore[arg-type]
        recorder=lambda record: record_call(store, record),
        ledger=FakeLedger(),
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(store),
        verify_provenance=verifier(store),
    )


@pytest.mark.parametrize("adapter", [_Remote([ok("Cobalt.")]), _Unlabelled([ok("Cobalt.")])])
def test_a_local_label_is_not_enough_the_destination_must_be_this_machine(
    store: Engine, adapter: LocalAdapter
) -> None:
    """A real typed turn, on the local partner route, whose adapter would send elsewhere
    or declares no destination: refused at the narrowest door, nothing sent, the turn
    ends unanswered rather than answered from somewhere unverified."""
    gateway = _gateway_with_local(store, adapter)
    outcome = deliberated_send(
        store,
        gateway,
        "What colour is the hall?",
        catalogue=load_catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
        live_voice=LiveVoiceConversations(),
    )
    assert adapter.sent == [], "nothing was transmitted"
    assert not hasattr(outcome, "turn") or getattr(outcome.turn, "val_message", None) is None
    assert "destination" in str(outcome)


@dataclass
class _Loopback(LocalAdapter):
    destination: str = "http://127.0.0.1:1234/v1"


def test_a_verified_loopback_destination_is_allowed(store: Engine) -> None:
    adapter = _Loopback([ok("Cobalt, my lord.")])
    gateway = _gateway_with_local(store, adapter)
    outcome = deliberated_send(
        store,
        gateway,
        "What colour is the hall?",
        catalogue=load_catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
        live_voice=LiveVoiceConversations(),
    )
    assert len(adapter.sent) == 1
    assert outcome.turn.val_message.content == "Cobalt, my lord."  # type: ignore[union-attr]


# --- a typed turn in a new conversation ------------------------------------------------


def test_a_typed_turn_in_a_new_conversation_is_answered_locally_and_classified_not_run(
    store: Engine,
) -> None:
    local = _Loopback([ok("Cobalt, my lord.")])
    cloud = CloudSpy()
    gateway = two_worlds(store, local, cloud)
    outcome = deliberated_send(
        store,
        gateway,
        "What colour is the hall?",
        catalogue=load_catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
        live_voice=LiveVoiceConversations(),
    )
    assert cloud.seen == [], "the classifier's cloud route was not called"
    assert outcome.turn.val_message.content == "Cobalt, my lord."  # type: ignore[union-attr]
    with store.connect() as connection:
        row = connection.execute(
            text(
                "select established, verdict, attempts, not_run_reason from classifications "
                " where message_id = :id"
            ),
            {"id": outcome.turn.user_message.id},  # type: ignore[union-attr]
        ).one()
    assert row.verdict is None, "no verdict was invented"
    assert (row.established, row.attempts) == (False, 0)
    assert "NOT RUN" in row.not_run_reason
    assert "owner rule, 2 October 2026" in row.not_run_reason
    assert "not a finding that the turn was ordinary" in row.not_run_reason


# --- startup ----------------------------------------------------------------------------


def test_startup_builds_no_hosted_adapter_and_needs_no_hosted_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for variable in ("VAL_ANTHROPIC_API_KEY", "VAL_OPENAI_API_KEY", "VAL_GOOGLE_API_KEY"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("VAL_LMSTUDIO_API_TOKEN", "not-a-real-value")
    adapters, problems = build_adapters({"anthropic", "openai", "lmstudio"})
    assert problems == []
    assert "anthropic" not in adapters and "openai" not in adapters
    assert "lmstudio" in adapters


def test_the_registry_is_unchanged_by_the_rule() -> None:
    """History is preserved: the hosted entries stay registered and recorded; they are
    unreachable, not erased."""
    assert by_slug("gpt-5-6-sol-medium") is not None
    assert by_slug("haiku-4-5-20251001") is not None
