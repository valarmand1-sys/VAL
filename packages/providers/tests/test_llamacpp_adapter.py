"""The llama.cpp adapter — declared is transmitted, the body counted is the body sent."""

from __future__ import annotations

import logging
from datetime import date
from types import SimpleNamespace
from uuid import UUID

import pytest

from val_domain.gateway import (
    AdapterStatus,
    Admission,
    Classification,
    GatewayError,
    GatewayErrorKind,
    Hosting,
    Message,
    Metering,
    ModelConfig,
    PricingFeature,
    QualificationTarget,
    ReasoningEffort,
    TerminalState,
)
from val_domain.provider import ContextFeasibility, ContextInspectionUnavailableError, TextDelta
from val_providers.base import ProviderResult
from val_providers.llamacpp_adapter import (
    DEFAULT_BASE_URL,
    LlamaCppAdapter,
    split_for_client,
    wire_body,
)
from val_providers.lmstudio_adapter import WIRE_SEPARATOR

SENTINEL = "llamacpp-sentinel-value-that-must-never-appear-anywhere"
REASONING = "HIDDEN-THOUGHT-the-user-must-never-see"
PERSONA = "You are Val, Maester to House Armand. (whole persona text)"
MODEL = "gemma-4-31b-it-q6_k"
HISTORY = (
    Message(role="user", content="first question"),
    Message(role="assistant", content="first answer"),
    Message(role="user", content="VAL-STATE-V1\n{...}"),
    Message(role="user", content="the current question"),
)


def gemma(**overrides: object) -> ModelConfig:
    fields: dict[str, object] = {
        "id": UUID("00000000-0000-4000-8000-0000000000aa"),
        "slug": "gemma-test-llamacpp",
        "provider": "llamacpp",
        "model_identifier": MODEL,
        "display_name": "Gemma test entry",
        "context_window_tokens": 32_768,
        "max_output_tokens": 16_384,
        "reasoning_effort": ReasoningEffort.NOT_APPLICABLE,
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 64,
        "thinking_enabled": True,
        "preserve_thinking": False,
        "hosting": Hosting.LOCAL,
        "metering": Metering.LOCAL_NO_METERED_COST,
        "cost_per_mtok_in_usd": 0.0,
        "cost_per_mtok_out_usd": 0.0,
        "caching": PricingFeature.NOT_VERIFIED,
        "batch_pricing": PricingFeature.NOT_VERIFIED,
        "eligible_classifications": frozenset(
            {Classification.PUBLIC, Classification.INTERNAL, Classification.PROTECTED}
        ),
        "capability_profiles": frozenset(),
        "qualification_targets": frozenset({QualificationTarget.PARTNER}),
        "fallback_slug": None,
        "admission": Admission.NOT_ADMITTED,
        "adapter_status": AdapterStatus.IMPLEMENTED,
        "activated_on": date(2026, 9, 18),
        "rates_verified_on": date(2026, 9, 18),
    }
    fields.update(overrides)
    return ModelConfig(**fields)  # type: ignore[arg-type]


class _Completions:
    def __init__(self, response: object | None = None, chunks: list[object] | None = None) -> None:
        self.kwargs: dict[str, object] = {}
        self.response, self.chunks = response, chunks or []

    def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return iter(self.chunks) if kwargs.get("stream") else self.response


class _Inspector:
    def __init__(self, tokens: int = 5_400, n_ctx: int = 32_768) -> None:
        self.tokens, self.n_ctx = tokens, n_ctx
        self.bodies: list[dict[str, object]] = []

    def measure(self, model_identifier: str, body: dict[str, object]) -> ContextFeasibility:
        self.bodies.append(dict(body))
        return ContextFeasibility(self.tokens, self.n_ctx, "llamacpp-server", {"n_ctx": self.n_ctx})

    def runtime_facts(self) -> dict[str, object]:
        return {"n_ctx": self.n_ctx}


def _usage(prompt: int = 5_400, completion: int = 300) -> SimpleNamespace:
    return SimpleNamespace(
        prompt_tokens=prompt, completion_tokens=completion, completion_tokens_details=None
    )


