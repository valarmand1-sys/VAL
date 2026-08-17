"""The persona at runtime: seeded from the document, served from PostgreSQL.

**Two authorities, and they are not the same one.**

- `docs/baselines/03-persona.md` is the **controlled source** for import and
  versioning. It is what Lord Armand edits.
- The **active `personas` row** is the **runtime authority**. It is what Val is
  built from on every call.

The file is read at seed time and never again. Reading it per call would make
Val's identity depend on a markdown file being present on the machine at the
moment of inference — so a deleted file, a bad deploy, or a working directory
one level off would quietly change who she is. `04-layer-0.md` WP-0.5 makes the
same point from the other end: the two acceptance checks are separate precisely
so that a divergence between file and row cannot read as a pass.

**Failure is closed, in all three directions.** No active persona, more than one
active persona, or no database at all each stop the call. There is no embedded
fallback copy and no "generic Val": a Val running without her persona is not a
degraded Val, she is a different one, and `00-charter.md` §1.2 is explicit that
provider or infrastructure substitution must not change her identity.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from uuid import UUID

from sqlalchemy import Engine, text

from val_domain.persona import GOVERNING_PERSONA_PATH, PersonaSource, digest_of, read_source


class PersonaProblem(StrEnum):
    """Why the runtime persona could not be established."""

    NONE_ACTIVE = "none_active"
    MULTIPLE_ACTIVE = "multiple_active"
    UNREADABLE = "unreadable"


class PersonaUnavailableError(Exception):
    """Val cannot be assembled. Nothing proceeds on a substitute."""

    def __init__(self, problem: PersonaProblem, detail: str) -> None:
        super().__init__(f"{problem.value}: {detail}")
        self.problem = problem
        self.detail = detail


class PersonaSourceChangedError(Exception):
    """The governing document differs from every stored revision.

    Not an error in the document and not an error in the store — it is an
    authored change that has not been imported, and importing it is a deliberate
    act rather than something a seeder does because git moved. Persona changes
    are Lord Armand's alone (`03-persona.md` §10).
    """


@dataclass(frozen=True)
class ActivePersona:
    """The persona Val is currently built from, with its provenance attached."""

    id: UUID
    #: Persistence revision — counts rows.
    version: int
    #: Authored label — counts authorship. Never interchangeable with `version`.
    semantic_version: str
    content: str
    source_sha256: str
    source_path: str
    created_at: datetime
    #: None on a revision that has never been active. See `_as_persona`.
    activated_at: datetime | None
    authored_by: str

    @property
    def provenance(self) -> str:
        """One line for a log or a debug view. Both scales, never just one."""
        return (
            f"persona revision {self.version} (authored v{self.semantic_version}), "
            f"id={self.id}, source {self.source_path}@{self.source_sha256[:12]}"
        )

    def content_is_intact(self) -> bool:
        """Whether the stored content still hashes to its recorded digest.

        Cheap, and it catches the one thing the immutability trigger cannot: a
        row restored from a backup taken mid-write, or content altered by a
        superuser going around the trigger.
        """
        return digest_of(self.content) == self.source_sha256


class PersonaLoader(Protocol):
    """What the gateway needs of a persona source, and nothing more.

    A Protocol so tests can drive a fixture persona without a database while the
    running system uses `DatabasePersonaLoader`. The Protocol deliberately has no
    "or None" in its signature: there is no supported way to obtain "no persona",
    only a persona or a raised failure.
    """

    def active(self) -> ActivePersona:
        """The one active persona, or raise. Never a fallback."""
        ...


@dataclass(frozen=True)
class SeedOutcome:
    """What a seed run did, in terms that can be asserted on."""

    #: `created` | `unchanged`
    action: str
    persona: ActivePersona


_SELECT_ACTIVE = text(
    "select id, version, semantic_version, content, source_sha256, source_path, "
    "created_at, activated_at, authored_by from personas where is_active"
)

_SELECT_BY_SHA = text(
    "select id, version, semantic_version, content, source_sha256, source_path, "
    "created_at, activated_at, authored_by from personas where source_sha256 = :sha "
    "order by version desc"
)

_SELECT_BY_ID = text(
    "select id, version, semantic_version, content, source_sha256, source_path, "
    "created_at, activated_at, authored_by from personas where id = :id"
)

_INSERT = text(
    "insert into personas (version, semantic_version, content, source_sha256, source_path, "
    "is_active, activated_at, authored_by) "
    "values (:version, :semantic_version, :content, :source_sha256, :source_path, "
    ":is_active, :activated_at, :authored_by) returning id"
)

_NEXT_VERSION = text("select coalesce(max(version), 0) + 1 from personas")

_DEACTIVATE_ALL = text("update personas set is_active = false where is_active")

_ACTIVATE = text(
    "update personas set is_active = true, activated_at = now() where id = :id returning id"
)


def _as_persona(row: object) -> ActivePersona:
    """One row, typed.

    `activated_at` is NULL only on a revision that has never been active, and
    every caller here either loaded an active row or is reading one back by id.
    A never-activated revision surfaces its NULL rather than being given an
    invented instant: a time in the record for an event that did not happen is
    the kind of small fiction this schema exists to refuse.
    """
    return ActivePersona(
        id=row.id,  # type: ignore[attr-defined]
        version=row.version,  # type: ignore[attr-defined]
        semantic_version=row.semantic_version,  # type: ignore[attr-defined]
        content=row.content,  # type: ignore[attr-defined]
        source_sha256=row.source_sha256,  # type: ignore[attr-defined]
        source_path=row.source_path,  # type: ignore[attr-defined]
        created_at=row.created_at,  # type: ignore[attr-defined]
        activated_at=row.activated_at,  # type: ignore[attr-defined]
        authored_by=row.authored_by,  # type: ignore[attr-defined]
    )


class DatabasePersonaLoader:
    """The runtime authority. Reads the one active row, or refuses.

    It never chooses. There is no "newest wins" and no "first wins": if the store
    says two personas are active, the store is wrong and the honest response is
    to stop, not to pick. Selecting one would produce a Val that is coherent,
    plausible, and not the one the records support (invariant 29).
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def active(self) -> ActivePersona:
        """The active persona, or raise. Never returns a fallback."""
        try:
            with self._engine.connect() as connection:
                rows = connection.execute(_SELECT_ACTIVE).all()
        except Exception as error:  # the driver's own failure, normalised
            raise PersonaUnavailableError(
                PersonaProblem.UNREADABLE,
                "the authoritative store could not be reached, so the active persona is "
                f"unknown. Val is not assembled from memory when PostgreSQL is unavailable: "
                f"{type(error).__name__}: {str(error)[:200]}",
            ) from error

        if not rows:
            raise PersonaUnavailableError(
                PersonaProblem.NONE_ACTIVE,
                "no persona revision is active. Val does not run on a generic substitute "
                "or an embedded copy — seed the governing persona and activate it "
                "(04-layer-0.md WP-0.5).",
            )
        if len(rows) > 1:
            versions = ", ".join(str(row.version) for row in rows)
            raise PersonaUnavailableError(
                PersonaProblem.MULTIPLE_ACTIVE,
                f"{len(rows)} persona revisions are active at once (revisions {versions}). "
                "This is a data-integrity defect, not a choice to be made: selecting one "
                "would give a Val the records do not support. The single-active index "
                "should have made this impossible, so its absence is the defect to find.",
            )
        return _as_persona(rows[0])

    def by_id(self, persona_id: UUID) -> ActivePersona | None:
        """Resolve any revision, active or not — historical attribution needs this."""
        with self._engine.connect() as connection:
            row = connection.execute(_SELECT_BY_ID, {"id": persona_id}).one_or_none()
        return None if row is None else _as_persona(row)


