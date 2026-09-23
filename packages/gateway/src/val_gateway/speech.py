"""Val Core asks for Val's words to be spoken — owner execution order, 22 September 2026.

The production path, end to end:

    VAL FINAL TEXT -> SPEECH BOUNDARY -> LOCAL QWEN3-TTS BASE
      -> REUSABLE LOCAL VAL VOICE CONDITIONING -> WAV

One thing is decided here and nowhere else: **what is spoken is what Val already
said.** `speak_message` reads the persisted `val` message and hands its content
to the provider verbatim. There is no rewriting step, no summarising step and no
style parameter, because a boundary that could change the words would make the
record of what Val said and the recording of what Val said two different things.

VoiceDesign is not reachable from here. It produced the canonical reference once
and its role ended; ordinary speech is the Base model conditioned on that
reference, so repeated utterances keep one speaker identity.

When local speech cannot be produced the caller gets an honest failure and
**nothing is sent to a cloud voice service** — ElevenLabs least of all, which
remains preserved historical continuity and an explicit owner choice, never an
automatic fallback.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

from val_domain.gateway import ModelConfig
from val_domain.speech import (
    SpeechProvider,
    SpeechRequest,
    SpeechResult,
    SpeechUnavailableError,
    VoiceConditioning,
    digest_of,
)

_LOGGER = logging.getLogger("val.speech")

#: Where generated speech is staged. Beside the governed voice rather than in a
#: new store of its own: audio Val produced is operating state, and the durable
#: fact about it — digest, duration, what was said — lives in PostgreSQL.
SPEECH_DIR = Path.home() / ".val-voice" / "spoken"


@dataclass(frozen=True)
class SpokenText:
    """One utterance, as the record holds it."""

    generation_id: UUID
    voice_id: UUID
    audio_path: Path
    audio_sha256: str
    sample_rate: int
    duration_seconds: float
    clone_prompt_sha256: str
    cost_usd: float
    local: bool


_INSERT_VOICE = text(
    "insert into speech_voices (name, reference_sha256, reference_bytes, "
    "reference_sample_rate, reference_duration_seconds, reference_text, "
    "reference_text_sha256, voice_description, voice_description_sha256, designed_by_model, "
    "designed_by_revision, designed_by_quantization, designed_by_runtime, "
    "designed_generation, origin, identity_claim) values (:n, :rs, :rb, :rr, :rd, :rt, :rts, "
    ":vd, :vds, :dm, :dr, :dq, :drt, cast(:dg as jsonb), :o, :ic) "
    "on conflict (reference_sha256) do nothing returning id"
)
_FIND_VOICE = text("select id from speech_voices where reference_sha256 = :rs")
_INSERT_GENERATION = text(
    "insert into speech_generations (voice_id, message_id, model_config_id, final_text, "
    "final_text_sha256, provider, model_identifier, model_revision, quantization, runtime, "
    "runtime_version, generation, clone_prompt_sha256, audio_sha256, audio_path, "
    "audio_bytes, sample_rate, duration_seconds, local, cost_usd, elapsed_ms) "
    "values (:v, :m, :cfg, :t, :ts, :p, :mi, :rev, :q, :rt, :rtv, cast(:gen as jsonb), :cp, "
    ":as256, :ap, :ab, :sr, :d, :local, :cost, :ms) returning id"
)
_MESSAGE_TEXT = text("select content, role::text as role from messages where id = :m")


def register_voice(engine: Engine, voice: VoiceConditioning, described: Mapping[str, Any]) -> UUID:
    """Record this voice, or find the row that already holds it.

    Idempotent on the reference digest: re-registering the same voice is the
    same voice, and two rows would invite two answers to "which voice?".
    """
    with engine.begin() as connection:
        found = connection.execute(
            _INSERT_VOICE,
            {
                "n": voice.name,
                "rs": voice.reference_sha256,
                "rb": len(voice.reference_audio),
                "rr": int(described["reference_sample_rate"]),
                "rd": described["reference_duration_seconds"],
                "rt": voice.reference_text,
                "rts": voice.reference_text_sha256,
                "vd": voice.voice_description,
                "vds": voice.voice_description_sha256,
                "dm": voice.designed_by_model,
                "dr": voice.designed_by_revision,
                "dq": str(described["designed_by_quantization"]),
                "drt": str(described["designed_by_runtime"]),
                "dg": json.dumps(described["designed_generation"], default=str),
                "o": str(described["origin"]),
                "ic": str(described["identity_claim"]),
            },
        ).scalar_one_or_none()
        if found is None:
            found = connection.execute(_FIND_VOICE, {"rs": voice.reference_sha256}).scalar_one()
    return UUID(str(found))


def speak(
    engine: Engine,
    provider: SpeechProvider,
    configuration: ModelConfig,
    voice: VoiceConditioning,
    voice_id: UUID,
    final_text: str,
    *,
    message_id: UUID | None = None,
    directory: Path = SPEECH_DIR,
) -> SpokenText:
    """Speak this finished text once, stage the audio, and record what happened.

    Raises `SpeechUnavailableError` when the local route cannot do it, after the
    adapter's one bounded recovery attempt. The caller fails closed on that: the
    words are **not** sent to a cloud voice service instead.
    """
    result = provider.synthesize(SpeechRequest(text=final_text, voice=voice))
    _LOGGER.info(
        "speech: %s",
        json.dumps(
            {
                "provider": result.provider,
                "model": result.model_identifier,
                "voice": voice.name,
                "characters": len(final_text),
                "seconds": result.duration_seconds,
                "elapsed": result.elapsed_seconds,
                "cost_usd": result.cost_usd,
                "local": result.local,
            }
        ),
    )
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{result.audio_sha256[:32]}.wav"
    path.write_bytes(result.audio)
    generation_id = _record(
        engine,
        configuration,
        result,
        voice_id=voice_id,
        message_id=message_id,
        final_text=final_text,
        path=path,
    )
    return SpokenText(
        generation_id=generation_id,
        voice_id=voice_id,
        audio_path=path,
        audio_sha256=result.audio_sha256,
        sample_rate=result.sample_rate,
        duration_seconds=result.duration_seconds,
        clone_prompt_sha256=result.clone_prompt_sha256,
        cost_usd=result.cost_usd,
        local=result.local,
    )


def speak_message(
    engine: Engine,
    provider: SpeechProvider,
    configuration: ModelConfig,
    voice: VoiceConditioning,
    voice_id: UUID,
    message_id: UUID,
    *,
    directory: Path = SPEECH_DIR,
) -> SpokenText:
    """Speak a persisted Val message, verbatim.

    The text is read from the record rather than passed in, which is the point:
    what is spoken is provably what Val said, not a caller's copy of it. A user
    message is refused — Val speaks her own words, not his back at him.
    """
    with engine.connect() as connection:
        row = connection.execute(_MESSAGE_TEXT, {"m": message_id}).one_or_none()
    if row is None:
        raise SpeechUnavailableError(f"no message {message_id} exists to speak")
    if row.role != "val":
        raise SpeechUnavailableError(
            f"message {message_id} is a {row.role} message; Val speaks her own words"
        )
    return speak(
        engine,
        provider,
        configuration,
        voice,
        voice_id,
        row.content,
        message_id=message_id,
        directory=directory,
    )


def _record(
    engine: Engine,
    configuration: ModelConfig,
    result: SpeechResult,
    *,
    voice_id: UUID,
    message_id: UUID | None,
    final_text: str,
    path: Path,
) -> UUID:
    with engine.begin() as connection:
        generation_id = connection.execute(
            _INSERT_GENERATION,
            {
                "v": voice_id,
                "m": message_id,
                "cfg": configuration.id,
                "t": final_text,
                "ts": digest_of(final_text),
                "p": result.provider,
                "mi": result.model_identifier,
                "rev": result.model_revision,
                "q": result.quantization,
                "rt": result.runtime,
                "rtv": result.runtime_version,
                "gen": json.dumps(result.generation, default=str),
                "cp": result.clone_prompt_sha256,
                "as256": result.audio_sha256,
                "ap": str(path),
                "ab": len(result.audio),
                "sr": result.sample_rate,
                "d": result.duration_seconds,
                "local": result.local,
                "cost": result.cost_usd,
                "ms": int(result.elapsed_seconds * 1000),
            },
        ).scalar_one()
    return UUID(str(generation_id))
