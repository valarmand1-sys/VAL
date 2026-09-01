"""Tests for the model_calls write path and the spend query it feeds.

These run against the real store, because what is being tested is that the row
lands, that an unknown cost lands as unknown rather than as a zero, and that the
database itself refuses the combinations that would make the record lie.
"""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from conftest import fabricate_a_legacy_row
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import DBAPIError

# Aliased on import: pytest collects any module-level name starting with `test_`,
# so importing this helper under its own name made pytest treat the scratch-URL
# accessor as a test case and warn about its return value.
from val_domain.database import test_database_url as scratch_database_url
from val_domain.gateway import CallStatus, CostCertainty
from val_domain.project import ProjectAttribution
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
    url = scratch_database_url()
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
        terminal_state="complete" if known else "failed",
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
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


#: Both refusal tests below name the constraint they expect. *Corrected 18
#: August 2026.* They previously asserted only `pytest.raises(Exception)`, and
#: when `0006` added `project_attribution` the value was appended without the
#: column name — so the statement failed on argument count and the tests passed
#: without ever reaching the constraint they exist to prove. A test that cannot
#: fail for the right reason is not evidence, and this one had stopped being.
def _violated_constraint(error: DBAPIError) -> str | None:
    """The constraint the database actually refused on.

    Read from psycopg's diagnostics rather than matched in the message text,
    because SQLAlchemy truncates long statements into the string form, and the
    constraint name is what gets cut. Reading it exactly also caught that the
    name asserted here was simply wrong — the constraint is
    `ck_model_calls_known_cost_is_recorded` — which a substring match against a
    truncated message would have gone on hiding.
    """
    diagnostic = getattr(error.orig, "diag", None)
    return None if diagnostic is None else diagnostic.constraint_name


_CALL_COLUMNS = (
    "insert into model_calls (model_config_id, provider, model_identifier, tokens_in, "
    "tokens_out, cost, cost_certainty, terminal_state, task_type, project_attribution, "
    "latency_ms, provider_request_id, status) values "
)


def test_the_database_refuses_an_unknown_cost_carrying_a_zero(engine: Engine) -> None:
    """The false factual zero is unwritable, not merely discouraged."""
    with pytest.raises(DBAPIError) as caught:
        with engine.begin() as connection:
            connection.execute(
                text(
                    _CALL_COLUMNS + "(gen_random_uuid(), 'anthropic', 'x', 0, 0, 0, "
                    "'unknown', 'complete', 'conversation', 'explicit_none', 1, '', 'error')"
                )
            )
    assert _violated_constraint(caught.value) == "ck_model_calls_unknown_cost_is_not_a_zero"


def test_the_database_refuses_a_known_cost_with_no_figure(engine: Engine) -> None:
    """The other half: `known` is a claim, and it must carry what it claims."""
    with pytest.raises(DBAPIError) as caught:
        with engine.begin() as connection:
            connection.execute(
                text(
                    _CALL_COLUMNS + "(gen_random_uuid(), 'anthropic', 'x', null, null, "
                    "null, 'known', 'complete', 'conversation', 'explicit_none', 1, '', 'ok')"
                )
            )
    assert _violated_constraint(caught.value) == "ck_model_calls_known_cost_is_recorded"


# --- the superseded fabricated zeroes — §2.2 amendment, 17 August 2026 -------
#
# Five rows written on 15 August 2026 carry a fabricated `cost = 0.000000` under
# accounting semantics that have since been superseded. They are preserved
# unmodified. These prove no aggregate can read them as confirmed free calls.


def a_superseded_row(engine: Engine) -> None:
    """Insert a row shaped exactly like the 15 August ones: 0/0/$0, no certainty.

    Those rows also predate project attribution, so they carry `legacy_unknown`
    — a value migration `0007` has since closed to new rows. The fabrication is
    therefore explicit; see `conftest.fabricate_a_legacy_row`.
    """
    fabricate_a_legacy_row(
        engine, tokens_in=0, tokens_out=0, cost=0, cost_certainty="null", status="'error'"
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


def test_a_superseded_row_reads_as_uncosted_in_its_own_month_only(engine: Engine) -> None:
    """The half that stops the zero being silent — restated durably.

    Until 31 August 2026 this test asserted the current-month counter moved,
    and it failed on the first CI run after the UTC month rolled over: the
    legacy set is bounded by check constraint to rows dated before 17 August
    2026, so from September onward a superseded row is honestly *outside*
    every "this month" window, permanently — the calendar was being tested by
    accident. The durable rules are the two asserted here: the month-scoped
    counter does not move for a row from a closed prior month, and the view
    still reads that row's cost as unknown, never as a confirmed zero. The
    current-month incompleteness signal is `test_unknown_cost_calls_are_countable`.
    """
    before = uncosted_calls_this_month(engine)
    a_superseded_row(engine)
    assert uncosted_calls_this_month(engine) == before, (
        "a superseded row from a closed prior month must not count against the "
        "current month's figure"
    )
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "select effective_cost_certainty, accounted_cost from model_calls_accounted "
                "where cost_certainty is null and status = 'error' "
                "order by created_at desc limit 1"
            )
        ).one()
    assert row.effective_cost_certainty == "unknown"
    assert row.accounted_cost is None, "the fabricated zero must never read as a known cost"


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
    fabricate_a_legacy_row(
        engine,
        created_at="timestamptz '2026-08-15 20:43:36+00'",
        provider="'openai'",
        model_identifier="'gpt-5.5'",
        tokens_in=37,
        tokens_out=24,
        cost=0.000905,
        cost_certainty="null",
        latency_ms=3378,
        provider_request_id="'req'",
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
    # *Closure pass, 18 August 2026.* Found by the test-quality audit: this
    # statement listed eleven columns and supplied twelve values, so it failed
    # on argument count and never reached the constraint it names — the same
    # defect class the WP-0.6 corrective round fixed in this file's neighbours.
    # It now names the constraint it expects, read from psycopg's diagnostics.
    with pytest.raises(DBAPIError) as caught:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into model_calls (model_config_id, provider, model_identifier, "
                    "tokens_in, tokens_out, cost, cost_certainty, project_attribution, "
                    "terminal_state, task_type, latency_ms, provider_request_id, status) "
                    "values (gen_random_uuid(), 'anthropic', 'x', 1, 1, 0.01, null, "
                    "'explicit_none', 'complete', 'conversation', 1, '', 'ok')"
                )
            )
    assert (
        _violated_constraint(caught.value)
        == "ck_model_calls_certainty_required_after_the_amendment"
    )
