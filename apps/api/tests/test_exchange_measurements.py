"""Exchange identity and per-call measurement through the real turn path — 13 September 2026.

A consequential streamed turn makes four calls — classification, strip, blind
position, response. Each one's reservation names the exchange; each one's
`model_call_measurements` row names it too, says whether it streamed, when the
first generated text arrived, and how much text came back. Machinery rows on
`model_calls` still carry no conversation provenance. A disabled envelope
changes nothing; an enabled one that the first call would exceed ends the turn
unanswered without contacting the provider. Real PostgreSQL, scripted adapters.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from sqlalchemy import Engine, text
from test_service import (
    CLOSE_UP,
    MIXED,
    PREFERENCE,
    ScriptedAdapter,
    blind_says,
    classifier_says,
    client,
    ok,
    plain_script,
    reconciled,
    strip_separates,
)
from test_turn_stream import Streamed, StreamingScriptedAdapter, events_of

from val_domain.gateway import CacheTtl, Message, ModelConfig
from val_domain.provider import ProviderResult
from val_gateway.ledger import DatabaseLedger


def _measurements(engine: Engine) -> list[dict[str, object]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "select c.task_type::text as task_type, c.conversation_id as call_conversation, "
                "       c.message_id as call_message, c.tokens_out, m.* "
                "  from model_calls c join model_call_measurements m on m.model_call_id = c.id "
                " order by c.created_at"
            )
        ).mappings()
        return [dict(row) for row in rows]


def _reservation_exchanges(engine: Engine) -> list[tuple[str, object, object]]:
    with engine.connect() as connection:
        return [
            (row[0], row[1], row[2])
            for row in connection.execute(
                text(
                    "select task_type::text, exchange_conversation_id, exchange_message_id "
                    "from budget_reservations order by created_at"
                )
            ).all()
        ]


def _the_user_message(engine: Engine) -> tuple[object, object]:
    with engine.connect() as connection:
        row = connection.execute(
            text("select conversation_id, id from messages where role = 'user'")
        ).one()
    return row[0], row[1]


def test_every_call_of_a_consequential_exchange_names_it_and_is_measured(store: Engine) -> None:
    prose = "I hold: open on the close-up, my lord."
    response = reconciled(prose, "held")
    adapter = StreamingScriptedAdapter(
        [
            classifier_says("consequential"),
            strip_separates(),
            blind_says(CLOSE_UP),
            Streamed(deltas=[prose[:10], prose[10:], response.text[len(prose) :]], result=response),
        ]
    )
    api = client(store, adapter, ledger=DatabaseLedger(store))  # type: ignore[arg-type]
    events = events_of(api, {"content": MIXED, "project": "Project Alpha"})
    assert events[-1][0] == "settled" and events[-1][1]["kind"] == "answered"

    conversation_id, message_id = _the_user_message(store)
    reservations = _reservation_exchanges(store)
    assert [task for task, _, _ in reservations] == [
        "classification",
        "strip",
        "blind_position",
        "conversation",
    ]
    assert all((conv, msg) == (conversation_id, message_id) for _, conv, msg in reservations), (
        "every reservation of the exchange names it"
    )

    measured = _measurements(store)
    assert [row["task_type"] for row in measured] == [
        "classification",
        "strip",
        "blind_position",
        "conversation",
    ]
    for row in measured:
        assert (row["exchange_conversation_id"], row["exchange_message_id"]) == (
            conversation_id,
            message_id,
        )
        assert row["reasoning_present"] is None and row["reasoning_output_tokens"] is None, (
            "the scripted provider exposes no reasoning fact, so none is recorded"
        )
    machinery = measured[:3]
    assert all(row["call_conversation"] is None for row in machinery), (
        "machinery keeps its no-provenance model_calls row; the exchange lives elsewhere"
    )
    assert all(not row["streamed"] and row["first_text_ms"] is None for row in machinery)
    final = measured[3]
    assert final["streamed"] is True
    assert isinstance(final["first_text_ms"], int) and final["first_text_ms"] >= 0
    assert final["text_output_chars"] == len(response.text)
    assert final["call_message"] == message_id


def test_the_blind_call_still_receives_no_preference_under_the_bounded_instruction(
    store: Engine,
) -> None:
    from val_policy.deliberation import BLIND_POSITION_INSTRUCTION

    sent: list[str] = []

    class Capturing(ScriptedAdapter):
        def complete(
            self,
            config: ModelConfig,
            messages: tuple[Message, ...],
            system: str | None,
            max_output_tokens: int,
            output_schema: Mapping[str, object] | None = None,
            cache_ttl: CacheTtl | None = None,
        ) -> ProviderResult:
            sent.append("\n".join(m.content for m in messages))
            return super().complete(
                config, messages, system, max_output_tokens, output_schema, cache_ttl
            )

    adapter = Capturing(
        [
            classifier_says("consequential"),
            strip_separates(),
            blind_says(CLOSE_UP),
            reconciled("I hold, my lord.", "held"),
        ]
    )
    api = client(store, adapter)
    assert (
        api.post("/turns", json={"content": MIXED, "project": "Project Alpha"}).status_code == 200
    )
    blind = sent[2]
    assert blind.startswith(BLIND_POSITION_INSTRUCTION)
    assert PREFERENCE not in blind, "the preference never reaches the blind call"


def test_an_ordinary_exchange_is_measured_and_a_disabled_envelope_changes_nothing(
    store: Engine,
) -> None:
    adapter = ScriptedAdapter(plain_script("Two o'clock, my lord."))
    api = client(store, adapter, ledger=DatabaseLedger(store))  # type: ignore[arg-type]
    body = api.post(
        "/turns", json={"content": "What time is the screening?", "project": "Project Alpha"}
    ).json()
    assert body["kind"] == "answered"
    measured = _measurements(store)
    assert [row["task_type"] for row in measured] == ["classification", "conversation"]
    assert measured[1]["streamed"] is False and measured[1]["first_text_ms"] is None
    assert measured[1]["text_output_chars"] == len("Two o'clock, my lord.")


def test_a_classification_retry_stays_inside_the_exchange(store: Engine) -> None:
    adapter = ScriptedAdapter(
        [ok("not a verdict"), classifier_says("not_consequential"), ok("Two o'clock, my lord.")]
    )
    api = client(store, adapter, ledger=DatabaseLedger(store))  # type: ignore[arg-type]
    api.post("/turns", json={"content": "What time is the screening?", "project": "Project Alpha"})
    _, message_id = _the_user_message(store)
    reservations = _reservation_exchanges(store)
    assert [task for task, _, _ in reservations] == [
        "classification",
        "classification",
        "conversation",
    ]
    assert {msg for _, _, msg in reservations} == {message_id}


def test_an_enabled_envelope_the_first_call_exceeds_ends_the_turn_uncontacted(
    store: Engine,
) -> None:
    adapter = ScriptedAdapter([classifier_says("not_consequential"), ok("unused")])
    api = client(
        store,
        adapter,
        ledger=DatabaseLedger(store, exchange_envelope_usd=0.000001),  # type: ignore[arg-type]
    )
    body = api.post(
        "/turns", json={"content": "What time is the screening?", "project": "Project Alpha"}
    ).json()
    assert body["kind"] != "answered"
    assert "exchange_envelope_exceeded" in json.dumps(body)
    assert adapter.calls == 0, "the provider was never contacted"
    with store.connect() as connection:
        assert connection.execute(text("select count(*) from model_calls")).scalar_one() == 0
        assert (
            connection.execute(text("select count(*) from budget_reservations")).scalar_one() == 0
        )


def test_a_provider_failure_is_measured_as_unknown(store: Engine) -> None:
    from val_domain.gateway import GatewayError, GatewayErrorKind

    adapter = ScriptedAdapter(
        [
            classifier_says("not_consequential"),
            GatewayError(GatewayErrorKind.TIMEOUT, "slow"),
            GatewayError(GatewayErrorKind.TIMEOUT, "slow"),
            GatewayError(GatewayErrorKind.TIMEOUT, "slow"),
        ]
    )
    api = client(store, adapter, ledger=DatabaseLedger(store))  # type: ignore[arg-type]
    api.post("/turns", json={"content": "What time is the screening?", "project": "Project Alpha"})
    failed = [row for row in _measurements(store) if row["task_type"] == "conversation"]
    assert failed, "a failed conversation call is still measured"
    for row in failed:
        assert row["text_output_chars"] is None and row["first_text_ms"] is None
        assert row["exchange_message_id"] is not None
