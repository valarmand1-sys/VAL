"""The local wire canonicalization — owner ruling, 17 September 2026.

Root cause represented here: Val Core structurally sends the record-state
envelope and the current user turn as two adjacent user messages; LM Studio's
two ingress paths merged that pair differently (SDK `Chat`: content parts with
no separator; chat-completions: one string with a blank line), so the exact
preflight and the inference request rendered different prompts on a
Jinja-templated model (5,560 vs 5,561, Qwen3.8-27B). The local adapter now
canonicalizes consecutive same-role messages into one message, joined by one
blank line, before BOTH branches — the same sequence feeds the inspector and the
request. Core is unchanged.
"""

from __future__ import annotations

from val_domain.gateway import Message
from val_providers.lmstudio_adapter import WIRE_SEPARATOR, _chat_turns, canonicalize_turns

PERSONA = "Val is Maester to House Armand — the persona, whole."
ENVELOPE = (
    'VAL-STATE-V1 {"prior_record": {"state": "none"}, "capability_state": {"books": "unavailable"}}'
)
TURN = "Good evening, Val. What shall we turn our attention to?"


def _t(role: str, content: str) -> dict[str, str]:
    return {"role": role, "content": content}


# --- A. one isolated message --------------------------------------------------------------


def test_a_single_message_is_returned_unchanged() -> None:
    assert canonicalize_turns([_t("user", "hello")]) == [_t("user", "hello")]
    assert canonicalize_turns([]) == []


# --- B. alternating roles -----------------------------------------------------------------


def test_alternating_roles_are_untouched() -> None:
    turns = [_t("system", "S"), _t("user", "U1"), _t("assistant", "A1"), _t("user", "U2")]
    assert canonicalize_turns(turns) == turns


# --- C / D. two and three consecutive user messages --------------------------------------


def test_two_consecutive_user_messages_become_one_joined_by_one_blank_line() -> None:
    assert canonicalize_turns([_t("user", "first"), _t("user", "second")]) == [
        _t("user", "first\n\nsecond")
    ]


def test_three_consecutive_user_messages_become_one_in_order() -> None:
    result = canonicalize_turns([_t("user", "a"), _t("user", "b"), _t("user", "c")])
    assert result == [_t("user", "a" + WIRE_SEPARATOR + "b" + WIRE_SEPARATOR + "c")]


# --- E. same-role assistant and system messages share the one role-based rule -------------


def test_consecutive_assistant_messages_follow_the_same_rule() -> None:
    result = canonicalize_turns([_t("user", "q"), _t("assistant", "x"), _t("assistant", "y")])
    assert result == [_t("user", "q"), _t("assistant", "x\n\ny")]


def test_consecutive_system_messages_follow_the_same_rule() -> None:
    assert canonicalize_turns([_t("system", "s1"), _t("system", "s2"), _t("user", "u")]) == [
        _t("system", "s1\n\ns2"),
        _t("user", "u"),
    ]


# --- F. never across a role boundary; order kept ------------------------------------------


def test_no_merge_across_a_role_boundary_and_order_is_preserved() -> None:
    turns = [_t("user", "u1"), _t("assistant", "a1"), _t("user", "u2"), _t("user", "u3")]
    assert canonicalize_turns(turns) == [
        _t("user", "u1"),
        _t("assistant", "a1"),
        _t("user", "u2\n\nu3"),
    ]


# --- G. no content loss, no other rewrite --------------------------------------------------


def test_no_content_is_lost_and_nothing_else_is_rewritten() -> None:
    parts = [
        "  leading and trailing  ",
        "line\nbreaks\n",
        "unicode — \u2018quotes\u2019 \u00a3",
        "",
    ]
    result = canonicalize_turns([_t("user", p) for p in parts])
    (only,) = result
    assert only["content"] == WIRE_SEPARATOR.join(parts)
    assert only["content"].replace(WIRE_SEPARATOR, "", len(parts) - 1) == "".join(parts)


# --- H. deterministic separator ------------------------------------------------------------


def test_the_separator_is_exactly_one_blank_line() -> None:
    assert WIRE_SEPARATOR == "\n\n"
    (only,) = canonicalize_turns([_t("user", "x"), _t("user", "y")])
    assert only["content"].count(WIRE_SEPARATOR) == 1 and only["content"] == "x\n\ny"


# --- I. idempotence -----------------------------------------------------------------------


def test_canonicalization_is_idempotent() -> None:
    turns = [
        _t("system", "S"),
        _t("user", ENVELOPE),
        _t("user", TURN),
        _t("assistant", "A"),
        _t("user", "U"),
    ]
    once = canonicalize_turns(turns)
    assert canonicalize_turns(once) == once
    assert canonicalize_turns(canonicalize_turns(once)) == once


# --- J. the actual Val shape: persona, record-state envelope, current user turn -----------


def test_the_val_shape_becomes_one_user_message_with_the_envelope_then_the_turn() -> None:
    messages = (Message(role="user", content=ENVELOPE), Message(role="user", content=TURN))
    turns = _chat_turns(messages, PERSONA)
    assert [t["role"] for t in turns] == ["system", "user"], "one deterministic user message"
    assert turns[0]["content"] == PERSONA
    body = turns[1]["content"]
    assert ENVELOPE in body and TURN in body
    assert body.index(ENVELOPE) < body.index(TURN), "order unchanged"
    assert body == ENVELOPE + WIRE_SEPARATOR + TURN, "exactly one blank line, nothing else changed"
    assert body.count(WIRE_SEPARATOR) == 1
    assert canonicalize_turns(turns) == turns, "idempotent on the shape"


def test_a_val_shape_with_history_keeps_every_boundary_between_roles() -> None:
    messages = (
        Message(role="user", content="earlier question"),
        Message(role="assistant", content="earlier answer"),
        Message(role="user", content=ENVELOPE),
        Message(role="user", content=TURN),
    )
    turns = _chat_turns(messages, PERSONA)
    assert [t["role"] for t in turns] == ["system", "user", "assistant", "user"]
    assert turns[1]["content"] == "earlier question" and turns[2]["content"] == "earlier answer"
    assert turns[3]["content"] == ENVELOPE + WIRE_SEPARATOR + TURN
