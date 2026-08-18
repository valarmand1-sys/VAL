"""WP-0.6 — project resolution is deterministic, and the application owns it.

Pure tests: no database, no provider, no clock. That is the same property the
module has, and it is the enforcement mechanism rather than a convenience — a
resolver that cannot reach a model cannot be talked into a project by one.

The fixture catalogue carries **two deliberately confusable pairs**, because a
test suite whose projects are named "alpha" and "beta" proves nothing about the
case that actually bites: two real projects a person would refer to the same way.
"""

from uuid import UUID, uuid4

import pytest

from val_domain.project import (
    AmbiguityReason,
    AmbiguousProject,
    ExplicitNoProject,
    ProjectRecord,
    ResolutionSource,
    ResolvedProject,
)
from val_policy.project_resolution import (
    PRECEDENCE,
    InconsistentConversationScopeError,
    ProjectCatalogue,
    ProjectSignals,
    normalise,
    resolve,
)

# --- fixtures ----------------------------------------------------------------
#
# Two clearly different projects, and two that share a human-facing word on
# purpose. "Tony" matches neither exactly — it is the kind of half-reference a
# person actually types — while "Winter Light" is an exact name collision, which
# the schema permits because only `slug` is unique.

ALPHA = ProjectRecord(
    id=UUID("11111111-1111-4111-8111-111111111111"),
    name="Project Alpha",
    slug="project-alpha",
    status="active",
)
BETA = ProjectRecord(
    id=UUID("22222222-2222-4222-8222-222222222222"),
    name="Project Beta",
    slug="project-beta",
    status="active",
)
TONY_PILOT = ProjectRecord(
    id=UUID("33333333-3333-4333-8333-333333333333"),
    name="Tony & Joni Pilot",
    slug="tony-joni-pilot",
    status="active",
)
TONY_THEME = ProjectRecord(
    id=UUID("44444444-4444-4444-8444-444444444444"),
    name="Tony Theme Sequence",
    slug="tony-theme-sequence",
    status="active",
)
#: Two projects with the *same display name* and different slugs. Legal in this
#: schema, and the sharpest form of the ambiguity WP-0.6 must ask about.
WINTER_A = ProjectRecord(
    id=UUID("55555555-5555-4555-8555-555555555555"),
    name="Winter Light",
    slug="winter-light-series",
    status="active",
)
WINTER_B = ProjectRecord(
    id=UUID("66666666-6666-4666-8666-666666666666"),
    name="Winter Light",
    slug="winter-light-short",
    status="archived",
)

CATALOGUE = ProjectCatalogue([ALPHA, BETA, TONY_PILOT, TONY_THEME, WINTER_A, WINTER_B])


def signals(**overrides: object) -> ProjectSignals:
    return ProjectSignals(**overrides)  # type: ignore[arg-type]


# --- 1-3. exact id, slug, canonical name -------------------------------------


def test_an_exact_project_id_resolves() -> None:
    """Test 1."""
    outcome = resolve(signals(supplied_project_id=ALPHA.id), CATALOGUE)
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project_id == ALPHA.id
    assert outcome.via is ResolutionSource.TRUSTED_APPLICATION_ID


def test_an_exact_slug_resolves() -> None:
    """Test 2. Slugs are unique by constraint, so a slug match is never ambiguous."""
    outcome = resolve(signals(explicit_selection="project-beta"), CATALOGUE)
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project_id == BETA.id


def test_an_exact_canonical_name_resolves() -> None:
    """Test 3."""
    outcome = resolve(signals(explicit_selection="Project Alpha"), CATALOGUE)
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project_id == ALPHA.id


def test_a_slug_wins_over_a_name_of_the_same_text() -> None:
    """Slug is checked first because it is the only unique human-facing key."""
    catalogue = ProjectCatalogue(
        [
            ProjectRecord(id=uuid4(), name="overlap", slug="distinct-slug", status="active"),
            ProjectRecord(id=ALPHA.id, name="ignored", slug="overlap", status="active"),
        ]
    )
    outcome = resolve(signals(explicit_selection="overlap"), catalogue)
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project_id == ALPHA.id


# --- 4. normalisation is deterministic ---------------------------------------


