"""Owner precedence over an obsolete unheard answer — Milestone B §8, corrected 26 September 2026.

Release-gaps order §1 and §2. Behind `owner_precedence=True`. When his next words are
confirmed while the answer to his previous words is still being made and none of it has
begun to be heard, **his words decide**: a stop or a clear replacement, correction or
redirection sets the obsolete answer aside — the provider stream is closed at the next
chunk, the call is recorded `superseded` with its reason on the measurement row and its
usage unknown, no message is written for it, his earlier message stays exactly as it was
— and a replacement is answered as its own message while a stop asks for nothing new. A
continuation ("And after that…") or anything ambiguous leaves the earlier request in
force: both are answered, in order. An answer he has begun to hear (the desktop's
playback report) is never cut by this rule. Without the switch nothing changes.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from test_deliberation_machinery import ScriptedAdapter, build_gateway, clean_personas, ok, store
from test_voice_input import MARKER, ScriptedRecognizer, a_conversation, final, started
from test_voice_presentation import HeldVoice

from val_domain.gateway import (
    CacheTtl,
    GatewayError,
    GatewayErrorKind,
    Message,
    ModelConfig,
)
from val_domain.provider import ProviderEvent, ProviderResult, TextDelta
from val_gateway.deliberate import send
from val_gateway.loop import UnansweredTurn
from val_gateway.projects import load_catalogue
from val_gateway.seal import SealRoute
from val_gateway.voice import VoiceSession


@dataclass
class SlowStreamingAdapter(ScriptedAdapter):
    """Streams a scripted answer word by word, honouring `cancelled` between chunks.

    `late` extra chunks are yielded *after* the cancellation is seen and before the
    stream ends, standing for tokens a runtime may still emit after the close.
    """

    delay: float = 0.05
    late: int = 0
    released: list[bool] = field(default_factory=list)
    late_yielded: int = 0

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
        result = self.complete(config, messages, system, max_output_tokens, output_schema)
        for word in result.text.split(" "):
            if cancelled is not None and cancelled():
                self.released.append(True)
                for _ in range(self.late):
                    self.late_yielded += 1
                    yield TextDelta("late ")
                raise GatewayError(
                    GatewayErrorKind.SUPERSEDED, "the call was superseded (scripted stream)"
                )
            time.sleep(self.delay)
            yield TextDelta(word + " ")
        yield result


class UnheardDelivery(HeldVoice):
    """The presentation fake with the attributes the session reads, and a hand-off sink.

    `sink` has `collect`, so the session treats it as a desktop hand-off: hearing is then
    the desktop's playback report, never synthesis or the hand-off itself.
    """

    active = True
    state = "started"
    delivered_prefix = ""
    segments_delivered = 0

    def __init__(self) -> None:
        super().__init__()
        self.message_id: object | None = None
        self.fed: list[str] = []
        self.interrupted: list[str] = []
        self.sink = SimpleNamespace(collect=lambda: None, first_audio_at=None)

    def feed(self, text: str) -> None:
        if not self.interrupted:
            self.fed.append(text)

    def bind(self, message_id: object) -> None:
        self.message_id = message_id
        super().bind(message_id)

    def finish(self, text: str) -> None:
        self.finishing.set()

    def interrupt(self, reason: str) -> None:
        self.interrupted.append(reason)


def rows(store: Engine, query: str, **params: object) -> list[tuple]:
    with store.connect() as connection:
        return [tuple(r) for r in connection.execute(text(query), params).all()]


def test_a_superseded_call_ends_unanswered_and_is_recorded_as_such(store: Engine) -> None:
    adapter = SlowStreamingAdapter([ok(" ".join(["word"] * 40))])
    conversation = a_conversation(store)
    flag = threading.Event()
    seen: list[str] = []

    def on_delta(piece: str) -> None:
        seen.append(piece)
        if len(seen) == 3:
            flag.set()  # the owner's next turn confirmed while this answer streams

    outcome = send(
        store,
        build_gateway(store, adapter),
        "Tell me about the garden.",
        catalogue=load_catalogue(store),
        conversation_id=conversation,
        spoken=True,
        seal_route=SealRoute.UTTERANCE_FINALIZED,
        on_delta=on_delta,
        cancelled=flag.is_set,
    )
    assert isinstance(outcome, UnansweredTurn)
    assert isinstance(outcome.error, GatewayError)
    assert outcome.error.kind is GatewayErrorKind.SUPERSEDED
    assert adapter.released == [True], "the stream was closed at the next chunk"
    assert rows(
        store, "select role::text from messages where conversation_id = :c", c=conversation
    ) == [("user",)], "his message stays; no message is written for the superseded answer"
    call = rows(
        store,
        "select mc.status::text, mc.terminal_state::text, mc.tokens_out, "
        "m.runtime_diagnostics->'superseded'->>'reason' from model_calls mc "
        "left join model_call_measurements m on m.model_call_id = mc.id where mc.message_id = :m",
        m=outcome.user_message.id,
    )
    assert len(call) == 1 and call[0][0] == "error" and call[0][1] == "failed"
    assert call[0][2] is None, "what the model produced before the cut is not claimed"
    assert call[0][3] and "superseded" in call[0][3], "distinguishable from an ordinary failure"


def _session(
    store: Engine, adapter: SlowStreamingAdapter, second: str, *, precedence: bool
) -> tuple[VoiceSession, list[UnheardDelivery]]:
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1), final(1, "Tell me about the garden.")],
            [started(2), final(2, second)],
        ]
    )
    gateway = build_gateway(store, adapter)
    catalogue = load_catalogue(store)
    conversation = a_conversation(store)

    def submit(content: str, existing: UUID | None, **kwargs: object) -> object:
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
            withhold_answer=bool(kwargs.get("withhold_answer", False)),
        )

    deliveries: list[UnheardDelivery] = []

    def unheard_delivery() -> HeldVoice:
        held = UnheardDelivery()
        held.audible = False
        deliveries.append(held)
        return held

    clock = {"now": 1000.0}
    session = VoiceSession(
        store,
        recognizer,
        submit=submit,  # type: ignore[arg-type]
        conversation_id=conversation,
        clock=lambda: clock["now"],
        speech=unheard_delivery,  # type: ignore[arg-type]
        owner_precedence=precedence,
    )
    session._clock_box = clock  # type: ignore[attr-defined]
    return session, deliveries


def _speak_twice(session: VoiceSession, *, between: Callable[[], None] | None = None) -> None:
    clock = session._clock_box  # type: ignore[attr-defined]
    session.start()
    session.feed(MARKER)  # utterance 1 settles
    clock["now"] += 5.0
    session.advance()  # submitted; the answer streams slowly, nothing heard
    time.sleep(0.3)
    if between is not None:
        between()
    session.feed(MARKER)  # utterance 2 settles while 1 is in flight
    clock["now"] += 5.0
    session.advance()  # due: decided against the answer in flight


def _drain(session: VoiceSession, store: Engine, *, val_messages: int) -> None:
    session.await_turn(timeout=15)
    for _ in range(80):
        session.advance()
        if rows(store, "select count(*) from messages where role = 'val'")[0][0] >= val_messages:
            break
        time.sleep(0.1)
    session.await_turn(timeout=15)


def test_a_clear_replacement_supersedes_the_unheard_answer(store: Engine) -> None:
    adapter = SlowStreamingAdapter(
        [ok(" ".join(["garden"] * 60)), ok("The venue, my lord, is the library.")], late=2
    )
    session, deliveries = _session(
        store, adapter, "Actually, never mind. Tell me about the venue instead.", precedence=True
    )
    _speak_twice(session)
    _drain(session, store, val_messages=1)
    got = rows(store, "select role::text, content from messages order by sequence")
    assert [r[0] for r in got] == ["user", "user", "val"], got
    assert got[0][1] == "Tell me about the garden.", "his earlier message stays as it was"
    assert got[2][1].startswith("The venue"), "the replacement is answered as its own message"
    assert "late" not in got[2][1] and "garden" not in got[2][1], "late tokens attach to nothing"
    assert adapter.released == [True] and adapter.late_yielded == 2
    first = deliveries[0]
    # First the supersession; then the record's own closing of a turn with no answer.
    assert first.interrupted[0] == "superseded by the owner's next confirmed turn"
    assert all("late" not in piece for piece in first.fed), "nothing fed after the interruption"
    view = session.snapshot()
    assert view.superseded == {
        "kind": "replacement",
        "superseded_utterance": 1,
        "by_utterance": 2,
        "heard": False,
    }
    session.close()


def test_a_continuation_keeps_the_earlier_request_and_both_are_answered(store: Engine) -> None:
    adapter = SlowStreamingAdapter(
        [ok(" ".join(["garden"] * 20)), ok("The orchard, my lord, is beyond the wall.")],
        delay=0.02,
    )
    session, _ = _session(
        store, adapter, "And after that, tell me about the orchard.", precedence=True
    )
    _speak_twice(session)
    _drain(session, store, val_messages=2)
    got = rows(store, "select role::text, content from messages order by sequence")
    assert [r[0] for r in got] == ["user", "val", "user", "val"], got
    assert "garden" in got[1][1] and got[3][1].startswith("The orchard")
    assert adapter.released == [], "nothing was cut: a continuation is not a cancellation"
    assert session.snapshot().superseded is None
    session.close()


def test_ambiguous_new_speech_never_cancels(store: Engine) -> None:
    adapter = SlowStreamingAdapter(
        [ok(" ".join(["garden"] * 20)), ok("Seven, my lord.")], delay=0.02
    )
    session, _ = _session(store, adapter, "What time is the reading?", precedence=True)
    _speak_twice(session)
    _drain(session, store, val_messages=2)
    got = rows(store, "select role::text from messages order by sequence")
    assert [r[0] for r in got] == ["user", "val", "user", "val"], got
    assert adapter.released == []
    session.close()


def test_a_stop_alone_supersedes_and_asks_for_nothing(store: Engine) -> None:
    adapter = SlowStreamingAdapter([ok(" ".join(["garden"] * 60))])
    session, deliveries = _session(store, adapter, "Never mind, Val.", precedence=True)
    _speak_twice(session)
    session.await_turn(timeout=15)
    for _ in range(80):
        session.advance()
        settled = rows(store, "select count(*) from messages")[0][0] >= 2
        # The superseded call's thread is not waited for (§3); its record lands when the
        # scripted stream reaches its next chunk, a moment after the stop was submitted.
        recorded = rows(store, "select count(*) from model_calls where status = 'error'")[0][0]
        if settled and session.snapshot().pending == "" and recorded >= 1:
            break
        time.sleep(0.1)
    session.await_turn(timeout=15)
    got = rows(store, "select role::text, content from messages order by sequence")
    assert [(r[0], r[1]) for r in got] == [
        ("user", "Tell me about the garden."),
        ("user", "Never mind, Val."),
    ], got
    calls = rows(
        store,
        "select m.content, mc.status::text from model_calls mc "
        "join messages m on m.id = mc.message_id "
        "where mc.task_type::text in ('conversation', 'light_conversation') order by mc.created_at",
    )
    assert calls == [("Tell me about the garden.", "error")], (
        "one call, the superseded one; the stop asked for nothing"
    )
    assert adapter.released == [True]
    assert deliveries[0].interrupted, "queued audio of the obsolete answer was discarded"
    assert session.snapshot().superseded == {
        "kind": "stop",
        "superseded_utterance": 1,
        "by_utterance": 2,
        "heard": False,
    }
    assert session.error is None, "a stop is his decision, not a failure of the session"
    session.close()


def test_an_answer_he_has_begun_to_hear_is_not_cut_by_this_rule(store: Engine) -> None:
    """The heard boundary is the desktop's playback report; barge-in is a separate rule."""
    adapter = SlowStreamingAdapter(
        [ok(" ".join(["garden"] * 20)), ok("The venue, my lord, is the library.")], delay=0.02
    )
    session, _ = _session(
        store, adapter, "Actually, never mind. Tell me about the venue instead.", precedence=True
    )
    _speak_twice(session, between=lambda: session.playback_reported("playback_started"))
    _drain(session, store, val_messages=2)
    got = rows(store, "select role::text from messages order by sequence")
    assert [r[0] for r in got] == ["user", "val", "user", "val"], got
    assert adapter.released == [], "an answer he has begun to hear is never superseded"
    assert session.snapshot().superseded is None
    session.close()


