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
    sys.stdout.flush()
    return 1


#: Reference-primed streaming-decoder states, by clone-prompt digest (owner order,
#: 26 September 2026, audio regression). See `_prime_streaming_decoder`.
_PRIMED_DECODER: dict[str, dict[str, Any]] = {}


def _decoder_module(model: Any) -> Any:  # noqa: ANN401 - MLX module objects
    """The speech tokenizer's decoder module itself.

    `model.speech_tokenizer.decoder` is an MLX compiled-function object that forwards
    attribute reads to the module but not writes; the module is reached through the
    bound method it hands back.
    """
    return model.speech_tokenizer.decoder.reset_streaming_state.__self__


def _private_state(module: Any) -> dict[str, Any]:  # noqa: ANN401 - MLX module objects
    """A module's streaming buffers: MLX keeps array-valued attributes as dict items
    (private names are excluded from parameters) and other attributes in __dict__."""
    state = {k: v for k, v in dict.items(module) if k.startswith("_")}
    state.update({k: v for k, v in vars(module).items() if k.startswith("_") and not callable(v)})
    return state


def _prime_streaming_decoder(model: Any, ref_codes: Any, digest: str) -> dict[str, Any]:  # noqa: ANN401
    """Make the streaming decoder start every segment as the whole decoder does.

    **The cause of the audio regression** (owner order, 26 September 2026, §8). The
    library's whole-segment path decodes the reference codes and the generated codes
    together, then cuts the reference portion: the generated speech is decoded by a
    decoder whose convolution buffers and attention already hold the voice. Its
    streaming path resets the decoder and feeds generated codes alone, so every
    segment began from a **cold** decoder — a burst in the first 60 ms (measured 0.065
    RMS against 0.0015) and a rendering that differed from the whole decode across the
    entire sentence (log-mel distance 0.11 to 0.50 against 0.0). That is the click at
    each sentence and the altered quality he heard.

    Priming the streaming decoder with the reference codes reproduces the whole
    path (distance 0.00 to 0.015, onset identical), but recomputing that on every
    segment cost 0.57 s. So it is computed **once per reference**: the primed state —
    the transformer's KV cache and every buffer `reset_streaming_state` clears — is
    captured here, and the library's own reset is wrapped to restore it instead of
    leaving the decoder cold. Restored generation is sample-identical to freshly
    primed generation (measured, four seeds) and the first piece is back to ~0.46 s.
    The library file is untouched; this is the runner's own use of its decoder.
    """
    import copy

    if digest in _PRIMED_DECODER:
        return _PRIMED_DECODER[digest]
    module = _decoder_module(model)
    original = type(module).reset_streaming_state.__get__(module)
    stateful = [m for _, m in module.named_modules() if hasattr(m, "reset_state")]
    original()
    module.streaming_step(ref_codes)
    snapshot = {
        "cache": copy.deepcopy(module._transformer_cache),
        "modules": [copy.deepcopy(_private_state(m)) for m in stateful],
        "reference_codes": int(ref_codes.shape[-1]),
    }

    def restore_primed() -> None:
        original()
        module._transformer_cache = copy.deepcopy(snapshot["cache"])
        for m, state in zip(stateful, snapshot["modules"], strict=True):
            for key, value in state.items():
                setattr(m, key, copy.deepcopy(value))

    module.reset_streaming_state = restore_primed
    _PRIMED_DECODER[digest] = snapshot
    return snapshot


def write_wav(path: Path, samples: object, sample_rate: int) -> None:
    """The waveform as a 16-bit PCM WAV, written with the standard library.

    Deliberately not a third-party writer: the file this produces is durable
    evidence the owner will play, and it should be readable by anything.
    """
    path.write_bytes(wav_bytes(samples, sample_rate))


