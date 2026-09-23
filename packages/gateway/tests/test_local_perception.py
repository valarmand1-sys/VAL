# ruff: noqa: F811, F401 - fixtures imported by name
"""Local visual perception, end to end — owner ruling, 22 September 2026.

Seventeen proofs, one per numbered requirement of §28 of that order. Real
PostgreSQL, a stub cognition adapter, and a fake perception provider standing in
for the isolated MLX-VLM runtime: what is under test is Val Core's behaviour, not
Qwen3.5's eyesight, and Qwen3.5's eyesight was settled by the acceptance test
(`docs/reviews/qualification/runs/2026-09-22-qwen3_5-9b/`) rather than here.

The fake records every request it is given, so the assertions can be about what
actually reached the provider rather than about what the code looks like.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pytest
from gateway_fakes import StubAdapter
from PIL import Image
from sqlalchemy import Engine, text
from test_conversation_memory import (
    answering,
    build_gateway,
    catalogue,
    clean_personas,
    scope_of,
    seeded_conversation,
    store,
)

from val_domain.gateway import CapabilityProfile, Classification
from val_domain.perception import (
    PerceptionObservation,
    PerceptionRequest,
    PerceptionResult,
    PerceptionUnavailableError,
)
from val_domain.registry import by_slug
from val_gateway.attachments import CandidateAttachment
from val_gateway.context import STATE_ENVELOPE_MARKER
from val_gateway.loop import Turn, UnansweredTurn, perception_configuration, send
from val_gateway.perception import PERCEPTION_ENVELOPE_MARKER, handoffs_for, perception_prompt
from val_policy.project_resolution import ProjectSignals
from val_policy.routing import can_carry_images, is_admitted, satisfies_profile

PERCEPTION_SLUG = "qwen3-5-9b-mlx-4bit-mlxvlm-perception"

#: What the fake reports. Deliberately the shape of a grounded observation — a
#: description, not an answer and not advice.
OBSERVED = (
    "Three people are present: two adults and a child. The child is wearing a black "
    "top hat and a black cape. The adults are embracing the child. The setting is an "
    "indoor living room with a beige sofa."
)


def png(width: int = 320, height: int = 240, colour: str = "navy") -> bytes:
    buffer = io.BytesIO()
    image = Image.new("RGB", (width, height), colour)
    image.paste(Image.new("RGB", (width // 4, height // 4), "white"), (0, 0))
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def attach(content: bytes = b"", name: str = "family.png") -> CandidateAttachment:
    return CandidateAttachment(
        content=content or png(),
        given_filename=name,
        stated_classification=Classification.PROTECTED,
    )


@dataclass
class FakePerception:
    """The isolated visual runtime, standing still so Core can be measured.

    It records the exact `PerceptionRequest` it was handed — sources, question
    and the full transmitted prompt — because every assertion about targeting
    and about which bytes were perceived is an assertion about that object.
    """

    observation: str = OBSERVED
    failure: Exception | None = None
    requests: list[PerceptionRequest] = field(default_factory=list)
    released: int = 0
    #: What this stand-in is admitted for, exactly as a real specialist declares
    #: it. Core routes on this, so the fake has to carry it too.
    modalities: frozenset[str] = frozenset({"image", "video"})

    def perceive(self, request: PerceptionRequest) -> PerceptionResult:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return PerceptionResult(
            observations=tuple(
                PerceptionObservation(
                    source_sha256=source.sha256,
                    modality=source.modality,
                    text=self.observation,
                )
                for source in request.sources
            ),
            provider="mlxvlm",
            model_identifier="lmstudio-community/Qwen3.5-9B-MLX-4bit",
            model_revision="b455506b0f574c74616dbcd56879bde38fafcff3",
            quantization="4-bit, group size 64, affine (MLX)",
            runtime="mlx-vlm",
            runtime_version="0.7.2",
            generation={"max_tokens": 2048, "temperature": 0.0, "repetition_penalty": None},
            duration_seconds=28.1,
            cost_usd=0.0,
            local=True,
            reasoning_separated=True,
        )

    def release(self) -> None:
        self.released += 1


def turn(
    store: Engine,
    content: str,
    *,
    attachments: tuple[CandidateAttachment, ...] = (),
    conversation_id: UUID | None = None,
    perception: FakePerception | None = None,
) -> tuple[Any, StubAdapter, FakePerception]:
    """One ordinary turn, with local perception wired as the application wires it."""
    eyes = perception or FakePerception()
    adapter = answering("Three of them, my lord, and the boy is in costume.")
    gateway = build_gateway(store, adapter)
    gateway.perception = (eyes,)
    outcome = send(
        store,
        gateway,
        content,
        catalogue=catalogue(store),
        signals=None if conversation_id else ProjectSignals(explicit_no_project=True),
        conversation_id=conversation_id,
        attachments=attachments,
    )
    return outcome, adapter, eyes


def rows(store: Engine, table: str) -> list[Any]:
    with store.connect() as connection:
        return list(connection.execute(text(f"select * from {table}")).mappings())  # noqa: S608


def record_state(adapter: StubAdapter) -> dict[str, Any]:
    block = next(m for m in adapter.sent_messages if m.content.startswith(STATE_ENVELOPE_MARKER))
    return json.loads(block.content.split("\n", 1)[1])["prior_record_state"]


def perception_envelope(adapter: StubAdapter) -> dict[str, Any]:
    block = next(
        m for m in adapter.sent_messages if m.content.startswith(PERCEPTION_ENVELOPE_MARKER)
    )
    parsed: dict[str, Any] = json.loads(block.content.split("\n", 1)[1])
    return parsed


def sent_images(adapter: StubAdapter) -> tuple[Any, ...]:
    return tuple(part for message in adapter.sent_messages for part in message.images)


# --- 1. a normal governed image turn selects admitted local perception -----------


def test_a_normal_image_turn_selects_the_admitted_local_perception_route(store: Engine) -> None:
    """§28.1. The route is chosen by the profile it declares, never by its name."""
    config = perception_configuration(Classification.PROTECTED, "visual")
    assert config is not None and config.slug == PERCEPTION_SLUG
    assert is_admitted(config)
    assert satisfies_profile(config, CapabilityProfile.PERCEPTION)
    assert config.hosting.value == "local" and config.cost_per_mtok_in_usd == 0.0

    outcome, _, eyes = turn(store, "What is in this?", attachments=(attach(),))
    assert isinstance(outcome, Turn)
    assert len(eyes.requests) == 1, "the local route was used, once"

    run = rows(store, "perception_runs")
    assert len(run) == 1
    assert run[0]["provider"] == "mlxvlm"
    assert run[0]["model_config_id"] == config.id
    assert run[0]["current_perception_state"] == "perceived"
    assert run[0]["local"] is True and run[0]["cost_usd"] == 0


# --- 2. the correct attachment reaches perception --------------------------------


def test_the_correct_attachment_reaches_perception(store: Engine) -> None:
    """§28.2. By digest, and by bytes — not by trusting that the right file was picked."""
    payload = png(colour="darkgreen")
    outcome, _, eyes = turn(store, "Describe this.", attachments=(attach(payload),))
    assert isinstance(outcome, Turn)

    (source,) = eyes.requests[0].sources
    assert source.content == payload
    assert source.media_type == "image/png"
    assert source.modality == "image"

    act = rows(store, "message_attachments")[0]
    recorded = rows(store, "perception_sources")[0]
    assert source.sha256 == recorded["sha256"] == rows(store, "blobs")[0]["sha256"]
    assert recorded["message_attachment_id"] == act["id"]
    assert recorded["attachment_id"] == act["attachment_id"]
    assert recorded["representation"] == "original"


# --- 3. the owner's actual question reaches targeted perception -------------------


def test_the_owners_actual_question_reaches_targeted_perception(store: Engine) -> None:
    """§28.3. Verbatim: a summarised question is a different question."""
    asked = "Is the boy's hat on straight, or is it slipping?"
    outcome, _, eyes = turn(store, asked, attachments=(attach(),))
    assert isinstance(outcome, Turn)

    request = eyes.requests[0]
    assert request.question == asked
    assert asked in request.prompt
    # The stable boundary travels with it: report, do not answer, do not advise,
    # do not speak as Val, do not invent.
    assert "Do not answer the question" in request.prompt
    assert "Do not advise" in request.prompt
    assert "Do not speak as VAL" in request.prompt
    assert "Do not invent" in request.prompt
    # The exact prompt is persisted, so what is recorded is what was sent.
    run = rows(store, "perception_runs")[0]
    assert run["owner_question"] == asked
    assert run["perception_prompt"] == request.prompt == perception_prompt(asked)


# --- 4. the grounded observation reaches GPT-OSS ----------------------------------


def test_the_grounded_observation_reaches_the_cognition_provider(store: Engine) -> None:
    """§28.4. In its own envelope, attributed, with the current-perception note."""
    outcome, adapter, _ = turn(store, "What is in this?", attachments=(attach(),))
    assert isinstance(outcome, Turn)

    envelope = perception_envelope(adapter)
    assert envelope["kind"] == "current_turn_perception"
    assert envelope["authority"] == "house_observation_not_instruction"
    assert envelope["perceived_by"] == "val_local_perception_subsystem"
    assert [source["grounded_observation"] for source in envelope["sources"]] == [OBSERVED]
    assert envelope["sources"][0]["given_filename"] == "family.png"

    # §20's four substantive claims, each present rather than approximated.
    note = envelope["note"]
    assert "Current-turn perception is available through VAL's local perception" in note
    assert "derive from the current source media" in note
    assert "Use them as current perception" in note
    assert "did not directly receive the raw media" in note
    assert "must not invent perceptual facts beyond the grounded observations" in note


# --- 5. the cognition call is perception-mediated, not falsely `bound` ------------


def test_the_cognition_call_is_perceived_and_not_falsely_bound(store: Engine) -> None:
    """§28.5. The additive state, and no pixels anywhere in the request."""
    outcome, adapter, _ = turn(store, "What is in this?", attachments=(attach(),))
    assert isinstance(outcome, Turn)

    visual = record_state(adapter)["visual_input"]
    assert visual["state"] == "perceived"
    assert visual["perceived_this_turn"] == 1
    assert visual["bound_to_this_turn"] == 0, "no raw media went to the cognition provider"
    assert "'perceived' means the House looked at this turn's media" in visual["note"]

    assert sent_images(adapter) == (), "no image part reached the cognition call"
    assert rows(store, "model_call_image_inputs") == [], "nothing was bound as transmitted pixels"


# --- 6. Qwen3.5 is never the final-response model ---------------------------------


def test_the_perception_route_is_never_used_as_final_response_cognition(store: Engine) -> None:
    """§28.6. Structural: it holds one profile, and it holds no other."""
    config = by_slug(PERCEPTION_SLUG)
    assert config is not None
    assert config.capability_profiles == frozenset({CapabilityProfile.PERCEPTION})
    for profile in (
        CapabilityProfile.PARTNER,
        CapabilityProfile.STRUCTURED,
        CapabilityProfile.STRIP,
    ):
        assert not satisfies_profile(config, profile)

    outcome, _, _ = turn(store, "What is in this?", attachments=(attach(),))
    assert isinstance(outcome, Turn)
    # Every recorded cognition call went somewhere else.
    for call in rows(store, "model_calls"):
        assert call["model_config_id"] != config.id


# --- 9 and 10. a later text-only turn ---------------------------------------------


def test_a_text_only_follow_up_uses_stored_perception_without_reinspecting(
    store: Engine,
) -> None:
    """§28.9 and §28.10 together, because they are one behaviour seen from two sides.

    The stored observation is in the record and is not re-perceived; the earlier
    media are not silently re-read; and nothing lets the cognition provider reach
    for the raw bytes on its own.
    """
    first, _, eyes = turn(store, "What is in this?", attachments=(attach(),))
    assert isinstance(first, Turn)
    assert len(eyes.requests) == 1

    second, follow_up, _ = turn(
        store,
        "How many people did you say there were?",
        conversation_id=first.conversation.id,
        perception=eyes,
    )
    assert isinstance(second, Turn)

    # §28.10 — no autonomous raw-media access. Perception did not run again, no
    # second run row exists, and no image part reached the cognition call.
    assert len(eyes.requests) == 1, "the follow-up did not reinspect"
    assert len(rows(store, "perception_runs")) == 1
    assert sent_images(follow_up) == ()

    # §28.9 — what is available to the follow-up is the stored record: the
    # earlier exchange, in history, with the observation Val already gave.
    state = record_state(follow_up)["visual_input"]
    assert state["state"] == "earlier_only", "in the record, not in view"
    assert state["perceived_this_turn"] == 0
    assert state["earlier_in_conversation"] == 1
    stored = rows(store, "perception_runs")[0]
    assert stored["observation"] == OBSERVED
    assert stored["message_id"] == first.user_message.id


# --- 11. a healthy local route prevents silent paid perception --------------------


def test_a_healthy_local_route_prevents_silent_paid_perception(store: Engine) -> None:
    """§28.11. The paid image-capable route still exists, and is not used for this."""
    sol = by_slug("gpt-5-6-sol-medium")
    assert sol is not None and can_carry_images(sol), "Sol's declared capability is untouched"

    outcome, adapter, _ = turn(store, "What is in this?", attachments=(attach(),))
    assert isinstance(outcome, Turn)
    # No image reached any provider, so no image-capable route was needed and
    # none was pinned for the image's sake.
    assert sent_images(adapter) == ()
    assert rows(store, "model_call_image_inputs") == []
    run = rows(store, "perception_runs")[0]
    assert run["cost_usd"] == 0 and run["local"] is True


# --- 12. one bounded recovery attempt, then fail closed ---------------------------


def test_a_runtime_failure_gets_one_bounded_recovery_then_fails_closed(store: Engine) -> None:
    """§28.12. The recovery belongs to the adapter; Core's job is to stop honestly.

    What is proved here is the stopping: the turn ends unanswered, the user's
    message survives, no perception row is written, and — the part that matters —
    **no cognition call happens at all**, so the media cannot have gone anywhere.
    """
    broken = FakePerception(
        failure=PerceptionUnavailableError(
            "local visual perception failed twice and is not available. "
            "Nothing was sent to any paid provider and nothing was charged."
        )
    )
    outcome, adapter, _ = turn(
        store, "What is in this?", attachments=(attach(),), perception=broken
    )
    assert isinstance(outcome, UnansweredTurn)
    assert "failed twice" in str(outcome.error)
    assert "Nothing was sent to any paid provider" in str(outcome.error)

    assert tuple(adapter.sent_messages) == (), "no cognition call was made"
    assert rows(store, "perception_runs") == []
    assert rows(store, "model_calls") == []
    # The message was said, so it is history. The act and the bytes are too.
    assert len(rows(store, "messages")) == 1
    assert len(rows(store, "message_attachments")) == 1


# --- 13. no Terminal, no manual runtime action ------------------------------------


def test_ordinary_owner_use_requires_no_terminal_or_manual_runtime_action(
    store: Engine,
) -> None:
    """§28.13. The whole mechanism is inside one `send`, with nothing to start first.

    The adapter's own argument vector is checked in `test_perception_adapter.py`;
    what this proves is the shape of the call site — one ordinary turn, no
    activation step, no load step, no unload step, nothing for the owner to do.
    """
    from val_providers.mlxvlm_perception import MLXVLMPerception

    outcome, _, eyes = turn(store, "What is in this?", attachments=(attach(),))
    assert isinstance(outcome, Turn)
    assert outcome.val_message.content
    assert len(eyes.requests) == 1

    # The real provider needs no `start`, no `load` and no `ensure_ready`: there
    # is no daemon and no resident model, so there is nothing to bring up.
    real = MLXVLMPerception()
    assert not hasattr(real, "start")
    assert not hasattr(real, "ensure_ready")
    assert hasattr(real, "perceive") and hasattr(real, "release")


# --- 14 and 15. resources are released, and GPT-OSS resumes -----------------------


def test_visual_resources_release_and_cognition_continues_afterwards(store: Engine) -> None:
    """§28.14 and §28.15. Sequential residency, seen from Core's side.

    The measured proof is in the qualification record — wired memory 13.10 GB
    during perception, 2.97 GB after the process exited, GPT-OSS reloaded at its
    registered 32,768-token window in 10.7 s. What Core must show is that the two
    take turns: a perception turn, then ordinary cognition, then another
    perception turn, with no residency held in between and nothing to reset.
    """
    first, _, eyes = turn(store, "What is in this?", attachments=(attach(),))
    assert isinstance(first, Turn)

    text_turn, _, _ = turn(
        store,
        "And what should I do about it?",
        conversation_id=first.conversation.id,
        perception=eyes,
    )
    assert isinstance(text_turn, Turn)
    assert text_turn.val_message.content, "ordinary cognition still works afterwards"
    assert len(eyes.requests) == 1, "a text turn does not touch the visual runtime"

    again, _, _ = turn(
        store,
        "Here is another.",
        attachments=(attach(png(colour="maroon"), "second.png"),),
        conversation_id=first.conversation.id,
        perception=eyes,
    )
    assert isinstance(again, Turn)
    assert len(eyes.requests) == 2, "the visual runtime is invoked again on a later image"
    assert len(rows(store, "perception_runs")) == 2


# --- 16. historical `bound` semantics are unchanged -------------------------------


def test_historical_bound_semantics_are_unchanged(store: Engine) -> None:
    """§28.16, and the fail-closed rule of the execution order together.

    `bound` keeps its meaning exactly — raw media supplied directly to the
    cognition provider — it keeps its place in the vocabulary, and the machinery
    that produces it is untouched and still proved in `test_image_turns.py`.
    What is *not* preserved, deliberately, is the fall-through: with a perception
    route admitted and no local provider wired, a media turn **fails closed**
    rather than quietly reverting to sending pixels to a paid provider. A missing
    local adapter is a misconfigured house, not permission.
    """
    from val_domain.schema import PerceptionState

    assert list(PerceptionState.enums) == ["perceived", "bound"]

    adapter = answering("A navy field, my lord.")
    gateway = build_gateway(store, adapter)
    assert gateway.perception == (), "the admitted route's provider is not wired"
    outcome = send(
        store,
        gateway,
        "What is in this?",
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
        attachments=(attach(),),
    )
    assert isinstance(outcome, UnansweredTurn)
    assert "no local visual-perception provider is wired" in str(outcome.error)
    assert "nothing was charged" in str(outcome.error)
    assert tuple(adapter.sent_messages) == (), "no cognition call, so no pixels anywhere"
    assert rows(store, "model_call_image_inputs") == [], "nothing was transmitted as pixels"

    # And the Track C path itself, in the world it belongs to: no admitted
    # perception route. Same machinery, same `bound`, same binding row.
    import val_gateway.loop as loop

    original = loop.perception_configuration
    loop.perception_configuration = lambda *_: None  # type: ignore[assignment]
    try:
        track_c_adapter = answering("A navy field, my lord.")
        track_c = send(
            store,
            build_gateway(store, track_c_adapter),
            "And this one?",
            catalogue=catalogue(store),
            signals=ProjectSignals(explicit_no_project=True),
            attachments=(attach(png(colour="teal"), "teal.png"),),
        )
    finally:
        loop.perception_configuration = original  # type: ignore[assignment]

    assert isinstance(track_c, Turn)
    visual = record_state(track_c_adapter)["visual_input"]
    assert visual["state"] == "bound"
    assert visual["bound_to_this_turn"] == 1
    assert visual["perceived_this_turn"] == 0
    assert len(sent_images(track_c_adapter)) == 1, "the pixels were transmitted, as before"
    assert len(rows(store, "model_call_image_inputs")) == 1


# --- 17. historical evidence is unchanged -----------------------------------------


def test_historical_sol_track_c_and_failed_candidate_evidence_is_unchanged() -> None:
    """§28.17. Nothing about the earlier record was edited to make room for this."""
    sol = by_slug("gpt-5-6-sol-medium")
    assert sol is not None
    assert sol.image_input is not None, "Sol's Track C image capability stands"
    assert is_admitted(sol) and satisfies_profile(sol, CapabilityProfile.PARTNER)

    # The failed candidates' records: registered, never admitted, no profile.
    for slug in (
        "gpt-oss-20b-mxfp4-mlx-lmstudio",
        "qwen3-8-27b-mlx-6bit-lmstudio",
    ):
        entry = by_slug(slug)
        assert entry is not None, f"{slug} is preserved"
        assert not is_admitted(entry)
        assert entry.capability_profiles == frozenset()

    # The local Partner admission of 21 September is untouched by this one.
    partner = by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio-partner")
    assert partner is not None
    assert partner.capability_profiles == frozenset({CapabilityProfile.PARTNER})
    assert len(partner.known_weaknesses) == 3, "the Stage A findings are still carried"


# --- 7 and 8. the consequential turn ----------------------------------------------
#
# These two need the deliberation orchestrator rather than the ordinary loop, so
# they live beside the rest of that machinery — but they are §28.7 and §28.8 and
# they are named here so the seventeen can be counted in one place.


def test_seven_and_eight_are_proved_in_the_deliberation_suite() -> None:
    """§28.7 and §28.8 — one perception per consequential turn, identical grounding.

    Proved in `test_deliberation_machinery.py`, against the real orchestrator:
    `test_a_consequential_media_turn_perceives_once` and
    `test_the_blind_position_and_the_final_answer_receive_identical_grounding`.
    The database backs both independently — `perception_runs.message_id` is
    unique, so a second run for one turn cannot be written even by mistake.
    """
    from val_domain import schema

    unique = {
        constraint.name
        for constraint in schema.PerceptionRun.__table__.constraints
        if constraint.name is not None
    }
    assert "uq_perception_runs_message" in unique


# --- the record, whole -------------------------------------------------------------


def test_the_provenance_record_holds_everything_the_ruling_lists(store: Engine) -> None:
    """§26, as a single readable row rather than as a promise."""
    asked = "What is going on here?"
    outcome, _, _ = turn(store, asked, attachments=(attach(),))
    assert isinstance(outcome, Turn)

    run = rows(store, "perception_runs")[0]
    source = rows(store, "perception_sources")[0]
    config = by_slug(PERCEPTION_SLUG)
    assert config is not None

    assert run["conversation_id"] == outcome.conversation.id
    assert run["message_id"] == outcome.user_message.id
    assert run["model_config_id"] == config.id
    assert run["provider"] == "mlxvlm"
    assert run["model_identifier"] == "lmstudio-community/Qwen3.5-9B-MLX-4bit"
    assert run["model_revision"] == "b455506b0f574c74616dbcd56879bde38fafcff3"
    assert run["quantization"] == "4-bit, group size 64, affine (MLX)"
    assert run["runtime"] == "mlx-vlm" and run["runtime_version"] == "0.7.2"
    assert run["generation"]["max_tokens"] == 2048
    assert run["generation"]["repetition_penalty"] is None
    assert run["owner_question"] == asked
    assert asked in run["perception_prompt"]
    assert run["observation"] == OBSERVED
    assert run["current_perception_state"] == "perceived"
    assert run["local"] is True and run["cost_usd"] == 0
    assert run["duration_ms"] > 0 and run["reasoning_separated"] is True

    assert source["modality"] == "image" and source["media_type"] == "image/png"
    assert source["byte_size"] > 0 and len(source["sha256"]) == 64
    assert source["observation"] == OBSERVED

    # OBSERVATION -> COGNITION: the response call is on record as having been
    # grounded in this run.
    with store.connect() as connection:
        received = handoffs_for(connection, UUID(str(run["id"])))
    assert len(received) == 1
    assert received[0] == outcome.response.model_call_id


def test_the_grounded_observation_is_not_stored_as_an_ordinary_chat_message(
    store: Engine,
) -> None:
    """§26's closing rule: it is evidence, not something Val said."""
    outcome, _, _ = turn(store, "What is in this?", attachments=(attach(),))
    assert isinstance(outcome, Turn)
    contents = [row["content"] for row in rows(store, "messages")]
    assert OBSERVED not in contents
    assert rows(store, "perception_runs")[0]["observation"] == OBSERVED


