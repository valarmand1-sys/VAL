"""The service binds both loopbacks, one port, and nothing routable — WP-0.10.

Found in real use, 31 August 2026: macOS resolves `localhost` to ::1 first,
and an IPv4-only bind made a healthy service invisible to any client that
resolved the name rather than spelling the address. The guarantee has two
halves and these pin both: reachable on this machine over either stack, and
bound to loopback addresses only — never a wildcard, never dual-stack via a
platform default.

No database and no running server needed: the contract under test is what
`loopback_sockets` binds.
"""

from __future__ import annotations

import socket

from val_api.main import loopback_sockets


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_both_loopback_stacks_are_bound_on_one_port() -> None:
    port = _free_port()
    sockets = loopback_sockets(port)
    try:
        bound = {(s.family, s.getsockname()[0], s.getsockname()[1]) for s in sockets}
        assert bound == {
            (socket.AF_INET, "127.0.0.1", port),
            (socket.AF_INET6, "::1", port),
        }, "exactly the two loopback addresses, both on the configured port"
    finally:
        for s in sockets:
            s.close()


def test_nothing_bound_is_routable_off_machine() -> None:
    """No wildcard and no dual-stack: the addresses are loopback, literally."""
    sockets = loopback_sockets(_free_port())
    try:
        for s in sockets:
            address = s.getsockname()[0]
            assert address in ("127.0.0.1", "::1"), f"{address} is not a loopback address"
            if s.family == socket.AF_INET6:
                assert s.getsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY) == 1, (
                    "the ::1 socket must not be widenable into dual-stack by a platform default"
                )
    finally:
        for s in sockets:
            s.close()
