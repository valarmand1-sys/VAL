"""Does a cold model load slow the owner-message commit? Reproduction, $0, local only.

Times `open_turn` (sealed new chat, scratch store) every 100 ms: first with the
machine quiet, then while the production readiness call loads the model from
unloaded, exactly as Voice On's cognition warm-up did at 09:18:32.
"""

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from sqlalchemy import create_engine

from val_domain.registry import by_slug
from val_gateway.loop import open_turn
from val_gateway.projects import load_catalogue
from val_gateway.seal import SealRoute
from val_policy.project_resolution import ProjectSignals
from val_providers.lmstudio_runtime import IDLE_TTL_SECONDS, LMS

engine = create_engine("postgresql+psycopg://localhost:5433/val_test")
cat = load_catalogue(engine)
config = by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio-partner")


def sample(seconds: float) -> list[float]:
    out, end = [], time.monotonic() + seconds
    while time.monotonic() < end:
        t = time.monotonic()
        open_turn(
            engine,
            "Good evening, Val.",
            catalogue=cat,
            signals=ProjectSignals(explicit_no_project=True),
            seal=SealRoute.UTTERANCE_FINALIZED,
        )
        out.append(round((time.monotonic() - t) * 1000, 1))
        time.sleep(0.1)
    return out


quiet = sample(5)
subprocess.run([str(LMS), "unload", "--all"], check=True, capture_output=True)
time.sleep(2)
runtime_report: dict = {}


def load():
    t = time.monotonic()
    # The exact command the production readiness call issues when the model is absent.
    done = subprocess.run(
        [
            str(LMS),
            "load",
            config.model_identifier,
            "--context-length",
            str(config.context_window_tokens),
            "--ttl",
            str(IDLE_TTL_SECONDS),
            "--yes",
        ],
        capture_output=True,
        text=True,
    )
    runtime_report["returncode"] = done.returncode
    runtime_report["seconds"] = round(time.monotonic() - t, 3)


loader = threading.Thread(target=load)
loader.start()
during = []
while loader.is_alive():
    during.extend(sample(0.5))
loader.join()
after = sample(3)
report = {"quiet_ms": quiet, "during_load_ms": during, "after_ms": after, "load": runtime_report}
print(
    json.dumps(
        {
            k: (
                v if k == "load" else {"n": len(v), "max": max(v), "median": sorted(v)[len(v) // 2]}
            )
            for k, v in report.items()
        },
        indent=1,
    )
)
Path(sys.argv[1]).write_text(json.dumps(report, indent=1, default=str))