def seed(engine: Engine, root: Path, path: str = GOVERNING_PERSONA_PATH) -> SeedOutcome:
    """Import the governing persona, idempotently.

    Three outcomes, and only one of them writes:

    - **No revision holds this document's digest, and none exists at all** —
      create revision 1 and activate it.
    - **A revision already holds this exact digest** — do nothing. Re-running is
      a no-op: no duplicate revision, no content update, no version increment.
      Idempotency is keyed on the source digest rather than on "did we run
      before", so it holds across machines and across a restored database.
    - **Revisions exist but none holds this digest** — **refuse.** The document
      has been edited since it was imported. Importing that is a deliberate act
      under `create_revision`, not something a seeder does because git moved.
      `03-persona.md` §10 reserves persona changes to Lord Armand, and a seeder
      that silently followed the file would be exercising that authority for him.
    """
    source = read_source(root, path)

    with engine.connect() as connection:
        existing = connection.execute(_SELECT_BY_SHA, {"sha": source.sha256}).all()
        total = connection.execute(text("select count(*) from personas")).scalar_one()

    if existing:
        return SeedOutcome(action="unchanged", persona=_as_persona(existing[0]))

    if total:
        raise PersonaSourceChangedError(
            f"{path} does not match any stored persona revision ({total} stored). The "
            "authored document has changed since it was imported. Seeding will not "
            "overwrite the active revision or follow the file automatically — persona "
            "changes are Lord Armand's (03-persona.md §10). Create the new revision "
            "deliberately with `create_revision(..., activate=True)`."
        )

    persona = create_revision(engine, source, activate=True, authored_by="Lord Armand")
    return SeedOutcome(action="created", persona=persona)


