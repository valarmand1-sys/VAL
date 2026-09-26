"""What Val is told about the spoken path — targeted voice latency order, 25 Sept 2026.

In his session that evening she said she was "designed to generate a reply within
about one second", put a delay down to "network or local processing load rather
than the model itself", advised a wired connection, a GPU and a lower sample rate,
and offered to "record a brief demonstration". None of it had a source. The
correction is record-state fact, not persona: the persona is unchanged, and these
tests hold where the facts appear, where they do not, and what they say.
"""

from __future__ import annotations

import json

from val_gateway.context import CAPABILITY_STATE, SPOKEN_PATH, PriorRecordState


def document(*reasons: str) -> dict[str, object]:
    return PriorRecordState(
        history_state="zero",
        history_prior_messages=0,
        history_retained_messages=0,
        retrieval_state="not_run",
        retrieval_excerpts=0,
        local_only=bool(reasons),
        local_only_reasons=reasons,
    ).as_document()


def test_a_conversation_with_voice_on_is_told_the_spoken_path() -> None:
    assert document("voice_session_active")["spoken_path"] == dict(SPOKEN_PATH)
    assert "spoken_path" in document("conversation_sealed")


def test_a_typed_conversation_is_not_given_it() -> None:
    """The per-turn necessity rule: nothing added to a conversation with no voice."""
    assert "spoken_path" not in document()
    # Sealed only because it recalled a spoken conversation: nothing was spoken here.
    assert "spoken_path" not in document("recalled_sealed_content")


def test_it_promises_no_response_time_and_offers_no_measurement() -> None:
    facts = json.dumps(dict(SPOKEN_PATH)).lower()
    assert SPOKEN_PATH["response_time_promise"] == "none"
    assert SPOKEN_PATH["timing_measurement"] == "unavailable"
    assert "one second" not in facts and "1 second" not in facts
    assert "no stage sends this conversation over a network" in facts
    assert "not a promise" in facts and "25 september 2026" in facts
    # Dated today, it was read as this conversation's own timing in the first check.
    assert "not this conversation" in facts
    assert "tell him plainly that you cannot" in facts
    # The second check: asked for a one-second reply, she said no stage could be
    # shortened by software — false, and the same invention in the other direction.
    assert "neither promise it nor rule it out" in facts
    # The third check: with no stage figures she invented them (200 ms for Whisper,
    # "1 to 2 seconds of internal computation"). The measured ones are given instead.
    assert len(SPOKEN_PATH["measured_stages"]) == 4  # type: ignore[arg-type]
    assert "the only timing figures you have" in facts


def test_the_ruled_capability_state_is_untouched() -> None:
    """The 13 September ruling names books alone; this correction does not widen it."""
    assert dict(CAPABILITY_STATE) == {"books": "unavailable"}
