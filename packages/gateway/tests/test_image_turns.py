# ruff: noqa: F811, F401 - fixtures imported by name
"""An image turn, end to end: admitted, committed atomically, derived once, bound.

Owner ruling, 19 September 2026 (Track C). Real PostgreSQL, stub adapter, no
provider. Proved here:

- the atomic evidence commit — blob, attachment, act and message together, and
  **nothing at all** when admission refuses;
- the exact bytes reach the route as an image part of the current turn;
- the binding row names the call, the act, the attachment and the transmitted
  digest, with the dimensions that priced it and the detail that was declared;
- a derived `model_input_image` is recorded with its processing events, and the
  binding names the representation rather than the original;
- **current-turn binding**: a later turn does not retransmit the image, and the
  record state says `earlier_only` rather than letting "we discussed this" read
  as "I can see it";
- the effective classification is the strictest of the text's and every act's.
"""

from __future__ import annotations

import io
import json
from typing import Any
from uuid import UUID, uuid4

import pytest
from gateway_fakes import StubAdapter
from PIL import Image
from sqlalchemy import Engine, text
from test_conversation_memory import (
    ALPHA_SLUG,
    answering,
    build_gateway,
    catalogue,
    clean_personas,
    scope_of,
    seeded_conversation,
    store,
)

from val_domain.gateway import Classification, ImagePart
from val_gateway.attachments import AttachmentAct, CandidateAttachment, strictest
from val_gateway.context import STATE_ENVELOPE_MARKER
from val_gateway.loop import Turn, send
from val_policy.attachments import AdmissionRefusedError
from val_policy.project_resolution import ProjectSignals


