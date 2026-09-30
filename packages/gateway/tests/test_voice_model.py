"""A different conversational model for Voice — owner order of 29 September 2026.

Unset (production), the registry is as written and nothing is pinned. Set, the candidate
is pin-only: routing never selects it, a Voice turn is asked of it, a typed turn outside
Voice is asked of the Partner route, and a Voice call that fails before any word is
delivered is answered by the Partner route once.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

from collections.abc import Iterator

import pytest
from gateway_fakes import FakeLedger
from sqlalchemy import Engine, text
from test_deliberation_machinery import ScriptedAdapter, clean_personas, ok, store
from test_voice_input import a_conversation

import val_domain.registry as registry
from val_domain.gateway import Admission, GatewayError, GatewayErrorKind, ModelConfig
from val_gateway.deliberate import send
from val_gateway.gateway import Gateway
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader
from val_gateway.projects import load_catalogue
from val_gateway.provenance import verifier
from val_gateway.seal import SealRoute
from val_gateway.startup import (
    PARTNER_SLUG,
    VOICE_MODELS,
    configured_voice_model,
    enable_voice_model,
)

CANDIDATE = "gemma-4-26b-a4b-q4km-llamacpp-voice"


@pytest.fixture
def voice_model() -> Iterator[ModelConfig]:
    saved, pin_only = registry.REGISTRY, set(registry.PIN_ONLY)
    try:
        yield enable_voice_model("gemma-4-26b-a4b")
    finally:
        registry.REGISTRY = saved
        registry.PIN_ONLY.clear()
        registry.PIN_ONLY.update(pin_only)


def gateway_with(store: Engine, adapter: ScriptedAdapter, pinned: ModelConfig | None) -> Gateway:
    gateway = Gateway(
        adapters={"lmstudio": adapter, "llamacpp": adapter},
        recorder=lambda record: record_call(store, record),
        ledger=FakeLedger(),
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(store),
        verify_provenance=verifier(store),
    )
    gateway.voice_configuration = pinned
    return gateway


def slugs(store: Engine) -> list[str]:
    with store.connect() as connection:
        ids = [
            r[0]
            for r in connection.execute(
                text(
                    "select model_config_id from model_calls "
                    "where task_type::text = 'conversation' order by created_at"
                )
            )
        ]
    return [registry.by_id(i).slug for i in ids]  # type: ignore[union-attr]


def say(store: Engine, gateway: Gateway, words: str, conversation: object, spoken: bool) -> object:
    return send(
        store,
        gateway,
        words,
        catalogue=load_catalogue(store),
        conversation_id=conversation,
        spoken=spoken,
        seal_route=SealRoute.UTTERANCE_FINALIZED,
    )


def test_unset_means_the_registry_as_written(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VAL_VOICE_MODEL", raising=False)
    assert configured_voice_model() == (None, None)
    entry = registry.by_slug(CANDIDATE)
    assert entry is not None
    assert entry.admission is Admission.NOT_ADMITTED and entry.capability_profiles == frozenset()
    assert CANDIDATE not in {c.slug for c in registry.active()}
    assert CANDIDATE not in registry.PIN_ONLY


def test_an_unknown_value_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAL_VOICE_MODEL", "something-else")
    assert configured_voice_model()[1] is not None
    monkeypatch.setenv("VAL_VOICE_MODEL", " Gemma-4-26B-A4B ")
    assert configured_voice_model() == ("gemma-4-26b-a4b", None)
    assert VOICE_MODELS["gemma-4-26b-a4b"] == CANDIDATE


def test_enabled_it_is_pin_only_and_routing_never_selects_it(voice_model: ModelConfig) -> None:
    assert voice_model.slug == CANDIDATE
    assert CANDIDATE in registry.PIN_ONLY
    assert CANDIDATE not in {c.slug for c in registry.active()}
    partner = registry.by_slug(PARTNER_SLUG)
    assert partner is not None and partner in registry.active(), "typed work keeps its route"


def test_a_spoken_turn_is_asked_of_the_voice_model_and_a_typed_one_is_not(
    store: Engine, voice_model: ModelConfig
) -> None:
    adapter = ScriptedAdapter([ok("Good evening, my lord."), ok("Lisbon, my lord.")])
    gateway = gateway_with(store, adapter, voice_model)
    conversation = a_conversation(store)
    say(store, gateway, "Good evening, Val.", conversation, spoken=True)
    # Typed later into the same conversation, with no Voice session open: the seal keeps
    # it local, and it is not a Voice turn.
    say(store, gateway, "What is the capital of Portugal?", conversation, spoken=False)
    assert slugs(store) == [CANDIDATE, PARTNER_SLUG]


def test_a_failing_voice_call_is_answered_by_the_partner_route_once(
    store: Engine, voice_model: ModelConfig
) -> None:
    class FailsFirst(ScriptedAdapter):
        calls = 0

        def complete(self, *args, **kwargs) -> object:  # noqa: ANN002, ANN003
            FailsFirst.calls += 1
            if FailsFirst.calls == 1:
                raise GatewayError(GatewayErrorKind.PROVIDER_ERROR, "scripted Voice model failure")
            return super().complete(*args, **kwargs)

    adapter = FailsFirst([ok("Good evening, my lord.")])
    gateway = gateway_with(store, adapter, voice_model)
    got = say(store, gateway, "Good evening, Val.", a_conversation(store), spoken=True)
    assert got.turn.val_message.content == "Good evening, my lord."  # type: ignore[attr-defined]
    with store.connect() as connection:
        answers = connection.execute(
            text("select count(*) from messages where role = 'val'")
        ).scalar_one()
    assert answers == 1, "one answer, from the Partner route"


def test_with_nothing_pinned_a_spoken_turn_takes_the_partner_route(store: Engine) -> None:
    adapter = ScriptedAdapter([ok("Good evening, my lord.")])
    gateway = gateway_with(store, adapter, None)
    say(store, gateway, "Good evening, Val.", a_conversation(store), spoken=True)
    assert slugs(store) == [PARTNER_SLUG]


class Residency(ScriptedAdapter):
    """A local runtime that records loads and releases by model identifier (§10)."""

    def __init__(self) -> None:
        super().__init__([])
        self.events: list[tuple[str, str]] = []

    def ensure_runtime_ready(self, config: ModelConfig) -> dict[str, object]:
        self.events.append(("load", config.model_identifier))
        return {"model_loaded": True}

    def release_model(self, config: ModelConfig) -> dict[str, object]:
        self.events.append(("release", config.model_identifier))
        return {"released": True, "model": config.model_identifier}


def test_unset_voice_on_keeps_the_partner_model_resident(
    store: Engine, voice_model: ModelConfig
) -> None:
    adapter = Residency()
    gateway = gateway_with(store, adapter, voice_model)
    warmed = gateway.warm_cognition()
    assert warmed["warmed"] is True and "partner_released" not in warmed
    assert adapter.events == [("load", voice_model.model_identifier)]


def test_set_voice_on_releases_the_partner_model_and_voice_off_brings_it_back(
    store: Engine, voice_model: ModelConfig
) -> None:
    adapter = Residency()
    gateway = gateway_with(store, adapter, voice_model)
    gateway.voice_releases_partner = True
    partner = registry.by_slug(PARTNER_SLUG)
    assert partner is not None
    warmed = gateway.warm_cognition()
    assert warmed["partner_released"] == {  # type: ignore[index]
        "slug": PARTNER_SLUG,
        "released": True,
        "model": partner.model_identifier,
    }
    # The release comes first, so the Voice model loads into the memory it gave back.
    assert adapter.events == [
        ("release", partner.model_identifier),
        ("load", voice_model.model_identifier),
    ]
    back = gateway.rewarm_partner_after_voice()
    assert back["warmed"] is True and back["slug"] == PARTNER_SLUG
    assert adapter.events[-1] == ("load", partner.model_identifier)


def test_with_nothing_pinned_the_switch_releases_nothing(store: Engine) -> None:
    adapter = Residency()
    gateway = gateway_with(store, adapter, None)
    gateway.voice_releases_partner = True
    warmed = gateway.warm_cognition()
    assert "partner_released" not in warmed
    assert all(kind == "load" for kind, _ in adapter.events)
