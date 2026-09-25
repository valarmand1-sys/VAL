# ruff: noqa: F811, F401 - fixtures and harness imported by name
"""What his Step B run found — owner acceptance, 25 September 2026.

He spoke one sentence, waited about thirty seconds, and spoke again. Four canonical
messages and four answers came out of two intended utterances, one of them containing
a word he never said, and one containing his own words in the wrong order with a
stale fragment in front of them.

These tests are the shapes of those failures, so they cannot come back:

**A.** One utterance and then silence settles on its own. Nothing about a spoken turn
may wait for him to speak again.

**B.** The resume window expires on the clock. A later utterance after it is a new
turn, whatever state the previous answer is in.

**C.** No stale fragment contaminates a later, deliberate attempt — the defect that
put thirty-five seconds between two halves of one message.

**D.** A legitimate merge preserves chronology.
"""

from __future__ import annotations

import time
from uuid import UUID

from sqlalchemy import Engine, text
from test_deliberation_machinery import ScriptedAdapter, clean_personas, ok, store
from test_voice_input import (
    MARKER,
    Clock,
    ScriptedRecognizer,
    a_conversation,
    a_session,
    final,
    settle,
    started,
)

from val_gateway.voice import RESUME_GRACE_SECONDS


def test_a_one_utterance_then_silence_settles_without_further_speech(store: Engine) -> None:
    """**A.** His words were in the store 1.1 s after he stopped; only the interface waited.

    The session is advanced the way the desktop's poll advances it — `snapshot`, which
    is what `GET /voice/sessions/{id}` calls — and **no further audio and no control
    action are supplied**. The turn must settle anyway.
    """
    recognizer = ScriptedRecognizer(
        batches=[[started(1), final(1, "Good evening, Val. I'm testing your voice system now.")]]
    )
    conversation = a_conversation(store)
    adapter = ScriptedAdapter([ok("Good evening, my lord.")])
    session, _, clock = a_session(store, recognizer, adapter=adapter, conversation_id=conversation)

    session.feed(MARKER)  # the one and only audio he supplies
    assert session.snapshot().turns == (), "nothing is submitted inside the resume window"

    # Time passes. He says nothing more and presses nothing. The desktop polls, which
    # is the only thing that advances the session — and that is enough.
    clock.tick(RESUME_GRACE_SECONDS + 0.1)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and not session.snapshot().turns:
        time.sleep(0.02)
    (turn,) = session.snapshot().turns
    assert turn.utterance.text == "Good evening, Val. I'm testing your voice system now."
    assert turn.message_id is not None, "the canonical message exists without a second utterance"

    with store.connect() as connection:
        said = (
            connection.execute(
                text("select content from messages where conversation_id = :c order by sequence"),
                {"c": conversation},
            )
            .scalars()
            .all()
        )
    assert said[0] == "Good evening, Val. I'm testing your voice system now."


def test_b_the_resume_window_expires_on_the_clock(store: Engine) -> None:
    """**B.** Utterance A, a long silence, utterance B: two turns, never one."""
    # The recognizer's own marks, as the real one reports them: the first utterance
    # ends at 10.0 and he begins again at 40.0 — a thirty-second pause.
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1, at=5.0), final(1, "I'm testing your system.", at=10.0, endpoint_at=10.0)],
            [started(2, at=40.0), final(2, "Good evening Val.", at=42.0, endpoint_at=42.0)],
        ]
    )
    conversation = a_conversation(store)
    adapter = ScriptedAdapter([ok("Very good, my lord."), ok("Good evening, my lord.")])
    session, _, clock = a_session(store, recognizer, adapter=adapter, conversation_id=conversation)

    session.feed(MARKER)
    settle(session, clock)
    (first,) = session.snapshot().turns

    # **Thirty seconds of silence**, exactly the gap in his run.
    clock.tick(30.0)
    session.feed(MARKER)
    settle(session, clock)

    turns = session.snapshot().turns
    assert len(turns) == 2, "a deliberate retry after the window is its own turn"
    second = next(turn for turn in turns if turn.message_id != first.message_id)
    assert second.utterance.text == "Good evening Val.", "and carries only its own words"
    assert first.superseded_by is None, "the earlier turn is not superseded by it"
    assert first.revised_to is None, "and is not rewritten by it"