def test_synthesis_under_way_but_nothing_played_is_still_unheard(store: Engine) -> None:
    adapter = SlowStreamingAdapter(
        [ok(" ".join(["garden"] * 60)), ok("The venue, my lord, is the library.")]
    )
    session, deliveries = _session(
        store, adapter, "Actually, never mind. Tell me about the venue instead.", precedence=True
    )

    def synthesis_begun() -> None:
        # Audio at the hand-off, synthesis begun, nothing reported played by the desktop.
        deliveries[0].first_tts_start_ms = 120
        deliveries[0].sink.first_audio_at = 1.0

    _speak_twice(session, between=synthesis_begun)
    _drain(session, store, val_messages=1)
    got = rows(store, "select role::text from messages order by sequence")
    assert [r[0] for r in got] == ["user", "user", "val"], got
    assert adapter.released == [True]
    session.close()


def test_without_the_switch_the_new_words_wait(store: Engine) -> None:
    adapter = SlowStreamingAdapter(
        [ok(" ".join(["garden"] * 20)), ok("The venue, my lord.")], delay=0.02
    )
    session, _ = _session(
        store, adapter, "Actually, never mind. Tell me about the venue instead.", precedence=False
    )
    _speak_twice(session)
    _drain(session, store, val_messages=2)
    got = rows(store, "select role::text from messages order by sequence")
    assert [r[0] for r in got] == ["user", "val", "user", "val"], got
    assert adapter.released == []
    assert session.snapshot().superseded is None
    session.close()


