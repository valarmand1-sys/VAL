"""The Core-owned Tier-1 request and its eligibility guard — owner order of 26 September 2026, §2.

What the Tier-1 route sends is Core's decision: the persona whole, the last exchange,
a reduced record state that says what it left out, Core's contract for the turn, his
words. What it never sends: recall, media state, older history. And who may take it:
only a turn whose authoritative state is settled — an open question of hers, a
corrected previous message, or an answer Core cannot read all fall back to MEDIUM.
"""

# ruff: noqa: F811, F401 - fixtures imported by name

from __future__ import annotations

import json
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from test_deliberation_machinery import ScriptedAdapter, build_gateway, clean_personas, ok, store
from test_light_route import light_candidate
from test_voice_input import a_conversation

from val_domain.egress import LocalOnlyReason, sealed
from val_domain.gateway import Message
from val_gateway import conversations
from val_gateway.deliberate import send as deliberated_send
from val_gateway.deliberate import tier1_eligibility
from val_gateway.projects import load_catalogue
from val_gateway.revisions import revise
from val_gateway.seal import SealRoute
from val_gateway.startup import LIGHT_CANDIDATE_SLUG
from val_gateway.tier1 import (
    TIER1_CONTRACT,
    TIER1_INSTRUCTION_MARKER,
    TIER1_STATE_MARKER,
    tier1_messages,
)
from val_policy.light_conversation import FastRoute

TIER_ONE = FastRoute(frozenset({1}))


def spoken(store: Engine, adapter: ScriptedAdapter, text_: str, conversation: UUID):  # noqa: ANN201
    return deliberated_send(
        store,
        build_gateway(store, adapter),
        text_,
        catalogue=load_catalogue(store),
        conversation_id=conversation,
        spoken=True,
        seal_route=SealRoute.UTTERANCE_FINALIZED,
        fast_route=TIER_ONE,
    )


def test_the_tier_1_request_keeps_the_last_exchange_and_states_what_it_left_out(
    store: Engine,
) -> None:
    adapter = ScriptedAdapter([ok("One."), ok("Two."), ok("Three.")])
    conversation = a_conversation(store)
    for words in ("First question.", "Second question.", "Third question."):
        spoken(store, adapter, words, conversation)
    thread = conversations.working(store, conversation)
    messages, projection = tier1_messages(
        thread,
        Message(role="user", content="Thank you, Val."),
        before_sequence=99,
        egress=sealed(LocalOnlyReason.CONVERSATION_SEALED),
    )
    assert [m.role for m in messages] == ["user", "assistant", "user", "user", "user"]
    assert messages[0].content == "Third question." and messages[1].content == "Three."
    assert messages[-1].content == "Thank you, Val."
    assert projection.retained_exchange and projection.prior_messages_in_record == 6
    state = json.loads(messages[2].content.split("\n", 1)[1])
    assert messages[2].content.startswith(TIER1_STATE_MARKER)
    record = state["record_state"]
    assert record["same_conversation_history"] == {
        "state": "available",
        "shown_in_this_request": "most_recent_exchange",
        "earlier_messages_in_record_not_shown": 4,
    }
    assert record["retrieved_excerpts"]["state"] == "not_run"
    assert record["house_recall"]["state"] == "not_run"
    assert record["external_egress"]["reasons"] == ["conversation_sealed"]
    assert "visual_input" not in record and "audio_input" not in record
    instruction = json.loads(messages[3].content.split("\n", 1)[1])
    assert messages[3].content.startswith(TIER1_INSTRUCTION_MARKER)
    assert instruction["authority"] == "val_core"
    assert instruction["contract"] == list(TIER1_CONTRACT)


