"""The CORS grant: exactly the shell's origins, nothing wider — WP-0.10.

Found in real use, 31 August 2026: the desktop shell is a browser client on
its own origin, the webview preflighted its reads, and the service answered
405 — a healthy service invisible to its only interface. These pin the grant
that closes it, and pin its bounds: an origin that is not the shell's gets no
grant, so the loopback bind stays the only thing that decides who can talk to
the service and CORS never quietly widens into a second audience.

No database needed: the middleware is app-level, so the app is built with
inert stand-ins for the engine and gateway.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from val_api.app import create_app

#: The shell's origins: Tauri serves the interface from tauri://localhost on
#: macOS and http://tauri.localhost on Windows.
SHELL_ORIGINS = ("tauri://localhost", "http://tauri.localhost")


def client() -> TestClient:
    return TestClient(create_app(MagicMock(), MagicMock(), []))


@pytest.mark.parametrize("origin", SHELL_ORIGINS)
def test_the_shells_preflight_is_granted(origin: str) -> None:
    """The exact request shape that failed on 31 August 2026, now answered."""
    response = client().options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize("origin", SHELL_ORIGINS)
def test_the_shells_reads_and_writes_carry_the_grant(origin: str) -> None:
    read = client().get("/health", headers={"Origin": origin})
    assert read.status_code == 200
    assert read.headers["access-control-allow-origin"] == origin

    write_preflight = client().options(
        "/execution-events",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert write_preflight.status_code == 200
    assert "POST" in write_preflight.headers["access-control-allow-methods"]


def test_no_other_origin_is_granted(origin_elsewhere: str = "http://evil.example") -> None:
    """The grant names the shell and stops there."""
    preflight = client().options(
        "/health",
        headers={
            "Origin": origin_elsewhere,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert "access-control-allow-origin" not in preflight.headers

    read = client().get("/health", headers={"Origin": origin_elsewhere})
    assert "access-control-allow-origin" not in read.headers
