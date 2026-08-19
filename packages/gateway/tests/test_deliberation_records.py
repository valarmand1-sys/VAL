"""WP-0.9 — deliberation capture: the record half.

The governing criterion, `04-layer-0.md` WP-0.9:

    Done when: consequential exchanges are classified per
    02-partner-systems.md §4.8, a blind position is formed before exposure to
    preference, and the record populates.

These tests pin down the writer and the derived signal — the parts of WP-0.9
that are provable deterministically against the real store:

- every §4.7 field lands, complete at insert time, immutable afterwards;
- incoherent shapes are refused (an update without what changed her mind,
  a changed mind on an outcome that did not change, half a compromise,
  a compromise on agreement-from-the-start);
- `ordering = contaminated` is representable and honest;
- the drift signal — time since Val last disagreed — is queryable and
  correct, and `agreed_from_start` does not count as disagreement;
- the trap-question doctrine holds against deliberations: an
  `agreed_from_start` outcome is never reported as an approval.

The blind position *machinery* — classification, strip, blind call, payload
inspection — is the orchestration half of WP-0.9 and is tested where it is
built. Real-use evidence (classifier accuracy over fifty hand-labelled
exchanges, outcome across all four values in real use) is Lord Armand's and
accumulates through use.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from test_persona import REPO_ROOT, clean_personas  # noqa: F401 - fixture reused

from val_domain.conversation import StoredRole
from val_domain.deliberation import (
    ClassifiedBy,
    Confidence,
    DeliberationClassification,
    Ordering,
    Outcome,
)
from val_domain.project import ExplicitNoProject, ProjectRecord, ResolutionSource, ResolvedProject
from val_gateway import conversations as conv
from val_gateway.deliberation import (
    IncoherentDeliberationError,
    deliberations_for,
    last_disagreement_at,
    record_deliberation,
)
from val_gateway.persona import seed


@pytest.fixture
def store(clean_personas: Engine) -> Engine:  # noqa: F811 - pytest fixture injection
    seed(clean_personas, REPO_ROOT)
    with clean_personas.begin() as connection:
        connection.execute(
            text(
                "insert into projects (name, slug, description, status) "
                "values ('Project Alpha', 'project-alpha', '', 'active')"
            )
        )
    return clean_personas


def alpha(engine: Engine) -> ResolvedProject:
    with engine.connect() as connection:
        row = connection.execute(
            text("select id, name, slug, status from projects where slug = 'project-alpha'")
        ).one()
    return ResolvedProject(
        ProjectRecord(id=row.id, name=row.name, slug=row.slug, status=row.status),
        via=ResolutionSource.EXPLICIT_SELECTION,
    )


def a_consequential_turn(engine: Engine, scope: object | None = None) -> tuple:
    """A conversation whose user turn poses a choice that binds later work."""
    conversation = conv.create(
        engine,
        scope=scope if scope is not None else ExplicitNoProject(),  # type: ignore[arg-type]
        title="the opening shot",
    )
    question = conv.append(
        engine,
        conversation.id,
        role=StoredRole.USER,
        content="I think we should open on the wide shot. What do you think?",
    )
    return conversation, question


def a_deliberation(
    engine: Engine,
    conversation_id: object,
    message_id: object,
    *,
    outcome: Outcome = Outcome.HELD,
    what_changed_her_mind: str | None = None,
    both_positions: str | None = None,
    predictions: str | None = None,
    ordering: Ordering = Ordering.ENFORCED,
    stripped_content: str = "I think we should open on the wide shot.",
) -> object:
    """One recordable deliberation with sensible facts, overridable per test."""
    return record_deliberation(
        engine,
        conversation_id=conversation_id,  # type: ignore[arg-type]
        message_id=message_id,  # type: ignore[arg-type]
        position="Open on the close-up: the film is about her hands.",
        confidence=Confidence.MEDIUM,
        reasoning="The wide shot delays the audience meeting the subject.",
        stripped_content=stripped_content,
        ordering=ordering,
        user_response="I still prefer the wide shot for the sense of scale.",
        outcome=outcome,
        what_changed_her_mind=what_changed_her_mind,
        both_positions=both_positions,
        predictions=predictions,
    )


# =============================================================================
# The record populates — every §4.7 field, complete at insert time
# =============================================================================


def test_a_held_deliberation_records_every_field(store: Engine) -> None:
    conversation, question = a_consequential_turn(store)

    recorded = a_deliberation(store, conversation.id, question.id)

    assert recorded.position.startswith("Open on the close-up")
    assert recorded.confidence is Confidence.MEDIUM
    assert recorded.reasoning
    assert recorded.stripped_content == "I think we should open on the wide shot."
    assert recorded.ordering is Ordering.ENFORCED
    assert recorded.user_response
    assert recorded.outcome is Outcome.HELD
    assert recorded.what_changed_her_mind is None
    assert recorded.classification is DeliberationClassification.CONSEQUENTIAL
    assert recorded.classified_by is ClassifiedBy.AUTOMATIC

    with store.connect() as connection:
        row = connection.execute(
            text("select outcome, ordering from deliberations where id = :i"),
            {"i": recorded.id},
        ).one()
    assert row.outcome == "held"
    assert row.ordering == "enforced"


def test_all_four_outcomes_are_recordable(store: Engine) -> None:
    """§4.7's outcome vocabulary, one row each, read back oldest first."""
    conversation, question = a_consequential_turn(store)

    a_deliberation(store, conversation.id, question.id, outcome=Outcome.HELD)
    a_deliberation(
        store,
        conversation.id,
        question.id,
        outcome=Outcome.UPDATED,
        what_changed_her_mind="His point about scale — the location is the antagonist.",
    )
    a_deliberation(store, conversation.id, question.id, outcome=Outcome.OVERRIDDEN)
    a_deliberation(store, conversation.id, question.id, outcome=Outcome.AGREED_FROM_START)

    recorded = deliberations_for(store, conversation.id)
    assert [d.outcome for d in recorded] == [
        Outcome.HELD,
        Outcome.UPDATED,
        Outcome.OVERRIDDEN,
        Outcome.AGREED_FROM_START,
    ]


