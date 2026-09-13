"""Moving a conversation through the service — Stage 4 (ruling, 12 September 2026).

After a move, the next turn's classification, blind position and every call are
attributed to the destination; the earlier turn's evidence keeps its origin; the
conversation view carries both scopes; the listing follows the current one.
"""

from __future__ import annotations

from sqlalchemy import Engine, text
from test_service import ScriptedAdapter, classifier_says, client, deliberated_script, ok


def plain(answer: str = "As you say, my lord.") -> list:
    return [classifier_says("not_consequential"), ok(answer)]


def _project_id(store: Engine, name: str) -> str:
    with store.connect() as connection:
        return str(
            connection.execute(
                text("select id from projects where name = :n"), {"n": name}
            ).scalar_one()
        )


_SCOPES = {
    "classifications": text(
        "select t.project_id from classifications t join messages m on m.id = t.message_id "
        "where t.conversation_id = :c order by m.sequence, t.created_at"
    ),
    "blind_positions": text(
        "select t.project_id from blind_positions t join messages m on m.id = t.message_id "
        "where t.conversation_id = :c order by m.sequence, t.created_at"
    ),
}


def _scopes(store: Engine, table: str, conversation_id: str) -> list[str | None]:
    with store.connect() as connection:
        return [
            None if row[0] is None else str(row[0])
            for row in connection.execute(_SCOPES[table], {"c": conversation_id})
        ]


def test_after_a_move_the_next_turns_evidence_belongs_to_the_destination(store: Engine) -> None:
    alpha = _project_id(store, "Project Alpha")
    beta = _project_id(store, "Project Beta")
    api = client(store, ScriptedAdapter([*plain(), *deliberated_script()]))
    turn = api.post(
        "/turns", json={"content": "Begin the notes.", "project": "Project Alpha"}
    ).json()
    conversation_id = turn["conversation"]["id"]

    moved = api.post(f"/conversations/{conversation_id}/scope", json={"project_id": beta})
    assert moved.status_code == 200
    assert moved.json()["project_id"] == beta and moved.json()["origin_project_id"] == alpha

    second = api.post(
        "/turns",
        json={
            "content": "I think we should open on the wide shot. Which opening do we commit to?",
            "conversation_id": conversation_id,
        },
    ).json()
    assert second["kind"] == "answered"
    assert second["conversation"]["project_id"] == beta

    assert _scopes(store, "classifications", conversation_id) == [alpha, beta]
    assert _scopes(store, "blind_positions", conversation_id) == [beta]
    # Every call — classification, strip, blind, response, with or without a
    # message anchor — made before the move is Alpha's; every one after, Beta's.
    with store.connect() as connection:
        moved_at = connection.execute(
            text(
                "select created_at from conversation_scope_transitions where conversation_id = :c"
            ),
            {"c": conversation_id},
        ).scalar_one()
        calls = connection.execute(
            text("select created_at, project_id from model_calls order by created_at")
        ).all()
    assert {str(p) for at, p in calls if at < moved_at} == {alpha}
    assert {str(p) for at, p in calls if at > moved_at} == {beta}
    assert len([1 for at, _ in calls if at > moved_at]) == 4
    with store.connect() as connection:
        origin = connection.execute(
            text("select project_id from conversations where id = :c"), {"c": conversation_id}
        ).scalar_one()
    assert str(origin) == alpha

    detail = api.get(f"/conversations/{conversation_id}").json()
    (transition,) = detail["scope_transitions"]
    assert (transition["from_project_id"], transition["to_project_id"]) == (alpha, beta)
    assert transition["after_sequence"] == 2
    assert [c["id"] for c in api.get("/conversations", params={"project_id": beta}).json()] == [
        conversation_id
    ]
    assert api.get("/conversations", params={"project_id": alpha}).json() == []


def test_moving_out_of_every_project_and_the_refusals(store: Engine) -> None:
    beta = _project_id(store, "Project Beta")
    api = client(store, ScriptedAdapter(plain()))
    turn = api.post("/turns", json={"content": "Begin.", "project": "Project Beta"}).json()
    conversation_id = turn["conversation"]["id"]
    route = f"/conversations/{conversation_id}/scope"

    assert api.post(route, json={}).status_code == 422
    assert api.post(route, json={"project_id": beta, "no_project": True}).status_code == 422
    unchanged = api.post(route, json={"project_id": beta})
    assert unchanged.status_code == 409 and unchanged.json()["detail"]["reason"] == "unchanged"
    unknown = api.post(route, json={"project_id": "01a00000-0000-7000-8000-000000000000"})
    assert unknown.status_code == 404

    out = api.post(route, json={"no_project": True})
    assert out.status_code == 200
    assert out.json()["project_id"] is None and out.json()["origin_project_id"] == beta
    listed = api.get("/conversations", params={"scope": "none"}).json()
    assert [c["id"] for c in listed] == [conversation_id]
    missing = api.post(
        "/conversations/01a00000-0000-7000-8000-000000000000/scope", json={"no_project": True}
    )
    assert missing.status_code == 404
