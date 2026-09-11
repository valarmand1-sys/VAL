"""The Anthropic adapter's streaming mode — Val Core Phase 1, 11 September 2026.

Both modes send the identical SDK request and map the identical final
message; `stream` yields the provider-neutral `TextDelta`s the SDK's
`text_stream` reports, then the mapped final message, once.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import anthropic
import pytest

from val_domain.gateway import CacheTtl, GatewayError, GatewayErrorKind, Message, TerminalState
from val_domain.provider import ProviderResult, TextDelta, supports_streaming
from val_domain.registry import by_slug
from val_providers.anthropic_adapter import AnthropicAdapter

MESSAGES = (Message(role="user", content="Good evening."),)


def _final(stop_reason: str = "end_turn") -> object:
    return SimpleNamespace(
        content=[anthropic.types.TextBlock(type="text", text="Good evening, my lord.")],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=12, output_tokens=7),
        _request_id="req-stream",
    )


class _Stream:
    def __init__(self, deltas: list[str], final: object, fail_after: int | None = None) -> None:
        self._deltas = deltas
        self._final = final
        self._fail_after = fail_after

    def __enter__(self) -> _Stream:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    @property
    def text_stream(self) -> Iterator[str]:
        for index, delta in enumerate(self._deltas):
            if self._fail_after is not None and index == self._fail_after:
                raise anthropic.APIConnectionError(request=None)  # type: ignore[arg-type]
            yield delta

    def get_final_message(self) -> object:
        return self._final


class _RecordingClient:
    def __init__(self, final: object, deltas: list[str], fail_after: int | None = None) -> None:
        self.create_kwargs: dict[str, object] = {}
        self.stream_kwargs: dict[str, object] = {}
        self._final = final
        self._deltas = deltas
        self._fail_after = fail_after
        self.messages = self

    def create(self, **kwargs: object) -> object:
        self.create_kwargs = kwargs
        return self._final

    def stream(self, **kwargs: object) -> _Stream:
        self.stream_kwargs = kwargs
        return _Stream(self._deltas, self._final, self._fail_after)


def _adapter(client: _RecordingClient) -> AnthropicAdapter:
    adapter = AnthropicAdapter.__new__(AnthropicAdapter)
    adapter._client = client  # type: ignore[assignment]
    return adapter


def test_the_adapter_declares_streaming() -> None:
    assert supports_streaming(_adapter(_RecordingClient(_final(), [])))


def test_stream_yields_deltas_then_the_same_result_complete_returns() -> None:
    config = by_slug("opus-5-medium")
    assert config is not None
    client = _RecordingClient(_final(), ["Good ", "evening, ", "my lord."])
    adapter = _adapter(client)

    events = list(adapter.stream(config, MESSAGES, "persona", 100, cache_ttl=CacheTtl.ONE_HOUR))
    completed = adapter.complete(config, MESSAGES, "persona", 100, cache_ttl=CacheTtl.ONE_HOUR)

    assert [e.text for e in events[:-1]] == ["Good ", "evening, ", "my lord."]
    assert all(isinstance(e, TextDelta) for e in events[:-1])
    assert isinstance(events[-1], ProviderResult)
    assert events[-1] == completed
    assert events[-1].terminal is TerminalState.COMPLETE
    assert events[-1].tokens_in == 12 and events[-1].tokens_out == 7
    assert client.stream_kwargs == client.create_kwargs, "one request, two modes"
    assert client.stream_kwargs["output_config"] == {"effort": "medium"}


def test_a_truncated_stream_maps_to_truncated_exactly_as_a_completion_does() -> None:
    config = by_slug("opus-5-medium")
    assert config is not None
    adapter = _adapter(_RecordingClient(_final("max_tokens"), ["partial"]))
    events = list(adapter.stream(config, MESSAGES, None, 100))
    assert isinstance(events[-1], ProviderResult) and events[-1].terminal is TerminalState.TRUNCATED
    assert events[-1].stop_reason == "max_tokens"


def test_a_failure_mid_stream_is_normalized() -> None:
    config = by_slug("opus-5-medium")
    assert config is not None
    adapter = _adapter(_RecordingClient(_final(), ["one", "two"], fail_after=1))
    events = adapter.stream(config, MESSAGES, None, 100)
    assert next(events) == TextDelta("one")
    with pytest.raises(GatewayError) as caught:
        next(events)
    assert caught.value.kind is GatewayErrorKind.PROVIDER_ERROR


def test_effort_none_is_refused_before_streaming_too() -> None:
    from val_domain.gateway import ReasoningEffort

    sonnet = by_slug("sonnet-5-low")
    assert sonnet is not None
    config = sonnet.model_copy(update={"reasoning_effort": ReasoningEffort.NONE})
    client = _RecordingClient(_final(), ["x"])
    with pytest.raises(GatewayError):
        list(_adapter(client).stream(config, MESSAGES, None, 100))
    assert client.stream_kwargs == {}, "the provider was never contacted"
