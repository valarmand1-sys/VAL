"""The rules of hand-labelling — ruling of 7 September 2026, three amendments."""

from __future__ import annotations

import pytest

from val_domain.classification_review import (
    NONE_FAILS_INCLUSION_TEST,
    Agreement,
    HumanClassification,
    ReviewConclusion,
    TuningState,
)
from val_domain.deliberation import ClassificationVerdict
from val_policy.classification_review import (
    DETERMINATIONS,
    InvalidLabelError,
    InvalidReviewError,
    score,
    validate_determination,
    validate_review,
)
from val_policy.deliberation import HARD_EXCLUSIONS

C, U, N = (
    HumanClassification.CONSEQUENTIAL,
    HumanClassification.UNCERTAIN,
    HumanClassification.NOT_CONSEQUENTIAL,
)
VC, VU, VN = (
    ClassificationVerdict.CONSEQUENTIAL,
    ClassificationVerdict.UNCERTAIN,
    ClassificationVerdict.NOT_CONSEQUENTIAL,
)


# --- amendment 2: the determination is explicit --------------------------------


def test_the_determinations_are_the_six_and_the_explicit_none() -> None:
    assert DETERMINATIONS == (*HARD_EXCLUSIONS, NONE_FAILS_INCLUSION_TEST)


def test_not_consequential_requires_a_determination_and_omitted_is_not_none() -> None:
    with pytest.raises(InvalidLabelError, match="omitted answer is not 'none'"):
        validate_determination(N, None)
    validate_determination(N, NONE_FAILS_INCLUSION_TEST)
    validate_determination(N, "logistics_and_scheduling")
    with pytest.raises(InvalidLabelError, match="not one of the six"):
        validate_determination(N, "vibes")


@pytest.mark.parametrize("label", [C, U])
def test_consequential_and_uncertain_carry_no_determination(label: HumanClassification) -> None:
    validate_determination(label, None)
    with pytest.raises(InvalidLabelError, match="carries no hard-exclusion determination"):
        validate_determination(label, "no_choice_present")
    with pytest.raises(InvalidLabelError):
        validate_determination(label, NONE_FAILS_INCLUSION_TEST)


# --- amendment 3: scoring ---------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "determination", "verdict", "expected"),
    [
        (C, None, VC, Agreement.AGREE),
        (U, None, VU, Agreement.AGREE),
        (N, "no_choice_present", VN, Agreement.AGREE),
        (N, NONE_FAILS_INCLUSION_TEST, VN, Agreement.AGREE),
        # Zero tolerance: a named exclusion against a consequential verdict, only.
        (N, "status_progress_schedule_or_cost", VC, Agreement.ZERO_TOLERANCE_FAILURE),
        # A named exclusion against `uncertain` is an inclusion disagreement.
        (N, "status_progress_schedule_or_cost", VU, Agreement.INCLUSION_DISAGREEMENT),
        # No hard exclusion named: never zero tolerance, whatever the verdict.
        (N, NONE_FAILS_INCLUSION_TEST, VC, Agreement.INCLUSION_DISAGREEMENT),
        (N, NONE_FAILS_INCLUSION_TEST, VU, Agreement.INCLUSION_DISAGREEMENT),
        # `uncertain` against either verdict is an inclusion disagreement.
        (U, None, VC, Agreement.INCLUSION_DISAGREEMENT),
        (U, None, VN, Agreement.INCLUSION_DISAGREEMENT),
        (C, None, VN, Agreement.INCLUSION_DISAGREEMENT),
        (C, None, VU, Agreement.INCLUSION_DISAGREEMENT),
    ],
)
def test_scoring_has_exactly_two_kinds_of_mismatch(
    label: HumanClassification,
    determination: str | None,
    verdict: ClassificationVerdict,
    expected: Agreement,
) -> None:
    assert score(label, determination, verdict) is expected


# --- amendment 1: the review record -------------------------------------------------


def test_a_review_states_its_reason() -> None:
    with pytest.raises(InvalidReviewError, match="states its reason"):
        validate_review(ReviewConclusion.CLASSIFIER_UPHELD_LABEL_WRONG, "  ", None, None, None)


def test_classifier_wrong_carries_tuning_and_verified_cites_the_change() -> None:
    wrong = ReviewConclusion.LABEL_UPHELD_CLASSIFIER_WRONG
    with pytest.raises(InvalidReviewError, match="carries a tuning state"):
        validate_review(wrong, "It missed the choice.", None, None, None)
    validate_review(wrong, "It missed the choice.", TuningState.TUNING_REQUIRED, None, None)
    with pytest.raises(InvalidReviewError, match="never closed merely"):
        validate_review(wrong, "Fixed.", TuningState.TUNING_VERIFIED, None, None)
    with pytest.raises(InvalidReviewError, match="carries no change or verification yet"):
        validate_review(wrong, "Soon.", TuningState.TUNING_REQUIRED, "abc123", None)
    validate_review(
        wrong, "Fixed.", TuningState.TUNING_VERIFIED, "commit abc123", "re-run on the exchange"
    )


@pytest.mark.parametrize(
    "conclusion",
    [ReviewConclusion.CLASSIFIER_UPHELD_LABEL_WRONG, ReviewConclusion.AMBIGUOUS_NEEDS_RULING],
)
def test_other_conclusions_carry_no_tuning_state(conclusion: ReviewConclusion) -> None:
    validate_review(conclusion, "Because.", None, None, None)
    with pytest.raises(InvalidReviewError, match="carries no tuning state"):
        validate_review(conclusion, "Because.", TuningState.TUNING_REQUIRED, None, None)
