"""Blind-position calls request no prompt cache — ruling, 13 September 2026.

Through the full deliberated path with a gateway configured for one-hour
caching: the blind-position call is sent with no cache lifetime, reserved at the
base input rate, and writes no cache-usage row; its persona attribution and
route are unchanged; and the other calls ask for exactly what they asked for
before — the response and strip calls the configured lifetime, the classifier
none (its prefix is below Haiku's minimum). No provider is contacted.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from test_service import OpenLedger, ScriptedAdapter, deliberated_script

from val_api.app import create_app
from val_domain.gateway import CacheTtl, Message, ModelConfig, TaskType
from val_domain.registry import by_slug
from val_gateway.gateway import Gateway
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader
from val_gateway.provenance import verifier
from val_policy.budget import maximum_cost
from val_providers.base import ProviderResult


@dataclass
class RecordingAdapter(ScriptedAdapter):
    """The scripted provider, remembering what each call asked for."""

    sent: list[tuple[str | None, bool, CacheTtl | None]] = field(default_factory=list)
    parts: list[tuple[tuple[str, ...], int]] = field(default_factory=list)

    def complete(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> ProviderResult:
        self.sent.append((config.slug, output_schema is not None, cache_ttl))
        body = tuple(m.content for m in messages) + ((system,) if system is not None else ())
        self.parts.append((body, max_output_tokens))
        return super().complete(
            config, messages, system, max_output_tokens, output_schema, cache_ttl
        )


@dataclass
class RecordingLedger(OpenLedger):
    reserved: list[tuple[TaskType, str, float]] = field(default_factory=list)

    def reserve(
        self,
        config: ModelConfig,
        max_cost_usd: float,
        task_type: TaskType,
        project_id: UUID | None,
        exchange: object = None,
    ) -> object:
        self.reserved.append((task_type, config.slug, max_cost_usd))
        return super().reserve(config, max_cost_usd, task_type, project_id, exchange)


def test_the_blind_call_requests_no_cache_and_everything_else_is_unchanged(store: Engine) -> None:
    adapter = RecordingAdapter(deliberated_script())
    ledger = RecordingLedger()
    gateway = Gateway(
        adapters={"anthropic": adapter, "openai": adapter},
        recorder=lambda record: record_call(store, record),
        ledger=ledger,  # type: ignore[arg-type]
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(store),
        verify_provenance=verifier(store),
        cache_ttl=CacheTtl.ONE_HOUR,
    )
    api = TestClient(create_app(store, gateway))
    turn = api.post(
        "/turns",
        json={
            "content": "I think we should open on the wide shot. How should the film open?",
            "project": "Project Alpha",
        },
    ).json()
    assert turn["kind"] == "answered" and turn["glimpse"]["blind"]["ordering"] == "enforced"

    by_task = dict(
        zip(
            ("classification", "strip", "blind_position", "conversation"), adapter.sent, strict=True
        )
    )
    assert by_task["blind_position"] == ("opus-5-medium", True, None)
    assert by_task["conversation"] == ("opus-5-medium", False, CacheTtl.ONE_HOUR)
    assert by_task["strip"] == ("sonnet-5-low", True, CacheTtl.ONE_HOUR)
    assert by_task["classification"][2] is None

    with store.connect() as connection:
        calls = connection.execute(
            text(
                "select m.task_type::text, m.persona_id, m.model_config_id, "
                "       (select count(*) from model_call_cache_usage u "
                "         where u.model_call_id = m.id) "
                "  from model_calls m order by m.created_at"
            )
        ).all()
        active_persona = connection.execute(
            text("select id from personas where is_active")
        ).scalar_one()
    rows = {row[0]: row for row in calls}
    opus_config = by_slug("opus-5-medium")
    assert opus_config is not None
    assert rows["blind_position"][2] == opus_config.id, "route unchanged: opus-5-medium"
    assert rows["blind_position"][1] == active_persona, "persona attribution unchanged"
    assert rows["blind_position"][3] == 0, "no cache-usage row: nothing was requested"
    assert rows["conversation"][3] == 1 and rows["strip"][3] == 1

    blind_reserved = next(
        cost for task, _, cost in ledger.reserved if task is TaskType.BLIND_POSITION
    )
    opus = by_slug("opus-5-medium")
    assert opus is not None
    blind_parts, blind_max_output = adapter.parts[2]
    assert blind_reserved == maximum_cost(opus, blind_parts, blind_max_output, None), (
        "reserved at the base input rate"
    )
    assert blind_reserved < maximum_cost(opus, blind_parts, blind_max_output, CacheTtl.ONE_HOUR)