def test_uncertain_and_manual_classification_are_recordable(store: Engine) -> None:
    """§4.8: borderline is captured and marked, and override runs both ways."""
    conversation, question = a_consequential_turn(store)

    recorded = record_deliberation(
        store,
        conversation_id=conversation.id,
        message_id=question.id,
        position="Either opening works; the edit will decide.",
        confidence=Confidence.LOW,
        reasoning="The choice may not bind later work at all.",
        stripped_content="",
        ordering=Ordering.ENFORCED,
        user_response="Noted. Mark it anyway — I recognised this later as the turning point.",
        outcome=Outcome.AGREED_FROM_START,
        classification=DeliberationClassification.UNCERTAIN,
        classified_by=ClassifiedBy.USER,
    )
    assert recorded.classification is DeliberationClassification.UNCERTAIN
    assert recorded.classified_by is ClassifiedBy.USER


# =============================================================================
# What the writer refuses — a record that cannot describe one real deliberation
# =============================================================================


def test_an_update_without_what_changed_her_mind_is_refused(store: Engine) -> None:
    """§4.4: she updates AND says what changed her mind, or she has not updated."""
    conversation, question = a_consequential_turn(store)
    for missing in (None, "   "):
        with pytest.raises(IncoherentDeliberationError, match="what changed her mind"):
            a_deliberation(
                store,
                conversation.id,
                question.id,
                outcome=Outcome.UPDATED,
                what_changed_her_mind=missing,
            )
    assert deliberations_for(store, conversation.id) == ()


@pytest.mark.parametrize("outcome", [Outcome.HELD, Outcome.OVERRIDDEN, Outcome.AGREED_FROM_START])
def test_a_changed_mind_on_an_unchanged_outcome_is_refused(store: Engine, outcome: Outcome) -> None:
    conversation, question = a_consequential_turn(store)
    with pytest.raises(IncoherentDeliberationError, match="did not change"):
        a_deliberation(
            store,
            conversation.id,
            question.id,
            outcome=outcome,
            what_changed_her_mind="Nothing did, but here is text anyway.",
        )


def test_half_a_compromise_is_refused_either_way(store: Engine) -> None:
    """§4.5: both positions AND the predictions — the ledger seed — or neither."""
    conversation, question = a_consequential_turn(store)
    with pytest.raises(IncoherentDeliberationError, match="travel together"):
        a_deliberation(
            store,
            conversation.id,
            question.id,
            both_positions="Hers: close-up. His: wide.",
        )
    with pytest.raises(IncoherentDeliberationError, match="travel together"):
        a_deliberation(
            store,
            conversation.id,
            question.id,
            predictions="She predicts re-cutting; he predicts it plays.",
        )


def test_a_compromise_is_recordable_with_both_halves(store: Engine) -> None:
    conversation, question = a_consequential_turn(store)
    recorded = a_deliberation(
        store,
        conversation.id,
        question.id,
        outcome=Outcome.OVERRIDDEN,
        both_positions="Hers: open on the close-up. His: open on the wide shot.",
        predictions=(
            "She predicts the opening will be re-cut after the first screening; "
            "he predicts the scale will carry it."
        ),
    )
    assert recorded.both_positions is not None
    assert recorded.predictions is not None


