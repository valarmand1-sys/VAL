"""The as-of rule for revision and retraction — ruling of 12 September 2026.

Pure: no database. `working_thread` is the one derivation every reader of a
conversation's working state uses, and its rule is sequence-based, never
timestamp-based: the turn at sequence *s* sees exactly the facts with
`after_sequence < s`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from val_domain.conversation import (
    MessageRecord,
    MessageRevisionRecord,
    MessageState,
    RevisionKind,
    StoredRole,
    working_thread,
)

CONVERSATION = uuid4()
#: Deliberately misleading clocks: every fact is dated before every message, so
#: a timestamp-based rule would apply all of them everywhere.
EARLY = datetime(2020, 1, 1, tzinfo=UTC)
LATE = datetime(2030, 1, 1, tzinfo=UTC)


def message(sequence: int, role: StoredRole, content: str) -> MessageRecord:
    return MessageRecord(
        id=UUID(int=sequence),
        conversation_id=CONVERSATION,
        role=role,
        content=content,
        sequence=sequence,
        created_at=LATE,
    )


def fact(
    message_sequence: int,
    number: int,
    after: int,
    kind: RevisionKind,
    content: str | None = None,
) -> MessageRevisionRecord:
    return MessageRevisionRecord(
        id=uuid4(),
        conversation_id=CONVERSATION,
        message_id=UUID(int=message_sequence),
        revision_number=number,
        after_sequence=after,
        kind=kind,
        content=content,
        authored_by="Lord Armand",
        note=None,
        created_at=EARLY,
    )


HISTORY = (
    message(1, StoredRole.USER, "Open on the wide shot."),
    message(2, StoredRole.VAL, "The wide shot, my lord."),
    message(3, StoredRole.USER, "And the second scene?"),
    message(4, StoredRole.VAL, "The workshop."),
    message(5, StoredRole.USER, "Thank you."),
)


def test_no_facts_is_the_stored_record_exactly() -> None:
    thread = working_thread(HISTORY, ())
    assert thread.live_records() == HISTORY
    assert all(item.state is MessageState.CURRENT for item in thread.messages)
    assert [item.record for item in thread.messages] == list(HISTORY)


def test_a_revision_applies_only_to_turns_after_it_was_recorded() -> None:
    corrected = fact(1, 1, after=4, kind=RevisionKind.REVISION, content="Open on the close-up.")
    # The turn at sequence 3 was assembled before the revision: it saw the original.
    earlier = working_thread(HISTORY, (corrected,), as_of_sequence=3)
    assert earlier.live_records()[0].content == "Open on the wide shot."
    assert earlier.messages[0].state is MessageState.CURRENT
    # The turn at sequence 5 came after: it sees the correction in A's position.
    later = working_thread(HISTORY, (corrected,), as_of_sequence=5)
    assert later.live_records()[0].content == "Open on the close-up."
    assert later.messages[0].state is MessageState.CORRECTED
    assert later.messages[0].record.content == "Open on the wide shot.", "the original is untouched"
    # Val's answer stays attached to the wording she received, and says so.
    assert later.messages[1].answered_state is MessageState.CORRECTED
    assert later.messages[1].content == "The wide shot, my lord."


def test_a_fact_recorded_at_the_turns_own_sequence_is_invisible_to_that_turn() -> None:
    """after_sequence == s means the fact was recorded after message s existed."""
    raced = fact(3, 1, after=3, kind=RevisionKind.REVISION, content="And the third scene?")
    assert working_thread(HISTORY, (raced,), as_of_sequence=3).messages[2].content == (
        "And the second scene?"
    )
    assert working_thread(HISTORY, (raced,), as_of_sequence=4).messages[2].content == (
        "And the third scene?"
    )


def test_messages_after_the_as_of_point_do_not_exist_for_it() -> None:
    thread = working_thread(HISTORY, (), as_of_sequence=3)
    assert [item.record.sequence for item in thread.messages] == [1, 2, 3]


def test_a_retraction_withdraws_the_message_and_its_immediate_answer_only() -> None:
    withdrawn = fact(1, 1, after=5, kind=RevisionKind.RETRACTION)
    thread = working_thread(HISTORY, (withdrawn,))
    assert thread.messages[0].state is MessageState.WITHDRAWN
    assert thread.messages[1].answered_state is MessageState.WITHDRAWN
    assert [record.sequence for record in thread.live_records()] == [3, 4, 5]
    assert len(thread.messages) == 5, "withdrawn messages remain in the thread, marked"


def test_the_latest_fact_decides_and_a_revision_after_retraction_reinstates() -> None:
    facts = (
        fact(3, 1, after=4, kind=RevisionKind.REVISION, content="And scene two?"),
        fact(3, 2, after=4, kind=RevisionKind.RETRACTION),
        fact(3, 3, after=5, kind=RevisionKind.REVISION, content="And scene three?"),
    )
    assert working_thread(HISTORY, facts, as_of_sequence=5).messages[2].state is (
        MessageState.WITHDRAWN
    )
    now = working_thread(HISTORY, facts)
    assert now.messages[2].state is MessageState.CORRECTED
    assert now.messages[2].content == "And scene three?"
    assert [f.revision_number for f in now.messages[2].revisions] == [1, 2, 3]


def test_val_messages_are_never_changed_by_facts() -> None:
    """The writer and the trigger refuse such facts; the derivation ignores one regardless."""
    stray = fact(2, 1, after=5, kind=RevisionKind.REVISION, content="Something else.")
    thread = working_thread(HISTORY, (stray,))
    assert thread.messages[1].content == "The wide shot, my lord."
    assert thread.messages[1].state is MessageState.CURRENT
