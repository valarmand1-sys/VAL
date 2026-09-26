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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import cast
from uuid import UUID

from val_domain.egress import Egress
from val_domain.gateway import (
    PERSONA_ATTRIBUTED_TASKS,
    Admission,
    CacheTtl,
    CallStatus,
    CapabilityProfile,
    Classification,
    CostCertainty,
    GatewayError,
    GatewayErrorKind,
    GatewayRequest,
    GatewayResponse,
    Hosting,
    Message,
    Metering,
    ModelConfig,
    PersonaAttribution,
    PricingFeature,
    TaskType,
    TerminalState,
    TurnReference,
)
from val_domain.perception import PerceptionProvider
from val_domain.project import (
    ExplicitNoProject,
    ProjectAttribution,
    ProjectScope,
)
from val_domain.provider import (
    ContextFeasibility,
    ContextInspectingAdapter,
    ContextInspectionUnavailableError,
    DeltaSink,
    LocalRuntimeAdapter,
    LocalRuntimeUnavailableError,
    PrefixPrimingAdapter,
    ProviderAdapter,
    ProviderResult,
    TextDelta,
    supports_context_inspection,
    supports_local_runtime,
    supports_prefix_priming,
    supports_streaming,
)
from val_domain.registry import active, by_id, fallback_for, stale_rates
from val_domain.speech import SpeechProvider, VoiceConditioning
from val_domain.timings import mark
from val_gateway.context import assemble
from val_gateway.ledger import BudgetLedger, ExchangeEnvelopeRefusal, Refusal, Reservation
from val_gateway.persona import PersonaLoader, PersonaProblem, PersonaUnavailableError
from val_policy.budget import (
    CONVERSATION_MAX_OUTPUT_TOKENS,
    admits,
    ceiling_message,
    effective_rates,
    exchange_envelope_message,
    limit_overrun,
    local_context_overrun,
    maximum_cost,
    no_affordable_route_message,
    output_cap_overrun,
)
from val_policy.eligibility import egress_refusal_for, refusal_for, startup_violations
from val_policy.restricted import preflight, refusal_message
from val_policy.routing import (
    attempt_order,
    can_carry_images,
    is_admitted,
    is_eligible,
    local_alternative,
    paid_partner_refusal,
    required_profile,
    satisfies_profile,
)
from val_policy.tokens import estimate_tokens

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


@dataclass(frozen=True)
class CacheUsage:
    """What the prompt cache did on one call, priced — the `model_call_cache_usage`
    evidence row (ruling, 8 September 2026).

    Written only when caching was requested and the provider reported usage.
    Every figure is the provider's own; every cost is computed at call time
    from the configuration's verified cache rates and never recomputed.
    """

    requested_ttl: CacheTtl
    uncached_input_tokens: int
    cache_write_5m_tokens: int
    cache_write_1h_tokens: int
    cache_read_tokens: int
    #: `hit` (read, nothing written), `created` (written, nothing read),
    #: `hit_and_created` (both — a longer prefix extended a hit), or
    #: `not_cached` (requested, but the provider cached nothing — typically a
    #: prefix below the model's minimum).
    outcome: str
    cost_uncached_usd: float
    cost_cache_write_usd: float
    cost_cache_read_usd: float
    cost_output_usd: float


@dataclass(frozen=True)
class CallMeasurement:
    """Per-call measurement — the `model_call_measurements` row (ruling, 13 September 2026).

    Written for every recorded call. Every field is what this call observably
    did or what its provider reported; a figure the provider or the call mode
    does not expose is `None`, never zero and never inferred.
    """

    exchange: TurnReference | None
    streamed: bool
    #: Milliseconds from the start of the provider call to the first non-empty
    #: generated-text delta the gateway forwarded; None when not streamed or no
    #: text arrived.
    first_text_ms: int | None
    #: Characters of generated text returned (never thinking); None when no
    #: response arrived.
    text_output_chars: int | None
    reasoning_present: bool | None
    reasoning_output_tokens: int | None
    provider_cached_input_tokens: int | None
    provider_cache_write_tokens: int | None
    #: Ruling, 15 September 2026: the prompt-cache key sent and the provider's
    #: cache diagnostics, verbatim; None where the provider exposes neither.
    prompt_cache_key: str | None = None
    cache_diagnostics: Mapping[str, object] | None = None
    #: Ruling, 16 September 2026: the model the provider's response named, and
    #: the runtime's own account of the call, with the entry's hosting axis.
    provider_reported_model: str | None = None
    runtime_diagnostics: Mapping[str, object] | None = None


def _runtime_diagnostics(
    config: ModelConfig,
    reported: Mapping[str, object] | None,
    *,
    feasibility: ContextFeasibility | None = None,
    server_prompt_tokens: int | None = None,
) -> dict[str, object]:
    """The runtime facts recorded on every call: the hosting axis, whatever the
    adapter reported verbatim, and — ruling, 16 September 2026 — the exact
    preflight that admitted the call beside the server's own prompt count, so
    parity is evidence on the row and a disagreement is visible, never normal."""
    facts: dict[str, object] = {
        "hosting": config.hosting.value,
        **({} if reported is None else dict(reported)),
    }
    if feasibility is not None:
        difference = (
            None
            if server_prompt_tokens is None
            else server_prompt_tokens - feasibility.prompt_tokens
        )
        facts["preflight"] = {
            "source": feasibility.source,
            "prompt_tokens": feasibility.prompt_tokens,
            "context_tokens": feasibility.context_tokens,
            "registry_context_tokens": config.context_window_tokens,
            "registry_agrees": feasibility.context_tokens == config.context_window_tokens,
            **dict(feasibility.details),
        }
        facts["parity"] = {
            "preflight_prompt_tokens": feasibility.prompt_tokens,
            "server_prompt_tokens": server_prompt_tokens,
            "difference": difference,
            "exact": difference == 0,
        }
        if difference is not None and difference != 0:
            _LOGGER.warning(
                "%s: preflight counted %d prompt tokens, the server reported %d (difference %+d); "
                "parity is not exact",
                config.slug,
                feasibility.prompt_tokens,
                server_prompt_tokens,
                difference,
            )
    return facts


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
        cache_usage: CacheUsage | None = None,
        measurement: CallMeasurement | None = None,
    ) -> None:
        self.model_config_id = model_config_id
        self.cache_usage = cache_usage
        self.measurement = measurement
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


def _reported_cache_writes(result: ProviderResult) -> int | None:
    """Every prompt-cache write the provider reported, whatever its lifetime, or None."""
    figures = (
        result.cache_write_5m_tokens,
        result.cache_write_1h_tokens,
        result.cache_write_auto_tokens,
    )
    if all(figure is None for figure in figures):
        return None
    return sum(figure or 0 for figure in figures)


