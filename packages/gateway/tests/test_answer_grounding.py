# ruff: noqa: F811, F401 - fixtures imported by name
"""House Recall grounding continuity as provenance — ruling of 13 September 2026.

Real PostgreSQL, stub adapters, no provider. Proved here:

- a response generated with House Recall acquires the support linkage, bound to
  its call and to the exact wording of each source;
- a later retained-history turn receives provenance-only grounding state, with
  no excerpt content anywhere in the request, and House Recall does not run
  because of it;
- a response generated without House Recall acquires nothing, and no grounding
  key appears;
- a later revision of a source cannot change what the earlier answer used, and
  is reported as corrected since;
- a withdrawn source, or a removed source conversation, keeps its historical
  support role, is reported as such, and does not become live intent;
- no provider call is added.
"""

from __future__ import annotations

import json
from uuid import UUID

import pytest
from gateway_fakes import StubAdapter
from sqlalchemy import Engine, text
from test_conversation_memory import (
    ALPHA_SLUG,
    answering,
    build_gateway,
    catalogue,
    clean_personas,
    scope_of,
    seeded_conversation,
    store,
)

from val_domain.conversation import StoredRole
from val_gateway import conversations as conv
from val_gateway.context import GROUNDING_NOTE, STATE_ENVELOPE_MARKER
from val_gateway.loop import Turn, send
from val_gateway.revisions import retract, revise
from val_policy.project_resolution import ProjectSignals

SOURCE_TEXT = "The House Armand sigil is a sword held between two wolves beneath a silver moon."
ASK_HOUSE = "What did we decide about the House Armand sigil in our earlier conversations?"


def _state(adapter: StubAdapter) -> dict[str, object]:
    block = next(m for m in adapter.sent_messages if m.content.startswith(STATE_ENVELOPE_MARKER))
    return json.loads(block.content.split("\n", 1)[1])["prior_record_state"]


def _seed_source(store: Engine) -> tuple[UUID, UUID]:
    seeded = seeded_conversation(
        store, scope_of(store, ALPHA_SLUG), "The sigil", (StoredRole.USER, SOURCE_TEXT)
    )
    return seeded.id, conv.history(store, seeded.id)[0].id


def _turn(
    store: Engine, content: str, conversation_id: UUID | None = None
) -> tuple[Turn, StubAdapter]:
    adapter = answering("It is the sword between two wolves, my lord.")
    outcome = send(
        store,
        build_gateway(store, adapter),
        content,
        catalogue=catalogue(store),
        signals=None if conversation_id else ProjectSignals(explicit_no_project=True),
        conversation_id=conversation_id,
    )
    assert isinstance(outcome, Turn)
    assert adapter.calls == 1, "no provider call is added"
    return outcome, adapter


def _rows(store: Engine) -> list[object]:
    with store.connect() as connection:
        return connection.execute(
            text("select * from answer_recall_sources order by created_at, rank_position")
        ).all()


def test_a_house_recall_answer_acquires_its_support_linkage(store: Engine) -> None:
    source_conversation, source_message = _seed_source(store)
    first, _ = _turn(store, ASK_HOUSE)
    rows = _rows(store)
    assert len(rows) == 1
    row = rows[0]
    assert row.answer_message_id == first.val_message.id
    assert row.conversation_id == first.conversation.id
    assert row.source_message_id == source_message
    assert row.source_conversation_id == source_conversation
    assert row.source_revision_number is None, "the original wording"
    assert row.retrieval_path == "house_recall" and row.rank_position == 1
    with store.connect() as connection:
        call = connection.execute(
            text("select message_id, task_type::text from model_calls where id = :i"),
            {"i": row.model_call_id},
        ).one()
    assert call == (first.user_message.id, "conversation"), "bound to the call that received it"


