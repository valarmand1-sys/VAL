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

**Corrected 18 August 2026, after independent source review.** The paragraph
that stood here said a model's output entered as a candidate and *"resolves only
when the catalogue agrees and nothing of higher authority disagrees"* — which is
the defect, stated plainly and then not noticed. With no session and no
conversation there **is** nothing of higher authority, so a model naming a real
project exactly resolved it outright. The rule is *no model output determines
scope*, not *no model output determines scope when something else objects*.

The two are now different fields, so origin is part of every call site:

- **`trusted_reference`** — deterministic and application-owned: a UI control, an
  exact command parsed by application code, a trusted identifier. May resolve at
  precedence 5.
- **`untrusted_candidate`** — a model or a heuristic. **Never resolves**, however
  exactly it matches. At most it becomes a candidate attached to a question, so
  confirming it is one answer rather than a fresh interrogation.

Separate fields rather than one field carrying a flag, because a flag can be set
wrongly by the same code that would have used the wrong field, while a field name
is read by everyone who touches the call site. And origin cannot be recovered
from the string: `"Project Beta"` looks identical whether a person typed it or a
model produced it.

## Precedence

No governing document defines an order — WP-0.6 names the signals and requires
determinism without ranking them — so the order recommended in the 17 August
2026 authorisation is adopted, and recorded here because it is the kind of
decision that becomes invisible once it works:

1. **Trusted application project id** — supplied by application state, never by
   a user typing into a message.
2. **The explicit current-interaction scope choice**, in *either* form:
   **selecting a project** or **declining one**. One authority class — see below.
3. **The conversation's established scope** — a project, *or* a deliberate
   explicit-none. Both are decisions and both outrank the session.
4. **The session's current scope** — likewise a project *or* a deliberate none.
5. **An unambiguous exact canonical name or slug** in the text, trusted only.
6. Otherwise: **unresolved** — including the case where the only thing pointing
   at a project was an untrusted suggestion, which is offered for confirmation
   and never acted on.

**Level 2 holds two sources, and that is the correction of 18 August 2026.**
*"Select Project Beta"* and *"this is not for a project"* are the same kind of
act: the user deciding scope now. Ranking the second at level 6 — below
conversation and session — meant a session set an hour ago outranked a decision
being made in this breath, so a user who said *"this isn't for a project"* while
Alpha was selected got Alpha. Both supplied at once is a contradiction between
instructions of equal authority, and it asks rather than picking.

**Established scope is a pair, for both conversation and session.** `…_is_set`
says a decision exists; `…_project_id` says whether it names a project or
declines one. The two are handled by the same code, which is what stopped the
session's explicit-none from being a special case that only survived when
nothing else was said.

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

