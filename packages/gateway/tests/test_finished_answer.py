"""An answer whose synthesis has finished — remaining latency work, 28 September 2026, §5 and §6.

Barge-in used to reach only a delivery still being synthesised: once her last segment had
been voiced the session held no active delivery, so his onset left the desktop playing
the rest. Now:

- his onset while a finished answer is still audibly playing stops it at once
  (`request_stop`), and the record follows the desktop's own report of the segment it
  cut (`playback_cut_reported`) — never the service's estimate, which a delayed report
  can make wrong — and never relabels audible sound as unheard;
- a finished answer he has not begun to hear is held while he speaks, and his words
  decide it: a stop or a clear replacement sets it aside, anything else lets it play;
- behind `combine_continuations`, a clear continuation of an unheard answer still being
  made sets it aside too, and one answer covers both of his messages — both stay
  canonical — at most `MAX_COMBINED_RESTARTS` times in a row.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

import time
from uuid import UUID

from sqlalchemy import Engine
from test_deliberation_machinery import build_gateway, clean_personas, ok, store
from test_owner_precedence import SlowStreamingAdapter, UnheardDelivery, rows
from test_voice_input import MARKER, ScriptedRecognizer, a_conversation, final, started
from test_voice_presentation import HeldVoice

from val_gateway.deliberate import send
from val_gateway.projects import load_catalogue
from val_gateway.seal import SealRoute
from val_gateway.voice import MAX_COMBINED_RESTARTS, VoiceSession


class FinishedDelivery(UnheardDelivery):
    """A hand-off delivery whose synthesis finishes when the turn does."""

    def __init__(self) -> None:
        super().__init__()
        self.cuts: list[tuple[str, set[int]]] = []
        self.stops: list[str] = []
        self.reported_cuts: list[int] = []
        self.stop_requested: str | None = None

    def finish(self, text: str) -> None:
        super().finish(text)
        self.active = False
        self.state = "completed"

    def request_stop(self, reason: str) -> float | None:
        if self.state in ("interrupted", "failed"):
            return None
        self.stops.append(reason)
        self.stop_requested = reason
        return 0.01

    def playback_cut_reported(self, segment_index: int) -> bool:
        self.reported_cuts.append(segment_index)
        self.state = "interrupted"
        return True

    def cut_playback(self, reason: str, started_segments: set[int]) -> float | None:
        if self.state in ("interrupted", "failed"):
            return None
        self.cuts.append((reason, set(started_segments)))
        self.state = "interrupted"
        return 0.01


def _session(
    store: Engine,
    adapter: SlowStreamingAdapter,
    batches: list,
    *,
    precedence: bool = True,
    combine: bool = False,
) -> tuple[VoiceSession, list[FinishedDelivery], dict]:
    gateway = build_gateway(store, adapter)
    catalogue = load_catalogue(store)

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

    deliveries: list[FinishedDelivery] = []

    def make() -> HeldVoice:
        delivery = FinishedDelivery()
        delivery.audible = False
        deliveries.append(delivery)
        return delivery

    clock = {"now": 1000.0}
    session = VoiceSession(
        store,
        ScriptedRecognizer(batches=batches),
        submit=submit,  # type: ignore[arg-type]
        conversation_id=a_conversation(store),
        clock=lambda: clock["now"],
        speech=make,  # type: ignore[arg-type]
        owner_precedence=precedence,
        combine_continuations=combine,
    )
    return session, deliveries, clock


def _answered(store: Engine, count: int, session: VoiceSession, clock: dict) -> None:
    for _ in range(150):
        session.advance()
        clock["now"] += 0.5
        if rows(store, "select count(*) from messages where role = 'val'")[0][0] >= count:
            break
        time.sleep(0.05)
    session.await_turn(timeout=15)


def test_speaking_over_a_finished_answer_still_playing_stops_it(store: Engine) -> None:
    adapter = SlowStreamingAdapter([ok("Good evening, my lord.")], delay=0.0)
    session, deliveries, clock = _session(
        store,
        adapter,
        [[started(1), final(1, "Good evening, Val.")], [started(2)]],
        precedence=False,  # the rule holds without the candidate switches too
    )
    session.start()
    session.feed(MARKER)
    clock["now"] += 5.0
    _answered(store, 1, session, clock)
    first = deliveries[0]
    assert first.state == "completed" and session.delivery is None, "synthesis finished"
    message = str(first.message_id)
    # The desktop took her first segment and began playing it; 3 s of audio are sounding.
    session.speech_handed_over(3.0, segment=(message, 1), current=True)
    session.speech_handed_over(2.0, segment=(message, 2))
    session.playback_reported("playback_started", segment=(message, 1))
    session.feed(MARKER)  # his onset, while she is still audibly speaking
    assert first.stops and "still playing" in first.stops[0], (
        "barge-in reached an answer whose synthesis had finished"
    )
    assert first.cuts == [] and first.reported_cuts == [], "nothing recorded on an estimate"
    assert not session._playback_occupied_locked(), "nothing is counted as sounding any more"
    # The desktop stops and says which segment it cut; that word is the record.
    session.playback_reported("playback_interrupted", segment=(message, 1))
    assert first.reported_cuts == [1]
    session.close()


def test_a_stop_that_lands_after_she_finished_records_no_interruption(store: Engine) -> None:
    """B2, 28 September: reports delayed 1.5 s, his words 1.1 s after her last sound."""
    adapter = SlowStreamingAdapter([ok("You're welcome, my lord.")], delay=0.0)
    session, deliveries, clock = _session(
        store, adapter, [[started(1), final(1, "Thank you, Val.")], [started(2)]]
    )
    session.start()
    session.feed(MARKER)
    clock["now"] += 5.0
    _answered(store, 1, session, clock)
    first = deliveries[0]
    message = str(first.message_id)
    session.speech_handed_over(3.0, segment=(message, 1), current=True)
    session.playback_reported("playback_started", segment=(message, 1))
    session.feed(MARKER)  # the service still believes she is sounding
    assert first.stops, "the desktop is told to stop — harmless if nothing plays"
    # Its delayed report: the segment had completed, and nothing was interrupted.
    session.playback_reported("playback_completed", segment=(message, 1))
    assert first.reported_cuts == [] and first.cuts == [], "heard whole; the record stays so"
    session.close()


def test_silence_after_she_has_finished_playing_cuts_nothing(store: Engine) -> None:
    adapter = SlowStreamingAdapter([ok("Good evening, my lord.")], delay=0.0)
    session, deliveries, clock = _session(
        store, adapter, [[started(1), final(1, "Good evening, Val.")], [started(2)]]
    )
    session.start()
    session.feed(MARKER)
    clock["now"] += 5.0
    _answered(store, 1, session, clock)
    message = str(deliveries[0].message_id)
    session.speech_handed_over(0.05, segment=(message, 1), current=True)
    session.playback_reported("playback_started", segment=(message, 1))
    session.playback_reported("playback_completed", segment=(message, 1))
    time.sleep(0.1)
    session.feed(MARKER)
    assert deliveries[0].cuts == [] and deliveries[0].stops == [], (
        "an answer already heard to its end is left alone"
    )
    session.close()


def test_a_finished_unheard_answer_is_held_and_a_replacement_sets_it_aside(
    store: Engine,
) -> None:
    adapter = SlowStreamingAdapter(
        [ok("The garden, my lord, is in bloom."), ok("The venue, my lord, is the library.")],
        delay=0.0,
    )
    session, deliveries, clock = _session(
        store,
        adapter,
        [
            [started(1), final(1, "Tell me about the garden.")],
            [started(2)],
            [final(2, "Actually, never mind. Tell me about the venue instead.")],
        ],
    )
    session.start()
    session.feed(MARKER)
    clock["now"] += 5.0
    _answered(store, 1, session, clock)
    assert deliveries[0].state == "completed"
    session.feed(MARKER)  # he begins before a sound of it was played
    assert session.speech_hold, "nothing of the finished answer is handed over while he speaks"
    session.feed(MARKER)  # his replacement settles
    clock["now"] += 5.0
    _answered(store, 2, session, clock)
    assert deliveries[0].cuts == [
        ("superseded by the owner's next confirmed turn before any of it was heard", set())
    ], "set aside, and recorded as never heard"
    got = rows(store, "select role::text, content from messages order by sequence")
    assert [r[0] for r in got] == ["user", "val", "user", "val"], "nothing is withdrawn"
    assert got[3][1].startswith("The venue")
    session.close()


def test_a_finished_unheard_answer_plays_after_a_continuation(store: Engine) -> None:
    adapter = SlowStreamingAdapter(
        [ok("The garden, my lord, is in bloom."), ok("The orchard, my lord, is beyond.")],
        delay=0.0,
    )
    session, deliveries, clock = _session(
        store,
        adapter,
        [
            [started(1), final(1, "Tell me about the garden.")],
            [started(2)],
            [final(2, "And after that, tell me about the orchard.")],
        ],
    )
    session.start()
    session.feed(MARKER)
    clock["now"] += 5.0
    _answered(store, 1, session, clock)
    deliveries[0].sink.waiting = 3  # as DesktopSink reports it: three offers uncollected
    session.feed(MARKER)
    assert session.speech_hold
    session.feed(MARKER)
    clock["now"] += 5.0
    _answered(store, 2, session, clock)
    assert deliveries[0].cuts == [], "a continuation keeps the finished answer"
    # 28 September 2026 (L2): kept, then dropped unheard when the next turn began.
    assert session.speech_handover is deliveries[0], "the kept answer is offered first"
    deliveries[0].sink.waiting = 0  # the desktop has collected it
    assert session.speech_handover is deliveries[1], "then the new answer follows"
    session.close()


def _continuation_chain(store: Engine, fragments: list[str], *, combine: bool) -> tuple:
    answers = [ok(" ".join(["garden"] * 80))] + [
        ok(f"Answer {index}, my lord.") for index in range(1, len(fragments) + 1)
    ]
    adapter = SlowStreamingAdapter(answers, delay=0.03)
    batches: list = [[started(1), final(1, "Tell me about the garden.")]]
    for index, words in enumerate(fragments, start=2):
        batches.append([started(index), final(index, words)])
    session, deliveries, clock = _session(store, adapter, batches, combine=combine)
    session.start()
    session.feed(MARKER)
    clock["now"] += 5.0
    session.advance()  # the first answer is being made, nothing heard
    for _ in fragments:
        time.sleep(0.2)
        session.feed(MARKER)  # a continuation settles while an answer is being made
        clock["now"] += 5.0
        session.advance()
    return session, deliveries, clock, adapter


def test_a_continuation_of_an_unheard_answer_is_answered_together_with_it(
    store: Engine,
) -> None:
    session, _, clock, adapter = _continuation_chain(
        store, ["And after that, tell me about the orchard."], combine=True
    )
    _answered(store, 1, session, clock)
    got = rows(
        store,
        "select m.role::text, mc.content, mc.state::text from messages m "
        "join messages_current mc on mc.id = m.id order by m.sequence",
    )
    assert [(r[0], r[2]) for r in got] == [
        ("user", "current"),
        ("user", "current"),
        ("val", "current"),
    ], "both of his messages stay canonical; one answer follows them"
    assert adapter.released == [True], "the answer to the first half was set aside unheard"
    last = adapter.sent[-1]
    said = " ".join(str(message) for message in last.messages)
    assert "Tell me about the garden." in said and "tell me about the orchard." in said, (
        "the combined answer was asked with both requests in view"
    )
    session.close()


def test_without_the_switch_a_continuation_still_waits(store: Engine) -> None:
    session, _, clock, adapter = _continuation_chain(
        store, ["And after that, tell me about the orchard."], combine=False
    )
    _answered(store, 2, session, clock)
    assert adapter.released == []
    session.close()


def test_continuations_restart_her_at_most_twice_in_a_row(store: Engine) -> None:
    fragments = [
        "And after that, tell me about the orchard.",
        "And also the stables.",
        "And then the kitchens.",
    ]
    assert MAX_COMBINED_RESTARTS == 2
    session, _, clock, adapter = _continuation_chain(store, fragments, combine=True)
    _answered(store, 2, session, clock)
    assert len(adapter.released) <= MAX_COMBINED_RESTARTS, "no unbounded restart loop"
    session.close()


def test_the_record_says_what_was_heard_of_a_finished_answer_cut_short(store: Engine) -> None:
    """The real delivery: `completed` stays as it was; one `interrupted` row follows it."""
    from test_speech_delivery import ANSWER, ScriptedVoice, _a_val_message, a_delivery, deliver

    from val_gateway.delivery import short_deliveries

    conversation = a_conversation(store)
    message_id = _a_val_message(store, conversation, ANSWER)
    delivery = a_delivery(store, ScriptedVoice())
    deliver(delivery, ANSWER)
    delivery.bind(message_id)
    assert delivery.state.value == "completed"
    ordered = sorted(delivery.spoken, key=lambda segment: segment.index)
    assert len(ordered) >= 3
    first, second = ordered[0], ordered[1]

    interval = delivery.request_stop("the owner began speaking while her answer was still playing")
    assert interval is not None
    assert delivery.stop_requested is not None
    assert [
        r[0]
        for r in rows(
            store,
            "select state from speech_deliveries where message_id = :m order by event",
            m=message_id,
        )
    ][-1] == "completed", "a stop request alone records nothing"
    assert delivery.playback_cut_reported(second.index), "the desktop's word is recorded"
    assert not delivery.playback_cut_reported(first.index), "recorded once; never less heard"
    got = rows(
        store,
        "select event, state, delivered_prefix, segments_delivered, segments_total, reason "
        "from speech_deliveries where message_id = :m order by event",
        m=message_id,
    )
    states = [row[1] for row in got]
    assert states[-2:] == ["completed", "interrupted"], "history kept; the correction appended"
    last = got[-1]
    assert last[2] == f"{first.text} {second.text}", "exactly the segments that had begun"
    assert last[3] == 2 and last[4] == len(ordered)
    assert f"segment {second.index} was cut off while playing" in last[5]
    assert "no playback-start report" in last[5]
    (short,) = short_deliveries(store, conversation)
    assert short.state == "interrupted", "later context knows he did not hear it all"
    # 2 October 2026: the segments that had begun bound what he may have heard; the one
    # cut off is not handed on as heard text.
    assert short.possibly_heard_characters == len(last[2]) < short.total_characters
    assert short.delivered_characters < short.possibly_heard_characters
    assert delivery.sink.stopped_because is not None, "nothing more is handed over"


def test_a_delayed_report_that_more_was_heard_appends_the_larger_truth(store: Engine) -> None:
    """Superseded as unheard; the desktop's late report says segment 1 had played."""
    from test_speech_delivery import ANSWER, ScriptedVoice, _a_val_message, a_delivery, deliver

    conversation = a_conversation(store)
    message_id = _a_val_message(store, conversation, ANSWER)
    delivery = a_delivery(store, ScriptedVoice())
    deliver(delivery, ANSWER)
    delivery.bind(message_id)
    first = min(delivery.spoken, key=lambda segment: segment.index)
    assert delivery.cut_playback("superseded before any of it was heard", set()) is not None
    assert delivery.playback_cut_reported(first.index)
    got = rows(
        store,
        "select state, delivered_prefix, segments_delivered from speech_deliveries "
        "where message_id = :m order by event",
        m=message_id,
    )
    assert [row[0] for row in got][-3:] == ["completed", "interrupted", "interrupted"]
    assert got[-2][2] == 0 and got[-1][1] == first.text and got[-1][2] == 1, "appended, not edited"
