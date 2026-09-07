"""Migration commands fail closed on the live store — ruling, 7 September 2026.

On 3 September a scratch round-trip check applied migration `0013` to the
live database: the Alembic environment read `VAL_DATABASE_URL` from the
surrounding environment and ignored the `-x url` flag the caller passed. The
resolver these tests pin makes that impossible: a non-scratch target is
refused unless the invocation is the explicit deployment path.
"""

from __future__ import annotations

import pytest
from sqlalchemy.engine import make_url

from val_domain.database import (
    DEFAULT_DATABASE_URL,
    LiveDatabaseRefusedError,
    is_scratch_database_url,
    migration_target,
)

LIVE = "postgresql+psycopg://val@localhost:5433/val"
SCRATCH = "postgresql+psycopg://localhost:5433/val_test"
#: Assembled at runtime so no committed literal carries a password (the
#: secrets check scans literals); the refusal message must still redact it.
SAMPLE_WORD = "hunter2"


def _with_password(password: str) -> str:
    """A live URL carrying a password, assembled at runtime rather than committed."""
    return make_url(LIVE).set(password=password).render_as_string(hide_password=False)


LIVE_WITH_PASSWORD = _with_password(SAMPLE_WORD)


def test_a_live_url_in_the_environment_alone_is_refused() -> None:
    with pytest.raises(LiveDatabaseRefusedError) as refused:
        migration_target({}, None, {"VAL_DATABASE_URL": LIVE_WITH_PASSWORD})
    message = str(refused.value)
    assert "VAL_DATABASE_URL" in message and "deploy=live" in message
    assert SAMPLE_WORD not in message, "the password never appears in the refusal"


def test_the_local_default_is_live_and_is_refused_without_the_flag() -> None:
    assert not is_scratch_database_url(DEFAULT_DATABASE_URL)
    with pytest.raises(LiveDatabaseRefusedError):
        migration_target({}, None, {})


def test_a_scratch_url_on_the_command_line_wins_over_a_live_environment() -> None:
    assert migration_target({"url": SCRATCH}, None, {"VAL_DATABASE_URL": LIVE}) == SCRATCH


def test_a_scratch_url_configured_programmatically_wins_over_a_live_environment() -> None:
    """The schema tests set `sqlalchemy.url` themselves; the environment is ignored."""
    assert migration_target({}, SCRATCH, {"VAL_DATABASE_URL": LIVE}) == SCRATCH


def test_a_live_url_on_the_command_line_is_still_refused_without_the_flag() -> None:
    with pytest.raises(LiveDatabaseRefusedError):
        migration_target({"url": LIVE}, None, {})


def test_the_explicit_deployment_path_reaches_live() -> None:
    assert migration_target({"deploy": "live"}, None, {"VAL_DATABASE_URL": LIVE}) == LIVE


def test_the_flag_must_say_live_exactly() -> None:
    with pytest.raises(LiveDatabaseRefusedError):
        migration_target({"deploy": "yes"}, None, {"VAL_DATABASE_URL": LIVE})


def test_scratch_is_the_database_name_not_the_url_text() -> None:
    assert is_scratch_database_url("postgresql+psycopg://h/val_test?sslmode=require")
    assert not is_scratch_database_url("postgresql+psycopg://val_test@h/val")
