"""The review queue and its writers — ruling of 7 September 2026.

Against real PostgreSQL. What these pin down: the queue never carries a
verdict; the label is stored before the verdict is revealed; one label per
exchange, never overwritten; the explicit determination; eligibility
(established, on or after the resume boundary); scoring derived on read; a
disagreement stays open until a review resolves it, never by being viewed;
and both tables refuse update and delete.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from test_persona import clean_personas  # noqa: F401 - fixture reused

from val_domain.classification_review import (
    NONE_FAILS_INCLUSION_TEST,
    REVIEW_ELIGIBLE_FROM,
    Agreement,
    HumanClassification,
    ReviewConclusion,
    TuningState,
)
from val_gateway.classification_review import (
    ReviewRefusedError,
    disagreements,
    labelled,
    progress,
    record_label,
    record_review,
    review_queue,
)

C, U, N = (
    HumanClassification.CONSEQUENTIAL,
    HumanClassification.UNCERTAIN,
    HumanClassification.NOT_CONSEQUENTIAL,
)


@pytest.fixture
def store(clean_personas: Engine) -> Engine:  # noqa: F811 - pytest fixture injection
    return clean_personas


def _classified(
    engine: Engine,
    content: str,
    verdict: str | None,
    hard_exclusion: str | None = None,
    *,
    at: datetime | None = None,
) -> UUID:
    """A user message with its classification row, as the orchestrator would leave them."""
    when = at or (REVIEW_ELIGIBLE_FROM + timedelta(hours=1))
    with engine.begin() as connection:
        conversation = connection.execute(
            text(
                "insert into conversations (project_id, title, started_at, last_message_at) "
                "values (null, :t, :w, :w) returning id"
            ),
            {"t": content[:30], "w": when},
        ).scalar_one()
        message = connection.execute(
            text(
                "insert into messages (conversation_id, role, content, created_at, sequence) "
                "values (:c, 'user', :m, :w, 1) returning id"
            ),
            {"c": conversation, "m": content, "w": when},
        ).scalar_one()
        return connection.execute(
            text(
                "insert into classifications (created_at, conversation_id, message_id, "
                "  established, verdict, hard_exclusion, attempts, model_call_ids, resolution) "
                "values (:w, :c, :m, :e, :v, :h, 1, '{}', :r) returning id"
            ),
            {
                "w": when,
                "c": conversation,
                "m": message,
                "e": verdict is not None,
                "v": verdict,
                "h": hard_exclusion,
                "r": None if verdict is not None else "attempt 1: no verdict",
            },
        ).scalar_one()


def test_the_queue_is_oldest_first_established_only_and_carries_no_verdict(store: Engine) -> None:
    later = _classified(
        store, "Which opening?", "consequential", at=REVIEW_ELIGIBLE_FROM + timedelta(hours=2)
    )
    earlier = _classified(
        store, "What time?", "not_consequential", "status_progress_schedule_or_cost"
    )
    _classified(store, "Unresolved.", None)
    _classified(
        store, "Before the resume.", "consequential", at=REVIEW_ELIGIBLE_FROM - timedelta(days=1)
    )

    queue = review_queue(store)
    assert [q.classification_id for q in queue] == [earlier, later]
    assert [q.content for q in queue] == ["What time?", "Which opening?"]
    for item in queue:
        assert not hasattr(item, "verdict") and not hasattr(item, "hard_exclusion")


def test_the_label_is_stored_and_only_then_revealed(store: Engine) -> None:
    cid = _classified(store, "What time?", "not_consequential", "status_progress_schedule_or_cost")

    revealed = record_label(
        store,
        classification_id=cid,
        label=N,
        exclusion_determination="status_progress_schedule_or_cost",
    )
    assert revealed.verdict.value == "not_consequential"
    assert revealed.hard_exclusion == "status_progress_schedule_or_cost"
    assert revealed.agreement is Agreement.AGREE
    assert revealed.label.labelled_by == "user"
    assert review_queue(store) == (), "labelled, so no longer queued"
    stored = labelled(store, cid)
    assert stored is not None and stored.label.id == revealed.label.id


def test_the_original_label_is_never_overwritten(store: Engine) -> None:
    cid = _classified(store, "Which opening?", "consequential")
    record_label(store, classification_id=cid, label=U, exclusion_determination=None)
    with pytest.raises(ReviewRefusedError, match="never overwritten"):
        record_label(store, classification_id=cid, label=C, exclusion_determination=None)
    with store.connect() as connection, pytest.raises(Exception, match="rows are evidence"):
        connection.execute(text("update classification_labels set label = 'consequential'"))
    with store.connect() as connection, pytest.raises(Exception, match="hard delete"):
        connection.execute(text("delete from classification_labels"))


def test_an_omitted_determination_is_refused_not_read_as_none(store: Engine) -> None:
    cid = _classified(store, "What time?", "not_consequential", "status_progress_schedule_or_cost")
    with pytest.raises(ReviewRefusedError, match="omitted answer is not 'none'"):
        record_label(store, classification_id=cid, label=N, exclusion_determination=None)
    with pytest.raises(ReviewRefusedError, match="carries no hard-exclusion determination"):
        record_label(
            store, classification_id=cid, label=C, exclusion_determination="no_choice_present"
        )
    assert labelled(store, cid) is None, "nothing was stored by a refused label"


def test_ineligible_classifications_cannot_be_labelled(store: Engine) -> None:
    unresolved = _classified(store, "Unresolved.", None)
    old = _classified(
        store, "Old.", "consequential", at=REVIEW_ELIGIBLE_FROM - timedelta(minutes=1)
    )
    for cid in (unresolved, old):
        with pytest.raises(ReviewRefusedError, match="not eligible"):
            record_label(store, classification_id=cid, label=C, exclusion_determination=None)


def test_zero_tolerance_and_inclusion_disagreements_are_scored_on_read(store: Engine) -> None:
    zero = _classified(store, "Is the screening at two?", "consequential")
    inclusion = _classified(store, "Which opening?", "consequential")
    record_label(
        store,
        classification_id=zero,
        label=N,
        exclusion_determination="status_progress_schedule_or_cost",
    )
    record_label(store, classification_id=inclusion, label=U, exclusion_determination=None)

    items = {d.classification_id: d for d in disagreements(store)}
    assert items[zero].agreement is Agreement.ZERO_TOLERANCE_FAILURE
    assert items[inclusion].agreement is Agreement.INCLUSION_DISAGREEMENT
    assert all(d.open_disagreement for d in items.values())
    view = progress(store)
    assert (view.labelled, view.zero_tolerance_failures, view.inclusion_disagreements) == (2, 1, 1)
    assert view.open_disagreements == 2 and view.target == 50


def test_a_disagreement_is_resolved_by_a_review_never_by_viewing(store: Engine) -> None:
    cid = _classified(store, "Which opening?", "consequential")
    record_label(
        store, classification_id=cid, label=N, exclusion_determination=NONE_FAILS_INCLUSION_TEST
    )
    assert disagreements(store)[0].open_disagreement, "looking at it changes nothing"

    review = record_review(
        store,
        classification_id=cid,
        conclusion=ReviewConclusion.CLASSIFIER_UPHELD_LABEL_WRONG,
        reason="On reflection the outline decision binds later work.",
    )
    assert review.tuning_state is None
    item = labelled(store, cid)
    assert item is not None and not item.open_disagreement
    assert item.label.label is N, "the original label stands as committed"
    assert progress(store).open_disagreements == 0


def test_classifier_wrong_stays_open_until_tuning_is_verified(store: Engine) -> None:
    cid = _classified(store, "Is the screening at two?", "consequential")
    record_label(
        store,
        classification_id=cid,
        label=N,
        exclusion_determination="status_progress_schedule_or_cost",
    )
    first = record_review(
        store,
        classification_id=cid,
        conclusion=ReviewConclusion.LABEL_UPHELD_CLASSIFIER_WRONG,
        reason="A schedule query is a hard exclusion.",
    )
    assert first.tuning_state is TuningState.TUNING_REQUIRED
    item = labelled(store, cid)
    assert item is not None and item.open_disagreement, "tuning required keeps it open"

    with pytest.raises(ReviewRefusedError, match="never closed merely"):
        record_review(
            store,
            classification_id=cid,
            conclusion=ReviewConclusion.LABEL_UPHELD_CLASSIFIER_WRONG,
            reason="Done.",
            tuning_state=TuningState.TUNING_VERIFIED,
        )
    closed = record_review(
        store,
        classification_id=cid,
        conclusion=ReviewConclusion.LABEL_UPHELD_CLASSIFIER_WRONG,
        reason="The classifier now names the exclusion.",
        tuning_state=TuningState.TUNING_VERIFIED,
        tuning_change="commit 1234567",
        tuning_verification="re-classified the exchange: status_progress_schedule_or_cost",
    )
    assert closed.tuning_change == "commit 1234567"
    item = labelled(store, cid)
    assert item is not None and not item.open_disagreement
    assert len(item.reviews) == 2, "both rows stand; nothing was rewritten"
    with store.connect() as connection, pytest.raises(Exception, match="rows are evidence"):
        connection.execute(text("update classification_reviews set reason = 'x'"))


def test_a_review_needs_a_label_first(store: Engine) -> None:
    cid = _classified(store, "Which opening?", "consequential")
    with pytest.raises(ReviewRefusedError, match="blind label comes first"):
        record_review(
            store,
            classification_id=cid,
            conclusion=ReviewConclusion.AMBIGUOUS_NEEDS_RULING,
            reason="Unclear.",
        )


def test_progress_counts_eligible_unlabelled_exchanges(store: Engine) -> None:
    _classified(store, "A?", "not_consequential", "no_choice_present")
    _classified(store, "B?", "consequential")
    _classified(store, "Unresolved.", None)
    view = progress(store)
    assert (view.labelled, view.eligible_unlabelled) == (0, 2)
    assert datetime.now(UTC) > REVIEW_ELIGIBLE_FROM
