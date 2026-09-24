"""The live-voice seal: what may leave this machine, and what established that.

Owner ruling, 24 September 2026 — Voice work package 3 §1.5, §2.1, §2.6. The
rule it implements is one sentence: **a live microphone transcript never leaves
this Mac**, and neither does anything derived from it, in this conversation or
any other.

That is enforced here and in the gateway, structurally, rather than by a sentence
in the persona asking the model not to send something. A model cannot be the
guard on its own egress.

Three questions settle it, in the order §2.1 states them:

1. Is a Voice session live in this conversation right now? — the **transient**
   layer. It applies from the moment the owner turns Voice on, to every request
   the conversation makes while the session lasts, typed or spoken, and whether
   or not anything has yet been said.
2. Has live-microphone-derived text ever become a canonical message here? — the
   **durable** layer. It outlives the session and is not lifted by turning Voice
   off. There is no unseal control.
3. Does this request carry content recalled from a sealed conversation? — §2.6.
   The seal travels with the content, so a sealed conversation cannot reach a
   provider by being remembered somewhere else.

A Voice session that produced no canonical spoken text leaves the conversation
**unsealed**: turning Voice on blocks egress while it is on, and that is all
(§2.1, and the negative §19 names).
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import Engine, text

from val_domain.egress import ORDINARY, EgressDecision, LocalOnlyReason, sealed

__all__ = [
    "LiveVoiceConversations",
    "decide_egress",
    "escalate_for_recall",
    "is_conversation_sealed",
    "sealed_conversations",
]


class LiveVoiceConversations:
    """Which conversations have Voice on right now.

    Deliberately an interface over live state rather than a table: a session is
    live in one process and dies with it, and a durable row saying "Voice is on"
    that outlived a crash would be exactly the stored "Voice was enabled"
    preference §4.2 forbids. Nothing here can turn a microphone on; it only
    reports what the desktop's owner-started sessions already are.
    """

    def __init__(self, conversations: Iterable[UUID] = ()) -> None:
        self._conversations = {conversation for conversation in conversations}

    def active_in(self, conversation_id: UUID | None) -> bool:
        return conversation_id is not None and conversation_id in self._conversations


def is_conversation_sealed(engine: Engine, conversation_id: UUID | None) -> bool:
    """Whether live-microphone-derived text has ever become canonical here.

    Reads the durable seal, which is written in the same transaction as the
    first such message (§2.1's atomicity rule), so there is no window in which
    the message exists and this returns False.
    """
    if conversation_id is None:
        return False
    with engine.connect() as connection:
        found = connection.execute(
            text("SELECT 1 FROM conversation_egress_seals WHERE conversation_id = :conversation"),
            {"conversation": conversation_id},
        ).first()
    return found is not None


def sealed_conversations(engine: Engine, conversation_ids: Iterable[UUID]) -> frozenset[UUID]:
    """Which of these conversations are durably sealed. One query, not N."""
    wanted = [conversation for conversation in dict.fromkeys(conversation_ids)]
    if not wanted:
        return frozenset()
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT conversation_id FROM conversation_egress_seals "
                "WHERE conversation_id = ANY(:conversations)"
            ),
            {"conversations": wanted},
        ).all()
    return frozenset(row.conversation_id for row in rows)


def decide_egress(
    engine: Engine,
    conversation_id: UUID | None,
    *,
    live: LiveVoiceConversations | None = None,
    recalled_from: Iterable[UUID] = (),
) -> EgressDecision:
    """The one decision for this turn, taken before any call is routed.

    Taken once and carried, so every call a turn makes is governed by the same
    answer — the classifier's, the strip's, the blind position's and the final
    response's alike. Recomputing it per call would let one of them disagree.

    `recalled_from` is every conversation whose content this request will carry.
    Fails toward the seal: a conversation that cannot be read is not treated as
    unsealed here, because `is_conversation_sealed` raising is a failure to
    establish absence, not evidence of it.
    """
    reasons: list[LocalOnlyReason] = []
    if live is not None and live.active_in(conversation_id):
        reasons.append(LocalOnlyReason.VOICE_SESSION_ACTIVE)
    if is_conversation_sealed(engine, conversation_id):
        reasons.append(LocalOnlyReason.CONVERSATION_SEALED)
    others = [other for other in recalled_from if other != conversation_id]
    if others and sealed_conversations(engine, others):
        reasons.append(LocalOnlyReason.RECALLED_SEALED_CONTENT)
    return sealed(*reasons) if reasons else ORDINARY


def escalate_for_recall(
    engine: Engine,
    decision: EgressDecision,
    recalled_conversation_ids: Iterable[UUID],
) -> EgressDecision:
    """Apply §2.6: content recalled from a sealed conversation seals the request.

    Called where recall has just been assembled into a request and before a route
    is chosen, so the seal accounts for what the request *carries* and not merely
    for where it belongs. A request already local-only is returned unchanged — it
    cannot become more sealed — and its reasons are not padded with a second one
    that would add nothing.

    Sealed conversations are deliberately **not** excluded from recall. A voice
    conversation is remembered exactly as a typed one is (§1.6); what changes is
    that remembering it makes the remembering request local-only too.
    """
    if decision.local_only:
        return decision
    if not sealed_conversations(engine, recalled_conversation_ids):
        return decision
    return sealed(LocalOnlyReason.RECALLED_SEALED_CONTENT)
