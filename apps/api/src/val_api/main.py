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
import socket

import uvicorn
from fastapi import FastAPI
from sqlalchemy import create_engine

from val_api.app import create_app
from val_api.settings import Settings
from val_gateway.startup import start

_LOGGER = logging.getLogger("val.api")

#: Both loopback addresses, by family. The service must be reachable from this
#: machine and from nowhere else, and "this machine" has two loopbacks: macOS
#: resolves `localhost` to ::1 first, so an IPv4-only bind made the service
#: invisible to any client that resolved the name instead of spelling the
#: address (found in real use, 31 August 2026 — curl to 127.0.0.1 answered
#: while ::1 was empty). Binding the pair keeps the loopback-only guarantee
#: exactly: neither address is routable off-machine, and no wildcard bind is
#: involved anywhere.
_LOOPBACKS = ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1"))


def loopback_sockets(port: int) -> list[socket.socket]:
    """One bound socket per loopback stack, and nothing else.

    Built by hand rather than asking uvicorn to bind, because uvicorn takes a
    single host — and the alternatives are worse: `localhost` binds whatever
    the resolver says first, and a wildcard would be reachable off-machine.
    Explicit addresses cannot drift with resolver configuration. `IPV6_V6ONLY`
    is set so the ::1 socket can never be widened into a dual-stack one by a
    platform default.
    """
    sockets: list[socket.socket] = []
    for family, address in _LOOPBACKS:
        bound = socket.socket(family, socket.SOCK_STREAM)
        bound.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if family == socket.AF_INET6:
            bound.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        bound.bind((address, port))
        sockets.append(bound)
    return sockets


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
    """Run the service on both loopbacks. The `val-api` entry point."""
    logging.basicConfig(level=logging.INFO)
    app, settings = build()
    server = uvicorn.Server(uvicorn.Config(app, port=settings.port))
    server.run(sockets=loopback_sockets(settings.port))


if __name__ == "__main__":
    serve()
