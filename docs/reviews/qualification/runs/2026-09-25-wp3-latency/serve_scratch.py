"""The real service, on a scratch store and a second port — for measurement only.

WP3 Step B latency pass, 25 September 2026. The owner-facing intervals are measured
through the **same application** launchd runs (`val_api.main.build`): the same
composition root, recognizer, gateway, local GPT-OSS at MEDIUM, speech delivery and
`val-established-v1`. Only the store (the scratch database, rebuilt empty) and the
port (8766) differ, so nothing here writes into Lord Armand's conversation history.

The service's environment is read from its own launchd definition, exactly as the
previous latency harness did; nothing from it is printed. A spoken turn is sealed,
so it contacts no cloud route: every call it makes is local and costs $0.
"""

from __future__ import annotations

import logging
import os
import plistlib
import sys
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    for name, value in plistlib.load(handle)["EnvironmentVariables"].items():
        if name != "VAL_DATABASE_URL":
            os.environ[name] = value

ROOT = Path(__file__).resolve().parents[5]
URL = "postgresql+psycopg://localhost:5433/val_test"
PORT = 8766
os.environ["VAL_DATABASE_URL"] = URL
os.environ["VAL_PORT"] = str(PORT)

import uvicorn  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from val_api.main import build, loopback_sockets  # noqa: E402
from val_gateway.persona import seed  # noqa: E402


def fresh_store() -> None:
    engine = create_engine(URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "packages/domain/migrations"))
    config.set_main_option("sqlalchemy.url", URL)
    command.upgrade(config, "head")
    engine = create_engine(URL)
    seed(engine, ROOT)
    engine.dispose()


if __name__ == "__main__":
    fresh_store()
    # Alembic's own logging configuration disables every existing logger and lowers
    # the root to WARNING; undone here, so the service logs as it does under launchd
    # (plus a wall-clock time on each line, which this measurement needs).
    for logger in logging.Logger.manager.loggerDict.values():
        if isinstance(logger, logging.Logger):
            logger.disabled = False
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(created).3f %(levelname)s:%(name)s:%(message)s",
    )
    app, _ = build()
    uvicorn.Server(uvicorn.Config(app, port=PORT, log_level="info")).run(
        sockets=loopback_sockets(PORT)
    )
