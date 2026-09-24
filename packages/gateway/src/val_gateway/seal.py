"""Applying the live-voice seal — owner ruling, 24 September 2026.

Voice work package 3 §2.1. The reading half of the seal lives in
`val_policy.egress`, which decides; this is the writing half, which records.

One rule governs everything here: **the seal is committed in the same transaction
as the canonical message that causes it.** Not afterwards, not on a worker thread,
not best-effort. If the message is in the store, the seal is too — otherwise there
would exist a window, however short, in which live-microphone-derived text is
canonical and the conversation is not sealed, and the moment immediately after
Voice is turned off is exactly when that window would be exploited by an ordinary
typed turn routing to a cloud provider.

The routes to canonical are named rather than assumed (§2.1's "every route" rule):

`utterance_finalized`
    the ordinary case — an utterance endpointed, settled, and submitted.
`resume_merge`
    the resume-before-delivery merge, where two halves of one sentence become one
    owner message.
`recovered_fragment_adopted`
    the owner adopting a provisional fragment a restart found open. It arrives as
    ordinary text through the ordinary door, and it is still live-microphone-derived
    text, so it still seals.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import Connection, Engine, text

__all__ = ["SealRoute", "apply_seal", "apply_seal_now", "seal_reason"]


class SealRoute(StrEnum):
    """How live-microphone-derived text reached canonical form."""

    UTTERANCE_FINALIZED = "utterance_finalized"
    RESUME_MERGE = "resume_merge"
    RECOVERED_FRAGMENT_ADOPTED = "recovered_fragment_adopted"


def seal_reason(route: SealRoute) -> str:
    """The owner ruling in its own words, carried on the row."""
    return (
        "live-microphone-derived text became a canonical message in this conversation "
        f"by {route.value}. Nothing from this conversation, and nothing derived from it, "
        "is transmitted off this machine — not by this turn, not by a later typed turn, "
        "and not by being recalled elsewhere (owner ruling, 24 September 2026, Voice "
        "work package 3 section 1.5). There is no unseal control."
    )


#: `ON CONFLICT DO NOTHING` because the seal is one fact about a conversation, not
#: one per spoken turn: the second utterance finds it already there. The first
#: message to seal is the one recorded, which is why the conflict is ignored rather
#: than updated — and an UPDATE would be refused by trigger in any case.
_APPLY = text(
    "insert into conversation_egress_seals (conversation_id, message_id, applied_by, reason) "
    "values (:conversation_id, :message_id, :applied_by, :reason) "
    "on conflict (conversation_id) do nothing"
)


def apply_seal(
    connection: Connection,
    conversation_id: UUID,
    message_id: UUID,
    *,
    route: SealRoute,
) -> None:
    """Seal this conversation, on the caller's own open transaction.

    Takes a `Connection` and not an `Engine` on purpose: the caller must already
    be inside the transaction that writes the message, and a function that opened
    its own would quietly break the atomicity rule while looking correct.
    """
    connection.execute(
        _APPLY,
        {
            "conversation_id": conversation_id,
            "message_id": message_id,
            "applied_by": route.value,
            "reason": seal_reason(route),
        },
    )


def apply_seal_now(
    engine: Engine, conversation_id: UUID, message_id: UUID, *, route: SealRoute
) -> None:
    """Seal in a transaction of its own.

    For the one case where the canonical message was committed by machinery this
    module does not own and cannot join — the resume merge, which corrects an
    already-persisted message through the append-only revision path. The message
    it names is already canonical and already sealed by the turn that submitted
    it; this exists so a merge that somehow reached canonical first still seals,
    rather than relying on the ordering of two writes.
    """
    with engine.begin() as connection:
        apply_seal(connection, conversation_id, message_id, route=route)