@pytest.mark.parametrize(
    "reference",
    ["Project Alpha", "project alpha", "PROJECT ALPHA", "  Project   Alpha  ", "\tProject Alpha\n"],
)
def test_case_and_whitespace_normalise_the_same_way_every_time(reference: str) -> None:
    """Test 4. One rule, applied to both sides of every comparison."""
    outcome = resolve(signals(explicit_selection=reference), CATALOGUE)
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project_id == ALPHA.id


def test_normalisation_is_not_fuzzy_matching() -> None:
    """Near-misses do not resolve. Similarity has no authority in WP-0.6."""
    for near_miss in ("Project Alpah", "Projekt Alpha", "Alpha", "Project Alph"):
        outcome = resolve(signals(explicit_selection=near_miss), CATALOGUE)
        assert isinstance(outcome, AmbiguousProject), f"{near_miss!r} resolved by similarity"
        assert outcome.reason is AmbiguityReason.UNKNOWN_IDENTIFIER


def test_normalise_is_idempotent() -> None:
    """Applying it twice changes nothing, so both sides always agree."""
    for value in ("  Winter   Light ", "TONY & Joni Pilot", "project-beta"):
        assert normalise(normalise(value)) == normalise(value)


# --- 5-6. missing and ambiguous ----------------------------------------------


def test_an_unknown_project_id_is_unresolved_not_no_project() -> None:
    """Test 5, and test 16. A well-formed UUID is not evidence of existence."""
    stale = uuid4()
    outcome = resolve(signals(supplied_project_id=stale), CATALOGUE)
    assert isinstance(outcome, AmbiguousProject)
    assert outcome.reason is AmbiguityReason.UNKNOWN_IDENTIFIER
    assert str(stale) in outcome.question
    assert not hasattr(outcome, "project_id"), "an unresolved outcome must carry no attribution"


def test_a_name_matching_two_projects_asks() -> None:
    """Test 6. The sharpest case: one display name, two real projects."""
    outcome = resolve(signals(explicit_selection="Winter Light"), CATALOGUE)
    assert isinstance(outcome, AmbiguousProject)
    assert outcome.reason is AmbiguityReason.MULTIPLE_NAME_MATCHES
    assert {p.id for p in outcome.candidates} == {WINTER_A.id, WINTER_B.id}
    assert "Winter Light" in outcome.question


def test_the_question_names_only_the_candidates() -> None:
    """Clarification shows the smallest useful distinction, not the catalogue."""
    outcome = resolve(signals(explicit_selection="Winter Light"), CATALOGUE)
    assert isinstance(outcome, AmbiguousProject)
    for unrelated in ("Project Alpha", "Project Beta", "Tony Theme Sequence"):
        assert unrelated not in outcome.question


def test_a_half_reference_does_not_resolve() -> None:
    """'Tony' matches two projects but is an exact name for neither."""
    outcome = resolve(signals(explicit_selection="Tony"), CATALOGUE)
    assert isinstance(outcome, AmbiguousProject)
    assert outcome.reason is AmbiguityReason.UNKNOWN_IDENTIFIER


# --- 7. a model cannot establish scope ---------------------------------------


def test_a_model_suggestion_cannot_establish_scope() -> None:
    """Test 7. A confidently wrong model naming a real project loses to the session.

    The model's output can only enter as `mentioned_reference` — a candidate. It
    is looked up like any other reference and weighed against everything of
    higher authority. Here the session says Alpha and the "model" insists on
    Beta, and the result is a question, not Beta.
    """
    model_says = "Project Beta"  # confident, well-formed, and wrong
    outcome = resolve(
        signals(
            session_project_id=ALPHA.id,
            session_is_set=True,
            mentioned_reference=model_says,
        ),
        CATALOGUE,
    )
    assert not isinstance(outcome, ResolvedProject) or outcome.project_id != BETA.id
    assert isinstance(outcome, AmbiguousProject)
    assert outcome.reason is AmbiguityReason.CONFLICTING_SIGNALS


def test_a_model_naming_a_project_that_does_not_exist_resolves_to_nothing() -> None:
    """A hallucinated project name creates no scope at all."""
    outcome = resolve(signals(mentioned_reference="The Secret Ninth Project"), CATALOGUE)
    assert isinstance(outcome, AmbiguousProject)
    assert outcome.candidates == ()