def test_a_first_greeting_carries_no_exchange_and_says_so(store: Engine) -> None:
    conversation = a_conversation(store)
    thread = conversations.working(store, conversation)
    messages, projection = tier1_messages(
        thread,
        Message(role="user", content="Good evening, Val."),
        before_sequence=1,
        egress=sealed(LocalOnlyReason.CONVERSATION_SEALED),
    )
    assert [m.role for m in messages] == ["user", "user", "user"]
    assert not projection.retained_exchange
    record = json.loads(messages[0].content.split("\n", 1)[1])["record_state"]
    assert record["same_conversation_history"]["state"] == "zero"
    assert record["same_conversation_history"]["shown_in_this_request"] == "none"


def test_thanks_after_an_open_question_stays_on_medium(
    store: Engine, light_candidate: None
) -> None:
    adapter = ScriptedAdapter([ok("Shall I send it tonight, my lord?"), ok("As you wish.")])
    conversation = a_conversation(store)
    spoken(store, adapter, "Draft the reply to the reader.", conversation)
    spoken(store, adapter, "Thank you, Val.", conversation)
    assert all(call.config_slug != LIGHT_CANDIDATE_SLUG for call in adapter.sent)
    thread = conversations.working(store, conversation)
    verdict = tier1_eligibility(thread, "Thank you, Val.", 3, TIER_ONE)
    assert verdict.tier is None and "open" in verdict.reason


def test_a_turn_after_a_corrected_message_stays_on_medium(store: Engine) -> None:
    adapter = ScriptedAdapter([ok("Noted, my lord.")])
    conversation = a_conversation(store)
    outcome = spoken(store, adapter, "The venue is the hall.", conversation)
    revise(
        store,
        outcome.turn.user_message.id,  # type: ignore[attr-defined]
        "The venue is the chapel.",
        note="corrected",
    )
    thread = conversations.working(store, conversation)
    verdict = tier1_eligibility(thread, "Thank you, Val.", 3, TIER_ONE)
    assert verdict.tier is None and "correction-sensitive" in verdict.reason


def test_earlier_turns_with_no_readable_answer_are_uncertain_state(store: Engine) -> None:
    conversation = a_conversation(store)
    with store.begin() as connection:
        connection.execute(
            text(
                "insert into messages (conversation_id, role, content, sequence) "
                "values (:c, 'user', 'A question she never answered.', 1)"
            ),
            {"c": conversation},
        )
    thread = conversations.working(store, conversation)
    verdict = tier1_eligibility(thread, "Good evening, Val.", 2, TIER_ONE)
    assert verdict.tier is None and "uncertain" in verdict.reason


def test_a_tier_1_answer_that_hits_its_cap_is_not_delivered_and_the_partner_answers(
    store: Engine, light_candidate: None
) -> None:
    from val_domain.gateway import TerminalState
    from val_domain.provider import ProviderResult

    adapter = ScriptedAdapter(
        [
            ProviderResult("Good evening, my lord, and", TerminalState.TRUNCATED, 5000, 1024, "r"),
            ok("Good evening, my lord."),
        ]
    )
    conversation = a_conversation(store)
    delivered: list[str] = []
    outcome = deliberated_send(
        store,
        build_gateway(store, adapter),
        "Good evening, Val.",
        catalogue=load_catalogue(store),
        conversation_id=conversation,
        spoken=True,
        seal_route=SealRoute.UTTERANCE_FINALIZED,
        fast_route=TIER_ONE,
        on_delta=delivered.append,
    )
    assert outcome.turn.val_message.content == "Good evening, my lord."  # type: ignore[attr-defined]
    # The scripted adapter does not stream, so the partner's text arrives with the
    # settled turn; what matters here is that no fragment of the capped answer did.
    assert "and" not in "".join(delivered), "nothing of the capped answer reached him"
    assert adapter.sent[0].config_slug == LIGHT_CANDIDATE_SLUG
    assert adapter.sent[1].config_slug != LIGHT_CANDIDATE_SLUG
    with store.connect() as connection:
        roles = (
            connection.execute(
                text(
                    "select role::text from messages where conversation_id = :c order by sequence"
                ),
                {"c": conversation},
            )
            .scalars()
            .all()
        )
    assert roles == ["user", "val"], "exactly one answer"
