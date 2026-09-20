"""A turn is an ordered sequence of content parts, and text is one of them.

Owner ruling, 19 September 2026 (Track C). Two things are being defended here at
once, and they pull in opposite directions:

- **the text path did not change.** Every existing caller, adapter and test
  builds a message from a string and reads `.content` back as a string. If that
  moved even slightly, a boundary change would have become a conversation
  change, which is a stop condition;
- **the boundary is genuinely parts.** Images are not a field bolted beside the
  string, and audio and video become further members of one union rather than a
  second boundary beside this one.
"""

import pytest
from pydantic import ValidationError

from val_domain.gateway import ImagePart, Message, TextPart

PIXELS = b"\x89PNG\r\n\x1a\nsome bytes"
DIGEST = "b" * 64


def image(**overrides: object) -> ImagePart:
    fields: dict[str, object] = {
        "sha256": DIGEST,
        "media_type": "image/png",
        "width": 1024,
        "height": 768,
        "content": PIXELS,
    }
    fields.update(overrides)
    return ImagePart(**fields)  # type: ignore[arg-type]


# --- the text path is unchanged -------------------------------------------------


def test_a_string_makes_one_text_part_and_reads_back_as_itself() -> None:
    message = Message(role="user", content="Evening, Val.")
    assert message.content == "Evening, Val."
    assert message.parts == (TextPart(text="Evening, Val."),)
    assert message.images == ()


def test_an_empty_string_is_still_a_turn_that_said_nothing() -> None:
    """Envelopes and stripped payloads can be empty; that is not a malformed turn."""
    assert Message(role="user", content="").content == ""


def test_the_cache_breakpoint_survives_a_copy() -> None:
    message = Message(role="assistant", content="Said.")
    marked = message.model_copy(update={"cache_breakpoint": True})
    assert marked.cache_breakpoint is True
    assert marked.content == "Said." and marked.parts == message.parts


def test_a_message_is_frozen_and_its_role_is_the_provider_neutral_pair() -> None:
    message = Message(role="user", content="x")
    with pytest.raises(ValidationError):
        message.role = "val"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        Message(role="val", content="x")


# --- parts ----------------------------------------------------------------------


def test_a_turn_may_carry_words_and_images_in_order() -> None:
    message = Message(role="user", parts=(TextPart(text="What is wrong here?"), image()))
    assert [part.kind for part in message.parts] == ["text", "image"]
    assert message.content == "What is wrong here?", "the words, without the pixels"
    assert message.images == (message.parts[1],)


def test_the_words_of_a_mixed_turn_are_the_text_parts_in_order() -> None:
    message = Message(
        role="user", parts=(TextPart(text="Before. "), image(), TextPart(text="After."))
    )
    assert message.content == "Before. After."


def test_pixels_are_never_counted_as_characters() -> None:
    """§8 — an image is priced by its dimensions, never by pretending it is text."""
    words = "Look at this."
    message = Message(role="user", parts=(TextPart(text=words), image()))
    assert len(message.content) == len(words)


def test_an_image_part_keeps_its_bytes_out_of_a_repr() -> None:
    """An image in a log line is an image outside the record."""
    rendered = repr(image())
    assert "89PNG" not in rendered and "some bytes" not in rendered
    assert DIGEST in rendered, "the digest identifies it without reproducing it"


def test_an_image_part_states_dimensions_that_could_have_been_measured() -> None:
    for bad in ({"width": 0}, {"height": -1}):
        with pytest.raises(ValidationError):
            image(**bad)
    with pytest.raises(ValidationError):
        image(sha256="too short")


def test_a_turn_with_no_parts_is_not_a_turn() -> None:
    with pytest.raises(ValidationError):
        Message(role="user", parts=())


def test_content_is_shorthand_for_text_and_refuses_to_mean_anything_else() -> None:
    with pytest.raises(ValidationError, match="content is text"):
        Message(role="user", content=PIXELS)  # type: ignore[arg-type]


def test_parts_and_content_are_one_source_of_truth_not_two() -> None:
    """`content` is derived from the parts; there is no second field to disagree."""
    assert "content" not in Message.model_fields
    assert set(Message.model_fields) == {"role", "parts", "cache_breakpoint"}


def test_the_union_is_discriminated_so_a_new_modality_is_additive() -> None:
    """Audio and video join this union; they do not replace the boundary."""
    rebuilt = Message.model_validate(
        {
            "role": "user",
            "parts": [
                {"kind": "text", "text": "Here."},
                {
                    "kind": "image",
                    "sha256": DIGEST,
                    "media_type": "image/png",
                    "width": 2,
                    "height": 2,
                    "content": PIXELS,
                },
            ],
        }
    )
    assert isinstance(rebuilt.parts[0], TextPart)
    assert isinstance(rebuilt.parts[1], ImagePart)
    assert rebuilt.images[0].content == PIXELS