def test_a_compromise_on_agreement_from_the_start_is_refused(store: Engine) -> None:
    conversation, question = a_consequential_turn(store)
    with pytest.raises(IncoherentDeliberationError, match="no disagreement to compromise"):
        a_deliberation(
            store,
            conversation.id,
            question.id,
            outcome=Outcome.AGREED_FROM_START,
            both_positions="x",
            predictions="y",
        )


@pytest.mark.parametrize("field", ["position", "reasoning", "user_response"])
def test_a_blank_required_field_is_refused(store: Engine, field: str) -> None:
    """A deliberation missing its position, reasoning, or his response is not one."""
    conversation, question = a_consequential_turn(store)
    facts: dict[str, object] = {
        "position": "Open on the close-up.",
        "confidence": Confidence.HIGH,
        "reasoning": "The film is about her hands.",
        "stripped_content": "",
        "ordering": Ordering.ENFORCED,
        "user_response": "Understood.",
        "outcome": Outcome.HELD,
    }
    facts[field] = "   "
    with pytest.raises(IncoherentDeliberationError, match=field):
        record_deliberation(
            store,
            conversation_id=conversation.id,
            message_id=question.id,
            **facts,  # type: ignore[arg-type]
        )


# =============================================================================
# Ordering is recorded honestly
# =============================================================================


def test_no_preference_present_records_enforced_with_nothing_stripped(store: Engine) -> None:
    """§4.1: where no preference is present, blindness holds trivially."""
    conversation, question = a_consequential_turn(store)
    recorded = a_deliberation(
        store, conversation.id, question.id, stripped_content="", ordering=Ordering.ENFORCED
    )
    assert recorded.stripped_content == ""
    assert recorded.ordering is Ordering.ENFORCED


def test_contaminated_is_representable_and_stays_contaminated(store: Engine) -> None:
    """Where preference cannot be separated, the record says so — honestly,
    permanently. A contaminated position labelled clean is the failure §4.1
    exists to prevent, and 0009 makes the label unchangeable after the fact."""
    conversation, question = a_consequential_turn(store)
    recorded = a_deliberation(
        store,
        conversation.id,
        question.id,
        ordering=Ordering.CONTAMINATED,
        stripped_content="",
    )
    assert recorded.ordering is Ordering.CONTAMINATED

    with pytest.raises(Exception, match="rows are evidence"):
        with store.begin() as connection:
            connection.execute(
                text("update deliberations set ordering = 'enforced' where id = :i"),
                {"i": recorded.id},
            )


# =============================================================================
# Anchoring: a deliberation is about an exchange that actually happened
# =============================================================================


def test_the_project_is_derived_from_the_conversation(store: Engine) -> None:
    scope = alpha(store)
    conversation, question = a_consequential_turn(store, scope)
    recorded = a_deliberation(store, conversation.id, question.id)
    assert recorded.project_id == scope.project_id


def test_a_no_project_conversation_yields_a_null_project_deliberation(store: Engine) -> None:
    conversation, question = a_consequential_turn(store)
    recorded = a_deliberation(store, conversation.id, question.id)
    assert recorded.project_id is None


def test_a_message_from_another_conversation_is_refused(store: Engine) -> None:
    first, _ = a_consequential_turn(store)
    _, stray_question = a_consequential_turn(store)
    with pytest.raises(IncoherentDeliberationError, match="belongs to conversation"):
        a_deliberation(store, first.id, stray_question.id)
    assert deliberations_for(store, first.id) == ()


def test_a_message_that_does_not_exist_is_refused(store: Engine) -> None:
    conversation, _ = a_consequential_turn(store)
    with pytest.raises(IncoherentDeliberationError, match="does not exist"):
        a_deliberation(store, conversation.id, uuid4())


# =============================================================================
# The record is evidence
# =============================================================================


def test_a_deliberation_cannot_be_edited_after_the_fact(store: Engine) -> None:
    """Migration 0009: capture is append-only, and the writer has no update path."""
    conversation, question = a_consequential_turn(store)
    recorded = a_deliberation(store, conversation.id, question.id)
    with pytest.raises(Exception, match="rows are evidence"):
        with store.begin() as connection:
            connection.execute(
                text("update deliberations set outcome = 'agreed_from_start' where id = :i"),
                {"i": recorded.id},
            )


