"""Conversation lifecycle and the one authoritative message-append path — WP-0.7.

`04-layer-0.md` WP-0.7: *"a real conversation persists across a full application
restart and Val recalls prior context within a project"*, verified in part by
*"message ordering is stable and gapless under concurrent writes"*.

Everything a conversation is lives in PostgreSQL. This module is the only way in
and the only way out, which is what makes the restart criterion provable: there
is no in-process cache to survive, so there is nothing that *could* survive
except the rows.

## Creating a conversation requires settled scope

`create` takes a `ProjectScope` — `ResolvedProject | ExplicitNoProject`. An
`AmbiguousProject` is not of that type, so an unresolved exchange cannot open a
conversation at all. That is WP-0.6's guarantee extended one table further, and
it is why a NULL `conversations.project_id` can be read as *explicitly no
project* without a companion attribution column: the only writer refuses to
create one otherwise.

**Scope is then immutable.** Migration `0008` enforces it in the database. A
project switch starts a new conversation; the old one keeps its own history,
because the messages in it were said inside that scope and the `model_calls`
rows attributed to it say so.

## Sequence, and why it is not a PostgreSQL sequence

`sequence` is the conversation's order. `created_at` is not: two messages
written in one transaction can share a timestamp, and wall clocks move.

WP-0.7 requires the order be **gapless**, and that rules out the obvious
mechanism. A PostgreSQL `SEQUENCE` is deliberately non-transactional — its
whole value is that concurrent writers never wait on it — so a rolled-back
append consumes a number permanently and leaves a hole. Gapless and
lock-free-by-sequence are incompatible; the criterion picks gapless.

So `append` does this, in one transaction:

    SELECT ... FROM conversations WHERE id = :id FOR UPDATE   -- serialise
    SELECT coalesce(max(sequence), 0) + 1 FROM messages ...   -- next number
    INSERT INTO messages ...                                  -- take it
    UPDATE conversations SET last_message_at = ...            -- metadata

The row lock is held until commit, so two appenders to one conversation cannot
read the same maximum. A rollback releases the lock having committed nothing, and
the next appender computes the same number — the hole never opens. Appends to
*different* conversations never contend, because the lock is the conversation's
own row rather than a table or an advisory global.

**The unique constraint is the backstop, not the mechanism.**
`uq_messages_conversation_id_sequence` already existed; it turns any failure of
the reasoning above into a refused write rather than a duplicated order. A test
proving uniqueness only through the constraint would be proving the backstop
works, so the concurrency test asserts gaplessness too — which the constraint
alone would not give.

No advisory lock and no external lock service: the row that owns the order is
the row being ordered, and a second locking vocabulary would be one more thing
to get wrong.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Engine, text

from val_domain.conversation import (
    ConversationRecord,
    MessageRecord,
    MessageRevisionRecord,
    RevisionKind,
    StoredRole,
    WorkingThread,
    working_thread,
)
from val_domain.project import ProjectScope, attribution_of
from val_gateway.projects import load_project

_INSERT_CONVERSATION = text(
    "insert into conversations (project_id, title) values (:project_id, :title) "
    "returning id, project_id, title, started_at, last_message_at, archived_at"
)

_SELECT_CONVERSATION = text(
    "select id, project_id, title, started_at, last_message_at, archived_at "
    "from conversations where id = :id"
)

#: Locks the conversation row for the rest of the transaction. Every appender to
#: this conversation queues here; appenders to other conversations do not.
_LOCK_CONVERSATION = text("select id from conversations where id = :id for update")

_NEXT_SEQUENCE = text(
    "select coalesce(max(sequence), 0) + 1 from messages where conversation_id = :id"
)

_INSERT_MESSAGE = text(
    "insert into messages (conversation_id, role, content, sequence) "
    "values (:conversation_id, :role, :content, :sequence) "
    "returning id, conversation_id, role, content, sequence, created_at"
)

#: `greatest` rather than a bare assignment: `last_message_at` must never point
#: earlier than the newest committed message, and an append whose transaction
#: started before another's cannot be allowed to drag it backwards.
_TOUCH_CONVERSATION = text(
    "update conversations set last_message_at = greatest(last_message_at, now()) "
    "where id = :id returning last_message_at"
)

_SELECT_HISTORY = text(
    "select id, conversation_id, role, content, sequence, created_at "
    "from messages where conversation_id = :id order by sequence"
)


class ConversationNotFoundError(Exception):
    """A conversation id that names nothing.

    Fails loudly rather than returning `None`. A caller resuming a conversation
    that does not exist has lost track of what it is doing, and continuing with
    an empty history would silently start a *different* conversation wearing the
    same identifier.
    """

    def __init__(self, conversation_id: UUID) -> None:
        self.conversation_id = conversation_id
        super().__init__(
            f"no conversation {conversation_id}. Nothing was created in its place: "
            "resuming an identifier that names nothing would begin a different "
            "conversation under the same name."
        )


def _record(row: object) -> ConversationRecord:
    return ConversationRecord(
        id=row.id,  # type: ignore[attr-defined]
        project_id=row.project_id,  # type: ignore[attr-defined]
        title=row.title,  # type: ignore[attr-defined]
        started_at=row.started_at,  # type: ignore[attr-defined]
        last_message_at=row.last_message_at,  # type: ignore[attr-defined]
        archived_at=row.archived_at,  # type: ignore[attr-defined]
    )


def _message(row: object) -> MessageRecord:
    return MessageRecord(
        id=row.id,  # type: ignore[attr-defined]
        conversation_id=row.conversation_id,  # type: ignore[attr-defined]
        role=StoredRole(row.role),  # type: ignore[attr-defined]
        content=row.content,  # type: ignore[attr-defined]
        sequence=row.sequence,  # type: ignore[attr-defined]
        created_at=row.created_at,  # type: ignore[attr-defined]
    )


def create(engine: Engine, *, scope: ProjectScope, title: str) -> ConversationRecord:
    """Open a conversation in an already-settled scope.

    `scope` is required and is a `ProjectScope`. There is no default and no
    nullable project argument, so a caller who has not decided cannot express
    that here — the same shape as `converse`, for the same reason.
    """
    with engine.begin() as connection:
        row = connection.execute(
            _INSERT_CONVERSATION, {"project_id": attribution_of(scope), "title": title}
        ).one()
    return _record(row)


def listing(
    engine: Engine,
    *,
    project_id: UUID | None = None,
    explicit_none: bool = False,
    include_archived: bool = False,
) -> tuple[ConversationRecord, ...]:
    """Conversations, most recently active first — WP-0.10's history view.

    Three shapes, matching how scope is actually asked about: everything
    (neither filter), one project's conversations (`project_id`), or the
    explicitly-no-project ones (`explicit_none=True`). Asking for both at once
    is a contradiction and raises rather than picking one.

    Archived conversations are excluded by default — that is the whole of what
    archiving does (§2.1 amendment, 31 August 2026: presentation scoping,
    never evidentiary). Only this listing filters: `load`, `resume`, recall,
    and every capture path are archive-blind, so an archived conversation
    still behaves identically everywhere except the sidebar.
    """
    if project_id is not None and explicit_none:
        raise ValueError("a conversation is in a project or explicitly in none, never both")
    columns = (
        "select id, project_id, title, started_at, last_message_at, archived_at from conversations"
    )
    order = "order by last_message_at desc, id desc"
    clauses = [] if include_archived else ["archived_at is null"]
    if project_id is not None:
        clauses.append("project_id = :p")
    elif explicit_none:
        clauses.append("project_id is null")
    where = f"where {' and '.join(clauses)} " if clauses else ""
    statement = text(f"{columns} {where}{order}")
    with engine.connect() as connection:
        rows = connection.execute(
            statement, {"p": project_id} if project_id is not None else {}
        ).all()
    return tuple(_record(row) for row in rows)


def load(engine: Engine, conversation_id: UUID) -> ConversationRecord:
    """One conversation, by identity. Raises if it does not exist."""
    with engine.connect() as connection:
        row = connection.execute(_SELECT_CONVERSATION, {"id": conversation_id}).one_or_none()
    if row is None:
        raise ConversationNotFoundError(conversation_id)
    return _record(row)


def resume(engine: Engine, conversation_id: UUID) -> tuple[ConversationRecord, ProjectScope]:
    """Reopen a conversation and recover its scope from the authoritative record.

    **The stored `project_id` is the authority, not the session and not a
    model.** WP-0.7 requires that reopening restores project scope from records;
    this reads the row, resolves the project it names, and returns both. Session
    state is not consulted — a session pointing at Project Beta cannot make an
    Alpha conversation resume as Beta, which is the leak §18 exists to close.

    A conversation naming a project that is not in the catalogue raises
    `InconsistentConversationError` rather than degrading to explicit-none: a
    dangling reference is a broken row, not a decision to work outside every
    project.
    """
    conversation = load(engine, conversation_id)
    project = (
        None if conversation.project_id is None else load_project(engine, conversation.project_id)
    )
    return conversation, conversation.scope(project)


def append(
    engine: Engine, conversation_id: UUID, *, role: StoredRole, content: str
) -> MessageRecord:
    """Append one message and return it as persisted.

    The whole of this — lock, number, insert, touch — is one transaction. Either
    the message exists with its sequence and the conversation's metadata reflects
    it, or none of that happened.

    `content` is written exactly as given. Nothing here trims, normalises, or
    truncates it: the stored message is the record of what was said, and a
    representation better suited to some later purpose is that purpose's problem,
    not a licence to edit history (`00-charter.md` invariant 14).
    """
    with engine.begin() as connection:
        locked = connection.execute(_LOCK_CONVERSATION, {"id": conversation_id}).one_or_none()
        if locked is None:
            raise ConversationNotFoundError(conversation_id)

        sequence = connection.execute(_NEXT_SEQUENCE, {"id": conversation_id}).scalar_one()
        row = connection.execute(
            _INSERT_MESSAGE,
            {
                "conversation_id": conversation_id,
                "role": role.value,
                "content": content,
                "sequence": sequence,
            },
        ).one()
        connection.execute(_TOUCH_CONVERSATION, {"id": conversation_id})
    return _message(row)


# --- rename and archive: presentation-class writers (ruling, 12 September 2026) ---

#: The longest title a person may set. A label, not a summary; the refusal is
#: stated rather than the title silently shortened.
MAX_TITLE_LENGTH = 200

_RENAME = text(
    "update conversations set title = :title where id = :id "
    "returning id, project_id, title, started_at, last_message_at, archived_at"
)

#: Archiving an archived conversation keeps its first instant; unarchiving clears it.
_SET_ARCHIVED = text(
    "update conversations "
    "   set archived_at = case when :archived then coalesce(archived_at, now()) else null end "
    " where id = :id "
    "returning id, project_id, title, started_at, last_message_at, archived_at"
)


class TitleRefusedError(ValueError):
    """A title that cannot be a conversation's label — empty, or too long to be one."""


