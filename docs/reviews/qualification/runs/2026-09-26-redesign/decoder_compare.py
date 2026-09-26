"""Streamed against whole decode of the SAME speech codes — audio regression §8.

Run in the voice runtime. Seeds MLX's sampler identically before a whole and a streamed
generation of one text, so the talker produces the same codes and only the decoder path
differs: whole decode (reference codes prepended, reference portion cut) against the
library's streaming decoder (fresh state, generated codes only). Reports where the two
waveforms differ, in 100 ms bins after alignment, plus peak levels and chunk seams.
Audio stays in memory; nothing is written.
"""

from __future__ import annotations

import json
import sys

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
TEXTS = [
    "My lord, I shall outline three methods by which a film scene can be rendered tense.",
    "Good evening, my lord. How may I assist you tonight?",
]


def run(text: str, seed: int, stream: bool) -> list[np.ndarray]:
    mx.random.seed(seed)
    chunks = []
    for result in model.generate(
        text=text, ref_audio=ref_audio, ref_text=ref_text, lang_code="english",
        verbose=False, stream=stream, streaming_interval=1.0,
    ):
        chunks.append(np.asarray(result.audio, dtype=np.float32).reshape(-1))
    return chunks


def align(a: np.ndarray, b: np.ndarray, search: int = 4800) -> int:
    """Lag (samples) of b against a maximising correlation over the first 2 s."""
    n = min(len(a), len(b), rate * 2)
    best, best_lag = -1.0, 0
    for lag in range(-search, search + 1, 8):
        if lag >= 0:
            x, y = a[lag : lag + n], b[:n]
        else:
            x, y = a[:n], b[-lag : -lag + n]
        m = min(len(x), len(y))
        if m < rate:
            continue
        c = float(np.dot(x[:m], y[:m]) / (np.linalg.norm(x[:m]) * np.linalg.norm(y[:m]) + 1e-9))
        if c > best:
            best, best_lag = c, lag
    return best_lag


out = []
for text in TEXTS:
    for seed in (7, 11):
        whole = np.concatenate(run(text, seed, False))
        pieces = run(text, seed, True)
        streamed = np.concatenate(pieces)
        same_length = abs(len(whole) - len(streamed)) < rate * 0.5
        lag = align(whole, streamed)
        if lag >= 0:
            w, s = whole[lag:], streamed
        else:
            w, s = whole, streamed[-lag:]
        n = min(len(w), len(s))
        w, s = w[:n], s[:n]
        bins = []
        step = rate // 10
        for i in range(0, n - step, step):
            d = s[i : i + step] - w[i : i + step]
            bins.append(round(float(np.sqrt(np.mean(d * d)) / (np.sqrt(np.mean(w[i:i+step] ** 2)) + 1e-6)), 3))
        seams = []
        at = 0
        for chunk in pieces[:-1]:
            at += len(chunk)
            if 0 < at < len(streamed):
                seams.append(round(float(abs(streamed[at] - streamed[at - 1])), 4))
        out.append({
            "text": text[:40], "seed": seed, "whole_s": round(len(whole) / rate, 3),
            "streamed_s": round(len(streamed) / rate, 3), "codes_identical_length": same_length,
            "lag_samples": lag, "correlation_first_2s": None,
            "relative_rms_difference_per_100ms": bins[:40],
            "streamed_peak": round(float(np.max(np.abs(streamed))), 3),
            "whole_peak": round(float(np.max(np.abs(whole))), 3),
            "seam_steps": seams,
            "p999_step_streamed": round(float(np.percentile(np.abs(np.diff(streamed)), 99.9)), 4),
        })
        print(json.dumps(out[-1]), flush=True)
json.dump(out, open(sys.argv[2], "w"), indent=1)