def test_c_a_stale_fragment_cannot_contaminate_a_later_attempt(store: Engine) -> None:
    """**C.** The exact defect: an answer he never heard kept its turn mergeable for ever.

    His fragment's answer was interrupted at zero characters, so `delivered` stayed
    false — and thirty-five seconds later a fresh attempt was appended to it, putting
    the stale half first. The bound is the configured resume window, measured from the
    previous utterance's endpoint to the next one's first voiced frame.
    """
    recognizer = ScriptedRecognizer(
        batches=[
            [
                started(1, at=5.0),
                final(
                    1,
                    "Now please tell me exactly what you heard me say.",
                    at=10.0,
                    endpoint_at=10.0,
                ),
            ],
            [
                started(2, at=45.0),
                final(2, "Good evening Val. I'm testing your system.", at=48.0, endpoint_at=48.0),
            ],
        ]
    )
    conversation = a_conversation(store)
    adapter = ScriptedAdapter(
        [ok("I do not have that in the record."), ok("Good evening, my lord.")]
    )
    session, _, clock = a_session(store, recognizer, adapter=adapter, conversation_id=conversation)

    session.feed(MARKER)
    settle(session, clock)
    (first,) = session.snapshot().turns
    # His answer was never heard — exactly the state that made the old turn eligible
    # for ever. `delivered` is false and stays false.
    assert first.delivered is False

    clock.tick(30.0)
    session.feed(MARKER)
    settle(session, clock)

    turns = session.snapshot().turns
    assert len(turns) == 2
    second = next(turn for turn in turns if turn.message_id != first.message_id)
    assert second.utterance.text == "Good evening Val. I'm testing your system."
    assert "Now please tell me exactly" not in second.utterance.text, (
        "the stale fragment was prepended to a later attempt — the Step B defect"
    )
    assert first.superseded_by is None

    with store.connect() as connection:
        said = (
            connection.execute(
                text(
                    "select content from messages where conversation_id = :c and role = 'user' "
                    " order by sequence"
                ),
                {"c": conversation},
            )
            .scalars()
            .all()
        )
    assert said == [
        "Now please tell me exactly what you heard me say.",
        "Good evening Val. I'm testing your system.",
    ], "two messages, each holding exactly what was said into it"


def test_d_a_legitimate_merge_still_joins_in_speech_order(store: Engine) -> None:
    """**D.** Inside the window, the halves join — and the earlier half comes first."""
    # He resumes 0.4 s after the endpoint — inside the configured window, which is
    # exactly the case the resume mechanism exists for.
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1, at=5.0), final(1, "Ask the cook about dinner", at=10.0, endpoint_at=10.0)],
            [
                started(2, at=10.4),
                final(2, "and tell her the guests are late.", at=12.0, endpoint_at=12.0),
            ],
        ]
    )
    conversation = a_conversation(store)
    adapter = ScriptedAdapter([ok("At once, my lord."), ok("I will tell her, my lord.")])
    session, _, clock = a_session(store, recognizer, adapter=adapter, conversation_id=conversation)

    session.feed(MARKER)
    settle(session, clock)
    (first,) = session.snapshot().turns

    # He resumes immediately — inside the window, which is what it is for.
    session.feed(MARKER)
    settle(session, clock)

    turns = session.snapshot().turns
    superseded = next(turn for turn in turns if turn.message_id == first.message_id)
    combined = "Ask the cook about dinner and tell her the guests are late."
    assert superseded.superseded_by == combined, "joined, in the order he spoke them"
    fresh = next(turn for turn in turns if turn.message_id != first.message_id)
    assert fresh.utterance.text == combined
    assert fresh.utterance.text.index("Ask the cook") < fresh.utterance.text.index("tell her")


def test_the_replacement_turn_keeps_its_voice_origin_and_its_seal(store: Engine) -> None:
    """§8: a resubmitted Voice turn is still a Voice turn, and still local-only."""
    recognizer = ScriptedRecognizer(
        batches=[
            [started(1, at=5.0), final(1, "Ask the cook about dinner", at=10.0, endpoint_at=10.0)],
            [
                started(2, at=10.4),
                final(2, "and tell her the guests are late.", at=12.0, endpoint_at=12.0),
            ],
        ]
    )
    conversation = a_conversation(store)
    adapter = ScriptedAdapter([ok("At once, my lord."), ok("I will tell her, my lord.")])
    session, _, clock = a_session(store, recognizer, adapter=adapter, conversation_id=conversation)

    session.feed(MARKER)
    settle(session, clock)
    (first,) = session.snapshot().turns
    session.feed(MARKER)
    settle(session, clock)

    fresh = next(turn for turn in session.snapshot().turns if turn.message_id != first.message_id)
    with store.connect() as connection:
        provenance = connection.execute(
            text(
                "select input_mode, transcription_status from voice_message_provenance "
                " where message_id = :id"
            ),
            {"id": fresh.message_id},
        ).one()
        sealed = connection.execute(
            text("select applied_by from conversation_egress_seals where conversation_id = :c"),
            {"c": conversation},
        ).scalar_one()
        not_run = connection.execute(
            text("select not_run_reason from classifications where message_id = :id"),
            {"id": fresh.message_id},
        ).scalar_one()
    assert (provenance.input_mode, provenance.transcription_status) == ("voice", "final")
    assert sealed in ("utterance_finalized", "resume_merge")
    assert not_run is not None and "local-only" in not_run
    assert isinstance(fresh.conversation_id, UUID) and fresh.conversation_id == conversation
