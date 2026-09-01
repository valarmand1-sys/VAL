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

from dataclasses import dataclass
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
