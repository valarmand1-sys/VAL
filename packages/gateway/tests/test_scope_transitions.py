# ruff: noqa: F811, F401 - fixtures imported by name
"""Explicit scope transitions — Stage 4 of the ruling of 12 September 2026.

Real PostgreSQL, stub adapters, no provider. What is proved here:

- a move never changes `conversations.project_id`, and the 0008 guard still
  refuses any attempt to;
- pre-transition messages and calls keep their historical scope; post-transition
  turns, calls and evidence receive the new effective scope; resume uses it;
- the moved conversation's own retained history survives the move;
- automatic recall scopes every message by the scope it was written in, so a
  move carries no unrelated material between projects, in either direction;
- moving to explicit no-project leaves automatic recall not run while keeping
  the thread;
- House Recall reports each excerpt's source scope as written;
- the writer and the trigger refuse no-op, stale, unknown and removed moves.

The existing Project A / Project B isolation tests are untouched; these add the
cases a move creates.
"""

from __future__ import annotations

import json
from uuid import UUID

import pytest
from gateway_fakes import StubAdapter
from sqlalchemy import Engine, text
from test_conversation_memory import (
    ALPHA_SLUG,
    BETA_SLUG,
    answering,
    build_gateway,
    catalogue,
    clean_personas,
    project,
    scope_of,
    seeded_conversation,
    store,
)

from val_domain.conversation import StoredRole
from val_domain.execution import ExecutionEventType
from val_domain.gateway import GatewayError, Message, TurnReference
from val_domain.project import ExplicitNoProject, ResolvedProject
from val_gateway import conversations as conv
from val_gateway.context import MEMORY_ENVELOPE_MARKER, STATE_ENVELOPE_MARKER
from val_gateway.conversations import ScopeTransitionRefusedError
from val_gateway.execution import record_event
from val_gateway.loop import Turn, send
from val_policy.project_resolution import ProjectSignals

ALPHA_ONLY = "The lighthouse keeper's ledger is bound in green morocco."
BETA_ONLY = "The harbour survey's ledger is bound in red morocco."


def _state(adapter: StubAdapter) -> dict[str, object]:
    block = next(m for m in adapter.sent_messages if m.content.startswith(STATE_ENVELOPE_MARKER))
    return json.loads(block.content.split("\n", 1)[1])["prior_record_state"]


def _excerpts(adapter: StubAdapter) -> list[dict[str, object]]:
    block = next(
        (m for m in adapter.sent_messages if m.content.startswith(MEMORY_ENVELOPE_MARKER)), None
    )
    return [] if block is None else list(json.loads(block.content.split("\n", 1)[1])["excerpts"])


def _turn(store: Engine, content: str, **kwargs: object) -> tuple[Turn, StubAdapter]:
    adapter = answering("Noted, my lord.")
    conversation_id = kwargs.pop("conversation_id", None)
    signals = None if conversation_id else ProjectSignals(**kwargs)  # type: ignore[arg-type]
    outcome = send(
        store,
        build_gateway(store, adapter),
        content,
        catalogue=catalogue(store),
        signals=signals,
        conversation_id=conversation_id,  # type: ignore[arg-type]
    )
    assert isinstance(outcome, Turn), outcome
    return outcome, adapter


def _origin(store: Engine, conversation_id: UUID) -> UUID | None:
    with store.connect() as connection:
        return connection.execute(
            text("select project_id from conversations where id = :c"), {"c": conversation_id}
        ).scalar_one()


def _calls(store: Engine, conversation_id: UUID) -> list[tuple[object, ...]]:
    with store.connect() as connection:
        return [
            tuple(row)
            for row in connection.execute(
                text(
                    "select m.sequence, c.project_id, c.project_attribution::text "
                    "  from model_calls c join messages m on m.id = c.message_id "
                    " where c.conversation_id = :c order by m.sequence"
                ),
                {"c": conversation_id},
            )
        ]


# --- origin immutable; history keeps its scope; the future takes the new one ------------


def test_a_move_keeps_the_origin_and_the_past_and_attributes_the_future(store: Engine) -> None:
    alpha = project(store, ALPHA_SLUG)
    beta = project(store, BETA_SLUG)
    first, _ = _turn(store, "Begin the ledger notes.", explicit_selection=ALPHA_SLUG)
    conversation_id = first.conversation.id

    moved = conv.move(store, conversation_id, to_project_id=beta.id)
    assert moved.project_id == alpha.id, "the origin is untouched"
    assert moved.current_project_id == beta.id and moved.scope_transitions == 1
    assert _origin(store, conversation_id) == alpha.id
    with pytest.raises(Exception, match="project_id is immutable"), store.begin() as connection:
        connection.execute(
            text("update conversations set project_id = :b where id = :c"),
            {"b": beta.id, "c": conversation_id},
        )

    second, _ = _turn(store, "Continue the ledger notes.", conversation_id=conversation_id)
    assert isinstance(second.scope, ResolvedProject) and second.scope.project.id == beta.id
    assert _calls(store, conversation_id) == [
        (1, alpha.id, "resolved"),
        (3, beta.id, "resolved"),
    ]

    # Evidence recorded against each message carries that message's scope.
    earlier = record_event(
        store,
        conversation_id=conversation_id,
        message_id=first.val_message.id,
        subject="the first notes",
        event_type=ExecutionEventType.ACCEPTED,
        reason="clear",
    )
    later = record_event(
        store,
        conversation_id=conversation_id,
        message_id=second.val_message.id,
        subject="the continued notes",
        event_type=ExecutionEventType.ACCEPTED,
        reason="clear",
    )
    assert earlier.project_id == alpha.id and later.project_id == beta.id

    (transition,) = conv.scope_transitions(store, conversation_id)
    assert (transition.from_project_id, transition.to_project_id) == (alpha.id, beta.id)
    assert transition.after_sequence == 2


