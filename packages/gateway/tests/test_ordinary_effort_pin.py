"""The LOW-effort experiment's pin through Core — 28 September 2026 (EFFORT_EXPERIMENT.md §1).

Only reasoning effort changes, only for an eligible turn, only by Core's pin: the LOW
copy of the partner entry is pin-only (routing never selects it), an ineligible turn is
MEDIUM, a failing LOW call falls back to MEDIUM once before any word is delivered, and
with the switch off (production) nothing is different.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from test_deliberation_machinery import ScriptedAdapter, build_gateway, clean_personas, ok, store
from test_voice_input import a_conversation

import val_domain.registry as registry
import val_gateway.deliberate as core
from val_domain.gateway import GatewayError, GatewayErrorKind, ReasoningEffort
from val_gateway.deliberate import send
from val_gateway.projects import load_catalogue
from val_gateway.seal import SealRoute
from val_gateway.startup import ORDINARY_LOW_SLUG, ORDINARY_LOW_SOURCE_SLUG, enable_ordinary_low


@pytest.fixture
def low() -> Iterator[object]:
    saved, pin_only = registry.REGISTRY, set(registry.PIN_ONLY)
    config = enable_ordinary_low()
    core.ORDINARY_LOW = config
    try:
        yield config
    finally:
        core.ORDINARY_LOW = None
        registry.REGISTRY = saved
        registry.PIN_ONLY.clear()
        registry.PIN_ONLY.update(pin_only)


def _slugs(store: Engine) -> list[str]:
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


def _say(store: Engine, adapter: ScriptedAdapter, words: str, conversation: object) -> object:
    return send(
        store,
        build_gateway(store, adapter),
        words,
        catalogue=load_catalogue(store),
        conversation_id=conversation,
        spoken=True,
        seal_route=SealRoute.UTTERANCE_FINALIZED,
    )


def test_the_copy_differs_from_the_partner_in_effort_alone(low: object) -> None:
    source = registry.by_slug(ORDINARY_LOW_SOURCE_SLUG)
    copy = registry.by_slug(ORDINARY_LOW_SLUG)
    assert source is not None and copy is not None
    assert copy.reasoning_effort is ReasoningEffort.LOW
    differing = {k for k in type(source).model_fields if getattr(source, k) != getattr(copy, k)}
    assert differing == {"id", "slug", "reasoning_effort"}
    assert copy not in registry.active(), "routing never selects it"


def test_an_eligible_turn_is_pinned_low_and_an_ineligible_one_is_not(
    store: Engine, low: object
) -> None:
    adapter = ScriptedAdapter([ok("Lisbon, my lord."), ok("I would need the text, my lord.")])
    conversation = a_conversation(store)
    _say(store, adapter, "What is the capital of Portugal?", conversation)
    _say(store, adapter, "What do you think of the second act?", conversation)
    assert _slugs(store) == [ORDINARY_LOW_SLUG, ORDINARY_LOW_SOURCE_SLUG]


def test_a_failing_low_call_falls_back_to_medium_once(store: Engine, low: object) -> None:
    class FailsFirst(ScriptedAdapter):
        calls = 0

        def complete(self, *args, **kwargs) -> object:  # noqa: ANN002, ANN003
            FailsFirst.calls += 1
            if FailsFirst.calls == 1:
                raise GatewayError(GatewayErrorKind.PROVIDER_ERROR, "scripted LOW failure")
            return super().complete(*args, **kwargs)

    adapter = FailsFirst([ok("Lisbon, my lord.")])
    got = _say(store, adapter, "What is the capital of Portugal?", a_conversation(store))
    assert got.turn.val_message.content == "Lisbon, my lord."  # type: ignore[attr-defined]
    with store.connect() as connection:
        answers = connection.execute(
            text("select count(*) from messages where role = 'val'")
        ).scalar_one()
    assert answers == 1, "one answer, from MEDIUM"


def test_with_the_switch_off_nothing_is_pinned(store: Engine) -> None:
    assert core.ORDINARY_LOW is None
    adapter = ScriptedAdapter([ok("Lisbon, my lord.")])
    _say(store, adapter, "What is the capital of Portugal?", a_conversation(store))
    assert _slugs(store) == [ORDINARY_LOW_SOURCE_SLUG]
