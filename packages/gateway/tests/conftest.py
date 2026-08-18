"""Database fixture for the gateway tests.

The fakes and builders live in `gateway_fakes.py`; only what pytest must
discover automatically is here.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text

TEST_URL_VARIABLE = "VAL_TEST_DATABASE_URL"


@pytest.fixture(scope="session")
def ledger_engine() -> Iterator[Engine]:
    """A scratch database at head, for tests that need the real ledger.

    Skips rather than fails when no scratch database is configured: these tests
    are run by CI's `database` job, and a developer running the unit suite
    without PostgreSQL should not see a red bar for a dependency they were never
    asked to have. The skip is visible in the run, so it cannot be mistaken for
    a pass.
    """
    url = os.environ.get(TEST_URL_VARIABLE, "")
    if not url:
        pytest.skip(f"{TEST_URL_VARIABLE} is not set; the ledger's concurrency tests need one")
    if not url.rsplit("/", 1)[-1].split("?", 1)[0].endswith("_test"):
        raise RuntimeError(
            f"Refusing to run ledger tests against {url!r}: these write rows, and the "
            "database name must end in '_test'."
        )

    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parents[3]
    alembic_config = Config(str(root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(root / "packages/domain/migrations"))
    alembic_config.set_main_option("sqlalchemy.url", url)

    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config, "head")
    yield engine
    engine.dispose()


def fabricate_a_legacy_row(engine: Engine, **columns: object) -> None:
    """Insert a row shaped like the nine that predate WP-0.6.

    Migration `0007` closed `legacy_unknown` to new rows — it describes
    `model_calls` written before project attribution existed, that set was
    backfilled once, and nothing may join it afterwards. A test that needs such a
    row is therefore asking the database for something it is built to refuse, and
    has to say so rather than find a way in.

    Several tests below genuinely need one, because what they exercise *is* the
    handling of pre-WP-0.6 rows: that a legacy NULL is never read as a decision,
    and that the accounting view treats a NULL `cost_certainty` correctly. This
    function is where the admission lives, and it is the only place in the test
    suite that suspends the guard.

    The suspension is scoped to one transaction and restored in the same one, so
    a failure part-way cannot leave the scratch database unguarded. Nothing in
    `val_gateway` may do this: a writer that disables the guard has simply
    decided not to decide scope, which is exactly what `0007` exists to stop.
    """
    values = {
        "created_at": "timestamptz '2026-08-15 20:43:09+00'",
        "model_config_id": "gen_random_uuid()",
        "provider": "'anthropic'",
        "model_identifier": "'claude-opus-5'",
        "tokens_in": "10",
        "tokens_out": "5",
        "cost": "0.001",
        "cost_certainty": "'known'",
        "project_id": "null",
        "project_attribution": "'legacy_unknown'",
        "task_type": "'conversation'",
        "latency_ms": "900",
        "provider_request_id": "''",
        "status": "'ok'",
    } | {name: str(value) for name, value in columns.items()}
    named = ", ".join(values)
    rendered = ", ".join(values.values())

    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE model_calls DISABLE TRIGGER model_calls_legacy_attribution_is_closed")
        )
        try:
            connection.execute(text(f"insert into model_calls ({named}) values ({rendered})"))  # noqa: S608
        finally:
            connection.execute(
                text(
                    "ALTER TABLE model_calls ENABLE TRIGGER "
                    "model_calls_legacy_attribution_is_closed"
                )
            )
