"""The request-construction experiment's switch — release-gaps order §4, 26 September 2026.

Off (production), the assembled request is exactly what it was. On, and only on, the
record-state envelope leaves the user role for the system message after the persona,
and his words are the last user message alone; recall excerpts are not moved.
"""

from __future__ import annotations

import json

import val_gateway.context as context
from val_domain.gateway import Message
from val_gateway.context import (
    ENVELOPE_SYSTEM_SEPARATOR,
    MEMORY_ENVELOPE_MARKER,
    STATE_ENVELOPE_MARKER,
    relocate_envelope,
)

PERSONA = "You are Val."
MESSAGES = (
    Message(role="user", content="Earlier words."),
    Message(role="assistant", content="Earlier answer."),
    Message(role="user", content=MEMORY_ENVELOPE_MARKER + "\n" + json.dumps({"excerpts": []})),
    Message(role="user", content=STATE_ENVELOPE_MARKER + "\n" + json.dumps({"record_state": {}})),
    Message(role="user", content="Recap that in one sentence."),
)


def test_off_changes_nothing() -> None:
    assert context.ENVELOPE_IN_SYSTEM is False
    assert relocate_envelope(PERSONA, MESSAGES) == (PERSONA, MESSAGES)


def test_on_moves_only_the_record_state_envelope() -> None:
    context.ENVELOPE_IN_SYSTEM = True
    try:
        system, messages = relocate_envelope(PERSONA, MESSAGES)
    finally:
        context.ENVELOPE_IN_SYSTEM = False
    assert system.startswith(PERSONA + ENVELOPE_SYSTEM_SEPARATOR), (
        "the persona stays whole and first"
    )
    assert system.endswith(MESSAGES[3].content), "the envelope's content is unchanged"
    assert [m.content for m in messages] == [
        "Earlier words.",
        "Earlier answer.",
        MESSAGES[2].content,  # recall excerpts: conversational data, not moved
        "Recap that in one sentence.",
    ]
    assert messages[-1].content == "Recap that in one sentence."


def test_on_without_an_envelope_changes_nothing() -> None:
    context.ENVELOPE_IN_SYSTEM = True
    try:
        assert relocate_envelope(PERSONA, MESSAGES[:2]) == (PERSONA, MESSAGES[:2])
    finally:
        context.ENVELOPE_IN_SYSTEM = False
