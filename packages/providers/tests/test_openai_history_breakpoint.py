"""The explicit OpenAI cache breakpoint, translated to a legal user boundary — 14 September 2026.

Val Core flags the last retained history message (the logical boundary). The
live proof of 14 September 2026 established a service-level fact the pinned
SDK's types did not: OpenAI rejects `input_text` on an assistant item (HTTP
400, "Supported values are: 'output_text' and 'refusal'"), and `output_text`
carries no `prompt_cache_breakpoint`. So the adapter places the physical
marker on the nearest preceding user message — the most recent legal boundary at or
before the logical one — and never on an assistant block. The earlier green
tests proved the SDK contract they could see; the service supplied the rest.
No network: the client is a recording fake.
"""

from __future__ import annotations

from types import SimpleNamespace

from val_domain.gateway import Message
from val_domain.registry import by_slug
from val_providers.openai_adapter import (
    OpenAIAdapter,
    logical_cache_boundary,
    physical_cache_boundary,
)


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


def _sent(messages: tuple[Message, ...], **kwargs: object) -> list[dict[str, object]]:
    adapter, client = _adapter()
    adapter.complete(_sol(), messages, "persona", 100, **kwargs)  # type: ignore[arg-type]
    assert "prompt_cache_options" not in client.kwargs, "implicit caching is kept"
    return list(client.kwargs["input"])  # type: ignore[arg-type]


def _marked(sent: list[dict[str, object]]) -> list[int]:
    return [
        index
        for index, item in enumerate(sent)
        if isinstance(item["content"], list)
        and any("prompt_cache_breakpoint" in block for block in item["content"])  # type: ignore[union-attr]
    ]


def _texts(sent: list[dict[str, object]]) -> list[str]:
    return [
        item["content"] if isinstance(item["content"], str) else item["content"][0]["text"]  # type: ignore[index]
        for item in sent
    ]


def _assert_invalid_combination_absent(sent: list[dict[str, object]]) -> None:
    """The exact shape the live service rejected on 14 September 2026."""
    for item in sent:
        if item["role"] == "assistant":
            assert isinstance(item["content"], str), "an assistant item is a plain string"


# The shape of a real partner turn after the first: history ending with Val's reply
# (flagged by Core), then the record-state envelope, then the current message.
ALTERNATING = (
    Message(role="user", content="first question"),
    Message(role="assistant", content="first answer"),
    Message(role="user", content="second question"),
    Message(role="assistant", content="second answer", cache_breakpoint=True),
    Message(role="user", content="VAL-STATE-V1\n{...}"),
    Message(role="user", content="the current question"),
)


def test_1_a_no_history_conversation_is_unchanged() -> None:
    sent = _sent(
        (Message(role="user", content="VAL-STATE-V1"), Message(role="user", content="hello"))
    )
    assert sent == [
        {"role": "user", "content": "VAL-STATE-V1"},
        {"role": "user", "content": "hello"},
    ]


def test_2_a_logical_boundary_on_a_user_message_is_marked_directly() -> None:
    messages = (
        Message(role="user", content="a note", cache_breakpoint=True),
        Message(role="user", content="VAL-STATE-V1"),
        Message(role="user", content="now"),
    )
    assert physical_cache_boundary(messages) == logical_cache_boundary(messages) == 0
    sent = _sent(messages)
    assert _marked(sent) == [0]
    assert sent[0] == {
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": "a note",
                "prompt_cache_breakpoint": {"mode": "explicit"},
            }
        ],
    }


def test_3_and_4_assistant_boundary_kept_and_preceding_user_marked() -> None:
    assert logical_cache_boundary(ALTERNATING) == 3 and physical_cache_boundary(ALTERNATING) == 2
    sent = _sent(ALTERNATING)
    assert sent[3] == {"role": "assistant", "content": "second answer"}, (
        "still assistant, ordinary string representation, no breakpoint"
    )
    assert _marked(sent) == [2], "exactly one marker, on the nearest preceding user message"
    assert sent[2]["content"] == [
        {
            "type": "input_text",
            "text": "second question",
            "prompt_cache_breakpoint": {"mode": "explicit"},
        }
    ]


def test_5_the_marked_user_message_is_the_latest_legal_one_not_an_earlier_turn() -> None:
    sent = _sent(ALTERNATING)
    assert _marked(sent) == [2] and sent[0] == {"role": "user", "content": "first question"}


def test_6_7_8_the_assistant_reply_envelope_and_current_message_stay_in_place() -> None:
    sent = _sent(ALTERNATING)
    assert [item["role"] for item in sent] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "user",
    ]
    assert sent[3]["content"] == "second answer", "the reply after the boundary remains"
    assert sent[4] == {"role": "user", "content": "VAL-STATE-V1\n{...}"}, "envelope after history"
    assert sent[5] == {"role": "user", "content": "the current question"}, "current after envelope"


def test_9_to_12_no_text_changes_and_nothing_is_removed_duplicated_or_reordered() -> None:
    sent = _sent(ALTERNATING)
    assert len(sent) == len(ALTERNATING)
    assert _texts(sent) == [m.content for m in ALTERNATING]


def test_13_no_legal_preceding_user_boundary_means_implicit_caching_only() -> None:
    messages = (
        Message(role="assistant", content="an opening line", cache_breakpoint=True),
        Message(role="user", content="VAL-STATE-V1"),
        Message(role="user", content="now"),
    )
    assert physical_cache_boundary(messages) is None
    sent = _sent(messages)
    assert _marked(sent) == [] and sent[0] == {"role": "assistant", "content": "an opening line"}
    assert len(sent) == 3, "the request is still valid and complete"


def test_14_classification_and_strip_requests_are_unchanged() -> None:
    single = (Message(role="user", content="classify this"),)
    assert _sent(single, output_schema={"type": "object"}) == [
        {"role": "user", "content": "classify this"}
    ]


def test_15_the_structured_blind_request_is_unchanged() -> None:
    blind = (Message(role="user", content="State your position.\n\nThe question:\nq"),)
    sent = _sent(blind, output_schema={"type": "object"})
    assert sent == [{"role": "user", "content": "State your position.\n\nThe question:\nq"}]


def test_16_anthropic_is_covered_by_its_own_tests() -> None:
    """`test_adapters.py::test_anthropic_history_breakpoint_behaviour_is_unchanged…` pins it."""
    from val_providers.anthropic_adapter import AnthropicAdapter

    assert not hasattr(AnthropicAdapter, "physical_cache_boundary")


def test_17_the_provider_invalid_combination_can_never_be_emitted() -> None:
    shapes = [
        ALTERNATING,
        (
            Message(role="assistant", content="x", cache_breakpoint=True),
            Message(role="user", content="y"),
        ),
        (
            Message(role="user", content="primer", cache_breakpoint=False),
            Message(role="assistant", content="reply", cache_breakpoint=True),
            Message(role="user", content="VAL-STATE-V1"),
            Message(role="user", content="q"),
        ),
    ]
    for shape in shapes:
        _assert_invalid_combination_absent(_sent(shape))


def test_streaming_sends_the_identical_shape() -> None:
    adapter, client = _adapter()
    list(adapter.stream(_sol(), ALTERNATING, "persona", 100))  # type: ignore[arg-type]
    streamed = client.kwargs["input"]
    adapter.complete(_sol(), ALTERNATING, "persona", 100)  # type: ignore[arg-type]
    assert streamed == client.kwargs["input"]
