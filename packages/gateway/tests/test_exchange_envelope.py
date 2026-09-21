"""Exchange identity and the exchange envelope, against a real PostgreSQL — 13 September 2026.

Every reservation names the user exchange that caused it; with an envelope
configured, the ledger sums that exchange's settled and outstanding claims under
the same advisory lock as the monthly ceiling and refuses the next call that
would exceed it. The envelope is disabled unless a threshold is set, and a
refusal never becomes a cheaper route.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import Engine, text

from val_domain.gateway import (
    Classification,
    CostCertainty,
    GatewayError,
    GatewayErrorKind,
    GatewayRequest,
    Message,
    TaskType,
    TurnReference,
)
from val_domain.project import ProjectAttribution
from val_domain.registry import by_slug
from val_gateway.gateway import RETRYABLE, Gateway
from val_gateway.ledger import DatabaseLedger, ExchangeEnvelopeRefusal, Refusal, Reservation
from val_gateway.persistence import record_call
from val_policy.budget import admits_exchange


def haiku() -> object:
    found = by_slug("haiku-4-5-20251001")
    assert found is not None
    return found


def an_exchange(engine: Engine) -> TurnReference:
    """A real conversation and user message, so the foreign keys hold."""
    with engine.begin() as connection:
        conversation = connection.execute(
            text(
                "insert into conversations (project_id, title, started_at, last_message_at) "
                "values (null, 'envelope', now(), now()) returning id"
            )
        ).scalar_one()
        message = connection.execute(
            text(
                "insert into messages (conversation_id, role, content, sequence) "
                "values (:c, 'user', 'a question', 1) returning id"
            ),
            {"c": conversation},
        ).scalar_one()
    return TurnReference(conversation_id=conversation, message_id=message)


def reserve(
    ledger: DatabaseLedger, amount: float, exchange: TurnReference | None
) -> Reservation | Refusal | ExchangeEnvelopeRefusal:
    return ledger.reserve(
        haiku(),  # type: ignore[arg-type]
        amount,
        TaskType.CLASSIFICATION,
        None,
        exchange=exchange,
    )


def exchange_of(engine: Engine, reservation_id: UUID) -> tuple[UUID | None, UUID | None]:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "select exchange_conversation_id, exchange_message_id "
                "from budget_reservations where id = :id"
            ),
            {"id": reservation_id},
        ).one()
    return row[0], row[1]


# --- the pure rule -------------------------------------------------------------


def test_the_envelope_rule_is_maximum_arithmetic_and_none_disables_it() -> None:
    assert admits_exchange(1_000.0, 1_000.0, None) is True
    assert admits_exchange(0.30, 0.20, 0.50) is True
    assert admits_exchange(0.30, 0.2000001, 0.50) is False


# --- exchange identity on every reservation -------------------------------------


def test_a_reservation_records_its_exchange_and_none_records_none(ledger_engine: Engine) -> None:
    ledger = DatabaseLedger(ledger_engine)
    exchange = an_exchange(ledger_engine)
    named = reserve(ledger, 0.01, exchange)
    unnamed = reserve(ledger, 0.01, None)
    assert isinstance(named, Reservation) and isinstance(unnamed, Reservation)
    assert exchange_of(ledger_engine, named.id) == (exchange.conversation_id, exchange.message_id)
    assert exchange_of(ledger_engine, unnamed.id) == (None, None)


def test_a_reservations_exchange_is_identity_and_cannot_be_rewritten(
    ledger_engine: Engine,
) -> None:
    ledger = DatabaseLedger(ledger_engine)
    claim = reserve(ledger, 0.01, an_exchange(ledger_engine))
    other = an_exchange(ledger_engine)
    assert isinstance(claim, Reservation)
    with pytest.raises(Exception, match="immutable"), ledger_engine.begin() as connection:
        connection.execute(
            text(
                "update budget_reservations set exchange_conversation_id = :c, "
                "exchange_message_id = :m where id = :id"
            ),
            {"c": other.conversation_id, "m": other.message_id, "id": claim.id},
        )


# --- the envelope, disabled -----------------------------------------------------


def test_a_disabled_envelope_admits_exactly_as_before(ledger_engine: Engine) -> None:
    ledger = DatabaseLedger(ledger_engine)
    exchange = an_exchange(ledger_engine)
    for _ in range(5):
        claim = reserve(ledger, 0.50, exchange)
        assert isinstance(claim, Reservation), "no exchange sum is consulted without a threshold"
        ledger.settle(claim.id, 0.40, CostCertainty.KNOWN, None)


# --- the envelope, enabled -------------------------------------------------------


def test_serial_calls_are_admitted_against_settled_cost_not_their_earlier_maximum(
    ledger_engine: Engine,
) -> None:
    ledger = DatabaseLedger(ledger_engine, exchange_envelope_usd=0.50)
    exchange = an_exchange(ledger_engine)
    first = reserve(ledger, 0.40, exchange)
    assert isinstance(first, Reservation)
    ledger.settle(first.id, 0.10, CostCertainty.KNOWN, None)
    # 0.10 settled + 0.40 maximum = 0.50: admitted, because the first call settled.
    second = reserve(ledger, 0.40, exchange)
    assert isinstance(second, Reservation)


def test_an_outstanding_reservation_counts_at_its_maximum(ledger_engine: Engine) -> None:
    ledger = DatabaseLedger(ledger_engine, exchange_envelope_usd=0.50)
    exchange = an_exchange(ledger_engine)
    held = reserve(ledger, 0.30, exchange)
    assert isinstance(held, Reservation)
    refused = reserve(ledger, 0.25, exchange)
    assert isinstance(refused, ExchangeEnvelopeRefusal), (
        "0.30 outstanding at maximum + 0.25 exceeds 0.50, however little either will cost"
    )
    assert refused.exchange_committed_usd == pytest.approx(0.30)
    assert refused.max_cost_usd == pytest.approx(0.25)
    assert refused.envelope_usd == pytest.approx(0.50)


def test_a_refused_reservation_writes_nothing(ledger_engine: Engine) -> None:
    ledger = DatabaseLedger(ledger_engine, exchange_envelope_usd=0.10)
    exchange = an_exchange(ledger_engine)
    assert isinstance(reserve(ledger, 0.20, exchange), ExchangeEnvelopeRefusal)
    with ledger_engine.connect() as connection:
        count = connection.execute(
            text("select count(*) from budget_reservations where exchange_message_id = :m"),
            {"m": exchange.message_id},
        ).scalar_one()
    assert count == 0


def test_retries_and_later_calls_stay_inside_the_same_exchange(ledger_engine: Engine) -> None:
    """An unknown-cost attempt settles at its maximum and the retry is summed with it."""
    ledger = DatabaseLedger(ledger_engine, exchange_envelope_usd=0.50)
    exchange = an_exchange(ledger_engine)
    attempt = reserve(ledger, 0.30, exchange)
    assert isinstance(attempt, Reservation)
    ledger.settle(attempt.id, None, CostCertainty.UNKNOWN, None)
    retry = reserve(ledger, 0.25, exchange)
    assert isinstance(retry, ExchangeEnvelopeRefusal), "0.30 unknown at maximum + 0.25 > 0.50"
    released = reserve(ledger, 0.20, exchange)
    assert isinstance(released, Reservation)
    ledger.release(released.id, "no provider request occurred")
    after_release = reserve(ledger, 0.20, exchange)
    assert isinstance(after_release, Reservation), "a released claim counts for nothing"


def test_exchanges_do_not_contaminate_one_another(ledger_engine: Engine) -> None:
    ledger = DatabaseLedger(ledger_engine, exchange_envelope_usd=0.50)
    spent = an_exchange(ledger_engine)
    fresh = an_exchange(ledger_engine)
    claim = reserve(ledger, 0.45, spent)
    assert isinstance(claim, Reservation)
    assert isinstance(reserve(ledger, 0.45, fresh), Reservation)
    assert isinstance(reserve(ledger, 0.45, None), Reservation), "no exchange, no envelope"


# --- the gateway: a refusal, never a cheaper route --------------------------------


class _NeverCalled:
    name = "anthropic"
    calls = 0

    def complete(self, *args: object, **kwargs: object) -> object:
        self.calls += 1
        raise AssertionError("the provider must not be contacted")


def test_the_gateway_refuses_without_trying_another_route(ledger_engine: Engine) -> None:
    assert GatewayErrorKind.EXCHANGE_ENVELOPE_EXCEEDED not in RETRYABLE
    adapter = _NeverCalled()
    gateway = Gateway(
        adapters={"anthropic": adapter, "openai": adapter, "lmstudio": adapter},  # type: ignore[dict-item]
        recorder=lambda record: record_call(ledger_engine, record),
        ledger=DatabaseLedger(ledger_engine, exchange_envelope_usd=0.000001),
        observe_block=lambda message: None,
    )
    exchange = an_exchange(ledger_engine)
    request = GatewayRequest(
        task_type=TaskType.CLASSIFICATION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="classify this"),),
        output_schema={"type": "object"},
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
        exchange=exchange,
    )
    with pytest.raises(GatewayError) as refused:
        gateway.complete(request)
    assert refused.value.kind is GatewayErrorKind.EXCHANGE_ENVELOPE_EXCEEDED
    assert "authorisation" in refused.value.detail
    assert adapter.calls == 0
    with ledger_engine.connect() as connection:
        assert (
            connection.execute(
                text("select count(*) from budget_reservations where exchange_message_id = :m"),
                {"m": exchange.message_id},
            ).scalar_one()
            == 0
        )


def test_a_conversation_calls_exchange_must_be_its_own_turn() -> None:
    from uuid import uuid4

    from val_domain.gateway import ConversationProvenance

    turn = TurnReference(conversation_id=uuid4(), message_id=uuid4())
    provenance = ConversationProvenance(
        conversation_id=turn.conversation_id, message_id=turn.message_id, persona_id=uuid4()
    )
    base = {
        "task_type": TaskType.CONVERSATION,
        "classification": Classification.PROTECTED,
        "messages": (Message(role="user", content="hello"),),
        "project_id": None,
        "project_attribution": ProjectAttribution.EXPLICIT_NONE,
        "conversation": provenance,
    }
    derived = GatewayRequest(**base)  # type: ignore[arg-type]
    assert derived.exchange_reference == turn
    with pytest.raises(ValueError, match="two exchanges"):
        GatewayRequest(
            **base,  # type: ignore[arg-type]
            exchange=TurnReference(conversation_id=turn.conversation_id, message_id=uuid4()),
        )


def test_the_envelope_setting_is_disabled_unless_a_positive_amount_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from val_gateway.startup import EXCHANGE_ENVELOPE_SETTING, configured_exchange_envelope

    monkeypatch.delenv(EXCHANGE_ENVELOPE_SETTING, raising=False)
    assert configured_exchange_envelope() == (None, None)
    monkeypatch.setenv(EXCHANGE_ENVELOPE_SETTING, "0.75")
    assert configured_exchange_envelope() == (0.75, None)
    for bad in ("0", "-1", "nan", "inf", "a lot"):
        monkeypatch.setenv(EXCHANGE_ENVELOPE_SETTING, bad)
        value, problem = configured_exchange_envelope()
        assert value is None and problem is not None and EXCHANGE_ENVELOPE_SETTING in problem
