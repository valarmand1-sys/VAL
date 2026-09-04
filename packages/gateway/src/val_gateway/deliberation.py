"""The one writer for deliberation records — WP-0.9.

`04-layer-0.md` WP-0.9: *"consequential exchanges are classified per
`02-partner-systems.md` §4.8, a blind position is formed before exposure to
preference, and the record populates."*

This module is the record half: the writer that persists a completed
deliberation, and the drift signal §4.7 derives from the records. The blind
position *machinery* — classification, strip, blind call, response — hands its
facts to this writer when the exchange resolves; it does not get to write rows
any other way, and there is no other writer.

## Complete at insert time

`0009` refuses UPDATE on `deliberations`, so there is no
insert-now-fill-in-later path and none was built. A deliberation is recorded
when its outcome is known — position, ordering, his response, and what became
of the position, together, once. §4.7 lists exactly these fields; a row
missing any of them would not be the record §4.7 describes.

## What the writer refuses

The writer's contract is that every recorded shape describes one real
deliberation:

- `what_changed_her_mind` exists **iff** `outcome = updated`. A mind that did
  not change cannot have a changed-mind explanation, and an update without one
  violates §4.4 — she says what changed her mind, or she has not updated.
- `both_positions` and `predictions` travel together (§4.5 — a compromise
  records both positions *and* what each party predicted), and never on
  `agreed_from_start`: agreement from the start means there was no
  disagreement to compromise on.
- `project_id` is derived from the anchoring conversation's stored scope,
  never supplied by the caller, and the message must belong to the
  conversation — the same anchoring doctrine as `execution.record_event`.

## What this module does not do

It never infers an outcome from the wording of a response, never reports
`agreed_from_start` or recorded enthusiasm as an approval (the 15 August 2026
trap-question amendment), never updates or deletes, and it is not the Layer 3
deliberation machinery arriving early: no adversary Role, no ledger scoring,
no retrieval of past deliberations into context.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, Row, text

from val_domain.deliberation import (
    BlindPositionRecord,
    ClassificationRecord,
    ClassificationVerdict,
    ClassifiedBy,
    Confidence,
    DeliberationClassification,
    DeliberationRecord,
    Ordering,
    Outcome,
)

_CLASSIFICATION_INSERT = text(
    "insert into classifications "
    "  (project_id, conversation_id, message_id, established, verdict, hard_exclusion, "
    "   attempts, model_call_ids, resolving_model_call_id, resolution) "
    "values "
    "  (:project_id, :conversation_id, :message_id, :established, :verdict, "
    "   :hard_exclusion, :attempts, :model_call_ids, :resolving_model_call_id, :resolution) "
    "returning id, project_id, conversation_id, message_id, established, verdict, "
    "          hard_exclusion, attempts, model_call_ids, resolving_model_call_id, "
    "          resolution, created_at"
)

_ANCHOR = text(
    "select m.conversation_id as message_conversation, c.project_id "
    "  from messages m "
    "  join conversations c on c.id = m.conversation_id "
    " where m.id = :message_id"
)

_INSERT = text(
    "insert into deliberations "
    "  (project_id, conversation_id, message_id, position, confidence, "
    "   reasoning, stripped_content, ordering, user_response, outcome, "
    "   what_changed_her_mind, both_positions, predictions, classification, "
    "   classified_by, blind_position_id) "
    "values "
    "  (:project_id, :conversation_id, :message_id, :position, :confidence, "
    "   :reasoning, :stripped_content, :ordering, :user_response, :outcome, "
    "   :what_changed_her_mind, :both_positions, :predictions, :classification, "
    "   :classified_by, :blind_position_id) "
    "returning id, project_id, conversation_id, message_id, position, confidence, "
    "          reasoning, stripped_content, ordering, user_response, outcome, "
    "          what_changed_her_mind, both_positions, predictions, classification, "
    "          classified_by, blind_position_id, created_at"
)

_BLIND_ANCHOR = text(
    "select conversation_id, message_id from blind_positions where id = :blind_position_id"
)

_BLIND_INSERT = text(
    "insert into blind_positions "
    "  (project_id, conversation_id, message_id, model_call_id, persona_id, "
    "   position, confidence, reasoning, stripped_content, ordering, "
    "   classification, classified_by) "
    "values "
    "  (:project_id, :conversation_id, :message_id, :model_call_id, :persona_id, "
    "   :position, :confidence, :reasoning, :stripped_content, :ordering, "
    "   :classification, :classified_by) "
    "returning id, project_id, conversation_id, message_id, model_call_id, "
    "          persona_id, position, confidence, reasoning, stripped_content, "
    "          ordering, classification, classified_by, created_at"
)


class IncoherentDeliberationError(Exception):
    """The record's fields cannot describe one real deliberation."""


