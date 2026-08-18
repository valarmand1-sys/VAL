"""WP-0.6 — attribution reaches the store correctly, and never crosses projects.

Against a real PostgreSQL, because what WP-0.6 finally promises is a property of
what is written: `model_calls.project_id` equal to the deterministically resolved
project, NULL exactly when someone decided there was none, and **nothing at all**
when scope was never settled.

The fixture projects are deliberately confusable. Two named `Winter Light` with
different slugs — legal here, since only `slug` is unique — because a suite whose
projects are "A" and "B" proves nothing about the case that bites.
"""

from uuid import UUID, uuid4

import pytest
from gateway_fakes import FakeLedger, StubAdapter
from sqlalchemy import Engine, text
from test_persona import REPO_ROOT, clean_personas  # noqa: F401 - fixture reused

from val_domain.gateway import Message
from val_domain.project import (
    AmbiguityReason,
    AmbiguousProject,
    ExplicitNoProject,
    ProjectScope,
    ResolvedProject,
    attribution_of,
    is_settled,
)
from val_gateway.exchange import (
    ClarificationNeeded,
    RestrictedContentRefusedError,
    exchange,
    resolve_scope,
)
from val_gateway.gateway import Gateway
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader, seed
from val_gateway.projects import ProjectSession, load_catalogue, project_exists
from val_policy.project_resolution import ProjectSignals
from val_providers.base import ProviderResult

ALPHA_SLUG, BETA_SLUG = "project-alpha", "project-beta"


@pytest.fixture
def store(clean_personas: Engine) -> Engine:  # noqa: F811 - pytest fixture injection
    """A migrated scratch database with a seeded persona and four projects."""
    seed(clean_personas, REPO_ROOT)
    with clean_personas.begin() as connection:
        for name, slug, status in (
            ("Project Alpha", ALPHA_SLUG, "active"),
            ("Project Beta", BETA_SLUG, "active"),
            ("Winter Light", "winter-light-series", "active"),
            ("Winter Light", "winter-light-short", "archived"),
        ):
            connection.execute(
                text(
                    "insert into projects (name, slug, description, status) "
                    "values (:name, :slug, '', :status)"
                ),
                {"name": name, "slug": slug, "status": status},
            )
    return clean_personas


def project_id(engine: Engine, slug: str) -> UUID:
    with engine.connect() as connection:
        found: UUID = connection.execute(
            text("select id from projects where slug = :slug"), {"slug": slug}
        ).scalar_one()
    return found


def build_gateway(engine: Engine, adapter: StubAdapter) -> Gateway:
    return Gateway(
        adapters={"anthropic": adapter, "openai": adapter},
        recorder=lambda record: record_call(engine, record),
        ledger=FakeLedger(),
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(engine),
    )


def answering() -> StubAdapter:
    return StubAdapter(ProviderResult("Good evening, my lord.", 20, 10, "req", False))


def latest_call(engine: Engine) -> object:
    with engine.connect() as connection:
        return connection.execute(
            text(
                "select project_id, persona_id, status from model_calls "
                "order by created_at desc limit 1"
            )
        ).one()


def call_count(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text("select count(*) from model_calls")).scalar_one())


# --- 22-23. resolved scope reaches the model call ----------------------------


def test_a_resolved_project_reaches_the_model_call(store: Engine) -> None:
    """Test 22."""
    alpha = project_id(store, ALPHA_SLUG)
    adapter = answering()
    outcome = exchange(
        build_gateway(store, adapter),
        (Message(role="user", content="Good evening."),),
        ProjectSignals(supplied_project_id=alpha),
        load_catalogue(store),
    )
    assert not isinstance(outcome, ClarificationNeeded)
    assert latest_call(store).project_id == alpha  # type: ignore[attr-defined]


