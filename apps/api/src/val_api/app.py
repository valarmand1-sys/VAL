"""The FastAPI service behind the text interface — WP-0.10.

`04-layer-0.md` WP-0.10: *"the interface supports daily use without developer
tooling."* This service is the interface's only door to the house: the desktop
shell reaches it over HTTP and imports nothing (`components.toml`), and every
route here is a thin projection over the same writers and readers the rest of
Layer 0 already proved — `deliberate.send` for turns, `record_event` and
`record_deliberation` for judgments, the authoritative tables for every read.

**Invariant 29 is enforced in the contracts, not the styling.** A response can
carry a deliberation outcome only when a `deliberations` row exists; a blind
position always carries its recorded `ordering`, so a contaminated position
cannot be projected as independently formed; an unanswered turn is a shape
with no Val message in it; and the cost view says plainly when its figure is
not complete. The interface renders these shapes — it cannot invent states
they cannot express.

**What this service refuses to be.** It exposes no generic SQL, no raw
gateway entrance, no way to write a table except through the writers, and no
tool of any kind — Layer 0 has no tools, and an HTTP surface is not a reason
to acquire one.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine

from val_api.contracts import (
    BlindPositionView,
    CandidateView,
    ConversationDetail,
    ConversationView,
    CostView,
    DeliberationGlimpse,
    DeliberationView,
    DisagreementSignal,
    ExecutionEventRequest,
    ExecutionEventView,
    Health,
    ManualDeliberationRequest,
    MessageView,
    ProjectView,
    TurnAnswered,
    TurnClarification,
    TurnRequest,
    TurnResponse,
    TurnTruncated,
    TurnUnanswered,
)
from val_domain.deliberation import ClassifiedBy
from val_gateway import conversations
from val_gateway.conversations import ConversationNotFoundError
from val_gateway.deliberate import send as deliberated_send
from val_gateway.deliberation import (
    IncoherentDeliberationError,
    blind_positions_for,
    deliberations_for,
    last_disagreement_at,
    record_deliberation,
)
from val_gateway.exchange import ClarificationNeeded, RestrictedContentRefusedError
from val_gateway.execution import (
    IncoherentEventError,
    ReasonRequiredError,
    events_for,
    record_event,
)
from val_gateway.gateway import Gateway
from val_gateway.loop import TruncatedTurn, Turn, UnansweredTurn
from val_gateway.persistence import (
    month_to_date_spend,
    spend_by_task_type,
    uncosted_calls_this_month,
)
from val_gateway.projects import load_catalogue, project_listing
from val_policy.project_resolution import ProjectSignals


def create_app(engine: Engine, gateway: Gateway, warnings: list[str] | None = None) -> FastAPI:
    """The service, wired to an already-started house.

    The caller supplies the engine and a gateway that `val_gateway.startup`
    has already built — startup enforcement (eligibility, keys, ledger sweep)
    happens there, before this function is reachable, so a running service is
    one that was allowed to start (`04-layer-0.md` WP-0.4).
    """
    app = FastAPI(title="Val", version="0.0.0")

    # The desktop shell is a browser client on its own origin (Tauri serves the
    # interface from tauri://localhost on macOS, http://tauri.localhost on
    # Windows), so the webview enforces CORS on every call here — found in real
    # use, 31 August 2026, when a healthy service was invisible to the app
    # because its preflights were answered 405. This grant is browser policy,
    # not reachability: the loopback-only bind is untouched, and exactly the
    # shell's origins are granted, nothing wider.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["tauri://localhost", "http://tauri.localhost"],
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )
    startup_warnings = list(warnings or [])

    @app.get("/health")
    def health() -> Health:
        return Health(status="running", warnings=startup_warnings)

    # --- reads: projections of the authoritative record ----------------------

    @app.get("/projects")
    def projects(archived: bool = False) -> list[ProjectView]:
        """Projects, archived ones excluded unless asked for — display scoping only."""
        return [
            ProjectView.of(record) for record in project_listing(engine, include_archived=archived)
        ]

    @app.get("/conversations")
    def conversation_listing(
        project_id: UUID | None = None, scope: str | None = None, archived: bool = False
    ) -> list[ConversationView]:
        """All conversations, one project's, or the explicitly-no-project ones.

        `archived=true` includes archived rows; the flag is presentation
        scoping and carries no evidentiary meaning (§2.1 amendment, 31 August
        2026). Everything outside these two listings is archive-blind.
        """
        records = conversations.listing(
            engine,
            project_id=project_id,
            explicit_none=scope == "none",
            include_archived=archived,
        )
        return [ConversationView.of(record) for record in records]

    @app.get("/conversations/{conversation_id}")
    def conversation_detail(conversation_id: UUID) -> ConversationDetail:
        try:
            record = conversations.load(engine, conversation_id)
        except ConversationNotFoundError as missing:
            raise HTTPException(status_code=404, detail=str(missing)) from missing
        return ConversationDetail(
            conversation=ConversationView.of(record),
            messages=[
                MessageView.of(message)
                for message in conversations.history(engine, conversation_id)
            ],
            blind_positions=[
                BlindPositionView.of(row) for row in blind_positions_for(engine, conversation_id)
            ],
            deliberations=[
                DeliberationView.of(row) for row in deliberations_for(engine, conversation_id)
            ],
            execution_events=[
                ExecutionEventView.of(row) for row in events_for(engine, conversation_id)
            ],
        )

    # --- the turn -------------------------------------------------------------

    @app.post("/turns")
    def turn(request: TurnRequest) -> TurnResponse:
        """One thing said to Val, through the full WP-0.9 deliberated path."""
        try:
            outcome = deliberated_send(
                engine,
                gateway,
                request.content,
                catalogue=load_catalogue(engine),
                signals=ProjectSignals(
                    explicit_selection=request.project,
                    explicit_no_project=request.no_project,
                ),
                conversation_id=request.conversation_id,
                title=request.title,
                max_output_tokens=request.max_output_tokens,
            )
        except RestrictedContentRefusedError as refusal:
            # A refusal to transmit is not a transport error and must never be
            # quiet (WP-0.7 §15). 403: the request was understood and refused.
            raise HTTPException(status_code=403, detail=str(refusal)) from refusal

        if isinstance(outcome, ClarificationNeeded):
            return TurnClarification(
                question=outcome.question,
                reason=str(outcome.reason.value),
                candidates=[
                    CandidateView(project_id=c.project_id, name=c.name, slug=c.slug)
                    for c in outcome.candidates
                ],
            )
        if isinstance(outcome, UnansweredTurn):
            return TurnUnanswered(
                conversation=ConversationView.of(outcome.conversation),
                user_message=MessageView.of(outcome.user_message),
                error=str(outcome.error),
            )

        glimpse = DeliberationGlimpse(
            captured_as=outcome.captured_as,
            hard_exclusion=outcome.hard_exclusion,
            blind=None if outcome.blind is None else BlindPositionView.of(outcome.blind),
            deliberation=(
                None if outcome.deliberation is None else DeliberationView.of(outcome.deliberation)
            ),
        )
        if isinstance(outcome.turn, TruncatedTurn):
            return TurnTruncated(
                conversation=ConversationView.of(outcome.turn.conversation),
                user_message=MessageView.of(outcome.turn.user_message),
                partial_text=outcome.turn.partial_text,
                glimpse=glimpse,
            )
        settled: Turn = outcome.turn
        return TurnAnswered(
            conversation=ConversationView.of(settled.conversation),
            user_message=MessageView.of(settled.user_message),
            val_message=MessageView.of(settled.val_message),
            glimpse=glimpse,
        )

    # --- recording: the two in-flow writers ------------------------------------

    @app.post("/execution-events")
    def execution_event(request: ExecutionEventRequest) -> ExecutionEventView:
        """Record one judgment — WP-0.8's writer, with its prompt surfaced.

        A missing reason is not an error to swallow: the 422 carries
        `reason_required` so the interface can put the question in place,
        exactly as the WP-0.8 criterion asks, and the declination path stays
        one explicit flag.
        """
        try:
            recorded = record_event(
                engine,
                conversation_id=request.conversation_id,
                message_id=request.message_id,
                subject=request.subject,
                event_type=request.event_type,
                reaction=request.reaction,
                reason=request.reason,
                reason_inferred=request.reason_inferred,
                declined_to_give_reason=request.declined_to_give_reason,
            )
        except ReasonRequiredError as prompt:
            raise HTTPException(
                status_code=422,
                detail={"reason_required": True, "message": str(prompt)},
            ) from prompt
        except IncoherentEventError as incoherent:
            raise HTTPException(status_code=422, detail=str(incoherent)) from incoherent
        return ExecutionEventView.of(recorded)

    @app.post("/deliberations")
    def manual_deliberation(request: ManualDeliberationRequest) -> DeliberationView:
        """Mark an exchange consequential by hand — §4.8's override channel."""
        if request.classified_by is ClassifiedBy.AUTOMATIC:
            raise HTTPException(
                status_code=422,
                detail=(
                    "classified_by=automatic is the orchestrator's own provenance. A "
                    "hand-entered record claiming the classifier made it would be a "
                    "false record; state user or val (02-partner-systems.md §4.8)."
                ),
            )
        try:
            recorded = record_deliberation(
                engine,
                conversation_id=request.conversation_id,
                message_id=request.message_id,
                position=request.position,
                confidence=request.confidence,
                reasoning=request.reasoning,
                stripped_content=request.stripped_content,
                ordering=request.ordering,
                user_response=request.user_response,
                outcome=request.outcome,
                what_changed_her_mind=request.what_changed_her_mind,
                both_positions=request.both_positions,
                predictions=request.predictions,
                classification=request.classification,
                classified_by=request.classified_by,
                blind_position_id=request.blind_position_id,
            )
        except IncoherentDeliberationError as incoherent:
            raise HTTPException(status_code=422, detail=str(incoherent)) from incoherent
        return DeliberationView.of(recorded)

    # --- the cost view and the drift signal -------------------------------------

    @app.get("/costs")
    def costs() -> CostView:
        uncosted = uncosted_calls_this_month(engine)
        return CostView(
            month_to_date_usd=month_to_date_spend(engine),
            by_task_type=spend_by_task_type(engine),
            uncosted_calls=uncosted,
            complete=uncosted == 0,
        )

    @app.get("/signals/disagreement")
    def disagreement() -> DisagreementSignal:
        return DisagreementSignal(last_disagreement_at=last_disagreement_at(engine))

    return app
