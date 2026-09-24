# ruff: noqa: F811, F401 - fixtures and harness imported by name
"""Warming the cognition runtime early — pre-WP3 latency pass §12 and §19.

A local model carries a one-hour idle TTL, so the first turn after an idle hour
pays its load while the owner waits: measured **9.290 s** against **0.148 s** when
it was already resident. Warming does the same readiness call earlier, on its own
thread, while he is still speaking.

What these hold is that it is an **optimisation and never a gate**: the turn still
asks, the turn's answer still governs, a warming failure breaks nothing, and
nothing about routing, eligibility, policy or the model's input changes.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from uuid import UUID

import pytest
from gateway_fakes import FakeLedger
from sqlalchemy import Engine
from test_deliberation_machinery import (
    ScriptedAdapter,
    classifier_says,
    clean_personas,
    ok,
    store,
)
from test_voice_input import MARKER, ScriptedRecognizer, a_conversation, final, started

from val_domain.gateway import ModelConfig
from val_domain.provider import LocalRuntimeUnavailableError
from val_domain.registry import by_slug
from val_gateway.gateway import Gateway
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader
from val_gateway.provenance import verifier
from val_gateway.voice import VoiceSession

PRODUCTION = "gpt-oss-20b-mxfp4-mlx-lmstudio-partner"


@dataclass
class LocalAdapter(ScriptedAdapter):
    """A scripted adapter that also declares a local runtime it can bring up."""

    warmed: list[str] = field(default_factory=list)
    refuses: bool = False

    def ensure_runtime_ready(self, config: ModelConfig) -> Mapping[str, object]:
        self.warmed.append(config.slug)
        if self.refuses:
            raise LocalRuntimeUnavailableError("the runtime could not be brought up")
        return {"server_found_running": True, "model_found_loaded": True, "model_loaded": False}


def a_gateway(engine: Engine, adapter: ScriptedAdapter) -> Gateway:
    return Gateway(
        adapters={"anthropic": adapter, "openai": adapter, "lmstudio": adapter},
        recorder=lambda record: record_call(engine, record),
        ledger=FakeLedger(),
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(engine),
        verify_provenance=verifier(engine),
    )


# --- what warming is ---------------------------------------------------------------------


def test_warming_brings_up_the_route_an_ordinary_turn_would_use(store: Engine) -> None:
    adapter = LocalAdapter([])
    result = a_gateway(store, adapter).warm_cognition()
    assert adapter.warmed == [PRODUCTION], "the admitted partner route, and only it"
    assert result["warmed"] is True
    assert result["slug"] == PRODUCTION
    assert result["model_found_loaded"] is True


def test_warming_reports_a_failure_and_does_not_raise(store: Engine) -> None:
    """The turn's own readiness call is the one that must fail honestly."""
    adapter = LocalAdapter([], refuses=True)
    result = a_gateway(store, adapter).warm_cognition()
    assert result["warmed"] is False
    assert "could not be brought up" in str(result["reason"])
    assert adapter.warmed == [PRODUCTION], "it tried"


def test_a_route_with_no_local_runtime_is_left_alone(store: Engine) -> None:
    adapter = ScriptedAdapter([])  # declares no local runtime
    result = a_gateway(store, adapter).warm_cognition()
    assert result["warmed"] is False
    assert "no admitted partner route has a local runtime" in str(result["reason"])


def test_warming_picks_the_route_a_turn_would_pick_and_not_the_first_listed() -> None:
    """The defect this test found: the first version warmed whichever admitted
    partner route the registry happened to list first — a paid cloud route with no
    runtime — and so warmed nothing that mattered. Routes are ranked cheapest
    first, exactly as a turn ranks them, and only a local one has anything to warm.
    """
    from val_domain.gateway import CapabilityProfile
    from val_domain.registry import active
    from val_policy.routing import is_admitted, satisfies_profile

    partner = [
        config
        for config in active()
        if is_admitted(config) and satisfies_profile(config, CapabilityProfile.PARTNER)
    ]
    cheapest = min(partner, key=lambda config: config.cost_per_mtok_in_usd)
    assert cheapest.slug == PRODUCTION, (
        "the local route is the cheapest partner route, which is why a turn selects it"
    )
    assert cheapest.cost_per_mtok_in_usd == 0.0