def test_a_perception_row_cannot_be_edited_or_deleted(store: Engine) -> None:
    """Append-only, under the standing Layer 0 guards."""
    outcome, _, _ = turn(store, "What is in this?", attachments=(attach(),))
    assert isinstance(outcome, Turn)
    run_id = rows(store, "perception_runs")[0]["id"]
    with pytest.raises(Exception, match=r"evidence|immutable|cannot"):
        with store.begin() as connection:
            connection.execute(
                text("update perception_runs set observation = 'something else' where id = :i"),
                {"i": run_id},
            )
    with pytest.raises(Exception, match=r"delete|evidence|cannot"):
        with store.begin() as connection:
            connection.execute(text("delete from perception_runs where id = :i"), {"i": run_id})


# --- OP-3, reviewed at its own checkpoint -----------------------------------------


def _shape(adapter: StubAdapter) -> list[str]:
    """What each assembled message is, by kind rather than by content."""
    from val_gateway.context import MEMORY_ENVELOPE_MARKER

    kinds = []
    for message in adapter.sent_messages:
        if message.content.startswith(MEMORY_ENVELOPE_MARKER):
            kinds.append("recall_envelope")
        elif message.content.startswith(STATE_ENVELOPE_MARKER):
            kinds.append("record_state_envelope")
        elif message.content.startswith(PERCEPTION_ENVELOPE_MARKER):
            kinds.append("perception_envelope")
        else:
            kinds.append(f"turn:{message.role}")
    return kinds