def rename(engine: Engine, conversation_id: UUID, title: str) -> ConversationRecord:
    """Set a conversation's title — ruling, 12 September 2026.

    `title` is presentation-class metadata (migration `0008`: "retitling a
    conversation changes a label; rescoping it changes what the record means").
    No evidence identity depends on it; every anchor is by id. No title history
    is kept, by ruling: a later reconstruction may show the current title beside
    an older excerpt, and that imprecision is accepted.
    """
    cleaned = title.strip()
    if not cleaned:
        raise TitleRefusedError("a conversation title cannot be empty")
    if len(cleaned) > MAX_TITLE_LENGTH:
        raise TitleRefusedError(
            f"a conversation title is a label of at most {MAX_TITLE_LENGTH} characters; "
            f"this one has {len(cleaned)}. Nothing was shortened on your behalf."
        )
    with engine.begin() as connection:
        row = connection.execute(_RENAME, {"id": conversation_id, "title": cleaned}).one_or_none()
    if row is None:
        raise ConversationNotFoundError(conversation_id)
    return _record(row)


def set_archived(engine: Engine, conversation_id: UUID, *, archived: bool) -> ConversationRecord:
    """Archive or unarchive a conversation — ruling, 12 September 2026.

    Archive means exactly: hidden from the default sidebar listing (§2.1
    amendment, 31 August 2026). It changes no attribution, recall, resumption,
    evidence, judgment or cost; the archived listing recovers it.
    """
    with engine.begin() as connection:
        row = connection.execute(
            _SET_ARCHIVED, {"id": conversation_id, "archived": archived}
        ).one_or_none()
    if row is None:
        raise ConversationNotFoundError(conversation_id)
    return _record(row)


