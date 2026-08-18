"""Project-scoped recall over persisted conversation — WP-0.7.

`04-layer-0.md` WP-0.7 requires that *"retrieval is project-scoped. A query in
project A returns nothing from project B. Test with deliberately similar content
in both."*

## Isolation is a `WHERE` clause, never a filter afterwards

The project restriction is inside the query, applied before anything is ranked:

    join conversations c on c.id = m.conversation_id
    where c.project_id = :project_id        -- or `is null`, for no-project
      and to_tsvector('english', m.content) @@ plainto_tsquery('english', :q)
    order by ts_rank(...) desc, m.created_at desc

**Search-then-remove is the shape this deliberately does not have.** Ranking
globally and discarding Project B afterwards would mean the house had already
assembled a result set containing B, and every later change — a limit applied a
line too early, a caching layer, a debug log, an ordering tweak — becomes an
opportunity for B to survive the trip. Filtering first means B was never
selected, so there is no moment at which it existed to leak.

`limit` is applied to the already-restricted set for the same reason: a limit
over a global ranking would let a strong Project B match consume the budget and
starve Project A of its own history without any row from B ever being returned.
That is a leak in effect even when it is not one in content.

## The two scopes are two queries, not one query with a flag

`ResolvedProject` searches `c.project_id = :id`. `ExplicitNoProject` searches
`c.project_id is null`. They are separate SQL because `= NULL` is never true in
SQL and a single parameterised comparison would silently return nothing for the
no-project case — failing closed, but for the wrong reason, and looking like
"there is no history" rather than "this query cannot express what you asked".

**No-project retrieves only no-project.** A project's material never reaches an
explicit-no-project exchange, and no-project material never reaches a project's.
The governing documents do not permit mixing, so this does not.

## What retrieval is *for*

Retrieved conversation is **source material**, not established truth. It says
what was said, and being said is not being decided. This module returns records
carrying full provenance — project, conversation, message, sequence, role — so
the caller can show where a claim came from, and `val_gateway.context` frames it
as history rather than as instruction. Nothing here promotes anything to canon;
that machinery belongs to a later layer and is not built early.

## Why full text and not embeddings

Chosen deliberately, recorded in `VAL_Open_Decisions.md` and migration `0008`.
The governing criterion asks for project-scoped retrieval that lets Val recall
prior context; it does not ask for semantic similarity. Embeddings would require
a new provider, a new egress route for Protected conversation content, an
eligibility ruling, and embedding-version governance — four decisions, not an
implementation detail. PostgreSQL full text is deterministic, needs no network
call, and cannot send a single word of a conversation anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Engine, text

from val_domain.conversation import StoredRole
from val_domain.project import ProjectScope, ResolvedProject

#: ## Why the query matches *any* term rather than all of them
#:
#: `plainto_tsquery` joins its lexemes with `&`, so `"what colour was the
#: lighthouse lens"` would only match a message containing every one of those
#: words. Real questions almost never repeat the wording of the answer, and under
#: AND semantics recall returned nothing for exactly the queries it exists to
#: serve — confirmed against the database before this was changed.
#:
#: So the operators are rewritten to `|` and relevance is left to `ts_rank`,
#: which is the part that decides *which* of the matching messages come back. A
#: message sharing one strong term ranks below one sharing four; the `limit`
#: keeps the tail out.
#:
#: **The rewrite is safe because `plainto_tsquery` has already sanitised the
#: input.** It is not a formatting shortcut around user text: it parses the query
#: and emits nothing but quoted lexemes joined by `&` — every operator,
#: quotation mark and semicolon in the input is discarded. Verified directly:
#:
#:     plainto_tsquery('english', $$a & b | c ! d <-> e ' " ; drop table x --$$)
#:     ->  'b' & 'c' & 'd' & 'e' & 'drop' & 'tabl' & 'x'
#:
#: There is therefore no `&` in that output that came from the user, and nothing
#: the replacement could turn into syntax. The cast back to `tsquery` would fail
#: loudly rather than execute anything if that ever stopped being true.
#:
#: **The two retrieval queries, written out in full.**
#:
#: Deliberately not composed from shared fragments. This is the code that has to
#: be *read* to confirm the criterion — "a query in project A returns nothing
#: from project B" — and a reader checking that should see one whole statement,
#: not reassemble it from four constants and trust the concatenation. The
#: duplication between them is the price of each being auditable alone.
#:
#: In both: the project restriction and the relevance test are in the same
#: `where`, so ranking only ever sees rows already inside the scope. `limit`
#: applies to that restricted set.
#:
#: `m.role in ('user', 'val')` excludes stored `system` rows — application
#: bookkeeping is not conversation, and recalling it would put the house's own
#: notes into Val's mouth.
#:
#: `m.conversation_id is distinct from :exclude` keeps the current conversation
#: out: its history is assembled in full and in order by the caller, so a message
#: arriving through both paths would be injected twice.
_IN_PROJECT = text(
    "select m.id, m.conversation_id, m.role, m.content, m.sequence, "
    "       c.project_id, c.title, "
    "       ts_rank(to_tsvector('english', m.content), "
    "               replace(plainto_tsquery('english', :query)::text, "
    "                       '&', '|')::tsquery) as rank "
    "  from messages m "
    "  join conversations c on c.id = m.conversation_id "
    " where c.project_id = :project_id "
    "   and m.conversation_id is distinct from :exclude "
    "   and m.role in ('user', 'val') "
    "   and to_tsvector('english', m.content) "
    "       @@ replace(plainto_tsquery('english', :query)::text, "
    "                  '&', '|')::tsquery "
    " order by rank desc, m.created_at desc, m.id "
    " limit :limit"
)

#: The explicit-no-project half. `c.project_id is null` rather than a bound
#: parameter compared with `=`: in SQL `= NULL` is never true, so one
#: parameterised query serving both scopes would return nothing here — failing
#: closed, but silently, and looking like "no history exists" rather than "this
#: query cannot ask what you asked".
_IN_NO_PROJECT = text(
    "select m.id, m.conversation_id, m.role, m.content, m.sequence, "
    "       c.project_id, c.title, "
    "       ts_rank(to_tsvector('english', m.content), "
    "               replace(plainto_tsquery('english', :query)::text, "
    "                       '&', '|')::tsquery) as rank "
    "  from messages m "
    "  join conversations c on c.id = m.conversation_id "
    " where c.project_id is null "
    "   and m.conversation_id is distinct from :exclude "
    "   and m.role in ('user', 'val') "
    "   and to_tsvector('english', m.content) "
    "       @@ replace(plainto_tsquery('english', :query)::text, "
    "                  '&', '|')::tsquery "
    " order by rank desc, m.created_at desc, m.id "
    " limit :limit"
)


@dataclass(frozen=True)
class RecalledMessage:
    """One retrieved message, with enough provenance to be checked.

    WP-0.7 §13 requires a retrieval result be reconstructable — that the house
    can say which persisted messages were selected for a response. Every field
    needed to find the original row is here, so a test can assert on exact ids
    rather than on the text having appeared somewhere.

    `project_id` rides along even though the query already restricted it: an
    isolation test that asserts on the *returned* project has checked the answer,
    while one that trusts the query has checked the question.
    """

    message_id: UUID
    conversation_id: UUID
    conversation_title: str
    project_id: UUID | None
    role: StoredRole
    content: str
    sequence: int
    rank: float


class CrossProjectLeakError(Exception):
    """Retrieval returned material from outside the requested scope.

    This should be unreachable: the restriction is in the query. It exists
    because *"a query in project A returns nothing from project B"* is the
    criterion most costly to get wrong and the one whose failure is quietest —
    a leak looks exactly like Val being well informed. Failing loudly is the
    only outcome that cannot be mistaken for working.
    """

    def __init__(self, expected: UUID | None, found: list[RecalledMessage]) -> None:
        self.expected = expected
        self.found = tuple(found)
        scopes = sorted({str(item.project_id) for item in found})
        super().__init__(
            f"retrieval for project {expected} returned {len(found)} message(s) from "
            f"{', '.join(scopes)}. The project restriction is inside the query, so this "
            "means the query itself was changed. No results are returned."
        )


#: How many prior messages one exchange may recall. Deliberately small: WP-0.7
#: §14 forbids injecting everything ever written in a project, and a bound that
#: is a constant is a bound somebody can reason about. It is applied *after* the
#: project restriction, so it can never be spent on another project's material.
DEFAULT_LIMIT = 6


def recall(
    engine: Engine,
    *,
    scope: ProjectScope,
    query: str,
    exclude_conversation: UUID | None = None,
    limit: int = DEFAULT_LIMIT,
) -> tuple[RecalledMessage, ...]:
    """Prior conversation from this scope, most relevant first.

    Returns an empty tuple when nothing matches, when the query has no
    searchable terms, or when the scope has no prior conversation. Empty is an
    ordinary outcome — an exchange with nothing to recall proceeds on its
    same-conversation history alone.

    `exclude_conversation` keeps the current conversation out of the result. Its
    messages are assembled in full and in order by the caller, and a message that
    arrived through both paths would appear twice in the prompt.
    """
    if not query.strip():
        return ()

    statement = _IN_PROJECT if isinstance(scope, ResolvedProject) else _IN_NO_PROJECT
    parameters: dict[str, object] = {
        "query": query,
        "exclude": exclude_conversation,
        "limit": limit,
    }
    if isinstance(scope, ResolvedProject):
        parameters["project_id"] = scope.project_id

    with engine.connect() as connection:
        rows = connection.execute(statement, parameters).all()

    recalled = tuple(
        RecalledMessage(
            message_id=row.id,
            conversation_id=row.conversation_id,
            conversation_title=row.title,
            project_id=row.project_id,
            role=StoredRole(row.role),
            content=row.content,
            sequence=row.sequence,
            rank=float(row.rank),
        )
        for row in rows
    )

    # A second, independent check on the thing this module exists to guarantee.
    # The query above is correct; this asserts it *was* correct on the rows that
    # came back, so a future edit to the SQL cannot quietly widen the scope
    # without a test — or a running system — noticing immediately.
    expected = scope.project_id
    trespassers = [item for item in recalled if item.project_id != expected]
    if trespassers:
        raise CrossProjectLeakError(expected, trespassers)

    return recalled
