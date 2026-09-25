# ruff: noqa: F811, F401 - fixtures and harness imported by name
"""The live-voice seal, end to end — owner ruling, 24 September 2026.

Voice work package 3 §1.5, §2.1, §2.6, §2.7 and §19. One sentence is under test
here, and everything else is a way of trying to break it:

    **A live microphone transcript never leaves this Mac.**

Not on the turn it was spoken. Not on a later typed turn in the same conversation.
Not by being recalled into a different conversation. Not through the classifier, the
strip route, the blind position, a tool or a title call.

The device throughout is a **canary phrase** and a **cloud transport spy**. The spy
stands where every cloud provider stands and records the complete request it was
handed; nothing is ever sent to a real provider to prove a negative. If the phrase
reaches the spy, the seal failed — and the assertion is over the *whole* request
body, not over the field a test author happened to think of.

The local route answers normally throughout, because a sealed conversation must
still work. A privacy rule that silenced Val would be a different failure, not a
success.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from uuid import UUID

import pytest
from gateway_fakes import FakeLedger
from sqlalchemy import Engine, text
from test_deliberation_machinery import (
    classifier_says,
    clean_personas,
    ok,
    store,
    verifier,
)
from test_voice_input import (
    MARKER,
    Clock,
    ScriptedRecognizer,
    a_conversation,
    final,
    settle,
    started,
)

from val_domain.egress import Egress
from val_domain.gateway import (
    CacheTtl,
    GatewayError,
    GatewayErrorKind,
    Hosting,
    Message,
    ModelConfig,
)
from val_domain.provider import ContextFeasibility
from val_domain.registry import active
from val_gateway.deliberate import DeliberatedOutcome
from val_gateway.deliberate import send as deliberated_send
from val_gateway.gateway import Gateway
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader
from val_gateway.projects import load_catalogue
from val_gateway.seal import SealRoute
from val_gateway.voice import VoiceSession, VoiceSessions
from val_policy.egress import (
    LiveVoiceConversations,
    decide_egress,
    is_conversation_sealed,
)
from val_policy.project_resolution import ProjectSignals
from val_providers.base import ProviderResult

#: Said aloud once, and then hunted for everywhere. Distinctive enough that a
#: substring search over a whole serialized request cannot match it by accident.
CANARY = "the Wollaton codicil is in the second drawer"


# --- the two worlds ------------------------------------------------------------------


@dataclass
class LocalAdapter:
    """The machine's own route. Answers, and records what it was asked."""

    script: list[ProviderResult | Exception]
    sent: list[tuple[str, str]] = field(default_factory=list)
    #: `ContextInspectingAdapter` declares itself by `measure_context` **and** a
    #: name, and the exact preflight is what keeps the byte bound from striking
    #: the local route out of an ordinary turn (21 September 2026).
    name: str = "local-test"

    def measure_context(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int | None = None,
    ) -> ContextFeasibility:
        return ContextFeasibility(
            prompt_tokens=1_024, context_tokens=32_768, source="local-test", details={}
        )

    def complete(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> ProviderResult:
        self.sent.append((config.slug, _body(messages, system)))
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


@dataclass
class CloudSpy:
    """Stands where every cloud provider stands. Records, and never answers.

    Refusing rather than answering is deliberate: a spy that answered would let a
    leak pass as a working turn, and the test would have to notice the leak to
    fail. This way a leak fails the turn *and* leaves the evidence.
    """

    seen: list[tuple[str, str]] = field(default_factory=list)
    script: list[ProviderResult | Exception] = field(default_factory=list)
    name: str = "cloud-spy"

    def complete(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> ProviderResult:
        self.seen.append((config.slug, _body(messages, system)))
        if self.script:
            step = self.script.pop(0)
            if isinstance(step, Exception):
                raise step
            return step
        raise GatewayError(
            GatewayErrorKind.PROVIDER_ERROR,
            "the cloud transport spy never answers; it only records what it was handed",
        )

    def carries(self, phrase: str) -> bool:
        return any(phrase in body for _, body in self.seen)


def _body(messages: tuple[Message, ...], system: str | None) -> str:
    """Everything a provider would receive, flattened for searching."""
    pieces: list[str] = [system or ""]
    for message in messages:
        pieces.append(message.role)
        for part in message.parts:
            pieces.append(repr(part))
        pieces.append(getattr(message, "content", "") or "")
    return "\n".join(pieces)


def two_worlds(engine: Engine, local: LocalAdapter, cloud: CloudSpy) -> Gateway:
    """A gateway whose local route works and whose every cloud route is watched."""
    cloud_providers = {config.provider for config in active() if config.hosting is Hosting.CLOUD}
    local_providers = {config.provider for config in active() if config.hosting is Hosting.LOCAL}
    assert cloud_providers, "this test is about the cloud providers the registry has"
    adapters: dict[str, object] = {provider: cloud for provider in cloud_providers}
    for provider in local_providers:
        adapters[provider] = local
    return Gateway(
        adapters=adapters,  # type: ignore[arg-type]
        recorder=lambda record: record_call(engine, record),
        ledger=FakeLedger(),
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(engine),
        verify_provenance=verifier(engine),
    )


def spoken_session(
    engine: Engine,
    gateway: Gateway,
    words: str,
    *,
    conversation_id: UUID | None = None,
    sessions: VoiceSessions | None = None,
) -> tuple[VoiceSession, object]:
    """A voice session wired exactly as the service wires it."""
    live = sessions if sessions is not None else VoiceSessions()

    def submit(
        content: str,
        existing: UUID | None,
        *,
        on_delta: Callable[[str], None] | None = None,
        merged: bool = False,
        on_persisted: Callable[[UUID, UUID], None] | None = None,
    ) -> DeliberatedOutcome:
        return deliberated_send(
            engine,
            gateway,
            content,
            catalogue=load_catalogue(engine),
            signals=None
            if existing is not None
            else ProjectSignals(explicit_selection="Project Alpha"),
            conversation_id=existing,
            on_delta=on_delta,
            on_persisted=on_persisted,
            spoken=True,
            seal_route=SealRoute.RESUME_MERGE if merged else SealRoute.UTTERANCE_FINALIZED,
            live_voice=live.live_conversations(),
        )

    clock = Clock()
    session = VoiceSession(
        engine,
        ScriptedRecognizer(batches=[[started(1), final(1, words)]]),
        submit=submit,
        conversation_id=conversation_id if conversation_id is not None else a_conversation(engine),
        clock=clock,
    )
    session.start()
    live.add(UUID(int=1), session)
    session.feed(MARKER)
    settle(session, clock)
    return session, clock


# --- the turn itself ----------------------------------------------------------------


def test_a_spoken_turn_reaches_no_cloud_provider_at_all(store: Engine) -> None:
    """§19: zero remote classifier, strip, blind, model and tool calls."""
    local = LocalAdapter([ok("Noted, my lord.")])
    cloud = CloudSpy()
    gateway = two_worlds(store, local, cloud)

    session, _ = spoken_session(store, gateway, CANARY)

    (turn,) = session.snapshot().turns
    assert cloud.seen == [], "a spoken turn contacted a cloud provider"
    assert not cloud.carries(CANARY)
    assert len(local.sent) == 1, "one call, on this machine: the response"
    assert CANARY in local.sent[0][1], "and it did carry his words, locally"

    with store.connect() as connection:
        tasks = [
            row.task_type
            for row in connection.execute(
                text("select task_type from model_calls where conversation_id = :id"),
                {"id": turn.conversation_id},
            )
        ]
    assert tasks == ["conversation"], "no classification, strip, blind or title call was made"


def test_the_spoken_turn_is_recorded_as_not_run_never_as_not_consequential(
    store: Engine,
) -> None:
    """§2.3. The distinction the record exists to keep."""
    gateway = two_worlds(store, LocalAdapter([ok("Very good.")]), CloudSpy())
    session, _ = spoken_session(store, gateway, CANARY)
    (turn,) = session.snapshot().turns

    with store.connect() as connection:
        row = connection.execute(
            text(
                "select established, verdict, attempts, resolution, not_run_reason, "
                "       cardinality(model_call_ids) as calls "
                "  from classifications where message_id = :id"
            ),
            {"id": turn.message_id},
        ).one()
    assert row.not_run_reason is not None
    assert "local-only" in row.not_run_reason and "live-voice seal" in row.not_run_reason
    assert row.verdict is None, "no verdict was invented"
    assert row.verdict != "not_consequential"
    assert (row.established, row.attempts, row.calls) == (False, 0, 0)
    assert row.resolution is None, "a failure resolution would claim attempts that never happened"


def test_val_answers_normally_in_a_sealed_conversation(store: Engine) -> None:
    """A privacy rule that silenced her would be a different failure."""
    gateway = two_worlds(store, LocalAdapter([ok("Eight, my lord.")]), CloudSpy())
    session, _ = spoken_session(store, gateway, "What time is dinner?")
    (turn,) = session.snapshot().turns
    assert turn.answer_message_id is not None
    with store.connect() as connection:
        last = connection.execute(
            text(
                "select content from messages where conversation_id = :id "
                " order by sequence desc limit 1"
            ),
            {"id": turn.conversation_id},
        ).scalar_one()
    assert last == "Eight, my lord."


# --- when the seal takes effect -----------------------------------------------------


def test_the_durable_seal_is_committed_with_the_message_that_causes_it(
    store: Engine,
) -> None:
    """§2.1's atomicity rule, checked from the record it leaves."""
    gateway = two_worlds(store, LocalAdapter([ok("Noted.")]), CloudSpy())
    session, _ = spoken_session(store, gateway, CANARY)
    (turn,) = session.snapshot().turns

    with store.connect() as connection:
        seal = connection.execute(
            text(
                "select conversation_id, message_id, applied_by, reason "
                "  from conversation_egress_seals where conversation_id = :id"
            ),
            {"id": turn.conversation_id},
        ).one()
    assert seal.message_id == turn.message_id, "the seal names the message that caused it"
    assert seal.applied_by == "utterance_finalized"
    assert "does not leave" not in seal.reason  # the wording is the ruling's, checked below
    assert "transmitted off this machine" in seal.reason
    assert is_conversation_sealed(store, turn.conversation_id)


def test_no_state_exists_with_the_spoken_message_present_and_the_seal_absent(
    store: Engine,
) -> None:
    """The atomicity rule, from the other side: every voice message is sealed.

    Asserted over the store rather than over one turn, so a second route to
    canonical that forgot to seal would fail here too.
    """
    gateway = two_worlds(store, LocalAdapter([ok("Noted.")]), CloudSpy())
    spoken_session(store, gateway, CANARY)

    with store.connect() as connection:
        unsealed = connection.execute(
            text(
                "select count(*) from voice_message_provenance p "
                "  join messages m on m.id = p.message_id "
                " where not exists ("
                "   select 1 from conversation_egress_seals s "
                "    where s.conversation_id = m.conversation_id)"
            )
        ).scalar_one()
    assert unsealed == 0, "a canonical voice message exists whose conversation is not sealed"


def test_a_voice_session_that_says_nothing_leaves_the_conversation_unsealed(
    store: Engine,
) -> None:
    """§2.1, §2.7's third negative. Turning Voice on does not durably seal anything."""
    conversation = a_conversation(store)
    sessions = VoiceSessions()

    def submit(*args: object, **kwargs: object) -> DeliberatedOutcome:
        raise AssertionError("nothing was said, so nothing should have been submitted")

    session = VoiceSession(
        store,
        ScriptedRecognizer(batches=[]),
        submit=submit,  # type: ignore[arg-type]
        conversation_id=conversation,
    )
    session.start()
    sessions.add(UUID(int=2), session)

    # While the session is open, the conversation is local-only — the transient layer.
    assert decide_egress(store, conversation, live=sessions.live_conversations()).local_only, (
        "an open Voice session blocks egress before anything is said"
    )

    session.close("the owner turned Voice off")
    sessions.remove(UUID(int=2))

    assert not is_conversation_sealed(store, conversation), "nothing was said; nothing is sealed"
    assert not decide_egress(store, conversation, live=sessions.live_conversations()).local_only, (
        "and its ordinary egress rules resume"
    )


def test_a_typed_turn_is_local_only_while_voice_is_on_in_that_conversation(
    store: Engine,
) -> None:
    """§2.1's transient layer reaches a typed turn too."""
    conversation = a_conversation(store)
    sessions = VoiceSessions()
    session = VoiceSession(
        store,
        ScriptedRecognizer(batches=[]),
        submit=lambda *a, **k: None,  # type: ignore[arg-type,misc]
        conversation_id=conversation,
    )
    session.start()
    sessions.add(UUID(int=3), session)

    local = LocalAdapter([ok("Cobalt, my lord.")])
    cloud = CloudSpy()
    outcome = deliberated_send(
        store,
        two_worlds(store, local, cloud),
        f"Typed, not spoken: {CANARY}",
        catalogue=load_catalogue(store),
        conversation_id=conversation,
        live_voice=sessions.live_conversations(),
    )
    assert cloud.seen == [], "a typed turn under an open Voice session reached the cloud"
    assert not cloud.carries(CANARY)
    assert len(local.sent) == 1
    # And it did not durably seal the conversation: nothing was spoken.
    assert not is_conversation_sealed(store, conversation)
    assert outcome is not None


# --- §2.7: the later turns --------------------------------------------------------


def test_a_later_typed_turn_in_the_same_sealed_conversation_cannot_leak_it(
    store: Engine,
) -> None:
    """§2.7's first negative, and the one the ruling exists for."""
    gateway_local = LocalAdapter([ok("Noted, my lord."), ok("Of course, my lord.")])
    cloud = CloudSpy()
    gateway = two_worlds(store, gateway_local, cloud)

    session, _ = spoken_session(store, gateway, CANARY)
    (turn,) = session.snapshot().turns
    conversation = turn.conversation_id

    # Voice off: the transient layer is gone, and the durable seal is not.
    session.close("the owner turned Voice off")
    assert is_conversation_sealed(store, conversation)

    deliberated_send(
        store,
        gateway,
        "And what did I say about the drawer?",
        catalogue=load_catalogue(store),
        conversation_id=conversation,
        live_voice=LiveVoiceConversations(),
    )

    assert cloud.seen == [], "a later typed turn in a sealed conversation reached the cloud"
    assert not cloud.carries(CANARY)
    assert len(gateway_local.sent) == 2, "both turns were answered here"
    assert CANARY in gateway_local.sent[1][1], "the history really did carry the phrase locally"


def test_a_new_unsealed_conversation_keeps_its_ordinary_cloud_support(
    store: Engine,
) -> None:
    """§2.7's clean boundary. The seal is narrow, not a global downgrade."""
    local = LocalAdapter([ok("Noted.")])
    cloud = CloudSpy()
    gateway = two_worlds(store, local, cloud)
    spoken_session(store, gateway, CANARY)

    # A different conversation that draws in nothing sealed.
    fresh_local = LocalAdapter([ok("Cobalt, my lord.")])
    fresh_cloud = CloudSpy(script=[classifier_says("not_consequential")])
    deliberated_send(
        store,
        two_worlds(store, fresh_local, fresh_cloud),
        "What colour is the hall?",
        catalogue=load_catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
        live_voice=LiveVoiceConversations(),
    )
    assert len(fresh_cloud.seen) == 1, "it classified on its cloud structured route, as before"
    assert not fresh_cloud.carries(CANARY), "and carried nothing from the sealed conversation"


def test_the_request_is_refused_if_a_sealed_turn_somehow_reaches_a_cloud_route(
    store: Engine,
) -> None:
    """The structural backstop, at the narrowest door.

    Every layer above this one is supposed to prevent it: the decision is taken
    once, routing filters cloud routes out, and the sealed branch never calls the
    classifier. This asserts the floor beneath all of that — a local-only request
    handed directly to a cloud configuration is refused before transmission.
    """
    cloud = CloudSpy()
    gateway = two_worlds(store, LocalAdapter([]), cloud)
    cloud_config = next(config for config in active() if config.hosting is Hosting.CLOUD)

    from val_domain.gateway import Classification, GatewayRequest, TaskType

    request = GatewayRequest(
        task_type=TaskType.CLASSIFICATION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content=CANARY),),
        project_id=None,
        project_attribution="explicit_none",  # type: ignore[arg-type]
        egress=Egress.LOCAL_ONLY,
    )
    with pytest.raises(GatewayError) as refused:
        gateway.complete_with_configuration(request, cloud_config)
    assert refused.value.kind is GatewayErrorKind.LOCAL_ONLY_EGRESS_REFUSED
    assert cloud.seen == [], "the refusal happened before the adapter was reached"
    assert not cloud.carries(CANARY)

    with store.connect() as connection:
        calls = connection.execute(text("select count(*) from model_calls")).scalar_one()
    assert calls == 0, "and no row asserts a call that never happened"


