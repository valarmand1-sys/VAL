"""Does priming the streaming decoder with the reference cost the first piece? §8."""
from __future__ import annotations
import json, sys, time
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
PRIME = {"on": False}
def primed():
    _reset()
    if PRIME["on"]:
        real.streaming_step(REF)
real.reset_streaming_state = primed
TEXTS = ["My lord, I shall outline three methods by which a film scene can be rendered tense.",
         "Good evening, my lord. How may I assist you tonight?"]
rows = []
for _ in range(3):
    for text in TEXTS:
        for on in (False, True):
            PRIME["on"] = on
            t0 = time.monotonic(); first = None; n = 0; total = 0
            for r in model.generate(text=text, ref_audio=ref_audio, ref_text=ref_text, lang_code="english",
                                    verbose=False, stream=True, streaming_interval=1.0):
                if first is None: first = time.monotonic() - t0
                n += 1; total += np.asarray(r.audio).size
            rows.append({"text": text[:24], "primed": on, "first_piece_s": round(first, 3),
                         "total_s": round(time.monotonic() - t0, 3), "pieces": n, "audio_s": round(total / rate, 2)})
            print(json.dumps(rows[-1]), flush=True)
json.dump(rows, open(sys.argv[2], "w"), indent=1)
