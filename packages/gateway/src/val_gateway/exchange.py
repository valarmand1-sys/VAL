"""Scope resolution at the application boundary — WP-0.6.

**This module no longer talks to a provider.** *Corrected 18 August 2026, after
independent source review of `VAL_Source_Snapshot_d137925.zip`.*

It used to export an `exchange()` function that resolved scope and then called
`gateway.converse()` directly. That was correct for WP-0.6, when an exchange
held nothing and there was nothing to persist. WP-0.7 made it a defect: a caller
choosing this path got a real `TaskType.CONVERSATION` provider call with **no
conversation created, no user message persisted, no reply persisted, and no
durable provenance** — the whole of WP-0.7 bypassed, by picking the older of two
functions that both looked like the front door.

Review found it while the module still described itself as *the* application
exchange boundary. It is not. **`val_gateway.loop.send` is the only application
path that may initiate conversation inference**, and it is the only one that
persists what it sends.

What remains here is what was always deterministic and provider-free:

- `resolve_scope` — folds session state into signals and settles scope, or
  produces the question that must be asked first;
- `ClarificationNeeded` — an unresolved exchange as an ordinary outcome rather
  than an exception;
- `RestrictedContentRefusedError` — raised when content must never leave.

None of it can reach a model: this module imports no `Gateway`, and a boundary
test asserts that it never will again. Keeping the helpers is not "keeping the
old function for compatibility" — there is no longer a compatibility path by
which a conversation can happen without being recorded.
"""

from dataclasses import dataclass, replace

from val_domain.project import (
    AmbiguityReason,
    AmbiguousProject,
    ProjectCandidate,
    ProjectResolution,
)
from val_gateway.projects import ProjectSession
from val_policy.project_resolution import (
    InconsistentConversationScopeError,
    ProjectCatalogue,
    ProjectSignals,
    resolve,
)


@dataclass(frozen=True)
class ClarificationNeeded:
    """The exchange stopped to ask. Nothing was sent and nothing was recorded.

    Returned rather than raised: needing to ask which project something belongs
    to is an ordinary conversational outcome, not an error, and a caller that
    forgets to handle an exception would proceed on nothing.
    """

    question: str
    reason: AmbiguityReason
    #: The projects the user is being asked to choose between, **with stable
    #: identity**. Corrective round, 18 August 2026: this carried display names
    #: only, so two projects both called `Winter Light` arrived as
    #: `("Winter Light", "Winter Light")` — a question the caller could put and
    #: could not interpret the answer to.
    #:
    #: Only the candidates. The unrelated catalogue is never exposed; a payload
    #: that recites every project makes the caller do the narrowing this module
    #: was supposed to have done.
    candidates: tuple[ProjectCandidate, ...] = ()

    @property
    def project_id(self) -> None:
        """No attribution. There is nothing here to file anything under."""
        return None


class RestrictedContentRefusedError(Exception):
    """Obvious Restricted material was found before anything left the machine."""


def resolve_scope(
    signals: ProjectSignals,
    catalogue: ProjectCatalogue,
    session: ProjectSession | None = None,
) -> ProjectResolution:
    """Settle scope from signals, the session, and the catalogue.

    The session is folded into the signals **as a pair**, exactly the way the
    conversation is: `session_is_set` says a decision exists, and
    `session_project_id` says whether that decision names a project or declines
    one. The resolver then treats the two symmetrically and this function does
    no deciding of its own.

    **Corrected 18 August 2026.** It previously erased an explicit-none session
    from the signals — `session_is_set=session.is_set and not
    session.is_explicit_none` — and restored it only through a special case that
    fired when *nothing else had been said*. So the moment any other signal
    appeared the session's decision simply vanished: a trusted reference to
    another project resolved outright instead of asking, and an untrusted
    candidate produced the wrong question. A decision that survives only in the
    absence of other input is not a decision the system is holding.

    Signals the caller stated explicitly always win over the session object, so
    a caller that supplies its own session pair is not overridden.
    """
    if session is not None and not signals.session_is_set:
        signals = replace(
            signals,
            session_project_id=session.project_id,
            session_is_set=session.is_set,
        )

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
