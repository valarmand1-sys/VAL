"""The prime carries only stable material — §4 of the 27 September 2026 order.

Under the request-construction experiment the primed system is the persona followed by
the static separator and nothing else: no record state, no conversation content, no hidden
reasoning; the plan is asked for the developer-end boundary. With the switch off, the
prime is exactly what production sends.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from sqlalchemy import Engine
from test_deliberation_machinery import clean_personas, ok, store
from test_prefix_prime import PrimingAdapter, a_gateway

import val_gateway.context as context
from val_domain.gateway import CacheTtl, Message, ModelConfig
from val_domain.provider import PrefixPrimePlan


@dataclass
class RecordingPrimingAdapter(PrimingAdapter):
    systems: list[str] = field(default_factory=list)
    boundaries: list[str] = field(default_factory=list)
    captured: list[tuple[str | None, tuple[Message, ...]]] = field(default_factory=list)

    def plan_prefix_prime(
        self, config: ModelConfig, system: str, *, boundary: str = "user_header"
    ) -> PrefixPrimePlan:
        self.systems.append(system)
        self.boundaries.append(boundary)
        return super().plan_prefix_prime(config, system)

    def complete(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> object:
        self.captured.append((system, messages))
        return super().complete(config, messages, system, max_output_tokens, output_schema)


def test_the_prime_under_the_experiment_is_persona_plus_static_separator_only(
    store: Engine,
) -> None:
    adapter = RecordingPrimingAdapter([ok("Good"), ok("Good")])
    gateway = a_gateway(store, adapter)
    persona = gateway.active_persona_content()
    assert persona
    context.ENVELOPE_IN_SYSTEM = True
    try:
        gateway.prime_prefix(routes=("partner",))
    finally:
        context.ENVELOPE_IN_SYSTEM = False
    assert adapter.boundaries == ["developer_end"]
    assert adapter.systems == [persona + context.ENVELOPE_SYSTEM_SEPARATOR]
    system, messages = adapter.captured[-1]
    assert system == persona + context.ENVELOPE_SYSTEM_SEPARATOR
    assert context.STATE_ENVELOPE_MARKER not in (system or "")
    assert [m.role for m in messages] == ["user"] and messages[
        0
    ].content == "ok ok ok ok ok ok ok ok"
    for word in ("prior_record_state", "current_time", "<|channel|>", "<|start|>"):
        assert word not in (system or ""), word


def test_the_prime_with_the_switch_off_is_the_persona_alone(store: Engine) -> None:
    adapter = RecordingPrimingAdapter([ok("Good")])
    gateway = a_gateway(store, adapter)
    persona = gateway.active_persona_content()
    gateway.prime_prefix(routes=("partner",))
    assert adapter.boundaries == ["user_header"]
    assert adapter.systems == [persona]
    assert adapter.captured[-1][0] == persona


def test_the_light_route_keeps_the_persona_boundary_under_the_experiment(store: Engine) -> None:
    """The Tier-1 request relocates nothing, so its prime must not move (27 September 2026:
    the desktop comparison paid a 7.9 s cold prefill on the light route when it did)."""
    from test_light_route import light_candidate

    adapter = RecordingPrimingAdapter([ok("Good"), ok("Good"), ok("Good")])
    gateway = a_gateway(store, adapter)
    persona = gateway.active_persona_content()
    context.ENVELOPE_IN_SYSTEM = True
    try:
        result = gateway.prime_prefix(routes=("light", "partner"))
    finally:
        context.ENVELOPE_IN_SYSTEM = False
    # With a light route admitted the plans are [light, partner]; without one, [partner].
    # Either way only the conversation route's plan moves to the developer-end boundary.
    if len(adapter.boundaries) == 2:
        assert adapter.boundaries[0] == "user_header" and adapter.systems[0] == persona
        assert adapter.boundaries[1] == "developer_end"
    else:
        assert adapter.boundaries == ["developer_end"]
    del result
