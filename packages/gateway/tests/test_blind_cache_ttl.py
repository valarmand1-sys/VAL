"""The gateway never asks for a cache on a blind-position call — ruling, 13 September 2026.

The same verified route, the same long system text, the same configured
lifetime: every other task type is decided exactly as before; `blind_position`
alone requests none, and its reservation is the base-rate bound.
"""

from __future__ import annotations

from gateway_fakes import build, config, request

from val_domain.gateway import CacheTtl, TaskType
from val_gateway.gateway import content_parts
from val_policy.budget import maximum_cost

OPUS = config("opus-5-medium")
LONG_SYSTEM = "persona " * 3_000


def test_only_blind_position_is_refused_a_cache_lifetime() -> None:
    gateway, _, _, _ = build()
    gateway._cache_ttl = CacheTtl.ONE_HOUR
    # `model_copy` skips the provenance validators: the decision reads only the
    # task type and the system text, and this test is about nothing else.
    base = request(system=LONG_SYSTEM)
    decisions = {
        task: gateway._cache_ttl_for(OPUS, base.model_copy(update={"task_type": task}))
        for task in TaskType
    }
    assert decisions.pop(TaskType.BLIND_POSITION) is None
    assert set(decisions.values()) == {CacheTtl.ONE_HOUR}, "every other task type is unchanged"


def test_the_blind_reservation_is_the_base_rate_bound() -> None:
    blind = request(system=LONG_SYSTEM).model_copy(update={"task_type": TaskType.BLIND_POSITION})
    base = maximum_cost(OPUS, content_parts(blind), blind.max_output_tokens, None)
    written = maximum_cost(OPUS, content_parts(blind), blind.max_output_tokens, CacheTtl.ONE_HOUR)
    assert base < written
