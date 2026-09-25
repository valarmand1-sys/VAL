# ruff: noqa: F811, F401 - fixtures and harness imported by name
"""Val speaks, and stops when he does. Voice work package 2, sections 6 to 13.

Real PostgreSQL, a scripted provider standing in for the model and a scripted
voice standing in for Qwen3-TTS. What is under test is Val's behaviour, not the
voice: the voice was settled by its own acceptance, and what has to hold here is
what the order names.

- only Core's **visible** text enters speech, and a withheld marker stops it;
- every spoken segment is an exact slice of the answer, and they reconstruct it;
- speech begins before Val has finished writing;
- live audio is **never** written to disk and is released when delivery ends;
- the five delivery states are distinct, append-only, and honest;
- the **first** audio is the delivered boundary, not the last;
- barge-in stops her, discards what was queued, keeps the exact heard prefix, and
  undoes nothing that already happened;
- the next turn's context does not assume he heard the part she never spoke.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from test_deliberation_machinery import (
    ScriptedAdapter,
    build_gateway,
    clean_personas,
    ok,
    store,
)
from test_voice_input import (
    MARKER,
    Clock,
    ScriptedRecognizer,
    a_conversation,
    final,
    guess,
    started,
)

from val_domain.gateway import CapabilityProfile, ModelConfig
from val_domain.registry import active, by_slug
from val_domain.speech import (
    DeliveryState,
    SpeechRequest,
    SpeechResult,
    SpeechUnavailableError,
    VoiceConditioning,
    digest_of,
)
from val_gateway.deliberate import DeliberatedOutcome
from val_gateway.deliberate import send as deliberated_send
from val_gateway.delivery import (
    CANCELLATION_TARGET_MS,
    EphemeralSink,
    SpeechDelivery,
    delivery_for,
    short_deliveries,
)
from val_gateway.loop import spoken_delivery_facts
from val_gateway.seal import SealRoute
from val_gateway.voice import RESUME_GRACE_SECONDS, VoiceSession
from val_policy.deliberation import RECONCILIATION_VERDICT_MARKER
from val_policy.project_resolution import ProjectSignals
from val_policy.speech_segments import SpeechTextRefusedError

SPEECH_SLUG = "qwen3-tts-12hz-1-7b-base-8bit-mlxaudio-speech"
REFERENCE = b"RIFF" + b"\x00" * 60 + b"the established reference"


def a_voice() -> VoiceConditioning:
    return VoiceConditioning(
        name="val-established-v1",
        reference_audio=REFERENCE,
        reference_sha256=digest_of(REFERENCE),
        reference_text="Good evening, my lord.",
        voice_description="Adult British woman. Kind, intelligent, warm.",
        designed_by_model="mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit",
        designed_by_revision="f90d617701d9f7f4ca499291e0b57f2b3c2fd2ee",
    )


@dataclass
class ScriptedVoice:
    """The local voice, standing still so delivery can be measured.

    Records exactly what it was asked to say, which is how the exactness claim is
    checked at the boundary that matters: what actually reached the voice.
    """

    spoken: list[str] = field(default_factory=list)
    model_revision: str = "e7dd0585652209fa0d7783659aad4e8a324de11c"
    quantization: str = "8-bit MLX, group size 64, affine"
    #: Seconds each call takes, so a test can hold a segment mid-flight.
    takes: float = 0.0
    fails_on: int | None = None
    started: threading.Event = field(default_factory=threading.Event)
    release: threading.Event | None = None

    def synthesize(self, request: SpeechRequest) -> SpeechResult:
        self.started.set()
        if self.release is not None:
            self.release.wait(timeout=10)
        if self.takes:
            time.sleep(self.takes)
        self.spoken.append(request.text)
        if self.fails_on is not None and len(self.spoken) == self.fails_on:
            raise SpeechUnavailableError("the local voice failed on this segment")
        audio = b"RIFF" + hashlib.sha256(request.text.encode()).digest() * 2
        return SpeechResult(
            audio=audio,
            sample_rate=24000,
            duration_seconds=max(0.4, len(request.text) / 16),
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


def speech_configuration() -> ModelConfig:
    """The admitted speech route, by the profile it declares — never by name."""
    for config in active():
        if CapabilityProfile.SPEECH in config.capability_profiles:
            return config
    raise AssertionError("no admitted speech route")


def register_the_voice(engine: Engine, voice: VoiceConditioning) -> UUID:
    """The governed voice's row, so a spoken segment can be attributed to it."""
    with engine.begin() as connection:
        return connection.execute(
            text(
                "insert into speech_voices "
                "  (name, reference_sha256, reference_bytes, reference_sample_rate, "
                "   reference_duration_seconds, reference_text, reference_text_sha256, "
                "   voice_description, voice_description_sha256, designed_by_model, "
                "   designed_by_revision, designed_by_quantization, designed_by_runtime, "
                "   designed_generation, origin, identity_claim) "
                "values (:name, :digest, 64, 24000, 18.756, :ref_text, :ref_text_digest, "
                "        :description, :description_digest, :model, :revision, 'q', 'r', "
                "        '{}'::jsonb, 'o', 'i') returning id"
            ),
            {
                "name": voice.name,
                "digest": voice.reference_sha256,
                "ref_text": voice.reference_text,
                "ref_text_digest": hashlib.sha256(voice.reference_text.encode()).hexdigest(),
                "description": voice.voice_description,
                "description_digest": hashlib.sha256(voice.voice_description.encode()).hexdigest(),
                "model": voice.designed_by_model,
                "revision": voice.designed_by_revision,
            },
        ).scalar_one()