def test_the_assembled_request_contains_exactly_the_enumerated_parts(store: Engine) -> None:
    """OP-3's closure condition, landing at the checkpoint that made it meaningful.

    Recorded 1 September 2026: an exact-composition assertion was declined then
    because it would have asserted the absence of a feature that did not exist.
    The perception envelope is the first non-conversation context block to arrive
    since — a real one, added by this very change — so the assertion is now worth
    what it claims. Any later addition must name itself here.

    The system channel is pinned byte-exact elsewhere; this is the message
    channel, which was only ever asserted piecewise.
    """
    text_turn, plain, eyes = turn(store, "Good morning.")
    assert isinstance(text_turn, Turn)
    assert _shape(plain) == ["record_state_envelope", "turn:user"]

    image_turn, seen, _ = turn(
        store,
        "And what is in this?",
        attachments=(attach(),),
        conversation_id=text_turn.conversation.id,
        perception=eyes,
    )
    assert isinstance(image_turn, Turn)
    assert _shape(seen) == [
        "turn:user",
        "turn:assistant",
        "record_state_envelope",
        "perception_envelope",
        "turn:user",
    ], "history, the record state, the perception it describes, then the turn"


# --- video and audio join the owner's path — execution order, 22 September 2026 ----


def mp4(seconds: float = 9.0) -> bytes:
    """A minimal, structurally valid MP4, built the way the admission reads one."""
    import struct

    def box(name: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body) + 8) + name + body

    mvhd = box(
        b"mvhd",
        bytes(4)
        + struct.pack(">I", 0)
        + struct.pack(">I", 0)
        + struct.pack(">I", 1000)
        + struct.pack(">I", int(seconds * 1000))
        + bytes(80),
    )
    return b"".join(
        [
            box(b"ftyp", b"isom" + struct.pack(">I", 512) + b"isomiso2mp41"),
            box(b"moov", mvhd),
            box(b"mdat", bytes(64)),
        ]
    )