def cost_components(
    config: ModelConfig,
    tokens_in: int,
    tokens_out: int,
    *,
    cache_read: int = 0,
    cache_write_5m: int = 0,
    cache_write_1h: int = 0,
    cache_write_auto: int = 0,
) -> tuple[float, float, float, float]:
    """The four billed components of a completed call, in USD: uncached input,
    cache writes, cache reads, output — at the rates that actually applied.

    Ruling, 14 September 2026: `cache_write_auto` is what an automatically
    caching provider reported writing, priced at the route's verified automatic
    write rate — never also as uncached input, because the adapter reports the
    three input figures disjointly. Unverified, it is priced at base like any
    other cache figure on an unverified route.

    Uses `effective_rates`, the same function the pre-call bound prices with —
    closure pass, 18 August 2026 — so a call whose input crossed a provider's
    long-context threshold settles at the multiplied rates the provider bills,
    and the estimator and the settlement cannot disagree about what a token
    costs. The threshold is judged on the **total** input the provider
    processed, cached parts included, because that is what the provider does.

    Ruling, 8 September 2026: cache figures are priced at the configuration's
    verified cache rates. A cache figure reported by a provider whose entry
    carries no verified cache rate is priced at the base input rate — never
    cheaper than base on an unverified number.
    """
    total_in = tokens_in + cache_read + cache_write_5m + cache_write_1h + cache_write_auto
    rate_in, rate_out = effective_rates(config, total_in)
    # Ruling, 16 September 2026: an unmetered local route has a zero base rate
    # and, by its validator, no cache pricing; every component below is zero
    # and there is no multiplier to derive.
    multiplier = 1.0 if config.cost_per_mtok_in_usd == 0 else rate_in / config.cost_per_mtok_in_usd
    read_rate = (config.cache_read_per_mtok_in_usd or config.cost_per_mtok_in_usd) * multiplier
    write_auto_rate = (
        config.cache_write_auto_per_mtok_in_usd or config.cost_per_mtok_in_usd
    ) * multiplier
    write_5m_rate = (
        config.cache_write_5m_per_mtok_in_usd or config.cost_per_mtok_in_usd
    ) * multiplier
    write_1h_rate = (
        config.cache_write_1h_per_mtok_in_usd or config.cost_per_mtok_in_usd
    ) * multiplier
    return (
        tokens_in * rate_in / 1_000_000,
        (
            cache_write_5m * write_5m_rate
            + cache_write_1h * write_1h_rate
            + cache_write_auto * write_auto_rate
        )
        / 1_000_000,
        cache_read * read_rate / 1_000_000,
        tokens_out * rate_out / 1_000_000,
    )


