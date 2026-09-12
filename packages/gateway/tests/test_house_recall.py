# ruff: noqa: F811, F401 - fixtures imported by name
"""House Recall through the loop — ruling of 12 September 2026.

Real PostgreSQL, stub adapters. The explicitly triggered cross-conversation
path returns material from every scope except the current conversation, with
provenance and chronology, only when the message refers to earlier
conversation; the automatic path — its project scoping, its clean room, its
leak check and its tests — is untouched.
"""

from __future__ import annotations

import json

import pytest
from gateway_fakes import FakeLedger, StubAdapter
from sqlalchemy import Engine, text
from test_conversation_memory import (
    ALPHA_FACT,
    ALPHA_SLUG,
    BETA_FACT,
    BETA_SLUG,
    NO_PROJECT_FACT,
    answering,
    build_gateway,
    catalogue,
    clean_personas,
    fake_credential,
    scope_of,
    seeded_conversation,
    store,
)

from val_domain.conversation import StoredRole
from val_domain.project import ExplicitNoProject
from val_gateway.context import MEMORY_ENVELOPE_MARKER, STATE_ENVELOPE_MARKER
from val_gateway.exchange import RestrictedContentRefusedError
from val_gateway.loop import Turn, send
from val_gateway.memory import house_recall_with_state
from val_policy.project_resolution import ProjectSignals

ASK_HOUSE = "What did we decide about the lighthouse lens colour in our earlier conversations?"
ASK_PLAIN = "Remind me about the lighthouse lens colour."


def _seed_house(store: Engine) -> None:
    alpha = scope_of(store, ALPHA_SLUG)
    beta = scope_of(store, BETA_SLUG)
    seeded_conversation(
        store, alpha, "Alpha history", (StoredRole.USER, ALPHA_FACT), (StoredRole.VAL, "Cobalt.")
    )
    seeded_conversation(
        store, beta, "Beta history", (StoredRole.USER, BETA_FACT), (StoredRole.VAL, "Amber.")
    )
    seeded_conversation(
        store, ExplicitNoProject(), "No project", (StoredRole.USER, NO_PROJECT_FACT)
    )


def _envelope(adapter: StubAdapter) -> dict[str, object] | None:
    block = next(
        (m for m in adapter.sent_messages if m.content.startswith(MEMORY_ENVELOPE_MARKER)), None
    )
    return None if block is None else json.loads(block.content.split("\n", 1)[1])


def _state(adapter: StubAdapter) -> dict[str, object]:
    block = next(m for m in adapter.sent_messages if m.content.startswith(STATE_ENVELOPE_MARKER))
    return json.loads(block.content.split("\n", 1)[1])["prior_record_state"]


def _excerpts(adapter: StubAdapter) -> list[dict[str, object]]:
    envelope = _envelope(adapter)
    return [] if envelope is None else list(envelope["excerpts"])  # type: ignore[arg-type]


# --- the explicitly triggered path ------------------------------------------------


def test_house_recall_from_an_unassigned_conversation_reaches_every_scope(store: Engine) -> None:
    _seed_house(store)
    adapter = answering()
    outcome = send(
        store,
        build_gateway(store, adapter),
        ASK_HOUSE,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )
    assert isinstance(outcome, Turn)
    excerpts = _excerpts(adapter)
    contents = {e["content"] for e in excerpts}
    assert {ALPHA_FACT, BETA_FACT, NO_PROJECT_FACT} <= contents
    assert {e["retrieval_path"] for e in excerpts} == {"house_recall"}
    assert {e["source_scope"] for e in excerpts} == {
        "project: Project Alpha",
        "project: Project Beta",
        "unassigned",
    }
    for excerpt in excerpts:
        for field in (
            "message_id",
            "conversation_id",
            "conversation_title",
            "sequence",
            "stored_role",
            "created_at",
            "project_id",
        ):
            assert field in excerpt, field
        assert excerpt["created_at"] is not None
    state = _state(adapter)
    assert state["retrieved_excerpts"] == {
        "state": "not_run",
        "count": 0,
        "detail": "no_project_scope",
    }, "the automatic path is still a clean room for an unassigned conversation"
    assert state["house_recall"]["state"] == "returned"
    assert state["house_recall"]["count"] == len(excerpts) >= 3


def test_house_recall_excludes_the_current_conversation(store: Engine) -> None:
    _seed_house(store)
    adapter = answering()
    first = send(
        store,
        build_gateway(store, adapter),
        "The lighthouse lens is, in this conversation, said to be green.",
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )
    assert isinstance(first, Turn)
    adapter = answering()
    send(
        store,
        build_gateway(store, adapter),
        ASK_HOUSE,
        catalogue=catalogue(store),
        conversation_id=first.conversation.id,
    )
    assert all(e["conversation_id"] != str(first.conversation.id) for e in _excerpts(adapter))
    assert all("green" not in str(e["content"]) for e in _excerpts(adapter))


