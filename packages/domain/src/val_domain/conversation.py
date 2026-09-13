"""Conversations and messages as the authoritative store holds them — WP-0.7.

`04-layer-0.md` WP-0.7 requires that *"a real conversation persists across a
full application restart and Val recalls prior context within a project"*, and
that *"message ordering is stable and gapless under concurrent writes"*.

**The point of this module is that conversation state is House Armand state.**
Nothing here refers to a provider thread, a provider conversation id, or model
memory. A conversation is a row and its messages are rows, and the only way to
know what was said is to read them. That is what makes a restart survivable: an
application that has forgotten everything can recover the whole conversation
from PostgreSQL, because PostgreSQL is where the conversation actually lives
(`00-charter.md` — the authoritative store).

## Two role vocabularies, deliberately not merged

| Where | Values | Why |
|---|---|---|
| `messages.role` (stored) | `user`, `val`, `system` | §2.1. Val's own record, and *Val* spoke. |
| `Message.role` (provider) | `user`, `assistant` | Provider-neutral wire vocabulary. |

`StoredRole.VAL` becomes `assistant` on the way out. They are converted at one
place — `provider_role` — rather than being kept identical, because they are not
the same fact: renaming Val to "assistant" in her own history would make the
record describe the transport instead of the house.

**`system` is stored but never sent as a conversational turn.** The persona is
the system prompt and it comes from the `personas` table on every call (WP-0.5).
A stored `system` message is a record of something the application said, not an
instruction channel a later reader can write into.

## Scope is derived, never guessed

A conversation's project is `conversations.project_id`, and it is read as a
decision: a real id means that project, NULL means explicitly no project. That
reading is exact because **every writer resolves scope before creating a
conversation** — `AmbiguousProject` is not of the right type to create one, the
same guarantee WP-0.6 gives persistence.

This is also why there is no `legacy_unknown` conversation state. `model_calls`
needed one because nine rows predated the distinction; `conversations` had zero
rows when WP-0.7 began, so the clean set exists from the first row onward and
there is nothing to disambiguate. See `VAL_Open_Decisions.md` item 9.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from val_domain.gateway import Message
from val_domain.project import (
    ExplicitNoProject,
    ProjectRecord,
    ProjectScope,
    ResolutionSource,
    ResolvedProject,
)


class StoredRole(StrEnum):
    """`messages.role` — who spoke, in the house's own vocabulary."""

    #: Lord Armand.
    USER = "user"
    #: Val. Becomes `assistant` on the wire and nowhere else.
    VAL = "val"
    #: The application itself. Recorded, never sent as a conversational turn —
    #: the persona is the system prompt and it comes from `personas`.
    SYSTEM = "system"


def provider_role(role: StoredRole) -> str:
    """The wire role for a stored role.

    The one place the two vocabularies meet. `SYSTEM` has no conversational
    equivalent and raises rather than silently arriving as a `user` turn, which
    would let application bookkeeping read as something Lord Armand said.
    """
    if role is StoredRole.USER:
        return "user"
    if role is StoredRole.VAL:
        return "assistant"
    raise ValueError(
        f"{role.value!r} has no provider role. Stored `system` messages are the "
        "application's own record; the persona is the system prompt and is loaded "
        "from `personas` on every call (WP-0.5). Sending one as a conversational "
        "turn would present bookkeeping as something a participant said."
    )


@dataclass(frozen=True)
class MessageRecord:
    """One persisted message. The unit of conversational history.

    `sequence` is the order, not `created_at`. Two messages written in the same
    transaction can share a timestamp to the microsecond, and clock adjustment
    can reorder wall time; `sequence` is assigned under a lock and is unique per
    conversation by database constraint.
    """

    id: UUID
    conversation_id: UUID
    role: StoredRole
    content: str
    sequence: int
    created_at: datetime

    def as_provider_message(self) -> Message:
        """This turn as the provider will see it. Content is passed unchanged."""
        return Message(role=provider_role(self.role), content=self.content)


