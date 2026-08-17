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
