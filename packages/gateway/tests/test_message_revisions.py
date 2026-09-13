# ruff: noqa: F811, F401 - fixtures imported by name
"""Message revision and retraction — Stage 2 of the ruling of 12 September 2026.

Real PostgreSQL, stub adapters, no provider. What is proved here:

- the original `messages` row is byte-identical after a revision, and neither
  it nor a revision fact can be updated or deleted;
- a revision consumes no message sequence;
- **as-of exactness** — a call made before a revision reconstructs, afterwards,
  to exactly the request it sent; a revision recorded while a turn is open is
  invisible to that turn; the lock makes the order exact under concurrency;
- a later turn receives the corrected wording in the original position, Val's
  answer stays attached to the wording she received, and the record-state
  envelope says so deterministically;
- a retracted exchange leaves assembly and both recall paths, while downstream
  messages, classifications, deliberations and costs stay exactly as they were;
- a message anchoring a deliberation refuses revision and permits retraction;
- Val's words are never revised; Restricted wording is refused;
- both recall paths match a corrected message on its corrected wording and mark
  the excerpt so it is never presented as what was said at the time.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
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
    fake_credential,
    scope_of,
    seeded_conversation,
    store,
)

from val_domain.conversation import MessageState, RevisionKind, StoredRole
from val_domain.deliberation import ClassifiedBy, Confidence, Ordering, Outcome
from val_domain.project import ExplicitNoProject
from val_gateway import conversations as conv
from val_gateway import loop
from val_gateway.context import (
    ANSWERED_EARLIER_WORDING_NOTE,
    CORRECTED_WORDING_NOTE,
    MEMORY_ENVELOPE_MARKER,
    STATE_ENVELOPE_MARKER,
)
from val_gateway.deliberation import record_deliberation
from val_gateway.loop import OpenedTurn, Turn, assemble_turn, send
from val_gateway.revisions import RevisionRefusedError, retract, revise
from val_policy.project_resolution import ProjectSignals

FIXED_NOW = datetime.fromisoformat("2026-09-12T18:00:00-05:00")

ASK_A = "Should the harbour scene open on the wide shot?"
CORRECTED_A = "Should the harbour scene open on the close-up?"


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """The envelope states the time; a reconstruction must read the same clock."""
    monkeypatch.setattr(loop, "local_now", lambda: FIXED_NOW)


def _state(adapter: StubAdapter) -> dict[str, object]:
    block = next(m for m in adapter.sent_messages if m.content.startswith(STATE_ENVELOPE_MARKER))
    return json.loads(block.content.split("\n", 1)[1])["prior_record_state"]


def _excerpts(adapter: StubAdapter) -> list[dict[str, object]]:
    block = next(
        (m for m in adapter.sent_messages if m.content.startswith(MEMORY_ENVELOPE_MARKER)), None
    )
    if block is None:
        return []
    return list(json.loads(block.content.split("\n", 1)[1])["excerpts"])


def _say(store: Engine, content: str, conversation_id: UUID | None, reply: str) -> Turn:
    adapter = answering(reply)
    outcome = send(
        store,
        build_gateway(store, adapter),
        content,
        catalogue=catalogue(store),
        signals=None if conversation_id else ProjectSignals(explicit_no_project=True),
        conversation_id=conversation_id,
    )
    assert isinstance(outcome, Turn)
    _say.last_adapter = adapter  # type: ignore[attr-defined]
    return outcome


def _conversation_rows(store: Engine, conversation_id: UUID) -> dict[str, object]:
    with store.connect() as connection:
        return {
            "messages": connection.execute(
                text(
                    "select id, role, content, sequence, created_at from messages "
                    "where conversation_id = :c order by sequence"
                ),
                {"c": conversation_id},
            ).all(),
            "calls": connection.execute(
                text(
                    "select id, message_id, project_id, task_type, cost, tokens_in "
                    "from model_calls where conversation_id = :c order by created_at, id"
                ),
                {"c": conversation_id},
            ).all(),
            "deliberations": connection.execute(
                text("select * from deliberations where conversation_id = :c order by id"),
                {"c": conversation_id},
            ).all(),
        }


# --- the original is untouched; the fact is frozen ------------------------------


def test_the_original_message_row_is_byte_identical_after_a_revision(store: Engine) -> None:
    first = _say(store, ASK_A, None, "The wide shot, my lord.")
    before = _conversation_rows(store, first.conversation.id)
    fact = revise(store, first.user_message.id, CORRECTED_A, note=None)
    assert fact.kind is RevisionKind.REVISION and fact.revision_number == 1
    assert fact.after_sequence == 2, "recorded after the answer existed"
    assert _conversation_rows(store, first.conversation.id) == before
    with store.connect() as connection:
        stored = connection.execute(
            text("select content from messages where id = :m"), {"m": first.user_message.id}
        ).scalar_one()
    assert stored == ASK_A


def test_revision_facts_cannot_be_updated_or_deleted(store: Engine) -> None:
    first = _say(store, ASK_A, None, "The wide shot, my lord.")
    revise(store, first.user_message.id, CORRECTED_A)
    with pytest.raises(Exception, match="rows are evidence"), store.begin() as connection:
        connection.execute(text("update message_revisions set content = 'rewritten'"))
    with pytest.raises(Exception, match="hard delete is not permitted"), store.begin() as c:
        c.execute(text("delete from message_revisions"))
    with pytest.raises(Exception, match="rows are evidence"), store.begin() as connection:
        connection.execute(
            text("update messages set content = 'rewritten' where id = :m"),
            {"m": first.user_message.id},
        )


def test_a_revision_consumes_no_message_sequence(store: Engine) -> None:
    first = _say(store, ASK_A, None, "The wide shot, my lord.")
    revise(store, first.user_message.id, CORRECTED_A)
    second = _say(store, "And the second scene?", first.conversation.id, "The workshop.")
    assert second.user_message.sequence == 3
    assert [m.sequence for m in conv.history(store, first.conversation.id)] == [1, 2, 3, 4]


# --- as-of exactness --------------------------------------------------------------


def test_an_earlier_call_reconstructs_exactly_after_a_revision(store: Engine) -> None:
    first = _say(store, ASK_A, None, "The wide shot, my lord.")
    second = _say(store, "And the second scene?", first.conversation.id, "The workshop.")
    sent_before = _say.last_adapter.sent_messages  # type: ignore[attr-defined]
    assert sent_before[0].content == ASK_A

    revise(store, first.user_message.id, CORRECTED_A)
    third = _say(store, "Thank you.", first.conversation.id, "My lord.")

    # Reconstruct the second turn's request from the record, after the revision
    # and after a later turn: identical to what the adapter was handed.
    reconstructed, _ = assemble_turn(
        store,
        OpenedTurn(
            conversation=second.conversation, scope=second.scope, user_message=second.user_message
        ),
    )
    assert reconstructed == sent_before

    # The later turn received the corrected wording in A's position.
    later = _say.last_adapter  # type: ignore[attr-defined]
    del later
    reconstructed_third, _ = assemble_turn(
        store,
        OpenedTurn(
            conversation=third.conversation, scope=third.scope, user_message=third.user_message
        ),
    )
    assert reconstructed_third[0].content == CORRECTED_A
    assert reconstructed_third[1].content == "The wide shot, my lord."


def test_a_revision_recorded_while_a_turn_is_open_is_invisible_to_it(store: Engine) -> None:
    first = _say(store, ASK_A, None, "The wide shot, my lord.")
    opened = loop.open_turn(
        store,
        "And the second scene?",
        catalogue=catalogue(store),
        conversation_id=first.conversation.id,
    )
    assert isinstance(opened, OpenedTurn)
    # The revision lands after this turn's message was appended, before assembly.
    fact = revise(store, first.user_message.id, CORRECTED_A)
    assert fact.after_sequence == opened.user_message.sequence
    messages, _ = assemble_turn(store, opened)
    assert messages[0].content == ASK_A, "a fact recorded after the turn opened cannot reach it"


def test_the_conversation_lock_orders_a_revision_against_a_concurrent_append(
    store: Engine,
) -> None:
    first = _say(store, ASK_A, None, "The wide shot, my lord.")
    result: dict[str, object] = {}
    holder = store.connect()
    transaction = holder.begin()
    holder.execute(
        text("select id from conversations where id = :c for update"), {"c": first.conversation.id}
    )

    def revise_in_background() -> None:
        result["fact"] = revise(store, first.user_message.id, CORRECTED_A)

    worker = threading.Thread(target=revise_in_background)
    worker.start()
    time.sleep(0.3)
    assert "fact" not in result, "the revision waits for the conversation lock"
    holder.execute(
        text(
            "insert into messages (conversation_id, role, content, sequence) "
            "values (:c, 'user', 'Appended under the lock.', 3)"
        ),
        {"c": first.conversation.id},
    )
    transaction.commit()
    holder.close()
    worker.join(timeout=10)
    fact = result["fact"]
    assert fact.after_sequence == 3  # type: ignore[attr-defined]
    thread = conv.working(store, first.conversation.id, as_of_sequence=3)
    assert thread.messages[0].content == ASK_A, "the append at 3 preceded the revision"


# --- the later turn: corrected wording, attached answer, stated facts ---------------


def test_a_later_turn_is_told_the_earlier_message_was_corrected_after_its_answer(
    store: Engine,
) -> None:
    first = _say(store, ASK_A, None, "The wide shot, my lord.")
    revise(store, first.user_message.id, CORRECTED_A)
    _say(store, "Thank you.", first.conversation.id, "My lord.")
    adapter = _say.last_adapter  # type: ignore[attr-defined]
    assert adapter.sent_messages[0].content == CORRECTED_A
    assert adapter.sent_messages[1].content == "The wide shot, my lord."
    history = _state(adapter)["same_conversation_history"]
    assert history["corrected_after_answer"] == [{"message_position": 1, "answer_position": 2}]
    assert "withdrawn_exchanges" not in history


def test_no_facts_means_no_revision_keys_in_the_envelope(store: Engine) -> None:
    first = _say(store, ASK_A, None, "The wide shot, my lord.")
    _say(store, "Thank you.", first.conversation.id, "My lord.")
    history = _state(_say.last_adapter)["same_conversation_history"]  # type: ignore[attr-defined]
    assert set(history) == {"state", "prior_messages", "retained_in_this_request"}


# --- retraction ----------------------------------------------------------------------


def test_a_retracted_exchange_leaves_assembly_and_keeps_everything_else(store: Engine) -> None:
    first = _say(store, ASK_A, None, "The wide shot, my lord.")
    second = _say(store, "And the second scene?", first.conversation.id, "The workshop.")
    before = _conversation_rows(store, first.conversation.id)

    retract(store, first.user_message.id)
    assert _conversation_rows(store, first.conversation.id) == before, "nothing rewritten"

    _say(store, "Thank you.", first.conversation.id, "My lord.")
    adapter = _say.last_adapter  # type: ignore[attr-defined]
    contents = [m.content for m in adapter.sent_messages]
    assert ASK_A not in contents and "The wide shot, my lord." not in contents
    assert "And the second scene?" in contents and "The workshop." in contents
    history = _state(adapter)["same_conversation_history"]
    assert history["withdrawn_exchanges"] == [{"after_position": 0}]
    assert history["prior_messages"] == 2

    thread = conv.working(store, first.conversation.id)
    assert thread.messages[0].state is MessageState.WITHDRAWN
    assert thread.messages[1].answered_state is MessageState.WITHDRAWN
    assert second.user_message.id in {m.record.id for m in thread.live()}


def test_a_retracted_exchange_leaves_both_recall_paths(store: Engine) -> None:
    alpha = scope_of(store, ALPHA_SLUG)
    seeded = seeded_conversation(
        store,
        alpha,
        "Alpha history",
        (StoredRole.USER, "The lighthouse lens is cobalt."),
        (StoredRole.VAL, "Cobalt, noted."),
    )
    withdrawn_ids = {str(message.id) for message in conv.history(store, seeded.id)}
    user_id = conv.history(store, seeded.id)[0].id
    retract(store, user_id)

    adapter = answering()
    send(
        store,
        build_gateway(store, adapter),
        "Remind me about the lighthouse lens colour.",
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_selection=ALPHA_SLUG),
    )
    assert _excerpts(adapter) == []
    assert _state(adapter)["retrieved_excerpts"]["state"] == "zero"

    adapter = answering()
    send(
        store,
        build_gateway(store, adapter),
        "What did we decide about the lighthouse lens in our earlier conversations?",
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )
    # House Recall may find the turn just sent in Project Alpha; it never finds
    # the withdrawn exchange, message or answer.
    assert not withdrawn_ids & {str(e["message_id"]) for e in _excerpts(adapter)}
    assert _state(adapter)["house_recall"]["state"] in ("zero", "returned")


def test_retracting_twice_is_refused(store: Engine) -> None:
    first = _say(store, ASK_A, None, "The wide shot, my lord.")
    retract(store, first.user_message.id)
    with pytest.raises(RevisionRefusedError) as refused:
        retract(store, first.user_message.id)
    assert refused.value.reason == "already_withdrawn"


# --- deliberated messages ---------------------------------------------------------------


def test_a_deliberated_message_refuses_revision_and_permits_retraction(store: Engine) -> None:
    first = _say(store, ASK_A, None, "The close-up, my lord.")
    record_deliberation(
        store,
        conversation_id=first.conversation.id,
        message_id=first.user_message.id,
        position="Open on the close-up.",
        confidence=Confidence.MEDIUM,
        reasoning="The film is about her hands.",
        stripped_content="",
        ordering=Ordering.CONTAMINATED,
        user_response=ASK_A,
        outcome=Outcome.HELD,
        classified_by=ClassifiedBy.USER,
    )
    before = _conversation_rows(store, first.conversation.id)

    with pytest.raises(RevisionRefusedError) as refused:
        revise(store, first.user_message.id, CORRECTED_A)
    assert refused.value.reason == "deliberated"
    assert "recorded decision exchange" in str(refused.value)

    # The database refuses it for any writer too.
    with pytest.raises(Exception, match="recorded decision exchange"), store.begin() as c:
        c.execute(
            text(
                "insert into message_revisions (conversation_id, message_id, revision_number, "
                "after_sequence, kind, content, authored_by) values (:c, :m, 1, 2, 'revision', "
                "'x', 'Lord Armand')"
            ),
            {"c": first.conversation.id, "m": first.user_message.id},
        )

    fact = retract(store, first.user_message.id)
    assert fact.kind is RevisionKind.RETRACTION
    assert _conversation_rows(store, first.conversation.id) == before


# --- authorship, wording, Restricted -----------------------------------------------------


def test_val_messages_cannot_be_revised_or_retracted(store: Engine) -> None:
    first = _say(store, ASK_A, None, "The wide shot, my lord.")
    for attempt in (
        lambda: revise(store, first.val_message.id, "Something else."),
        lambda: retract(store, first.val_message.id),
    ):
        with pytest.raises(RevisionRefusedError) as refused:
            attempt()
        assert refused.value.reason == "not_authored_by_lord_armand"
    with (
        pytest.raises(Exception, match=r"Val.{1,2}s words are hers"),
        store.begin() as c,
    ):
        c.execute(
            text(
                "insert into message_revisions (conversation_id, message_id, revision_number, "
                "after_sequence, kind, authored_by) values (:c, :m, 1, 2, 'retraction', 'x')"
            ),
            {"c": first.conversation.id, "m": first.val_message.id},
        )


def test_empty_unchanged_restricted_and_unknown_revisions_are_refused(store: Engine) -> None:
    first = _say(store, ASK_A, None, "The wide shot, my lord.")
    cases = {
        "empty": lambda: revise(store, first.user_message.id, "   "),
        "unchanged": lambda: revise(store, first.user_message.id, ASK_A),
        "restricted": lambda: revise(
            store,
            first.user_message.id,
            "The key is " + fake_credential("sk-", "ant-", "api03-", "A" * 40),
        ),
        "not_found": lambda: revise(store, UUID(int=7), CORRECTED_A),
    }
    for reason, attempt in cases.items():
        with pytest.raises(RevisionRefusedError) as refused:
            attempt()
        assert refused.value.reason == reason, reason
    with store.connect() as connection:
        assert connection.execute(text("select count(*) from message_revisions")).scalar_one() == 0


def test_a_revision_after_a_retraction_reinstates_the_message(store: Engine) -> None:
    first = _say(store, ASK_A, None, "The wide shot, my lord.")
    retract(store, first.user_message.id)
    fact = revise(store, first.user_message.id, ASK_A)
    assert fact.revision_number == 2
    thread = conv.working(store, first.conversation.id)
    assert thread.messages[0].state is MessageState.CORRECTED
    assert thread.messages[0].live and thread.messages[1].live


# --- recall of corrected wording -----------------------------------------------------------


def test_both_recall_paths_match_corrected_wording_and_mark_the_excerpt(store: Engine) -> None:
    alpha = scope_of(store, ALPHA_SLUG)
    seeded = seeded_conversation(
        store,
        alpha,
        "Alpha history",
        (StoredRole.USER, "The lighthouse lens is cobalt."),
        (StoredRole.VAL, "Noted, my lord."),
    )
    user_id = conv.history(store, seeded.id)[0].id
    revise(store, user_id, "The lighthouse lens is saffron.")

    adapter = answering()
    send(
        store,
        build_gateway(store, adapter),
        "Remind me about the saffron lighthouse lens.",
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_selection=ALPHA_SLUG),
    )
    excerpts = _excerpts(adapter)
    corrected = next(e for e in excerpts if e["message_id"] == str(user_id))
    assert corrected["content"] == "The lighthouse lens is saffron."
    assert corrected["wording_state"] == "corrected"
    assert corrected["wording_note"] == CORRECTED_WORDING_NOTE
    assert corrected["sent_at"] is not None and corrected["wording_recorded_at"] is not None
    assert corrected["sent_at"] < corrected["wording_recorded_at"]

    # The original wording no longer finds it.
    adapter = answering()
    send(
        store,
        build_gateway(store, adapter),
        "Remind me about cobalt.",
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_selection=ALPHA_SLUG),
    )
    assert all(e["message_id"] != str(user_id) for e in _excerpts(adapter))

    # House Recall: the same marking, and Val's answer carries its note.
    adapter = answering()
    send(
        store,
        build_gateway(store, adapter),
        "What did we decide about the saffron lens in our earlier conversations?",
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )
    house = {e["message_id"]: e for e in _excerpts(adapter)}
    assert house[str(user_id)]["wording_state"] == "corrected"
    assert house[str(user_id)]["retrieval_path"] == "house_recall"
    val_id = str(conv.history(store, seeded.id)[1].id)
    if val_id in house:
        assert house[val_id]["answer_note"] == ANSWERED_EARLIER_WORDING_NOTE


def test_an_unrevised_excerpt_carries_no_revision_keys(store: Engine) -> None:
    alpha = scope_of(store, ALPHA_SLUG)
    seeded_conversation(
        store, alpha, "Alpha history", (StoredRole.USER, "The lighthouse lens is cobalt.")
    )
    adapter = answering()
    send(
        store,
        build_gateway(store, adapter),
        "Remind me about the cobalt lighthouse lens.",
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_selection=ALPHA_SLUG),
    )
    (excerpt,) = _excerpts(adapter)
    assert not {"wording_state", "wording_note", "answer_note", "sent_at"} & set(excerpt)
