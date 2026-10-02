"""Database fixture for the service tests — the gateway suite's discipline.

A scratch database at head, refused unless its name ends in `_test`, skipped
when none is configured (CI's database job supplies one; a developer running
the unit suite without PostgreSQL sees a visible skip, not a red bar).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text

TEST_URL_VARIABLE = "VAL_TEST_DATABASE_URL"
REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def store() -> Iterator[Engine]:
    """A freshly migrated scratch database with a seeded persona and two projects."""
    url = os.environ.get(TEST_URL_VARIABLE, "")
    if not url:
        pytest.skip(f"{TEST_URL_VARIABLE} is not set; the service tests need a real store")
    if not url.rsplit("/", 1)[-1].split("?", 1)[0].endswith("_test"):
        raise RuntimeError(
            f"Refusing to run service tests against {url!r}: these write rows, and "
            "the database name must end in '_test'."
        )

    from alembic import command
    from alembic.config import Config

    scratch = create_engine(url)
    with scratch.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    alembic_config = Config(str(REPO_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(REPO_ROOT / "packages/domain/migrations"))
    alembic_config.set_main_option("sqlalchemy.url", url)
    command.upgrade(alembic_config, "head")
    # Dropping the schema gave every enum a new OID; a pooled connection still
    # holding the old ones fails on the next enum parameter. A fresh engine
    # avoids the stale type cache entirely (the gateway conftest's lesson).
    scratch.dispose()

    engine = create_engine(url)
    from val_gateway.persona import seed

    seed(engine, REPO_ROOT)
    with engine.begin() as connection:
        for name, slug in (("Project Alpha", "project-alpha"), ("Project Beta", "project-beta")):
            connection.execute(
                text(
                    "insert into projects (name, slug, description, status) "
                    "values (:name, :slug, '', 'active')"
                ),
                {"name": name, "slug": slug},
            )
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def hosted_routes_open_for_scripted_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """The governing rule of 2 October 2026 forbids hosted models in production. The
    tests written before it drive scripted adapters registered under hosted provider
    names — nothing leaves the machine in a test — and they hold governance that is
    still true; they run with the rule stood down. The rule's own tests set it back
    (`test_local_ai_rule.py`); production code never reads this fixture."""
    import val_policy.egress as egress_policy

    monkeypatch.setattr(egress_policy, "HOSTED_MODELS_FORBIDDEN", False)
