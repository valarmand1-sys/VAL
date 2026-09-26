"""The fast route inside Core — owner order, 26 September 2026 (§5).

A light turn is still Val's turn: assembled, sealed, persisted and recorded by Core.
Only the route differs, and the record says so. These tests hold the candidate switch
(promotion for this process only, restored afterwards), routing by task type, the
record, the Partner fallback when the light route fails before a word is delivered,
and that production — no switch — routes nothing light.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from test_deliberation_machinery import ScriptedAdapter, build_gateway, clean_personas, ok, store
from test_voice_input import a_conversation

import val_domain.registry as registry
from val_domain.gateway import (
    Admission,
    CapabilityProfile,
    GatewayError,
    GatewayErrorKind,
    TaskType,
)
from val_gateway.deliberate import send as deliberated_send
from val_gateway.projects import load_catalogue
from val_gateway.seal import SealRoute
from val_gateway.startup import (
    LIGHT_CANDIDATE_SLUG,
    configured_fast_route,
    enable_light_candidate,
)
from val_policy.light_conversation import FastRoute
from val_policy.routing import required_profile

BOTH = FastRoute(frozenset({1, 2}))


@pytest.fixture
def light_candidate() -> Iterator[None]:
    """The candidate promoted for this process, and the registry restored afterwards."""
    before = registry.REGISTRY
    enable_light_candidate()
    try:
        yield
    finally:
        registry.REGISTRY = before


def spoken(
    store: Engine, adapter: ScriptedAdapter, text_: str, conversation: UUID, fast: FastRoute
) -> object:
    return deliberated_send(
        store,
        build_gateway(store, adapter),
        text_,
        catalogue=load_catalogue(store),
        conversation_id=conversation,
        spoken=True,
        seal_route=SealRoute.UTTERANCE_FINALIZED,
        fast_route=fast,
    )


def calls(store: Engine, conversation: UUID) -> list[tuple[str, str]]:
    with store.connect() as connection:
        rows = connection.execute(
            text(
                "select task_type::text, model_config_id::text from model_calls "
                "where conversation_id = :c order by id"
            ),
            {"c": conversation},
        ).all()
    return [(row[0], row[1]) for row in rows]


def test_the_light_task_requires_the_light_floor_and_production_declares_none() -> None:
    assert required_profile(TaskType.LIGHT_CONVERSATION) is CapabilityProfile.LIGHT
    assert not any(
        CapabilityProfile.LIGHT in config.capability_profiles for config in registry.active()
    ), "no production configuration may carry light conversation"
    entry = registry.by_slug(LIGHT_CANDIDATE_SLUG)
    assert entry is not None and entry.admission is Admission.NOT_ADMITTED


def test_the_switch_promotes_the_candidate_for_this_process_only(light_candidate: None) -> None:
    promoted = next(c for c in registry.active() if c.slug == LIGHT_CANDIDATE_SLUG)
    assert CapabilityProfile.LIGHT in promoted.capability_profiles
    assert promoted.admission is Admission.PROVISIONALLY_ADMITTED


def test_the_registry_is_the_registry_again_afterwards() -> None:
    entry = registry.by_slug(LIGHT_CANDIDATE_SLUG)
    assert entry is not None and entry.admission is Admission.NOT_ADMITTED


def test_a_greeting_takes_the_light_route_and_the_record_says_so(
    store: Engine, light_candidate: None
) -> None:
    adapter = ScriptedAdapter([ok("Good evening, my lord. The house is quiet.")])
    conversation = a_conversation(store)
    outcome = spoken(store, adapter, "Good evening, Val.", conversation, BOTH)
    assert outcome.turn.val_message.content.startswith("Good evening")  # type: ignore[attr-defined]
    assert [call.config_slug for call in adapter.sent] == [LIGHT_CANDIDATE_SLUG]
    recorded = calls(store, conversation)
    assert [task for task, _ in recorded] == ["light_conversation"]


def test_a_request_takes_the_partner_route(store: Engine, light_candidate: None) -> None:
    adapter = ScriptedAdapter([ok("The invitation is not finished, my lord.")])
    conversation = a_conversation(store)
    spoken(store, adapter, "Good evening, Val. Did you finish the invitation?", conversation, BOTH)
    assert adapter.sent[0].config_slug != LIGHT_CANDIDATE_SLUG
    assert [task for task, _ in calls(store, conversation)] == ["conversation"]


def test_without_the_switch_nothing_is_light(store: Engine) -> None:
    adapter = ScriptedAdapter([ok("Good evening, my lord.")])
    conversation = a_conversation(store)
    spoken(store, adapter, "Good evening, Val.", conversation, FastRoute())
    assert adapter.sent[0].config_slug != LIGHT_CANDIDATE_SLUG
    assert [task for task, _ in calls(store, conversation)] == ["conversation"]


def test_a_light_route_that_fails_before_a_word_falls_back_to_the_partner_route(
    store: Engine, light_candidate: None
) -> None:
    adapter = ScriptedAdapter(
        [
            GatewayError(GatewayErrorKind.PROVIDER_ERROR, "the light runtime is gone"),
            ok("Good evening, my lord."),
        ]
    )
    conversation = a_conversation(store)
    outcome = spoken(store, adapter, "Good evening, Val.", conversation, BOTH)
    assert outcome.turn.val_message.content == "Good evening, my lord."  # type: ignore[attr-defined]
    assert adapter.sent[0].config_slug == LIGHT_CANDIDATE_SLUG
    assert adapter.sent[1].config_slug != LIGHT_CANDIDATE_SLUG
    with store.connect() as connection:
        messages = (
            connection.execute(
                text(
                    "select role::text from messages where conversation_id = :c order by sequence"
                ),
                {"c": conversation},
            )
            .scalars()
            .all()
        )
    assert messages == ["user", "val"], "one message of his, one answer of hers"
    recorded = [task for task, _ in calls(store, conversation)]
    assert recorded[-1] == "conversation" and "light_conversation" in recorded


def test_the_setting_is_read_and_refused_when_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VAL_FAST_ROUTE_TIERS", raising=False)
    assert configured_fast_route() == (FastRoute(), None)
    monkeypatch.setenv("VAL_FAST_ROUTE_TIERS", "1,2")
    assert configured_fast_route()[0].tiers == frozenset({1, 2})
    monkeypatch.setenv("VAL_FAST_ROUTE_TIERS", "fast")
    assert configured_fast_route()[1] is not None
