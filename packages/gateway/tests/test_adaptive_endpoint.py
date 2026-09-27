"""The adaptive endpoint through the session — owner order of 27 September 2026, §3.

Plainly finished words are submitted after a short window; ambiguous words wait as long
as the fixed path does; and speech that resumes inside the fixed path's silence bound
after an early submission cancels the early turn and joins the two halves into one turn —
never a half-question answered, never a duplicate, never an abandoned request.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

import time
from uuid import UUID

from sqlalchemy import Engine, text
from test_deliberation_machinery import ScriptedAdapter, build_gateway, clean_personas, ok, store
from test_owner_precedence import SlowStreamingAdapter, UnheardDelivery
from test_voice_input import MARKER, ScriptedRecognizer, a_conversation, final, started
from test_voice_presentation import HeldVoice

from val_gateway.deliberate import send
from val_gateway.projects import load_catalogue
from val_gateway.seal import SealRoute
from val_gateway.voice import VoiceSession
from val_policy.turn_completion import COMPLETE_GRACE_S, UNCERTAIN_GRACE_S


def rows(store: Engine, query: str) -> list[tuple]:
    with store.connect() as connection:
        return [tuple(r) for r in connection.execute(text(query)).all()]


def _session(store: Engine, adapter: ScriptedAdapter, batches: list) -> VoiceSession:
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
        )

    def unheard() -> HeldVoice:
        held = UnheardDelivery()
        held.audible = False
        return held

    clock = {"now": 1000.0}
    session = VoiceSession(
        store,
        ScriptedRecognizer(batches=batches),
        submit=submit,  # type: ignore[arg-type]
        conversation_id=a_conversation(store),
        clock=lambda: clock["now"],
        speech=unheard,  # type: ignore[arg-type]
        adaptive_endpoint=True,
    )
    session._clock_box = clock  # type: ignore[attr-defined]
    return session


def test_finished_words_go_after_the_short_window(store: Engine) -> None:
    adapter = ScriptedAdapter([ok("Good evening, my lord.")])
    session = _session(store, adapter, [[started(1), final(1, "Good evening, Val.")]])
    clock = session._clock_box  # type: ignore[attr-defined]
    session.start()
    session.feed(MARKER)
    clock["now"] += COMPLETE_GRACE_S + 0.01
    session.advance()
    assert session._inflight is not None or rows(store, "select count(*) from messages")[0][0]
    session.await_turn(timeout=10)
    assert [r[0] for r in rows(store, "select role::text from messages order by sequence")] == [
        "user",
        "val",
    ]
    session.close()


def test_ambiguous_words_wait_as_long_as_today(store: Engine) -> None:
    adapter = ScriptedAdapter([ok("My lord?")])
    session = _session(store, adapter, [[started(1), final(1, "The venue.")]])
    clock = session._clock_box  # type: ignore[attr-defined]
    session.start()
    session.feed(MARKER)
    clock["now"] += COMPLETE_GRACE_S + 0.01
    session.advance()
    assert session._inflight is None and session._pending is not None, "not yet"
    clock["now"] += UNCERTAIN_GRACE_S
    session.advance()
    session.await_turn(timeout=10)
    assert rows(store, "select count(*) from messages where role = 'val'")[0][0] == 1
    session.close()


def test_a_resumption_after_an_early_submission_joins_the_halves(store: Engine) -> None:
    adapter = SlowStreamingAdapter(
        [
            ok(" ".join(["invitation"] * 60)),
            ok("The invitation and the venue, my lord: both are in hand."),
        ],
        delay=0.05,
    )
    session = _session(
        store,
        adapter,
        [
            [
                started(1, at=10.0),
                final(1, "Tell me about the invitation.", at=11.6, endpoint_at=11.5),
            ],
            [started(2, at=12.2)],
            [final(2, "And the venue as well.", at=13.4, endpoint_at=13.3)],
        ],
    )
    clock = session._clock_box  # type: ignore[attr-defined]
    session.start()
    session.feed(MARKER)
    clock["now"] += COMPLETE_GRACE_S + 0.01
    session.advance()  # submitted early: plainly finished words
    time.sleep(0.3)
    session.feed(MARKER)  # he resumes 0.7 s after the endpoint: inside the bound
    assert session.speech_hold, "nothing of the early answer is handed over while he speaks"
    session.feed(MARKER)  # the rest settles
    for _ in range(80):
        session.advance()
        clock["now"] += 0.5
        if rows(store, "select count(*) from messages where role = 'val'")[0][0] >= 1:
            break
        time.sleep(0.05)
    session.await_turn(timeout=15)
    got = rows(
        store,
        "select m.role::text, mc.content, m.id in (select message_id from message_revisions "
        "where kind::text = 'retraction') from messages m join messages_current mc on mc.id = m.id "
        "order by m.sequence",
    )
    assert [(r[0], r[2]) for r in got] == [("user", True), ("user", False), ("val", False)], got
    assert got[1][1] == "Tell me about the invitation. And the venue as well."
    assert got[2][1].startswith("The invitation and the venue")
    assert adapter.released == [True], "the early call was cancelled, once"
    session.close()


def test_speech_resuming_after_the_bound_is_its_own_turn(store: Engine) -> None:
    adapter = SlowStreamingAdapter(
        [ok(" ".join(["invitation"] * 20)), ok("The venue, my lord.")], delay=0.02
    )
    session = _session(
        store,
        adapter,
        [
            [
                started(1, at=10.0),
                final(1, "Tell me about the invitation.", at=11.6, endpoint_at=11.5),
            ],
            [started(2, at=14.0)],
            [final(2, "What about the venue?", at=15.2, endpoint_at=15.1)],
        ],
    )
    clock = session._clock_box  # type: ignore[attr-defined]
    session.start()
    session.feed(MARKER)
    clock["now"] += COMPLETE_GRACE_S + 0.01
    session.advance()
    time.sleep(0.1)
    session.feed(MARKER)
    session.feed(MARKER)
    for _ in range(120):
        session.advance()
        clock["now"] += 0.5
        if rows(store, "select count(*) from messages where role = 'val'")[0][0] >= 2:
            break
        time.sleep(0.05)
    session.await_turn(timeout=15)
    got = rows(store, "select role::text from messages order by sequence")
    assert [r[0] for r in got] == ["user", "val", "user", "val"], got
    assert adapter.released == []
    session.close()


# --- §4 of the remaining latency work, 27 September 2026: the merge window under the
# faster path. An early-submitted answer can be ready before he resumes; its audio is
# held until the window closes, so resumption inside it always finds private work that
# can be discarded, never audio he has begun to hear. After the window his words are an
# independent turn, and audio that has begun is barge-in's ground: nothing already
# audible is relabelled unheard.


def _captured(session: VoiceSession) -> list[UnheardDelivery]:
    made: list[UnheardDelivery] = []
    original = session._speech

    def make() -> UnheardDelivery:
        delivery = original()  # type: ignore[misc]
        made.append(delivery)
        return delivery

    session._speech = make  # type: ignore[assignment]
    return made


def _until_answers(store: Engine, session: VoiceSession, count: int, clock: dict) -> None:
    for _ in range(120):
        session.advance()
        if rows(store, "select count(*) from messages where role = 'val'")[0][0] >= count:
            return
        time.sleep(0.05)
    raise AssertionError("the answer never arrived")


def test_an_answer_ready_before_he_resumes_is_held_until_the_window_closes(
    store: Engine,
) -> None:
    adapter = ScriptedAdapter([ok("It is in hand, my lord.")])
    session = _session(
        store,
        adapter,
        [
            [
                started(1, at=10.0),
                final(1, "Tell me about the invitation.", at=11.6, endpoint_at=11.5),
            ]
        ],
    )
    made = _captured(session)
    clock = session._clock_box  # type: ignore[attr-defined]
    session.start()
    session.feed(MARKER)
    clock["now"] += COMPLETE_GRACE_S + 0.01
    session.advance()  # submitted early
    _until_answers(store, session, 1, clock)
    session.await_turn(timeout=10)
    assert made, "a delivery was made for the early answer"
    # Her short answer is written and waiting; the window is still open.
    assert session.speech_hold, "not a sound of it before the merge window closes"
    until = session._merge_hold[0]  # type: ignore[index]
    clock["now"] = until - 0.01
    assert session.speech_hold
    clock["now"] = until + 0.01
    assert not session.speech_hold, "released the moment the window has closed"
    session.close()


def test_a_correction_near_the_end_of_the_window_withdraws_a_finished_unheard_answer(
    store: Engine,
) -> None:
    adapter = ScriptedAdapter(
        [ok("The Hound of the Baskervilles, my lord."), ok("The Turn of the Screw, my lord.")]
    )
    session = _session(
        store,
        adapter,
        [
            [
                started(1, at=10.0),
                final(1, "Name a famous mystery novel.", at=11.6, endpoint_at=11.5),
            ],
            # 1.3 s after the endpoint: inside the 1.37 s window, near its end.
            [started(2, at=12.8)],
            [final(2, "No, a famous ghost story.", at=14.1, endpoint_at=14.0)],
        ],
    )
    clock = session._clock_box  # type: ignore[attr-defined]
    session.start()
    session.feed(MARKER)
    clock["now"] += COMPLETE_GRACE_S + 0.01
    session.advance()
    _until_answers(store, session, 1, clock)
    session.await_turn(timeout=10)
    assert session.speech_hold, "the finished answer is still private"
    session.feed(MARKER)  # he resumes
    session.feed(MARKER)  # and settles
    clock["now"] += 2.0
    _until_answers(store, session, 2, clock)
    session.await_turn(timeout=10)
    got = rows(
        store,
        "select m.role::text, mc.content, m.id in (select message_id from message_revisions "
        "where kind::text = 'retraction') from messages m join messages_current mc on mc.id = m.id "
        "order by m.sequence",
    )
    # The fragment and the unheard answer to it are withdrawn, not deleted; the joined
    # request keeps his correction's meaning and gets its own answer.
    assert [(r[0], r[2]) for r in got][-2:] == [("user", False), ("val", False)], got
    assert got[-2][1] == "Name a famous mystery novel. No, a famous ghost story."
    assert got[-1][1] == "The Turn of the Screw, my lord."
    assert any(r[1] == "Name a famous mystery novel." and r[2] for r in got), got
    session.close()


def test_audio_that_has_begun_after_the_window_is_not_relabelled_unheard(
    store: Engine,
) -> None:
    adapter = ScriptedAdapter([ok("The Hound of the Baskervilles, my lord."), ok("Very well.")])
    session = _session(
        store,
        adapter,
        [
            [
                started(1, at=10.0),
                final(1, "Name a famous mystery novel.", at=11.6, endpoint_at=11.5),
            ],
            # 3.0 s after the endpoint: past the window; her answer has begun to play.
            [started(2, at=14.5)],
            [final(2, "No, a famous ghost story.", at=15.8, endpoint_at=15.7)],
        ],
    )
    made = _captured(session)
    clock = session._clock_box  # type: ignore[attr-defined]
    session.start()
    session.feed(MARKER)
    clock["now"] += COMPLETE_GRACE_S + 0.01
    session.advance()
    _until_answers(store, session, 1, clock)
    session.await_turn(timeout=10)
    clock["now"] = session._merge_hold[0] + 0.5  # type: ignore[index]
    assert not session.speech_hold
    session.speech_handed_over(3.0, current=True)  # the desktop took it and it is playing
    session.playback_reported("playback_started", segment=(str(made[0].message_id), 1))
    session.feed(MARKER)  # he speaks over her
    session.feed(MARKER)
    clock["now"] += 2.0
    _until_answers(store, session, 2, clock)
    session.await_turn(timeout=10)
    got = rows(
        store,
        "select m.role::text, m.id in (select message_id from message_revisions "
        "where kind::text = 'retraction') from messages m order by m.sequence",
    )
    # Both of his requests stand, and so does the answer he had begun to hear.
    assert got == [("user", False), ("val", False), ("user", False), ("val", False)], got
    # Recorded, not asserted: once an answer's synthesis has finished, the session holds
    # no active delivery, so his onset does not stop what the desktop is still playing
    # (a pre-existing gap in barge-in, found by this test; LATENCY_CANDIDATE.md §7c).
    session.close()
