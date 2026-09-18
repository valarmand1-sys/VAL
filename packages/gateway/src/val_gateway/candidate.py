"""The candidate lane — the one way an unqualified configuration speaks as Val, on a scratch store.

Ruling, 14 September 2026. A configuration new to the house has to be exercised
on partner-class work before it can be qualified for the partner floor, and it
must do so **without ever pretending to be qualified**: not admitted, no
capability profile, never routable, never a fallback, recorded under its own
identity. The historical packet harnesses achieved qualification by
substituting an already-admitted entry in memory; that would represent a new
candidate as something it is not, and is not used here.

## The construction is the safety property

`CandidateGateway` is a distinct type. It exists only when
`candidate_gateway_for_scratch_store` builds it, and that factory refuses any
database whose name does not end in `_test` — the repository's one trusted
scratch-store identity (`packages/domain/migrations/env.py`; the test
fixtures). Production startup (`val_gateway.startup.start`) constructs a plain
`Gateway`, no HTTP contract names a configuration, and a plain `Gateway` has
no candidate method to call. The live service cannot become a candidate lane
by flipping a flag, because there is no flag.

## What the lane reuses, and what it adds

The two candidate methods are the pinned `converse` and the pinned blind path
with **one check exchanged**: `_verify_candidate_configuration` in place of
`_verify_named_configuration`. Everything else is the ordinary gateway code —
persona loaded whole per call and attributed, Restricted preflight, the
provenance verifier, the persona-attribution check, the model-limit check,
the reservation with exchange identity, the call, settlement, the
`model_calls` row under the candidate's own id, the measurement row, and the
terminal-state semantics. `_attempt` has no fallback, so neither does this.

The exchanged check admits exactly: the registry's own entry for its id,
identical in every field; not retired; `NOT_ADMITTED`; declaring no capability
profile; carrying the task's `QualificationTarget`; eligible for the content's
classification; and only the two tasks in which Val speaks. Classification and
strip never come through here — the deliberation orchestrator routes them as
always, and pins only the partner-class calls to the candidate.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import cast
from uuid import UUID

from sqlalchemy import Engine

from val_domain.gateway import (
    Admission,
    CacheTtl,
    Classification,
    GatewayError,
    GatewayErrorKind,
    GatewayRequest,
    GatewayResponse,
    Message,
    ModelConfig,
    QualificationTarget,
    TaskType,
    TurnReference,
)
from val_domain.project import ProjectScope
from val_domain.provider import (
    ContextFeasibility,
    ContextInspectingAdapter,
    ContextInspectionUnavailableError,
    DeltaSink,
    ProviderAdapter,
    supports_context_inspection,
)
from val_domain.registry import by_id
from val_gateway.context import assemble
from val_gateway.gateway import CallRecorder, Gateway, content_parts
from val_gateway.ledger import BudgetLedger
from val_gateway.persona import PersonaLoader, PersonaProblem, PersonaUnavailableError
from val_policy.routing import is_eligible

_LOGGER = logging.getLogger("val.candidate")

#: The tasks a candidate may be exercised on, and the target each requires.
_CANDIDATE_TASKS: dict[TaskType, QualificationTarget] = {
    TaskType.CONVERSATION: QualificationTarget.PARTNER,
    TaskType.BLIND_POSITION: QualificationTarget.PARTNER,
}


class ScratchStoreRequiredError(Exception):
    """The candidate lane was asked to exist against a store that is not scratch."""


def scratch_store_or_refuse(engine: Engine) -> None:
    """Refuse, before anything is built, unless the engine's database is a scratch store.

    The trusted identity is the database name's `_test` suffix — the same rule
    the migration environment uses to refuse live without `-x deploy=live`,
    and the test fixtures use to refuse to write anywhere else.
    """
    name = engine.url.database or ""
    if not name.endswith("_test"):
        raise ScratchStoreRequiredError(
            f"the candidate lane runs only against a scratch store whose database name ends "
            f"in '_test'; refusing {name!r}. An unqualified configuration never speaks as Val "
            "against the house's record (ruling, 14 September 2026)."
        )


class CandidateGateway(Gateway):
    """A gateway that can also exercise a registered candidate on partner-class work.

    Everything a `Gateway` is, plus two methods. Build it only through
    `candidate_gateway_for_scratch_store`.
    """

    def converse_candidate(
        self,
        messages: tuple[Message, ...],
        *,
        scope: ProjectScope,
        turn: TurnReference,
        configuration: ModelConfig,
        classification: Classification = Classification.PROTECTED,
        max_output_tokens: int = 4096,
        on_delta: DeltaSink | None = None,
    ) -> GatewayResponse:
        """`converse`, pinned to a candidate: the same assembly, the same checks, one exchanged."""
        if self._persona_loader is None:
            raise PersonaUnavailableError(
                PersonaProblem.NONE_ACTIVE,
                "this gateway was built without a persona loader, so it cannot assemble Val; "
                "a candidate is never exercised without her persona.",
            )
        persona = self._persona_loader.active()
        request = assemble(
            persona,
            messages,
            classification=classification,
            task_type=TaskType.CONVERSATION,
            scope=scope,
            turn=turn,
            max_output_tokens=max_output_tokens,
        )
        self._refuse_restricted(request)
        self._refuse_incoherent_provenance(request)
        known = self._verify_candidate_configuration(
            configuration, request.classification, request.task_type
        )
        return self._attempt(request, known, content_parts(request), on_delta=on_delta)

    def measure_candidate_context(
        self,
        messages: tuple[Message, ...],
        *,
        scope: ProjectScope,
        turn: TurnReference,
        configuration: ModelConfig,
        classification: Classification = Classification.PROTECTED,
    ) -> ContextFeasibility | None:
        """Measure exactly what `converse_candidate` would send, without sending it.

        Ruling, 16 September 2026: the same assembly (persona whole, the same
        messages) and the same candidate checks, then the adapter's exact
        measurement against the loaded runtime. `None` means the adapter cannot
        measure — the caller falls back to the conservative bound; nothing is
        estimated here.
        """
        if self._persona_loader is None:
            raise PersonaUnavailableError(
                PersonaProblem.NONE_ACTIVE,
                "this gateway was built without a persona loader, so it cannot assemble Val.",
            )
        persona = self._persona_loader.active()
        request = assemble(
            persona,
            messages,
            classification=classification,
            task_type=TaskType.CONVERSATION,
            scope=scope,
            turn=turn,
        )
        known = self._verify_candidate_configuration(
            configuration, request.classification, request.task_type
        )
        adapter = self._adapters.get(known.provider)
        if adapter is None or not supports_context_inspection(adapter):
            return None
        inspecting = cast(ContextInspectingAdapter, adapter)
        try:
            return inspecting.measure_context(
                known, request.messages, request.system, request.max_output_tokens
            )
        except ContextInspectionUnavailableError as why:
            _LOGGER.warning("candidate context measurement unavailable for %s: %s", known.slug, why)
            return None

    def complete_candidate(
        self, request: GatewayRequest, configuration: ModelConfig
    ) -> GatewayResponse:
        """The pinned blind-position call on a candidate. Blind position only."""
        if request.task_type is not TaskType.BLIND_POSITION:
            raise GatewayError(
                GatewayErrorKind.INVALID_REQUEST,
                f"{request.task_type.value} is not exercised on a candidate through this "
                "method: the blind position is the one non-conversation task in which Val "
                "speaks; classification and strip route as always.",
            )
        self._refuse_masquerade(request)
        self._refuse_restricted(request)
        self._refuse_unverified_persona(request)
        known = self._verify_candidate_configuration(
            configuration, request.classification, request.task_type
        )
        return self._attempt(request, known, content_parts(request))

    def _verify_candidate_configuration(
        self, config: ModelConfig, classification: Classification, task_type: TaskType
    ) -> ModelConfig:
        """The registry's own candidate entry, or a refusal. Never the caller's copy."""
        target = _CANDIDATE_TASKS.get(task_type)
        if target is None:
            raise GatewayError(
                GatewayErrorKind.INVALID_REQUEST,
                f"{task_type.value} is not a task a candidate is qualified on",
            )
        known = by_id(config.id)
        if known is None or known != config:
            raise GatewayError(
                GatewayErrorKind.NO_ELIGIBLE_ROUTE,
                f"configuration {config.slug!r} ({config.provider}/{config.model_identifier}) "
                "is not the Model Configuration Registry's entry for its id; a configuration "
                "assembled by a caller is not exercised any more than it is routed to.",
            )
        if known.retired:
            raise GatewayError(
                GatewayErrorKind.NO_ELIGIBLE_ROUTE,
                f"{known.slug} is retired; retirement closes the candidate lane too.",
            )
        if known.admission is not Admission.NOT_ADMITTED or known.capability_profiles:
            raise GatewayError(
                GatewayErrorKind.NO_ELIGIBLE_ROUTE,
                f"{known.slug} is not a candidate (admission {known.admission.value}, profiles "
                f"{sorted(p.value for p in known.capability_profiles)}); a serving "
                "configuration is exercised through routing or the pinned path, never here.",
            )
        if target not in known.qualification_targets:
            raise GatewayError(
                GatewayErrorKind.NO_ELIGIBLE_ROUTE,
                f"{known.slug} carries no qualification target for {task_type.value}; a "
                "candidate is marked for a floor by ruling before it is exercised on it.",
            )
        if not is_eligible(known, classification):
            raise GatewayError(
                GatewayErrorKind.NO_ELIGIBLE_ROUTE,
                f"{known.slug} is not declared eligible for {classification.value} content; "
                "the candidate lane does not widen eligibility (00-charter.md invariant 17).",
            )
        return known


def candidate_gateway_for_scratch_store(
    engine: Engine,
    *,
    adapters: dict[str, ProviderAdapter],
    recorder: CallRecorder,
    ledger: BudgetLedger,
    persona_loader: PersonaLoader,
    verify_provenance: Callable[[GatewayRequest], None],
    observe_block: Callable[[str], None] | None = None,
    cache_ttl: CacheTtl | None = None,
) -> CandidateGateway:
    """The only constructor of a candidate lane: refuses first, builds second.

    `engine` is the store the recorder, ledger, persona loader and verifier are
    bound to; it is checked, not trusted. The persona loader and the
    provenance verifier are required, not optional, because a candidate turn
    is a Val turn and runs under every check a Val turn runs under.
    """
    scratch_store_or_refuse(engine)
    return CandidateGateway(
        adapters=adapters,
        recorder=recorder,
        ledger=ledger,
        observe_block=observe_block,
        persona_loader=persona_loader,
        verify_provenance=verify_provenance,
        cache_ttl=cache_ttl,
    )


__all__ = [
    "CandidateGateway",
    "ScratchStoreRequiredError",
    "candidate_gateway_for_scratch_store",
    "scratch_store_or_refuse",
]

# Referenced so the type is part of this module's stated contract.
_ = UUID
