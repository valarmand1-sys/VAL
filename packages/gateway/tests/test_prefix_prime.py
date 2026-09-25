"""The prefix prime is a governed, recorded call and nothing more — 25 September 2026.

Owner order, priming-cache pass §3, §8, §9, §13. A prime is a local infrastructure
model call: the persona and a short filler, sent through the same governed path as
every call, recorded as `prefix_prime` and attached to no conversation. Its one
generated token is discarded. It is never sent while a request of his is waiting,
and never sent when the adapter cannot place it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Engine, text
from test_cognition_warming import PRODUCTION, LocalAdapter, a_gateway
from test_deliberation_machinery import (  # noqa: F401 - pytest fixtures by injection
    clean_personas,
    ok,
    store,
)

from val_domain.gateway import ModelConfig
from val_domain.provider import PrefixPrimePlan


@dataclass
class PrimingAdapter(LocalAdapter):
    """A local adapter that can plan a prime — or refuse to."""

    refuse: str | None = None
    planned: list[str] = field(default_factory=list)

    def plan_prefix_prime(self, config: ModelConfig, system: str) -> PrefixPrimePlan:
        self.planned.append(config.slug)
        if self.refuse is not None:
            return PrefixPrimePlan(engine="test-engine", refused=self.refuse)
        return PrefixPrimePlan(
            filler="ok ok ok ok ok ok ok ok",
            boundary_tokens=100,
            prime_tokens=111,
            boundary_sha256="b" * 64,
            engine="test-engine",
        )


def rows(engine: Engine, query: str) -> list[dict]:
    with engine.connect() as connection:
        return [dict(row._mapping) for row in connection.execute(text(query))]


def test_a_prime_is_recorded_as_what_it_is(store: Engine) -> None:  # noqa: F811
    adapter = PrimingAdapter([ok("Good")])
    result = a_gateway(store, adapter).prime_prefix()

    assert result["primed"] is True and result["outcome"] == "established"
    calls = rows(
        store,
        "select task_type::text as task_type, conversation_id, message_id, persona_id, "
        "tokens_in, tokens_out, cost, status::text as status, model_identifier "
        "from model_calls",
    )
    assert len(calls) == 1
    call = calls[0]
    assert call["task_type"] == "prefix_prime"
    # Attached to no conversation and no message: it is not a turn.
    assert call["conversation_id"] is None and call["message_id"] is None
    # The persona it carried is attributed, as on any persona-bearing call.
    assert call["persona_id"] is not None
    assert float(call["cost"]) == 0.0
    # Made ready before planning (the plan reads the loaded instance), and asked again
    # by the governed call path itself, as every call is — the same route both times.
    assert adapter.warmed == [PRODUCTION, PRODUCTION]
    assert adapter.planned == [PRODUCTION]


def test_nothing_a_prime_produces_becomes_conversation(store: Engine) -> None:  # noqa: F811
    before = rows(store, "select count(*) as n from messages")[0]["n"]
    a_gateway(store, PrimingAdapter([ok("A word that must go nowhere")])).prime_prefix()
    assert rows(store, "select count(*) as n from messages")[0]["n"] == before
    assert rows(store, "select count(*) as n from conversations")[0]["n"] == 0


def test_no_prime_is_sent_while_a_request_of_his_is_waiting(store: Engine) -> None:  # noqa: F811
    adapter = PrimingAdapter([ok("unused")])
    result = a_gateway(store, adapter).prime_prefix(still_wanted=lambda: False)
    assert result["primed"] is False and result["outcome"] == "skipped"
    assert "owner request is waiting" in str(result["reason"])
    assert adapter.sent == [], "nothing reached the model"
    assert adapter.planned == [], "not even planning, which asks the runtime to render"
    assert rows(store, "select count(*) as n from model_calls")[0]["n"] == 0


def test_a_prime_the_adapter_cannot_place_is_not_sent(store: Engine) -> None:  # noqa: F811
    adapter = PrimingAdapter([ok("unused")], refuse="the selected engine is not the qualified one")
    result = a_gateway(store, adapter).prime_prefix()
    assert result["primed"] is False and "qualified" in str(result["reason"])
    assert adapter.sent == []
    assert rows(store, "select count(*) as n from model_calls")[0]["n"] == 0