def test_explicit_no_project_reaches_the_model_call_as_null(store: Engine) -> None:
    """Test 23. NULL, and it means a decision because nothing else can write one."""
    adapter = answering()
    exchange(
        build_gateway(store, adapter),
        (Message(role="user", content="A general question."),),
        ProjectSignals(explicit_no_project=True),
        load_catalogue(store),
    )
    assert latest_call(store).project_id is None  # type: ignore[attr-defined]


# --- 20-21. ambiguity costs nothing and records nothing ----------------------


def test_ambiguity_makes_no_provider_call_and_no_row(store: Engine) -> None:
    """Tests 20 and 21, and the invariant-16 case.

    Scope is unknown and the content may well be Protected project material, so
    asking a cloud model which project it belongs to would be doing the thing
    invariant 16 forbids in order to find out whether it applies.
    """
    adapter = answering()
    before = call_count(store)

    outcome = exchange(
        build_gateway(store, adapter),
        (Message(role="user", content="Let's continue with the boards."),),
        ProjectSignals(explicit_selection="Winter Light"),
        load_catalogue(store),
    )

    assert isinstance(outcome, ClarificationNeeded)
    assert outcome.reason is AmbiguityReason.MULTIPLE_NAME_MATCHES
    assert outcome.project_id is None
    assert adapter.calls == 0, "a provider was contacted to resolve deterministic ambiguity"
    assert call_count(store) == before, "a model_calls row was written for a call never made"


def test_silence_asks_rather_than_filing_under_no_project(store: Engine) -> None:
    """Test 9 at the boundary: unresolved must not become explicit none."""
    adapter = answering()
    before = call_count(store)
    outcome = exchange(
        build_gateway(store, adapter),
        (Message(role="user", content="Where were we?"),),
        ProjectSignals(),
        load_catalogue(store),
    )
    assert isinstance(outcome, ClarificationNeeded)
    assert adapter.calls == 0
    assert call_count(store) == before


def test_a_stale_project_uuid_is_rejected_without_attribution(store: Engine) -> None:
    """Test 16. Not attributed to anything, and not filed under none either."""
    adapter = answering()
    before = call_count(store)
    outcome = exchange(
        build_gateway(store, adapter),
        (Message(role="user", content="Continue."),),
        ProjectSignals(supplied_project_id=uuid4()),
        load_catalogue(store),
    )
    assert isinstance(outcome, ClarificationNeeded)
    assert outcome.reason is AmbiguityReason.UNKNOWN_IDENTIFIER
    assert adapter.calls == 0
    assert call_count(store) == before


def test_project_existence_is_validated_against_the_store(store: Engine) -> None:
    """A well-formed UUID is not evidence that a project exists."""
    assert project_exists(store, project_id(store, ALPHA_SLUG))
    assert not project_exists(store, uuid4())


# --- 10-11, 14-15. session and switching -------------------------------------


def test_selecting_a_project_resolves_later_unspecified_exchanges(store: Engine) -> None:
    """Test 11."""
    alpha = project_id(store, ALPHA_SLUG)
    session = ProjectSession()
    catalogue = load_catalogue(store)

    first = resolve_scope(ProjectSignals(explicit_selection=ALPHA_SLUG), catalogue)
    assert isinstance(first, ResolvedProject)
    session.select(first)

    later = resolve_scope(ProjectSignals(), catalogue, session)
    assert isinstance(later, ResolvedProject)
    assert later.project_id == alpha