def test_a_house_recall_turn_does_not_mutate_attribution(store: Engine) -> None:
    _seed_house(store)
    alpha = scope_of(store, ALPHA_SLUG)
    adapter = answering()
    outcome = send(
        store,
        build_gateway(store, adapter),
        ASK_HOUSE,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_selection="Project Alpha"),
    )
    assert isinstance(outcome, Turn)
    with store.connect() as connection:
        project_id = connection.execute(
            text("select project_id from conversations where id = :c"),
            {"c": outcome.conversation.id},
        ).scalar_one()
        others = connection.execute(
            text("select count(*) from conversations where project_id is distinct from :p"),
            {"p": alpha.project_id},
        ).scalar_one()
    assert project_id == alpha.project_id
    assert others == 2, "the Beta and unassigned conversations keep their own attribution"


# --- the automatic path is untouched ------------------------------------------------


def test_an_ordinary_unassigned_turn_still_searches_nothing_outside_itself(store: Engine) -> None:
    _seed_house(store)
    adapter = answering()
    send(
        store,
        build_gateway(store, adapter),
        ASK_PLAIN,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )
    assert _envelope(adapter) is None
    state = _state(adapter)
    assert state["retrieved_excerpts"]["detail"] == "no_project_scope"
    assert state["house_recall"] == {
        "state": "not_run",
        "count": 0,
        "detail": "no_cross_conversation_reference",
    }
    payload = adapter.sent_text
    assert ALPHA_FACT not in payload and BETA_FACT not in payload and NO_PROJECT_FACT not in payload


def test_an_ordinary_project_a_turn_still_cannot_receive_project_b(store: Engine) -> None:
    _seed_house(store)
    adapter = answering()
    send(
        store,
        build_gateway(store, adapter),
        ASK_PLAIN,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_selection="Project Alpha"),
    )
    excerpts = _excerpts(adapter)
    assert {e["retrieval_path"] for e in excerpts} == {"project_recall"}
    assert ALPHA_FACT in adapter.sent_text
    assert BETA_FACT not in adapter.sent_text and NO_PROJECT_FACT not in adapter.sent_text
    assert _state(adapter)["house_recall"]["state"] == "not_run"


def test_explicit_house_recall_from_project_a_reaches_b_only_through_house_recall(
    store: Engine,
) -> None:
    _seed_house(store)
    adapter = answering()
    send(
        store,
        build_gateway(store, adapter),
        ASK_HOUSE,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_selection="Project Alpha"),
    )
    excerpts = _excerpts(adapter)
    by_content = {str(e["content"]): e for e in excerpts}
    assert by_content[ALPHA_FACT]["retrieval_path"] == "project_recall", (
        "automatic recall as before"
    )
    assert by_content[BETA_FACT]["retrieval_path"] == "house_recall"
    assert by_content[NO_PROJECT_FACT]["retrieval_path"] == "house_recall"
    # Deduplicated by message identity: the Alpha fact appears once, through the automatic path.
    assert sum(1 for e in excerpts if e["content"] == ALPHA_FACT) == 1
    state = _state(adapter)
    assert state["retrieved_excerpts"]["state"] == "returned"
    assert state["house_recall"]["state"] == "returned"


def test_a_thread_grounded_reference_does_not_invoke_house_recall(store: Engine) -> None:
    _seed_house(store)
    adapter = answering("The lens is cobalt, my lord.")
    first = send(
        store,
        build_gateway(store, adapter),
        "Which colour is the lens?",
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )
    assert isinstance(first, Turn)
    adapter = answering()
    send(
        store,
        build_gateway(store, adapter),
        'You said earlier "The lens is cobalt, my lord." Why cobalt?',
        catalogue=catalogue(store),
        conversation_id=first.conversation.id,
    )
    state = _state(adapter)
    assert state["house_recall"] == {"state": "not_run", "count": 0, "detail": "thread_grounded"}
    assert _envelope(adapter) is None


# --- states, chronology, protections --------------------------------------------------


