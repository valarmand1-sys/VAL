"""One user exchange, from input to attributed answer — or to a question.

This is the application boundary WP-0.6 asks for: the place where scope becomes
a settled fact *before* anything protected is sent anywhere. The order is
deliberate and each step is a gate on the next:

    user input
      → Restricted preflight            content that must never leave, refused
      → project resolution              deterministic, local, no provider
      → if unresolved: ask              no model call, no attribution, no row
      → active persona                  the runtime authority (WP-0.5)
      → context assembly                persona whole, exactly once
      → gateway routing                 eligibility, budget, provider
      → attributed persistence          one project id, consistently

**Why resolution comes before the persona and the provider, not after.**
`00-charter.md` invariant 16 — *ambiguous or unresolved project context blocks
protected or consequential action* — and invariant 17 puts unreleased creative
IP in Protected. An exchange whose scope is unknown may well be Protected
project material, so sending it to a cloud model to work out which project it
belongs to would be doing the thing the invariant forbids, in order to find out
whether the invariant applies. The question is asked locally instead.

**A clarification is not a model call.** It is deterministic application text
assembled from the catalogue, so no provider is contacted and **no `model_calls`
row is written** — writing one would assert a call that never happened, which is
the same error `cost_certainty` exists to prevent on the accounting side.

**Ambiguity is never persisted.** `converse` takes a `ProjectScope`, a union
that does not include `AmbiguousProject`, so an unresolved exchange cannot be
attributed even by a caller who wants to. The type is the guarantee.
"""

from dataclasses import dataclass
from uuid import UUID

from val_domain.gateway import Classification, GatewayResponse, Message, TaskType
from val_domain.project import (
    AmbiguityReason,
    AmbiguousProject,
    ProjectResolution,
    ProjectScope,
)
from val_gateway.gateway import Gateway
from val_gateway.projects import ProjectSession
from val_policy.project_resolution import (
    InconsistentConversationScopeError,
    ProjectCatalogue,
    ProjectSignals,
    resolve,
)
from val_policy.restricted import preflight, refusal_message


@dataclass(frozen=True)
class ClarificationNeeded:
    """The exchange stopped to ask. Nothing was sent and nothing was recorded.

    Returned rather than raised: needing to ask which project something belongs
    to is an ordinary conversational outcome, not an error, and a caller that
    forgets to handle an exception would proceed on nothing.
    """

    question: str
    reason: AmbiguityReason
    #: What the user's answer will be matched against, so the caller does not
    #: have to re-derive the candidate set to interpret the reply.
    candidates: tuple[str, ...] = ()

    @property
    def project_id(self) -> None:
        """No attribution. There is nothing here to file anything under."""
        return None


#: What an exchange produces: an answer, or the question that must come first.
ExchangeOutcome = GatewayResponse | ClarificationNeeded


class RestrictedContentRefusedError(Exception):
    """Obvious Restricted material was found before anything left the machine."""


def resolve_scope(
    signals: ProjectSignals,
    catalogue: ProjectCatalogue,
    session: ProjectSession | None = None,
) -> ProjectResolution:
    """Settle scope from signals, the session, and the catalogue.

    The session contributes only where the signals are silent about it, so an
    explicit selection in this interaction still outranks whatever was selected
    earlier — which is what makes switching work without special-casing it.
    """
    if session is not None and not signals.session_is_set:
        signals = ProjectSignals(
            supplied_project_id=signals.supplied_project_id,
            explicit_selection=signals.explicit_selection,
            explicit_no_project=signals.explicit_no_project,
            conversation_project_id=signals.conversation_project_id,
            conversation_is_established=signals.conversation_is_established,
            session_project_id=session.project_id,
            session_is_set=session.is_set and not session.is_explicit_none,
            mentioned_reference=signals.mentioned_reference,
        )
        # A session set to explicit none is a decision, and it stands until the
        # user changes it — otherwise every unspecified exchange after choosing
        # "no project" would go back to asking.
        if session.is_explicit_none and _nothing_else_said(signals):
            scope = session.scope(catalogue)
            if scope is not None:
                return scope

    try:
        return resolve(signals, catalogue)
    except InconsistentConversationScopeError as broken:
        # Not a question the user can answer, so it becomes one they can act on.
        return AmbiguousProject(
            reason=AmbiguityReason.INCONSISTENT_CONVERSATION_STATE,
            question=(
                "This conversation's project no longer exists, so I cannot tell what "
                f"it is scoped to ({broken.project_id}). I have filed nothing. Which "
                "project should it be?"
            ),
        )


def _nothing_else_said(signals: ProjectSignals) -> bool:
    """Whether any signal other than the session speaks to scope."""
    return (
        signals.supplied_project_id is None
        and signals.explicit_selection is None
        and signals.mentioned_reference is None
        and not signals.conversation_is_established
        and not signals.explicit_no_project
    )


def exchange(
    gateway: Gateway,
    messages: tuple[Message, ...],
    signals: ProjectSignals,
    catalogue: ProjectCatalogue,
    *,
    session: ProjectSession | None = None,
    classification: Classification = Classification.PROTECTED,
    task_type: TaskType = TaskType.CONVERSATION,
    conversation_id: UUID | None = None,
    message_id: UUID | None = None,
    max_output_tokens: int = 4096,
) -> ExchangeOutcome:
    """Run one exchange, in the order the invariants require.

    Returns a `GatewayResponse` when scope was settled and the provider
    answered, or a `ClarificationNeeded` when it was not — in which case no
    provider was contacted, no `model_calls` row exists, and no project was
    attributed to anything.
    """
    # 1. Restricted first. Content that must never leave the machine is refused
    #    before it is even worth asking which project it belongs to.
    parts = tuple(message.content for message in messages)
    finding = preflight(parts)
    if finding is not None:
        raise RestrictedContentRefusedError(refusal_message(finding))

    # 2. Scope, deterministically and locally.
    resolution = resolve_scope(signals, catalogue, session)

    # 3. Unresolved stops here. No provider, no row, no attribution.
    if isinstance(resolution, AmbiguousProject):
        return ClarificationNeeded(
            question=resolution.question,
            reason=resolution.reason,
            candidates=tuple(project.name for project in resolution.candidates),
        )

    # 4. Settled. `resolution` is now a `ProjectScope` by elimination, and the
    #    signature below will not accept anything else.
    scope: ProjectScope = resolution
    return gateway.converse(
        messages,
        scope=scope,
        classification=classification,
        task_type=task_type,
        conversation_id=conversation_id,
        message_id=message_id,
        max_output_tokens=max_output_tokens,
    )
