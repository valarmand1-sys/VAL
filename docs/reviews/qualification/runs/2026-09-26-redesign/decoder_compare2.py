"""Where streamed decoding differs from whole decoding, and whether priming the
streaming decoder with the reference codes (as the whole path effectively does)
removes the difference — audio regression §8. Same codes by seeding; exact lag by
FFT cross-correlation; a log-mel distance that tolerates sub-sample shifts; onset
energy in the first 60 ms (a cold-start transient would show there)."""

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
REF_CODES = mx.array(stored["ref_codes"])  # [1, 16, ref_time]
model._icl_cache[(ref_text, (ref_audio.size, float(ref_audio.sum())))] = (REF_CODES, mx.array(stored["ref_text_ids"]))
decoder = model.speech_tokenizer.decoder
# The tokenizer's decoder is wrapped by an MLX compiled-function object that forwards
# attribute reads to the module but not writes; the module itself is reached through
# the bound method it hands back.
_real = decoder.reset_streaming_state.__self__
TEXTS = [
    "My lord, I shall outline three methods by which a film scene can be rendered tense.",
    "Good evening, my lord. How may I assist you tonight?",
    "The lamps are lit, the house is quiet, and the evening is yours to direct.",
]

_reset = _real.reset_streaming_state
PRIME = {"on": False, "count": 0}


def primed_reset() -> None:
    """The library's reset, then the reference codes through the fresh state, discarded.

    Mirrors the whole-decode path, which decodes reference + generated codes together
    and cuts the reference portion: the generated codes are then decoded by a decoder
    whose buffers and attention already hold the voice, not by a cold one.
    """
    _reset()
    if PRIME["on"] and PRIME["count"] % 2 == 0:  # the library resets at start and end
        decoder.streaming_step(REF_CODES)
    PRIME["count"] += 1


_real.reset_streaming_state = primed_reset


def run(text: str, seed: int, stream: bool) -> np.ndarray:
    mx.random.seed(seed)
    PRIME["count"] = 0
    chunks = [np.asarray(r.audio, dtype=np.float32).reshape(-1) for r in model.generate(
        text=text, ref_audio=ref_audio, ref_text=ref_text, lang_code="english",
        verbose=False, stream=stream, streaming_interval=1.0)]
    return np.concatenate(chunks)


def lag_of(a: np.ndarray, b: np.ndarray) -> int:
    n = 1 << (max(len(a), len(b)) * 2 - 1).bit_length()
    c = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)), n)
    k = int(np.argmax(c))
    return k if k < n // 2 else k - n


def logmel(x: np.ndarray) -> np.ndarray:
    frame, hop = 1024, 256
    win = np.hanning(frame)
    frames = np.lib.stride_tricks.sliding_window_view(np.pad(x, (0, frame)), frame)[::hop]
    spec = np.abs(np.fft.rfft(frames * win, axis=1)) ** 2
    bins = np.linspace(0, spec.shape[1], 65).astype(int)
    mel = np.stack([spec[:, bins[i]:max(bins[i + 1], bins[i] + 1)].mean(1) for i in range(64)], 1)
    return np.log10(mel + 1e-8)


def compare(whole: np.ndarray, streamed: np.ndarray) -> dict:
    lag = lag_of(whole, streamed)
    w, s = (whole[lag:], streamed) if lag >= 0 else (whole, streamed[-lag:])
    n = min(len(w), len(s)); w, s = w[:n], s[:n]
    mw, ms = logmel(w), logmel(s)
    m = min(len(mw), len(ms))
    d = np.abs(mw[:m] - ms[:m]).mean(1)  # per 10.7 ms frame
    per_100ms = [round(float(d[i:i + 9].mean()), 3) for i in range(0, len(d) - 9, 9)]
    return {
        "lag_samples": lag,
        "logmel_distance_median": round(float(np.median(d)), 3),
        "logmel_distance_first_300ms": round(float(d[:28].mean()), 3),
        "logmel_distance_after_300ms": round(float(d[28:].mean()), 3),
        "per_100ms_first_2s": per_100ms[:20],
        "onset_rms_first_60ms_whole": round(float(np.sqrt(np.mean(whole[:1440] ** 2))), 4),
        "onset_rms_first_60ms_streamed": round(float(np.sqrt(np.mean(streamed[:1440] ** 2))), 4),
        "max_abs_step_first_60ms_streamed": round(float(np.max(np.abs(np.diff(streamed[:1440])))), 4),
    }


out = []
for text in TEXTS:
    for seed in (7, 11):
        whole = run(text, seed, False)
        PRIME["on"] = False
        cold = run(text, seed, True)
        PRIME["on"] = True
        warm = run(text, seed, True)
        PRIME["on"] = False
        same = run(text, seed, False)
        row = {"text": text[:34], "seed": seed,
               "whole_vs_whole_again": compare(whole, same)["logmel_distance_median"],
               "cold_stream": compare(whole, cold), "reference_primed_stream": compare(whole, warm)}
        out.append(row); print(json.dumps(row), flush=True)
json.dump(out, open(sys.argv[2], "w"), indent=1)