def wav(seconds: float = 2.0) -> bytes:
    import io as _io
    import wave as _wave

    buffer = _io.BytesIO()
    with _wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16_000)
        writer.writeframes(b"\x00\x00" * int(16_000 * seconds))
    return buffer.getvalue()


@dataclass
class FakeEars:
    """The audio specialist, declaring audio and nothing else."""

    observation: str = "A woman says the number is forty-two and to bring the red envelope."
    requests: list[PerceptionRequest] = field(default_factory=list)
    modalities: frozenset[str] = frozenset({"audio"})

    def perceive(self, request: PerceptionRequest) -> PerceptionResult:
        self.requests.append(request)
        return PerceptionResult(
            observations=tuple(
                PerceptionObservation(
                    source_sha256=source.sha256, modality="audio", text=self.observation
                )
                for source in request.sources
            ),
            provider="llamacpp-omni",
            model_identifier="ggml-org/Qwen3-Omni-30B-A3B-Instruct-GGUF",
            model_revision="6e35a28f4a19b18730f8949b0c579c6429649ab8",
            quantization="Q4_K_M (language model), Q8_0 (projector)",
            runtime="llama.cpp",
            runtime_version="0.4.1 (build 10964, commit b29c606e2)",
            generation={"context_tokens": 16384, "sampling_arguments_passed": []},
            duration_seconds=3.5,
            cost_usd=0.0,
            local=True,
            reasoning_separated=True,
        )

    def release(self) -> None:
        return None


