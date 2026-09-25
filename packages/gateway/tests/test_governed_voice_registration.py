# ruff: noqa: F811, F401 - fixtures imported by name
"""The governed voice must exist in the store the application actually uses.

Owner acceptance repair, 25 September 2026 (WP3 §3, §3.1). In the room, two of his
replies were silent and the session ended in error:

    the spoken turn was answered and its voice provenance could not be recorded: the
    governed voice has no `speech_voices` row, so a spoken segment cannot be
    attributed to it; nothing was recorded.

The delivery tests had always passed because **their fixtures registered the voice**.
The running application never did. So the live store had no row, provenance could not
be written for anything Val spoke, and the gap was invisible precisely because the
tests provisioned what production did not.

These tests are the shape of that gap, so it cannot come back: the first fails
against the pre-fix state — a store with no `speech_voices` row after the
application has started — and the rest hold the repair to registering the real
governed voice and inventing nothing.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from test_deliberation_machinery import clean_personas, store

from val_domain.speech import VoiceConditioning, digest_of
from val_gateway.speech import register_voice

REFERENCE = b"RIFF" + b"\x00" * 64


def a_voice_record(directory: Path) -> Path:
    """A governed voice record of exactly the shape the real one has."""
    reference = directory / "reference.wav"
    reference.write_bytes(REFERENCE)
    record = directory / "val-voice.json"
    record.write_text(
        json.dumps(
            {
                "name": "val-established-v1",
                "reference_path": str(reference),
                "reference_sha256": digest_of(REFERENCE),
                "reference_bytes": len(REFERENCE),
                "reference_sample_rate": 24000,
                "reference_duration_seconds": 18.756,
                "reference_text": "Good evening, my lord.",
                "reference_text_sha256": digest_of(b"Good evening, my lord."),
                "voice_description": "VAL's established voice.",
                "voice_description_sha256": digest_of(b"VAL's established voice."),
                "designed_by_model": "ElevenLabs Voice Design (owner-created, external)",
                "designed_by_revision": "not applicable",
                "designed_by_quantization": "not applicable",
                "designed_by_runtime": "not applicable",
                "designed_generation": {"note": "produced outside this house"},
                "origin": "owner-created original synthetic voice",
                "identity_claim": "zero-shot reference conditioning; not model-verified",
            }
        )
    )
    return record


def credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """The startup credential check is not weakened to run these tests.

    `start` refuses when a configured route has no credential, which is correct and
    is the behaviour a test must not erode. So the routes are given placeholder
    values: nothing is called, and the refusal stays in force for anything that is
    genuinely unconfigured.
    """
    for name in ("VAL_ANTHROPIC_API_KEY", "VAL_OPENAI_API_KEY", "VAL_LMSTUDIO_API_TOKEN"):
        monkeypatch.setenv(name, "not-a-real-value")


def test_the_voice_record_carries_everything_registration_needs(tmp_path: Path) -> None:
    """Read from the record, never restated in code and never defaulted."""
    from val_providers.qwen_tts_speech import canonical_voice_description, load_canonical_voice

    record = a_voice_record(tmp_path)
    voice = load_canonical_voice(record)
    described = canonical_voice_description(record)

    assert voice.name == "val-established-v1"
    assert voice.reference_sha256 == digest_of(REFERENCE)
    assert described["reference_sample_rate"] == 24000
    assert described["reference_duration_seconds"] == 18.756
    assert "not model-verified" in str(described["identity_claim"])


def test_a_record_missing_a_field_is_refused_rather_than_defaulted(tmp_path: Path) -> None:
    """A voice that cannot be described is not registered with guesses."""
    from val_providers.qwen_tts_speech import SpeechUnavailableError, canonical_voice_description

    record = a_voice_record(tmp_path)
    described = json.loads(record.read_text())
    del described["identity_claim"]
    record.write_text(json.dumps(described))

    with pytest.raises(SpeechUnavailableError) as refused:
        canonical_voice_description(record)
    assert "incomplete" in str(refused.value)


def test_starting_the_application_registers_the_governed_voice(
    store: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The regression.** Against the pre-fix code this store stays empty.

    Nothing here registers the voice: the application does, at startup, the way it
    now must — which is the whole difference between the test fixtures and the room.
    """
    import val_gateway.startup as startup
    from val_providers.qwen_tts_speech import canonical_voice_description, load_canonical_voice

    credentials(monkeypatch)
    record = a_voice_record(tmp_path)

    class ReadySpeech:
        def available(self) -> str | None:
            return None

    monkeypatch.setattr(startup, "QwenTTSSpeech", lambda: ReadySpeech())
    monkeypatch.setattr(startup, "load_canonical_voice", lambda: load_canonical_voice(record))
    monkeypatch.setattr(
        startup, "canonical_voice_description", lambda: canonical_voice_description(record)
    )

    with store.connect() as connection:
        before = connection.execute(text("select count(*) from speech_voices")).scalar_one()
    assert before == 0, "the store begins as production began: with no governed voice"

    started = startup.start(store)

    with store.connect() as connection:
        rows = connection.execute(
            text(
                "select name, reference_sha256, reference_bytes, reference_sample_rate, "
                "       reference_duration_seconds, identity_claim from speech_voices"
            )
        ).all()
    assert len(rows) == 1, "starting the application registered the governed voice"
    (row,) = rows
    assert row.name == "val-established-v1"
    assert row.reference_sha256 == digest_of(REFERENCE), "the real reference, by digest"
    assert row.reference_bytes == len(REFERENCE)
    assert row.reference_sample_rate == 24000
    assert "not model-verified" in row.identity_claim
    assert started.gateway.voice is not None, "and the gateway holds the voice it registered"


