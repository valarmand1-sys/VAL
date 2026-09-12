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

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Engine, text

from val_domain.conversation import StoredRole
from val_domain.project import ProjectScope, ResolvedProject
from val_policy.recall import (
    RECALL_MESSAGE_LIMIT,
    RECALL_TOKEN_BUDGET_DEFAULT,
    RecallSelection,
    select_within_budget,
)

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


#: House Recall (ruling, 12 September 2026): every stored conversation except
#: the current one, across projects and the unassigned pool, joined to
#: `projects` for the source name. No scope predicate, deliberately — this is
#: the one authorised cross-project path, and it is reachable only through
#: `house_recall_with_state`, which only `gate_house_recall` opens.
_ACROSS_HOUSE = text(
    "select m.id, m.conversation_id, m.role, m.content, m.sequence, m.created_at, "
    "       c.project_id, c.title, p.name as project_name, "
    "       ts_rank(to_tsvector('english', m.content), "
    "               replace(plainto_tsquery('english', :query)::text, "
    "                       '&', '|')::tsquery) as rank "
    "  from messages m "
    "  join conversations c on c.id = m.conversation_id "
    "  left join projects p on p.id = c.project_id "
    " where m.conversation_id is distinct from :exclude "
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
    #: House Recall provenance (ruling, 12 September 2026), additive: the source
    #: project's name (None for an unassigned conversation), the message's stored
    #: timestamp, and which path retrieved it — ``project_recall`` (the automatic,
    #: scoped path) or ``house_recall`` (the explicitly triggered cross-conversation
    #: path). Ordinary recall leaves the defaults.
    project_name: str | None = None
    created_at: datetime | None = None
    retrieval_path: str = "project_recall"

    @property
    def source_scope(self) -> str:
        """Where this came from, in the envelope's words: a named project or unassigned."""
        if self.project_id is None:
            return "unassigned"
        return (
            f"project: {self.project_name}" if self.project_name else f"project: {self.project_id}"
        )


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
DEFAULT_LIMIT = RECALL_MESSAGE_LIMIT

#: Ruling, 7 September 2026: a soft token budget alongside the count. Read from
#: the environment so it is configuration, not a buried literal.
RECALL_BUDGET_SETTING = "VAL_RECALL_TOKEN_BUDGET"

_LOGGER = logging.getLogger("val.recall")


def token_budget() -> int:
    """The soft recall budget in estimated tokens: `VAL_RECALL_TOKEN_BUDGET`, else 16,000."""
    raw = os.environ.get(RECALL_BUDGET_SETTING, "").strip()
    if not raw:
        return RECALL_TOKEN_BUDGET_DEFAULT
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{RECALL_BUDGET_SETTING} must be a positive integer, not {raw!r}")
    return value


def recall(
    engine: Engine,
    *,
    scope: ProjectScope,
    query: str,
    exclude_conversation: UUID | None = None,
    limit: int = DEFAULT_LIMIT,
    budget: int | None = None,
) -> tuple[RecalledMessage, ...]:
    """`recall_selection`, returning the admitted messages alone."""
    return recall_selection(
        engine,
        scope=scope,
        query=query,
        exclude_conversation=exclude_conversation,
        limit=limit,
        budget=budget,
    )[0]


def recall_selection(
    engine: Engine,
    *,
    scope: ProjectScope,
    query: str,
    exclude_conversation: UUID | None = None,
    limit: int = DEFAULT_LIMIT,
    budget: int | None = None,
) -> tuple[tuple[RecalledMessage, ...], RecallSelection | None]:
    """Prior conversation from this scope, most relevant first, within budget.

    Returns an empty tuple when nothing matches, when the query has no
    searchable terms, or when the scope has no prior conversation. Empty is an
    ordinary outcome — an exchange with nothing to recall proceeds on its
    same-conversation history alone.

    `exclude_conversation` keeps the current conversation out of the result. Its
    messages are assembled in full and in order by the caller, and a message that
    arrived through both paths would appear twice in the prompt.

    Ruling, 7 September 2026: the ranked candidates then pass the hybrid
    count-and-token bound of `val_policy.recall` — the top candidate always,
    whole; each next candidate in rank order only if it fits the remaining
    budget; stop at the first that does not; never truncate. Every decision
    is logged so the selection can be reconstructed.
    """
    if not query.strip():
        return (), None

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

    selection = select_within_budget(
        recalled, budget=token_budget() if budget is None else budget, limit=limit
    )
    _LOGGER.info(
        "recall selection: %s",
        json.dumps(
            {
                "budget": selection.budget,
                "admitted_tokens": selection.admitted_tokens,
                "candidates": [
                    {
                        "rank_position": decision.rank_position,
                        "message_id": str(recalled[decision.rank_position - 1].message_id),
                        "conversation_id": str(
                            recalled[decision.rank_position - 1].conversation_id
                        ),
                        "sequence": recalled[decision.rank_position - 1].sequence,
                        "rank": recalled[decision.rank_position - 1].rank,
                        "characters": len(recalled[decision.rank_position - 1].content),
                        "estimated_tokens": decision.estimated_tokens,
                        "admitted": decision.admitted,
                        "reason": decision.reason,
                    }
                    for decision in selection.decisions
                ],
            }
        ),
    )
    return tuple(recalled[position - 1] for position in selection.admitted_positions), selection


# --- prior-record state (ruling, 9 September 2026) ---------------------------


@dataclass(frozen=True)
class RecallOutcome:
    """What retrieval actually did for this call, typed, never collapsed.

    Ruled 9 September 2026 after the v1.5 qualification reveal: an empty record
    reached the response model as silence, and silence does not distinguish
    "nothing available" from "not supplied". The states are:

    - ``returned`` — retrieval ran and admitted ``len(items)`` excerpts (> 0);
    - ``zero`` — retrieval ran and found nothing to admit;
    - ``not_run`` — retrieval was not attempted (the query had nothing searchable);
    - ``unavailable`` — retrieval was attempted and failed; ``detail`` names the
      failure class. The call proceeds without recall rather than halting
      (`00-charter.md` invariant 25), and the envelope says so.

    A ``zero`` is a fact about the record; the other three are facts about the
    call. Only ``returned`` and ``zero`` may be read as "the record was consulted".
    """

    state: str
    items: tuple[RecalledMessage, ...] = ()
    detail: str | None = None


#: The deterministic `not_run` reasons, in precedence order (ruled 10 September 2026).
NOT_RUN_REASONS = ("no_project_scope", "tier_one", "tier_two", "under_specified_query")


def recall_with_state(
    engine: Engine,
    *,
    scope: ProjectScope,
    query: str,
    exclude_conversation: UUID | None = None,
    limit: int = DEFAULT_LIMIT,
    budget: int | None = None,
) -> RecallOutcome:
    """`recall_selection`, with the outcome typed instead of flattened into a tuple.

    A cross-project leak is not a retrieval failure: it is the one error this
    module exists to raise, and it still raises. A query with nothing searchable
    is ``not_run`` / ``under_specified_query``: retrieval was not attempted
    because no usable query could be formed. A ranking whose top candidate alone
    exceeded the aggregate budget is ``zero`` with the detail
    ``top_candidate_exceeds_budget`` — retrieval ran and admitted nothing, and
    the reason is stated rather than left as an unexplained zero.
    """
    if not query.strip():
        return RecallOutcome(state="not_run", detail="under_specified_query")
    try:
        items, selection = recall_selection(
            engine,
            scope=scope,
            query=query,
            exclude_conversation=exclude_conversation,
            limit=limit,
            budget=budget,
        )
    except CrossProjectLeakError:
        raise
    except Exception as error:  # the store or the driver failing, normalised
        _LOGGER.warning(
            "recall unavailable for this call (%s); proceeding without retrieved material",
            type(error).__name__,
        )
        return RecallOutcome(state="unavailable", detail=type(error).__name__)
    if items:
        return RecallOutcome(state="returned", items=items)
    if selection is not None and selection.top_candidate_exceeded:
        return RecallOutcome(state="zero", detail="top_candidate_exceeds_budget")
    return RecallOutcome(state="zero")


def house_recall_with_state(
    engine: Engine,
    *,
    query: str,
    exclude_conversation: UUID | None = None,
    exclude_message_ids: frozenset[UUID] = frozenset(),
    limit: int = DEFAULT_LIMIT,
    budget: int | None = None,
) -> RecallOutcome:
    """House Recall: relevant prior conversation from anywhere in the House's record.

    Ruling, 12 September 2026. The explicitly triggered path beside automatic
    recall: it searches every stored conversation except the current one,
    across projects and the unassigned pool, with the same ranking, limit and
    aggregate budget as automatic recall, and returns excerpts that carry their
    provenance — source project or unassigned, conversation, message, sequence,
    role, timestamp — marked ``retrieval_path = "house_recall"``. Messages
    already admitted by automatic recall (`exclude_message_ids`) are not
    admitted twice. It reads; it never writes, and it never touches the current
    conversation's attribution. The same state vocabulary as `RecallOutcome`.
    """
    if not query.strip():
        return RecallOutcome(state="not_run", detail="under_specified_query")
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                _ACROSS_HOUSE,
                {"query": query, "exclude": exclude_conversation, "limit": limit},
            ).all()
    except Exception as error:  # the store or the driver failing, normalised
        _LOGGER.warning(
            "house recall unavailable for this call (%s); proceeding without it",
            type(error).__name__,
        )
        return RecallOutcome(state="unavailable", detail=type(error).__name__)
    candidates = tuple(
        RecalledMessage(
            message_id=row.id,
            conversation_id=row.conversation_id,
            conversation_title=row.title,
            project_id=row.project_id,
            role=StoredRole(row.role),
            content=row.content,
            sequence=row.sequence,
            rank=float(row.rank),
            project_name=row.project_name,
            created_at=row.created_at,
            retrieval_path="house_recall",
        )
        for row in rows
        if row.id not in exclude_message_ids
    )
    if not candidates:
        return RecallOutcome(state="zero")
    selection = select_within_budget(
        candidates, budget=token_budget() if budget is None else budget, limit=limit
    )
    _LOGGER.info(
        "house recall selection: %s",
        json.dumps(
            {
                "budget": selection.budget,
                "admitted_tokens": selection.admitted_tokens,
                "candidates": [
                    {
                        "rank_position": decision.rank_position,
                        "message_id": str(candidates[decision.rank_position - 1].message_id),
                        "source_scope": candidates[decision.rank_position - 1].source_scope,
                        "admitted": decision.admitted,
                        "reason": decision.reason,
                    }
                    for decision in selection.decisions
                ],
            }
        ),
    )
    admitted = tuple(candidates[d.rank_position - 1] for d in selection.decisions if d.admitted)
    if admitted:
        return RecallOutcome(state="returned", items=admitted)
    if selection.top_candidate_exceeded:
        return RecallOutcome(state="zero", detail="top_candidate_exceeds_budget")
    return RecallOutcome(state="zero")
