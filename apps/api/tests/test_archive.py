"""`archived_at` is presentation scoping and nothing else — §2.1 amendment.

Two halves, both pinned here: archived rows leave the default listings (the
whole of what archiving does), and everything else is archive-blind — an
archived project still resolves by name and an archived conversation still
resumes, because a display flag acquiring authority over scope or history
would be presentation deciding what is real.
"""

from __future__ import annotations

import json

from sqlalchemy import Engine, text
from test_service import ScriptedAdapter, classifier_says, client, ok


def plain(answer: str = "As you say, my lord.") -> list:
    return [classifier_says("not_consequential"), ok(answer)]


def _archive_conversation(store: Engine, conversation_id: str) -> None:
    with store.begin() as connection:
        connection.execute(
            text("update conversations set archived_at = now() where id = :i"),
            {"i": conversation_id},
        )


def _archive_project_named(store: Engine, name: str) -> None:
    with store.begin() as connection:
        connection.execute(
            text("update projects set archived_at = now() where name = :n"), {"n": name}
        )


def test_an_archived_conversation_leaves_the_default_listing_only(store: Engine) -> None:
    api = client(store, ScriptedAdapter(plain()))
    turn = api.post("/turns", json={"content": "Where were we?", "project": "Project Alpha"}).json()
    conversation_id = turn["conversation"]["id"]

    assert [c["id"] for c in api.get("/conversations").json()] == [conversation_id]

    _archive_conversation(store, conversation_id)

    assert api.get("/conversations").json() == [], "archived rows leave the default listing"
    included = api.get("/conversations", params={"archived": "true"}).json()
    assert [c["id"] for c in included] == [conversation_id]
    assert included[0]["archived"] is True


def test_an_archived_project_leaves_the_default_listing_only(store: Engine) -> None:
    api = client(store, ScriptedAdapter([]))
    _archive_project_named(store, "Project Beta")

    names = [p["name"] for p in api.get("/projects").json()]
    assert names == ["Project Alpha"]

    included = api.get("/projects", params={"archived": "true"}).json()
    assert [p["name"] for p in included] == ["Project Alpha", "Project Beta"]
    assert {p["name"]: p["archived"] for p in included} == {
        "Project Alpha": False,
        "Project Beta": True,
    }


def test_everything_but_the_listings_is_archive_blind(store: Engine) -> None:
    """The flag has no authority: scope resolution and resumption unchanged."""
    api = client(store, ScriptedAdapter([*plain(), *plain("Still here, my lord.")]))
    turn = api.post(
        "/turns", json={"content": "Begin the survey notes.", "project": "Project Beta"}
    ).json()
    assert turn["kind"] == "answered"
    conversation_id = turn["conversation"]["id"]

    _archive_project_named(store, "Project Beta")
    _archive_conversation(store, conversation_id)

    # The archived conversation still resumes, and its archived project still
    # scopes it — a real exchange, recorded exactly as any other.
    resumed = api.post(
        "/turns", json={"content": "And the next entry.", "conversation_id": conversation_id}
    ).json()
    assert resumed["kind"] == "answered", json.dumps(resumed)
    assert resumed["conversation"]["id"] == conversation_id

    detail = api.get(f"/conversations/{conversation_id}").json()
    assert len(detail["messages"]) == 4
    assert detail["conversation"]["archived"] is True
