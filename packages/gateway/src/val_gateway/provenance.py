"""Do the three ids on a conversation call actually agree? — WP-0.7 corrective.

`ConversationProvenance` asserts that a conversation call carries a
conversation, a triggering message, and a persona. It cannot assert that they
*belong together*: that is a fact about the database, and this module is where
it is checked.

**The failure this exists to prevent.** Independent review of
`VAL_Source_Snapshot_d137925.zip` observed that the lower-level contract could
be handed three unrelated UUIDs, so a `model_calls` row could record

    conversation A + a message from conversation B + project C

as though those facts agreed. Every column would be populated, every constraint
satisfied, and the row would be a coherent-looking lie — the worst shape a
record can take, because nothing downstream has any reason to doubt it.

**Checked before transmission, not after.** The foreign keys would eventually
refuse a *non-existent* id, but they would happily accept a real message from
the wrong conversation, and they only fire when the row is written — after the
provider has already been paid and the content has already left. A mismatch
that is detectable beforehand is refused beforehand. `00-charter.md`: an
indeterminate consequential action stops rather than proceeding.

**One query, not four.** Everything needed is reachable from the message row by
joining its conversation, so the check is a single read on an indexed primary
key. This runs on every conversation call, and a check expensive enough to be
worth skipping is a check that will be skipped.

**What it does not do.** It is not an audit trail, not a workflow, and it writes
nothing. It answers one question and raises if the answer is no.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from sqlalchemy import Engine, text

from val_domain.conversation import StoredRole
from val_domain.gateway import ConversationProvenance, GatewayRequest

#: Everything the coherence rules need, from the message outward. A message that
#: does not exist returns no row at all, which is itself one of the answers.
_COHERENCE = text(
    "select m.role      as message_role, "
    "       m.conversation_id as message_conversation, "
    "       c.project_id as conversation_project "
    "  from messages m "
    "  join conversations c on c.id = m.conversation_id "
    " where m.id = :message_id"
)


class IncoherentProvenanceError(Exception):
    """The ids on a conversation call do not describe one coherent event.

    Raised rather than returned. A caller that can carry on without knowing
    which conversation it is in has already lost the thread, and a
    `model_calls` row written from these ids would assert a relationship that
    does not exist.
    """


def verify(engine: Engine, provenance: ConversationProvenance, project_id: UUID | None) -> None:
    """Refuse a conversation call whose ids do not agree with the records.

    Checks, in the order a reader would ask them:

    1. the message exists;
    2. it is a **user** message — the triggering turn, not Val's reply, which
       does not exist when the call is made;
    3. it belongs to the conversation named;
    4. the conversation's scope is the scope this call is being attributed to,
       with `NULL` meaning explicitly no project on both sides.

    `project_id` is taken as the request holds it — the already-resolved value —
    rather than as a `ProjectScope`, so this module has no opinion about
    resolution and cannot be handed something unresolved to compare against.

    `persona_id` is present by construction — `ConversationProvenance` has no
    default for it — and is not re-read here: the persona is loaded from
    `personas` moments earlier by the WP-0.5 loader, so a second lookup would
    check the loader against itself.
    """
    with engine.connect() as connection:
        row = connection.execute(_COHERENCE, {"message_id": provenance.message_id}).one_or_none()

    if row is None:
        raise IncoherentProvenanceError(
            f"message {provenance.message_id} does not exist. A conversation call "
            "must name the persisted user message that caused it; a call naming "
            "nothing would be recorded as answering a question that was never asked."
        )

    if row.message_role != StoredRole.USER.value:
        raise IncoherentProvenanceError(
            f"message {provenance.message_id} is a {row.message_role!r} message. "
            "The triggering message is the user's turn — the question. Val's reply "
            "does not exist when the call is made, so a call attributed to one is "
            "attributed to something that had not happened yet."
        )

    if row.message_conversation != provenance.conversation_id:
        raise IncoherentProvenanceError(
            f"message {provenance.message_id} belongs to conversation "
            f"{row.message_conversation}, not {provenance.conversation_id}. Recording "
            "this call would assert that a turn in one conversation caused a reply in "
            "another, and every reader afterwards would have no reason to doubt it."
        )

    if row.conversation_project != project_id:
        stored = row.conversation_project or "no project"
        asked = project_id or "no project"
        raise IncoherentProvenanceError(
            f"conversation {provenance.conversation_id} is scoped to {stored}, but this "
            f"call is attributed to {asked}. Conversation scope is immutable (migration "
            "`0008`) and switching project starts a new conversation, so these can only "
            "disagree because the wrong one was supplied."
        )


def of(conversation_id: UUID, message_id: UUID, persona_id: UUID) -> ConversationProvenance:
    """Assemble provenance from three ids the caller already holds.

    A convenience with one purpose: keeping the argument order in one place, so
    a call site cannot transpose `conversation_id` and `message_id` — both
    UUIDs, both plausible, and a transposition would be caught by `verify` but
    only at runtime.
    """
    return ConversationProvenance(
        conversation_id=conversation_id, message_id=message_id, persona_id=persona_id
    )


def verifier(engine: Engine) -> Callable[[GatewayRequest], None]:
    """A verifier bound to one database, in the shape the gateway wants.

    The gateway holds no engine — it is given a recorder and a ledger rather
    than a connection, so that its routing and budget logic stay testable
    without one. Provenance verification is a database question, so it arrives
    the same way: as a callable the application supplies at construction.

    A gateway built **without** one refuses conversation calls rather than
    skipping the check. An optional guarantee is not a guarantee, and the
    failure would be silent in exactly the configuration that matters.
    """

    def check(request: GatewayRequest) -> None:
        if request.conversation is None:
            return
        verify(engine, request.conversation, request.project_id)

    return check