def multimodal_turn(
    store: Engine,
    content: str,
    *,
    attachments: tuple[CandidateAttachment, ...],
    eyes: FakePerception | None = None,
    ears: FakeEars | None = None,
    conversation_id: UUID | None = None,
) -> tuple[Any, StubAdapter, FakePerception, FakeEars]:
    """A turn with both specialists wired, exactly as the application wires them."""
    eyes = eyes or FakePerception()
    ears = ears or FakeEars()
    adapter = answering("Noted, my lord.")
    gateway = build_gateway(store, adapter)
    gateway.perception = (eyes, ears)
    outcome = send(
        store,
        gateway,
        content,
        catalogue=catalogue(store),
        signals=None if conversation_id else ProjectSignals(explicit_no_project=True),
        conversation_id=conversation_id,
        attachments=attachments,
    )
    return outcome, adapter, eyes, ears


def test_a_video_turn_reaches_the_visual_specialist_and_not_the_audio_one(
    store: Engine,
) -> None:
    """§5. Governed MP4 ingestion, end to end, on the ordinary owner path."""
    clip = mp4(seconds=9.0)
    outcome, adapter, eyes, ears = multimodal_turn(
        store,
        "What happens in this clip?",
        attachments=(
            CandidateAttachment(
                content=clip,
                given_filename="sequence.mp4",
                stated_classification=Classification.PROTECTED,
            ),
        ),
    )
    assert isinstance(outcome, Turn)
    assert len(eyes.requests) == 1 and ears.requests == [], "the video went to the eyes"
    (perceived,) = eyes.requests[0].sources
    assert perceived.modality == "video" and perceived.media_type == "video/mp4"
    assert perceived.content == clip

    run = rows(store, "perception_runs")[0]
    source = rows(store, "perception_sources")[0]
    assert run["current_perception_state"] == "perceived"
    assert source["modality"] == "video"
    assert float(source["duration_seconds"]) == 9.0
    assert source["verified"] == "container_structure", "a container walk, honestly named"

    # No raw video anywhere near the cognition call.
    assert sent_images(adapter) == ()
    envelope = perception_envelope(adapter)
    assert envelope["sources"][0]["modality"] == "video"
    visual = record_state(adapter)["visual_input"]
    assert visual["state"] == "perceived" and visual["perceived_this_turn"] == 1


