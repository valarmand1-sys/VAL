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


# =============================================================================
# Rulings of 11 September 2026: the completeness guard, record evidence, the
# mixed case, and an attributed prior with no author preference
# =============================================================================

from val_policy.deliberation import RetainedQuote, is_grounded  # noqa: E402

CORRECTION = (
    "You said, “This project's library is empty.” That is not the state of the "
    "system. Which categories do we define? I lean toward decision-type."
)
VAL_SAID = "As far as I can see, this project's library is empty, my lord."
LEAN = RemovedSpan("I lean toward decision-type.", 1)
QUOTE = RetainedQuote("This project's library is empty.", 1)


def with_evidence(*quotes: RetainedQuote, spans: tuple[RemovedSpan, ...] = (LEAN,)) -> StripOutcome:
    return StripOutcome(
        preference_present=True,
        separable=True,
        question="",
        removed=spans,
        attributed_prior_present=False,
        record_evidence=quotes,
    )


def test_the_completeness_guard_fails_closed_before_any_parse_is_trusted() -> None:
    """Part 4: an incomplete or truncated strip never enters the blind record."""
    truncated = validate_strip(MESSAGE, None, complete=False, terminal="truncated")
    assert truncated.state == "truncated" and truncated.residue is None
    assert not truncated.enforceable
    # Even a perfectly formed outcome is refused when the reply did not complete.
    perfect = outcome(spans=(RemovedSpan("I say recast.", 1),))
    refused = validate_strip(MESSAGE, perfect, complete=False, terminal="refused")
    assert refused.state == "incomplete" and refused.residue is None and refused.spans == ()


def test_grounded_record_evidence_is_retained_and_the_result_is_enforceable() -> None:
    v = validate_strip(CORRECTION, with_evidence(QUOTE), record=(VAL_SAID,))
    assert v.state == "enforceable"
    assert v.evidence == (QUOTE,)
    assert v.residue is not None and "This project's library is empty." in v.residue
    assert "I lean toward decision-type." not in v.residue


def test_record_evidence_not_in_the_message_is_invalid() -> None:
    v = validate_strip(
        CORRECTION, with_evidence(RetainedQuote("The library is full.", 1)), record=(VAL_SAID,)
    )
    assert v.state == "invalid" and "not found verbatim" in v.reasons[0]


def test_record_evidence_overlapping_a_removed_span_is_invalid_the_mixed_case_rule() -> None:
    """A quotation is retained as evidence or removed as a prior, never both."""
    mixed = (
        "You said, “Scene 4 should be deleted because Joni has no motivation.” "
        "Reconsider the scene from scratch."
    )
    prior = RemovedSpan(
        "You said, “Scene 4 should be deleted because Joni has no motivation.”",
        1,
        kind="attributed_prior",
    )
    both = StripOutcome(
        preference_present=False,
        separable=True,
        question="",
        removed=(prior,),
        attributed_prior_present=True,
        record_evidence=(
            RetainedQuote("Scene 4 should be deleted because Joni has no motivation.", 1),
        ),
    )
    v = validate_strip(
        mixed, both, record=("Scene 4 should be deleted because Joni has no motivation.",)
    )
    assert v.state == "invalid" and "never both" in v.reasons[0]


def test_ungrounded_record_evidence_is_final_and_never_enforceable() -> None:
    v = validate_strip(CORRECTION, with_evidence(QUOTE), record=("Good evening, my lord.",))
    assert v.state == "ungrounded" and v.residue is None and v.spans == ()
    assert "not grounded" in v.reasons[0]
    assert validate_strip(CORRECTION, with_evidence(QUOTE)).state == "ungrounded", "no record"


def test_grounding_is_literal_whitespace_aside() -> None:
    assert is_grounded(
        "This project's  library is empty.", ("...this project's library is empty...",)
    )
    assert not is_grounded("This project's library is full.", (VAL_SAID,))
    assert not is_grounded("", (VAL_SAID,))


def test_no_preference_with_record_evidence_is_still_grounded() -> None:
    plain = StripOutcome(
        preference_present=False,
        separable=True,
        question=CORRECTION,
        removed=(),
        record_evidence=(QUOTE,),
    )
    assert validate_strip(CORRECTION, plain, record=(VAL_SAID,)).state == "no_preference"
    assert validate_strip(CORRECTION, plain, record=()).state == "ungrounded"


def test_an_attributed_prior_with_no_author_preference_is_enforceable() -> None:
    message = "You argued last week for the close-up. Which opening do we commit to?"
    prior = RemovedSpan("You argued last week for the close-up.", 1, kind="attributed_prior")
    only_prior = StripOutcome(
        preference_present=False,
        separable=True,
        question="",
        removed=(prior,),
        attributed_prior_present=True,
    )
    v = validate_strip(message, only_prior)
    assert v.state == "enforceable" and v.residue == "Which opening do we commit to?"
    inseparable = StripOutcome(
        preference_present=False,
        separable=False,
        question="",
        removed=(),
        attributed_prior_present=True,
    )
    assert validate_strip(message, inseparable).state == "not_separable"


def test_a_span_kind_contradicting_the_declarations_is_invalid() -> None:
    v = validate_strip(
        MESSAGE,
        StripOutcome(
            preference_present=False,
            separable=True,
            question="",
            removed=(RemovedSpan("I say recast.", 1),),
            attributed_prior_present=True,
        ),
    )
    assert v.state == "invalid"
    assert any("preference_present=false yet" in r for r in v.reasons)