def test_switching_changes_future_scope_only(store: Engine) -> None:
    """Test 14. Alpha's history is untouched by a switch to Beta."""
    alpha, beta = project_id(store, ALPHA_SLUG), project_id(store, BETA_SLUG)
    session, catalogue = ProjectSession(), load_catalogue(store)
    adapter = answering()
    gateway = build_gateway(store, adapter)

    session.select(resolve_scope(ProjectSignals(explicit_selection=ALPHA_SLUG), catalogue))  # type: ignore[arg-type]
    exchange(
        gateway,
        (Message(role="user", content="In Alpha."),),
        ProjectSignals(),
        catalogue,
        session=session,
    )
    alpha_call = latest_call(store)

    session.select(resolve_scope(ProjectSignals(explicit_selection=BETA_SLUG), catalogue))  # type: ignore[arg-type]
    exchange(
        gateway,
        (Message(role="user", content="Now in Beta."),),
        ProjectSignals(),
        catalogue,
        session=session,
    )
    beta_call = latest_call(store)

    assert alpha_call.project_id == alpha  # type: ignore[attr-defined]
    assert beta_call.project_id == beta  # type: ignore[attr-defined]

    with store.connect() as connection:
        still = connection.execute(
            text("select count(*) from model_calls where project_id = :id"), {"id": alpha}
        ).scalar_one()
    assert still == 1, "switching rewrote Alpha's history"


def test_switching_to_no_project_preserves_prior_project_history(store: Engine) -> None:
    """Test 15."""
    alpha = project_id(store, ALPHA_SLUG)
    session, catalogue = ProjectSession(), load_catalogue(store)
    gateway = build_gateway(store, answering())

    session.select(resolve_scope(ProjectSignals(explicit_selection=ALPHA_SLUG), catalogue))  # type: ignore[arg-type]
    exchange(
        gateway,
        (Message(role="user", content="In Alpha."),),
        ProjectSignals(),
        catalogue,
        session=session,
    )

    session.select(ExplicitNoProject())
    exchange(
        gateway,
        (Message(role="user", content="Just a general note."),),
        ProjectSignals(),
        catalogue,
        session=session,
    )

    with store.connect() as connection:
        rows = connection.execute(
            text("select project_id from model_calls order by created_at")
        ).all()
    assert rows[-2].project_id == alpha
    assert rows[-1].project_id is None


def test_an_explicit_none_session_stays_none_for_later_exchanges(store: Engine) -> None:
    """A decision to work outside every project is not re-asked every turn."""
    session, catalogue = ProjectSession(), load_catalogue(store)
    session.select(ExplicitNoProject())
    outcome = resolve_scope(ProjectSignals(), catalogue, session)
    assert isinstance(outcome, ExplicitNoProject)


def test_an_unset_session_is_unresolved_not_no_project(store: Engine) -> None:
    """Session lifetime is the process; after a restart, scope asks."""
    fresh = ProjectSession()
    assert not fresh.is_set
    assert not fresh.is_explicit_none
    outcome = resolve_scope(ProjectSignals(), load_catalogue(store), fresh)
    assert isinstance(outcome, AmbiguousProject)


def test_clearing_a_session_returns_to_unset_not_to_none(store: Engine) -> None:
    """Forgetting a selection is not deciding there is no project."""
    session, catalogue = ProjectSession(), load_catalogue(store)
    session.select(resolve_scope(ProjectSignals(explicit_selection=ALPHA_SLUG), catalogue))  # type: ignore[arg-type]
    session.clear()
    assert not session.is_set
    assert isinstance(resolve_scope(ProjectSignals(), catalogue, session), AmbiguousProject)


def test_an_explicit_selection_overrides_the_session(store: Engine) -> None:
    """Test 12 — the deliberate way to switch, and it needs no special case."""
    beta = project_id(store, BETA_SLUG)
    session, catalogue = ProjectSession(), load_catalogue(store)
    session.select(resolve_scope(ProjectSignals(explicit_selection=ALPHA_SLUG), catalogue))  # type: ignore[arg-type]

    outcome = resolve_scope(ProjectSignals(explicit_selection=BETA_SLUG), catalogue, session)
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project_id == beta


# --- 17, 24. cross-project safety --------------------------------------------


