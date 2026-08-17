"""Tests for the model_calls write path and the spend query it feeds.

These run against the real store, because what is being tested is that the row
lands, that an unknown cost lands as unknown rather than as a zero, and that the
database itself refuses the combinations that would make the record lie.
"""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, text

from val_domain.database import test_database_url
from val_domain.gateway import CallStatus, CostCertainty
from val_gateway.gateway import CallRecord
from val_gateway.persistence import (
    month_to_date_spend,
    record_call,
    superseded_zero_calls,
    uncosted_calls_this_month,
)


@pytest.fixture
def engine() -> Iterator[Engine]:
    """The scratch database, never the authoritative store."""
    url = test_database_url()
    assert url.rsplit("/", 1)[-1].endswith("_test"), "refusing to run against a non-test database"
    made = create_engine(url)
    yield made
    made.dispose()


def a_record(
    cost: float | None = 0.25,
    status: CallStatus = CallStatus.OK,
    certainty: CostCertainty = CostCertainty.KNOWN,
) -> CallRecord:
    known = certainty is CostCertainty.KNOWN
    return CallRecord(
        model_config_id=uuid4(),
        slug="opus-5",
        provider="anthropic",
        model_identifier="claude-opus-5",
        tokens_in=1000 if known else None,
        tokens_out=500 if known else None,
        cost_usd=cost if known else None,
        cost_certainty=certainty,
        project_id=None,
        task_type="conversation",
        conversation_id=None,
        message_id=None,
        persona_id=None,
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
                "select provider, model_identifier, cost, task_type, status, cost_certainty "
                "from model_calls order by created_at desc limit 1"
            )
        ).one()
    assert row[0] == "anthropic"
    assert float(row[2]) == pytest.approx(0.125)
    assert row[3] == "conversation"
    assert row[5] == "known"
    assert month_to_date_spend(engine) == pytest.approx(before + 0.125)


def test_record_call_returns_the_new_row_id(engine: Engine) -> None:
    """The reservation that paid for the call points at it by this id."""
    call_id = record_call(engine, a_record())
    with engine.connect() as connection:
        found = connection.execute(
            text("select count(*) from model_calls where id = :id"), {"id": call_id}
        ).scalar_one()
    assert found == 1


def test_a_missing_provider_request_id_is_recorded_not_nulled(engine: Engine) -> None:
    """§2 marks the column NOT NULL; an absent reference is recorded as absent."""
    record_call(engine, a_record())
    with engine.connect() as connection:
        value = connection.execute(
            text("select provider_request_id from model_calls order by created_at desc limit 1")
        ).scalar_one()
    assert value == ""


@pytest.mark.parametrize("status", [CallStatus.ERROR, CallStatus.REFUSED])
def test_calls_with_a_known_cost_count_toward_spend(engine: Engine, status: CallStatus) -> None:
    """A refusal consumed input tokens; excluding it would let a loop overspend."""
    before = month_to_date_spend(engine)
    record_call(engine, a_record(cost=0.05, status=status))
    assert month_to_date_spend(engine) == pytest.approx(before + 0.05)


# --- unknown cost is unknown, and the database enforces it -------------------


def test_an_unknown_cost_lands_as_null_not_as_zero(engine: Engine) -> None:
    """The correction: an error after transmission is not a $0.00 call."""
    before = month_to_date_spend(engine)
    record_call(engine, a_record(status=CallStatus.ERROR, certainty=CostCertainty.UNKNOWN))

    with engine.connect() as connection:
        row = connection.execute(
            text(
                "select tokens_in, tokens_out, cost, cost_certainty, status "
                "from model_calls order by created_at desc limit 1"
            )
        ).one()

    assert row.cost_certainty == "unknown"
    assert row.cost is None, "an unestablished cost was recorded as a figure"
    assert row.tokens_in is None
    assert row.tokens_out is None
    # It contributes nothing to the recorded sum, which is exactly why the
    # ceiling is not enforced against that sum.
    assert month_to_date_spend(engine) == pytest.approx(before)


def test_unknown_cost_calls_are_countable(engine: Engine) -> None:
    """No view may show month-to-date spend as complete when it is not."""
    before = uncosted_calls_this_month(engine)
    record_call(engine, a_record(status=CallStatus.ERROR, certainty=CostCertainty.UNKNOWN))
    assert uncosted_calls_this_month(engine) == before + 1


def test_the_database_refuses_an_unknown_cost_carrying_a_zero(engine: Engine) -> None:
    """The false factual zero is unwritable, not merely discouraged."""
    with pytest.raises(Exception):  # noqa: B017 - the driver's own constraint error
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into model_calls (model_config_id, provider, model_identifier, "
                    "tokens_in, tokens_out, cost, cost_certainty, task_type, latency_ms, "
                    "provider_request_id, status) values "
                    "(gen_random_uuid(), 'anthropic', 'x', 0, 0, 0, 'unknown', "
                    "'conversation', 1, '', 'error')"
                )
            )


