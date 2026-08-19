"""WP-0.8 — execution history capture.

The governing criterion, `04-layer-0.md` WP-0.8:

    Done when: every acceptance, rejection, revision, and correction writes an
    execution_events row with its reason.

    Verified by:
    - Accept, reject, request revision, and correct — one of each in real use —
      and confirm four rows with correct types.
    - A rejection without a stated reason prompts for one. Declining to give a
      reason records reason_source = absent rather than fabricating one.
    - reason_source correctly distinguishes stated from inferred across a
      sample of twenty real events, checked by hand.

What is provable deterministically is here. The two real-use halves — four
events in real use, and the twenty-event hand-checked sample — are Lord
Armand's own judgments about Val's actual work and accumulate through use;
the machinery they run on is what these tests pin down.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from test_persona import REPO_ROOT, clean_personas  # noqa: F401 - fixture reused

from val_domain.conversation import StoredRole
from val_domain.execution import ExecutionEventType, Reaction, ReasonSource
from val_domain.project import ExplicitNoProject, ProjectRecord, ResolutionSource, ResolvedProject
from val_gateway import conversations as conv
from val_gateway.execution import (
    IncoherentEventError,
    ReasonRequiredError,
    events_for,
    record_event,
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


def a_judged_turn(engine: Engine, scope: object | None = None) -> tuple:
    """A conversation with a user question and a Val reply to be judged."""
    conversation = conv.create(
        engine,
        scope=scope if scope is not None else ExplicitNoProject(),  # type: ignore[arg-type]
        title="work under judgment",
    )
    conv.append(engine, conversation.id, role=StoredRole.USER, content="Draft the summary.")
    reply = conv.append(engine, conversation.id, role=StoredRole.VAL, content="Here is the draft.")
    return conversation, reply


# =============================================================================
# The four event types, each with its reason
# =============================================================================


@pytest.mark.parametrize("event_type", list(ExecutionEventType))
def test_each_event_type_records_with_its_stated_reason(
    store: Engine, event_type: ExecutionEventType
) -> None:
    """One of each type, with a stated reason, lands with the correct type."""
    conversation, reply = a_judged_turn(store)

    recorded = record_event(
        store,
        conversation_id=conversation.id,
        message_id=reply.id,
        subject="the draft summary",
        event_type=event_type,
        reason="It reads exactly as I wanted."
        if event_type is ExecutionEventType.ACCEPTED
        else "The tone is wrong for the recipient.",
    )

    assert recorded.event_type is event_type
    assert recorded.reason_source is ReasonSource.STATED
    assert recorded.reason is not None
    with store.connect() as connection:
        row = connection.execute(
            text("select event_type, reason_source from execution_events where id = :i"),
            {"i": recorded.id},
        ).one()
    assert row.event_type == event_type.value
    assert row.reason_source == "stated"


def test_all_four_types_in_one_conversation_yield_four_rows(store: Engine) -> None:
    """The Done-when shape: four judgments, four rows, correct types, in order."""
    conversation, reply = a_judged_turn(store)
    for event_type, reason in (
        (ExecutionEventType.REJECTED, "Wrong structure entirely."),
        (ExecutionEventType.REVISION_REQUESTED, "Tighten the middle section."),
        (ExecutionEventType.CORRECTED, "The date was the 12th, not the 15th."),
        (ExecutionEventType.ACCEPTED, "Good. Ship it."),
    ):
        record_event(
            store,
            conversation_id=conversation.id,
            message_id=reply.id,
            subject="the draft summary",
            event_type=event_type,
            reason=reason,
        )

    recorded = events_for(store, conversation.id)
    assert [event.event_type for event in recorded] == [
        ExecutionEventType.REJECTED,
        ExecutionEventType.REVISION_REQUESTED,
        ExecutionEventType.CORRECTED,
        ExecutionEventType.ACCEPTED,
    ]
    assert all(event.reason_source is ReasonSource.STATED for event in recorded)


# =============================================================================
# The prompt, and the honest absence
# =============================================================================


def test_a_rejection_without_a_reason_is_prompted_for(store: Engine) -> None:
    """The criterion's own case: no reason, no declination — ask, write nothing."""
    conversation, reply = a_judged_turn(store)

    with pytest.raises(ReasonRequiredError, match="needs its reason"):
        record_event(
            store,
            conversation_id=conversation.id,
            message_id=reply.id,
            subject="the draft summary",
            event_type=ExecutionEventType.REJECTED,
        )

    assert events_for(store, conversation.id) == (), "a reasonless event was written anyway"


