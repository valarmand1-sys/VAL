"""Tests for the model_calls write path and the spend query it feeds.

These run against the real store, because what is being tested is that the row
lands and that the ceiling reads the record rather than a counter that could
drift from it.
"""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, text

from val_domain.database import test_database_url
from val_domain.gateway import CallStatus
from val_gateway.gateway import CallRecord
from val_gateway.persistence import month_to_date_spend, record_call


@pytest.fixture
def engine() -> Iterator[Engine]:
    """The scratch database, never the authoritative store."""
    url = test_database_url()
    assert url.rsplit("/", 1)[-1].endswith("_test"), "refusing to run against a non-test database"
    made = create_engine(url)
    yield made
    made.dispose()


def a_record(cost: float = 0.25, status: CallStatus = CallStatus.OK) -> CallRecord:
    return CallRecord(
        model_config_id=uuid4(),
        slug="opus-5",
        provider="anthropic",
        model_identifier="claude-opus-5",
        tokens_in=1000,
        tokens_out=500,
        cost_usd=cost,
        project_id=None,
        task_type="conversation",
        conversation_id=None,
        message_id=None,
        latency_ms=850,
        provider_request_id=None,
        status=status,
    )


def test_a_record_lands_with_its_cost_and_task_type(engine: Engine) -> None:
    """The row is the record; everything downstream reads it."""
    before = month_to_date_spend(engine)
    record_call(engine, a_record(cost=0.125))
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "select provider, model_identifier, cost, task_type, status "
                "from model_calls order by created_at desc limit 1"
            )
        ).one()
    assert row[0] == "anthropic"
    assert float(row[2]) == pytest.approx(0.125)
    assert row[3] == "conversation"
    assert month_to_date_spend(engine) == pytest.approx(before + 0.125)


def test_a_missing_provider_request_id_is_recorded_not_nulled(engine: Engine) -> None:
    """§2 marks the column NOT NULL; an absent reference is recorded as absent."""
    record_call(engine, a_record())
    with engine.connect() as connection:
        value = connection.execute(
            text("select provider_request_id from model_calls order by created_at desc limit 1")
        ).scalar_one()
    assert value == ""


@pytest.mark.parametrize("status", [CallStatus.ERROR, CallStatus.REFUSED])
def test_failed_and_refused_calls_count_toward_spend(engine: Engine, status: CallStatus) -> None:
    """A refusal consumed input tokens; excluding it would let a loop overspend."""
    before = month_to_date_spend(engine)
    record_call(engine, a_record(cost=0.05, status=status))
    assert month_to_date_spend(engine) == pytest.approx(before + 0.05)
