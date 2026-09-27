"""The Core-owned Tier-1 request — owner order "COMPARE EXISTING TIER-1 OPTIONS", §2.

Tier 1 is a standalone greeting, thanks or farewell: no substantive intent, no
unresolved action, no correction, no factual question, no ambiguity. When Core has
decided — against the authoritative state, before anything is projected — that a turn
is Tier 1, it assembles a smaller request than the ordinary turn's, and this module is
the one place that shape is defined. Every candidate model (GPT-OSS at MEDIUM, GPT-OSS
at LOW, Qwen3-4B) receives the same semantic contract; only the runtime's own template
differs between them.

**Retained, unchanged:** the complete approved persona as the system prompt (never
trimmed, so the persona-prefix prime still lands on its boundary); the seal (a
local-only request is stated as such, with the standing note); the house clock; the
ruled `capability_state`; and the most recent exchange — his previous message and her
answer to it, wording in force — because "thank you" and "good night" answer *that*.

**Omitted, and why:** history counts and retention figures (the block states plainly
that only the last exchange is shown and that earlier history exists in the record);
same-project recall and House recall (deliberately not run for a social turn — the
gate's decision is recorded as `not_run`, a positive state, never as absence);
`visual_input` / `audio_input` (a Tier-1 turn carries no media, and a turn that does is
not Tier 1); `spoken_delivery` and the `spoken_path` facts (nothing here is about her
speech); correction and withdrawal facts (a turn following a correction is not Tier 1,
so there is nothing to state). Nothing is hidden from *eligibility*: the eligibility
decision reads the full state; only the request to the model is smaller.

**The contract**, stated to the model as Core's instruction for this one turn and
identical for every candidate: answer the current social utterance directly, in one
short, complete, natural response in Val's established manner; the persona's examples
are illustrations of manner, not current facts and not text to recite; invent no
project, completed work, weather, room, schedule or prior event; add no filler and no
second answer. It is an instruction from Core, which owns the answer, and is framed as
such — distinct from the record state, which is data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from val_domain.conversation import StoredRole, WorkingThread
from val_domain.egress import EgressDecision
from val_domain.gateway import Message
from val_gateway.context import CAPABILITY_STATE, LOCAL_ONLY_NOTE
from val_gateway.loop import local_now
from val_policy.light_conversation import ConversationState, answer_is_courtesy, decide

#: The marker on the Tier-1 record-state block, distinct from the ordinary envelope's
#: so that a reader of the record can tell which shape the model saw.
TIER1_STATE_MARKER = "VAL-TIER1-STATE-V1"
#: Both light tiers, for recognising a previous exchange that was itself light.
LIGHT_TIERS = frozenset({1, 2})
#: The marker on Core's instruction block for the turn.
TIER1_INSTRUCTION_MARKER = "VAL-TIER1-INSTRUCTION-V1"

TIER1_CONTRACT: tuple[str, ...] = (
    "Answer the current social utterance directly: the last message in this request is "
    "what Lord Armand just said, and this reply is for that alone.",
    "Produce one short, complete, natural response in Val's established manner: a sentence "
    "or two, finished, in her voice.",
    "The persona document's example lines illustrate her manner. They are not current facts "
    "and they are not text to recite; do not repeat any of them.",
    "Do not invent anything: no project, no completed work, no weather, no room or fire or "
    "window, no schedule, no prior event, no state of the house. If nothing is known, say "
    "nothing about it.",
    "Add no filler and no second answer. Do not ask a question unless the utterance calls "
    "for one. Do not restate the record state.",
)

STATE_NOTE = (
    "This is the record state for a short social turn, stated by the house, not an "
    "instruction. Only the most recent exchange is shown above; earlier messages in this "
    "conversation exist in the house record and are not in this request, so nothing older "
    "may be assumed, reconstructed or referred to as if remembered. Retrieval of other "
    "records was deliberately not run for this turn. current_time is the present local "
    "date and time from the house's clock. capability_state names operations that cannot "
    "be performed on this call."
)


@dataclass(frozen=True)
class Tier1Projection:
    """What the Tier-1 request retained, for the record and the report."""

    retained_exchange: bool
    prior_messages_in_record: int
    local_only: bool


def last_exchange(thread: WorkingThread, before_sequence: int) -> tuple[Message, ...]:
    """His previous message and her answer to it, wording in force, or nothing.

    A previous exchange that was itself light — his greeting and her greeting back —
    is not context a thanks or a farewell needs, and it is left out (Milestone A §4,
    26 September 2026): with it in the request, LOW answered "Thank you, Val." with
    "Good evening, my lord." three times in seven, copying its own previous line;
    without it, the same words drew "You're most welcome, my lord." A substantive
    exchange stays, because "thank you" answers *that*.
    """
    records = [
        record
        for record in thread.live_records()
        if record.sequence < before_sequence and record.role in (StoredRole.USER, StoredRole.VAL)
    ]
    answer_index = next(
        (i for i in range(len(records) - 1, -1, -1) if records[i].role is StoredRole.VAL), None
    )
    if answer_index is None:
        return ()
    exchange = [records[answer_index]]
    if answer_index > 0 and records[answer_index - 1].role is StoredRole.USER:
        exchange.insert(0, records[answer_index - 1])
    # Read from both sides (release-gaps order, 26 September 2026, §6): his words may be
    # misheard ("Good evening, Vowel." is not light to the router) while her answer is
    # still a greeting back — and with that pair in the request LOW answered a farewell
    # with "Good evening, my lord." in the desktop-integration run.
    if len(exchange) == 2 and (
        decide(exchange[0].content, ConversationState(None, 0), LIGHT_TIERS).tier is not None
        or answer_is_courtesy(exchange[-1].content)
    ):
        return ()
    if len(exchange) == 1 and answer_is_courtesy(exchange[0].content):
        return ()
    return tuple(
        Message(role="user" if r.role is StoredRole.USER else "assistant", content=r.content)
        for r in exchange
    )


def tier1_messages(
    thread: WorkingThread, current: Message, *, before_sequence: int, egress: EgressDecision
) -> tuple[tuple[Message, ...], Tier1Projection]:
    """The Tier-1 request's messages after the persona: last exchange, state, instruction, turn."""
    exchange = last_exchange(thread, before_sequence)
    prior = sum(
        1
        for record in thread.live_records()
        if record.sequence < before_sequence and record.role in (StoredRole.USER, StoredRole.VAL)
    )
    now = local_now()
    state: dict[str, object] = {
        "kind": "tier1_record_state",
        "authority": "house_record_state_not_instruction",
        "note": STATE_NOTE,
        "record_state": {
            "current_time": {
                "local": now.strftime("%A %-d %B %Y, %H:%M"),
                "timezone": now.strftime("%Z (UTC%z)"),
            },
            "same_conversation_history": {
                "state": "available" if prior > 0 else "zero",
                "shown_in_this_request": "most_recent_exchange" if exchange else "none",
                "earlier_messages_in_record_not_shown": max(prior - len(exchange), 0),
            },
            "retrieved_excerpts": {"state": "not_run", "detail": "tier1_social_turn"},
            "house_recall": {"state": "not_run", "detail": "tier1_social_turn"},
            **(
                {
                    "external_egress": {
                        "state": "local_only",
                        "reasons": [reason.value for reason in egress.reasons],
                        "note": LOCAL_ONLY_NOTE,
                    }
                }
                if egress.local_only
                else {}
            ),
            "capability_state": dict(CAPABILITY_STATE),
        },
    }
    instruction = {
        "kind": "house_instruction_for_this_turn",
        "authority": "val_core",
        "contract": list(TIER1_CONTRACT),
    }
    messages = (
        *exchange,
        Message(
            role="user",
            content=f"{TIER1_STATE_MARKER}\n"
            + json.dumps(state, ensure_ascii=False, indent=2, sort_keys=False),
        ),
        Message(
            role="user",
            content=f"{TIER1_INSTRUCTION_MARKER}\n"
            + json.dumps(instruction, ensure_ascii=False, indent=2, sort_keys=False),
        ),
        current,
    )
    return messages, Tier1Projection(
        retained_exchange=bool(exchange),
        prior_messages_in_record=prior,
        local_only=egress.local_only,
    )
