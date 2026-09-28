"""A superseded stream ends at once, whatever the runtime does with its socket — §3, 27 Sept 2026.

The measured behaviour this guards against: after `Stream.close()` from another thread,
the runtime stopped generating but kept its side of the socket open, and the reader stayed
blocked for the whole 600 s read timeout. Shutting the socket down first (httpcore's
`network_stream` extension, `get_extra_info("socket")`) made the read fail in 10 ms.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest
from test_lmstudio_adapter import HISTORY, PERSONA, _adapter, _chunk, _Completions, local

from val_domain.gateway import GatewayError, GatewayErrorKind


class _Socket:
    def __init__(self) -> None:
        self.shut = threading.Event()
        self.how: int | None = None

    def shutdown(self, how: int) -> None:
        self.how = how
        self.shut.set()


class _NetworkStream:
    def __init__(self, sock: _Socket) -> None:
        self._sock = sock

    def get_extra_info(self, name: str) -> object:
        return self._sock if name == "socket" else None


class _BlockedStream:
    """A runtime that sends nothing and never closes its side: the read blocks until the
    socket is shut down, then fails as a real socket read does."""

    def __init__(self, sock: _Socket) -> None:
        self._sock = sock
        self.response = type("R", (), {"extensions": {"network_stream": _NetworkStream(sock)}})()
        self.closed = 0

    def __iter__(self) -> _BlockedStream:
        return self

    def __next__(self) -> object:
        if not self._sock.shut.wait(30):
            raise AssertionError("the reader was never released")
        raise OSError(9, "Bad file descriptor")

    def close(self) -> None:
        self.closed += 1


class _BlockedCompletions(_Completions):
    def __init__(self, stream: _BlockedStream) -> None:
        super().__init__()
        self.blocked = stream

    def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return self.blocked


def test_a_superseded_stream_is_shut_down_and_the_reader_released_at_once() -> None:
    sock = _Socket()
    stream = _BlockedStream(sock)
    adapter, _ = _adapter(_BlockedCompletions(stream))
    flag = threading.Event()
    threading.Thread(target=lambda: (time.sleep(0.15), flag.set()), daemon=True).start()
    began = time.monotonic()
    with pytest.raises(GatewayError) as ended:
        list(adapter.stream(local(), HISTORY, PERSONA, 6_144, cancelled=flag.is_set))
    assert ended.value.kind is GatewayErrorKind.SUPERSEDED
    assert time.monotonic() - began < 2.0, "the reader did not wait for any timeout"
    assert sock.how == socket.SHUT_RDWR and stream.closed == 1


def test_an_unsuperseded_stream_is_never_shut_down() -> None:
    chunks = [_chunk(content="Good evening, my lord.", finish="stop")]
    completions = _Completions(chunks=chunks)
    adapter, _ = _adapter(completions)
    events = list(adapter.stream(local(), HISTORY, PERSONA, 6_144, cancelled=lambda: False))
    assert any(getattr(e, "text", None) == "Good evening, my lord." for e in events)


def test_a_call_superseded_before_dispatch_sends_nothing() -> None:
    """28 September 2026 (C1b): a call superseded while it was still being prepared was
    dispatched anyway, 2.7 s later. Stale work sends nothing."""
    completions = _Completions(chunks=[_chunk(content="Good evening.", finish="stop")])
    adapter, _ = _adapter(completions)
    with pytest.raises(GatewayError) as ended:
        list(adapter.stream(local(), HISTORY, PERSONA, 6_144, cancelled=lambda: True))
    assert ended.value.kind is GatewayErrorKind.SUPERSEDED
    assert "no request was sent" in str(ended.value)
    assert completions.kwargs == {}, "nothing reached the runtime"
