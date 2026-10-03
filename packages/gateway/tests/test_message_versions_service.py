"""Answering a correction, and continuing from an earlier version — owner order,
2 October 2026 (§B, §C), through the real store and the deliberated path, under the
local-AI rule (every route local; the classifier NOT RUN)."""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from test_deliberation_machinery import clean_personas, ok, store
from test_local_ai_rule import _gateway_with_local, _Loopback
from test_message_revisions import ASK_A, CORRECTED_A, catalogue

from val_domain.conversation import MessageState
from val_gateway import conversations as conv
from val_gateway.deliberate import Turn, answer_revision
from val_gateway.deliberate import send as deliberated_send
from val_gateway.revisions import RevisionRefusedError
from val_policy.project_resolution import ProjectSignals


@pytest.fixture(autouse=True)
def the_rule_stands(monkeypatch: pytest.MonkeyPatch) -> None:
    import val_policy.egress as egress_policy

    monkeypatch.setattr(egress_policy, "HOSTED_MODELS_FORBIDDEN", True)


def say(store: Engine, content: str, conversation_id: UUID | None, reply: str) -> Turn:
    adapter = _Loopback([ok(reply)])
    outcome = deliberated_send(
        store,
        _gateway_with_local(store, adapter),
        content,
        catalogue=catalogue(store),
        signals=None if conversation_id else ProjectSignals(explicit_no_project=True),
        conversation_id=conversation_id,
    )
    assert hasattr(outcome, "turn"), outcome
    return outcome.turn  # type: ignore[union-attr, no-any-return]


def sent_bodies(adapter: _Loopback) -> list[str]:
    return [body for _, body in adapter.sent]


def test_a_saved_correction_is_answered_once_and_the_earlier_answer_keeps_its_version(
    store: Engine,
) -> None:
    first = say(store, ASK_A, None, "The wide shot, my lord.")
    adapter = _Loopback([ok("The close-up, my lord.")])
    outcome = answer_revision(
        store, _gateway_with_local(store, adapter), first.user_message.id, CORRECTED_A
    )
    assert hasattr(outcome, "turn"), outcome
    assert outcome.turn.val_message.content == "The close-up, my lord."  # type: ignore[union-attr]
    # One answer, to the corrected wording, with the earlier answer out of the view.
    (body,) = sent_bodies(adapter)
    assert CORRECTED_A in body and "The wide shot" not in body
    # The message was not re-appended: A, the first answer, the new answer at the end.
    thread = conv.working(store, first.conversation.id)
    assert [m.record.sequence for m in thread.messages] == [1, 2, 3]
    assert [m.in_view for m in thread.messages] == [True, False, True]
    assert thread.messages[0].version == 2 and thread.messages[0].content == CORRECTED_A
    assert thread.messages[2].answered_state is MessageState.CORRECTED
    # Version 1 keeps its answer.
    earlier = conv.working(store, first.conversation.id, view={first.user_message.id: 1})
    assert [m.record.sequence for m in earlier.live()] == [1, 2]
    assert earlier.messages[0].content == ASK_A


def test_a_refused_correction_answers_nothing(store: Engine) -> None:
    first = say(store, ASK_A, None, "The wide shot, my lord.")
    adapter = _Loopback([ok("unused")])
    with pytest.raises(RevisionRefusedError) as refused:
        answer_revision(store, _gateway_with_local(store, adapter), first.user_message.id, ASK_A)
    assert refused.value.reason == "unchanged"
    assert adapter.sent == []
    assert [m.record.sequence for m in conv.working(store, first.conversation.id).messages] == [
        1,
        2,
    ]


def test_continuing_from_an_earlier_version_uses_that_versions_history(store: Engine) -> None:
    first = say(store, ASK_A, None, "The wide shot, my lord.")
    answer_revision(
        store,
        _gateway_with_local(store, _Loopback([ok("The close-up, my lord.")])),
        first.user_message.id,
        CORRECTED_A,
    )
    # He goes back to version 1 and continues from it.
    adapter = _Loopback([ok("Gladly, my lord.")])
    outcome = deliberated_send(
        store,
        _gateway_with_local(store, adapter),
        "And the second scene?",
        catalogue=catalogue(store),
        signals=None,
        conversation_id=first.conversation.id,
        continue_from=(first.user_message.id, 0),
    )
    assert hasattr(outcome, "turn"), outcome
    (body,) = sent_bodies(adapter)
    assert ASK_A in body and "The wide shot" in body and "And the second scene?" in body
    assert CORRECTED_A not in body and "The close-up" not in body, "version 2 is not in view"
    thread = conv.working(store, first.conversation.id)
    assert thread.messages[0].version == 1
    assert [m.record.sequence for m in thread.live()] == [1, 2, 4, 5]
    with store.connect() as connection:
        rows = connection.execute(
            text("select revision_number, after_sequence from message_version_selections")
        ).all()
    assert [(r.revision_number, r.after_sequence) for r in rows] == [(0, 3)]
    # And version 2 still holds exactly its own answer.
    other = conv.working(store, first.conversation.id, view={first.user_message.id: 2})
    assert [m.record.sequence for m in other.live()] == [1, 3]
