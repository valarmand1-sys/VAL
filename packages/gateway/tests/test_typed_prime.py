"""Typed prefix preparation — owner authorisation, 2 October 2026.

The persona-and-guidance prefix every typed turn shares is computed in the typed route's
runtime ahead of the turn: at start, when the Partner model returns after Voice, and (in
the "on" mode) after each typed answer once the service is idle. It is the existing prime
— governed, recorded as `prefix_prime`, attached to no conversation — pointed at the
typed route. Residency is respected and it never runs ahead of a request.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

import time

from sqlalchemy import Engine
from test_cognition_warming import PRODUCTION, a_gateway
from test_deliberation_machinery import clean_personas, ok, store
from test_prefix_prime import PrimingAdapter, rows


def test_the_typed_route_is_primed_and_recorded_like_any_prime(store: Engine) -> None:
    adapter = PrimingAdapter([ok("Good")])
    gateway = a_gateway(store, adapter)
    result = gateway.prime_typed_prefix()
    assert result["primed"] is True and result["outcome"] == "established"
    assert result["slug"] == PRODUCTION
    calls = rows(store, "select task_type::text as task_type, conversation_id from model_calls")
    assert [c["task_type"] for c in calls] == ["prefix_prime"]
    assert calls[0]["conversation_id"] is None


def test_nothing_is_primed_while_voice_holds_the_memory(store: Engine) -> None:
    """The typed route is never loaded beside the Voice model."""
    adapter = PrimingAdapter([ok("unused")])
    gateway = a_gateway(store, adapter)
    gateway._voice_holds_memory = True
    result = gateway.prime_typed_prefix()
    assert result["primed"] is False and "Voice holds the memory" in str(result["reason"])
    assert adapter.sent == [] and adapter.warmed == []


def test_no_prime_is_sent_while_a_typed_turn_is_in_flight(store: Engine) -> None:
    adapter = PrimingAdapter([ok("unused")])
    gateway = a_gateway(store, adapter)
    gateway.typed_turn_started()
    result = gateway.prime_typed_prefix()
    assert result["primed"] is False and "owner request is waiting" in str(result["reason"])
    assert adapter.sent == []
    gateway.typed_turn_finished()
    assert gateway.prime_typed_prefix()["primed"] is True


def test_the_partner_returning_after_voice_is_primed_only_when_the_mode_says_so(
    store: Engine,
) -> None:
    adapter = PrimingAdapter([ok("Good")])
    gateway = a_gateway(store, adapter)
    assert gateway.typed_prime == "off", "unset is the service as before"
    off = gateway.rewarm_partner_after_voice()
    assert off["warmed"] is True and "primed" not in off
    assert adapter.sent == []
    gateway.typed_prime = "transition"
    on = gateway.rewarm_partner_after_voice()
    assert on["warmed"] is True and on["primed"]["primed"] is True  # type: ignore[index]
    assert len(adapter.sent) == 1


def test_a_refresh_after_an_answer_is_coalesced_and_waits_for_idleness(store: Engine) -> None:
    adapter = PrimingAdapter([ok("Good"), ok("Good"), ok("Good")])
    gateway = a_gateway(store, adapter)
    gateway.typed_prime = "on"
    gateway.TYPED_REFRESH_IDLE_SECONDS = 0.05  # type: ignore[misc]
    # Two answers in quick succession: one refresh.
    gateway.typed_turn_started()
    gateway.typed_turn_finished()
    gateway.typed_turn_started()
    gateway.typed_turn_finished()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and gateway._typed_refresh_pending:
        time.sleep(0.02)
    assert len(adapter.sent) == 1, "coalesced"
    # A refresh owed while a new turn is in flight waits for it.
    gateway.typed_turn_started()
    gateway.typed_turn_finished()
    gateway.typed_turn_started()  # his next message arrives before the idle time
    time.sleep(0.2)
    assert len(adapter.sent) == 1, "nothing sent ahead of his turn"
    gateway.typed_turn_finished()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and gateway._typed_refresh_pending:
        time.sleep(0.02)
    assert len(adapter.sent) == 2


def test_the_transition_mode_does_not_refresh_after_answers(store: Engine) -> None:
    adapter = PrimingAdapter([ok("unused")])
    gateway = a_gateway(store, adapter)
    gateway.typed_prime = "transition"
    gateway.typed_turn_started()
    gateway.typed_turn_finished()
    time.sleep(0.1)
    assert adapter.sent == []
