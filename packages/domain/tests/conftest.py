"""Fixtures for the schema tests.

Two safeguards, both deliberate:

- The fixtures refuse to run against any database whose name does not end in
  `_test`. They reset the schema, and a reset pointed at the authoritative store
  would destroy the one thing Layer 0 exists to protect.
- Tests that insert rows run inside a transaction that is rolled back. They
  cannot clean up by deleting, because §2.3 forbids hard delete and the database
  enforces it.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text

from val_domain.database import TEST_DATABASE_URL_VARIABLE, test_database_url

REPO_ROOT_MARKER = "alembic.ini"


def _alembic_config(url: str) -> Config:
    """Alembic configuration pointed at the scratch database."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    config = Config(str(root / REPO_ROOT_MARKER))
    config.set_main_option("script_location", str(root / "packages" / "domain" / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _require_scratch_database(url: str) -> None:
    """Refuse anything that is not plainly a scratch database."""
    name = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not name.endswith("_test"):
        raise RuntimeError(
            f"Refusing to run schema tests against {name!r}. These fixtures reset the "
            f"schema, so the database name must end in '_test'. Set "
            f"{TEST_DATABASE_URL_VARIABLE} to a scratch database."
        )


@pytest.fixture(scope="session")
def database_url() -> str:
    """The scratch database's URL, checked."""
    url = test_database_url()
    _require_scratch_database(url)
    return url


@pytest.fixture(scope="session")
def alembic_config(database_url: str) -> Config:
    """Alembic configuration for the scratch database."""
    return _alembic_config(database_url)


@pytest.fixture(scope="session")
def engine(database_url: str, alembic_config: Config) -> Iterator[Engine]:
    """A scratch database migrated to head, from empty."""
    _require_scratch_database(database_url)
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def connection(engine: Engine) -> Iterator[Connection]:
    """A connection whose work is rolled back, since nothing may be deleted."""
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()