def test_the_moved_conversation_keeps_its_own_thread(store: Engine) -> None:
    beta = project(store, BETA_SLUG)
    first, _ = _turn(store, "The ledger is bound in green morocco.", explicit_selection=ALPHA_SLUG)
    conv.move(store, first.conversation.id, to_project_id=beta.id)
    _, adapter = _turn(store, "What binding did I name?", conversation_id=first.conversation.id)
    contents = [m.content for m in adapter.sent_messages]
    assert "The ledger is bound in green morocco." in contents
    assert _state(adapter)["same_conversation_history"]["prior_messages"] == 2


def test_a_call_attributed_to_the_old_scope_after_a_move_is_refused(store: Engine) -> None:
    alpha = scope_of(store, ALPHA_SLUG)
    beta = project(store, BETA_SLUG)
    conversation = conv.create(store, scope=alpha, title="A1")
    conv.append(store, conversation.id, role=StoredRole.USER, content="Hello.")
    conv.move(store, conversation.id, to_project_id=beta.id)
    later = conv.append(store, conversation.id, role=StoredRole.USER, content="Hello again.")
    adapter = answering()
    with pytest.raises(GatewayError) as caught:
        build_gateway(store, adapter).converse(
            (Message(role="user", content="Hello again."),),
            scope=alpha,
            turn=TurnReference(conversation_id=conversation.id, message_id=later.id),
        )
    assert "is scoped to" in str(caught.value)
    assert adapter.calls == 0


# --- automatic recall by each message's own scope -----------------------------------------


def test_recall_follows_the_scope_each_message_was_written_in(store: Engine) -> None:
    alpha = scope_of(store, ALPHA_SLUG)
    beta = project(store, BETA_SLUG)
    # Unrelated Project Alpha material, elsewhere.
    seeded_conversation(store, alpha, "Alpha elsewhere", (StoredRole.USER, ALPHA_ONLY))
    # A conversation that begins in Alpha and is moved to Beta.
    moving = seeded_conversation(
        store, alpha, "Moving", (StoredRole.USER, "Pre-move: the ledger's ribbon is saffron.")
    )
    conv.move(store, moving.id, to_project_id=beta.id)
    conv.append(
        store, moving.id, role=StoredRole.USER, content="Post-move: the ledger's clasp is brass."
    )

    # Inside the moved conversation (now Beta): unrelated Alpha material never arrives.
    _, adapter = _turn(store, "Remind me about the ledger binding.", conversation_id=moving.id)
    assert ALPHA_ONLY not in {e["content"] for e in _excerpts(adapter)}

    # A Beta conversation reaches the moved conversation's post-move message only.
    _, adapter = _turn(
        store, "Remind me about the ledger ribbon and clasp.", explicit_selection=BETA_SLUG
    )
    contents = {e["content"] for e in _excerpts(adapter)}
    assert "Post-move: the ledger's clasp is brass." in contents
    assert "Pre-move: the ledger's ribbon is saffron." not in contents
    assert all(e["project_id"] == str(beta.id) for e in _excerpts(adapter))

    # An Alpha conversation reaches the pre-move message only.
    _, adapter = _turn(
        store, "Remind me about the ledger ribbon and clasp.", explicit_selection=ALPHA_SLUG
    )
    contents = {e["content"] for e in _excerpts(adapter)}
    assert "Pre-move: the ledger's ribbon is saffron." in contents
    assert "Post-move: the ledger's clasp is brass." not in contents


def test_moving_out_of_every_project_stops_automatic_recall_and_keeps_the_thread(
    store: Engine,
) -> None:
    alpha = scope_of(store, ALPHA_SLUG)
    seeded_conversation(store, alpha, "Alpha elsewhere", (StoredRole.USER, ALPHA_ONLY))
    first, _ = _turn(store, "The ledger binding is on my mind.", explicit_selection=ALPHA_SLUG)
    moved = conv.move(store, first.conversation.id, to_project_id=None)
    assert moved.current_project_id is None and moved.project_id is not None

    second, adapter = _turn(
        store, "Remind me about the ledger binding.", conversation_id=first.conversation.id
    )
    assert isinstance(second.scope, ExplicitNoProject)
    state = _state(adapter)
    assert state["retrieved_excerpts"] == {
        "state": "not_run",
        "count": 0,
        "detail": "no_project_scope",
    }
    assert "The ledger binding is on my mind." in [m.content for m in adapter.sent_messages]
    assert _calls(store, first.conversation.id)[-1][1:] == (None, "explicit_none")


