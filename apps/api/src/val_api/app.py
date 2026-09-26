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

import json
import logging
import time
from base64 import b64decode, b64encode
from binascii import Error as BinasciiError
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import Engine, text
from starlette.concurrency import run_in_threadpool

from val_api.contracts import (
    AdoptedFragmentRequest,
    BlindPositionView,
    CandidateView,
    ClassificationReviewView,
    ClassificationView,
    ConversationDetail,
    ConversationView,
    CostView,
    DeliberationGlimpse,
    DeliberationView,
    DeliveryView,
    DesktopTimingReport,
    DisagreementSignal,
    ExecutionEventRequest,
    ExecutionEventView,
    Health,
    InterruptedUtteranceView,
    LabelledExchangeView,
    LabelRequest,
    LiveDeliveryView,
    ManualDeliberationRequest,
    MessageView,
    MoveRequest,
    PlaybackEventView,
    PlaybackReport,
    ProjectCreateRequest,
    ProjectView,
    QueuedExchangeView,
    RemovalRequest,
    RenameRequest,
    RetractionRequest,
    ReviewProgressView,
    ReviewRequest,
    RevisionRequest,
    RevisionView,
    ScopeTransitionView,
    SpeechEndView,
    SpeechOfferView,
    SpeechView,
    SpokenAudioView,
    TurnAnswered,
    TurnClarification,
    TurnRequest,
    TurnResponse,
    TurnTruncated,
    TurnUnanswered,
    VoiceCommittedView,
    VoiceSessionRequest,
    VoiceSessionView,
    VoiceTurnView,
)
from val_api.streaming import turn_event_stream
from val_domain.deliberation import ClassifiedBy, Ordering
from val_domain.gateway import (
    CapabilityProfile,
    Classification,
    GatewayError,
    ModelConfig,
)
from val_domain.registry import active
from val_domain.speech import SpeechRefusedError, SpeechUnavailableError
from val_domain.voice import LiveRecognizer, VoiceUnavailableError
from val_gateway import conversations
from val_gateway.attachments import (
    CandidateAttachment,
    acts_for_message,
    blob_bytes,
)
from val_gateway.classification_review import (
    ReviewRefusedError,
    disagreements,
    labelled,
    progress,
    record_label,
    record_review,
    review_queue,
)
from val_gateway.conversations import (
    ConversationNotFoundError,
    ConversationRemovedError,
    RemovalRefusedError,
    ScopeTransitionRefusedError,
    TitleRefusedError,
)
from val_gateway.deliberate import DeliberatedOutcome, prepare_light_answer
from val_gateway.deliberate import send as deliberated_send
from val_gateway.deliberation import (
    IncoherentDeliberationError,
    blind_positions_for,
    classifications_for,
    deliberations_for,
    last_disagreement_at,
    record_deliberation,
)
from val_gateway.delivery import SpeechDelivery, delivery_for
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
    response_call_recorded,
    spend_by_task_type,
    uncosted_calls_this_month,
)
from val_gateway.playback import (
    DesktopSink,
    PlaybackEvent,
    PlaybackState,
    playback_of,
    record_playback,
)
from val_gateway.projects import (
    ProjectCreationRefusedError,
    create_project,
    load_catalogue,
    project_listing,
)
from val_gateway.revisions import RevisionRefusedError, retract, revise
from val_gateway.seal import SealRoute
from val_gateway.speculation import PreparedAnswer
from val_gateway.speech import register_voice, speak_message
from val_gateway.voice import NO_SESSION, VoiceSession, VoiceSessions, interrupted
from val_policy.attachments import AdmissionRefusedError
from val_policy.light_conversation import FastRoute
from val_policy.project_resolution import ProjectSignals
from val_policy.routing import is_admitted, satisfies_profile
from val_providers.qwen_tts_speech import VOICE_RECORD

_LOGGER = logging.getLogger("val.api")


def _revision_http_error(refused: RevisionRefusedError) -> HTTPException:
    """A refused revision or retraction, with the writer's words and a fitting status."""
    status = {"not_found": 404, "restricted": 403, "empty": 422}.get(refused.reason, 409)
    return HTTPException(
        status_code=status, detail={"reason": refused.reason, "message": str(refused)}
    )


def speech_configuration() -> ModelConfig | None:
    """The admitted local speech route, or `None`.

    Selected by the profile it declares, never by name — the same rule every
    other capability floor uses.
    """
    for config in active():
        if is_admitted(config) and satisfies_profile(config, CapabilityProfile.SPEECH):
            return config
    return None


def voice_record(path: Path = VOICE_RECORD) -> dict[str, object]:
    """The governed voice's own description, as written when it was designed."""
    described: dict[str, object] = json.loads(path.read_text())
    return described