def test_the_database_refuses_a_known_cost_with_no_figure(engine: Engine) -> None:
    """The other half: `known` is a claim, and it must carry what it claims."""
    with pytest.raises(Exception):  # noqa: B017 - the driver's own constraint error
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into model_calls (model_config_id, provider, model_identifier, "
                    "tokens_in, tokens_out, cost, cost_certainty, task_type, latency_ms, "
                    "provider_request_id, status) values "
                    "(gen_random_uuid(), 'anthropic', 'x', null, null, null, 'known', "
                    "'conversation', 1, '', 'ok')"
                )
            )


# --- the superseded fabricated zeroes — §2.2 amendment, 17 August 2026 -------
#
# Five rows written on 15 August 2026 carry a fabricated `cost = 0.000000` under
# accounting semantics that have since been superseded. They are preserved
# unmodified. These prove no aggregate can read them as confirmed free calls.


def a_superseded_row(engine: Engine) -> None:
    """Insert a row shaped exactly like the 15 August ones: 0/0/$0, no certainty."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "insert into model_calls (created_at, model_config_id, provider, "
                "model_identifier, tokens_in, tokens_out, cost, cost_certainty, "
                "task_type, latency_ms, provider_request_id, status) values "
                "(timestamptz '2026-08-15 20:43:09+00', gen_random_uuid(), 'anthropic', "
                "'claude-opus-5', 0, 0, 0, null, 'conversation', 900, '', 'error')"
            )
        )


def test_the_original_row_is_preserved_exactly_as_written(engine: Engine) -> None:
    """The correction must not have touched the evidence."""
    a_superseded_row(engine)
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "select tokens_in, tokens_out, cost, cost_certainty, status "
                "from model_calls where cost_certainty is null and status = 'error' "
                "order by created_at desc limit 1"
            )
        ).one()
    assert row.tokens_in == 0
    assert row.tokens_out == 0
    assert float(row.cost) == 0.0
    assert row.cost_certainty is None
    assert row.status == "error"


def test_the_view_reports_the_cost_as_unknown_not_zero(engine: Engine) -> None:
    """The correction, readable from SQL by a human who knows nothing about it."""
    a_superseded_row(engine)
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "select cost, accounted_cost, effective_cost_certainty, accounting_note "
                "from model_calls_accounted where cost_certainty is null and status = 'error' "
                "order by created_at desc limit 1"
            )
        ).one()
    assert float(row.cost) == 0.0, "the original figure is still visible"
    assert row.accounted_cost is None, "a fabricated zero was reported as a real cost"
    assert row.effective_cost_certainty == "unknown"
    assert row.accounting_note is not None
    assert "superseded" in row.accounting_note.lower()
    assert "unknown" in row.accounting_note.lower()


def test_a_superseded_row_adds_nothing_to_known_spend(engine: Engine) -> None:
    """It contributes zero — but as an absence, not as a confirmed free call."""
    before = month_to_date_spend(engine)
    a_superseded_row(engine)
    assert month_to_date_spend(engine) == pytest.approx(before)


def test_a_superseded_row_is_counted_as_uncosted(engine: Engine) -> None:
    """The half that stops the zero being silent.

    Adding nothing to the total is only honest if something says the total is
    incomplete. This is that something.
    """
    before = uncosted_calls_this_month(engine)
    a_superseded_row(engine)
    assert uncosted_calls_this_month(engine) == before + 1


def test_superseded_rows_are_separately_countable(engine: Engine) -> None:
    """A reader can ask whether any of this history is superseded."""
    before = superseded_zero_calls(engine)
    a_superseded_row(engine)
    assert superseded_zero_calls(engine) == before + 1


def test_a_legacy_success_row_is_still_treated_as_known(engine: Engine) -> None:
    """The rule is exact, not a blanket distrust of everything written that day.

    The superseded implementation wrote real usage on success and refusal. Only
    its error path fabricated figures, so only its error rows are superseded.
    """
    with engine.begin() as connection:
        connection.execute(
            text(
                "insert into model_calls (created_at, model_config_id, provider, "
                "model_identifier, tokens_in, tokens_out, cost, cost_certainty, "
                "task_type, latency_ms, provider_request_id, status) values "
                "(timestamptz '2026-08-15 20:43:36+00', gen_random_uuid(), 'openai', "
                "'gpt-5.5', 37, 24, 0.000905, null, 'conversation', 3378, 'req', 'ok')"
            )
        )
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "select accounted_cost, effective_cost_certainty, accounting_note "
                "from model_calls_accounted where cost_certainty is null and status = 'ok' "
                "order by created_at desc limit 1"
            )
        ).one()
    assert row.effective_cost_certainty == "known"
    assert float(row.accounted_cost) == pytest.approx(0.000905)
    assert row.accounting_note is None


def test_a_new_row_may_not_omit_its_cost_certainty(engine: Engine) -> None:
    """What makes NULL certainty mean 'legacy' forever rather than merely today.

    Without this, a future writer could add an unstated-certainty row and the
    superseding rule would quietly widen to cover a row it was never written for.
    """
    with pytest.raises(Exception):  # noqa: B017 - the driver's own constraint error
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into model_calls (model_config_id, provider, model_identifier, "
                    "tokens_in, tokens_out, cost, cost_certainty, task_type, latency_ms, "
                    "provider_request_id, status) values "
                    "(gen_random_uuid(), 'anthropic', 'x', 1, 1, 0.01, null, "
                    "'conversation', 1, '', 'ok')"
                )
            )
