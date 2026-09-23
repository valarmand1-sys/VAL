"""One production smoke per owner-facing modality.

Not a qualification. The only thing under test is whether the *installed
production application* works: the real composition root (`val_gateway.startup.start`)
builds the gateway, wires the adapters and wires both perception specialists,
and one ordinary `send` carries the turn. Nothing is injected.

Governed scratch store, so no manufactured history enters the owner's real
conversation record.

The negative proof matters more than the answer: an answer that reads correctly
is not evidence the local path produced it. So each smoke records how many
provider calls happened in the interval, what they cost, which routes they were
on, and — for audio — every process that ran while the turn was in flight, so a
silent transcription helper would be visible.
"""

from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
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

from val_domain.gateway import Classification  # noqa: E402
from val_domain.registry import by_slug  # noqa: E402
from val_gateway.attachments import CandidateAttachment  # noqa: E402
from val_gateway.loop import Turn, send  # noqa: E402
from val_gateway.projects import load_catalogue  # noqa: E402
from val_gateway.startup import start  # noqa: E402
from val_policy.project_resolution import ProjectSignals  # noqa: E402
from val_providers.lmstudio_adapter import DEFAULT_BASE_URL  # noqa: E402
from val_providers.lmstudio_runtime import LMStudioRuntime  # noqa: E402

SCRATCH = Path(
    "/private/tmp/claude-501/-Users-josepharmand-Projects-val/"
    "f5cf12ed-8043-4d6d-95f1-c313ddbf0b76/scratchpad/fixtures"
)
REPO = Path("/Users/josepharmand/Projects/val")

FIXTURES = {
    "image": (SCRATCH / "case_a_image.png", "family.png", "Is the boy's hat on straight?"),
    "video": (
        REPO / "docs/reviews/qualification/runs/2026-09-22-case-c-repair/case_c_video_v2.mp4",
        "sequence.mp4",
        "What happens in this clip, and in what order?",
    ),
    "audio": (
        SCRATCH / "case_b_audio.wav",
        "note.wav",
        "Which envelope should she bring, and what is the number?",
    ),
}


class ProcessWatch:
    """Every process that ran while the turn was in flight.

    Crude on purpose: the claim to be proved is a negative one — no transcription
    helper, no cloud client — and a sampler that simply names everything running
    cannot be accused of looking only where it expected to find nothing.
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
        return sorted(
            name
            for name in self.seen
            if any(needle in name.lower() for needle in needles)
        )


def calls_since(engine: object, marker: str) -> list[dict[str, object]]:
    with engine.connect() as connection:  # type: ignore[attr-defined]
        rows = connection.execute(
            text(
                "select task_type, cost, model_config_id, status from model_calls "
                " where created_at > :t order by created_at"
            ),
            {"t": marker},
        ).mappings()
        return [dict(row) for row in rows]


def main() -> int:
    modality = sys.argv[1]
    path, filename, question = FIXTURES[modality]
    engine = create_engine(os.environ["VAL_DATABASE_URL"])

    # Cognition is local; make sure it is up, through the production supervisor.
    LMStudioRuntime(DEFAULT_BASE_URL, os.environ["VAL_LMSTUDIO_API_TOKEN"]).ensure_ready(
        by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio-partner")
    )

    started = start(engine)
    report: dict[str, object] = {
        "modality": modality,
        "startup_warnings": started.warnings,
        "perception_providers": [
            {"class": type(p).__name__, "modalities": sorted(p.modalities)}
            for p in started.gateway.perception
        ],
    }
    with engine.connect() as connection:
        marker = connection.execute(text("select now()")).scalar_one()

    began = time.monotonic()
    with ProcessWatch() as watch:
        outcome = send(
            engine,
            started.gateway,
            question,
            catalogue=load_catalogue(engine),
            signals=ProjectSignals(explicit_no_project=True),
            attachments=(
                CandidateAttachment(
                    content=path.read_bytes(),
                    given_filename=filename,
                    stated_classification=Classification.PROTECTED,
                ),
            ),
        )
    report["seconds"] = round(time.monotonic() - began, 2)
    report["outcome"] = type(outcome).__name__

    if not isinstance(outcome, Turn):
        report["error"] = str(getattr(outcome, "error", outcome))
        print(json.dumps(report, indent=1, default=str))
        return 1

    report["val_answer"] = outcome.val_message.content
    with engine.connect() as connection:
        run = connection.execute(
            text("select * from perception_runs order by created_at desc limit 1")
        ).mappings().one()
        sources = connection.execute(
            text("select * from perception_sources where perception_run_id = :r order by position"),
            {"r": run["id"]},
        ).mappings().all()
        handoffs = connection.execute(
            text("select model_call_id from perception_handoffs where perception_run_id = :r"),
            {"r": run["id"]},
        ).all()
        bound_pixels = connection.execute(
            text(
                "select count(*) from model_call_image_inputs i join model_calls c on c.id = "
                "i.model_call_id where c.created_at > :t"
            ),
            {"t": marker},
        ).scalar_one()

    calls = calls_since(engine, marker)
    report["perception"] = {
        "state": run["current_perception_state"],
        "provider": run["provider"],
        "model": run["model_identifier"],
        "revision": run["model_revision"],
        "runtime": f"{run['runtime']} {run['runtime_version']}",
        "local": run["local"],
        "cost_usd": str(run["cost_usd"]),
        "duration_ms": run["duration_ms"],
        "owner_question": run["owner_question"],
        "observation": run["observation"],
        "sources": [
            {
                "modality": s["modality"],
                "media_type": s["media_type"],
                "sha256": s["sha256"],
                "duration_seconds": str(s["duration_seconds"]),
                "verified": s["verified"],
            }
            for s in sources
        ],
        "handoffs": len(handoffs),
    }
    report["negative_proof"] = {
        "provider_calls_in_interval": len(calls),
        "calls": [
            {
                "task": c["task_type"],
                "cost_usd": str(c["cost"]),
                "route": (by_slug_of(c["model_config_id"])),
                "status": c["status"],
            }
            for c in calls
        ],
        "total_provider_cost_usd": str(
            sum(float(c["cost"] or 0) for c in calls)
        ),
        "raw_media_bound_to_any_cognition_call": bound_pixels,
        "perception_cost_usd": str(run["cost_usd"]),
        "transcription_or_cloud_processes_seen": watch.matching(
            "whisper", "vosk", "deepgram", "assembly", "openai", "curl", "wget"
        ),
        "local_perception_binaries_seen": watch.matching("llama-mtmd", "python3.1"),
        "processes_sampled": len(watch.seen),
    }
    print(json.dumps(report, indent=1, default=str))
    return 0


def by_slug_of(config_id: object) -> str:
    from val_domain.registry import by_id

    found = by_id(UUID(str(config_id)))
    return found.slug if found else str(config_id)


if __name__ == "__main__":
    raise SystemExit(main())