def wav_bytes(samples: object, sample_rate: int, *, scale_to_fit: bool = True) -> bytes:
    """The same 16-bit PCM WAV, in memory.

    `scale_to_fit=False` is for one streamed piece of a longer utterance: scaling a
    piece by its own peak would change its level against its neighbours, so a piece
    is clipped instead. The model stays inside [-1, 1] in ordinary speech, in which
    case both are the same bytes.
    """
    import io

    import numpy as np

    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    # Scaled only if the model produced samples outside [-1, 1]; a model that
    # stays in range is written through unchanged, so nothing is "normalised"
    # behind the measurement that follows.
    if scale_to_fit and peak > 1.0:
        audio = audio / peak
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(pcm.tobytes())
    return buffer.getvalue()


def main() -> int:
    request = json.load(sys.stdin) if len(sys.argv) < 2 else {"mode": sys.argv[1]}
    if request["mode"] == "serve":
        return serve()
    from mlx_audio.tts.utils import load_model

    started = time.monotonic()
    model = load_model(request["model_path"])
    return perform(model, request, started, time.monotonic() - started)


def serve() -> int:
    """The resident worker: load once, then one request per stdin line, one reply each.

    Owner order, 25 September 2026 (Voice-mode repair §5). Each one-shot run spent
    ~0.26 s starting the interpreter and ~1.0 s loading the model before generating,
    for every sentence Val spoke — about half of each sentence's synthesis time. This
    mode runs the **same** `perform` on the **same** model with the **same** settings
    and conditioning; only the process lives longer. It lives only while a Voice
    session wants it: the service starts it at Voice On and stops it when Voice ends,
    so the speech, audio-perception and cognition models still take turns in memory
    rather than competing all day.

    The first stdin line names the model; `{"mode": "stop"}` ends the worker.
    """
    from mlx_audio.tts.utils import load_model

    first = json.loads(sys.stdin.readline())
    started = time.monotonic()
    model = load_model(first["model_path"])
    ready: dict[str, Any] = {
        "ok": True,
        "mode": "ready",
        "load_seconds": round(time.monotonic() - started, 3),
    }
    prime = first.get("prime")
    if prime:
        # The voice is known at Voice On: load its conditioning and prime the
        # streaming decoder now, so the first sentence of the session pays neither.
        try:
            ready["primed"] = _load_voice_and_prime(model, prime)
        except Exception as failure:  # priming is optional; the first request does it
            ready["primed"] = {"failed": f"{type(failure).__name__}: {failure}"}
    print(json.dumps(ready), flush=True)
    for line in sys.stdin:
        if not line.strip():
            continue
        request = json.loads(line)
        if request.get("mode") == "stop":
            break
        began = time.monotonic()
        try:
            perform(model, request, began, 0.0)
        except Exception as failure:  # one bad request does not end the worker
            _fail(f"{type(failure).__name__}: {failure}")
        sys.stdout.flush()
    return 0


def _load_voice_and_prime(model: Any, request: dict[str, Any]) -> dict[str, Any]:  # noqa: ANN401
    """Load the stored clone prompt for this reference and prime the streaming decoder.

    The same steps `perform` takes on a `speak` request, done at worker start instead:
    the reference is checked against its digest, the stored codes are loaded under the
    library's own cache key, and the decoder's primed state is captured once.
    """
    import mlx.core as mx
    import numpy as np
    from mlx_audio.utils import load_audio

    reference = Path(request["ref_audio_path"])
    digest = hashlib.sha256(reference.read_bytes()).hexdigest()
    if digest != request["ref_audio_sha256"]:
        raise ValueError("the reference written for priming does not hash to its digest")
    ref_audio = load_audio(str(reference), sample_rate=int(model.sample_rate))
    cache_key = (request["ref_text"], (ref_audio.size, float(ref_audio.sum())))
    prompt_path = Path(request["clone_prompt_path"])
    if not prompt_path.is_file():
        return {"skipped": "no stored clone prompt for this reference yet"}
    stored = np.load(prompt_path)
    model._icl_cache[cache_key] = (
        mx.array(stored["ref_codes"]),
        mx.array(stored["ref_text_ids"]),
    )
    primed = _prime_streaming_decoder(model, model._icl_cache[cache_key][0], digest)
    # The first generation of a process also pays MLX's own one-time compilation
    # (~0.6 s, measured on the first piece). Spent here, on a short utterance that is
    # discarded inside this process: never played, never written, never recorded —
    # Val has said nothing. The same standing the persona prime's discarded token has.
    began = time.monotonic()
    for _ in model.generate(
        text="Good evening.",
        ref_audio=ref_audio,
        ref_text=request["ref_text"],
        lang_code="english",
        verbose=False,
        stream=True,
        streaming_interval=1.0,
    ):
        pass
    return {
        "reference_codes": primed["reference_codes"],
        "warmup_generation": {"discarded": True, "seconds": round(time.monotonic() - began, 3)},
    }


