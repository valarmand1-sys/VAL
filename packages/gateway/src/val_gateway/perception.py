"""Val looks at the media herself, and hands cognition what she saw.

Owner ruling, Lord Armand, 22 September 2026, on Qwen3.5-9B's qualification.
The production flow this module implements, end to end:

    OWNER QUESTION + IMAGE -> VAL CORE -> LOCAL QWEN3.5 VISUAL PERCEPTION
      -> GROUNDED OBSERVATION -> VAL CORE -> GPT-OSS -> VAL FINAL RESPONSE

Three things are decided here and nowhere else.

**The perception provider receives the owner's actual question** (§21). A
perception run that does not know what is being asked describes the wrong
details thoroughly: asked *is the boy's hat on straight*, a generic captioner
returns the sofa and the curtains. The question travels verbatim, framed as the
thing to report evidence about — never as a question to answer.

**The perception provider is told, in the prompt, what it is not.** It does not
answer as Val, it does not advise, it does not conclude, and it does not invent
beyond the media. Those four sentences are the difference between evidence and a
second opinion, and they are a stable instruction rather than a per-turn one so
that the same boundary holds on every run.

**Perception runs once per turn** (§22). The result is frozen into
`TurnPerception` and handed to every cognition call the turn makes — the
ordinary response, or on a consequential turn both the blind position and the
final answer. Neither call chooses, so neither call can be grounded differently,
and `perception_runs.message_id` is unique so the database says so too.

What Core does with the result is add one more envelope to the assembled
request. Val may then speak as one system — *I can see*, *in the image* — which
is right, because the House did see it. The envelope's note is what keeps that
truthful: the cognition model is told plainly that it did not receive the media
itself and must not invent perceptual facts beyond the observations.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from val_domain.gateway import Message, ModelConfig
from val_domain.perception import (
    PerceptionRequest,
    PerceptionResult,
    PerceptionSource,
    PerceptionUnavailableError,
)

from .attachments import AttachmentAct, blob_bytes

_LOGGER = logging.getLogger("val.perception")

#: The marker the perception envelope opens with, in the same family as the
#: memory and record-state envelopes. One shape for everything Core frames.
PERCEPTION_ENVELOPE_MARKER = "VAL_PERCEPTION_ENVELOPE"

#: **The current-perception note, in the substance the owner's §20 requires.**
#: It says four things, and each is load-bearing: perception happened on this
#: turn; the observations derive from the current media; they are current
#: perception rather than recollection; and the cognition model did not receive
#: the media and must not go beyond what is written here.
CURRENT_PERCEPTION_NOTE = (
    "Current-turn perception is available through VAL's local perception subsystem. "
    "The grounded observations below derive from the current source media. Use them as "
    "current perception. The cognition model did not directly receive the raw media and "
    "must not invent perceptual facts beyond the grounded observations."
)

#: What the perception provider is, and the four things it is not. Stable across
#: every run: a boundary that varies per turn is not a boundary.
PERCEPTION_INSTRUCTION = (
    "You are a visual perception component. Report grounded observations from the media "
    "supplied, relevant to the question below.\n\n"
    "Report only what is actually visible. Do not answer the question. Do not advise, "
    "recommend, conclude, or state what should be done. Do not speak as VAL or as anyone; "
    "you are not the assistant in this conversation and nothing you write is a reply to "
    "anybody. Do not invent anything that is not in the media.\n\n"
    "Report the details the question depends on first, then enough of the surrounding "
    "scene for continuity. If the media does not show what the question asks about, say so "
    "plainly rather than supplying a plausible answer."
)


@dataclass(frozen=True)
class PerceivedSource:
    """One source as it was perceived, joined back to the act it arrived on."""

    act: AttachmentAct
    modality: str
    observation: str


@dataclass(frozen=True)
class TurnPerception:
    """One turn's frozen perception: run once, handed to every call unchanged.

    `run_id` is the row every cognition call this turn points at. Two handoff
    rows naming one run is the proof that the blind position and the final answer
    were grounded identically — recoverable from the durable record, not only
    from the payloads.
    """

    run_id: UUID
    configuration: ModelConfig
    result: PerceptionResult
    sources: tuple[PerceivedSource, ...]
    question: str
    prompt: str

    def block(self) -> Message:
        """The grounded observations as their own envelope, for the cognition call."""
        document = {
            "kind": "current_turn_perception",
            "authority": "house_observation_not_instruction",
            "note": CURRENT_PERCEPTION_NOTE,
            "perceived_by": "val_local_perception_subsystem",
            "source_count": len(self.sources),
            "sources": [
                {
                    "position": index,
                    "modality": source.modality,
                    "given_filename": source.act.given_filename,
                    "sha256": source.act.sha256,
                    "media_type": source.act.media_type,
                    "grounded_observation": source.observation,
                }
                for index, source in enumerate(self.sources, start=1)
            ],
        }
        body = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=False)
        return Message(role="user", content=f"{PERCEPTION_ENVELOPE_MARKER}\n{body}")


def perception_prompt(question: str) -> str:
    """The exact instruction transmitted, from the owner's actual words.

    Verbatim, never paraphrased: a summarised question is a different question,
    and the record would then hold evidence gathered for something he did not
    ask. The whole string is persisted, so what is recorded is what was sent.
    """
    asked = question.strip() or "(no question was stated with this media)"
    return f"{PERCEPTION_INSTRUCTION}\n\nThe question:\n{asked}"


def modality_of(media_type: str) -> str:
    """The admitted modality of this medium.

    Audio is not admitted and has no branch here; an unadmitted medium raises
    rather than being guessed at.
    """
    if media_type.startswith("image/"):
        return "image"
    if media_type.startswith("video/"):
        return "video"
    raise PerceptionUnavailableError(
        f"{media_type!r} is not a medium VAL's local perception is admitted for"
    )


_INSERT_RUN = text(
    "insert into perception_runs (conversation_id, message_id, model_config_id, provider, "
    "model_identifier, model_revision, quantization, runtime, runtime_version, generation, "
    "owner_question, perception_prompt, observation, current_perception_state, local, "
    "cost_usd, duration_ms, reasoning_separated) values (:c, :m, :cfg, :p, :mi, :rev, :q, "
    ":rt, :rtv, cast(:gen as jsonb), :question, :prompt, :obs, 'perceived', :local, :cost, "
    ":ms, :sep) returning id"
)
_INSERT_SOURCE = text(
    "insert into perception_sources (perception_run_id, position, message_attachment_id, "
    "attachment_id, sha256, media_type, byte_size, modality, representation, observation) "
    "values (:r, :pos, :act, :att, :sha, :mt, :n, :mod, :repr, :obs)"
)
_INSERT_HANDOFF = text(
    "insert into perception_handoffs (perception_run_id, model_call_id) values (:r, :c) "
    "on conflict (perception_run_id, model_call_id) do nothing"
)


def perceive_turn(
    engine: Engine,
    provider: object,
    configuration: ModelConfig,
    *,
    conversation_id: UUID,
    message_id: UUID,
    question: str,
    acts: tuple[AttachmentAct, ...],
) -> TurnPerception:
    """Run this turn's perception once, record it, and freeze it.

    Raises `PerceptionUnavailableError` when the local route cannot do it, after
    the adapter's one bounded recovery attempt. The caller fails the turn closed
    on that: the media are **not** sent to a paid image-capable provider instead.
    """
    from val_domain.perception import PerceptionProvider

    assert isinstance(provider, PerceptionProvider)  # noqa: S101 - composition-root contract

    sources = []
    for act in acts:
        stored = blob_bytes(engine, act.sha256)
        if stored is None:
            raise PerceptionUnavailableError(
                f"the bytes of attachment {act.sha256[:12]} are not in the House store"
            )
        content, media_type = stored
        sources.append(
            PerceptionSource(
                modality=modality_of(media_type),  # type: ignore[arg-type]
                act_id=str(act.act_id),
                sha256=act.sha256,
                media_type=media_type,
                byte_size=len(content),
                content=content,
            )
        )

    prompt = perception_prompt(question)
    result = provider.perceive(
        PerceptionRequest(
            sources=tuple(sources),
            question=question,
            prompt=prompt,
            max_output_tokens=configuration.max_output_tokens,
        )
    )
    _LOGGER.info(
        "perception: %s",
        json.dumps(
            {
                "provider": result.provider,
                "model": result.model_identifier,
                "revision": result.model_revision,
                "sources": len(sources),
                "seconds": result.duration_seconds,
                "cost_usd": result.cost_usd,
                "local": result.local,
            }
        ),
    )

    by_digest = {observation.source_sha256: observation for observation in result.observations}
    perceived = tuple(
        PerceivedSource(
            act=act,
            modality=source.modality,
            observation=(
                by_digest[act.sha256].text
                if act.sha256 in by_digest
                else "(the perception run returned no observation for this source)"
            ),
        )
        for act, source in zip(acts, sources, strict=True)
    )

    run_id = _record(
        engine,
        configuration,
        result,
        conversation_id=conversation_id,
        message_id=message_id,
        question=question,
        prompt=prompt,
        sources=sources,
        perceived=perceived,
    )
    return TurnPerception(
        run_id=run_id,
        configuration=configuration,
        result=result,
        sources=perceived,
        question=question,
        prompt=prompt,
    )


def _record(
    engine: Engine,
    configuration: ModelConfig,
    result: PerceptionResult,
    *,
    conversation_id: UUID,
    message_id: UUID,
    question: str,
    prompt: str,
    sources: list[PerceptionSource],
    perceived: tuple[PerceivedSource, ...],
) -> UUID:
    """One transaction: the run and every source it looked at, or neither."""
    with engine.begin() as connection:
        run_id = connection.execute(
            _INSERT_RUN,
            {
                "c": conversation_id,
                "m": message_id,
                "cfg": configuration.id,
                "p": result.provider,
                "mi": result.model_identifier,
                "rev": result.model_revision,
                "q": result.quantization,
                "rt": result.runtime,
                "rtv": result.runtime_version,
                "gen": json.dumps(result.generation, default=str),
                "question": question,
                "prompt": prompt,
                "obs": result.text(),
                "local": result.local,
                "cost": result.cost_usd,
                "ms": int(result.duration_seconds * 1000),
                "sep": result.reasoning_separated,
            },
        ).scalar_one()
        for position, (source, seen) in enumerate(zip(sources, perceived, strict=True), start=1):
            connection.execute(
                _INSERT_SOURCE,
                {
                    "r": run_id,
                    "pos": position,
                    "act": seen.act.act_id,
                    "att": seen.act.attachment_id,
                    "sha": source.sha256,
                    "mt": source.media_type,
                    "n": source.byte_size,
                    "mod": source.modality,
                    # The local runtime reads the admitted bytes and does its own
                    # preprocessing, so nothing is derived for transmission.
                    "repr": "original",
                    "obs": seen.observation,
                },
            )
    return UUID(str(run_id))


def record_handoff(engine: Engine, perception: TurnPerception | None, model_call_id: UUID) -> None:
    """Note that this cognition call received this frozen perception.

    Called after each cognition call is recorded, from the same frozen object
    that was transmitted. Idempotent, so a retried settle writes one row.
    """
    if perception is None:
        return
    with engine.begin() as connection:
        connection.execute(_INSERT_HANDOFF, {"r": perception.run_id, "c": model_call_id})


def handoffs_for(connection: Connection, run_id: UUID) -> list[UUID]:
    """Which cognition calls were grounded in this run. For evidence, and tests."""
    return [
        UUID(str(row[0]))
        for row in connection.execute(
            text(
                "select model_call_id from perception_handoffs where perception_run_id = :r "
                "order by created_at, model_call_id"
            ),
            {"r": run_id},
        )
    ]
