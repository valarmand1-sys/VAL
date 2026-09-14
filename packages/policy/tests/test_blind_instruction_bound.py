"""The bounded blind-position instruction — ruling, 13 September 2026.

The instruction now asks for at most two sentences of position and about 120
words of material reasoning. Nothing else in the contract moves: the schema and
the parser are unchanged, a longer but valid position still parses (there is no
length rejection, which would turn a valid position into a retry), and the
reconciliation envelope still carries position, confidence and reasoning.
"""

from __future__ import annotations

import json

from val_domain.deliberation import Confidence
from val_policy.deliberation import (
    BLIND_POSITION_INSTRUCTION,
    BLIND_POSITION_OUTPUT_SCHEMA,
    RECONCILIATION_ENVELOPE_MARKER,
    BlindOutcome,
    parse_blind_outcome,
    reconciliation_envelope,
)

BOUND = (
    "Commit: name the option you would choose, in at most two sentences, and give only "
    "the material reasons for it — at most about 120 words of reasoning. Do not restate "
    "the question, draft the work itself, or add caveats that would not change the position."
)


def test_the_instruction_carries_the_ruled_bound_verbatim() -> None:
    assert BOUND in " ".join(BLIND_POSITION_INSTRUCTION.split())
    assert "why, briefly" not in BLIND_POSITION_INSTRUCTION


def test_the_confidence_and_answer_contract_are_unchanged() -> None:
    assert "State your confidence honestly" in BLIND_POSITION_INSTRUCTION
    assert BLIND_POSITION_INSTRUCTION.endswith(
        '{"position": "<your position>", "confidence": "high" | "medium" | "low", '
        '"reasoning": "<brief reasoning>"}'
    )


def test_the_schema_is_unchanged() -> None:
    assert BLIND_POSITION_OUTPUT_SCHEMA == {
        "type": "object",
        "properties": {
            "position": {"type": "string"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "reasoning": {"type": "string"},
        },
        "required": ["position", "confidence", "reasoning"],
        "additionalProperties": False,
    }


def test_a_longer_but_valid_position_still_parses() -> None:
    reasoning = " ".join(["The material reason, stated at length."] * 120)  # ~600 words
    parsed = parse_blind_outcome(
        json.dumps({"position": "Keep it.", "confidence": "medium", "reasoning": reasoning})
    )
    assert parsed == BlindOutcome(
        position="Keep it.", confidence=Confidence.MEDIUM, reasoning=reasoning
    )


def test_the_parser_still_refuses_what_it_refused() -> None:
    assert parse_blind_outcome('{"position": "", "confidence": "medium", "reasoning": "x"}') is None
    assert parse_blind_outcome('{"position": "x", "confidence": "sure", "reasoning": "x"}') is None
    assert parse_blind_outcome("not json") is None


def test_the_reconciliation_envelope_still_carries_all_three_fields() -> None:
    outcome = BlindOutcome(position="Keep it.", confidence=Confidence.HIGH, reasoning="Because.")
    envelope = reconciliation_envelope(outcome)
    assert envelope.startswith(RECONCILIATION_ENVELOPE_MARKER)
    document = json.loads(envelope.split("\n", 1)[1])
    assert document["blind_position"] == {
        "position": "Keep it.",
        "confidence": "high",
        "reasoning": "Because.",
    }
