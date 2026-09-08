"""The review queue and its two writers — ruling of 7 September 2026.

The same doctrine as the blind position, applied to Lord Armand: the queue
returns the exchange and never the classifier's verdict; the verdict is
returned only by the call that durably stores his label. Nothing here can
show what the record has not yet earned.

Eligibility is applied here, not by the user: established classifications
from live turns on or after `REVIEW_ELIGIBLE_FROM`, oldest first, without a
label yet. Unestablished rows never enter the queue; classifications that
accumulated before the interface existed remain eligible and are reviewed in
the same queue.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Engine, Row, text

from val_domain.classification_review import (
    REVIEW_ELIGIBLE_FROM,
    REVIEW_TARGET,
    Agreement,
    ClassificationLabelRecord,
    ClassificationReviewRecord,
    HumanClassification,
    ReviewConclusion,
    TuningState,
)
from val_domain.deliberation import ClassificationVerdict
from val_policy.classification_review import (
    InvalidLabelError,
    score,
    validate_determination,
    validate_review,
)

#: The one actor who labels at Layer 0.
LABELLED_BY_USER = "user"


class ReviewRefusedError(Exception):
    """The label or review cannot be recorded as asked, and the message says why."""


@dataclass(frozen=True)
class QueuedExchange:
    """One exchange awaiting its label. Carries no verdict, by design."""

    classification_id: UUID
    conversation_id: UUID
    conversation_title: str
    message_id: UUID
    content: str
    classified_at: datetime


@dataclass(frozen=True)
class LabelledExchange:
    """A labelled exchange with the verdict revealed and agreement derived."""

    classification_id: UUID
    conversation_id: UUID
    conversation_title: str
    message_id: UUID
    content: str
    label: ClassificationLabelRecord
    verdict: ClassificationVerdict
    hard_exclusion: str | None
    agreement: Agreement
    reviews: tuple[ClassificationReviewRecord, ...]

    @property
    def open_disagreement(self) -> bool:
        """A disagreement with no review yet, or tuning still required."""
        if self.agreement is Agreement.AGREE:
            return False
        if not self.reviews:
            return True
        newest = self.reviews[-1]
        return newest.tuning_state is TuningState.TUNING_REQUIRED


@dataclass(frozen=True)
class ReviewProgress:
    """Visible progress toward the fifty, from the record."""

    labelled: int
    target: int
    agreements: int
    inclusion_disagreements: int
    zero_tolerance_failures: int
    open_disagreements: int
    eligible_unlabelled: int


_ELIGIBLE = (
    "select k.id as classification_id, k.created_at as classified_at, k.verdict, "
    "       k.hard_exclusion, m.id as message_id, m.content, c.id as conversation_id, c.title "
    "  from classifications k "
    "  join messages m on m.id = k.message_id "
    "  join conversations c on c.id = k.conversation_id "
    " where k.established and k.created_at >= :since "
)

# The three queries below concatenate module constants only — no value from
# outside this file reaches the SQL text; parameters travel as bind values.
_QUEUE = text(
    _ELIGIBLE + "   and not exists (select 1 from classification_labels l "
    "                   where l.classification_id = k.id) "
    " order by k.created_at, k.id limit :limit"
)

_LABELLED = text(
    _ELIGIBLE + "   and exists (select 1 from classification_labels l "
    "               where l.classification_id = k.id) "
    " order by k.created_at, k.id"
)

_ONE_SQL = _ELIGIBLE + "   and k.id = :classification_id"
_ONE = text(_ONE_SQL)

_LABEL_INSERT = text(
    "insert into classification_labels "
    "  (classification_id, label, exclusion_determination, labelled_by) "
    "values (:classification_id, :label, :exclusion_determination, :labelled_by) "
    "returning id, classification_id, label, exclusion_determination, labelled_by, created_at"
)

_LABEL_FOR = text(
    "select id, classification_id, label, exclusion_determination, labelled_by, created_at "
    "  from classification_labels where classification_id = :classification_id"
)

_REVIEW_INSERT = text(
    "insert into classification_reviews "
    "  (classification_id, label_id, conclusion, reason, tuning_state, tuning_change, "
    "   tuning_verification) "
    "values (:classification_id, :label_id, :conclusion, :reason, :tuning_state, "
    "        :tuning_change, :tuning_verification) "
    "returning id, classification_id, label_id, conclusion, reason, tuning_state, "
    "          tuning_change, tuning_verification, created_at"
)

_REVIEWS_FOR = text(
    "select id, classification_id, label_id, conclusion, reason, tuning_state, "
    "       tuning_change, tuning_verification, created_at "
    "  from classification_reviews where classification_id = :classification_id "
    " order by created_at, id"
)


def review_queue(engine: Engine, *, limit: int = 20) -> tuple[QueuedExchange, ...]:
    """Eligible exchanges without a label, oldest first — verdict withheld."""
    with engine.connect() as connection:
        rows = connection.execute(_QUEUE, {"since": REVIEW_ELIGIBLE_FROM, "limit": limit}).all()
    return tuple(
        QueuedExchange(
            classification_id=row.classification_id,
            conversation_id=row.conversation_id,
            conversation_title=row.title,
            message_id=row.message_id,
            content=row.content,
            classified_at=row.classified_at,
        )
        for row in rows
    )


def record_label(
    engine: Engine,
    *,
    classification_id: UUID,
    label: HumanClassification,
    exclusion_determination: str | None,
) -> LabelledExchange:
    """Store the blind label, then — and only then — reveal the verdict.

    Amendment 1: one label per classification; a second is refused, never
    merged. Amendment 2: the determination is validated as explicit. The
    classification must be eligible; an unestablished or pre-resume row is
    refused rather than labelled quietly.
    """
    try:
        validate_determination(label, exclusion_determination)
    except InvalidLabelError as invalid:
        raise ReviewRefusedError(str(invalid)) from invalid
    with engine.begin() as connection:
        target = connection.execute(
            _ONE, {"since": REVIEW_ELIGIBLE_FROM, "classification_id": classification_id}
        ).one_or_none()
        if target is None:
            raise ReviewRefusedError(
                f"classification {classification_id} is not eligible for hand-labelling: it "
                "does not exist, established no verdict, or predates the 7 September 2026 "
                "resume."
            )
        if connection.execute(_LABEL_FOR, {"classification_id": classification_id}).one_or_none():
            raise ReviewRefusedError(
                "this exchange already carries its original blind label, which is never "
                "overwritten. Record a review if you have reconsidered."
            )
        row = connection.execute(
            _LABEL_INSERT,
            {
                "classification_id": classification_id,
                "label": label.value,
                "exclusion_determination": exclusion_determination,
                "labelled_by": LABELLED_BY_USER,
            },
        ).one()
        return _labelled(connection, target, _label_from(row))


def labelled(engine: Engine, classification_id: UUID) -> LabelledExchange | None:
    """One labelled exchange with its verdict and reviews, or None if unlabelled."""
    with engine.connect() as connection:
        target = connection.execute(
            _ONE, {"since": REVIEW_ELIGIBLE_FROM, "classification_id": classification_id}
        ).one_or_none()
        if target is None:
            return None
        label = connection.execute(
            _LABEL_FOR, {"classification_id": classification_id}
        ).one_or_none()
        if label is None:
            return None
        return _labelled(connection, target, _label_from(label))


def labelled_exchanges(engine: Engine) -> tuple[LabelledExchange, ...]:
    """Every labelled exchange, oldest first, verdicts revealed."""
    with engine.connect() as connection:
        rows = connection.execute(_LABELLED, {"since": REVIEW_ELIGIBLE_FROM}).all()
        out = []
        for target in rows:
            label = connection.execute(
                _LABEL_FOR, {"classification_id": target.classification_id}
            ).one()
            out.append(_labelled(connection, target, _label_from(label)))
    return tuple(out)


def disagreements(engine: Engine) -> tuple[LabelledExchange, ...]:
    """Every labelled exchange whose label and verdict differ, with its reviews."""
    return tuple(
        item for item in labelled_exchanges(engine) if item.agreement is not Agreement.AGREE
    )


def progress(engine: Engine) -> ReviewProgress:
    """Counts toward the fifty, derived from the record on every read."""
    items = labelled_exchanges(engine)
    with engine.connect() as connection:
        unlabelled = len(
            connection.execute(_QUEUE, {"since": REVIEW_ELIGIBLE_FROM, "limit": 100000}).all()
        )
    return ReviewProgress(
        labelled=len(items),
        target=REVIEW_TARGET,
        agreements=sum(1 for i in items if i.agreement is Agreement.AGREE),
        inclusion_disagreements=sum(
            1 for i in items if i.agreement is Agreement.INCLUSION_DISAGREEMENT
        ),
        zero_tolerance_failures=sum(
            1 for i in items if i.agreement is Agreement.ZERO_TOLERANCE_FAILURE
        ),
        open_disagreements=sum(1 for i in items if i.open_disagreement),
        eligible_unlabelled=unlabelled,
    )


def record_review(
    engine: Engine,
    *,
    classification_id: UUID,
    conclusion: ReviewConclusion,
    reason: str,
    tuning_state: TuningState | None = None,
    tuning_change: str | None = None,
    tuning_verification: str | None = None,
) -> ClassificationReviewRecord:
    """Append one adjudication to a labelled exchange.

    A classifier-was-wrong conclusion with no tuning state given is recorded
    `tuning_required`; closing it is a later row with `tuning_verified` citing
    the change and its verification. Viewing records nothing.
    """
    if conclusion is ReviewConclusion.LABEL_UPHELD_CLASSIFIER_WRONG and tuning_state is None:
        tuning_state = TuningState.TUNING_REQUIRED
    try:
        validate_review(conclusion, reason, tuning_state, tuning_change, tuning_verification)
    except ValueError as invalid:
        raise ReviewRefusedError(str(invalid)) from invalid
    with engine.begin() as connection:
        label = connection.execute(
            _LABEL_FOR, {"classification_id": classification_id}
        ).one_or_none()
        if label is None:
            raise ReviewRefusedError(
                "a review adjudicates a label that exists; this exchange has not been "
                "labelled, and the blind label comes first."
            )
        row = connection.execute(
            _REVIEW_INSERT,
            {
                "classification_id": classification_id,
                "label_id": label.id,
                "conclusion": conclusion.value,
                "reason": reason,
                "tuning_state": None if tuning_state is None else tuning_state.value,
                "tuning_change": tuning_change,
                "tuning_verification": tuning_verification,
            },
        ).one()
    return _review_from(row)


def _labelled(
    connection: Connection, target: Row[Any], label: ClassificationLabelRecord
) -> LabelledExchange:
    verdict = ClassificationVerdict(target.verdict)
    reviews = tuple(
        _review_from(row)
        for row in connection.execute(
            _REVIEWS_FOR, {"classification_id": target.classification_id}
        ).all()
    )
    return LabelledExchange(
        classification_id=target.classification_id,
        conversation_id=target.conversation_id,
        conversation_title=target.title,
        message_id=target.message_id,
        content=target.content,
        label=label,
        verdict=verdict,
        hard_exclusion=target.hard_exclusion,
        agreement=score(label.label, label.exclusion_determination, verdict),
        reviews=reviews,
    )


def _label_from(row: Row[Any]) -> ClassificationLabelRecord:
    return ClassificationLabelRecord(
        id=row.id,
        classification_id=row.classification_id,
        label=HumanClassification(row.label),
        exclusion_determination=row.exclusion_determination,
        labelled_by=row.labelled_by,
        created_at=row.created_at,
    )


def _review_from(row: Row[Any]) -> ClassificationReviewRecord:
    return ClassificationReviewRecord(
        id=row.id,
        classification_id=row.classification_id,
        label_id=row.label_id,
        conclusion=ReviewConclusion(row.conclusion),
        reason=row.reason,
        tuning_state=None if row.tuning_state is None else TuningState(row.tuning_state),
        tuning_change=row.tuning_change,
        tuning_verification=row.tuning_verification,
        created_at=row.created_at,
    )