def record_deliberation(
    engine: Engine,
    *,
    conversation_id: UUID,
    message_id: UUID,
    position: str,
    confidence: Confidence,
    reasoning: str,
    stripped_content: str,
    ordering: Ordering,
    user_response: str,
    outcome: Outcome,
    what_changed_her_mind: str | None = None,
    both_positions: str | None = None,
    predictions: str | None = None,
    classification: DeliberationClassification = DeliberationClassification.CONSEQUENTIAL,
    classified_by: ClassifiedBy = ClassifiedBy.AUTOMATIC,
    blind_position_id: UUID | None = None,
) -> DeliberationRecord:
    """Record one resolved deliberation, completely, at insert time.

    `position`, `confidence`, and `reasoning` are the blind position as it was
    formed (§4.1 step 2). `stripped_content` is what the strip step removed —
    empty when the message carried no preference to remove, in which case
    `ordering = ENFORCED` holds trivially. `user_response` is Lord Armand's
    side of the exchange, and `outcome` is what became of the position; both
    must exist before there is a deliberation to record.

    `outcome` is **stated by the caller, never inferred by this writer** from
    the wording of anyone's response — the same manual-marking doctrine as
    `ideas` (§2.4). An `AGREED_FROM_START` outcome records agreement, not
    approval, and no query in this module will ever count it as one.
    """
    for field_name, value in (
        ("position", position),
        ("reasoning", reasoning),
        ("user_response", user_response),
    ):
        if not value.strip():
            raise IncoherentDeliberationError(
                f"{field_name} is required. A deliberation without it is not the "
                "record 02-partner-systems.md §4.7 describes, and a blank one "
                "recorded anyway would be noise wearing a record's shape."
            )

    if outcome is Outcome.UPDATED:
        if what_changed_her_mind is None or not what_changed_her_mind.strip():
            raise IncoherentDeliberationError(
                "outcome says she updated, but not what changed her mind. §4.4 is "
                "explicit: she updates AND says what changed her mind, or she has "
                "not updated. Record the reason, or record the outcome that "
                "actually happened."
            )
    elif what_changed_her_mind is not None:
        raise IncoherentDeliberationError(
            f"what_changed_her_mind was provided on outcome {outcome.value!r}. A "
            "mind that did not change cannot have a changed-mind explanation; one "
            "of the two fields is not telling the truth."
        )

    if (both_positions is None) != (predictions is None):
        raise IncoherentDeliberationError(
            "both_positions and predictions travel together. §4.5: a compromise "
            "records both positions AND what each party predicted would happen — "
            "the predictions are the seed of the prediction ledger, and half a "
            "compromise record is the half that cannot be reconstructed later."
        )
    if both_positions is not None and outcome is Outcome.AGREED_FROM_START:
        raise IncoherentDeliberationError(
            "a compromise was recorded on agreed_from_start. Agreement from the "
            "start means there was no disagreement to compromise on; these fields "
            "cannot both be true of one exchange."
        )

    with engine.begin() as connection:
        anchor = connection.execute(_ANCHOR, {"message_id": message_id}).one_or_none()
        if anchor is None:
            raise IncoherentDeliberationError(
                f"message {message_id} does not exist. A deliberation records a "
                "position formed about something that was actually asked."
            )
        if anchor.message_conversation != conversation_id:
            raise IncoherentDeliberationError(
                f"message {message_id} belongs to conversation "
                f"{anchor.message_conversation}, not {conversation_id}. A "
                "deliberation pairing a conversation with another conversation's "
                "turn would record a position about an exchange that never happened."
            )

        if blind_position_id is not None:
            blind = connection.execute(
                _BLIND_ANCHOR, {"blind_position_id": blind_position_id}
            ).one_or_none()
            if blind is None:
                raise IncoherentDeliberationError(
                    f"blind position {blind_position_id} does not exist. A "
                    "deliberation resolves evidence that was actually captured."
                )
            if blind.conversation_id != conversation_id or blind.message_id != message_id:
                raise IncoherentDeliberationError(
                    f"blind position {blind_position_id} belongs to a different "
                    "exchange. A deliberation resolves the blind position formed "
                    "for its own turn, not one borrowed from another — the link "
                    "exists so the pairing can be trusted (ruling, 19 August 2026)."
                )

        row = connection.execute(
            _INSERT,
            {
                # Derived from the conversation's stored scope, never supplied:
                # a deliberation cannot claim a project its conversation was not in.
                "project_id": anchor.project_id,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "position": position,
                "confidence": confidence.value,
                "reasoning": reasoning,
                "stripped_content": stripped_content,
                "ordering": ordering.value,
                "user_response": user_response,
                "outcome": outcome.value,
                "what_changed_her_mind": what_changed_her_mind,
                "both_positions": both_positions,
                "predictions": predictions,
                "classification": classification.value,
                "classified_by": classified_by.value,
                "blind_position_id": blind_position_id,
            },
        ).one()

    return _record_from(row)


