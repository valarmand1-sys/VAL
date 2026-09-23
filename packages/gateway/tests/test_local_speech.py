# ruff: noqa: F811, F401 - fixtures imported by name
"""Val's voice, through Core — owner execution order, 22 September 2026.

Real PostgreSQL, a fake speech provider standing in for the isolated MLX-Audio
runtime. What is under test is Val Core's behaviour, not Qwen3-TTS's voice: the
voice was settled by the acceptance generations
(`docs/reviews/qualification/runs/2026-09-22-local-voice/`), and the thing that
has to hold here is that **what is spoken is what Val already said**, in the
governed voice, recorded honestly, and never anywhere near a cloud.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pytest
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

from val_domain.gateway import CapabilityProfile, ModelConfig
from val_domain.registry import by_slug
from val_domain.speech import (
    SpeechRefusedError,
    SpeechRequest,
    SpeechResult,
    SpeechUnavailableError,
    VoiceConditioning,
    digest_of,
)
from val_gateway.loop import Turn, send
from val_gateway.speech import register_voice, speak, speak_message
from val_policy.project_resolution import ProjectSignals
from val_policy.routing import is_admitted, satisfies_profile

SPEECH_SLUG = "qwen3-tts-12hz-1-7b-base-8bit-mlxaudio-speech"
REFERENCE = b"RIFF" + b"\x00" * 60 + b"the canonical locally designed reference"
CLONE_PROMPT_DIGEST = "c" * 64

DESCRIBED: dict[str, Any] = {
    "reference_sample_rate": 24000,
    "reference_duration_seconds": 8.24,
    "designed_by_quantization": "8-bit MLX, group size 64, affine",
    "designed_by_runtime": "mlx-audio 0.5.5",
    "designed_generation": {"temperature": 0.9, "kwargs_passed_to_generate": []},
    "origin": (
        "Generated locally by Qwen3-TTS VoiceDesign from the owner's frozen textual "
        "description. No ElevenLabs audio was used as conditioning input."
    ),
    "identity_claim": (
        "Independently designed. NOT claimed to be an acoustic clone of the historical "
        "ElevenLabs voice. Identity is not model-verified."
    ),
}


def a_voice() -> VoiceConditioning:
    return VoiceConditioning(
        name="val-local-v1",
        reference_audio=REFERENCE,
        reference_sha256=digest_of(REFERENCE),
        reference_text="Good evening, my lord. I have finished the work.",
        voice_description="Adult British woman. Kind, intelligent, warm, gentle.",
        designed_by_model="mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit",
        designed_by_revision="f90d617701d9f7f4ca499291e0b57f2b3c2fd2ee",
    )


@dataclass
class FakeVoice:
    """The speech runtime, standing still so Core can be measured."""

    failure: Exception | None = None
    requests: list[SpeechRequest] = field(default_factory=list)

    def synthesize(self, request: SpeechRequest) -> SpeechResult:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return SpeechResult(
            audio=b"RIFF" + b"\x00" * 60 + request.text.encode(),
            sample_rate=24000,
            duration_seconds=2.88,
            provider="mlxaudio",
            model_identifier="mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit",
            model_revision="e7dd0585652209fa0d7783659aad4e8a324de11c",
            quantization="8-bit MLX, group size 64, affine",
            runtime="mlx-audio",
            runtime_version="0.5.5",
            generation={"temperature": 0.9, "kwargs_passed_to_generate": []},
            clone_prompt_sha256=CLONE_PROMPT_DIGEST,
            elapsed_seconds=4.35,
            cost_usd=0.0,
            local=True,
        )

    def available(self) -> str | None:
        return None


def rows(store: Engine, table: str) -> list[Any]:
    with store.connect() as connection:
        return list(connection.execute(text(f"select * from {table}")).mappings())  # noqa: S608


def configuration() -> ModelConfig:
    found = by_slug(SPEECH_SLUG)
    assert found is not None
    return found


def a_val_message(store: Engine, content: str = "The local systems are ready, my lord.") -> Turn:
    """One ordinary turn, so the text spoken is a genuine finished response."""
    outcome = send(
        store,
        build_gateway(store, answering(content)),
        "Are the local systems ready?",
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )
    assert isinstance(outcome, Turn)
    return outcome


# --- the route ---------------------------------------------------------------------


def test_the_speech_route_is_admitted_and_carries_nothing_else() -> None:
    """Structural: it holds one profile, the narrowest in the house."""
    config = configuration()
    assert is_admitted(config)
    assert config.capability_profiles == frozenset({CapabilityProfile.SPEECH})
    for profile in (
        CapabilityProfile.PARTNER,
        CapabilityProfile.STRUCTURED,
        CapabilityProfile.STRIP,
        CapabilityProfile.PERCEPTION,
    ):
        assert not satisfies_profile(config, profile)
    assert config.hosting.value == "local" and config.cost_per_mtok_in_usd == 0.0
    # Its declared weaknesses say what is not claimed, in the words it matters in.
    assert any("not model-verified" in weakness for weakness in config.known_weaknesses)


# --- what is spoken is what Val said ------------------------------------------------


def test_val_speaks_her_own_persisted_words_verbatim(store: Engine) -> None:
    """The text comes from the record, not from a caller's copy of it."""
    turn = a_val_message(store, "Everything is ready for you, my lord.")
    voice = a_voice()
    voice_id = register_voice(store, voice, DESCRIBED)
    provider = FakeVoice()

    spoken = speak_message(store, provider, configuration(), voice, voice_id, turn.val_message.id)

    assert len(provider.requests) == 1
    assert provider.requests[0].text == "Everything is ready for you, my lord."
    row = rows(store, "speech_generations")[0]
    assert row["final_text"] == turn.val_message.content
    assert row["final_text_sha256"] == digest_of(turn.val_message.content)
    assert row["message_id"] == turn.val_message.id
    assert spoken.audio_path.read_bytes().endswith(b"Everything is ready for you, my lord.")