def create_revision(
    engine: Engine,
    source: PersonaSource,
    *,
    activate: bool,
    authored_by: str = "Lord Armand",
) -> ActivePersona:
    """Write a new immutable persona revision. Optionally make it the live one.

    The revision number is `max(version) + 1`, computed inside the same
    transaction as the insert, so two concurrent creations cannot both claim it —
    the unique constraint on `version` would refuse the second regardless, but
    failing on a constraint is a worse way to learn it than not racing.

    **Existing revisions are untouched.** This inserts; it never updates content.
    """
    with engine.begin() as connection:
        version = connection.execute(_NEXT_VERSION).scalar_one()
        new_id = connection.execute(
            _INSERT,
            {
                "version": version,
                "semantic_version": source.semantic_version,
                "content": source.content,
                "source_sha256": source.sha256,
                "source_path": source.path,
                # Activation is a second, separate step even when both are wanted
                # at once — `activate` runs in its own transaction below, so the
                # deactivate-then-activate pair is atomic on its own terms.
                "is_active": False,
                "activated_at": None,
                "authored_by": authored_by,
            },
        ).scalar_one()

    if activate:
        activate_revision(engine, new_id)

    loaded = DatabasePersonaLoader(engine).by_id(new_id)
    if loaded is None:  # pragma: no cover - the insert committed, so this cannot happen
        raise PersonaUnavailableError(
            PersonaProblem.UNREADABLE,
            f"persona revision {new_id} was written and could not be read back",
        )
    return loaded


def activate_revision(engine: Engine, persona_id: UUID) -> None:
    """Make one revision the live one, atomically.

    Deactivate-then-activate **in a single transaction**. Both halves commit or
    neither does, so a failure cannot leave the store with no active persona or
    with two — the two states the loader refuses to run on.

    The order matters as much as the atomicity: activating first would collide
    with the single-active partial index before the old row was cleared, and the
    transaction would abort on a constraint rather than doing the work.
    """
    with engine.begin() as connection:
        connection.execute(_DEACTIVATE_ALL)
        activated = connection.execute(_ACTIVATE, {"id": persona_id}).one_or_none()
        if activated is None:
            # Nothing was activated. Raising rolls the deactivation back with it,
            # so the previously active revision survives untouched.
            raise PersonaUnavailableError(
                PersonaProblem.NONE_ACTIVE,
                f"no persona revision has id {persona_id}; nothing was activated and the "
                "previous active revision is unchanged.",
            )


def verify_against_source(persona: ActivePersona, root: Path, path: str | None = None) -> list[str]:
    """Check two, run on demand: does this record still match its source document?

    Returns findings, empty when the record and the document agree. Separate from
    the runtime path by design — `04-layer-0.md` WP-0.5 requires the source check
    and the runtime check to be **independent**, and a loader that consulted the
    file on every call would collapse them into one.
    """
    source = read_source(root, path or persona.source_path)
    findings: list[str] = []

    if persona.source_sha256 != source.sha256:
        findings.append(
            f"stored digest {persona.source_sha256[:12]} does not match "
            f"{source.path}, now {source.sha256[:12]}. The authored document has changed "
            "since this revision was imported; a new revision is required."
        )
    if persona.content != source.content:
        findings.append(
            f"stored content differs from {source.path} by "
            f"{abs(len(persona.content) - len(source.content))} characters."
        )
    if persona.semantic_version != source.semantic_version:
        findings.append(
            f"stored authored version {persona.semantic_version} does not match the "
            f"document's {source.semantic_version}."
        )
    if not persona.content_is_intact():
        findings.append(
            "stored content does not hash to its own recorded digest — the row has been "
            "altered since it was written, around the immutability trigger."
        )
    return findings
