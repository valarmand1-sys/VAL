"""The Model Gateway itself (`01-architecture.md` §5.1).

Every model call enters here and nothing else calls a provider. There are two
entrances and they are deliberately not equivalent:

- **`complete(request)`** — normal routing. The gateway selects the
  configuration. This is what application code uses, and it is the reason this
  is a gateway rather than a shared HTTP client: a component that has to name
  its own provider is a component that can name the wrong one.
- **`converse(messages, ...)`** — the normal Val conversational path. It loads
  the active persona from PostgreSQL, assembles it whole into the request, and
  routes. **This is what an application uses to talk to Val**, and it is the only
  entrance that guarantees her persona is present: `complete` will faithfully
  send whatever it is given, including a request with no persona in it.
- **`complete_with_configuration(request, config)`** — the deliberate explicit
  path, for the strip step of `04-layer-0.md` §4 (which must run on a named
  cheapest route) and for tests that pin one provider. It is **not** a bypass:
  the configuration must be the registry's own entry, identical field for field,
  and it passes every admission, eligibility, and budget check the routed path
  applies. Handing it a fabricated `ModelConfig` naming an arbitrary provider and
  model gets a normalized refusal, not a call.

In order, per call, each step failing before the next begins:

1. **Restricted content is refused**, two ways, before any route is even
   selected, and no `model_calls` row is written either way — it was never a
   call (`04-layer-0.md` §1.1, WP-0.4). The caller's stated classification is
   honoured, *and* the content is scanned locally for obvious credentials and
   personal data before anything leaves the machine (`val_policy.restricted`).
   The second check exists because the first is only as good as the caller's own
   knowledge.
2. **Route selection.** Enabled, admitted for Layer 0, eligible for this
   classification, adapter present, and affordable — in that order, with cost
   ranking only what has already survived (`val_policy.routing`).
3. **Budget, before the call, against the call.** A reservation for the most
   this call may consume is taken atomically in PostgreSQL. Refused means the
   provider is never contacted (`00-charter.md` invariant 24).
4. **The call**, through the adapter, with every provider failure arriving as
   one normalized error.
5. **Settlement.** The reservation closes against what was actually consumed,
   and the `model_calls` row records the cost as known or as explicitly unknown
   — never as a zero the implementation cannot support.

Startup is the other half. `check_startup` refuses to start on any eligibility
violation, because a check that only fires when the call is made is not the
guarantee `04-layer-0.md` §1.1 claims.
"""

import logging
import time
from collections.abc import Callable
from datetime import date
from uuid import UUID

from val_domain.gateway import (
    CallStatus,
    Classification,
    CostCertainty,
    GatewayError,
    GatewayErrorKind,
    GatewayRequest,
    GatewayResponse,
    Message,
    ModelConfig,
    TaskType,
    TerminalState,
    TurnReference,
)
from val_domain.project import (
    ProjectAttribution,
    ProjectScope,
)
from val_domain.registry import active, by_id, fallback_for, stale_rates
from val_gateway.context import assemble
from val_gateway.ledger import BudgetLedger, Refusal, Reservation
from val_gateway.persona import PersonaLoader, PersonaProblem, PersonaUnavailableError
from val_policy.budget import (
    admits,
    ceiling_message,
    effective_rates,
    limit_overrun,
    maximum_cost,
    no_affordable_route_message,
)
from val_policy.eligibility import refusal_for, startup_violations
from val_policy.restricted import preflight, refusal_message
from val_policy.routing import attempt_order, is_admitted, is_eligible
from val_providers.base import ProviderAdapter

_LOGGER = logging.getLogger("val.gateway")

#: Failures that justify trying the next route. A content refusal is deliberately
#: absent: a provider declining to answer is an answer, and re-asking elsewhere
#: until someone complies is shopping for permission. `INVALID_REQUEST` is absent
#: for the same reason — a malformed request will be malformed everywhere, and
#: retrying it just spends money to be told so twice.
RETRYABLE = frozenset(
    {
        GatewayErrorKind.TIMEOUT,
        GatewayErrorKind.RATE_LIMIT,
        GatewayErrorKind.PROVIDER_ERROR,
        GatewayErrorKind.AUTHENTICATION,
        # A route that does not fit in the remaining ceiling is not a failure of
        # the request, and a cheaper eligible route may still fit. Every
        # candidate re-reserves atomically on its own account, so moving on
        # cannot overspend — it can only find something affordable or run out.
        GatewayErrorKind.BUDGET_EXCEEDED,
    }
)


