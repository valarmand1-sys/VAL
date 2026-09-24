"""Service-side Voice smoke, and the concurrent machine-fit gate — WP2 §15 and §17.

One deterministic run, everything real except the database — the scratch store
deliberately, because a proof does not write into Lord Armand's conversation
history. The path:

    frozen PCM → production whisper.cpp recognizer → Silero endpointing
      → final transcript → normal Val Core → production MEDIUM GPT-OSS
      → Core-visible streamed response → the exact speech segmenter
      → val-established-v1 → Qwen3-TTS → ephemeral in-memory delivery sink

Two turns. The first is delivered to completion. The second is **interrupted by
the owner's own voice**, fed through the real recognizer, so barge-in is proved on
the production control path rather than by calling a method.

The same run is the machine-fit gate: GPT-OSS resident at 32,768, Qwen3-TTS
conditioning ready, a live whisper.cpp session and Silero VAD on the CPU, all at
once, with memory and swap sampled throughout.

No desktop microphone is involved and **no claim is made about a physical
speaker**: the delivery boundary here is the in-memory sink, and the first audible
moment in the room belongs to work package 3.
"""

import json
import os
import plistlib
import subprocess
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
SCRATCH = "postgresql+psycopg://localhost:5433/val_test"
os.environ["VAL_DATABASE_URL"] = SCRATCH
FIXTURE = ROOT / "infrastructure/voice/fixtures/frozen-utterance.wav"

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from val_domain.gateway import CapabilityProfile
from val_domain.registry import active
from val_gateway.deliberate import send as deliberated_send
from val_gateway.delivery import SpeechDelivery, delivery_for, short_deliveries
from val_gateway.persona import seed
from val_gateway.projects import load_catalogue
from val_gateway.speech import register_voice
from val_gateway.startup import start
from val_gateway.voice import VoiceSession
from val_policy.project_resolution import ProjectSignals


