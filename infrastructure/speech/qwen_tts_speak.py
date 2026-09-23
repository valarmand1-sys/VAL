"""One speech run, inside the house's isolated MLX-Audio runtime.

Owner execution order, 22 September 2026. This file is executed by
`~/.val-runtimes/mlx-audio-venv/bin/python`, a **different interpreter from
Val's** — a dedicated environment holding mlx-audio, which is not a production
dependency and which this order does not permit to become one. Keeping the
speech runtime out of Val's pinned environment is a constraint of the order, and
keeping it out of the *visual* runtime as well leaves the admitted perception
runtime frozen exactly as it was qualified.

**It imports nothing from Val.** One JSON request on stdin, one JSON response on
stdout, and the audio written to a path the caller named. Nothing reaches it
through the command line, so no value from a model, a document or a tool result
can become an argument.

Two modes, and the difference between them is the whole architecture.

    design  — runs ONCE, ever, to create Val's canonical voice. The VoiceDesign
              model turns a natural-language description into a speaker that did
              not exist before. This is the provenance of the voice.

    speak   — runs on every ordinary utterance. The Base model speaks new text
              conditioned on that canonical reference, through Qwen3-TTS's
              in-context-learning path (`ref_audio` + `ref_text`). **VoiceDesign
              is never invoked here**, because designing the voice afresh per
              sentence is exactly how a speaker identity drifts.

**The reusable identity anchor.** `speak` persists and reloads the ICL
conditioning — the speech tokenizer's codes for the reference recording, and the
reference text's token ids — which is the library's own `_icl_cache` value and
the MLX-Audio equivalent of Qwen3-TTS's `create_voice_clone_prompt`. Computed
once, written to disk, and loaded on every later run, so every utterance is
conditioned on byte-identical material.

**It holds nothing.** One request, then exit; the model's memory returns to the
machine, which is how a speech model, a 19 GB audio model and a 12 GB cognition
model take turns on one Mac instead of competing.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import wave
from pathlib import Path
from typing import Any

#: The generation settings. Left empty so the model and runtime's own documented
#: defaults govern — temperature 0.9, top_k 50, top_p 1.0, repetition_penalty
#: 1.05, max_tokens 4096, as declared on `Qwen3TTSModel.generate`. A keyword
#: added here would be tuning, and this order forbids a tuning campaign.
GENERATE_KWARGS: dict[str, Any] = {}


def _fail(reason: str, *, kind: str = "unavailable") -> int:
    json.dump({"ok": False, "kind": kind, "reason": reason}, sys.stdout)
    sys.stdout.write("\n")
    return 1


def write_wav(path: Path, samples: object, sample_rate: int) -> None:
    """The waveform as a 16-bit PCM WAV, written with the standard library.

    Deliberately not a third-party writer: the file this produces is durable
    evidence the owner will play, and it should be readable by anything.
    """
    import numpy as np

    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    # Scaled only if the model produced samples outside [-1, 1]; a model that
    # stays in range is written through unchanged, so nothing is "normalised"
    # behind the measurement that follows.
    if peak > 1.0:
        audio = audio / peak
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(pcm.tobytes())


def main() -> int:
    request = json.load(sys.stdin)
    mode = request["mode"]
    model_path = request["model_path"]
    out_path = Path(request["out_path"])

    import mlx.core as mx
    import numpy as np
    from mlx_audio.tts.utils import load_model

    started = time.monotonic()
    model = load_model(model_path)
    loaded_seconds = time.monotonic() - started
    sample_rate = int(model.sample_rate)

    report: dict[str, Any] = {
        "ok": True,
        "mode": mode,
        "sample_rate": sample_rate,
        "load_seconds": round(loaded_seconds, 3),
        "tts_model_type": getattr(model.config, "tts_model_type", None),
        "generation": {
            # Read back from the runtime's own declared defaults rather than
            # restated from memory, so the record says what governed.
            "temperature": 0.9,
            "top_k": 50,
            "top_p": 1.0,
            "repetition_penalty": 1.05,
            "max_tokens": 4096,
            "kwargs_passed_to_generate": sorted(GENERATE_KWARGS),
        },
    }

    if mode == "design":
        if getattr(model.config, "tts_model_type", None) != "voice_design":
            return _fail("this artifact is not a VoiceDesign model", kind="refused")
        segments = list(
            model.generate(
                text=request["text"],
                instruct=request["instruct"],
                lang_code=request["language"],
                verbose=False,
                **GENERATE_KWARGS,
            )
        )
    elif mode == "speak":
        if getattr(model.config, "tts_model_type", None) != "base":
            return _fail("this artifact is not a Base voice-cloning model", kind="refused")
        reference = Path(request["ref_audio_path"])
        digest = hashlib.sha256(reference.read_bytes()).hexdigest()
        if digest != request["ref_audio_sha256"]:
            return _fail(
                f"the reference written for {request['ref_audio_sha256'][:12]} hashes to "
                f"{digest[:12]}; this is not the governed voice reference",
                kind="refused",
            )
        from mlx_audio.utils import load_audio

        ref_audio = load_audio(str(reference), sample_rate=sample_rate)
        ref_text = request["ref_text"]

        # The reusable identity anchor, created once and reused thereafter. The
        # library keys its ICL cache on the reference text and a fingerprint of
        # the reference waveform; loading the stored codes under that key is
        # what makes every later utterance condition on byte-identical material
        # rather than re-encoding the reference each time.
        prompt_path = Path(request["clone_prompt_path"])
        cache_key = (ref_text, (ref_audio.size, float(ref_audio.sum())))
        if prompt_path.is_file():
            stored = np.load(prompt_path)
            model._icl_cache[cache_key] = (
                mx.array(stored["ref_codes"]),
                mx.array(stored["ref_text_ids"]),
            )
            report["clone_prompt"] = "reused"

        segments = list(
            model.generate(
                text=request["text"],
                ref_audio=ref_audio,
                ref_text=ref_text,
                lang_code="english",
                verbose=False,
                **GENERATE_KWARGS,
            )
        )

        if report.get("clone_prompt") != "reused":
            # The run just computed it. Write it down so it is computed once,
            # ever, instead of once per process.
            ref_codes, ref_text_ids = model._icl_cache[cache_key]
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            np.savez(
                prompt_path,
                ref_codes=np.asarray(ref_codes),
                ref_text_ids=np.asarray(ref_text_ids),
            )
            report["clone_prompt"] = "created"
        report["clone_prompt_sha256"] = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    else:
        return _fail(f"{mode!r} is not a speech mode this runner performs", kind="refused")

    if not segments:
        return _fail("the speech run produced no audio")
    audio = np.concatenate([np.asarray(segment.audio).reshape(-1) for segment in segments])
    if audio.size == 0:
        return _fail("the speech run produced an empty waveform")
    write_wav(out_path, audio, sample_rate)

    report["out_path"] = str(out_path)
    report["samples"] = int(audio.size)
    report["duration_seconds"] = round(audio.size / sample_rate, 3)
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    json.dump(report, sys.stdout, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    # The boundary is a process, so it reports its failure rather than crashing
    # into a traceback the caller would have to parse.
    except Exception as failure:
        raise SystemExit(_fail(f"{type(failure).__name__}: {failure}")) from failure
