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

import hashlib
import io
import json
from typing import Any
from unittest.mock import patch as patched
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
from val_domain.registry import by_slug
from val_gateway.attachments import AttachmentAct, CandidateAttachment, strictest
from val_gateway.context import STATE_ENVELOPE_MARKER
from val_gateway.loop import Turn, send
from val_policy.attachments import AdmissionRefusedError
from val_policy.budget import CONVERSATION_MAX_OUTPUT_TOKENS, maximum_cost, upper_bound_image_tokens
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


def _narrowed(**limits: object) -> tuple[object, ...]:
    """The real registry with only Sol's request-level limits narrowed."""
    from val_domain.registry import REGISTRY

    narrowed = []
    for config in REGISTRY:
        if config.slug == "gpt-5-6-sol-medium" and config.image_input is not None:
            support = config.image_input
            narrowed.append(
                config.model_copy(
                    update={
                        "image_input": support.model_copy(
                            update={
                                "provider_request": support.provider_request.model_copy(
                                    update=limits
                                )
                            }
                        )
                    }
                )
            )
        else:
            narrowed.append(config)
    return tuple(narrowed)


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
    original = png(2400, 2400)
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
    assert (binding["width"], binding["height"]) == (1600, 1600), "the largest square that fits"
    assert binding["transmitted_sha256"] != rows(store, "attachments")[0]["sha256"]

    blobs = {row["sha256"] for row in rows(store, "blobs")}
    assert len(blobs) == 2, "the original and the derived bytes, both kept"


def test_a_real_derivation_records_one_started_and_one_terminal_event(store: Engine) -> None:
    turn(store, "And this one?", attachments=(attach(png(2400, 2400)),))
    events = rows(store, "attachment_processing_events")
    assert [event["event"] for event in events] == ["started", "succeeded"]
    assert len({event["attempt_id"] for event in events}) == 1
    assert all(event["intent"] == "derive:model_input_image" for event in events)
    assert events[0]["representation_id"] is None
    assert events[1]["representation_id"] == rows(store, "attachment_representations")[0]["id"]
    assert all(event["error"] is None for event in events)


def test_an_unchanged_original_records_no_derivation_attempt(store: Engine) -> None:
    """Owner correction, 20 September 2026.

    The implementation previously wrote `derive:model_input_image started ->
    succeeded` even when the original went unchanged and no representation was
    produced — recording that a derivation succeeded when none occurred, which
    is a false statement in a table whose whole purpose is honest attempts. The
    honest record of a derivation that did not happen is silence.
    """
    _, adapter = turn(store, "What is in this?", attachments=(attach(png(320, 240)),))
    assert rows(store, "attachment_processing_events") == []
    assert rows(store, "attachment_representations") == []
    # And the image still went, unchanged, and is still bound to the call.
    assert sent_images(adapter)[0].content == rows(store, "blobs")[0]["bytes"]
    assert rows(store, "model_call_image_inputs")[0]["input_kind"] == "original"


def test_a_sixteen_by_nine_frame_is_transmitted_whole(store: Engine) -> None:
    """The correction's motivating case, end to end: no resize, no attempt, no loss."""
    payload = png(2048, 1152)
    _, adapter = turn(store, "Look at this frame.", attachments=(attach(payload),))
    assert sent_images(adapter)[0].content == payload
    assert rows(store, "attachment_processing_events") == []
    binding = rows(store, "model_call_image_inputs")[0]
    assert (binding["width"], binding["height"]) == (2048, 1152)
    assert binding["input_kind"] == "original"


def test_a_failed_derivation_records_started_then_failed_with_its_reason(
    store: Engine,
) -> None:
    """A real attempt that really failed is durable, with the reason it gave."""
    from unittest.mock import patch as patched

    from val_policy.attachments import AdmissionRefusedError

    with (
        patched(
            "val_gateway.attachments.plan_transmission",
            side_effect=AdmissionRefusedError("the derived image is still too large"),
        ),
        pytest.raises(AdmissionRefusedError),
    ):
        turn(store, "And this one?", attachments=(attach(png(2400, 2400)),))

    events = rows(store, "attachment_processing_events")
    assert [event["event"] for event in events] == ["started", "failed"]
    assert len({event["attempt_id"] for event in events}) == 1
    assert events[1]["error"] == "the derived image is still too large"
    assert events[1]["representation_id"] is None
    assert rows(store, "attachment_representations") == [], "nothing was produced"


