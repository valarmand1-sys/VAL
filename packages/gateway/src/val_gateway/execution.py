"""The one writer for execution events — WP-0.8.

`04-layer-0.md` WP-0.8: *"every acceptance, rejection, revision, and correction
writes an `execution_events` row with its reason"*, verified in part by *"a
rejection without a stated reason prompts for one. Declining to give a reason
records `reason_source = absent` rather than fabricating one."*

## Where the prompt lives at Layer 0

There is no interface until WP-0.10, so "prompts for one" is enforced at the
API boundary: **an event offered without a reason and without an explicit
declination is refused**, with an error that tells the caller to ask. The
caller — today a person invoking this directly, later the WP-0.10 interface —
either returns with Lord Armand's words (`reason_source = STATED`), with what
Val inferred (`INFERRED`), or with the fact that he declined
(`declined_to_give_reason=True` → `ABSENT`). There is no path on which a
missing reason quietly becomes a recorded event, and no path on which one is
invented.

The criterion names rejection, and §2.2 says a null reason is *a defect to be
surfaced* on every event — so the same contract covers all four event types.
A **reaction-only** record is different: a reaction is an observation, not a
decision, and demanding a rationale for "he was enthusiastic" would manufacture
exactly the reason-shaped noise `reason_source` exists to keep out. Reaction-only
records therefore carry `ABSENT` without ceremony (a reason may still be
attached when one was actually given).

## What is derived rather than trusted

`project_id` comes from the anchoring conversation's stored scope — WP-0.7's
doctrine that the conversation's own record is the authority. The message must
belong to the conversation, checked before writing, so an event cannot pair a
conversation with a turn from a different one (the same incoherence the
provenance verifier refuses on calls).

## What this module does not do

It never infers a reaction from wording, never infers `approved` from
enthusiasm (§2.2 / §2.4), never updates or deletes (`0009` refuses UPDATE; §2.3
refuses DELETE), and it is not the WP-0.9 deliberation classifier arriving
early: it records what the caller states, completely, at insert time.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Engine, text

from val_domain.execution import (
    ExecutionEventRecord,
    ExecutionEventType,
    Reaction,
    ReasonSource,
)

_ANCHOR = text(
    "select m.conversation_id as message_conversation, c.project_id "
    "  from messages m "
    "  join conversations c on c.id = m.conversation_id "
    " where m.id = :message_id"
)

_INSERT = text(
    "insert into execution_events "
    "  (project_id, conversation_id, message_id, event_type, subject, "
    "   reason, reason_source, reaction) "
    "values "
    "  (:project_id, :conversation_id, :message_id, :event_type, :subject, "
    "   :reason, :reason_source, :reaction) "
    "returning id, project_id, conversation_id, message_id, event_type, subject, "
    "          reason, reason_source, reaction, created_at"
)


class ReasonRequiredError(Exception):
    """An event was offered with no reason and no declination. Ask, then record.

    This is the WP-0.8 prompt, expressed where Layer 0 can express it: the
    caller is told to put the question. Nothing is written — a record created
    before the question is answered would have to guess the answer.
    """

    def __init__(self, event_type: ExecutionEventType) -> None:
        self.event_type = event_type
        super().__init__(
            f"a {event_type.value!r} event needs its reason. Ask why — and record "
            "his words with reason_source=STATED, what Val inferred with INFERRED, "
            "or, if he declines to say, pass declined_to_give_reason=True so the "
            "absence is recorded as a fact rather than papered over "
            "(04-layer-0.md WP-0.8)."
        )


class IncoherentEventError(Exception):
    """The event's fields cannot describe one real occurrence."""


