"""A model for ordinary typed conversation, and deep reasoning as a deliberate choice.

Owner order of 2 October 2026 ("CORRECT THE TEXT-MODEL TASK AND CARRY IT THROUGH TO
COMPLETION") and his ruling of 3 October. Unset (production today), the registry is as
written. Set, the typed candidate is the ordinary typed route; the Partner entry (GPT-OSS
MEDIUM) is pin-only and is reached only by a turn that asks for deep reasoning; a spoken
turn keeps the Voice model; and local cognition models are used one at a time at all
times, the change of model being a preparation that happens once and is reported.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from test_deliberation_machinery import ScriptedAdapter, clean_personas, ok, store
from test_prefix_prime import PrimingAdapter
from test_voice_input import a_conversation
from test_voice_model import Residency, gateway_with, slugs, voice_model

import val_domain.registry as registry
import val_policy.egress as egress_policy
from val_domain.gateway import (
    Admission,
    CapabilityProfile,
    GatewayError,
    GatewayErrorKind,
    ModelConfig,
)
from val_gateway.deliberate import send
from val_gateway.gateway import Gateway
from val_gateway.projects import load_catalogue
from val_gateway.seal import SealRoute
from val_gateway.startup import (
    PARTNER_SLUG,
    TYPED_MODELS,
    configured_typed_model,
    enable_typed_model,
)

TYPED = "gemma-4-26b-a4b-styletune-v2-q4km-llamacpp-typed"
KEY = "gemma-4-26b-a4b-styletune-v2"


@pytest.fixture(autouse=True)
def the_rule_stands(monkeypatch: pytest.MonkeyPatch) -> None:
    """As production: AI processing is local (2 October 2026), so a typed turn is not
    classified on a hosted route first — it goes to its local model."""
    monkeypatch.setattr(egress_policy, "HOSTED_MODELS_FORBIDDEN", True)


@pytest.fixture
def typed_model() -> Iterator[tuple[ModelConfig, ModelConfig]]:
    saved, pin_only = registry.REGISTRY, set(registry.PIN_ONLY)
    try:
        yield enable_typed_model(KEY)
    finally:
        registry.REGISTRY = saved
        registry.PIN_ONLY.clear()
        registry.PIN_ONLY.update(pin_only)


def typed_gateway(
    store: Engine,
    adapter: ScriptedAdapter,
    models: tuple[ModelConfig, ModelConfig],
    voice: ModelConfig | None = None,
) -> Gateway:
    # The rule verifies where each local adapter sends: this one says this machine.
    adapter.destination = "http://127.0.0.1:8099/v1"  # type: ignore[attr-defined]
    gateway = gateway_with(store, adapter, voice)
    gateway.typed_configuration, gateway.deep_configuration = models
    gateway.serialized_models = True
    return gateway


def say(
    store: Engine, gateway: Gateway, words: str, *, deep: bool = False, spoken: bool = False
) -> object:
    return send(
        store,
        gateway,
        words,
        catalogue=load_catalogue(store),
        conversation_id=a_conversation(store),
        spoken=spoken,
        seal_route=SealRoute.UTTERANCE_FINALIZED,
        deep_reasoning=deep,
    )


def test_unset_means_the_registry_as_written(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VAL_TYPED_MODEL", raising=False)
    assert configured_typed_model() == (None, None)
    entry = registry.by_slug(TYPED)
    assert entry is not None
    assert entry.admission is Admission.NOT_ADMITTED and entry.capability_profiles == frozenset()
    assert TYPED not in {c.slug for c in registry.active()}
    assert PARTNER_SLUG in {c.slug for c in registry.active()}, "typed work keeps GPT-OSS"
    assert PARTNER_SLUG not in registry.PIN_ONLY


def test_an_unknown_value_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAL_TYPED_MODEL", "regular-gemma")
    assert configured_typed_model()[1] is not None
    monkeypatch.setenv("VAL_TYPED_MODEL", " Gemma-4-26B-A4B-StyleTune-V2 ")
    assert configured_typed_model() == (KEY, None)
    assert TYPED_MODELS[KEY] == TYPED


def test_enabled_it_is_the_typed_route_and_the_partner_entry_is_reached_only_by_name(
    typed_model: tuple[ModelConfig, ModelConfig],
) -> None:
    typed, deep = typed_model
    assert typed.slug == TYPED and deep.slug == PARTNER_SLUG
    assert typed in registry.active() and CapabilityProfile.PARTNER in typed.capability_profiles
    assert TYPED not in registry.PIN_ONLY
    assert PARTNER_SLUG in registry.PIN_ONLY
    assert PARTNER_SLUG not in {c.slug for c in registry.active()}, "routing never selects it"
    assert deep.admission is not Admission.NOT_ADMITTED, "its own admission is untouched"


def test_an_ordinary_typed_turn_and_a_deep_one_are_asked_of_different_models(
    store: Engine, typed_model: tuple[ModelConfig, ModelConfig]
) -> None:
    adapter = ScriptedAdapter([ok("Good evening, my lord."), ok("Three reasons, my lord.")])
    gateway = typed_gateway(store, adapter, typed_model)
    say(store, gateway, "Good evening, Val.")
    say(store, gateway, "Reason carefully about the financing structure.", deep=True)
    assert slugs(store) == [TYPED, PARTNER_SLUG]


def test_a_spoken_turn_keeps_the_voice_model_whatever_the_flag_says(
    store: Engine, voice_model: ModelConfig, typed_model: tuple[ModelConfig, ModelConfig]
) -> None:
    adapter = ScriptedAdapter([ok("Good evening, my lord.")])
    gateway = typed_gateway(store, adapter, typed_model, voice=voice_model)
    say(store, gateway, "Good evening, Val.", deep=True, spoken=True)
    assert slugs(store) == [voice_model.slug]


def test_a_failed_deep_turn_is_reported_and_no_other_model_answers_in_its_place(
    store: Engine, typed_model: tuple[ModelConfig, ModelConfig]
) -> None:
    class Fails(ScriptedAdapter):
        calls = 0

        def complete(self, *args, **kwargs) -> object:  # noqa: ANN002, ANN003
            Fails.calls += 1
            raise GatewayError(GatewayErrorKind.PROVIDER_ERROR, "scripted deep-route failure")

    adapter = Fails([ok("this must never be delivered")])
    gateway = typed_gateway(store, adapter, typed_model)
    got = say(store, gateway, "Reason carefully about this.", deep=True)
    assert not hasattr(got, "turn"), "unanswered"
    assert Fails.calls == 1, "asked once, of the deep route, and of nothing else"
    with store.connect() as connection:
        answers = connection.execute(
            text("select count(*) from messages where role = 'val'")
        ).scalar_one()
    assert answers == 0


def test_local_models_are_used_one_at_a_time_and_each_change_is_a_release_then_a_load(
    store: Engine, typed_model: tuple[ModelConfig, ModelConfig]
) -> None:
    typed, deep = typed_model
    adapter = Residency()
    gateway = typed_gateway(store, adapter, typed_model)
    assert gateway.prepare_cognition()["prepared"] is True
    assert adapter.loaded == {typed.model_identifier}
    assert gateway.prepare_cognition(deep=True)["prepared"] is True
    assert adapter.loaded == {deep.model_identifier}, "never both"
    assert gateway.prepare_cognition()["prepared"] is True
    assert adapter.events == [
        ("load", typed.model_identifier),
        ("release", typed.model_identifier),
        ("load", deep.model_identifier),
        ("release", deep.model_identifier),
        ("load", typed.model_identifier),
    ]


def test_without_the_switch_nothing_is_released_outside_voice(store: Engine) -> None:
    """Production today: no typed model, so a second local model does not evict the first."""
    adapter = Residency()
    gateway = gateway_with(store, adapter, None)
    partner = registry.by_slug(PARTNER_SLUG)
    assert partner is not None
    gateway._ready_local(partner)
    other = partner.model_copy(update={"slug": "another-local", "model_identifier": "another"})
    gateway._ready_local(other)
    assert all(kind == "load" for kind, _ in adapter.events)


def test_the_state_says_what_is_resident_and_what_is_ready(
    store: Engine, typed_model: tuple[ModelConfig, ModelConfig]
) -> None:
    typed, deep = typed_model
    gateway = typed_gateway(store, Residency(), typed_model)
    before = gateway.cognition_state()
    assert before["configured"] is True
    assert (before["typed_model"], before["deep_model"]) == (typed.slug, deep.slug)
    assert before["resident"] == [] and not before["typed_ready"] and not before["deep_ready"]
    gateway.prepare_cognition()
    ordinary = gateway.cognition_state()
    assert ordinary["resident"] == [typed.slug]
    assert ordinary["typed_ready"] is True and ordinary["deep_ready"] is False
    gateway.prepare_cognition(deep=True)
    reasoning = gateway.cognition_state()
    assert reasoning["resident"] == [deep.slug]
    assert reasoning["typed_ready"] is False and reasoning["deep_ready"] is True


def test_the_prefix_preparation_is_reported_and_a_release_forgets_it(
    store: Engine, typed_model: tuple[ModelConfig, ModelConfig]
) -> None:
    typed, _ = typed_model

    class Primes(PrimingAdapter):
        def release_model(self, config: ModelConfig) -> dict[str, object]:
            return {"released": True, "model": config.model_identifier}

    adapter = Primes([ok("Good")])
    gateway = typed_gateway(store, adapter, typed_model)  # type: ignore[arg-type]
    gateway.typed_prime = "transition"
    gateway._ready_local(typed)
    loaded = gateway.cognition_state()
    assert loaded["typed_ready"] is True, "resident: a message now is answered by it"
    assert loaded["typed_prefix_prepared"] is False
    assert gateway.prime_typed_prefix()["primed"] is True
    prepared = gateway.cognition_state()
    assert prepared["typed_ready"] is True and prepared["typed_prefix_prepared"] is True
    assert prepared["preparing"] is None, "the mark is lifted when the prime ends"
    gateway._release_local(typed)
    released = gateway.cognition_state()
    assert released["typed_ready"] is False and released["typed_prefix_prepared"] is False


def test_nothing_is_changed_while_voice_holds_the_memory(
    store: Engine, voice_model: ModelConfig, typed_model: tuple[ModelConfig, ModelConfig]
) -> None:
    adapter = Residency()
    gateway = typed_gateway(store, adapter, typed_model, voice=voice_model)
    gateway.voice_releases_partner = True
    gateway.warm_cognition()  # Voice On
    assert adapter.loaded == {voice_model.model_identifier}
    refused = gateway.prepare_cognition()
    assert refused["prepared"] is False and "Voice is on" in str(refused["reason"])
    assert adapter.loaded == {voice_model.model_identifier}, "the Voice model is untouched"
    gateway.release_voice()  # Voice ends
    back = gateway.rewarm_partner_after_voice()
    assert back["warmed"] is True and back["slug"] == TYPED, "the typed model returns, once"
    assert adapter.loaded == {typed_model[0].model_identifier}


def test_voice_on_releases_the_deep_model_too_when_that_is_what_was_resident(
    store: Engine, voice_model: ModelConfig, typed_model: tuple[ModelConfig, ModelConfig]
) -> None:
    _, deep = typed_model
    adapter = Residency()
    gateway = typed_gateway(store, adapter, typed_model, voice=voice_model)
    gateway.voice_releases_partner = True
    gateway.prepare_cognition(deep=True)
    gateway.warm_cognition()  # Voice On, with GPT-OSS resident
    assert adapter.loaded == {voice_model.model_identifier}
    assert ("release", deep.model_identifier) in adapter.events
