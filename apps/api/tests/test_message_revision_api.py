"""Message revision and retraction through the service — Stage 2 (ruling, 12 September 2026).

The routes are thin projections over `val_gateway.revisions`. Proved here: the
detail shows the wording in force with the original distinguishable and Val's
answer attached to what she answered; a message behind an enforced blind
position refuses revision in words and permits retraction, leaving every
evidence row and cost in place; a Val message is refused; refusals carry the
writer's reason; and no route makes a provider call.
"""

from __future__ import annotations

from sqlalchemy import Engine, text
from test_service import (
    ScriptedAdapter,
    classifier_says,
    client,
    deliberated_script,
    ok,
)


def plain(answer: str = "The wide shot, my lord.") -> list:
    return [classifier_says("not_consequential"), ok(answer)]


def _evidence(store: Engine, conversation_id: str) -> dict[str, object]:
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
                "blind_positions",
                "deliberations",
                "execution_events",
            )
        }


def test_a_correction_is_shown_in_place_with_the_original_and_the_answer_marked(
    store: Engine,
) -> None:
    adapter = ScriptedAdapter(plain())
    api = client(store, adapter)
    turn = api.post("/turns", json={"content": "Open on the wide shot?", "no_project": True}).json()
    conversation_id = turn["conversation"]["id"]
    user_id = turn["user_message"]["id"]
    calls_before = adapter.calls
    before = _evidence(store, conversation_id)

    response = api.post(f"/messages/{user_id}/revisions", json={"content": "Open on the close-up?"})
    assert response.status_code == 201
    assert response.json()["kind"] == "revision" and response.json()["note"] is None
    assert adapter.calls == calls_before, "an edit makes no provider call"
    assert _evidence(store, conversation_id) == before, "no evidence row moved"

    detail = api.get(f"/conversations/{conversation_id}").json()
    user, val = detail["messages"]
    assert user["content"] == "Open on the close-up?"
    assert user["original_content"] == "Open on the wide shot?"
    assert user["state"] == "corrected"
    assert [r["kind"] for r in user["revisions"]] == ["revision"]
    assert user["revision_refusal"] is None
    assert val["content"] == "The wide shot, my lord."
    assert val["answered_state"] == "corrected"


def test_a_retraction_is_marked_and_destroys_nothing(store: Engine) -> None:
    api = client(store, ScriptedAdapter(plain()))
    turn = api.post("/turns", json={"content": "Open on the wide shot?", "no_project": True}).json()
    conversation_id = turn["conversation"]["id"]
    before = _evidence(store, conversation_id)

    response = api.post(f"/messages/{turn['user_message']['id']}/retraction", json={})
    assert response.status_code == 201
    assert response.json()["kind"] == "retraction"
    assert _evidence(store, conversation_id) == before

    user, val = api.get(f"/conversations/{conversation_id}").json()["messages"]
    assert user["state"] == "withdrawn" and user["content"] == "Open on the wide shot?"
    assert val["answered_state"] == "withdrawn"

    again = api.post(f"/messages/{turn['user_message']['id']}/retraction", json={})
    assert again.status_code == 409
    assert again.json()["detail"]["reason"] == "already_withdrawn"


def test_an_enforced_blind_position_refuses_revision_and_permits_retraction(store: Engine) -> None:
    api = client(store, ScriptedAdapter(deliberated_script()))
    turn = api.post(
        "/turns",
        json={
            "content": "I think we should open on the wide shot. Which opening do we commit to?",
            "project": "Project Alpha",
        },
    ).json()
    assert turn["kind"] == "answered"
    assert turn["glimpse"]["blind"]["ordering"] == "enforced"
    conversation_id = turn["conversation"]["id"]
    user_id = turn["user_message"]["id"]
    before = _evidence(store, conversation_id)

    detail = api.get(f"/conversations/{conversation_id}").json()
    assert "recorded decision exchange" in detail["messages"][0]["revision_refusal"]

    refused = api.post(f"/messages/{user_id}/revisions", json={"content": "Open wide."})
    assert refused.status_code == 409
    assert refused.json()["detail"]["reason"] == "deliberated"
    assert "cannot be rewritten" in refused.json()["detail"]["message"]

    withdrawn = api.post(f"/messages/{user_id}/retraction", json={"note": "sent too early"})
    assert withdrawn.status_code == 201
    assert withdrawn.json()["note"] == "sent too early"
    assert _evidence(store, conversation_id) == before, "the decision exchange stands whole"
    detail = api.get(f"/conversations/{conversation_id}").json()
    assert detail["messages"][0]["state"] == "withdrawn"
    assert len(detail["blind_positions"]) == 1 and len(detail["classifications"]) == 1


def test_refusals_carry_the_writers_reason_and_status(store: Engine) -> None:
    api = client(store, ScriptedAdapter(plain()))
    turn = api.post("/turns", json={"content": "Open on the wide shot?", "no_project": True}).json()
    val_id = turn["val_message"]["id"]
    user_id = turn["user_message"]["id"]

    val = api.post(f"/messages/{val_id}/revisions", json={"content": "Something else."})
    assert val.status_code == 409
    assert val.json()["detail"]["reason"] == "not_authored_by_lord_armand"
    assert api.post(f"/messages/{val_id}/retraction", json={}).status_code == 409

    empty = api.post(f"/messages/{user_id}/revisions", json={"content": "  "})
    assert empty.status_code == 422
    unchanged = api.post(
        f"/messages/{user_id}/revisions", json={"content": "Open on the wide shot?"}
    )
    assert unchanged.status_code == 409 and unchanged.json()["detail"]["reason"] == "unchanged"
    missing = api.post(
        "/messages/01a00000-0000-7000-8000-000000000000/revisions", json={"content": "x"}
    )
    assert missing.status_code == 404
    with store.connect() as connection:
        assert connection.execute(text("select count(*) from message_revisions")).scalar_one() == 0