def test_an_audio_turn_reaches_the_audio_specialist_and_not_the_visual_one(
    store: Engine,
) -> None:
    """§9 and §10. Governed WAV ingestion, with the audio doctrine in the prompt."""
    recording = wav(seconds=2.0)
    asked = "What did she say about the envelope?"
    outcome, _, eyes, ears = multimodal_turn(
        store,
        asked,
        attachments=(
            CandidateAttachment(
                content=recording,
                given_filename="note.wav",
                stated_classification=Classification.PROTECTED,
            ),
        ),
    )
    assert isinstance(outcome, Turn)
    assert len(ears.requests) == 1 and eyes.requests == [], "the recording went to the ears"
    request = ears.requests[0]
    (perceived,) = request.sources
    assert perceived.modality == "audio" and perceived.media_type == "audio/wav"
    assert perceived.content == recording

    # §10's doctrine, in the verbs that fit a recording.
    assert request.question == asked and asked in request.prompt
    assert "audio perception component" in request.prompt
    assert "Do not answer the question" in request.prompt
    assert "Do not invent anything that was not said" in request.prompt
    assert "If the recording does not establish" in request.prompt
    assert "visible" not in request.prompt, "a recording is not visible"

    run = rows(store, "perception_runs")[0]
    assert run["provider"] == "llamacpp-omni"
    assert run["perception_prompt"] == request.prompt
    assert run["local"] is True and run["cost_usd"] == 0
    source = rows(store, "perception_sources")[0]
    assert source["modality"] == "audio"
    assert float(source["duration_seconds"]) == 2.0
    assert source["verified"] == "decoded_header"


