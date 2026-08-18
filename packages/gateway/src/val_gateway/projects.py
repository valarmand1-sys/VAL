"""The project catalogue, and the session that holds current scope.

The resolver in `val_policy.project_resolution` is pure and knows nothing about
storage. This is the half that reads PostgreSQL and remembers what the user
selected — kept separate so the rules stay testable with no application running
(`01-architecture.md` §3) and so nothing that touches a database can quietly
acquire the authority to decide scope.

**Session lifetime at Layer 0: the process, and no longer.** Selecting a project
lasts as long as the application runs. It is not written to the database and
does not survive a restart, because persistent conversation state is WP-0.7's
and pulling it forward would be building a later layer early. After a restart,
scope is unset — which is *unresolved*, not *no project*, so the next exchange
asks rather than assuming. That is the safe direction to fail, and it is stated
here rather than left for someone to discover.

**Session state is application-owned.** It lives in this process, keyed by
nothing a provider can see. No provider's conversation memory contributes to it,
which is the point: a model that "remembers" the last project discussed has no
way to make that memory into scope.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Engine, text

from val_domain.project import (
    ExplicitNoProject,
    ProjectRecord,
    ProjectScope,
    ResolutionSource,
    ResolvedProject,
)
from val_policy.project_resolution import ProjectCatalogue

_SELECT_PROJECTS = text("select id, name, slug, status from projects order by slug")

_SELECT_ONE = text("select id, name, slug, status from projects where id = :id")


def load_catalogue(engine: Engine) -> ProjectCatalogue:
    """Every project, as a snapshot the pure resolver can be handed.

    Read per resolution rather than cached. At Layer 0 there are a handful of
    projects and one indexed read is not worth the class of bug a stale
    catalogue introduces — a project created a moment ago failing to resolve, or
    one renamed still answering to its old name.
    """
    with engine.connect() as connection:
        rows = connection.execute(_SELECT_PROJECTS).all()
    return ProjectCatalogue(
        ProjectRecord(id=row.id, name=row.name, slug=row.slug, status=row.status) for row in rows
    )


def project_exists(engine: Engine, project_id: UUID) -> bool:
    """Whether a project id names something real.

    Used where an id arrives from outside the resolver — a caller passing one
    directly. Well-formed UUID syntax is not evidence of existence, and the
    foreign key would catch it eventually, but a constraint violation at write
    time is a worse way to learn it than a refusal at resolution time.
    """
    with engine.connect() as connection:
        return connection.execute(_SELECT_ONE, {"id": project_id}).one_or_none() is not None


@dataclass
class ProjectSession:
    """The project currently selected, for this process.

    Three states, and the third is why this is not just an optional UUID:

    | State | Means |
    |---|---|
    | unset | Nothing has been selected. **Unresolved**, so the next exchange asks. |
    | a project | Selected; unspecified exchanges resolve to it |
    | explicit none | The user chose to work outside every project |

    `unset` and `explicit none` are both "no project id", and collapsing them
    would make a fresh process indistinguishable from a deliberate decision —
    exactly the confusion the whole work package exists to remove.
    """

    #: None means unset. `_explicit_none` distinguishes it from a chosen none.
    _project_id: UUID | None = None
    _explicit_none: bool = False

    @property
    def is_set(self) -> bool:
        """Whether the session carries a decision of any kind."""
        return self._project_id is not None or self._explicit_none

    @property
    def project_id(self) -> UUID | None:
        """The selected project, or None for unset *and* for explicit none.

        Read alongside `is_set`; on its own it cannot tell you which.
        """
        return self._project_id

    @property
    def is_explicit_none(self) -> bool:
        return self._explicit_none

    def select(self, scope: ProjectScope) -> None:
        """Set current scope from an already-resolved outcome.

        Takes a `ProjectScope`, so an `AmbiguousProject` cannot be selected —
        the session can only ever hold something that was settled. Scope changes
        **only forward**: nothing here touches a stored conversation, message,
        or model call, so history keeps the attribution it was written with.
        """
        if isinstance(scope, ResolvedProject):
            self._project_id = scope.project_id
            self._explicit_none = False
        else:
            self._project_id = None
            self._explicit_none = True

    def clear(self) -> None:
        """Return to unset — not to explicit none.

        Forgetting what was selected is not the same as deciding there is no
        project, so this restores the state where the next exchange asks.
        """
        self._project_id = None
        self._explicit_none = False

    def scope(self, catalogue: ProjectCatalogue) -> ProjectScope | None:
        """The session's decision as a scope, or None if it holds none.

        Existence is re-checked: a project selected earlier and since removed is
        an inconsistency, and returning None sends the caller back to asking
        rather than attributing an exchange to something that is gone.
        """
        if self._explicit_none:
            return ExplicitNoProject(via=ResolutionSource.EXPLICIT_SELECTION)
        if self._project_id is None:
            return None
        found = catalogue.by_id(self._project_id)
        if found is None:
            return None
        return ResolvedProject(found, via=ResolutionSource.SESSION)