def test_an_unheard_answer_is_held_while_he_speaks_and_played_after_a_continuation(
    store: Engine,
) -> None:
    """Onset holds the hand-off of an unheard answer; confirmation decides it (§1 and §2)."""
    adapter = SlowStreamingAdapter(
        [ok(" ".join(["garden"] * 30)), ok("The orchard, my lord.")], delay=0.03
    )
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1), final(1, "Tell me about the garden.")],
            [started(2)],
            [final(2, "And after that, tell me about the orchard.")],
        ]
    )
    gateway = build_gateway(store, adapter)
    catalogue = load_catalogue(store)
    deliveries: list[UnheardDelivery] = []

    def unheard_delivery() -> HeldVoice:
        held = UnheardDelivery()
        held.audible = False
        deliveries.append(held)
        return held

    def submit(content: str, existing: UUID | None, **kwargs: object) -> object:
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
            withhold_answer=bool(kwargs.get("withhold_answer", False)),
        )

    clock = {"now": 1000.0}
    session = VoiceSession(
        store,
        recognizer,
        submit=submit,  # type: ignore[arg-type]
        conversation_id=a_conversation(store),
        clock=lambda: clock["now"],
        speech=unheard_delivery,  # type: ignore[arg-type]
        owner_precedence=True,
    )
    session.start()
    session.feed(MARKER)
    clock["now"] += 5.0
    session.advance()  # utterance 1 in flight, unheard
    time.sleep(0.2)
    assert not session.speech_hold
    session.feed(MARKER)  # he begins to speak: onset only
    assert session.speech_hold, "held while his words are in the air"
    assert deliveries[0].interrupted == [], "not stopped on onset: nothing of it was heard"
    session.feed(MARKER)  # his words settle
    assert session.speech_hold, "still held: settled but not yet confirmed and decided"
    clock["now"] += 5.0
    session.advance()  # confirmed: a continuation — kept
    assert not session.speech_hold, "released: the earlier answer plays after him"
    assert deliveries[0].interrupted == []
    session.await_turn(timeout=15)
    for _ in range(80):
        session.advance()
        if rows(store, "select count(*) from messages where role = 'val'")[0][0] >= 2:
            break
        time.sleep(0.1)
    session.await_turn(timeout=15)
    got = rows(store, "select role::text from messages order by sequence")
    assert [r[0] for r in got] == ["user", "val", "user", "val"], got
    assert adapter.released == []
    session.close()


