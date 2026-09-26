"""Preparing a light answer before the turn is confirmed — owner order, 26 September 2026 (§6).

While his settled utterance waits out the resume window, Core may prepare the answer
it would give if he does not continue: the conversation assembled exactly as the
turn would assemble it, with the settled words in the current message's place, sent
to the light route. The result is **private** — not spoken, not persisted, not
remembered — until the completed request arrives and is found to be the very request
the preparation was made for. That binding is a digest over everything the model
saw: the persona, every assembled message in order, and the light task. Revised
wording, a resumed sentence or any change of state makes a different digest, and a
different digest is a discarded preparation.

One field is deliberately left out of the digest: the record-state envelope's
`current_time`, the house clock stated to the minute. A preparation begins when his
words settle and is bound at most a few seconds later, so the two requests can differ
only in that minute reading, and the answer prepared at 23:59 is the answer for
00:00. Everything else in the envelope — history counts, recall, seal, capability
state — stays in the digest, because a change there is a change in what she knew.

Every preparation is recorded, whatever became of it, with the call it made.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Engine, text

from val_domain.gateway import GatewayResponse, Message, TaskType

_RECORD = text(
    "insert into speculative_preparations "
    "  (conversation_id, utterance_sha256, tier, model_call_id, outcome, detail, "
    "   user_message_id, answer_message_id, prepared_ms) "
    "values (:conversation_id, :utterance_sha256, :tier, :model_call_id, :outcome, :detail, "
    "        :user_message_id, :answer_message_id, :prepared_ms)"
)


@dataclass(frozen=True)
class PreparedAnswer:
    """A light answer prepared for words he has not yet confirmed."""

    #: The settled words it was prepared for, exactly.
    content: str
    conversation_id: UUID | None
    tier: int
    #: The binding: a digest of the assembled request the answer was made from.
    fingerprint: str
    response: GatewayResponse
    prepared_ms: int

    @property
    def utterance_sha256(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()


#: The record-state envelope's marker line, as `val_gateway.context` writes it.
_ENVELOPE_MARKER = "VAL-STATE-V1"


def _bound_content(content: object) -> object:
    """A message's content as the digest sees it: the envelope without its clock."""
    if not isinstance(content, str) or not content.startswith(_ENVELOPE_MARKER + "\n"):
        return content
    try:
        document = json.loads(content[len(_ENVELOPE_MARKER) + 1 :])
    except ValueError:
        return content
    state = document.get("prior_record_state")
    if isinstance(state, dict):
        state.pop("current_time", None)
    return json.dumps(document, sort_keys=True, ensure_ascii=False)


def fingerprint(system: str, messages: tuple[Message, ...], task_type: TaskType) -> str:
    """What the model saw, digested: the persona, every message in order, the task."""
    document = json.dumps(
        {
            "system": system,
            "messages": [(message.role, _bound_content(message.content)) for message in messages],
            "task": task_type.value,
        },
        ensure_ascii=False,
    )
    return hashlib.sha256(document.encode()).hexdigest()


def record_preparation(
    engine: Engine,
    *,
    conversation_id: UUID | None,
    utterance_sha256: str,
    tier: int,
    outcome: str,
    model_call_id: UUID | None = None,
    detail: str | None = None,
    user_message_id: UUID | None = None,
    answer_message_id: UUID | None = None,
    prepared_ms: int | None = None,
) -> None:
    """One row per preparation: what became of it, and the call it made."""
    with engine.begin() as connection:
        connection.execute(
            _RECORD,
            {
                "conversation_id": conversation_id,
                "utterance_sha256": utterance_sha256,
                "tier": tier,
                "model_call_id": model_call_id,
                "outcome": outcome,
                "detail": detail,
                "user_message_id": user_message_id,
                "answer_message_id": answer_message_id,
                "prepared_ms": prepared_ms,
            },
        )
