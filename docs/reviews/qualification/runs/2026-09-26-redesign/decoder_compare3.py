"""How much reference context the streaming decoder needs — audio regression §8.

Priming with the whole reference (234 codes) restored whole-decode quality but cost
0.57 s on the first piece. The library's own chunked decode treats 25 codes of left
context as sufficient. Measured here: quality (log-mel distance to the whole decode,
same codes by seeding) and first-piece cost, priming with the last 25, 50 and 100
reference codes."""
from __future__ import annotations
import json, sys, time
import mlx.core as mx
import numpy as np
from mlx_audio.tts.utils import load_model
from mlx_audio.utils import load_audio
sys.path.insert(0, ".")
config = json.loads(sys.argv[1])
model = load_model(config["model_path"]); rate = int(model.sample_rate)
ref_audio = load_audio(config["ref_audio_path"], sample_rate=rate); ref_text = config["ref_text"]
stored = np.load(config["clone_prompt_path"]); REF = mx.array(stored["ref_codes"])
model._icl_cache[(ref_text, (ref_audio.size, float(ref_audio.sum())))] = (REF, mx.array(stored["ref_text_ids"]))
real = model.speech_tokenizer.decoder.reset_streaming_state.__self__
_reset = real.reset_streaming_state
PRIME = {"tail": 0}
def primed():
    _reset()
    if PRIME["tail"]:
        real.streaming_step(REF[:, :, -PRIME["tail"]:])
real.reset_streaming_state = primed
print("ref codes", REF.shape, flush=True)

def logmel(x):
    frame, hop = 1024, 256; win = np.hanning(frame)
    frames = np.lib.stride_tricks.sliding_window_view(np.pad(x, (0, frame)), frame)[::hop]
    spec = np.abs(np.fft.rfft(frames * win, axis=1)) ** 2
    bins = np.linspace(0, spec.shape[1], 65).astype(int)
    return np.log10(np.stack([spec[:, bins[i]:max(bins[i+1], bins[i]+1)].mean(1) for i in range(64)], 1) + 1e-8)

def run(text, seed, stream, tail=0):
    PRIME["tail"] = tail; mx.random.seed(seed); t0 = time.monotonic(); first = None; chunks = []
    for r in model.generate(text=text, ref_audio=ref_audio, ref_text=ref_text, lang_code="english",
                            verbose=False, stream=stream, streaming_interval=1.0):
        if first is None: first = time.monotonic() - t0
        chunks.append(np.asarray(r.audio, dtype=np.float32).reshape(-1))
    return np.concatenate(chunks), first

TEXTS = ["My lord, I shall outline three methods by which a film scene can be rendered tense.",
         "Good evening, my lord. How may I assist you tonight?",
         "The lamps are lit, the house is quiet, and the evening is yours to direct."]
rows = []
for text in TEXTS:
    for seed in (7, 11):
        whole, _ = run(text, seed, False)
        mw = logmel(whole)
        row = {"text": text[:24], "seed": seed}
        for tail in (0, 25, 50, 100, REF.shape[2]):
            s, first = run(text, seed, True, tail)
            ms = logmel(s); m = min(len(mw), len(ms)); d = np.abs(mw[:m] - ms[:m]).mean(1)
            row[f"tail_{tail}"] = {"logmel_median": round(float(np.median(d)), 3), "logmel_first_300ms": round(float(d[:28].mean()), 3),
                                    "first_piece_s": round(first, 3), "onset_rms_60ms": round(float(np.sqrt(np.mean(s[:1440] ** 2))), 4)}
        row["whole_onset_rms_60ms"] = round(float(np.sqrt(np.mean(whole[:1440] ** 2))), 4)
        rows.append(row); print(json.dumps(row), flush=True)
json.dump(rows, open(sys.argv[2], "w"), indent=1)