def test_the_database_refuses_a_succeeded_derivation_that_produced_nothing(
    store: Engine,
) -> None:
    """The rule is structural, not merely observed (migration 0024, as corrected)."""
    turn(store, "Something.", attachments=(attach(),))
    attachment_id = rows(store, "attachments")[0]["id"]
    attempt = uuid4()
    with store.begin() as connection:
        connection.execute(
            text(
                "insert into attachment_processing_events (attachment_id, attempt_id, intent, "
                "event) values (:a, :t, 'derive:model_input_image', 'started')"
            ),
            {"a": attachment_id, "t": attempt},
        )
    with pytest.raises(Exception, match="succeeded_derivation_produces"), store.begin() as c:
        c.execute(
            text(
                "insert into attachment_processing_events (attachment_id, attempt_id, intent, "
                "event) values (:a, :t, 'derive:model_input_image', 'succeeded')"
            ),
            {"a": attachment_id, "t": attempt},
        )


def test_verify_keeps_its_own_meaning_and_produces_nothing(store: Engine) -> None:
    """`verify` succeeds without producing a representation, and is not invented
    to give an unchanged original something to point at."""
    turn(store, "Something.", attachments=(attach(),))
    attachment_id = rows(store, "attachments")[0]["id"]
    attempt = uuid4()
    with store.begin() as connection:
        for event in ("started", "succeeded"):
            connection.execute(
                text(
                    "insert into attachment_processing_events (attachment_id, attempt_id, "
                    "intent, event) values (:a, :t, 'verify', :e)"
                ),
                {"a": attachment_id, "t": attempt, "e": event},
            )
    verified = [e for e in rows(store, "attachment_processing_events") if e["intent"] == "verify"]
    assert [e["event"] for e in verified] == ["started", "succeeded"]
    assert all(e["representation_id"] is None for e in verified)


# --- current-turn binding ---------------------------------------------------------


def test_a_later_turn_does_not_retransmit_the_image(store: Engine) -> None:
    first, _ = turn(store, "What is in this?", attachments=(attach(),))
    _, adapter = turn(store, "Say more about it.", conversation_id=first.conversation.id)
    assert sent_images(adapter) == (), "the image is in the record, not in view"
    assert len(rows(store, "model_call_image_inputs")) == 1, "bound to the first call only"