# --- §2.6: the seal travels with recall ---------------------------------------------


def test_sealed_content_recalled_into_another_conversation_cannot_leak(
    store: Engine,
) -> None:
    """§2.6 and §2.7's second negative — the leak the ruling is really about.

    A1 is spoken and sealed. A2 is a **different, unsealed** conversation in the
    same project, with no history of its own, so anything it knows came from recall.
    The assertion has two halves and both matter: the canary must reach the local
    route — otherwise recall returned nothing and this test proves nothing — and it
    must reach **no cloud route**.

    **A stated ordering fact, recorded rather than smoothed over.** A2 is an
    ordinary unsealed conversation, so its turn classifies on the cloud structured
    route as usual, and that call happens *before* recall is assembled. What it
    carries is A2's own newly typed message and nothing else: no history, no recall,
    no envelope, no voice-derived context. So the sealed phrase cannot reach it, and
    the assertion below is over the complete request body rather than over a
    convenient field. The escalation §2.6 requires applies to the call that actually
    carries the recalled content — the response — which routes locally.

    The alternative would have been to seal every conversation in a project as soon
    as one of them was spoken in, which §2.7 explicitly rules out: a new
    conversation that draws in no sealed content is the clean boundary back to
    ordinary egress.
    """
    spoken_local = LocalAdapter([ok("Noted, my lord.")])
    spoken_cloud = CloudSpy()
    session, _ = spoken_session(store, two_worlds(store, spoken_local, spoken_cloud), CANARY)
    (spoken_turn,) = session.snapshot().turns
    session.close("the owner turned Voice off")
    assert is_conversation_sealed(store, spoken_turn.conversation_id)

    local = LocalAdapter([ok("In the second drawer, my lord.")])
    cloud = CloudSpy(script=[classifier_says("not_consequential")])
    outcome = deliberated_send(
        store,
        two_worlds(store, local, cloud),
        "Where is the Wollaton codicil?",
        catalogue=load_catalogue(store),
        signals=ProjectSignals(explicit_selection="Project Alpha"),
        title="A2",
        live_voice=LiveVoiceConversations(),
    )

    # Recall really did carry it. Without this the negative below is vacuous.
    assert len(local.sent) == 1, "the second conversation was answered on this machine"
    assert CANARY in local.sent[0][1], (
        "recall did not carry the sealed phrase into the second conversation, so this "
        "test would prove nothing about the seal"
    )
    # The cloud saw exactly one call — A2's own classification, of A2's own typed
    # message — and it carried nothing from the sealed conversation.
    assert len(cloud.seen) == 1
    (slug, body) = cloud.seen[0]
    assert not cloud.carries(CANARY), "the sealed phrase reached a cloud provider"
    assert "codicil" in body, "the classifier did see the new typed message, as it always does"
    assert "second drawer" not in body, "and no part of the recalled sealed content"
    assert "Noted, my lord." not in body, "nor Val's answer from the sealed conversation"
    assert slug is not None
    assert outcome is not None

    # The second conversation itself is NOT durably sealed: it spoke nothing. Its
    # request was local-only because of what it carried, which is a fact about the
    # request and not about the conversation.
    with store.connect() as connection:
        sealed_ids = {
            row.conversation_id
            for row in connection.execute(
                text("select conversation_id from conversation_egress_seals")
            )
        }
    assert sealed_ids == {spoken_turn.conversation_id}