def test_a_recording_is_reported_as_audio_and_never_as_visual_input(
    store: Engine,
) -> None:
    """§7. The envelope does not call a recording something Val can see."""
    outcome, adapter, _, _ = multimodal_turn(
        store,
        "What is on this recording?",
        attachments=(
            CandidateAttachment(
                content=wav(),
                given_filename="note.wav",
                stated_classification=Classification.PROTECTED,
            ),
        ),
    )
    assert isinstance(outcome, Turn)
    state = record_state(adapter)
    assert state["visual_input"]["state"] == "none", "nothing was seen"
    assert state["visual_input"]["perceived_this_turn"] == 0
    audio = state["audio_input"]
    assert audio["state"] == "perceived"
    assert audio["perceived_this_turn"] == 1
    assert "presently hear" in audio["note"]


def test_a_conversation_with_no_audio_never_mentions_audio(store: Engine) -> None:
    """The per-turn necessity rule: a field restating nothing is context spent on nothing."""
    outcome, adapter, _ = turn(store, "Good morning.")
    assert isinstance(outcome, Turn)
    assert "audio_input" not in record_state(adapter)
    assert "visual_input" in record_state(adapter), "the visual field is unchanged"


def test_audio_beside_visual_material_fails_closed_and_says_exactly_why(
    store: Engine,
) -> None:
    """§6. The refusal names mixed audio-and-visual attachment, not "failed"."""
    outcome, adapter, eyes, ears = multimodal_turn(
        store,
        "Compare these.",
        attachments=(
            CandidateAttachment(
                content=png(),
                given_filename="frame.png",
                stated_classification=Classification.PROTECTED,
            ),
            CandidateAttachment(
                content=wav(),
                given_filename="note.wav",
                stated_classification=Classification.PROTECTED,
            ),
        ),
    )
    assert isinstance(outcome, UnansweredTurn)
    said = str(outcome.error)
    assert "audio and visual material together" in said
    assert "different local specialists" in said
    assert "separate turns" in said
    assert "single-modality turns are fully supported" in said

    # Nothing ran, nothing was sent, nothing was perceived.
    assert eyes.requests == [] and ears.requests == []
    assert tuple(adapter.sent_messages) == ()
    assert rows(store, "perception_runs") == []
    # The message and both acts are history: they were sent.
    assert len(rows(store, "messages")) == 1
    assert len(rows(store, "message_attachments")) == 2


def test_the_specialists_are_chosen_by_declaration_not_by_order(store: Engine) -> None:
    """A model's name and its encoders say nothing; its declaration decides."""
    from val_gateway.loop import perception_configuration, perception_provider_for

    visual = perception_configuration(Classification.PROTECTED, "visual")
    audio = perception_configuration(Classification.PROTECTED, "audio")
    assert visual is not None and audio is not None and visual.slug != audio.slug
    assert visual.perception_modalities == frozenset({"image", "video"})
    assert audio.perception_modalities == frozenset({"audio"})

    eyes, ears = FakePerception(), FakeEars()
    adapter = answering("Noted.")
    gateway = build_gateway(store, adapter)
    # Deliberately audio-first, so position cannot be what decides.
    gateway.perception = (ears, eyes)
    assert perception_provider_for(gateway, "visual") is eyes
    assert perception_provider_for(gateway, "audio") is ears
