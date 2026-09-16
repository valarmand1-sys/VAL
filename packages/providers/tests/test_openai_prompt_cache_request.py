"""The OpenAI request states its cache bucketing, and the response's account of it is kept.

Ruling, 15 September 2026, after five production GPT-5.6 Sol calls reported
zero cache reads with nothing recorded about the cache request or the
provider's view of it. Every request now carries a stable `prompt_cache_key`
(configuration slug + a digest of the system prompt — never per-turn text)
and `prompt_cache_options` in implicit mode with the 30-minute minimum
lifetime; the Option 1b breakpoint translation is unchanged; and the result
carries what was requested and what the provider echoed, verbatim, so the
next genuine miss is diagnosable. No network: the client is a recording fake.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

from val_domain.gateway import Message
from val_domain.registry import by_slug
from val_providers.openai_adapter import (
    PROMPT_CACHE_MODE,
    PROMPT_CACHE_TTL,
    OpenAIAdapter,
    prompt_cache_key_for,
)


class _Client:
    def __init__(self, response: object | None = None) -> None:
        self.kwargs: dict[str, object] = {}
        self.responses = self
        self.response = response if response is not None else _response()

    def create(self, **kwargs: object) -> object:
        streamed = kwargs.pop("stream", None)
        self.kwargs = kwargs
        if streamed:
            return iter(
                [
                    SimpleNamespace(type="response.output_text.delta", delta="ok"),
                    SimpleNamespace(type="response.completed", response=self.response),
                ]
            )
        return self.response


def _response(**extra: object) -> SimpleNamespace:
    usage = SimpleNamespace(
        input_tokens=11_889,
        output_tokens=4_096,
        input_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=11_886),
        output_tokens_details=SimpleNamespace(reasoning_tokens=2_521),
    )
    fields: dict[str, object] = {
        "status": "completed",
        "output": [],
        "output_text": "ok",
        "usage": usage,
        "id": "resp_1",
        "incomplete_details": None,
        "error": None,
    }
    fields.update(extra)
    return SimpleNamespace(**fields)


def _adapter(response: object | None = None) -> tuple[OpenAIAdapter, _Client]:
    adapter = OpenAIAdapter.__new__(OpenAIAdapter)
    client = _Client(response)
    adapter._client = client  # type: ignore[assignment]
    return adapter, client


def _sol() -> object:
    config = by_slug("gpt-5-6-sol-medium")
    assert config is not None
    return config


PERSONA = "persona text, whole"
HISTORY = (
    Message(role="user", content="first question"),
    Message(role="assistant", content="first answer", cache_breakpoint=True),
    Message(role="user", content="VAL-STATE-V1\n{...}"),
    Message(role="user", content="the current question"),
)
BLIND = (Message(role="user", content="State your position.\n\nThe question:\nq"),)


# --- the emitted request ------------------------------------------------------


def test_every_request_carries_the_stable_key_and_the_implicit_30m_options() -> None:
    adapter, client = _adapter()
    adapter.complete(_sol(), HISTORY, PERSONA, 6_144)  # type: ignore[arg-type]
    expected = f"val:gpt-5-6-sol-medium:{hashlib.sha256(PERSONA.encode()).hexdigest()[:16]}"
    assert client.kwargs["prompt_cache_key"] == expected == prompt_cache_key_for(_sol(), PERSONA)  # type: ignore[arg-type]
    assert client.kwargs["prompt_cache_options"] == {"mode": "implicit", "ttl": "30m"}
    assert (PROMPT_CACHE_MODE, PROMPT_CACHE_TTL) == ("implicit", "30m")
    assert "prompt_cache_retention" not in client.kwargs, "the deprecated field is never sent"


def test_the_key_carries_no_per_turn_text_and_is_shared_by_blind_and_conversation_calls() -> None:
    adapter, client = _adapter()
    adapter.complete(_sol(), HISTORY, PERSONA, 6_144)  # type: ignore[arg-type]
    conversation_key = client.kwargs["prompt_cache_key"]
    adapter.complete(_sol(), BLIND, PERSONA, 4_096, output_schema={"type": "object"})  # type: ignore[arg-type]
    blind_key = client.kwargs["prompt_cache_key"]
    later = (*HISTORY, Message(role="assistant", content="x"), Message(role="user", content="y"))
    adapter.complete(_sol(), later, PERSONA, 6_144)  # type: ignore[arg-type]
    assert conversation_key == blind_key == client.kwargs["prompt_cache_key"]
    assert isinstance(conversation_key, str)
    for text in ("first question", "the current question", "State your position", "q"):
        assert text not in conversation_key


def test_a_different_system_prompt_is_a_different_key() -> None:
    assert prompt_cache_key_for(_sol(), PERSONA) != prompt_cache_key_for(_sol(), PERSONA + " ")  # type: ignore[arg-type]
    assert prompt_cache_key_for(_sol(), None) == "val:gpt-5-6-sol-medium:no-system"  # type: ignore[arg-type]


def test_option_1b_translation_and_the_items_are_unchanged_by_the_cache_fields() -> None:
    adapter, client = _adapter()
    adapter.complete(_sol(), HISTORY, PERSONA, 6_144)  # type: ignore[arg-type]
    sent = list(client.kwargs["input"])  # type: ignore[arg-type]
    assert sent[0] == {
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": "first question",
                "prompt_cache_breakpoint": {"mode": "explicit"},
            }
        ],
    }
    assert sent[1] == {"role": "assistant", "content": "first answer"}
    assert [item["role"] for item in sent] == ["user", "assistant", "user", "user"]
    assert client.kwargs["instructions"] == PERSONA
    assert client.kwargs["max_output_tokens"] == 6_144


def test_streaming_sends_the_identical_cache_fields() -> None:
    adapter, client = _adapter()
    list(adapter.stream(_sol(), HISTORY, PERSONA, 6_144))  # type: ignore[arg-type]
    streamed = dict(client.kwargs)
    adapter.complete(_sol(), HISTORY, PERSONA, 6_144)  # type: ignore[arg-type]
    assert streamed == client.kwargs


# --- the diagnostic mapping ---------------------------------------------------


def test_the_result_carries_the_request_and_the_providers_echo_verbatim() -> None:
    echoed = _response(
        prompt_cache_key="val:gpt-5-6-sol-medium:abcdef0123456789",
        prompt_cache_options=SimpleNamespace(mode="implicit", ttl="30m"),
        prompt_cache_retention=None,
    )
    adapter, client = _adapter(echoed)
    result = adapter.complete(_sol(), HISTORY, PERSONA, 6_144)  # type: ignore[arg-type]
    assert result.prompt_cache_key == client.kwargs["prompt_cache_key"]
    assert result.cache_diagnostics == {
        "requested": {
            "prompt_cache_key": client.kwargs["prompt_cache_key"],
            "prompt_cache_options": {"mode": "implicit", "ttl": "30m"},
        },
        "reported": {
            "prompt_cache_key": "val:gpt-5-6-sol-medium:abcdef0123456789",
            "prompt_cache_options": {"mode": "implicit", "ttl": "30m"},
            "prompt_cache_retention": None,
            "cached_tokens": 0,
            "cache_write_tokens": 11_886,
        },
    }
    # The accounting the diagnostics sit beside is unchanged.
    assert (result.tokens_in, result.cache_read_tokens, result.cache_write_auto_tokens) == (
        3,
        0,
        11_886,
    )
    assert result.reasoning_tokens == 2_521


def test_an_absent_echo_is_recorded_as_none_never_inferred() -> None:
    adapter, client = _adapter(_response())
    result = adapter.complete(_sol(), HISTORY, PERSONA, 6_144)  # type: ignore[arg-type]
    assert result.cache_diagnostics is not None
    reported = result.cache_diagnostics["reported"]
    assert reported["prompt_cache_key"] is None and reported["prompt_cache_options"] is None  # type: ignore[index]
    assert reported["cached_tokens"] == 0 and reported["cache_write_tokens"] == 11_886  # type: ignore[index]
    assert "prompt_cache_diagnostics" not in reported  # type: ignore[operator]
    requested = result.cache_diagnostics["requested"]
    assert requested["prompt_cache_key"] == client.kwargs["prompt_cache_key"]  # type: ignore[index]


def test_a_provider_diagnostics_object_is_carried_verbatim_when_a_response_has_one() -> None:
    """The pinned client exposes none; if a response ever does, it is kept, not shaped."""
    diagnostics = SimpleNamespace(
        miss_reason="prefix_not_found", reusable_tokens=4_821, missed_tokens=7_065
    )
    adapter, _ = _adapter(_response(prompt_cache_diagnostics=diagnostics))
    result = adapter.complete(_sol(), HISTORY, PERSONA, 6_144)  # type: ignore[arg-type]
    assert result.cache_diagnostics is not None
    assert result.cache_diagnostics["reported"]["prompt_cache_diagnostics"] == {  # type: ignore[index]
        "miss_reason": "prefix_not_found",
        "reusable_tokens": 4_821,
        "missed_tokens": 7_065,
    }


def test_the_streamed_result_carries_the_same_diagnostics() -> None:
    echoed = _response(
        prompt_cache_key="k", prompt_cache_options=SimpleNamespace(mode="implicit", ttl="30m")
    )
    adapter, _ = _adapter(echoed)
    events = list(adapter.stream(_sol(), HISTORY, PERSONA, 6_144))  # type: ignore[arg-type]
    final = events[-1]
    assert getattr(final, "cache_diagnostics", None) is not None
    assert final.cache_diagnostics["reported"]["prompt_cache_key"] == "k"  # type: ignore[union-attr, index]


def test_max_output_tokens_incompleteness_still_maps_to_truncated_with_diagnostics() -> None:
    cut = _response(
        status="incomplete", incomplete_details=SimpleNamespace(reason="max_output_tokens")
    )
    adapter, _ = _adapter(cut)
    result = adapter.complete(_sol(), HISTORY, PERSONA, 6_144)  # type: ignore[arg-type]
    assert result.terminal.value == "truncated"
    assert result.stop_details == "incomplete_details.reason=max_output_tokens"
    assert result.cache_diagnostics is not None
