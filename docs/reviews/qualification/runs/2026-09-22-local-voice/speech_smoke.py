"""One production speech smoke through the REAL application composition.

Nothing is injected: `val_gateway.startup.start` builds the gateway, wires the
adapters, wires both perception specialists, and wires the speech provider and
Val's governed voice. The text spoken is an ordinary completed Val response read
from the record, so what is spoken is provably what Val said.

Governed scratch store, so no manufactured history enters the owner's real
conversation record.

The negative proof matters more than the waveform: an answer that sounds right
is not evidence the local path produced it. So this records every process that
ran while the turn was in flight, every provider call in the interval, and the
cost of each.
"""

from __future__ import annotations

import json
import os
import plistlib
import subprocess
import threading
import time
from pathlib import Path
from uuid import UUID

os.environ["VAL_DATABASE_URL"] = os.environ["VAL_TEST_DATABASE_URL"]
_plist = plistlib.loads(
    (Path.home() / "Library/LaunchAgents/house.armand.val.api.plist").read_bytes()
)
for _name, _value in _plist["EnvironmentVariables"].items():
    os.environ.setdefault(_name, _value)
os.environ["VAL_DATABASE_URL"] = os.environ["VAL_TEST_DATABASE_URL"]

from sqlalchemy import create_engine, text  # noqa: E402

from val_domain.gateway import CapabilityProfile  # noqa: E402
from val_domain.registry import active, by_slug  # noqa: E402
from val_gateway.loop import Turn, send  # noqa: E402
from val_gateway.projects import load_catalogue  # noqa: E402
from val_gateway.speech import register_voice, speak_message  # noqa: E402
from val_gateway.startup import start  # noqa: E402
from val_policy.project_resolution import ProjectSignals  # noqa: E402
from val_policy.routing import is_admitted, satisfies_profile  # noqa: E402
from val_providers.lmstudio_adapter import DEFAULT_BASE_URL  # noqa: E402
from val_providers.lmstudio_runtime import LMStudioRuntime  # noqa: E402
from val_providers.qwen_tts_speech import VOICE_RECORD  # noqa: E402


class ProcessWatch:
    """Every process that ran while the run was in flight.

    Crude on purpose: the claim is a negative one — no cloud voice service, no
    transcription helper — and a sampler that names everything cannot be accused
    of looking only where it expected to find nothing.
    """

    def __init__(self) -> None:
        self.seen: set[str] = set()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            out = subprocess.run(
                ["/bin/ps", "-Ao", "comm"], capture_output=True, text=True, check=False
            ).stdout
            self.seen.update(line.strip() for line in out.splitlines()[1:] if line.strip())
            time.sleep(0.4)

    def __enter__(self) -> ProcessWatch:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def matching(self, *needles: str) -> list[str]:
        return sorted(n for n in self.seen if any(needle in n.lower() for needle in needles))


def main() -> int:
    engine = create_engine(os.environ["VAL_DATABASE_URL"])
    LMStudioRuntime(DEFAULT_BASE_URL, os.environ["VAL_LMSTUDIO_API_TOKEN"]).ensure_ready(
        by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio-partner")
    )
    started = start(engine)
    report: dict[str, object] = {
        "startup_warnings": started.warnings,
        "speech_provider": type(started.gateway.speech).__name__
        if started.gateway.speech
        else None,
        "voice_wired": started.gateway.voice.name if started.gateway.voice else None,
    }
    if started.gateway.speech is None or started.gateway.voice is None:
        report["error"] = "the composition root did not wire local speech"
        print(json.dumps(report, indent=1, default=str))
        return 1

    # An ordinary Val turn, so the text spoken is a genuine finished response.
    outcome = send(
        engine,
        started.gateway,
        "In one sentence, tell me the local systems are ready.",
        catalogue=load_catalogue(engine),
        signals=ProjectSignals(explicit_no_project=True),
    )
    if not isinstance(outcome, Turn):
        report["error"] = f"the turn did not complete: {getattr(outcome, 'error', outcome)}"
        print(json.dumps(report, indent=1, default=str))
        return 1
    report["val_final_text"] = outcome.val_message.content

    configuration = next(
        config
        for config in active()
        if is_admitted(config) and satisfies_profile(config, CapabilityProfile.SPEECH)
    )
    described = json.loads(VOICE_RECORD.read_text())
    voice_id = register_voice(engine, started.gateway.voice, described)

    with engine.connect() as connection:
        marker = connection.execute(text("select now()")).scalar_one()

    began = time.monotonic()
    with ProcessWatch() as watch:
        spoken = speak_message(
            engine,
            started.gateway.speech,
            configuration,
            started.gateway.voice,
            voice_id,
            outcome.val_message.id,
        )
    report["speech_seconds"] = round(time.monotonic() - began, 2)

    with engine.connect() as connection:
        row = connection.execute(
            text("select * from speech_generations where id = :i"), {"i": spoken.generation_id}
        ).mappings().one()
        voice_row = connection.execute(
            text("select * from speech_voices where id = :i"), {"i": voice_id}
        ).mappings().one()
        calls = list(
            connection.execute(
                text(
                    "select task_type, cost, model_config_id, status from model_calls "
                    "where created_at > :t order by created_at"
                ),
                {"t": marker},
            ).mappings()
        )

    report["speech"] = {
        "audio_path": str(spoken.audio_path),
        "audio_sha256": spoken.audio_sha256,
        "sample_rate": spoken.sample_rate,
        "duration_seconds": spoken.duration_seconds,
        "clone_prompt_sha256": spoken.clone_prompt_sha256,
        "provider": row["provider"],
        "model": row["model_identifier"],
        "revision": row["model_revision"],
        "quantization": row["quantization"],
        "runtime": f"{row['runtime']} {row['runtime_version']}",
        "generation": row["generation"],
        "local": row["local"],
        "cost_usd": str(row["cost_usd"]),
        "final_text_recorded": row["final_text"],
        "final_text_matches_message": row["final_text"] == outcome.val_message.content,
        "message_id": str(row["message_id"]),
    }
    report["voice"] = {
        "name": voice_row["name"],
        "reference_sha256": voice_row["reference_sha256"],
        "reference_text_sha256": voice_row["reference_text_sha256"],
        "voice_description_sha256": voice_row["voice_description_sha256"],
        "designed_by": f"{voice_row['designed_by_model']} @ {voice_row['designed_by_revision']}",
    }
    report["negative_proof"] = {
        "provider_calls_in_interval": len(calls),
        "calls": [
            {"task": c["task_type"], "cost_usd": str(c["cost"]), "status": c["status"]}
            for c in calls
        ],
        "speech_cost_usd": str(row["cost_usd"]),
        "cloud_voice_or_stt_processes_seen": watch.matching(
            "eleven", "whisper", "vosk", "deepgram", "azure", "polly", "openai", "curl", "wget"
        ),
        "local_speech_runtime_seen": watch.matching("mlx-audio-venv", "python3.1"),
        "processes_sampled": len(watch.seen),
        "voice_design_ran": any("voicedesign" in name.lower() for name in watch.seen),
    }
    print(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