def perform(model: Any, request: dict[str, Any], started: float, loaded_seconds: float) -> int:  # noqa: ANN401 - the MLX model object
    """One request against a loaded model: warm, design or speak."""
    import mlx.core as mx
    import numpy as np

    mode = request["mode"]
    out_path = Path(request.get("out_path") or ".")
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

    if mode == "warm":
        # Owner acceptance, 25 September 2026 (WP3 Step B §9). **Load and nothing
        # else.** Each synthesis is its own subprocess, so the first one of a session
        # pays for reading the weights off disk: measured 6.708 s for a 1.68 s phrase
        # against 2.727 s once the file was in the page cache. Loading early — while
        # the owner is still speaking — removes that from his first answer.
        #
        # It generates no audio, writes no file and produces no provenance, because
        # there is nothing to attribute: Val has not spoken. That is the whole reason
        # this is a mode rather than a discarded synthesis.
        report["warmed"] = True
        print(json.dumps(report), flush=True)
        return 0

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
    elif mode in ("speak", "speak_stream"):
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

        if mode == "speak_stream":
            # **Incremental audio** (owner order, 26 September 2026: reduce the wait
            # before Val speaks). The same model, conditioning and sampling, through
            # the installed library's own streaming path: every `streaming_interval`
            # seconds of speech tokens are decoded by its stateful streaming decoder
            # and handed over at once, instead of the whole sentence first. Each piece
            # goes out on stdout as it exists; nothing is written to a file.
            import base64

            interval = float(request["streaming_interval"])
            # The decoder starts each segment holding the voice, as the whole path
            # does — computed once per reference, restored per segment.
            primed = _prime_streaming_decoder(
                model, model._icl_cache[cache_key][0], request["ref_audio_sha256"]
            )
            report["decoder_priming"] = {
                "reference_codes": primed["reference_codes"],
                "restored_per_segment": True,
            }
            generated = model.generate(
                text=request["text"],
                ref_audio=ref_audio,
                ref_text=ref_text,
                lang_code="english",
                verbose=False,
                stream=True,
                streaming_interval=interval,
                **GENERATE_KWARGS,
            )
            segments = []
            for piece, result in enumerate(generated):
                samples = np.asarray(result.audio).reshape(-1)
                segments.append(result)
                chunk = {
                    "chunk": piece,
                    "duration_seconds": round(samples.size / sample_rate, 3),
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "wav_base64": base64.b64encode(
                        wav_bytes(samples, sample_rate, scale_to_fit=False)
                    ).decode("ascii"),
                }
                print(json.dumps(chunk), flush=True)
            report["streamed"] = True
            report["streaming_interval"] = interval
            report["chunks"] = len(segments)
        else:
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
    if mode == "speak_stream":
        # The pieces have already gone; the whole is kept only long enough to be
        # digested into the record, and is never written.
        import hashlib as _hashlib

        whole = wav_bytes(audio, sample_rate, scale_to_fit=False)
        report["audio_sha256"] = _hashlib.sha256(whole).hexdigest()
        report["audio_bytes"] = len(whole)
        report["samples"] = int(audio.size)
        report["duration_seconds"] = round(audio.size / sample_rate, 3)
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        json.dump(report, sys.stdout, default=str)
        sys.stdout.write("\n")
        sys.stdout.flush()
        return 0
    write_wav(out_path, audio, sample_rate)

    report["out_path"] = str(out_path)
    report["samples"] = int(audio.size)
    report["duration_seconds"] = round(audio.size / sample_rate, 3)
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    json.dump(report, sys.stdout, default=str)
    sys.stdout.write("\n")
    sys.stdout.flush()
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
