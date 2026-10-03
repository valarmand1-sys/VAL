"""Versions of a corrected message, each with its own continuation — owner order,
2 October 2026 (§C, §D). Pure: the model alone, on records built in memory."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from test_working_thread import CONVERSATION, HISTORY, fact, message

from val_domain.conversation import (
    MessageState,
    RevisionKind,
    StoredRole,
    VersionSelectionRecord,
    WorkingThread,
    working_thread,
)


def selection(message_sequence: int, revision_number: int, after: int) -> VersionSelectionRecord:
    return VersionSelectionRecord(
        id=uuid4(),
        conversation_id=CONVERSATION,
        message_id=UUID(int=message_sequence),
        revision_number=revision_number,
        after_sequence=after,
        created_at=datetime(2026, 10, 2, 20, 0, tzinfo=UTC),
    )


# HISTORY: 1 user A, 2 val, 3 user, 4 val, 5 user "Thank you."


def sequences(thread: WorkingThread) -> list[int]:
    return [m.record.sequence for m in thread.live()]


def test_a_correction_starts_a_version_whose_continuation_is_what_followed_it() -> None:
    corrected = fact(1, 1, after=4, kind=RevisionKind.REVISION, content="Open on the close-up.")
    thread = working_thread(HISTORY, (corrected,))
    first = thread.messages[0]
    assert [v.number for v in first.versions] == [1, 2]
    assert [v.content for v in first.versions] == [
        "Open on the wide shot.",
        "Open on the close-up.",
    ]
    assert first.version == 2 and first.content == "Open on the close-up."
    # Messages 2 to 4 followed version 1; message 5 followed the correction.
    assert sequences(thread) == [1, 5]
    assert [m.in_view for m in thread.messages] == [True, False, False, False, True]


def test_viewing_an_earlier_version_shows_its_own_continuation_and_generates_nothing() -> None:
    corrected = fact(1, 1, after=4, kind=RevisionKind.REVISION, content="Open on the close-up.")
    thread = working_thread(HISTORY, (corrected,), view={UUID(int=1): 1})
    first = thread.messages[0]
    assert first.version == 1 and first.content == "Open on the wide shot."
    assert first.state is MessageState.CURRENT, "the version shown is this version's wording"
    assert sequences(thread) == [1, 2, 3, 4]
    assert thread.messages[1].answered_state is MessageState.CURRENT
    # A view of a version that does not exist shows the version in force.
    assert working_thread(HISTORY, (corrected,), view={UUID(int=1): 9}).messages[0].version == 2


def test_continuing_from_an_earlier_version_attaches_what_follows_to_it() -> None:
    corrected = fact(1, 1, after=4, kind=RevisionKind.REVISION, content="Open on the close-up.")
    history = (
        *HISTORY,
        message(6, StoredRole.VAL, "Gladly."),
        message(7, StoredRole.USER, "More."),
    )
    # He continued from version 1 after sequence 6: message 7 is version 1's.
    chosen = selection(1, 0, after=6)
    thread = working_thread(history, (corrected,), selections=(chosen,))
    assert thread.messages[0].version == 1, "version 1 is in force again"
    assert sequences(thread) == [1, 2, 3, 4, 7]
    # And the view of version 2 holds exactly what followed the correction.
    other = working_thread(history, (corrected,), selections=(chosen,), view={UUID(int=1): 2})
    assert sequences(other) == [1, 5, 6]


def test_the_as_of_rule_applies_to_selections_too() -> None:
    corrected = fact(1, 1, after=4, kind=RevisionKind.REVISION, content="Open on the close-up.")
    history = (
        *HISTORY,
        message(6, StoredRole.VAL, "Gladly."),
        message(7, StoredRole.USER, "More."),
    )
    chosen = selection(1, 0, after=6)
    # The turn at 6 was assembled before he went back: it saw version 2.
    before = working_thread(history, (corrected,), selections=(chosen,), as_of_sequence=6)
    assert before.messages[0].version == 2 and sequences(before) == [1, 5, 6]


def test_a_withdrawn_message_reinstated_with_its_wording_is_not_a_new_version() -> None:
    withdrawn = fact(1, 1, after=5, kind=RevisionKind.RETRACTION)
    returned = fact(1, 2, after=5, kind=RevisionKind.REVISION, content="Open on the wide shot.")
    thread = working_thread(HISTORY, (withdrawn, returned))
    first = thread.messages[0]
    assert first.state is MessageState.CURRENT and first.versions == ()
    assert thread.messages[1].live, "its answer returns with it"
    assert sequences(thread) == [1, 2, 3, 4, 5]


def test_a_withdrawn_message_reinstated_with_other_wording_is_a_correction() -> None:
    withdrawn = fact(1, 1, after=5, kind=RevisionKind.RETRACTION)
    changed = fact(1, 2, after=5, kind=RevisionKind.REVISION, content="Open on the close-up.")
    thread = working_thread(HISTORY, (withdrawn, changed))
    assert thread.messages[0].state is MessageState.CORRECTED
    assert [v.number for v in thread.messages[0].versions] == [1, 2]


def test_a_version_point_inside_a_hidden_continuation_does_not_hide_the_view() -> None:
    """Message 3, corrected, lies in version 1's continuation of message 1. Viewing
    message 1's version 2, message 3 and its versions are simply out of view."""
    first_fix = fact(1, 1, after=4, kind=RevisionKind.REVISION, content="Open on the close-up.")
    inner_fix = fact(3, 1, after=4, kind=RevisionKind.REVISION, content="And the third scene?")
    thread = working_thread(HISTORY, (first_fix, inner_fix))
    assert sequences(thread) == [1, 5]
    seen = working_thread(HISTORY, (first_fix, inner_fix), view={UUID(int=1): 1})
    assert seen.messages[2].versions != () and seen.messages[2].version == 2
    assert sequences(seen) == [1, 2, 3]