def test_the_record_state_distinguishes_bound_from_merely_earlier(store: Engine) -> None:
    first, bound_adapter = turn(store, "What is in this?", attachments=(attach(),))
    # `bound` is untouched by the 22 September 2026 perception ruling, and this
    # gateway has no perception provider wired — so the Track C path is exactly
    # what it was. The additive `perceived_this_turn` is 0, which is the honest
    # count of media perceived locally on a turn whose pixels were transmitted.
    assert state(bound_adapter)["visual_input"] == {
        "state": "bound",
        "bound_to_this_turn": 1,
        "perceived_this_turn": 0,
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


# --- several images at once, and the request-level guard -------------------------


def test_several_images_keep_their_order_acts_and_digests(store: Engine) -> None:
    """Each image stays bound to its own act and its own transmitted bytes."""
    first, second, third = png(320, 240, "navy"), png(200, 150, "maroon"), png(64, 64, "olive")
    _, adapter = turn(
        store,
        "Compare these three.",
        attachments=(
            attach(first, "a.png"),
            attach(second, "b.png", Classification.INTERNAL),
            attach(third, "c.png"),
        ),
    )
    sent = sent_images(adapter)
    assert [image.content for image in sent] == [first, second, third], "order preserved"

    acts = sorted(rows(store, "message_attachments"), key=lambda row: row["position"])
    assert [act["given_filename"] for act in acts] == ["a.png", "b.png", "c.png"]
    assert [act["stated_classification"] for act in acts] == ["protected", "internal", "protected"]

    bindings = sorted(rows(store, "model_call_image_inputs"), key=lambda row: row["position"])
    assert len(bindings) == 3
    assert [b["position"] for b in bindings] == [1, 2, 3]
    # Each binding names its own act, its own attachment and its own digest.
    assert [b["message_attachment_id"] for b in bindings] == [a["id"] for a in acts]
    assert [b["attachment_id"] for b in bindings] == [a["attachment_id"] for a in acts]
    assert [b["transmitted_sha256"] for b in bindings] == [
        hashlib.sha256(payload).hexdigest() for payload in (first, second, third)
    ]
    assert len({b["transmitted_sha256"] for b in bindings}) == 3, "three distinct images"
    # And the act's own statement rides on its own binding.
    assert [b["stated_classification"] for b in bindings] == [
        "protected",
        "internal",
        "protected",
    ]


def test_every_image_of_the_turn_is_counted_in_the_reservation(store: Engine) -> None:
    """Not only the first: the bound covers each transmitted image and its margin.

    Measured over the images the turn *actually* transmitted, so this is the
    composition over a real turn rather than over invented parts. The arithmetic
    itself is pinned in the policy tests.
    """
    config = by_slug("gpt-5-6-sol-medium")
    assert config is not None
    _, adapter = turn(
        store,
        "Two of these.",
        attachments=(attach(png(320, 240)), attach(png(640, 480), "b.png")),
    )
    images = list(sent_images(adapter))
    assert len(images) == 2
    both = upper_bound_image_tokens(images, config)
    assert both == sum(upper_bound_image_tokens([image], config) for image in images)
    assert both > upper_bound_image_tokens(images[:1], config), "the second image counts"
    # And the whole-call bound is strictly larger than the same turn's text alone.
    text_only = maximum_cost(config, ("Two of these.",), CONVERSATION_MAX_OUTPUT_TOKENS)
    with_images = maximum_cost(
        config, ("Two of these.",), CONVERSATION_MAX_OUTPUT_TOKENS, images=images
    )
    assert with_images > text_only


def test_too_many_images_refuses_before_the_provider_is_reached(store: Engine) -> None:
    """The aggregate guard runs in Core, after derivation and before transmission."""
    narrow = _narrowed(max_images_per_request=2)
    adapter = answering("unused")
    with (
        patched("val_domain.registry.REGISTRY", narrow),
        pytest.raises(AdmissionRefusedError, match="provider request limit: image count"),
    ):
        send(
            store,
            build_gateway(store, adapter),
            "Three of these.",
            catalogue=catalogue(store),
            signals=ProjectSignals(explicit_no_project=True),
            attachments=tuple(attach(png(64, 64), f"{n}.png") for n in "abc"),
        )
    assert adapter.calls == 0, "the provider adapter was never invoked"
    assert rows(store, "model_call_image_inputs") == [], "no binding claims a transmission"


def test_too_much_image_data_refuses_before_the_provider_is_reached(store: Engine) -> None:
    narrow = _narrowed(max_total_payload_bytes=2_000)
    adapter = answering("unused")
    with (
        patched("val_domain.registry.REGISTRY", narrow),
        pytest.raises(AdmissionRefusedError) as refused,
    ):
        send(
            store,
            build_gateway(store, adapter),
            "Two large ones.",
            catalogue=catalogue(store),
            signals=ProjectSignals(explicit_no_project=True),
            attachments=(attach(png(400, 300)), attach(png(400, 300), "b.png")),
        )
    message = str(refused.value)
    assert "provider request limit: total image data" in message
    assert "measured conservatively by the house" in message, "the unit is undocumented"
    assert adapter.calls == 0, "the provider adapter was never invoked"
    assert rows(store, "model_call_image_inputs") == [], "no binding claims a transmission"


def test_a_refused_aggregate_leaves_the_admitted_evidence_it_truly_has(
    store: Engine,
) -> None:
    """The attachments were genuinely admitted; only the transmission is refused.

    The refusal does not pretend the files never arrived, and it does not write
    a binding claiming they were sent. Both statements are true at once, and the
    record keeps them apart.
    """
    narrow = _narrowed(max_images_per_request=1)
    adapter = answering("unused")
    with (
        patched("val_domain.registry.REGISTRY", narrow),
        pytest.raises(AdmissionRefusedError),
    ):
        send(
            store,
            build_gateway(store, adapter),
            "Two of these.",
            catalogue=catalogue(store),
            signals=ProjectSignals(explicit_no_project=True),
            attachments=(attach(png(64, 64)), attach(png(80, 80), "b.png")),
        )
    assert len(rows(store, "message_attachments")) == 2, "the acts happened"
    assert rows(store, "model_call_image_inputs") == [], "the transmission did not"
