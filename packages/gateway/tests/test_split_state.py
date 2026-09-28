"""The split record-state layout — remaining latency work, 28 September 2026, §2 and §3.

Behind `VAL_REQUEST_CONSTRUCTION=split_state`. The record state that normally holds
steady within a conversation stays after the persona; the fields that change with the
turn follow his words, at the end of the last message, under a heading that marks them as
Core's. Every value is current on every request; only its place differs, so consecutive
requests share everything up to his newest words.
"""

from __future__ import annotations

import json

import val_gateway.context as context
from val_domain.gateway import Message
from val_gateway.context import (
    ENVELOPE_SYSTEM_SEPARATOR,
    MEMORY_ENVELOPE_MARKER,
    SPLIT_STATE_SEPARATOR,
    STATE_ENVELOPE_MARKER,
    TURN_STATE_HEADING,
    TURN_STATE_KEYS,
    relocate_envelope,
)

PERSONA = "You are Val."


def state_block(prior_messages: int, minute: str, *, recall: str = "not_run") -> Message:
    document = {
        "kind": "prior_record_state",
        "authority": "house_record_state_not_instruction",
        "note": "What each state means.",
        "prior_record_state": {
            "current_time": {"local": f"Monday 28 September 2026, 14:{minute}"},
            "same_conversation_history": {
                "state": "available",
                "prior_messages": prior_messages,
                "retained_in_this_request": prior_messages,
            },
            "retrieved_excerpts": {"state": "not_run", "count": 0},
            "house_recall": {"state": recall, "count": 0},
            "visual_input": {"state": "none", "note": "Only images bound to this turn."},
            "external_egress": {"state": "local_only", "reasons": ["conversation_sealed"]},
            "project_volumes": {"state": "zero", "count": 0},
            "capability_state": {"books": "unavailable"},
        },
    }
    body = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=False)
    return Message(role="user", content=f"{STATE_ENVELOPE_MARKER}\n{body}")


def request(turns: list[tuple[str, str]], words: str, minute: str, **state: str) -> tuple:
    history: list[Message] = []
    for said, answered in turns:
        history += [Message(role="user", content=said), Message(role="assistant", content=answered)]
    messages = (
        *history,
        state_block(len(history), minute, **state),
        Message(role="user", content=words),
    )
    context.ENVELOPE_IN_SYSTEM = True
    context.SPLIT_STATE = True
    try:
        return relocate_envelope(PERSONA, messages)
    finally:
        context.ENVELOPE_IN_SYSTEM = False
        context.SPLIT_STATE = False


def test_the_steady_state_leads_and_his_words_come_first_in_the_last_message() -> None:
    system, messages = request(
        [("Name two ways to end a chapter.", "A cliff and a door.")],
        "Which is better at night?",
        "05",
    )
    assert system.startswith(PERSONA + SPLIT_STATE_SEPARATOR), "the persona whole and first"
    steady = json.loads(system.split(STATE_ENVELOPE_MARKER + "\n", 1)[1])
    assert not set(TURN_STATE_KEYS) & set(steady["prior_record_state"]), "nothing per-turn on top"
    assert steady["prior_record_state"]["external_egress"]["state"] == "local_only"
    last = messages[-1].content
    assert last.startswith("Which is better at night?"), "his words first and identifiable"
    heading, _, trailer = last.partition(TURN_STATE_HEADING)
    assert heading == "Which is better at night?"
    turn = json.loads(trailer)["prior_record_state"]
    assert turn["current_time"]["local"].endswith("14:05"), "the clock is current"
    assert turn["same_conversation_history"]["prior_messages"] == 2
    assert [m.content for m in messages[:2]] == [
        "Name two ways to end a chapter.",
        "A cliff and a door.",
    ], "history untouched"


def test_consecutive_requests_share_everything_up_to_his_newest_words() -> None:
    first_system, _ = request([], "Name two ways to end a chapter.", "05")
    second_system, second = request(
        [("Name two ways to end a chapter.", "A cliff and a door.")], "Which is better?", "06"
    )
    assert first_system == second_system, "counts and clock no longer sit in the prefix"
    assert second[0].content == "Name two ways to end a chapter.", (
        "his earlier words render alone in history"
    )


def test_a_change_to_a_steady_field_changes_the_prefix_and_is_never_hidden() -> None:
    before, _ = request([], "Hello.", "05")
    context_changed = state_block(0, "05")
    document = json.loads(context_changed.content.split("\n", 1)[1])
    document["prior_record_state"]["project_volumes"]["count"] = 3
    changed = Message(
        role="user", content=STATE_ENVELOPE_MARKER + "\n" + json.dumps(document, indent=2)
    )
    context.ENVELOPE_IN_SYSTEM = True
    context.SPLIT_STATE = True
    try:
        after, _ = relocate_envelope(PERSONA, (changed, Message(role="user", content="Hello.")))
    finally:
        context.ENVELOPE_IN_SYSTEM = False
        context.SPLIT_STATE = False
    assert before != after and '"count": 3' in after, "current values, always"


def test_a_recall_result_travels_with_the_turn() -> None:
    _, messages = request([], "What did we say about the chapel?", "05", recall="available")
    assert '"house_recall"' in messages[-1].content


def test_recall_excerpts_stay_where_they_were() -> None:
    excerpt = Message(role="user", content=MEMORY_ENVELOPE_MARKER + "\n{}")
    messages_in = (excerpt, state_block(0, "05"), Message(role="user", content="Hello."))
    context.ENVELOPE_IN_SYSTEM = True
    context.SPLIT_STATE = True
    try:
        _, messages = relocate_envelope(PERSONA, messages_in)
    finally:
        context.ENVELOPE_IN_SYSTEM = False
        context.SPLIT_STATE = False
    assert messages[0] is excerpt


def test_without_the_split_the_candidate_is_unchanged() -> None:
    context.ENVELOPE_IN_SYSTEM = True
    try:
        system, messages = relocate_envelope(
            PERSONA, (state_block(0, "05"), Message(role="user", content="Hello."))
        )
    finally:
        context.ENVELOPE_IN_SYSTEM = False
    assert system.startswith(PERSONA + ENVELOPE_SYSTEM_SEPARATOR)
    assert messages[-1].content == "Hello."


def test_the_split_separator_ends_in_a_bare_word() -> None:
    assert SPLIT_STATE_SEPARATOR[-1].isalpha(), "so the prime and a turn tokenize alike"