def png(width: int = 320, height: int = 240, colour: str = "navy") -> bytes:
    buffer = io.BytesIO()
    image = Image.new("RGB", (width, height), colour)
    image.paste(Image.new("RGB", (width // 4, height // 4), "white"), (0, 0))
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def attach(
    content: bytes = b"",
    name: str = "setting.png",
    classification: Classification = Classification.PROTECTED,
) -> CandidateAttachment:
    return CandidateAttachment(
        content=content or png(), given_filename=name, stated_classification=classification
    )


def turn(
    store: Engine,
    content: str,
    *,
    attachments: tuple[CandidateAttachment, ...] = (),
    conversation_id: UUID | None = None,
    classification: Classification = Classification.PROTECTED,
) -> tuple[Any, StubAdapter]:
    adapter = answering("A navy field with a white square in one corner, my lord.")
    outcome = send(
        store,
        build_gateway(store, adapter),
        content,
        catalogue=catalogue(store),
        signals=None if conversation_id else ProjectSignals(explicit_no_project=True),
        conversation_id=conversation_id,
        classification=classification,
        attachments=attachments,
    )
    return outcome, adapter


def rows(store: Engine, table: str) -> list[Any]:
    with store.connect() as connection:
        return list(connection.execute(text(f"select * from {table}")).mappings())  # noqa: S608


def state(adapter: StubAdapter) -> dict[str, Any]:
    block = next(m for m in adapter.sent_messages if m.content.startswith(STATE_ENVELOPE_MARKER))
    return json.loads(block.content.split("\n", 1)[1])["prior_record_state"]


def sent_images(adapter: StubAdapter) -> tuple[ImagePart, ...]:
    return tuple(part for message in adapter.sent_messages for part in message.images)


# --- the commit ------------------------------------------------------------------


def test_an_image_turn_commits_blob_attachment_and_act_with_the_message(store: Engine) -> None:
    payload = png()
    outcome, _ = turn(store, "What is in this?", attachments=(attach(payload),))
    assert isinstance(outcome, Turn)

    blobs, attachments, acts = (
        rows(store, t) for t in ("blobs", "attachments", "message_attachments")
    )
    assert len(blobs) == 1 and blobs[0]["bytes"] == payload
    assert blobs[0]["media_type"] == "image/png", "read from the bytes, not the filename"
    assert len(attachments) == 1 and attachments[0]["sha256"] == blobs[0]["sha256"]
    assert len(acts) == 1
    assert acts[0]["message_id"] == outcome.user_message.id
    assert acts[0]["position"] == 1
    assert acts[0]["given_filename"] == "setting.png"
    assert acts[0]["stated_classification"] == "protected"


def test_a_refused_admission_writes_nothing_at_all(store: Engine) -> None:
    """§3.3 — no conversation, no message, no blob, no attachment, no act, no event.

    The refusal is raised rather than returned, exactly as a Restricted refusal
    is: the send did not happen. Admission runs before scope is even resolved,
    so a file that could not be read leaves no orphan conversation behind.
    """
    with pytest.raises(AdmissionRefusedError, match=r"notes\.pdf"):
        turn(store, "Look at this.", attachments=(attach(b"%PDF-1.7 not an image", "notes.pdf"),))
    for table in (
        "blobs",
        "attachments",
        "message_attachments",
        "attachment_processing_events",
        "messages",
        "conversations",
        "model_calls",
    ):
        assert rows(store, table) == [], f"{table} must be untouched"


def test_one_unreadable_file_refuses_the_whole_send(store: Engine) -> None:
    """All or nothing: an image is never quietly dropped from a turn that claimed it."""
    with pytest.raises(AdmissionRefusedError, match=r"broken\.png"):
        turn(
            store,
            "Two of these.",
            attachments=(attach(), attach(b"\x89PNG\r\n\x1a\nrubbish", "broken.png")),
        )
    assert rows(store, "blobs") == []
    assert rows(store, "messages") == []


def test_the_same_bytes_attached_twice_are_one_identity_and_two_acts(store: Engine) -> None:
    """§3.3 — re-use is a new act with its own statement, over one content row."""
    payload = png()
    first, _ = turn(store, "This one.", attachments=(attach(payload),))
    turn(
        store,
        "And again.",
        attachments=(attach(payload, classification=Classification.INTERNAL),),
        conversation_id=first.conversation.id,
    )
    assert len(rows(store, "blobs")) == 1
    assert len(rows(store, "attachments")) == 1
    acts = rows(store, "message_attachments")
    assert len(acts) == 2
    assert {act["stated_classification"] for act in acts} == {"protected", "internal"}


# --- what reaches the route ------------------------------------------------------


def test_the_exact_bytes_reach_the_route_on_the_current_turn(store: Engine) -> None:
    payload = png()
    _, adapter = turn(store, "What is in this?", attachments=(attach(payload),))
    images = sent_images(adapter)
    assert len(images) == 1
    assert images[0].content == payload, "the admitted original, unchanged"
    assert (images[0].width, images[0].height) == (320, 240)
    current = adapter.sent_messages[-1]
    assert current.content == "What is in this?"
    assert [part.kind for part in current.parts] == ["text", "image"], "words, then the image"


def test_the_binding_names_the_call_the_act_and_the_transmitted_bytes(store: Engine) -> None:
    payload = png()
    turn(store, "What is in this?", attachments=(attach(payload),))
    bindings = rows(store, "model_call_image_inputs")
    assert len(bindings) == 1
    binding = bindings[0]
    act = rows(store, "message_attachments")[0]
    assert binding["message_attachment_id"] == act["id"]
    assert binding["attachment_id"] == act["attachment_id"]
    assert binding["input_kind"] == "original"
    assert binding["representation_id"] is None
    assert binding["transmitted_sha256"] == rows(store, "blobs")[0]["sha256"]
    assert (binding["width"], binding["height"]) == (320, 240)
    assert binding["provider_options"] == {"detail": "high"}
    assert binding["stated_classification"] == "protected"
    assert binding["position"] == 1


def test_sight_is_the_binding_and_a_completed_call_together(store: Engine) -> None:
    """§4 — the two facts stay separate and a reader must ask for both."""
    turn(store, "What is in this?", attachments=(attach(),))
    with store.connect() as connection:
        sighted = connection.execute(
            text(
                "select count(*) from model_call_image_inputs i join model_calls m "
                "on m.id = i.model_call_id where m.terminal_state = 'complete'"
            )
        ).scalar_one()
    assert sighted == 1


# --- derivation ------------------------------------------------------------------


def test_an_oversized_image_is_derived_once_and_the_binding_names_it(store: Engine) -> None:
    original = png(2400, 1800)
    turn(store, "And this one?", attachments=(attach(original, "storyboard.png"),))

    representations = rows(store, "attachment_representations")
    assert len(representations) == 1
    assert representations[0]["representation_type"] == "model_input_image"
    assert representations[0]["derived_by"].startswith("Pillow ")
    assert representations[0]["model_call_id"] is None, "a local derivation, not a model's"

    binding = rows(store, "model_call_image_inputs")[0]
    assert binding["input_kind"] == "representation"
    assert binding["representation_id"] == representations[0]["id"]
    assert binding["transmitted_sha256"] == representations[0]["sha256"]
    assert max(binding["width"], binding["height"]) == 1600, "inside the route's patch budget"
    assert binding["transmitted_sha256"] != rows(store, "attachments")[0]["sha256"]

    blobs = {row["sha256"] for row in rows(store, "blobs")}
    assert len(blobs) == 2, "the original and the derived bytes, both kept"


def test_a_derivation_records_one_started_and_one_terminal_event(store: Engine) -> None:
    turn(store, "And this one?", attachments=(attach(png(2400, 1800)),))
    events = rows(store, "attachment_processing_events")
    assert [event["event"] for event in events] == ["started", "succeeded"]
    assert len({event["attempt_id"] for event in events}) == 1
    assert all(event["intent"] == "derive:model_input_image" for event in events)
    assert events[0]["representation_id"] is None
    assert events[1]["representation_id"] == rows(store, "attachment_representations")[0]["id"]
    assert all(event["error"] is None for event in events)


# --- current-turn binding ---------------------------------------------------------


def test_a_later_turn_does_not_retransmit_the_image(store: Engine) -> None:
    first, _ = turn(store, "What is in this?", attachments=(attach(),))
    _, adapter = turn(store, "Say more about it.", conversation_id=first.conversation.id)
    assert sent_images(adapter) == (), "the image is in the record, not in view"
    assert len(rows(store, "model_call_image_inputs")) == 1, "bound to the first call only"


def test_the_record_state_distinguishes_bound_from_merely_earlier(store: Engine) -> None:
    first, bound_adapter = turn(store, "What is in this?", attachments=(attach(),))
    assert state(bound_adapter)["visual_input"] == {
        "state": "bound",
        "bound_to_this_turn": 1,
        "earlier_in_conversation": 0,
        "note": state(bound_adapter)["visual_input"]["note"],
    }

    _, later = turn(store, "Say more about it.", conversation_id=first.conversation.id)
    visual = state(later)["visual_input"]
    assert visual["state"] == "earlier_only"
    assert visual["bound_to_this_turn"] == 0
    assert visual["earlier_in_conversation"] == 1
    assert "not being shown to you now" in visual["note"]


def test_a_conversation_with_no_image_says_so(store: Engine) -> None:
    _, adapter = turn(store, "Good evening, Val.")
    visual = state(adapter)["visual_input"]
    assert (visual["state"], visual["bound_to_this_turn"], visual["earlier_in_conversation"]) == (
        "none",
        0,
        0,
    )


# --- classification ----------------------------------------------------------------


def test_the_effective_classification_is_the_strictest_of_text_and_acts(store: Engine) -> None:
    """§6 — an image is external egress exactly as text is; ambiguity resolves upward."""
    turn(
        store,
        "A public question.",
        classification=Classification.PUBLIC,
        attachments=(attach(classification=Classification.PROTECTED),),
    )
    # The act's own statement is what the egress record carries, self-contained,
    # even though the text of the turn was offered as public.
    assert rows(store, "model_call_image_inputs")[0]["stated_classification"] == "protected"


def test_the_strictest_rule_resolves_upward_over_every_act() -> None:
    def act(value: Classification) -> AttachmentAct:
        return AttachmentAct(
            act_id=uuid4(),
            attachment_id=uuid4(),
            position=1,
            given_filename="x.png",
            stated_classification=value,
            sha256="e" * 64,
            media_type="image/png",
            width=1,
            height=1,
            byte_size=1,
        )

    assert strictest(Classification.PUBLIC, ()) is Classification.PUBLIC
    assert strictest(Classification.PUBLIC, (act(Classification.INTERNAL),)) is (
        Classification.INTERNAL
    )
    assert strictest(Classification.PROTECTED, (act(Classification.PUBLIC),)) is (
        Classification.PROTECTED
    )
    assert (
        strictest(
            Classification.INTERNAL, (act(Classification.PUBLIC), act(Classification.PROTECTED))
        )
        is Classification.PROTECTED
    )
