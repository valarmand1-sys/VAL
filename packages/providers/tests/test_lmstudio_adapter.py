"""The LM Studio adapter, deterministically — ruling of 16 September 2026.

What these tests establish: what the adapter *sends* through the installed
OpenAI client and how it *maps* what that client would return. What they do
not establish: anything about the LM Studio server's actual dialect — whether
it honours `reasoning_effort`, returns usage on a stream, or names the
reasoning field `reasoning` or `reasoning_content`. Only the live loopback
proof shows that. No network: the client is a recording fake.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import httpx
import openai
import pytest

from val_domain.gateway import GatewayError, GatewayErrorKind, Message, ModelConfig, TerminalState
from val_domain.provider import TextDelta
from val_domain.registry import by_slug
from val_providers.lmstudio_adapter import (
    DEFAULT_BASE_URL,
    LOOPBACK_HOSTS,
    LMStudioAdapter,
    is_loopback,
)

SENTINEL = "lmstudio-sentinel-value-that-must-never-appear-anywhere"
REASONING = "HIDDEN-REASONING-TEXT-the-user-must-never-see"
PERSONA = "You are Val, Maester to House Armand. (whole persona text)"


def local() -> ModelConfig:
    config = by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio")
    assert config is not None
    return config


class _Completions:
    def __init__(self, response: object | None = None, chunks: list[object] | None = None) -> None:
        self.kwargs: dict[str, object] = {}
        self.response = response
        self.chunks = chunks or []
        self.raises: Exception | None = None

    def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        if self.raises is not None:
            raise self.raises
        if kwargs.get("stream"):
            return iter(self.chunks)
        return self.response


class _Client:
    def __init__(self, completions: _Completions, native: object | Exception | None = None) -> None:
        self.chat = SimpleNamespace(completions=completions)
        self.native = native
        self.get_calls: list[str] = []

    def get(self, path: str, cast_to: object) -> object:
        self.get_calls.append(path)
        if isinstance(self.native, Exception):
            raise self.native
        return self.native


def _usage(
    prompt: int = 6_000, completion: int = 120, reasoning: int | None = 40
) -> SimpleNamespace:
    details = None if reasoning is None else SimpleNamespace(reasoning_tokens=reasoning)
    return SimpleNamespace(
        prompt_tokens=prompt, completion_tokens=completion, completion_tokens_details=details
    )


def _completion(
    content: str = "Good evening, my lord.",
    *,
    model: str = "openai/gpt-oss-20b",
    finish: str | None = "stop",
    usage: object | None = None,
    reasoning: str | None = REASONING,
    reasoning_field: str = "reasoning",
    refusal: str | None = None,
    stats: object | None = None,
) -> SimpleNamespace:
    fields: dict[str, object] = {"content": content, "refusal": refusal, "role": "assistant"}
    if reasoning is not None:
        fields[reasoning_field] = reasoning
    message = SimpleNamespace(**fields)
    completion = SimpleNamespace(
        id="chatcmpl-1",
        model=model,
        choices=[SimpleNamespace(message=message, finish_reason=finish)],
        usage=usage if usage is not None else _usage(),
    )
    if stats is not None:
        completion.stats = stats
    return completion


def _chunk(
    *,
    content: str | None = None,
    reasoning: str | None = None,
    reasoning_field: str = "reasoning",
    finish: str | None = None,
    usage: object | None = None,
    model: str = "openai/gpt-oss-20b",
    choices: bool = True,
) -> SimpleNamespace:
    delta_fields: dict[str, object] = {"content": content, "refusal": None}
    if reasoning is not None:
        delta_fields[reasoning_field] = reasoning
    delta = SimpleNamespace(**delta_fields)
    return SimpleNamespace(
        model=model,
        choices=[SimpleNamespace(delta=delta, finish_reason=finish)] if choices else [],
        usage=usage,
    )


def _adapter(
    completions: _Completions, *, native: object | Exception | None = None
) -> tuple[LMStudioAdapter, _Client]:
    adapter = LMStudioAdapter(DEFAULT_BASE_URL, SENTINEL, read_native_models=False)
    client = _Client(completions, native)
    adapter._client = client  # type: ignore[assignment]
    return adapter, client


HISTORY = (
    Message(role="user", content="first question"),
    Message(role="assistant", content="first answer", cache_breakpoint=True),
    Message(role="user", content="VAL-STATE-V1\n{...}"),
    Message(role="user", content="the current question"),
)


# --- construction: loopback only, token required, never leaked -------------------------


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:1234/v1", "http://localhost:1234/v1", "http://[::1]:1234/v1"],
)
def test_loopback_base_urls_are_accepted(url: str) -> None:
    assert is_loopback(url)
    adapter = LMStudioAdapter(url, SENTINEL, read_native_models=False)
    assert adapter.name == "lmstudio"


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.20:1234/v1",
        "https://api.openai.com/v1",
        "http://lmstudio.local:1234/v1",
        "http://10.0.0.5/v1",
        "ftp://127.0.0.1/v1",
    ],
)
def test_a_non_loopback_base_url_is_refused_at_construction(url: str) -> None:
    assert not is_loopback(url)
    with pytest.raises(ValueError, match="must name this machine"):
        LMStudioAdapter(url, SENTINEL, read_native_models=False)
    assert "127.0.0.1" in LOOPBACK_HOSTS


def test_the_token_is_required_to_construct() -> None:
    with pytest.raises(ValueError, match="VAL_LMSTUDIO_API_TOKEN"):
        LMStudioAdapter(DEFAULT_BASE_URL, "", read_native_models=False)
    with pytest.raises(ValueError, match="VAL_LMSTUDIO_API_TOKEN"):
        LMStudioAdapter(DEFAULT_BASE_URL, None, read_native_models=False)


def test_the_token_reaches_the_client_and_appears_nowhere_else(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    adapter = LMStudioAdapter(DEFAULT_BASE_URL, SENTINEL, read_native_models=False)
    assert adapter._client.api_key == SENTINEL, "handed to the transport"
    assert adapter._client.max_retries == 0, "no silent transport retries"
    adapter, _ = _adapter(_Completions(_completion()))
    result = adapter.complete(local(), HISTORY, PERSONA, 6_144)
    rendered = (
        repr(result)
        + repr(result.runtime_diagnostics)
        + caplog.text
        + repr(adapter.__dict__.keys())
    )
    assert SENTINEL not in rendered


# --- the emitted request ------------------------------------------------------------


def test_the_request_is_the_core_prompt_whole_with_no_tools_and_no_cloud_fields() -> None:
    adapter, client = _adapter(_Completions(_completion()))
    adapter.complete(local(), HISTORY, PERSONA, 6_144)
    sent = client.chat.completions.kwargs
    assert sent["model"] == "openai/gpt-oss-20b"
    # Pin moved under the owner ruling of 17 September 2026 (local wire
    # canonicalization): the two adjacent user messages Core assembles — the
    # record-state envelope and the current turn — travel as ONE user message
    # joined by exactly one blank line, the same canonical form the exact
    # preflight measures. Text unchanged, order unchanged, nothing dropped.
    assert sent["messages"] == [
        {"role": "system", "content": PERSONA},
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "VAL-STATE-V1\n{...}\n\nthe current question"},
    ], "every item, in order, text unchanged — adjacent same-role items joined once"
    assert sent["max_tokens"] == 6_144
    assert sent["reasoning_effort"] == "medium", "the registry's declared effort is sent"
    for forbidden in (
        "tools",
        "tool_choice",
        "functions",
        "response_format",
        "prompt_cache_key",
        "prompt_cache_options",
        "prompt_cache_retention",
        "instructions",
        "input",
        "stream",
    ):
        assert forbidden not in sent, forbidden


def test_a_schema_constrained_request_is_refused_not_sent_unconstrained() -> None:
    adapter, client = _adapter(_Completions(_completion()))
    with pytest.raises(GatewayError) as refused:
        adapter.complete(local(), HISTORY, PERSONA, 4_096, output_schema={"type": "object"})
    assert refused.value.kind is GatewayErrorKind.INVALID_REQUEST
    assert client.chat.completions.kwargs == {}, "nothing left the adapter"


def test_a_configuration_of_another_provider_is_refused() -> None:
    adapter, client = _adapter(_Completions(_completion()))
    sol = by_slug("gpt-5-6-sol-medium")
    assert sol is not None
    with pytest.raises(GatewayError) as refused:
        adapter.complete(sol, HISTORY, PERSONA, 6_144)
    assert refused.value.kind is GatewayErrorKind.INVALID_REQUEST
    assert client.chat.completions.kwargs == {}


# --- response mapping: content and reasoning ------------------------------------------


def test_content_becomes_text_and_reasoning_is_discarded(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    adapter, _ = _adapter(_Completions(_completion()))
    result = adapter.complete(local(), HISTORY, PERSONA, 6_144)
    assert result.text == "Good evening, my lord."
    assert result.terminal is TerminalState.COMPLETE
    assert result.reasoning_present is True
    assert REASONING not in repr(result) and REASONING not in caplog.text


def test_the_reasoning_content_variant_is_recognised_and_equally_discarded() -> None:
    adapter, _ = _adapter(_Completions(_completion(reasoning_field="reasoning_content")))
    result = adapter.complete(local(), HISTORY, PERSONA, 6_144)
    assert result.reasoning_present is True and REASONING not in repr(result)


def test_no_reasoning_field_means_reasoning_absent_not_guessed() -> None:
    adapter, _ = _adapter(_Completions(_completion(reasoning=None, usage=_usage(reasoning=None))))
    result = adapter.complete(local(), HISTORY, PERSONA, 6_144)
    assert result.reasoning_present is False and result.reasoning_tokens is None


def test_usage_and_reasoning_tokens_are_mapped_from_the_completion() -> None:
    adapter, _ = _adapter(_Completions(_completion(usage=_usage(6_000, 120, 40))))
    result = adapter.complete(local(), HISTORY, PERSONA, 6_144)
    assert (result.tokens_in, result.tokens_out, result.reasoning_tokens) == (6_000, 120, 40)
    assert result.total_input_tokens == 6_000
    assert result.cache_read_tokens is None and result.cache_write_auto_tokens is None


def test_missing_usage_is_none_never_zero() -> None:
    completion = _completion()
    completion.usage = None
    adapter, _ = _adapter(_Completions(completion))
    result = adapter.complete(local(), HISTORY, PERSONA, 6_144)
    assert (
        result.tokens_in is None and result.tokens_out is None and result.reasoning_tokens is None
    )
    assert result.text == "Good evening, my lord."


@pytest.mark.parametrize(
    ("finish", "terminal"),
    [
        ("stop", TerminalState.COMPLETE),
        ("length", TerminalState.TRUNCATED),
        ("content_filter", TerminalState.FILTERED),
        ("tool_calls", TerminalState.UNKNOWN),
    ],
)
def test_finish_reasons_map_explicitly_and_anything_else_is_unknown(
    finish: str, terminal: TerminalState
) -> None:
    adapter, _ = _adapter(_Completions(_completion(finish=finish)))
    result = adapter.complete(local(), HISTORY, PERSONA, 6_144)
    assert result.terminal is terminal and result.stop_reason == finish


def test_a_refusal_is_the_refusal_text_marked_refused() -> None:
    adapter, _ = _adapter(_Completions(_completion(content="", refusal="I cannot help with that.")))
    result = adapter.complete(local(), HISTORY, PERSONA, 6_144)
    assert result.terminal is TerminalState.REFUSED and result.text == "I cannot help with that."


def test_a_response_naming_another_model_is_refused_not_attributed() -> None:
    adapter, _ = _adapter(_Completions(_completion(model="qwen/qwen3-8b")))
    with pytest.raises(GatewayError) as refused:
        adapter.complete(local(), HISTORY, PERSONA, 6_144)
    assert refused.value.kind is GatewayErrorKind.INVALID_OUTPUT
    assert "qwen/qwen3-8b" in refused.value.detail and "openai/gpt-oss-20b" in refused.value.detail


def test_provenance_carries_the_reported_model_and_runtime_facts() -> None:
    adapter, _ = _adapter(_Completions(_completion(stats={"tokens_per_second": 71.2})))
    adapter._native_models = {
        "openai/gpt-oss-20b": {
            "id": "openai/gpt-oss-20b",
            "state": "loaded",
            "arch": "gpt-oss",
            "quantization": "MXFP4",
            "max_context_length": 131_072,
            "loaded_context_length": 32_768,
        }
    }
    result = adapter.complete(local(), HISTORY, PERSONA, 6_144)
    assert result.provider_reported_model == "openai/gpt-oss-20b"
    diagnostics = result.runtime_diagnostics or {}
    assert (
        diagnostics["runtime"] == "LM Studio"
        and diagnostics["requested_model"] == "openai/gpt-oss-20b"
    )
    assert diagnostics["reported_model"] == "openai/gpt-oss-20b"
    assert diagnostics["quantization"] == "MXFP4" and diagnostics["loaded_context_length"] == 32_768
    assert diagnostics["stats"] == {"tokens_per_second": 71.2}, "the server's own figures, verbatim"
    assert diagnostics["finish_reason"] == "stop"
    assert SENTINEL not in repr(diagnostics)


# --- no silent context truncation ---------------------------------------------------


def test_a_prompt_that_filled_the_loaded_context_is_refused_not_settled() -> None:
    adapter, _ = _adapter(_Completions(_completion(usage=_usage(prompt=4_096))))
    adapter._native_models = {
        "openai/gpt-oss-20b": {"id": "openai/gpt-oss-20b", "loaded_context_length": 4_096}
    }
    with pytest.raises(GatewayError) as refused:
        adapter.complete(local(), HISTORY, PERSONA, 6_144)
    assert refused.value.kind is GatewayErrorKind.INVALID_OUTPUT
    assert "silent truncation cannot be excluded" in refused.value.detail


def test_a_prompt_within_the_loaded_context_is_settled_and_the_prompt_was_sent_whole() -> None:
    adapter, client = _adapter(_Completions(_completion(usage=_usage(prompt=4_000))))
    adapter._native_models = {
        "openai/gpt-oss-20b": {"id": "openai/gpt-oss-20b", "loaded_context_length": 32_768}
    }
    long_history = (*HISTORY, Message(role="user", content="x" * 20_000))
    result = adapter.complete(local(), long_history, PERSONA, 6_144)
    assert result.terminal is TerminalState.COMPLETE
    sent = client.chat.completions.kwargs["messages"]
    # Pin moved under the ruling of 17 September 2026: the long turn shares one
    # canonical user message with the envelope that precedes it; it is sent whole.
    assert sent[-1]["content"].endswith("\n\n" + "x" * 20_000), "nothing shortened"
    assert sent[-1]["content"].count("x" * 20_000) == 1
    # Five Core messages plus the persona travel as four wire items: the envelope,
    # the current question and the long turn — three adjacent user messages —
    # share one canonical user message (ruling, 17 September 2026).
    assert len(sent) == len(long_history) + 1 - 2


# --- streaming: content deltas only, reasoning interleaved anywhere ------------------


def _events(adapter: LMStudioAdapter) -> list[object]:
    return list(adapter.stream(local(), HISTORY, PERSONA, 6_144))


def test_reasoning_deltas_before_between_and_after_content_never_reach_the_sink(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    chunks = [
        _chunk(reasoning=REASONING + "-1"),
        _chunk(content="Good "),
        _chunk(reasoning=REASONING + "-2"),
        _chunk(content="evening, "),
        _chunk(content="my lord."),
        _chunk(reasoning=REASONING + "-3", finish="stop"),
        _chunk(choices=False, usage=_usage(6_000, 120, 40)),
    ]
    adapter, _ = _adapter(_Completions(chunks=chunks))
    events = _events(adapter)
    deltas = [event for event in events if isinstance(event, TextDelta)]
    assert [delta.text for delta in deltas] == ["Good ", "evening, ", "my lord."]
    final = events[-1]
    assert not isinstance(final, TextDelta)
    assert final.text == "Good evening, my lord." and final.terminal is TerminalState.COMPLETE
    assert final.reasoning_present is True and final.reasoning_tokens == 40
    assert (final.tokens_in, final.tokens_out) == (6_000, 120), "usage from the final chunk"
    everything = repr(events) + caplog.text
    assert REASONING not in everything


def test_the_reasoning_content_variant_in_deltas_is_equally_withheld() -> None:
    chunks = [
        _chunk(reasoning=REASONING, reasoning_field="reasoning_content"),
        _chunk(content="Yes.", finish="stop"),
    ]
    adapter, _ = _adapter(_Completions(chunks=chunks))
    events = _events(adapter)
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["Yes."]
    assert events[-1].reasoning_present is True and REASONING not in repr(events)


def test_a_stream_without_usage_reports_none_not_zero() -> None:
    chunks = [_chunk(content="Yes."), _chunk(finish="stop")]
    adapter, _ = _adapter(_Completions(chunks=chunks))
    final = _events(adapter)[-1]
    assert final.tokens_in is None and final.tokens_out is None and final.text == "Yes."


def test_the_stream_sends_the_identical_request_plus_stream_options() -> None:
    adapter, client = _adapter(
        _Completions(_completion(), chunks=[_chunk(content="Yes.", finish="stop")])
    )
    adapter.complete(local(), HISTORY, PERSONA, 6_144)
    plain = dict(client.chat.completions.kwargs)
    _events(adapter)
    streamed = dict(client.chat.completions.kwargs)
    assert streamed.pop("stream") is True
    assert streamed.pop("stream_options") == {"include_usage": True}
    assert streamed == plain


def test_a_streamed_response_naming_another_model_is_refused_mid_stream() -> None:
    chunks = [_chunk(content="Yes.", model="qwen/qwen3-8b", finish="stop")]
    adapter, _ = _adapter(_Completions(chunks=chunks))
    with pytest.raises(GatewayError) as refused:
        _events(adapter)
    assert refused.value.kind is GatewayErrorKind.INVALID_OUTPUT


# --- error normalisation -------------------------------------------------------------


def _request() -> httpx.Request:
    return httpx.Request("POST", DEFAULT_BASE_URL + "/chat/completions")


def test_connection_refused_names_the_local_server_as_not_running() -> None:
    completions = _Completions()
    completions.raises = openai.APIConnectionError(request=_request())
    adapter, _ = _adapter(completions)
    with pytest.raises(GatewayError) as refused:
        adapter.complete(local(), HISTORY, PERSONA, 6_144)
    assert refused.value.kind is GatewayErrorKind.PROVIDER_ERROR
    assert "LM Studio's server is not running" in refused.value.detail
    assert SENTINEL not in refused.value.detail


def test_a_timeout_is_a_timeout() -> None:
    completions = _Completions()
    completions.raises = openai.APITimeoutError(request=_request())
    adapter, _ = _adapter(completions)
    with pytest.raises(GatewayError) as refused:
        adapter.complete(local(), HISTORY, PERSONA, 6_144)
    assert refused.value.kind is GatewayErrorKind.TIMEOUT


def test_a_model_the_server_does_not_have_is_an_invalid_request_naming_the_model() -> None:
    completions = _Completions()
    completions.raises = openai.NotFoundError(
        "model 'openai/gpt-oss-20b' not found",
        response=httpx.Response(404, request=_request()),
        body=None,
    )
    adapter, _ = _adapter(completions)
    with pytest.raises(GatewayError) as refused:
        adapter.complete(local(), HISTORY, PERSONA, 6_144)
    assert refused.value.kind is GatewayErrorKind.INVALID_REQUEST
    assert "no such model" in refused.value.detail


def test_a_context_overflow_rejection_by_the_server_is_surfaced_not_retried() -> None:
    completions = _Completions()
    completions.raises = openai.BadRequestError(
        "The number of tokens to keep from the initial prompt is greater than the context length",
        response=httpx.Response(400, request=_request()),
        body=None,
    )
    adapter, client = _adapter(completions)
    with pytest.raises(GatewayError) as refused:
        adapter.complete(local(), HISTORY, PERSONA, 6_144)
    assert refused.value.kind is GatewayErrorKind.INVALID_REQUEST
    assert "context length" in refused.value.detail
    assert client.chat.completions.kwargs["messages"][0]["content"] == PERSONA, "sent whole, once"


# --- the native listing ---------------------------------------------------------------


def test_the_native_listing_is_read_with_the_token_and_its_absence_is_tolerated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def fake_get(url: str, *, headers: dict[str, str], timeout: float) -> object:
        calls.append((url, headers))
        return httpx.Response(
            200,
            json={"data": [{"id": "openai/gpt-oss-20b", "loaded_context_length": 8_192}]},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    adapter, _ = _adapter(_Completions(_completion()))
    adapter._native_models = adapter._read_native_models()
    assert calls[0][0] == "http://127.0.0.1:1234/api/v0/models"
    assert calls[0][1] == {"Authorization": f"Bearer {SENTINEL}"}, (
        "the token, to the local server only"
    )
    assert adapter.loaded_context_length("openai/gpt-oss-20b") == 8_192

    def refused(url: str, *, headers: dict[str, str], timeout: float) -> object:
        raise httpx.ConnectError("refused", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", refused)
    adapter._native_models = adapter._read_native_models()
    assert adapter._native_models == {}
    assert adapter.loaded_context_length("openai/gpt-oss-20b") is None


# --- exact context measurement through the adapter (ruling, 16 September 2026) -------------


def test_measurement_is_unavailable_without_an_inspector_never_estimated() -> None:
    from val_domain.provider import ContextInspectionUnavailableError

    adapter, _ = _adapter(_Completions(_completion()))
    with pytest.raises(ContextInspectionUnavailableError, match="no runtime inspector"):
        adapter.measure_context(local(), HISTORY, PERSONA)


def test_measurement_receives_exactly_the_turns_the_request_transmits() -> None:
    from val_domain.provider import ContextFeasibility

    seen: dict[str, object] = {}

    class FakeInspector:
        sdk_version = "fake"

        def measure(self, model_identifier: str, turns: object) -> ContextFeasibility:
            seen["model"] = model_identifier
            seen["turns"] = [dict(t) for t in turns]  # type: ignore[attr-defined]
            return ContextFeasibility(5_417, 32_768, "fake", {})

    adapter, client = _adapter(_Completions(_completion()))
    adapter._inspector = FakeInspector()  # type: ignore[assignment]
    result = adapter.measure_context(local(), HISTORY, PERSONA)
    adapter.complete(local(), HISTORY, PERSONA, 6_144)
    assert seen["model"] == "openai/gpt-oss-20b"
    assert seen["turns"] == client.chat.completions.kwargs["messages"], (
        "one construction for measurement and transmission"
    )
    assert (result.prompt_tokens, result.context_tokens) == (5_417, 32_768)
    assert client.chat.completions.kwargs["messages"][0] == {"role": "system", "content": PERSONA}


# --- the Category-A Mistral challenger's wire form (owner amendment, 17 September 2026) ------


def _mistral() -> ModelConfig:
    config = by_slug("mistral-small-3-2-24b-8bit-mlx-lmstudio")
    assert config is not None
    return config


def test_the_mistral_request_sends_exactly_the_upstream_temperature_and_no_reasoning() -> None:
    completion = _completion(model="mistral-small-3.2-24b-instruct-2506-mlx")
    adapter, client = _adapter(_Completions(completion))
    adapter._native_models = {
        "mistral-small-3.2-24b-instruct-2506-mlx": {
            "id": "mistral-small-3.2-24b-instruct-2506-mlx",
            "loaded_context_length": 36_352,
        }
    }
    adapter.complete(_mistral(), HISTORY, PERSONA, 6_144)
    sent = client.chat.completions.kwargs
    assert sent["model"] == "mistral-small-3.2-24b-instruct-2506-mlx"
    assert sent["temperature"] == 0.15, "the upstream pin, transmitted exactly"
    assert "reasoning_effort" not in sent and "reasoning" not in sent
    assert "enable_thinking" not in sent and "thinking" not in sent
    invented = (
        "top_p",
        "top_k",
        "min_p",
        "repeat_penalty",
        "presence_penalty",
        "frequency_penalty",
        "seed",
    )
    for field in invented:
        assert field not in sent, f"no invented sampling field: {field}"
    assert set(sent) == {"model", "messages", "max_tokens", "temperature"}


def test_the_gpt_oss_request_is_unchanged_by_the_mistral_pin() -> None:
    adapter, client = _adapter(_Completions(_completion()))
    adapter.complete(local(), HISTORY, PERSONA, 6_144)
    sent = client.chat.completions.kwargs
    assert "temperature" not in sent, "no sampling pin on the GPT-OSS entry"
    assert sent["reasoning_effort"] == "medium"


# --- a declared state is transmitted or refused (owner ruling, 18 September 2026) ------------


def test_a_declared_thinking_or_extra_sampling_setting_is_refused_not_dropped() -> None:
    adapter, client = _adapter(_Completions(_completion()))
    for update in (
        {"thinking_enabled": True, "preserve_thinking": False},
        {"top_p": 0.95},
        {"top_k": 64},
    ):
        config = ModelConfig(**{**local().model_dump(), **update})
        with pytest.raises(GatewayError) as refused:
            adapter.complete(config, HISTORY, PERSONA, 6_144)
        assert refused.value.kind is GatewayErrorKind.INVALID_REQUEST
        assert "does not transmit" in refused.value.detail
    assert client.chat.completions.kwargs == {}, "nothing was sent"