def test_a_later_turn_receives_provenance_and_no_content(store: Engine) -> None:
    _, source_message = _seed_source(store)
    first, _ = _turn(store, ASK_HOUSE)
    _, adapter = _turn(store, "Thank you. Say more about the wolves.", first.conversation.id)

    state = _state(adapter)
    assert state["house_recall"]["state"] == "not_run", "provenance does not trigger recall"
    history = state["same_conversation_history"]
    assert history["grounding_note"] == GROUNDING_NOTE
    (answer,) = history["grounded_answers"]
    assert answer["answer_position"] == 2 and answer["support"] == "house_recall"
    (source,) = answer["sources"]
    assert source["message_id"] == str(source_message)
    assert source["conversation_title"] == "The sigil"
    assert source["source_scope"] == "project: Project Alpha"
    assert source["wording"] == "original" and source["status_now"] == "unchanged"
    assert source["retrieval_path"] == "house_recall" and source["sent_at"]
    for message in adapter.sent_messages:
        assert SOURCE_TEXT not in message.content, "no excerpt content is carried forward"


def test_an_answer_without_house_recall_acquires_nothing(store: Engine) -> None:
    _seed_source(store)
    first, _ = _turn(store, "Good evening, Val.")
    assert _rows(store) == []
    _, adapter = _turn(store, "Thank you.", first.conversation.id)
    assert "grounded_answers" not in _state(adapter)["same_conversation_history"]


def test_a_later_revision_cannot_change_what_the_answer_used(store: Engine) -> None:
    _, source_message = _seed_source(store)
    first, _ = _turn(store, ASK_HOUSE)
    revise(store, source_message, "The House Armand sigil is a sword between two ravens.")
    assert _rows(store)[0].source_revision_number is None
    _, adapter = _turn(store, "Thank you.", first.conversation.id)
    (source,) = _state(adapter)["same_conversation_history"]["grounded_answers"][0]["sources"]
    assert source["wording"] == "original" and source["status_now"] == "corrected since"


def test_a_source_retrieved_after_a_correction_records_that_correction(store: Engine) -> None:
    _, source_message = _seed_source(store)
    revise(store, source_message, SOURCE_TEXT + " It was chosen in winter.")
    _turn(store, ASK_HOUSE)
    assert _rows(store)[0].source_revision_number == 1


@pytest.mark.parametrize("withdrawal", ["retract", "remove"])
def test_a_withdrawn_source_keeps_its_historical_role_without_becoming_live(
    store: Engine, withdrawal: str
) -> None:
    source_conversation, source_message = _seed_source(store)
    first, _ = _turn(store, ASK_HOUSE)
    if withdrawal == "retract":
        retract(store, source_message)
        expected = "withdrawn since"
    else:
        conv.remove(store, source_conversation)
        expected = "conversation removed since"
    _, adapter = _turn(store, "Thank you.", first.conversation.id)
    state = _state(adapter)
    (source,) = state["same_conversation_history"]["grounded_answers"][0]["sources"]
    assert source["status_now"] == expected
    assert state["house_recall"]["state"] == "not_run"
    assert all(SOURCE_TEXT not in m.content for m in adapter.sent_messages)


def test_the_trigger_refuses_incoherent_provenance(store: Engine) -> None:
    _seed_source(store)
    first, _ = _turn(store, ASK_HOUSE)
    row = _rows(store)[0]
    base = {
        "conversation_id": row.conversation_id,
        "model_call_id": row.model_call_id,
        "source_message_id": row.source_message_id,
        "source_conversation_id": row.source_conversation_id,
        "source_sequence": row.source_sequence,
        "sent": row.source_sent_at,
    }
    insert = text(
        "insert into answer_recall_sources (conversation_id, answer_message_id, model_call_id, "
        "retrieval_path, rank_position, source_message_id, source_conversation_id, "
        "source_sequence, source_revision_number, source_sent_at, source_conversation_title) "
        "values (:conversation_id, :answer, :model_call_id, 'house_recall', 2, "
        ":source_message_id, :source_conversation_id, :source_sequence, :revision, :sent, 't')"
    )
    with pytest.raises(Exception, match="is not a Val message"), store.begin() as connection:
        connection.execute(insert, {**base, "answer": first.user_message.id, "revision": None})
    with pytest.raises(Exception, match="is not a revision"), store.begin() as connection:
        connection.execute(insert, {**base, "answer": first.val_message.id, "revision": 7})
    with pytest.raises(Exception, match="rows are evidence"), store.begin() as connection:
        connection.execute(text("update answer_recall_sources set rank_position = 3"))
    with pytest.raises(Exception, match="hard delete is not permitted"), store.begin() as c:
        c.execute(text("delete from answer_recall_sources"))
