"""Stage progress on the streamed turn — ruling, 13 September 2026.

Backend-confirmed, content-free presentation state, sent only when the request
asks for `progress`. Proved here: an ordinary turn reports understanding and
then preparing a response; a consequential turn with an enforced blind position
also reports forming an independent view, at that moment and in order; a
consequential turn whose strip finds nothing to separate never claims to form
one; stage events carry no label, preference, position or text; nothing is
stored; a clarification reports nothing; without the flag the stream is exactly
what it was; and the settled timing states when the response call began, on the
whole-request origin. No provider is contacted.
"""

from __future__ import annotations

import json

from sqlalchemy import Engine, text
from test_service import MIXED, classifier_says, client, deliberated_script, ok
from test_turn_stream import StreamingScriptedAdapter, events_of

STAGE_VALUES = {"understanding", "forming_view", "preparing_response"}


def _stages(events: list[tuple[str, dict]]) -> list[str]:
    return [data["stage"] for kind, data in events if kind == "stage"]


def _inseparable() -> object:
    return ok(
        json.dumps(
            {
                "preference_present": True,
                "attributed_prior_present": False,
                "separable": False,
                "question": "",
                "removed": [],
                "record_evidence": [],
            }
        )
    )


def test_an_ordinary_turn_reports_understanding_then_preparing(store: Engine) -> None:
    api = client(
        store, StreamingScriptedAdapter([classifier_says("not_consequential"), ok("Yes, my lord.")])
    )
    events = events_of(api, {"content": "Ready?", "no_project": True, "progress": True})
    kinds = [kind for kind, _ in events]
    assert kinds == ["stage", "stage", "delta", "settled"], kinds
    assert _stages(events) == ["understanding", "preparing_response"]
    for kind, data in events:
        if kind == "stage":
            assert set(data) == {"stage", "api_ms"} and data["stage"] in STAGE_VALUES
    timing = events[-1][1]["timing"]
    assert timing["api_response_started_ms"] is not None
    assert (
        timing["api_response_started_ms"] <= timing["api_first_delta_ms"] <= timing["api_total_ms"]
    )


def test_an_enforced_consequential_turn_reports_forming_a_view_in_order(store: Engine) -> None:
    api = client(store, StreamingScriptedAdapter(deliberated_script()))
    events = events_of(api, {"content": MIXED, "project": "Project Alpha", "progress": True})
    assert events[-1][1]["glimpse"]["blind"]["ordering"] == "enforced"
    assert _stages(events) == ["understanding", "forming_view", "preparing_response"]
    first_delta = next(i for i, (kind, _) in enumerate(events) if kind == "delta")
    last_stage = max(i for i, (kind, _) in enumerate(events) if kind == "stage")
    assert last_stage < first_delta, "every stage precedes Val's first words"
    api_ms = [data["api_ms"] for kind, data in events if kind == "stage"]
    assert api_ms == sorted(api_ms)
    raw = json.dumps([data for kind, data in events if kind == "stage"])
    for forbidden in ("consequential", "wide shot", "close-up", "preference", "position"):
        assert forbidden not in raw, forbidden


def test_no_view_is_claimed_when_no_blind_position_is_formed(store: Engine) -> None:
    api = client(
        store,
        StreamingScriptedAdapter(
            [classifier_says("consequential"), _inseparable(), ok("One sequence, my lord.")]
        ),
    )
    events = events_of(api, {"content": MIXED, "project": "Project Alpha", "progress": True})
    assert events[-1][1]["glimpse"]["blind"] is None
    assert _stages(events) == ["understanding", "preparing_response"]


def test_without_the_flag_the_stream_is_unchanged_and_nothing_is_stored(store: Engine) -> None:
    api = client(
        store, StreamingScriptedAdapter([classifier_says("not_consequential"), ok("Yes.")])
    )
    events = events_of(api, {"content": "Ready?", "no_project": True})
    assert [kind for kind, _ in events] == ["delta", "settled"]
    with store.connect() as connection:
        contents = [row[0] for row in connection.execute(text("select content from messages"))]
    assert contents == ["Ready?", "Yes."], "no stage became a message"


def test_a_clarification_reports_no_stage(store: Engine) -> None:
    api = client(store, StreamingScriptedAdapter([]))
    events = events_of(api, {"content": "Continue.", "project": "Project Gamma", "progress": True})
    assert [kind for kind, _ in events] == ["settled"]
    assert events[0][1]["kind"] == "clarification"
