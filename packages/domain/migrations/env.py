"""Alembic environment for Val's authoritative store.

No connection string is committed. The target is resolved by
`val_domain.database.migration_target`, and the resolution **fails closed
on the live database** (ruling, 7 September 2026): a migration command whose
resolved target is not a scratch database is refused unless the invocation
is explicitly the authorized deployment path, `-x deploy=live`.

Why. On 3 September 2026 a round-trip check meant for the scratch database
applied a migration to the live store, because this file read
`VAL_DATABASE_URL` from the surrounding environment and ignored the `-x url`
flag the caller passed. That ended well only because the migration was
additive. A verification command that *can* reach live is a defect whatever
it happens to do, so:

- `-x url=<url>` names the target explicitly and wins;
- a caller that configured `sqlalchemy.url` programmatically (the schema
  tests do) is honoured next;
- `VAL_DATABASE_URL`, or the local default, is the fallback;
- and whichever way it was resolved, a target whose database name does not
  end in `_test` is refused without `-x deploy=live`.

Deploying to the live store is therefore always spelled out:
`uv run alembic -x deploy=live upgrade head`.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from val_domain.database import LiveDatabaseRefusedError, migration_target
from val_domain.schema import Base

config = context.config

if config.config_file_name is not None:
    # Keep loggers that already exist enabled. The default (`True`) silently
    # disables every logger created before this call — in a test process that
    # migrates the scratch database first, that is every application logger,
    # including the one whose blind-payload lines are WP-0.9 evidence.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

try:
    _target = migration_target(
        context.get_x_argument(as_dictionary=True),
        config.get_main_option("sqlalchemy.url", None),
    )
except LiveDatabaseRefusedError as refused:
    raise SystemExit(f"alembic: refused. {refused}") from refused
config.set_main_option("sqlalchemy.url", _target)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to a script rather than a database."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