def a_delivery(engine: Engine, voice_provider: ScriptedVoice, **options: object) -> SpeechDelivery:
    return SpeechDelivery(
        engine,
        speech=voice_provider,
        voice=a_voice(),
        configuration=speech_configuration(),
        **options,  # type: ignore[arg-type]
    )


ANSWER = (
    "Evening, my lord. The two readers disagree because they are answering different "
    "questions. Both can be true at once. I would keep the pages and ask the second "
    "reader what he meant by best."
)


def deliver(delivery: SpeechDelivery, text_body: str, *, pieces: int = 7) -> None:
    """Feed an answer as a provider stream would, then finish."""
    step = max(1, len(text_body) // pieces)
    for start in range(0, len(text_body), step):
        delivery.feed(text_body[start : start + step])
    delivery.finish()


# =============================================================================
# §6-§7. Only Core's visible text, and every segment an exact slice of it
# =============================================================================


def test_every_spoken_segment_is_an_exact_slice_that_reconstructs_the_answer(
    store: Engine,
) -> None:
    """The exactness invariant, at the boundary that matters: the voice itself."""
    voice = ScriptedVoice()
    delivery = a_delivery(store, voice)
    deliver(delivery, ANSWER)

    assert voice.spoken, "something was spoken"
    assert [segment.text for segment in delivery.spoken] == voice.spoken
    for said in voice.spoken:
        assert said in ANSWER, "the voice was handed a slice, never a paraphrase"
    assert "".join("".join(said.split()) for said in voice.spoken) == "".join(ANSWER.split())
    assert delivery.segmenter.reconstructs()
    assert (
        "".join(delivery.segmenter.source[s.start : s.end] for s in delivery.segmenter.segments)
        == ANSWER
    )


def test_speech_begins_before_val_has_finished_writing(store: Engine) -> None:
    """Progressive: the first sentence is spoken while the rest is still arriving."""
    voice = ScriptedVoice()
    delivery = a_delivery(store, voice)

    delivery.feed("Evening, my lord. ")
    assert voice.started.wait(timeout=5), "the voice was given the first sentence at once"
    delivery.feed("The rest of the answer follows, and it is long enough to matter here.")
    delivery.finish()

    assert voice.spoken[0] == "Evening, my lord."
    assert len(voice.spoken) >= 2


def test_text_core_withheld_stops_speech_rather_than_being_spoken(store: Engine) -> None:
    """A verdict marker in the speech stream is a boundary failure, not a filter job."""
    voice = ScriptedVoice()
    delivery = a_delivery(store, voice)
    delivery.feed("Certainly, my lord. ")
    delivery.feed(f"{RECONCILIATION_VERDICT_MARKER}\n" + json.dumps({"outcome": "held"}))

    assert delivery.state is DeliveryState.FAILED
    assert delivery.reason is not None and "must never be spoken" in delivery.reason
    assert all(RECONCILIATION_VERDICT_MARKER not in said for said in voice.spoken)


@pytest.mark.parametrize("hidden", ["<|channel|>", "<think>", "</think>"])
def test_hidden_reasoning_never_reaches_the_voice(store: Engine, hidden: str) -> None:
    voice = ScriptedVoice()
    delivery = a_delivery(store, voice)
    delivery.feed(f"Well, my lord. {hidden} the hidden part")
    assert delivery.state is DeliveryState.FAILED
    assert all(hidden not in said for said in voice.spoken)


# =============================================================================
# §8-§10. The established voice, and audio that does not survive
# =============================================================================


def test_only_the_established_voice_is_used_and_voice_design_never_runs(
    store: Engine,
) -> None:
    voice = ScriptedVoice()
    delivery = a_delivery(store, voice)
    deliver(delivery, "The work is finished, my lord.")
    assert delivery._voice.name == "val-established-v1"
    assert delivery._voice.reference_sha256 == digest_of(REFERENCE)


def test_no_cloud_voice_and_no_voice_design_is_reachable_from_delivery() -> None:
    """Structural, with comments and docstrings stripped first."""
    import inspect
    import io
    import tokenize

    from val_gateway import delivery as delivery_module

    code = "".join(
        token.string
        for token in tokenize.generate_tokens(
            io.StringIO(inspect.getsource(delivery_module)).readline
        )
        if token.type not in (tokenize.COMMENT, tokenize.STRING)
    ).lower()
    for forbidden in (
        "eleven",
        "http://",
        "https://",
        "requests",
        "urllib",
        "httpx",
        "azure",
        "polly",
        "voicedesign",
        "voice_design",
    ):
        assert forbidden not in code, f"{forbidden!r} must not appear in executable code"


def test_the_sink_writes_nothing_to_disk_and_holds_nothing_afterwards() -> None:
    """Live speech is generated, delivered and released — that is the whole of it."""
    import inspect
    import io
    import tokenize

    from val_gateway import delivery as delivery_module

    code = "".join(
        token.string
        for token in tokenize.generate_tokens(
            io.StringIO(inspect.getsource(delivery_module)).readline
        )
        if token.type not in (tokenize.COMMENT, tokenize.STRING)
    )
    for forbidden in (
        "write_bytes",
        "write_text",
        "NamedTemporaryFile",
        "mkdtemp",
        "wave",
        "open(",
    ):
        assert forbidden not in code, f"{forbidden} must not appear: live audio is never written"


def test_the_sink_holds_one_piece_at_a_time_and_lets_go_at_the_end(store: Engine) -> None:
    voice = ScriptedVoice()
    sink = EphemeralSink()
    delivery = a_delivery(store, voice, sink=sink)
    deliver(delivery, ANSWER)

    assert sink.segments_played >= 2
    assert sink.holding_bytes == 0, "nothing is held once delivery has finished"
    assert sink.finished is True


def test_a_spoken_segment_is_recorded_with_no_path_and_no_bytes(store: Engine) -> None:
    """The durable audit: text, ordering, digests, timings. Never a waveform."""
    conversation = a_conversation(store)
    message_id = _a_val_message(store, conversation, ANSWER)
    register_the_voice(store, a_voice())
    voice = ScriptedVoice()
    delivery = a_delivery(store, voice)
    deliver(delivery, ANSWER)
    delivery.bind(message_id)
    written = delivery.record_segments()

    assert written == len(delivery.spoken)
    with store.connect() as connection:
        rows = connection.execute(
            text(
                "select segment_index, segment_reason, final_text, audio_path, "
                "       audio_retained, audio_sha256, audio_bytes, cost_usd, local "
                "  from speech_generations where message_id = :id order by segment_index"
            ),
            {"id": message_id},
        ).all()
    assert [row.segment_index for row in rows] == list(range(1, written + 1))
    assert all(row.audio_path is None for row in rows), "no path to a file that never existed"
    assert all(row.audio_retained is False for row in rows), "and the row says so"
    assert all(len(row.audio_sha256) == 64 for row in rows), "the digest survives the bytes"
    assert all(row.audio_bytes > 0 and row.local and row.cost_usd == 0 for row in rows)
    assert "".join("".join(row.final_text.split()) for row in rows) == "".join(ANSWER.split())


def test_the_store_refuses_a_row_that_claims_a_file_it_does_not_have(
    store: Engine,
) -> None:
    """`audio_retained` and `audio_path` cannot disagree. Held by the database."""
    conversation = a_conversation(store)
    message_id = _a_val_message(store, conversation, "Anything.")
    voice_id = register_the_voice(store, a_voice())
    with pytest.raises(Exception, match="retained_names_its_file"):
        with store.begin() as connection:
            connection.execute(
                text(
                    "insert into speech_generations "
                    "  (voice_id, message_id, model_config_id, final_text, final_text_sha256, "
                    "   provider, model_identifier, model_revision, quantization, runtime, "
                    "   runtime_version, generation, clone_prompt_sha256, audio_sha256, "
                    "   audio_path, audio_retained, audio_bytes, sample_rate, "
                    "   duration_seconds, local, cost_usd, elapsed_ms) "
                    "values (:voice, :message, :config, 't', :d, 'mlxaudio', 'm', 'r', 'q', "
                    "        'mlx-audio', '0', '{}'::jsonb, :d, :d, "
                    "        '/tmp/not-really-there.wav', false, 1, 24000, 1, true, 0, 1)"
                ),
                {
                    "voice": voice_id,
                    "message": message_id,
                    "config": speech_configuration().id,
                    "d": "d" * 64,
                },
            )


# =============================================================================
# §11-§12. Delivery state, and the boundary at the first audio
# =============================================================================


def test_the_five_delivery_states_are_distinct_and_append_only(store: Engine) -> None:
    conversation = a_conversation(store)
    message_id = _a_val_message(store, conversation, ANSWER)
    voice = ScriptedVoice()
    delivery = a_delivery(store, voice)
    deliver(delivery, ANSWER)
    delivery.bind(message_id)

    found = delivery_for(store, message_id)
    assert found is not None
    assert found.state is DeliveryState.COMPLETED
    assert found.events >= 2, "started, then completed — each its own row"
    assert found.delivered_characters == len(found.delivered_prefix)
    assert found.segments_total == len(delivery.segmenter.segments)

    with pytest.raises(Exception, match=r"evidence|UPDATE"):
        with store.begin() as connection:
            connection.execute(text("update speech_deliveries set state = 'completed'"))
    with pytest.raises(Exception, match=r"delete|DELETE|hard"):
        with store.begin() as connection:
            connection.execute(text("delete from speech_deliveries"))


def test_the_delivered_boundary_is_the_first_audio_not_the_last(store: Engine) -> None:
    """He has begun to hear her the moment the first piece reaches the sink."""
    voice = ScriptedVoice()
    voice.release = threading.Event()
    delivery = a_delivery(store, voice)
    delivery.feed("Evening, my lord. ")
    assert voice.started.wait(timeout=5)
    assert delivery.audible is False, "the first piece has not been handed over yet"

    voice.release.set()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not delivery.audible:
        time.sleep(0.01)
    assert delivery.audible is True, "and now it has"
    assert delivery.state is DeliveryState.STARTED
    assert delivery.active is True, "still speaking, so owner speech now is barge-in"
    delivery.feed("The rest follows, at some length, so there is more to say after this.")
    delivery.finish()
    assert delivery.state is DeliveryState.COMPLETED


def test_an_answer_that_was_never_spoken_says_not_started(store: Engine) -> None:
    conversation = a_conversation(store)
    message_id = _a_val_message(store, conversation, "   ")
    voice = ScriptedVoice()
    delivery = a_delivery(store, voice)
    delivery.feed("   ")
    delivery.finish()
    delivery.bind(message_id)

    assert voice.spoken == [], "nothing was handed to the voice"
    found = delivery_for(store, message_id)
    assert found is not None
    assert found.state is DeliveryState.NOT_STARTED
    assert found.delivered_characters == 0 and found.segments_delivered == 0


def test_a_voice_failure_is_recorded_as_failed_and_the_text_still_stands(
    store: Engine,
) -> None:
    conversation = a_conversation(store)
    message_id = _a_val_message(store, conversation, ANSWER)
    voice = ScriptedVoice(fails_on=1)
    delivery = a_delivery(store, voice)
    deliver(delivery, ANSWER)
    delivery.bind(message_id)

    assert delivery.state is DeliveryState.FAILED
    found = delivery_for(store, message_id)
    assert found is not None and found.state is DeliveryState.FAILED
    assert found.reason is not None and "could not speak" in found.reason
    with store.connect() as connection:
        content = connection.execute(
            text("select content from messages where id = :id"), {"id": message_id}
        ).scalar_one()
    assert content == ANSWER, "the words stand; they were simply not spoken"


# =============================================================================
# §13. Barge-in
# =============================================================================


def test_barge_in_stops_delivery_and_keeps_the_exact_heard_prefix(store: Engine) -> None:
    conversation = a_conversation(store)
    message_id = _a_val_message(store, conversation, ANSWER)
    voice = ScriptedVoice()
    delivery = a_delivery(store, voice)

    delivery.feed("Evening, my lord. The two readers disagree. ")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and delivery.segments_delivered < 1:
        time.sleep(0.01)
    heard = delivery.delivered_prefix
    assert heard, "something had been spoken before he cut in"

    elapsed = delivery.interrupt("the owner began speaking")
    delivery.bind(message_id)

    assert delivery.state is DeliveryState.INTERRUPTED
    assert delivery.delivered_prefix == heard, "the prefix is exactly what he heard"
    assert heard in ANSWER.replace("  ", " ") or all(piece in ANSWER for piece in heard.split(". "))
    found = delivery_for(store, message_id)
    assert found is not None
    assert found.state is DeliveryState.INTERRUPTED
    assert found.reason == "the owner began speaking"
    assert found.delivered_prefix == heard
    assert found.delivered_characters == len(heard)
    assert elapsed >= 0


def test_barge_in_discards_what_was_queued_and_speaks_no_more(store: Engine) -> None:
    """She stops. She does not finish the sentence she was about to start."""
    voice = ScriptedVoice()
    voice.release = threading.Event()
    delivery = a_delivery(store, voice)
    delivery.feed(ANSWER)
    assert voice.started.wait(timeout=5), "the first segment is in the voice"
    queued = len(delivery.segmenter.segments)
    assert queued >= 2, "and more were waiting behind it"

    delivery.interrupt("the owner began speaking")
    voice.release.set()
    time.sleep(0.3)

    assert len(voice.spoken) <= 1, "nothing queued behind the interruption was spoken"
    assert delivery.sink.stopped_because == "the owner began speaking"
    assert delivery.sink.holding_bytes == 0, "and the sink let go of what it held"


def test_the_service_side_cancellation_is_within_the_target(store: Engine) -> None:
    """§13.1, and what it is **not**.

    This measures the signal reaching delivery control and the sink stopping. It
    is not a claim about when a physical Mac speaker falls silent — that needs the
    speakers, and belongs to work package 3.
    """
    voice = ScriptedVoice()
    delivery = a_delivery(store, voice)
    delivery.feed(ANSWER)
    time.sleep(0.05)
    elapsed = delivery.interrupt("the owner began speaking")
    assert elapsed <= CANCELLATION_TARGET_MS, f"{elapsed:.1f} ms exceeds the service-side target"
    assert delivery.cancellation_ms == elapsed


def test_the_recognizer_hearing_him_interrupts_her_by_itself(store: Engine) -> None:
    """The session wires barge-in without anyone having to ask for it.

    The voice is held mid-segment so delivery is genuinely live when the
    recognizer reports him speaking — which is the only moment barge-in means
    anything. Nothing about the timing is guessed at: the test waits for the
    voice to be in hand, cuts in, and then lets it go.
    """
    conversation = a_conversation(store)
    voice = ScriptedVoice()
    voice.release = threading.Event()
    deliveries: list[SpeechDelivery] = []

    def make() -> SpeechDelivery:
        built = a_delivery(store, voice)
        deliveries.append(built)
        return built

    recognizer = ScriptedRecognizer(
        batches=[
            [started(1), final(1, "What do you make of it?")],
            # He starts speaking again while she is still answering.
            [started(2)],
        ]
    )
    session, _, clock = _a_speaking_session(store, recognizer, conversation, make)

    session.feed(MARKER)
    clock.tick(RESUME_GRACE_SECONDS + 0.1)
    settling = threading.Thread(target=lambda: session.await_turn(timeout=60.0), daemon=True)
    settling.start()

    assert voice.started.wait(timeout=30), "the voice has the first segment in hand"
    assert deliveries, "delivery exists and is live"
    assert deliveries[0].active is True

    session.feed(MARKER)  # the recognizer reports speech_start — barge-in
    session.advance()
    voice.release.set()
    settling.join(timeout=60)

    assert deliveries[0].state is DeliveryState.INTERRUPTED
    assert session.cancellations, "the session recorded the cancellation interval"
    assert session.cancellations[0] <= CANCELLATION_TARGET_MS
    assert len(voice.spoken) <= 1, "she did not carry on after he cut in"


def test_playback_audio_is_never_reintroduced_as_owner_speech(store: Engine) -> None:
    """§14, and only what §14 permits claiming.

    The logical proof: what the sink holds is audio *leaving*, and there is no
    path from it into the recognizer's PCM input — the sink has no reference to a
    recognizer and the session never feeds it back. **No claim is made about room
    acoustics**; that needs the speakers and the microphone, in work package 3.
    """
    # Executable code only: the class's own docstring explains the prohibition, and
    # a scan that matched prose would be matching the explanation.
    import inspect
    import io
    import tokenize

    from val_gateway import delivery as delivery_module
    from val_gateway import voice as voice_module

    sink_code = "".join(
        token.string
        for token in tokenize.generate_tokens(
            io.StringIO(inspect.getsource(delivery_module.EphemeralSink)).readline
        )
        if token.type not in (tokenize.COMMENT, tokenize.STRING)
    )
    assert "feed" not in sink_code, "the sink cannot hand anything to a recognizer"
    assert "recognizer" not in sink_code.lower()

    session_source = inspect.getsource(voice_module.VoiceSession)
    # The only thing fed to the recognizer is the caller's PCM, and it comes from
    # the session's own `feed` parameter — never from a sink, a segment or audio.
    assert "_recognizer.feed(pcm)" in session_source
    assert session_source.count("_recognizer.feed(") == 1
    for forbidden in ("_recognizer.feed(segment", "_recognizer.feed(audio", "sink"):
        assert f"_recognizer.feed({forbidden}" not in session_source


def test_an_interruption_undoes_nothing_that_already_happened(store: Engine) -> None:
    """Speech stopping is not a time machine."""
    conversation = a_conversation(store)
    message_id = _a_val_message(store, conversation, ANSWER)
    with store.begin() as connection:
        connection.execute(
            text(
                "insert into execution_events (conversation_id, message_id, subject, "
                "  reason, reason_source, event_type) "
                "values (:c, :m, 'the barn booking', 'he asked for it', 'stated', 'accepted')"
            ),
            {"c": conversation, "m": message_id},
        )
    voice = ScriptedVoice()
    delivery = a_delivery(store, voice)
    delivery.feed(ANSWER)
    time.sleep(0.2)
    delivery.interrupt("the owner began speaking")
    delivery.bind(message_id)

    with store.connect() as connection:
        events = connection.execute(
            text("select count(*) from execution_events where message_id = :m"),
            {"m": message_id},
        ).scalar_one()
    assert events == 1, "the recorded consequential act stands, interruption or not"


# =============================================================================
# §11. The next turn does not assume he heard the rest
# =============================================================================


def test_the_next_turn_is_told_how_much_of_the_last_answer_he_heard(
    store: Engine,
) -> None:
    conversation = a_conversation(store)
    _a_user_message(store, conversation, "What do you make of it?")
    message_id = _a_val_message(store, conversation, ANSWER)
    voice = ScriptedVoice()
    delivery = a_delivery(store, voice)
    delivery.feed(ANSWER)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and delivery.segments_delivered < 1:
        time.sleep(0.01)
    heard = delivery.delivered_prefix
    delivery.interrupt("the owner began speaking")
    delivery.bind(message_id)

    (short,) = short_deliveries(store, conversation)
    assert short.message_id == message_id
    assert short.state is DeliveryState.INTERRUPTED
    assert short.delivered_characters == len(heard)
    assert short.total_characters == len(ANSWER)
    assert short.delivered_characters < short.total_characters, "he did not hear all of it"


def test_a_fully_heard_answer_says_nothing_in_the_envelope(store: Engine) -> None:
    """A field restating 'he heard everything' on every turn would be noise."""
    conversation = a_conversation(store)
    message_id = _a_val_message(store, conversation, ANSWER)
    voice = ScriptedVoice()
    delivery = a_delivery(store, voice)
    deliver(delivery, ANSWER)
    delivery.bind(message_id)

    assert short_deliveries(store, conversation) == ()


def test_the_envelope_names_the_unheard_answer_and_tells_val_what_it_means(
    store: Engine,
) -> None:
    from val_gateway.context import SPOKEN_DELIVERY_NOTE, PriorRecordState

    state = PriorRecordState(
        history_state="available",
        history_prior_messages=2,
        history_retained_messages=2,
        retrieval_state="not_run",
        retrieval_excerpts=0,
        spoken_delivery=(
            __import__("val_gateway.context", fromlist=["ShortSpokenAnswer"]).ShortSpokenAnswer(
                answer_position=2,
                state="interrupted",
                heard_characters=17,
                generated_characters=len(ANSWER),
                reason="the owner began speaking",
            ),
        ),
    )
    document = state.as_document()
    spoken = document["spoken_delivery"]
    assert isinstance(spoken, dict)
    assert spoken["note"] == SPOKEN_DELIVERY_NOTE
    assert "Do not assume he knows the part he did not hear" in SPOKEN_DELIVERY_NOTE
    assert spoken["answers"][0]["heard_characters"] == 17
    assert spoken["answers"][0]["generated_characters"] == len(ANSWER)

    quiet = PriorRecordState(
        history_state="zero",
        history_prior_messages=0,
        history_retained_messages=0,
        retrieval_state="not_run",
        retrieval_excerpts=0,
    )
    assert "spoken_delivery" not in quiet.as_document()


# --- helpers ----------------------------------------------------------------------------


def _a_user_message(engine: Engine, conversation: UUID, content: str) -> UUID:
    from val_domain.conversation import StoredRole
    from val_gateway import conversations as conv

    return conv.append(engine, conversation, role=StoredRole.USER, content=content).id


def _a_val_message(engine: Engine, conversation: UUID, content: str) -> UUID:
    from val_domain.conversation import StoredRole
    from val_gateway import conversations as conv

    return conv.append(engine, conversation, role=StoredRole.VAL, content=content).id


def _a_speaking_session(
    engine: Engine,
    recognizer: ScriptedRecognizer,
    conversation: UUID,
    speech: Callable[[], SpeechDelivery],
) -> tuple[VoiceSession, ScriptedAdapter, Clock]:
    adapter = ScriptedAdapter([ok(ANSWER)])
    clock = Clock()

    def submit(
        content: str,
        existing: UUID | None,
        *,
        on_delta: Callable[[str], None] | None = None,
        merged: bool = False,
        on_persisted: Callable[[UUID, UUID], None] | None = None,
    ) -> DeliberatedOutcome:
        # Mirrors the service's own voice door exactly (owner ruling, 24 September
        # 2026, Voice work package 3 §1.5): a spoken turn is submitted `spoken`,
        # which seals its conversation in the same transaction as the message and
        # takes the classifier and strip calls off the path. A double that omitted
        # it would be testing a voice turn the application no longer performs.
        return deliberated_send(
            engine,
            build_gateway(engine, adapter),
            content,
            catalogue=__import__(
                "val_gateway.projects", fromlist=["load_catalogue"]
            ).load_catalogue(engine),
            signals=None
            if existing is not None
            else ProjectSignals(explicit_selection="Project Alpha"),
            conversation_id=existing,
            on_delta=on_delta,
            on_persisted=on_persisted,
            spoken=True,
            seal_route=SealRoute.RESUME_MERGE if merged else SealRoute.UTTERANCE_FINALIZED,
        )

    session = VoiceSession(
        engine,
        recognizer,
        submit=submit,
        conversation_id=conversation,
        clock=clock,
        speech=speech,
    )
    session.start()
    return session, adapter, clock


# =============================================================================
# The progressive invariant, after owner acceptance Step B
# =============================================================================


def test_the_first_segment_is_synthesised_before_the_answer_is_finished(
    store: Engine,
) -> None:
    """§9.1. Speech must not wait for the whole answer — proved from the record.

    Owner acceptance, 24 September 2026: he could read the complete reply before Val
    began to speak it, and described the result as delayed read-aloud. The question
    that settles whether the pipeline is progressive is narrow — **did synthesis of
    segment 1 begin before cognition finished?** — and until now nothing recorded it,
    so it could only be argued from the code.

    Here a stream arrives in pieces with a complete sentence early, and the assertion
    is against the two marks the delivery now keeps.
    """
    voice_provider = ScriptedVoice()
    register_the_voice(store, a_voice())
    delivery = a_delivery(store, voice_provider)

    # A complete first sentence, then a long tail still being written.
    delivery.feed("Good evening, my lord. ")
    # The synthesis worker takes the first segment while the rest is still arriving.
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and delivery.first_tts_start_ms is None:
        time.sleep(0.01)
    assert delivery.first_tts_start_ms is not None, "segment 1 was never synthesised"
    assert delivery.cognition_complete_ms is None, (
        "synthesis began while Core was still writing, which is the invariant"
    )

    delivery.feed("The two readers disagree because they are answering different questions.")
    delivery.finish(
        "Good evening, my lord. The two readers disagree because they are answering "
        "different questions."
    )

    assert delivery.cognition_complete_ms is not None
    assert delivery.first_segment_began_before_the_answer_was_finished is True, (
        "the first segment's synthesis must start before the answer is complete"
    )
    assert delivery.first_tts_start_ms < delivery.cognition_complete_ms


def test_the_progressive_boundary_is_absent_rather_than_false_when_unmeasured(
    store: Engine,
) -> None:
    """An interval with one end is not an interval, and must not read as a failure."""
    voice_provider = ScriptedVoice()
    register_the_voice(store, a_voice())
    delivery = a_delivery(store, voice_provider)
    assert delivery.first_segment_began_before_the_answer_was_finished is None
    delivery.feed("Good evening, my lord. ")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and delivery.first_tts_start_ms is None:
        time.sleep(0.01)
    # One end only: still None, never False.
    assert delivery.first_segment_began_before_the_answer_was_finished is None


def test_a_route_that_cannot_stream_still_speaks_and_says_so_in_the_record(
    store: Engine,
) -> None:
    """The honest case: no delta arrived, so nothing was progressive — and it shows.

    Work package 2's rule is unchanged: a route that cannot stream still speaks, from
    the persisted answer. What this adds is that the record distinguishes it from a
    progressive delivery rather than letting both look alike.
    """
    voice_provider = ScriptedVoice()
    register_the_voice(store, a_voice())
    delivery = a_delivery(store, voice_provider)

    delivery.finish("Good evening, my lord.")  # no deltas at all

    assert delivery.cognition_complete_ms is not None
    assert delivery.first_tts_start_ms is not None
    assert delivery.first_segment_began_before_the_answer_was_finished is False, (
        "a non-streaming route is read-aloud, and the record says so plainly"
    )