def _completion(
    content: str = "Good evening, my lord.",
    reasoning: str | None = REASONING,
    finish: str = "stop",
    usage: object | None = None,
) -> SimpleNamespace:
    message = SimpleNamespace(
        content=content, refusal=None, role="assistant", reasoning_content=reasoning
    )
    return SimpleNamespace(
        model=MODEL,
        choices=[SimpleNamespace(message=message, finish_reason=finish)],
        usage=usage or _usage(),
    )


def _chunk(
    content: str | None = None,
    reasoning: str | None = None,
    finish: str | None = None,
    usage: object | None = None,
) -> SimpleNamespace:
    delta = SimpleNamespace(content=content, refusal=None, reasoning_content=reasoning)
    return SimpleNamespace(
        model=MODEL, choices=[SimpleNamespace(delta=delta, finish_reason=finish)], usage=usage
    )


def _adapter(completions: _Completions, inspector: _Inspector | None = None) -> LlamaCppAdapter:
    adapter = LlamaCppAdapter(DEFAULT_BASE_URL, SENTINEL, inspector=inspector)  # type: ignore[arg-type]
    adapter._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))  # type: ignore[assignment]
    return adapter


# --- construction ---------------------------------------------------------------------------


def test_loopback_and_the_dedicated_key_are_required_and_retries_are_off() -> None:
    with pytest.raises(ValueError, match="must name this machine"):
        LlamaCppAdapter("http://192.168.1.20:8766/v1", SENTINEL)
    with pytest.raises(ValueError, match="VAL_LLAMACPP_API_KEY"):
        LlamaCppAdapter(DEFAULT_BASE_URL, "")
    adapter = LlamaCppAdapter(DEFAULT_BASE_URL, SENTINEL)
    assert adapter._client.max_retries == 0, "no silent transport retries"
    assert adapter.name == "llamacpp"


# --- the canonical body: declared is transmitted --------------------------------------------


def test_thinking_on_preserve_off_and_the_official_sampling_travel_verbatim() -> None:
    body = wire_body(gemma(), HISTORY, PERSONA, 6_144)
    assert body["chat_template_kwargs"] == {"enable_thinking": True, "preserve_thinking": False}
    assert body["temperature"] == 1.0 and body["top_p"] == 0.95 and body["top_k"] == 64
    assert body["model"] == MODEL and body["max_tokens"] == 6_144
    assert "reasoning_effort" not in body and "reasoning" not in body


def test_thinking_off_is_declared_as_false_not_omitted() -> None:
    body = wire_body(gemma(thinking_enabled=False), HISTORY, PERSONA, 6_144)
    assert body["chat_template_kwargs"] == {"enable_thinking": False, "preserve_thinking": False}


def test_none_sends_nothing_and_never_means_whatever_the_runtime_prefers() -> None:
    config = gemma(
        thinking_enabled=None, preserve_thinking=None, top_p=None, top_k=None, temperature=None
    )
    body = wire_body(config, HISTORY, PERSONA, 6_144)
    assert set(body) == {"model", "messages", "max_tokens"}


def test_the_messages_take_the_accepted_canonical_local_wire_form() -> None:
    messages = wire_body(gemma(), HISTORY, PERSONA, 6_144)["messages"]
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[3]["content"] == "VAL-STATE-V1\n{...}" + WIRE_SEPARATOR + "the current question"


def test_a_graded_reasoning_effort_is_refused_not_dropped() -> None:
    adapter = _adapter(_Completions(_completion()))
    with pytest.raises(GatewayError) as refused:
        adapter.complete(gemma(reasoning_effort=ReasoningEffort.MEDIUM), HISTORY, PERSONA, 6_144)
    assert refused.value.kind is GatewayErrorKind.INVALID_REQUEST
    assert "transmitted or refused" in refused.value.detail


def test_a_schema_constrained_task_is_refused() -> None:
    adapter = _adapter(_Completions(_completion()))
    with pytest.raises(GatewayError) as refused:
        adapter.complete(gemma(), HISTORY, PERSONA, 6_144, output_schema={"type": "object"})
    assert refused.value.kind is GatewayErrorKind.INVALID_REQUEST


# --- the body counted is the body sent -------------------------------------------------------


