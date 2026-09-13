"""Rename and archive — conversation management, Stage 1 (ruling, 12 September 2026).

Rename changes the mutable, presentation-class title and nothing else: every
evidence anchor is by id. Archive hides a conversation from the default listing
and nothing else: it still resumes, still scopes, still recalls, and its
evidence and costs are untouched. The existing archive tests
(`test_archive.py`) are unchanged; these add the writers the product lacked.
"""

from __future__ import annotations

from sqlalchemy import Engine, text
from test_service import ScriptedAdapter, classifier_says, client, ok


def plain(answer: str = "As you say, my lord.") -> list:
    return [classifier_says("not_consequential"), ok(answer)]


def _evidence(store: Engine, conversation_id: str) -> dict[str, object]:
    """Everything a conversation's evidence identity consists of, read by id."""
    with store.connect() as connection:
        return {
            "project_id": connection.execute(
                text("select project_id from conversations where id = :c"), {"c": conversation_id}
            ).scalar_one(),
            "messages": connection.execute(
                text(
                    "select id, role, content, sequence from messages "
                    "where conversation_id = :c order by sequence"
                ),
                {"c": conversation_id},
            ).all(),
            "calls": connection.execute(
                text(
                    "select id, message_id, project_id, cost from model_calls "
                    "where conversation_id = :c order by created_at, id"
                ),
                {"c": conversation_id},
            ).all(),
            "classifications": connection.execute(
                text(
                    "select id, message_id, verdict from classifications where conversation_id = :c"
                ),
                {"c": conversation_id},
            ).all(),
        }


def test_rename_changes_the_title_and_no_evidence_identity(store: Engine) -> None:
    api = client(store, ScriptedAdapter(plain()))
    turn = api.post("/turns", json={"content": "Where were we?", "project": "Project Alpha"}).json()
    conversation_id = turn["conversation"]["id"]
    before = _evidence(store, conversation_id)

    renamed = api.post(
        f"/conversations/{conversation_id}/title", json={"title": "  Harbour notes  "}
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Harbour notes"
    assert api.get(f"/conversations/{conversation_id}").json()["conversation"]["title"] == (
        "Harbour notes"
    )
    assert _evidence(store, conversation_id) == before


def test_an_empty_or_overlong_title_is_refused_in_words(store: Engine) -> None:
    api = client(store, ScriptedAdapter(plain()))
    turn = api.post("/turns", json={"content": "Begin.", "no_project": True}).json()
    conversation_id = turn["conversation"]["id"]
    title = turn["conversation"]["title"]

    empty = api.post(f"/conversations/{conversation_id}/title", json={"title": "   "})
    assert empty.status_code == 422
    assert "cannot be empty" in empty.json()["detail"]
    long = api.post(f"/conversations/{conversation_id}/title", json={"title": "x" * 201})
    assert long.status_code == 422
    assert "Nothing was shortened" in long.json()["detail"]
    assert api.get(f"/conversations/{conversation_id}").json()["conversation"]["title"] == title


def test_renaming_or_archiving_an_unknown_conversation_is_a_404(store: Engine) -> None:
    api = client(store, ScriptedAdapter([]))
    missing = "01a00000-0000-7000-8000-000000000000"
    assert api.post(f"/conversations/{missing}/title", json={"title": "x"}).status_code == 404
    assert api.post(f"/conversations/{missing}/archive").status_code == 404
    assert api.post(f"/conversations/{missing}/unarchive").status_code == 404


def test_archive_changes_the_listing_only_and_unarchive_recovers_it(store: Engine) -> None:
    api = client(store, ScriptedAdapter([*plain(), *plain("Still here, my lord.")]))
    turn = api.post("/turns", json={"content": "Survey notes.", "project": "Project Beta"}).json()
    conversation_id = turn["conversation"]["id"]
    before = _evidence(store, conversation_id)

    archived = api.post(f"/conversations/{conversation_id}/archive").json()
    assert archived["archived"] is True
    assert api.get("/conversations").json() == []
    recovered = api.get("/conversations", params={"archived": "true"}).json()
    assert [c["id"] for c in recovered] == [conversation_id]
    assert _evidence(store, conversation_id) == before, "archiving wrote nothing else"

    # Still resumes, in its own scope, while archived.
    resumed = api.post(
        "/turns", json={"content": "Continue.", "conversation_id": conversation_id}
    ).json()
    assert resumed["kind"] == "answered"
    assert resumed["conversation"]["project_id"] == str(before["project_id"])

    # Archiving twice keeps the first instant.
    with store.connect() as connection:
        first = connection.execute(
            text("select archived_at from conversations where id = :c"), {"c": conversation_id}
        ).scalar_one()
    api.post(f"/conversations/{conversation_id}/archive")
    with store.connect() as connection:
        again = connection.execute(
            text("select archived_at from conversations where id = :c"), {"c": conversation_id}
        ).scalar_one()
    assert again == first

    unarchived = api.post(f"/conversations/{conversation_id}/unarchive").json()
    assert unarchived["archived"] is False
    assert [c["id"] for c in api.get("/conversations").json()] == [conversation_id]
