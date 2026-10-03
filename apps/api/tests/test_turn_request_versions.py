"""The turn request's version fields — owner order, 2 October 2026 (§B, §C)."""

from __future__ import annotations

from uuid import UUID

from val_api.contracts import MessageView, TurnRequest, VersionView


def test_a_turn_may_answer_a_correction_or_continue_from_a_version() -> None:
    plain = TurnRequest(content="Hello.")
    assert plain.revise_message_id is None and plain.continue_from_message_id is None
    revising = TurnRequest(content="Open on the close-up.", revise_message_id=UUID(int=1))
    assert revising.revise_message_id == UUID(int=1)
    continuing = TurnRequest(
        content="And the second scene?",
        conversation_id=UUID(int=2),
        continue_from_message_id=UUID(int=1),
        continue_from_revision=0,
    )
    assert (continuing.continue_from_message_id, continuing.continue_from_revision) == (
        UUID(int=1),
        0,
    )


def test_a_message_view_carries_its_versions_and_whether_it_is_in_view() -> None:
    view = MessageView(
        id=UUID(int=1),
        role="user",
        content="B",
        sequence=1,
        created_at="2026-10-02T20:00:00Z",  # type: ignore[arg-type]
        version=2,
        versions=[
            VersionView(
                number=1, revision_number=0, content="A", created_at="2026-10-02T20:00:00Z"
            ),  # type: ignore[arg-type]
            VersionView(
                number=2, revision_number=1, content="B", created_at="2026-10-02T20:01:00Z"
            ),  # type: ignore[arg-type]
        ],
        in_view=True,
    )
    assert view.version == 2 and len(view.versions) == 2
    assert (
        MessageView(
            id=UUID(int=2), role="val", content="x", sequence=2, created_at="2026-10-02T20:00:00Z"
        ).in_view
        is True
    )  # type: ignore[arg-type]