def test_the_resolver_cannot_reach_a_model_at_all() -> None:
    """The structural half of test 7, asserted on the import graph.

    `val_policy.project_resolution` importing a provider or the gateway is the
    only way a model could contribute, so that is what is checked — not the
    presence of a word in the source.
    """
    import ast
    from pathlib import Path

    import val_policy.project_resolution as module

    tree = ast.parse(Path(module.__file__ or "").read_text())
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)

    for name in imported:
        assert not name.startswith(("val_providers", "val_gateway", "anthropic", "openai")), (
            f"the resolver imports {name}: a model would have a path into scope"
        )


# --- 8-9. explicit none, and what must never become it -----------------------


def test_an_explicit_no_project_instruction_resolves_to_none() -> None:
    """Test 8."""
    outcome = resolve(signals(explicit_no_project=True), CATALOGUE)
    assert isinstance(outcome, ExplicitNoProject)
    assert outcome.project_id is None
    assert outcome.via is ResolutionSource.EXPLICIT_NONE_INSTRUCTION


def test_silence_is_unresolved_and_never_no_project() -> None:
    """Test 9, and the heart of the work package.

    Nobody said anything about scope. That is not a decision to work outside
    every project — it is the absence of a decision, and treating it as the
    former is how an unanswered question becomes an answer.
    """
    outcome = resolve(signals(), CATALOGUE)
    assert isinstance(outcome, AmbiguousProject)
    assert not isinstance(outcome, ExplicitNoProject)
    assert "will not assume" in outcome.question


@pytest.mark.parametrize(
    "ambiguous",
    [
        signals(),
        signals(supplied_project_id=uuid4()),
        signals(explicit_selection="Winter Light"),
        signals(explicit_selection="No Such Project"),
        signals(
            session_project_id=ALPHA.id, session_is_set=True, mentioned_reference="Project Beta"
        ),
    ],
)
def test_no_ambiguous_outcome_can_be_read_as_no_project(ambiguous: ProjectSignals) -> None:
    """Every unresolved path produces something with no attribution at all."""
    outcome = resolve(ambiguous, CATALOGUE)
    assert isinstance(outcome, AmbiguousProject)
    assert not isinstance(outcome, ExplicitNoProject | ResolvedProject)


# --- 10-13. precedence -------------------------------------------------------


def test_an_established_conversation_resolves_a_later_exchange() -> None:
    """Test 10. The user does not restate the project every time."""
    outcome = resolve(
        signals(conversation_project_id=ALPHA.id, conversation_is_established=True), CATALOGUE
    )
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project_id == ALPHA.id
    assert outcome.via is ResolutionSource.CONVERSATION


def test_a_session_project_resolves_a_later_exchange() -> None:
    """Test 11."""
    outcome = resolve(signals(session_project_id=BETA.id, session_is_set=True), CATALOGUE)
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project_id == BETA.id
    assert outcome.via is ResolutionSource.SESSION


def test_an_exact_reference_resolves_when_nothing_is_established() -> None:
    """Test 12. Precedence 5 — a reference with nothing to weigh it against."""
    outcome = resolve(signals(mentioned_reference="Project Alpha"), CATALOGUE)
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project_id == ALPHA.id
    assert outcome.via is ResolutionSource.EXACT_REFERENCE


def test_an_explicit_selection_outranks_an_established_conversation() -> None:
    """Precedence 2 over 3 — this is how switching works, deliberately."""
    outcome = resolve(
        signals(
            explicit_selection="Project Beta",
            conversation_project_id=ALPHA.id,
            conversation_is_established=True,
        ),
        CATALOGUE,
    )
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project_id == BETA.id
    assert outcome.via is ResolutionSource.EXPLICIT_SELECTION


def test_a_trusted_id_outranks_everything() -> None:
    """Precedence 1."""
    outcome = resolve(
        signals(
            supplied_project_id=TONY_PILOT.id,
            explicit_selection="Project Beta",
            conversation_project_id=ALPHA.id,
            conversation_is_established=True,
            session_project_id=BETA.id,
            session_is_set=True,
        ),
        CATALOGUE,
    )
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project_id == TONY_PILOT.id


def test_a_conversation_outranks_a_session() -> None:
    """Precedence 3 over 4."""
    outcome = resolve(
        signals(
            conversation_project_id=ALPHA.id,
            conversation_is_established=True,
            session_project_id=BETA.id,
            session_is_set=True,
        ),
        CATALOGUE,
    )
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project_id == ALPHA.id
    assert outcome.via is ResolutionSource.CONVERSATION