def test_starting_twice_is_the_same_voice_and_not_two(
    store: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Idempotent on the reference digest: a restart is not a second voice."""
    import val_gateway.startup as startup
    from val_providers.qwen_tts_speech import canonical_voice_description, load_canonical_voice

    credentials(monkeypatch)
    record = a_voice_record(tmp_path)

    class ReadySpeech:
        def available(self) -> str | None:
            return None

    monkeypatch.setattr(startup, "QwenTTSSpeech", lambda: ReadySpeech())
    monkeypatch.setattr(startup, "load_canonical_voice", lambda: load_canonical_voice(record))
    monkeypatch.setattr(
        startup, "canonical_voice_description", lambda: canonical_voice_description(record)
    )

    startup.start(store)
    startup.start(store)

    with store.connect() as connection:
        count = connection.execute(text("select count(*) from speech_voices")).scalar_one()
    assert count == 1


def test_a_voice_that_cannot_be_registered_stops_speech_rather_than_speaking_unattributed(
    store: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§3: never permit unattributed speech, and never fabricate an identity."""
    from sqlalchemy.exc import OperationalError

    import val_gateway.startup as startup
    from val_providers.qwen_tts_speech import canonical_voice_description, load_canonical_voice

    credentials(monkeypatch)
    record = a_voice_record(tmp_path)

    class ReadySpeech:
        def available(self) -> str | None:
            return None

    def refuse(*_: object, **__: object) -> UUID:
        raise OperationalError("insert", {}, Exception("the store refused"))

    monkeypatch.setattr(startup, "QwenTTSSpeech", lambda: ReadySpeech())
    monkeypatch.setattr(startup, "load_canonical_voice", lambda: load_canonical_voice(record))
    monkeypatch.setattr(
        startup, "canonical_voice_description", lambda: canonical_voice_description(record)
    )
    monkeypatch.setattr(startup, "register_voice", refuse)

    started = startup.start(store)

    assert started.gateway.voice is None, "no voice, so nothing is spoken unattributed"
    assert any("could not be registered" in warning for warning in started.warnings), (
        "and the house says so at startup rather than failing quietly at the first word"
    )


def test_registering_writes_the_record_and_nothing_else(store: Engine) -> None:
    """A voice registration is one row: no generation, no delivery, no session."""
    voice = VoiceConditioning(
        name="val-established-v1",
        reference_audio=REFERENCE,
        reference_sha256=digest_of(REFERENCE),
        reference_text="Good evening, my lord.",
        voice_description="VAL's established voice.",
        designed_by_model="ElevenLabs Voice Design (owner-created, external)",
        designed_by_revision="not applicable",
    )
    register_voice(
        store,
        voice,
        described={
            "reference_sample_rate": 24000,
            "reference_duration_seconds": 18.756,
            "designed_by_quantization": "not applicable",
            "designed_by_runtime": "not applicable",
            "designed_generation": {},
            "origin": "owner-created",
            "identity_claim": "not model-verified",
        },
    )
    with store.connect() as connection:
        assert connection.execute(text("select count(*) from speech_voices")).scalar_one() == 1
        assert connection.execute(text("select count(*) from speech_generations")).scalar_one() == 0
        assert connection.execute(text("select count(*) from voice_sessions")).scalar_one() == 0
