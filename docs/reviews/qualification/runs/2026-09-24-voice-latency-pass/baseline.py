"""Production-shaped latency baseline — latency pass §8, §9 and §11.

Three identical trials through the real composition root, with the diagnostic
recorder installed so every named boundary is a directly observed mark rather
than a subtraction. Frozen PCM fixture, real whisper.cpp, real Silero, real
ordinary Core turn, real production classification, production MEDIUM GPT-OSS,
the exact segmenter, `val-established-v1`, Qwen3-TTS, ephemeral in-memory sink.

Scratch store: no proof writes into Lord Armand's conversation history.

Usage: baseline.py OUT.json [TRIALS]
"""

import json
import os
import plistlib
import sys
import threading
import time
import wave
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as f:
    _env = plistlib.load(f)["EnvironmentVariables"]
for _name, _value in _env.items():
    if _name != "VAL_DATABASE_URL":
        os.environ[_name] = _value

ROOT = Path("/Users/josepharmand/Projects/val")
HERE = Path(__file__).resolve().parent
URL = "postgresql+psycopg://localhost:5433/val_test"
os.environ["VAL_DATABASE_URL"] = URL
FIXTURE = ROOT / "infrastructure/voice/fixtures/frozen-utterance.wav"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "baseline.json"
TRIALS = int(sys.argv[2]) if len(sys.argv) > 2 else 3

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from val_domain import timings
from val_domain.gateway import CapabilityProfile
from val_domain.registry import active
from val_gateway.deliberate import send as deliberated_send
from val_gateway.delivery import SpeechDelivery, delivery_for
from val_gateway.persona import seed
from val_gateway.projects import load_catalogue
from val_gateway.speech import register_voice
from val_gateway.startup import start
from val_gateway.voice import VoiceSession
from val_policy.project_resolution import ProjectSignals

engine = create_engine(URL)
with engine.begin() as c:
    c.execute(text("DROP SCHEMA public CASCADE"))
    c.execute(text("CREATE SCHEMA public"))
cfg = Config(str(ROOT / "alembic.ini"))
cfg.set_main_option("script_location", str(ROOT / "packages/domain/migrations"))
cfg.set_main_option("sqlalchemy.url", URL)
command.upgrade(cfg, "head")
engine.dispose()
engine = create_engine(URL)
seed(engine, ROOT)
with engine.begin() as c:
    c.execute(
        text(
            "insert into projects (name, slug, description, status) "
            "values ('Latency Pass', 'latency-pass', '', 'active')"
        )
    )

started_house = start(engine)
gateway = started_house.gateway
assert started_house.recognizers is not None
assert gateway.speech is not None and gateway.voice is not None
speech_config = next(c for c in active() if CapabilityProfile.SPEECH in c.capability_profiles)
register_voice(
    engine,
    gateway.voice,
    described={
        "reference_sample_rate": 24000,
        "reference_duration_seconds": 18.756,
        "designed_by_quantization": "8-bit MLX, group size 64, affine",
        "designed_by_runtime": "mlx-audio 0.5.5",
        "designed_generation": {},
        "origin": "Owner-authorised established voice reference (23 September 2026).",
        "identity_claim": "Not model-verified. The owner's listening judgement governs.",
    },
)

with wave.open(str(FIXTURE)) as reader:
    pcm = reader.readframes(reader.getnframes())
BLOCK = 320 * 2
SILENCE = b"\x00\x00" * 320

report: dict[str, object] = {
    "measurement": "production-shaped voice latency baseline",
    "order": "pre-WP3 latency pass §8, §9, §11 — owner execution order 24 September 2026",
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "trials": TRIALS,
    "fixture": str(FIXTURE.relative_to(ROOT)),
    "startup_warnings": started_house.warnings,
    "runs": [],
}


