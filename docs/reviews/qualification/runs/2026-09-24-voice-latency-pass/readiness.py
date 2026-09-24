"""Attribution for the readiness change — latency pass §14.

The end-to-end figure is dominated by provider generation, which this pass does
not touch, so a claimed improvement is measured **at the stage that changed**.
Three runs of each, both paths, on the same machine minutes apart.

    warm, over HTTP   — the new behaviour
    warm, over the CLI — the old behaviour, forced, for comparison

No provider inference. $0.
"""

import json
import os
import plistlib
import time
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as f:
    env = plistlib.load(f)["EnvironmentVariables"]
for k, v in env.items():
    if k != "VAL_DATABASE_URL":
        os.environ[k] = v

HERE = Path(__file__).resolve().parent
from val_domain.registry import by_slug
from val_providers.lmstudio_runtime import LMStudioRuntime

token = env["VAL_LMSTUDIO_API_TOKEN"]
config = by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio-partner")
assert config is not None


def three(label: str, runtime: LMStudioRuntime) -> dict:
    runs = []
    for _ in range(3):
        started = time.monotonic()
        readiness = dict(runtime.ensure_ready(config))
        runs.append(round(time.monotonic() - started, 4))
        assert readiness["model_loaded"] is False, "warm: nothing had to be loaded"
    ordered = sorted(runs)
    return {"runs_s": runs, "median_s": ordered[1], "min_s": ordered[0], "max_s": ordered[2]}


after = three("warm over HTTP (new)", LMStudioRuntime(
    "http://127.0.0.1:1234/v1", token
))

# The old behaviour, forced: the HTTP observation is made to fail so the CLI
# fallback answers. Nothing is reconfigured; only this diagnostic object is aimed
# at a port nothing serves, and only for its residency observation.
class ForcedCli(LMStudioRuntime):
    def _loaded_over_http(self):  # type: ignore[no-untyped-def]
        return None


before = three("warm over the CLI (old)", ForcedCli("http://127.0.0.1:1234/v1", token))

report = {
    "measurement": "readiness stage, before and after, three runs each",
    "order": "pre-WP3 latency pass §14 — owner execution order 24 September 2026",
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "what_changed": (
        "residency is observed through the server's own HTTP listing instead of "
        "spawning LM Studio's Node CLI; the CLI remains the fallback"
    ),
    "before_cli": before,
    "after_http": after,
    "delta_median_ms": round((before["median_s"] - after["median_s"]) * 1000, 1),
    "delta_median_percent": round(
        (before["median_s"] - after["median_s"]) / before["median_s"] * 100, 1
    ),
    "both_sources_agree_on_residency": True,
    "provider_inference_calls": 0,
    "cost_usd": 0.0,
}
out = HERE / "readiness.json"
out.write_text(json.dumps(report, indent=1))
print(json.dumps(report, indent=1))
print("written:", out)
