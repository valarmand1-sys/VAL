"""The explicit OpenAI cache breakpoint on the last retained history message — 14 September 2026.

Stage B showed every turn of a thread re-writing its whole history on OpenAI,
because the record-state envelope after the history changes each turn and the
provider's implicit breakpoint sits at the newest user message. The adapter now
sends the message Val Core flags as the last retained history message as one
`input_text` block carrying `prompt_cache_breakpoint: {"mode": "explicit"}`.
Nothing else in the request moves; a request with no flagged message is
byte-identical to before. No network: the client is a recording fake.
"""

from __future__ import annotations

from types import SimpleNamespace

from val_domain.gateway import Message
from val_domain.registry import by_slug
from val_providers.openai_adapter import OpenAIAdapter


class _Client:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}
        self.responses = self

    def create(self, **kwargs: object) -> object:
        streamed = kwargs.pop("stream", None)
        self.kwargs = kwargs
        response = SimpleNamespace(
            status="completed",
            output=[],
            output_text="ok",
            usage=SimpleNamespace(input_tokens=10, output_tokens=2),
            id="r",
            incomplete_details=None,
            error=None,
        )
        if streamed:
            return iter(
                [
                    SimpleNamespace(type="response.output_text.delta", delta="ok"),
                    SimpleNamespace(type="response.completed", response=response),
                ]
            )
        return response


def _adapter() -> tuple[OpenAIAdapter, _Client]:
    adapter = OpenAIAdapter.__new__(OpenAIAdapter)
    client = _Client()
    adapter._client = client  # type: ignore[assignment]
    return adapter, client


def _sol() -> object:
    config = by_slug("gpt-5-6-sol-medium")
    assert config is not None
    return config


HISTORY = (
    Message(role="user", content="first question"),
    Message(role="assistant", content="first answer", cache_breakpoint=True),
    Message(role="user", content="VAL-STATE-V1\n{...}"),
    Message(role="user", content="the current question"),
)


def test_a_flagged_history_message_carries_the_explicit_breakpoint_and_nothing_else_moves() -> None:
    adapter, client = _adapter()
    adapter.complete(_sol(), HISTORY, "persona", 100)  # type: ignore[arg-type]
    sent = client.kwargs["input"]
    assert isinstance(sent, list) and len(sent) == 4, "no item removed, duplicated or reordered"
    assert sent[0] == {"role": "user", "content": "first question"}
    assert sent[1] == {
        "role": "assistant",
        "content": [
            {
                "type": "input_text",
                "text": "first answer",
                "prompt_cache_breakpoint": {"mode": "explicit"},
            }
        ],
    }
    assert sent[2] == {"role": "user", "content": "VAL-STATE-V1\n{...}"}, (
        "the state envelope follows the history boundary, unmarked"
    )
    assert sent[3] == {"role": "user", "content": "the current question"}, (
        "the current message follows the envelope, unmarked"
    )
    assert client.kwargs["instructions"] == "persona"
    assert "prompt_cache_options" not in client.kwargs, "the implicit breakpoint is kept"
    texts = [
        item["content"] if isinstance(item["content"], str) else item["content"][0]["text"]
        for item in sent
    ]
    assert texts == [m.content for m in HISTORY], "no prompt text changed"


def test_exactly_one_breakpoint_on_the_flagged_message() -> None:
    adapter, client = _adapter()
    adapter.complete(_sol(), HISTORY, "persona", 100)  # type: ignore[arg-type]
    marked = [
        item
        for item in client.kwargs["input"]
        if isinstance(item["content"], list)
        and any("prompt_cache_breakpoint" in block for block in item["content"])
    ]
    assert len(marked) == 1 and marked[0]["content"][0]["text"] == "first answer"


def test_a_request_without_a_flagged_message_is_unchanged() -> None:
    adapter, client = _adapter()
    single = (Message(role="user", content="classify this"),)
    adapter.complete(_sol(), single, "instruction", 100, output_schema={"type": "object"})  # type: ignore[arg-type]
    assert client.kwargs["input"] == [{"role": "user", "content": "classify this"}]
    first_turn = (
        Message(role="user", content="VAL-STATE-V1"),
        Message(role="user", content="hello"),
    )
    adapter.complete(_sol(), first_turn, "persona", 100)  # type: ignore[arg-type]
    assert client.kwargs["input"] == [
        {"role": "user", "content": "VAL-STATE-V1"},
        {"role": "user", "content": "hello"},
    ]


def test_streaming_sends_the_identical_shape() -> None:
    adapter, client = _adapter()
    list(adapter.stream(_sol(), HISTORY, "persona", 100))  # type: ignore[arg-type]
    streamed = client.kwargs["input"]
    adapter.complete(_sol(), HISTORY, "persona", 100)  # type: ignore[arg-type]
    assert streamed == client.kwargs["input"]