def test_conflicting_signals_ask_rather_than_choose() -> None:
    """Test 13. A session in Alpha and a mention of Beta is genuinely unclear.

    *Switch to Beta*, or *while in Alpha, note what Beta did*? Choosing either
    is how an exchange about one project is filed under another and stays there.
    """
    outcome = resolve(
        signals(
            session_project_id=ALPHA.id, session_is_set=True, mentioned_reference="Project Beta"
        ),
        CATALOGUE,
    )
    assert isinstance(outcome, AmbiguousProject)
    assert outcome.reason is AmbiguityReason.CONFLICTING_SIGNALS
    assert {p.id for p in outcome.candidates} == {ALPHA.id, BETA.id}
    assert "switch" in outcome.question.lower()


def test_mentioning_the_project_you_are_already_in_is_not_a_conflict() -> None:
    """Restating the current project is agreement, not disagreement."""
    outcome = resolve(
        signals(
            session_project_id=ALPHA.id, session_is_set=True, mentioned_reference="Project Alpha"
        ),
        CATALOGUE,
    )
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project_id == ALPHA.id


def test_an_explicit_selection_outranks_an_explicit_no_project_instruction() -> None:
    """Precedence 2 over 6. Naming a project is a decision about scope."""
    outcome = resolve(
        signals(explicit_selection="Project Alpha", explicit_no_project=True), CATALOGUE
    )
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project_id == ALPHA.id


def test_the_documented_precedence_matches_the_implemented_one() -> None:
    """A precedence documented in one place and implemented in another drifts."""
    assert PRECEDENCE == tuple(ResolutionSource)


# --- inconsistent established state ------------------------------------------


def test_a_conversation_pointing_at_a_missing_project_is_an_inconsistency() -> None:
    """Not a question the user can answer, so it is raised rather than returned."""
    with pytest.raises(InconsistentConversationScopeError):
        resolve(
            signals(conversation_project_id=uuid4(), conversation_is_established=True), CATALOGUE
        )


def test_a_session_pointing_at_a_missing_project_is_an_inconsistency() -> None:
    with pytest.raises(InconsistentConversationScopeError):
        resolve(signals(session_project_id=uuid4(), session_is_set=True), CATALOGUE)


# --- status is carried, not interpreted --------------------------------------


def test_an_archived_project_still_resolves() -> None:
    """No status policy is invented where the baselines define none.

    `WINTER_B` is archived and resolves by slug like any other project. Whether
    an archived project may be the *current* project is a policy question the
    baselines do not answer, and guessing at it here would be writing policy
    this implementation is not entitled to write. Recorded as an open decision.
    """
    outcome = resolve(signals(explicit_selection="winter-light-short"), CATALOGUE)
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project.status == "archived"


def test_a_clarification_distinguishes_candidates_that_share_a_name() -> None:
    """Found by running the acceptance cases, not by reading the code.

    Two projects both called "Winter Light" produced *"I have 2 projects
    matching 'Winter Light': Winter Light and Winter Light"* — a question nobody
    can answer. A clarification that does not distinguish its candidates has not
    clarified anything, and `slug` is unique by constraint, so it always can.
    """
    outcome = resolve(signals(explicit_selection="Winter Light"), CATALOGUE)
    assert isinstance(outcome, AmbiguousProject)
    assert "winter-light-series" in outcome.question
    assert "winter-light-short" in outcome.question


def test_distinct_names_are_not_cluttered_with_slugs() -> None:
    """The slug appears only where it is doing work."""
    catalogue = ProjectCatalogue([TONY_PILOT, TONY_THEME])
    duplicate = ProjectRecord(
        id=uuid4(), name="Tony & Joni Pilot", slug="tony-joni-pilot-v2", status="active"
    )
    both = ProjectCatalogue([TONY_PILOT, duplicate])

    unique_names = resolve(signals(explicit_selection="Tony & Joni Pilot"), catalogue)
    assert isinstance(unique_names, ResolvedProject)

    collided = resolve(signals(explicit_selection="Tony & Joni Pilot"), both)
    assert isinstance(collided, AmbiguousProject)
    assert "tony-joni-pilot" in collided.question
    assert "tony-joni-pilot-v2" in collided.question
