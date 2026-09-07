"""How to reach the authoritative store.

PostgreSQL is the sole authoritative store (`00-charter.md` invariant 12). The
URL is read from the environment so that no credential is ever committed, and it
defaults to the local development instance.

Val's instance runs on port **5433**. Port 5432 belongs to a separate PostgreSQL
installation that has nothing to do with this project; nothing here may address
it. That is why the default port is explicit rather than PostgreSQL's own.
"""

import os
from collections.abc import Mapping

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


# --- migration targets fail closed on the live store — ruling, 7 September 2026


#: `alembic -x url=<url>`: the target named on the command line, which wins.
MIGRATION_URL_ARGUMENT = "url"
#: `alembic -x deploy=live`: the one authorized way to migrate a non-scratch
#: database. Spelled out on every deployment, never implied by the environment.
MIGRATION_DEPLOY_ARGUMENT = "deploy"
MIGRATION_DEPLOY_LIVE = "live"


class LiveDatabaseRefusedError(RuntimeError):
    """A migration command resolved to a non-scratch database without the deploy flag."""


def is_scratch_database_url(url: str) -> bool:
    """Whether a URL names a scratch database — one whose name ends in `_test`."""
    name = url.rsplit("/", 1)[-1].split("?", 1)[0]
    return name.endswith("_test")


def _redacted(url: str) -> str:
    from sqlalchemy.engine import make_url

    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return url


def migration_target(
    x_arguments: Mapping[str, str],
    configured: str | None,
    environment: Mapping[str, str] | None = None,
) -> str:
    """The database a migration command may run against, or a refusal.

    Resolution order: `-x url=` on the command line; then a URL the caller
    configured programmatically (the schema tests set `sqlalchemy.url`
    themselves); then `VAL_DATABASE_URL`; then the local default. Then the
    guard, whichever way the target was reached: **a target that is not a
    scratch database is refused unless `-x deploy=live` was passed.**

    Ruling, 7 September 2026, after a scratch round-trip check applied
    migration `0013` to the live store because the environment held the live
    URL and the `-x url` flag was ignored. A verification command must not be
    able to reach the live database; deployment names it explicitly.
    """
    env = os.environ if environment is None else environment
    if MIGRATION_URL_ARGUMENT in x_arguments:
        target, source = x_arguments[MIGRATION_URL_ARGUMENT], "-x url"
    elif configured:
        target, source = configured, "the configured sqlalchemy.url"
    elif DATABASE_URL_VARIABLE in env:
        target, source = env[DATABASE_URL_VARIABLE], DATABASE_URL_VARIABLE
    else:
        target, source = DEFAULT_DATABASE_URL, "the local default"
    if is_scratch_database_url(target):
        return target
    if x_arguments.get(MIGRATION_DEPLOY_ARGUMENT) == MIGRATION_DEPLOY_LIVE:
        return target
    raise LiveDatabaseRefusedError(
        f"the resolved target ({source}) is not a scratch database: {_redacted(target)}. "
        "A migration reaches a non-scratch database only through the explicit "
        f"deployment path, `alembic -x {MIGRATION_DEPLOY_ARGUMENT}={MIGRATION_DEPLOY_LIVE} "
        "<command>`. To run against scratch, pass `-x url=<...>_test` or point "
        f"{DATABASE_URL_VARIABLE} at a database whose name ends in `_test`."
    )