def record_blind_position(
    engine: Engine,
    *,
    conversation_id: UUID,
    message_id: UUID,
    model_call_id: UUID,
    persona_id: UUID,
    position: str,
    confidence: Confidence,
    reasoning: str,
    stripped_content: str,
    ordering: Ordering,
    classification: DeliberationClassification,
    classified_by: ClassifiedBy,
) -> BlindPositionRecord:
    """Persist one blind position as evidence — before the response call runs.

    Append-only from the moment it exists (`0011`): the primary evidence that
    the position was formed, and what it was, independent of whether the
    exchange ever resolves into a `deliberations` row. `model_call_id` names
    the blind call itself; `persona_id` names the revision assembled into it.
    Both are facts about a call that already happened, which is why neither is
    optional. `project_id` is derived from the anchoring conversation, the
    same doctrine as everywhere.
    """
    if not position.strip() or not reasoning.strip():
        raise IncoherentDeliberationError(
            "a blind position without its position or reasoning is not evidence "
            "of a formed judgment; there is nothing to record."
        )
    with engine.begin() as connection:
        anchor = connection.execute(_ANCHOR, {"message_id": message_id}).one_or_none()
        if anchor is None:
            raise IncoherentDeliberationError(
                f"message {message_id} does not exist. A blind position is formed "
                "about something that was actually asked."
            )
        if anchor.message_conversation != conversation_id:
            raise IncoherentDeliberationError(
                f"message {message_id} belongs to conversation "
                f"{anchor.message_conversation}, not {conversation_id}."
            )
        row = connection.execute(
            _BLIND_INSERT,
            {
                "project_id": anchor.project_id,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "model_call_id": model_call_id,
                "persona_id": persona_id,
                "position": position,
                "confidence": confidence.value,
                "reasoning": reasoning,
                "stripped_content": stripped_content,
                "ordering": ordering.value,
                "classification": classification.value,
                "classified_by": classified_by.value,
            },
        ).one()
    return _blind_record_from(row)


def record_classification(
    engine: Engine,
    *,
    conversation_id: UUID,
    message_id: UUID,
    verdict: ClassificationVerdict | None,
    hard_exclusion: str | None,
    attempts: int,
    model_call_ids: tuple[UUID, ...],
    resolving_model_call_id: UUID | None,
    resolution: str | None,
) -> ClassificationRecord:
    """Persist one turn's classification as evidence — established or not.

    Ruling, 3 September 2026. Written when classification concludes and before
    any strip or response call, so the record exists whatever the turn then
    does. `verdict` None means every permitted attempt failed to state one,
    and `resolution` must then say why; a verdict with a resolution, or no
    verdict without one, cannot describe one real classification and is
    refused. `project_id` is derived from the anchoring conversation, the
    same doctrine as everywhere.
    """
    if attempts < 1:
        raise IncoherentDeliberationError("a classification that was never attempted is not one.")
    if verdict is None and not (resolution or "").strip():
        raise IncoherentDeliberationError(
            "an unestablished classification must say why; a bare failure is not evidence."
        )
    if verdict is not None and resolution is not None:
        raise IncoherentDeliberationError(
            "an established classification carries no failure resolution."
        )
    if resolving_model_call_id is not None and resolving_model_call_id not in model_call_ids:
        raise IncoherentDeliberationError(
            "the resolving call must be one of the calls the classification made."
        )
    with engine.begin() as connection:
        anchor = connection.execute(_ANCHOR, {"message_id": message_id}).one_or_none()
        if anchor is None:
            raise IncoherentDeliberationError(
                f"message {message_id} does not exist. A classification is of something "
                "that was actually said."
            )
        if anchor.message_conversation != conversation_id:
            raise IncoherentDeliberationError(
                f"message {message_id} belongs to conversation "
                f"{anchor.message_conversation}, not {conversation_id}."
            )
        row = connection.execute(
            _CLASSIFICATION_INSERT,
            {
                "project_id": anchor.project_id,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "established": verdict is not None,
                "verdict": None if verdict is None else verdict.value,
                "hard_exclusion": hard_exclusion,
                "attempts": attempts,
                "model_call_ids": list(model_call_ids),
                "resolving_model_call_id": resolving_model_call_id,
                "resolution": resolution,
            },
        ).one()
    return _classification_record_from(row)


