"""A different conversational model for Voice — owner order of 29 September 2026.

Unset (production), the registry is as written and nothing is pinned. Set, the candidate
is pin-only: routing never selects it, a Voice turn is asked of it, a typed turn outside
Voice is asked of the Partner route, and a Voice call that fails before any word is
delivered is answered by the Partner route once.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import pytest
from gateway_fakes import FakeLedger
from sqlalchemy import Engine, text
from test_deliberation_machinery import ScriptedAdapter, clean_personas, ok, store
from test_voice_input import a_conversation

import val_domain.registry as registry
from val_domain.conversation import StoredRole
from val_domain.gateway import (
    Admission,
    Egress,
    GatewayError,
    GatewayErrorKind,
    Message,
    ModelConfig,
    TurnReference,
)
from val_domain.project import ResolutionSource, ResolvedProject
from val_gateway import conversations
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
    """A local runtime that records loads and releases by model identifier (§10.8).

    `loaded` mirrors what it has been told, so the gateway learns residency from it the
    way it learns it from LM Studio or the llama.cpp server.
    """

    def __init__(self) -> None:
        super().__init__([])
        self.events: list[tuple[str, str]] = []
        self.loaded: set[str] = set()

    def ensure_runtime_ready(self, config: ModelConfig) -> dict[str, object]:
        self.events.append(("load", config.model_identifier))
        self.loaded.add(config.model_identifier)
        return {"model_loaded": True}

    def release_model(self, config: ModelConfig) -> dict[str, object]:
        self.events.append(("release", config.model_identifier))
        self.loaded.discard(config.model_identifier)
        return {"released": True, "model": config.model_identifier}

    def model_loaded(self, config: ModelConfig) -> bool:
        return config.model_identifier in self.loaded

    def kinds(self) -> list[str]:
        return [f"{kind}:{model.split('/')[-1][:8]}" for kind, model in self.events]


def _partner() -> ModelConfig:
    partner = registry.by_slug(PARTNER_SLUG)
    assert partner is not None
    return partner


def test_unset_voice_on_keeps_the_partner_model_resident(
    store: Engine, voice_model: ModelConfig
) -> None:
    adapter = Residency()
    adapter.loaded.add(_partner().model_identifier)
    gateway = gateway_with(store, adapter, voice_model)
    warmed = gateway.warm_cognition()
    assert warmed["warmed"] is True and "transitions" not in warmed
    assert adapter.events == [("load", voice_model.model_identifier)]
    assert _partner().model_identifier in adapter.loaded, "both resident, as today"


def test_set_voice_on_releases_the_partner_model_and_voice_off_brings_it_back(
    store: Engine, voice_model: ModelConfig
) -> None:
    adapter = Residency()
    adapter.loaded.add(_partner().model_identifier)
    gateway = gateway_with(store, adapter, voice_model)
    gateway.voice_releases_partner = True
    warmed = gateway.warm_cognition()
    (transition,) = warmed["transitions"]  # type: ignore[index]
    assert transition["released"] == PARTNER_SLUG and transition["for"] == voice_model.slug
    # The release comes first, so the Voice model loads into the memory it gave back.
    assert adapter.events == [
        ("release", _partner().model_identifier),
        ("load", voice_model.model_identifier),
    ]
    assert adapter.loaded == {voice_model.model_identifier}, "one model resident"
    back = gateway.rewarm_partner_after_voice()
    assert back["warmed"] is True and back["slug"] == PARTNER_SLUG
    assert adapter.events[-1] == ("load", _partner().model_identifier)


def test_voice_on_with_nothing_loaded_releases_nothing(
    store: Engine, voice_model: ModelConfig
) -> None:
    adapter = Residency()  # the Partner model idled out of memory earlier
    gateway = gateway_with(store, adapter, voice_model)
    gateway.voice_releases_partner = True
    warmed = gateway.warm_cognition()
    assert warmed["transitions"] == []  # type: ignore[index]
    assert adapter.events == [("load", voice_model.model_identifier)]


def test_with_nothing_pinned_the_switch_releases_nothing(store: Engine) -> None:
    adapter = Residency()
    gateway = gateway_with(store, adapter, None)
    gateway.voice_releases_partner = True
    warmed = gateway.warm_cognition()
    assert "transitions" not in warmed
    assert all(kind == "load" for kind, _ in adapter.events)


def _holding_gateway(store: Engine, adapter: Residency, voice_model: ModelConfig) -> Gateway:
    gateway = gateway_with(store, adapter, voice_model)
    gateway.voice_releases_partner = True
    gateway.warm_cognition()  # Voice On: the Partner model released, the memory held
    return gateway


def _typed_call(store: Engine, gateway: Gateway, words: str) -> object:
    """A typed conversational call at the gateway seam, as another request thread makes it."""
    (alpha,) = load_catalogue(store).matching("project-alpha")
    scope = ResolvedProject(project=alpha, via=ResolutionSource.EXPLICIT_SELECTION)
    conversation = conversations.create(store, scope=scope, title="Typed").id
    message = conversations.append(store, conversation, role=StoredRole.USER, content=words)
    return gateway.converse(
        (Message(role="user", content=words),),
        scope=scope,
        turn=TurnReference(conversation_id=conversation, message_id=message.id),
        egress=Egress.LOCAL_ONLY,
    )


def _wait_for(predicate, seconds: float = 10.0) -> bool:  # noqa: ANN001
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def test_a_typed_turn_elsewhere_during_voice_replaces_the_voice_model_and_it_returns(
    store: Engine, voice_model: ModelConfig
) -> None:
    """§10.8: serialized model use. The Voice model is released before the Partner model is
    loaded; after the typed call settles the Voice model is brought back, off the path."""
    adapter = Residency()
    adapter.loaded.add(_partner().model_identifier)
    adapter.script = [ok("Lisbon, my lord.")]
    notes: list[str] = []
    gateway = Gateway(
        adapters={"lmstudio": adapter, "llamacpp": adapter},
        recorder=lambda record: record_call(store, record),
        ledger=FakeLedger(),
        observe_block=notes.append,
        persona_loader=DatabasePersonaLoader(store),
        verify_provenance=verifier(store),
    )
    gateway.voice_configuration = voice_model
    gateway.voice_releases_partner = True
    gateway.warm_cognition()
    del adapter.events[:]
    _typed_call(store, gateway, "What is the capital of Portugal?")
    assert adapter.events[:2] == [
        ("release", voice_model.model_identifier),
        ("load", _partner().model_identifier),
    ], "the Voice model released first, then the Partner model loaded — never both"
    assert any("model transition" in note for note in notes)
    # The return runs on its own thread once the call has settled.
    assert _wait_for(lambda: ("load", voice_model.model_identifier) in adapter.events[2:])
    assert adapter.events[2:4] == [
        ("release", _partner().model_identifier),
        ("load", voice_model.model_identifier),
    ], "the Partner model released, then the Voice model back"
    assert adapter.loaded == {voice_model.model_identifier}
    # Voice ending clears the hold: afterwards a typed turn keeps the Partner model resident.
    gateway.release_voice()
    adapter.script = [ok("Madrid, my lord.")]
    del adapter.events[:]
    _typed_call(store, gateway, "And of Spain?")
    assert adapter.events == [("load", _partner().model_identifier)]


class Blocking(Residency):
    """Answers only once `go` is set, and records each completed call."""

    def __init__(self) -> None:
        super().__init__()
        self.go = threading.Event()
        self.started = threading.Semaphore(0)

    def complete(self, *args, **kwargs) -> object:  # noqa: ANN002, ANN003
        self.started.release()
        assert self.go.wait(10), "the test never let the call proceed"
        result = super().complete(*args, **kwargs)
        self.events.append(("complete", "-"))
        return result


def test_a_release_never_lands_on_a_model_another_request_is_using(
    store: Engine, voice_model: ModelConfig
) -> None:
    """§10.8: a transition waits for the calls using the model it must release."""
    adapter = Blocking()
    adapter.script = [ok("Lisbon, my lord.")]
    gateway = gateway_with(store, adapter, voice_model)
    gateway.voice_releases_partner = True
    typed = threading.Thread(target=_typed_call, args=(store, gateway, "Capital of Portugal?"))
    typed.start()
    assert adapter.started.acquire(timeout=10)  # the Partner model is answering now
    on = threading.Thread(target=gateway.warm_cognition)  # Voice On arrives meanwhile
    on.start()
    time.sleep(0.3)
    assert ("release", _partner().model_identifier) not in adapter.events, "not while in use"
    assert on.is_alive(), "Voice On waits for the call to settle"
    adapter.go.set()
    typed.join(10)
    on.join(10)
    assert adapter.events[-3:] == [
        ("complete", "-"),
        ("release", _partner().model_identifier),
        ("load", voice_model.model_identifier),
    ], "released after the call settled, then the Voice model loaded"


def test_the_fallback_during_voice_replaces_the_voice_model_and_it_returns(
    store: Engine, voice_model: ModelConfig
) -> None:
    class VoiceFails(Residency):
        def complete(self, *args, **kwargs) -> object:  # noqa: ANN002, ANN003
            if not any(kind == "complete" for kind, _ in self.events):
                self.events.append(("complete", "voice-failed"))
                raise GatewayError(GatewayErrorKind.PROVIDER_ERROR, "scripted Voice model failure")
            self.events.append(("complete", "-"))
            return super().complete(*args, **kwargs)

    adapter = VoiceFails()
    adapter.script = [ok("Good evening, my lord.")]
    gateway = _holding_gateway(store, adapter, voice_model)
    got = say(store, gateway, "Good evening, Val.", a_conversation(store), spoken=True)
    assert got.turn.val_message.content == "Good evening, my lord."  # type: ignore[attr-defined]
    fallback = adapter.events.index(("complete", "voice-failed"))
    assert adapter.events[fallback + 1 : fallback + 4] == [
        ("release", voice_model.model_identifier),
        ("load", _partner().model_identifier),
        ("complete", "-"),
    ], "the fallback released the Voice model, loaded the Partner model, answered"
    assert _wait_for(lambda: adapter.events[-1] == ("load", voice_model.model_identifier))
    assert adapter.loaded == {voice_model.model_identifier}, "and the Voice model is back"


def test_a_prefill_during_a_typed_call_waits_rather_than_reloading_beside_it(
    store: Engine, voice_model: ModelConfig
) -> None:
    """§10.8 (found live, 00:35): the session's prefill at speech start reached the runtime
    directly and brought the Voice model back beside the Partner model. Every readiness
    path now goes through the transition, so the prefill waits for the typed call."""
    adapter = Blocking()
    adapter.script = [ok("Lisbon, my lord."), ok(".")]  # the typed answer, the prime's token
    gateway = _holding_gateway(store, adapter, voice_model)
    typed = threading.Thread(target=_typed_call, args=(store, gateway, "Capital of Portugal?"))
    typed.start()
    assert adapter.started.acquire(timeout=10)  # the Partner model is answering now
    assert adapter.loaded == {_partner().model_identifier}, "the Voice model was released for it"
    results: list[object] = []
    prefill = threading.Thread(
        target=lambda: results.append(
            gateway.prefill_turn((Message(role="user", content="state block"),))
        )
    )
    prefill.start()
    time.sleep(0.3)
    assert adapter.loaded == {_partner().model_identifier}, "not reloaded beside it"
    assert prefill.is_alive(), "the prefill waits for the typed call to settle"
    adapter.go.set()
    typed.join(10)
    prefill.join(10)
    assert _wait_for(lambda: adapter.loaded == {voice_model.model_identifier})
    assert ("release", _partner().model_identifier) in adapter.events
