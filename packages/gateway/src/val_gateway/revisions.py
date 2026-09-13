"""The one writer for revision and retraction facts — ruling of 12 September 2026.

`04-layer-0.md` §2.1 (amendment of 12 September 2026): Lord Armand may correct
or withdraw a message he sent, and the record is never rewritten to do it. The
original `messages` row stays exactly what was said; each correction or
withdrawal is a new `message_revisions` row, numbered under the same
conversation row lock that numbers messages, so the fact's place in the
conversation's order — `after_sequence` — is exact.

## What this writer refuses, in words

- a message that does not exist, or is not Lord Armand's (Val's words are hers);
- a **revision** of a message that anchors an enforced blind position or a
  deliberation — it is part of a recorded decision exchange and cannot be
  rewritten; it may be retracted, or corrected by a new message;
- a revision with no wording, or one that changes nothing;
- a retraction of a message already withdrawn;
- any message in a conversation that has been removed;
- wording the Restricted preflight refuses — a correction will enter later
  assembly and recall, so it is checked before it becomes history, exactly as
  a sent message is.

The database's coherence trigger (`0016`) refuses the same structural cases for
any writer; this module says why first.

## What it never does

No provider call. An edit is not a turn: nothing is regenerated and no answer
is implied. No UPDATE and no DELETE anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Connection, Engine, text

from val_domain.conversation import MessageRevisionRecord, RevisionKind, StoredRole
from val_gateway.conversations import revision_record
from val_policy.restricted import preflight, refusal_message

#: Who records these facts. Retraction authority is per-author (§2.1).
AUTHOR = "Lord Armand"

_MESSAGE = text("select id, conversation_id, role, content from messages where id = :id")

_LOCK_CONVERSATION = text("select id from conversations where id = :id for update")

_REMOVED = text("select val_conversation_removed_at(:id)")

_HIGHEST_SEQUENCE = text("select max(sequence) from messages where conversation_id = :id")

_FACTS = text(
    "select id, conversation_id, message_id, revision_number, after_sequence, kind, "
    "       content, authored_by, note, created_at "
    "  from message_revisions where message_id = :id order by revision_number"
)

_DELIBERATED = text(
    "select exists (select 1 from blind_positions "
    "                where message_id = :id and ordering = 'enforced') "
    "    or exists (select 1 from deliberations where message_id = :id)"
)

_INSERT = text(
    "insert into message_revisions "
    "  (conversation_id, message_id, revision_number, after_sequence, kind, content, "
    "   authored_by, note) "
    "values (:conversation_id, :message_id, :revision_number, :after_sequence, :kind, "
    "        :content, :authored_by, :note) "
    "returning id, conversation_id, message_id, revision_number, after_sequence, kind, "
    "          content, authored_by, note, created_at"
)


class RevisionRefusedError(Exception):
    """The fact was not recorded, and `reason` says which rule refused it."""

    def __init__(self, reason: str, detail: str) -> None:
        self.reason = reason
        super().__init__(detail)


@dataclass(frozen=True)
class _Anchor:
    conversation_id: UUID
    current_content: str
    withdrawn: bool
    next_number: int
    after_sequence: int


def _anchor(connection: Connection, message_id: UUID) -> _Anchor:
    """Load, lock and check the message, inside the writing transaction."""
    row = connection.execute(_MESSAGE, {"id": message_id}).one_or_none()
    if row is None:
        raise RevisionRefusedError("not_found", f"message {message_id} does not exist")
    if row.role != StoredRole.USER.value:
        raise RevisionRefusedError(
            "not_authored_by_lord_armand",
            f"message {message_id} is a {row.role!r} message. Only Lord Armand's own "
            "messages may be corrected or withdrawn; Val's words are hers.",
        )
    # The conversation row lock, the same one `conversations.append` takes: no
    # message can be appended between reading the highest sequence and inserting.
    connection.execute(_LOCK_CONVERSATION, {"id": row.conversation_id})
    # A removed conversation is out of active use: its messages take no new facts
    # until it is reinstated (ruling, 12 September 2026).
    if connection.execute(_REMOVED, {"id": row.conversation_id}).scalar_one() is not None:
        raise RevisionRefusedError(
            "removed",
            "this conversation has been removed; reinstate it before correcting or "
            "withdrawing its messages",
        )
    highest = connection.execute(_HIGHEST_SEQUENCE, {"id": row.conversation_id}).scalar_one()
    facts = tuple(
        revision_record(fact) for fact in connection.execute(_FACTS, {"id": message_id}).all()
    )
    newest = facts[-1] if facts else None
    current = (
        newest.content
        if newest is not None and newest.kind is RevisionKind.REVISION and newest.content
        else row.content
    )
    return _Anchor(
        conversation_id=row.conversation_id,
        current_content=current,
        withdrawn=newest is not None and newest.kind is RevisionKind.RETRACTION,
        next_number=len(facts) + 1,
        after_sequence=int(highest),
    )


def _insert(
    connection: Connection,
    anchor: _Anchor,
    message_id: UUID,
    *,
    kind: RevisionKind,
    content: str | None,
    note: str | None,
) -> MessageRevisionRecord:
    cleaned_note = note.strip() if note is not None and note.strip() else None
    row = connection.execute(
        _INSERT,
        {
            "conversation_id": anchor.conversation_id,
            "message_id": message_id,
            "revision_number": anchor.next_number,
            "after_sequence": anchor.after_sequence,
            "kind": kind.value,
            "content": content,
            "authored_by": AUTHOR,
            "note": cleaned_note,
        },
    ).one()
    return revision_record(row)


def revise(
    engine: Engine, message_id: UUID, content: str, *, note: str | None = None
) -> MessageRevisionRecord:
    """Record a corrected wording of one of Lord Armand's messages.

    The wording is stored exactly as given. Later turns see it in the
    message's position; every earlier call keeps what it received.
    """
    if not content.strip():
        raise RevisionRefusedError(
            "empty",
            "a correction needs wording; to remove the message from the conversation, "
            "withdraw it instead",
        )
    finding = preflight((content,))
    if finding is not None:
        raise RevisionRefusedError("restricted", refusal_message(finding))
    with engine.begin() as connection:
        anchor = _anchor(connection, message_id)
        if connection.execute(_DELIBERATED, {"id": message_id}).scalar_one():
            raise RevisionRefusedError(
                "deliberated",
                "This message is part of a recorded decision exchange — Val formed a "
                "position on it, or a deliberation was recorded against it — and it cannot "
                "be rewritten. Send a correction as a new message, or withdraw the "
                "exchange; the record of the decision stays exactly as it happened.",
            )
        if not anchor.withdrawn and content == anchor.current_content:
            raise RevisionRefusedError(
                "unchanged", "the correction is the wording already in force; nothing changed"
            )
        return _insert(
            connection, anchor, message_id, kind=RevisionKind.REVISION, content=content, note=note
        )


def retract(engine: Engine, message_id: UUID, *, note: str | None = None) -> MessageRevisionRecord:
    """Withdraw one of Lord Armand's messages from the working conversation.

    The message and Val's immediate answer stay in the record, marked; they
    leave later assembly and both recall paths. Every classification,
    deliberation, judgment and cost attached to the exchange stays exactly as
    it was — a retraction deletes no evidence and invalidates none.
    """
    with engine.begin() as connection:
        anchor = _anchor(connection, message_id)
        if anchor.withdrawn:
            raise RevisionRefusedError("already_withdrawn", "this message is already withdrawn")
        return _insert(
            connection, anchor, message_id, kind=RevisionKind.RETRACTION, content=None, note=note
        )
