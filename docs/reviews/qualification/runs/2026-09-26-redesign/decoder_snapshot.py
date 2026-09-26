"""Can the reference-primed streaming-decoder state be captured once and restored per
segment, so full-reference priming costs nothing at request time? — audio regression §8.

Primes the streaming decoder with all reference codes once, snapshots every buffer
that `reset_streaming_state` clears (deep copies, since MLX KV caches update in
place), then on every reset restores the snapshot instead of recomputing. Checks that
a restored-state generation is sample-identical to a freshly primed one for the same
seed, and measures the first-piece time."""
from __future__ import annotations
import copy, json, sys, time
import mlx.core as mx
import numpy as np
from mlx_audio.tts.utils import load_model
from mlx_audio.utils import load_audio

config = json.loads(sys.argv[1])
model = load_model(config["model_path"]); rate = int(model.sample_rate)
ref_audio = load_audio(config["ref_audio_path"], sample_rate=rate); ref_text = config["ref_text"]
stored = np.load(config["clone_prompt_path"]); REF = mx.array(stored["ref_codes"])
model._icl_cache[(ref_text, (ref_audio.size, float(ref_audio.sum())))] = (REF, mx.array(stored["ref_text_ids"]))
real = model.speech_tokenizer.decoder.reset_streaming_state.__self__
_reset = real.reset_streaming_state

stateful = [m for _, m in real.named_modules() if hasattr(m, "reset_state")]
print("stateful modules", len(stateful), flush=True)

def private_state(m):
    """MLX modules keep array-valued attributes as dict items (private names excluded
    from parameters) and other attributes in __dict__; the streaming buffers use both."""
    state = {k: v for k, v in dict.items(m) if k.startswith("_")}
    state.update({k: v for k, v in vars(m).items() if k.startswith("_") and not callable(v)})
    return state

def capture():
    snap = {"cache": copy.deepcopy(real._transformer_cache)}
    for i, m in enumerate(stateful):
        snap[i] = copy.deepcopy(private_state(m))
    return snap

def restore(snap):
    real._transformer_cache = copy.deepcopy(snap["cache"])
    for i, m in enumerate(stateful):
        for k, v in snap[i].items():
            setattr(m, k, copy.deepcopy(v))

MODE = {"mode": "cold"}
SNAP = {}
def reset():
    _reset()
    if MODE["mode"] == "prime":
        real.streaming_step(REF)
    elif MODE["mode"] == "restore":
        restore(SNAP["state"])
real.reset_streaming_state = reset

# Build the snapshot once.
t0 = time.monotonic(); _reset(); real.streaming_step(REF); mx.eval(real._transformer_cache[0].keys if hasattr(real._transformer_cache[0], "keys") else mx.array(0))
SNAP["state"] = capture(); print("snapshot built in", round(time.monotonic() - t0, 3), "s; keys", [list(v.keys()) for v in list(SNAP["state"].values())[1:4]], flush=True)
t0 = time.monotonic(); restore(SNAP["state"]); print("restore alone", round(time.monotonic() - t0, 4), "s", flush=True)

def run(text, seed, mode):
    MODE["mode"] = mode; mx.random.seed(seed); t0 = time.monotonic(); first = None; chunks = []
    for r in model.generate(text=text, ref_audio=ref_audio, ref_text=ref_text, lang_code="english",
                            verbose=False, stream=True, streaming_interval=1.0):
        if first is None: first = time.monotonic() - t0
        chunks.append(np.asarray(r.audio, dtype=np.float32).reshape(-1))
    return np.concatenate(chunks), first

rows = []
for text in ["My lord, I shall outline three methods by which a film scene can be rendered tense.", "Good evening, my lord. How may I assist you tonight?"]:
    for seed in (7, 11):
        primed, t_prime = run(text, seed, "prime")
        restored, t_restore = run(text, seed, "restore")
        restored2, t_restore2 = run(text, seed, "restore")
        identical = len(primed) == len(restored) and bool(np.array_equal(primed, restored))
        maxdiff = float(np.max(np.abs(primed[:min(len(primed), len(restored))] - restored[:min(len(primed), len(restored))]))) if len(primed) and len(restored) else None
        rows.append({"text": text[:24], "seed": seed, "identical": identical, "max_abs_diff": maxdiff,
                     "first_piece_primed_s": round(t_prime, 3), "first_piece_restored_s": round(t_restore, 3), "again": round(t_restore2, 3),
                     "repeat_identical": bool(np.array_equal(restored, restored2))})
        print(json.dumps(rows[-1]), flush=True)
json.dump(rows, open(sys.argv[2], "w"), indent=1)
