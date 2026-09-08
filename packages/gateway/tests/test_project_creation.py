"""Creating a project by name — ruled 7 September 2026.

The smallest proper user-facing path: a name in, an active project out, with a
mechanically derived slug. Two refusals, both in words: nothing to identify
the project by, and a name or slug an existing project already holds —
archived or not, because an archived project still resolves by name and a
second one would manufacture the ambiguity WP-0.6 exists to surface.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text
from test_persona import clean_personas  # noqa: F401 - fixture reused

from val_gateway.projects import (
    ProjectCreationRefused,
    create_project,
    load_catalogue,
    project_listing,
    slug_for,
)


@pytest.fixture
def store(clean_personas: Engine) -> Engine:  # noqa: F811 - pytest fixture injection
    return clean_personas


def test_the_slug_is_derived_mechanically() -> None:
    assert slug_for("Tony Spumoni") == "tony-spumoni"
    assert slug_for("  Winter   Light: The Short!  ") == "winter-light-the-short"
    assert slug_for("Épisode 2") == "pisode-2", "only ASCII letters and digits form the slug"
    assert slug_for("***") == ""


def test_a_named_project_is_created_active_and_resolves(store: Engine) -> None:
    created = create_project(store, "Tony Spumoni")

    assert created.name == "Tony Spumoni"
    assert created.slug == "tony-spumoni"
    assert created.status == "active"
    assert created.archived_at is None
    assert [p.slug for p in project_listing(store)] == ["tony-spumoni"]
    # The catalogue the resolver is handed sees it at once — no cache, no restart.
    assert load_catalogue(store).by_id(created.id) is not None
    with store.connect() as connection:
        description = connection.execute(
            text("select description from projects where id = :i"), {"i": created.id}
        ).scalar_one()
    assert description == ""


def test_surrounding_and_repeated_whitespace_is_normalised_in_the_name(store: Engine) -> None:
    created = create_project(store, "  Tony   Spumoni ")
    assert created.name == "Tony Spumoni"


@pytest.mark.parametrize("name", ["", "   ", "***", "—"])
def test_a_name_with_nothing_to_identify_it_by_is_refused(store: Engine, name: str) -> None:
    with pytest.raises(ProjectCreationRefused, match="at least one letter or digit"):
        create_project(store, name)
    assert project_listing(store) == ()


def test_a_name_already_held_is_refused_in_words(store: Engine) -> None:
    create_project(store, "Tony Spumoni")
    with pytest.raises(ProjectCreationRefused, match="already exists"):
        create_project(store, "tony spumoni")  # same name, different case
    with pytest.raises(ProjectCreationRefused, match="already exists"):
        create_project(store, "Tony  Spumoni!")  # same slug
    assert len(project_listing(store)) == 1


def test_an_archived_project_still_holds_its_name(store: Engine) -> None:
    created = create_project(store, "Tony Spumoni")
    with store.begin() as connection:
        connection.execute(
            text("update projects set archived_at = now() where id = :i"), {"i": created.id}
        )
    with pytest.raises(ProjectCreationRefused, match="archived"):
        create_project(store, "Tony Spumoni")
