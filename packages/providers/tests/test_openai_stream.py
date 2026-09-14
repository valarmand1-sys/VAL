"""The OpenAI adapter's streaming mode and usage mapping — ruling, 13 September 2026.

The OpenAI equivalent of `test_anthropic_stream.py`: both modes send the
identical Responses request and map the identical final response; `stream`
yields provider-neutral `TextDelta`s for `response.output_text.delta` events
only, then the mapped final response, once. Truncation, content filtering,
refusal, failure and a stream with no terminal event keep their meanings.
Cached input, cache writes and reasoning are recorded as the provider reports
them. No network: the SDK client is a recording fake.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import openai
import pytest

from val_domain.gateway import GatewayError, GatewayErrorKind, Message, TerminalState
from val_domain.provider import ProviderResult, TextDelta, supports_streaming
from val_domain.registry import by_slug
from val_providers.openai_adapter import OpenAIAdapter

MESSAGES = (Message(role="user", content="Good evening."),)


def _response(
    status: str = "completed",
    incomplete_reason: str | None = None,
    *,
    output: list[object] | None = None,
    usage: object | None = None,
) -> object:
    return SimpleNamespace(
        status=status,
        output=[] if output is None else output,
        output_text="Good evening, my lord.",
        usage=usage
        if usage is not None
        else SimpleNamespace(
            input_tokens=1_500,
            output_tokens=40,
            input_tokens_details=SimpleNamespace(cached_tokens=1_200, cache_write_tokens=0),
            output_tokens_details=SimpleNamespace(reasoning_tokens=25),
        ),
        id="resp-stream",
        incomplete_details=SimpleNamespace(reason=incomplete_reason) if incomplete_reason else None,
        error=None,
    )


def _events(deltas: list[str], final: object | None, terminal: str) -> list[object]:
    events: list[object] = [SimpleNamespace(type="response.created")]
    events += [SimpleNamespace(type="response.output_text.delta", delta=d) for d in deltas]
    events.append(SimpleNamespace(type="response.reasoning_summary_text.delta", delta="hidden"))
    events.append(SimpleNamespace(type="response.refusal.delta", delta="not text"))
    if final is not None:
        events.append(SimpleNamespace(type=terminal, response=final))
    return events


class _RecordingClient:
    def __init__(
        self, final: object | None, deltas: list[str], terminal: str = "response.completed"
    ) -> None:
        self.create_kwargs: dict[str, object] = {}
        self.stream_kwargs: dict[str, object] = {}
        self._final = final
        self._deltas = deltas
        self._terminal = terminal
        self.fail_after: int | None = None
        self.responses = self

    def create(self, **kwargs: object) -> object:
        if kwargs.pop("stream", False):
            self.stream_kwargs = kwargs
            return self._iterate()
        self.create_kwargs = kwargs
        return self._final

    def _iterate(self) -> Iterator[object]:
        for index, event in enumerate(_events(self._deltas, self._final, self._terminal)):
            if self.fail_after is not None and index == self.fail_after:
                raise openai.APIConnectionError(request=None)  # type: ignore[arg-type]
            yield event


def _adapter(client: _RecordingClient) -> OpenAIAdapter:
    adapter = OpenAIAdapter.__new__(OpenAIAdapter)
    adapter._client = client  # type: ignore[assignment]
    return adapter


def _config() -> object:
    config = by_slug("gpt-5-5-20260423")
    assert config is not None
    return config


def test_the_adapter_declares_streaming() -> None:
    assert supports_streaming(_adapter(_RecordingClient(_response(), [])))


def test_stream_yields_text_deltas_then_the_same_result_complete_returns() -> None:
    client = _RecordingClient(_response(), ["Good ", "evening, ", "my lord."])
    adapter = _adapter(client)
    events = list(adapter.stream(_config(), MESSAGES, "persona", 100))  # type: ignore[arg-type]
    completed = adapter.complete(_config(), MESSAGES, "persona", 100)  # type: ignore[arg-type]

    assert [e.text for e in events[:-1]] == ["Good ", "evening, ", "my lord."], (
        "only output-text deltas are text; reasoning and refusal deltas are not"
    )
    assert all(isinstance(e, TextDelta) for e in events[:-1])
    assert isinstance(events[-1], ProviderResult)
    assert events[-1] == completed
    assert client.stream_kwargs == client.create_kwargs, "one request, two modes"
    assert client.stream_kwargs["reasoning"] == {"effort": "medium"}


def test_usage_maps_cached_input_writes_and_reasoning_as_reported() -> None:
    reasoning_item = SimpleNamespace(type="reasoning", summary=[])
    usage = SimpleNamespace(
        input_tokens=2_000,
        output_tokens=300,
        input_tokens_details=SimpleNamespace(cached_tokens=1_024, cache_write_tokens=512),
        output_tokens_details=SimpleNamespace(reasoning_tokens=220),
    )
    result = _adapter(
        _RecordingClient(_response(output=[reasoning_item], usage=usage), [])
    ).complete(
        _config(),  # type: ignore[arg-type]
        MESSAGES,
        None,
        100,
    )
    assert result.tokens_in == 976 and result.cache_read_tokens == 1_024
    assert result.total_input_tokens == 2_000, "the whole input, uncached plus cached"
    assert result.reported_cache_write_tokens == 512
    assert result.reasoning_tokens == 220 and result.reasoning_present is True
    assert result.cache_write_5m_tokens is None and result.cache_write_1h_tokens is None


def test_absent_usage_details_are_none_never_zero() -> None:
    usage = SimpleNamespace(input_tokens=10, output_tokens=5)
    result = _adapter(_RecordingClient(_response(usage=usage), [])).complete(
        _config(),  # type: ignore[arg-type]
        MESSAGES,
        None,
        100,
    )
    assert result.tokens_in == 10 and result.cache_read_tokens is None
    assert result.reasoning_tokens is None and result.reported_cache_write_tokens is None
    assert result.reasoning_present is False, "an output list with no reasoning item"


def test_a_truncated_stream_maps_to_truncated_exactly_as_a_completion_does() -> None:
    final = _response("incomplete", "max_output_tokens")
    events = list(
        _adapter(_RecordingClient(final, ["partial"], "response.incomplete")).stream(
            _config(),  # type: ignore[arg-type]
            MESSAGES,
            None,
            100,
        )
    )
    assert isinstance(events[-1], ProviderResult)
    assert events[-1].terminal is TerminalState.TRUNCATED
    assert events[-1].stop_details == "incomplete_details.reason=max_output_tokens"


def test_a_filtered_stream_is_filtered_never_refused() -> None:
    final = _response("incomplete", "content_filter")
    events = list(
        _adapter(_RecordingClient(final, ["part"], "response.incomplete")).stream(
            _config(),  # type: ignore[arg-type]
            MESSAGES,
            None,
            100,
        )
    )
    assert isinstance(events[-1], ProviderResult)
    assert events[-1].terminal is TerminalState.FILTERED


def test_a_refusal_streams_no_text_and_settles_refused() -> None:
    refusal = SimpleNamespace(content=[SimpleNamespace(type="refusal", refusal="I cannot.")])
    events = list(
        _adapter(_RecordingClient(_response(output=[refusal]), [])).stream(
            _config(),  # type: ignore[arg-type]
            MESSAGES,
            None,
            100,
        )
    )
    assert len(events) == 1 and isinstance(events[0], ProviderResult)
    assert events[0].terminal is TerminalState.REFUSED and events[0].text == "I cannot."


def test_a_failed_terminal_event_raises_the_normalized_provider_error() -> None:
    final = _response("failed")
    stream = _adapter(_RecordingClient(final, ["x"], "response.failed")).stream(
        _config(),  # type: ignore[arg-type]
        MESSAGES,
        None,
        100,
    )
    assert next(stream) == TextDelta("x")
    with pytest.raises(GatewayError) as caught:
        list(stream)
    assert caught.value.kind is GatewayErrorKind.PROVIDER_ERROR


def test_a_stream_without_a_terminal_event_is_a_provider_failure() -> None:
    stream = _adapter(_RecordingClient(None, ["x"])).stream(
        _config(),  # type: ignore[arg-type]
        MESSAGES,
        None,
        100,
    )
    with pytest.raises(GatewayError) as caught:
        list(stream)
    assert caught.value.kind is GatewayErrorKind.PROVIDER_ERROR


def test_a_failure_mid_stream_is_normalized() -> None:
    client = _RecordingClient(_response(), ["one", "two"])
    client.fail_after = 2
    stream = _adapter(client).stream(_config(), MESSAGES, None, 100)  # type: ignore[arg-type]
    assert next(stream) == TextDelta("one")
    with pytest.raises(GatewayError) as caught:
        next(stream)
    assert caught.value.kind in (GatewayErrorKind.PROVIDER_ERROR, GatewayErrorKind.TIMEOUT)


def test_no_openai_type_leaves_the_adapter() -> None:
    events = list(
        _adapter(_RecordingClient(_response(), ["a"])).stream(
            _config(),  # type: ignore[arg-type]
            MESSAGES,
            None,
            100,
        )
    )
    assert {type(event) for event in events} == {TextDelta, ProviderResult}