def test_a_sealed_conversation_is_still_recallable_locally(store: Engine) -> None:
    """§1.6 and §2.6's explicit instruction: not excluded from recall, only from egress.

    A voice conversation is remembered exactly as a typed one is. Solving the leak
    by making sealed conversations invisible to recall would have been a different
    system, and a worse one.
    """
    session, _ = spoken_session(
        store, two_worlds(store, LocalAdapter([ok("Noted.")]), CloudSpy()), CANARY
    )
    session.close("off")

    local = LocalAdapter([ok("In the second drawer.")])
    cloud = CloudSpy(script=[classifier_says("not_consequential")])
    deliberated_send(
        store,
        two_worlds(store, local, cloud),
        "Where is the Wollaton codicil?",
        catalogue=load_catalogue(store),
        signals=ProjectSignals(explicit_selection="Project Alpha"),
        live_voice=LiveVoiceConversations(),
    )
    assert CANARY in local.sent[0][1], "the sealed conversation was excluded from recall"
    assert not cloud.carries(CANARY), "and recalling it locally did not leak it"


def test_the_record_state_envelope_states_the_local_only_condition(store: Engine) -> None:
    """§2.5: Val is told, so she can answer truthfully about what is unavailable.

    Present only when true: an ordinary turn's envelope says nothing about egress.
    """
    local = LocalAdapter([ok("Noted.")])
    session, _ = spoken_session(store, two_worlds(store, local, CloudSpy()), CANARY)
    assert session.snapshot().turns

    body = local.sent[0][1]
    assert '"external_egress"' in body
    assert '"state": "local_only"' in body
    assert "voice_session_active" in body or "conversation_sealed" in body
    assert "Web search, remote tools" in body, "and what it costs, said once"

    # An ordinary typed turn in a fresh conversation says nothing about egress.
    ordinary_local = LocalAdapter([ok("Cobalt.")])
    deliberated_send(
        store,
        two_worlds(store, ordinary_local, CloudSpy(script=[classifier_says("not_consequential")])),
        "What colour is the hall?",
        catalogue=load_catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
        live_voice=LiveVoiceConversations(),
    )
    assert '"external_egress"' not in ordinary_local.sent[0][1], (
        "an ordinary turn should not spend context restating the ordinary case"
    )