def test_project_a_and_b_attribution_never_cross(store: Engine) -> None:
    """Test 17, with deliberately similar names in the catalogue to confuse it."""
    alpha, beta = project_id(store, ALPHA_SLUG), project_id(store, BETA_SLUG)
    catalogue = load_catalogue(store)
    gateway = build_gateway(store, answering())

    for slug in (ALPHA_SLUG, BETA_SLUG, ALPHA_SLUG, BETA_SLUG):
        exchange(
            gateway,
            (Message(role="user", content="Work."),),
            ProjectSignals(explicit_selection=slug),
            catalogue,
        )

    with store.connect() as connection:
        counts = dict(
            connection.execute(
                text(
                    "select project_id, count(*) from model_calls "
                    "where project_id is not null group by project_id"
                )
            ).all()
        )
    assert counts == {alpha: 2, beta: 2}


def test_stale_session_state_cannot_leak_into_a_resolved_exchange(store: Engine) -> None:
    """Test 24's sharpest form: a session in Alpha, an explicit call about Beta."""
    beta = project_id(store, BETA_SLUG)
    session, catalogue = ProjectSession(), load_catalogue(store)
    session.select(resolve_scope(ProjectSignals(explicit_selection=ALPHA_SLUG), catalogue))  # type: ignore[arg-type]

    gateway = build_gateway(store, answering())
    exchange(
        gateway,
        (Message(role="user", content="Work."),),
        ProjectSignals(supplied_project_id=beta),
        catalogue,
        session=session,
    )

    assert latest_call(store).project_id == beta  # type: ignore[attr-defined]


def test_scope_does_not_come_from_provider_conversation_memory(store: Engine) -> None:
    """Test 24. The provider's view of the conversation contributes nothing.

    The adapter is handed content that names Alpha repeatedly and would, if it
    had any say, "remember" Alpha. The exchange is explicitly scoped to Beta and
    is recorded as Beta.
    """
    beta = project_id(store, BETA_SLUG)
    adapter = answering()
    exchange(
        build_gateway(store, adapter),
        (
            Message(role="user", content="Earlier we worked on Project Alpha."),
            Message(role="assistant", content="Yes, Project Alpha."),
            Message(role="user", content="Continue."),
        ),
        ProjectSignals(supplied_project_id=beta),
        load_catalogue(store),
    )
    assert latest_call(store).project_id == beta  # type: ignore[attr-defined]


# --- 18-19. persona and provider stability -----------------------------------


def test_the_same_persona_revision_is_used_across_projects(store: Engine) -> None:
    """Test 18. A project changes scope. It does not change who Val is."""
    catalogue = load_catalogue(store)
    persona = DatabasePersonaLoader(store).active()
    gateway = build_gateway(store, answering())

    for signals in (
        ProjectSignals(explicit_selection=ALPHA_SLUG),
        ProjectSignals(explicit_selection=BETA_SLUG),
        ProjectSignals(explicit_no_project=True),
    ):
        exchange(gateway, (Message(role="user", content="Good evening."),), signals, catalogue)

    with store.connect() as connection:
        rows = connection.execute(
            text("select distinct persona_id from model_calls where persona_id is not null")
        ).all()
    assert len(rows) == 1
    assert rows[0].persona_id == persona.id

    after = DatabasePersonaLoader(store).active()
    assert (after.id, after.version, after.semantic_version) == (
        persona.id,
        persona.version,
        persona.semantic_version,
    )


def test_provider_substitution_does_not_alter_project_attribution(store: Engine) -> None:
    """Test 19."""
    alpha = project_id(store, ALPHA_SLUG)
    catalogue = load_catalogue(store)

    for provider in ("anthropic", "openai"):
        adapter = StubAdapter(ProviderResult("ok", 10, 10, "r", False), name=provider)
        gateway = Gateway(
            adapters={provider: adapter},
            recorder=lambda record: record_call(store, record),
            ledger=FakeLedger(),
            persona_loader=DatabasePersonaLoader(store),
        )
        exchange(
            gateway,
            (Message(role="user", content="Work."),),
            ProjectSignals(supplied_project_id=alpha),
            catalogue,
        )

    with store.connect() as connection:
        rows = connection.execute(
            text("select distinct project_id from model_calls where project_id is not null")
        ).all()
    assert [row.project_id for row in rows] == [alpha]