def test_val_does_not_speak_the_owners_words_back_at_him(store: Engine) -> None:
    turn = a_val_message(store)
    voice = a_voice()
    voice_id = register_voice(store, voice, DESCRIBED)
    provider = FakeVoice()
    with pytest.raises(SpeechUnavailableError, match="Val speaks her own words"):
        speak_message(store, provider, configuration(), voice, voice_id, turn.user_message.id)
    assert provider.requests == []
    assert rows(store, "speech_generations") == []


def test_a_message_that_does_not_exist_is_not_invented(store: Engine) -> None:
    voice = a_voice()
    voice_id = register_voice(store, voice, DESCRIBED)
    with pytest.raises(SpeechUnavailableError, match="no message"):
        speak_message(
            store,
            FakeVoice(),
            configuration(),
            voice,
            voice_id,
            UUID("01a0cc68-0000-7000-8000-000000000000"),
        )


# --- the voice is a governed object -------------------------------------------------


def test_the_voice_is_recorded_once_with_its_origin_and_its_limits(store: Engine) -> None:
    voice = a_voice()
    first = register_voice(store, voice, DESCRIBED)
    second = register_voice(store, voice, DESCRIBED)
    assert first == second, "re-registering the same voice is the same voice"
    assert len(rows(store, "speech_voices")) == 1

    row = rows(store, "speech_voices")[0]
    assert row["name"] == "val-local-v1"
    assert row["reference_sha256"] == digest_of(REFERENCE)
    assert row["reference_text"] == voice.reference_text
    assert row["voice_description"] == voice.voice_description
    assert row["designed_by_model"].endswith("VoiceDesign-8bit")
    assert row["designed_by_revision"] == "f90d617701d9f7f4ca499291e0b57f2b3c2fd2ee"
    # The two facts a reader in a year will need and will not otherwise have.
    assert "No ElevenLabs audio" in row["origin"]
    assert "NOT claimed to be an acoustic clone" in row["identity_claim"]