def history(engine: Engine, conversation_id: UUID) -> tuple[MessageRecord, ...]:
    """Every message in this conversation, in `sequence` order.

    Ordered by `sequence` and never by `created_at`. The two normally agree; when
    they disagree, `sequence` is the one that was assigned under a lock.
    """
    with engine.connect() as connection:
        rows = connection.execute(_SELECT_HISTORY, {"id": conversation_id}).all()
    return tuple(_message(row) for row in rows)


# --- the working conversation (ruling, 12 September 2026) ----------------------

_SELECT_FACTS = text(
    "select id, conversation_id, message_id, revision_number, after_sequence, kind, "
    "       content, authored_by, note, created_at "
    "  from message_revisions where conversation_id = :id "
    " order by message_id, revision_number"
)


def revision_record(row: object) -> MessageRevisionRecord:
    """One `message_revisions` row as its domain record."""
    return MessageRevisionRecord(
        id=row.id,  # type: ignore[attr-defined]
        conversation_id=row.conversation_id,  # type: ignore[attr-defined]
        message_id=row.message_id,  # type: ignore[attr-defined]
        revision_number=row.revision_number,  # type: ignore[attr-defined]
        after_sequence=row.after_sequence,  # type: ignore[attr-defined]
        kind=RevisionKind(row.kind),  # type: ignore[attr-defined]
        content=row.content,  # type: ignore[attr-defined]
        authored_by=row.authored_by,  # type: ignore[attr-defined]
        note=row.note,  # type: ignore[attr-defined]
        created_at=row.created_at,  # type: ignore[attr-defined]
    )


def working(
    engine: Engine, conversation_id: UUID, *, as_of_sequence: int | None = None
) -> WorkingThread:
    """The conversation as it stood for the turn at `as_of_sequence` — or now.

    Reads the stored messages and the appended revision facts in one
    repeatable-read snapshot and applies `val_domain.conversation.working_thread`
    — the as-of rule stated once. The stored rows are returned untouched inside
    each `WorkingMessage`; only assembly uses the wording in force.
    """
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        history_rows = connection.execute(_SELECT_HISTORY, {"id": conversation_id}).all()
        fact_rows = connection.execute(_SELECT_FACTS, {"id": conversation_id}).all()
    return working_thread(
        tuple(_message(row) for row in history_rows),
        tuple(revision_record(row) for row in fact_rows),
        as_of_sequence=as_of_sequence,
    )