def _log_block(message: str) -> None:
    """Default observer for a blocked request: the application log."""
    _LOGGER.warning("%s", message)


#: What the gateway records for one call. The caller supplies the writer, so this
#: package never imports a database driver and stays testable without one. It
#: returns the new row's id so the reservation can point at the call it paid for.
CallRecorder = Callable[["CallRecord"], UUID | None]


class CallRecord:
    """One `model_calls` row, assembled by the gateway and handed to the writer.

    `tokens_in`, `tokens_out`, and `cost_usd` are None exactly when
    `cost_certainty` is `UNKNOWN`. There is no combination that records a zero
    for a call whose cost was never established — the database refuses it too.
    """

    def __init__(
        self,
        *,
        model_config_id: UUID,
        slug: str,
        provider: str,
        model_identifier: str,
        tokens_in: int | None,
        tokens_out: int | None,
        cost_usd: float | None,
        cost_certainty: CostCertainty,
        terminal_state: str,
        project_id: UUID | None,
        project_attribution: ProjectAttribution,
        task_type: str,
        conversation_id: UUID | None,
        message_id: UUID | None,
        persona_id: UUID | None,
        latency_ms: int,
        provider_request_id: str | None,
        status: CallStatus,
    ) -> None:
        self.model_config_id = model_config_id
        self.slug = slug
        self.provider = provider
        self.model_identifier = model_identifier
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.cost_usd = cost_usd
        self.cost_certainty = cost_certainty
        self.terminal_state = terminal_state
        self.project_id = project_id
        self.project_attribution = project_attribution
        self.task_type = task_type
        self.conversation_id = conversation_id
        self.message_id = message_id
        self.persona_id = persona_id
        self.latency_ms = latency_ms
        self.provider_request_id = provider_request_id
        self.status = status


def compute_cost(config: ModelConfig, tokens_in: int, tokens_out: int) -> float:
    """The settled cost of a completed call, at the rates that actually applied.

    Uses `effective_rates`, the same function the pre-call bound prices with —
    closure pass, 18 August 2026 — so a call whose input crossed a provider's
    long-context threshold settles at the multiplied rates the provider bills,
    and the estimator and the settlement cannot disagree about what a token
    costs.
    """
    rate_in, rate_out = effective_rates(config, tokens_in)
    return round((tokens_in * rate_in + tokens_out * rate_out) / 1_000_000, 6)


def check_startup(today: date) -> tuple[list[str], list[str]]:
    """Everything that must stop startup, and everything worth warning about.

    Returns `(violations, warnings)`. A non-empty violations list means the
    service must not start: eligibility is enforced at startup, not at call time
    (`04-layer-0.md` WP-0.4). Stale rates are only a warning — they degrade the
    accuracy of a record, they do not make the system unsafe to run.
    """
    return list(startup_violations(list(active()))), stale_rates(today)


def content_parts(request: GatewayRequest) -> tuple[str, ...]:
    """Everything about this request that would leave the machine."""
    parts = tuple(message.content for message in request.messages)
    if request.system is not None:
        parts = (*parts, request.system)
    return parts