def test_the_preflight_counts_exactly_the_body_inference_transmits() -> None:
    completions, inspector = _Completions(_completion()), _Inspector()
    adapter = _adapter(completions, inspector)
    adapter.measure_context(gemma(), HISTORY, PERSONA, 6_144)
    adapter.complete(gemma(), HISTORY, PERSONA, 6_144)
    sent = dict(completions.kwargs)
    extra = sent.pop("extra_body")
    transmitted = {**sent, **extra}  # what the client serialises
    assert inspector.bodies == [transmitted], "one canonical body, counted then sent"
    assert transmitted == wire_body(gemma(), HISTORY, PERSONA, 6_144)


def test_streaming_adds_only_the_stream_keys_to_the_same_body() -> None:
    completions, inspector = (
        _Completions(chunks=[_chunk(content="x", finish="stop", usage=_usage())]),
        _Inspector(),
    )
    adapter = _adapter(completions, inspector)
    adapter.measure_context(gemma(), HISTORY, PERSONA, 6_144)
    list(adapter.stream(gemma(), HISTORY, PERSONA, 6_144))
    sent = dict(completions.kwargs)
    extra = sent.pop("extra_body")
    assert sent.pop("stream") is True and sent.pop("stream_options") == {"include_usage": True}
    assert {**sent, **extra} == inspector.bodies[0]


def test_split_and_merge_is_the_identity() -> None:
    body = wire_body(gemma(), HISTORY, PERSONA, 6_144)
    kwargs, extra = split_for_client(body)
    assert {**kwargs, **extra} == body and set(extra) == {"top_k", "chat_template_kwargs"}


def test_measurement_without_the_allowance_or_an_inspector_is_unavailable_never_estimated() -> None:
    with pytest.raises(ContextInspectionUnavailableError, match="no runtime inspector"):
        _adapter(_Completions()).measure_context(gemma(), HISTORY, PERSONA, 6_144)
    with pytest.raises(
        ContextInspectionUnavailableError, match="body counted must be the body sent"
    ):
        _adapter(_Completions(), _Inspector()).measure_context(gemma(), HISTORY, PERSONA)


# --- reasoning separation ----------------------------------------------------------------------


def test_hidden_thought_is_discarded_and_only_its_presence_travels(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    result = _adapter(_Completions(_completion())).complete(gemma(), HISTORY, PERSONA, 6_144)
    assert isinstance(result, ProviderResult)
    assert result.text == "Good evening, my lord." and result.reasoning_present is True
    assert result.terminal is TerminalState.COMPLETE
    rendered = repr(result) + repr(result.runtime_diagnostics) + caplog.text
    assert REASONING not in rendered and SENTINEL not in rendered


def test_reasoning_deltas_are_never_yielded_as_visible_text() -> None:
    chunks = [
        _chunk(reasoning="thinking " + REASONING),
        _chunk(content="Good "),
        _chunk(reasoning="more"),
        _chunk(content="evening."),
        _chunk(finish="stop", usage=_usage()),
    ]
    events = list(_adapter(_Completions(chunks=chunks)).stream(gemma(), HISTORY, PERSONA, 6_144))
    deltas = [e.text for e in events if isinstance(e, TextDelta)]
    final = events[-1]
    assert deltas == ["Good ", "evening."] and isinstance(final, ProviderResult)
    assert final.text == "Good evening." and final.reasoning_present is True
    assert REASONING not in "".join(deltas) + final.text


def test_thinking_off_shows_no_reasoning_presence() -> None:
    result = _adapter(_Completions(_completion(reasoning=None))).complete(
        gemma(thinking_enabled=False), HISTORY, PERSONA, 6_144
    )
    assert result.reasoning_present is False and result.reasoning_tokens is None


def test_a_prompt_that_filled_the_server_context_is_refused_not_settled() -> None:
    adapter = _adapter(_Completions(_completion(usage=_usage(prompt=32_768))), _Inspector())
    adapter.measure_context(gemma(), HISTORY, PERSONA, 6_144)
    with pytest.raises(GatewayError) as refused:
        adapter.complete(gemma(), HISTORY, PERSONA, 6_144)
    assert (
        refused.value.kind is GatewayErrorKind.INVALID_OUTPUT
        and "silent truncation" in refused.value.detail
    )


def test_a_truncated_answer_is_truncated_never_retried() -> None:
    completions = _Completions(_completion(finish="length"))
    result = _adapter(completions).complete(gemma(), HISTORY, PERSONA, 6_144)
    assert result.terminal is TerminalState.TRUNCATED
