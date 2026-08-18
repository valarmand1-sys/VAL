"""Project scope as a typed fact, and the three states it can be in.

`04-layer-0.md` WP-0.6 requires that *"every exchange is attributable to a
project or explicitly to none, and resolution is deterministic"*, and that
*"no message exists with an unresolved project state — nullable means
'explicitly none,' and the distinction is queryable."*

**The whole design follows from one observation about NULL.** A nullable
`project_id` can carry exactly one meaning, and the schema already spends it:
NULL means *explicitly no project*. It therefore cannot also mean *nobody has
worked out which project this is yet*. Those two are opposite in consequence —
one is a decision, the other is the absence of one — and a system that stores
them in the same field will eventually read an unanswered question as an answer.

So there are three states in the domain and only two of them can be persisted:

| State | Means | Persists as |
|---|---|---|
| `ResolvedProject` | A specific existing project, deterministically identified | its `id` |
| `ExplicitNoProject` | This exchange is deliberately outside any project | **NULL** |
| `AmbiguousProject` | Scope cannot be determined safely | **nothing — it must be asked about** |

**`ProjectScope` is the union of the first two, and that is the mechanism.**
Every function that attributes or persists an exchange takes a `ProjectScope`,
so an `AmbiguousProject` cannot reach persistence at all — not because a check
rejects it, but because it is not the right type to pass. A check can be
forgotten by the next caller; a signature cannot.

That is also what makes the distinction queryable without a schema change:
`project_id IS NULL` returns exactly the explicit-none set, because the only
value that produces NULL is `ExplicitNoProject`, and ambiguity has no path to
the database to muddy it.

Nothing here touches a database or a model. Resolution rules live in
`val_policy.project_resolution`; the catalogue and session live in
`val_gateway.projects`.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class ResolutionSource(StrEnum):
    """Which authoritative signal decided the scope.

    Recorded on every resolution so that "why is this exchange attributed to
    Alpha?" is answerable from the result rather than by re-running the
    reasoning. The order of the members is the precedence order of
    `val_policy.project_resolution`, and the two are asserted equal by a test —
    a precedence documented in one place and implemented in another drifts.
    """

    #: A project id supplied by trusted application state, not by a user typing.
    TRUSTED_APPLICATION_ID = "trusted_application_id"
    #: An explicit select-or-switch action taken in this interaction.
    EXPLICIT_SELECTION = "explicit_selection"
    #: The project this conversation was already established in.
    CONVERSATION = "conversation"
    #: The project currently selected for the session.
    SESSION = "session"
    #: An exact canonical name or slug, with nothing higher-authority to weigh
    #: it against.
    EXACT_REFERENCE = "exact_reference"
    #: The user said this exchange has no project.
    EXPLICIT_NONE_INSTRUCTION = "explicit_none_instruction"


class AmbiguityReason(StrEnum):
    """Why scope could not be settled. Each becomes a different question."""

    #: A human-facing name matched more than one project.
    MULTIPLE_NAME_MATCHES = "multiple_name_matches"
    #: An id, slug, or name that resolves to no project at all.
    UNKNOWN_IDENTIFIER = "unknown_identifier"
    #: Two signals of comparable authority disagreed — a session in one project
    #: and an exact reference to another, for instance.
    CONFLICTING_SIGNALS = "conflicting_signals"
    #: The conversation's own recorded scope contradicts itself or names a
    #: project that no longer exists.
    INCONSISTENT_CONVERSATION_STATE = "inconsistent_conversation_state"


@dataclass(frozen=True)
class ProjectRecord:
    """One project as the authoritative store holds it.

    A snapshot rather than a live handle: the resolver is pure, so it is given
    the catalogue rather than reaching for it. `status` is carried but not
    interpreted — see `val_policy.project_resolution` for why Layer 0 declines
    to invent a status policy the baselines do not define.
    """

    id: UUID
    name: str
    slug: str
    status: str


@dataclass(frozen=True)
class ResolvedProject:
    """A specific existing project, deterministically identified."""

    project: ProjectRecord
    via: ResolutionSource

    @property
    def project_id(self) -> UUID:
        """What persists. Always a real id — existence was validated to get here."""
        return self.project.id


@dataclass(frozen=True)
class ExplicitNoProject:
    """This exchange is deliberately outside any project.

    A decision, not an absence of one. It is the *only* thing in this system
    that produces a NULL `project_id`, which is what lets NULL be read as a
    decision everywhere it appears.
    """

    via: ResolutionSource = ResolutionSource.EXPLICIT_NONE_INSTRUCTION

    @property
    def project_id(self) -> None:
        """NULL, meaning explicitly none."""
        return None


@dataclass(frozen=True)
class AmbiguousProject:
    """Scope cannot be settled. The user must be asked.

    Carries the candidates it could not choose between and the question to put,
    so the caller does not have to reconstruct either. **It has no
    `project_id`** — deliberately, and that absence is the point: there is
    nothing here that could be persisted by accident.
    """

    reason: AmbiguityReason
    question: str
    candidates: tuple[ProjectRecord, ...] = ()


#: What may be attributed and persisted. `AmbiguousProject` is absent by
#: construction: a function taking a `ProjectScope` cannot be handed an
#: unresolved exchange, so "unresolved never reaches the database" is enforced
#: by the type checker on every call site rather than by a runtime check that
#: some future caller forgets.
ProjectScope = ResolvedProject | ExplicitNoProject

#: Everything resolution can produce.
ProjectResolution = ResolvedProject | ExplicitNoProject | AmbiguousProject


def is_settled(resolution: ProjectResolution) -> bool:
    """Whether this exchange may proceed to attributed persistence."""
    return not isinstance(resolution, AmbiguousProject)


def attribution_of(scope: ProjectScope) -> UUID | None:
    """The `project_id` to write. The single place scope becomes a column value.

    Every persistence path goes through this, so there is one answer to "how
    does a resolution become a stored value" rather than one per table.
    """
    return scope.project_id