# --- revision and retraction as appended facts (ruling, 12 September 2026) -----


class RevisionKind(StrEnum):
    """`message_revisions.kind`."""

    #: A corrected wording of the message.
    REVISION = "revision"
    #: The message withdrawn from the working conversation.
    RETRACTION = "retraction"


class MessageState(StrEnum):
    """What the record says a user message currently is, as of some point."""

    CURRENT = "current"
    CORRECTED = "corrected"
    WITHDRAWN = "withdrawn"


@dataclass(frozen=True)
class MessageRevisionRecord:
    """One appended fact about one of Lord Armand's messages.

    `after_sequence` is the conversation's highest message sequence when the
    fact was recorded, read under the conversation row lock. It is the whole of
    the as-of rule: the turn whose message has sequence *s* sees this fact
    exactly when `after_sequence < s`.
    """

    id: UUID
    conversation_id: UUID
    message_id: UUID
    revision_number: int
    after_sequence: int
    kind: RevisionKind
    content: str | None
    authored_by: str
    note: str | None
    created_at: datetime


@dataclass(frozen=True)
class WorkingMessage:
    """A stored message as it stands at one point in the conversation's order.

    `record` is the stored row, untouched — its `content` is what was said.
    `content` is the wording in force at that point. For a Val message,
    `answered_state` is the state of the user message she immediately answered
    (None when the message before hers was not a user message), because her
    words stay attached to the wording she actually received.
    """

    record: MessageRecord
    content: str
    state: MessageState
    answered_state: MessageState | None = None
    revisions: tuple[MessageRevisionRecord, ...] = ()

    @property
    def live(self) -> bool:
        """Whether this message belongs to the working conversation: not withdrawn,
        and not Val's immediate answer to a withdrawn message."""
        return (
            self.state is not MessageState.WITHDRAWN
            and self.answered_state is not MessageState.WITHDRAWN
        )

    def working_record(self) -> MessageRecord:
        """The stored record with the wording in force — for assembly only.

        Identity, role, sequence and timestamp stay the stored row's; only the
        wording is the current one. Never persisted, never presented as what
        was originally said.
        """
        if self.content == self.record.content:
            return self.record
        return replace(self.record, content=self.content)


@dataclass(frozen=True)
class WorkingThread:
    """A conversation as it stands at one point in its own order."""

    messages: tuple[WorkingMessage, ...]

    def live(self) -> tuple[WorkingMessage, ...]:
        """The working conversation: withdrawn exchanges left out."""
        return tuple(message for message in self.messages if message.live)

    def live_records(self) -> tuple[MessageRecord, ...]:
        """The working conversation as records carrying the wording in force."""
        return tuple(message.working_record() for message in self.live())


