"""The scratch service against the EXPERIMENT model instance — remaining latency work, 27 Sept 2026.

The same application launchd runs (`val_api.main.build`), on the scratch store
(`val_test`, rebuilt empty) and port 8766, as the earlier benches. What differs: **every**
GPT-OSS configuration — the MEDIUM partner, the LOW light route the candidate promotes,
and the evaluation entries — addresses the experiment instance, the byte-identical
clone loaded as `val-exp-gpt-oss-20b` (the only model path on the cache-renewal
allowlist). The earlier launcher (`2026-09-25-priming/serve_scratch.py`) replaced the
partner's identifier alone, so its LOW turns addressed production's instance; that is
corrected here, and this process can address no production model at all. Only this
process's registry changes; nothing on disk does. Production's environment is read from
its launchd definition and nothing from it is printed.
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

import val_domain.registry as registry  # noqa: E402
from val_api.main import build, loopback_sockets  # noqa: E402
from val_gateway.persona import seed  # noqa: E402

PRODUCTION_IDENTIFIER = "openai/gpt-oss-20b"
EXPERIMENT = os.environ.get("VAL_EXPERIMENT_MODEL_IDENTIFIER", "val-exp-gpt-oss-20b")
assert EXPERIMENT != PRODUCTION_IDENTIFIER, "the experiment never addresses production's model"
registry.REGISTRY = tuple(
    config.model_copy(update={"model_identifier": EXPERIMENT})
    if config.model_identifier == PRODUCTION_IDENTIFIER
    else config
    for config in registry.REGISTRY
)
assert not any(c.model_identifier == PRODUCTION_IDENTIFIER for c in registry.REGISTRY)


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
    # 28 September: every thread's stack on SIGUSR1, to see a stalled turn (C1a).
    import faulthandler
    import signal

    faulthandler.register(signal.SIGUSR1, all_threads=True)
    fresh_store()
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