def test_warming_changes_no_routing_and_no_eligibility(store: Engine) -> None:
    """It is the same readiness call, earlier. Nothing about the turn moves."""
    production = by_slug(PRODUCTION)
    assert production is not None
    before = (
        production.reasoning_effort,
        production.capability_profiles,
        production.eligible_classifications,
        production.context_window_tokens,
        production.admission,
    )
    a_gateway(store, LocalAdapter([])).warm_cognition()
    after = by_slug(PRODUCTION)
    assert after is not None
    assert (
        after.reasoning_effort,
        after.capability_profiles,
        after.eligible_classifications,
        after.context_window_tokens,
        after.admission,
    ) == before


def test_warming_sends_nothing_to_any_provider(store: Engine) -> None:
    adapter = LocalAdapter([])
    a_gateway(store, adapter).warm_cognition()
    assert adapter.sent == [], "readiness is not a call to the model"


# --- how a voice session uses it ---------------------------------------------------------


def test_opening_a_voice_session_warms_the_runtime_while_he_speaks(store: Engine) -> None:
    """Off the critical path: it runs on its own thread from `start`."""
    warmed = threading.Event()
    calls: list[float] = []

    def warm() -> object:
        calls.append(time.monotonic())
        warmed.set()
        return {"warmed": True, "slug": PRODUCTION}

    recognizer = ScriptedRecognizer(batches=[[started(1)]])
    session = VoiceSession(
        store,
        recognizer,
        submit=lambda content, existing, *, on_delta=None: pytest.fail("no turn was sent"),
        conversation_id=a_conversation(store),
        warm=warm,
    )
    session.start()
    assert warmed.wait(timeout=5), "warming began when the session opened"
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and session.warmed is None:
        time.sleep(0.01)
    assert session.warmed == {"warmed": True, "slug": PRODUCTION}, "and its result is on record"
    assert len(calls) == 1, "once per session, not once per turn"
    session.close()


def test_a_session_with_nothing_to_warm_simply_listens(store: Engine) -> None:
    recognizer = ScriptedRecognizer(batches=[[started(1)]])
    session = VoiceSession(
        store,
        recognizer,
        submit=lambda content, existing, *, on_delta=None: pytest.fail("no turn was sent"),
        conversation_id=a_conversation(store),
    )
    session.start()
    assert session.warmed is None
    assert session.snapshot().error is None
    session.close()


def test_a_warming_failure_does_not_stop_the_session_hearing_him(store: Engine) -> None:
    """Warming is not a gate. A session whose warm-up failed still works."""

    def warm() -> object:
        raise RuntimeError("the runtime is not there")

    recognizer = ScriptedRecognizer(batches=[[started(1), final(1, "Are you there?")]])
    submitted: list[str] = []

    def submit(content: str, existing: UUID | None, *, on_delta: object = None) -> object:
        submitted.append(content)
        raise AssertionError("stop here: the turn was reached, which is the point")

    session = VoiceSession(
        store,
        recognizer,
        submit=submit,  # type: ignore[arg-type]
        conversation_id=a_conversation(store),
        warm=warm,
        resume_grace_seconds=0.0,
    )
    session.start()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and session.warmed is None:
        time.sleep(0.01)
    assert session.warmed is not None
    assert session.warmed["warmed"] is False  # type: ignore[index]
    assert "not there" in str(session.warmed["reason"])  # type: ignore[index]

    session.feed(MARKER)
    session.await_turn(timeout=15.0)
    assert submitted == ["Are you there?"], "the session heard him and submitted the turn"
    session.close()