# --- §2.1: every route to canonical seals -------------------------------------------


def test_the_resume_merge_route_applies_the_seal(store: Engine) -> None:
    """Two halves of one sentence, joined before submission, still seal."""
    local = LocalAdapter([ok("At once, my lord.")])
    cloud = CloudSpy()
    gateway = two_worlds(store, local, cloud)
    conversation = a_conversation(store)
    sessions = VoiceSessions()

    def submit(
        content: str,
        existing: UUID | None,
        *,
        on_delta: Callable[[str], None] | None = None,
        merged: bool = False,
        on_persisted: Callable[[UUID, UUID], None] | None = None,
    ) -> DeliberatedOutcome:
        assert merged, "this is the resume-merge case"
        return deliberated_send(
            store,
            gateway,
            content,
            catalogue=load_catalogue(store),
            conversation_id=existing,
            on_delta=on_delta,
            on_persisted=on_persisted,
            spoken=True,
            seal_route=SealRoute.RESUME_MERGE if merged else SealRoute.UTTERANCE_FINALIZED,
            live_voice=sessions.live_conversations(),
        )

    clock = Clock()
    session = VoiceSession(
        store,
        ScriptedRecognizer(
            batches=[
                [started(1), final(1, "Ask the cook about dinner")],
                [started(2), final(2, "and the wine.")],
            ]
        ),
        submit=submit,
        conversation_id=conversation,
        clock=clock,
    )
    session.start()
    sessions.add(UUID(int=4), session)

    session.feed(MARKER)
    # Inside the resume window: the second half joins the first before submission.
    session.feed(MARKER)
    settle(session, clock)

    (turn,) = session.snapshot().turns
    assert turn.utterance.merged_from, "the two halves were joined"
    with store.connect() as connection:
        seal = connection.execute(
            text(
                "select applied_by, message_id from conversation_egress_seals "
                " where conversation_id = :id"
            ),
            {"id": conversation},
        ).one()
    assert seal.applied_by == "resume_merge"
    assert seal.message_id == turn.message_id
    assert cloud.seen == []


