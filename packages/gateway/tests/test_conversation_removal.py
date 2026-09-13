# ruff: noqa: F811, F401 - fixtures imported by name
"""Conversation Remove and Reinstate — Stage 3 of the ruling of 12 September 2026.

Real PostgreSQL, stub adapters, no provider. A removed conversation is
excluded from automatic recall and House Recall, cannot be resumed for new turns,
takes no new revision facts, and loses nothing: every message, evidence row and
cost is byte-identical. Reinstating is another appended fact and restores all of
it. Archive and Remove are independent.
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
from val_gateway.context import MEMORY_ENVELOPE_MARKER
from val_gateway.conversations import ConversationRemovedError, RemovalRefusedError
from val_gateway.loop import Turn, send
from val_gateway.revisions import RevisionRefusedError, retract, revise
from val_policy.project_resolution import ProjectSignals

FACT = "The lighthouse lens is cobalt."


def _excerpt_ids(adapter: StubAdapter) -> set[str]:
    block = next(
        (m for m in adapter.sent_messages if m.content.startswith(MEMORY_ENVELOPE_MARKER)), None
    )
    if block is None:
        return set()
    return {e["message_id"] for e in json.loads(block.content.split("\n", 1)[1])["excerpts"]}


def _everything(store: Engine, conversation_id: UUID) -> dict[str, object]:
    with store.connect() as connection:
        return {
            table: connection.execute(
                text(f"select * from {table} where conversation_id = :c order by id"),  # noqa: S608
                {"c": conversation_id},
            ).all()
            for table in (
                "messages",
                "model_calls",
                "classifications",
                "deliberations",
                "blind_positions",
                "execution_events",
                "message_revisions",
            )
        } | {
            "conversation": connection.execute(
                text(
                    "select id, project_id, title, started_at, last_message_at, archived_at "
                    "from conversations where id = :c"
                ),
                {"c": conversation_id},
            ).one()
        }


def _ask(store: Engine, content: str, **signals: object) -> StubAdapter:
    adapter = answering()
    send(
        store,
        build_gateway(store, adapter),
        content,
        catalogue=catalogue(store),
        signals=ProjectSignals(**signals),  # type: ignore[arg-type]
    )
    return adapter


def test_remove_excludes_both_recall_paths_and_destroys_nothing(store: Engine) -> None:
    seeded = seeded_conversation(
        store, scope_of(store, ALPHA_SLUG), "Alpha history", (StoredRole.USER, FACT)
    )
    fact_id = str(conv.history(store, seeded.id)[0].id)
    assert fact_id in _excerpt_ids(
        _ask(store, "Remind me about the lighthouse lens colour.", explicit_selection=ALPHA_SLUG)
    )
    before = _everything(store, seeded.id)

    removed = conv.remove(store, seeded.id, note="finished with this")
    assert removed.removed_at is not None
    assert _everything(store, seeded.id) == before, "nothing in the conversation changed"

    assert fact_id not in _excerpt_ids(
        _ask(store, "Remind me about the lighthouse lens colour.", explicit_selection=ALPHA_SLUG)
    )
    assert fact_id not in _excerpt_ids(
        _ask(
            store,
            "What did we decide about the lighthouse lens in our earlier conversations?",
            explicit_no_project=True,
        )
    )

    conv.reinstate(store, seeded.id)
    assert conv.load(store, seeded.id).removed_at is None
    assert fact_id in _excerpt_ids(
        _ask(store, "Remind me about the lighthouse lens colour.", explicit_selection=ALPHA_SLUG)
    )


def test_a_removed_conversation_refuses_new_turns_before_writing_anything(store: Engine) -> None:
    adapter = answering()
    first = send(
        store,
        build_gateway(store, adapter),
        "Begin the harbour notes.",
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )
    assert isinstance(first, Turn)
    conv.remove(store, first.conversation.id)
    before = _everything(store, first.conversation.id)
    calls = adapter.calls

    with pytest.raises(ConversationRemovedError, match="reinstate it to continue"):
        send(
            store,
            build_gateway(store, adapter),
            "Continue.",
            catalogue=catalogue(store),
            conversation_id=first.conversation.id,
        )
    assert adapter.calls == calls, "no provider contacted"
    assert _everything(store, first.conversation.id) == before, "no message appended"

    conv.reinstate(store, first.conversation.id)
    resumed = send(
        store,
        build_gateway(store, adapter),
        "Continue.",
        catalogue=catalogue(store),
        conversation_id=first.conversation.id,
    )
    assert isinstance(resumed, Turn)


def test_a_removed_conversation_takes_no_revision_facts(store: Engine) -> None:
    seeded = seeded_conversation(
        store, scope_of(store, ALPHA_SLUG), "Alpha history", (StoredRole.USER, FACT)
    )
    message_id = conv.history(store, seeded.id)[0].id
    conv.remove(store, seeded.id)
    for attempt in (
        lambda: revise(store, message_id, "The lighthouse lens is saffron."),
        lambda: retract(store, message_id),
    ):
        with pytest.raises(RevisionRefusedError) as refused:
            attempt()
        assert refused.value.reason == "removed"


def test_removal_facts_alternate_and_are_frozen(store: Engine) -> None:
    seeded = seeded_conversation(
        store, scope_of(store, ALPHA_SLUG), "Alpha history", (StoredRole.USER, FACT)
    )
    with pytest.raises(RemovalRefusedError) as refused:
        conv.reinstate(store, seeded.id)
    assert refused.value.reason == "not_removed"
    conv.remove(store, seeded.id)
    with pytest.raises(RemovalRefusedError) as refused:
        conv.remove(store, seeded.id)
    assert refused.value.reason == "already_removed"

    # The trigger holds for any writer.
    with pytest.raises(Exception, match="already removed"), store.begin() as connection:
        connection.execute(
            text(
                "insert into conversation_removals (conversation_id, event_number, kind, "
                "authored_by) values (:c, 2, 'removed', 'Lord Armand')"
            ),
            {"c": seeded.id},
        )
    with pytest.raises(Exception, match="rows are evidence"), store.begin() as connection:
        connection.execute(text("update conversation_removals set kind = 'reinstated'"))
    with pytest.raises(Exception, match="hard delete is not permitted"), store.begin() as c:
        c.execute(text("delete from conversation_removals"))
    with pytest.raises(Exception, match="hard delete is not permitted"), store.begin() as c:
        c.execute(text("delete from conversations where id = :c"), {"c": seeded.id})


def test_listing_leaves_out_removed_conversations_unless_asked(store: Engine) -> None:
    alpha = scope_of(store, ALPHA_SLUG)
    kept = seeded_conversation(store, alpha, "Kept", (StoredRole.USER, "One."))
    gone = seeded_conversation(store, alpha, "Removed", (StoredRole.USER, "Two."))
    conv.remove(store, gone.id)
    assert [c.id for c in conv.listing(store)] == [kept.id]
    assert {c.id for c in conv.listing(store, include_removed=True)} == {kept.id, gone.id}


def test_archive_and_remove_are_independent(store: Engine) -> None:
    seeded = seeded_conversation(
        store, scope_of(store, ALPHA_SLUG), "Alpha history", (StoredRole.USER, FACT)
    )
    conv.set_archived(store, seeded.id, archived=True)
    conv.remove(store, seeded.id)
    conv.set_archived(store, seeded.id, archived=False)
    record = conv.load(store, seeded.id)
    assert record.archived_at is None and record.removed_at is not None
    conv.reinstate(store, seeded.id)
    record = conv.load(store, seeded.id)
    assert record.archived_at is None and record.removed_at is None