def classifications_for(engine: Engine, conversation_id: UUID) -> tuple[ClassificationRecord, ...]:
    """Every classification recorded for one conversation, oldest first."""
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "select id, project_id, conversation_id, message_id, established, verdict, "
                "       hard_exclusion, attempts, model_call_ids, resolving_model_call_id, "
                "       resolution, created_at "
                "  from classifications where conversation_id = :c order by created_at, id"
            ),
            {"c": conversation_id},
        ).all()
    return tuple(_classification_record_from(row) for row in rows)


def _classification_record_from(row: Row[Any]) -> ClassificationRecord:
    return ClassificationRecord(
        id=row.id,
        project_id=row.project_id,
        conversation_id=row.conversation_id,
        message_id=row.message_id,
        established=row.established,
        verdict=None if row.verdict is None else ClassificationVerdict(row.verdict),
        hard_exclusion=row.hard_exclusion,
        attempts=row.attempts,
        model_call_ids=tuple(row.model_call_ids),
        resolving_model_call_id=row.resolving_model_call_id,
        resolution=row.resolution,
        created_at=row.created_at,
    )


def blind_positions_for(engine: Engine, conversation_id: UUID) -> tuple[BlindPositionRecord, ...]:
    """Every blind position captured for one conversation, oldest first."""
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "select id, project_id, conversation_id, message_id, model_call_id, "
                "       persona_id, position, confidence, reasoning, stripped_content, "
                "       ordering, classification, classified_by, created_at "
                "  from blind_positions where conversation_id = :c order by created_at, id"
            ),
            {"c": conversation_id},
        ).all()
    return tuple(_blind_record_from(row) for row in rows)


def deliberations_for(engine: Engine, conversation_id: UUID) -> tuple[DeliberationRecord, ...]:
    """Every deliberation recorded against one conversation, oldest first."""
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "select id, project_id, conversation_id, message_id, position, confidence, "
                "       reasoning, stripped_content, ordering, user_response, outcome, "
                "       what_changed_her_mind, both_positions, predictions, classification, "
                "       classified_by, blind_position_id, created_at "
                "  from deliberations where conversation_id = :c order by created_at, id"
            ),
            {"c": conversation_id},
        ).all()
    return tuple(_record_from(row) for row in rows)


def last_disagreement_at(engine: Engine) -> datetime | None:
    """When Val last disagreed — the §4.7 drift signal, or None if she never has.

    A disagreement is any deliberation whose outcome is not
    `agreed_from_start`: whether she then updated, held, or was overridden,
    her blind position differed from his preference and she said so. The one
    outcome excluded is the one where there was nothing to disagree about.

    Returned as the timestamp rather than an elapsed duration, so the caller
    supplies the clock and a test does not have to. *Time since* is
    `now - last_disagreement_at(engine)`.

    Sycophancy drift is invisible from inside a conversation — each individual
    agreement is reasonable, and the pattern only shows in aggregate. This one
    number makes it measurable, and it is the earliest available warning that
    the most important behavior in the specification is failing (§4.7).
    """
    with engine.connect() as connection:
        return connection.execute(
            text("select max(created_at) from deliberations where outcome <> 'agreed_from_start'")
        ).scalar()


def _blind_record_from(row: Row[Any]) -> BlindPositionRecord:
    return BlindPositionRecord(
        id=row.id,
        project_id=row.project_id,
        conversation_id=row.conversation_id,
        message_id=row.message_id,
        model_call_id=row.model_call_id,
        persona_id=row.persona_id,
        position=row.position,
        confidence=Confidence(row.confidence),
        reasoning=row.reasoning,
        stripped_content=row.stripped_content,
        ordering=Ordering(row.ordering),
        classification=DeliberationClassification(row.classification),
        classified_by=ClassifiedBy(row.classified_by),
        created_at=row.created_at,
    )


def _record_from(row: Row[Any]) -> DeliberationRecord:
    return DeliberationRecord(
        id=row.id,
        project_id=row.project_id,
        conversation_id=row.conversation_id,
        message_id=row.message_id,
        position=row.position,
        confidence=Confidence(row.confidence),
        reasoning=row.reasoning,
        stripped_content=row.stripped_content,
        ordering=Ordering(row.ordering),
        user_response=row.user_response,
        outcome=Outcome(row.outcome),
        what_changed_her_mind=row.what_changed_her_mind,
        both_positions=row.both_positions,
        predictions=row.predictions,
        classification=DeliberationClassification(row.classification),
        classified_by=ClassifiedBy(row.classified_by),
        blind_position_id=row.blind_position_id,
        created_at=row.created_at,
    )
