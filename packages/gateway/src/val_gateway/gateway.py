"""The Model Gateway itself (`01-architecture.md` §5.1).

Every model call enters here and nothing else calls a provider. In order, per
call, and each step failing before the next begins:

1. **Restricted content is refused**, two ways, and no `model_calls` row is
   written either way — it was never a call (`04-layer-0.md` §1.1, WP-0.4).
   The caller's stated classification is honoured, *and* the content itself is
   scanned locally for obvious credentials and personal data before anything
   leaves the machine (`val_policy.restricted`). The second check exists because
   the first is only as good as the caller's own knowledge.
2. **Eligibility.** Checked again at call time even though startup already made
   it structurally impossible to fail. Defence in depth costs one set lookup,
   and the structural guarantee dissolves at Layer 2 when tools bring in mixed
   content.
3. **Budget, before the call.** Month-to-date cloud spend is checked against the
   ceiling *before* the provider is contacted, never reported after
   (`00-charter.md` invariant 24). A blocked call writes no row: no call was
   made, so there is nothing to cost.
4. **The call**, through the adapter, with every provider failure arriving as
   one normalized error.
5. **Cost and attribution**, computed at call time from the configuration's
   rates and written to `model_calls` — including on error and refusal, so
   "zero calls without a row" holds for the failures too.

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
    GatewayError,
    GatewayErrorKind,
    GatewayRequest,
    GatewayResponse,
    ModelConfig,
)
from val_domain.registry import active, stale_rates
from val_policy.budget import ceiling_message, cloud_call_permitted
from val_policy.eligibility import refusal_for, startup_violations
from val_policy.restricted import preflight, refusal_message
from val_providers.base import ProviderAdapter

_LOGGER = logging.getLogger("val.gateway")


def _log_block(message: str) -> None:
    """Default observer for a blocked request: the application log."""
    _LOGGER.warning("%s", message)


#: What the gateway records for one call. The caller supplies the writer, so this
#: package never imports a database driver and stays testable without one.
CallRecorder = Callable[["CallRecord"], None]


class CallRecord:
    """One `model_calls` row, assembled by the gateway and handed to the writer."""

    def __init__(
        self,
        *,
        model_config_id: UUID,
        slug: str,
        provider: str,
        model_identifier: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        project_id: UUID | None,
        task_type: str,
        conversation_id: UUID | None,
        message_id: UUID | None,
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
        self.project_id = project_id
        self.task_type = task_type
        self.conversation_id = conversation_id
        self.message_id = message_id
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


class Gateway:
    """The one entrance to inference."""

    def __init__(
        self,
        adapters: dict[str, ProviderAdapter],
        recorder: CallRecorder,
        month_to_date_spend: Callable[[], float],
        observe_block: Callable[[str], None] | None = None,
    ) -> None:
        self._adapters = adapters
        self._record = recorder
        self._spend = month_to_date_spend
        self._observe_block = observe_block or _log_block

    def complete(self, request: GatewayRequest, config: ModelConfig) -> GatewayResponse:
        """Run one call end to end, recording it whatever the outcome."""
        # Before anything else, and before any provider is contacted: does the
        # content itself carry obvious Restricted material, whatever the caller
        # believes about it? Blocks, never downgrades; fails closed.
        parts = tuple(message.content for message in request.messages)
        if request.system is not None:
            parts = (*parts, request.system)
        finding = preflight(parts)
        if finding is not None:
            self._blocked(request, finding.kind)
            raise GatewayError(GatewayErrorKind.RESTRICTED_CONTENT, refusal_message(finding))

        refusal = refusal_for(request.classification, config)
        if refusal is not None:
            kind, detail = refusal
            # Restricted content was never a call: no provider was contacted, no
            # tokens were spent, so no model_calls row is written (WP-0.4).
            if request.classification is Classification.RESTRICTED:
                raise GatewayError(kind, detail)
            raise GatewayError(kind, detail)

        if not cloud_call_permitted(self._spend()):
            # Enforced before the call, never reported after (invariant 24).
            raise GatewayError(GatewayErrorKind.BUDGET_EXCEEDED, ceiling_message(self._spend()))

        adapter = self._adapters.get(config.provider)
        if adapter is None:
            raise GatewayError(
                GatewayErrorKind.INVALID_REQUEST,
                f"no adapter is configured for provider {config.provider!r}",
            )

        started = time.monotonic()
        try:
            result = adapter.complete(
                config, request.messages, request.system, request.max_output_tokens
            )
        except GatewayError as error:
            # A failed call still cost the provider's input tokens in most cases
            # and, more importantly, still happened. Zero calls without a row.
            self._write(request, config, 0, 0, self._elapsed(started), None, CallStatus.ERROR)
            raise error

        latency = self._elapsed(started)
        status = CallStatus.REFUSED if result.refused else CallStatus.OK
        cost = self._write(
            request,
            config,
            result.tokens_in,
            result.tokens_out,
            latency,
            result.provider_request_id,
            status,
        )
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

    def _write(
        self,
        request: GatewayRequest,
        config: ModelConfig,
        tokens_in: int,
        tokens_out: int,
        latency_ms: int,
        provider_request_id: str | None,
        status: CallStatus,
    ) -> float:
        cost = compute_cost(config, tokens_in, tokens_out)
        self._record(
            CallRecord(
                model_config_id=config.id,
                slug=config.slug,
                provider=config.provider,
                model_identifier=config.model_identifier,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost,
                project_id=request.project_id,
                task_type=request.task_type.value,
                conversation_id=request.conversation_id,
                message_id=request.message_id,
                latency_ms=latency_ms,
                provider_request_id=provider_request_id,
                status=status,
            )
        )
        return cost