def test_every_utterance_is_anchored_to_the_same_conditioning(store: Engine) -> None:
    """Equal clone prompts across utterances is what says the voice did not drift."""
    voice = a_voice()
    voice_id = register_voice(store, voice, DESCRIBED)
    provider = FakeVoice()
    for content in ("One thing, my lord.", "And another."):
        speak(store, provider, configuration(), voice, voice_id, content)

    generations = rows(store, "speech_generations")
    assert len(generations) == 2
    assert {row["clone_prompt_sha256"] for row in generations} == {CLONE_PROMPT_DIGEST}
    assert {row["voice_id"] for row in generations} == {voice_id}
    assert all(row["message_id"] is None for row in generations), "house-internal utterances"


# --- the record -----------------------------------------------------------------------


def test_the_record_holds_everything_the_order_lists(store: Engine) -> None:
    """§13, as a readable row rather than as a promise."""
    turn = a_val_message(store, "It is done, my lord.")
    voice = a_voice()
    voice_id = register_voice(store, voice, DESCRIBED)
    speak_message(store, FakeVoice(), configuration(), voice, voice_id, turn.val_message.id)

    row = rows(store, "speech_generations")[0]
    assert row["model_config_id"] == configuration().id
    assert row["provider"] == "mlxaudio"
    assert row["model_identifier"] == "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit"
    assert row["model_revision"] == "e7dd0585652209fa0d7783659aad4e8a324de11c"
    assert row["quantization"] == "8-bit MLX, group size 64, affine"
    assert (row["runtime"], row["runtime_version"]) == ("mlx-audio", "0.5.5")
    assert row["generation"]["kwargs_passed_to_generate"] == []
    assert row["clone_prompt_sha256"] == CLONE_PROMPT_DIGEST
    assert len(row["audio_sha256"]) == 64 and row["audio_bytes"] > 0
    assert row["sample_rate"] == 24000 and float(row["duration_seconds"]) > 0
    assert row["local"] is True and row["cost_usd"] == 0
    assert row["elapsed_ms"] > 0


def test_a_speech_row_cannot_be_edited_or_deleted(store: Engine) -> None:
    """Append-only, under the standing Layer 0 guards."""
    voice = a_voice()
    voice_id = register_voice(store, voice, DESCRIBED)
    spoken = speak(store, FakeVoice(), configuration(), voice, voice_id, "It is done.")
    with pytest.raises(Exception, match=r"evidence|immutable|cannot"):
        with store.begin() as connection:
            connection.execute(
                text("update speech_generations set final_text = 'something else' where id = :i"),
                {"i": spoken.generation_id},
            )
    with pytest.raises(Exception, match=r"delete|evidence|cannot"):
        with store.begin() as connection:
            connection.execute(
                text("delete from speech_generations where id = :i"),
                {"i": spoken.generation_id},
            )


# --- failure is closed ----------------------------------------------------------------


def test_when_local_speech_fails_nothing_reaches_a_cloud_voice_service(
    store: Engine,
) -> None:
    """§12's rule: fail closed, and never silently invoke ElevenLabs."""
    turn = a_val_message(store)
    voice = a_voice()
    voice_id = register_voice(store, voice, DESCRIBED)
    broken = FakeVoice(
        failure=SpeechUnavailableError(
            "local speech failed twice and is not available. No cloud text-to-speech was "
            "called and nothing was charged."
        )
    )
    with pytest.raises(SpeechUnavailableError) as stopped:
        speak_message(store, broken, configuration(), voice, voice_id, turn.val_message.id)
    assert "No cloud text-to-speech was called" in str(stopped.value)
    assert rows(store, "speech_generations") == [], "a failed utterance is not a record"


def test_a_refusal_is_not_a_runtime_failure(store: Engine) -> None:
    """Different causes read differently: one is a condition, one is a mistake."""
    voice = a_voice()
    voice_id = register_voice(store, voice, DESCRIBED)
    refusing = FakeVoice(failure=SpeechRefusedError("there is nothing to say"))
    with pytest.raises(SpeechRefusedError):
        speak(store, refusing, configuration(), voice, voice_id, "   anything   ")
    assert rows(store, "speech_generations") == []


def test_the_gateway_holds_no_voice_until_the_composition_root_wires_one(
    store: Engine,
) -> None:
    """A house with no voice says so; it does not substitute one."""
    gateway = build_gateway(store, answering("Ready."))
    assert gateway.speech is None and gateway.voice is None
