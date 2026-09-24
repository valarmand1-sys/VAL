"""TTS cold/warm and GPT contention — latency pass §10. Established voice only.

Three bounded local comparisons on the same short representative phrase:

    A. the first synthesis after the speech provider is newly initialised
    B. an immediate repeated synthesis with the same ready provider
    C. a synthesis while GPT-OSS is actively generating a representative MEDIUM turn

The purpose is to separate cold voice/model setup, steady-state synthesis cost and
resource contention. Nothing is claimed about contention unless the comparison
shows it. No audio is kept beyond the call. The voice, the model and mlx-audio are
untouched.
"""

import json
import os
import plistlib
import threading
import time
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as f:
    _env = plistlib.load(f)["EnvironmentVariables"]
for _name, _value in _env.items():
    if _name != "VAL_DATABASE_URL":
        os.environ[_name] = _value

ROOT = Path("/Users/josepharmand/Projects/val")
HERE = Path(__file__).resolve().parent

from val_domain.gateway import Message
from val_domain.registry import by_slug
from val_domain.speech import SpeechRequest
from val_providers.qwen_tts_speech import QwenTTSSpeech, load_canonical_voice
from val_providers.lmstudio_adapter import LMStudioAdapter
from val_gateway.startup import build_adapters

PHRASE = "Good evening, my lord. The work is finished."
voice = load_canonical_voice()
report: dict[str, object] = {
    "measurement": "TTS cold/warm and GPT contention",
    "order": "pre-WP3 latency pass §10 — owner execution order 24 September 2026",
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "voice": voice.name,
    "voice_reference_sha256": voice.reference_sha256,
    "phrase": PHRASE,
    "phrase_characters": len(PHRASE),
}


def one_synthesis(provider: QwenTTSSpeech) -> dict:
    started = time.monotonic()
    result = provider.synthesize(SpeechRequest(text=PHRASE, voice=voice))
    elapsed = time.monotonic() - started
    return {
        "wall_clock_s": round(elapsed, 3),
        "audio_seconds": round(result.duration_seconds, 3),
        "audio_bytes": len(result.audio),
        "clone_prompt_sha256": result.clone_prompt_sha256[:16],
        "cost_usd": result.cost_usd,
        "realtime_factor": round(elapsed / max(result.duration_seconds, 0.001), 3),
    }


# --- A: a newly initialised provider ------------------------------------------------------
print("A: first synthesis after a fresh provider")
cold_provider = QwenTTSSpeech()
a = one_synthesis(cold_provider)
print(json.dumps(a, indent=1))

# --- B: immediately again, same provider --------------------------------------------------
print("B: immediate repeat, same ready provider")
b = one_synthesis(cold_provider)
print(json.dumps(b, indent=1))
b2 = one_synthesis(cold_provider)
print(json.dumps(b2, indent=1))

report["a_first_after_fresh_provider"] = a
report["b_immediate_repeats"] = [b, b2]

# --- C: while GPT-OSS is generating -------------------------------------------------------
print("C: synthesis while GPT-OSS is generating")
adapters, problems = build_adapters({"lmstudio"})
assert not problems, problems
adapter = adapters["lmstudio"]
config = by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio")
assert config is not None
adapter.ensure_runtime_ready(config)

generating = threading.Event()
finished = threading.Event()
generation: dict[str, object] = {}


def generate() -> None:
    """One representative MEDIUM generation, long enough to overlap the synthesis."""
    started = time.monotonic()
    try:
        pieces = 0
        for event in adapter.stream(
            config,
            (
                Message(
                    role="user",
                    content=(
                        "Describe, in five unhurried paragraphs, how a house keeps a "
                        "record of the decisions it takes and the reasons behind them."
                    ),
                ),
            ),
            None,
            1024,
        ):
            if pieces == 0:
                generating.set()
            pieces += 1
        generation["pieces"] = pieces
    except Exception as failure:  # recorded, not hidden
        generation["error"] = f"{type(failure).__name__}: {failure}"
        generating.set()
    generation["wall_clock_s"] = round(time.monotonic() - started, 3)
    finished.set()


worker = threading.Thread(target=generate, daemon=True)
worker.start()
overlapped = None
if generating.wait(timeout=180):
    overlapped = one_synthesis(cold_provider)
    report["c_during_gpt_generation"] = overlapped
    report["c_overlap_confirmed"] = not finished.is_set()
    print(json.dumps(overlapped, indent=1))
else:
    report["c_during_gpt_generation"] = None
    report["c_overlap_confirmed"] = False
    print("GPT generation never started; C not measured")
finished.wait(timeout=300)
worker.join(timeout=10)
report["c_generation"] = generation

steady = min(x["wall_clock_s"] for x in (b, b2))
report["findings"] = {
    "cold_first_call_s": a["wall_clock_s"],
    "steady_state_s": steady,
    "cold_penalty_s": round(a["wall_clock_s"] - steady, 3),
    "during_gpt_generation_s": None if overlapped is None else overlapped["wall_clock_s"],
    "contention_penalty_s": (
        None if overlapped is None else round(overlapped["wall_clock_s"] - steady, 3)
    ),
    "note": (
        "Every call is a subprocess of the isolated mlx-audio runtime, so 'cold' "
        "here means the first call after this provider object existed, not a "
        "process that stays warm between calls."
    ),
}
out = HERE / "tts-warmth.json"
out.write_text(json.dumps(report, indent=1, default=str))
print("\n=== findings ===")
print(json.dumps(report["findings"], indent=1))
print("written:", out)
