"""How to reach the authoritative store.

PostgreSQL is the sole authoritative store (`00-charter.md` invariant 12). The
URL is read from the environment so that no credential is ever committed, and it
defaults to the local development instance.

Val's instance runs on port **5433**. Port 5432 belongs to a separate PostgreSQL
installation that has nothing to do with this project; nothing here may address
it. That is why the default port is explicit rather than PostgreSQL's own.
"""

import os

#: Environment variable naming the store. Overrides the default below.
DATABASE_URL_VARIABLE = "VAL_DATABASE_URL"

#: Environment variable naming the scratch database the schema tests use.
TEST_DATABASE_URL_VARIABLE = "VAL_TEST_DATABASE_URL"

DEFAULT_DATABASE_URL = "postgresql+psycopg://localhost:5433/val"
DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://localhost:5433/val_test"


def database_url() -> str:
    """The authoritative store's URL."""
    return os.environ.get(DATABASE_URL_VARIABLE, DEFAULT_DATABASE_URL)


def test_database_url() -> str:
    """The scratch database's URL. Never the authoritative store."""
    return os.environ.get(TEST_DATABASE_URL_VARIABLE, DEFAULT_TEST_DATABASE_URL)