def test_the_database_backstops_the_updated_coherence(store: Engine) -> None:
    """The check constraint behind the API contract, exercised directly."""
    conversation, question = a_consequential_turn(store)
    with pytest.raises(Exception, match="updated_requires_what_changed_her_mind"):
        with store.begin() as connection:
            connection.execute(
                text(
                    "insert into deliberations (conversation_id, message_id, position, "
                    "confidence, reasoning, stripped_content, ordering, user_response, "
                    "outcome, classification, classified_by) values "
                    "(:c, :m, 'p', 'high', 'r', '', 'enforced', 'u', 'updated', "
                    "'consequential', 'automatic')"
                ),
                {"c": conversation.id, "m": question.id},
            )


def test_a_deliberation_outlives_nothing_it_references_being_deletable(store: Engine) -> None:
    """§2.3: cascades on nothing, and nothing it references can be hard-deleted."""
    conversation, question = a_consequential_turn(store)
    a_deliberation(store, conversation.id, question.id)
    with pytest.raises(Exception, match="hard delete"):
        with store.begin() as connection:
            connection.execute(
                text("delete from conversations where id = :c"), {"c": conversation.id}
            )


# =============================================================================
# The disagreement signal — §4.7's one derived number
# =============================================================================


def test_no_deliberations_means_no_disagreement_yet(store: Engine) -> None:
    assert last_disagreement_at(store) is None


def test_agreement_from_the_start_is_not_a_disagreement(store: Engine) -> None:
    """The signal measures drift toward agreeableness; counting agreement as
    disagreement would hide exactly the pattern it exists to surface."""
    conversation, question = a_consequential_turn(store)
    a_deliberation(store, conversation.id, question.id, outcome=Outcome.AGREED_FROM_START)
    assert last_disagreement_at(store) is None


def test_every_other_outcome_counts_and_the_newest_wins(store: Engine) -> None:
    """Updated, held, and overridden all began with her stating a differing
    position — each is a real disagreement, whatever became of it."""
    conversation, question = a_consequential_turn(store)

    held = a_deliberation(store, conversation.id, question.id, outcome=Outcome.HELD)
    assert last_disagreement_at(store) == held.created_at

    updated = a_deliberation(
        store,
        conversation.id,
        question.id,
        outcome=Outcome.UPDATED,
        what_changed_her_mind="His argument about scale.",
    )
    assert last_disagreement_at(store) == updated.created_at

    # A later agreement does not advance the disagreement clock.
    a_deliberation(store, conversation.id, question.id, outcome=Outcome.AGREED_FROM_START)
    assert last_disagreement_at(store) == updated.created_at

    overridden = a_deliberation(store, conversation.id, question.id, outcome=Outcome.OVERRIDDEN)
    assert last_disagreement_at(store) == overridden.created_at


# =============================================================================
# The trap questions run against deliberations too (15 August 2026 amendment)
# =============================================================================


def test_agreed_from_start_is_never_reported_as_an_approval(store: Engine) -> None:
    """`04-layer-0.md` WP-0.9: enthusiasm recorded in a deliberation — or an
    agreed_from_start outcome — is never reported as an approval.

    Layer 0 has exactly two places an approval can truthfully live: an
    `execution_events` row with `event_type = 'accepted'`, and an `ideas`
    lifecycle reaching `approved`. A deliberation records how a position was
    formed, not that work was accepted — so a store containing only an
    enthusiastic agreement-from-the-start answers every approval query with
    zero."""
    scope = alpha(store)
    conversation, question = a_consequential_turn(store, scope)
    record_deliberation(
        store,
        conversation_id=conversation.id,
        message_id=question.id,
        position="The brass telescope would suit the tower.",
        confidence=Confidence.HIGH,
        reasoning="It fits the gallery and the period.",
        stripped_content="I love the idea of a brass telescope on the gallery.",
        ordering=Ordering.ENFORCED,
        user_response="Marvellous idea. Wonderful. Let us keep talking about it.",
        outcome=Outcome.AGREED_FROM_START,
    )

    with store.connect() as connection:
        approvals = connection.execute(
            text("select count(*) from execution_events where event_type = 'accepted'")
        ).scalar_one()
        approved_ideas = connection.execute(
            text("select count(*) from ideas where lifecycle_state = 'approved'")
        ).scalar_one()
    assert approvals == 0
    assert approved_ideas == 0

    # And the record itself says what it is: agreement, with the enthusiasm
    # sitting in his recorded response — not an acceptance of anything.
    (recorded,) = deliberations_for(store, conversation.id)
    assert recorded.outcome is Outcome.AGREED_FROM_START
