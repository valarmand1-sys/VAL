"""A light answer prepared before the turn is confirmed — owner order, 26 September 2026 (§6).

The preparation is private until Core binds it: the same persona, the same assembled
messages, the same light task. Words he changed, a turn that turns out not to be
light, a resumed sentence — each discards the preparation and says so on the record.
These tests hold the binding, the record, and the session's scheduling, with the
light candidate promoted for this process and restored afterwards.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

import threading
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from test_deliberation_machinery import ScriptedAdapter, build_gateway, clean_personas, ok, store
from test_light_route import light_candidate
from test_voice_input import MARKER, ScriptedRecognizer, a_conversation, final, started

from val_gateway.deliberate import prepare_light_answer
from val_gateway.deliberate import send as deliberated_send
from val_gateway.projects import load_catalogue
from val_gateway.seal import SealRoute
from val_gateway.speculation import PreparedAnswer
from val_gateway.startup import LIGHT_CANDIDATE_SLUG
from val_gateway.voice import VoiceSession
from val_policy.light_conversation import FastRoute
from val_policy.project_resolution import ProjectSignals

BOTH = FastRoute(frozenset({1, 2}))


def prepare(
    store: Engine, adapter: ScriptedAdapter, text_: str, conversation: UUID | None
) -> PreparedAnswer | None:
    return prepare_light_answer(
        store,
        build_gateway(store, adapter),
        text_,
        catalogue=load_catalogue(store),
        signals=ProjectSignals(explicit_no_project=True) if conversation is None else None,
        conversation_id=conversation,
        fast_route=BOTH,
    )


def spoken(
    store: Engine,
    adapter: ScriptedAdapter,
    text_: str,
    conversation: UUID | None,
    prepared: PreparedAnswer | None,
) -> object:
    return deliberated_send(
        store,
        build_gateway(store, adapter),
        text_,
        catalogue=load_catalogue(store),
        signals=ProjectSignals(explicit_no_project=True) if conversation is None else None,
        conversation_id=conversation,
        spoken=True,
        seal_route=SealRoute.UTTERANCE_FINALIZED,
        fast_route=BOTH,
        prepared=prepared,
    )


def rows(store: Engine, query: str, **params: object) -> list[tuple]:
    with store.connect() as connection:
        return [tuple(row) for row in connection.execute(text(query), params).all()]


def test_a_prepared_answer_is_bound_to_the_turn_and_becomes_her_answer(
    store: Engine, light_candidate: None
) -> None:
    adapter = ScriptedAdapter([ok("Good evening, my lord. The lamps are lit.")])
    conversation = a_conversation(store)
    prepared = prepare(store, adapter, "Good evening, Val.", conversation)
    assert prepared is not None and prepared.tier == 1
    assert prepared.response.slug == LIGHT_CANDIDATE_SLUG
    # Nothing of his, and nothing of hers, is in the conversation yet.
    assert (
        rows(store, "select count(*) from messages where conversation_id = :c", c=conversation)[0][
            0
        ]
        == 0
    )

    outcome = spoken(store, adapter, "Good evening, Val.", conversation, prepared)
    assert outcome.turn.val_message.content == "Good evening, my lord. The lamps are lit."  # type: ignore[attr-defined]
    # One model call in all: the speculative one. No second answer was generated.
    assert [call.config_slug for call in adapter.sent] == [LIGHT_CANDIDATE_SLUG]
    tasks = rows(store, "select task_type::text, conversation_id from model_calls order by id")
    assert [task for task, _ in tasks] == ["speculative_light_conversation"]
    assert tasks[0][1] is None, "the speculative call is attached to no conversation"
    record = rows(
        store,
        "select outcome, user_message_id, answer_message_id, model_call_id "
        "from speculative_preparations",
    )
    assert len(record) == 1 and record[0][0] == "accepted"
    assert record[0][1] == outcome.turn.user_message.id  # type: ignore[attr-defined]
    assert record[0][2] == outcome.turn.val_message.id  # type: ignore[attr-defined]
    assert record[0][3] is not None


def test_changed_words_discard_the_preparation_and_the_turn_answers_afresh(
    store: Engine, light_candidate: None
) -> None:
    adapter = ScriptedAdapter([ok("Good evening, my lord."), ok("Good night, my lord.")])
    conversation = a_conversation(store)
    prepared = prepare(store, adapter, "Good evening, Val.", conversation)
    outcome = spoken(store, adapter, "Good night, Val.", conversation, prepared)
    assert outcome.turn.val_message.content == "Good night, my lord."  # type: ignore[attr-defined]
    assert [call.config_slug for call in adapter.sent] == [LIGHT_CANDIDATE_SLUG] * 2
    outcomes = rows(store, "select outcome from speculative_preparations")
    assert outcomes == [("discarded_mismatch",)]


def test_a_turn_that_is_not_light_discards_the_preparation(
    store: Engine, light_candidate: None
) -> None:
    adapter = ScriptedAdapter([ok("Good evening, my lord."), ok("Not yet, my lord.")])
    conversation = a_conversation(store)
    prepared = prepare(store, adapter, "Good evening, Val.", conversation)
    spoken(
        store, adapter, "Good evening, Val. Did you finish the invitation?", conversation, prepared
    )
    assert rows(store, "select outcome from speculative_preparations") == [("discarded_not_light",)]
    assert adapter.sent[1].config_slug != LIGHT_CANDIDATE_SLUG


def test_words_that_are_not_light_prepare_nothing(store: Engine, light_candidate: None) -> None:
    adapter = ScriptedAdapter([])
    conversation = a_conversation(store)
    assert prepare(store, adapter, "Did you finish the invitation?", conversation) is None
    assert adapter.sent == []
    assert rows(store, "select count(*) from speculative_preparations")[0][0] == 0


def test_a_greeting_that_would_open_a_conversation_is_prepared_and_bound(
    store: Engine, light_candidate: None
) -> None:
    adapter = ScriptedAdapter([ok("Good evening, my lord.")])
    prepared = prepare(store, adapter, "Good evening, Val.", None)
    assert prepared is not None and prepared.conversation_id is None
    outcome = spoken(store, adapter, "Good evening, Val.", None, prepared)
    assert outcome.turn.val_message.content == "Good evening, my lord."  # type: ignore[attr-defined]
    assert rows(store, "select outcome from speculative_preparations") == [("accepted",)]


def test_the_session_prepares_during_the_window_and_hands_the_result_to_core(
    store: Engine,
) -> None:
    recognizer = ScriptedRecognizer(batches=[[started(1), final(1, "Good evening, Val.")]])
    received: list[object] = []
    prepared_marker = object()

    def submit(content: str, existing: UUID | None, **kwargs: object) -> object:
        received.append(kwargs.get("prepared"))
        raise RuntimeError("stop here: the submission itself is not under test")

    started_at = threading.Event()

    def prepare_(content: str, conversation: UUID | None) -> object:
        started_at.set()
        return prepared_marker

    clock = {"now": 1000.0}
    session = VoiceSession(
        store,
        recognizer,
        submit=submit,  # type: ignore[arg-type]
        conversation_id=a_conversation(store),
        clock=lambda: clock["now"],
        prepare=prepare_,
    )
    session.start()
    session.feed(MARKER)
    assert started_at.wait(5), "preparation began when the utterance settled"
    clock["now"] += 5.0
    session.advance()
    session.await_turn(timeout=10)
    assert received == [prepared_marker], "the preparation reached Core with the turn"
    assert session.speculations and session.speculations[0]["prepared"] is True
    session.close()


def test_adaptive_grace_submits_a_finished_sentence_sooner_and_a_leading_one_later(
    store: Engine,
) -> None:
    submitted: list[float] = []
    clock = {"now": 1000.0}

    def submit(content: str, existing: UUID | None, **kwargs: object) -> object:
        submitted.append(clock["now"])
        raise RuntimeError("stop here")

    for text_, expected in (("Good evening, Val.", 0.44), ("Good evening, Val, and", 1.65)):
        submitted.clear()
        clock["now"] = 1000.0
        recognizer = ScriptedRecognizer(batches=[[started(1), final(1, text_)]])
        session = VoiceSession(
            store,
            recognizer,
            submit=submit,  # type: ignore[arg-type]
            conversation_id=a_conversation(store),
            clock=lambda: clock["now"],
            adaptive_grace=True,
        )
        session.start()
        session.feed(MARKER)
        clock["now"] += expected - 0.05
        session.advance()
        assert submitted == [], f"{text_!r} not yet submitted at {expected - 0.05:.2f} s"
        clock["now"] += 0.1
        session.advance()
        session.await_turn(timeout=10)
        assert submitted, f"{text_!r} submitted once its window passed"
        session.close()