@pytest.mark.parametrize("event_type", list(ExecutionEventType))
def test_every_event_type_gets_the_same_prompt(
    store: Engine, event_type: ExecutionEventType
) -> None:
    """§2.2: a null reason is a defect to be surfaced on every event, not only rejection."""
    conversation, reply = a_judged_turn(store)

    with pytest.raises(ReasonRequiredError):
        record_event(
            store,
            conversation_id=conversation.id,
            message_id=reply.id,
            subject="the work",
            event_type=event_type,
        )


def test_declining_records_absent_rather_than_fabricating(store: Engine) -> None:
    """The criterion's second half: declining is itself the recorded fact."""
    conversation, reply = a_judged_turn(store)

    recorded = record_event(
        store,
        conversation_id=conversation.id,
        message_id=reply.id,
        subject="the draft summary",
        event_type=ExecutionEventType.REJECTED,
        declined_to_give_reason=True,
    )

    assert recorded.reason is None
    assert recorded.reason_source is ReasonSource.ABSENT


def test_stated_and_inferred_are_distinguished(store: Engine) -> None:
    """The load-bearing distinction, recorded exactly as the caller declares it."""
    conversation, reply = a_judged_turn(store)

    stated = record_event(
        store,
        conversation_id=conversation.id,
        message_id=reply.id,
        subject="the draft",
        event_type=ExecutionEventType.REVISION_REQUESTED,
        reason="Too long — cut it by half.",
    )
    inferred = record_event(
        store,
        conversation_id=conversation.id,
        message_id=reply.id,
        subject="the draft",
        event_type=ExecutionEventType.REJECTED,
        reason="He moved on immediately; likely the format rather than the content.",
        reason_inferred=True,
    )

    assert stated.reason_source is ReasonSource.STATED
    assert inferred.reason_source is ReasonSource.INFERRED


def test_the_incoherent_reason_shapes_are_refused(store: Engine) -> None:
    """Reason present + declined, and inferred-without-text, cannot be recorded."""
    conversation, reply = a_judged_turn(store)

    with pytest.raises(IncoherentEventError, match="not true"):
        record_event(
            store,
            conversation_id=conversation.id,
            message_id=reply.id,
            subject="x",
            event_type=ExecutionEventType.ACCEPTED,
            reason="fine work",
            declined_to_give_reason=True,
        )
    with pytest.raises(IncoherentEventError, match="nothing for it to describe"):
        record_event(
            store,
            conversation_id=conversation.id,
            message_id=reply.id,
            subject="x",
            event_type=ExecutionEventType.ACCEPTED,
            reason_inferred=True,
        )


# =============================================================================
# Reaction is not intent (15 August 2026 amendment)
# =============================================================================


def test_a_reaction_only_record_is_representable_and_is_not_an_approval(
    store: Engine,
) -> None:
    """ "He loved the idea" with no acceptance event — a real, queryable record."""
    conversation, reply = a_judged_turn(store)

    recorded = record_event(
        store,
        conversation_id=conversation.id,
        message_id=reply.id,
        subject="the brass telescope idea",
        reaction=Reaction.STRONGLY_ENTHUSIASTIC,
    )

    assert recorded.event_type is None
    assert recorded.reaction is Reaction.STRONGLY_ENTHUSIASTIC
    assert recorded.reason_source is ReasonSource.ABSENT
    # And the query the trap-question doctrine depends on: enthusiasm exists,
    # approval does not.
    with store.connect() as connection:
        approvals = connection.execute(
            text(
                "select count(*) from execution_events "
                "where conversation_id = :c and event_type = 'accepted'"
            ),
            {"c": conversation.id},
        ).scalar_one()
    assert approvals == 0


def test_an_event_may_carry_its_observed_reaction_alongside(store: Engine) -> None:
    conversation, reply = a_judged_turn(store)

    recorded = record_event(
        store,
        conversation_id=conversation.id,
        message_id=reply.id,
        subject="the summary",
        event_type=ExecutionEventType.ACCEPTED,
        reaction=Reaction.ENTHUSIASTIC,
        reason="Exactly right, and quicker than I expected.",
    )

    assert recorded.event_type is ExecutionEventType.ACCEPTED
    assert recorded.reaction is Reaction.ENTHUSIASTIC


