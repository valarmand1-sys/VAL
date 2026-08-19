"""The adapters' actual SDK payloads — independent-review corrections, 18 Aug 2026.

Two findings live here. The registry declared reasoning settings that neither
adapter sent — descriptive metadata wearing a configuration's clothes — and the
OpenAI adapter mapped a content-filter `incomplete` to REFUSED, which the loop
persists as a finished utterance.

These tests monkeypatch a recording fake in place of the SDK client and assert
on the **kwargs the SDK method actually receives**, because "the registry says
HIGH" proves nothing about the wire.
"""

from __future__ import annotations

from types import SimpleNamespace

import anthropic
import openai
import pytest

from val_domain.gateway import Message, TerminalState
from val_domain.registry import by_slug
from val_providers.anthropic_adapter import AnthropicAdapter
from val_providers.openai_adapter import OpenAIAdapter

MESSAGES = (Message(role="user", content="Good evening."),)


class _RecordingAnthropic:
    def __init__(self, response: object) -> None:
        self.kwargs: dict[str, object] = {}
        self._response = response
        self.messages = self

    def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return self._response


def _anthropic_response(stop_reason: str = "end_turn") -> object:
    return SimpleNamespace(
        content=[],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        _request_id="req-a",
    )


class _RecordingOpenAI:
    def __init__(self, response: object) -> None:
        self.kwargs: dict[str, object] = {}
        self._response = response
        self.responses = self

    def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return self._response


def _openai_response(status: str = "completed", incomplete_reason: str | None = None) -> object:
    return SimpleNamespace(
        status=status,
        output=[],
        output_text="an answer",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        id="req-o",
        incomplete_details=(
            SimpleNamespace(reason=incomplete_reason) if incomplete_reason else None
        ),
        error=None,
    )


def _anthropic_adapter(response: object) -> tuple[AnthropicAdapter, _RecordingAnthropic]:
    adapter = AnthropicAdapter.__new__(AnthropicAdapter)
    fake = _RecordingAnthropic(response)
    adapter._client = fake
    return adapter, fake


def _openai_adapter(response: object) -> tuple[OpenAIAdapter, _RecordingOpenAI]:
    adapter = OpenAIAdapter.__new__(OpenAIAdapter)
    fake = _RecordingOpenAI(response)
    adapter._client = fake
    return adapter, fake


# --- finding 6: the declared reasoning setting reaches the wire ---------------


def test_opus_high_effort_is_sent_explicitly() -> None:
    """Opus 5 declares HIGH; the Anthropic request carries it, stated."""
    config = by_slug("opus-5")
    assert config is not None
    adapter, fake = _anthropic_adapter(_anthropic_response())

    adapter.complete(config, MESSAGES, "system", 100)

    assert fake.kwargs["output_config"] == {"effort": "high"}, (
        "the registry's declared effort never reached the SDK call"
    )


def test_haiku_not_applicable_sends_no_effort_field() -> None:
    """NOT_APPLICABLE means the parameter is omitted, not invented."""
    config = by_slug("haiku-4-5-20251001")
    assert config is not None
    adapter, fake = _anthropic_adapter(_anthropic_response())

    adapter.complete(config, MESSAGES, "system", 100)

    assert fake.kwargs["output_config"] is anthropic.omit


def test_gpt_medium_reasoning_is_sent_explicitly() -> None:
    """GPT-5.5 declares MEDIUM; the Responses request carries it, stated.

    The provider default happens to be medium today; a versioned configuration
    does not depend on a provider default silently staying put.
    """
    config = by_slug("gpt-5-5-20260423")
    assert config is not None
    adapter, fake = _openai_adapter(_openai_response())

    adapter.complete(config, MESSAGES, "system", 100)

    assert fake.kwargs["reasoning"] == {"effort": "medium"}


def test_a_not_applicable_openai_config_would_omit_reasoning() -> None:
    """The omission branch, proved with a synthetic NOT_APPLICABLE config."""
    config = by_slug("gpt-5-5-20260423")
    assert config is not None
    from val_domain.gateway import ReasoningEffort

    unset = config.model_copy(update={"reasoning_effort": ReasoningEffort.NOT_APPLICABLE})
    adapter, fake = _openai_adapter(_openai_response())

    adapter.complete(unset, MESSAGES, "system", 100)

    assert fake.kwargs["reasoning"] is openai.omit


