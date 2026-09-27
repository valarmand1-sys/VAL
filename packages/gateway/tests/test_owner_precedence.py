"""Owner precedence over an obsolete unspoken answer — Milestone B §8, 26 September 2026.

Isolated behind `owner_precedence=True`. A confirmed new turn, arriving while the
previous answer's cognition is still running and none of that answer has been heard,
supersedes it: the provider stream is closed at the next chunk (which on the local
runtime releases a generation in progress), the call is recorded as `superseded`, no
message is written for it, his earlier message stays exactly as it was, and the new
turn is answered as its own message. An answer he has begun to hear is never cut off by
this rule, and without the switch nothing changes: the new words wait, as today.
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
from test_voice_input import MARKER, ScriptedRecognizer, a_conversation, final, started
from test_voice_presentation import HeldVoice

from val_domain.gateway import (
    CacheTtl,
    GatewayError,
    GatewayErrorKind,
    Message,
    ModelConfig,
    TerminalState,
)
from val_domain.provider import ProviderEvent, ProviderResult, TextDelta
from val_gateway.deliberate import send
from val_gateway.loop import UnansweredTurn
from val_gateway.projects import load_catalogue
from val_gateway.seal import SealRoute
from val_gateway.voice import VoiceSession


@dataclass
class SlowStreamingAdapter(ScriptedAdapter):
    """Streams a scripted answer word by word, honouring `cancelled` between chunks."""

    delay: float = 0.05
    released: list[bool] = field(default_factory=list)

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
                raise GatewayError(
                    GatewayErrorKind.SUPERSEDED, "the call was superseded (scripted stream)"
                )
            time.sleep(self.delay)
            yield TextDelta(word + " ")
        yield result


class UnheardDelivery(HeldVoice):
    """The presentation fake, with the remaining Delivery attributes the session reads."""

    active = True
    state = "started"
    delivered_prefix = ""
    segments_delivered = 0

    def __init__(self) -> None:
        super().__init__()
        self.message_id: object | None = None

    def bind(self, message_id: object) -> None:
        self.message_id = message_id
        super().bind(message_id)

    def finish(self, text: str) -> None:
        # The presentation fake holds her voice until released; here it simply ends.
        self.finishing.set()


def rows(store: Engine, query: str, **params: object) -> list[tuple]:
    with store.connect() as connection:
        return [tuple(r) for r in connection.execute(text(query), params).all()]


def test_a_superseded_call_ends_unanswered_and_is_recorded(store: Engine) -> None:
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
        "select status::text, terminal_state::text, tokens_out from model_calls "
        "where message_id = :m",
        m=outcome.user_message.id,
    )
    assert len(call) == 1 and call[0][0] == "error" and call[0][1] == "failed"
    assert call[0][2] is None, "what the model produced before the cut is not claimed"


def _session(store: Engine, adapter: SlowStreamingAdapter, *, precedence: bool) -> VoiceSession:
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1), final(1, "Tell me about the garden.")],
            [started(2), final(2, "And after that, tell me about the orchard.")],
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
        )

    def unheard_delivery() -> HeldVoice:
        # A delivery that has text fed to it but has not become audible: the streamed
        # answer is being written and voiced, and none of it has reached him yet.
        held = UnheardDelivery()
        held.audible = False
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
    return session


def test_a_confirmed_new_turn_supersedes_an_unheard_answer(store: Engine) -> None:
    adapter = SlowStreamingAdapter(
        [ok(" ".join(["garden"] * 60)), ok("The orchard, my lord, is beyond the wall.")],
        delay=0.05,
    )
    session = _session(store, adapter, precedence=True)
    clock = session._clock_box  # type: ignore[attr-defined]
    session.start()
    session.feed(MARKER)  # utterance 1 settles
    clock["now"] += 5.0
    session.advance()  # submitted; the answer streams slowly, nothing spoken (no speech)
    time.sleep(0.3)
    session.feed(MARKER)  # utterance 2 settles while 1 is in flight
    clock["now"] += 5.0
    session.advance()  # due: supersedes 1
    session.await_turn(timeout=15)
    for _ in range(50):  # the second turn is submitted once the lane is free
        session.advance()
        if rows(store, "select count(*) from messages where role = 'val'")[0][0] >= 1:
            break
        time.sleep(0.1)
    session.await_turn(timeout=15)
    got = rows(store, "select role::text, content from messages order by sequence")
    assert [r[0] for r in got] == ["user", "user", "val"], got
    assert got[0][1] == "Tell me about the garden." and got[2][1].startswith("The orchard")
    assert adapter.released == [True]
    session.close()


def test_without_the_switch_the_new_words_wait(store: Engine) -> None:
    adapter = SlowStreamingAdapter(
        [ok(" ".join(["garden"] * 20)), ok("The orchard, my lord.")], delay=0.02
    )
    session = _session(store, adapter, precedence=False)
    clock = session._clock_box  # type: ignore[attr-defined]
    session.start()
    session.feed(MARKER)
    clock["now"] += 5.0
    session.advance()
    time.sleep(0.1)
    session.feed(MARKER)
    clock["now"] += 5.0
    session.advance()
    session.await_turn(timeout=15)
    for _ in range(50):
        session.advance()
        if rows(store, "select count(*) from messages where role = 'val'")[0][0] >= 2:
            break
        time.sleep(0.1)
    session.await_turn(timeout=15)
    got = rows(store, "select role::text from messages order by sequence")
    assert [r[0] for r in got] == ["user", "val", "user", "val"], got
    assert adapter.released == []
    session.close()