def test_a_row_that_says_nothing_is_refused(store: Engine) -> None:
    conversation, reply = a_judged_turn(store)

    with pytest.raises(IncoherentEventError, match="says nothing"):
        record_event(
            store,
            conversation_id=conversation.id,
            message_id=reply.id,
            subject="nothing in particular",
        )


# =============================================================================
# Anchoring: an event is about something that actually happened
# =============================================================================


def test_the_project_is_derived_from_the_conversation(store: Engine) -> None:
    """Scope comes from the record, never from the caller — WP-0.7's doctrine."""
    scope = alpha(store)
    conversation, reply = a_judged_turn(store, scope)

    recorded = record_event(
        store,
        conversation_id=conversation.id,
        message_id=reply.id,
        subject="scoped work",
        event_type=ExecutionEventType.ACCEPTED,
        reason="Good.",
    )

    assert recorded.project_id == scope.project_id


def test_a_no_project_conversation_yields_a_null_project_event(store: Engine) -> None:
    conversation, reply = a_judged_turn(store)
    recorded = record_event(
        store,
        conversation_id=conversation.id,
        message_id=reply.id,
        subject="general work",
        event_type=ExecutionEventType.ACCEPTED,
        reason="Fine.",
    )
    assert recorded.project_id is None


def test_a_message_from_another_conversation_is_refused(store: Engine) -> None:
    """The judgment must be about the exchange it claims to be about."""
    first, _ = a_judged_turn(store)
    _, stray_reply = a_judged_turn(store)

    with pytest.raises(IncoherentEventError, match="belongs to conversation"):
        record_event(
            store,
            conversation_id=first.id,
            message_id=stray_reply.id,
            subject="x",
            event_type=ExecutionEventType.ACCEPTED,
            reason="fine",
        )
    assert events_for(store, first.id) == ()


def test_a_message_that_does_not_exist_is_refused(store: Engine) -> None:
    conversation, _ = a_judged_turn(store)
    with pytest.raises(IncoherentEventError, match="does not exist"):
        record_event(
            store,
            conversation_id=conversation.id,
            message_id=uuid4(),
            subject="x",
            event_type=ExecutionEventType.ACCEPTED,
            reason="fine",
        )


# =============================================================================
# The record is evidence
# =============================================================================


def test_an_event_cannot_be_edited_after_the_fact(store: Engine) -> None:
    """Migration 0009: audit is append-only, and the writer has no update path."""
    conversation, reply = a_judged_turn(store)
    recorded = record_event(
        store,
        conversation_id=conversation.id,
        message_id=reply.id,
        subject="the summary",
        event_type=ExecutionEventType.REJECTED,
        reason="Wrong tone.",
    )

    with pytest.raises(Exception, match="rows are evidence"):
        with store.begin() as connection:
            connection.execute(
                text("update execution_events set event_type = 'accepted' where id = :i"),
                {"i": recorded.id},
            )


def test_the_database_backstops_the_reason_coherence(store: Engine) -> None:
    """The check constraint behind the API contract, exercised directly."""
    conversation, reply = a_judged_turn(store)
    with pytest.raises(Exception, match="reason_matches_source"):
        with store.begin() as connection:
            connection.execute(
                text(
                    "insert into execution_events (conversation_id, message_id, event_type, "
                    "subject, reason, reason_source) values (:c, :m, 'accepted', 'x', "
                    "'a reason', 'absent')"
                ),
                {"c": conversation.id, "m": reply.id},
            )


def test_an_event_outlives_nothing_it_references_being_deletable(store: Engine) -> None:
    """§2.3: cascades on nothing, and nothing it references can be hard-deleted."""
    conversation, reply = a_judged_turn(store)
    record_event(
        store,
        conversation_id=conversation.id,
        message_id=reply.id,
        subject="the summary",
        event_type=ExecutionEventType.ACCEPTED,
        reason="Good.",
    )
    with pytest.raises(Exception, match="hard delete"):
        with store.begin() as connection:
            connection.execute(
                text("delete from conversations where id = :c"), {"c": conversation.id}
            )
