"""Project scope as a typed fact, and the three states it can be in.

`04-layer-0.md` WP-0.6 requires that *"every exchange is attributable to a
project or explicitly to none, and resolution is deterministic"*, and that
*"no message exists with an unresolved project state — nullable means
'explicitly none,' and the distinction is queryable."*

**The whole design follows from one observation about NULL.** A nullable
`project_id` can carry exactly one meaning, and the schema already spends it on
*explicitly no project*. It therefore cannot also mean *nobody has worked out
which project this is yet*. Those two are opposite in consequence — one is a
decision, the other is the absence of one — and a system that stores them in the
same field will eventually read an unanswered question as an answer.

So there are three states in the domain and only two of them can be persisted:

| State | Means | Persists as |
|---|---|---|
| `ResolvedProject` | A specific project, deterministically identified | its `id`, as `resolved` |
| `ExplicitNoProject` | Deliberately outside any project | NULL, as `explicit_none` |
| `AmbiguousProject` | Scope cannot be determined safely | **nothing — it is asked about** |

**A NULL `project_id` is not by itself an explicit no-project decision**, and no
code here should read it as one. `model_calls` rows carry a `ProjectAttribution`
that says which state produced them, and the nine rows written before WP-0.6
existed carry NULL with `legacy_unknown` — a NULL nobody chose. Query
`project_attribution = 'explicit_none'` for the decisions; `project_id IS NULL`
alone returns those decisions *and* that history mixed together.

**`ProjectScope` is the union of the first two, and that is the mechanism.**
Every function that attributes or persists an exchange takes a `ProjectScope`,
so an `AmbiguousProject` cannot reach persistence at all — not because a check
rejects it, but because it is not the right type to pass. A check can be
forgotten by the next caller; a signature cannot.

**Corrected 18 August 2026, after independent source review.** This module
previously claimed that `project_id IS NULL` was *exactly* the explicit-none set.
That was true of everything the resolver writes and false of the database as a
whole, which is a different and much weaker claim than the one being made. Nine
rows predate WP-0.6 entirely, and the generic `GatewayRequest` still let a caller
default `project_id` to `None` without deciding anything.

A NULL therefore no longer stands alone. Every `model_calls` row carries a
`ProjectAttribution` beside it saying which of the three states it is in, so a
reader gets the distinction from the row rather than from a rule about dates that
nobody looking at one row could apply.

Nothing here touches a database or a model. Resolution rules live in
`val_policy.project_resolution`; the catalogue and session live in
`val_gateway.projects`.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class ProjectAttribution(StrEnum):
    """What a stored `project_id` *means*. Corrective round, 18 August 2026.

    The original WP-0.6 claimed *"`project_id IS NULL` is exactly the
    explicit-none set"*. Independent review found that untrue globally, and it
    was right twice over: nine rows written before WP-0.6 existed carry NULL and
    were never a decision, and `GatewayRequest.project_id` still defaulted to
    `None`, so any caller could write a fresh semantically-empty NULL.

    A NULL alone cannot carry two meanings, so the meaning is stored beside it
    rather than inferred from it later. Inference would have had to key on a
    date, and a rule that says *"NULLs before this timestamp mean one thing"* is
    a rule nobody reading a single row can apply.

    | State | `project_id` | Means |
    |---|---|---|
    | `RESOLVED` | a real id | Deterministically identified |
    | `EXPLICIT_NONE` | NULL | Somebody decided this is outside every project |
    | `LEGACY_UNKNOWN` | NULL | **Predates the distinction.** Nobody decided. |

    **`LEGACY_UNKNOWN` is a read state, never a write state.** `GatewayRequest`
    refuses it and the database refuses it on any row created after the
    corrective migration, so it cannot become the way new code avoids deciding
    scope. That reservation is the whole reason it is safe to have a third value
    at all.
    """

    RESOLVED = "resolved"
    EXPLICIT_NONE = "explicit_none"
    LEGACY_UNKNOWN = "legacy_unknown"


class ReferenceTrust(StrEnum):
    """Whether a project reference may decide scope, or only suggest it.

    Corrective round, 18 August 2026. `04-layer-0.md` WP-0.6 requires that
    *"application code sets final scope; no model output determines it"*, and
    independent review found the original implementation satisfied that only
    when something else disagreed: with no session and no conversation, an exact
    reference from **any** origin resolved outright — including one a model
    produced.

    Origin is now part of the type rather than a matter of which field a caller
    happened to use, because "this string came from a model" is not recoverable
    by looking at the string.
    """

    #: Deterministic and application-owned: a UI selection, an exact user command
    #: parsed by application code, a trusted identifier. **May resolve.**
    TRUSTED = "trusted"
    #: A model's suggestion, a heuristic, anything inferred from prose.
    #: **Never resolves.** At most it becomes a candidate to confirm.
    UNTRUSTED = "untrusted"


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
    #:
    #: **This and `EXPLICIT_NONE_INSTRUCTION` are one authority class.** Corrected
    #: 18 August 2026: *"select Project Beta"* and *"this is not for a project"*
    #: are both explicit current-interaction scope choices, and treating the
    #: second as a weak fallback below conversation and session state meant a
    #: stale session outranked a decision the user was making right now.
    EXPLICIT_SELECTION = "explicit_selection"
    #: The user said, in this interaction, that this work has no project. Same
    #: authority as naming one — see `EXPLICIT_SELECTION`.
    EXPLICIT_NONE_INSTRUCTION = "explicit_none_instruction"
    #: The scope this conversation was already established in — a project, or a
    #: deliberate none.
    CONVERSATION = "conversation"
    #: The scope currently selected for the session — a project, or a deliberate
    #: none.
    SESSION = "session"
    #: An exact canonical name or slug **from a trusted origin**, with nothing
    #: higher-authority to weigh it against. An untrusted candidate never
    #: appears here — it has no `ResolutionSource` at all, because it never
    #: resolves anything.
    EXACT_REFERENCE = "exact_reference"


class AmbiguityReason(StrEnum):
    """Why scope could not be settled. Each becomes a different question."""

    #: A human-facing name matched more than one project.
    MULTIPLE_NAME_MATCHES = "multiple_name_matches"
    #: An id, slug, or name that resolves to no project at all.
    UNKNOWN_IDENTIFIER = "unknown_identifier"
    #: Two signals of comparable authority disagreed — a session in one project
    #: and an exact reference to another, for instance.
    CONFLICTING_SIGNALS = "conflicting_signals"
    #: Nothing authoritative settled scope, and the only thing pointing at a
    #: project was an untrusted suggestion. It is offered for confirmation and
    #: never acted on: a model naming a real project correctly is still a model
    #: naming it (corrective round, 18 August 2026).
    UNTRUSTED_SUGGESTION_ONLY = "untrusted_suggestion_only"
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
class ProjectCandidate:
    """One project offered for the user to choose between.

    Carries **stable identity**, not a display string. Corrective round,
    18 August 2026: the clarification payload previously carried names only, so
    two projects both called `Winter Light` arrived as
    `("Winter Light", "Winter Light")` — a question the caller could put but
    could not interpret the answer to.

    `slug` distinguishes them for a human; `project_id` resolves the answer
    without a second lookup that could pick the wrong one. `status` is
    deliberately absent: it has no settled semantics (executive decision,
    17 August), and a field with no meaning does not belong in a payload whose
    whole job is to identify.
    """

    project_id: UUID
    name: str
    slug: str

    @classmethod
    def of(cls, project: ProjectRecord) -> ProjectCandidate:
        return cls(project_id=project.id, name=project.name, slug=project.slug)


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


def attribution_state_of(scope: ProjectScope) -> ProjectAttribution:
    """What that `project_id` *means*, written beside it.

    Never `LEGACY_UNKNOWN`: this function takes a `ProjectScope`, and a scope is
    by definition a decision somebody made. The legacy state is reachable only by
    reading a historical row, which is exactly the reservation that keeps it from
    becoming the way new code avoids deciding.
    """
    return (
        ProjectAttribution.RESOLVED
        if isinstance(scope, ResolvedProject)
        else ProjectAttribution.EXPLICIT_NONE
    )