class Gateway:
    """The one entrance to inference."""

    def __init__(
        self,
        adapters: dict[str, ProviderAdapter],
        recorder: CallRecorder,
        ledger: BudgetLedger,
        observe_block: Callable[[str], None] | None = None,
        persona_loader: PersonaLoader | None = None,
        verify_provenance: Callable[[GatewayRequest], None] | None = None,
    ) -> None:
        self._adapters = adapters
        self._record = recorder
        self._ledger = ledger
        self._observe_block = observe_block or _log_block
        self._persona_loader = persona_loader
        #: WP-0.7 corrective round. Checks that a conversation call's ids
        #: describe one coherent event before anything is transmitted. Supplied
        #: by the application because it is a database question; see
        #: `val_gateway.provenance.verifier`. A gateway without one **refuses**
        #: conversation calls rather than skipping the check.
        self._verify_provenance = verify_provenance

    # --- the entrances ---------------------------------------------------------

    def converse(
        self,
        messages: tuple[Message, ...],
        *,
        scope: ProjectScope,
        turn: TurnReference,
        classification: Classification = Classification.PROTECTED,
        max_output_tokens: int = 4096,
    ) -> GatewayResponse:
        """Talk to Val. The persona is loaded, assembled whole, and attributed.

        The one path an application uses for ordinary conversation, and the only
        one that guarantees the persona is present. **The persona is loaded per
        call from PostgreSQL**, not cached in this object: activating a new
        revision must take effect on the next exchange rather than at the next
        restart, and at Layer 0 volumes one indexed read is not worth the class of
        bug that a stale in-memory copy of Val's identity would introduce.

        If no persona can be established the call does not happen. There is no
        degraded mode — see `val_gateway.persona`.

        **`scope` is required and is a `ProjectScope`** — WP-0.6. It replaced
        `project_id: UUID | None = None`, which was wrong in two ways at once: the
        default let a caller who said nothing about scope silently write NULL,
        and `None` had to mean both *explicitly no project* and *nobody decided*.
        A `ProjectScope` is `ResolvedProject | ExplicitNoProject`, so it is always
        a decision, it must be passed, and `AmbiguousProject` is not of the right
        type to offer. Unresolved cannot reach persistence by construction rather
        than by a check some later caller forgets.
        """
        if self._persona_loader is None:
            raise PersonaUnavailableError(
                PersonaProblem.NONE_ACTIVE,
                "this gateway was built without a persona loader, so it cannot assemble "
                "Val. `converse` is the persona-bearing path; a gateway wired without one "
                "can only serve `complete`, which sends what it is given.",
            )
        persona = self._persona_loader.active()
        request = assemble(
            persona,
            messages,
            classification=classification,
            # Fixed, not a parameter. *Closure pass, 18 August 2026*: `converse`
            # is one real conversational turn by definition, and a caller who
            # could relabel it CLASSIFICATION or TITLE could file Val's own
            # utterances under machinery. The task type is what the function
            # *is*, so the function states it.
            task_type=TaskType.CONVERSATION,
            scope=scope,
            turn=turn,
            max_output_tokens=max_output_tokens,
        )
        return self._execute(request)

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        """Route one piece of non-conversation model work, or fail truthfully.

        The caller names no provider and no model. It names what the content is
        and what the work is; the gateway decides where that may go.

        **`TaskType.CONVERSATION` is refused here.** *Closure pass, 18 August
        2026.* A conversation is Val speaking, and Val speaks through
        `converse`, which loads her persona from the WP-0.5 loader and binds it
        into the call's provenance. A hand-built conversation request arriving
        here could carry any UUID in `persona_id` — coherent-looking provenance
        for an identity that was never loaded. The generic entrance therefore
        serves classification, strip, blind_position and title, and nothing
        that claims to be Val.
        """
        self._refuse_masquerade(request)
        return self._execute(request)

    def _execute(self, request: GatewayRequest) -> GatewayResponse:
        """The one execution body behind both entrances.

        Private on purpose: `converse` builds conversation requests and comes
        here directly, having just loaded the persona; `complete` comes here for
        non-conversation work after refusing anything conversational. There is
        exactly one copy of the guard order — Restricted, provenance, budget,
        route — because two copies is how one of them drifts.
        """
        self._refuse_restricted(request)
        self._refuse_incoherent_provenance(request)

        parts = content_parts(request)
        committed = self._ledger.committed_usd()

        order = attempt_order(
            active(),
            request.classification,
            is_ready=lambda config: config.provider in self._adapters,
            # A route whose model cannot hold this request — output cap or
            # context window — is not a candidate, exactly as an unaffordable
            # one is not. Filtered here so the request can still be served by a
            # route that CAN hold it, and so `_attempt`'s own refusal is the
            # backstop rather than the mechanism.
            is_affordable=lambda config: (
                limit_overrun(config, parts, request.max_output_tokens) is None
                and self._affordable(config, request, parts, committed)
            ),
            resolve_fallback=fallback_for,
        )
        if not order:
            raise GatewayError(
                GatewayErrorKind.NO_ELIGIBLE_ROUTE,
                self._no_route_detail(request, parts, committed),
            )

        last: GatewayError | None = None
        for config in order:
            try:
                return self._attempt(request, config, parts)
            except GatewayError as error:
                last = error
                if error.kind not in RETRYABLE:
                    raise
                self._observe_block(
                    f"route {config.slug} failed with {error.kind.value}; "
                    "trying the next independently eligible route"
                )

        # Every route in the order was tried and every one failed retryably. The
        # last failure is raised as it stands: a normalized, truthful account of
        # why nothing answered, not a synthesised summary of several.
        if last is not None:
            raise last
        raise GatewayError(GatewayErrorKind.NO_ELIGIBLE_ROUTE, "no route was attempted")

    def complete_with_configuration(
        self, request: GatewayRequest, config: ModelConfig
    ) -> GatewayResponse:
        """Run one call on a named configuration. Deliberate, not a bypass.

        The configuration must be the registry's own entry for its id, identical
        in every field. A caller that builds a `ModelConfig` naming an arbitrary
        provider and model — or that copies a real entry and edits the model
        identifier, or the eligibility set — is refused here, before any of the
        checks it was trying to walk around. Discovery of a shape is not
        authorization to route to it (`00-charter.md` invariant 6, in the spirit
        it was written).

        Refuses `TaskType.CONVERSATION` for the same reason `complete` does:
        naming a configuration explicitly is *more* deliberate, not more
        trusted, and it must not become the quiet way to talk as Val.
        """
        self._refuse_masquerade(request)
        self._refuse_restricted(request)

        known = by_id(config.id)
        if known is None or known != config:
            raise GatewayError(
                GatewayErrorKind.NO_ELIGIBLE_ROUTE,
                f"configuration {config.slug!r} ({config.provider}/{config.model_identifier}) "
                "is not the Model Configuration Registry's entry for its id. Routing selects "
                "among registered configurations and never among raw models "
                "(01-architecture.md §5.2); a configuration assembled by a caller is not one.",
            )
        if known.retired:
            raise GatewayError(
                GatewayErrorKind.NO_ELIGIBLE_ROUTE,
                f"{known.slug} is retired. A retired configuration resolves history; "
                "it does not serve new calls, and naming it explicitly does not "
                "un-retire it (closure red-team, 18 August 2026).",
            )
        if not is_admitted(known) or not is_eligible(known, request.classification):
            raise GatewayError(
                GatewayErrorKind.NO_ELIGIBLE_ROUTE,
                f"{known.slug} is not admitted for Layer 0 use, or not eligible for "
                f"{request.classification.value} content. Naming it explicitly does not "
                "admit it (00-charter.md invariant 17).",
            )

        return self._attempt(request, known, content_parts(request))

    # --- one attempt on one configuration ------------------------------------

    def _attempt(
        self, request: GatewayRequest, config: ModelConfig, parts: tuple[str, ...]
    ) -> GatewayResponse:
        """Reserve, call, settle. Every exit leaves the reservation resolved."""
        refusal = refusal_for(request.classification, config)
        if refusal is not None:
            kind, detail = refusal
            # No provider was contacted, so no row is written: a row would assert
            # a call that never happened.
            raise GatewayError(kind, detail)

        adapter = self._adapters.get(config.provider)
        if adapter is None:
            raise GatewayError(
                GatewayErrorKind.INVALID_REQUEST,
                f"no adapter is configured for provider {config.provider!r}",
            )

        # Closure pass, 18 August 2026: the model's own limits are enforced
        # HERE, before a reservation is taken and before anything is
        # transmitted. Relying on the provider to reject an impossible request
        # would mean routing it, reserving money for it, and sending the
        # content — three things that should not happen to a call that cannot
        # succeed. Nothing is clamped: a request for more output than the model
        # supports is refused in those words, because silently serving less
        # than was asked is a quiet lie about what was authorised.
        overrun = limit_overrun(config, parts, request.max_output_tokens)
        if overrun is not None:
            raise GatewayError(GatewayErrorKind.INVALID_REQUEST, overrun)

        authorised = maximum_cost(config, parts, request.max_output_tokens)
        claim = self._ledger.reserve(config, authorised, request.task_type, request.project_id)
        if isinstance(claim, Refusal):
            # The ceiling stopped this call before the provider was contacted.
            # Nothing was sent, so nothing is recorded (accounting state NOT_SENT).
            raise GatewayError(
                GatewayErrorKind.BUDGET_EXCEEDED,
                ceiling_message(claim.committed_usd, claim.max_cost_usd),
            )

        return self._call_and_settle(request, config, adapter, claim)

    def _call_and_settle(
        self,
        request: GatewayRequest,
        config: ModelConfig,
        adapter: ProviderAdapter,
        claim: Reservation,
    ) -> GatewayResponse:
        """Contact the provider with a reservation held, and always resolve it."""
        started = time.monotonic()
        try:
            result = adapter.complete(
                config, request.messages, request.system, request.max_output_tokens
            )
        except GatewayError as error:
            self._settle_unknown(request, config, claim, error, self._elapsed(started))
            raise

        latency = self._elapsed(started)

        # Closure pass, 18 August 2026 — two corrections in what follows.
        #
        # **Missing usage is UNKNOWN, never zero.** A response can arrive whole
        # with no usage block; pricing absent figures as 0 tokens recorded a
        # *known* $0 for exactly the calls whose cost was not known. Tokens are
        # `None` from the adapter in that case, the row records NULLs with
        # UNKNOWN certainty, and the reservation settles at its full maximum —
        # the same doctrine as a provider failure, because accounting-wise it is
        # one: the provider was paid an amount it declined to state.
        cost = (
            compute_cost(config, result.tokens_in, result.tokens_out)
            if result.tokens_in is not None and result.tokens_out is not None
            else None
        )
        certainty = CostCertainty.KNOWN if cost is not None else CostCertainty.UNKNOWN

        # **The terminal state decides the row's status and whether the text is
        # an answer.** COMPLETE and TRUNCATED are successful provider calls
        # (status OK — the *call* worked; whether the text may be persisted as a
        # Val message is the caller's branch on `terminal`). REFUSED is the
        # model's deliberate refusal. UNKNOWN is a stop state this system does
        # not recognise: the row records ERROR and the call fails closed below,
        # after the money has been accounted for honestly.
        status = {
            TerminalState.COMPLETE: CallStatus.OK,
            TerminalState.TRUNCATED: CallStatus.OK,
            TerminalState.FILTERED: CallStatus.OK,
            TerminalState.REFUSED: CallStatus.REFUSED,
            TerminalState.UNKNOWN: CallStatus.ERROR,
        }[result.terminal]

        call_id = self._record(
            CallRecord(
                model_config_id=config.id,
                slug=config.slug,
                provider=config.provider,
                model_identifier=config.model_identifier,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                cost_usd=cost,
                cost_certainty=certainty,
                terminal_state=result.terminal.value,
                project_id=request.project_id,
                project_attribution=request.project_attribution,
                task_type=request.task_type.value,
                conversation_id=request.conversation_id,
                message_id=request.message_id,
                persona_id=request.persona_id,
                latency_ms=latency,
                provider_request_id=result.provider_request_id,
                status=status,
            )
        )
        # Known cost settles at the real figure, returning the unspent
        # difference; unknown cost settles at the reserved maximum.
        self._ledger.settle(claim.id, cost, certainty, call_id)

        if result.terminal is TerminalState.UNKNOWN:
            raise GatewayError(
                GatewayErrorKind.INVALID_OUTPUT,
                f"{config.provider} ended this call in a state this system does not "
                "recognise. The call is recorded and its cost accounted for, but the "
                "text is not handed onward as an answer: an unrecognised outcome is "
                "unverified, not successful (00-charter.md §4).",
            )

        return GatewayResponse(
            text=result.text,
            terminal=result.terminal,
            model_config_id=config.id,
            slug=config.slug,
            provider=config.provider,
            model_identifier=config.model_identifier,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost_usd=cost,
            latency_ms=latency,
            provider_request_id=result.provider_request_id,
        )

    def _settle_unknown(
        self,
        request: GatewayRequest,
        config: ModelConfig,
        claim: Reservation,
        error: GatewayError,
        latency_ms: int,
    ) -> None:
        """A provider failure whose cost cannot be established.

        The request left the machine — or may have; a timeout cannot tell us
        which — and a request that reached the provider consumed its input
        tokens. Two things follow, and both are the opposite of what the previous
        implementation did:

        - The `model_calls` row records **unknown**, with NULL figures. Not a
          zero. A zero is a claim, and it is the wrong one.
        - The reservation settles at its **full authorised maximum**, not at
          nothing. Releasing it would treat "we cannot tell" as "nothing was
          spent", and the ceiling would then admit calls against money that may
          already be gone.
        """
        call_id = self._record(
            CallRecord(
                model_config_id=config.id,
                slug=config.slug,
                provider=config.provider,
                model_identifier=config.model_identifier,
                tokens_in=None,
                tokens_out=None,
                cost_usd=None,
                cost_certainty=CostCertainty.UNKNOWN,
                # No response object exists, so no provider terminal state does
                # either; `failed` records that truthfully rather than guessing.
                terminal_state="failed",
                project_id=request.project_id,
                project_attribution=request.project_attribution,
                task_type=request.task_type.value,
                conversation_id=request.conversation_id,
                message_id=request.message_id,
                persona_id=request.persona_id,
                latency_ms=latency_ms,
                provider_request_id=None,
                status=CallStatus.ERROR,
            )
        )
        self._ledger.settle(claim.id, None, CostCertainty.UNKNOWN, call_id)
        self._observe_block(
            f"{config.slug} failed with {error.kind.value} and reported no usage. "
            f"Recorded as unknown cost, and its reservation of "
            f"${claim.max_cost_usd:.4f} stays charged against this month."
        )

    # --- refusals that are not calls -----------------------------------------

    def _refuse_masquerade(self, request: GatewayRequest) -> None:
        """A generic entrance is not a way to talk as Val.

        *Closure pass, 18 August 2026.* `GatewayRequest` already refuses a
        conversation without provenance, and the verifier already refuses
        provenance that disagrees with the records — but neither could tell a
        persona revision *loaded through the WP-0.5 loader* from a UUID somebody
        typed. The only structure that can is the entrance: `converse` loads the
        persona itself and builds the request itself, so a conversation request
        arriving at a public generic entrance is by definition one `converse`
        did not build.
        """
        if request.task_type is TaskType.CONVERSATION:
            raise GatewayError(
                GatewayErrorKind.INVALID_REQUEST,
                "conversation inference goes through `converse`, which loads the active "
                "persona from the WP-0.5 loader and binds it into the call's provenance. "
                "The generic entrances serve non-conversation work only; accepting a "
                "hand-built conversation request here would let any typed persona UUID "
                "stand in for Val (current-version closure pass, 18 August 2026).",
            )

        # The inverse, at the entrance as well as in the request validator —
        # independent-review correction, 18 August 2026. `model_copy` skips
        # pydantic validation, so a shape the constructor refuses can still be
        # assembled; the entrance refuses it again before anything is routed,
        # reserved, or transmitted. Provenance on machinery would write
        # model_calls attribution for a conversation that never made the call.
        if request.conversation is not None:
            raise GatewayError(
                GatewayErrorKind.INVALID_REQUEST,
                f"a {request.task_type.value!r} request may not carry conversation "
                "provenance: only a conversation is caused by a conversation turn. "
                "Refused before routing (independent-review correction, 18 August 2026).",
            )

    def _refuse_incoherent_provenance(self, request: GatewayRequest) -> None:
        """Refuse a conversation call whose ids do not agree with the records.

        Runs **before** routing, the budget, and the provider, for the same
        reason `_refuse_restricted` does: a call that must not happen should not
        first select a route, reserve money, and transmit content. The foreign
        keys would catch a wholly invented id when the row was written, which is
        after the provider has been paid — and they would not catch a *real*
        message belonging to a different conversation at all.

        Non-conversation task types have no provenance and are not checked;
        `GatewayRequest` already refuses a conversation without one.
        """
        if request.conversation is None:
            return

        if self._verify_provenance is None:
            raise GatewayError(
                GatewayErrorKind.INVALID_REQUEST,
                "this gateway was built without a provenance verifier, so it cannot "
                "confirm that this call's conversation, message and project agree "
                "with the records. Conversation calls are refused rather than "
                "transmitted unverified (04-layer-0.md WP-0.7, corrective round). "
                "Build it with `verify_provenance=val_gateway.provenance.verifier(engine)`.",
            )

        try:
            self._verify_provenance(request)
        except Exception as mismatch:
            self._blocked(request, "incoherent conversation provenance")
            raise GatewayError(GatewayErrorKind.INVALID_REQUEST, str(mismatch)) from mismatch

    def _refuse_restricted(self, request: GatewayRequest) -> None:
        """Refuse obvious Restricted material before a route is even selected.

        Runs ahead of routing and ahead of the budget, so the reason Lord Armand
        is given is the real one, and so no route is ever chosen for content that
        was never going to be sent.
        """
        finding = preflight(content_parts(request))
        if finding is not None:
            self._blocked(request, finding.kind)
            raise GatewayError(GatewayErrorKind.RESTRICTED_CONTENT, refusal_message(finding))

        if request.classification is Classification.RESTRICTED:
            self._blocked(request, "content stated as Restricted")
            raise GatewayError(
                GatewayErrorKind.RESTRICTED_CONTENT,
                "Restricted content routes to local inference only, which does not "
                "exist until Layer 1. It is refused, not reclassified (04-layer-0.md §1.1).",
            )

    def _affordable(
        self,
        config: ModelConfig,
        request: GatewayRequest,
        parts: tuple[str, ...],
        committed: float,
    ) -> bool:
        """Whether this route's maximum still fits in what is left.

        A pre-filter on a figure read once, so an unaffordable route is not even
        attempted. It is not the enforcement — `ledger.reserve` is, atomically,
        under a lock. This one can race; that one cannot.
        """
        return admits(committed, maximum_cost(config, parts, request.max_output_tokens))

    def _no_route_detail(
        self, request: GatewayRequest, parts: tuple[str, ...], committed: float
    ) -> str:
        """Say which of the filters emptied the candidate set.

        The difference between "no route is eligible for this" and "no route
        fits in what is left of the budget" is the difference between a decision
        Lord Armand must make and one he can wait out.
        """
        eligible = [
            config
            for config in active()
            if is_admitted(config) and is_eligible(config, request.classification)
        ]
        if not eligible:
            return (
                f"No configuration is admitted for Layer 0 use and eligible for "
                f"{request.classification.value} content. I will not downgrade the "
                "classification or route to an unadmitted provider to get around it "
                "(00-charter.md invariant 17)."
            )
        ready = [config for config in eligible if config.provider in self._adapters]
        if not ready:
            return (
                "Every eligible configuration is missing its adapter or its credential "
                "in this process. No call was made."
            )
        if not any(self._affordable(config, request, parts, committed) for config in ready):
            return no_affordable_route_message(committed)
        return "No eligible route could be selected."

    def _blocked(self, request: GatewayRequest, kind: str) -> None:
        """Record that a request was blocked — without recording a call.

        No `model_calls` row is written: no provider was contacted, no tokens
        were spent, and a row would assert a call that never happened. The block
        is reported to the observer the caller supplied, so it is visible
        without inventing a table `04-layer-0.md` §2 does not name.
        """
        self._observe_block(
            f"blocked before transmission: {kind} "
            f"(task_type={request.task_type.value}, project_id={request.project_id})"
        )

    @staticmethod
    def _elapsed(started: float) -> int:
        return int((time.monotonic() - started) * 1000)