def test_house_recall_states_are_represented_independently(
    store: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # zero: an explicit reference with nothing matching anywhere else.
    adapter = answering()
    send(
        store,
        build_gateway(store, adapter),
        "What did we decide about the zebra enclosure in our earlier conversations?",
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )
    state = _state(adapter)
    assert state["house_recall"] == {"state": "zero", "count": 0}
    assert state["retrieved_excerpts"]["state"] == "not_run"

    # unavailable: the house query fails at the store; the turn still proceeds.
    import val_gateway.loop as loop
    from val_gateway.memory import RecallOutcome

    monkeypatch.setattr(
        loop,
        "house_recall_with_state",
        lambda engine, **kw: RecallOutcome(state="unavailable", detail="RuntimeError"),
    )
    adapter = answering()
    outcome = send(
        store,
        build_gateway(store, adapter),
        ASK_HOUSE,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )
    assert isinstance(outcome, Turn), "the turn proceeds without House Recall"
    assert _state(adapter)["house_recall"]["state"] == "unavailable"
    assert _state(adapter)["house_recall"]["detail"] == "RuntimeError"


def test_a_failing_store_degrades_house_recall_to_unavailable() -> None:
    """The function itself, against a broken engine: unavailable, never an exception."""
    from sqlalchemy import create_engine

    broken = create_engine("postgresql+psycopg://nobody@127.0.0.1:1/nowhere")
    outcome = house_recall_with_state(broken, query="what did we decide")
    assert outcome.state == "unavailable" and outcome.items == ()


def test_conflicting_excerpts_remain_distinct_with_chronology(store: Engine) -> None:
    alpha = scope_of(store, ALPHA_SLUG)
    earlier = seeded_conversation(
        store, alpha, "First view", (StoredRole.USER, "The lighthouse lens should be cobalt.")
    )
    later = seeded_conversation(
        store,
        ExplicitNoProject(),
        "Second view",
        (StoredRole.USER, "The lighthouse lens should be amber, not cobalt."),
    )
    adapter = answering()
    send(
        store,
        build_gateway(store, adapter),
        "What did we decide about the lighthouse lens in earlier conversations?",
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )
    excerpts = _excerpts(adapter)
    assert len(excerpts) == 2, "two statements, two excerpts — never merged"
    by_conv = {e["conversation_id"]: e for e in excerpts}
    assert str(earlier.id) in by_conv and str(later.id) in by_conv
    assert by_conv[str(earlier.id)]["created_at"] < by_conv[str(later.id)]["created_at"]
    assert by_conv[str(earlier.id)]["source_scope"] == "project: Project Alpha"
    assert by_conv[str(later.id)]["source_scope"] == "unassigned"
    note = str(_envelope(adapter)["note"])  # type: ignore[index]
    assert "conflict with each other" in note and "provenance and chronology" in note


def test_restricted_material_reached_only_through_house_recall_blocks_the_call(
    store: Engine,
) -> None:
    beta = scope_of(store, BETA_SLUG)
    secret = (
        fake_credential("-----BE", "GIN RSA PRIVATE KE", "Y-----")
        + "\nMIIEowIBAAKCAQEA\n"
        + fake_credential("-----E", "ND RSA PRIVATE KE", "Y-----")
    )
    seeded_conversation(
        store,
        beta,
        "Careless Beta conversation",
        (StoredRole.USER, f"The lighthouse deploy key is {secret}"),
    )
    adapter = answering()
    with pytest.raises(RestrictedContentRefusedError):
        send(
            store,
            build_gateway(store, adapter),
            "What did we decide about the lighthouse deploy key in earlier conversations?",
            catalogue=catalogue(store),
            signals=ProjectSignals(explicit_selection="Project Alpha"),
        )
    assert adapter.calls == 0


def test_the_budget_reservation_includes_house_recall_material(store: Engine) -> None:
    """The ceiling is computed from the assembled payload, house excerpts included."""
    from test_conversation_memory import _only_reservation

    beta = scope_of(store, BETA_SLUG)
    bulky = "The lighthouse lens colour was discussed at length. " * 400
    seeded_conversation(store, beta, "A long Beta conversation", (StoredRole.USER, bulky))
    question = "What did we decide about the lighthouse lens colour in earlier conversations?"

    with_house = FakeLedger()
    adapter = answering()
    gateway = build_gateway(store, adapter)
    gateway._ledger = with_house  # type: ignore[attr-defined]
    send(
        store,
        gateway,
        question,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )
    assert any(e["retrieval_path"] == "house_recall" for e in _excerpts(adapter))

    without = FakeLedger()
    adapter2 = answering()
    gateway2 = build_gateway(store, adapter2)
    gateway2._ledger = without  # type: ignore[attr-defined]
    send(
        store,
        gateway2,
        ASK_PLAIN,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )
    assert _envelope(adapter2) is None

    assert _only_reservation(with_house) > _only_reservation(without), (
        "the reservation must grow with the house-recalled material"
    )
