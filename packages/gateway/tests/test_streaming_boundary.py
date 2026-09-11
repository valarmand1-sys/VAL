# ruff: noqa: F811, F401 - `store` and `clean_personas` are fixtures imported by name
"""Streaming through Val Core — Phase 1, 11 September 2026.

Real PostgreSQL, scripted adapters. A route whose adapter declares streaming
answers as deltas; the gateway forwards each to a sink owned by the core and
settles the terminal result exactly as a completed call. The persisted
message, the evidence tables, the cost rows and the fragment doctrine are
unchanged by streaming; only the response stage may stream; the verdict block
never reaches the sink; a stream that never ends in a result is a provider
failure settled as unknown; the reservation is durable before the first
delta; an adapter without `stream` is served by `complete` even when a sink
is offered.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field

from sqlalchemy import Engine, text
from test_deliberation_machinery import (
    CLOSE_UP,
    MIXED_MESSAGE,
    ScriptedAdapter,
    SentCall,
    _calls_by_task,
    blind_says,
    build_gateway,
    classifier_says,
    deliberated_send,
    load_catalogue,
    ok,
    reconciled,
    store,
    strip_says,
)
from test_persona import clean_personas

from val_domain.gateway import (
    CacheTtl,
    Classification,
    GatewayError,
    GatewayErrorKind,
    GatewayRequest,
    Message,
    ModelConfig,
    TaskType,
    TerminalState,
)
from val_domain.project import ProjectAttribution
from val_domain.provider import ProviderEvent, ProviderResult, TextDelta
from val_gateway.deliberate import DeliberatedTurn
from val_gateway.gateway import Gateway
from val_gateway.ledger import DatabaseLedger
from val_gateway.loop import TruncatedTurn, Turn, UnansweredTurn
from val_gateway.persistence import record_call
from val_policy.deliberation import RECONCILIATION_VERDICT_MARKER
from val_policy.project_resolution import ProjectSignals


@dataclass
class Streamed:
    """A scripted streamed reply: deltas, then the terminal result (or a failure)."""

    deltas: list[str]
    result: ProviderResult | Exception
    terminal_missing: bool = False


@dataclass
class StreamingScriptedAdapter(ScriptedAdapter):
    """A scripted adapter that also declares streaming.

    `streamed` records which calls (indices into `sent`) went through
    `stream`, so a test can prove which stage streamed and which completed.
    """

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
        self.sent.append(
            SentCall(
                config_slug=config.slug,
                messages=messages,
                system=system,
                max_output_tokens=max_output_tokens,
                observed_blind_rows=None,
                output_schema=output_schema,
            )
        )
        self.streamed.append(len(self.sent) - 1)
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


def _send(store: Engine, adapter: ScriptedAdapter, content: str, sink: list[str]) -> object:
    return deliberated_send(
        store,
        build_gateway(store, adapter),
        content,
        catalogue=load_catalogue(store),
        signals=ProjectSignals(explicit_selection="Project Alpha"),
        on_delta=sink.append,
    )


def _conversation_rows(store: Engine) -> list[tuple[str, object]]:
    with store.connect() as connection:
        return [
            (row[0], row[1])
            for row in connection.execute(
                text(
                    "select terminal_state::text, cost from model_calls "
                    "where task_type = 'conversation' order by created_at"
                )
            ).all()
        ]


# --- the ordinary path ---------------------------------------------------------


def test_an_ordinary_turn_streams_through_the_core_and_settles_identically(
    store: Engine,
) -> None:
    sink: list[str] = []
    adapter = StreamingScriptedAdapter(
        [
            classifier_says("not_consequential"),
            Streamed(["Good ", "evening, ", "my lord."], ok("Good evening, my lord.")),
        ]
    )
    outcome = _send(store, adapter, "Good evening.", sink)

    assert isinstance(outcome, DeliberatedTurn) and isinstance(outcome.turn, Turn)
    assert sink == ["Good ", "evening, ", "my lord."], "every delta, in order, through the core"
    assert outcome.turn.val_message.content == "Good evening, my lord.", "settled from the result"
    assert adapter.streamed == [1], "the response streamed; the classifier completed"
    calls = _calls_by_task(store)
    assert calls["conversation"] == 1 and calls["classification"] == 1
    assert _conversation_rows(store)[0][0] == "complete"


def test_a_truncated_stream_is_presented_but_never_spoken(store: Engine) -> None:
    """The fragment doctrine survives streaming: deltas were shown, nothing is persisted."""
    sink: list[str] = []
    fragment = ProviderResult("I was going to", TerminalState.TRUNCATED, 20, 4096, "req")
    adapter = StreamingScriptedAdapter(
        [classifier_says("not_consequential"), Streamed(["I was ", "going to"], fragment)]
    )
    outcome = _send(store, adapter, "Go on.", sink)

    assert isinstance(outcome, DeliberatedTurn) and isinstance(outcome.turn, TruncatedTurn)
    assert sink == ["I was ", "going to"]
    with store.connect() as connection:
        val_messages = connection.execute(
            text("select count(*) from messages where role = 'val'")
        ).scalar_one()
    assert val_messages == 0, "a fragment is not Val's message, streamed or not"
    assert _conversation_rows(store)[0][0] == "truncated"


def test_a_stream_without_a_terminal_result_is_a_provider_failure_settled_unknown(
    store: Engine,
) -> None:
    sink: list[str] = []
    adapter = StreamingScriptedAdapter(
        [
            classifier_says("not_consequential"),
            Streamed(["partial"], ok("never delivered"), terminal_missing=True),
        ]
    )
    outcome = _send(store, adapter, "Go on.", sink)

    # An unanswered turn is returned as itself (the deliberated path's contract).
    assert isinstance(outcome, UnansweredTurn)
    assert isinstance(outcome.error, GatewayError)
    assert outcome.error.kind is GatewayErrorKind.PROVIDER_ERROR
    assert "without a terminal result" in str(outcome.error)
    assert sink == ["partial"], "what streamed was shown; nothing from it was persisted"
    rows = _conversation_rows(store)
    assert len(rows) == 1 and rows[0][1] is None, "recorded, cost unknown, never zero"


def test_an_adapter_without_stream_answers_by_completion_when_a_sink_is_offered(
    store: Engine,
) -> None:
    sink: list[str] = []
    adapter = ScriptedAdapter([classifier_says("not_consequential"), ok("As you say.")])
    outcome = _send(store, adapter, "Good evening.", sink)

    assert isinstance(outcome, DeliberatedTurn) and isinstance(outcome.turn, Turn)
    assert sink == [], "no streaming capability, no deltas — and no failure"
    assert outcome.turn.val_message.content == "As you say."


# --- the deliberated path ------------------------------------------------------


def test_only_the_response_stage_streams_and_the_verdict_block_is_withheld(
    store: Engine,
) -> None:
    sink: list[str] = []
    verdict_reply = reconciled(
        "I hold: open on the close-up, my lord — the film is about her hands.", "held"
    )
    prose, marker, tail = verdict_reply.text.partition(RECONCILIATION_VERDICT_MARKER)
    assert marker, "the scripted reply carries a verdict block"
    # The verdict block arrives split across deltas, as a real stream would send it.
    deltas = [prose[:12], prose[12:], marker[:4], marker[4:] + tail[:5], tail[5:]]
    adapter = StreamingScriptedAdapter(
        [
            classifier_says("consequential"),
            strip_says(
                question="How should the film open?", removed=MIXED_MESSAGE.split(" How")[0]
            ),
            blind_says(CLOSE_UP),
            Streamed(deltas, verdict_reply),
        ]
    )
    outcome = _send(store, adapter, MIXED_MESSAGE, sink)

    assert isinstance(outcome, DeliberatedTurn) and isinstance(outcome.turn, Turn)
    assert adapter.streamed == [3], "classifier, strip and blind completed; the response streamed"
    streamed_text = "".join(sink)
    assert RECONCILIATION_VERDICT_MARKER not in streamed_text
    assert "outcome" not in streamed_text
    assert streamed_text.strip() == outcome.turn.val_message.content.strip(), (
        "what streamed is her prose, and her prose is what was persisted"
    )
    assert outcome.blind is not None and outcome.deliberation is not None
    assert outcome.deliberation.outcome.value == "held"


# --- the gateway itself ----------------------------------------------------------


def _structured_request() -> GatewayRequest:
    return GatewayRequest(
        task_type=TaskType.CLASSIFICATION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="classify this"),),
        max_output_tokens=256,
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
    )


class _ProbingStreamer:
    """Asserts, before its first delta, that the attempt is already durably reserved."""

    name = "anthropic"

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self.reserved_at_first_delta: bool | None = None

    def complete(self, *args: object, **kwargs: object) -> ProviderResult:
        raise AssertionError("a streaming adapter offered a sink must be streamed, not completed")

    def stream(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> Iterator[ProviderEvent]:
        with self._engine.connect() as connection:
            reserved = connection.execute(
                text("select count(*) from budget_reservations where state = 'reserved'")
            ).scalar_one()
        self.reserved_at_first_delta = reserved == 1
        yield TextDelta('{"verdict": ')
        yield TextDelta('"not_consequential", "hard_exclusion": null}')
        yield ProviderResult(
            '{"verdict": "not_consequential", "hard_exclusion": null}',
            TerminalState.COMPLETE,
            9,
            9,
            "req",
        )


def test_the_reservation_is_durable_before_the_first_delta_and_first_output_is_measured(
    store: Engine,
) -> None:
    adapter = _ProbingStreamer(store)
    gateway = Gateway(
        adapters={"anthropic": adapter, "openai": adapter},
        recorder=lambda record: record_call(store, record),
        ledger=DatabaseLedger(store),
        observe_block=lambda message: None,
    )
    sink: list[str] = []
    response = gateway.complete(_structured_request(), on_delta=sink.append)

    assert adapter.reserved_at_first_delta is True
    assert "".join(sink) == response.text
    assert response.first_output_ms is not None and response.first_output_ms >= 0
    assert response.latency_ms >= response.first_output_ms
    with store.connect() as connection:
        settled = connection.execute(
            text("select count(*) from budget_reservations where state = 'settled'")
        ).scalar_one()
        rows = connection.execute(text("select count(*) from model_calls")).scalar_one()
    assert settled == 1 and rows == 1


def test_a_completed_call_reports_no_first_output_time(store: Engine) -> None:
    adapter = ScriptedAdapter([ok('{"verdict": "not_consequential", "hard_exclusion": null}')])
    gateway = build_gateway(store, adapter)
    response = gateway.complete(_structured_request())
    assert response.first_output_ms is None
