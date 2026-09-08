"""Hand-labelling of classifications — the fifty-exchange criterion's records.

WP-0.9's acceptance criterion, verbatim: "Classifier accuracy: across fifty
real exchanges hand-labelled by Lord Armand, hard exclusions are never
classified consequential (zero tolerance — these are unambiguous), and
disagreements on the inclusion test are reviewed and used to tune."

Ruled 7 September 2026, with three amendments:

1. **The initial hand-label is immutable evidence.** One original blind label
   per classification, committed before the classifier's verdict is revealed
   and never overwritten. Reconsideration after the reveal is a separate
   append-only review, so the independent judgment the criterion collects and
   the conclusion reached after comparison are two different records.
2. **Hard-exclusion selection is explicit.** A `not_consequential` label
   carries a second determination: one of the six governing hard exclusions,
   or an explicit statement that none applies and the exchange fails the
   inclusion test. An omitted determination is refused, never read as "none".
   Consequential and uncertain labels carry no determination.
3. **Scoring.** Zero tolerance fires only when the label named a hard
   exclusion and the classifier called the exchange consequential. Every
   other mismatch, including `uncertain` against either verdict, is an
   inclusion-test disagreement. There is no third rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

#: Classifications eligible for hand-labelling are those recorded from live
#: use on or after the resume of 7 September 2026 — the commit of the last
#: WP-0.9 repair, b6d5c32, deployed to the live service that evening. Nothing
#: from the paused interval counts (gate-state ruling, 7 September 2026), and
#: the classification table held no live rows before it.
REVIEW_ELIGIBLE_FROM = datetime(2026, 9, 7, 22, 56, 30, tzinfo=UTC)

#: The fifty.
REVIEW_TARGET = 50

#: The explicit "no hard exclusion" determination: the exchange fails the
#: two-part inclusion test rather than falling under one of the six.
NONE_FAILS_INCLUSION_TEST = "none_fails_inclusion_test"


class HumanClassification(StrEnum):
    """Lord Armand's own verdict under the §4.8 contract."""

    CONSEQUENTIAL = "consequential"
    UNCERTAIN = "uncertain"
    NOT_CONSEQUENTIAL = "not_consequential"


class Agreement(StrEnum):
    """How a label compares with the recorded verdict — derived, never stored."""

    AGREE = "agree"
    INCLUSION_DISAGREEMENT = "inclusion_disagreement"
    ZERO_TOLERANCE_FAILURE = "zero_tolerance_failure"


class ReviewConclusion(StrEnum):
    """What was concluded after comparing the label with the classifier."""

    LABEL_UPHELD_CLASSIFIER_WRONG = "label_upheld_classifier_wrong"
    CLASSIFIER_UPHELD_LABEL_WRONG = "classifier_upheld_label_wrong"
    AMBIGUOUS_NEEDS_RULING = "ambiguous_needs_ruling"


class TuningState(StrEnum):
    """Where a classifier-was-wrong conclusion stands. Never closed by viewing."""

    TUNING_REQUIRED = "tuning_required"
    TUNING_VERIFIED = "tuning_verified"


@dataclass(frozen=True)
class ClassificationLabelRecord:
    """One original blind label, exactly as committed."""

    id: UUID
    classification_id: UUID
    label: HumanClassification
    #: One of the six hard exclusions, or `NONE_FAILS_INCLUSION_TEST`, present
    #: iff the label is `not_consequential`.
    exclusion_determination: str | None
    labelled_by: str
    created_at: datetime


@dataclass(frozen=True)
class ClassificationReviewRecord:
    """One adjudication after the reveal, appended to the label it reviews."""

    id: UUID
    classification_id: UUID
    label_id: UUID
    conclusion: ReviewConclusion
    reason: str
    tuning_state: TuningState | None
    tuning_change: str | None
    tuning_verification: str | None
    created_at: datetime
