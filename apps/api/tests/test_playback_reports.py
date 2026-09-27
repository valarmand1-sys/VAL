"""Playback reports that arrive together, or twice — remaining latency work, 27 September 2026.

The desktop holds the reports for a segment voiced before her answer was written and
releases them together once the answer is known, so `playback_started` and
`playback_completed` for one segment reached the service at the same moment. Both
inserts computed the same next event number, the unique constraint refused one, the
endpoint answered 500 and a record of what the speakers did was lost — in every bench
run, baseline and candidate. Writers for one (answer, segment) are now serialised, and a
transition already on record is not written again.
"""

from __future__ import annotations

import threading
import time
from uuid import UUID

from sqlalchemy import Engine, text
from test_service import ScriptedAdapter, ok
from test_voice_service import (
    PCM,
    ScriptedRecognizer,
    ScriptedVoiceProvider,
    _poll_until_answered,
    final,
    speaking_client,
    started,
)

from val_gateway.playback import PlaybackState, record_playback


def _answer_with_one_handed_over_segment(reachable, session: str) -> tuple[str, dict]:  # noqa: ANN001
    reachable.post(
        f"/voice/sessions/{session}/audio",
        content=PCM,
        headers={"content-type": "application/octet-stream"},
    )
    view = _poll_until_answered(reachable, session)
    (turn,) = view["turns"]
    message_id = turn["answer"]["val_message"]["id"]
    segment = None
    for _ in range(40):
        offer = reachable.get(f"/voice/sessions/{session}/speech/next").json()
        if offer["segment"] is not None:
            segment = offer["segment"]
            break
        time.sleep(0.05)
    assert segment is not None
    return message_id, segment


def _rows(engine: Engine, message_id: str) -> list[tuple[int, int, str, str]]:
    with engine.connect() as connection:
        return [
            (row.segment_index, row.event, row.state, str(row.message_id))
            for row in connection.execute(
                text(
                    "select segment_index, event, state, message_id from speech_playbacks "
                    " where message_id = :id order by segment_index, event"
                ),
                {"id": message_id},
            )
        ]


def test_held_reports_released_together_and_delivered_twice_are_each_recorded_once(
    store: Engine,
) -> None:
    recognizer = ScriptedRecognizer(batches=[[started(), final("What time is dinner?")]])
    adapter = ScriptedAdapter([ok("Eight, my lord.")])
    with speaking_client(store, adapter, recognizer, ScriptedVoiceProvider()) as reachable:
        session = reachable.post("/voice/sessions", json={"project": "Project Alpha"}).json()[
            "session"
        ]
        message_id, segment = _answer_with_one_handed_over_segment(reachable, session)
        index = segment["segment_index"]
        # The held pair, released together — and each delivered three times, as a
        # desktop that retried or double-flushed would.
        reports = [
            {
                "message_id": message_id,
                "segment_index": index,
                "state": state,
                "observed_ms_ago": 400 if state == "playback_started" else 10,
            }
            for state in ("playback_started", "playback_completed")
            for _ in range(3)
        ]
        gate = threading.Barrier(len(reports))
        statuses: list[int] = []

        def send(body: dict) -> None:
            gate.wait()
            response = reachable.post(f"/voice/sessions/{session}/speech/played", json=body)
            statuses.append(response.status_code)

        threads = [threading.Thread(target=send, args=(body,)) for body in reports]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert statuses == [200] * len(reports), "no report refused, none lost"
    rows = _rows(store, message_id)
    states = [row[2] for row in rows]
    assert sorted(states) == sorted(
        ["available_to_desktop", "playback_started", "playback_completed"]
    ), "each transition exactly once, the repeats recorded as nothing new"
    assert {row[0] for row in rows} == {index}, "every event on the segment it describes"
    assert {row[3] for row in rows} == {message_id}, "and on the answer it describes"
    assert [row[1] for row in rows] == [1, 2, 3], "event numbers unbroken and unique"
    # When each happened is carried by the time observed, not by the order recorded.
    with store.connect() as connection:
        when = dict(
            connection.execute(
                text("select state, recorded_at from speech_playbacks where message_id = :id"),
                {"id": message_id},
            ).all()
        )
    assert when["playback_started"] < when["playback_completed"]


def test_concurrent_writers_for_one_segment_never_collide(store: Engine) -> None:
    """The writer itself, without the HTTP layer: eight threads released at once."""
    recognizer = ScriptedRecognizer(batches=[[started(), final("What time is dinner?")]])
    adapter = ScriptedAdapter([ok("Eight, my lord.")])
    with speaking_client(store, adapter, recognizer, ScriptedVoiceProvider()) as reachable:
        session = reachable.post("/voice/sessions", json={"project": "Project Alpha"}).json()[
            "session"
        ]
        message_id, segment = _answer_with_one_handed_over_segment(reachable, session)
    answer = UUID(message_id)
    index = segment["segment_index"]
    plan = [PlaybackState.PLAYBACK_STARTED, PlaybackState.PLAYBACK_COMPLETED] * 4
    gate = threading.Barrier(len(plan))
    events: list[tuple[str, int]] = []
    failures: list[BaseException] = []

    def write(state: PlaybackState) -> None:
        gate.wait()
        try:
            events.append(
                (
                    state.value,
                    record_playback(
                        store,
                        message_id=answer,
                        segment_index=index,
                        state=state,
                        spoken_text=segment["text"],
                    ),
                )
            )
        except BaseException as failure:
            failures.append(failure)

    threads = [threading.Thread(target=write, args=(state,)) for state in plan]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    by_state: dict[str, set[int]] = {}
    for state, event in events:
        by_state.setdefault(state, set()).add(event)
    assert all(len(numbers) == 1 for numbers in by_state.values()), (
        "every writer of one transition is told the same, single event"
    )
    assert [row[2] for row in _rows(store, message_id)].count("playback_started") == 1
    assert [row[2] for row in _rows(store, message_id)].count("playback_completed") == 1
