"""The typed model at the API — owner order of 2 October 2026 and his ruling of 3 October.

A turn may ask for deep reasoning; a submission the desktop names is answered once and
can be cancelled; and `GET /cognition` says which model holds the memory and what is
ready, so the desktop shows preparation truthfully.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from test_service import OpenLedger, ScriptedAdapter, ok
from test_voice_service import ScriptedRecognizer

import val_domain.registry as registry
import val_policy.egress as egress_policy
from val_api.app import create_app
from val_api.contracts import TurnRequest
from val_domain.gateway import ModelConfig
from val_gateway.gateway import Gateway
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader
from val_gateway.provenance import verifier
from val_gateway.startup import PARTNER_SLUG, enable_typed_model

TYPED = "gemma-4-26b-a4b-styletune-v2-q4km-llamacpp-typed"


@pytest.fixture(autouse=True)
def the_rule_stands(monkeypatch: pytest.MonkeyPatch) -> None:
    """As production: AI processing is local (2 October 2026), so a typed turn is not
    classified on a hosted route first — it goes to its local model."""
    monkeypatch.setattr(egress_policy, "HOSTED_MODELS_FORBIDDEN", True)


@pytest.fixture
def typed_model() -> Iterator[tuple[ModelConfig, ModelConfig]]:
    saved, pin_only = registry.REGISTRY, set(registry.PIN_ONLY)
    try:
        yield enable_typed_model("gemma-4-26b-a4b-styletune-v2")
    finally:
        registry.REGISTRY = saved
        registry.PIN_ONLY.clear()
        registry.PIN_ONLY.update(pin_only)


def _client(
    store: Engine, adapter: ScriptedAdapter, models: tuple[ModelConfig, ModelConfig] | None
) -> tuple[TestClient, Gateway]:
    # The rule verifies where each local adapter sends: this one says this machine.
    adapter.destination = "http://127.0.0.1:8099/v1"  # type: ignore[attr-defined]
    gateway = Gateway(
        adapters={
            "anthropic": adapter,
            "openai": adapter,
            "lmstudio": adapter,
            "llamacpp": adapter,
        },
        recorder=lambda record: record_call(store, record),
        ledger=OpenLedger(),
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(store),
        verify_provenance=verifier(store),
    )
    if models is not None:
        gateway.typed_configuration, gateway.deep_configuration = models
        gateway.serialized_models = True
    client = TestClient(
        create_app(store, gateway, warnings=[], recognizers=lambda: ScriptedRecognizer())
    )
    return client, gateway


def _slugs(store: Engine) -> list[str]:
    with store.connect() as connection:
        ids = [
            row[0]
            for row in connection.execute(
                text(
                    "select model_config_id from model_calls "
                    "where task_type::text = 'conversation' order by created_at"
                )
            )
        ]
    return [registry.by_id(i).slug for i in ids]  # type: ignore[union-attr]


def test_the_request_carries_the_choice_and_the_submission_name() -> None:
    plain = TurnRequest(content="Hello.")
    assert plain.deep_reasoning is False and plain.request_id is None
    chosen = TurnRequest(content="Think it through.", deep_reasoning=True, request_id="a" * 12)
    assert chosen.deep_reasoning is True and chosen.request_id == "a" * 12


def test_a_deep_turn_is_asked_of_the_deep_route_and_an_ordinary_one_is_not(
    store: Engine, typed_model: tuple[ModelConfig, ModelConfig]
) -> None:
    adapter = ScriptedAdapter([ok("Good evening, my lord."), ok("Three reasons, my lord.")])
    client, _ = _client(store, adapter, typed_model)
    first = client.post("/turns", json={"content": "Good evening, Val.", "no_project": True})
    assert first.status_code == 200 and first.json()["kind"] == "answered"
    second = client.post(
        "/turns",
        json={"content": "Reason about the financing.", "no_project": True, "deep_reasoning": True},
    )
    assert second.status_code == 200 and second.json()["kind"] == "answered"
    assert _slugs(store) == [TYPED, PARTNER_SLUG]


def test_without_a_typed_model_the_flag_changes_nothing(store: Engine) -> None:
    adapter = ScriptedAdapter([ok("Good evening, my lord.")])
    client, _ = _client(store, adapter, None)
    got = client.post(
        "/turns", json={"content": "Good evening.", "no_project": True, "deep_reasoning": True}
    )
    assert got.status_code == 200
    assert _slugs(store) == [PARTNER_SLUG], "production's route, as ever"
    assert client.get("/cognition").json()["configured"] is False


def test_cognition_reports_the_models_and_voice(
    store: Engine, typed_model: tuple[ModelConfig, ModelConfig]
) -> None:
    client, _ = _client(store, ScriptedAdapter([]), typed_model)
    state = client.get("/cognition").json()
    assert state["configured"] is True
    assert (state["typed_model"], state["deep_model"]) == (TYPED, PARTNER_SLUG)
    assert state["voice_open"] is False and state["voice_holds_memory"] is False


def test_cancelling_an_unknown_submission_changes_nothing(store: Engine) -> None:
    client, _ = _client(store, ScriptedAdapter([]), None)
    assert client.post("/turns/cancel", json={"request_id": "never-submitted"}).json() == {
        "cancelled": False
    }


def test_a_submission_is_answered_once_and_can_be_cancelled_while_it_waits(
    store: Engine, typed_model: tuple[ModelConfig, ModelConfig]
) -> None:
    """A second request with the same name is refused while the first is in flight, and
    a cancel reaches the turn: his message is kept, unanswered, and nothing is invented."""
    import threading

    entered, release = threading.Event(), threading.Event()

    class Waits(ScriptedAdapter):
        def complete(self, *args, **kwargs) -> object:  # noqa: ANN002, ANN003
            entered.set()
            release.wait(timeout=10)
            return super().complete(*args, **kwargs)

    client, _ = _client(store, Waits([ok("Good evening, my lord.")]), typed_model)
    body = {"content": "Good evening, Val.", "no_project": True, "request_id": "submission-0001"}
    results: list[object] = []
    worker = threading.Thread(target=lambda: results.append(client.post("/turns", json=body)))
    worker.start()
    assert entered.wait(timeout=10), "the first submission is being answered"
    again = client.post("/turns", json=body)
    assert again.status_code == 409 and again.json()["detail"]["duplicate"] is True
    assert client.post("/turns/cancel", json={"request_id": "submission-0001"}).json() == {
        "cancelled": True
    }
    release.set()
    worker.join(timeout=10)
    with store.connect() as connection:
        mine = connection.execute(
            text("select count(*) from messages where role = 'user'")
        ).scalar_one()
    assert mine == 1, "submitted once"
    # Once it has settled, the name is free again: nothing is held for ever.
    assert client.post("/turns/cancel", json={"request_id": "submission-0001"}).json() == {
        "cancelled": False
    }


def test_while_the_model_is_prepared_the_stream_says_so_until_it_is_ready(
    store: Engine, typed_model: tuple[ModelConfig, ModelConfig]
) -> None:
    """Later stages are held while the model is prepared, and said once it is ready
    (found through the desktop, 3 October 2026: they replaced `preparing_model` at once)."""
    import json as _json

    client, gateway = _client(store, ScriptedAdapter([ok("Good evening, my lord.")]), typed_model)
    readiness = iter([False, False, False] + [True] * 100)
    original = gateway.cognition_state

    def slow_to_ready() -> dict[str, object]:
        state = dict(original())
        state["typed_ready"] = next(readiness)
        return state

    gateway.cognition_state = slow_to_ready  # type: ignore[method-assign]
    body = {"content": "Good evening, Val.", "no_project": True, "progress": True}
    with client.stream("POST", "/turns/stream", json=body) as response:
        frames = [line for line in response.iter_lines() if line]
    stages: list[tuple[str, bool]] = []
    saw_text = False
    for index, line in enumerate(frames):
        if line == "event: stage":
            stages.append((_json.loads(frames[index + 1][6:])["stage"], saw_text))
        if line == "event: delta":
            saw_text = True
    assert stages[0] == ("preparing_model", False)
    assert [s for s, _ in stages].count("preparing_model") == 1
    later = [s for s, _ in stages[1:]]
    assert later and later[-1] == "preparing_response", "the held stage is said once ready"
    assert len(later) == 1, "the intermediate stages were not flashed over the preparation"