def create_app(
    engine: Engine,
    gateway: Gateway,
    warnings: list[str] | None = None,
    *,
    recognizers: Callable[[], LiveRecognizer] | None = None,
    fast_route: FastRoute | None = None,
    speculation: bool = False,
    adaptive_grace: bool = False,
) -> FastAPI:
    """The service, wired to an already-started house.

    `fast_route` (26 September 2026) is the candidate's enabled light tiers, from
    startup; `None` or disabled in production. It reaches only the microphone's door.

    The caller supplies the engine and a gateway that `val_gateway.startup`
    has already built — startup enforcement (eligibility, keys, ledger sweep)
    happens there, before this function is reachable, so a running service is
    one that was allowed to start (`04-layer-0.md` WP-0.4).
    """
    #: The live voice sessions this process is listening with. In-process because
    #: a live session *is* process state — it holds a subprocess and volatile
    #: audio buffers — and could not be resumed from a store if it tried.
    # When the last Voice session ends, the resident speech worker is stopped with it.
    sessions = VoiceSessions(on_empty=gateway.release_voice)
    #: Segments handed to a desktop before her answer was written, per session: there
    #: was no message to record the hand-off against yet. Written, with the time it
    #: happened, once the delivery names its answer (targeted voice latency order).
    unbound_handoffs: dict[UUID, list[tuple[object, int, str, datetime]]] = {}

    def settle_handoffs(session: UUID, live: VoiceSession) -> None:
        waiting = unbound_handoffs.get(session)
        if not waiting:
            return
        still: list[tuple[object, int, str, datetime]] = []
        for delivery, index, spoken, at in waiting:
            named = getattr(delivery, "message_id", None)
            if named is None:
                still.append((delivery, index, spoken, at))
                continue
            record_playback(
                engine,
                message_id=named,
                segment_index=index,
                state=PlaybackState.AVAILABLE_TO_DESKTOP,
                spoken_text=spoken,
                voice_session_id=live.session_id,
                observed_at=at,
            )
        if still:
            unbound_handoffs[session] = still
        else:
            unbound_handoffs.pop(session, None)

    if recognizers is not None:
        # A window that went away without its close request reaching here leaves a
        # session nobody asks about; it is closed rather than kept listening
        # (owner diagnostic, 25 September 2026).
        sessions.start_reaper()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """A recognizer is a subprocess; the service does not leave one behind."""
        yield
        sessions.close_all()

    app = FastAPI(title="Val", version="0.0.0", lifespan=lifespan)

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

    @app.post("/projects", status_code=201)
    def new_project(request: ProjectCreateRequest) -> ProjectView:
        """Create a project by name — ruled 7 September 2026.

        A daily-use, project-aware interface in which the user cannot create a
        project is an operational hole next to "conducted through the
        interface, with no developer tooling." A name taken by an existing
        project, archived or not, is refused in words (409): the user chooses
        another name rather than the house inventing a suffix.
        """
        try:
            return ProjectView.of(create_project(engine, request.name))
        except ProjectCreationRefusedError as refused:
            raise HTTPException(status_code=409, detail=str(refused)) from refused

    @app.get("/conversations")
    def conversation_listing(
        project_id: UUID | None = None,
        scope: str | None = None,
        archived: bool = False,
        removed: bool = False,
    ) -> list[ConversationView]:
        """All conversations, one project's, or the explicitly-no-project ones.

        `archived=true` includes archived rows; the flag is presentation
        scoping and carries no evidentiary meaning (§2.1 amendment, 31 August
        2026). Everything outside these two listings is archive-blind.
        `removed=true` includes conversations removed from active use (ruling,
        12 September 2026), which the default listing leaves out.
        """
        records = conversations.listing(
            engine,
            project_id=project_id,
            explicit_none=scope == "none",
            include_archived=archived,
            include_removed=removed,
        )
        return [ConversationView.of(record) for record in records]

    @app.get("/conversations/{conversation_id}")
    def conversation_detail(conversation_id: UUID) -> ConversationDetail:
        try:
            record = conversations.load(engine, conversation_id)
        except ConversationNotFoundError as missing:
            raise HTTPException(status_code=404, detail=str(missing)) from missing
        blinds = blind_positions_for(engine, conversation_id)
        recorded = deliberations_for(engine, conversation_id)
        # Ruling, 12 September 2026: a message anchoring an enforced blind
        # position or any deliberation cannot be rewritten. The writer refuses
        # regardless; this lets the interface say so before being asked.
        deliberated = {b.message_id for b in blinds if b.ordering is Ordering.ENFORCED} | {
            d.message_id for d in recorded
        }
        return ConversationDetail(
            conversation=ConversationView.of(record),
            scope_transitions=[
                ScopeTransitionView.of(transition)
                for transition in conversations.scope_transitions(engine, conversation_id)
            ],
            messages=[
                MessageView.of_working(
                    message,
                    deliberated=message.record.id in deliberated,
                    # Owner ruling, 19 September 2026: what was attached to this
                    # message, so the thread can render it. Bytes are fetched
                    # separately, by digest.
                    attachments=acts_for_message(engine, message.record.id),
                )
                for message in conversations.working(engine, conversation_id).messages
            ],
            classifications=[
                ClassificationView.of(row) for row in classifications_for(engine, conversation_id)
            ],
            blind_positions=[BlindPositionView.of(row) for row in blinds],
            deliberations=[DeliberationView.of(row) for row in recorded],
            execution_events=[
                ExecutionEventView.of(row) for row in events_for(engine, conversation_id)
            ],
        )

    # --- conversation management (ruling, 12 September 2026) -------------------

    @app.post("/conversations/{conversation_id}/title")
    def rename_conversation(conversation_id: UUID, request: RenameRequest) -> ConversationView:
        """Rename: the mutable title, presentation-class. No evidence identity changes."""
        try:
            return ConversationView.of(conversations.rename(engine, conversation_id, request.title))
        except ConversationNotFoundError as missing:
            raise HTTPException(status_code=404, detail=str(missing)) from missing
        except TitleRefusedError as refused:
            raise HTTPException(status_code=422, detail=str(refused)) from refused

    @app.post("/conversations/{conversation_id}/archive")
    def archive_conversation(conversation_id: UUID) -> ConversationView:
        """Archive: hidden from the default listing, and nothing else."""
        try:
            return ConversationView.of(
                conversations.set_archived(engine, conversation_id, archived=True)
            )
        except ConversationNotFoundError as missing:
            raise HTTPException(status_code=404, detail=str(missing)) from missing

    @app.post("/conversations/{conversation_id}/unarchive")
    def unarchive_conversation(conversation_id: UUID) -> ConversationView:
        """Unarchive: back in the default listing."""
        try:
            return ConversationView.of(
                conversations.set_archived(engine, conversation_id, archived=False)
            )
        except ConversationNotFoundError as missing:
            raise HTTPException(status_code=404, detail=str(missing)) from missing

    @app.post("/conversations/{conversation_id}/scope")
    def move_conversation(conversation_id: UUID, request: MoveRequest) -> ConversationView:
        """Move: an appended scope transition. The origin is never rewritten.

        Earlier messages and calls keep the scope they occurred in; the next
        turn, and everything recorded about it, belongs to the destination.
        """
        if (request.project_id is None) == (not request.no_project):
            raise HTTPException(
                status_code=422,
                detail="name exactly one destination: a project_id, or no_project: true",
            )
        try:
            return ConversationView.of(
                conversations.move(
                    engine, conversation_id, to_project_id=request.project_id, note=request.note
                )
            )
        except ConversationNotFoundError as missing:
            raise HTTPException(status_code=404, detail=str(missing)) from missing
        except ScopeTransitionRefusedError as refused:
            status = 404 if refused.reason == "unknown_project" else 409
            raise HTTPException(
                status_code=status, detail={"reason": refused.reason, "message": str(refused)}
            ) from refused

    @app.post("/conversations/{conversation_id}/remove")
    def remove_conversation(conversation_id: UUID, request: RemovalRequest) -> ConversationView:
        """Remove: out of active use — no recall, no new turns — and nothing destroyed."""
        try:
            return ConversationView.of(
                conversations.remove(engine, conversation_id, note=request.note)
            )
        except ConversationNotFoundError as missing:
            raise HTTPException(status_code=404, detail=str(missing)) from missing
        except RemovalRefusedError as refused:
            raise HTTPException(
                status_code=409, detail={"reason": refused.reason, "message": str(refused)}
            ) from refused

    @app.post("/conversations/{conversation_id}/reinstate")
    def reinstate_conversation(conversation_id: UUID, request: RemovalRequest) -> ConversationView:
        """Reinstate: back in active use, by another appended fact."""
        try:
            return ConversationView.of(
                conversations.reinstate(engine, conversation_id, note=request.note)
            )
        except ConversationNotFoundError as missing:
            raise HTTPException(status_code=404, detail=str(missing)) from missing
        except RemovalRefusedError as refused:
            raise HTTPException(
                status_code=409, detail={"reason": refused.reason, "message": str(refused)}
            ) from refused

    @app.post("/messages/{message_id}/revisions", status_code=201)
    def revise_message(message_id: UUID, request: RevisionRequest) -> RevisionView:
        """Correct one of Lord Armand's messages: an appended fact, never an edit.

        No provider call and no regeneration. Later turns see the corrected
        wording in the message's position; every earlier call keeps what it
        received.
        """
        try:
            return RevisionView.of(revise(engine, message_id, request.content, note=request.note))
        except RevisionRefusedError as refused:
            raise _revision_http_error(refused) from refused

    @app.post("/messages/{message_id}/retraction", status_code=201)
    def retract_message(message_id: UUID, request: RetractionRequest) -> RevisionView:
        """Remove one of Lord Armand's messages, and Val's reply, from the conversation.

        Both stay in the record, marked withdrawn, with every classification,
        deliberation, judgment and cost attached to them.
        """
        try:
            return RevisionView.of(retract(engine, message_id, note=request.note))
        except RevisionRefusedError as refused:
            raise _revision_http_error(refused) from refused

    # --- the turn -------------------------------------------------------------

    def _candidates(request: TurnRequest) -> tuple[CandidateAttachment, ...]:
        """The turn's offered images, decoded. Nothing else is trusted about them.

        Base64 that is not base64 is refused here, before admission, with the
        same honesty admission itself uses: the send does not happen.
        """
        candidates = []
        for offered in request.attachments:
            try:
                content = b64decode(offered.content_base64, validate=True)
            except (BinasciiError, ValueError) as broken:
                raise HTTPException(
                    status_code=422,
                    detail=f"{offered.filename!r}: the attachment is not valid base64",
                ) from broken
            candidates.append(
                CandidateAttachment(
                    content=content,
                    given_filename=offered.filename,
                    stated_classification=Classification(offered.classification),
                )
            )
        return tuple(candidates)

    # --- Val's voice: the production seam (owner execution order, 22 Sep 2026) ---
    #
    # The smallest real path from a finished Val response to a waveform. It is
    # deliberately not a "text to speech" endpoint: the caller names a message,
    # and the words come from the record, so what is spoken is provably what Val
    # said. There is no avatar and no voice-mode UX here — those are later
    # layers, and this is the seam they will stand on.

    @app.post("/messages/{message_id}/speech")
    def speak(message_id: UUID) -> SpeechView:
        """Speak a persisted Val message in Val's governed local voice."""
        if gateway.speech is None or gateway.voice is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Val has no local voice available. Nothing was sent to a cloud voice "
                    "service: the local route fails closed rather than falling back."
                ),
            )
        configuration = speech_configuration()
        if configuration is None:
            raise HTTPException(
                status_code=503, detail="no admitted local speech route is registered"
            )
        voice_id = register_voice(engine, gateway.voice, voice_record())
        try:
            spoken = speak_message(
                engine,
                gateway.speech,
                configuration,
                gateway.voice,
                voice_id,
                message_id,
            )
        except SpeechRefusedError as refused:
            raise HTTPException(status_code=400, detail=str(refused)) from refused
        except SpeechUnavailableError as unavailable:
            raise HTTPException(status_code=503, detail=str(unavailable)) from unavailable
        return SpeechView.of(spoken)

    @app.get("/speech/{audio_sha256}/bytes")
    def speech_bytes(audio_sha256: str) -> Response:
        """The generated waveform, by its own digest, for the interface to play.

        Content-addressed, like the attachment bytes beside it: the key is the
        digest, so nothing is guessable and nothing is enumerable, and the
        service listens on the loopback interface only.
        """
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "select audio_path from speech_generations where audio_sha256 = :s "
                    "order by created_at desc limit 1"
                ),
                {"s": audio_sha256},
            ).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="no such speech")
        audio = Path(row.audio_path)
        if not audio.is_file():
            raise HTTPException(status_code=410, detail="the staged audio is no longer present")
        return Response(
            content=audio.read_bytes(),
            media_type="audio/wav",
            headers={"Cache-Control": "private, max-age=31536000, immutable"},
        )

    @app.get("/attachments/{sha256}/bytes")
    def attachment_bytes(sha256: str) -> Response:
        """The admitted or derived bytes, by their own digest, for display.

        Content-addressed: the key IS the digest, so nothing is guessable and
        nothing is enumerable. The service listens on the loopback interface
        only, and this endpoint is for the house's own interface to render what
        it already holds — never for making an image addressable to a provider,
        which receives the bytes inline and never a URL.
        """
        found = blob_bytes(engine, sha256)
        if found is None:
            raise HTTPException(status_code=404, detail="no such attachment")
        content, media_type = found
        return Response(
            content=content,
            media_type=media_type,
            headers={"Cache-Control": "private, max-age=31536000, immutable"},
        )

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
                attachments=_candidates(request),
                # Owner ruling, 24 September 2026 (§2.1's transient layer). A
                # **typed** turn in a conversation whose Voice session is open is
                # local-only too, from the moment Voice was turned on. `spoken`
                # stays false: this is not microphone-derived text, so it does not
                # durably seal anything by itself.
                live_voice=sessions.live_conversations(),
            )
        except AdmissionRefusedError as refused:
            # Ruling, 19 September 2026: a file that could not be admitted
            # refused the whole send, and nothing was written. 422: the request
            # was understood and its content could not be accepted.
            raise HTTPException(status_code=422, detail=str(refused)) from refused
        except RestrictedContentRefusedError as refusal:
            # A refusal to transmit is not a transport error and must never be
            # quiet (WP-0.7 §15). 403: the request was understood and refused.
            raise HTTPException(status_code=403, detail=str(refusal)) from refusal
        except ConversationRemovedError as removed:
            # Ruling, 12 September 2026: refused before anything is written.
            raise HTTPException(status_code=409, detail=str(removed)) from removed

        return render_turn(outcome)

    def render_turn(outcome: DeliberatedOutcome) -> TurnResponse:
        """The plain route's response from a deliberated outcome — shared with the
        streamed route, so the settled event is exactly what `POST /turns` returns."""
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
            failure = outcome.error
            return TurnUnanswered(
                conversation=ConversationView.of(outcome.conversation),
                user_message=MessageView.of(outcome.user_message),
                error=str(failure),
                error_kind=(failure.kind.value if isinstance(failure, GatewayError) else "unknown"),
                # From the record, not the message: a contacted provider leaves
                # a model_calls row for this turn; a pre-contact refusal leaves
                # none (ruled 2 September 2026).
                provider_contacted=response_call_recorded(engine, outcome.user_message.id),
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

    @app.post("/turns/stream")
    def turn_stream(request: TurnRequest) -> StreamingResponse:
        """The same turn as `POST /turns`, with Val's text delivered as it is produced.

        Responsiveness phase, 11 September 2026. Server-sent events: `delta`
        frames carry generated text forwarded through Val Core; the final
        `settled` frame carries the identical object the plain route returns,
        plus timing measured at the gateway and here. A Restricted refusal and
        any other failure arrive as events, since the status line has already
        been sent (`val_api.streaming`).
        """
        return StreamingResponse(
            turn_event_stream(
                engine,
                gateway,
                request,
                render_turn,
                _candidates(request),
                # The seal's transient layer reaches the streaming door too.
                live_voice=sessions.live_conversations(),
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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

    # --- classification review: the fifty, blind before reveal -----------------

    @app.get("/classification-review/queue")
    def classification_queue(limit: int = 20) -> list[QueuedExchangeView]:
        """Eligible exchanges awaiting a label, oldest first. **No verdict.**"""
        return [QueuedExchangeView.of(item) for item in review_queue(engine, limit=limit)]

    @app.post("/classification-review/labels", status_code=201)
    def label_exchange(request: LabelRequest) -> LabelledExchangeView:
        """Store the original blind label; the reply is the first reveal."""
        try:
            return LabelledExchangeView.of(
                record_label(
                    engine,
                    classification_id=request.classification_id,
                    label=request.label,
                    exclusion_determination=request.exclusion_determination,
                )
            )
        except ReviewRefusedError as refused:
            raise HTTPException(status_code=409, detail=str(refused)) from refused

    @app.get("/classification-review/labelled/{classification_id}")
    def labelled_exchange(classification_id: UUID) -> LabelledExchangeView:
        item = labelled(engine, classification_id)
        if item is None:
            raise HTTPException(status_code=404, detail="no label exists for this exchange")
        return LabelledExchangeView.of(item)

    @app.get("/classification-review/disagreements")
    def classification_disagreements() -> list[LabelledExchangeView]:
        return [LabelledExchangeView.of(item) for item in disagreements(engine)]

    @app.get("/classification-review/progress")
    def classification_progress() -> ReviewProgressView:
        return ReviewProgressView.of(progress(engine))

    @app.post("/classification-review/reviews", status_code=201)
    def review_exchange(request: ReviewRequest) -> ClassificationReviewView:
        """Append an adjudication. Viewing a disagreement records nothing."""
        try:
            return ClassificationReviewView.of(
                record_review(
                    engine,
                    classification_id=request.classification_id,
                    conclusion=request.conclusion,
                    reason=request.reason,
                    tuning_state=request.tuning_state,
                    tuning_change=request.tuning_change,
                    tuning_verification=request.tuning_verification,
                )
            )
        except ReviewRefusedError as refused:
            raise HTTPException(status_code=409, detail=str(refused)) from refused

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

    # --- live voice input ------------------------------------------------------
    #
    # The smallest contract the later desktop package needs: open a session, feed
    # PCM, poll the guess and the state, finalize an utterance, observe the
    # canonical result, stop. It rides the existing transport — ordinary POST and
    # GET on the same loopback-only service, under the same CORS grant and the
    # same two shell origins — because the existing stack carries these events
    # perfectly well and a second realtime framework would be a second thing to
    # secure. **Nothing here is weaker than the rest of the service**: no new
    # origin, no new bind, no new header, no upgrade, no token.
    #
    # Audio arrives as `application/octet-stream` and goes straight to the
    # recognizer. It is not stored, not buffered here, and not written anywhere.

    def speech_delivery_factory() -> Callable[[], SpeechDelivery] | None:
        """How a voice session obtains speech, or `None` when the house has none.

        The admitted speech route is selected by the profile it declares, never by
        name, exactly as every other capability floor is. A missing runtime or a
        missing governed voice means a session that hears and does not speak —
        stated, and never a reason to call a cloud voice service.
        """
        configuration = speech_configuration()
        if configuration is None or gateway.speech is None or gateway.voice is None:
            return None
        provider, voice = gateway.speech, gateway.voice

        def build() -> SpeechDelivery:
            # Owner execution order, 24 September 2026 (§11). The sink is the one
            # that can hand audio to the desktop that owns the Mac's speakers.
            # Everything work package 2 proved about delivery truth holds
            # unchanged — `DesktopSink` extends the ephemeral sink rather than
            # replacing it — and what is added is the hand-off and the separate
            # record of what the speakers then did.
            return SpeechDelivery(
                engine,
                speech=provider,
                voice=voice,
                configuration=configuration,
                sink=DesktopSink(),
            )

        return build

    def voice_session_or_404(session: UUID) -> VoiceSession:
        live = sessions.get(session)
        if live is None:
            raise HTTPException(status_code=404, detail="no such voice session")
        return live

    def render_delivery(message_id: UUID) -> DeliveryView | None:
        found = delivery_for(engine, message_id)
        if found is None:
            return None
        return DeliveryView(
            message_id=found.message_id,
            state=found.state.value,
            delivered_prefix=found.delivered_prefix,
            delivered_characters=found.delivered_characters,
            segments_delivered=found.segments_delivered,
            segments_total=found.segments_total,
            reason=found.reason,
            events=found.events,
        )

    def render_voice(session: UUID, live: VoiceSession) -> VoiceSessionView:
        view = live.snapshot()
        speaking = live.delivery
        return VoiceSessionView(
            session=session,
            voice_session_id=None if view.session_id == NO_SESSION else view.session_id,
            conversation_id=view.conversation_id,
            state=view.state.value,
            utterance=view.utterance,
            provisional=view.provisional,
            hearing=view.hearing,
            pending=view.pending,
            progress=view.progress,
            queued=view.queued,
            turns=[
                VoiceTurnView(
                    message_id=turn.message_id,
                    conversation_id=turn.conversation_id,
                    text=turn.utterance.text,
                    utterance=turn.utterance.utterance,
                    endpoint_reason=turn.utterance.reason,
                    provisional_events=turn.provisional_events,
                    merged_from=list(turn.utterance.merged_from),
                    revised_to=turn.revised_to,
                    merge_refused=turn.merge_refused,
                    delivered=turn.delivered,
                    # Keyed on **Val's** answer: delivery is about her words.
                    delivery=(
                        None
                        if turn.answer_message_id is None
                        else render_delivery(turn.answer_message_id)
                    ),
                    answer=render_turn(turn.outcome),
                )
                for turn in view.turns
            ],
            error=view.error,
            recognizer=view.recognizer,
            endpoint={key: float(value) for key, value in view.endpoint.items()},
            delivery=(
                None
                if speaking is None
                else LiveDeliveryView(
                    state=speaking.state.value,
                    audible=speaking.audible,
                    active=speaking.active,
                    segments_delivered=speaking.segments_delivered,
                    delivered_characters=len(speaking.delivered_prefix),
                    cancellation_ms=speaking.cancellation_ms,
                )
            ),
            cancellations_ms=list(live.cancellations),
            committed=(
                None
                if view.committed is None
                else VoiceCommittedView(
                    conversation_id=view.committed.conversation_id,
                    message_id=view.committed.message_id,
                    utterance=view.committed.utterance,
                )
            ),
            answered=(
                None
                if view.answered is None
                else VoiceCommittedView(
                    conversation_id=view.answered.conversation_id,
                    message_id=view.answered.message_id,
                    utterance=view.answered.utterance,
                )
            ),
            speech_end=(
                None
                if view.speech_end is None
                else SpeechEndView(
                    utterance=view.speech_end[0],
                    ms_ago=round((time.monotonic() - view.speech_end[1]) * 1000, 1),
                )
            ),
        )

    def timed_warm(run: Callable[[], Mapping[str, object]]) -> dict[str, object]:
        """One warm-up, with when it began and how long it took, for the log."""
        began = datetime.now(UTC)
        clock = time.monotonic()
        report = dict(run())
        report["began"] = began.isoformat(timespec="milliseconds")
        report["seconds"] = round(time.monotonic() - clock, 3)
        return report

    @app.post("/voice/sessions", status_code=201)
    def open_voice_session(request: VoiceSessionRequest) -> VoiceSessionView:
        """Start listening. One recognizer, one conversation, one session."""
        if recognizers is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "live voice input is not available in this service. No cloud speech "
                    "recognition was called and none is configured."
                ),
            )
        signals = ProjectSignals(
            explicit_selection=request.project, explicit_no_project=request.no_project
        )

        def submit(
            content: str,
            conversation_id: UUID | None,
            *,
            on_delta: Callable[[str], None] | None = None,
            merged: bool = False,
            on_persisted: Callable[[UUID, UUID], None] | None = None,
            prepared: object | None = None,
        ) -> DeliberatedOutcome:
            """The ordinary door. A spoken turn is an ordinary turn.

            The session's project signals are a statement made when it was
            opened, and they are offered **only** while there is no conversation
            yet. Once there is one, its own stored scope is the authority
            (WP-0.7 §18) — and restating a project on a resumed conversation is
            read, correctly, as switching, which starts a new conversation. A
            voice session that restated its signals every utterance would
            therefore scatter one spoken conversation across many.
            """
            return deliberated_send(
                engine,
                gateway,
                content,
                catalogue=load_catalogue(engine),
                signals=None if conversation_id is not None else signals,
                conversation_id=conversation_id,
                # Core's visible output as it is produced, so Val can begin
                # speaking the first sentence while she writes the second. The
                # turn is otherwise identical to a typed one.
                on_delta=on_delta,
                # Owner ruling, 24 September 2026 (Voice work package 3 §1.5,
                # §2.1). **This door is the microphone's door.** `spoken` is not
                # inferred from anything: it is true because of where this closure
                # lives, which is why a typed turn cannot reach it and a spoken
                # turn cannot avoid it. The conversation's local-only seal is
                # written in the same transaction as the message it creates.
                spoken=True,
                seal_route=(SealRoute.RESUME_MERGE if merged else SealRoute.UTTERANCE_FINALIZED),
                live_voice=sessions.live_conversations(),
                # His words are canonical: the session is told at once, so the next
                # poll shows the desktop a message to read while she is thinking.
                on_persisted=on_persisted,
                # The candidate's light tiers, if this process enables any.
                fast_route=fast_route,
                # A light answer prepared during the resume window, for Core to bind or
                # discard (owner order §6).
                prepared=prepared if isinstance(prepared, PreparedAnswer) else None,
            )

        def prepare(content: str, conversation_id: UUID | None) -> object | None:
            """Speculative preparation (owner order §6), through Core, persisting nothing."""
            if fast_route is None:
                return None
            return prepare_light_answer(
                engine,
                gateway,
                content,
                catalogue=load_catalogue(engine),
                signals=None if conversation_id is not None else signals,
                conversation_id=conversation_id,
                fast_route=fast_route,
                live_voice=sessions.live_conversations(),
            )

        live = VoiceSession(
            engine,
            recognizers(),
            submit=submit,
            conversation_id=request.conversation_id,
            # How this session speaks, when the house has a voice to speak with.
            # `None` is a session that hears and says nothing aloud, which is what
            # a house with no admitted speech route gets — honestly, rather than
            # by reaching for a cloud one.
            speech=speech_delivery_factory(),
            # Optional work, done early and never ahead of him (owner diagnostic, 25
            # September 2026, §8, §9). The cognition runtime's readiness — no
            # inference; any load it does is the one his first turn would do itself —
            # and the resident speech worker, which holds the voice model while Voice
            # is on and is released when the last session ends (Voice-mode repair §5,
            # 25 September 2026). Each is timed on the record.
            warm=lambda: {
                "cognition": timed_warm(gateway.warm_cognition),
                "voice": timed_warm(gateway.warm_voice),
            },
            # The persona prefix, primed at Voice On and refreshed after each turn, so
            # later turns do not recompute it (owner order, 25 September 2026). Never
            # started while a request of his is waiting; recorded as `prefix_prime`.
            prime=gateway.prime_prefix,
            # Candidate behaviours (owner order, 26 September 2026 §6, §7), both off in
            # production: a light answer prepared during the resume window, and a
            # resume window sized from the transcript's own cues.
            prepare=prepare if speculation else None,
            adaptive_grace=adaptive_grace,
        )
        try:
            live.start()
        except VoiceUnavailableError as unavailable:
            raise HTTPException(status_code=503, detail=str(unavailable)) from unavailable
        key = uuid4()
        sessions.add(key, live)
        return render_voice(key, live)

    @app.post("/voice/sessions/{session}/audio")
    async def feed_voice_session(session: UUID, request: Request) -> VoiceSessionView:
        """One block of 16 kHz mono little-endian int16 PCM.

        Handed to the recognizer and to nothing else. Never stored, never a file,
        never a database field.
        """
        live = voice_session_or_404(session)
        pcm = await request.body()
        try:
            # **Off the event loop** (owner diagnostic, 25 September 2026). Handing
            # audio to the recognizer is synchronous work — a pipe write that waits
            # when the helper is busy decoding, and journal writes to the store — and
            # this route is `async`, so it used to do that work on the one loop every
            # request shares. While it did, nothing else returned: not a poll, and
            # not the conversation read that shows him his own words. A test holds
            # one hand-over open and requires a conversation read to return meanwhile.
            # Order is unaffected: the desktop sends one block at a time.
            await run_in_threadpool(live.feed, pcm)
        except VoiceUnavailableError as unavailable:
            raise HTTPException(status_code=409, detail=str(unavailable)) from unavailable
        return render_voice(session, live)

    @app.get("/voice/sessions/{session}")
    def poll_voice_session(session: UUID) -> VoiceSessionView:
        """The guess, the state, and any turns this session has produced."""
        return render_voice(session, voice_session_or_404(session))

    @app.post("/voice/sessions/{session}/timings", status_code=204)
    def report_desktop_timings(session: UUID, report: DesktopTimingReport) -> Response:
        """The desktop's owner-facing intervals for one turn, kept in the log."""
        voice_session_or_404(session)
        _LOGGER.info("voice desktop timing: %s", report.model_dump_json())
        return Response(status_code=204)

    @app.post("/voice/sessions/{session}/finalize")
    def finalize_voice_session(session: UUID) -> VoiceSessionView:
        """End the utterance in progress now, rather than waiting for silence."""
        live = voice_session_or_404(session)
        try:
            live.finalize()
        except VoiceUnavailableError as unavailable:
            raise HTTPException(status_code=409, detail=str(unavailable)) from unavailable
        return render_voice(session, live)

    @app.post("/voice/sessions/{session}/delivered/{message_id}")
    def voice_turn_delivered(session: UUID, message_id: UUID) -> VoiceSessionView:
        """The caller has given the owner this answer.

        After it, resumed speech is a new turn rather than a continuation. In this
        package nothing speaks aloud, so nothing calls this yet; the delivering
        layer does, in work package 2.
        """
        live = voice_session_or_404(session)
        live.deliver(message_id)
        return render_voice(session, live)

    @app.post("/voice/sessions/{session}/interrupt")
    def interrupt_voice_delivery(session: UUID) -> VoiceSessionView:
        """Stop Val speaking now — barge-in, from a caller that heard him start.

        The recognizer already does this by itself when it reports the owner
        speaking while delivery is live; this is the same act available to the
        capture layer that will hear him first (work package 3). Nothing already
        executed is undone, and the exact delivered prefix goes on the record.
        """
        live = voice_session_or_404(session)
        live.interrupt_delivery("the caller signalled barge-in")
        return render_voice(session, live)

    @app.get("/messages/{message_id}/delivery")
    def message_delivery(message_id: UUID) -> DeliveryView:
        """What speech delivery did for this answer, from the append-only record."""
        found = render_delivery(message_id)
        if found is None:
            raise HTTPException(
                status_code=404, detail="this message has no speech delivery on record"
            )
        return found

    def _playback_view(event: PlaybackEvent) -> PlaybackEventView:
        return PlaybackEventView(
            segment_index=event.segment_index,
            event=event.event,
            state=event.state.value,
            text=event.text,
            elapsed_ms=event.elapsed_ms,
            reason=event.reason,
        )

    @app.get("/voice/sessions/{session}/speech/next")
    def collect_speech(session: UUID) -> SpeechOfferView:
        """What the desktop should do about speech right now.

        Owner execution order, 24 September 2026 (§11, §12). **One poll, two
        questions**: is a synthesised segment waiting to be played, and should what
        is already playing stop? A desktop that asked only the first would keep a
        buffer sounding for a poll interval after Val had been interrupted, which is
        precisely the failure barge-in must not have.

        A segment handed over here **leaves the service**: the bytes are released
        the moment this response is written, and there is no route to fetch them
        again. That is what keeps live speech ephemeral rather than uncollected.
        """
        live = voice_session_or_404(session)
        settle_handoffs(session, live)
        # The delivery in flight, or the one that has just finished: the last
        # segment of an answer must stay collectable for a moment after the turn
        # ends, or her final words are synthesised and dropped (§11).
        speaking = live.speech_handover
        if speaking is None:
            return SpeechOfferView(delivery_state="none", stop=False)
        state = speaking.state.value
        speaks = speaking.message_id
        sink = getattr(speaking, "sink", None)
        # Stop when delivery ended other than by completing. `active` is False for a
        # completed answer too, which is why the state decides rather than the flag.
        stopped_because = getattr(sink, "stopped_because", None)
        should_stop = state in ("interrupted", "failed") or (
            stopped_because is not None and state != "completed"
        )
        reason = None
        if should_stop:
            reason = getattr(speaking, "reason", None) or stopped_because or "delivery ended"
        if not isinstance(sink, DesktopSink):
            return SpeechOfferView(
                delivery_state=state, stop=should_stop, reason=reason, message_id=speaks
            )
        offer = sink.collect()
        if offer is None:
            return SpeechOfferView(
                delivery_state=state, stop=should_stop, reason=reason, message_id=speaks
            )
        message_id = speaking.message_id
        if offer.chunk > 0:
            # A later piece of a segment already handed over: one hand-off per segment.
            pass
        elif message_id is None:
            # Voiced before her answer was written: recorded once it is.
            unbound_handoffs.setdefault(session, []).append(
                (speaking, offer.segment_index, offer.text, datetime.now(UTC))
            )
        else:
            # The service's own half of the record: this segment became available
            # to the desktop. It is **not** a claim that anything was heard.
            record_playback(
                engine,
                message_id=message_id,
                segment_index=offer.segment_index,
                state=PlaybackState.AVAILABLE_TO_DESKTOP,
                spoken_text=offer.text,
                voice_session_id=live.session_id,
            )
        return SpeechOfferView(
            delivery_state=state,
            stop=should_stop,
            reason=reason,
            message_id=speaks,
            segment=SpokenAudioView(
                message_id=message_id if message_id is not None else UUID(int=0),
                segment_index=offer.segment_index,
                text=offer.text,
                audio_format=offer.audio_format,
                sample_rate=offer.sample_rate,
                duration_seconds=offer.duration_seconds,
                audio_bytes=len(offer.audio),
                audio_base64=b64encode(offer.audio).decode("ascii"),
                chunk=offer.chunk,
                last=offer.last,
            ),
        )

    @app.post("/voice/sessions/{session}/speech/played")
    def report_playback(session: UUID, report: PlaybackReport) -> list[PlaybackEventView]:
        """What the Mac's speakers actually did with one segment.

        The physical boundary §11.1 requires, and the only place it can come from:
        the service cannot observe an output device, so it records what the desktop
        reports and never guesses. `available_to_desktop` is refused here — that one
        is the service's own fact about its own hand-off, and a desktop claiming it
        would be reporting someone else's act.
        """
        live = voice_session_or_404(session)
        settle_handoffs(session, live)
        try:
            state = PlaybackState(report.state)
        except ValueError as unknown:
            raise HTTPException(
                status_code=422, detail=f"unknown playback state {report.state!r}"
            ) from unknown
        if state is PlaybackState.AVAILABLE_TO_DESKTOP:
            raise HTTPException(
                status_code=422,
                detail=(
                    "available_to_desktop is the service's own record of handing the segment "
                    "over; a desktop reports what its output device did, not what the service did"
                ),
            )
        offered = [
            event
            for event in playback_of(engine, report.message_id)
            if event.segment_index == report.segment_index
        ]
        if not offered:
            raise HTTPException(
                status_code=409,
                detail=(
                    "this segment was never handed to a desktop, so nothing can be reported "
                    "about playing it"
                ),
            )
        record_playback(
            engine,
            message_id=report.message_id,
            segment_index=report.segment_index,
            state=state,
            # The text this segment actually spoke, taken from the record of the
            # hand-off rather than from the report: the desktop reports what its
            # device did, and the house says what the words were.
            spoken_text=offered[0].text,
            voice_session_id=live.session_id,
            elapsed_ms=report.elapsed_ms,
            reason=report.reason,
            observed_at=None
            if report.observed_ms_ago is None
            else datetime.now(UTC) - timedelta(milliseconds=report.observed_ms_ago),
        )
        return [_playback_view(event) for event in playback_of(engine, report.message_id)]

    @app.get("/messages/{message_id}/playback")
    def message_playback(message_id: UUID) -> list[PlaybackEventView]:
        """Every physical-playback transition for one answer, from the record."""
        return [_playback_view(event) for event in playback_of(engine, message_id)]

    @app.post("/voice/adopt")
    def adopt_recovered_fragment(request: AdoptedFragmentRequest) -> TurnResponse:
        """Adopt a guess a restart found open, as the owner's own words.

        Owner execution order, 24 September 2026 (§2.1). The third route to
        canonical, and it seals exactly as the other two do: the words are
        live-microphone-derived, so the conversation becomes local-only in the same
        transaction as the message they become. Nothing here promotes a fragment by
        itself — the owner's call to this route *is* the adoption.
        """
        try:
            outcome = deliberated_send(
                engine,
                gateway,
                request.content,
                catalogue=load_catalogue(engine),
                conversation_id=request.conversation_id,
                spoken=True,
                seal_route=SealRoute.RECOVERED_FRAGMENT_ADOPTED,
                live_voice=sessions.live_conversations(),
            )
        except RestrictedContentRefusedError as refusal:
            raise HTTPException(status_code=403, detail=str(refusal)) from refusal
        except ConversationRemovedError as removed:
            raise HTTPException(status_code=409, detail=str(removed)) from removed
        return render_turn(outcome)

    @app.post("/voice/sessions/{session}/close")
    def close_voice_session(session: UUID) -> VoiceSessionView:
        """Stop listening and release the recognizer."""
        live = voice_session_or_404(session)
        live.close()
        sessions.remove(session)
        return render_voice(session, live)

    @app.get("/voice/interrupted")
    def interrupted_utterances() -> list[InterruptedUtteranceView]:
        """Guesses an interrupted session left open, labelled as interrupted.

        Read once after a restart. Each is the words the recognizer had reached,
        offered back as a guess — **never** silently promoted into something the
        owner said.
        """
        return [
            InterruptedUtteranceView(
                voice_session_id=open_guess.voice_session_id,
                conversation_id=open_guess.conversation_id,
                utterance=open_guess.utterance,
                provisional_text=open_guess.provisional_text,
            )
            for open_guess in interrupted(engine)
        ]

    return app
