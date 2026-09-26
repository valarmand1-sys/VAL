"""A session whose window has gone is closed — owner diagnostic, 25 September 2026.

Three of the four sessions of his diagnostic were never closed: each window went
away without its close request reaching the service. An hour later the service still
held their three recognizer processes, about 600 MB each, and the store still said
`listening`. These tests hold the service-side rule that ends such a session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from val_gateway.voice import ABANDONED_AFTER_SECONDS, VoiceSessions, VoiceSessionState


@dataclass
class FakeSession:
    conversation_id: UUID | None = field(default_factory=uuid4)
    state: VoiceSessionState = VoiceSessionState.LISTENING
    closed: list[str] = field(default_factory=list)

    def close(self, reason: str = "") -> None:
        self.closed.append(reason)
        self.state = VoiceSessionState.CLOSED


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_a_session_nothing_asks_about_is_closed_and_one_in_use_is_not() -> None:
    clock = Clock()
    registry = VoiceSessions(clock=clock)
    used, abandoned = FakeSession(), FakeSession()
    used_key, abandoned_key = uuid4(), uuid4()
    registry.add(used_key, used)  # type: ignore[arg-type]
    registry.add(abandoned_key, abandoned)  # type: ignore[arg-type]

    clock.now = ABANDONED_AFTER_SECONDS - 1
    assert registry.get(used_key) is used  # the desktop is still polling this one
    clock.now = ABANDONED_AFTER_SECONDS + 1

    assert registry.reap() == [abandoned_key]
    assert abandoned.closed and "window has gone" in abandoned.closed[0]
    assert used.closed == []
    assert registry.get(abandoned_key) is None
    assert registry.get(used_key) is used


def test_a_reaped_session_no_longer_seals_its_conversation_transiently() -> None:
    clock = Clock()
    registry = VoiceSessions(clock=clock)
    gone = FakeSession()
    registry.add(uuid4(), gone)  # type: ignore[arg-type]
    assert registry.live_conversations().active_in(gone.conversation_id)
    clock.now = ABANDONED_AFTER_SECONDS + 1
    registry.reap()
    assert not registry.live_conversations().active_in(gone.conversation_id)


def test_nothing_is_reaped_early() -> None:
    clock = Clock()
    registry = VoiceSessions(clock=clock)
    session = FakeSession()
    registry.add(uuid4(), session)  # type: ignore[arg-type]
    clock.now = ABANDONED_AFTER_SECONDS - 0.5
    assert registry.reap() == []
    assert session.closed == []


def test_the_voice_is_released_when_the_last_session_ends_and_not_before() -> None:
    """Voice-mode repair §5: the resident speech worker lives only while Voice is on."""
    released: list[str] = []
    registry = VoiceSessions(clock=Clock(), on_empty=lambda: released.append("released"))
    first, second = uuid4(), uuid4()
    registry.add(first, FakeSession())  # type: ignore[arg-type]
    registry.add(second, FakeSession())  # type: ignore[arg-type]

    registry.remove(first)
    assert released == [], "another session still has Voice on"
    registry.remove(second)
    assert released == ["released"]


def test_a_reaped_last_session_releases_the_voice_too() -> None:
    clock = Clock()
    released: list[str] = []
    registry = VoiceSessions(clock=clock, on_empty=lambda: released.append("released"))
    registry.add(uuid4(), FakeSession())  # type: ignore[arg-type]
    clock.now = ABANDONED_AFTER_SECONDS + 1
    registry.reap()
    assert released == ["released"]


def test_a_failing_release_does_not_break_closing() -> None:
    def broken() -> None:
        raise RuntimeError("the worker would not stop")

    registry = VoiceSessions(clock=Clock(), on_empty=broken)
    key = uuid4()
    registry.add(key, FakeSession())  # type: ignore[arg-type]
    registry.remove(key)
    assert registry.get(key) is None
