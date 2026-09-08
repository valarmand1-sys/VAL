"""The rules of hand-labelling — pure, like everything in `policy`.

Ruled 7 September 2026. Three functions the writers and the interface share
so that the rules exist once:

- `validate_determination` — the explicit hard-exclusion determination is
  present iff the label is `not_consequential`, and names one of the six or
  the explicit "none".
- `score` — agreement derived from the label and the recorded verdict; zero
  tolerance fires only when the label named a hard exclusion and the
  classifier said consequential; every other mismatch is an inclusion-test
  disagreement.
- `validate_review` — a classifier-was-wrong conclusion carries a tuning
  state; `tuning_verified` cites the change and its verification; nothing
  else carries either.
"""

from __future__ import annotations

from val_domain.classification_review import (
    NONE_FAILS_INCLUSION_TEST,
    Agreement,
    HumanClassification,
    ReviewConclusion,
    TuningState,
)
from val_domain.deliberation import ClassificationVerdict
from val_policy.deliberation import HARD_EXCLUSIONS

#: Every value the determination may take: the six, and the explicit none.
DETERMINATIONS: tuple[str, ...] = (*HARD_EXCLUSIONS, NONE_FAILS_INCLUSION_TEST)


class InvalidLabelError(ValueError):
    """The label and its determination do not describe one real judgment."""


class InvalidReviewError(ValueError):
    """The review's fields do not describe one real conclusion."""


def validate_determination(label: HumanClassification, determination: str | None) -> None:
    """Amendment 2: explicit, never optional, never on the other two labels."""
    if label is HumanClassification.NOT_CONSEQUENTIAL:
        if determination is None:
            raise InvalidLabelError(
                "a not_consequential label needs its second determination: one of the "
                "six hard exclusions, or an explicit statement that none applies and the "
                "exchange fails the inclusion test. An omitted answer is not 'none'."
            )
        if determination not in DETERMINATIONS:
            raise InvalidLabelError(
                f"{determination!r} is not one of the six hard exclusions nor the explicit "
                f"{NONE_FAILS_INCLUSION_TEST!r}."
            )
    elif determination is not None:
        raise InvalidLabelError(
            f"a {label.value} label carries no hard-exclusion determination; the "
            "determination exists only for not_consequential."
        )


def names_hard_exclusion(determination: str | None) -> bool:
    """Whether the determination is one of the six, as opposed to none or absent."""
    return determination in HARD_EXCLUSIONS


def score(
    label: HumanClassification,
    determination: str | None,
    verdict: ClassificationVerdict,
) -> Agreement:
    """Amendment 3, applied. Derived on read; nothing stores it."""
    if label.value == verdict.value:
        return Agreement.AGREE
    if names_hard_exclusion(determination) and verdict is ClassificationVerdict.CONSEQUENTIAL:
        return Agreement.ZERO_TOLERANCE_FAILURE
    return Agreement.INCLUSION_DISAGREEMENT


def validate_review(
    conclusion: ReviewConclusion,
    reason: str,
    tuning_state: TuningState | None,
    tuning_change: str | None,
    tuning_verification: str | None,
) -> None:
    """Amendment 1's review record: a conclusion, a stated reason, tuning tracked."""
    if not reason.strip():
        raise InvalidReviewError("a review states its reason in words; an empty reason is none.")
    if conclusion is ReviewConclusion.LABEL_UPHELD_CLASSIFIER_WRONG:
        if tuning_state is None:
            raise InvalidReviewError(
                "a conclusion that the classifier was wrong carries a tuning state: "
                "tuning_required until an engineering change is verified against it."
            )
        if tuning_state is TuningState.TUNING_VERIFIED:
            if not (tuning_change or "").strip() or not (tuning_verification or "").strip():
                raise InvalidReviewError(
                    "tuning_verified cites the engineering change and how it was verified; "
                    "a disagreement is never closed merely because it was looked at."
                )
        elif tuning_change is not None or tuning_verification is not None:
            raise InvalidReviewError(
                "tuning_required carries no change or verification yet; record those on "
                "the row that verifies the tuning."
            )
    else:
        if tuning_state is not None or tuning_change is not None or tuning_verification is not None:
            raise InvalidReviewError(
                f"a {conclusion.value} conclusion carries no tuning state: nothing in the "
                "classifier is to be changed on its account."
            )
