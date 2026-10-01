"""Core's conversational guidance (owner order, 1 October 2026).

Behind its own switch: the guidance follows the persona in a conversation's system
message and changes nothing of the persona.
"""

from __future__ import annotations

import pytest

import val_gateway.context as context

PERSONA = "You are Val.\n\nThe whole persona, verbatim."


def test_with_the_switch_off_the_system_message_is_the_persona_exactly() -> None:
    assert context.CONVERSATIONAL_GUIDANCE_ENABLED is False, "off unless the house enables it"
    assert context.conversation_system(PERSONA) == PERSONA


def test_with_the_switch_on_the_persona_is_whole_and_first_and_the_guidance_follows_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(context, "CONVERSATIONAL_GUIDANCE_ENABLED", True)
    system = context.conversation_system(PERSONA)
    assert system.startswith(PERSONA + context.CONVERSATION_SYSTEM_SEPARATOR)
    assert system.count(PERSONA) == 1
    assert system.count(context.CONVERSATIONAL_GUIDANCE) == 1
    assert system.endswith(context.CONVERSATIONAL_GUIDANCE)


def test_the_guidance_is_fixed_text_that_carries_no_record_content_and_no_film_question() -> None:
    """Governing guidance stays distinct from the record: nothing is interpolated into it,
    and the question that exposed the failure is not hard-coded."""
    guidance = context.CONVERSATIONAL_GUIDANCE
    assert "{" not in guidance and "}" not in guidance
    assert "film?" not in guidance and "opening line" not in guidance
    # The ruled limits it must not cross: no pace, no truncation, no output ceiling.
    lowered = guidance.lower()
    for forbidden in ("faster", "max_tokens", "truncate", "word limit", "words or fewer"):
        assert forbidden not in lowered


def test_the_guidance_states_each_requirement_of_the_order() -> None:
    guidance = context.CONVERSATIONAL_GUIDANCE
    for required in (
        "give it first",
        "Explain when he asks why",
        "Ask first only when what is missing makes a useful or responsible answer impossible",
        "you still say you do not have",
        "short by default",
        "give the developed answer in full",
        "not whether it was spoken or typed",
        "never present your own line as one from an existing film, book or person",
        "do not invent its wording, its source",
    ):
        assert " ".join(required.split()) in " ".join(guidance.split()), required