def one_trial(index: int) -> dict:
    deliveries: list[SpeechDelivery] = []

    def make_delivery() -> SpeechDelivery:
        built = SpeechDelivery(
            engine, speech=gateway.speech, voice=gateway.voice, configuration=speech_config
        )
        deliveries.append(built)
        return built

    def submit(content, conversation_id, *, on_delta=None):
        return deliberated_send(
            engine,
            gateway,
            content,
            catalogue=load_catalogue(engine),
            signals=None
            if conversation_id is not None
            else ProjectSignals(explicit_selection="Latency Pass"),
            conversation_id=conversation_id,
            on_delta=on_delta,
        )

    recognizer = started_house.recognizers()
    session = VoiceSession(
        engine,
        recognizer,
        submit=submit,
        speech=make_delivery,
        # Latency pass §12: the cognition runtime comes up while he is speaking.
        warm=gateway.warm_cognition,
    )
    session.start()

    with timings.recording() as recorder:
        speech_started = time.monotonic()
        for offset in range(0, len(pcm), BLOCK):
            session.feed(pcm[offset : offset + BLOCK])
        for _ in range(50):
            session.feed(SILENCE)
        input_ended = time.monotonic()
        recorder.mark("input_fixture_speech_end")

        deadline = time.monotonic() + 180
        while time.monotonic() < deadline and not session.snapshot().turns:
            session.advance()
            if session.snapshot().pending or session.delivery is not None:
                break
            time.sleep(0.02)
        session.await_turn(timeout=600)
        marks = recorder.as_record()
        spans = {
            "input_speech_end_to_turn_start": recorder.span(
                "input_fixture_speech_end", "turn_start"
            ),
            "turn_start_to_message_persisted": recorder.span(
                "turn_start", "message_persisted"
            ),
            "turn_start_to_classification_start": recorder.span(
                "turn_start", "classification_start"
            ),
            "classification_duration": recorder.span(
                "classification_start", "classification_end"
            ),
            "classification_end_to_assembly_start": recorder.span(
                "classification_end", "assembly_start"
            ),
            "assembly_duration": recorder.span("assembly_start", "assembly_end"),
            "assembly_end_to_runtime_ready_start": recorder.span(
                "assembly_end", "runtime_ready_start"
            ),
            "runtime_ready_duration": recorder.span(
                "runtime_ready_start", "runtime_ready_end"
            ),
            "exact_preflight_duration": recorder.span(
                "exact_preflight_start", "exact_preflight_end"
            ),
            "preflight_end_to_provider_dispatch": recorder.span(
                "exact_preflight_end", "provider_dispatch"
            ),
            "provider_dispatch_to_first_chunk": recorder.span(
                "provider_dispatch", "provider_chunk"
            ),
            "first_chunk_to_first_visible_text": recorder.span(
                "provider_chunk", "provider_visible_text"
            ),
            "first_visible_text_to_segment_queued": recorder.span(
                "provider_visible_text", "speech_segment_queued"
            ),
            "segment_queued_to_tts_start": recorder.span(
                "speech_segment_queued", "tts_synthesize_start"
            ),
            "tts_synthesize_duration": recorder.span(
                "tts_synthesize_start", "tts_synthesize_return"
            ),
            "tts_return_to_audio_at_sink": recorder.span(
                "tts_synthesize_return", "audio_at_sink"
            ),
        }
        at = {
            name: recorder.first(name)
            for name in (
                "input_fixture_speech_end",
                "transcript_final",
                "owner_turn_submitted",
                "turn_start",
                "message_persisted",
                "classification_start",
                "classification_end",
                "assembly_start",
                "assembly_end",
                "runtime_ready_start",
                "runtime_ready_end",
                "exact_preflight_start",
                "exact_preflight_end",
                "provider_dispatch",
                "provider_chunk",
                "provider_visible_text",
                "speech_first_visible_text",
                "speech_segment_queued",
                "tts_synthesize_start",
                "tts_synthesize_return",
                "audio_at_sink",
            )
        }
        counts = {
            name: recorder.count(name)
            for name in (
                "provider_dispatch",
                "exact_preflight_start",
                "runtime_ready_start",
                "classification_start",
                "speech_segment_queued",
                "tts_synthesize_start",
                "audio_at_sink",
            )
        }

    view = session.snapshot()
    turn = view.turns[0] if view.turns else None
    first = deliveries[0] if deliveries else None
    session.close("the baseline trial is finished")
    with engine.connect() as c:
        val_text = c.execute(
            text(
                "select content from messages where role = 'val' order by created_at desc limit 1"
            )
        ).scalar()
        calls = c.execute(
            text(
                "select provider, task_type, cost, latency_ms from model_calls "
                "order by created_at desc limit 4"
            )
        ).mappings().all()
    record = delivery_for(engine, first.message_id) if first and first.message_id else None
    return {
        "trial": index,
        "owner_transcript": None if turn is None else turn.utterance.text,
        "val_characters": len(val_text or ""),
        "segments": [] if first is None else [s.text for s in first.spoken],
        "delivery_state": None if first is None else first.state.value,
        "delivery_record": None if record is None else record.state.value,
        "warmed": session.warmed,
        "at_seconds": {k: (None if v is None else round(v, 3)) for k, v in at.items()},
        "spans_seconds": {k: (None if v is None else round(v, 3)) for k, v in spans.items()},
        "mark_counts": counts,
        "end_of_speech_to_first_audio_s": (
            None
            if at["audio_at_sink"] is None or at["input_fixture_speech_end"] is None
            else round(at["audio_at_sink"] - at["input_fixture_speech_end"], 3)
        ),
        "first_visible_text_to_first_audio_s": (
            None
            if at["audio_at_sink"] is None or at["provider_visible_text"] is None
            else round(at["audio_at_sink"] - at["provider_visible_text"], 3)
        ),
        "model_calls": [dict(c) for c in calls],
        "all_marks": marks,
    }


for index in range(1, TRIALS + 1):
    print(f"=== trial {index} ===", flush=True)
    result = one_trial(index)
    report["runs"].append(result)
    print(json.dumps(result["spans_seconds"], indent=1), flush=True)
    print("end of speech -> first audio:", result["end_of_speech_to_first_audio_s"], "s", flush=True)


def median(values: list[float]) -> float | None:
    clean = sorted(v for v in values if v is not None)
    return None if not clean else clean[len(clean) // 2]


keys = report["runs"][0]["spans_seconds"].keys()
report["medians"] = {
    k: median([r["spans_seconds"][k] for r in report["runs"]]) for k in keys
}
report["medians"]["end_of_speech_to_first_audio_s"] = median(
    [r["end_of_speech_to_first_audio_s"] for r in report["runs"]]
)
report["medians"]["first_visible_text_to_first_audio_s"] = median(
    [r["first_visible_text_to_first_audio_s"] for r in report["runs"]]
)
with engine.connect() as c:
    report["total_provider_cost_usd"] = float(
        c.execute(text("select coalesce(sum(cost), 0) from model_calls")).scalar_one()
    )
OUT.write_text(json.dumps(report, indent=1, default=str))
print("\n=== medians ===")
print(json.dumps(report["medians"], indent=1))
print("cost:", report["total_provider_cost_usd"])
print("written:", OUT)
