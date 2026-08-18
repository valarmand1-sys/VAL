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

    The model's output enters only as `untrusted_candidate`, which never
    resolves. Here the session says Alpha and the "model" insists on Beta, and
    the result is a question, not Beta.
    """
    model_says = "Project Beta"  # confident, well-formed, and wrong
    outcome = resolve(
        signals(
            session_project_id=ALPHA.id,
            session_is_set=True,
            untrusted_candidate=model_says,
        ),
        CATALOGUE,
    )
    assert not isinstance(outcome, ResolvedProject) or outcome.project_id != BETA.id
    assert isinstance(outcome, AmbiguousProject)
    assert outcome.reason is AmbiguityReason.CONFLICTING_SIGNALS


def test_a_model_naming_a_project_that_does_not_exist_resolves_to_nothing() -> None:
    """A hallucinated project name creates no scope at all."""
    outcome = resolve(signals(untrusted_candidate="The Secret Ninth Project"), CATALOGUE)
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
        signals(session_project_id=ALPHA.id, session_is_set=True, trusted_reference="Project Beta"),
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
    outcome = resolve(signals(trusted_reference="Project Alpha"), CATALOGUE)
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
        signals(session_project_id=ALPHA.id, session_is_set=True, trusted_reference="Project Beta"),
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
            session_project_id=ALPHA.id, session_is_set=True, trusted_reference="Project Alpha"
        ),
        CATALOGUE,
    )
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project_id == ALPHA.id


def test_an_explicit_selection_and_an_explicit_none_no_longer_rank() -> None:
    """*Superseded 18 August 2026 by independent review — see case F below.*

    This test used to assert that naming a project beats "not for a project",
    on the reasoning that precedence 2 outranks precedence 6. The ranking was
    the defect. Both utterances are the *same act* — a person stating scope for
    this exchange — so one cannot outrank the other, and a resolver that picks
    the naming one is guessing which of two contradictory instructions the
    speaker meant. They now share an authority class and fail closed.

    Kept as a named test rather than deleted: the old behaviour is the thing a
    future reader is most likely to reintroduce, since it looks decisive.
    """
    outcome = resolve(
        signals(explicit_selection="Project Alpha", explicit_no_project=True), CATALOGUE
    )
    assert isinstance(outcome, AmbiguousProject)
    assert outcome.reason is AmbiguityReason.CONFLICTING_SIGNALS


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


# =========================================================================
# WP-0.6 corrective round, 18 August 2026 — independent source review
# =========================================================================


# --- Finding 1. A model may suggest. It may never decide. --------------------


def test_an_untrusted_candidate_naming_an_exact_project_does_not_resolve_it() -> None:
    """**The missing adversarial test.** The one the original suite lacked.

    No conversation, no session, no explicit selection — nothing of higher
    authority to disagree — and an untrusted candidate naming Project Beta
    exactly. The original resolver returned `ResolvedProject(Beta)`, because its
    rule was *"resolves when nothing of higher authority disagrees"* and here
    nothing did. The rule is *no model output determines scope*, full stop.
    """
    outcome = resolve(signals(untrusted_candidate="Project Beta"), CATALOGUE)

    assert not isinstance(outcome, ResolvedProject), "a model established scope"
    assert isinstance(outcome, AmbiguousProject)
    assert outcome.reason is AmbiguityReason.UNTRUSTED_SUGGESTION_ONLY
    # The suggestion is carried so confirming it is one answer, not a fresh start.
    assert {p.id for p in outcome.candidates} == {BETA.id}
    assert "suggestion is not a decision" in outcome.question


@pytest.mark.parametrize(
    "reference", ["Project Beta", "project-beta", "PROJECT BETA", " Project  Beta "]
)
def test_no_spelling_of_an_untrusted_candidate_resolves(reference: str) -> None:
    """Exactness is not authority. Every normalisation of a real name still asks."""
    outcome = resolve(signals(untrusted_candidate=reference), CATALOGUE)
    assert isinstance(outcome, AmbiguousProject)
    assert outcome.reason is AmbiguityReason.UNTRUSTED_SUGGESTION_ONLY


def test_an_untrusted_candidate_by_exact_id_string_does_not_resolve() -> None:
    """A model that produces the right UUID is still a model producing it.

    `supplied_project_id` is trusted *application state*. A model's opinion never
    arrives there, so a UUID it emits is just another untrusted string, and it
    matches no name or slug.
    """
    outcome = resolve(signals(untrusted_candidate=str(BETA.id)), CATALOGUE)
    assert isinstance(outcome, AmbiguousProject)
    assert outcome.reason is AmbiguityReason.UNKNOWN_IDENTIFIER


def test_a_hallucinated_untrusted_candidate_establishes_nothing() -> None:
    """A project that does not exist creates no scope and no false candidate."""
    outcome = resolve(signals(untrusted_candidate="The Secret Ninth Project"), CATALOGUE)
    assert isinstance(outcome, AmbiguousProject)
    assert outcome.candidates == ()
    assert not isinstance(outcome, ExplicitNoProject)


def test_the_same_string_resolves_from_a_trusted_field_and_not_an_untrusted_one() -> None:
    """The difference is origin, and origin alone. Byte-identical input, both ways.

    This is the whole correction in one assertion: nothing about the *string*
    decides, because nothing about the string can. Only which field it arrived in.
    """
    trusted = resolve(signals(trusted_reference="Project Beta"), CATALOGUE)
    untrusted = resolve(signals(untrusted_candidate="Project Beta"), CATALOGUE)

    assert isinstance(trusted, ResolvedProject)
    assert trusted.project_id == BETA.id
    assert isinstance(untrusted, AmbiguousProject)


def test_an_untrusted_candidate_cannot_override_a_trusted_one() -> None:
    """Both present, disagreeing: the trusted one decides and the model is ignored."""
    outcome = resolve(
        signals(trusted_reference="Project Alpha", untrusted_candidate="Project Beta"),
        CATALOGUE,
    )
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project_id == ALPHA.id


# --- Finding 2. An established explicit-no-project conversation --------------


def test_an_established_conversation_with_no_project_is_explicitly_none() -> None:
    """Case A. `04-layer-0.md` §2.1: a NULL conversation project means exactly this.

    The original resolver required `conversation_project_id is not None` to treat
    a conversation as established, so an explicit-none conversation fell through
    to the session and then to unresolved — re-asking a question already answered.
    """
    outcome = resolve(signals(conversation_is_established=True), CATALOGUE)
    assert isinstance(outcome, ExplicitNoProject)
    assert outcome.via is ResolutionSource.CONVERSATION
    assert outcome.project_id is None


def test_a_session_cannot_hijack_an_explicit_no_project_conversation() -> None:
    """Case B, and the dangerous one.

    Before the correction this returned `ResolvedProject(Alpha)` **via session**:
    a conversation the user had deliberately placed outside every project was
    silently pulled into whatever the session happened to hold. WP-0.7 will
    persist and resume conversation scope, so this would have become durable.
    """
    outcome = resolve(
        signals(
            conversation_is_established=True,
            session_project_id=ALPHA.id,
            session_is_set=True,
        ),
        CATALOGUE,
    )
    assert isinstance(outcome, ExplicitNoProject), "the session took over"
    assert outcome.via is ResolutionSource.CONVERSATION


def test_an_explicit_no_project_conversation_stays_none_for_ordinary_exchanges() -> None:
    """Case C. It is a decision, and it holds without being restated."""
    for _ in range(3):
        outcome = resolve(signals(conversation_is_established=True), CATALOGUE)
        assert isinstance(outcome, ExplicitNoProject)


def test_an_explicit_selection_can_still_switch_out_of_a_no_project_conversation() -> None:
    """Case D. Precedence 2 outranks 3, and that is how switching works."""
    outcome = resolve(
        signals(conversation_is_established=True, explicit_selection="Project Beta"), CATALOGUE
    )
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project_id == BETA.id
    assert outcome.via is ResolutionSource.EXPLICIT_SELECTION


@pytest.mark.parametrize("field", ["trusted_reference", "untrusted_candidate"])
def test_a_lower_authority_reference_does_not_reattribute_a_no_project_conversation(
    field: str,
) -> None:
    """Case E. A mention is not a switch — it asks, whatever its origin."""
    outcome = resolve(
        signals(conversation_is_established=True, **{field: "Project Beta"}), CATALOGUE
    )
    assert isinstance(outcome, AmbiguousProject)
    assert outcome.reason is AmbiguityReason.CONFLICTING_SIGNALS
    assert BETA.id in {p.id for p in outcome.candidates}
    assert "no project" in outcome.question


def test_an_established_project_conversation_still_resolves_normally() -> None:
    """The correction must not have broken the case that already worked."""
    outcome = resolve(
        signals(conversation_is_established=True, conversation_project_id=ALPHA.id), CATALOGUE
    )
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project_id == ALPHA.id
    assert outcome.via is ResolutionSource.CONVERSATION


# --- Finding 3. Candidates must be distinguishable ---------------------------


def test_duplicate_display_names_produce_structurally_distinct_candidates() -> None:
    """Two projects, one name. The candidates must still be told apart."""
    outcome = resolve(signals(explicit_selection="Winter Light"), CATALOGUE)
    assert isinstance(outcome, AmbiguousProject)

    ids = [p.id for p in outcome.candidates]
    slugs = [p.slug for p in outcome.candidates]
    names = [p.name for p in outcome.candidates]

    assert len(set(ids)) == 2, "candidates share an id"
    assert len(set(slugs)) == 2, "candidates share a slug"
    assert len(set(names)) == 1, "the premise: they genuinely share a display name"


def test_the_question_and_the_candidate_set_describe_the_same_projects() -> None:
    """A question naming projects the payload does not carry is unanswerable."""
    outcome = resolve(signals(explicit_selection="Winter Light"), CATALOGUE)
    assert isinstance(outcome, AmbiguousProject)
    for candidate in outcome.candidates:
        assert candidate.slug in outcome.question


# --- Finding 5. `projects.status` has no resolution authority ----------------


@pytest.mark.parametrize(
    "status", ["active", "archived", "disabled", "", "on hold", "DELETED", "whatever"]
)
def test_project_status_has_no_resolution_authority(status: str) -> None:
    """Behavioural regression on the executive decision of 17 August 2026.

    The *same project identity* resolves identically under any status string.
    Deliberately not a source-text assertion: what matters is that no status
    changes the outcome, not that a particular word is absent from a file.

    **A future governing decision may intentionally change this test**, together
    with the status vocabulary and the restrictions it defines. Until then, a
    metadata column with no settled semantics decides nothing.
    """
    project = ProjectRecord(
        id=UUID("77777777-7777-4777-8777-777777777777"),
        name="Status Probe",
        slug="status-probe",
        status=status,
    )
    catalogue = ProjectCatalogue([project])

    by_slug = resolve(signals(explicit_selection="status-probe"), catalogue)
    by_name = resolve(signals(explicit_selection="Status Probe"), catalogue)
    by_id = resolve(signals(supplied_project_id=project.id), catalogue)

    for outcome in (by_slug, by_name, by_id):
        assert isinstance(outcome, ResolvedProject)
        assert outcome.project_id == project.id


# =========================================================================
# WP-0.6 corrective round two, 18 August 2026 — explicit scope authority
# =========================================================================
#
# "Select Project Beta" and "this is not for a project" are the same kind of
# act. Ranking the second below conversation and session meant a session set an
# hour ago outranked a decision being made now.


def test_an_explicit_no_project_beats_a_session_project() -> None:
    """Case A. Was `ResolvedProject(Alpha)` via session."""
    outcome = resolve(
        signals(session_project_id=ALPHA.id, session_is_set=True, explicit_no_project=True),
        CATALOGUE,
    )
    assert isinstance(outcome, ExplicitNoProject), "a stale session outranked a live decision"
    assert outcome.via is ResolutionSource.EXPLICIT_NONE_INSTRUCTION


def test_an_explicit_no_project_beats_an_established_conversation() -> None:
    """Case B. The forward-only counterpart of an explicit selection.

    It decides *this* exchange. Nothing historical is touched — the resolver
    writes nothing, and switching has always been forward-only.
    """
    outcome = resolve(
        signals(
            conversation_project_id=ALPHA.id,
            conversation_is_established=True,
            explicit_no_project=True,
        ),
        CATALOGUE,
    )
    assert isinstance(outcome, ExplicitNoProject)
    assert outcome.via is ResolutionSource.EXPLICIT_NONE_INSTRUCTION


def test_an_explicit_no_project_beats_a_trusted_reference() -> None:
    """Level 2 over level 5, the same way an explicit selection would."""
    outcome = resolve(
        signals(explicit_no_project=True, trusted_reference="Project Beta"), CATALOGUE
    )
    assert isinstance(outcome, ExplicitNoProject)


def test_a_trusted_application_id_still_outranks_an_explicit_no_project() -> None:
    """Level 1 is unchanged. The correction raised level 6 to 2, not to 0."""
    outcome = resolve(signals(supplied_project_id=ALPHA.id, explicit_no_project=True), CATALOGUE)
    assert isinstance(outcome, ResolvedProject)
    assert outcome.project_id == ALPHA.id


def test_two_contradictory_explicit_choices_fail_closed() -> None:
    """Case F. Same authority class, disagreeing. There is no principled pick."""
    outcome = resolve(
        signals(explicit_selection="Project Beta", explicit_no_project=True), CATALOGUE
    )
    assert isinstance(outcome, AmbiguousProject)
    assert outcome.reason is AmbiguityReason.CONFLICTING_SIGNALS
    assert "not for a project" in outcome.question
    assert "Project Beta" in outcome.question


# --- the session's explicit-none is structural, not a special case -----------


def test_a_session_explicitly_set_to_no_project_resolves_to_none() -> None:
    """Case C, expressed the way the resolver now reads it: a pair.

    `session_is_set` with a NULL id means the session holds a decision to work
    outside every project — read exactly like the conversation pair.
    """
    outcome = resolve(signals(session_is_set=True, session_project_id=None), CATALOGUE)
    assert isinstance(outcome, ExplicitNoProject)
    assert outcome.via is ResolutionSource.SESSION


def test_an_explicit_none_session_conflicts_with_a_trusted_reference() -> None:
    """Case D. It used to vanish, and Beta resolved outright with no question."""
    outcome = resolve(
        signals(session_is_set=True, session_project_id=None, trusted_reference="Project Beta"),
        CATALOGUE,
    )
    assert isinstance(outcome, AmbiguousProject), "the session's decision disappeared"
    assert outcome.reason is AmbiguityReason.CONFLICTING_SIGNALS
    assert BETA.id in {p.id for p in outcome.candidates}
    assert "no project" in outcome.question


def test_an_explicit_none_session_conflicts_with_an_untrusted_candidate() -> None:
    """Case E. The model must not establish Beta *and* must not erase the session."""
    outcome = resolve(
        signals(session_is_set=True, session_project_id=None, untrusted_candidate="Project Beta"),
        CATALOGUE,
    )
    assert not isinstance(outcome, ResolvedProject), "a model established scope"
    assert isinstance(outcome, AmbiguousProject)
    assert outcome.reason is AmbiguityReason.CONFLICTING_SIGNALS


def test_an_unset_session_is_still_distinct_from_an_explicit_none_session() -> None:
    """The two must not collapse. One asks; the other is a decision."""
    unset = resolve(signals(session_is_set=False, session_project_id=None), CATALOGUE)
    decided = resolve(signals(session_is_set=True, session_project_id=None), CATALOGUE)

    assert isinstance(unset, AmbiguousProject)
    assert isinstance(decided, ExplicitNoProject)


def test_a_conversation_outranks_a_session_for_explicit_none_too() -> None:
    """Symmetry: the pair is read the same way at both levels."""
    outcome = resolve(
        signals(
            conversation_is_established=True,
            conversation_project_id=None,
            session_project_id=ALPHA.id,
            session_is_set=True,
        ),
        CATALOGUE,
    )
    assert isinstance(outcome, ExplicitNoProject)
    assert outcome.via is ResolutionSource.CONVERSATION


def test_the_documented_precedence_levels_match_the_enum() -> None:
    """The drift guard, now over levels rather than a flat list."""
    flattened = [source for level in PRECEDENCE for source in sorted(level, key=lambda s: s.value)]
    assert set(flattened) == set(ResolutionSource)
    assert len(flattened) == len(ResolutionSource)
    # Level 2 is the one that holds two, and they are the pair that must.
    assert PRECEDENCE[1] == frozenset(
        {ResolutionSource.EXPLICIT_SELECTION, ResolutionSource.EXPLICIT_NONE_INSTRUCTION}
    )
