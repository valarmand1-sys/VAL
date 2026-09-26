"""The voice side of the first-synthesis probe — run by `onset_probe.py` in the voice runtime.

Loads the admitted Qwen3-TTS Base model once (as the resident worker does), conditions
on the governed reference through the stored clone prompt (as the runner does), and
answers one JSON command per line: synthesise `text` whole, or streamed with
`interval` seconds of audio per chunk. Reports timings and a continuity check at chunk
boundaries. Audio stays in memory and is discarded.
"""

from __future__ import annotations

import json
import sys
import time

import mlx.core as mx
import numpy as np
from mlx_audio.tts.utils import load_model
from mlx_audio.utils import load_audio

config = json.loads(sys.argv[1])
model = load_model(config["model_path"])
rate = int(model.sample_rate)
ref_audio = load_audio(config["ref_audio_path"], sample_rate=rate)
ref_text = config["ref_text"]
stored = np.load(config["clone_prompt_path"])
model._icl_cache[(ref_text, (ref_audio.size, float(ref_audio.sum())))] = (
    mx.array(stored["ref_codes"]),
    mx.array(stored["ref_text_ids"]),
)
print(json.dumps({"ready": True}), flush=True)

for line in sys.stdin:
    command = json.loads(line)
    if command.get("stop"):
        break
    stream = command["interval"] is not None
    started = time.monotonic()
    first = None
    chunks = []
    for result in model.generate(
        text=command["text"], ref_audio=ref_audio, ref_text=ref_text, lang_code="english",
        verbose=False, stream=stream, streaming_interval=command["interval"] or 2.0,
    ):
        if first is None:
            first = time.monotonic() - started
        chunks.append(np.asarray(result.audio).reshape(-1))
    total = time.monotonic() - started
    audio = np.concatenate(chunks) if chunks else np.zeros(0)
    # Continuity: the largest sample jump at a chunk boundary, against the waveform's
    # own 99.9th-percentile step. A seam that clicks would stand out.
    steps = np.abs(np.diff(audio)) if audio.size > 1 else np.zeros(1)
    seams, at = [], 0
    for chunk in chunks[:-1]:
        at += chunk.size
        seams.append(float(abs(audio[at] - audio[at - 1])))
    print(json.dumps({
        "text_chars": len(command["text"]), "stream_interval": command["interval"],
        "first_audio_s": round(first or total, 3), "total_s": round(total, 3),
        "audio_s": round(audio.size / rate, 3), "chunks": len(chunks),
        "max_seam_step": round(max(seams), 5) if seams else None,
        "p999_step": round(float(np.percentile(steps, 99.9)), 5),
    }), flush=True)
