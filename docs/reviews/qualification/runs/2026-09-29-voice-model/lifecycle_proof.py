"""The Partner model's release-and-return, on production's own model key — 29 September 2026.

VOICE_MODEL.md §10.3. The desktop harness serves GPT-OSS as an experiment *instance*
(`val-exp-hub` over the model key `gpt-oss-20b-renewal`), and `lms load val-exp-hub` is
"Model not found": the harness cannot show the return. Production's route names
`openai/gpt-oss-20b`, which is both the model key and the loaded instance's identifier,
so this exercises exactly the two supervisor calls the switch makes, on that key, in the
shared LM Studio server production uses — the same load its own next turn would make.
Nothing about the production service, plist or store is touched; the model's idle TTL
unloads it after an hour as ever.

Usage: uv run --project ROOT python lifecycle_proof.py OUT.json
"""

from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    for name, value in plistlib.load(handle)["EnvironmentVariables"].items():
        if name != "VAL_DATABASE_URL":
            os.environ.setdefault(name, value)

import val_domain.registry as registry  # noqa: E402
from val_providers.lmstudio_runtime import LMStudioRuntime  # noqa: E402

OUT = Path(sys.argv[1])
config = registry.by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio-partner")
assert config is not None
runtime = LMStudioRuntime("http://127.0.0.1:1234/v1", os.environ["VAL_LMSTUDIO_API_TOKEN"])


def swap_mb() -> float:
    out = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True).stdout
    return float(out.split("used = ")[1].split("M")[0])


def loaded() -> list[str]:
    return [str(i.get("identifier")) for i in runtime.loaded()]


steps: list[dict[str, object]] = []


def step(name: str, action) -> None:  # noqa: ANN001
    before = time.monotonic()
    result = action()
    steps.append(
        {
            "step": name,
            "seconds": round(time.monotonic() - before, 3),
            "result": dict(result),
            "loaded_after": loaded(),
            "swap_mb": swap_mb(),
        }
    )
    print(json.dumps(steps[-1])[:300])


steps.append({"step": "start", "loaded": loaded(), "swap_mb": swap_mb()})
step("ensure_ready (as the service does at start or on a turn)", lambda: runtime.ensure_ready(config))
step("release (as Voice On would, switch set)", lambda: runtime.release(config.model_identifier))
step("release again (idempotent: nothing loaded)", lambda: runtime.release(config.model_identifier))
step("ensure_ready (as Voice ending would)", lambda: runtime.ensure_ready(config))
OUT.write_text(json.dumps({"model_identifier": config.model_identifier, "steps": steps}, indent=1))
print("written", OUT)
