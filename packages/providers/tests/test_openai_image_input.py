"""The OpenAI adapter transmits the content parts Core selected, and selects nothing.

Owner ruling, 19 September 2026 (Track C §11). Two properties are defended here:

- **a text-only request is byte-identical to what it always was.** The content
  boundary changed underneath every existing path, and if the wire changed with
  it, a boundary change would have become a conversation change;
- **an image request carries exactly the bytes it was handed**, at the detail
  the configuration declares, in the order Core assembled — and the adapter
  refuses rather than improvising when the route cannot take it.

The wire shape asserted here is the one proven against the provider on
19 September 2026 (`docs/reviews/evidence/2026-09-19-sol-image-input.json`).
No network: the client is a recording fake.
"""

from __future__ import annotations

import io
from base64 import b64decode
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from val_domain.gateway import GatewayError, ImagePart, Message, TextPart
from val_domain.registry import by_slug
from val_providers.openai_adapter import OpenAIAdapter

SOL = by_slug("gpt-5-6-sol-medium")
assert SOL is not None


def pixels() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), "navy").save(buffer, format="PNG")
    return buffer.getvalue()


PNG = pixels()


def image_part(**overrides: Any) -> ImagePart:  # noqa: ANN401
    fields: dict[str, Any] = {
        "sha256": "c" * 64,
        "media_type": "image/png",
        "width": 64,
        "height": 48,
        "content": PNG,
    }
    fields.update(overrides)
    return ImagePart(**fields)


class _Client:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}
        self.responses = self

    def create(self, **kwargs: Any) -> object:  # noqa: ANN401
        kwargs.pop("stream", None)
        self.kwargs = kwargs
        return SimpleNamespace(
            status="completed",
            output=[],
            output_text="Blue",
            usage=SimpleNamespace(input_tokens=326, output_tokens=5),
            id="r",
            incomplete_details=None,
            error=None,
        )


def _adapter() -> tuple[OpenAIAdapter, _Client]:
    adapter = OpenAIAdapter.__new__(OpenAIAdapter)
    client = _Client()
    adapter._client = client  # type: ignore[assignment]
    return adapter, client


def send(messages: tuple[Message, ...], config: Any = SOL) -> list[Any]:  # noqa: ANN401
    adapter, client = _adapter()
    adapter.complete(config, messages, "persona", 64)
    return list(client.kwargs["input"])


# --- the text path did not move -------------------------------------------------


def test_a_text_only_request_still_sends_plain_strings() -> None:
    items = send((Message(role="user", content="Evening, Val."),))
    assert items == [{"role": "user", "content": "Evening, Val."}]


def test_a_text_history_is_unchanged_in_shape_and_order() -> None:
    items = send(
        (
            Message(role="user", content="One."),
            Message(role="assistant", content="Two."),
            Message(role="user", content="Three."),
        )
    )
    assert items == [
        {"role": "user", "content": "One."},
        {"role": "assistant", "content": "Two."},
        {"role": "user", "content": "Three."},
    ]


# --- images ---------------------------------------------------------------------


def test_an_image_turn_carries_the_exact_bytes_at_the_declared_detail() -> None:
    items = send((Message(role="user", parts=(TextPart(text="What is this?"), image_part())),))
    assert len(items) == 1
    blocks = items[0]["content"]
    assert [block["type"] for block in blocks] == ["input_text", "input_image"]
    assert blocks[0]["text"] == "What is this?"
    assert blocks[1]["detail"] == "high", "from the configuration, never a provider default"
    prefix, _, payload = blocks[1]["image_url"].partition(",")
    assert prefix == "data:image/png;base64"
    assert b64decode(payload) == PNG, "the bytes Core selected, unchanged"


def test_the_order_of_parts_is_the_order_on_the_wire() -> None:
    blocks = send(
        (
            Message(
                role="user",
                parts=(
                    TextPart(text="Before."),
                    image_part(),
                    TextPart(text="After."),
                ),
            ),
        )
    )[0]["content"]
    assert [block["type"] for block in blocks] == ["input_text", "input_image", "input_text"]
    assert [block.get("text") for block in blocks if block["type"] == "input_text"] == [
        "Before.",
        "After.",
    ]


def test_two_images_are_both_sent_in_order() -> None:
    other = image_part(sha256="d" * 64, content=PNG + b"\x00", width=8, height=8)
    blocks = send((Message(role="user", parts=(TextPart(text="Compare."), image_part(), other)),))[
        0
    ]["content"]
    images = [block for block in blocks if block["type"] == "input_image"]
    assert len(images) == 2
    assert b64decode(images[0]["image_url"].partition(",")[2]) == PNG
    assert b64decode(images[1]["image_url"].partition(",")[2]) == PNG + b"\x00"


def test_the_adapter_never_resizes_or_re_encodes_what_it_was_given() -> None:
    """Resize policy is Core's. An adapter that resized would break the binding."""
    big = Image.new("RGB", (4000, 3000), "navy")
    buffer = io.BytesIO()
    big.save(buffer, format="PNG")
    huge = buffer.getvalue()
    blocks = send(
        (
            Message(
                role="user",
                parts=(TextPart(text="x"), image_part(content=huge, width=4000, height=3000)),
            ),
        )
    )[0]["content"]
    sent = b64decode(blocks[1]["image_url"].partition(",")[2])
    assert sent == huge
    with Image.open(io.BytesIO(sent)) as unchanged:
        assert unchanged.size == (4000, 3000)


# --- refusals --------------------------------------------------------------------


def test_a_route_that_declares_no_image_input_refuses_rather_than_guessing() -> None:
    incumbent = by_slug("opus-5-medium")
    assert incumbent is not None and incumbent.image_input is None
    with pytest.raises(GatewayError, match="declares no image input"):
        send((Message(role="user", parts=(TextPart(text="x"), image_part())),), incumbent)


def test_a_media_type_the_route_does_not_accept_is_refused_before_transmission() -> None:
    support = SOL.image_input
    assert support is not None
    narrowed = SOL.model_copy(
        update={
            "image_input": support.model_copy(
                update={
                    "provider": support.provider.model_copy(
                        update={"media_types": frozenset({"image/jpeg"})}
                    )
                }
            )
        }
    )
    with pytest.raises(GatewayError, match="accepts image/jpeg"):
        send((Message(role="user", parts=(TextPart(text="x"), image_part())),), narrowed)


# --- the cache boundary still works, with images present -------------------------


def test_the_boundary_marker_lands_on_the_first_text_block_of_an_image_turn() -> None:
    items = send(
        (
            Message(
                role="user",
                parts=(TextPart(text="History."), image_part()),
                cache_breakpoint=True,
            ),
            Message(role="user", content="Current."),
        )
    )
    blocks = items[0]["content"]
    assert blocks[0]["prompt_cache_breakpoint"] == {"mode": "explicit"}
    assert "prompt_cache_breakpoint" not in blocks[1], "the marker is a position, not a repetition"
    assert items[1] == {"role": "user", "content": "Current."}


def test_a_text_boundary_message_keeps_the_block_form_it_already_had() -> None:
    items = send(
        (
            Message(role="user", content="History.", cache_breakpoint=True),
            Message(role="user", content="Current."),
        )
    )
    assert items[0] == {
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": "History.",
                "prompt_cache_breakpoint": {"mode": "explicit"},
            }
        ],
    }
