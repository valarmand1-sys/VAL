"""The strip invariant — ruling of 9 September 2026.

`ordering = enforced` requires deterministic proof that preference-bearing
material was actually removed: preference present, separable, one or more
valid preference spans, every span resolving exactly, the derivation changing
the message, and an attributed-prior span wherever one is declared. Every
contradictory state is `invalid`; a valid "not separable" is its own state.
"""

from __future__ import annotations

from val_policy.deliberation import RemovedSpan, StripOutcome, validate_strip

MESSAGE = "Recast the innkeeper or keep her? I say recast. One position, briefly."


def outcome(
    *,
    present: bool = True,
    separable: bool = True,
    attributed: bool = False,
    spans: tuple[RemovedSpan, ...] = (),
    question: str = "",
) -> StripOutcome:
    return StripOutcome(
        preference_present=present,
        separable=separable,
        question=question,
        removed=spans,
        attributed_prior_present=attributed,
    )


def test_a_proved_removal_is_enforceable() -> None:
    v = validate_strip(MESSAGE, outcome(spans=(RemovedSpan("I say recast.", 1),)))
    assert v.state == "enforceable"
    assert v.residue == "Recast the innkeeper or keep her? One position, briefly."
    assert v.spans == (RemovedSpan("I say recast.", 1),)


def test_s7_present_and_separable_with_no_spans_is_invalid() -> None:
    """The conformance finding: an inseparable question recorded separable, nothing removed."""
    v = validate_strip("Why is the wide shot the right opening?", outcome(spans=()))
    assert v.state == "invalid"
    assert "without a preference span" in v.reasons[0]


def test_preference_absent_with_removal_spans_is_invalid() -> None:
    v = validate_strip(MESSAGE, outcome(present=False, spans=(RemovedSpan("I say recast.", 1),)))
    assert v.state == "invalid"


def test_separable_false_with_spans_is_invalid() -> None:
    v = validate_strip(MESSAGE, outcome(separable=False, spans=(RemovedSpan("I say recast.", 1),)))
    assert v.state == "invalid"


def test_a_span_that_does_not_resolve_is_invalid() -> None:
    v = validate_strip(MESSAGE, outcome(spans=(RemovedSpan("I say we recast.", 1),)))
    assert v.state == "invalid" and "does not resolve" in v.reasons[0]


def test_a_removal_that_does_not_alter_the_message_is_invalid() -> None:
    """A whitespace-only or empty span cannot prove removal."""
    v = validate_strip(MESSAGE, outcome(spans=(RemovedSpan("   ", 1),)))
    assert v.state == "invalid"


def test_only_attributed_spans_without_a_preference_span_is_invalid() -> None:
    message = "You chose the wide last time. Which lens for the harbour, the wide or the long?"
    v = validate_strip(
        message,
        outcome(
            attributed=True,
            spans=(RemovedSpan("You chose the wide last time.", 1, "attributed_prior"),),
        ),
    )
    assert v.state == "invalid" and "without a preference span" in v.reasons[0]


def test_a_declared_attributed_prior_needs_its_own_span() -> None:
    message = "You chose the wide last time. I'd go long now. Which lens?"
    v = validate_strip(
        message, outcome(attributed=True, spans=(RemovedSpan("I'd go long now.", 1),))
    )
    assert v.state == "invalid" and "attributed_prior" in v.reasons[0]
    both = outcome(
        attributed=True,
        spans=(
            RemovedSpan("You chose the wide last time.", 1, "attributed_prior"),
            RemovedSpan("I'd go long now.", 1),
        ),
    )
    assert validate_strip(message, both).state == "enforceable"
    assert validate_strip(message, both).residue == "Which lens?"


def test_a_valid_not_separable_is_its_own_state() -> None:
    v = validate_strip("Why is the wide shot right?", outcome(separable=False))
    assert v.state == "not_separable" and v.residue is None and v.spans == ()


def test_no_preference_is_its_own_state_and_never_enforceable() -> None:
    v = validate_strip(MESSAGE, outcome(present=False))
    assert v.state == "no_preference" and not v.enforceable


def test_an_unparseable_result_is_invalid() -> None:
    assert validate_strip(MESSAGE, None).state == "invalid"