def compute_cost(
    config: ModelConfig,
    tokens_in: int,
    tokens_out: int,
    *,
    cache_read: int = 0,
    cache_write_5m: int = 0,
    cache_write_1h: int = 0,
    cache_write_auto: int = 0,
) -> float:
    """The settled cost of a completed call: the sum of `cost_components`."""
    return round(
        sum(
            cost_components(
                config,
                tokens_in,
                tokens_out,
                cache_read=cache_read,
                cache_write_5m=cache_write_5m,
                cache_write_1h=cache_write_1h,
                cache_write_auto=cache_write_auto,
            )
        ),
        6,
    )


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
        cache_ttl: CacheTtl | None = None,
        perception: Sequence[PerceptionProvider] = (),
        speech: SpeechProvider | None = None,
        voice: VoiceConditioning | None = None,
    ) -> None:
        #: Owner ruling, 22 September 2026, extended the same evening: Val's
        #: local perception **specialists**, supplied by the composition root
        #: exactly as the adapters are. One sees, one hears; each declares the
        #: modalities it is admitted for, and Core selects by that declaration
        #: rather than by order or by class name. Empty means none is wired —
        #: in which case a turn carrying media whose route *is* admitted fails
        #: closed rather than falling back to the paid raw-media path.
        #:
        #: Held here rather than reached for, because the core must not import a
        #: provider package to find out whether it can see or hear.
        self.perception: tuple[PerceptionProvider, ...] = tuple(perception)
        #: Owner execution order, 22 September 2026: Val's local voice, wired
        #: here for the same reason the adapters and the perception specialists
        #: are — the core must not import a provider package to find out whether
        #: it can speak. `None` means no speech route is wired, in which case a
        #: request for speech fails closed rather than reaching for a cloud
        #: voice service.
        self.speech = speech
        #: The governed voice she speaks in: the canonical locally designed
        #: reference and its provenance, loaded once at startup.
        self.voice = voice
        self._adapters = adapters
        self._record = recorder
        self._ledger = ledger
        self._cache_ttl = cache_ttl
        self._observe_block = observe_block or _log_block
        self._persona_loader = persona_loader
        #: WP-0.7 corrective round. Checks that a conversation call's ids
        #: describe one coherent event before anything is transmitted. Supplied
        #: by the application because it is a database question; see
        #: `val_gateway.provenance.verifier`. A gateway without one **refuses**
        #: conversation calls rather than skipping the check.
        self._verify_provenance = verify_provenance

    # --- the entrances ---------------------------------------------------------

    def warm_voice(self) -> Mapping[str, object]:
        """Load the speech model once for this Voice session, and generate nothing.

        Owner order, 25 September 2026 (Voice-mode repair §5), superseding the load-
        and-exit warm-up of WP3 Step B §9. The provider starts its **resident** worker:
        the same runner, model, settings and conditioning, holding the model while
        Voice is on so that each sentence no longer pays an interpreter start and a
        model load (one-shot 2.35 to 2.81 s against resident 1.13 to 1.59 s for the same
        phrases, measured on this Mac). `release_voice` stops it when the last Voice
        session ends. A sentence that arrives while it loads waits for that load, and
        any failure of the worker falls back to the one-shot synthesis.

        Not a gate, exactly like `warm_cognition`: a failure is reported and the first
        answer proceeds as it would have. Nothing is spoken and nothing is recorded —
        Val has not said anything, so there is nothing to attribute.
        """
        speech = self.speech
        if speech is None:
            return {"warmed": False, "reason": "this house has no admitted speech route"}
        warm = getattr(speech, "warm", None)
        if not callable(warm):
            return {"warmed": False, "reason": "this speech provider cannot be warmed"}
        try:
            # The governed voice, when this gateway has one: its conditioning is
            # loaded and the streaming decoder primed at start (26 September 2026).
            report = warm(self.voice) if self.voice is not None else warm()
        except Exception as failure:  # reported, never fatal
            return {"warmed": False, "reason": f"{type(failure).__name__}: {failure}"}
        return dict(report) if isinstance(report, Mapping) else {"warmed": False}

    def _spoken_turn_route(self, task_type: TaskType = TaskType.CONVERSATION) -> ModelConfig | None:
        """The route a spoken turn will try first, chosen the way that turn chooses it."""
        order = attempt_order(
            active(),
            Classification.PROTECTED,
            is_ready=lambda config: config.provider in self._adapters,
            is_affordable=lambda config: True,
            resolve_fallback=fallback_for,
            profile=required_profile(task_type),
            cost_bound=lambda config: maximum_cost(config, (), CONVERSATION_MAX_OUTPUT_TOKENS),
            egress=Egress.LOCAL_ONLY,
        )
        return order[0] if order else None

    def prime_prefix(self, still_wanted: Callable[[], bool] = lambda: True) -> Mapping[str, object]:
        """Prime the spoken turn's route — and the light route too, when one is admitted.

        Owner order, 26 September 2026 (§9): exact persona-prefix reuse is qualified for
        the fast model as for the Partner route, by the same plan, on its own instance.
        The Partner route's result is this method's result, as before; the light
        route's rides alongside as `light`.
        """
        result = dict(self._prime_route(TaskType.CONVERSATION, still_wanted))
        light = self._spoken_turn_route(TaskType.LIGHT_CONVERSATION)
        if light is not None:
            result["light"] = self._prime_route(TaskType.LIGHT_CONVERSATION, still_wanted)
        return result

    def _prime_route(
        self, task_type: TaskType, still_wanted: Callable[[], bool]
    ) -> Mapping[str, object]:
        """Leave the computation of Val's persona in the local runtime, for later turns.

        Owner order, 25 September 2026 (priming-cache pass). **A local infrastructure
        model call**: the persona, whole and verbatim as every turn sends it, and one
        short user message sized so the runtime's checkpoint lands exactly on the
        boundary every real turn renders identically. Later turns — which Core still
        assembles completely, every time — find that computation already done and
        process only what follows it. Measured through LM Studio on an isolated
        instance: first output ~0.7 s against ~7 s on turns whose suffixes differ.

        It is governed like any call: it goes through `_attempt`, so it is budgeted,
        preflighted, attributed to the persona revision and **recorded** as
        `prefix_prime`, attached to no conversation. Its one generated token is
        discarded here; nothing it produces reaches a message, recall or memory.

        **Never ahead of him.** `still_wanted` is asked after the runtime is ready and
        immediately before the call is sent; if a real owner request is waiting by
        then, nothing is sent. Once sent it runs to completion — it computes exactly
        the prefix his request would otherwise compute itself, so waiting for it is
        never longer than doing that work from nothing.
        """
        config = self._spoken_turn_route(task_type)
        if config is None:
            return {"primed": False, "outcome": "skipped", "reason": "no admitted partner route"}
        adapter = self._adapters[config.provider]
        if not supports_prefix_priming(adapter) or not supports_local_runtime(adapter):
            return {
                "primed": False,
                "outcome": "skipped",
                "slug": config.slug,
                "reason": "this route's runtime cannot be primed",
            }
        if self._persona_loader is None:
            return {"primed": False, "outcome": "skipped", "reason": "no persona loader"}
        try:
            cast(LocalRuntimeAdapter, adapter).ensure_runtime_ready(config)
        except LocalRuntimeUnavailableError as failure:
            return {
                "primed": False,
                "outcome": "failed",
                "slug": config.slug,
                "reason": str(failure),
            }
        # Planning asks the runtime to render and tokenize; that is optional work too,
        # and on a sequential instance it competes with his request. Qualification
        # found it adding ~3 s to a cold first turn, so it waits its turn as well.
        if not still_wanted():
            return {
                "primed": False,
                "outcome": "skipped",
                "slug": config.slug,
                "reason": "an owner request is waiting; maintenance never starts ahead of it",
            }
        persona = self._persona_loader.active()
        plan = cast(PrefixPrimingAdapter, adapter).plan_prefix_prime(config, persona.content)
        if plan.refused is not None:
            return {
                "primed": False,
                "outcome": "skipped",
                "slug": config.slug,
                "engine": plan.engine,
                "reason": plan.refused,
            }
        if not still_wanted():
            return {
                "primed": False,
                "outcome": "skipped",
                "slug": config.slug,
                "reason": "an owner request is waiting; maintenance never starts ahead of it",
            }
        request = assemble(
            persona,
            (Message(role="user", content=plan.filler),),
            task_type=TaskType.PREFIX_PRIME,
            scope=ExplicitNoProject(),
            max_output_tokens=1,
            egress=Egress.LOCAL_ONLY,
        ).model_copy(
            # It carries the persona whole, so it names the revision it carried —
            # the same rule as every persona-bearing call that is not a turn.
            update={"persona": PersonaAttribution(persona_id=persona.id)}
        )
        started = time.monotonic()
        try:
            response = self._attempt(request, config, content_parts(request))
        except GatewayError as failure:
            return {
                "primed": False,
                "outcome": "failed",
                "slug": config.slug,
                "reason": f"{failure.kind.value}: {failure}",
            }
        return {
            "primed": True,
            "outcome": "established",
            "slug": config.slug,
            "engine": plan.engine,
            "boundary_tokens": plan.boundary_tokens,
            "boundary_sha256": plan.boundary_sha256,
            "prime_tokens": plan.prime_tokens,
            "model_call_id": str(response.model_call_id),
            "seconds": round(time.monotonic() - started, 3),
        }

    def release_voice(self) -> Mapping[str, object]:
        """Give back what Voice held: the resident speech worker, if one is running."""
        release = getattr(self.speech, "release", None)
        if not callable(release):
            return {"released": False, "reason": "this speech provider holds nothing"}
        result = release()
        return dict(result) if isinstance(result, Mapping) else {"released": True}

    def warm_cognition(self) -> Mapping[str, object]:
        """Bring the ordinary conversation route's local runtime up, early.

        Latency pass §12. A local model carries a one-hour idle TTL, so the first
        turn after an idle hour pays its load **on the critical path**: measured
        9.143 s against 0.148 s when it was already resident. Doing the same
        readiness call early — while the owner is still speaking, say — removes
        that from the turn without changing anything about the turn.

        It is the *same* supervisor call the turn makes, not a substitute for it:
        the turn still asks, the turn's answer still governs, and this method
        changes no routing, no eligibility, no policy and nothing the model sees.
        A failure here is reported and swallowed, because the turn's own readiness
        call is the one that must fail honestly if the runtime cannot be had.

        Returns what it found and did, for the caller's record.
        """
        # **The route a spoken turn will try first, chosen the way that turn chooses
        # it** (owner diagnostic, 25 September 2026, §8). Warming is optional work,
        # and the only thing it shares with a real turn is the runtime's load lock:
        # a turn that arrives while warming holds it waits. That wait is legitimate
        # only if the warm-up is doing **exactly the initialization the turn itself
        # requires** — so the warm-up must pick the turn's own first route, not a
        # route that happens to coincide with it. The first version ranked by input
        # rate among all partner routes and then looked for a local runtime; that
        # agreed with the turn only because one local partner route exists. This is
        # the turn's own ordering, under the turn's own egress: a Voice session makes
        # its conversation local-only for as long as it is open, so every turn it
        # carries routes `LOCAL_ONLY`. The runtime re-observes residency under the
        # lock, so the turn then finds the model loaded and does not load it again.
        chosen = self._spoken_turn_route()
        if chosen is None:
            return {"warmed": False, "reason": "no admitted partner route is configured"}
        if not supports_local_runtime(self._adapters[chosen.provider]):
            return {
                "warmed": False,
                "reason": (
                    "no admitted partner route has a local runtime to warm "
                    f"(a spoken turn would try {chosen.slug} first)"
                ),
            }
        adapter = self._adapters[chosen.provider]
        try:
            readiness = cast(LocalRuntimeAdapter, adapter).ensure_runtime_ready(chosen)
        except LocalRuntimeUnavailableError as failure:
            # Not raised: the turn's own readiness call is the one that must fail
            # honestly. Warming early is an optimisation, never a gate.
            self._observe_block(
                f"warming {chosen.slug} did not succeed: {failure}. The turn will ask again "
                "and will fail honestly there if the runtime cannot be had."
            )
            return {"warmed": False, "slug": chosen.slug, "reason": str(failure)}
        result: dict[str, object] = {"warmed": True, "slug": chosen.slug, **dict(readiness)}
        # The light route's runtime too, when one is admitted (26 September 2026): its
        # model is small, and a first greeting should not pay its load.
        light = self._spoken_turn_route(TaskType.LIGHT_CONVERSATION)
        if light is not None and supports_local_runtime(self._adapters[light.provider]):
            try:
                ready = cast(LocalRuntimeAdapter, self._adapters[light.provider])
                readiness_light = ready.ensure_runtime_ready(light)
                result["light"] = {"warmed": True, "slug": light.slug, **dict(readiness_light)}
            except LocalRuntimeUnavailableError as failure:
                result["light"] = {"warmed": False, "slug": light.slug, "reason": str(failure)}
        return result

    def converse(
        self,
        messages: tuple[Message, ...],
        *,
        scope: ProjectScope,
        turn: TurnReference,
        classification: Classification = Classification.PROTECTED,
        max_output_tokens: int = 4096,
        configuration: ModelConfig | None = None,
        on_delta: DeltaSink | None = None,
        egress: Egress = Egress.ORDINARY,
    ) -> GatewayResponse:
        """Talk to Val. The persona is loaded, assembled whole, and attributed.

        `egress` is the live-voice seal (owner ruling, 24 September 2026): pass
        `LOCAL_ONLY` and this call may be carried only by a configuration whose
        inference runs on this machine, with no fallback and no approval path.

        `on_delta` (Val Core Phase 1, 11 September 2026) is a sink owned by the
        caller inside Val Core — the loop or the deliberation orchestrator —
        that receives Val's generated text as the provider produces it, when
        the route's adapter can stream. It is presentation only: the response
        this method returns is settled, recorded and governed exactly as
        without it, and nothing outside the core is ever handed the stream
        directly.

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
        return self._converse(
            messages,
            # Fixed, not a parameter. *Closure pass, 18 August 2026*: `converse`
            # is one real conversational turn by definition, and a caller who
            # could relabel it CLASSIFICATION or TITLE could file Val's own
            # utterances under machinery. The task type is what the function
            # *is*, so the function states it. The light kind has its own
            # function, `converse_lightly`, for the same reason.
            TaskType.CONVERSATION,
            scope=scope,
            turn=turn,
            classification=classification,
            max_output_tokens=max_output_tokens,
            configuration=configuration,
            on_delta=on_delta,
            egress=egress,
        )

    def converse_lightly(
        self,
        messages: tuple[Message, ...],
        *,
        scope: ProjectScope,
        turn: TurnReference,
        max_output_tokens: int,
        on_delta: DeltaSink | None = None,
        egress: Egress = Egress.ORDINARY,
    ) -> GatewayResponse:
        """Val's own turn on the light route — owner order, 26 September 2026 (§5).

        Core has decided, deterministically and before this call, that the turn is a
        standalone greeting, thanks, farewell or admitted pleasantry. The request is
        assembled exactly as `converse` assembles it — persona whole, provenance,
        seal — and differs in one thing only: the task is `LIGHT_CONVERSATION`, so
        routing requires the light capability floor, and the record says so. It is a
        separate function rather than a parameter for the closure contract's reason
        (§3, 18 August 2026): the label is what the function is. No pinned
        configuration: a light turn carries no images and is never a blind
        position's partner.
        """
        if self._persona_loader is None:
            raise PersonaUnavailableError(
                PersonaProblem.NONE_ACTIVE,
                "this gateway was built without a persona loader, so it cannot assemble Val.",
            )
        return self._converse(
            messages,
            TaskType.LIGHT_CONVERSATION,
            scope=scope,
            turn=turn,
            classification=Classification.PROTECTED,
            max_output_tokens=max_output_tokens,
            configuration=None,
            on_delta=on_delta,
            egress=egress,
        )

    def _converse(
        self,
        messages: tuple[Message, ...],
        task_type: TaskType,
        *,
        scope: ProjectScope,
        turn: TurnReference,
        classification: Classification,
        max_output_tokens: int,
        configuration: ModelConfig | None,
        on_delta: DeltaSink | None,
        egress: Egress,
    ) -> GatewayResponse:
        """The body shared by `converse` and `converse_lightly`; each names its task."""
        if self._persona_loader is None:  # both callers checked; stated for the type
            raise PersonaUnavailableError(PersonaProblem.NONE_ACTIVE, "no persona loader")
        persona = self._persona_loader.active()
        request = assemble(
            persona,
            messages,
            classification=classification,
            task_type=task_type,
            scope=scope,
            turn=turn,
            max_output_tokens=max_output_tokens,
            egress=egress,
        )
        if configuration is None:
            return self._execute(request, on_delta=on_delta)

        # The pinned conversational path — WP-0.9's same-configuration rule
        # (ruling, 19 August 2026). Still `converse`: the persona was loaded
        # above and the provenance verifier still runs, so pinning narrows only
        # *which route*, never which checks. The named configuration must be
        # the registry's own entry and passes admission, eligibility, and the
        # budget on this call's own account. No fallback: if this route cannot
        # answer, the turn is unanswered — a silent config change would break
        # the same-configuration guarantee the caller pinned this for.
        self._refuse_restricted(request)
        self._refuse_incoherent_provenance(request)
        known = self._verify_named_configuration(
            configuration, request.classification, request.task_type
        )
        return self._attempt(request, known, content_parts(request), on_delta=on_delta)

    def active_persona_content(self) -> str | None:
        """The active persona's content, for binding a prepared answer; None if none is loaded."""
        if self._persona_loader is None:
            return None
        try:
            return self._persona_loader.active().content
        except PersonaUnavailableError:
            return None

    def converse_prospectively(
        self,
        messages: tuple[Message, ...],
        *,
        scope: ProjectScope,
        max_output_tokens: int,
        egress: Egress = Egress.LOCAL_ONLY,
    ) -> tuple[GatewayResponse, str]:
        """Prepare a light answer before the turn exists — owner order, 26 September 2026 (§6).

        The persona is loaded and assembled whole, exactly as `converse` does, and the
        call goes through the same execution body: Restricted refused, persona
        verified, budgeted, preflighted, routed by the light floor, **recorded** as
        `speculative_light_conversation` with no conversation or message, because the
        message it may answer has not been committed. Nothing it produces is spoken,
        persisted or remembered here; Core decides at acceptance whether it is bound to
        the completed request. Returns the response and the persona's content, which
        the binding is computed over.
        """
        if self._persona_loader is None:
            raise PersonaUnavailableError(
                PersonaProblem.NONE_ACTIVE,
                "this gateway was built without a persona loader, so it cannot prepare Val.",
            )
        persona = self._persona_loader.active()
        request = assemble(
            persona,
            messages,
            task_type=TaskType.SPECULATIVE_LIGHT,
            scope=scope,
            max_output_tokens=max_output_tokens,
            egress=egress,
            attributed=True,
        )
        return self._execute(request), persona.content

    def complete(
        self, request: GatewayRequest, *, on_delta: DeltaSink | None = None
    ) -> GatewayResponse:
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
        return self._execute(request, on_delta=on_delta)

    def _execute(
        self, request: GatewayRequest, *, on_delta: DeltaSink | None = None
    ) -> GatewayResponse:
        """The one execution body behind both entrances.

        Private on purpose: `converse` builds conversation requests and comes
        here directly, having just loaded the persona; `complete` comes here for
        non-conversation work after refusing anything conversational. There is
        exactly one copy of the guard order — Restricted, provenance, persona,
        budget, route — because two copies is how one of them drifts.
        """
        self._refuse_restricted(request)
        self._refuse_incoherent_provenance(request)
        self._refuse_unverified_persona(request)

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
                self._fits(config, parts, request.max_output_tokens)
                and self._affordable(config, request, parts, committed)
            ),
            resolve_fallback=fallback_for,
            # Ruling, 7 September 2026: the task's capability floor sits
            # between eligibility and cost, and cost never lowers it.
            profile=required_profile(request.task_type),
            # And cost is the total bound of this call at each candidate's
            # rates — the reservation figure — never the input rate alone.
            cost_bound=lambda config: maximum_cost(config, parts, request.max_output_tokens),
            on_tie=self._report_tie,
            # Owner ruling, 24 September 2026: a local-only request is routed
            # locally rather than routed anywhere and then refused.
            egress=request.egress,
        )
        if not order:
            raise GatewayError(
                GatewayErrorKind.NO_ELIGIBLE_ROUTE,
                self._no_route_detail(request, parts, committed),
            )
        self._refuse_paid_partner(
            order[0],
            request.classification,
            parts,
            request.max_output_tokens,
            profile=required_profile(request.task_type),
            requires_image_input=False,
        )

        last: GatewayError | None = None
        # Every call written on the way to failing, across routes, so the
        # failure that is finally raised names all of them (3 September 2026).
        attempted: list[UUID] = []
        for config in order:
            try:
                return self._attempt(request, config, parts, on_delta=on_delta)
            except GatewayError as error:
                last = error
                attempted.extend(error.model_call_ids)
                error.model_call_ids = tuple(attempted)
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
        self,
        request: GatewayRequest,
        config: ModelConfig,
        *,
        on_delta: DeltaSink | None = None,
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
        self._refuse_unverified_persona(request)

        known = self._verify_named_configuration(config, request.classification, request.task_type)
        return self._attempt(request, known, content_parts(request), on_delta=on_delta)

    def evaluate_with_configuration(
        self, request: GatewayRequest, config: ModelConfig
    ) -> GatewayResponse:
        """Run one call on a configuration registered for evaluation only.

        Ruling, 10 September 2026. A candidate for a capability floor has to be
        exercised through the real gateway — reservation, `model_calls` row,
        settlement — before it can be designated, and it must not be routable
        while it is being exercised. So a candidate is registered `NOT_ADMITTED`
        with **no capability profile**: routing can never select it, and the
        pinned path above refuses it for the floor. This door is the only way
        to reach it, and it is narrower than the pinned path, not wider:

        - the configuration must be the registry's own entry, not retired,
          `NOT_ADMITTED`, and declaring no profile — an admitted configuration
          is refused here, because a serving configuration is exercised
          through routing or the pinned path, never through the evaluation door;
        - the request must be schema-constrained structured work — an
          `output_schema` is required, and the task is neither conversation
          nor blind position, the two tasks in which Val speaks;
        - eligibility by classification is checked exactly as for any call
          (`refusal_for`, in `_attempt`), and the reservation is the ordinary one.

        Evaluation is not admission: nothing here changes what the registry
        says, and passing an evaluation confers no profile — designation is a
        recorded ruling that edits the entry.
        """
        if request.task_type in (TaskType.CONVERSATION, TaskType.BLIND_POSITION):
            raise GatewayError(
                GatewayErrorKind.INVALID_REQUEST,
                f"{request.task_type.value} is a task in which Val speaks; a configuration "
                "under evaluation never serves it (ruling, 10 September 2026)",
            )
        if request.output_schema is None:
            raise GatewayError(
                GatewayErrorKind.INVALID_REQUEST,
                "evaluation calls are schema-constrained structured work only; a request "
                "without an output schema is refused",
            )
        self._refuse_masquerade(request)
        self._refuse_restricted(request)
        self._refuse_unverified_persona(request)
        known = by_id(config.id)
        if known is None or known != config:
            raise GatewayError(
                GatewayErrorKind.NO_ELIGIBLE_ROUTE,
                f"configuration {config.slug!r} ({config.provider}/{config.model_identifier}) "
                "is not the Model Configuration Registry's entry for its id; a configuration "
                "assembled by a caller is not evaluated any more than it is routed to.",
            )
        if known.retired:
            raise GatewayError(
                GatewayErrorKind.NO_ELIGIBLE_ROUTE,
                f"{known.slug} is retired and is not evaluated.",
            )
        if known.admission is not Admission.NOT_ADMITTED or known.capability_profiles:
            raise GatewayError(
                GatewayErrorKind.NO_ELIGIBLE_ROUTE,
                f"{known.slug} is not an evaluation-only configuration (admission "
                f"{known.admission.value}, profiles "
                f"{sorted(profile.value for profile in known.capability_profiles)}); a "
                "configuration admitted to serve is exercised through routing or the pinned "
                "path, never through the evaluation door.",
            )
        if not is_eligible(known, request.classification):
            raise GatewayError(
                GatewayErrorKind.NO_ELIGIBLE_ROUTE,
                f"{known.slug} is not declared eligible for {request.classification.value} "
                "content; evaluation does not widen eligibility (00-charter.md invariant 17).",
            )
        return self._attempt(request, known, content_parts(request))

    def _verify_named_configuration(
        self, config: ModelConfig, classification: Classification, task_type: TaskType
    ) -> ModelConfig:
        """The registry's own entry for this id, or a refusal. Never the caller's copy."""
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
        if not is_admitted(known) or not is_eligible(known, classification):
            raise GatewayError(
                GatewayErrorKind.NO_ELIGIBLE_ROUTE,
                f"{known.slug} is not admitted for Layer 0 use, or not eligible for "
                f"{classification.value} content. Naming it explicitly does not "
                "admit it (00-charter.md invariant 17).",
            )
        floor = required_profile(task_type)
        if not satisfies_profile(known, floor):
            raise GatewayError(
                GatewayErrorKind.NO_ELIGIBLE_ROUTE,
                f"{known.slug} does not satisfy the {floor.value} capability profile that "
                f"{task_type.value} work requires. A pinned configuration below the floor "
                "is refused, not used (ruling, 7 September 2026).",
            )
        return known

    # --- one attempt on one configuration ------------------------------------

    def _attempt(
        self,
        request: GatewayRequest,
        config: ModelConfig,
        parts: tuple[str, ...],
        *,
        on_delta: DeltaSink | None = None,
    ) -> GatewayResponse:
        """Reserve, call, settle. Every exit leaves the reservation resolved."""
        # Owner ruling, 24 September 2026 (Voice work package 3 §1.5). **The
        # narrowest door every provider call passes through.** `_execute` already
        # declines to route a local-only request to a cloud configuration, and
        # `candidates` filters it out of the order; this is the check that holds
        # when a caller arrives by another entrance — `complete_with_configuration`
        # and the candidate lane among them — because a rule enforced only at the
        # place that happens to be convenient is not structural. It runs before
        # eligibility, before the adapter is looked up, before a runtime is asked
        # to come up and before anything is reserved, so a refused call transmits
        # nothing and charges nothing.
        egress_refusal = egress_refusal_for(request.egress, config)
        if egress_refusal is not None:
            kind, detail = egress_refusal
            # No row is written: a row would assert a call that never happened.
            raise GatewayError(kind, detail)

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

        # Owner ruling, 21 September 2026: an adapter that can bring its own
        # runtime up is asked to, before anything is reserved or transmitted, so
        # ordinary use never requires a terminal. Provider-neutral at this seam:
        # the core asks whether the capability is declared and learns nothing
        # about what is underneath. A runtime that cannot be brought up ends the
        # turn honestly — it is never a reason to try a paid route instead, which
        # is why the failure carries the same kind as the stop above.
        if supports_local_runtime(adapter):
            local = cast(LocalRuntimeAdapter, adapter)
            try:
                mark("runtime_ready_start")
                readiness = local.ensure_runtime_ready(config)
                mark("runtime_ready_end")
                self._observe_block(
                    "local runtime ready: "
                    + ", ".join(f"{key}={value}" for key, value in readiness.items())
                )
            except LocalRuntimeUnavailableError as failure:
                raise GatewayError(
                    GatewayErrorKind.LOCAL_PARTNER_UNAVAILABLE,
                    f"the local runtime for {config.slug} could not be made ready, and one "
                    f"bounded recovery attempt was made: {failure}. Nothing was transmitted "
                    "and nothing was charged; cloud escalation would need Lord Armand's "
                    "explicit approval (owner ruling, 21 September 2026).",
                ) from failure

        # Closure pass, 18 August 2026: the model's own limits are enforced
        # HERE, before a reservation is taken and before anything is
        # transmitted. Relying on the provider to reject an impossible request
        # would mean routing it, reserving money for it, and sending the
        # content — three things that should not happen to a call that cannot
        # succeed. Nothing is clamped: a request for more output than the model
        # supports is refused in those words, because silently serving less
        # than was asked is a quiet lie about what was authorised.
        # Ruling, 16 September 2026: on an unmetered local route the context
        # check is exact — the runtime's own rendering and tokenizer against
        # the window that is actually loaded — and the byte bound remains the
        # fail-closed fallback when the runtime cannot be measured. Cloud
        # routes are untouched: the byte bound governs them as before.
        feasibility: ContextFeasibility | None = None
        if config.metering is Metering.LOCAL_NO_METERED_COST and isinstance(
            adapter, ContextInspectingAdapter
        ):
            try:
                mark("exact_preflight_start")
                feasibility = adapter.measure_context(
                    config, request.messages, request.system, request.max_output_tokens
                )
                mark("exact_preflight_end")
            except ContextInspectionUnavailableError as why:
                _LOGGER.warning(
                    "local context measurement unavailable for %s (%s); failing closed on the "
                    "conservative bound",
                    config.slug,
                    why,
                )
        if feasibility is not None:
            if feasibility.context_tokens != config.context_window_tokens:
                _LOGGER.warning(
                    "%s: loaded runtime context %d disagrees with the registry's nominal %d; "
                    "the runtime governs",
                    config.slug,
                    feasibility.context_tokens,
                    config.context_window_tokens,
                )
            overrun = local_context_overrun(
                config,
                feasibility.prompt_tokens,
                feasibility.context_tokens,
                request.max_output_tokens,
            )
        else:
            overrun = limit_overrun(config, parts, request.max_output_tokens)
        if overrun is not None:
            raise GatewayError(GatewayErrorKind.INVALID_REQUEST, overrun)

        # Ruling, 8 September 2026: the reservation assumes a cache miss that
        # writes the whole prefix at the write premium, never a hit.
        cache_ttl = self._cache_ttl_for(config, request)
        authorised = maximum_cost(config, parts, request.max_output_tokens, cache_ttl)
        claim = self._ledger.reserve(
            config,
            authorised,
            request.task_type,
            request.project_id,
            exchange=request.exchange_reference,
        )
        if isinstance(claim, Refusal):
            # The ceiling stopped this call before the provider was contacted.
            # Nothing was sent, so nothing is recorded (accounting state NOT_SENT).
            raise GatewayError(
                GatewayErrorKind.BUDGET_EXCEEDED,
                ceiling_message(claim.committed_usd, claim.max_cost_usd),
            )
        if isinstance(claim, ExchangeEnvelopeRefusal):
            # Ruling, 13 September 2026: the exchange envelope stopped this call
            # before the provider was contacted. Not retryable — no cheaper
            # route is tried to fit the envelope — and nothing is recorded.
            raise GatewayError(
                GatewayErrorKind.EXCHANGE_ENVELOPE_EXCEEDED,
                exchange_envelope_message(
                    claim.exchange_committed_usd, claim.max_cost_usd, claim.envelope_usd
                ),
            )

        return self._call_and_settle(
            request, config, adapter, claim, cache_ttl, on_delta, feasibility=feasibility
        )

    def _cache_ttl_for(self, config: ModelConfig, request: GatewayRequest) -> CacheTtl | None:
        """Whether this call asks the provider to cache its stable prefix, and for how long.

        Ruling, 8 September 2026. Three conditions, all required: the gateway
        is configured with a TTL (`VAL_CACHE_TTL`); the configuration's caching
        is verified, with rates read from the provider (`caching = AVAILABLE`);
        and the stable prefix — the `system` text, which is the persona on
        every partner call — is at least the model's documented minimum
        cacheable length, judged by the local estimator. Below the minimum the
        provider would cache nothing and charge nothing, so nothing is
        requested and nothing is reserved for it.
        """
        if self._cache_ttl is None or request.system is None:
            return None
        # Ruling, 13 September 2026: a blind-position call never asks for a
        # cache. Its breakpoint already sat at the end of the persona, but the
        # provider renders the structured-output format's own system text inside
        # that prefix, so the prefix is always longer than the persona prefix the
        # response route caches (265 tokens on every blind call on record, under
        # two persona revisions) and can never read it. Blind calls are days
        # apart, so the one-hour write it paid for was never read either. The
        # request, persona, route, effort and schema are unchanged; only the
        # cache-control metadata is not sent, and the reservation is taken at
        # the base input rate instead of the write rate.
        if request.task_type is TaskType.BLIND_POSITION:
            return None
        if config.caching is not PricingFeature.AVAILABLE:
            return None
        # Ruling, 14 September 2026: a provider that caches automatically is
        # asked for no lifetime — it decides for itself, and what it reports is
        # priced at its verified rates and recorded in the measurement row.
        if config.caches_automatically:
            return None
        minimum = config.cache_minimum_prefix_tokens or 0
        if estimate_tokens(request.system) < minimum:
            return None
        return self._cache_ttl

    def _call_and_settle(
        self,
        request: GatewayRequest,
        config: ModelConfig,
        adapter: ProviderAdapter,
        claim: Reservation,
        cache_ttl: CacheTtl | None = None,
        on_delta: DeltaSink | None = None,
        *,
        feasibility: ContextFeasibility | None = None,
    ) -> GatewayResponse:
        """Contact the provider with a reservation held, and always resolve it.

        Val Core Phase 1 (11 September 2026): when a sink is given and the
        adapter declares streaming, the call runs as a stream — each text
        delta is forwarded to the sink as it arrives, the moment of the first
        delta is measured (`first_output_ms`), and the stream's terminal
        `ProviderResult` is settled by exactly the code that settles a
        completed call. Nothing downstream can tell the two apart except by
        that one figure. A stream that ends without a terminal result is a
        provider failure, settled as unknown like any other.
        """
        started = time.monotonic()
        first_output_ms: int | None = None
        streamed = on_delta is not None and supports_streaming(adapter)
        try:
            if streamed and on_delta is not None:
                result, first_output_ms = self._stream(
                    adapter, config, request, cache_ttl, on_delta, started
                )
            else:
                result = adapter.complete(
                    config,
                    request.messages,
                    request.system,
                    request.max_output_tokens,
                    output_schema=request.output_schema,
                    cache_ttl=cache_ttl,
                )
        except GatewayError as error:
            call_id = self._settle_unknown(
                request, config, claim, error, self._elapsed(started), streamed=streamed
            )
            # A fresh error naming exactly this attempt's call, never a
            # mutation of the adapter's own exception object: an adapter (or a
            # scripted one in tests) may raise the same instance twice, and
            # ids from an earlier call must not travel with it.
            raise GatewayError(
                error.kind, error.detail, model_call_ids=() if call_id is None else (call_id,)
            ) from error

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
        # Ruling, 8 September 2026: settled from the provider's four usage
        # figures — uncached input, cache writes by lifetime, cache reads, and
        # output — at the configuration's verified rates, stored at call time.
        cost: float | None = None
        cache_usage: CacheUsage | None = None
        if result.tokens_in is not None and result.tokens_out is not None:
            read = result.cache_read_tokens or 0
            write_5m = result.cache_write_5m_tokens or 0
            write_1h = result.cache_write_1h_tokens or 0
            write_auto = result.cache_write_auto_tokens or 0
            parts_usd = cost_components(
                config,
                result.tokens_in,
                result.tokens_out,
                cache_read=read,
                cache_write_5m=write_5m,
                cache_write_1h=write_1h,
                cache_write_auto=write_auto,
            )
            cost = round(sum(parts_usd), 6)
            if cache_ttl is None and (read or write_auto):
                _LOGGER.info(
                    "automatic prompt cache on %s: uncached=%d write=%d read=%d; cost $%.6f",
                    config.slug,
                    result.tokens_in,
                    write_auto,
                    read,
                    cost,
                )
            if cache_ttl is not None:
                if read and (write_5m or write_1h):
                    outcome = "hit_and_created"
                elif read:
                    outcome = "hit"
                elif write_5m or write_1h:
                    outcome = "created"
                else:
                    outcome = "not_cached"
                cache_usage = CacheUsage(
                    requested_ttl=cache_ttl,
                    uncached_input_tokens=result.tokens_in,
                    cache_write_5m_tokens=write_5m,
                    cache_write_1h_tokens=write_1h,
                    cache_read_tokens=read,
                    outcome=outcome,
                    cost_uncached_usd=round(parts_usd[0], 6),
                    cost_cache_write_usd=round(parts_usd[1], 6),
                    cost_cache_read_usd=round(parts_usd[2], 6),
                    cost_output_usd=round(parts_usd[3], 6),
                )
                _LOGGER.info(
                    "prompt cache: %s on %s (ttl %s): uncached=%d write_5m=%d write_1h=%d "
                    "read=%d; cost $%.6f",
                    outcome,
                    config.slug,
                    cache_ttl.value,
                    result.tokens_in,
                    write_5m,
                    write_1h,
                    read,
                    cost,
                )
        # Ruling, 16 September 2026: a LOCAL_NO_METERED_COST route has no
        # metered provider/API charge, so its monetary cost is a *known* $0
        # whether or not the runtime reported token usage — token telemetry
        # (NULL when unreported) and monetary certainty are separate facts. A
        # metered route with missing usage stays UNKNOWN exactly as before.
        if config.metering is Metering.LOCAL_NO_METERED_COST:
            cost = 0.0
            _LOGGER.info(
                "unmetered local route %s: provider/API cost $0 known; tokens %s",
                config.slug,
                "reported" if result.tokens_in is not None else "not reported",
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
                # The row's `tokens_in` is everything the provider processed as
                # input — uncached plus cached — so the column keeps meaning
                # "tokens sent"; the split lives in the cache-usage row.
                tokens_in=result.total_input_tokens,
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
                cache_usage=cache_usage,
                measurement=CallMeasurement(
                    exchange=request.exchange_reference,
                    streamed=streamed,
                    first_text_ms=first_output_ms,
                    text_output_chars=len(result.text),
                    reasoning_present=result.reasoning_present,
                    reasoning_output_tokens=result.reasoning_tokens,
                    provider_cached_input_tokens=result.cache_read_tokens,
                    provider_cache_write_tokens=_reported_cache_writes(result),
                    prompt_cache_key=result.prompt_cache_key,
                    cache_diagnostics=result.cache_diagnostics,
                    provider_reported_model=result.provider_reported_model,
                    runtime_diagnostics=_runtime_diagnostics(
                        config,
                        result.runtime_diagnostics,
                        feasibility=feasibility,
                        server_prompt_tokens=result.total_input_tokens,
                    ),
                ),
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
            tokens_in=result.total_input_tokens,
            tokens_out=result.tokens_out,
            cost_usd=cost,
            latency_ms=latency,
            provider_request_id=result.provider_request_id,
            # WP-0.9: evidence that must name its call — blind_positions —
            # names the row this call actually wrote.
            model_call_id=call_id,
            stop_reason=result.stop_reason,
            stop_details=result.stop_details,
            first_output_ms=first_output_ms,
        )

    def _stream(
        self,
        adapter: ProviderAdapter,
        config: ModelConfig,
        request: GatewayRequest,
        cache_ttl: CacheTtl | None,
        on_delta: DeltaSink,
        started: float,
    ) -> tuple[ProviderResult, int | None]:
        """Consume one streamed call, forwarding text deltas; return the terminal result.

        The gateway is the only consumer of the adapter's events: it forwards
        text to the Val Core-owned sink and keeps the terminal result for
        settlement. The sink is called with generated text only, in order. If
        the sink raises, the exception propagates as the caller's own failure
        after the provider stream is closed — it is not a provider error and is
        not normalized into one.
        """
        stream = adapter.stream(  # type: ignore[attr-defined]
            config,
            request.messages,
            request.system,
            request.max_output_tokens,
            output_schema=request.output_schema,
            cache_ttl=cache_ttl,
        )
        first_output_ms: int | None = None
        for event in stream:
            if isinstance(event, TextDelta):
                if event.text:
                    if first_output_ms is None:
                        first_output_ms = self._elapsed(started)
                    on_delta(event.text)
                continue
            if isinstance(event, ProviderResult):
                return event, first_output_ms
            raise GatewayError(
                GatewayErrorKind.PROVIDER_ERROR,
                f"{adapter.name}: the stream yielded an event of type "
                f"{type(event).__name__}, which the provider-neutral contract does not "
                "define; the call is treated as failed and settled as unknown",
            )
        raise GatewayError(
            GatewayErrorKind.PROVIDER_ERROR,
            f"{adapter.name}: the stream ended without a terminal result, so the call's "
            "outcome, usage and cost are unknown; nothing from it is handed onward",
        )

    def _settle_unknown(
        self,
        request: GatewayRequest,
        config: ModelConfig,
        claim: Reservation,
        error: GatewayError,
        latency_ms: int,
        *,
        streamed: bool = False,
    ) -> UUID | None:
        """A provider failure whose cost cannot be established.

        Returns the `model_calls` id written for the failed call, so the
        failure raised to the caller can name it.

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
                # Ruling, 16 September 2026: an unmetered local route's monetary
                # cost is a known $0 even for a failed attempt; a metered route's
                # failed attempt stays UNKNOWN, settled at its full maximum.
                cost_usd=0.0 if config.metering is Metering.LOCAL_NO_METERED_COST else None,
                cost_certainty=(
                    CostCertainty.KNOWN
                    if config.metering is Metering.LOCAL_NO_METERED_COST
                    else CostCertainty.UNKNOWN
                ),
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
                measurement=CallMeasurement(
                    exchange=request.exchange_reference,
                    streamed=streamed,
                    first_text_ms=None,
                    text_output_chars=None,
                    reasoning_present=None,
                    reasoning_output_tokens=None,
                    provider_cached_input_tokens=None,
                    provider_cache_write_tokens=None,
                    runtime_diagnostics=_runtime_diagnostics(config, None),
                ),
            )
        )
        self._ledger.settle(claim.id, None, CostCertainty.UNKNOWN, call_id)
        self._observe_block(
            f"{config.slug} failed with {error.kind.value} and reported no usage. "
            f"Recorded as unknown cost, and its reservation of "
            f"${claim.max_cost_usd:.4f} stays charged against this month."
        )
        return call_id

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
        if request.task_type in (
            TaskType.CONVERSATION,
            TaskType.LIGHT_CONVERSATION,
            TaskType.SPECULATIVE_LIGHT,
        ):
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

    def _refuse_unverified_persona(self, request: GatewayRequest) -> None:
        """A blind-position call attributes the active persona, verified, or does not run.

        *WP-0.9 ruling, 19 August 2026.* The blind call carries Val's persona
        (WP-0.5 as amended), so its `model_calls` row must name the revision —
        and the id must be the **active** persona's, checked against the WP-0.5
        loader here rather than trusted from the caller: a typed UUID naming a
        retired revision would record an identity that was not assembled.

        Both directions are guarded at the entrance as well as in the request
        validator, for the `model_copy` reason `_refuse_masquerade` states.
        """
        if request.task_type in PERSONA_ATTRIBUTED_TASKS:
            if request.persona is None:
                raise GatewayError(
                    GatewayErrorKind.INVALID_REQUEST,
                    f"a {request.task_type.value} call must carry its persona attribution: "
                    "it assembles Val's persona with no conversation to record it, and a "
                    "persona-bearing call recording NULL persona_id would be a false "
                    "record (WP-0.9 ruling, 19 August 2026).",
                )
            if self._persona_loader is None:
                raise GatewayError(
                    GatewayErrorKind.INVALID_REQUEST,
                    "this gateway was built without a persona loader, so it cannot "
                    f"verify that this {request.task_type.value} call attributes the active "
                    "persona. The call is refused rather than transmitted with an "
                    "unverified identity claim.",
                )
            active_persona = self._persona_loader.active()
            if request.persona.persona_id != active_persona.id:
                raise GatewayError(
                    GatewayErrorKind.INVALID_REQUEST,
                    f"persona attribution names revision {request.persona.persona_id}, "
                    f"but the active persona is {active_persona.id}. The record must "
                    "name the identity that was actually assembled; a stale or typed "
                    "id is refused before transmission (WP-0.9 ruling, 19 August 2026).",
                )
        elif request.persona is not None:
            raise GatewayError(
                GatewayErrorKind.INVALID_REQUEST,
                f"a {request.task_type.value!r} request may not carry persona "
                "attribution: classification, strip, and title assemble no persona "
                "(WP-0.5's deliberate narrowing), and a conversation's persona rides "
                "in its provenance. Refused before routing.",
            )

    def select_configuration(
        self,
        classification: Classification,
        parts: tuple[str, ...],
        max_output_tokens: int,
        *,
        task_type: TaskType,
        requires_image_input: bool = False,
    ) -> ModelConfig:
        """The configuration routing would choose for this work, without calling.

        *WP-0.9, 19 August 2026.* §4.1 requires the blind position and the
        response to use **the same model configuration, selected once**. The
        deliberation orchestrator selects here, then runs both calls pinned to
        the result — each still passing every admission, eligibility, and
        budget check on its own account. A mid-turn failure of the selected
        route leaves the turn unanswered rather than falling back: a silent
        config change between the two calls would produce a clean paper trail
        of an independence that never existed.
        """
        committed = self._ledger.committed_usd()
        floor = required_profile(task_type)
        order = attempt_order(
            active(),
            classification,
            is_ready=lambda config: config.provider in self._adapters,
            is_affordable=lambda config: (
                # A turn that shows something needs a route that can see it.
                # Ruled into selection on 21 September 2026, when a local Partner
                # route with no image capability joined the partner profile at
                # zero cost: cost ranks what the floor admits, so without this
                # the cheapest partner route would be pinned for an image turn
                # and refused later by the component that derives bytes. Track C
                # behaviour is unchanged by it — the one image-capable partner
                # route is still the one chosen.
                (not requires_image_input or can_carry_images(config))
                and self._fits(config, tuple(parts), max_output_tokens)
                and admits(committed, maximum_cost(config, parts, max_output_tokens))
            ),
            resolve_fallback=fallback_for,
            profile=floor,
            cost_bound=lambda config: maximum_cost(config, parts, max_output_tokens),
            on_tie=self._report_tie,
        )
        if not order:
            raise GatewayError(
                GatewayErrorKind.NO_ELIGIBLE_ROUTE,
                f"no configuration is admitted, eligible, qualified for the {floor.value} "
                f"capability profile, ready, and affordable for {classification.value} "
                "content of this size. Truthful unavailability, not a licence to "
                "downgrade or to lower the floor (01-architecture.md §5.4, §5.5).",
            )
        self._refuse_paid_partner(
            order[0],
            classification,
            tuple(parts),
            max_output_tokens,
            profile=floor,
            requires_image_input=requires_image_input,
        )
        return order[0]

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

    @staticmethod
    def _report_tie(first: str, second: str, bound: float) -> None:
        """Log a true cost tie the last-resort tie-break decided (ruling, 7 September 2026)."""
        _LOGGER.info(
            "cost ordering: true tie between %s and %s at a total bound of $%.6f; "
            "the order between them was decided by the stable last-resort "
            "tie-break (slug), not by cost",
            first,
            second,
            bound,
        )

    def _fits(self, config: ModelConfig, parts: tuple[str, ...], max_output_tokens: int) -> bool:
        """Whether this route can hold the request, as well as that can be known here.

        On a route the runtime measures exactly — an unmetered local one with an
        inspecting adapter — only the model's published output cap is applied,
        and the context question waits for the exact measurement `_attempt`
        makes against the window that is actually loaded. Everywhere else the
        conservative byte bound governs, unchanged.

        The reason is arithmetic, found on 21 September 2026: the byte bound
        counts the persona alone at about 23,600 tokens where the runtime counts
        about 5,000, so against a 32,768-token window it leaves roughly 3,000
        tokens of headroom and an ordinary conversation exhausts that almost at
        once. Striking the route out on that basis would end turns the model can
        comfortably answer. Nothing is loosened by this: the exact preflight
        still refuses what will not fit, before anything is transmitted, and it
        still falls back to the byte bound when the runtime cannot be measured.
        """
        adapter = self._adapters.get(config.provider)
        exactly_measured = (
            config.metering is Metering.LOCAL_NO_METERED_COST
            and adapter is not None
            and supports_context_inspection(adapter)
        )
        if exactly_measured:
            return output_cap_overrun(config, max_output_tokens) is None
        return limit_overrun(config, parts, max_output_tokens) is None

    def _refuse_paid_partner(
        self,
        chosen: ModelConfig,
        classification: Classification,
        parts: tuple[str, ...],
        max_output_tokens: int,
        *,
        profile: CapabilityProfile,
        requires_image_input: bool,
    ) -> None:
        """Stop before a Partner-class call the local route should have carried.

        Owner ruling, 21 September 2026. Placed **after** the order is computed
        and **before** anything is attempted, so nothing is transmitted, nothing
        is reserved and nothing is charged. `local_alternative` is blind to
        readiness on purpose: the local runtime being down is the case this
        exists for, not a reason to decide the work was never local work.
        """

        def can_hold(config: ModelConfig) -> bool:
            """Whether the local route was *the kind of route* this request needed.

            Capability only, and deliberately **not** the size estimate. The
            house's byte bound is a conservative pre-routing guess — it counts
            the persona alone at about five times the runtime's own figure — and
            letting it answer this question would mean that "our estimate says it
            might not fit" silently became authority to spend the owner's money
            on a cloud Partner model. It is not. A request the local route cannot
            hold stops with a reason, which is the rule as ruled on 21 September
            2026. A request it was never capable of — a turn carrying images,
            which it has no image input for — is a different matter, and is the
            one thing still checked here.
            """
            return not requires_image_input or can_carry_images(config)

        refusal = paid_partner_refusal(
            chosen,
            local_alternative(active(), classification, profile=profile, can_hold=can_hold),
            profile=profile,
        )
        if refusal is not None:
            raise GatewayError(GatewayErrorKind.LOCAL_PARTNER_UNAVAILABLE, refusal)

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
        # Owner ruling, 24 September 2026. A local-only request that found no
        # route is a different situation from an ineligible one, and saying so is
        # the difference between "the house cannot answer this here" and "the
        # house will not answer this at all".
        if request.local_only:
            local = [
                config
                for config in active()
                if is_admitted(config)
                and config.hosting is Hosting.LOCAL
                and is_eligible(config, request.classification)
                and satisfies_profile(config, required_profile(request.task_type))
            ]
            if not local:
                return (
                    "This conversation is local-only, because live-voice content is in it or "
                    "was recalled into it, and no configuration that runs on this machine is "
                    f"admitted, eligible and qualified for the "
                    f"{required_profile(request.task_type).value} capability profile this "
                    "work requires. Nothing was transmitted: the transcript does not leave "
                    "this machine to obtain an answer (owner ruling, 24 September 2026)."
                )
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
        floor = required_profile(request.task_type)
        qualified = [config for config in eligible if satisfies_profile(config, floor)]
        if not qualified:
            return (
                f"No eligible configuration is qualified for the {floor.value} capability "
                f"profile that {request.task_type.value} work requires. I will not lower the "
                "floor to a cheaper or merely available route (ruling, 7 September 2026)."
            )
        ready = [config for config in qualified if config.provider in self._adapters]
        if not ready:
            return (
                f"Every configuration qualified for the {floor.value} capability profile "
                "is missing its adapter or its credential in this process. No call was "
                "made, and no route below the floor was tried in its place."
            )
        if not any(self._affordable(config, request, parts, committed) for config in ready):
            return no_affordable_route_message(committed)
        return f"No route qualified for the {floor.value} capability profile could be selected."

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