def test_house_recall_reports_each_excerpts_scope_as_written(store: Engine) -> None:
    alpha = scope_of(store, ALPHA_SLUG)
    beta = project(store, BETA_SLUG)
    moving = seeded_conversation(
        store, alpha, "Moving", (StoredRole.USER, "Pre-move: the lantern glass is violet.")
    )
    conv.move(store, moving.id, to_project_id=beta.id)
    conv.append(
        store, moving.id, role=StoredRole.USER, content="Post-move: the lantern glass is amber."
    )
    _, adapter = _turn(
        store,
        "What did we decide about the lantern glass in our earlier conversations?",
        explicit_no_project=True,
    )
    scopes = {e["content"]: e["source_scope"] for e in _excerpts(adapter)}
    assert scopes["Pre-move: the lantern glass is violet."] == "project: Project Alpha"
    assert scopes["Post-move: the lantern glass is amber."] == "project: Project Beta"


def test_the_listing_follows_the_current_scope(store: Engine) -> None:
    alpha = scope_of(store, ALPHA_SLUG)
    beta = project(store, BETA_SLUG)
    moving = seeded_conversation(store, alpha, "Moving", (StoredRole.USER, "One."))
    assert [c.id for c in conv.listing(store, project_id=alpha.project.id)] == [moving.id]
    conv.move(store, moving.id, to_project_id=beta.id)
    assert conv.listing(store, project_id=alpha.project.id) == ()
    assert [c.id for c in conv.listing(store, project_id=beta.id)] == [moving.id]
    conv.move(store, moving.id, to_project_id=None)
    assert [c.id for c in conv.listing(store, explicit_none=True)] == [moving.id]
    conv.move(store, moving.id, to_project_id=alpha.project.id)
    assert [c.id for c in conv.listing(store, project_id=alpha.project.id)] == [moving.id]
    assert [t.transition_number for t in conv.scope_transitions(store, moving.id)] == [1, 2, 3]
    assert _origin(store, moving.id) == alpha.project.id


# --- refusals ---------------------------------------------------------------------------------


def test_no_op_unknown_and_removed_moves_are_refused(store: Engine) -> None:
    alpha = scope_of(store, ALPHA_SLUG)
    moving = seeded_conversation(store, alpha, "Moving", (StoredRole.USER, "One."))
    cases = {
        "unchanged": lambda: conv.move(store, moving.id, to_project_id=alpha.project.id),
        "unknown_project": lambda: conv.move(store, moving.id, to_project_id=UUID(int=9)),
    }
    for reason, attempt in cases.items():
        with pytest.raises(ScopeTransitionRefusedError) as refused:
            attempt()
        assert refused.value.reason == reason
    conv.remove(store, moving.id)
    with pytest.raises(ScopeTransitionRefusedError) as refused:
        conv.move(store, moving.id, to_project_id=None)
    assert refused.value.reason == "removed"
    assert conv.scope_transitions(store, moving.id) == ()


def test_the_trigger_refuses_a_move_from_the_wrong_scope_and_the_rows_are_frozen(
    store: Engine,
) -> None:
    alpha = scope_of(store, ALPHA_SLUG)
    beta = project(store, BETA_SLUG)
    moving = seeded_conversation(store, alpha, "Moving", (StoredRole.USER, "One."))
    with pytest.raises(Exception, match="effective scope"), store.begin() as connection:
        connection.execute(
            text(
                "insert into conversation_scope_transitions (conversation_id, transition_number, "
                "after_sequence, from_project_id, to_project_id, authored_by) "
                "values (:c, 1, 1, null, :b, 'Lord Armand')"
            ),
            {"c": moving.id, "b": beta.id},
        )
    with pytest.raises(Exception, match="highest sequence"), store.begin() as connection:
        connection.execute(
            text(
                "insert into conversation_scope_transitions (conversation_id, transition_number, "
                "after_sequence, from_project_id, to_project_id, authored_by) "
                "values (:c, 1, 0, :a, :b, 'Lord Armand')"
            ),
            {"c": moving.id, "a": alpha.project.id, "b": beta.id},
        )
    conv.move(store, moving.id, to_project_id=beta.id)
    with pytest.raises(Exception, match="rows are evidence"), store.begin() as connection:
        connection.execute(text("update conversation_scope_transitions set to_project_id = null"))
    with pytest.raises(Exception, match="hard delete is not permitted"), store.begin() as c:
        c.execute(text("delete from conversation_scope_transitions"))
