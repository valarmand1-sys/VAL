"""The service's front door: start the house, or refuse and say why.

`val-api` (the console script) is what launchd runs. Startup enforcement is
`val_gateway.startup.start`: eligibility violations, missing keys, and an
unverified registry stop the process here with the reasons printed — a check
that only fires when a call is made is not the guarantee `04-layer-0.md` §1.1
claims. Warnings that do not stop startup are carried into `/health`, so the
interface can show them without anyone tailing a log.
"""

from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI
from sqlalchemy import create_engine

from val_api.app import create_app
from val_api.settings import Settings
from val_gateway.startup import start

_LOGGER = logging.getLogger("val.api")


def build() -> tuple[FastAPI, Settings]:
    """The application, wired to the real house. Raises StartupRefusedError."""
    # `database_url` arrives from VAL_DATABASE_URL; pydantic-settings fills it
    # at runtime, which mypy cannot see from the constructor signature.
    settings = Settings()  # type: ignore[call-arg]
    engine = create_engine(settings.database_url)
    started = start(engine)
    for warning in started.warnings:
        _LOGGER.warning("%s", warning)
    return create_app(engine, started.gateway, started.warnings), settings


def serve() -> None:
    """Run the service. The `val-api` entry point."""
    logging.basicConfig(level=logging.INFO)
    app, settings = build()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    serve()
