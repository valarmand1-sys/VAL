"""First-synthesis latency: contention, and incremental audio — REDUCE THE WAIT order §3.

The same first-segment texts, the same admitted voice model loaded once, the same
stored voice conditioning, three repeats each, under four conditions:

- whole sentence, nothing else running;
- whole sentence, while GPT-OSS (the production instance, loaded by the service's own
  readiness code at parallel 1) is generating an answer — the real situation, since
  her first sentence is voiced while the rest of her answer is still being written;
- streamed (the installed mlx-audio 0.5.5 ICL path's own `stream=True`), alone;
- streamed, under the same generation.

GPT-OSS's streaming rate is recorded with and without speech alongside it, so a
scheduling choice can be judged on the whole path. Local, $0. The token is read from
the service's launchd definition and never printed.

Usage: onset_probe.py OUT.json
"""

from __future__ import annotations

import json
import plistlib
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx

from val_providers.qwen_tts_speech import (
    MODEL_PATH, VENV_PYTHON, VOICE_RECORD, clone_prompt_for, load_canonical_voice,
)

HERE = Path(__file__).resolve().parent
with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    TOKEN = plistlib.load(handle)["EnvironmentVariables"]["VAL_LMSTUDIO_API_TOKEN"]
TEXTS = {
    "23:03 first segment (107)": "My lord,\n\nI have no record in the House’s authoritative "
    "storage of any voice‑related work undertaken today.",
    "message 8 first sentence (121)": "My lord, the voice model is tuned for a natural "
    "conversational pace – roughly the cadence of an ordinary spoken exchange.",
}
REPEATS = 3
INTERVAL = 1.0

voice = load_canonical_voice(VOICE_RECORD)
workdir = Path(tempfile.mkdtemp(prefix="val-onset-"))
reference = workdir / "reference.wav"
reference.write_bytes(voice.reference_audio)
side = subprocess.Popen(
    [str(VENV_PYTHON), str(HERE / "tts_side.py"), json.dumps({
        "model_path": str(MODEL_PATH), "ref_audio_path": str(reference),
        "ref_text": voice.reference_text,
        "clone_prompt_path": str(clone_prompt_for(voice.reference_sha256)),
    })],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1,
)
assert side.stdin and side.stdout


def reply() -> dict:
    """The side's next JSON line; a library's own chatter on stdout is skipped."""
    while True:
        line = side.stdout.readline()
        if not line:
            raise RuntimeError("the voice side exited")
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed


assert reply()["ready"]


def synth(text: str, interval: float | None) -> dict:
    side.stdin.write(json.dumps({"text": text, "interval": interval}) + "\n")
    side.stdin.flush()
    return reply()


class Generation(threading.Thread):
    """One GPT-OSS answer streamed from the production instance; chunk times kept."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.times: list[float] = []
        self.flowing = threading.Event()

    def run(self) -> None:
        with httpx.stream(
            "POST", "http://127.0.0.1:1234/v1/chat/completions",
            headers={"Authorization": f"Bearer {TOKEN}"}, timeout=300,
            json={"model": "openai/gpt-oss-20b", "stream": True, "max_tokens": 1200,
                  "messages": [{"role": "user", "content":
                      "Write a detailed, multi-paragraph explanation of how a lighthouse "
                      "keeper maintained the lamp in the nineteenth century."}]},
        ) as response:
            for line in response.iter_lines():
                if line.startswith("data:") and '"delta"' in line:
                    self.times.append(time.monotonic())
                    if len(self.times) == 40:
                        self.flowing.set()
        self.flowing.set()


def rate(times: list[float], start: float, end: float) -> float | None:
    inside = [t for t in times if start <= t <= end]
    return round(len(inside) / (end - start), 1) if end > start and inside else None


rows = []
synth("Good evening, my lord.", None)  # settle the model
for _ in range(REPEATS):
    for label, text in TEXTS.items():
        for interval in (None, INTERVAL):
            rows.append({"case": label, "contended": False, **synth(text, interval)})
            print(json.dumps(rows[-1]), flush=True)
            gen = Generation()
            gen.start()
            assert gen.flowing.wait(60), "generation did not start"
            before_end = time.monotonic()
            began = time.monotonic()
            result = synth(text, interval)
            ended = time.monotonic()
            gen.join(timeout=300)
            baseline = rate(gen.times, gen.times[0], before_end) if gen.times else None
            after = rate(gen.times, ended, gen.times[-1]) if gen.times and gen.times[-1] > ended else None
            rows.append({"case": label, "contended": True, **result,
                         "generation_chunks_per_s_before": baseline,
                         "generation_chunks_per_s_during_speech": rate(gen.times, began, ended),
                         "generation_chunks_per_s_after": after})
            print(json.dumps(rows[-1]), flush=True)
side.stdin.write(json.dumps({"stop": True}) + "\n")
side.stdin.flush()
side.wait(timeout=30)
reference.unlink()
workdir.rmdir()
Path(sys.argv[1]).write_text(json.dumps({"rows": rows}, indent=1) + "\n")
