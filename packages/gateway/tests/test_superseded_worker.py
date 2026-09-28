"""A superseded worker that does not end cannot hold his words — 28 September 2026.

The C1a stall: speech resumed 0.55 s after an early submission, the early turn was
superseded, and its worker never returned; his joined words were submitted only at
that worker's end, so they waited 243 s. Where the worker blocked is not known. These
tests hold the worker deliberately — after his fragment was recorded, and before it
was — and require the recovery the order sets out:

- his complete words, in the order he said them, become the turn within the deadline;
- the stale worker publishes nothing, plays nothing, writes no answer and sends no
  further request when it finally returns (fault held, then released);
- no duplicate submission or answer;
- abandoned workers are counted, and past the limit Voice ends with the reason;
- a superseded turn's worker ending late never takes the newer turn's delivery.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from test_deliberation_machinery import ScriptedAdapter, build_gateway, clean_personas, ok, store
from test_owner_precedence import UnheardDelivery
from test_voice_input import MARKER, ScriptedRecognizer, a_conversation, final, started
from test_voice_presentation import HeldVoice

import val_gateway.voice as voice
from val_domain.gateway import CacheTtl, Message, ModelConfig
from val_domain.provider import ProviderEvent, TextDelta
from val_gateway import conversations
from val_gateway.deliberate import send
from val_gateway.projects import load_catalogue
from val_gateway.seal import SealRoute
from val_gateway.voice import VoiceSession, VoiceSessionState
from val_policy.turn_completion import COMPLETE_GRACE_S


@dataclass
class HeldFirstAdapter(ScriptedAdapter):
    """The first call blocks, deaf to cancellation, until released — then completes.

    It stands for the unknown point where the C1a worker blocked: the runtime had the
    request and the client had disconnected, yet the worker did not return.
    """

    hold: threading.Event = field(default_factory=threading.Event)
    calls: int = 0

    def stream(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> Iterator[ProviderEvent]:
        self.calls += 1
        result = self.complete(config, messages, system, max_output_tokens, output_schema)
        if self.calls == 1:
            assert self.hold.wait(30), "the test never released the held call"
        yield TextDelta(result.text)
        yield result


def rows(store: Engine, query: str) -> list[tuple]:
    with store.connect() as connection:
        return [tuple(r) for r in connection.execute(text(query)).all()]


def messages(store: Engine) -> list[tuple]:
    return rows(
        store,
        "select m.role::text, mc.content, mc.live from messages m "
        "join messages_current mc on mc.id = m.id order by m.sequence",
    )


def _session(
    store: Engine,
    adapter: ScriptedAdapter,
    batches: list,
    *,
    hold_submit: threading.Event | None = None,
    adaptive: bool = True,
    precedence: bool = False,
) -> tuple[VoiceSession, dict, list[UnheardDelivery]]:
    gateway = build_gateway(store, adapter)
    catalogue = load_catalogue(store)
    submissions: list[str] = []

    def submit(content: str, existing: UUID | None, **kwargs: object) -> object:
        submissions.append(content)
        if hold_submit is not None and len(submissions) == 1:
            assert hold_submit.wait(30), "the test never released the held submission"
        return send(
            store,
            gateway,
            content,
            catalogue=catalogue,
            conversation_id=existing,
            spoken=True,
            seal_route=SealRoute.UTTERANCE_FINALIZED,
            on_delta=kwargs.get("on_delta"),  # type: ignore[arg-type]
            cancelled=kwargs.get("cancelled"),  # type: ignore[arg-type]
            on_persisted=kwargs.get("on_persisted"),  # type: ignore[arg-type]
        )

    deliveries: list[UnheardDelivery] = []

    def make() -> HeldVoice:
        held = UnheardDelivery()
        held.audible = False
        deliveries.append(held)
        return held

    clock = {"now": 1000.0}
    session = VoiceSession(
        store,
        ScriptedRecognizer(batches=batches),
        submit=submit,  # type: ignore[arg-type]
        conversation_id=a_conversation(store),
        clock=lambda: clock["now"],
        speech=make,  # type: ignore[arg-type]
        adaptive_endpoint=adaptive,
        owner_precedence=precedence,
    )
    session._submissions = submissions  # type: ignore[attr-defined]
    return session, clock, deliveries


def resume_batches() -> list:
    """Utterance 1, then speech resuming 0.7 s after its endpoint (fresh per test: the
    scripted recognizer consumes its batches)."""
    return [
        [started(1, at=10.0), final(1, "Tell me about the invitation.", at=11.6, endpoint_at=11.5)],
        [started(2, at=12.2)],
        [final(2, "And the venue as well.", at=13.4, endpoint_at=13.3)],
    ]


def _resume(session: VoiceSession, clock: dict) -> float:
    """Utterance 1 submitted early; 2 resumes inside the bound. Returns when superseded."""
    session.start()
    session.feed(MARKER)
    clock["now"] += COMPLETE_GRACE_S + 0.01
    session.advance()  # submitted early
    time.sleep(0.3)  # the worker is inside the held call (or the held submission)
    session.feed(MARKER)  # he resumes
    session.feed(MARKER)  # the rest settles: the early turn is superseded
    return time.monotonic()


def _until(store: Engine, session: VoiceSession, clock: dict, val_messages: int) -> float:
    began = time.monotonic()
    for _ in range(200):
        session.advance()
        clock["now"] += 0.5
        if rows(store, "select count(*) from messages where role = 'val'")[0][0] >= val_messages:
            return time.monotonic() - began
        time.sleep(0.02)
    raise AssertionError("no answer arrived")


def _wait_for_workers(session: VoiceSession) -> None:
    for _ in range(300):
        with session._lock:
            if not session._superseded_workers:
                return
        time.sleep(0.02)
    raise AssertionError("the released worker never ended")


def test_a_worker_held_after_his_fragment_was_recorded_cannot_hold_his_words(
    store: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice, "SUPERSEDED_WORKER_DEADLINE_SECONDS", 0.2)
    adapter = HeldFirstAdapter(
        [ok("The invitation, my lord."), ok("The invitation and the venue, my lord: both in hand.")]
    )
    session, clock, deliveries = _session(store, adapter, resume_batches())
    superseded = _resume(session, clock)
    _until(store, session, clock, 1)
    recovered = time.monotonic() - superseded
    assert recovered < 0.2 + 2.0, "his words went ahead within the deadline plus the turn"
    got = messages(store)
    assert [(r[0], r[2]) for r in got] == [("user", False), ("user", True), ("val", True)], got
    assert got[1][1] == "Tell me about the invitation. And the venue as well.", "complete, in order"
    assert got[2][1].startswith("The invitation and the venue")
    assert adapter.calls == 2 and len(session._submissions) == 2  # type: ignore[attr-defined]
    assert deliveries[0].interrupted, "the stale delivery was stopped"

    adapter.hold.set()  # the stale worker finally returns — with a completed answer
    _wait_for_workers(session)
    session.advance()
    assert messages(store) == got, "its answer was refused: nothing published, nothing written"
    assert adapter.calls == 2, "no further request, no duplicate submission"
    assert session.state is not VoiceSessionState.ERROR
    session.close()


def test_a_worker_held_before_his_fragment_was_recorded_loses_none_of_his_words(
    store: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice, "SUPERSEDED_WORKER_DEADLINE_SECONDS", 0.2)
    held = threading.Event()
    adapter = HeldFirstAdapter([ok("The invitation and the venue, my lord: both in hand.")])
    adapter.calls = 1  # nothing is held inside the provider in this test
    session, clock, _ = _session(store, adapter, resume_batches(), hold_submit=held)
    _resume(session, clock)
    _until(store, session, clock, 1)
    got = messages(store)
    assert [(r[0], r[2]) for r in got] == [("user", True), ("val", True)], got
    assert got[0][1] == "Tell me about the invitation. And the venue as well."

    held.set()  # the stale worker reaches Core after the fact: it may write nothing
    _wait_for_workers(session)
    session.advance()
    assert messages(store) == got, "no late fragment, out of order or otherwise"
    assert session.state is not VoiceSessionState.ERROR
    session.close()


def test_abandoned_workers_past_the_limit_end_voice_with_the_reason(
    store: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voice, "SUPERSEDED_WORKER_DEADLINE_SECONDS", 0.2)
    monkeypatch.setattr(voice, "MAX_ABANDONED_WORKERS", 0)
    adapter = HeldFirstAdapter([ok("The invitation, my lord."), ok("Both in hand, my lord.")])
    session, clock, _ = _session(store, adapter, resume_batches())
    _resume(session, clock)
    for _ in range(50):
        session.advance()
        if session.state is VoiceSessionState.ERROR:
            break
        time.sleep(0.02)
    assert session.state is VoiceSessionState.ERROR
    assert "superseded voice workers have not ended" in (session.error or "")
    adapter.hold.set()
    _wait_for_workers(session)
    session.close()


def test_a_superseded_worker_ending_late_never_takes_the_newer_turns_delivery(
    store: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ten driver timeouts of 28 September: the old worker's `_record` moved the
    newer turn's delivery out of hand-off, so its closing piece was never collected."""
    monkeypatch.setattr(voice, "SUPERSEDED_WORKER_DEADLINE_SECONDS", 60.0)  # not abandoned
    adapter = HeldFirstAdapter(
        [ok("A haunted house, my lord."), ok("A lighthouse stands on the point, my lord.")]
    )
    session, clock, deliveries = _session(
        store,
        adapter,
        [
            [started(1), final(1, "Describe a haunted house in one sentence.")],
            [started(2)],
            [final(2, "Actually, never mind. Describe a lighthouse instead.")],
        ],
        adaptive=False,
        precedence=True,
    )
    session.start()
    session.feed(MARKER)
    clock["now"] += 5.0
    session.advance()  # the first turn: its call is held
    time.sleep(0.2)
    session.feed(MARKER)
    session.feed(MARKER)  # a clear replacement: the first is superseded, the second goes
    _until(store, session, clock, 1)
    newer = deliveries[1]
    assert session.speech_handover is newer
    adapter.hold.set()  # the superseded worker ends only now
    _wait_for_workers(session)
    assert session.speech_handover is newer, "the newer answer stays collectable"
    session.close()


def test_an_append_refused_under_the_lock_writes_nothing(store: Engine) -> None:
    conversation = a_conversation(store)
    with pytest.raises(conversations.AppendRefusedError):
        conversations.append(
            store,
            conversation,
            role=conversations.StoredRole.VAL,
            content="late",
            refuse_if=lambda: True,
        )
    assert rows(store, "select count(*) from messages where role = 'val'")[0][0] == 0