def working_thread(
    history: tuple[MessageRecord, ...],
    facts: tuple[MessageRevisionRecord, ...],
    *,
    as_of_sequence: int | None = None,
) -> WorkingThread:
    """The conversation as it stood for the turn at `as_of_sequence`.

    **The as-of rule (ruling, 12 September 2026).** With `as_of_sequence = s`,
    only messages with `sequence <= s` exist, and only facts with
    `after_sequence < s` apply — a fact recorded after the turn's own message was
    appended is invisible to that turn, however the two raced, because both
    were numbered under the same conversation row lock. No timestamp is read.
    With `as_of_sequence = None` every message and every fact applies: the
    conversation as it stands now.

    For each user message the newest applicable fact decides: none → current;
    a revision → corrected, with its wording; a retraction → withdrawn. A
    revision after a retraction reinstates the message with the new wording.
    """
    visible = (
        history
        if as_of_sequence is None
        else tuple(record for record in history if record.sequence <= as_of_sequence)
    )
    applicable: dict[UUID, list[MessageRevisionRecord]] = {}
    for fact in sorted(facts, key=lambda item: (item.message_id, item.revision_number)):
        if as_of_sequence is not None and fact.after_sequence >= as_of_sequence:
            continue
        applicable.setdefault(fact.message_id, []).append(fact)

    working: list[WorkingMessage] = []
    previous: WorkingMessage | None = None
    for record in visible:
        own = tuple(applicable.get(record.id, ()))
        content = record.content
        state = MessageState.CURRENT
        if record.role is StoredRole.USER and own:
            newest = own[-1]
            if newest.kind is RevisionKind.REVISION and newest.content is not None:
                content, state = newest.content, MessageState.CORRECTED
            elif newest.kind is RevisionKind.RETRACTION:
                state = MessageState.WITHDRAWN
        answered_state = (
            previous.state
            if record.role is StoredRole.VAL
            and previous is not None
            and previous.record.role is StoredRole.USER
            else None
        )
        message = WorkingMessage(
            record=record,
            content=content,
            state=state,
            answered_state=answered_state,
            revisions=own,
        )
        working.append(message)
        if record.role in (StoredRole.USER, StoredRole.VAL):
            previous = message
    return WorkingThread(messages=tuple(working))


class InconsistentConversationError(Exception):
    """A conversation names a project that could not be resolved.

    Raised rather than returned: unlike an ambiguous *reference*, this is not a
    question the user can settle by choosing. The stored row and the catalogue
    disagree, and that is a fact about the database.
    """

    def __init__(self, conversation_id: UUID, project_id: UUID) -> None:
        self.conversation_id = conversation_id
        self.project_id = project_id
        super().__init__(
            f"conversation {conversation_id} is scoped to project {project_id}, which "
            "is not in the catalogue. Its scope cannot be established, and it is not "
            "treated as explicitly no-project: that would convert a broken reference "
            "into a decision nobody made."
        )


@dataclass(frozen=True)
class ConversationRecord:
    """One conversation as the authoritative store holds it.

    `project_id` is the scope and is immutable after creation — enforced by
    database trigger, not by convention (migration `0008`). A project switch
    starts a new conversation; it never rewrites this one. That is WP-0.6's
    forward-only doctrine applied to the conversation itself: *"corrections
    preserve lineage"* (`00-charter.md` invariant 14) means the record of what
    was said inside Project Alpha stays a record of Project Alpha.
    """

    id: UUID
    project_id: UUID | None
    title: str
    started_at: datetime
    last_message_at: datetime
    #: Presentation scoping only, never evidentiary (§2.1 amendment, 31 August
    #: 2026). An archived conversation still resumes and still recalls.
    archived_at: datetime | None = None
    #: Ruling, 12 September 2026: when the conversation was removed from active
    #: use, if it currently is — derived from `conversation_removals`, never a
    #: column. A removed conversation is excluded from recall and cannot resume;
    #: nothing in it is touched.
    removed_at: datetime | None = None

    @property
    def is_explicit_no_project(self) -> bool:
        """Whether this conversation was deliberately started outside any project."""
        return self.project_id is None

    def scope(self, project: ProjectRecord | None) -> ProjectScope:
        """This conversation's scope, as a WP-0.6 `ProjectScope`.

        The project record is supplied rather than looked up, because this
        package touches no database. The caller resolves it from the catalogue
        and is responsible for having validated that it exists —
        `val_gateway.conversations.resume` does both.

        A conversation with a `project_id` and no matching record is not a
        question anybody can answer, so it raises rather than degrading to
        explicit-none. Silently treating a dangling reference as *"no project"*
        would turn a broken row into a decision nobody made.
        """
        if self.project_id is None:
            return ExplicitNoProject(via=ResolutionSource.CONVERSATION)
        if project is None or project.id != self.project_id:
            raise InconsistentConversationError(self.id, self.project_id)
        return ResolvedProject(project=project, via=ResolutionSource.CONVERSATION)
