"""The streamed turn route — responsiveness phase, 11 September 2026.

`POST /turns/stream` delivers Val's generated text as server-sent events,
every delta having passed through Val Core, and ends with the identical
settled object `POST /turns` returns. Real PostgreSQL, scripted adapters.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from test_service import (
    CLOSE_UP,
    MIXED,
    ScriptedAdapter,
    blind_says,
    classifier_says,
    client,
    ok,
    reconciled,
    strip_separates,
)

from val_domain.gateway import CacheTtl, Message, ModelConfig, TerminalState
from val_domain.provider import ProviderEvent, ProviderResult, TextDelta
from val_policy.deliberation import RECONCILIATION_VERDICT_MARKER


@dataclass
class Streamed:
    deltas: list[str]
    result: ProviderResult | Exception
    terminal_missing: bool = False


@dataclass
class StreamingScriptedAdapter(ScriptedAdapter):
    streamed: list[int] = field(default_factory=list)

    def stream(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> Iterator[ProviderEvent]:
        self.calls += 1
        self.streamed.append(self.calls)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        if isinstance(step, Streamed):
            for delta in step.deltas:
                yield TextDelta(delta)
            if isinstance(step.result, Exception):
                raise step.result
            if not step.terminal_missing:
                yield step.result
            return
        yield TextDelta(step.text)
        yield step


def events_of(api: TestClient, body: dict) -> list[tuple[str, dict]]:
    """Every server-sent event of one streamed turn, parsed."""
    with api.stream("POST", "/turns/stream", json=body) as response:
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = b"".join(response.iter_bytes()).decode()
    parsed: list[tuple[str, dict]] = []
    for frame in raw.split("\n\n"):
        if not frame.strip():
            continue
        lines = frame.split("\n")
        event = next(line[len("event: ") :] for line in lines if line.startswith("event: "))
        data = next(line[len("data: ") :] for line in lines if line.startswith("data: "))
        parsed.append((event, json.loads(data)))
    return parsed


def deltas_of(events: list[tuple[str, dict]]) -> str:
    return "".join(data["text"] for kind, data in events if kind == "delta")


def _model_calls(engine: Engine) -> list[tuple[str, str, object]]:
    with engine.connect() as connection:
        return [
            (row[0], row[1], row[2])
            for row in connection.execute(
                text(
                    "select task_type::text, terminal_state::text, cost from model_calls "
                    "order by created_at"
                )
            ).all()
        ]


def _reservations(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("select state::text, count(*) from budget_reservations group by 1")
        ).all()
    return {state: int(count) for state, count in rows}


# --- the ordinary turn ---------------------------------------------------------


def test_an_ordinary_turn_streams_its_deltas_then_settles_to_the_plain_routes_object(
    store: Engine,
) -> None:
    adapter = StreamingScriptedAdapter(
        [
            classifier_says("not_consequential"),
            Streamed(["Two ", "o'clock, ", "my lord."], ok("Two o'clock, my lord.")),
        ]
    )
    api = client(store, adapter)
    events = events_of(api, {"content": "What time is it?", "no_project": True})

    kinds = [kind for kind, _ in events]
    assert kinds == ["delta", "delta", "delta", "settled"], kinds
    assert deltas_of(events) == "Two o'clock, my lord."
    settled = events[-1][1]
    assert settled["kind"] == "answered"
    assert settled["val_message"]["content"] == deltas_of(events), (
        "the streamed text is the settled, persisted text"
    )
    assert settled["conversation"]["project_id"] is None, "unassigned: the null semantics stand"
    timing = settled["timing"]
    assert (
        timing["api_first_delta_ms"] is not None
        and timing["api_total_ms"] >= timing["api_first_delta_ms"]
    )
    assert timing["gateway_first_output_ms"] is not None
    assert adapter.streamed == [2], "the response streamed; the classifier completed"
    # The persisted record equals the settled event, and the plain route would return the same.
    detail = api.get(f"/conversations/{settled['conversation']['id']}").json()
    assert [m["content"] for m in detail["messages"]] == [
        "What time is it?",
        "Two o'clock, my lord.",
    ]


def test_multibyte_characters_survive_the_frames_and_equal_the_persisted_text(
    store: Engine,
) -> None:
    """Val's dashes and quotes are multi-byte; the frames carry them intact, and
    a client that decodes the byte stream incrementally reassembles exactly the
    persisted text. (A byte-at-a-time client that ignores decoding errors would
    drop them — the defect found in the 11 September 2026 measuring script.)"""
    reply = "Well enough, my lord — steady, and “ready” to work…"
    adapter = StreamingScriptedAdapter(
        [
            classifier_says("not_consequential"),
            Streamed(["Well enough, my lord —", " steady, and “ready” to work…"], ok(reply)),
        ]
    )
    api = client(store, adapter)
    with api.stream(
        "POST", "/turns/stream", json={"content": "How are you?", "no_project": True}
    ) as response:
        raw = b"".join(response.iter_bytes())
    # Decode incrementally, one byte at a time, as a correct streaming client would.
    import codecs

    decoder = codecs.getincrementaldecoder("utf-8")()
    decoded = "".join(decoder.decode(bytes([b])) for b in raw) + decoder.decode(b"", final=True)
    frames = [f for f in decoded.split("\n\n") if f.strip()]

    def data_of(frame: str) -> dict:
        return json.loads(next(line[6:] for line in frame.split("\n") if line.startswith("data: ")))

    deltas = "".join(data_of(f)["text"] for f in frames if f.startswith("event: delta"))
    settled = data_of(frames[-1])
    assert deltas == reply == settled["val_message"]["content"]
    detail = api.get(f"/conversations/{settled['conversation']['id']}").json()
    assert detail["messages"][-1]["content"] == reply


def test_the_settled_event_matches_the_plain_route_shape_exactly(store: Engine) -> None:
    streamed = client(
        store, StreamingScriptedAdapter([classifier_says("not_consequential"), ok("Yes.")])
    )
    plain = client(store, ScriptedAdapter([classifier_says("not_consequential"), ok("Yes.")]))
    settled = events_of(streamed, {"content": "Ready?", "no_project": True})[-1][1]
    settled.pop("timing")
    via_plain = plain.post("/turns", json={"content": "Ready?", "no_project": True}).json()
    assert set(settled) == set(via_plain)
    assert settled["kind"] == via_plain["kind"] == "answered"
    assert settled["val_message"]["content"] == via_plain["val_message"]["content"]


def test_reservations_and_cost_settle_under_streaming(store: Engine) -> None:
    adapter = StreamingScriptedAdapter(
        [classifier_says("not_consequential"), Streamed(["A", "B"], ok("AB"))]
    )
    api = client(store, adapter)
    events_of(api, {"content": "Go.", "no_project": True})
    calls = _model_calls(store)
    assert [c[0] for c in calls] == ["classification", "conversation"]
    assert all(c[1] == "complete" and c[2] is not None for c in calls), "known cost, both rows"


# --- honesty under failure -------------------------------------------------------


def test_a_truncated_stream_is_shown_then_settles_as_truncated_with_no_val_message(
    store: Engine,
) -> None:
    fragment = ProviderResult("I was going", TerminalState.TRUNCATED, 20, 4096, "req")
    adapter = StreamingScriptedAdapter(
        [classifier_says("not_consequential"), Streamed(["I was ", "going"], fragment)]
    )
    api = client(store, adapter)
    events = events_of(api, {"content": "Go on.", "no_project": True})
    assert deltas_of(events) == "I was going"
    settled = events[-1][1]
    assert settled["kind"] == "truncated" and settled["partial_text"] == "I was going"
    assert "val_message" not in settled
    detail = api.get(f"/conversations/{settled['conversation']['id']}").json()
    assert [m["role"] for m in detail["messages"]] == ["user"], "the fragment was never persisted"


def test_a_mid_stream_provider_failure_settles_as_unanswered_with_the_cost_unknown(
    store: Engine,
) -> None:
    adapter = StreamingScriptedAdapter(
        [
            classifier_says("not_consequential"),
            Streamed(["partial"], ok("never"), terminal_missing=True),
        ]
    )
    api = client(store, adapter)
    events = events_of(api, {"content": "Go on.", "no_project": True})
    assert deltas_of(events) == "partial"
    settled = events[-1][1]
    assert settled["kind"] == "unanswered"
    assert settled["error_kind"] == "provider_error"
    assert settled["provider_contacted"] is True
    conversation_rows = [c for c in _model_calls(store) if c[0] == "conversation"]
    assert len(conversation_rows) == 1 and conversation_rows[0][2] is None, (
        "cost unknown, never zero"
    )


def test_a_restricted_refusal_arrives_as_a_refused_event(store: Engine) -> None:
    api = client(store, StreamingScriptedAdapter([]))
    events = events_of(
        api,
        {"content": "My card is 4111 1111 1111 1111, keep it for me.", "no_project": True},
    )
    assert [kind for kind, _ in events] == ["refused"]
    detail = events[0][1]["detail"]
    assert "not sent" in detail and "payment card" in detail, detail
    assert "4111" not in detail, "the refusal never echoes the credential"


# --- the consequential turn --------------------------------------------------------


def test_the_verdict_block_never_reaches_the_stream_even_split_across_deltas(
    store: Engine,
) -> None:
    verdict_reply = reconciled("I hold: open on the close-up, my lord.", "held")
    prose, marker, tail = verdict_reply.text.partition(RECONCILIATION_VERDICT_MARKER)
    deltas = [prose[:10], prose[10:], marker[:3], marker[3:] + tail[:8], tail[8:]]
    adapter = StreamingScriptedAdapter(
        [
            classifier_says("consequential"),
            strip_separates(),
            blind_says(CLOSE_UP),
            Streamed(deltas, verdict_reply),
        ]
    )
    api = client(store, adapter)
    events = events_of(api, {"content": MIXED, "project": "Project Alpha"})
    streamed = deltas_of(events)
    assert RECONCILIATION_VERDICT_MARKER not in streamed
    assert "recorded_prior" not in streamed and "outcome" not in streamed
    settled = events[-1][1]
    assert settled["kind"] == "answered"
    assert streamed.strip() == settled["val_message"]["content"].strip()
    assert settled["glimpse"]["blind"]["ordering"] == "enforced"
    assert settled["glimpse"]["deliberation"]["outcome"] == "held"
    assert adapter.streamed == [4], "only the response stage streamed"


# --- an adapter that cannot stream ------------------------------------------------


def test_a_non_streaming_adapter_answers_through_the_same_route_with_no_deltas(
    store: Engine,
) -> None:
    api = client(store, ScriptedAdapter([classifier_says("not_consequential"), ok("As you say.")]))
    events = events_of(api, {"content": "Good evening.", "no_project": True})
    assert [kind for kind, _ in events] == ["settled"]
    settled = events[0][1]
    assert settled["kind"] == "answered" and settled["val_message"]["content"] == "As you say."
    assert settled["timing"]["api_first_delta_ms"] is None
    assert settled["timing"]["gateway_first_output_ms"] is None


# --- project semantics through the desktop's default payloads -----------------------


def test_the_desktops_default_payload_creates_an_unassigned_conversation(store: Engine) -> None:
    """`no_project: true` with no project field — what the desktop now sends for
    an ordinary conversation — creates a conversation with a null project."""
    api = client(store, ScriptedAdapter([classifier_says("not_consequential"), ok("Hello.")]))
    outcome = api.post("/turns", json={"content": "Hello.", "no_project": True}).json()
    assert outcome["kind"] == "answered"
    assert outcome["conversation"]["project_id"] is None
    listed = api.get("/conversations?scope=none").json()
    assert [c["id"] for c in listed] == [outcome["conversation"]["id"]]


def test_an_intentional_project_entry_still_attributes_the_conversation(store: Engine) -> None:
    api = client(store, ScriptedAdapter([classifier_says("not_consequential"), ok("Hello.")]))
    outcome = api.post("/turns", json={"content": "Hello.", "project": "Project Alpha"}).json()
    assert outcome["kind"] == "answered"
    assert outcome["conversation"]["project_id"] is not None
    projects = {p["name"]: p["id"] for p in api.get("/projects").json()}
    assert outcome["conversation"]["project_id"] == projects["Project Alpha"]