def record_event(
    engine: Engine,
    *,
    conversation_id: UUID,
    message_id: UUID,
    subject: str,
    event_type: ExecutionEventType | None = None,
    reaction: Reaction | None = None,
    reason: str | None = None,
    reason_inferred: bool = False,
    declined_to_give_reason: bool = False,
) -> ExecutionEventRecord:
    """Record one execution event, completely, at insert time.

    `subject` says what was accepted or rejected, in free text (§2.2).
    `reason` carries Lord Armand's words when he gave them; set
    `reason_inferred=True` when the text is Val's inference instead — the two
    are different evidence and are never conflated. `declined_to_give_reason`
    records an explicit declination as `ABSENT`.

    A reaction is recorded only when observed, never inferred from wording
    (§2.2 amendment). At least one of `event_type` and `reaction` must be
    present — a row that says nothing is not a record.
    """
    if event_type is None and reaction is None:
        raise IncoherentEventError(
            "an event must carry an event_type, a reaction, or both. A row with "
            "neither says nothing, and a record that says nothing is noise wearing "
            "a record's shape (§2.2)."
        )
    if not subject.strip():
        raise IncoherentEventError(
            "subject is what was accepted or rejected; an event about nothing cannot be read later."
        )

    if reason is not None and declined_to_give_reason:
        raise IncoherentEventError(
            "a reason was provided AND marked declined. One of these is not true, "
            "and recording either would make reason_source untrustworthy exactly "
            "where it is load-bearing."
        )
    if reason is None and reason_inferred:
        raise IncoherentEventError(
            "reason_inferred says how the reason text came to exist; without reason "
            "text there is nothing for it to describe."
        )

    if reason is not None:
        source = ReasonSource.INFERRED if reason_inferred else ReasonSource.STATED
    elif event_type is not None and not declined_to_give_reason:
        # The WP-0.8 prompt. Nothing is written until the question is answered
        # or explicitly declined.
        raise ReasonRequiredError(event_type)
    else:
        # An explicit declination, or a reaction-only observation — in both
        # cases the absence is the recorded fact.
        source = ReasonSource.ABSENT

    with engine.begin() as connection:
        anchor = connection.execute(_ANCHOR, {"message_id": message_id}).one_or_none()
        if anchor is None:
            raise IncoherentEventError(
                f"message {message_id} does not exist. An execution event records a "
                "judgment about something that was actually said."
            )
        if anchor.message_conversation != conversation_id:
            raise IncoherentEventError(
                f"message {message_id} belongs to conversation "
                f"{anchor.message_conversation}, not {conversation_id}. An event "
                "pairing a conversation with another conversation's turn would be "
                "a judgment about an exchange that never happened."
            )

        row = connection.execute(
            _INSERT,
            {
                # Derived from the conversation's stored scope, never supplied:
                # an event cannot claim a project its conversation was not in.
                "project_id": anchor.project_id,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "event_type": None if event_type is None else event_type.value,
                "subject": subject,
                "reason": reason,
                "reason_source": source.value,
                "reaction": None if reaction is None else reaction.value,
            },
        ).one()

    return ExecutionEventRecord(
        id=row.id,
        project_id=row.project_id,
        conversation_id=row.conversation_id,
        message_id=row.message_id,
        event_type=None if row.event_type is None else ExecutionEventType(row.event_type),
        subject=row.subject,
        reason=row.reason,
        reason_source=ReasonSource(row.reason_source),
        reaction=None if row.reaction is None else Reaction(row.reaction),
        created_at=row.created_at,
    )


def events_for(engine: Engine, conversation_id: UUID) -> tuple[ExecutionEventRecord, ...]:
    """Every event recorded against one conversation, oldest first."""
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "select id, project_id, conversation_id, message_id, event_type, "
                "       subject, reason, reason_source, reaction, created_at "
                "  from execution_events where conversation_id = :c order by created_at, id"
            ),
            {"c": conversation_id},
        ).all()
    return tuple(
        ExecutionEventRecord(
            id=row.id,
            project_id=row.project_id,
            conversation_id=row.conversation_id,
            message_id=row.message_id,
            event_type=None if row.event_type is None else ExecutionEventType(row.event_type),
            subject=row.subject,
            reason=row.reason,
            reason_source=ReasonSource(row.reason_source),
            reaction=None if row.reaction is None else Reaction(row.reaction),
            created_at=row.created_at,
        )
        for row in rows
    )
