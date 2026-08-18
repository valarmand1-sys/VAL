"""Deterministic project resolution. The application decides scope, and only it.

`04-layer-0.md` WP-0.6: *"Resolution uses explicit names, IDs, and session
state. Application code sets final scope; no model output determines it.
Ambiguous project reference produces a question, never a guess."*

**Pure by construction, and that is the enforcement mechanism.** This module
takes a catalogue snapshot and a set of signals and returns a resolution. It has
no database handle, no provider adapter, and no way to call anything — so there
is no code path by which a model's opinion could become scope, because there is
no code path by which a model could be consulted at all. `val_policy` may depend
only on `val_domain` (`01-architecture.md` §3), which CI enforces two ways.

A model output can enter here only as `mentioned_reference`, and only as a
*candidate*: it is looked up in the catalogue by exact name or slug like any
other reference, and it resolves only when the catalogue agrees and nothing of
higher authority disagrees. A confidently wrong model naming a real project it
was not asked about therefore loses to the session, and a model naming a project
that does not exist resolves to nothing at all.

## Precedence

No governing document defines an order — WP-0.6 names the signals and requires
determinism without ranking them — so the order recommended in the 17 August
2026 authorisation is adopted, and recorded here because it is the kind of
decision that becomes invisible once it works:

1. **Trusted application project id** — supplied by application state, never by
   a user typing into a message.
2. **Explicit selection or switch** in this interaction.
3. **The conversation's established project.**
4. **The session's current project.**
5. **An unambiguous exact canonical name or slug** in the text.
6. **An explicit "this has no project" instruction.**
7. Otherwise: **unresolved**.

**Higher authority wins outright; comparable authority in conflict asks.** A
session in Alpha and an exact reference to Beta is not a case for preferring one
— it is genuinely unclear whether the user means *switch to Beta* or *while
working in Alpha, note that Beta did this*. Guessing there is how an exchange
about Beta is filed under Alpha and stays there. So it asks, and the way to
actually change projects is the explicit switch at level 2, which outranks
everything below it and leaves nothing to interpret.

## What is deliberately not here

**No fuzzy matching.** Exact id, exact slug, exact canonical name, and nothing
else. A friendly interface may one day *suggest* likely projects; a suggestion
is not a resolution, and similarity ranking has no authority in Layer 0.

**No status policy.** `projects.status` exists and the baselines enumerate no
values for it, so nothing here treats any status as disqualifying. Inventing a
rule that archived projects cannot be conversed about would be policy this
implementation is not entitled to write. Recorded as a narrow open decision
rather than guessed at.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from val_domain.project import (
    AmbiguityReason,
    AmbiguousProject,
    ExplicitNoProject,
    ProjectRecord,
    ProjectResolution,
    ResolutionSource,
    ResolvedProject,
)

#: The precedence order, as data. `ResolutionSource`'s member order is asserted
#: equal to this by a test, so the documentation above and the behaviour below
#: cannot drift apart.
PRECEDENCE: tuple[ResolutionSource, ...] = (
    ResolutionSource.TRUSTED_APPLICATION_ID,
    ResolutionSource.EXPLICIT_SELECTION,
    ResolutionSource.CONVERSATION,
    ResolutionSource.SESSION,
    ResolutionSource.EXACT_REFERENCE,
    ResolutionSource.EXPLICIT_NONE_INSTRUCTION,
)


@dataclass(frozen=True)
class ProjectSignals:
    """Everything the application knows about this exchange's scope.

    Deliberately a record of *signals* rather than a request to interpret prose.
    Turning "work on the animation project" into a signal is the interface's job
    (WP-0.10); deciding what a set of signals means is this module's, and keeping
    the two apart is what stops a parser's guess from acquiring authority it was
    never granted.
    """

    #: From trusted application state. Never from message text.
    supplied_project_id: UUID | None = None
    #: An explicit select-or-switch action: a name, slug, or id the user chose.
    explicit_selection: str | None = None
    #: The user said this exchange has no project.
    explicit_no_project: bool = False
    #: The project this conversation is already in, if it is in one.
    conversation_project_id: UUID | None = None
    #: Whether the conversation is established at all. A conversation resolved to
    #: explicit-none is a different fact from a conversation not yet resolved,
    #: and `conversation_project_id = None` cannot tell them apart on its own.
    conversation_is_established: bool = False
    #: The session's current project, and whether the session has been set.
    session_project_id: UUID | None = None
    session_is_set: bool = False
    #: An exact name or slug appearing in the text. A candidate, never authority.
    mentioned_reference: str | None = None


class ProjectCatalogue:
    """The projects that exist, as a snapshot. Lookup only, exact only.

    Existence validation lives here because "this UUID is well-formed" and "this
    project exists" are different claims, and only the second is worth anything.
    A supplied id that matches nothing resolves to `UNKNOWN_IDENTIFIER`, not to
    a project and not to none.
    """

    def __init__(self, projects: Iterable[ProjectRecord]) -> None:
        self._by_id: dict[UUID, ProjectRecord] = {}
        self._by_slug: dict[str, ProjectRecord] = {}
        self._by_name: dict[str, list[ProjectRecord]] = {}
        for project in projects:
            self._by_id[project.id] = project
            self._by_slug[normalise(project.slug)] = project
            self._by_name.setdefault(normalise(project.name), []).append(project)

    def by_id(self, project_id: UUID) -> ProjectRecord | None:
        return self._by_id.get(project_id)

    def matching(self, reference: str) -> list[ProjectRecord]:
        """Every project an exact reference could mean, in a stable order.

        A slug is unique by database constraint, so a slug match is always one
        project. A **name is not unique** — nothing in the schema makes it so —
        so a name match may return several, and that is the ambiguity WP-0.6
        requires a question about rather than a choice between.
        """
        key = normalise(reference)
        slug_match = self._by_slug.get(key)
        if slug_match is not None:
            return [slug_match]
        return sorted(self._by_name.get(key, []), key=lambda project: project.slug)


def normalise(reference: str) -> str:
    """The one normalisation applied to every name and slug comparison.

    Case-folded and outer-whitespace-stripped, with internal runs of whitespace
    collapsed to a single space. Stated once and used for both sides of every
    comparison, so "Tony & Joni  Pilot" and "tony & joni pilot" are the same
    reference and neither is a fuzzy match for the other.

    Case-folding rather than lowercasing because `casefold` handles scripts
    `lower` does not, and a project named in one of them should not become
    unreachable by typing it correctly.
    """
    return " ".join(reference.split()).casefold()


def resolve(signals: ProjectSignals, catalogue: ProjectCatalogue) -> ProjectResolution:
    """Settle this exchange's scope, or produce the question that would.

    Returns exactly one of `ResolvedProject`, `ExplicitNoProject`, or
    `AmbiguousProject`. It never returns None and never raises for ordinary
    input: "I cannot tell" is a value, not an exception, because it is a normal
    outcome that the caller must handle rather than an error it may miss.
    """
    # 1. Trusted application id. Highest authority, and still existence-checked:
    #    a well-formed UUID is not evidence that a project exists.
    if signals.supplied_project_id is not None:
        found = catalogue.by_id(signals.supplied_project_id)
        if found is None:
            return AmbiguousProject(
                reason=AmbiguityReason.UNKNOWN_IDENTIFIER,
                question=(
                    f"I do not have a project with the id {signals.supplied_project_id}. "
                    "I have not filed this under any project, and I have not filed it "
                    "under none either — tell me which project you meant."
                ),
            )
        return ResolvedProject(found, via=ResolutionSource.TRUSTED_APPLICATION_ID)

    # 2. An explicit selection or switch. The deliberate way to change scope,
    #    and the reason a mere mention lower down never has to be treated as one.
    if signals.explicit_selection is not None:
        return _from_reference(
            signals.explicit_selection, catalogue, ResolutionSource.EXPLICIT_SELECTION
        )

    # 3-4. Established scope, and the conflict rule that governs both.
    #
    #      A mention of another project while scope is already established is
    #      genuinely unclear — *switch to Beta*, or *in Alpha, note what Beta
    #      did*? Choosing either is how an exchange about one project ends up
    #      filed under another and stays there. So it asks, and level 2 is how
    #      the user actually switches.
    established = _established_scope(signals, catalogue)
    if established is not None:
        settled, source = established
        if signals.mentioned_reference is not None:
            mentioned = catalogue.matching(signals.mentioned_reference)
            names_other = any(project.id != settled.id for project in mentioned)
            if mentioned and names_other:
                return AmbiguousProject(
                    reason=AmbiguityReason.CONFLICTING_SIGNALS,
                    question=(
                        f"We are in {settled.name}, but you have named "
                        f"{_list_names(mentioned)}. Do you want to switch, or is this "
                        f"still {settled.name}?"
                    ),
                    candidates=(settled, *[p for p in mentioned if p.id != settled.id]),
                )
        return ResolvedProject(settled, via=source)

    # 5. An exact reference, with nothing established to weigh it against.
    if signals.mentioned_reference is not None:
        resolved = _from_reference(
            signals.mentioned_reference, catalogue, ResolutionSource.EXACT_REFERENCE
        )
        # A mention that matches nothing is not a failure — the user may simply
        # have been talking. Fall through to the explicit-none check and then to
        # unresolved, rather than demanding they account for the words they used.
        if not isinstance(resolved, AmbiguousProject):
            return resolved
        if resolved.reason is AmbiguityReason.MULTIPLE_NAME_MATCHES:
            return resolved

    # 6. An explicit instruction that this has no project.
    if signals.explicit_no_project:
        return ExplicitNoProject(via=ResolutionSource.EXPLICIT_NONE_INSTRUCTION)

    # 7. Nothing said, nothing established. Unresolved — and *not* no-project.
    return AmbiguousProject(
        reason=AmbiguityReason.UNKNOWN_IDENTIFIER,
        question=(
            "Which project is this for? I can also file it under no project, but I "
            "will not assume that — an exchange nobody scoped and an exchange "
            "deliberately outside every project are different things."
        ),
    )


def _established_scope(
    signals: ProjectSignals, catalogue: ProjectCatalogue
) -> tuple[ProjectRecord, ResolutionSource] | None:
    """The conversation's project, else the session's. Existence-checked.

    A conversation or session pointing at a project that no longer exists is an
    inconsistency rather than a scope, and is reported as one — resolving it to
    "no project" would turn a broken pointer into a decision nobody made.
    """
    if signals.conversation_is_established and signals.conversation_project_id is not None:
        found = catalogue.by_id(signals.conversation_project_id)
        if found is not None:
            return found, ResolutionSource.CONVERSATION
        raise InconsistentConversationScopeError(signals.conversation_project_id)

    if signals.session_is_set and signals.session_project_id is not None:
        found = catalogue.by_id(signals.session_project_id)
        if found is not None:
            return found, ResolutionSource.SESSION
        raise InconsistentConversationScopeError(signals.session_project_id)

    return None


class InconsistentConversationScopeError(Exception):
    """Established scope names a project that does not exist.

    Raised rather than returned because it is not a question for the user — they
    cannot answer "your conversation points at a deleted project". It is a
    data-integrity defect for the application to surface, and the caller turns it
    into an `AmbiguousProject` so nothing proceeds on it.
    """

    def __init__(self, project_id: UUID) -> None:
        super().__init__(
            f"established scope names project {project_id}, which does not exist. "
            "Nothing is attributed and nothing is filed under no project."
        )
        self.project_id = project_id


def _from_reference(
    reference: str, catalogue: ProjectCatalogue, source: ResolutionSource
) -> ProjectResolution:
    """One reference, resolved exactly, or the question it raises."""
    matches = catalogue.matching(reference)
    if len(matches) == 1:
        return ResolvedProject(matches[0], via=source)
    if len(matches) > 1:
        return AmbiguousProject(
            reason=AmbiguityReason.MULTIPLE_NAME_MATCHES,
            question=(
                f"I have {len(matches)} projects matching '{reference.strip()}': "
                f"{_list_names(matches)}. Which one do you mean?"
            ),
            candidates=tuple(matches),
        )
    return AmbiguousProject(
        reason=AmbiguityReason.UNKNOWN_IDENTIFIER,
        question=(
            f"I have no project called '{reference.strip()}'. Which project did you "
            "mean, or is this outside any project?"
        ),
    )


def _list_names(projects: Iterable[ProjectRecord]) -> str:
    """The smallest useful distinction: the candidates, and only them.

    Unrelated projects are not listed. A question that recites the whole
    catalogue makes the user do the narrowing that was this module's job.

    **Where the names themselves collide, the slug is what distinguishes them.**
    Found by running the acceptance cases rather than by reading the code: two
    projects both called "Winter Light" produced *"I have 2 projects matching
    'Winter Light': Winter Light and Winter Light"*, which is a question nobody
    can answer. A clarification that does not distinguish the candidates has not
    clarified anything. `slug` is unique by database constraint, so it always
    can.
    """
    listed = list(projects)
    names = [project.name for project in listed]
    if len(names) <= 1:
        return "".join(names)

    seen = [name.casefold() for name in names]
    labelled = [
        f"{project.name} ({project.slug})"
        if seen.count(project.name.casefold()) > 1
        else project.name
        for project in listed
    ]
    return f"{', '.join(labelled[:-1])} and {labelled[-1]}"
