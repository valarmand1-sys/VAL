"""Does warming absorb the load? — latency pass §14, the direct measurement.

The production-shaped fixture is 2.6 seconds of speech and the load is about nine,
so the pipeline measurement cannot show this effect: the turn arrives before the
load can finish. Measured directly instead, at the stage that changed, three runs
of each:

    A. no warming        — the turn's readiness pays the whole load
    B. warming, 3 s head start  — a short utterance
    C. warming, 12 s head start — an ordinary spoken sentence

Each run starts from a genuinely unloaded model, which is the ordinary state after
the one-hour idle TTL. No inference, no cloud, $0.
"""

import json
import os
import plistlib
import subprocess
import threading
import time
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as f:
    env = plistlib.load(f)["EnvironmentVariables"]
for k, v in env.items():
    if k != "VAL_DATABASE_URL":
        os.environ[k] = v

HERE = Path(__file__).resolve().parent
LMS = str(Path.home() / ".lmstudio/bin/lms")

from val_domain.registry import by_slug
from val_providers.lmstudio_runtime import LMStudioRuntime

config = by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio-partner")
assert config is not None
token = env["VAL_LMSTUDIO_API_TOKEN"]


def unloaded() -> None:
    subprocess.run([LMS, "unload", "--all"], capture_output=True, text=True, timeout=180)
    time.sleep(1.0)


def turn_readiness(head_start: float | None) -> dict:
    """One trial: optionally warm, wait `head_start`, then time the turn's own call."""
    unloaded()
    runtime = LMStudioRuntime("http://127.0.0.1:1234/v1", token)
    warmed: dict[str, object] = {}
    if head_start is not None:
        def warm() -> None:
            started = time.monotonic()
            try:
                warmed["readiness"] = dict(runtime.ensure_ready(config))
            except Exception as failure:
                warmed["error"] = f"{type(failure).__name__}: {failure}"
            warmed["took_s"] = round(time.monotonic() - started, 3)

        threading.Thread(target=warm, daemon=True).start()
        time.sleep(head_start)
    started = time.monotonic()
    readiness = dict(runtime.ensure_ready(config))
    took = round(time.monotonic() - started, 3)
    # The model must be resident exactly once afterwards: the serialisation rule.
    listing = runtime.loaded()
    resident = sum(
        1
        for row in listing
        if config.model_identifier
        in {str(row.get(key, "")) for key in ("modelKey", "path", "identifier", "id")}
    )
    return {
        "head_start_s": head_start,
        "turn_readiness_s": took,
        "turn_loaded_it": readiness["model_loaded"],
        "warming": warmed or None,
        "resident_instances_afterwards": resident,
        "loaded_context": readiness["loaded_context_tokens"],
    }


def three(label: str, head_start: float | None) -> dict:
    runs = [turn_readiness(head_start) for _ in range(3)]
    times = sorted(r["turn_readiness_s"] for r in runs)
    print(f"{label}: runs {[r['turn_readiness_s'] for r in runs]} median {times[1]}")
    return {"runs": runs, "median_s": times[1], "min_s": times[0], "max_s": times[2]}


report = {
    "measurement": "does warming absorb the cold load",
    "order": "pre-WP3 latency pass §14 — owner execution order 24 September 2026",
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "provider_inference_calls": 0,
    "cost_usd": 0.0,
}
report["a_no_warming"] = three("A no warming", None)
report["b_warming_3s_head_start"] = three("B warming, 3 s head start", 3.0)
report["c_warming_12s_head_start"] = three("C warming, 12 s head start", 12.0)

a = report["a_no_warming"]["median_s"]
report["findings"] = {
    "cold_load_on_the_critical_path_s": a,
    "with_a_short_utterance_s": report["b_warming_3s_head_start"]["median_s"],
    "with_an_ordinary_utterance_s": report["c_warming_12s_head_start"]["median_s"],
    "absorbed_by_a_short_utterance_s": round(
        a - report["b_warming_3s_head_start"]["median_s"], 3
    ),
    "absorbed_by_an_ordinary_utterance_s": round(
        a - report["c_warming_12s_head_start"]["median_s"], 3
    ),
    "never_more_than_one_resident_instance": all(
        run["resident_instances_afterwards"] == 1
        for key in ("a_no_warming", "b_warming_3s_head_start", "c_warming_12s_head_start")
        for run in report[key]["runs"]
    ),
}
out = HERE / "warming-effect.json"
out.write_text(json.dumps(report, indent=1, default=str))
print("\n=== findings ===")
print(json.dumps(report["findings"], indent=1))
print("written:", out)
