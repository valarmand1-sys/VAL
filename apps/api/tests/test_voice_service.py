"""The voice-input service contract — Voice mode work package 1, 23 Sept 2026.

The smallest surface the later desktop package needs, against real PostgreSQL,
the real FastAPI application and a scripted recognizer: open a session, feed PCM,
poll the guess and the state, finalize, observe the canonical result, stop.

Three things these tests hold that the desktop package will depend on:

- the guess and the turns are **separate fields**, so nothing renders a rolling
  transcript as conversation by accident;
- audio is a request body and goes nowhere else — not to a file, not to a column;
- the origin rules are exactly the service's existing ones. No new origin, no new
  bind, no upgrade, no token; a voice route is not a reason to loosen anything.

With no recognizer wired, every voice route says so plainly and reaches for
nothing else — which is also what makes the rest of the service unchanged by this
package's presence.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from test_service import OpenLedger, ScriptedAdapter, classifier_says, client, ok

from val_api.app import create_app
from val_domain.speech import VoiceConditioning, digest_of
from val_domain.voice import EndpointConfiguration, RecognizerEvent, RecognizerIdentity
from val_gateway.gateway import Gateway
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader
from val_gateway.provenance import verifier
from val_gateway.speech import register_voice

PCM = b"\x33\x44" * 160

IDENTITY = RecognizerIdentity(
    name="whisper.cpp",
    version="v1.9.4",
    commit="927cfce34f31707e17f2bff35c349632fb9e2c3a",
    model_identifier="ggml-small.en",
    model_sha256="a" * 64,
    vad_model_identifier="silero-vad-v6.2.0",
    vad_model_sha256="b" * 64,
)


@dataclass
class ScriptedRecognizer:
    """A recognizer that reports from a script, one batch per handover."""

    batches: list[list[RecognizerEvent]] = field(default_factory=list)
    received: list[int] = field(default_factory=list)
    stopped: bool = False
    _queue: list[RecognizerEvent] = field(default_factory=list)

    @property
    def identity(self) -> RecognizerIdentity:
        return IDENTITY

    @property
    def endpoint(self) -> EndpointConfiguration:
        return EndpointConfiguration()

    def start(self) -> None:
        return None

    def feed(self, pcm: bytes) -> None:
        self.received.append(len(pcm))
        self._release()

    def flush(self) -> None:
        self._release()

    def drain(self) -> Iterator[RecognizerEvent]:
        while self._queue:
            yield self._queue.pop(0)

    def stop(self) -> None:
        self.stopped = True

    def _release(self) -> None:
        if self.batches:
            self._queue.extend(self.batches.pop(0))


def voice_client(
    engine: Engine, adapter: ScriptedAdapter, recognizer: ScriptedRecognizer
) -> TestClient:
    """The real application, with the recognizer factory the composition root supplies."""
    gateway = Gateway(
        adapters={"anthropic": adapter, "openai": adapter, "lmstudio": adapter},
        recorder=lambda record: record_call(engine, record),
        ledger=OpenLedger(),
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(engine),
        verify_provenance=verifier(engine),
    )
    return TestClient(
        create_app(engine, gateway, warnings=[], recognizers=lambda: recognizer),
    )


def started(index: int = 1) -> RecognizerEvent:
    return RecognizerEvent(kind="speech_start", session=index)


def guess(words: str, index: int = 1) -> RecognizerEvent:
    return RecognizerEvent(kind="provisional", session=index, text=words)


def final(words: str, index: int = 1) -> RecognizerEvent:
    return RecognizerEvent(kind="final", session=index, text=words, reason="silence")


# --- with no recognizer wired ---------------------------------------------------------


def test_without_a_recognizer_every_voice_route_says_so_and_reaches_for_nothing(
    store: Engine,
) -> None:
    """503, with the negative stated. Not a cloud call, not a silent nothing."""
    with client(store, ScriptedAdapter([])) as reachable:
        response = reachable.post("/voice/sessions", json={"project": "Project Alpha"})
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "not available" in detail
    assert "No cloud speech recognition was called" in detail


def test_the_rest_of_the_service_is_untouched_by_this_package(store: Engine) -> None:
    """A typed turn still works exactly as it did, with no recognizer in sight."""
    adapter = ScriptedAdapter([classifier_says("not_consequential"), ok("Cobalt, my lord.")])
    with client(store, adapter) as reachable:
        assert reachable.get("/health").json()["status"] == "running"
        answered = reachable.post(
            "/turns", json={"content": "What colour is the hall?", "project": "Project Alpha"}
        )
    assert answered.status_code == 200
    assert answered.json()["val_message"]["content"] == "Cobalt, my lord."


# --- the session's life --------------------------------------------------------------


def test_a_session_opens_and_reports_exactly_which_ears_are_listening(
    store: Engine,
) -> None:
    recognizer = ScriptedRecognizer()
    with voice_client(store, ScriptedAdapter([]), recognizer) as reachable:
        opened = reachable.post("/voice/sessions", json={"project": "Project Alpha"})
    assert opened.status_code == 201
    view = opened.json()
    assert view["state"] == "listening"
    assert view["provisional"] == ""
    assert view["turns"] == []
    assert view["recognizer"]["recognizer"] == "whisper.cpp"
    assert view["recognizer"]["recognizer_version"] == "v1.9.4"
    assert view["recognizer"]["asr_model_sha256"] == "a" * 64
    assert view["endpoint"]["min_silence_ms"] == 650
    assert view["endpoint"]["threshold"] == 0.5
    assert view["conversation_id"] is None, "no conversation yet; the first turn makes one"
    assert view["voice_session_id"] is None, "and so no durable session row yet"


def test_pcm_is_a_request_body_and_the_guess_is_a_field_of_its_own(
    store: Engine,
) -> None:
    """Feed, then poll. The rolling transcript is never in `turns`."""
    recognizer = ScriptedRecognizer(
        batches=[[started()], [guess("Ask the co")], [guess("Ask the cook")]]
    )
    with voice_client(store, ScriptedAdapter([]), recognizer) as reachable:
        session = reachable.post("/voice/sessions", json={"project": "Project Alpha"}).json()[
            "session"
        ]
        first = reachable.post(
            f"/voice/sessions/{session}/audio",
            content=PCM,
            headers={"content-type": "application/octet-stream"},
        ).json()
        assert first["state"] == "hearing" and first["hearing"] is True

        second = reachable.post(
            f"/voice/sessions/{session}/audio",
            content=PCM,
            headers={"content-type": "application/octet-stream"},
        ).json()
        assert second["provisional"] == "Ask the co"
        assert second["turns"] == [], "a guess is never a turn"

        third = reachable.post(
            f"/voice/sessions/{session}/audio",
            content=PCM,
            headers={"content-type": "application/octet-stream"},
        ).json()
        assert third["provisional"] == "Ask the cook", "and it revises in place"

        polled = reachable.get(f"/voice/sessions/{session}").json()
        assert polled["provisional"] == "Ask the cook"

    assert recognizer.received == [len(PCM)] * 3, "each block reached the recognizer whole"


def test_a_settled_utterance_becomes_one_canonical_turn_with_its_answer(
    store: Engine,
) -> None:
    """The observable result: one owner message, one Val answer, one provenance row."""
    recognizer = ScriptedRecognizer(
        batches=[[started(), guess("What time"), final("What time is dinner?")]]
    )
    adapter = ScriptedAdapter([classifier_says("not_consequential"), ok("Eight, my lord.")])
    with voice_client(store, adapter, recognizer) as reachable:
        session = reachable.post("/voice/sessions", json={"project": "Project Alpha"}).json()[
            "session"
        ]
        reachable.post(
            f"/voice/sessions/{session}/audio",
            content=PCM,
            headers={"content-type": "application/octet-stream"},
        )
        # The resume window has to pass before the turn is submitted; poll until
        # it has, exactly as the desktop will.
        view = _poll_until_answered(reachable, session)

    (turn,) = view["turns"]
    assert turn["text"] == "What time is dinner?"
    assert turn["provisional_events"] == 1
    assert turn["merged_from"] == []
    assert turn["revised_to"] is None
    assert turn["delivered"] is False
    assert turn["answer"]["val_message"]["content"] == "Eight, my lord."
    assert view["conversation_id"] == turn["conversation_id"]
    assert view["voice_session_id"] is not None, "the durable session exists now"

    with store.connect() as connection:
        provenance = connection.execute(
            text(
                "select input_mode, transcription_status from voice_message_provenance "
                " where message_id = :id"
            ),
            {"id": UUID(turn["message_id"])},
        ).one()
    assert (provenance.input_mode, provenance.transcription_status) == ("voice", "final")


def test_finalize_ends_the_utterance_without_waiting_for_silence(store: Engine) -> None:
    recognizer = ScriptedRecognizer(batches=[[started()], [final("That is all.")]])
    adapter = ScriptedAdapter([classifier_says("not_consequential"), ok("Very good.")])
    with voice_client(store, adapter, recognizer) as reachable:
        session = reachable.post("/voice/sessions", json={"project": "Project Alpha"}).json()[
            "session"
        ]
        reachable.post(
            f"/voice/sessions/{session}/audio",
            content=PCM,
            headers={"content-type": "application/octet-stream"},
        )
        flushed = reachable.post(f"/voice/sessions/{session}/finalize").json()
        assert flushed["pending"] == "That is all.", "settled, and waiting out the window"
        view = _poll_until_answered(reachable, session)
    assert view["turns"][0]["text"] == "That is all."


def test_marking_a_turn_delivered_is_a_call_the_delivering_layer_makes(
    store: Engine,
) -> None:
    """No audible delivery exists in this package, so nothing calls it yet."""
    recognizer = ScriptedRecognizer(batches=[[started(), final("Say that again.")]])
    adapter = ScriptedAdapter([classifier_says("not_consequential"), ok("Of course.")])
    with voice_client(store, adapter, recognizer) as reachable:
        session = reachable.post("/voice/sessions", json={"project": "Project Alpha"}).json()[
            "session"
        ]
        reachable.post(
            f"/voice/sessions/{session}/audio",
            content=PCM,
            headers={"content-type": "application/octet-stream"},
        )
        view = _poll_until_answered(reachable, session)
        message_id = view["turns"][0]["message_id"]
        assert view["turns"][0]["delivered"] is False
        after = reachable.post(f"/voice/sessions/{session}/delivered/{message_id}").json()
    assert after["turns"][0]["delivered"] is True


def test_closing_releases_the_recognizer_and_the_session_is_gone(store: Engine) -> None:
    recognizer = ScriptedRecognizer(batches=[[started()]])
    with voice_client(store, ScriptedAdapter([]), recognizer) as reachable:
        session = reachable.post("/voice/sessions", json={"project": "Project Alpha"}).json()[
            "session"
        ]
        closed = reachable.post(f"/voice/sessions/{session}/close").json()
        assert closed["state"] == "closed"
        assert recognizer.stopped is True
        assert reachable.get(f"/voice/sessions/{session}").status_code == 404


def test_an_unknown_session_is_a_plain_404(store: Engine) -> None:
    recognizer = ScriptedRecognizer()
    with voice_client(store, ScriptedAdapter([]), recognizer) as reachable:
        missing = "00000000-0000-4000-8000-000000000000"
        assert reachable.get(f"/voice/sessions/{missing}").status_code == 404
        assert reachable.post(f"/voice/sessions/{missing}/finalize").status_code == 404
        assert reachable.post(f"/voice/sessions/{missing}/audio", content=PCM).status_code == 404


# --- recovery, and the origin rules ---------------------------------------------------


def test_an_interrupted_guess_is_offered_back_labelled_and_never_as_a_message(
    store: Engine,
) -> None:
    """Read once after a restart: the words, marked `interrupted`."""
    recognizer = ScriptedRecognizer(batches=[[started(), final("First, a real turn.")]])
    adapter = ScriptedAdapter([classifier_says("not_consequential"), ok("Noted.")])
    with voice_client(store, adapter, recognizer) as reachable:
        session = reachable.post("/voice/sessions", json={"project": "Project Alpha"}).json()[
            "session"
        ]
        reachable.post(
            f"/voice/sessions/{session}/audio",
            content=PCM,
            headers={"content-type": "application/octet-stream"},
        )
        view = _poll_until_answered(reachable, session)
        conversation = view["conversation_id"]
        voice_session = view["voice_session_id"]

        # A guess the process never settled, written the way a live session does.
        with store.begin() as connection:
            connection.execute(
                text(
                    "insert into voice_recovery_journal "
                    "  (voice_session_id, conversation_id, utterance, entry, "
                    "   provisional_text, state) "
                    "values (:session, :conversation, 2, 1, "
                    "        'and I was in the middle of saying', 'provisional')"
                ),
                {"session": UUID(voice_session), "conversation": UUID(conversation)},
            )

        open_guesses = reachable.get("/voice/interrupted").json()
        assert len(open_guesses) == 1
        assert open_guesses[0]["state"] == "interrupted"
        assert open_guesses[0]["provisional_text"] == "and I was in the middle of saying"

        history = reachable.get(f"/conversations/{conversation}").json()
        assert all(
            "middle of saying" not in message["content"] for message in history["messages"]
        ), "a recovered guess is never in the conversation"
        assert reachable.get("/voice/interrupted").json() == [], "reported once, then marked"


def test_the_voice_routes_carry_the_services_existing_origin_rules(store: Engine) -> None:
    """Exactly the two shell origins the rest of the service grants — nothing wider."""
    recognizer = ScriptedRecognizer()
    with voice_client(store, ScriptedAdapter([]), recognizer) as reachable:
        allowed = reachable.options(
            "/voice/sessions",
            headers={
                "Origin": "tauri://localhost",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "tauri://localhost"

        refused = reachable.options(
            "/voice/sessions",
            headers={
                "Origin": "https://example.invalid",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert "access-control-allow-origin" not in refused.headers


def _poll_until_answered(
    reachable: TestClient, session: str, attempts: int = 200
) -> dict[str, object]:
    """Poll the way the desktop will, until the settled turn appears.

    Real seconds, because the resume window is a real interval: the house waits
    before submitting in case the owner was only drawing breath.
    """
    for _ in range(attempts):
        view = reachable.get(f"/voice/sessions/{session}").json()
        if view["turns"]:
            settled: dict[str, object] = view
            return settled
        if view["error"]:
            pytest.fail(f"the session failed: {view['error']}")
        time.sleep(0.05)
    pytest.fail("the turn never settled")


# --- speech delivery, through the service — work package 2 ----------------------------


@dataclass
class ScriptedVoiceProvider:
    """The local voice, standing still. Records exactly what it was asked to say."""

    spoken: list[str] = field(default_factory=list)
    model_revision: str = "e7dd0585652209fa0d7783659aad4e8a324de11c"
    quantization: str = "8-bit MLX, group size 64, affine"
    release: threading.Event | None = None
    started: threading.Event = field(default_factory=threading.Event)

    def synthesize(self, request: object) -> object:
        from val_domain.speech import SpeechResult

        self.started.set()
        if self.release is not None:
            self.release.wait(timeout=10)
        said = request.text  # type: ignore[attr-defined]
        self.spoken.append(said)
        return SpeechResult(
            audio=b"RIFF" + hashlib.sha256(said.encode()).digest(),
            sample_rate=24000,
            duration_seconds=max(0.4, len(said) / 16),
            provider="mlxaudio",
            model_identifier="mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit",
            model_revision=self.model_revision,
            quantization=self.quantization,
            runtime="mlx-audio",
            runtime_version="0.5.5",
            generation={},
            clone_prompt_sha256="9" * 64,
            elapsed_seconds=0.01,
            cost_usd=0.0,
            local=True,
        )


REFERENCE = b"RIFF" + b"\x00" * 60 + b"the established reference"


def a_governed_voice() -> VoiceConditioning:
    return VoiceConditioning(
        name="val-established-v1",
        reference_audio=REFERENCE,
        reference_sha256=digest_of(REFERENCE),
        reference_text="Good evening, my lord.",
        voice_description="Adult British woman. Kind, intelligent, warm.",
        designed_by_model="mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit",
        designed_by_revision="f90d617701d9f7f4ca499291e0b57f2b3c2fd2ee",
    )


def speaking_client(
    engine: Engine,
    adapter: ScriptedAdapter,
    recognizer: ScriptedRecognizer,
    voice_provider: ScriptedVoiceProvider,
) -> TestClient:
    """The real application, with a voice wired as the composition root wires one."""
    voice = a_governed_voice()
    register_voice(
        engine,
        voice,
        described={
            "reference_sample_rate": 24000,
            "reference_duration_seconds": 18.756,
            "designed_by_quantization": "8-bit MLX",
            "designed_by_runtime": "mlx-audio 0.5.5",
            "designed_generation": {},
            "origin": "owner-authorised established reference",
            "identity_claim": "not model-verified",
        },
    )
    gateway = Gateway(
        adapters={"anthropic": adapter, "openai": adapter, "lmstudio": adapter},
        recorder=lambda record: record_call(engine, record),
        ledger=OpenLedger(),
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(engine),
        verify_provenance=verifier(engine),
        speech=voice_provider,  # type: ignore[arg-type]
        voice=voice,
    )
    return TestClient(create_app(engine, gateway, warnings=[], recognizers=lambda: recognizer))


def test_a_spoken_turn_reports_its_delivery_through_the_service(store: Engine) -> None:
    """The desktop can see what was spoken, and what reached him."""
    recognizer = ScriptedRecognizer(batches=[[started(), final("What time is dinner?")]])
    adapter = ScriptedAdapter([classifier_says("not_consequential"), ok("Eight, my lord.")])
    voice_provider = ScriptedVoiceProvider()
    with speaking_client(store, adapter, recognizer, voice_provider) as reachable:
        session = reachable.post("/voice/sessions", json={"project": "Project Alpha"}).json()[
            "session"
        ]
        reachable.post(
            f"/voice/sessions/{session}/audio",
            content=PCM,
            headers={"content-type": "application/octet-stream"},
        )
        view = _poll_until_answered(reachable, session)

    (turn,) = view["turns"]
    assert voice_provider.spoken == ["Eight, my lord."], "her exact words, and only hers"
    assert turn["delivered"] is True, "audible delivery began, so the boundary was crossed"
    delivery = turn["delivery"]
    assert delivery is not None
    assert delivery["state"] == "completed"
    assert delivery["delivered_prefix"] == "Eight, my lord."
    assert delivery["delivered_characters"] == len("Eight, my lord.")
    assert delivery["segments_delivered"] == delivery["segments_total"] == 1


def test_the_delivery_of_one_answer_is_readable_by_message(store: Engine) -> None:
    recognizer = ScriptedRecognizer(batches=[[started(), final("What time is dinner?")]])
    adapter = ScriptedAdapter([classifier_says("not_consequential"), ok("Eight, my lord.")])
    with speaking_client(store, adapter, recognizer, ScriptedVoiceProvider()) as reachable:
        session = reachable.post("/voice/sessions", json={"project": "Project Alpha"}).json()[
            "session"
        ]
        reachable.post(
            f"/voice/sessions/{session}/audio",
            content=PCM,
            headers={"content-type": "application/octet-stream"},
        )
        view = _poll_until_answered(reachable, session)
        message_id = view["turns"][0]["answer"]["val_message"]["id"]
        found = reachable.get(f"/messages/{message_id}/delivery")
        missing = reachable.get(f"/messages/{uuid4()}/delivery")

    assert found.status_code == 200
    assert found.json()["state"] == "completed"
    assert missing.status_code == 404


def test_the_caller_can_stop_her_speaking(store: Engine) -> None:
    """Barge-in from the capture layer that will hear him first (work package 3)."""
    recognizer = ScriptedRecognizer(batches=[[started(), final("Tell me about the barn.")]])
    long_answer = (
        "The barn is available on the fourteenth, my lord. The generator limit applies "
        "after six. Mrs. Hale asked whether we still want both days."
    )
    adapter = ScriptedAdapter([classifier_says("not_consequential"), ok(long_answer)])
    voice_provider = ScriptedVoiceProvider(release=threading.Event())
    with speaking_client(store, adapter, recognizer, voice_provider) as reachable:
        session = reachable.post("/voice/sessions", json={"project": "Project Alpha"}).json()[
            "session"
        ]

        reachable.post(
            f"/voice/sessions/{session}/audio",
            content=PCM,
            headers={"content-type": "application/octet-stream"},
        )
        # The desktop polls, and polling is what moves the session on: the resume
        # window has to pass before the utterance is submitted at all.
        polling = threading.Event()

        def poll() -> None:
            while not polling.is_set():
                reachable.get(f"/voice/sessions/{session}")
                time.sleep(0.05)

        poller = threading.Thread(target=poll, daemon=True)
        poller.start()
        try:
            assert voice_provider.started.wait(timeout=60), "the voice has a segment in hand"
            cut = reachable.post(f"/voice/sessions/{session}/interrupt").json()
            voice_provider.release.set()  # type: ignore[union-attr]
            after = _poll_until_answered(reachable, session, attempts=1200)
        finally:
            polling.set()
            poller.join(timeout=5)

    assert cut["delivery"] is not None
    assert cut["delivery"]["state"] == "interrupted"
    assert cut["cancellations_ms"], "the service-side interval is reported"
    assert cut["cancellations_ms"][0] <= 300.0, "within the service-side target"
    (turn,) = after["turns"]
    assert turn["delivery"]["state"] == "interrupted"
    assert turn["delivery"]["reason"] == "the caller signalled barge-in"
    assert turn["delivery"]["delivered_characters"] < len(long_answer), "he heard part of it"


def test_interrupting_a_session_that_is_not_speaking_is_harmless(store: Engine) -> None:
    recognizer = ScriptedRecognizer()
    with speaking_client(
        store, ScriptedAdapter([]), recognizer, ScriptedVoiceProvider()
    ) as reachable:
        session = reachable.post("/voice/sessions", json={"project": "Project Alpha"}).json()[
            "session"
        ]
        quiet = reachable.post(f"/voice/sessions/{session}/interrupt")
    assert quiet.status_code == 200
    assert quiet.json()["delivery"] is None
    assert quiet.json()["cancellations_ms"] == []


def test_a_house_with_no_voice_hears_and_does_not_speak(store: Engine) -> None:
    """No admitted speech route means a session that listens — honestly, and silently."""
    recognizer = ScriptedRecognizer(batches=[[started(), final("What time is dinner?")]])
    adapter = ScriptedAdapter([classifier_says("not_consequential"), ok("Eight, my lord.")])
    with voice_client(store, adapter, recognizer) as reachable:
        session = reachable.post("/voice/sessions", json={"project": "Project Alpha"}).json()[
            "session"
        ]
        reachable.post(
            f"/voice/sessions/{session}/audio",
            content=PCM,
            headers={"content-type": "application/octet-stream"},
        )
        view = _poll_until_answered(reachable, session)
    (turn,) = view["turns"]
    assert view["delivery"] is None
    assert turn["delivery"] is None, "nothing was spoken, so there is no delivery record"
    assert turn["delivered"] is False