@dataclass
class StuckAdapter(SlowStreamingAdapter):
    """Ignores `cancelled` for `stuck` seconds after it is set — a runtime that stops
    generating on disconnect but keeps the socket open (the P4c run of 27 September)."""

    stuck: float = 2.5

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
        result = self.complete(config, messages, system, max_output_tokens, output_schema)
        for word in result.text.split(" "):
            if cancelled is not None and cancelled():
                time.sleep(self.stuck)  # blocked on a read the runtime never ends promptly
                self.released.append(True)
                raise GatewayError(GatewayErrorKind.SUPERSEDED, "stuck stream, finally closed")
            time.sleep(self.delay)
            yield TextDelta(word + " ")
        yield result


def test_the_replacement_is_dispatched_without_waiting_for_the_stuck_call(
    store: Engine,
) -> None:
    """Release-gaps order §3 (P4c): the superseded thread is not waited for."""
    adapter = StuckAdapter(
        [ok(" ".join(["garden"] * 80)), ok("The venue, my lord, is the library.")], stuck=2.5
    )
    session, _ = _session(
        store, adapter, "Actually, never mind. Tell me about the venue instead.", precedence=True
    )
    _speak_twice(session)
    began = time.monotonic()
    for _ in range(60):
        session.advance()
        if rows(store, "select count(*) from messages where role = 'val'")[0][0] >= 1:
            break
        time.sleep(0.05)
    answered_after = time.monotonic() - began
    assert answered_after < 2.5, f"the replacement waited {answered_after:.2f}s for the stuck call"
    assert adapter.released == [], "the stuck call had not ended when the replacement was answered"
    session.await_turn(timeout=15)
    for _ in range(80):  # the stuck thread ends later and clobbers nothing
        if adapter.released:
            break
        time.sleep(0.1)
    got = rows(store, "select role::text, content from messages order by sequence")
    assert [r[0] for r in got] == ["user", "user", "val"], got
    assert got[2][1].startswith("The venue")
    assert session.snapshot().superseded is not None and session.error is None
    session.close()
