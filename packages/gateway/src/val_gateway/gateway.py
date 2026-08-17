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
)
from val_domain.registry import active, by_id, fallback_for, stale_rates
from val_gateway.context import assemble
from val_gateway.ledger import BudgetLedger, Refusal, Reservation
from val_gateway.persona import PersonaLoader, PersonaProblem, PersonaUnavailableError
from val_policy.budget import (
    admits,
    ceiling_message,
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
        project_id: UUID | None,
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
        self.project_id = project_id
        self.task_type = task_type
        self.conversation_id = conversation_id
        self.message_id = message_id
        self.persona_id = persona_id
        self.latency_ms = latency_ms
        self.provider_request_id = provider_request_id
        self.status = status


def compute_cost(config: ModelConfig, tokens_in: int, tokens_out: int) -> float:
    """Cost in USD, from the configuration's rates, at call time.

    Stored, never derived later: provider pricing changes, and a historical
    record that silently re-prices itself is not a record (`04-layer-0.md` §2.2).
    """
    return (
        tokens_in * config.cost_per_mtok_in_usd + tokens_out * config.cost_per_mtok_out_usd
    ) / 1_000_000


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
    ) -> None:
        self._adapters = adapters
        self._record = recorder
        self._ledger = ledger
        self._observe_block = observe_block or _log_block
        self._persona_loader = persona_loader

    # --- the entrances ---------------------------------------------------------

    def converse(
        self,
        messages: tuple[Message, ...],
        *,
        classification: Classification = Classification.PROTECTED,
        task_type: TaskType = TaskType.CONVERSATION,
        project_id: UUID | None = None,
        conversation_id: UUID | None = None,
        message_id: UUID | None = None,
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
            task_type=task_type,
            project_id=project_id,
            conversation_id=conversation_id,
            message_id=message_id,
            max_output_tokens=max_output_tokens,
        )
        return self.complete(request)

    def complete(self, request: GatewayRequest) -> GatewayResponse:
        """Route this request and answer it, or fail truthfully.

        The caller names no provider and no model. It names what the content is
        and what the work is; the gateway decides where that may go.
        """
        self._refuse_restricted(request)

        parts = content_parts(request)
        committed = self._ledger.committed_usd()

        order = attempt_order(
            active(),
            request.classification,
            is_ready=lambda config: config.provider in self._adapters,
            is_affordable=lambda config: self._affordable(config, request, parts, committed),
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
        """
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
        status = CallStatus.REFUSED if result.refused else CallStatus.OK
        cost = compute_cost(config, result.tokens_in, result.tokens_out)
        call_id = self._record(
            CallRecord(
                model_config_id=config.id,
                slug=config.slug,
                provider=config.provider,
                model_identifier=config.model_identifier,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                cost_usd=cost,
                cost_certainty=CostCertainty.KNOWN,
                project_id=request.project_id,
                task_type=request.task_type.value,
                conversation_id=request.conversation_id,
                message_id=request.message_id,
                persona_id=request.persona_id,
                latency_ms=latency,
                provider_request_id=result.provider_request_id,
                status=status,
            )
        )
        # Settling at the real figure returns the unspent difference between the
        # reservation and the actual cost to the month's available budget.
        self._ledger.settle(claim.id, cost, CostCertainty.KNOWN, call_id)

        return GatewayResponse(
            text=result.text,
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
                project_id=request.project_id,
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
