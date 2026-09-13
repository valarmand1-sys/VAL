"""Remove and Reinstate through the service — Stage 3 (ruling, 12 September 2026)."""

from __future__ import annotations

from sqlalchemy import Engine, text
from test_service import ScriptedAdapter, classifier_says, client, ok


def plain(answer: str = "As you say, my lord.") -> list:
    return [classifier_says("not_consequential"), ok(answer)]


def test_remove_and_reinstate_through_the_routes(store: Engine) -> None:
    adapter = ScriptedAdapter([*plain(), *plain("Continuing, my lord.")])
    api = client(store, adapter)
    turn = api.post("/turns", json={"content": "Begin.", "project": "Project Alpha"}).json()
    conversation_id = turn["conversation"]["id"]

    removed = api.post(f"/conversations/{conversation_id}/remove", json={"note": "clutter"})
    assert removed.status_code == 200 and removed.json()["removed"] is True
    assert api.get("/conversations").json() == []
    listed = api.get("/conversations", params={"removed": "true"}).json()
    assert [c["id"] for c in listed] == [conversation_id] and listed[0]["removed"] is True
    assert api.get(f"/conversations/{conversation_id}").json()["conversation"]["removed"] is True

    again = api.post(f"/conversations/{conversation_id}/remove", json={})
    assert again.status_code == 409 and again.json()["detail"]["reason"] == "already_removed"

    calls = adapter.calls
    refused = api.post("/turns", json={"content": "Continue.", "conversation_id": conversation_id})
    assert refused.status_code == 409 and "reinstate" in refused.json()["detail"]
    with api.stream(
        "POST", "/turns/stream", json={"content": "Continue.", "conversation_id": conversation_id}
    ) as response:
        body = "".join(response.iter_text())
    assert "event: refused" in body and "reinstate" in body
    assert adapter.calls == calls
    with store.connect() as connection:
        count = connection.execute(
            text("select count(*) from messages where conversation_id = :c"),
            {"c": conversation_id},
        ).scalar_one()
    assert count == 2, "no message appended by a refused turn"

    reinstated = api.post(f"/conversations/{conversation_id}/reinstate", json={})
    assert reinstated.status_code == 200 and reinstated.json()["removed"] is False
    resumed = api.post("/turns", json={"content": "Continue.", "conversation_id": conversation_id})
    assert resumed.json()["kind"] == "answered"
    assert api.post(f"/conversations/{conversation_id}/reinstate", json={}).status_code == 409


def test_removing_an_unknown_conversation_is_a_404(store: Engine) -> None:
    api = client(store, ScriptedAdapter([]))
    missing = "01a00000-0000-7000-8000-000000000000"
    assert api.post(f"/conversations/{missing}/remove", json={}).status_code == 404
    assert api.post(f"/conversations/{missing}/reinstate", json={}).status_code == 404
