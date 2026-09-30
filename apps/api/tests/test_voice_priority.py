"""Voice has priority over typed work — owner order of 30 September 2026 §1.

While a Voice session is open and a Voice model holds the memory, `POST /turns` and
`POST /turns/stream` are refused with 409 before anything is written; the refusal carries
`voice_active` and the explanation he reads. When Voice ends the same request proceeds.
Without the Voice model switch the routes are as they were.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from test_service import OpenLedger, ScriptedAdapter, classifier_says, ok
from test_voice_service import ScriptedRecognizer

import val_domain.registry as registry
from val_api.app import create_app
from val_domain.gateway import ModelConfig
from val_gateway.gateway import Gateway
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader
from val_gateway.provenance import verifier
from val_gateway.startup import enable_voice_model


@pytest.fixture
def voice_model() -> Iterator[ModelConfig]:
    """The pin-only Voice model, enabled for this process only (as `VAL_VOICE_MODEL` does)."""
    saved, pin_only = registry.REGISTRY, set(registry.PIN_ONLY)
    try:
        yield enable_voice_model("gemma-4-26b-a4b")
    finally:
        registry.REGISTRY = saved
        registry.PIN_ONLY.clear()
        registry.PIN_ONLY.update(pin_only)


def _client(store: Engine, adapter: ScriptedAdapter, pinned: ModelConfig | None) -> TestClient:
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
    gateway.voice_configuration = pinned
    gateway.voice_releases_partner = pinned is not None
    return TestClient(
        create_app(store, gateway, warnings=[], recognizers=lambda: ScriptedRecognizer())
    )


def _messages(store: Engine) -> int:
    with store.connect() as connection:
        return connection.execute(text("select count(*) from messages")).scalar_one()


def test_typed_work_waits_while_voice_is_on_and_proceeds_when_it_ends(
    store: Engine, voice_model: ModelConfig
) -> None:
    adapter = ScriptedAdapter([classifier_says("not_consequential"), ok("Lisbon, my lord.")])
    client = _client(store, adapter, voice_model)
    opened = client.post("/voice/sessions", json={"project": "Project Alpha"})
    assert opened.status_code == 201, opened.text
    session = opened.json()["session"]
    before = _messages(store)

    refused = client.post(
        "/turns", json={"content": "Capital of Portugal?", "project": "Project Alpha"}
    )
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["voice_active"] is True
    assert "Typed messages wait until Voice ends" in detail["message"]
    streamed = client.post(
        "/turns/stream", json={"content": "Capital of Portugal?", "project": "Project Alpha"}
    )
    assert streamed.status_code == 409
    assert _messages(store) == before, "nothing written"
    assert adapter.calls == 0, "nothing sent to any model"

    client.post(f"/voice/sessions/{session}/close")
    answered = client.post(
        "/turns", json={"content": "Capital of Portugal?", "project": "Project Alpha"}
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["kind"] == "answered", answered.text[:900]
    assert _messages(store) == before + 2, "his message and her answer, once"


def test_without_the_voice_model_switch_typed_work_is_not_held(store: Engine) -> None:
    adapter = ScriptedAdapter([classifier_says("not_consequential"), ok("Lisbon, my lord.")])
    client = _client(store, adapter, None)
    opened = client.post("/voice/sessions", json={"project": "Project Alpha"})
    assert opened.status_code == 201, opened.text
    answered = client.post(
        "/turns", json={"content": "Capital of Portugal?", "project": "Project Alpha"}
    )
    assert answered.status_code == 200, answered.text