#: The precedence order, as data — **levels**, not a flat list. Corrected
#: 18 August 2026: level 2 holds two sources because *"select Project Beta"* and
#: *"this is not for a project"* are the same kind of act, and ranking one below
#: conversation and session state let stale scope outrank a decision being made
#: now.
#:
#: A test asserts that flattening this in order reproduces `tuple(ResolutionSource)`
#: exactly, so the enum's declaration order, the documentation above, and the
#: behaviour below cannot drift apart.
PRECEDENCE: tuple[frozenset[ResolutionSource], ...] = (
    frozenset({ResolutionSource.TRUSTED_APPLICATION_ID}),
    # One authority class: an explicit current-interaction scope choice, whether
    # it names a project or declines one. Both present is a contradiction the
    # user has to settle, not one for this module to pick between.
    frozenset({ResolutionSource.EXPLICIT_SELECTION, ResolutionSource.EXPLICIT_NONE_INSTRUCTION}),
    frozenset({ResolutionSource.CONVERSATION}),
    frozenset({ResolutionSource.SESSION}),
    frozenset({ResolutionSource.EXACT_REFERENCE}),
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
    #: The session's current scope, **read exactly like the conversation pair
    #: above**. Corrected 18 August 2026.
    #:
    #: `session_is_set` with `session_project_id = None` means *the session is
    #: explicitly set to no project* — a decision — not *the session is unset*.
    #: `session_is_set = False` is the unset case. Collapsing the two would make
    #: a fresh process indistinguishable from a deliberate choice.
    session_project_id: UUID | None = None
    session_is_set: bool = False
    #: An exact name or slug from a **deterministic, application-owned** source:
    #: a UI control, an exact command parsed by application code, a trusted
    #: identifier. May resolve at precedence 5.
    trusted_reference: str | None = None
    #: A project a **model or heuristic** suggested. **Never resolves**, however
    #: exactly it matches. Corrective round, 18 August 2026: this was previously
    #: one field with `trusted_reference`, and with no session and no
    #: conversation to disagree, a model's exact match resolved outright.
    #:
    #: The two are separate fields rather than one field with a flag because the
    #: field name is then part of every call site, and "this came from a model"
    #: is not something a later reader can recover from the string itself.
    untrusted_candidate: str | None = None

    @property
    def any_reference(self) -> str | None:
        """Whatever names a project, trusted or not — for conflict detection.

        Conflict is about *disagreement*, not about authority: a model naming
        Beta while the session says Alpha is still a reason to ask, even though
        the model could never have resolved Beta on its own.
        """
        return self.trusted_reference or self.untrusted_candidate


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

    # 2. The explicit current-interaction scope choice — either form.
    #
    #    Corrected 18 August 2026. "Select Project Beta" and "this is not for a
    #    project" are the same kind of act: the user deciding scope now. The
    #    second used to sit at precedence 6, below conversation and session, so a
    #    session set an hour ago outranked a decision being made in this breath.
    #
    #    Both supplied at once is a contradiction between two instructions of
    #    equal authority. There is no principled way to pick, so it asks.
    if signals.explicit_selection is not None and signals.explicit_no_project:
        return AmbiguousProject(
            reason=AmbiguityReason.CONFLICTING_SIGNALS,
            question=(
                f"You have asked for {signals.explicit_selection.strip()} and also said "
                "this is not for a project. Those are both scope decisions and they "
                "disagree, so I have not chosen between them — which did you mean?"
            ),
        )
    if signals.explicit_selection is not None:
        return _from_reference(
            signals.explicit_selection, catalogue, ResolutionSource.EXPLICIT_SELECTION
        )
    if signals.explicit_no_project:
        # Level 2, not a fallback. It outranks conversation and session exactly
        # as naming a project does, and it is how a user steps out of project
        # scope — the forward-only counterpart of an explicit selection. Nothing
        # historical is touched: this decides *this* exchange only.
        return ExplicitNoProject(via=ResolutionSource.EXPLICIT_NONE_INSTRUCTION)

    # 3-4. Established scope, and the conflict rule that governs both.
    #
    #      A reference to another project while scope is already established is
    #      genuinely unclear — *switch to Beta*, or *in Alpha, note what Beta
    #      did*? Choosing either is how an exchange about one project ends up
    #      filed under another and stays there. So it asks, and level 2 is how
    #      the user actually switches.
    #
    #      Conflict detection uses `any_reference`: a model naming Beta while the
    #      session says Alpha is still a disagreement worth asking about, even
    #      though it could never have resolved Beta by itself.
    established = _established_scope(signals, catalogue)
    if established is not None:
        settled, source = established
        named = signals.any_reference
        if named is not None:
            mentioned = catalogue.matching(named)
            names_other = any(settled is None or project.id != settled.id for project in mentioned)
            if mentioned and names_other:
                here = settled.name if settled is not None else "no project"
                others = [p for p in mentioned if settled is None or p.id != settled.id]
                return AmbiguousProject(
                    reason=AmbiguityReason.CONFLICTING_SIGNALS,
                    question=(
                        f"This conversation is scoped to {here}, but you have named "
                        f"{_list_names(mentioned)}. Do you want to switch, or is this "
                        f"still {here}?"
                    ),
                    candidates=tuple(([settled] if settled is not None else []) + others),
                )
        if settled is None:
            # An established conversation deliberately outside every project. A
            # decision, and it stands until an explicit selection changes it.
            return ExplicitNoProject(via=source)
        return ResolvedProject(settled, via=source)

    # 5. A **trusted** exact reference, with nothing established to weigh it
    #    against. Untrusted candidates are deliberately absent from this step: an
    #    exact match does not make a model authoritative, and the whole point of
    #    the corrective round is that this branch used to accept either.
    if signals.trusted_reference is not None:
        resolved = _from_reference(
            signals.trusted_reference, catalogue, ResolutionSource.EXACT_REFERENCE
        )
        # A reference matching nothing is not a failure — the user may simply
        # have been talking. Fall through to the explicit-none check and then to
        # unresolved, rather than demanding they account for the words they used.
        if not isinstance(resolved, AmbiguousProject):
            return resolved
        if resolved.reason is AmbiguityReason.MULTIPLE_NAME_MATCHES:
            return resolved

    # 6. An untrusted suggestion, and nothing else. It is **offered**, never
    #     acted on. A model naming a real project correctly is still a model
    #     naming it, and WP-0.6 says application code sets final scope. So this
    #     asks — with the suggestion attached, so confirming it is one answer
    #     rather than a fresh question.
    if signals.untrusted_candidate is not None:
        suggested = catalogue.matching(signals.untrusted_candidate)
        if suggested:
            return AmbiguousProject(
                reason=AmbiguityReason.UNTRUSTED_SUGGESTION_ONLY,
                question=(
                    "Nothing has established which project this is for. "
                    f"{_list_names(suggested)} was suggested, but a suggestion is not a "
                    "decision and I will not scope your work on one. Is that right?"
                ),
                candidates=tuple(suggested),
            )

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
) -> tuple[ProjectRecord | None, ResolutionSource] | None:
    """The conversation's scope, else the session's. Existence-checked.

    Returns `(project, source)` for an established project, `(None, source)` for
    an established **explicit no-project**, and `None` when nothing is
    established at all. Those three are distinct and the middle one is what this
    function got wrong before.

    **Corrected 18 August 2026.** An established conversation whose
    `project_id` is NULL is a conversation deliberately outside every project —
    `04-layer-0.md` §2.1 says NULL means exactly that. The original code required
    `conversation_project_id is not None` to treat the conversation as
    established at all, so an explicit-none conversation fell through to the
    session and, failing that, to unresolved. Two consequences, and the first is
    the dangerous one:

    - a session in Alpha **silently took over** a conversation the user had
      deliberately placed outside every project;
    - a conversation that was explicitly no-project came back as *unresolved*,
      which would have made WP-0.7 re-ask a question already answered.

    A conversation or session pointing at a project that no longer exists is an
    inconsistency rather than a scope, and is reported as one — resolving it to
    "no project" would turn a broken pointer into a decision nobody made.
    """
    if signals.conversation_is_established:
        if signals.conversation_project_id is None:
            # An established conversation with no project. A decision, and it
            # outranks the session below it like any other conversation scope.
            return None, ResolutionSource.CONVERSATION
        found = catalogue.by_id(signals.conversation_project_id)
        if found is not None:
            return found, ResolutionSource.CONVERSATION
        raise InconsistentConversationScopeError(signals.conversation_project_id)

    if signals.session_is_set:
        if signals.session_project_id is None:
            # A session explicitly set to no project. Corrected 18 August 2026:
            # this used to require a non-NULL id to count, so the decision
            # vanished from resolution the moment any other signal appeared —
            # and a trusted reference to another project then resolved outright
            # instead of asking.
            return None, ResolutionSource.SESSION
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
