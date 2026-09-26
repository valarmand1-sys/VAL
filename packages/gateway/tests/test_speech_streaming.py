"""Her first words heard sooner: segments voiced in pieces — owner order, 26 Sept 2026.

Voicing her first sentence whole took 4.3-5.4 s while her answer was still being
written; its first second, streamed through the installed library's own path, was
ready in ~0.75 s. These tests hold the delivery contract through that change: the
first piece is the delivered boundary, pieces reach the desktop in order and end with
a closing piece, a segment is counted and recorded once, an interruption stops the
rest, and a provider that cannot stream is voiced whole as before.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

import io
import threading
import wave
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import Engine
from test_deliberation_machinery import clean_personas, store
from test_speech_delivery import ANSWER, ScriptedVoice, a_delivery, deliver

from val_domain.speech import DeliveryState, SpeechRequest, SpeechResult
from val_gateway.playback import DesktopSink


def a_piece(samples: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(24000)
        writer.writeframes(b"\x01\x00" * samples)
    return buffer.getvalue()


@dataclass
class StreamingVoice(ScriptedVoice):
    """The local voice, voicing each segment in `pieces` pieces."""

    pieces: int = 3
    streams: bool = True
    after_first_piece: threading.Event | None = None
    hold: threading.Event | None = None
    handed: list[int] = field(default_factory=list)

    def synthesize_stream(
        self, request: SpeechRequest, on_chunk: Callable[[bytes, float], None]
    ) -> SpeechResult | None:
        if not self.streams:
            return None
        for index in range(self.pieces):
            on_chunk(a_piece(2400), 0.1)
            self.handed.append(index)
            if index == 0 and self.after_first_piece is not None:
                self.after_first_piece.set()
                if self.hold is not None:
                    self.hold.wait(10)
        self.spoken.append(request.text)
        whole = super().synthesize(request)
        self.spoken.pop()  # counted once, below
        self.spoken.append(request.text)
        return whole


def drained(sink: DesktopSink) -> list[tuple[int, int, bool, int]]:
    offers = []
    while (offer := sink.collect()) is not None:
        offers.append((offer.segment_index, offer.chunk, offer.last, len(offer.audio)))
    return offers


def test_pieces_reach_the_desktop_in_order_and_each_segment_is_closed(
    store: Engine,
) -> None:
    voice = StreamingVoice(pieces=3)
    sink = DesktopSink()
    delivery = a_delivery(store, voice, sink=sink)
    deliver(delivery, ANSWER)
    offers = drained(sink)
    segments = sorted({index for index, *_ in offers})
    assert segments == [segment.index for segment in delivery.spoken]
    for index in segments:
        mine = [(chunk, last, size) for i, chunk, last, size in offers if i == index]
        assert [chunk for chunk, *_ in mine] == [0, 1, 2, 3]
        assert [last for _, last, _ in mine] == [False, False, False, True]
        assert mine[-1][2] == 0, "the closing piece carries no audio"
    # Counted once per segment, and the delivered prefix is the segments' own text.
    assert sink.segments_played == len(segments)
    assert delivery.delivered_prefix == " ".join(s.text for s in delivery.spoken)
    assert delivery.state is DeliveryState.COMPLETED


def test_the_first_piece_is_the_delivered_boundary(store: Engine) -> None:
    first = threading.Event()
    hold = threading.Event()
    voice = StreamingVoice(pieces=3, after_first_piece=first, hold=hold)
    sink = DesktopSink()
    delivery = a_delivery(store, voice, sink=sink)
    worker = threading.Thread(target=deliver, args=(delivery, ANSWER), daemon=True)
    worker.start()
    assert first.wait(10)
    # Mid-segment: the rest is still being voiced, and she is already audible.
    assert delivery.audible
    assert delivery.state is DeliveryState.STARTED
    assert delivery.first_audio_ms is not None
    hold.set()
    worker.join(10)


def test_an_interruption_mid_segment_hands_over_nothing_more(store: Engine) -> None:
    first = threading.Event()
    hold = threading.Event()
    voice = StreamingVoice(pieces=4, after_first_piece=first, hold=hold)
    sink = DesktopSink()
    delivery = a_delivery(store, voice, sink=sink)
    worker = threading.Thread(target=deliver, args=(delivery, ANSWER), daemon=True)
    worker.start()
    assert first.wait(10)
    delivery.interrupt("the owner began speaking")
    hold.set()
    worker.join(10)
    assert drained(sink) == [], "what was not collected is discarded, and nothing follows"
    assert delivery.state is DeliveryState.INTERRUPTED


def test_a_provider_that_cannot_stream_is_voiced_whole_as_before(store: Engine) -> None:
    voice = StreamingVoice(streams=False)
    sink = DesktopSink()
    delivery = a_delivery(store, voice, sink=sink)
    deliver(delivery, ANSWER)
    offers = drained(sink)
    assert offers and all(chunk == 0 and last for _, chunk, last, _ in offers)
    assert [segment.text for segment in delivery.spoken] == voice.spoken