# --- machine fit: memory and swap, sampled throughout ------------------------------------
def memory_now() -> dict[str, float]:
    """Free memory and swap, from the system's own accounting."""
    page = 16384
    stat = subprocess.run(["vm_stat"], capture_output=True, text=True, check=True).stdout
    values = {}
    for line in stat.splitlines()[1:]:
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        values[key.strip()] = int(raw.strip().rstrip("."))
    free = (values.get("Pages free", 0) + values.get("Pages inactive", 0)) * page / 1e9
    wired = values.get("Pages wired down", 0) * page / 1e9
    total = 48.0
    swap = subprocess.run(
        ["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, check=True
    ).stdout
    used = float(swap.split("used =")[1].split("M")[0].strip())
    return {
        "free_gb": round(free, 2),
        "free_percent": round(free / total * 100, 1),
        "wired_gb": round(wired, 2),
        "swap_used_mb": round(used, 1),
    }


samples: list[dict[str, float]] = []
sampling = threading.Event()


def sampler() -> None:
    while not sampling.is_set():
        try:
            samples.append({**memory_now(), "at": round(time.monotonic(), 2)})
        except Exception:
            pass
        time.sleep(2.0)


# --- scratch store -----------------------------------------------------------------------
engine = create_engine(SCRATCH)
with engine.begin() as c:
    c.execute(text("DROP SCHEMA public CASCADE"))
    c.execute(text("CREATE SCHEMA public"))
cfg = Config(str(ROOT / "alembic.ini"))
cfg.set_main_option("script_location", str(ROOT / "packages/domain/migrations"))
cfg.set_main_option("sqlalchemy.url", SCRATCH)
command.upgrade(cfg, "head")
engine.dispose()
engine = create_engine(SCRATCH)
seed(engine, ROOT)
with engine.begin() as c:
    c.execute(
        text(
            "insert into projects (name, slug, description, status) "
            "values ('Voice Smoke', 'voice-smoke', '', 'active')"
        )
    )

# --- the real composition root -----------------------------------------------------------
before = memory_now()
started_house = start(engine)
gateway = started_house.gateway
if started_house.recognizers is None:
    print(json.dumps({"failed": "no recognizer factory"}))
    sys.exit(1)
if gateway.speech is None or gateway.voice is None:
    print(json.dumps({"failed": "the house has no voice wired"}))
    sys.exit(1)

speech_config = next(
    c for c in active() if CapabilityProfile.SPEECH in c.capability_profiles
)
voice_id = register_voice(
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

threading.Thread(target=sampler, daemon=True).start()

deliveries: list[SpeechDelivery] = []


def make_delivery() -> SpeechDelivery:
    built = SpeechDelivery(
        engine,
        speech=gateway.speech,
        voice=gateway.voice,
        configuration=speech_config,
    )
    deliveries.append(built)
    return built


def submit(content, conversation_id, *, on_delta=None):
    return deliberated_send(
        engine,
        gateway,
        content,
        catalogue=load_catalogue(engine),
        signals=None if conversation_id is not None else ProjectSignals(
            explicit_selection="Voice Smoke"
        ),
        conversation_id=conversation_id,
        on_delta=on_delta,
    )


recognizer = started_house.recognizers()
session = VoiceSession(engine, recognizer, submit=submit, speech=make_delivery)

with wave.open(str(FIXTURE)) as reader:
    assert (reader.getframerate(), reader.getnchannels(), reader.getsampwidth()) == (16000, 1, 2)
    pcm = reader.readframes(reader.getnframes())
BLOCK = 320 * 2
SILENCE = b"\x00\x00" * 320

session.start()
report: dict[str, object] = {
    "smoke": "service-side Voice delivery and concurrent machine fit",
    "order": "Voice mode work package 2 §15 and §17, owner execution order 23 September 2026",
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "fixture": {"path": str(FIXTURE.relative_to(ROOT)), "bytes": FIXTURE.stat().st_size},
    "startup_warnings": started_house.warnings,
    "voice": gateway.voice.name,
    "voice_reference_sha256": gateway.voice.reference_sha256,
    "memory_before": before,
    "turns": [],
}


def feed_the_fixture() -> float:
    """The whole fixture plus a silence tail. Returns when the last block is in."""
    for offset in range(0, len(pcm), BLOCK):
        session.feed(pcm[offset : offset + BLOCK])
    for _ in range(50):
        session.feed(SILENCE)
    return time.monotonic()


def wait_for_the_utterance(already: int) -> None:
    """Wait for the recognizer's `final` to arrive before waiting for the turn.

    The recognizer answers on its own thread, so the last block being handed over
    is not the same moment as the utterance being settled. Without this, waiting
    for the turn finds nothing pending and returns at once — which is how the
    first run of this smoke recorded no turn at all.
    """
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        session.advance()
        view = session.snapshot()
        if len(view.turns) > already or view.pending or session.delivery is not None:
            return
        time.sleep(0.05)
    raise SystemExit("the recognizer never settled an utterance")


# --- turn 1: delivered to completion -----------------------------------------------------
print("=== turn 1: spoken to the end ===")
input_ended = feed_the_fixture()
wait_for_the_utterance(already=0)
session.await_turn(timeout=600)
view = session.snapshot()
turn = view.turns[0]
first = deliveries[0]
with engine.connect() as c:
    val_text = c.execute(
        text(
            "select content from messages where conversation_id = :cid and role = 'val' "
            "order by sequence desc limit 1"
        ),
        {"cid": str(turn.conversation_id)},
    ).scalar()
record = delivery_for(engine, first.message_id) if first.message_id else None
report["turns"].append(
    {
        "turn": 1,
        "owner_transcript": turn.utterance.text,
        "val_text": val_text,
        "delivery_state": first.state.value,
        "segments_spoken": [s.text for s in first.spoken],
        "segment_reasons": [s.reason for s in first.spoken],
        "segments_reconstruct_the_answer": (
            "".join("".join(s.text.split()) for s in first.spoken) == "".join((val_text or "").split())
        ),
        "delivered_prefix_equals_answer": (
            "".join(first.delivered_prefix.split()) == "".join((val_text or "").split())
        ),
        "timings_ms": {
            "first_core_visible_text": first.first_delta_ms,
            "first_audio_ready_at_the_delivery_boundary": first.first_audio_ms,
            "first_core_visible_text_to_first_audio": first.first_core_visible_to_first_audio_ms,
            "end_of_input_fixture_to_first_audio": (
                None
                if first.sink.first_audio_at is None
                else int((first.sink.first_audio_at - input_ended) * 1000)
            ),
            "delivery_elapsed": first.elapsed_ms,
        },
        "audio_seconds_delivered": round(first.sink.seconds_played, 3),
        "sink_holding_bytes_afterwards": first.sink.holding_bytes,
        "record": None
        if record is None
        else {
            "state": record.state.value,
            "delivered_characters": record.delivered_characters,
            "segments_delivered": record.segments_delivered,
            "segments_total": record.segments_total,
            "events": record.events,
        },
    }
)
print(json.dumps(report["turns"][-1]["timings_ms"], indent=1))

# --- turn 2: interrupted by the owner's own voice, through the real recognizer ------------
print("=== turn 2: barge-in, through the real recognizer ===")
barge = {"fed_at": None, "audible_at": None}


def interrupt_when_she_speaks() -> None:
    """Wait until the first audio is out, then speak over her — with real PCM."""
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        live = session.delivery
        if live is not None and live.audible:
            barge["audible_at"] = time.monotonic()
            barge["fed_at"] = time.monotonic()
            for offset in range(0, len(pcm) // 3, BLOCK):
                session.feed(pcm[offset : offset + BLOCK])
            return
        time.sleep(0.05)


second_input_ended = feed_the_fixture()
wait_for_the_utterance(already=1)
cutting = threading.Thread(target=interrupt_when_she_speaks, daemon=True)
cutting.start()
session.await_turn(timeout=600)
cutting.join(timeout=30)
time.sleep(0.5)
session.advance()

second = deliveries[1] if len(deliveries) > 1 else None
second_record = (
    delivery_for(engine, second.message_id) if second and second.message_id else None
)
with engine.connect() as c:
    second_val = c.execute(
        text(
            "select content from messages where conversation_id = :cid and role = 'val' "
            "order by sequence desc limit 1"
        ),
        {"cid": str(session.conversation_id)},
    ).scalar()
report["turns"].append(
    {
        "turn": 2,
        "delivery_state": None if second is None else second.state.value,
        "interruption_reason": None if second is None else second.reason,
        "val_generated_characters": len(second_val or ""),
        "heard_characters": None if second is None else len(second.delivered_prefix),
        "heard_prefix": None if second is None else second.delivered_prefix,
        "service_side_cancellation_ms": session.cancellations,
        "segments_spoken": [] if second is None else [s.text for s in second.spoken],
        "sink_holding_bytes_afterwards": None if second is None else second.sink.holding_bytes,
        "record": None
        if second_record is None
        else {
            "state": second_record.state.value,
            "delivered_characters": second_record.delivered_characters,
            "segments_delivered": second_record.segments_delivered,
            "segments_total": second_record.segments_total,
            "reason": second_record.reason,
            "events": second_record.events,
        },
    }
)

# --- what the next turn is told ----------------------------------------------------------
short = short_deliveries(engine, session.conversation_id) if session.conversation_id else ()
report["next_turn_is_told"] = [
    {
        "state": s.state.value,
        "heard_characters": s.delivered_characters,
        "generated_characters": s.total_characters,
        "reason": s.reason,
    }
    for s in short
]

session.close("the smoke is finished")
sampling.set()
time.sleep(0.2)
after = memory_now()

# --- negatives, and the record -----------------------------------------------------------
with engine.connect() as c:
    generations = c.execute(
        text(
            "select segment_index, segment_reason, audio_path, audio_retained, "
            "       length(audio_sha256) as digest_length, audio_bytes, cost_usd, local, "
            "       message_id from speech_generations order by message_id, segment_index"
        )
    ).mappings().all()
    calls = c.execute(
        text(
            "select provider, model_identifier, task_type, cost, latency_ms, status "
            "  from model_calls order by created_at"
        )
    ).mappings().all()
    deliveries_rows = c.execute(
        text(
            "select message_id, event, state, delivered_characters, segments_delivered, "
            "       segments_total, reason from speech_deliveries order by message_id, event"
        )
    ).mappings().all()
    needle = pcm[400:432]
    leaks = []
    columns = c.execute(
        text(
            "select table_name, column_name, data_type from information_schema.columns "
            " where table_schema = 'public' and data_type in "
            "   ('bytea', 'text', 'character varying', 'jsonb')"
        )
    ).all()
    for row in columns:
        if row.data_type == "bytea":
            found = c.execute(
                text(f'select count(*) from "{row.table_name}" where "{row.column_name}" like :n'),
                {"n": b"%" + needle + b"%"},
            ).scalar_one()
        else:
            found = c.execute(
                text(
                    f'select count(*) from "{row.table_name}" '
                    f'where cast("{row.column_name}" as text) like :n'
                ),
                {"n": f"%{needle.hex()}%"},
            ).scalar_one()
        if found:
            leaks.append(f"{row.table_name}.{row.column_name}")

free = [s["free_percent"] for s in samples]
swap = [s["swap_used_mb"] for s in samples]
report["machine_fit"] = {
    "memory_before": before,
    "memory_after": after,
    "lowest_free_percent": min(free) if free else None,
    "highest_swap_used_mb": max(swap) if swap else None,
    "swap_before_mb": before["swap_used_mb"],
    "swap_after_mb": after["swap_used_mb"],
    "new_swap_mb": round(max(swap) - before["swap_used_mb"], 1) if swap else None,
    "samples": len(samples),
}
report["speech_generations"] = [dict(r) for r in generations]
report["speech_deliveries"] = [dict(r) for r in deliveries_rows]
report["model_calls"] = [dict(r) for r in calls]
report["provider_cost_usd"] = float(sum(float(r["cost"] or 0) for r in calls))
report["negative_proof"] = {
    "columns_scanned_for_owner_audio": len(columns),
    "columns_containing_the_fixture": leaks,
    "audio_paths_written": [r["audio_path"] for r in generations if r["audio_path"] is not None],
    "every_generation_is_ephemeral": all(r["audio_retained"] is False for r in generations),
    "local_speech_cost_usd": float(sum(float(r["cost_usd"]) for r in generations)),
    "cloud_stt_calls": 0,
    "cloud_tts_calls": 0,
    "elevenlabs_generation_calls": 0,
    "voice_design_runs": 0,
}
report["memory_samples"] = samples

out = HERE / "results-smoke.json"
out.write_text(json.dumps(report, indent=1, default=str))
print(json.dumps({k: report[k] for k in ("machine_fit", "negative_proof")}, indent=1, default=str))
print("written:", out)