# --- the structural guarantees -----------------------------------------------


def test_converse_cannot_be_called_without_a_scope(store: Engine) -> None:
    """The signature is the guarantee: there is no default that writes NULL."""
    gateway = build_gateway(store, answering())
    with pytest.raises(TypeError):
        gateway.converse((Message(role="user", content="hi"),))  # type: ignore[call-arg]


def test_an_ambiguous_outcome_is_not_a_project_scope() -> None:
    """`AmbiguousProject` is absent from `ProjectScope` by construction."""
    ambiguous = AmbiguousProject(reason=AmbiguityReason.UNKNOWN_IDENTIFIER, question="?")
    assert not is_settled(ambiguous)
    assert not isinstance(ambiguous, ResolvedProject | ExplicitNoProject)


def test_attribution_of_is_the_only_way_scope_becomes_a_column(store: Engine) -> None:
    """One answer to 'how does a resolution become a stored value'."""
    alpha = project_id(store, ALPHA_SLUG)
    catalogue = load_catalogue(store)
    resolved = resolve_scope(ProjectSignals(supplied_project_id=alpha), catalogue)
    assert isinstance(resolved, ResolvedProject)

    scope: ProjectScope = resolved
    assert attribution_of(scope) == alpha
    assert attribution_of(ExplicitNoProject()) is None


def test_restricted_content_is_refused_before_scope_is_even_considered(store: Engine) -> None:
    """§16's ordering: content that must never leave is refused first."""
    adapter = answering()
    before = call_count(store)
    with pytest.raises(RestrictedContentRefusedError):
        exchange(
            build_gateway(store, adapter),
            (Message(role="user", content="ssn 123-45-6789"),),
            ProjectSignals(),  # unresolved too — the Restricted refusal comes first
            load_catalogue(store),
        )
    assert adapter.calls == 0
    assert call_count(store) == before


def test_a_conversation_pointing_at_a_deleted_project_asks(store: Engine) -> None:
    """An inconsistency becomes a question, not an attribution and not a NULL."""
    outcome = resolve_scope(
        ProjectSignals(conversation_project_id=uuid4(), conversation_is_established=True),
        load_catalogue(store),
    )
    assert isinstance(outcome, AmbiguousProject)
    assert outcome.reason is AmbiguityReason.INCONSISTENT_CONVERSATION_STATE


def test_every_persisted_null_project_id_is_a_decision(store: Engine) -> None:
    """The queryable distinction WP-0.6 asks for.

    After a run containing resolved, explicit-none, and *unresolved* exchanges,
    every NULL in `model_calls` belongs to an exchange somebody decided about —
    because the unresolved ones produced no row at all.
    """
    catalogue = load_catalogue(store)
    gateway = build_gateway(store, answering())

    exchange(
        gateway,
        (Message(role="user", content="a"),),
        ProjectSignals(explicit_selection=ALPHA_SLUG),
        catalogue,
    )
    exchange(
        gateway,
        (Message(role="user", content="b"),),
        ProjectSignals(explicit_no_project=True),
        catalogue,
    )
    exchange(gateway, (Message(role="user", content="c"),), ProjectSignals(), catalogue)
    exchange(
        gateway,
        (Message(role="user", content="d"),),
        ProjectSignals(explicit_selection="Winter Light"),
        catalogue,
    )

    with store.connect() as connection:
        total = connection.execute(text("select count(*) from model_calls")).scalar_one()
        nulls = connection.execute(
            text("select count(*) from model_calls where project_id is null")
        ).scalar_one()
    assert total == 2, "an unresolved exchange wrote a row"
    assert nulls == 1, "explicit-none is exactly one row, and it is a decision"
