"""House Recall grounding continuity, as provenance — ruling of 13 September 2026.

When House Recall supplied excerpts to the response call that produced a Val
answer, that answer was grounded in retrieved House records at the time. The
excerpts themselves are supplied only to that call. This module records which
sources they were — exactly, including which wording of each — and derives, for
a later turn whose retained history contains that answer, the provenance-only
fact that it was grounded and in what.

**Provenance, never content.** Nothing here stores, reads back or forwards an
excerpt's wording. A later turn learns *that* an answer drew on named records,
not what they said; to quote or re-examine them they must be retrieved again,
and House Recall does not run merely because such a fact exists.

**Exact source state.** A row names the source message and the revision fact in
force when it was retrieved (`source_revision_number`, NULL for the original),
so a later correction cannot make the record point at wording the answer never
saw. The derived fact states the source's status now — unchanged, corrected
since, withdrawn since, or its conversation removed since — without reviving a
withdrawn source as live intent.

**Failure direction.** The rows are written immediately after Val's message is
persisted. If they could not be written, the answer simply carries no grounding
fact later, which is the state every answer before this ruling is in: absence of
provenance, never invented provenance. Nothing is backfilled from logs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Engine, text

from val_domain.conversation import MessageState, StoredRole, WorkingThread
from val_gateway.memory import RecalledMessage

_LOGGER = logging.getLogger("val.grounding")

HOUSE_RECALL = "house_recall"

_INSERT = text(
    "insert into answer_recall_sources "
    "  (conversation_id, answer_message_id, model_call_id, retrieval_path, rank_position, "
    "   source_message_id, source_conversation_id, source_sequence, source_revision_number, "
    "   source_project_id, source_sent_at, source_conversation_title) "
    "values (:conversation_id, :answer_message_id, :model_call_id, :retrieval_path, "
    "        :rank_position, :source_message_id, :source_conversation_id, :source_sequence, "
    "        :source_revision_number, :source_project_id, :source_sent_at, :source_title)"
)

#: The recorded sources of some answers, with each source's status now. Titles and
#: project names are read as they are now, for presentation; identity is the ids.
_SOURCES_FOR = text(
    "select s.answer_message_id, s.rank_position, s.source_message_id, "
    "       s.source_conversation_id, s.source_conversation_title, s.source_sequence, "
    "       s.source_revision_number, s.source_project_id, s.source_sent_at, "
    "       m.role::text as source_role, p.name as source_project_name, "
    "       mc.newest_revision_number, mc.live as source_live, "
    "       val_conversation_removed_at(s.source_conversation_id) as source_removed_at "
    "  from answer_recall_sources s "
    "  join messages m on m.id = s.source_message_id "
    "  join messages_current mc on mc.id = s.source_message_id "
    "  left join projects p on p.id = s.source_project_id "
    " where s.answer_message_id = any(cast(:ids as uuid[])) "
    " order by s.answer_message_id, s.rank_position"
)


@dataclass(frozen=True)
class GroundedSource:
    """One House Recall source an answer drew on, as provenance only."""

    message_id: UUID
    conversation_id: UUID
    conversation_title: str
    sequence: int
    speaker: str
    sent_at: datetime
    project_id: UUID | None
    project_name: str | None
    revision_number: int | None
    status_now: str

    @property
    def source_scope(self) -> str:
        if self.project_id is None:
            return "unassigned"
        return (
            f"project: {self.project_name}" if self.project_name else f"project: {self.project_id}"
        )


@dataclass(frozen=True)
class GroundedAnswer:
    """A retained Val answer that House Recall supported, by its position in the request."""

    answer_position: int
    sources: tuple[GroundedSource, ...]


def record_answer_sources(
    engine: Engine,
    *,
    conversation_id: UUID,
    answer_message_id: UUID,
    model_call_id: UUID | None,
    recalled: tuple[RecalledMessage, ...],
) -> int:
    """Bind a persisted Val answer to the House Recall sources its call received.

    Only `house_recall` excerpts are recorded. Returns how many rows were written.
    """
    sources = [item for item in recalled if item.retrieval_path == HOUSE_RECALL]
    if not sources:
        return 0
    if model_call_id is None:
        _LOGGER.warning(
            "answer %s drew on %d House Recall source(s) but its response call has no "
            "model_calls id; no grounding provenance is recorded rather than an unbound one",
            answer_message_id,
            len(sources),
        )
        return 0
    with engine.begin() as connection:
        for position, item in enumerate(sources, start=1):
            connection.execute(
                _INSERT,
                {
                    "conversation_id": conversation_id,
                    "answer_message_id": answer_message_id,
                    "model_call_id": model_call_id,
                    "retrieval_path": HOUSE_RECALL,
                    "rank_position": position,
                    "source_message_id": item.message_id,
                    "source_conversation_id": item.conversation_id,
                    "source_sequence": item.sequence,
                    "source_revision_number": item.revision_number,
                    "source_project_id": item.project_id,
                    "source_sent_at": item.sent_at or item.created_at,
                    "source_title": item.conversation_title,
                },
            )
    return len(sources)


def _status_now(row: object) -> str:
    if row.source_removed_at is not None:  # type: ignore[attr-defined]
        return "conversation removed since"
    if not row.source_live:  # type: ignore[attr-defined]
        return "withdrawn since"
    if row.newest_revision_number != row.source_revision_number:  # type: ignore[attr-defined]
        return "corrected since"
    return "unchanged"


def sources_for(
    engine: Engine, answer_message_ids: tuple[UUID, ...]
) -> dict[UUID, tuple[GroundedSource, ...]]:
    """The recorded House Recall sources of these answers, with status now."""
    if not answer_message_ids:
        return {}
    with engine.connect() as connection:
        rows = connection.execute(
            _SOURCES_FOR, {"ids": [str(item) for item in answer_message_ids]}
        ).all()
    grouped: dict[UUID, list[GroundedSource]] = {}
    for row in rows:
        grouped.setdefault(row.answer_message_id, []).append(
            GroundedSource(
                message_id=row.source_message_id,
                conversation_id=row.source_conversation_id,
                conversation_title=row.source_conversation_title,
                sequence=row.source_sequence,
                speaker="Lord Armand" if row.source_role == StoredRole.USER.value else "Val",
                sent_at=row.source_sent_at,
                project_id=row.source_project_id,
                project_name=row.source_project_name,
                revision_number=row.source_revision_number,
                status_now=_status_now(row),
            )
        )
    return {answer: tuple(items) for answer, items in grouped.items()}


def grounded_answers(
    engine: Engine, thread: WorkingThread, retained_from: int
) -> tuple[GroundedAnswer, ...]:
    """For the retained prior Val answers of one request, the grounding facts.

    Positions count the retained prior messages of the request from 1, oldest
    first — the same convention as the correction and withdrawal facts.
    """
    conversational = tuple(
        message
        for message in thread.live()
        if message.record.role in (StoredRole.USER, StoredRole.VAL)
    )
    prior = conversational[retained_from:][:-1]
    answers = {
        message.record.id: index + 1
        for index, message in enumerate(prior)
        if message.record.role is StoredRole.VAL and message.state is not MessageState.WITHDRAWN
    }
    found = sources_for(engine, tuple(answers))
    return tuple(
        GroundedAnswer(answer_position=answers[answer], sources=sources)
        for answer, sources in sorted(found.items(), key=lambda item: answers[item[0]])
    )