def test_an_adopted_recovered_fragment_applies_the_seal(store: Engine) -> None:
    """§2.1's third route: a guess a restart found, adopted by the owner.

    It arrives as ordinary text through the ordinary door, and it is still
    live-microphone-derived text, so it still seals.
    """
    local = LocalAdapter([ok("Noted, my lord.")])
    cloud = CloudSpy()
    conversation = a_conversation(store)

    outcome = deliberated_send(
        store,
        two_worlds(store, local, cloud),
        CANARY,
        catalogue=load_catalogue(store),
        conversation_id=conversation,
        spoken=True,
        seal_route=SealRoute.RECOVERED_FRAGMENT_ADOPTED,
        live_voice=LiveVoiceConversations(),
    )
    assert outcome is not None
    with store.connect() as connection:
        seal = connection.execute(
            text("select applied_by from conversation_egress_seals where conversation_id = :id"),
            {"id": conversation},
        ).one()
    assert seal.applied_by == "recovered_fragment_adopted"
    assert cloud.seen == [] and not cloud.carries(CANARY)


def test_the_seal_is_one_fact_per_conversation_however_many_turns_are_spoken(
    store: Engine,
) -> None:
    """A second utterance finds it already there and does not write a second row."""
    local = LocalAdapter([ok("One."), ok("Two.")])
    gateway = two_worlds(store, local, CloudSpy())
    conversation = a_conversation(store)
    sessions = VoiceSessions()

    def submit(
        content: str,
        existing: UUID | None,
        *,
        on_delta: Callable[[str], None] | None = None,
        merged: bool = False,
        on_persisted: Callable[[UUID, UUID], None] | None = None,
    ) -> DeliberatedOutcome:
        return deliberated_send(
            store,
            gateway,
            content,
            catalogue=load_catalogue(store),
            conversation_id=existing,
            on_delta=on_delta,
            on_persisted=on_persisted,
            spoken=True,
            live_voice=sessions.live_conversations(),
        )

    clock = Clock()
    session = VoiceSession(
        store,
        ScriptedRecognizer(
            batches=[
                [started(1), final(1, "First thing.")],
                [started(2), final(2, "Second thing.")],
            ]
        ),
        submit=submit,
        conversation_id=conversation,
        clock=clock,
    )
    session.start()
    sessions.add(UUID(int=5), session)

    session.feed(MARKER)
    settle(session, clock)
    first = session.snapshot().turns[0]
    session.deliver(first.message_id)
    session.feed(MARKER)
    settle(session, clock)

    assert len(session.snapshot().turns) == 2
    with store.connect() as connection:
        rows = connection.execute(
            text("select message_id from conversation_egress_seals where conversation_id = :id"),
            {"id": conversation},
        ).all()
    assert len(rows) == 1, "one seal per conversation"
    assert rows[0].message_id == first.message_id, "and it names the first spoken message"