def test_the_negative_fixture_a_wrong_effort_would_be_visible() -> None:
    """Mutation proof: if the adapter sent the wrong level, these tests see it.

    A config mutated to LOW produces a LOW payload — so the HIGH/MEDIUM
    assertions above genuinely depend on the registry value reaching the wire,
    not on a hard-coded string inside the adapter.
    """
    config = by_slug("opus-5")
    assert config is not None
    from val_domain.gateway import ReasoningEffort

    mutated = config.model_copy(update={"reasoning_effort": ReasoningEffort.LOW})
    adapter, fake = _anthropic_adapter(_anthropic_response())

    adapter.complete(mutated, MESSAGES, "system", 100)

    assert fake.kwargs["output_config"] == {"effort": "low"}
    assert fake.kwargs["output_config"] != {"effort": "high"}


# --- finding 7: the adapter-level content-filter mapping ----------------------


def test_incomplete_content_filter_maps_to_filtered_not_refused() -> None:
    """An incomplete response is incomplete, whatever stopped it."""
    config = by_slug("gpt-5-5-20260423")
    assert config is not None
    adapter, _ = _openai_adapter(
        _openai_response(status="incomplete", incomplete_reason="content_filter")
    )

    result = adapter.complete(config, MESSAGES, "system", 100)

    assert result.terminal is TerminalState.FILTERED
    assert result.terminal is not TerminalState.REFUSED


def test_incomplete_max_output_still_maps_to_truncated() -> None:
    config = by_slug("gpt-5-5-20260423")
    assert config is not None
    adapter, _ = _openai_adapter(
        _openai_response(status="incomplete", incomplete_reason="max_output_tokens")
    )

    assert adapter.complete(config, MESSAGES, "system", 100).terminal is TerminalState.TRUNCATED


def test_anthropic_max_tokens_still_maps_to_truncated() -> None:
    config = by_slug("opus-5")
    assert config is not None
    adapter, _ = _anthropic_adapter(_anthropic_response(stop_reason="max_tokens"))

    assert adapter.complete(config, MESSAGES, "system", 100).terminal is TerminalState.TRUNCATED


def test_unrecognised_stop_reasons_map_to_unknown() -> None:
    """Fail-closed inputs, both providers."""
    opus = by_slug("opus-5")
    gpt = by_slug("gpt-5-5-20260423")
    assert opus is not None and gpt is not None

    adapter, _ = _anthropic_adapter(_anthropic_response(stop_reason="tool_use"))
    assert adapter.complete(opus, MESSAGES, "system", 100).terminal is TerminalState.UNKNOWN

    oadapter, _ = _openai_adapter(_openai_response(status="incomplete", incomplete_reason="???"))
    assert oadapter.complete(gpt, MESSAGES, "system", 100).terminal is TerminalState.UNKNOWN


def test_missing_usage_is_none_at_the_adapter_boundary() -> None:
    """The §5 contract, held at the adapter itself."""
    config = by_slug("gpt-5-5-20260423")
    assert config is not None
    response = _openai_response()
    response.usage = None
    adapter, _ = _openai_adapter(response)

    result = adapter.complete(config, MESSAGES, "system", 100)

    assert result.tokens_in is None and result.tokens_out is None


def test_a_failed_response_raises_rather_than_returning() -> None:
    config = by_slug("gpt-5-5-20260423")
    assert config is not None
    response = _openai_response(status="failed")
    response.error = SimpleNamespace(message="upstream exploded")
    adapter, _ = _openai_adapter(response)

    with pytest.raises(Exception, match="failed"):
        adapter.complete(config, MESSAGES, "system", 100)


def test_stop_sequence_fails_closed_because_none_is_ever_sent() -> None:
    """Closure red-team, 18 August 2026. This adapter sends no `stop_sequences`,
    so `stop_sequence` cannot legitimately come back — the same cannot-occur
    rationale as `tool_use`, and the same fail-closed mapping."""
    config = by_slug("opus-5")
    assert config is not None
    adapter, _ = _anthropic_adapter(_anthropic_response(stop_reason="stop_sequence"))

    assert adapter.complete(config, MESSAGES, "system", 100).terminal is TerminalState.UNKNOWN
